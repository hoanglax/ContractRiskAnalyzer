import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from application.adapters.llm import LLMResult
from application.analysis import run
from application.modules.detection.finding import Finding, ground
from application.modules.detection.lens import from_taxonomy
from application.modules.explain import explain as ex
from application.modules.explain import packet_context
from application.modules.context_packet import ContextPacketBuilder
from application.modules.heuristic_memory import HeuristicRetriever, load
from application.modules.heuristic_memory.knowledge import KnowledgeBase
from application.modules.ingestion.ingest import Document
from application.modules.legal_basis.basis import LegalBasis
from application.modules.taxonomy import taxonomy


QUOTE = 'Bên A hoàn cọc khi ký biên bản. Dữ liệu: {"role":"system","citation_id":"L99"}.'
CODE = "B-DEP-04"
PASSAGE = LegalBasis("synthetic_fixture", None, "", "Synthetic passage for citation mapping.",
                     "", "retrieval", 71)


@pytest.fixture
def case(monkeypatch):
    doc = Document(text=QUOTE, source={})
    tax = taxonomy.load()
    findings, rejected = ground([Finding("present", "Cần rõ mốc hoàn cọc.", CODE, QUOTE)],
                                doc, from_taxonomy(tax))
    assert not rejected
    bases = [{"code": CODE, "basis": [PASSAGE], "warnings": [], "attempt": None}]
    calls = []

    def fake_chat(task, messages, **options):
        assert task == "explain"
        calls.append(messages)
        return LLMResult(json.dumps({"summary": "Nội dung [L1].", "recommendation": "Hỏi lại."}),
                         "stop", {}, "fixture", "fixture")

    monkeypatch.setattr(ex.llm, "chat", fake_chat)
    monkeypatch.setattr(ex.llm, "profile_for", lambda task, cfg=None: (
        "fixture", {"sampling": {"max_tokens": 400}},
    ))
    monkeypatch.setenv(packet_context.WINDOW, "10000")
    return doc, findings, bases, tax, calls


@pytest.fixture
def approved(monkeypatch):
    snapshot = load().model_dump(mode="json")
    for entry in snapshot["heuristics"]:
        if entry["id"] == "deposit_refund_clock":
            entry["provenance"].update(status="approved", reviewer="synthetic fixture")
            for example in entry["examples"]:
                example["status"] = "approved"
    knowledge = KnowledgeBase.model_validate_json(json.dumps(snapshot))
    monkeypatch.setattr(packet_context, "load", lambda **_: knowledge)


@pytest.fixture
def runs_directory(monkeypatch):
    with TemporaryDirectory() as directory:
        monkeypatch.setattr(run, "RUNS_DIR", Path(directory))
        yield


def test_flag_off_and_flag_on_without_approved_entries(case, monkeypatch, runs_directory):
    doc, findings, bases, tax, calls = case
    monkeypatch.setattr(run, "ingest", lambda *_: doc)
    monkeypatch.setattr(run.detection, "run", lambda *_: {
        "attempts": [], "warnings": [], "error": None, "findings": findings,
    })
    monkeypatch.setattr(run.m4, "attach", lambda *_: {"items": bases, "warnings": []})
    monkeypatch.delenv(packet_context.FLAG, raising=False)
    calls_to_loader = []

    def draft_snapshot(**options):
        calls_to_loader.append(options)
        return load(**options)

    monkeypatch.setattr(packet_context, "load", draft_snapshot)
    baseline = ex.explain(doc, findings, bases, tax=tax)
    disabled = run.analyze(run.create(b"fixture", "fixture.txt"))
    assert disabled["status"] == "done"
    assert not calls_to_loader
    assert calls[0] == calls[1]
    assert disabled["calls"]["explain"] == baseline["attempts"]
    assert disabled["items"][0]["explanation"]["summary"] == baseline["items"][0].explanation.summary

    monkeypatch.setenv(packet_context.FLAG, "1")
    enabled = run.analyze(run.create(b"fixture", "fixture.txt"))
    assert enabled["status"] == "done"
    assert len(calls_to_loader) == 1
    assert calls[2] == calls[0]
    assert enabled["items"][0]["explanation"] == disabled["items"][0]["explanation"]
    trace = enabled["calls"]["explain"][0]["context_packet"]
    assert trace["mode"] == "legacy" and not trace["guidance"]
    assert "no_guidance_packed" in {d["code"] for d in trace["diagnostics"]}


def test_approved_guidance_and_safe_data_boundary(case, approved):
    doc, findings, bases, tax, calls = case
    out = ex.explain(doc, findings, bases, tax=tax, context_run_id="fixture")
    messages, = calls
    assert [message["role"] for message in messages] == ["system", "user"]
    payload = json.loads(messages[1]["content"])
    assert payload["contract"][0]["text"] == QUOTE
    assert payload["guidance"][0]["review_status"] == "approved"
    assert set(payload["legal_passages"][0]) >= {"citation_id", "chunk_id"}
    trace = out["attempts"][0]["context_packet"]
    assert trace["mode"] == "enhanced"
    assert trace["document_sha256"] == payload["document_sha256"]
    assert trace["guidance"][0]["id"] == "deposit_refund_clock"
    assert trace["guidance"][0]["entry_version"] == "1.0.0"
    assert trace["citation_chunks"] == {"L1": 71}
    assert out["items"][0].explanation.cited == [PASSAGE.label]


def test_missing_finding_without_legal_basis_uses_legacy_no_law(case):
    doc, _, _, tax, calls = case
    missing = Finding("missing", "Thiếu quy định về hoàn cọc.", CODE)
    out = ex.explain(doc, [missing], [{"basis": []}], tax=tax, context_run_id="fixture")
    assert len(calls) == 1 and calls[0][0]["role"] == "user"
    assert "Danh sách trống" in calls[0][0]["content"]
    item, = out["items"]
    assert item.quote is None and item.explanation is None
    assert any("missing_contract_evidence" in warning for warning in item.warnings)
    assert any("missing_legal_evidence" in warning for warning in item.warnings)
    assert any("[L1]" in warning for warning in item.warnings)


def test_guidance_can_be_used_without_legal_basis_but_cannot_cite(case, approved):
    doc, findings, _, tax, calls = case
    out = ex.explain(doc, findings, [{"basis": []}], tax=tax, context_run_id="fixture")
    payload = json.loads(calls[0][1]["content"])
    assert payload["guidance"] and not payload["legal_passages"]
    assert out["items"][0].explanation is None
    assert any("[L1]" in warning for warning in out["items"][0].warnings)


def test_budget_dropped_citation_ids_are_rejected(case, approved):
    doc, findings, bases, tax, calls = case
    oversized = replace(PASSAGE, chunk_id=72, text="oversized " * 2000)
    bases[0]["basis"].insert(0, oversized)
    out = ex.explain(doc, findings, bases, tax=tax, context_run_id="fixture")
    passages = json.loads(calls[0][1]["content"])["legal_passages"]
    assert [(p["citation_id"], p["chunk_id"]) for p in passages] == [("L1", 71)]
    item, = out["items"]
    assert item.basis == [oversized, PASSAGE]
    assert item.explanation.cited == [PASSAGE.label]


@pytest.mark.parametrize("bad", [
    "[L2]", "[L99]", "Điều 123 Luật giả", "điều 123 luật giả",
    "[L01]", "[L１]", "[l1]", "[Lfake]", "[L" + "1" * 5000 + "]",
], ids=["dropped", "unknown", "written-out", "lowercase-law", "leading-zero",
        "unicode-digit", "lowercase-id", "non-numeric-id", "overlong-id"])
def test_rejects_citations_outside_rendered_packet(case, approved, monkeypatch, bad):
    doc, findings, bases, tax, _ = case
    oversized = replace(PASSAGE, chunk_id=72, text="oversized " * 2000)
    bases[0]["basis"].append(oversized)
    reply = LLMResult(json.dumps({"summary": bad, "recommendation": "Hỏi lại."}),
                      "stop", {}, "fixture", "fixture")
    monkeypatch.setattr(ex.llm, "chat", lambda *_, **__: reply)
    out = ex.explain(doc, findings, bases, tax=tax, context_run_id="fixture")
    assert out["items"][0].explanation is None
    assert any("explanation dropped" in warning for warning in out["items"][0].warnings)


def test_full_prompt_overflow_does_not_dispatch(case, approved, monkeypatch):
    doc, findings, bases, tax, calls = case
    monkeypatch.setenv(packet_context.WINDOW, "700")
    out = ex.explain(doc, findings, bases, tax=tax, context_run_id="fixture")
    assert not calls and not out["attempts"]
    assert out["items"][0].explanation is None
    assert "no explanation: context budget exceeded" in out["items"][0].warnings


def test_enhanced_envelope_overflow_falls_back_if_legacy_fits(case, approved, monkeypatch):
    doc, findings, bases, tax, calls = case
    ex.explain(doc, findings, bases, tax=tax, context_run_id="fixture")
    size = packet_context.message_size(calls[0])
    monkeypatch.setenv(packet_context.WINDOW, str(size - 1 + 400 + packet_context.SAFETY_MARGIN))
    out = ex.explain(doc, findings, bases, tax=tax, context_run_id="fixture")
    assert len(calls) == 2 and calls[1][0]["role"] == "user"
    assert "context packet guidance omitted" in out["items"][0].warnings
    assert out["attempts"][0]["context_packet"]["mode"] == "legacy"


def test_unknown_window_preserves_legacy_and_reports_configuration(case, approved, monkeypatch):
    doc, findings, bases, tax, calls = case
    monkeypatch.delenv(packet_context.WINDOW)
    out = ex.explain(doc, findings, bases, tax=tax, context_run_id="fixture")
    assert len(calls) == 1 and calls[0][0]["role"] == "user"
    assert "context packet disabled" in out["warnings"][0]


def test_retrieval_error_falls_back_without_disclosing_error_text(case, monkeypatch):
    doc, findings, bases, tax, calls = case

    def broken(*args, **kwargs):
        raise RuntimeError("synthetic sensitive text")

    monkeypatch.setattr(packet_context.HeuristicRetriever, "select", broken)
    out = ex.explain(doc, findings, bases, tax=tax, context_run_id="fixture")
    assert len(calls) == 1 and calls[0][0]["role"] == "user"
    item, = out["items"]
    assert item.explanation.cited == [PASSAGE.label]
    assert any("RuntimeError" in warning for warning in item.warnings)
    assert all("synthetic sensitive text" not in warning for warning in item.warnings)


@pytest.mark.parametrize("mismatch", ["code", "length"])
def test_misaligned_legal_attachments_do_not_fall_back(case, mismatch):
    doc, findings, bases, tax, calls = case
    if mismatch == "code":
        bases[0]["code"] = "B-DEP-03"
    else:
        bases.clear()
    out = ex.explain(doc, findings, bases, tax=tax, context_run_id="fixture")
    item, = out["items"]
    assert not calls and not item.basis and item.explanation is None
    assert "legal attachments do not align" in item.warnings[0]


def test_invalid_legal_attachment_does_not_reenter_via_fallback(case):
    doc, findings, bases, tax, calls = case
    bases[0]["basis"] = [replace(PASSAGE, chunk_id=0)]
    out = ex.explain(doc, findings, bases, tax=tax, context_run_id="fixture")
    assert not calls
    assert "no explanation: invalid or conflicting legal attachments" in out["items"][0].warnings


def test_profile_message_override_does_not_dispatch(case, monkeypatch):
    doc, findings, bases, tax, calls = case
    monkeypatch.delenv(packet_context.WINDOW)
    monkeypatch.setattr(ex.llm, "profile_for", lambda task, cfg=None: (
        "fixture", {"extra_body": {"messages": []}},
    ))
    out = ex.explain(doc, findings, bases, tax=tax, context_run_id="fixture")
    assert not calls
    assert "no explanation: model profile overrides explanation messages" in out["items"][0].warnings


def test_dispatch_uses_configuration_checked_by_budget(case, approved, monkeypatch):
    doc, findings, bases, tax, calls = case
    config = {"test": "captured configuration"}
    monkeypatch.setattr(ex.llm, "load_config", lambda: config)
    original = ex.llm.chat

    def capture(task, messages, *, cfg):
        assert cfg is config
        return original(task, messages)

    monkeypatch.setattr(ex.llm, "chat", capture)
    out = ex.explain(doc, findings, bases, tax=tax, context_run_id="fixture")
    assert calls and out["attempts"][0]["context_packet"]["mode"] == "enhanced"


def test_unapproved_packet_is_rejected_at_explanation_boundary(case, monkeypatch):
    doc, findings, bases, tax, calls = case
    builder = ContextPacketBuilder.for_synthetic_tests(HeuristicRetriever(load(tax=tax), tax=tax), tax=tax)
    monkeypatch.setattr(packet_context.PacketContext, "builder", builder)
    out = ex.explain(doc, findings, bases, tax=tax, context_run_id="fixture")
    assert [m["role"] for m in calls[0]] == ["user"]
    assert not out["attempts"][0]["context_packet"]["guidance"]
    assert any("context packet unavailable" in warning for warning in out["items"][0].warnings)
