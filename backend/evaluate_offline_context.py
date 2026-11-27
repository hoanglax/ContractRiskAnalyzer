"""Compare P3.1 strict selection with the frozen P3 synthetic results."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from statistics import mean

from application.modules.context_packet import ContextPacketBuilder, GroundedRisk, PromptBudget, clause_id
from application.modules.detection.finding import Finding, ground
from application.modules.detection.lens import from_taxonomy
from application.modules.heuristic_memory import HeuristicRetriever, load
from application.modules.ingestion.ingest import Clause, Document, Structure
from application.modules.offline_context import build_offline_context
from application.modules.taxonomy import taxonomy


DATASET = Path(__file__).resolve().parents[1] / "data/context_eval/offline_context_synthetic_v1.json"
BASELINE = DATASET.with_name(f"{DATASET.stem}_results.json")
RANKS = (1, 3, 5)


def _rank_metrics(refs, expected):
    metrics = {}
    for k in RANKS:
        ranked = refs[:k]
        hits = len(expected.intersection(ranked))
        metrics[f"recall@{k}"] = hits / len(expected) if expected else None
        metrics[f"precision@{k}"] = hits / k
        metrics[f"precision_returned@{k}"] = hits / len(ranked) if ranked else None
    metrics["precision_returned_all"] = len(expected.intersection(refs)) / len(refs) if refs else None
    return metrics


def _macro_metrics(rows):
    macro = {}
    for key in rows[0]:
        values = [row[key] for row in rows if row[key] is not None]
        macro[key] = {"value": mean(values) if values else None, "cases": len(values)}
    return macro


def evaluate(dataset: dict) -> dict:
    tax = taxonomy.load()
    lens = from_taxonomy(tax)
    knowledge = load(tax=tax)
    entries = tuple(entry for entry in knowledge.heuristics if entry.id == "return_milestones")
    if len(entries) != 1:
        raise ValueError("Expected the return_milestones fixture template")
    snapshot = knowledge.model_copy(update={"heuristics": entries})
    builder = ContextPacketBuilder.for_synthetic_tests(HeuristicRetriever(snapshot, tax=tax), tax=tax)
    rows = [_evaluate_case(dataset, case, lens, builder) for case in dataset["cases"]]
    if not rows or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Expected nonempty, uniquely named cases")
    return {
        "dataset_kind": "synthetic",
        "independently_reviewed": False,
        "case_count": len(rows),
        "rank_metrics": _macro_metrics([row["rank_metrics"] for row in rows]),
        "mean_context_coverage": mean(row["context_coverage"] for row in rows),
        "retained_mandatory_in_selection": sum(row["mandatory_in_selection"] for row in rows),
        "retained_mandatory_in_packet": sum(row["mandatory_in_packet"] for row in rows),
        "packets_with_data": sum(row["packet_status"] == "ready" for row in rows),
        "empty_label_cases_with_no_references": sum(
            not row["expected_relevant_ids"] and not row["selection"]["references"]["clause_ids"] for row in rows
        ),
        "contract_budget_compliant_cases": sum(row["contract_budget_compliant"] for row in rows),
        "packet_budget_compliant_cases": sum(row["packet_budget_compliant"] for row in rows),
        "strict_packet_text_budget_compliant_cases": sum(row["strict_packet_text_budget_compliant"] for row in rows),
        "invalid_labels_total": sum(len(row["invalid_checks"]) for row in rows),
        "invalid_labels_rejected": sum(check["rejected"] for row in rows for check in row["invalid_checks"]),
        "cases_with_errors": sum(bool(row["errors"]) for row in rows),
        "cases": rows,
    }


def _evaluate_case(dataset, case, lens, builder):
    spans = []
    start = 0
    for section in case["sections"]:
        heading = section.splitlines()[0]
        spans.append(Clause(heading, heading, start, start + len(section)))
        start += len(section) + 1
    document = Document("\n".join(case["sections"]), {}, structure=Structure(clauses=spans))
    findings, rejected = ground([
        Finding("present", "Cần làm rõ thủ tục trả nhà.", code="B-TRM-06", quote=case["quote"]),
    ], document, lens)
    if rejected or len(findings) != 1:
        raise ValueError(f"Invalid grounded fixture {case['id']}")
    finding = findings[0]
    anchor_id = clause_id(finding.char_start, finding.char_end)
    expected = set(case["expected_relevant_ids"])
    allowed_ids = {clause_id(span.char_start, span.char_end) for span in spans}
    source_ids = {
        clause_id(span.char_start, span.char_end) for span in spans
        if span.char_start <= finding.char_start < finding.char_end <= span.char_end
    }
    # The v1 fixture records the former missing-target diagnostic for this appendix
    # alongside its relevant container ID. P3.1 expects that same ID to resolve.
    invalid_labels = [] if case["id"] == "appendix-03" else case.get("expected_invalid", [])
    forbidden_ids = {identifier for label in invalid_labels for identifier in label["forbidden_ids"]}
    if source_ids != {case["source_clause_id"]} or not expected | forbidden_ids <= allowed_ids:
        raise ValueError(f"Invalid clause annotations in {case['id']}")
    budget = PromptBudget(case.get("packet_context_window", dataset["default_packet_context_window"]))
    result = build_offline_context(
        document, case["id"], (GroundedRisk(finding),), builder=builder,
        contract_budget_bytes=case.get("contract_budget_bytes", dataset["default_contract_budget_bytes"]),
        packet_budget=budget, selection_policy="strict",
    )
    selection, packet = result.selection, result.packet
    refs = selection.references.clause_ids
    selected = {entry.excerpt.clause_id for entry in selection.selected}
    packet_parts = packet.data.contract if packet and packet.data else ()
    packet_ids = {part.clause_id for part in packet_parts}
    packet_status = packet.status if packet else "not_built"
    rank_metrics = _rank_metrics(refs, expected)
    invalid_checks = []
    for label in invalid_labels:
        diagnostics = [
            d for d in selection.invalid
            if (d.reason, d.matching_text) == (label["reason"], label["matching_text"])
        ]
        emitted = any(
            entry.relation and entry.relation.matching_text == label["matching_text"]
            for entry in selection.selected
        )
        invalid_checks.append({
            **label,
            "rejected": bool(diagnostics) and not emitted and not set(refs).intersection(label["forbidden_ids"]),
        })
    missing = sorted(expected - set(refs))
    unexpected = sorted(set(refs) - expected)
    packet_missing = sorted(expected - packet_ids)
    mandatory_selected = any(
        entry.excerpt.clause_id == anchor_id and entry.excerpt.provenance == "grounded_span"
        for entry in selection.selected
    )
    mandatory_packet = any(part.clause_id == anchor_id and part.provenance == "grounded_span" for part in packet_parts)
    all_parts = (*packet_parts, *(entry.excerpt for entry in selection.selected))
    source_exact = all(part.text == document.text[part.start:part.end] for part in all_parts)
    contract_ok = sum(entry.text_bytes for entry in selection.selected) == selection.used_bytes <= selection.budget_bytes
    packet_ok = not packet or packet.data is None or (
        packet.estimated_prompt_tokens == len(packet.data.to_json().encode("utf-8")) <= budget.allowance
    )
    packet_text_bytes = sum(len(part.text.encode("utf-8")) for part in packet_parts)
    strict_text_ok = packet_text_bytes <= selection.budget_bytes
    expected_selection = case.get("expected_selection_status", "ready")
    expected_packet = case.get("expected_packet_status", "ready")
    checks = {
        "unexpected_selection_status": selection.status == expected_selection,
        "unexpected_packet_status": packet_status == expected_packet,
        "missing_mandatory_selection": expected_selection != "ready" or mandatory_selected,
        "missing_mandatory_packet": expected_packet != "ready" or mandatory_packet,
        "inexact_source": source_exact,
        "contract_budget_violation": contract_ok,
        "packet_budget_violation": packet_ok,
        "strict_packet_text_budget_violation": strict_text_ok,
        "invalid_reference_not_rejected": all(check["rejected"] for check in invalid_checks),
        "packet_context_outside_selection": packet_ids <= selected,
    }
    violations = [error for error, passed in checks.items() if not passed]
    errors = list(violations)
    if missing:
        errors.append(f"missing_relevant_references ({', '.join(missing)})")
    if unexpected:
        errors.append(f"unexpected_references ({', '.join(unexpected)})")
    if packet_missing:
        errors.append(f"relevant_context_not_in_packet ({', '.join(packet_missing)})")
    packet_only = sorted(packet_ids - selected)
    if packet_only:
        errors.append(f"packet_added_context_outside_selection ({', '.join(packet_only)})")
    return {
        "id": case["id"],
        "category": case["category"],
        "explanation": case["explanation"],
        "expected_relevant_ids": sorted(expected),
        "rank_metrics": rank_metrics,
        "context_coverage": len(({anchor_id} | expected).intersection(selected)) / (1 + len(expected)),
        "mandatory_in_selection": mandatory_selected,
        "mandatory_in_packet": mandatory_packet,
        "contract_budget_compliant": contract_ok,
        "packet_budget_compliant": packet_ok,
        "strict_packet_text_budget_compliant": strict_text_ok,
        "packet_text_bytes": packet_text_bytes,
        "packet_allowance": budget.allowance,
        "packet_status": packet_status,
        "packet_relevant_ids": sorted(expected & packet_ids),
        "packet_only_clause_ids": packet_only,
        "packing_diagnostics": [asdict(diagnostic) for diagnostic in result.packing_diagnostics],
        "invalid_checks": invalid_checks,
        "selection": asdict(selection),
        "packet": asdict(packet) if packet else None,
        "violations": violations,
        "errors": errors,
    }


def compare_with_baseline(report: dict, baseline: dict) -> dict:
    before = {row["id"]: row for row in baseline["cases"]}
    if before.keys() != {row["id"] for row in report["cases"]}:
        raise ValueError("Expected identical case IDs in both reports")
    changes = []
    for row in report["cases"]:
        old = before[row["id"]]
        expected = set(row["expected_relevant_ids"])
        if expected != set(old["expected_relevant_ids"]):
            raise ValueError(f"Relevant IDs changed for {row['id']}")
        old_refs = set(old["selection"]["references"]["clause_ids"])
        new_refs = set(row["selection"]["references"]["clause_ids"])
        old_packed = set(old["packet_relevant_ids"])
        new_packed = set(row["packet_relevant_ids"])
        retained_metrics = (
            "mandatory_in_selection", "mandatory_in_packet", "contract_budget_compliant", "packet_budget_compliant",
        )
        regressions = [metric for metric in retained_metrics if old[metric] and not row[metric]]
        if expected & (old_refs - new_refs):
            regressions.append("relevant_reference_lost")
        if old_packed - new_packed:
            regressions.append("relevant_packet_context_lost")
        if (new_refs - old_refs) - expected:
            regressions.append("new_unexpected_reference")
        if any(
            row["rank_metrics"][f"recall@{k}"] < old["rank_metrics"][f"recall@{k}"]
            for k in RANKS if expected
        ):
            regressions.append("ranked_recall_decreased")
        changes.append({
            "id": row["id"],
            "references_before": old["selection"]["references"]["clause_ids"],
            "references_after": row["selection"]["references"]["clause_ids"],
            "relevant_references_gained": sorted(expected & (new_refs - old_refs)),
            "relevant_references_lost": sorted(expected & (old_refs - new_refs)),
            "relevant_packet_context_gained": sorted(new_packed - old_packed),
            "relevant_packet_context_lost": sorted(old_packed - new_packed),
            "packet_only_before": old["packet_only_clause_ids"],
            "packet_only_after": row["packet_only_clause_ids"],
            "regressions": regressions,
        })
    return {
        "version": "p3.1-v2",
        "baseline": BASELINE.name,
        "annotation_note": "appendix-03 giữ nguyên ID đích và bỏ kỳ vọng chẩn đoán missing_target của P3.",
        "baseline_rank_metrics": {
            **_macro_metrics([
                _rank_metrics(row["selection"]["references"]["clause_ids"], set(row["expected_relevant_ids"]))
                for row in baseline["cases"]
            ]),
            **baseline["rank_metrics"],
        },
        "baseline_mean_context_coverage": baseline["mean_context_coverage"],
        "baseline_totals": {
            key: baseline[key] for key in (
                "retained_mandatory_in_selection", "retained_mandatory_in_packet", "contract_budget_compliant_cases",
                "packet_budget_compliant_cases", "invalid_labels_rejected", "invalid_labels_total",
            )
        },
        "cases_with_regressions": sum(bool(change["regressions"]) for change in changes),
        "comparison": changes,
        **report,
    }


def render_markdown(report: dict) -> str:
    total = report["case_count"]
    lines = [
        "# So sánh ngoại tuyến Short-term Memory P3.1",
        "",
        f"Bộ dữ liệu tổng hợp gồm {total} tình huống. Kết quả Golden Set được thẩm định độc lập chưa có.",
        "Recall chỉ tính ca có đích kỳ vọng. Precision@K chia số đích đúng cho K và tính cả ca không trả đích.",
        "Precision returned chia cho số đích thực sự trả về và bỏ qua ca không trả đích.",
        report["annotation_note"],
        "",
        "| Chỉ số | P3 | P3.1 | Mẫu P3.1 |",
        "|---|---:|---:|---:|",
    ]
    for key, metric in report["rank_metrics"].items():
        value = f"{metric['value']:.2%}" if metric["value"] is not None else "—"
        previous = report["baseline_rank_metrics"].get(key, {}).get("value")
        previous_text = f"{previous:.2%}" if previous is not None else "—"
        lines.append(f"| {key} | {previous_text} | {value} | {metric['cases']} |")
    lines.append(
        f"| Context coverage | {report['baseline_mean_context_coverage']:.2%}"
        f" | {report['mean_context_coverage']:.2%} | {total} |"
    )
    baseline = report["baseline_totals"]
    for key, label in (
        ("retained_mandatory_in_selection", "Giữ bằng chứng bắt buộc tại P2"),
        ("retained_mandatory_in_packet", "Giữ bằng chứng bắt buộc trong gói"),
        ("contract_budget_compliant_cases", "Tuân thủ hạn mức văn bản"),
        ("packet_budget_compliant_cases", "Tuân thủ hạn mức gói"),
    ):
        lines.append(f"| {label} | {baseline[key]}/{total} | {report[key]}/{total} | {total} |")
    lines.extend([
        f"| Văn bản thực tế trong gói tuân thủ hạn mức P2 | — | {report['strict_packet_text_budget_compliant_cases']}/{total} | {total} |",
        f"| Bác bỏ dẫn chiếu không hợp lệ | {baseline['invalid_labels_rejected']}/{baseline['invalid_labels_total']}"
        f" | {report['invalid_labels_rejected']}/{report['invalid_labels_total']} | {report['invalid_labels_total']} |",
        "",
        f"Số ca có hồi quy theo tiêu chí đối chiếu là {report['cases_with_regressions']}.",
        "",
        "| Ca | Đích P2 trước → sau | Đích đúng trong gói thêm / mất | Hồi quy | Sai lệch còn lại |",
        "|---|---|---|---|---|",
    ])
    for row, change in zip(report["cases"], report["comparison"]):
        before = ", ".join(change["references_before"]) or "—"
        after = ", ".join(change["references_after"]) or "—"
        gained = ", ".join(change["relevant_packet_context_gained"]) or "—"
        lost = ", ".join(change["relevant_packet_context_lost"]) or "—"
        regressions = ", ".join(change["regressions"]) or "—"
        errors = " · ".join(row["errors"]) or "—"
        lines.append(
            f"| {row['id']} | {before} → {after} | {gained} / {lost} | {regressions} | {errors} |"
        )
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()
    paths = (args.json, args.markdown)
    if paths[0].resolve() == paths[1].resolve() or any(path.exists() for path in paths):
        parser.error("Provide two distinct output paths that do not already exist")
    report = compare_with_baseline(
        evaluate(json.loads(DATASET.read_text(encoding="utf-8"))),
        json.loads(BASELINE.read_text(encoding="utf-8")),
    )
    for path, content in zip(paths, (json.dumps(report, ensure_ascii=False, indent=2) + "\n", render_markdown(report))):
        with path.open("x", encoding="utf-8", newline="\n") as output:
            output.write(content)
    return int(any(row["violations"] for row in report["cases"]))


if __name__ == "__main__":
    raise SystemExit(main())
