# Offline A/B evaluation for heuristic Explanation

The [runner](../../backend/evaluate_heuristic_explanation.py) exercises the actual Explanation entry point. Arm A calls it without a context run ID. Arm B supplies a context run ID and uses the real Context Packet Builder, Heuristic Retriever v2 and citation checker. When the enabled path falls back, the report records the actual mode. Both arms receive fresh copies of the same grounded finding, document and attached passages, and the same scripted model reply if a call is made. The harness mocks chat and configuration and blocks HTTP transport. The production flag, pipeline and knowledge base are left intact.

## Fixtures and scoring

The [Vietnamese rental fixture set](../../data/heuristic_eval/explanation_ab_v1.json) contains 11 fictional cases. Each has a stable ID, clause text, a quote clause index or missing-term marker, a taxonomy code and issue, optional attached passage fixtures, a list of draft templates to exercise, a context limit, a scripted reply and per-arm expectations. The loader derives source offsets from the text and sends findings through existing grounding. Legal attachments are inert, explicitly synthetic passages without article numbers or asserted legal rules. Unsupported `[Lk]` strings are deliberately malformed or out-of-scope packet identifiers used to exercise validation.

For cases that need guidance, the harness projects only explicitly listed draft templates into a case-local, test-approved snapshot in memory. It replaces the approval marker and example markers on the copies with fixture metadata as required by the existing schema, and strips legal reference links. The production approval guard and approved-only retrieval run unchanged. The projected snapshot must never be saved as reviewed content. The no-approved case uses an empty fixture snapshot. Source records remain draft.

| Check | What the runner compares |
| --- | --- |
| Citation scope and validation | Exact rendered `Lk → chunk ID` bindings, accepted or rejected scripted outcome, and labels resolved by the production checker. Cases cover valid IDs, an unsupported ID without legal evidence, an ID removed after budget packing and a noncanonical alias. |
| Packet completeness | Document digest, case ID, domain, risk and issue, exact source-aligned excerpts, required related clauses and verbatim attached passage content. Evaluated only when the packet reaches the model stub. |
| Guidance traceability | Expected selected IDs, entry and snapshot versions, match reasons, supporting clause IDs and agreement between the prompt and persisted trace. |
| Budget and fallback | UTF-8 bytes of the final serialized messages, against the configured window minus 400 completion tokens and the runtime 256 safety margin. Tests cover omission of an oversized legal chunk, no match, no approved entries, a missing finding, a retrieval error and a skipped call when even the legacy prompt exceeds the enabled budget. Legacy A prompt bytes are measured for comparison and scored as unbudgeted. |
| Contract evidence | Output quote, exact source offsets, taxonomy code, attached basis, and the evidence in the prompt when sent. |

JSON records each check, mode, call count, warnings, rendered citation map, resolved labels, selection trace, fixture profile, input and source digests normalized to LF, and evaluation version. A null check is inapplicable. Markdown summarizes every paired case. Reports omit wall-clock measurements and token usage because no model ran. Output creation is exclusive, and failed expectations produce a nonzero exit status after reports are written.

## Reproduce

From `backend/` in the project Python environment, choose two unused paths.

```powershell
..\.venv\Scripts\python.exe evaluate_heuristic_explanation.py --json ../data/heuristic_eval/reproduction_explanation_ab.json --markdown ../data/heuristic_eval/reproduction_explanation_ab.md
..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests/test_heuristic_explanation_evaluation.py
```

The frozen [JSON results](../../data/heuristic_eval/explanation_ab_results_v1.json) and [Markdown report](../../data/heuristic_eval/explanation_ab_results_v1.md) record 11/11 fixture passes for each arm. Arm B used six enhanced prompts, four legacy fallbacks and one skipped call. AB-07 illustrates why citation scope must follow the rendered prompt. The same `[L2]` token is valid for A and out of scope for B after legal passage packing. AB-11 documents that legacy accepts `[L01]` while the enhanced path rejects it. These are observed validator differences on scripted cases.

## Future real-model evaluation

1. Have domain reviewers adjudicate the fixture relevance and legal evidence. Build a separate held-out set of synthetic or authorized contracts with source spans and annotated passage applicability. Use an authorized approved-only heuristic snapshot and version it with the corpus, taxonomy and prompts.
2. Freeze the paired analysis inputs after detection and legal attachment. Run the same model and model revision, temperature, sampling, seed when supported, completion budget, request settings and input findings for every arm. Keep prompt and context policy as the intended differences. Randomize arm order and interleave the runs where practical. For nondeterministic outputs, preregister repetitions and uncertainty reporting. Add a budgeted context-without-guidance arm if the aim is to isolate the effect of guidance from the effect of extra excerpts or different packing.
3. Blind reviewers to the assigned arm and use a shared rubric. Score source fidelity, accurate identification of uncertainties, usefulness of the recommendation and plain Vietnamese clarity on a 0–2 scale (incorrect or absent, partial, clear and adequately supported). Separately record fabricated or misused citations, legal claims unsupported by the cited passage, and material factual assertions lacking contract evidence. Have two reviewers label independently, then adjudicate disagreements and report agreement.
4. Compare paired results by contract, including repeat variability, regressions, expected-empty cases and missing-law cases. Record provider-reported prompt and completion tokens, end-to-end and model latency, and cost using the priced model and date. Report unavailable values explicitly. Before setting promotion thresholds, agree on the acceptable rates of grounding and citation failures, and the token, latency and cost budget.

The current results establish infrastructure behavior on these fixtures. They provide no evidence that model-generated explanations are clearer, more useful or legally correct, or that an apparent citation is semantically relevant. The UTF-8 byte budget is a conservative proxy and does not measure provider tokens. The small fixture set uses provisional labels, one finding per case and deterministic replies. The next evaluation should add reviewed cross-clause and overlapping-finding cases, exercise more paraphrases, and measure real-model behavior under the separate protocol.
