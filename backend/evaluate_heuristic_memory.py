"""Run the offline, text-only heuristic memory benchmark from backend/."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean

from application.modules.heuristic_memory import HeuristicRetriever, load
from application.modules.heuristic_memory import _v1, rental_matching, retriever as retriever_module
from application.modules.heuristic_memory.knowledge import DEFAULT_JSON
from application.modules.taxonomy import taxonomy


DEFAULT_DATASET = (
    Path(__file__).resolve().parents[1] / "data/heuristic_eval/vn_residential_rental_v1.json"
)
KS = (1, 3, 5)
TYPES = ("positive", "negative", "paraphrased", "ambiguous", "cross_clause")
LABEL_STATUS = "provisional_requires_human_review"


def summarize(outcomes):
    metrics = ("precision", "recall", "hit")
    empty_count = sum(not row["expected_ids"] for row in outcomes)
    return {
        "scenarios": len(outcomes),
        "expected_empty": empty_count,
        "correct_empty": sum(
            not row["expected_ids"] and not row["selected_ids"] for row in outcomes
        ),
        "false_positives": sum(len(row["false_positives"]) for row in outcomes),
        "false_negatives": sum(len(row["false_negatives"]) for row in outcomes),
        **{metric: mean(row[metric] for row in outcomes) for metric in metrics},
    }


def score(row, selected_ids):
    expected = set(row["expected_ids"])
    selected = set(selected_ids)
    correct = expected & selected
    return {
        "scenario_id": row["id"],
        "type": row["type"],
        "expected_ids": row["expected_ids"],
        "selected_ids": selected_ids,
        "false_positives": sorted(selected - expected),
        "false_negatives": sorted(expected - selected),
        "precision": len(correct) / len(selected) if selected else int(not expected),
        "recall": len(correct) / len(expected) if expected else int(not selected),
        "hit": int(bool(correct) if expected else not selected),
    }


def evaluate(dataset_path, *, version="v2"):
    raw_dataset = dataset_path.read_bytes()
    dataset = json.loads(raw_dataset)
    if (dataset["schema_version"], dataset["source"], dataset["label_status"]) != (
        1, "synthetic", LABEL_STATUS
    ):
        raise ValueError("Expected a v1 synthetic dataset with provisional labels")

    tax = taxonomy.load()
    knowledge = load(tax=tax)
    selector, source = {
        "v1": (_v1.HeuristicRetriever, _v1),
        "v2": (HeuristicRetriever, retriever_module),
    }[version]
    retriever = selector(knowledge, tax=tax)
    domain = dataset["domain"]
    eligible = {
        entry.id for entry in knowledge.heuristics
        if entry.domain == domain and entry.provenance.status in {
            "approved", "draft", "pending_review"
        }
    }
    if not eligible:
        raise ValueError(f"No eligible knowledge entries for domain {domain}")

    scenarios = dataset["scenarios"]
    scenario_ids = set()
    outcomes = {k: [] for k in KS}
    for row in scenarios:
        expected_ids = row["expected_ids"]
        if (
            row["id"] in scenario_ids or row["type"] not in TYPES
            or not row["text"].strip() or not row["explanation"].strip()
            or len(expected_ids) != len(set(expected_ids)) or set(expected_ids) - eligible
        ):
            raise ValueError(f"Invalid or duplicate scenario {row['id']}")
        scenario_ids.add(row["id"])
        # Gold labels and scenario metadata never enter the retriever.
        ranked_ids = [
            hit.id for hit in retriever.select(
                domain=domain, text=row["text"], top_k=max(KS), include_drafts=True
            )
        ]
        for k in KS:
            outcomes[k].append(score(row, ranked_ids[:k]))

    type_counts = Counter(row["type"] for row in scenarios)
    if set(type_counts) != set(TYPES):
        raise ValueError("Benchmark requires coverage of all five scenario types")
    if not any(not row["expected_ids"] for row in scenarios):
        raise ValueError("Benchmark requires scenarios with no expected selection")

    return {
        "schema_version": 1,
        "domain": domain,
        "label_status": LABEL_STATUS,
        "dataset_sha256": sha256(raw_dataset).hexdigest(),
        "knowledge_version": knowledge.version,
        "knowledge_sha256": sha256(DEFAULT_JSON.read_bytes()).hexdigest(),
        "retriever_sha256": sha256(Path(source.__file__).read_bytes()).hexdigest(),
        **({"matching_rules_sha256": sha256(Path(rental_matching.__file__).read_bytes()).hexdigest()}
           if version == "v2" else {}),
        "settings": {"include_drafts": True, "risk_codes": [], "categories": []},
        "results": {
            k: {
                "overall": summarize(rows),
                "by_type": {
                    kind: summarize([row for row in rows if row["type"] == kind])
                    for kind in TYPES
                },
                "scenarios": rows,
            }
            for k, rows in outcomes.items()
        },
    }


def compare(dataset_path):
    v1 = evaluate(dataset_path, version="v1")
    v2 = evaluate(dataset_path, version="v2")
    changes = {}
    for k in KS:
        changes[k] = []
        before = v1["results"][k]["scenarios"]
        after = v2["results"][k]["scenarios"]
        for old, new in zip(before, after, strict=True):
            if old["selected_ids"] == new["selected_ids"]:
                continue
            changes[k].append({
                "scenario_id": new["scenario_id"],
                "v1_selected_ids": old["selected_ids"],
                "v2_selected_ids": new["selected_ids"],
                "metrics_decreased": [
                    name for name in ("precision", "recall", "hit") if new[name] < old[name]
                ],
                "new_false_positives": sorted(set(new["false_positives"]) - set(old["false_positives"])),
                "new_false_negatives": sorted(set(new["false_negatives"]) - set(old["false_negatives"])),
            })
    return {"v1": v1, "v2": v2, "selection_changes": changes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--version", choices=("v1", "v2", "compare"), default="compare")
    parser.add_argument("--output", type=Path, required=True, help="New JSON report path")
    args = parser.parse_args()
    report = compare(args.dataset) if args.version == "compare" else evaluate(
        args.dataset, version=args.version
    )
    with args.output.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")
    runs = {"v1": report["v1"], "v2": report["v2"]} if args.version == "compare" else {
        args.version: report
    }
    for version, run in runs.items():
        for k, result in run["results"].items():
            print(f"{version} @{k} {result['overall']}")


if __name__ == "__main__":
    main()
