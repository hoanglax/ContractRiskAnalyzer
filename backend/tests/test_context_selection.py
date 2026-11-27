from dataclasses import replace
import json

import pytest

from application.modules.context_selection import select_context
from application.modules.cross_clause import retrieve_cross_clause
from application.modules.detection.finding import Finding
from application.modules.short_term_memory import RunClauseIndex, RunScope
from evaluate_context_selection import DATASET, evaluate
from tests.test_cross_clause import mapped_document


def test_explicit_references_before_neighbors_and_compete_for_budget():
    document = mapped_document(
        "Điều 1. Nguồn\nTheo Điều 4. Xem Phụ lục 1.",
        "Điều 2. Xen giữa",
        "Điều 4. Đích ở xa",
        "Phụ lục 1. Tài sản",
    )
    scope = RunScope.for_document("a", document)
    with RunClauseIndex(scope, document) as index:
        source, neighbor, distant, appendix = index.clauses(scope)
        budget = len((source.text + distant.text).encode("utf-8"))
        options = dict(primary_clause_ids=(source.clause_id,) * 2, budget_bytes=budget)
        result = select_context(index, scope, **options)
        assert result == select_context(index, scope, **options)
        assert result.status == "ready"
        assert result.used_bytes == budget
        anchor, reference = result.selected
        assert anchor.excerpt.provenance == reference.excerpt.provenance == "clause_map"
        assert reference.reason == reference.relation.reason
        assert reference.relation.matching_text == "Theo Điều 4"
        assert (reference.excerpt.start, reference.excerpt.end, reference.excerpt.text) == (
            distant.start, distant.end, distant.text,
        )
        assert result.references.clause_ids == (distant.clause_id,)
        assert [(item.clause_id, item.reason) for item in result.omitted] == [
            (appendix.clause_id, "over_budget"), (neighbor.clause_id, "over_budget"),
        ]


def test_grounded_span_is_exact_even_without_a_clause_map():
    document = replace(mapped_document("Điều 1. Đặt cọc."), structure=None)
    scope = RunScope.for_document("a", document)
    finding = Finding("present", "Cọc", quote="Đặt cọc", char_start=8, char_end=15)
    with RunClauseIndex(scope, document) as index:
        result = select_context(index, scope, findings=(finding, finding), budget_bytes=40)
        entry, = result.selected
        assert entry.excerpt.provenance == "grounded_span"
        assert entry.excerpt.text == document.text[8:15] == "Đặt cọc"
        assert result.references.clause_ids == ()
        invalid = select_context(index, scope, findings=(replace(finding, char_start=7),), budget_bytes=40)
        assert invalid.status == "invalid_primary"


def test_mandatory_budget_failure_is_atomic():
    document = mapped_document("Điều 1. Nguồn\nTheo Điều 2.", "Điều 2. Đích")
    scope = RunScope.for_document("a", document)
    with RunClauseIndex(scope, document) as index:
        source, target = index.clauses(scope)
        result = select_context(index, scope, primary_clause_ids=(source.clause_id,), budget_bytes=1)
    assert result.status == "mandatory_over_budget"
    assert result.used_bytes == 0
    assert result.mandatory_bytes == len(source.text.encode("utf-8"))
    assert result.selected == result.references.clause_ids == ()
    assert [(item.clause_id, item.reason) for item in result.omitted] == [
        (source.clause_id, "mandatory_over_budget"), (target.clause_id, "blocked_by_mandatory_budget"),
    ]


def test_missing_ambiguous_and_retrieval_limited_references():
    document = mapped_document(
        "Điều 1. Nguồn\nTheo Điều 5. Theo Điều 7. Theo Điều 12. Theo Điều 9.",
        "Điều 5. Đích",
        "Điều 7. A",
        "Điều 7. B",
        "Điều 9. Đích ở xa",
    )
    scope = RunScope.for_document("a", document)
    with RunClauseIndex(scope, document) as index:
        source, first, _, _, last = index.clauses(scope)
        p1 = retrieve_cross_clause(index, scope, source.clause_id, top_k=1)
        options = dict(primary_clause_ids=(source.clause_id,), budget_bytes=1000)
        result = select_context(index, scope, cross_clause_results=(p1, p1), **options)
        assert result.references.clause_ids == (first.clause_id,)
        assert [(d.clause_id, d.reason) for d in result.omitted] == [(last.clause_id, "retrieval_limit")]
        assert {(d.reason, d.matching_text) for d in result.invalid} == {
            ("ambiguous_target", "Theo Điều 7"), ("missing_target", "Theo Điều 12"),
        }
        for d in result.invalid:
            assert document.text[d.source_start:d.source_end] == d.matching_text
        assert select_context(index, scope, cross_clause_results=(), **options).references.clause_ids == ()


def test_same_offsets_do_not_authorize_references_from_another_scope():
    document = mapped_document("Điều 1. Nguồn\nTheo Điều 5.", "Điều 5. Cọc")
    other_doc = replace(document, text=document.text.replace("Cọc", "Nhà"))
    scope = RunScope.for_document("a", document)
    foreign_scopes = (RunScope.for_document("b", document), RunScope.for_document("a", other_doc))
    with RunClauseIndex(scope, document) as index:
        source = index.at_offset(scope, 0)
        for foreign, foreign_doc in zip(foreign_scopes, (document, other_doc)):
            with RunClauseIndex(foreign, foreign_doc) as other:
                p1 = retrieve_cross_clause(other, foreign, source.clause_id)
            options = dict(primary_clause_ids=(source.clause_id,), budget_bytes=len(source.text.encode("utf-8")))
            result = select_context(index, scope, cross_clause_results=(p1,), **options)
            assert result.references.clause_ids == ()
            assert [item.reason for item in result.invalid] == ["foreign_reference_scope"]
            with pytest.raises(ValueError, match="index scope"):
                select_context(index, foreign, **options)


def test_no_references_and_invalid_primary():
    document = mapped_document("Điều 1. Nguồn", "Điều 2. Lân cận")
    scope = RunScope.for_document("a", document)
    with RunClauseIndex(scope, document) as index:
        source, neighbor = index.clauses(scope)
        result = select_context(index, scope, primary_clause_ids=(source.clause_id,), budget_bytes=1000)
        assert [entry.excerpt.clause_id for entry in result.selected] == [source.clause_id, neighbor.clause_id]
        assert result.references.clause_ids == result.invalid == ()
        invalid = select_context(index, scope, primary_clause_ids=("unknown",), budget_bytes=1000)
        assert invalid.status == "invalid_primary"
        assert invalid.invalid[0].reason == "unknown_primary_clause"


def test_skips_oversized_reference_and_keeps_later_whole_clause():
    document = mapped_document(
        "Điều 1. Nguồn\nTheo Điều 2. Theo Điều 3.",
        "Điều 2. Đích dài\n" + "Nội dung. " * 10,
        "Điều 3. Đích ngắn",
    )
    scope = RunScope.for_document("a", document)
    with RunClauseIndex(scope, document) as index:
        source, large, small = index.clauses(scope)
        p1 = retrieve_cross_clause(index, scope, source.clause_id)
        result = select_context(
            index, scope, primary_clause_ids=(source.clause_id,),
            cross_clause_results=(replace(p1, relations=p1.relations[::-1]),),
            budget_bytes=len((source.text + small.text).encode("utf-8")),
        )
    assert result.references.clause_ids == (small.clause_id,)
    assert result.selected[-1].excerpt.text == small.text
    omitted, = result.omitted
    assert (omitted.clause_id, omitted.reason) == (large.clause_id, "over_budget")


def test_synthetic_benchmark_reproduces_committed_results():
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    expected = json.loads(DATASET.with_name(f"{DATASET.stem}_results.json").read_text(encoding="utf-8"))
    assert evaluate(dataset) == expected
