# Optional Context Packet integration in Explanation

`EXPLANATION_CONTEXT_PACKET` is off when unset. Set it to `1` to request the integration. The server also needs `EXPLANATION_CONTEXT_WINDOW` set to the actual context window of the configured `explain` model, in tokens. The profile must specify a positive `max_tokens` or `max_completion_tokens` for the completion reserve. For example, for a profile whose context window is 8,192 tokens:

```dotenv
EXPLANATION_CONTEXT_PACKET=1
EXPLANATION_CONTEXT_WINDOW=8192
```

The adapter uses the same captured profile configuration for budget calculation and dispatch. It reserves the configured completion allowance and a 256-token safety margin, then measures the UTF-8 byte length of the serialized messages, including their roles and system instructions. Bytes are a proxy for tokens. This can reject prompts that a provider would accept, and the safety margin cannot guarantee fit with a provider's tokenizer, chat template, or hidden overhead. The operator supplies the model's actual context limit. A missing or invalid budget disables enhancement for that run and records a warning. In that case the legacy path uses its existing unbudgeted behavior. Set the feature flag to `0` or remove it to restore the default.

## Runtime flow

1. Detection grounds findings against the ingested contract. The existing legal basis stage attaches passages to each finding.
2. With the flag enabled, [analysis orchestration](../../backend/application/analysis/run.py) passes the run ID through the optional `explain(..., context_run_id=...)` argument. Explanation uses its existing grouping rules. Overlapping findings share one explanation call, and the packet contains each finding with its own attached basis. Missing findings remain separate.
3. The [adapter](../../backend/application/modules/explain/packet_context.py) builds a packet using the active document and the server's Vietnamese residential rental workflow domain. It loads the local reviewed snapshot once per explanation run. It never requests drafts. The current all-draft seed produces zero guidance. The adapter does not consult Short-term Memory or create session state.
4. A packet with approved guidance and a fitting complete prompt goes to the existing `explain` model task. Trusted instructions are a separate system message. Contract text, model-generated findings, legal passages and heuristic text arrive as JSON data in the user message. Instructions explicitly restrict contract facts to source excerpts, legal support to the rendered legal passages, and checklists to guidance. Typed fields prevent embedded text from registering citations or taking on a message role. A future evaluation still needs to test how models respond to adversarial content.
5. Explanation validates the reply against the exact legal attachments shown to the model, in packet order. It retains the existing citation checker and, on the enhanced path, rejects recognized written-out statutory references and citation aliases such as `[L01]`. The public item retains aligned original basis, evidence offsets and codes. The successful explanation attempt also records the active citation-ID-to-corpus-chunk mapping, document digest, clause IDs, approved heuristic IDs and versions, and packet diagnostics. This metadata adds no source text to the attempt record.

## Fallbacks and scope

| Condition | Behavior |
| --- | --- |
| Flag off | Legacy prompt, validation and output shape. The heuristic snapshot is not loaded. |
| No approved match, missing finding span or packet retrieval error | Use the legacy prompt and its existing citation scope if it fits. Record packet diagnostics or the error type. |
| Approved guidance with no attached legal passage | The enhanced prompt can use contract reasoning. The citation allowlist is empty. |
| Packet or enhanced message exceeds the budget | Omit guidance. Use the legacy prompt only if it fits. If it also exceeds the configured budget, keep the item, evidence and basis and report why no explanation was sent. |
| A legal chunk is omitted but the enhanced prompt fits | Only the rendered legal list can be cited. Labels are resolved through the original attached corpus records. |
| A legal attachment is misaligned, or fallback would reuse an invalid or conflicting attachment | Suppress the explanation call and record an item warning. Misaligned attachments are also removed from the affected explanation item's basis. |
| The enabled profile overrides the messages sent to the provider | Suppress the explanation call and record an item warning because the sent messages would bypass the local budget and citation scope. |

The adapter adds no model calls or legal search. The existing explanation provider settings still govern where explanation data is sent. Enhanced prompts can include more contract excerpts than the legacy prompt. Enable this only for the intended residential rental workflow and a model profile authorized to receive those excerpts. The citation check establishes an allowed reference and its label. It cannot establish whether a legal passage supports every statement in a response.

## Tests

The [integration tests](../../backend/tests/test_explanation_context.py) use synthetic contract text, temporary run records, an in-memory approval fixture and mocked model responses. They exercise both flag states, missing evidence, citation integrity, prompt overflows and retrieval failure. The checked-in snapshot retains its draft state.
