"""Run the offline synthetic P2 benchmark and print a JSON report."""

from dataclasses import asdict
import json
from pathlib import Path

from application.modules.context_selection import select_context
from application.modules.ingestion.ingest import Clause, Document, Structure
from application.modules.short_term_memory import RunClauseIndex, RunScope


DATASET = Path(__file__).resolve().parents[1] / "data/context_eval/context_selection_synthetic_v1.json"


def evaluate(dataset: dict) -> dict:
    k = dataset["k"]
    rows = []
    for case in dataset["cases"]:
        spans = []
        start = 0
        for section in case["sections"]:
            heading = section.splitlines()[0]
            spans.append(Clause(heading, heading, start, start + len(section)))
            start += len(section) + 1
        document = Document("\n".join(case["sections"]), {}, structure=Structure(clauses=spans))
        scope = RunScope.for_document(case["id"], document)
        primary_id = case["primary_clause_id"]
        relevant = set(case["expected_relevant_ids"])
        with RunClauseIndex(scope, document) as index:
            if any(index.by_id(scope, identifier) is None for identifier in relevant | {primary_id}):
                raise ValueError(f"Fixture {scope.run_id} has an unknown expected ID")
            result = select_context(index, scope, primary_clause_ids=(primary_id,), budget_bytes=case["budget_bytes"])
        selected = [entry.excerpt.clause_id for entry in result.selected]
        expected_context = relevant | {primary_id}
        rows.append({
            "id": scope.run_id,
            "status": result.status,
            "expected_status": case["expected_status"],
            "selected_clause_ids": selected,
            "selected_reference_ids": list(result.references.clause_ids),
            "recall_at_k": (
                len(relevant.intersection(result.references.clause_ids[:k])) / len(relevant) if relevant else None
            ),
            "context_coverage": len(expected_context.intersection(selected)) / len(expected_context),
            "omitted_references": [asdict(entry) for entry in result.omitted if entry.role == "reference"],
            "invalid_references": [asdict(entry) for entry in result.invalid],
            "used_bytes": result.used_bytes,
            "budget_bytes": result.budget_bytes,
            "budget_compliant": sum(entry.text_bytes for entry in result.selected) == result.used_bytes
            <= result.budget_bytes,
        })
    recalls = [row["recall_at_k"] for row in rows if row["recall_at_k"] is not None]
    return {
        "dataset": DATASET.name,
        "synthetic": True,
        "k": k,
        "case_count": len(rows),
        "recall_case_count": len(recalls),
        "macro_recall_at_k": sum(recalls) / len(recalls) if recalls else None,
        "macro_context_coverage": sum(row["context_coverage"] for row in rows) / len(rows),
        "omitted_reference_count": sum(len(row["omitted_references"]) for row in rows),
        "budget_compliant_cases": sum(row["budget_compliant"] for row in rows),
        "cases": rows,
    }


if __name__ == "__main__":
    report = evaluate(json.loads(DATASET.read_text(encoding="utf-8")))
    print(json.dumps(report, indent=2))
    raise SystemExit(any(
        not row["budget_compliant"] or row["status"] != row["expected_status"]
        for row in report["cases"]
    ))
