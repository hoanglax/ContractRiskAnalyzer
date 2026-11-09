# API-01 — Implemented API Contract (repository snapshot)

**Status:** AS-IMPLEMENTED / reference for Team A–B review — **not approved canonical API**  
**Reviewed:** 2026-11-09  
**Evidence:** `backend/application/api/analyses.py`, `backend/application/main.py`, `backend/application/analysis/run.py`, `backend/application/modules/ingestion/ingest.py`, `frontend/src/App.tsx`, and `backend/tests/test_analysis.py`.

> This document records code behavior rather than prescribing a new contract. The existing `docs/api/api-contract.md` (Draft v0.1) is a *proposal*, not the implemented endpoint contract. Do not change runtime API to fit the draft without a team decision.

## 1. Implemented endpoints

| Method | Path | Success | Purpose |
|---|---|---|---|
| `GET` | `/health` | `200` | Returns `{"status":"ok"}`. |
| `POST` | `/analyses` | `201` | Accepts **one** multipart field `file`, stores upload, queues an analysis. |
| `GET` | `/analyses/{rid}` | `200` | Returns saved analysis record (progress and eventual results). |
| `GET` | `/demo` | `200` | Server-rendered demo HTML (not part of public JSON API). |

There is **no implemented `/api/v1/analyses` route** in this snapshot. Frontend React calls `/analyses` directly through Vite proxy.

## 2. Upload request and response

```http
POST /analyses
Content-Type: multipart/form-data; boundary=...
```

Required field: `file` (`UploadFile`; exactly one file used by the route). On success, response is **HTTP 201**:

```json
{"id":"a34bb0932186","status":"queued"}
```

`id` is a **12-character lowercase hexadecimal string**, created from UUID and shortened; it is **not** the draft's `analysis_id` UUID. This is an illustrative ID shape, not a stable example run.

**Synchronous validation currently present in route:** `file.read()` is checked for zero bytes (`HTTP 400`, body `{"detail":"empty file"}`). Missing `file` is handled by default FastAPI request validation (typically `HTTP 422` with `detail` array). The route itself does **not** check size or supported type before returning 201.

**Asynchronous ingestion:** content-based type sniffing, 50 MiB baseline, parsing, OCR routing and other `IngestError`s run *after* the upload is accepted. A corrupt, unsupported, excessive-size or unreadable file can receive `201 queued` first and later become `failed` at stage `ingest` with an error code such as `too_large`, `unsupported_type`, `not_implemented`, `encrypted`, `no_text`, or `conversion_failed`. The 50 MiB limit is **current code baseline, not a formally approved product limit**. Recognizing TIFF/HEIC signatures does not imply full Vision support.

Example request using PowerShell:

```powershell
curl.exe -X POST http://localhost:8000/analyses -F "file=@sample.txt;type=text/plain"
```

Do not manually set the multipart `Content-Type` boundary when using `curl -F` or browser `FormData`.

## 3. Polling a run

```http
GET /analyses/{rid}
```

`200` response is a full, growing record with fields (some absent or null until finished):

```json
{
  "id": "a34bb0932186",
  "created": "2026-11-09T10:56:09",
  "filename": "sample.txt",
  "status": "running",
  "stage": "detect",
  "error": null,
  "warnings": [],
  "document": null,
  "findings": [],
  "bases": [],
  "items": [],
  "calls": {},
  "stage_seconds": {},
  "versions": {}
}
```

The JSON above is a **shape illustration**, not a literal response fixture for a specific run. Other fields appear after stages, including `usage` and final `seconds`. `document` contains extracted contract text and source details; never use real PII when sharing recordings or fixtures.

| Field | Current values / meaning |
|---|---|
| `status` | `queued` → `running` → `done` or `failed` |
| `stage` | `null`, `ingest`, `detect`, `legal_basis`, `explain` (processing stage, not status enum) |
| `error` | `null` or `{ "code": "...", "message": "..." }` on failure |
| `warnings` | Array of `{ "stage": "...", "message": "..." }` |
| `document` | Extracted document, including `text`, `source`, `pages`, `structure`, `warnings` when ingest succeeds |
| `findings`, `bases`, `items` | Detection, legal evidence and explanation results; may legitimately be empty |
| `calls`, `stage_seconds`, `versions` | Operational metadata, counters and versions |

When a finding has no validated legal basis, the explanation may be `null` and warning(s) recorded. **Do not treat lack of legal evidence as authorization to invent citations.**

Example polling:

```powershell
$r = Invoke-RestMethod 'http://localhost:8000/analyses/a34bb0932186'
$r | Select-Object id,status,stage,error
```

An unknown or malformed `rid` returns **HTTP 404** with a FastAPI-style `detail` response, e.g. `{"detail":"no such analysis"}`.

## 4. Current error contract vs proposed contract

| Situation | Implemented response | Draft v0.1 proposal | Reconciliation needed? |
|---|---|---|---|
| Accepted upload | `201` + `{id,status}` | `202` + `{analysis_id,status}` | **Yes** |
| Missing multipart file | FastAPI validation, normally `422` + `detail` | `400` + structured `error` | **Yes** |
| Empty upload | `400` + `{"detail":"empty file"}` | `400` + `error.code=EMPTY_FILE` | **Yes** |
| Invalid/unsupported/oversize contents | `201` first, then `status=failed`, `stage=ingest`, `error` in polled run | Immediate `413` / `415` etc. | **Yes** |
| Unknown run ID | `404` + `detail` | Not covered in upload-only draft | Extend documentation |
| Status enums | `queued/running/done/failed` | Same enums, different success ID field | Align schemas |

`backend/application/api/schemas/analysis.py` contains a **draft** `UploadAnalysisResponse` (`analysis_id: UUID`), but `create_analysis` neither uses that response model nor returns that shape. Do not advertise the Pydantic draft as the live API schema. `docs/api/examples/upload-success-202.json` and error examples are **proposed examples**, not captured production responses.

## 5. Security, concurrency and operational constraints

- User-provided contracts are untrusted and may contain sensitive PII. **Current external LLM PII redaction is not verified.** Do not send real identifiable contracts to remote providers before DEC-01 privacy gates are implemented and tested.
- Analysis jobs run in-process as FastAPI background tasks; `run.py` serializes them with a threading lock. Do not claim 20–30 parallel analyses based only on this code.
- Analysis records and uploads are saved under the configured `RUNS_DIR`; retention/access control need a separate decision.
- `/demo` remains available for development; frontend and demo use the same API endpoints.
- Do not include API keys or raw contract text in API examples, shared logs or repository commits.

## 6. Actions required to close API-01

- [x] Inventory implemented endpoint paths/methods and upload/polling shapes (static code review).
- [x] Record discrepancies between the draft API contract and runtime behavior.
- [ ] **Team review** decide canonical `201/{id}` or `202/{analysis_id}`, validation timing and error schema.
- [ ] Synchronize approved decision across Pydantic schemas, backend routes, frontend types, `docs/api/examples/`, tests and OpenAPI.
- [ ] Add API-level tests for agreed negative and success cases; confirm behavior in running Docker image, not just the source snapshot.
- [ ] Validate privacy and data retention requirements under DEC-01.

**Suggested sheet status:** `Đang làm — đã đối chiếu API code và lập as-implemented contract; chờ Team A/B chốt contract, đồng bộ schema và nghiệm thu`.
