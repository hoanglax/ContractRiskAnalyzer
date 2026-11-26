# Offline Heuristic Context Packet Builder

The [pilot module](../../backend/application/modules/context_packet/) implements the packet boundary from the [integration design](heuristic-context-builder-design.md). It consumes existing grounded findings and legal attachments. The builder remains independently usable offline and does not render a model prompt, search the legal corpus, call a model or persist data. The [optional Explanation adapter](heuristic-explanation-integration.md) provides its runtime call site.

## Input and output

- `ContextRequest` takes a run ID, the current ingested `Document`, a caller-established domain, and one or more `GroundedRisk` records. Supply only findings for one explanation item. Present findings must overlap as in the existing grouping stage, and missing findings get their own packet. Each record carries the existing `Finding` and its already-attached `LegalBasis` entries. The builder checks taxonomy membership and revalidates present-finding offsets with the existing quote locator, including its elision behavior. Missing findings carry no source span and skip heuristic retrieval.
- `ContextData` exposes contract excerpts with exact offsets and clause IDs, risk-to-evidence bindings, legal chunks with packet citation IDs, and guidance with heuristic ID, entry and snapshot versions, match reasons, and checklist fields. Legal reference IDs from heuristics are excluded. `ContextPacket` carries the payload, a budget estimate and structured diagnostics. Diagnostics stay outside the payload.
- The normal constructor passes `include_drafts=False` to v2 and checks the review state again before packing. With the checked-in seed, this produces no guidance. `for_synthetic_tests()` is an explicit constructor for caller-supplied synthetic snapshots. It exercises drafts and pending review records, marks their actual status in the output, and does not change approval state.

### Ordering and budget

The builder reserves the grounded quote and risk data first. It then fits legal passages in supplied order, deduplicated by corpus chunk ID. Budget drops are whole-passage drops. The builder queries v2 with explicit clause IDs, validated risk codes and a bounded anchor window. It tries resolved references in caller order, then the anchor and its immediate neighbors, then the anchor alone. It preserves v2 ranking within each window. A candidate must match a risk code or category and have evidence reaching the anchor or a resolved reference. It packs each guidance entry together with its supporting excerpts. Unused neighbors stay out. Included excerpts are sorted by source offsets.

`PromptBudget` subtracts completion reserve and safety margin from the context window. It also supports a separate guidance cap. The default offline counter uses UTF-8 byte length as a conservative proxy over the exact serialized context JSON, with an injectable counter for a future measured tokenizer. The estimate covers the packet only. A future adapter must account for role framing, instructions and response schema and check the complete serialized prompt. A core overflow returns no payload. Other diagnostics identify missing evidence, invalid or conflicting legal attachments, stale references, retrieval windows shortened to the grounded span, budget omissions and cases with no guidance packed. Required-context fields describe evidence to check. Their presence does not establish that the evidence exists.

### Citation and trust boundary

Only typed legal attachments from the existing upstream legal basis stage enter the citation allowlist. The builder checks attachment shape, excludes known nonstatutory sources and rejects conflicting records for the same chunk ID. The caller supplies provenance from the legal basis stage. The pilot does not independently verify corpus membership, statutory applicability or entailment. Packet-local IDs `L1`, `L2`, and so on are assigned only to passages that fit. `resolve_citations()` validates an explicit list of identifiers against that packet. It rejects chunk IDs or aliases presented as citation IDs, and offsets and heuristic IDs cannot create citations. Any future model adapter still needs the existing explanation checker and semantic review of legal claims.

`ContextData.to_json()` serializes source content and heuristic wording in named data fields without roles or instructions. Text containing JSON or citation-like strings remains a string and cannot register a passage. This data boundary does not establish how a future model will interpret the content.

## Worked synthetic example

Run the following from `backend/` using the project environment. The legal attachment is a mock passage for exercising identifier validation. It makes no legal claim.

```python
from application.modules.context_packet import (
    ContextPacketBuilder, ContextRequest, GroundedRisk, PromptBudget,
)
from application.modules.detection.finding import Finding, ground
from application.modules.detection.lens import from_taxonomy
from application.modules.heuristic_memory import HeuristicRetriever, load
from application.modules.ingestion.ingest import Document
from application.modules.legal_basis.basis import LegalBasis
from application.modules.taxonomy import taxonomy

text = "Bên A hoàn cọc trong 7 ngày kể từ khi ký biên bản trả nhà."
doc = Document(text=text, source={})
tax = taxonomy.load()
findings, rejected = ground(
    [Finding("present", "Cần làm rõ mốc tính hạn.", code="B-DEP-04", quote=text)],
    doc,
    from_taxonomy(tax),
)
assert not rejected
basis = LegalBasis("synthetic_fixture", None, "", "Synthetic citation fixture.",
                   "", "retrieval", 71)
retriever = HeuristicRetriever(load(tax=tax), tax=tax)
request = ContextRequest(
    "synthetic-run", doc, "vn_residential_rental",
    (GroundedRisk(findings[0], (basis,)),),
)
budget = PromptBudget(context_window=8000, completion_reserve=500, safety_margin=200)

packet = ContextPacketBuilder(retriever, tax=tax).build(request, budget)
assert packet.data is not None and packet.data.guidance == ()
assert packet.resolve_citations(["L1"])[0].chunk_id == 71
assert packet.data.contract[0].text == text

testing = ContextPacketBuilder.for_synthetic_tests(retriever, tax=tax)
synthetic_packet = testing.build(request, budget)
guidance, = synthetic_packet.data.guidance
assert (guidance.heuristic_id, guidance.review_status) == ("deposit_refund_clock", "draft")
```

The [synthetic test scenarios](../../backend/tests/test_context_packet.py) also cover early termination, emergency repair responsibility, repeated clause labels, separate return and key clauses, tight budgets and tampered citation identifiers.

## Future adapter boundaries

The existing clause map has offsets and potentially repeated display labels. The pilot uses `clause_id(start, end)` over the cleaned document and records whether each excerpt is a grounded span or a clause-map slice. A future Short-term Memory adapter can supply an optional `ClauseReferences` value with a run ID, SHA-256 of the cleaned UTF-8 text and clause IDs. The builder rejects stale scopes and rehydrates only from the supplied document. The adapter is responsible for resolving and authorizing the reference relationship before supplying it. No session store, separate segmentation model or shared context cache is introduced.

The explanation owner should agree on the citation namespace and prompt-specific allowlist before wiring a production adapter. Today the pilot validates a structured citation list, while the existing explanation checker handles citations embedded in generated prose. A production adapter also needs full prompt token accounting. The review path can exercise the pilot independently of both teams' production changes.
