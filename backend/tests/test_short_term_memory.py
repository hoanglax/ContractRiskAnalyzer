from dataclasses import replace
from hashlib import sha256

import pytest

from application.modules.context_packet import clause_id
from application.modules.ingestion.ingest import Clause, Document, Structure
from application.modules.short_term_memory import RunClauseIndex, RunScope


def make_document(text="cọc | nhà"):
    return Document(text, {"sha256": "upload digest"}, structure=Structure(clauses=[
        Clause("Điều 1", "Nhà", 6, 9),
        Clause("Điều 1", "Cọc", 0, 3, level=2),
    ]))


def test_exact_source_and_stable_clause_ids():
    document = make_document()
    scope = RunScope.for_document("run-a", document)
    assert scope.document_sha256 == sha256(document.text.encode("utf-8")).hexdigest()
    with RunClauseIndex(scope, document) as index:
        clause = index.by_id(scope, "clause-0-3")
        assert clause.clause_id == clause_id(0, 3)
        assert (clause.start, clause.end, clause.text) == (0, 3, "cọc")
        assert (clause.label, clause.heading, clause.level) == ("Điều 1", "Cọc", 2)
        assert clause.provenance == "clause_map"
        document.structure.clauses[1].heading = "changed"
        document.text = "xxx | yyy"
        assert index.at_offset(scope, 2) == clause
    document = make_document()
    document.structure.clauses.reverse()
    with RunClauseIndex(scope, document) as rebuilt:
        assert rebuilt.by_id(scope, clause.clause_id) == clause


def test_separate_runs_with_same_document_and_offsets():
    document = make_document()
    a = RunScope.for_document("run-a", document)
    b = RunScope.for_document("run-b", document)
    with RunClauseIndex(a, document) as first, RunClauseIndex(b, document) as second:
        assert first.at_offset(a, 0) == second.at_offset(b, 0)
        with pytest.raises(ValueError, match="index scope"):
            first.at_offset(b, 0)
        first.release()
        assert second.at_offset(b, 0).text == "cọc"


def test_same_offsets_different_documents_and_wrong_digest():
    first = make_document()
    second = make_document("thu | trả")
    a = RunScope.for_document("run-a", first)
    b = RunScope.for_document("run-a", second)
    with pytest.raises(ValueError, match="Document text"):
        RunClauseIndex(a, second)
    with RunClauseIndex(a, first) as left, RunClauseIndex(b, second) as right:
        assert left.at_offset(a, 0).text == "cọc"
        assert right.at_offset(b, 0).text == "thu"
        with pytest.raises(ValueError, match="index scope"):
            left.by_id(b, "clause-0-3")
        with pytest.raises(ValueError, match="index scope"):
            left.to_references(b, ("clause-0-3",))


@pytest.mark.parametrize("change", [{"run_id": " "}, {"document_sha256": "xyz"}])
def test_invalid_scope(change):
    with pytest.raises(ValueError):
        replace(RunScope.for_document("run-a", make_document()), **change)


def test_references_deduplicate_and_reject_invalid_ids():
    document = make_document()
    scope = RunScope.for_document("run-a", document)
    with RunClauseIndex(scope, document) as index:
        refs = index.to_references(scope, iter(("clause-6-9", "clause-0-3", "clause-6-9")))
        assert (refs.run_id, refs.document_sha256) == (scope.run_id, scope.document_sha256)
        assert refs.clause_ids == ("clause-6-9", "clause-0-3")
        assert index.by_id(scope, "clause-1-2") is None
        for identifier in ("clause-1-2", "garbage", None):
            with pytest.raises(ValueError, match="unknown clause ID"):
                index.to_references(scope, ("clause-6-9", identifier))


@pytest.mark.parametrize("structure", [
    None, Structure(), Structure(clauses=[
        Clause("a", "", 0, 3), Clause("b", "", 2, 6),
    ]), Structure(clauses=[
        Clause("a", "", 0, 3), Clause("b", "", 6, 10),
    ]),
])
def test_missing_or_invalid_structure_is_empty(structure):
    document = replace(make_document(), structure=structure)
    scope = RunScope.for_document("run-a", document)
    with RunClauseIndex(scope, document) as index:
        assert index.by_id(scope, "clause-0-3") is None
        assert index.at_offset(scope, 1) is None
        assert index.overlapping(scope, 0, 9) == ()
        assert index.to_references(scope, ()).clause_ids == ()


def test_overlap_is_half_open_and_keeps_valid_gaps():
    document = make_document()
    scope = RunScope.for_document("run-a", document)
    with RunClauseIndex(scope, document) as index:
        assert [c.text for c in index.overlapping(scope, 2, 7)] == ["cọc", "nhà"]
        assert [c.text for c in index.overlapping(scope, 0, 6)] == ["cọc"]
        assert [c.text for c in index.overlapping(scope, 6, 20)] == ["nhà"]
        assert index.overlapping(scope, 3, 6) == ()
        assert index.overlapping(scope, 1, 1) == ()
        assert index.overlapping(scope, 9, 20) == ()
        assert all(index.at_offset(scope, offset) is None for offset in (-1, 3, 5, 9))
        with pytest.raises(ValueError, match="source span"):
            index.overlapping(scope, 7, 2)


def test_release_on_exception_and_repeated_release():
    document = make_document()
    scope = RunScope.for_document("run-a", document)
    index = RunClauseIndex(scope, document)
    with pytest.raises(LookupError), index:
        raise LookupError("analysis failed")
    assert index._data is None
    index.release()
    for access in (
        lambda: index.by_id(scope, "clause-0-3"),
        lambda: index.at_offset(scope, 0),
        lambda: index.overlapping(scope, 0, 3),
        lambda: index.to_references(scope, ()),
    ):
        with pytest.raises(RuntimeError, match="released"):
            access()
