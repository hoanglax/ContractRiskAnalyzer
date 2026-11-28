"""Select whole contract excerpts for one item before packet construction."""

from dataclasses import dataclass
from typing import Literal

from application.modules.context_packet import ClauseReferences, clause_id
from application.modules.context_packet.models import ContractExcerpt
from application.modules.cross_clause import ClauseRelation, CrossClauseResult, retrieve_cross_clause
from application.modules.detection.finding import Finding, locate
from application.modules.short_term_memory import IndexedClause, RunClauseIndex, RunScope


@dataclass(frozen=True, slots=True)
class SelectionEntry:
    excerpt: ContractExcerpt
    reason: str
    relation: ClauseRelation | None = None

    @property
    def text_bytes(self) -> int:
        return len(self.excerpt.text.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class SelectionDiagnostic:
    reason: str
    clause_id: str | None = None
    source_clause_id: str | None = None
    matching_text: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    role: Literal["anchor", "reference", "neighbor"] | None = None


def _omission(entry: SelectionEntry, reason: str) -> SelectionDiagnostic:
    edge = entry.relation
    if edge is None:
        return SelectionDiagnostic(reason, entry.excerpt.clause_id, role=entry.excerpt.relation)
    return SelectionDiagnostic(
        reason, edge.target_clause_id, edge.source_clause_id, edge.matching_text,
        edge.source_start, edge.source_end, "reference",
    )


@dataclass(frozen=True, slots=True)
class ContextSelection:
    status: Literal["ready", "invalid_primary", "mandatory_over_budget"]
    selected: tuple[SelectionEntry, ...]
    omitted: tuple[SelectionDiagnostic, ...]
    invalid: tuple[SelectionDiagnostic, ...]
    references: ClauseReferences
    budget_bytes: int
    used_bytes: int
    mandatory_bytes: int


def _entry(
    clause: IndexedClause, role: Literal["anchor", "reference", "neighbor"],
    reason: str, relation: ClauseRelation | None = None,
) -> SelectionEntry:
    return SelectionEntry(
        ContractExcerpt(clause.clause_id, clause.label, clause.start, clause.end,
                        clause.text, role, clause.provenance),
        reason, relation,
    )


def _primary_evidence(index, scope, text, primary_clause_ids, findings, invalid):
    primary: dict[str, SelectionEntry] = {}
    sources: dict[str, IndexedClause] = {}
    for identifier in dict.fromkeys(primary_clause_ids):
        clause = index.by_id(scope, identifier)
        if clause is None:
            invalid.append(SelectionDiagnostic("unknown_primary_clause", identifier))
            continue
        sources[identifier] = clause
        primary[identifier] = _entry(clause, "anchor", "primary_clause")
    for finding in findings:
        start, end = finding.char_start, finding.char_end
        if (
            finding.kind == "missing" and start is None and end is None
            and finding.quote is None and finding.clause is None and not finding.elided
        ):
            invalid.append(SelectionDiagnostic("missing_primary_evidence"))
            continue
        if (
            finding.kind != "present" or type(start) is not int or type(end) is not int
            or not 0 <= start < end <= len(text) or not finding.quote
            or locate(text, finding.quote) != (start, end, finding.elided)
        ):
            invalid.append(SelectionDiagnostic("invalid_grounded_evidence"))
            continue
        identifier = clause_id(start, end)
        primary[identifier] = SelectionEntry(
            ContractExcerpt(identifier, finding.clause, start, end, text[start:end], "anchor", "grounded_span"),
            "grounded_evidence",
        )
        for clause in index.overlapping(scope, start, end):
            sources[clause.clause_id] = clause
    if not primary and not invalid:
        invalid.append(SelectionDiagnostic("missing_primary_evidence"))
    return primary, sources


def _explicit_candidates(index, scope, sources, results, invalid):
    candidates = []
    limited = set()
    for result in results:
        refs = result.references
        if (refs.run_id, refs.document_sha256) != (scope.run_id, scope.document_sha256):
            invalid.append(SelectionDiagnostic("foreign_reference_scope"))
            continue
        for diagnostic in result.unresolved:
            source = sources.get(diagnostic.source_clause_id)
            if source and source.start <= diagnostic.source_start < diagnostic.source_end <= source.end and (
                source.text[diagnostic.source_start - source.start:diagnostic.source_end - source.start]
                == diagnostic.matching_text
            ):
                invalid.append(SelectionDiagnostic(
                    diagnostic.reason, source_clause_id=diagnostic.source_clause_id,
                    matching_text=diagnostic.matching_text, source_start=diagnostic.source_start,
                    source_end=diagnostic.source_end,
                ))
            else:
                invalid.append(SelectionDiagnostic("invalid_reference_diagnostic"))
        ids = set(refs.clause_ids)
        capped_ids = {edge.target_clause_id for edge in result.limited}
        for edge in result.relations + result.limited:
            source = sources.get(edge.source_clause_id)
            target = index.by_id(scope, edge.target_clause_id)
            if (
                source is None or target is None or source.clause_id == target.clause_id
                or (target.start, target.end) != (edge.target_start, edge.target_end)
                or not source.start <= edge.source_start < edge.source_end <= source.end
                or source.text[edge.source_start - source.start:edge.source_end - source.start] != edge.matching_text
            ):
                invalid.append(SelectionDiagnostic("invalid_relation", edge.target_clause_id, edge.source_clause_id))
            elif target.clause_id in capped_ids:
                limited.add(target.clause_id)
            elif target.clause_id in ids:
                candidates.append(_entry(target, "reference", edge.reason, edge))
            else:
                invalid.append(SelectionDiagnostic("relation_without_reference", edge.target_clause_id))
        represented = {edge.target_clause_id for edge in result.relations}
        for identifier in dict.fromkeys(refs.clause_ids):
            if identifier not in represented:
                invalid.append(SelectionDiagnostic("reference_without_relation", identifier))
    candidates.sort(key=lambda entry: (
        -entry.relation.priority, entry.relation.source_start, entry.excerpt.start,
        entry.relation.relation_type, entry.relation.reason,
    ))
    return candidates, limited


def select_context(
    index: RunClauseIndex, scope: RunScope, *, budget_bytes: int,
    primary_clause_ids: tuple[str, ...] = (), findings: tuple[Finding, ...] = (),
    cross_clause_results: tuple[CrossClauseResult, ...] | None = None,
) -> ContextSelection:
    """Budget the sum of exact UTF-8 source text bytes, with atomic primary evidence."""
    if type(budget_bytes) is not int or budget_bytes < 0:
        raise ValueError("budget_bytes must be a nonnegative integer")
    text = index.source_text(scope)
    invalid: list[SelectionDiagnostic] = []
    primary, sources = _primary_evidence(index, scope, text, primary_clause_ids, findings, invalid)
    mandatory = sorted(primary.values(), key=lambda entry: (entry.excerpt.start, entry.excerpt.end))
    mandatory_bytes = sum(entry.text_bytes for entry in mandatory)
    if invalid:
        return ContextSelection(
            "invalid_primary", (), (), tuple(invalid), index.to_references(scope, ()),
            budget_bytes, 0, mandatory_bytes,
        )

    clauses = index.clauses(scope)
    if cross_clause_results is None:
        cross_clause_results = tuple(
            retrieve_cross_clause(index, scope, clause.clause_id, top_k=len(clauses))
            for clause in sorted(sources.values(), key=lambda clause: clause.start)
        )
    explicit, limited = _explicit_candidates(index, scope, sources, cross_clause_results, invalid)
    optional: dict[str, SelectionEntry] = {}
    for entry in explicit:
        identifier = entry.excerpt.clause_id
        if identifier not in primary:
            optional.setdefault(identifier, entry)
    neighbors: dict[str, IndexedClause] = {}
    for left, right in zip(clauses, clauses[1:]):
        if left.clause_id in sources and right.clause_id not in sources:
            neighbors[right.clause_id] = right
        if right.clause_id in sources and left.clause_id not in sources:
            neighbors[left.clause_id] = left
    for clause in sorted(neighbors.values(), key=lambda neighbor: neighbor.start):
        if clause.clause_id not in primary and clause.clause_id not in limited:
            optional.setdefault(clause.clause_id, _entry(clause, "neighbor", "adjacent_to_primary"))

    omitted = [
        SelectionDiagnostic("retrieval_limit", identifier, role="reference")
        for identifier in sorted(limited - optional.keys() - primary.keys())
    ]
    if mandatory_bytes > budget_bytes:
        omitted.extend(_omission(entry, "mandatory_over_budget") for entry in mandatory)
        omitted.extend(_omission(entry, "blocked_by_mandatory_budget") for entry in optional.values())
        return ContextSelection(
            "mandatory_over_budget", (), tuple(omitted), tuple(dict.fromkeys(invalid)),
            index.to_references(scope, ()),
            budget_bytes, 0, mandatory_bytes,
        )

    used = mandatory_bytes
    selected = list(mandatory)
    for entry in optional.values():
        cost = entry.text_bytes
        if used + cost > budget_bytes:
            omitted.append(_omission(entry, "over_budget"))
            continue
        selected.append(entry)
        used += cost
    references = index.to_references(scope, (
        entry.excerpt.clause_id for entry in selected if entry.relation is not None
    ))
    return ContextSelection(
        "ready", tuple(selected), tuple(omitted), tuple(dict.fromkeys(invalid)), references,
        budget_bytes, used, mandatory_bytes,
    )
