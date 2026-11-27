from dataclasses import replace
import json
from unittest.mock import Mock

import pytest

from application.adapters import llm
from application.modules.context_packet import ClauseReferences, GroundedRisk, PromptBudget, clause_id
from application.modules.offline_context import build_offline_context
from application.modules.short_term_memory import RunScope
from evaluate_offline_context import BASELINE, DATASET, compare_with_baseline, evaluate, render_markdown
from tests.test_context_packet import BUDGET, KEYS, RETURN, builder, make_request, synthetic_retriever, tax


def test_offline_pipeline_keeps_offsets_and_packs_distant_reference(builder, make_request, monkeypatch):
    def fail_online(*args, **kwargs):
        pytest.fail("Offline integration attempted a model call")

    monkeypatch.setattr(llm, "chat", fail_online)
    source = f"Điều 1. Trả nhà\n{RETURN} Quy định tại Điều 5."
    target = f"Điều 5. Bàn giao\n{KEYS}"
    request = make_request("B-TRM-06", source, "Điều 2. Giờ yên tĩnh", target)

    def run():
        return build_offline_context(
            request.document, request.run_id, request.risks, builder=builder,
            contract_budget_bytes=500, packet_budget=BUDGET,
        )

    result = run()
    assert result == run()
    assert result.selection.status == result.packet.status == "ready"
    assert result.packet.data.document_sha256 == result.selection.references.document_sha256
    anchor, = (part for part in result.packet.data.contract if part.provenance == "grounded_span")
    excerpt, = (part for part in result.packet.data.contract if part.relation == "reference")
    assert anchor.text == source
    assert excerpt.text == target
    assert result.selection.references.clause_ids == (clause_id(excerpt.start, excerpt.end),)
    for part in result.packet.data.contract:
        assert request.document.text[part.start:part.end] == part.text
    edge, = (entry.relation for entry in result.selection.selected if entry.relation)
    assert request.document.text[edge.source_start:edge.source_end] == "Quy định tại Điều 5"


def test_reused_builder_keeps_same_offsets_scoped_to_each_run(builder, make_request):
    source = f"Điều 1. Trả nhà\n{RETURN} Theo Điều 5."
    target = f"Điều 5. Bàn giao\n{KEYS} (A)"
    a = make_request("B-TRM-06", source, "Điều 2. Giờ yên tĩnh", target)
    b = make_request("B-TRM-06", source, "Điều 2. Giờ yên tĩnh", target.replace("(A)", "(B)"))
    results = [
        build_offline_context(request.document, rid, request.risks, builder=builder,
                              contract_budget_bytes=500, packet_budget=BUDGET)
        for request, rid in ((a, "run-a"), (a, "run-b"), (b, "run-b"))
    ]
    refs = [result.selection.references for result in results]
    assert refs[0].clause_ids == refs[1].clause_ids == refs[2].clause_ids
    assert refs[0].document_sha256 == refs[1].document_sha256 != refs[2].document_sha256
    for (request, rid), result in zip(((a, "run-a"), (a, "run-b"), (b, "run-b")), results):
        scope = RunScope.for_document(rid, request.document)
        assert (result.packet.data.run_id, result.packet.data.document_sha256) == (rid, scope.document_sha256)
        assert "stale_clause_references" not in {d.code for d in result.packet.diagnostics}
        expected = target.replace("(A)", "(B)") if request is b else target
        assert next(part.text for part in result.packet.data.contract if part.relation == "reference") == expected


def test_mandatory_overflow_blocks_builder_and_packet_overflow_is_distinct(builder, make_request):
    request = make_request("B-TRM-06", f"Điều 1. Trả nhà\n{RETURN}")
    unused_builder = Mock()
    blocked = build_offline_context(
        request.document, request.run_id, request.risks, builder=unused_builder,
        contract_budget_bytes=1, packet_budget=BUDGET,
    )
    unused_builder.build.assert_not_called()
    assert blocked.packet is None
    assert blocked.selection.status == "mandatory_over_budget"
    assert blocked.selection.references.clause_ids == ()
    assert blocked.selection.omitted[0].reason == "mandatory_over_budget"

    overflow = build_offline_context(
        request.document, request.run_id, request.risks, builder=builder,
        contract_budget_bytes=500, packet_budget=PromptBudget(1),
    )
    assert overflow.selection.status == "ready"
    assert overflow.packet.status == "core_over_budget"
    assert overflow.packet.data is None


def test_missing_map_and_forged_offsets(builder, make_request):
    request = make_request("B-TRM-06", RETURN)
    document = replace(request.document, structure=None)
    result = build_offline_context(
        document, request.run_id, request.risks, builder=builder,
        contract_budget_bytes=500, packet_budget=BUDGET,
    )
    assert result.selection.references.clause_ids == ()
    assert result.packet.data.contract[0].text == RETURN
    unused_builder = Mock()
    forged = replace(request.risks[0].finding, char_start=1)
    invalid = build_offline_context(
        document, request.run_id, (GroundedRisk(forged),), builder=unused_builder,
        contract_budget_bytes=500, packet_budget=BUDGET,
    )
    assert invalid.selection.status == "invalid_primary"
    assert invalid.selection.invalid[0].reason == "invalid_grounded_evidence"
    unused_builder.build.assert_not_called()


def test_missing_and_ambiguous_are_reported_but_not_forwarded(builder, make_request):
    request = make_request(
        "B-TRM-06", f"Điều 1. Trả nhà\n{RETURN} Theo Điều 2. Theo Điều 9.",
        "Điều 2. Bàn giao", "Điều 2. Nghĩa vụ",
    )
    result = build_offline_context(
        request.document, request.run_id, request.risks, builder=builder,
        contract_budget_bytes=500, packet_budget=BUDGET,
    )
    assert result.packet.status == "ready"
    assert result.selection.references.clause_ids == ()
    assert [d.reason for d in result.selection.invalid] == ["ambiguous_target", "missing_target"]
    assert all(part.relation != "reference" for part in result.packet.data.contract)


def test_strict_uses_only_selected_context_and_preserves_grounded_anchor(builder, make_request):
    request = make_request("B-TRM-06", f"Điều 1. Trả nhà\n{RETURN}", f"Điều 2. Chìa khóa\n{KEYS}")
    quote = replace(request.risks[0].finding, quote=RETURN, char_start=request.document.text.index(RETURN))
    quote = replace(quote, char_end=quote.char_start + len(RETURN))
    risks = (GroundedRisk(quote),)
    budget = len(RETURN.encode("utf-8"))

    def build(**options):
        return build_offline_context(
            request.document, request.run_id, risks, builder=builder,
            packet_budget=BUDGET, **options,
        )

    legacy = build(contract_budget_bytes=budget)
    strict = build(contract_budget_bytes=budget, selection_policy="strict")
    assert strict.selection == legacy.selection
    assert {d.reason for d in strict.selection.omitted} == {"over_budget"}
    assert legacy.packing_diagnostics[0].code == "packet_context_outside_selection"
    assert strict.packing_diagnostics == ()
    anchor, = strict.packet.data.contract
    assert (anchor.text, anchor.start, anchor.end, anchor.provenance) == (
        RETURN, quote.char_start, quote.char_end, "grounded_span",
    )
    with_neighbor = build(contract_budget_bytes=500, selection_policy="strict")
    neighbor, = (part for part in with_neighbor.packet.data.contract if part.relation == "neighbor")
    assert neighbor.text.endswith(KEYS)


@pytest.mark.parametrize("isolate_by", ["run_id", "document_sha256"])
def test_strict_builder_rejects_foreign_refs_and_neighbors(builder, make_request, isolate_by):
    request = make_request("B-TRM-06", RETURN, KEYS)
    scope = RunScope.for_document(request.run_id, request.document)
    target = request.document.structure.clauses[1]
    refs = ClauseReferences(scope.run_id, scope.document_sha256, (clause_id(target.char_start, target.char_end),))
    foreign_value = "other-run" if isolate_by == "run_id" else "0" * 64
    foreign = replace(refs, **{isolate_by: foreign_value})
    packet = builder.build(replace(
        request, references=foreign, selected_neighbors=foreign, selection_policy="strict",
    ), BUDGET)
    assert {"stale_clause_references", "stale_selected_neighbors"} <= {d.code for d in packet.diagnostics}
    anchor, = packet.data.contract
    assert anchor.text == RETURN


def test_new_benchmark_reproduces_both_reports():
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    report = compare_with_baseline(evaluate(dataset), json.loads(BASELINE.read_text(encoding="utf-8")))
    json_path = DATASET.with_name("offline_context_synthetic_v2_results.json")
    markdown_path = json_path.with_suffix(".md")
    assert report["case_count"] == 29
    assert report["invalid_labels_rejected"] == report["invalid_labels_total"] == 8
    assert not any(case["violations"] for case in report["cases"])
    tight_budget = next(case for case in report["cases"] if case["id"] == "budget-01")
    assert not tight_budget["selection"]["references"]["clause_ids"]
    assert tight_budget["packet_relevant_ids"] == tight_budget["packet_only_clause_ids"] == []
    cases = {case["id"]: case for case in report["comparison"]}
    assert cases["budget-01"]["regressions"] == ["relevant_packet_context_lost"]
    assert cases["appendix-03"]["relevant_references_gained"]
    assert cases["format-01"]["relevant_references_gained"]
    assert json.loads(json.dumps(report)) == json.loads(json_path.read_text(encoding="utf-8"))
    assert render_markdown(report) == markdown_path.read_text(encoding="utf-8")
