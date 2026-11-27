import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

import pytest

from application.modules.heuristic_memory import load
from application.modules.context_packet import builder
from application.modules.explain import explain, packet_context
from evaluate_heuristic_explanation import DATASET, digest, evaluate, fixture_snapshot, main, markdown


def test_fixture_approval_is_ephemeral_and_explicit():
    seed = load()
    original = seed.model_dump(mode="json")
    fixture = fixture_snapshot(seed, ["deposit_refund_clock"])
    heuristic, = fixture.heuristics
    assert heuristic.id == "deposit_refund_clock"
    assert heuristic.provenance.status == "approved"
    assert heuristic.provenance.reviewer == "offline fixture only"
    assert not fixture.legal_rules and not heuristic.legal_reference_ids
    assert not fixture_snapshot(seed, []).heuristics
    assert seed.model_dump(mode="json") == original == load().model_dump(mode="json")
    with pytest.raises(ValueError, match="draft entries"):
        fixture_snapshot(seed, ["unknown_id"])


def test_paired_outcomes_cover_enhanced_fallback_and_budget_paths():
    result = evaluate()
    assert result["summary"] == {
        "cases": 11, "arm_checks_passed": {"legacy": 11, "enhanced": 11},
        "enhanced_modes": {"enhanced": 6, "legacy": 4, "skipped": 1},
    }
    cases = {row["case_id"]: row for row in result["cases"]}
    altered_scope = cases["AB-07-dropped-chunk"]
    assert altered_scope["legacy"]["citation_chunks"] == {"L1": 71, "L2": 72}
    assert altered_scope["enhanced"]["citation_chunks"] == {"L1": 72}
    assert altered_scope["enhanced"]["reply_ids_outside_scope"] == ["L2"]
    assert altered_scope["legacy"]["outcome"] == "accepted"
    assert altered_scope["enhanced"]["outcome"] == "rejected"
    overflow = cases["AB-08-budget-overflow"]["enhanced"]
    assert overflow["call_count"] == 0 and overflow["checks"]["budget_compliance"]
    assert cases["AB-04-cross-clause"]["enhanced"]["checks"]["packet_completeness"]


def test_reports_reproduce_and_detect_wrong_expectation():
    result = evaluate()
    assert result == evaluate()
    saved = DATASET.parent / "explanation_ab_results_v1.json"
    expected = json.loads(saved.read_bytes())
    # The frozen replay checks legacy outcomes across Builder and runtime changes.
    for module in (builder, explain, packet_context):
        expected["input_digests_lf"][module.__name__.rsplit(".", 1)[-1]] = digest(module.__file__)
    assert result == expected
    assert markdown(result) == saved.with_suffix(".md").read_text(encoding="utf-8")
    dataset = json.loads(DATASET.read_bytes())
    dataset["cases"] = dataset["cases"][:1]
    dataset["cases"][0]["expected"]["enhanced"]["guidance_ids"] = []
    with TemporaryDirectory() as directory:
        path = Path(directory) / "fixture.json"
        path.write_text(json.dumps(dataset), encoding="utf-8")
        changed = evaluate(path)
    assert changed["summary"]["arm_checks_passed"] == {"legacy": 1, "enhanced": 0}
    assert changed["cases"][0]["enhanced"]["checks"]["guidance_selection"] is False


def test_cli_refuses_to_overwrite_existing_report(monkeypatch):
    with TemporaryDirectory() as directory:
        existing = Path(directory) / "original.json"
        markdown_path = Path(directory) / "new.md"
        existing.write_bytes(b"original")
        monkeypatch.setattr(sys, "argv", [
            "evaluate_heuristic_explanation", "--json", str(existing),
            "--markdown", str(markdown_path),
        ])
        with pytest.raises(SystemExit) as error:
            main()
        assert error.value.code == 2
        assert existing.read_bytes() == b"original"
        assert not markdown_path.exists()
