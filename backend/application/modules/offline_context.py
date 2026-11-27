"""Offline P0–P3 integration for one explanation item."""

from dataclasses import dataclass, replace
from typing import Literal

from application.modules.context_packet import (
    ContextPacket, ContextPacketBuilder, ContextRequest, GroundedRisk, PromptBudget,
)
from application.modules.context_selection import ContextSelection, select_context
from application.modules.context_packet.models import Diagnostic
from application.modules.ingestion.ingest import Document, Structure
from application.modules.short_term_memory import RunClauseIndex, RunScope


@dataclass(frozen=True, slots=True)
class OfflineContextResult:
    selection: ContextSelection
    packet: ContextPacket | None
    packing_diagnostics: tuple[Diagnostic, ...] = ()


def build_offline_context(
    document: Document, run_id: str, risks: tuple[GroundedRisk, ...], *,
    builder: ContextPacketBuilder, contract_budget_bytes: int, packet_budget: PromptBudget,
    domain: str | None = "vn_residential_rental",
    selection_policy: Literal["legacy", "strict"] = "legacy",
) -> OfflineContextResult:
    """Build a packet from grounded findings for one item, keeping both budget outcomes."""
    scope = RunScope.for_document(run_id, document)
    with RunClauseIndex(scope, document) as index:
        # P2 discovers source clauses and runs P1 against this index when no results are supplied.
        selection = select_context(
            index, scope, findings=tuple(risk.finding for risk in risks), budget_bytes=contract_budget_bytes,
        )
        neighbors = index.to_references(scope, (
            entry.excerpt.clause_id for entry in selection.selected if entry.excerpt.relation == "neighbor"
        )) if selection_policy == "strict" else None
    if selection.status != "ready":
        return OfflineContextResult(selection, None)

    # P0 accepts absent clause maps. Give Builder its normal empty Structure in that case.
    if getattr(document.structure, "clauses", None) is None:
        document = replace(document, structure=Structure())
    request = ContextRequest(
        run_id, document, domain, risks, selection.references,
        selection_policy=selection_policy, selected_neighbors=neighbors,
    )
    packet = builder.build(request, packet_budget)
    chosen = {entry.excerpt.clause_id for entry in selection.selected}
    packed = {part.clause_id for part in packet.data.contract} if packet.data else set()
    diagnostics = tuple(
        Diagnostic(code, tuple(sorted(ids)))
        for code, ids in (
            ("selected_context_not_packed", chosen - packed),
            ("packet_context_outside_selection", packed - chosen),
        ) if ids
    )
    return OfflineContextResult(selection, packet, diagnostics)
