# Domain specific heuristic memory

Heuristic memory v1 provides curated reasoning checklists for Vietnamese residential rental contracts. The UTF-8 JSON snapshot lives in [data/heuristics](../../data/heuristics/vn_residential_rental.json). The [backend module](../../backend/application/modules/heuristic_memory/) validates and selects records locally using the existing taxonomy loader and Pydantic from the backend's FastAPI dependency. The module has no runtime call site in the analysis pipeline.

## Architecture and authority

Detection builds its closed set of risk codes from the taxonomy and grounds findings through `finding.ground()`. Legal basis selection resolves candidate IDs to corpus passages. Explanation groups findings and checks its citation references against the attached legal basis. Heuristic memory supplies editorial reasoning guidance alongside those existing inputs. The taxonomy mappings identify subject matter and carry no legal authority.

## Snapshot schema

| Record | Fields and meaning |
| --- | --- |
| Snapshot | `schema_version` identifies the supported format. `version` identifies the curated snapshot. IDs are unique within a snapshot, including across record types. |
| `reasoning_heuristic` | Stable lowercase snake-case `id`, `domain`, three-part `version`, title, description, taxonomy `risk_codes` and/or group `categories`, vocabulary, triggers and exclusions. `required_context`, `cross_clause_checks`, `reasoning_checklist` and `expected_behavior` tell a consumer what to examine and how to report uncertainty. |
| Provenance | `origin`, editorial `source`, `status` and optional `reviewer`. Approval requires a named reviewer and approval of all attached examples. |
| Example | A nested `linguistic_pattern` or `illustrative_scenario` with text and review status. Examples are illustrative material. Only phrases explicitly listed in vocabulary or conditions participate in selection. |
| `verified_legal_rule` | Separate record with an ID, corpus law ID, positive article number, official source, rule text and verifier. A heuristic's optional `legal_reference_ids` can reference these records. The loader checks record shape and links. Verification of source, wording, applicability and effective dates belongs to the legal reviewer and corpus workflow. The seed has zero legal records and links. A selection contains reasoning guidance and may carry reference IDs as metadata. |

## Add and review an entry

1. Add a stable ID and the domain. Look up current codes and group identifiers in the [runtime taxonomy](../../data/taxonomy/taxonomy.json). Only link codes whose risk meaning matches the reasoning scenario.
2. Add Vietnamese trigger phrases and narrowly scoped exclusions. Describe the documents or facts needed, the clauses to compare and the expected behavior when evidence is missing. Use synthetic examples, set AI-authored material to `draft` or `pending_review`, and leave legal reference IDs empty until independently verified.
3. Check realistic positive and negative examples, including wording variants, negations and mixed-topic clauses. A domain reviewer checks taxonomy mappings, whether the checklist is usable and whether examples might be mistaken for contract evidence or legal conclusions. Record the reviewer and update status when review is complete. Mark withdrawn guidance `retired`.
4. Increment the entry version when its content or review state changes and the snapshot version whenever published snapshot content changes. Keep the ID stable across revisions. Git history preserves prior snapshots.

## Selection

The current selector adds optional clause input and Vietnamese rental matching rules. See the [v2 implementation and evaluation](heuristic-memory-retriever-v2.md) for the current matching behavior. The lexical behavior below describes the v1 baseline.

From `backend/`:

```python
from application.modules.heuristic_memory import HeuristicRetriever, load

retriever = HeuristicRetriever(load())
hits = retriever.select(
    domain="vn_residential_rental",
    text="Hoàn cọc sau khi ký biên bản trả nhà.",
    risk_codes=["B-DEP-04"],
    top_k=3,
    include_drafts=True,  # Local development only.
)
```

The selector filters by exact domain and review status. Default selection includes approved entries only. Development mode also includes draft and pending-review entries. Retired entries are always excluded. Each trigger group requires at least one phrase match, and at least one group is required. Any exclusion phrase found in the supplied text vetoes the entry. Matching is case-insensitive, Unicode NFC normalized, accent-sensitive and token-based. Whitespace and punctuation delimit tokens.

The selector ranks eligible records by descending counts of exact code matches, taxonomy group matches and distinct matched vocabulary phrases, then by ascending ID. Groups include those implied by codes. Scope is a ranking signal, so a text match can still be selected with no taxonomy overlap. Empty text and `top_k=0` return no hits. Results expose the ID, entry and snapshot versions, matched codes and groups, per-group trigger matches and matched vocabulary.

## Future Context Builder contract

Before detection, a Context Builder can pass a trusted domain, a focused text window from the ingested document and the candidate codes or group already used by detection. It can carry the selected checklist and cross-clause requirements in a reasoning-guidance field and keep clause IDs and offsets with the source evidence. For a post-detection context, pass the grounded finding code and relevant neighboring or referenced clause text. Record selection IDs, versions and match reasons for evaluation. Resolve any legal reference through the existing legal-basis workflow before it is used as a citation. The existing evidence and explanation gates still apply.

## Limits

Literal phrases miss paraphrases and OCR errors. Phrases can also appear in negated text, unrelated clauses or different sections of the same document. Exclusion phrases veto the entire window, so prefer focused windows and explicitly include relevant related clauses when selecting. Selection does not prove a trigger fact, resolve a contradiction or confirm that requested context exists. Every seed entry still requires human review. Detection quality has not been evaluated with heuristic memory.

## Tests

Run from `backend/` using the project's Python environment.

```text
python -m pytest -q tests/test_heuristic_memory.py
```

The suite uses the checked-in taxonomy and synthetic records. It exercises validation, review and version handling, lexical matching, ranking and the separation of reasoning records from legal authority.
