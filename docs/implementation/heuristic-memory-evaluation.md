# Heuristic Memory v1 evaluation

The unchanged retriever found all 18 direct positives and missed all six paraphrases. At K=5 it found a relevant heuristic in seven of eight cross-clause scenarios, but recovered only 62.5% of the expected IDs per cross-clause scenario on average. It correctly returned an empty list in 3 of 11 expected-empty scenarios. These are provisional results on synthetic fixtures. Real-world retrieval and downstream reasoning quality remain unmeasured.

## Knowledge base audit

Snapshot 1.0.0 contains 18 heuristics, all in `vn_residential_rental` and all `draft`. There are zero pending, approved or retired heuristics. All 18 examples are draft. There are zero verified legal rules and zero heuristic links to legal rules.

No heuristic declares a category directly. The table counts distinct heuristics in each runtime taxonomy group implied by their risk codes. A heuristic can appear in several groups. Unlisted taxonomy groups have zero entries.

| Category | Count |
| --- | ---: |
| DEP | 8 |
| TRM | 5 |
| PEN | 4 |
| MNT | 4 |
| AUT | 3 |
| TAX | 1 |

Each row examines the entry's lexical triggers, exclusions, required evidence and comparison. The retriever uses the first two for eligibility and returns the rest as checklist metadata. In the trigger column, “+” means both phrase groups must match.

| Heuristic ID | Triggers and exclusions | Required context and cross-clause comparison | Finding and proposed change |
| --- | --- | --- | --- |
| `deposit_identity` | Deposit or reservation + advance or offset; veto for no deposit | Reservation receipt, installments and first invoice; compare signing terms and rent credit | Generic offset matches penalty settlement (VN-44). Require a link to reservation or advance rent and distinguish from settlement deductions. |
| `deposit_refund_clock` | Refund wording; home-purchase reservation veto | Interval, start event, signers and utility cycle; compare handover and settlement terms | Misses ordinary descriptions of returning security (VN-27). A negated refund phrase can also match. Distinguish a timed refund from forfeiture and scope purchase exclusions to the transaction. |
| `deposit_deductions` | Deduction or offset against deposit; no exclusion | Amount, itemization, receipts and settlement; compare charges with payment, repair and exit terms | Distinguish deductions at settlement from crediting advance rent. Ask for the source clause, charge evidence and balance for each item. |
| `deposit_forfeiture` | Loss, confiscation or nonrefund; no exclusion | Forfeiture events, notice, cure and initiating party; compare early exit, mutual exit and recovery | A negated occurrence on an unrelated deposit still triggers (VN-22). Bind the remedy to the lease deposit and preserve negation. |
| `termination_notice_clock` | Termination or recovery + notice or cure; brokerage termination veto | Delivery channel, receipt date, day count and cure period; compare breach, notice and return | Unrelated events combine in VN-23, while an exit without canonical wording is missed in VN-40. Bind notice to actor and event, and recognize midterm exit language. |
| `renewal_vs_exit` | Extension + expiry, advance notice or nonrenewal; no exclusion | End date, renewal, rejection deadline and extension price; compare term, annex and early exit | Nonrenewal alone can satisfy both phrase groups. Require the object to be the lease term, rather than a card or warranty (VN-26). |
| `lessor_identity` | Lessor or owner + title or mandate wording; no exclusion | Unit, owner, signer, mandate and payee; compare party block, signatures, authority and payment | Title or authorization may concern another object. Check referenced unit and powers. Clarify overlap with `sublease_scope` under B-AUT-01 and A-AUT-01. |
| `co_owner_consent` | Shared ownership wording; no exclusion | Co-owners, property and consent; compare title, signature and authorization | Generic shared-property wording can refer to common areas. Bind ownership to the leased unit and detect descriptions without the term “đồng sở hữu” (VN-30). |
| `sublease_scope` | Sublet, re-rent or head lease; parking sublet veto | Head lease, consent, unit and both expiries; compare original permission with sublease and approval | Parking veto suppresses residential evidence elsewhere (VN-43). Scope exclusions to the object and distinguish re-renting from occupancy permission. |
| `wear_baseline` | Wear, deterioration or original condition; no exclusion | Inventory, photos, age, move-out condition and cause; compare handover, repair and deductions | “Nguyên trạng” is too broad (VN-25). Require a premise or fixture and a condition or restoration issue. Recognize existing defects across records (VN-42). |
| `repair_reimbursement` | Repair or maintenance + reimbursement, urgency or notice; vehicle repair veto | Notice, response, urgency, consent and invoice; compare repair, alteration and repayment | Notice alone activates it without a cost question (VN-34). Require a funding or emergency-payment signal and localize the vehicle veto. |
| `repair_disruption` | Maintenance or renovation + loss of use; no exclusion | Affected area, dates, access, accommodation and rent; compare work access, rent and exit | Work and disruption can refer to different assets. Require a relation to loss of residential use. The two repair heuristics can both apply when cost and use are separately at issue. |
| `rent_increase` | Three literal rent-change phrases; no exclusion | Fixed term, formula, cap, notice and dates; compare rent table, annex, renewal and improvements | Misses price changes expressed as a new amount or a new period (VN-28, VN-46). Compare time-scoped rent amounts and distinguish midterm resets from renewal prices. |
| `utility_service_fees` | Any service or utility fee term; brokerage fee veto | Included services, rates, meters, billing cycle and payee; compare inclusive rent, fee annex and exit settlement | A generic charge mention can be incidental. Require a relevant fee term or payment ambiguity. Localize brokerage veto to avoid masking building charges (VN-41). |
| `tax_incidence` | Tax or invoice + allocation wording or rent price; no exclusion | Price, included tax, payment on behalf and proof; compare pricing, tax, invoice and payment | Invoice for an appliance plus rent price triggers it (VN-37). Bind the invoice or tax to rental charges and track economic cost separately from filing or remittance. |
| `overlapping_remedies` | Penalty, damages or late interest + forfeiture, offset or connector; no exclusion | Breach event, formulas, loss evidence and offsets; compare default, remedy and settlement terms | Generic connectors and negated remedies combine across clauses (VN-40). Require two remedy references linked by event and account for offsets or alternatives (VN-44). |
| `return_milestones` | Handover or return + key, meter, record or delay wording; no exclusion | Initial inventory, access devices, readings, tender and signature dates; compare late fees, rent cutoff and refunds | Also selects initial handover (VN-21); require move-out direction or timing. Co-selection with `deposit_refund_clock` is appropriate when return controls refund (VN-39). |
| `annex_conflict` | Annex or supplement + conflict, priority, replacement or a common lease field; no exclusion | Signed versions, dates, amendment scope, parties and priority; compare the same field across documents | An unrelated annex and ordinary rent mention suffice (VN-20). Require competing terms for the same field or an express modification. Extend the comparison explicitly to fees if retaining VN-41's label. |

The review found overlapping scopes and conflicting selection signals, with no explicit pair of checklists that directs opposite outcomes on the same stated facts. `deposit_identity` and `deposit_deductions` share offset language but address different stages. `deposit_forfeiture` and `deposit_refund_clock` can both match “không hoàn cọc” despite pointing at different questions. `annex_conflict` is a general document comparison adjacent to more specific pricing, deposit and renewal checks. Define when a document-level checklist adds distinct work before selecting both.

### Legal claims to review

The entries mostly frame contractual fact checks. The following wording or concepts could be read as legal conclusions if carried into an explanation. Keep the output conditional on contract text and evidence until a reviewer verifies the applicable law.

- `deposit_refund_clock` says a period “may start only after” certain events. Frame these as candidate start events named by the contract. Review any claim that a condition can lawfully defer repayment or that partial release is owed.
- `deposit_identity` calls the security refundable. Track the amount described as refundable and its stated conditions. `deposit_deductions`, `deposit_forfeiture` and `overlapping_remedies` can map charges and sums, with independent review needed for entitlement, enforceability or cumulative recovery.
- `lessor_identity`, `co_owner_consent` and `sublease_scope` ask for authorization evidence. Review any conclusion about required signatures, sufficient authority, permission or legal effect.
- `termination_notice_clock`, `renewal_vs_exit` and `return_milestones` reconstruct contractual timelines. Any mandatory notice rule, legal effect of delivery or acceptance, or statutory cutoff needs separate verification.
- `wear_baseline`, `repair_reimbursement`, `repair_disruption`, `rent_increase` and `utility_service_fees` compare contractual costs and obligations. Review any asserted legal right to recover a cost, alter rent, or shift liability.
- `tax_incidence` already routes statutory responsibility to the legal workflow. Any filing, remittance or penalty obligation needs verification separate from the parties' cost allocation.
- `annex_conflict` asks which term controls. Treat express priority and signatures as evidence and review any legal conclusion about precedence or validity.

## Benchmark and scoring

The UTF-8 [dataset](../../data/heuristic_eval/vn_residential_rental_v1.json) contains 46 fictional Vietnamese scenarios. The root records `schema_version`, `domain`, `source` and `label_status`. Every label inherits `provisional_requires_human_review`. Each scenario contains an `id`, `type`, `text`, `expected_ids` and a Vietnamese `explanation`. The expected IDs identify reasoning checklists relevant to the supplied window. An empty list represents no relevant checklist in this knowledge base. An ambiguous case can still merit a checklist when missing facts are the reason to retrieve it.

The [evaluator](../../backend/evaluate_heuristic_memory.py) supplies only text and domain, explicitly enables drafts and leaves risk codes and categories empty. It retrieves the ranking at K=5 and scores prefixes at 1, 3 and 5. Labels, scenario IDs, types and explanations stay in the evaluation code. The baseline uses the original seed and retriever, with file hashes in the report. The direct positives deliberately cover every entry and use literal wording, so they measure basic coverage. The benchmark was authored with knowledge of the rules and should remain a diagnostic set. Confirm improvements on a separately authored holdout, with labels reviewed independently.

Scores are macro averages across scenarios, with each window weighted equally. Precision@K divides relevant retrieved IDs by the number returned up to K. Recall@K divides by the number expected. Hit@K is 1 when any expected ID is returned. If expected and selected are both empty, all three scores are 1. If exactly one set is empty, all three are 0. A correct empty outcome is also counted separately. False positives and negatives are unmatched IDs at each cutoff, so one scenario can contribute multiple errors.

From `backend/` using the project's Python environment, write a new report at an unused path. The evaluator opens the output in exclusive creation mode to preserve the saved baseline.

```powershell
..\.venv\Scripts\python.exe evaluate_heuristic_memory.py --output ../data/heuristic_eval/reproduction.json
```

## Measured baseline

Each cell shows Precision / Recall / Hit in percent. The [baseline JSON](../../data/heuristic_eval/baseline_v1.json) records selected IDs in rank order, expected IDs and both error lists for every scenario at every cutoff.

| Scenario type | Count | @1 | @3 | @5 |
| --- | ---: | --- | --- | --- |
| Overall | 46 | 63.04 / 57.61 / 63.04 | 65.58 / 63.04 / 67.39 | 65.58 / 63.04 / 67.39 |
| Positive | 18 | 100 / 100 / 100 | 100 / 100 / 100 | 100 / 100 / 100 |
| Negative | 8 | 25 / 25 / 25 | 25 / 25 / 25 | 25 / 25 / 25 |
| Paraphrased | 6 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| Ambiguous | 6 | 66.67 / 66.67 / 66.67 | 66.67 / 66.67 / 66.67 | 66.67 / 66.67 / 66.67 |
| Cross-clause | 8 | 62.50 / 31.25 / 62.50 | 77.08 / 62.50 / 87.50 | 77.08 / 62.50 / 87.50 |

At K=1 there were 10 false-positive IDs and 16 false-negative IDs. At K=3 and K=5 there were 10 and 11 respectively. At every cutoff, 3 of 11 expected-empty cases were correctly empty (27.27%). The largest returned list contained three IDs, accounting for the identical K=3 and K=5 results. VN-44 ranks an irrelevant deposit identity check ahead of both expected checks. VN-41 and VN-43 show two relevant matches suppressed by exclusions that fire elsewhere in the window.

The dataset samples short, clean excerpts and a fixed, known domain. It gives no estimate for full documents, OCR noise, other rental domains, taxonomy-assisted ranking, reviewer agreement, or changes in analysis quality. Class mix and the empty-set scoring convention affect the reported averages.

## Priorities for a follow-up

1. Improve abstention and localize exclusions. Eight of 11 expected-empty windows emitted a result. Test event, object and negation binding for initial handover, incidental invoices and unrelated notice. Check whether line- or clause-local exclusions recover VN-41 and VN-43.
2. Improve paraphrase recall using independently sourced Vietnamese wording and structured comparisons for money, dates and roles. Check recall on an independently authored holdout and measure the effect on empty-window accuracy.
3. Improve cross-clause coverage and ranking. Link clauses through shared amounts, events or document fields, and compare a separately labeled run with independently supplied taxonomy hints. Measure whether the relevant settlement checks move ahead of `deposit_identity` in patterns such as VN-44.
4. Have domain reviewers adjudicate labels, narrow overlapping mappings and review contract-versus-law boundaries. Keep the original baseline artifact and record subsequent runs separately.
