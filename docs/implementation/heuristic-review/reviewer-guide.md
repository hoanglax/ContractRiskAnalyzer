# Reviewer guide

Review the reasoning guidance and its retrieval behavior for Vietnamese residential leases. Use the [entry report](heuristic-review.md) for the seed conditions and the v2 behavior, and the [issue list](prioritized-issues.md) for cases that need closer attention. Record one row per heuristic in the [review sheet](review-sheet.csv). The source snapshot and its examples are draft. A completed worksheet is a review record. Any subsequent change to repository approval status requires an authorized human.

## Review each entry

1. Confirm that the purpose is useful within a residential lease and can be applied to the parties and facts described. Check every mapped risk code for topic, party perspective and scope. In `comments`, identify the specific code behind a disagreement.
2. Read the seed trigger groups and the additional v2 eligibility rules. Exercise one typical positive, one meaning-preserving Vietnamese paraphrase and one realistic negative. Include a condition or negation if it affects the rule. Inspect the selected ID, matched phrases and supporting passage IDs. A matched phrase may belong to a different asset, charge or event.
3. Check exclusions on two inputs. Put a relevant and an unrelated excluded event in separate clauses, then put them together in one passage. Record any suppression or false selection that follows from the passage boundary.
4. Check the evidence checklist and cross-clause dependency. Identify which terms, parties, documents and events must refer to the same thing. Try missing evidence and conflicting evidence. Check that the expected reasoning preserves uncertainty when material facts are absent.
5. Examine the provided examples and any proposed revisions. Decide whether the text describes contract facts or asserts a legal requirement, right, validity, enforceability, tax duty or remedy. Use the authorized legal review workflow for any legal assertion. Keep that review distinct from approving a retrieval checklist.
6. Review the provisional scenario labels themselves. If you disagree with a label, record the scenario ID, proposed expected IDs and rationale in comments. Preserve the frozen artifacts and record any later adjudicated labels separately.

When sampling, use synthetic wording or authorized excerpts. Keep the clause IDs, matched phrases and relevant case IDs in the review record. The published comparisons use the text entry point with no taxonomy hints. A reviewer can additionally exercise explicit clause input and independently chosen taxonomy hints to check scope and ranking.

## Fill out the worksheet

| Column | Value |
| --- | --- |
| `heuristic_id` | Stable ID already filled in. |
| `taxonomy_mapping_correct`, `trigger_correct`, `exclusion_correct`, `cross_clause_correct` | Enter `yes`, `no` or `uncertain`. Use `not_applicable` when the check genuinely has no applicable condition. Explain `no`, `uncertain` and `not_applicable`. An empty JSON exclusion list still merits review for missing exclusions and v2 filters. |
| `legal_review_required` | Enter `yes`, `no` or `uncertain` for the current wording and intended use. Explain what needs review. |
| `reviewer` | Name or approved organizational identifier of the person making the decision. |
| `decision` | Enter `approve`, `request_revision` or `reject` after completing the review. |
| `comments` | Record the reviewed version, date, scenario or clause IDs, rationale, and proposed change or legal review reference if applicable. |

Blank cells mean no decision has been recorded. Preserve the CSV header and quote comments containing commas or line breaks.

## Record the decision

- **Approve.** Use when applicable checks pass, examples have been reviewed and any necessary legal review is resolved or the wording has been narrowed to contract evidence. The authorized maintainer may then make a separate repository change. The loader requires a named `provenance.reviewer` and approved status on every attached example before it accepts an approved heuristic. Keep the ID stable, bump the entry and snapshot versions, and validate the revised snapshot.
- **Request revisions.** Keep the record draft. Describe the precise mapping, phrase, exclusion, evidence request or example to revise. Include positive and negative cases where possible. Re-review the revised entry and examples before changing status.
- **Reject.** Explain why the guidance should be excluded and whether another entry covers the need. Record the rejection in the worksheet and leave the entry draft for this review round. The schema has no `rejected` value. If the authorized maintainer later withdraws the entry, `retired` is the supported withdrawal status and is excluded even when drafts are enabled.

Retrieve draft entries only for review with `include_drafts=True`. Checklist approval alone does not add a legal reference. Any later verified legal rule and its citation must go through the separate legal workflow. See the [knowledge schema and review requirements](../heuristic-memory.md).
