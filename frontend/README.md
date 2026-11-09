# ContractRiskAnalyzer frontend

React + TypeScript + Vite UI for the **existing** FastAPI analysis pipeline.

## Run locally

1. Start the existing backend as documented in `../backend/README.md` (default port 8000).
2. From `frontend/`, run `npm ci` then `npm run dev`.
3. Open `http://localhost:5173`.

The Vite dev server proxies `/analyses` and `/health` to `http://127.0.0.1:8000`. The frontend uses the **implemented endpoints**, not the unapproved draft API schema:

- `POST /analyses`: multipart upload field `file`; currently HTTP 201 with `{id, status: "queued"}`.
- `GET /analyses/{id}`: poll run status (`queued`, `running`, `done`, `failed`) and consume `document.text`, `items`, and `warnings`.

The results view reuses the data layout of the backend's `/demo`: source text highlights, risk items, missing-content items, explanations and legal-basis snippets. It does **not** invent a clause endpoint or legal citations. Back-end results and cited laws require separate legal review.

## Scope / known gaps

- Implements Sprint 2 UI-01 (single-file upload) and the available part of UI-02 (extracted contract text and risk items). Structured segmentation with dedicated clause IDs, numbers, source offsets, and API routes is not yet exposed as a stable contract by this backend; do not treat this UI as completed clause-segmentation acceptance.
- File formats depend on backend ingestion adapters and configured providers. Do not upload real personal information to remote LLM/Vision services until the PII-redaction requirements in the SRS DEC-01 addendum are satisfied.
- `docs/api/api-contract.md` includes draft response shapes that currently differ from the running `/analyses` API; reconcile them with the team before a production release.
