"""Pack validated, source-aligned data without invoking a model or legal search."""

from collections.abc import Callable, Iterator
from dataclasses import asdict, replace
from hashlib import sha256
import re

from application.modules.detection.finding import locate
from application.modules.heuristic_memory import Clause, HeuristicRetriever
from application.modules.legal_basis.basis import NOT_STATUTE
from application.modules.taxonomy import taxonomy

from .models import (
    ContextData, ContextPacket, ContextRequest, ContractExcerpt, Diagnostic, LegalPassage,
    PromptBudget, ReasoningGuidance, RiskEvidence, SelectionReason, encode,
)


def clause_id(start: int, end: int) -> str:
    return f"clause-{start}-{end}"


def _byte_count(text: str) -> int:
    return len(text.encode("utf-8"))


def _grounded_evidence(request, tax):
    """Recheck source offsets without mutating or re-grounding upstream findings."""
    text = request.document.text
    risks, anchors = [], {}
    for risk in request.risks:
        finding = risk.finding
        if finding.code not in tax.by_code or not finding.issue.strip():
            raise ValueError("Expected a grounded finding with a taxonomy code and issue")
        evidence_id = None
        if finding.kind == "present":
            start, end = finding.char_start, finding.char_end
            located = locate(text, finding.quote) if finding.quote else None
            if (
                start is None or end is None or not 0 <= start < end <= len(text)
                or located != (start, end, finding.elided)
            ):
                raise ValueError("Finding evidence does not match the active document")
            evidence_id = clause_id(start, end)
            anchors[evidence_id] = ContractExcerpt(
                evidence_id, finding.clause, start, end, text[start:end], "anchor", "grounded_span"
            )
        elif finding.kind != "missing" or any(
            value is not None for value in (finding.char_start, finding.char_end, finding.quote)
        ):
            raise ValueError("Expected a present finding or a missing finding without evidence")
        risks.append(RiskEvidence(finding.code, finding.kind, finding.issue, evidence_id))
    ordered = tuple(sorted(anchors.values(), key=lambda item: (item.start, item.end)))
    if len(risks) > 1:
        end = -1
        for index, anchor in enumerate(ordered):
            if index and anchor.start >= end:
                raise ValueError("Findings in a packet must form one overlapping explanation item")
            end = max(end, anchor.end)
        if any(risk.kind == "missing" for risk in risks):
            raise ValueError("A missing finding must have its own packet")
    return tuple(risks), ordered


def _legal_candidates(request, diagnostics):
    """Validate attachment shape within the trusted upstream attachment boundary."""
    by_id = {}
    conflicts = set()
    for risk in request.risks:
        for basis in risk.attached_basis:
            if (
                type(basis.chunk_id) is not int or basis.chunk_id <= 0
                or not isinstance(basis.law, str) or not re.fullmatch(r"[a-z0-9_]+", basis.law)
                or basis.law in NOT_STATUTE
                or (basis.dieu is not None and (type(basis.dieu) is not int or basis.dieu <= 0))
                or not isinstance(basis.ref, str)
                or not isinstance(basis.text, str) or not basis.text.strip()
                or basis.source not in ("taxonomy", "retrieval")
            ):
                diagnostics.append(Diagnostic("invalid_legal_attachment"))
                continue
            passage = LegalPassage(
                "", basis.chunk_id, basis.law, basis.dieu, basis.ref, basis.text,
                basis.source, (risk.finding.code,),
            )
            previous = by_id.get(basis.chunk_id)
            if previous is None:
                by_id[basis.chunk_id] = passage
            elif (previous.law, previous.article, previous.ref, previous.text) != (
                passage.law, passage.article, passage.ref, passage.text
            ):
                conflicts.add(basis.chunk_id)
            else:
                codes = tuple(dict.fromkeys(previous.risk_codes + passage.risk_codes))
                by_id[basis.chunk_id] = replace(previous, risk_codes=codes)
    for chunk_id in sorted(conflicts):
        diagnostics.append(Diagnostic("conflicting_legal_attachment", (str(chunk_id),)))
    return (passage for chunk_id, passage in by_id.items() if chunk_id not in conflicts)


class ContextPacketBuilder:
    def __init__(
        self, retriever: HeuristicRetriever, *, tax: taxonomy.Taxonomy | None = None,
        count_tokens: Callable[[str], int] = _byte_count,
        max_guidance: int = 2, candidate_limit: int = 8,
        max_references: int = 3, max_window_chars: int = 6000,
    ):
        limits = (max_guidance, candidate_limit, max_references, max_window_chars)
        if any(type(value) is not int or value < 0 for value in limits):
            raise ValueError("Builder limits must be nonnegative integers")
        self._retriever = retriever
        self._tax = tax if tax is not None else taxonomy.load()
        self._count_tokens = count_tokens
        self._max_guidance = max_guidance
        self._candidate_limit = candidate_limit
        self._max_references = max_references
        self._max_window_chars = max_window_chars
        self._synthetic_drafts = False

    @classmethod
    def for_synthetic_tests(cls, retriever: HeuristicRetriever, **options):
        """Opt in explicitly with a caller-supplied synthetic test snapshot."""
        builder = cls(retriever, **options)
        builder._synthetic_drafts = True
        return builder

    def build(self, request: ContextRequest, budget: PromptBudget) -> ContextPacket:
        if request.selection_policy not in ("legacy", "strict"):
            raise ValueError("Unknown context selection policy")
        if not request.run_id.strip() or not request.risks:
            raise ValueError("Expected a run ID and at least one grounded finding")
        risks, anchors = _grounded_evidence(request, self._tax)
        diagnostics = [
            Diagnostic("missing_contract_evidence", (risk.code,))
            for risk in risks if risk.evidence_id is None
        ]
        data = ContextData(
            1, request.run_id, sha256(request.document.text.encode("utf-8")).hexdigest(),
            request.domain, risks, anchors,
        )
        size = self._measure(data.to_json())
        if size > budget.allowance:
            diagnostics.append(Diagnostic("core_over_budget"))
            return ContextPacket(None, "core_over_budget", size, tuple(diagnostics))

        for passage in _legal_candidates(request, diagnostics):
            numbered = replace(passage, citation_id=f"L{len(data.legal_passages) + 1}")
            updated = replace(data, legal_passages=data.legal_passages + (numbered,))
            if self._measure(updated.to_json()) <= budget.allowance:
                data = updated
            else:
                diagnostics.append(Diagnostic("legal_passage_over_budget", (str(passage.chunk_id),)))
        available_codes = {code for passage in data.legal_passages for code in passage.risk_codes}
        for code in dict.fromkeys(risk.code for risk in risks):
            if code not in available_codes:
                diagnostics.append(Diagnostic("missing_legal_evidence", (code,)))

        if not anchors or not request.domain:
            diagnostics.append(Diagnostic("guidance_skipped_missing_anchor_or_domain"))
        else:
            data = self._pack_guidance(request, data, budget, diagnostics)

        return ContextPacket(data, "ready", self._measure(data.to_json()), tuple(diagnostics))

    def _measure(self, serialized: str) -> int:
        count = self._count_tokens(serialized)
        if type(count) is not int or count < 0:
            raise ValueError("Token counter must return a nonnegative integer")
        return count

    def _windows(self, request, data, diagnostics) -> Iterator[tuple[ContractExcerpt, ...]]:
        text = request.document.text
        spans = sorted(request.document.structure.clauses, key=lambda c: (c.char_start, c.char_end))
        if any(not 0 <= span.char_start < span.char_end <= len(text) for span in spans) or any(
            a.char_end > b.char_start for a, b in zip(spans, spans[1:])
        ):
            diagnostics.append(Diagnostic("invalid_clause_map"))
            spans = []
        clauses = tuple(ContractExcerpt(
            clause_id(span.char_start, span.char_end), span.label, span.char_start,
            span.char_end, text[span.char_start:span.char_end], "neighbor", "clause_map",
        ) for span in spans)
        by_id = {part.clause_id: part for part in clauses}
        references = []
        source = request.references
        reference_ids = ()
        if source is not None:
            if (source.run_id, source.document_sha256) != (data.run_id, data.document_sha256):
                diagnostics.append(Diagnostic("stale_clause_references"))
            else:
                reference_ids = source.clause_ids
        for identifier in dict.fromkeys(reference_ids):
            if identifier not in by_id:
                diagnostics.append(Diagnostic("unresolved_clause_reference", (identifier,)))
            elif len(references) >= self._max_references:
                diagnostics.append(Diagnostic("clause_reference_limit", (identifier,)))
            else:
                references.append(replace(by_id[identifier], relation="reference"))

        if request.selection_policy == "strict":
            neighbors = request.selected_neighbors
            if neighbors is not None:
                if (neighbors.run_id, neighbors.document_sha256) != (data.run_id, data.document_sha256):
                    diagnostics.append(Diagnostic("stale_selected_neighbors"))
                else:
                    # A clause capped as a reference cannot re-enter under a different role.
                    for identifier in dict.fromkeys(neighbors.clause_ids):
                        if identifier not in by_id:
                            diagnostics.append(Diagnostic("unresolved_selected_neighbor", (identifier,)))
                        elif identifier not in reference_ids:
                            references.append(by_id[identifier])
            for anchor in data.contract:
                for part in references:
                    if max(anchor.start, part.start) >= min(anchor.end, part.end):
                        yield tuple(sorted((anchor, part), key=lambda excerpt: excerpt.start))
                yield (anchor,)
            return

        for anchor in data.contract:
            indices = [
                i for i, part in enumerate(clauses)
                if part.start < anchor.end and anchor.start < part.end
            ]
            if not indices:
                yield (anchor,)
                continue
            for i in indices:
                primary = replace(clauses[i], relation="anchor")
                if len(primary.text) > self._max_window_chars:
                    diagnostics.append(Diagnostic("clause_truncated_to_grounded_span", (primary.clause_id,)))
                    primary = anchor
                for reference in references:
                    if max(primary.start, reference.start) >= min(primary.end, reference.end):
                        yield tuple(sorted((primary, reference), key=lambda part: part.start))
                before = clauses[max(0, i - 1):i] if primary.provenance == "clause_map" else ()
                after = clauses[i + 1:i + 2] if primary.provenance == "clause_map" else ()
                yield before + (primary,) + after
                if before or after:
                    yield (primary,)

    def _pack_guidance(self, request, data, budget, diagnostics):
        allowed = {"approved", "draft", "pending_review"} if self._synthetic_drafts else {"approved"}
        codes = tuple(dict.fromkeys(risk.code for risk in data.risks if risk.evidence_id is not None))
        known_windows, packed = set(), set()
        for window in self._windows(request, data, diagnostics):
            ids = tuple(part.clause_id for part in window)
            if ids in known_windows:
                continue
            known_windows.add(ids)
            if sum(len(part.text) for part in window) > self._max_window_chars:
                diagnostics.append(Diagnostic("retrieval_window_limit", ids))
                continue
            by_id = {part.clause_id: part for part in window}
            hits = self._retriever.select(
                domain=request.domain, clauses=tuple(Clause(p.clause_id, p.text) for p in window),
                risk_codes=codes, top_k=self._candidate_limit,
                include_drafts=self._synthetic_drafts,
            )
            for hit in hits:
                key = (hit.id, hit.version)
                if key in packed:
                    continue
                if hit.heuristic.provenance.status not in allowed:
                    diagnostics.append(Diagnostic("unapproved_guidance", (hit.id,)))
                    continue
                support = tuple(by_id[identifier] for identifier in hit.matched_clause_ids if identifier in by_id)
                if (
                    len(support) != len(hit.matched_clause_ids)
                    or not any(p.relation in ("anchor", "reference") for p in support)
                    or not (hit.matched_codes or hit.matched_categories)
                ):
                    diagnostics.append(Diagnostic("guidance_outside_item_scope", (hit.id,)))
                    continue
                if len(data.guidance) >= self._max_guidance:
                    diagnostics.append(Diagnostic("guidance_count_limit", (hit.id,)))
                    continue
                heuristic = hit.heuristic
                guidance = ReasoningGuidance(
                    hit.id, hit.version, hit.knowledge_version, heuristic.provenance.status,
                    SelectionReason(hit.matched_codes, hit.matched_categories, hit.matched_triggers,
                                    hit.matched_vocabulary, hit.matched_clause_ids),
                    heuristic.required_context, heuristic.cross_clause_checks,
                    heuristic.reasoning_checklist, heuristic.expected_behavior,
                )
                updated_guidance = data.guidance + (guidance,)
                if self._measure(encode([asdict(item) for item in updated_guidance])) > budget.max_guidance_tokens:
                    diagnostics.append(Diagnostic("guidance_over_budget", (hit.id,)))
                    continue
                excerpts = {part.clause_id: part for part in data.contract}
                for part in support:
                    excerpts.setdefault(part.clause_id, part)
                updated = replace(
                    data, guidance=updated_guidance,
                    contract=tuple(sorted(excerpts.values(), key=lambda part: (part.start, part.end))),
                )
                if self._measure(updated.to_json()) > budget.allowance:
                    diagnostics.append(Diagnostic("guidance_and_evidence_over_budget", (hit.id,)))
                    continue
                data = updated
                packed.add(key)
        if not data.guidance:
            diagnostics.append(Diagnostic("no_guidance_packed"))
        return data
