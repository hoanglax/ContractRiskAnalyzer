import json
import unicodedata
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from application.modules.heuristic_memory import Clause, HeuristicRetriever, load


DOMAIN = "vn_residential_rental"


@pytest.fixture
def seed():
    return load()


@pytest.fixture
def records(seed):
    return seed.model_dump(mode="json")


@pytest.fixture
def load_records():
    def read(records):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "heuristics.json"
            path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
            return load(path)

    return read


@pytest.mark.parametrize(("field", "value", "error"), [
    ("id", "../invalid", "id"),
    ("version", "01.0", "version"),
    ("triggers", [[]], "triggers"),
    ("exclusions", ["..."], "exclusions"),
    ("required_context", ["  "], "required_context"),
    ("risk_codes", ["B-DEP-99"], "taxonomy"),
    ("categories", ["OTHER"], "taxonomy"),
    ("legal_reference_ids", ["unverified"], "unknown verified legal rule"),
    ("citations", [], "Extra inputs"),
    ("kind", "verified_legal_rule", "reasoning_heuristic"),
])
def test_rejects_invalid_records(records, load_records, field, value, error):
    records["heuristics"][0][field] = value
    with pytest.raises(ValueError, match=error):
        load_records(records)


def test_duplicate_id_rejected_across_versions(records, load_records):
    records["heuristics"].append({**records["heuristics"][0], "version": "2.0.0"})
    with pytest.raises(ValueError, match="duplicate record ID"):
        load_records(records)


def test_schema_version_and_reviewer_required(records, load_records):
    records["schema_version"] = "2.0.0"
    with pytest.raises(ValueError, match="schema_version"):
        load_records(records)
    records["schema_version"] = "1.0.0"
    records["heuristics"][0]["provenance"]["status"] = "approved"
    with pytest.raises(ValueError, match="require a reviewer"):
        load_records(records)
    records["heuristics"][0]["provenance"]["reviewer"] = "test reviewer"
    with pytest.raises(ValueError, match="examples to be approved"):
        load_records(records)


def test_seed_is_draft_guidance_without_citations(seed):
    assert 15 <= len(seed.heuristics) <= 20
    assert not seed.legal_rules
    assert all(h.provenance.status == "draft" and h.provenance.origin == "ai_authored"
               and h.kind == "reasoning_heuristic" and not h.legal_reference_ids
               for h in seed.heuristics)
    assert all(e.status == "draft" for h in seed.heuristics for e in h.examples)
    selector = HeuristicRetriever(seed)
    assert selector.select(domain=DOMAIN, text="Hoàn cọc") == []
    hits = selector.select(domain=DOMAIN, text="Hoàn cọc", include_drafts=True)
    assert [hit.id for hit in hits] == ["deposit_refund_clock"]
    assert hits[0].heuristic.legal_reference_ids == ()


def test_legal_record_requires_verification_metadata(records, load_records):
    records["legal_rules"] = [{"kind": "verified_legal_rule", "id": "incomplete_rule"}]
    with pytest.raises(ValueError, match="verified_by"):
        load_records(records)


def test_domain_and_status_filtering(records, load_records):
    entry = next(h for h in records["heuristics"] if h["id"] == "deposit_refund_clock")
    records["heuristics"] = [
        {**entry, "id": status, "version": "1.2.3", "provenance": {
            **entry["provenance"], "status": status, "reviewer": "test reviewer",
        }, "examples": []}
        for status in ("approved", "draft", "pending_review", "retired")
    ]
    records["heuristics"].append({**records["heuristics"][0], "id": "other", "domain": "other_domain"})
    records["version"] = "2.0.0"
    selector = HeuristicRetriever(load_records(records))
    query = {"text": "Hoàn cọc"}
    hits = selector.select(domain=DOMAIN, **query)
    assert [(h.id, h.version, h.knowledge_version) for h in hits] == [("approved", "1.2.3", "2.0.0")]
    assert [h.id for h in selector.select(domain=DOMAIN, include_drafts=True, **query)] == [
        "approved", "draft", "pending_review",
    ]
    assert [h.id for h in selector.select(domain="other_domain", **query)] == ["other"]
    assert selector.select(domain="unknown_domain", **query) == []


def test_trigger_groups_exclusions_and_unicode(seed):
    selector = HeuristicRetriever(seed)

    def ids(text):
        return {h.id for h in selector.select(domain=DOMAIN, text=text, include_drafts=True)}

    assert "termination_notice_clock" not in ids("Chấm dứt")
    assert "termination_notice_clock" in ids(unicodedata.normalize("NFD", "CHẤM DỨT, báo\ntrước"))
    assert "termination_notice_clock" not in ids("Chấm dứt hợp đồng môi giới, báo trước")
    assert "deposit_refund_clock" not in ids("xhoàn cọc")
    assert "deposit_refund_clock" not in ids("Hoàn cọc giữ chỗ mua nhà")


def test_rank_top_k_and_selection_reasons(seed):
    selector = HeuristicRetriever(seed)
    query = dict(domain=DOMAIN, text="Hoàn cọc, hoàn trả tiền cọc, tăng giá thuê, trả nhà và chìa khóa",
                 include_drafts=True)
    assert selector.select(top_k=0, **query) == []
    with pytest.raises(ValueError, match="top_k"):
        selector.select(top_k=-1, **query)
    hits = selector.select(risk_codes=["B-DEP-05"], categories=["TRM"], top_k=2, **query)
    assert [h.id for h in hits] == ["rent_increase", "deposit_refund_clock"]
    assert hits[0].matched_codes == ("B-DEP-05",)
    assert hits[0].matched_categories == ("DEP",)
    assert hits[0].matched_triggers == (("tăng giá thuê",),)
    assert hits[0].matched_vocabulary == ("tăng giá thuê",)
    assert selector.select(categories=["TRM"], top_k=1, **query)[0].id == "return_milestones"
    assert selector.select(**query)[0].id == "deposit_refund_clock"
    reversed_seed = seed.model_copy(update={"heuristics": tuple(reversed(seed.heuristics))})
    assert selector.select(**query) == HeuristicRetriever(reversed_seed).select(**query)
    assert selector.select(domain=DOMAIN, text="", risk_codes=["B-DEP-05"], include_drafts=True) == []


def test_category_only_record_matches_group_from_code(records, load_records):
    entry = records["heuristics"][0]
    entry["risk_codes"] = []
    entry["categories"] = ["DEP"]
    selector = HeuristicRetriever(load_records(records))
    hit, = selector.select(domain=DOMAIN, text="Tiền cọc được cấn trừ", risk_codes=["B-DEP-08"],
                           include_drafts=True)
    assert hit.id == "deposit_identity"
    assert hit.matched_categories == ("DEP",)
    assert hit.matched_codes == ()


@pytest.mark.parametrize(("text", "expected"), [
    ("Bên thuê nhận bàn giao chìa khóa vào ngày bắt đầu thuê.", set()),
    ("Sửa chữa máy lạnh phải thông báo lễ tân để đặt lịch.", set()),
    ("Không mất cọc khi bên thuê chuyển ngày nhận nhà.", set()),
    ("Nếu tự ý bỏ nhà giữa kỳ thì bên cho thuê không hoàn cọc.", {"deposit_forfeiture"}),
    ("Chủ nhà không được tăng tiền thuê trong năm đầu.", set()),
    ("Chủ nhà tăng tiền thuê nếu có thỏa thuận bằng văn bản.", {"rent_increase"}),
    ("Hợp đồng tự động gia hạn nếu không báo trước 45 ngày.", {"renewal_vs_exit"}),
    ("Tiền ký quỹ được gửi lại trong vòng 5 ngày kể từ khi thanh lý.", {"deposit_refund_clock"}),
    ("Người thuê gọi thợ và chi trước, chủ nhà hoàn lại chi phí theo phiếu thu.",
     {"repair_reimbursement"}),
])
def test_context_and_vietnamese_variants(seed, text, expected):
    selector = HeuristicRetriever(seed)
    assert {hit.id for hit in selector.select(
        domain=DOMAIN, text=text, include_drafts=True
    )} == expected


def test_clause_specific_exclusions_and_legacy_text(seed):
    selector = HeuristicRetriever(seed)
    clauses = (
        Clause("broker", "Phí dịch vụ môi giới đã trả một lần."),
        Clause("charges", "Tiền điện tính theo chỉ số công tơ riêng."),
    )
    query = dict(domain=DOMAIN, include_drafts=True)
    explicit, = selector.select(clauses=iter(clauses), **query)
    plain, = selector.select(text=" ".join(clause.text for clause in clauses), **query)
    assert explicit.id == plain.id == "utility_service_fees"
    assert explicit.matched_clause_ids == ("charges",)
    assert plain.matched_clause_ids == ("text-2",)
    assert selector.select(clauses=clauses[:1], **query) == []
    assert selector.select(domain=DOMAIN, clauses=clauses) == []


def test_cross_clause_evidence_and_deterministic_rank(seed):
    clauses = (
        Clause("exit", "Bên thuê trả căn hộ vào ngày cuối tháng."),
        Clause("keys", "Chìa khóa được gửi cho lễ tân theo giấy nhận."),
        Clause("security", "Chủ nhà trả cọc trong vòng 7 ngày sau khi thanh lý."),
    )
    query = dict(domain=DOMAIN, clauses=clauses, include_drafts=True, categories=["TRM"])
    selector = HeuristicRetriever(seed)
    hits = selector.select(**query)
    assert [hit.id for hit in hits] == ["return_milestones", "deposit_refund_clock"]
    assert hits[0].matched_triggers == (("trả căn hộ",), ("chìa khóa",))
    assert hits[0].matched_clause_ids == ("exit", "keys")
    assert hits[1].matched_clause_ids == ("security",)
    reversed_seed = seed.model_copy(update={"heuristics": tuple(reversed(seed.heuristics))})
    assert hits == HeuristicRetriever(reversed_seed).select(**query)


def test_unrelated_clause_events_do_not_form_a_trigger(seed):
    selector = HeuristicRetriever(seed)
    clauses = (
        Clause("guest", "Bên thuê thông báo danh sách khách."),
        Clause("ending", "Hai bên sẽ chấm dứt hợp đồng vào tháng tới."),
    )
    assert selector.select(domain=DOMAIN, clauses=clauses, include_drafts=True) == []


def test_clause_input_validation(seed):
    selector = HeuristicRetriever(seed)
    with pytest.raises(ValueError, match="either text or clauses"):
        selector.select(domain=DOMAIN, text="", clauses=())
    with pytest.raises(ValueError, match="nonempty and unique"):
        selector.select(domain=DOMAIN, clauses=[Clause("a", ""), Clause("a", "")])
    assert selector.select(domain=DOMAIN, clauses=(), include_drafts=True) == []
