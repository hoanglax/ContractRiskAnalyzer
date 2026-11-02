# Upload API Contract — Draft v0.1

> **Trạng thái:** Draft for Team B review  
> **Mục tiêu hoàn thành:** khoảng 60–70%  
> **Phạm vi:** Chỉ chốt contract khởi đầu cho upload một file hợp đồng/request. Chưa bao gồm API lấy trạng thái/kết quả, upload nhiều ảnh, authentication, persistence policy hoặc retry policy đầy đủ.

## 1. Quy ước trạng thái quyết định

| Nội dung | Trạng thái | Ghi chú |
|---|---|---|
| FastAPI backend; React + TypeScript + Vite frontend | ĐÃ THỐNG NHẤT | Theo SAD ADR-01 |
| F04 Risk Detection và F05 Risk Classification độc lập | ĐÃ THỐNG NHẤT | Không ảnh hưởng trực tiếp upload contract |
| `POST /analyses` nhận một file/request | HIỆN TRẠNG REPO | SRS DEC-01 ghi nhận route hiện tại |
| `202 Accepted` + `analysis_id` + `status=queued` | ĐỀ XUẤT CONTRACT | Cần Team B review; status `queued` khớp hiện trạng được ghi nhận |
| Giới hạn 50 MiB/file | BASELINE ĐỀ XUẤT, CHỜ XÁC NHẬN | Không coi là giới hạn sản phẩm đã phê duyệt |
| File types TXT, DOC/DOCX, PDF, PNG/JPEG/WEBP | THEO ROUTE HIỆN CÓ ĐƯỢC GHI NHẬN | TIFF/HEIC chưa có MIME route Vision hoàn chỉnh |
| Error schema bên dưới | ĐỀ XUẤT | Cần thống nhất với FastAPI exception handlers và frontend |
| `request_id` trong error | ĐỀ XUẤT | Có thể bỏ nếu chưa có middleware tạo request ID |

## 2. Endpoint

| Thuộc tính | Giá trị |
|---|---|
| Method | `POST` |
| Path | `/analyses` |
| Success status | `202 Accepted` |
| Request content type | `multipart/form-data` |
| Multipart field | `file` |
| Cardinality | Một file cho mỗi request |

**Lưu ý versioning:** SAD từng nêu endpoint dự kiến `/api/v1/analyses`, nhưng SRS DEC-01 ghi nhận repo hiện tại dùng `POST /analyses`. Draft này ưu tiên path đang có trong repo để tránh mô tả sai hiện trạng. Nếu nhóm muốn thêm prefix `/api/v1`, cần đổi đồng thời route, tài liệu, frontend service và tests; chưa tự ý áp dụng trong draft này.

## 3. Multipart request

### Field

| Field | Type | Required | Mô tả |
|---|---|---:|---|
| `file` | Binary file | Yes | Một file hợp đồng |

### Ví dụ cURL

```bash
curl -X POST "http://localhost:8000/analyses" \
  -H "accept: application/json" \
  -F "file=@./samples/contract.docx"
```

Không tự đặt `Content-Type: multipart/form-data` thủ công khi dùng `curl`/browser FormData; client cần tự sinh boundary.

### Định dạng dự kiến được nhận

| Định dạng | Extension | MIME tham khảo | Ghi chú |
|---|---|---|---|
| Plain text | `.txt` | `text/plain` | Parser text |
| Word | `.doc`, `.docx` | `application/msword`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | Parser DOC/DOCX |
| PDF | `.pdf` | `application/pdf` | PDF text; PDF scan có thể đi Vision OCR nếu cấu hình hợp lệ |
| PNG | `.png` | `image/png` | Vision OCR |
| JPEG | `.jpg`, `.jpeg` | `image/jpeg` | Vision OCR |
| WEBP | `.webp` | `image/webp` | Vision OCR |
| TIFF / HEIC | `.tif`, `.tiff`, `.heic` | varies | Chưa hỗ trợ route MIME Vision hoàn chỉnh; không nhận như định dạng đã hỗ trợ |

MIME trong bảng là giá trị tham khảo. Backend nên kiểm tra extension và nội dung thực tế/signature khi khả thi; không tin riêng `Content-Type` do client gửi.

## 4. Validation

1. Bắt buộc có field `file`.
2. Từ chối file rỗng (`0 bytes`).
3. Chỉ chấp nhận các định dạng đã có route: TXT, DOC/DOCX, PDF, PNG, JPEG, WEBP.
4. Từ chối TIFF/HEIC cho tới khi route MIME tương ứng được triển khai.
5. Baseline kích thước hiện có trong code là `50 MiB/file`; đây là **đề xuất chờ xác nhận**, không phải quyết định sản phẩm cuối cùng. Đặt qua cấu hình, không hard-code vào schema.
6. Không chốt giới hạn tổng dung lượng bộ ảnh hoặc PDF page cap trong contract này.
7. Không hỗ trợ upload nhiều file trong một request ở phiên bản contract này.
8. File hợp lệ về định dạng chưa đồng nghĩa nội dung trích xuất thành công; chất lượng OCR/extraction thuộc bước xử lý tiếp theo.

### Validation order đề xuất

`missing file` → `empty file` → `extension/MIME route` → `size limit` → kiểm tra khả năng đọc/parse sâu trong ingestion.

## 5. Success response

HTTP `202 Accepted`

```json
{
  "analysis_id": "8f3c2f7e-7f4e-4d9c-9f1a-8e7b6c5d4a3b",
  "status": "queued"
}
```

| Field | Type | Required | Ý nghĩa |
|---|---|---:|---|
| `analysis_id` | string (UUID) | Yes | ID của phiên phân tích |
| `status` | enum | Yes | Trạng thái xử lý ban đầu |

### Status enum ở contract upload

- `queued`: đã tiếp nhận và xếp hàng xử lý.
- `running`: đang xử lý.
- `done`: xử lý hoàn tất.
- `failed`: xử lý thất bại.

Các giá trị trên phản ánh enum code hiện tại được SRS DEC-01 ghi nhận. Không mở rộng sang các trạng thái chi tiết trong SAD (`VALIDATING`, `EXTRACTING`, ...) trong contract upload v0.1. Có thể bổ sung sau khi thống nhất API trạng thái.

## 6. Error response

### Schema đề xuất

```json
{
  "error": {
    "code": "UNSUPPORTED_FILE_TYPE",
    "message": "File type is not supported.",
    "details": {
      "field": "file",
      "allowed_extensions": [".txt", ".doc", ".docx", ".pdf", ".png", ".jpg", ".jpeg", ".webp"]
    }
  }
}
```

`request_id` chưa đưa vào schema bắt buộc vì cần middleware tạo ID và bảo đảm frontend có thể dùng để báo lỗi. Nếu Team B đồng ý, có thể thêm ở phiên bản kế tiếp.

### Error codes / HTTP status đề xuất

| HTTP | `code` | Khi nào |
|---:|---|---|
| 400 | `FILE_REQUIRED` | Thiếu multipart field `file` |
| 400 | `EMPTY_FILE` | File có kích thước 0 byte |
| 413 | `FILE_TOO_LARGE` | Vượt giới hạn cấu hình (baseline 50 MiB đang chờ xác nhận) |
| 415 | `UNSUPPORTED_FILE_TYPE` | Extension/MIME route không được hỗ trợ, gồm TIFF/HEIC ở trạng thái hiện tại |
| 422 | `INVALID_FILE` | File có định dạng được nhận diện nhưng không đọc/parse được ở bước kiểm tra đồng bộ |
| 500 | `INTERNAL_ERROR` | Lỗi không dự kiến khi tiếp nhận request |

**Phân biệt:** lỗi upload/validation đồng bộ trả HTTP error; lỗi phát sinh sau khi đã nhận request và tạo analysis run phải cập nhật run status thành `failed` (nếu xử lý được), không đổi thành một response upload mới.

FastAPI mặc định có thể trả `detail` cho lỗi validation. Backend cần exception handler để chuẩn hóa về schema trên. Cần quyết định riêng cách ánh xạ lỗi validation framework sang `400` hoặc `422`.

## 7. Ví dụ JSON

### 7.1 Success — `202 Accepted`

```json
{
  "analysis_id": "8f3c2f7e-7f4e-4d9c-9f1a-8e7b6c5d4a3b",
  "status": "queued"
}
```

### 7.2 Missing file — `400 Bad Request`

```json
{
  "error": {
    "code": "FILE_REQUIRED",
    "message": "A file must be provided in the 'file' field.",
    "details": {
      "field": "file"
    }
  }
}
```

### 7.3 Unsupported file — `415 Unsupported Media Type`

```json
{
  "error": {
    "code": "UNSUPPORTED_FILE_TYPE",
    "message": "The uploaded file type is not supported.",
    "details": {
      "field": "file",
      "received_filename": "contract.heic",
      "allowed_extensions": [".txt", ".doc", ".docx", ".pdf", ".png", ".jpg", ".jpeg", ".webp"]
    }
  }
}
```

### 7.4 File too large — `413 Payload Too Large`

```json
{
  "error": {
    "code": "FILE_TOO_LARGE",
    "message": "The uploaded file exceeds the configured size limit.",
    "details": {
      "field": "file",
      "max_bytes": 52428800
    }
  }
}
```

`max_bytes` ở ví dụ là 50 MiB (`50 * 1024 * 1024`) theo baseline code/đề xuất hiện tại; cần thay bằng giá trị cấu hình thực tế.

### 7.5 Empty file — `400 Bad Request`

```json
{
  "error": {
    "code": "EMPTY_FILE",
    "message": "The uploaded file is empty.",
    "details": {
      "field": "file"
    }
  }
}
```

## 8. Pydantic / Frontend mapping

- Backend dùng các model trong `backend/app/api/schemas/analysis.py`.
- Frontend tạo TypeScript types tương ứng: `UploadAnalysisResponse`, `ApiErrorResponse`, `AnalysisStatus`.
- Frontend gửi `FormData` với key chính xác là `file`; không tự set multipart boundary.
- Không parse success response theo một shape khác (ví dụ `data.analysisId`) nếu backend chưa thống nhất.
- JSON examples trong `docs/api/examples/` dùng làm fixtures cho backend tests và frontend mock/tests.

## 9. Những điểm còn mở — chưa được coi là đã chốt

1. Team B xác nhận path cuối cùng là `/analyses` hay `/api/v1/analyses`.
2. Team B xác nhận 50 MiB/file hay chọn giới hạn khác sau thử nghiệm.
3. Xác nhận MIME/signature validation và cách xử lý file giả extension.
4. Chốt có thêm `request_id` vào error schema hay không.
5. Chốt HTTP status cho lỗi thiếu field và lỗi validation của FastAPI (`400`/`422`).
6. Chốt status enum dùng chung cho upload và API polling.
7. Review bảo mật/privacy: không log nội dung file, PII hoặc API key; không gửi hợp đồng thật tới external LLM trước khi anonymization được triển khai/kiểm thử hoặc external calls bị vô hiệu hóa.

## 10. Checklist review Team B

- [ ] Backend xác nhận path, method, multipart field và success status.
- [ ] Backend xác nhận Pydantic schemas và exception mapping.
- [ ] Frontend xác nhận field `file`, response shape và error handling.
- [ ] Hai bên xác nhận extension/MIME allowlist.
- [ ] Hai bên xác nhận cách lấy size limit từ config.
- [ ] Team B review các ví dụ JSON và dùng chúng làm test fixtures.
- [ ] Sau review, cập nhật contract version và đồng bộ backend schemas, frontend types, fixtures, tests.

**Tiêu chí hoàn thành draft:** tài liệu và schema đã có cấu trúc + ví dụ để review; chưa được đánh dấu Approved cho tới khi hai thành viên Team B xác nhận các mục còn mở.
