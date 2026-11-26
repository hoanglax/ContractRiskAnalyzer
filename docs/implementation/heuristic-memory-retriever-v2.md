# Heuristic Retriever v2

On a 30-scenario synthetic holdout, v2 raised Precision@3 from 40.00% to 66.67% and Recall@3 from 38.33% to 63.33%. It still missed five of six holdout paraphrases and introduced one false positive on language disclaiming a repair reimbursement provision. The original 46 development scenarios reached 100% on all three metrics at K=3. Those cases informed the implementation and should be read as a regression suite.

## Baseline error analysis

The table covers all 10 baseline false-positive IDs and all 16 false-negative IDs at K=1. Five misses come from the cutoff and recover at K=3. The K=3 and K=5 error sets are identical. Taxonomy associations could affect hinted runs, but they caused none of the measured errors because both hint lists were empty. In particular, shared codes for deposit identity and settlement or for lessor authority and subletting deserve separate testing with independently supplied hints.

| Scenario | False positive or negative | Classification and assessment |
| --- | --- | --- |
| VN-20 | FP `annex_conflict` | Broad trigger and lost clause relation. A curtain annex and rent mention refer to different fields. |
| VN-21 | FP `return_milestones` | Broad trigger. Keys and inventory describe move-in. |
| VN-22 | FP `deposit_forfeiture` | Broad trigger. “Không mất cọc” is negated and concerns a parking deposit. |
| VN-23 | FP `termination_notice_clock` | Broad trigger and lost clause relation. Guest notice and termination of cleaning services do not describe a lease exit. |
| VN-25 | FP `wear_baseline` | Broad trigger. “Nguyên trạng” describes a label on a bike. |
| VN-26 | FP `renewal_vs_exit` | Broad trigger. The expiry and extension concern a card. |
| VN-27 | FN `deposit_refund_clock` | Missing vocabulary. The scenario separates the security noun from the action of transferring it back. |
| VN-28 | FN `rent_increase` | Missing vocabulary. “Nâng mức tiền nhà” expresses the price change. |
| VN-29 | FN `termination_notice_clock` | Missing vocabulary. Midterm move-out and a letter express exit and notice. |
| VN-30 | FN `co_owner_consent` | Missing vocabulary and provisional-label question. The wording implies joint ownership, but a contract reviewer should distinguish ownership from shared occupancy or management. |
| VN-31 | FN `repair_reimbursement` | Missing vocabulary. Calling a contractor, advancing money and later payment express the process. |
| VN-32 | FN `wear_baseline` | Missing vocabulary. Paint fading and move-in photographs express wear and baseline. |
| VN-34 | FP `repair_reimbursement` | Broad trigger and provisional-label question. Notice alone does not describe cost allocation. A reviewer may still want guidance on the missing reimbursement terms. |
| VN-37 | FP `tax_incidence` | Broad trigger and lost clause relation. The purchase invoice is unrelated to rent. The statement about tax describes absent wording. |
| VN-39 | FN `deposit_refund_clock` at K=1 | Multi-clause ranking. Both relevant checks qualify, and handover has more vocabulary matches. No unique preferred top result is labeled. |
| VN-40 | FP `overlapping_remedies`; FN `termination_notice_clock`; FN `deposit_forfeiture` at K=1 | Broad trigger joins a negated penalty with forfeiture. Missing early-exit vocabulary blocks the notice check. The irrelevant remedies hit outranks forfeiture at K=1. An adjudicator could argue the express exclusion of a penalty is relevant to comparing remedies. |
| VN-41 | FN `utility_service_fees` | Incorrect exclusion scope. Brokerage fees suppress building charges. The existing `annex_conflict` label also calls for judgment because the seed checklist emphasizes payment, refund and term fields, and the relevant annex language references the fee indirectly. |
| VN-42 | FN `wear_baseline` | Missing vocabulary and multi-clause context loss. Previously damaged paint connects a move-in record to a move-out deduction. |
| VN-43 | FN `sublease_scope` | Incorrect exclusion scope. A parking prohibition masks the apartment sublease. |
| VN-44 | FP `deposit_identity`; FNs `deposit_deductions` and `overlapping_remedies` at K=1 | Broad offset trigger and cutoff. The offset settles a penalty, so classifying it as rent or security is secondary at best. The remedies label is debatable because the credit describes one penalty paid from security. The checklist can still help verify that the amount was credited once. |
| VN-45 | FN `termination_notice_clock` at K=1 | Multi-clause ranking and provisional-label question. The midterm rule helps contrast timelines, although the proposed move-out occurs at expiry and the renewal check could suffice for that question. |
| VN-46 | FN `rent_increase` | Missing vocabulary and multi-clause context loss. An effective date and new price convey a change without the canonical rent-change phrase. |

The original expected IDs and explanations remain as published. Scores use them consistently across versions.

## Implementation

`HeuristicRetriever.select(domain=..., text=...)` remains available. A caller with parsed structure can instead pass ordered `clauses`, with unique, nonempty clause IDs.

```python
from application.modules.heuristic_memory import Clause, HeuristicRetriever, load

hits = HeuristicRetriever(load()).select(
    domain="vn_residential_rental",
    clauses=[
        Clause("return", "Bên thuê trả căn hộ vào ngày 30."),
        Clause("keys", "Chìa khóa được gửi tại quầy trực."),
    ],
    include_drafts=True,
)
```

Plain text is split at sentence and semicolon boundaries. Bare newlines can be line wraps inside a phrase. Within each segment, matching remains token-based, case-insensitive and NFC-normalized. Exclusions remove the matching segment from consideration for that heuristic. Extra signals require context for selected rental IDs, for example an exit cue for handover or a funding cue for repair reimbursement. A short negation check suppresses phrases such as “không được tăng tiền thuê.” Explicit negative conditions such as “không hoàn cọc” and “không báo trước” carry their own meaning and can serve as triggers.

Controlled alternatives record the Vietnamese phrases actually matched. Selected rules can combine adjacent eligible segments, such as exit and key return. Others recognize explicit relations across segments, such as an annex and a contract clause describing the same field. Custom records retain their own trigger groups. The returned `matched_clause_ids` identifies the evidence window and `matched_triggers` includes alias or relation evidence. With plain text the IDs are generated segment IDs. Ranking remains descending by matched codes, categories and vocabulary count, then ascending by ID. Relational fallbacks carry phrase and clause evidence and contribute zero vocabulary score.

Approval filtering still defaults to approved-only. The v1 program is preserved byte-for-byte in an evaluation-only module. The seed knowledge, legal records and production analysis pipeline were left intact.

## Evaluation and freeze

The evaluator gives both versions exactly the same text, domain and draft setting, with no taxonomy hints. It uses the [v1 scoring conventions](heuristic-memory-evaluation.md) and records each selected ID and error at K=1, 3 and 5. The rerun's v1 report matches the saved v1 JSON exactly after parsing. The comparison artifacts preserve all changes with either decreased metrics or newly missed or selected IDs, even when exchanging equally relevant IDs leaves the aggregate score unchanged.

Before generating the holdout, the v2 development results were written and both code hashes were captured. Both result artifacts record the same retriever SHA-256 `a53eb95c8c1e8685842478bf8ac0d6558d9e503884554ac8257983f3c06decef` and matching rules SHA-256 `8eecb11347a5253920622deb84b3a141be3ef89f72db6c78d81d2756c9b09517`. The [30 holdout cases](../../data/heuristic_eval/vn_residential_rental_holdout_v2.json) were separately written after the freeze. Codex authored both the rules and these synthetic cases, so the holdout has temporal separation but lacks independent authorship by a human reviewer. No holdout text, labels or errors were used to revise the frozen rules. Neither dataset measures real-world performance.

Run from `backend/` using an unused output path.

```powershell
..\.venv\Scripts\python.exe evaluate_heuristic_memory.py --output ../data/heuristic_eval/reproduction_v2.json
..\.venv\Scripts\python.exe evaluate_heuristic_memory.py --dataset ../data/heuristic_eval/vn_residential_rental_holdout_v2.json --output ../data/heuristic_eval/reproduction_holdout_v2.json
```

## Results

| Dataset | Version | K | Precision | Recall | Hit | Correct expected-empty |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Development | v1 | 1 | 63.04% | 57.61% | 63.04% | 3/11 |
| Development | v1 | 3 | 65.58% | 63.04% | 67.39% | 3/11 |
| Development | v1 | 5 | 65.58% | 63.04% | 67.39% | 3/11 |
| Development | v2 | 1 | 100.00% | 92.39% | 100.00% | 11/11 |
| Development | v2 | 3 | 100.00% | 100.00% | 100.00% | 11/11 |
| Development | v2 | 5 | 100.00% | 100.00% | 100.00% | 11/11 |
| Holdout | v1 | 1 | 40.00% | 38.33% | 40.00% | 4/9 |
| Holdout | v1 | 3 | 40.00% | 38.33% | 40.00% | 4/9 |
| Holdout | v1 | 5 | 40.00% | 38.33% | 40.00% | 4/9 |
| Holdout | v2 | 1 | 66.67% | 61.67% | 66.67% | 6/9 |
| Holdout | v2 | 3 | 66.67% | 63.33% | 66.67% | 6/9 |
| Holdout | v2 | 5 | 66.67% | 63.33% | 66.67% | 6/9 |

Each cell below gives Precision / Recall / Hit as percentages. All cutoff and scenario-type breakdowns are available in the [development comparison](../../data/heuristic_eval/comparison_v2.json) and [frozen holdout results](../../data/heuristic_eval/holdout_results_v2.json).

| Dataset and type | n | K | v1 | v2 |
| --- | ---: | ---: | --- | --- |
| Development paraphrase | 6 | 1, 3, 5 | 0 / 0 / 0 | 100 / 100 / 100 |
| Development cross-clause | 8 | 1 | 62.50 / 31.25 / 62.50 | 100 / 56.25 / 100 |
| Development cross-clause | 8 | 3, 5 | 77.08 / 62.50 / 87.50 | 100 / 100 / 100 |
| Holdout paraphrase | 6 | 1, 3, 5 | 0 / 0 / 0 | 16.67 / 16.67 / 16.67 |
| Holdout cross-clause | 8 | 1 | 37.50 / 31.25 / 37.50 | 87.50 / 68.75 / 87.50 |
| Holdout cross-clause | 8 | 3, 5 | 37.50 / 31.25 / 37.50 | 87.50 / 75.00 / 87.50 |

The holdout cross-clause group includes one correctly empty case in v2. Across the seven cross-clause cases with expected hits, v2 found at least one in six and retrieved seven of ten expected IDs at K=3. Precision@3 on all 30 holdout cases includes 3 false-positive and 9 false-negative IDs.

### Regressions and residual holdout errors

- **VN-41 at K=1.** `utility_service_fees` displaced `annex_conflict`. Both IDs are relevant, so the metrics tie. Both appear by K=3. This is the only new missing ID at any cutoff on the development set.
- **HO-21 at every cutoff.** v2 returns `repair_reimbursement` where v1 correctly abstained. “Không ghi bên nào … có quyền xin thanh toán lại” places the reimbursement phrase beyond the short negation pattern. This is the only holdout regression relative to v1 at any cutoff.
- **HO-09 and HO-11.** Both still produce irrelevant matches. Vehicle maintenance and a furniture invoice can satisfy housing disruption and lessor identity triggers respectively.
- **HO-01.** Two financial remedies connect through “ngoài khoản lãi này,” outside the supported offset and connector language.
- **HO-13, HO-14, HO-15, HO-16 and HO-18.** The missing expressions describe returning a sum held as guarantee, reimbursing a repair, resetting the monthly price, returning a room and extending a term by default.
- **HO-23, HO-25 and HO-26.** Plain-text splitting leaves numbered article headings separate from the fee terms. The wear baseline relation misses a deduction phrased as “trừ vào tiền cọc tiền thay ván.” The disruption rule misses two clauses connected by a loss-of-use condition across repair, exit and rent provisions.
- **HO-24 at K=1.** Both expected IDs are present by K=3. One result cannot cover the two labeled checklists.

The fixed aliases and short negation patterns have limited coverage of real drafting variation. Segments can contain multiple events, so a clause-level exclusion can still mask a relevant event in the same segment. Adjacent segments and shared field names are proxies for related evidence. Explicit clause IDs could help preserve document structure, but this comparison measures the text entry point only. The holdout is small and provisional, and the two versions share the same seed. The measured gains support continuing offline evaluation, with particular attention to paraphrase coverage, object binding and nested negation.

## Tests

Run from `backend/` with `..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`.

- With `tests/test_heuristic_memory.py`, 31 passed in 0.71s.
- Full backend suite, 224 passed, 19 skipped, 35 subtests passed and 1 teardown error in 7.10s. Windows held the Qdrant test's temporary `kb.db` open, the same failure mode recorded during v1 evaluation.
- With `--ignore=tests/test_qdrant_store.py`, 218 passed, 19 skipped and 35 subtests passed in 5.76s.
