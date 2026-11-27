# Offline Explanation A/B results

Evaluation 1.0.0 on `vn_residential_explanation_ab_v1`.
Both arms used the same synthetic inputs and scripted reply for each case.
The results measure infrastructure behavior. Semantic explanation quality was not evaluated.

Fixture checks passed for 11/11 legacy cases and 11/11 enabled cases.

| Case | A outcome | B mode and outcome | A / B prompt bytes | B guidance | Checks |
| --- | --- | --- | ---: | --- | --- |
| AB-01-deposit-refund | accepted | enhanced / accepted | 1552 / 2739 | deposit_refund_clock | Pass |
| AB-02-early-exit | accepted | enhanced / accepted | 1512 / 2458 | deposit_forfeiture | Pass |
| AB-03-repair-no-law | rejected | enhanced / rejected | 1586 / 2587 | repair_reimbursement | Pass |
| AB-04-cross-clause | accepted | enhanced / accepted | 1625 / 2976 | return_milestones | Pass |
| AB-05-no-approved | accepted | legacy / accepted | 1557 / 1557 | — | Pass |
| AB-06-no-match | accepted | legacy / accepted | 1518 / 1518 | — | Pass |
| AB-07-dropped-chunk | accepted | enhanced / rejected | 2671 / 2722 | deposit_refund_clock | Pass |
| AB-08-budget-overflow | accepted | skipped / skipped | 1474 / 0 | — | Pass |
| AB-09-retrieval-error | accepted | legacy / accepted | 1551 / 1551 | — | Pass |
| AB-10-missing-term | accepted | legacy / accepted | 1458 / 1458 | — | Pass |
| AB-11-citation-alias | accepted | enhanced / rejected | 1535 / 2722 | deposit_refund_clock | Pass |
