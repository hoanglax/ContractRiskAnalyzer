"""Data-only interfaces for a single offline explanation packet."""

from dataclasses import asdict, dataclass
import json
from typing import Literal

from application.modules.detection.finding import Finding
from application.modules.ingestion.ingest import Document
from application.modules.legal_basis.basis import LegalBasis


@dataclass(frozen=True)
class GroundedRisk:
    finding: Finding
    attached_basis: tuple[LegalBasis, ...] = ()


@dataclass(frozen=True)
class ClauseReferences:
    run_id: str
    document_sha256: str
    clause_ids: tuple[str, ...]


@dataclass(frozen=True)
class ContextRequest:
    run_id: str
    document: Document
    domain: str | None
    risks: tuple[GroundedRisk, ...]
    # Trusted adapter references resolved against this document's clause map.
    references: ClauseReferences | None = None


@dataclass(frozen=True)
class PromptBudget:
    context_window: int
    completion_reserve: int = 0
    safety_margin: int = 0
    max_guidance_tokens: int = 2000

    def __post_init__(self):
        values = (self.context_window, self.completion_reserve,
                  self.safety_margin, self.max_guidance_tokens)
        if any(type(value) is not int or value < 0 for value in values) or not self.context_window:
            raise ValueError("Budget values must be nonnegative integers with a positive context window")
        if self.completion_reserve + self.safety_margin > self.context_window:
            raise ValueError("Reserves exceed the context window")

    @property
    def allowance(self) -> int:
        return self.context_window - self.completion_reserve - self.safety_margin


@dataclass(frozen=True)
class ContractExcerpt:
    clause_id: str
    label: str | None
    start: int
    end: int
    text: str
    relation: Literal["anchor", "reference", "neighbor"]
    provenance: Literal["grounded_span", "clause_map"]


@dataclass(frozen=True)
class RiskEvidence:
    code: str
    kind: Literal["present", "missing"]
    issue: str
    evidence_id: str | None


@dataclass(frozen=True)
class LegalPassage:
    citation_id: str
    chunk_id: int
    law: str
    article: int | None
    ref: str
    text: str
    source: str
    risk_codes: tuple[str, ...]


@dataclass(frozen=True)
class SelectionReason:
    matched_codes: tuple[str, ...]
    matched_categories: tuple[str, ...]
    matched_triggers: tuple[tuple[str, ...], ...]
    matched_vocabulary: tuple[str, ...]
    matched_clause_ids: tuple[str, ...]


@dataclass(frozen=True)
class ReasoningGuidance:
    heuristic_id: str
    entry_version: str
    knowledge_version: str
    review_status: Literal["approved", "draft", "pending_review"]
    reason: SelectionReason
    required_context: tuple[str, ...]
    cross_clause_checks: tuple[str, ...]
    reasoning_checklist: tuple[str, ...]
    expected_behavior: str


def encode(data) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class ContextData:
    schema_version: Literal[1]
    run_id: str
    document_sha256: str
    domain: str | None
    risks: tuple[RiskEvidence, ...]
    contract: tuple[ContractExcerpt, ...]
    legal_passages: tuple[LegalPassage, ...] = ()
    guidance: tuple[ReasoningGuidance, ...] = ()

    def to_json(self) -> str:
        """Serialize context data only. No roles, messages or prompt instructions."""
        return encode(asdict(self))


@dataclass(frozen=True)
class Diagnostic:
    code: str
    ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContextPacket:
    data: ContextData | None
    status: Literal["ready", "core_over_budget"]
    estimated_prompt_tokens: int
    diagnostics: tuple[Diagnostic, ...]

    def resolve_citations(self, citation_ids: list[str] | tuple[str, ...]) -> tuple[LegalPassage, ...]:
        """Resolve a structured citation field against this packet's exact allowlist."""
        if not isinstance(citation_ids, (list, tuple)):
            raise ValueError("Expected a list of packet citation IDs")
        allowed = {p.citation_id: p for p in self.data.legal_passages} if self.data else {}
        resolved = []
        for identifier in citation_ids:
            if not isinstance(identifier, str) or identifier not in allowed:
                raise ValueError("Citation ID is not in this packet")
            resolved.append(allowed[identifier])
        return tuple(resolved)
