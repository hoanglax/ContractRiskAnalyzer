from dataclasses import replace

import pytest

from application.modules.cross_clause import retrieve_cross_clause
from application.modules.ingestion.ingest import Clause, Document, Structure
from application.modules.ingestion.structure import segment
from application.modules.short_term_memory import RunClauseIndex, RunScope


def mapped_document(*parts):
    text = "\n".join(parts)
    clauses = []
    offset = 0
    for part in parts:
        heading = part.splitlines()[0]
        clauses.append(Clause(heading, heading, offset, offset + len(part)))
        offset += len(part) + 1
    return Document(text, source={}, structure=Structure(clauses=clauses))


def retrieve(document, *, top_k=3):
    scope = RunScope.for_document("rental-run", document)
    with RunClauseIndex(scope, document) as index:
        source = index.at_offset(scope, 0)
        return retrieve_cross_clause(index, scope, source.clause_id, top_k=top_k)


def test_real_rule_segmentation_and_nonadjacent_reference():
    text = "\n".join([
        "Điều 1. Tiền cọc\nBên thuê nhận lại tiền theo Điều 5.",
        "Điều 2. Sử dụng nhà\nGiữ gìn căn nhà.",
        "Điều 5. Hoàn cọc\nHoàn trong 7 ngày.",
    ])
    structure, _ = segment(text)
    result = retrieve(Document(text, source={}, structure=structure))
    relation, = result.relations
    assert relation.source_clause_id == f"clause-0-{structure.clauses[0].char_end}"
    assert relation.relation_type == "article"
    assert relation.matching_text == text[relation.source_start:relation.source_end] == "theo Điều 5"
    assert text[relation.target_start:relation.target_end] == "Điều 5. Hoàn cọc\nHoàn trong 7 ngày."
    assert result.references.clause_ids == (relation.target_clause_id,)


def test_paragraph_appendix_and_stable_ranking_with_deduplication():
    document = mapped_document(
        "Điều 1. Phạm vi\nXem Phụ lục số 1 và thực hiện theo Điều 7. "
        "Tham chiếu Khoản 2 Điều 7. Quy định tại Điều 12 cũng áp dụng.",
        "Điều 7. Tiền thuê\n1. Trả trước.\n7.2. Quy định ngày đến hạn.",
        "Điều 12. Bàn giao",
        "PHỤ LỤC 1: Danh mục tài sản",
    )
    result = retrieve(document)
    assert [edge.relation_type for edge in result.relations] == ["paragraph", "appendix", "article"]
    assert [edge.matching_text for edge in result.relations] == [
        "Tham chiếu Khoản 2 Điều 7", "Xem Phụ lục số 1", "Quy định tại Điều 12",
    ]
    assert result.relations[0].priority > result.relations[1].priority
    assert result.references.clause_ids == tuple(edge.target_clause_id for edge in result.relations)
    assert retrieve(document) == result
    assert retrieve(document, top_k=1).relations == result.relations[:1]
    assert retrieve(document, top_k=0).relations == ()


@pytest.mark.parametrize("body", ["Khoản 2. Hoàn cọc.", "2) Hoàn cọc.", "7.2. Hoàn cọc."])
def test_paragraph_notation_and_parent_id(body):
    document = mapped_document("Điều 1. Tiền cọc\nTham chiếu Khoản 2 Điều 7.", f"Điều 7. Quy định\n{body}")
    edge, = retrieve(document).relations
    assert edge.target_start == document.structure.clauses[1].char_start
    assert edge.target_end == len(document.text)


@pytest.mark.parametrize(("mention", "targets"), [
    ("theo Điều 5", ("Điều 5. Hoàn cọc", "Điều 5. Chấm dứt")),
    ("tham chiếu Khoản 2 Điều 5", ("Điều 5. Cọc\n2. Hoàn cọc", "Điều 5. Chấm dứt")),
    ("xem Phụ lục 1", ("Phụ lục 1: A", "Phụ lục I: B")),
    ("theo Điều 12", ("Điều 5. Hoàn cọc",)),
    ("theo Điều 1", ("Điều 5. Hoàn cọc",)),
    ("tham chiếu Khoản 2 Điều 5", ("Điều 5. Hoàn cọc\n3. Trả nhà.",)),
    ("tham chiếu Khoản 2 Điều 5", ("Điều 5. Hoàn cọc\n2. Trả nhà.\n2. Hoàn cọc.",)),
    ("tham chiếu Khoản 2 Điều 5", ("Điều 5. Hoàn cọc\nPhụ lục 1\n2. Trả nhà.",)),
    ("xem Phụ lục 1", ("Điều 5. Hoàn cọc\nPhụ lục 1: Thiết bị",)),
    ("theo Điều 5a", ("Điều 5. Hoàn cọc",)),
    ("theo Điều 5.2", ("Điều 5. Hoàn cọc",)),
    ("theo Điều 5-6", ("Điều 5. Hoàn cọc",)),
    ("theo Điều 5 và Điều 6", ("Điều 5. Hoàn cọc",)),
    ("theo Điều 5 của Bộ luật Dân sự", ("Điều 5. Hoàn cọc",)),
    ("theo Điều 5 Luật Nhà ở", ("Điều 5. Hoàn cọc",)),
    ("theo Điều 5 của hợp đồng số 123", ("Điều 5. Hoàn cọc",)),
    ("Điều 5 được nêu ra", ("Điều 5. Hoàn cọc",)),
])
def test_unresolved_mentions_return_no_targets(mention, targets):
    result = retrieve(mapped_document(f"Điều 1. Phạm vi\nNội dung {mention}.", *targets))
    assert result.relations == ()
    assert result.references.clause_ids == ()


def test_wrong_scope_unknown_source_and_release():
    document = mapped_document("Điều 1. Tiền thuê\nTheo Điều 5.", "Điều 5. Hoàn cọc")
    scope = RunScope.for_document("rental-run", document)
    other = RunScope.for_document("rental-run", replace(document, text=document.text + "!"))
    with RunClauseIndex(scope, document) as index:
        source = index.at_offset(scope, 0)
        for wrong_scope in (replace(scope, run_id="other-run"), other):
            with pytest.raises(ValueError, match="index scope"):
                retrieve_cross_clause(index, wrong_scope, source.clause_id)
        assert retrieve_cross_clause(index, scope, "clause-0-0").references.clause_ids == ()
        with pytest.raises(ValueError, match="top_k"):
            retrieve_cross_clause(index, scope, source.clause_id, top_k=-1)
    with pytest.raises(RuntimeError, match="released"):
        retrieve_cross_clause(index, scope, source.clause_id)


def test_empty_index_returns_scoped_empty_references():
    document = Document("Nội dung theo Điều 5.", source={})
    scope = RunScope.for_document("rental-run", document)
    with RunClauseIndex(scope, document) as index:
        result = retrieve_cross_clause(index, scope, "clause-0-20")
    assert result.relations == ()
    assert result.references.run_id == scope.run_id
    assert result.references.document_sha256 == scope.document_sha256
    assert result.references.clause_ids == ()
