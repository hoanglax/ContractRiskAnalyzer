# Diagrams (mermaid sources + rendered PNG)

Mermaid sources for the module designs, rendered with mermaid-cli (`mmdc`).

## Rendering

Needs: `npm install -g @mermaid-js/mermaid-cli` and any Chromium-based browser.

From this folder:

    mmdc -i ingest_top.mmd -o ingest_top.png -p puppeteer.jsonc -b white -s 2
    mmdc -i route_pdf.mmd -o route_pdf.png -p puppeteer.jsonc -b white -s 2

`puppeteer.jsonc` points puppeteer at a system Chromium-based browser
(executablePath) so no private chromium download is needed; set the path to
your own browser and keep the separate `--user-data-dir` so a running browser
instance is not disturbed.

## Contents

Every diagram exists twice: `.mmd` (mermaid source, the single truth) and
`.png` (regenerated artifact). Together they are the planned architecture
(see `docs/architecture/proposal.md`): document first, then implement.
Diagrams marked *(planned)* describe code that does not match yet.

- `ingest_top` - M1 Ingest top level: load + guards, magic-byte sniffing,
  five routes, _finish quality check, Document and the IngestError codes.
  (`backend/application/modules/ingestion/ingest.py`)
- `route_pdf` - inside `route_pdf`: per-page text-layer quality check,
  vision-OCR fallback for bad pages, header/footer stripping, per-page
  provenance in `raw`. (`ingest.py`)
- `m2_top` - clause map entry `segment_auto`: tier 1, confidence decision,
  tier 2 fallback, keep-tier-1-with-warning paths. (`ingestion/structure_llm.py`)
- `m2_tier1` - deterministic segment(): marker families, chain rules,
  heading/clause building, the five confidence diagnostics.
  (`ingestion/structure.py`)
- `m2_tier2` - LLM fallback: numbered-line prompt, cache, strict answer
  gate, build from line indices only. (`ingestion/structure_llm.py`)
- `m3_top` - whole_doc detector: taxonomy as a closed set of
  codes, full-contract prompt (one call or one per group, to be measured),
  parse, ground, retry up to 2 times with the rejected items and why,
  result dict with every attempt. (`detection/whole_doc.py`)
- `m3_ground` - the gate: unknown taxonomy code rejected first,
  then verbatim-first quote locate with elision fallback; offsets, clause,
  severity and party set by code and the taxonomy row, never by the model.
  (`detection/finding.py`)
- `m3_eval` - eval harness: manifest hashes, predictions-per-file runs,
  rescore without model calls. (`detection/eval.py`)
- `m3_plant` - building the eval set: spec edits applied once
  each, re-ingest stability check, risk/decoy/scaffold roles, taxonomy code
  per planted risk, verbatim spans, validate, write text + gold.
  (`tools/plant_risks.py`, `detection/evalset.py`)
- `m3_score` - scoring one run: greedy one-to-one span matching, right code
  first (strict jaccard >= 0.5 / loose overlap), code check on matched pairs,
  same finding under another code counted as dup, decoy hits, extras, missing listed for a human. (`detection/score.py`)
- `m4_legal` - legal basis per finding: taxonomy citations plus
  retrieval as candidates, model picks passage ids only, ids gated, text from
  the KB, "no basis found" instead of inventing one.
  (`legal_basis/basis.py`)
- `m6_explain` - findings on overlapping quotes grouped into one Item per
  clause; plain-Vietnamese explanation and recommendation per Item, citing law
  only as [Lk] from its LegalBasis list (checked, then resolved to names).
  (`explain/explain.py`)
- `orch_api` - POST /analyses, background run M1 -> M6 one at a time, status
  and result in runs/<id>.json rewritten per stage, GET /analyses/{id} polling.
  (`analysis/run.py`, `api/analyses.py`)
- `llm_chat` *(planned)* - the one chat-completions client: OpenAI-compatible
  API configured in llm.toml, task -> profile, sampling merge, LLMError
  paths; no local-only guard. (`adapters/llm.py`)
- `m5_build` - legal KB build: khoan chunking, SQLite FTS5, verbatim-slice
  verify, dense embed, vectors loaded into embedded Qdrant.
  (`legal_retrieval/kb.py`, `chunk.py`, `dense.py`, `qdrant_store.py`)
- `m5_retr` - interchangeable Retrievers behind one Hit protocol: lexical,
  dense (embedded Qdrant or numpy), hybrid RRF, reranked. (`legal_retrieval/`)
- `m5_eval` - 29-question retrieval eval + bench matrix.
  (`legal_retrieval/eval.py`, `legal_retrieval/bench.py`)

Not drawn: the taxonomy build (`taxonomy/taxonomy.py`, xlsx -> json) is an
offline tool, rerun after each workbook edit; see `data/taxonomy/README.md`.

Sources are the single truth; PNGs are regenerated artifacts.
