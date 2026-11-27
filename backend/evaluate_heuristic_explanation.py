"""Replay paired synthetic Explanation cases using a fully offline chat fixture."""

import argparse
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from unittest.mock import patch

from application.adapters import llm
from application.modules.context_packet import builder, clause_id
from application.modules.detection.finding import Finding, ground
from application.modules.detection.lens import from_taxonomy
from application.modules.explain import explain as explanation, packet_context
from application.modules.heuristic_memory import load
from application.modules.heuristic_memory import rental_matching, retriever
from application.modules.heuristic_memory.knowledge import DEFAULT_JSON, KnowledgeBase
from application.modules.ingestion.ingest import Clause, Document, Structure
from application.modules.legal_basis.basis import LegalBasis
from application.modules.taxonomy import taxonomy


DATASET = Path(__file__).resolve().parents[1] / "data/heuristic_eval/explanation_ab_v1.json"
VERSION = "1.0.0"
COMPLETION_RESERVE = 400
PROFILE = {
    "default_profile": "offline_fixture",
    "profiles": {"offline_fixture": {
        "base_url": "http://127.0.0.1:1",
        "model": "scripted_reply_v1",
        "sampling": {"temperature": 0, "max_tokens": COMPLETION_RESERVE},
        "max_concurrency": 1,
    }},
}


def digest(path):
    # Normalize checkout line endings without changing the source artifact.
    return sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def fixture_snapshot(seed, identifiers):
    """Project explicitly named draft fixtures into an ephemeral test-approved snapshot."""
    selected = set(identifiers)
    data = seed.model_dump(mode="json")
    available = {entry["id"] for entry in data["heuristics"]
                 if entry["provenance"]["status"] == "draft"}
    if len(selected) != len(identifiers) or selected - available:
        raise ValueError("Fixture IDs must be unique and refer to draft entries")
    data["heuristics"] = [entry for entry in data["heuristics"] if entry["id"] in selected]
    data["legal_rules"] = []
    for entry in data["heuristics"]:
        entry["provenance"].update(status="approved", reviewer="offline fixture only")
        entry["legal_reference_ids"] = []
        for example in entry["examples"]:
            example["status"] = "approved"
    return KnowledgeBase.model_validate_json(json.dumps(data))


def case_inputs(case, tax):
    clauses = case["clauses"]
    spans, start = [], 0
    for number, text in enumerate(clauses, 1):
        end = start + len(text)
        label = f"Điều {number}"
        spans.append(Clause(label, label, start, end))
        start = end + 1
    doc = Document("\n".join(clauses), {"filename": f"{case['id']}.txt"},
                   structure=Structure(clauses=spans))
    quote_clause = case["quote_clause"]
    finding = Finding("missing" if quote_clause is None else "present", case["issue"],
                      case["code"], None if quote_clause is None else clauses[quote_clause])
    findings, rejected = ground([finding], doc, from_taxonomy(tax))
    if rejected:
        raise ValueError(f"Fixture failed grounding: {case['id']}")
    legal = [LegalBasis(
        p["fixture_id"], None, "", p["text"] * p.get("repeat", 1), "", "retrieval", p["chunk_id"]
    ) for p in case["attached_passages"]]
    if len(set(p.chunk_id for p in legal)) != len(legal):
        raise ValueError(f"Duplicate legal chunks in {case['id']}")
    return doc, findings, [{"code": finding.code, "basis": legal}]


def run_arm(case, inputs, tax, snapshot, arm):
    doc, findings, bases = deepcopy(inputs)
    calls = []

    def fake_chat(task, messages, **kwargs):
        if task != "explain" or calls:
            raise AssertionError("Expected at most one call to the explanation fixture")
        if kwargs.get("cfg", PROFILE) != PROFILE:
            raise AssertionError("Unexpected fixture profile")
        calls.append(deepcopy(messages))
        return llm.LLMResult(json.dumps(case["reply"], ensure_ascii=False), "stop", {},
                             "offline_fixture", "scripted_reply_v1")

    original_select = retriever.HeuristicRetriever.select

    def select(instance, **kwargs):
        if kwargs.get("include_drafts"):
            raise AssertionError("Runtime draft selection is prohibited")
        if case["retrieval_error"]:
            raise RuntimeError("injected offline retrieval failure")
        return original_select(instance, **kwargs)

    # Exercise actual Explanation and packet code. Fail closed if an HTTP
    # transport or an unexpected fixture call is reached.
    with (
        patch.dict(os.environ, {packet_context.WINDOW: str(case["context_window"])}),
        patch.object(llm, "chat", fake_chat),
        patch.object(llm, "load_config", return_value=PROFILE),
        patch.object(llm.urllib.request, "urlopen", side_effect=AssertionError("HTTP disabled")) as http,
        patch.object(packet_context, "load", return_value=snapshot),
        patch.object(retriever.HeuristicRetriever, "select", select),
    ):
        output = explanation.explain(
            doc, findings, bases, tax=tax, context_run_id=case["id"] if arm == "enhanced" else None
        )
        http.assert_not_called()
    return score(case, inputs, output, calls, arm)


def packet_checks(case, data, trace, doc, finding, legal):
    parts = {part["clause_id"]: part for part in data["contract"]}
    guidance = data["guidance"]
    anchor_id = clause_id(finding.char_start, finding.char_end)
    requested = [doc.structure.clauses[i] for i in case.get("required_clause_indices", [])]
    requested_ids = {clause_id(c.char_start, c.char_end) for c in requested}
    spans = all(
        0 <= p["start"] < p["end"] <= len(doc.text)
        and p["text"] == doc.text[p["start"]:p["end"]]
        and p["clause_id"] == clause_id(p["start"], p["end"])
        for p in data["contract"]
    )
    complete = (
        spans and anchor_id in parts and requested_ids <= parts.keys()
        and data["risks"] == [{"code": finding.code, "kind": finding.kind,
                              "issue": finding.issue, "evidence_id": anchor_id}]
        and data["run_id"] == case["id"]
        and data["domain"] == "vn_residential_rental"
        and data["document_sha256"] == sha256(doc.text.encode("utf-8")).hexdigest()
        and all(
            (p["law"], p["article"], p["ref"], p["text"]) ==
            (legal[p["chunk_id"]].law, legal[p["chunk_id"]].dieu,
             legal[p["chunk_id"]].ref, legal[p["chunk_id"]].text)
            for p in data["legal_passages"] if p["chunk_id"] in legal
        )
        and all(p["chunk_id"] in legal for p in data["legal_passages"])
    )
    traceable = (
        trace.get("document_sha256") == data["document_sha256"]
        and trace.get("clause_ids") == list(parts)
        and trace.get("guidance") == [
            {"id": g["heuristic_id"], "entry_version": g["entry_version"],
             "knowledge_version": g["knowledge_version"], "clause_ids": g["reason"]["matched_clause_ids"]}
            for g in guidance
        ]
        and all(
            g["review_status"] == "approved" and g["entry_version"] and g["knowledge_version"]
            and g["reason"]["matched_clause_ids"] and g["reason"]["matched_triggers"]
            and (g["reason"]["matched_codes"] or g["reason"]["matched_categories"])
            and set(g["reason"]["matched_clause_ids"]) <= parts.keys()
            and g["reasoning_checklist"] and g["required_context"] and g["cross_clause_checks"]
            for g in guidance
        )
    )
    return bool(complete), bool(traceable)


def score(case, inputs, output, calls, arm):
    doc, findings, bases = inputs
    finding, = findings
    item, = output["items"]
    legal = {p.chunk_id: p for p in bases[0]["basis"]}
    expected = case["expected"][arm]
    trace = output["attempts"][0].get("context_packet", {}) if output["attempts"] else {}
    messages = calls[0] if calls else []
    enhanced = [m["role"] for m in messages] == ["system", "user"]
    mode = "enhanced" if enhanced else "legacy" if messages else "skipped"
    outcome = "accepted" if item.explanation else "rejected" if messages else "skipped"
    data = json.loads(messages[1]["content"]) if enhanced else None
    quote = doc.text[finding.char_start:finding.char_end] if finding.kind == "present" else None
    prompt_bytes = (len(json.dumps(messages, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                    if messages else 0)
    if enhanced:
        citation_map = {p["citation_id"]: p["chunk_id"] for p in data["legal_passages"]}
        complete, traceable = packet_checks(case, data, trace, doc, finding, legal)
        prompt_evidence = any(part["text"] == quote for part in data["contract"])
    else:
        prompt = messages[0]["content"] if messages else ""
        citation_map = {
            f"L{i}": p.chunk_id for i, p in enumerate(legal.values(), 1)
            if f"[L{i}] {p.label}\n{p.text[:explanation.MAX_LAW_CHARS]}" in prompt
        }
        complete = traceable = None
        prompt_evidence = not messages or (
            quote in prompt if quote else "NỘI DUNG HỢP ĐỒNG CÒN THIẾU" in prompt
        )
    guidance_ids = [g["heuristic_id"] for g in data["guidance"]] if data else []
    reply = case["reply"]
    reply_ids = sorted({ref for part in reply.values() for ref in re.findall(r"\[(L[0-9]+)\]", part)})
    tokens = sorted({int(ref[1:]) for ref in reply_ids})
    expected_map = {i: chunk_id for i, chunk_id in enumerate(expected["citation_chunks"], 1)}
    cited = item.explanation.cited if item.explanation else []
    expected_labels = [legal[expected_map[n]].label for n in tokens if n in expected_map]
    warning = expected.get("warning_contains")
    checks = {
        "mode_and_fallback": mode == expected["mode"] and (
            not warning or any(warning in w for w in item.warnings + output["warnings"])
        ),
        "citation_validation": outcome == expected["outcome"] and (
            cited == (expected_labels if expected["outcome"] == "accepted" else [])
        ),
        "citation_scope": citation_map == {f"L{i}": chunk for i, chunk in expected_map.items()}
        and (not trace or trace["citation_chunks"] == citation_map),
        "packet_completeness": complete,
        "guidance_traceability": traceable,
        "guidance_selection": guidance_ids == expected["guidance_ids"],
        "budget_compliance": (prompt_bytes <= case["context_window"] - COMPLETION_RESERVE
                              - packet_context.SAFETY_MARGIN) if arm == "enhanced" else None,
        "call_count": len(calls) == len(output["attempts"]) == int(expected["mode"] != "skipped"),
        "evidence_preservation": item.quote == quote and item.codes == [finding.code]
        and (item.char_start, item.char_end) == (finding.char_start, finding.char_end)
        and [asdict(p) for p in item.basis] == [asdict(p) for p in legal.values()]
        and prompt_evidence,
    }
    return {
        "mode": mode, "outcome": outcome, "call_count": len(calls), "prompt_bytes": prompt_bytes,
        "citation_chunks": citation_map, "reply_reference_ids": reply_ids,
        "reply_ids_outside_scope": sorted(set(reply_ids) - citation_map.keys()),
        "resolved_labels": cited,
        "guidance_ids": guidance_ids, "trace": trace, "warnings": output["warnings"] + item.warnings,
        "checks": checks, "passed": all(value is not False for value in checks.values()),
    }


def evaluate(path: Path = DATASET):
    dataset = json.loads(path.read_bytes())
    if (dataset["schema_version"], dataset["source"], dataset["label_status"]) != (
        1, "synthetic", "provisional_requires_human_review",
    ):
        raise ValueError("Expected synthetic v1 fixture data with provisional labels")
    cases = dataset["cases"]
    if not cases or len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Expected nonempty, unique case IDs")
    tax = taxonomy.load()
    seed = load(tax=tax)
    rows = []
    for case in cases:
        inputs = case_inputs(case, tax)
        snapshot = fixture_snapshot(seed, case["fixture_heuristic_ids"])
        finding, = inputs[1]
        rows.append({
            "case_id": case["id"], "risk_code": finding.code, "kind": finding.kind,
            "evidence_offsets": [finding.char_start, finding.char_end],
            "document_sha256": sha256(inputs[0].text.encode("utf-8")).hexdigest(),
            "attached_chunk_ids": [p.chunk_id for p in inputs[2][0]["basis"]],
            "fixture_heuristics": [{"id": h.id, "version": h.version} for h in snapshot.heuristics],
            "context_window": case["context_window"], "scripted_reply": case["reply"],
            "expected": case["expected"],
            **{arm: run_arm(case, inputs, tax, snapshot, arm) for arm in ("legacy", "enhanced")},
        })
    return {
        "evaluation_version": VERSION, "experiment": "offline_scripted_infrastructure_only",
        "dataset": {"id": dataset["dataset_id"], "sha256_lf": digest(path),
                    "label_status": dataset["label_status"]},
        "fixture_profile": PROFILE, "safety_margin": packet_context.SAFETY_MARGIN,
        "knowledge_version": seed.version,
        "input_digests_lf": {
            "runner": digest(__file__),
            "knowledge": digest(DEFAULT_JSON),
            "taxonomy": digest(taxonomy.DEFAULT_JSON),
            **{module.__name__.rsplit(".", 1)[-1]: digest(module.__file__) for module in (
                explanation, packet_context, builder, rental_matching, retriever,
            )},
        },
        "summary": {
            "cases": len(rows),
            "arm_checks_passed": {
                arm: sum(row[arm]["passed"] for row in rows) for arm in ("legacy", "enhanced")
            },
            "enhanced_modes": {
                mode: sum(row["enhanced"]["mode"] == mode for row in rows)
                for mode in ("enhanced", "legacy", "skipped")
            },
        },
        "cases": rows,
    }


def markdown(report):
    summary = report["summary"]
    lines = [
        "# Offline Explanation A/B results", "",
        f"Evaluation {report['evaluation_version']} on `{report['dataset']['id']}`.",
        "Both arms used the same synthetic inputs and scripted reply for each case.",
        "The results measure infrastructure behavior. Semantic explanation quality was not evaluated.", "",
        f"Fixture checks passed for {summary['arm_checks_passed']['legacy']}/{summary['cases']} "
        f"legacy cases and {summary['arm_checks_passed']['enhanced']}/{summary['cases']} enabled cases.",
        "", "| Case | A outcome | B mode and outcome | A / B prompt bytes | B guidance | Checks |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for row in report["cases"]:
        a, b = row["legacy"], row["enhanced"]
        failed = [f"{arm}.{name}" for arm in ("legacy", "enhanced")
                  for name, passed in row[arm]["checks"].items() if passed is False]
        lines.append(
            f"| {row['case_id']} | {a['outcome']} | {b['mode']} / {b['outcome']} | "
            f"{a['prompt_bytes']} / {b['prompt_bytes']} | {', '.join(b['guidance_ids']) or '—'} | "
            f"{', '.join(failed) or 'Pass'} |"
        )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    if args.json.resolve() == args.markdown.resolve() or args.json.exists() or args.markdown.exists():
        parser.error("Report paths must be distinct and unused")
    report = evaluate(args.dataset)
    for path, content in ((args.json, json.dumps(report, ensure_ascii=False, indent=2) + "\n"),
                          (args.markdown, markdown(report))):
        with path.open("x", encoding="utf-8", newline="\n") as output:
            output.write(content)
    print(report["summary"])
    return int(any(n != report["summary"]["cases"]
                   for n in report["summary"]["arm_checks_passed"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
