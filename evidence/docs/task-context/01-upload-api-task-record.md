# TASK-API-01 — Upload API contract (draft)

**Snapshot:** 2026-11-02  
**Mức tiến độ tham chiếu:** khoảng 60–70% cho phần *draft contract*; không áp dụng cho implementation endpoint.  
**Trạng thái:** Draft for Team B review — chưa approved.

## 1. Mục tiêu task

Tạo một contract khởi đầu để Frontend và Backend có cùng cách hiểu về:
- Endpoint và HTTP method.
- Multipart request.
- Success response chứa ID và trạng thái phân tích.
- Validation đầu vào.
- Error response schema và HTTP status.
- Ví dụ JSON dùng làm tài liệu và test fixtures.

Phạm vi chỉ là upload một file cho mỗi request. Không bao gồm API polling/result, multi-image upload, auth, persistence policy hoặc retry policy đầy đủ.

## 2. Artifact đã tạo

- `docs/api/api-contract.md`
- `docs/api/examples/upload-success-202.json`
- `docs/api/examples/error-file-required-400.json`
- `docs/api/examples/error-empty-file-400.json`
- `docs/api/examples/error-file-too-large-413.json`
- `docs/api/examples/error-unsupported-file-415.json`

Các file này được lưu trong `evidence/upload-api-draft/`.

**Lưu ý về Pydantic schema:** README của gói draft mô tả file `backend/app/api/schemas/analysis.py`, nhưng file schema đó không có trong archive đã kiểm tra. Vì vậy không ghi nhận Pydantic schema là artifact đã bàn giao trong evidence pack này. Cần tạo/bổ sung và kiểm tra lại nếu muốn đưa vào repo.

## 3. Contract đang được đề xuất

| Thuộc tính | Giá trị trong draft |
|---|---|
| Method | `POST` |
| Path | `/analyses` |
| Request | `multipart/form-data` |
| Multipart field | `file` |
| Cardinality | Một file/request |
| Success | `202 Accepted` |
| Response ID | `analysis_id` (UUID) |
| Initial status | `queued` |
| Error shape | `{ "error": { "code", "message", "details" } }` |

Allowlist draft: TXT, DOC, DOCX, PDF, PNG, JPG/JPEG, WEBP. TIFF/HEIC chưa được xem là định dạng đã hỗ trợ đầy đủ.

Giới hạn 50 MiB/file là baseline đề xuất/chờ xác nhận, không phải quyết định sản phẩm cuối cùng.

## 4. Quan trọng: phân biệt draft với implementation hiện tại

Trong snapshot repo được kiểm tra, file `backend/application/api/analyses.py` hiện có:

- Router prefix: `/analyses`.
- `POST /analyses` nhận `UploadFile`.
- Đọc nội dung file; từ chối file rỗng với HTTP 400.
- Tạo run thông qua `run.create(...)`.
- Đưa `run.analyze(...)` vào `BackgroundTasks`.
- Trả HTTP **201** với response `{ "id": rid, "status": "queued" }`.
- Có `GET /analyses/{rid}` để lấy run record.

Do đó implementation hiện tại **chưa khớp** draft contract ở các điểm:
- HTTP status hiện tại là 201, draft đề xuất 202.
- Field hiện tại là `id`, draft đề xuất `analysis_id`.
- Chưa có bằng chứng trong route này về normalized error schema.
- Validation trong route được kiểm tra chỉ thấy xử lý file rỗng; chưa thấy đầy đủ size/type/MIME validation.
- Route hiện tại có kích hoạt background analysis; vì vậy chưa thể nói task “upload only, không chạy pipeline” đã được hoàn thành.

Không được sửa tài liệu để che đi khác biệt này. Cần một quyết định có chủ đích: cập nhật contract theo code hiện tại, hoặc thay implementation để tuân theo contract đã được Team B duyệt.

## 5. Bằng chứng và cách kiểm tra

**Tài liệu:** `evidence/upload-api-draft/api-contract.md`  
**Ví dụ:** `evidence/upload-api-draft/examples/*.json`  
**Code hiện trạng:** `backend/application/api/analyses.py` trong repo snapshot nguồn.

Lệnh kiểm tra thủ công:
```bash
# Chạy backend theo hướng dẫn hiện tại của repo
# Sau đó kiểm tra OpenAPI tại /docs và thử POST /analyses với:
# 1) file hợp lệ
# 2) file rỗng
# 3) file sai định dạng
# 4) file vượt giới hạn
```

Chưa ghi nhận automated tests cho contract này trong artifact draft. Không tuyên bố đã kiểm thử đủ các trường hợp.

## 6. Tiêu chí nghiệm thu còn thiếu

- [ ] Team B xác nhận path và success status.
- [ ] Team B xác nhận response field (`id` hay `analysis_id`).
- [ ] Chốt file allowlist và cách kiểm tra MIME/signature.
- [ ] Chốt size limit từ config.
- [ ] Chuẩn hóa error handler để response thực tế khớp schema.
- [ ] Thống nhất HTTP 400/422 cho lỗi validation.
- [ ] Tạo Pydantic schema trong đúng vị trí repo và test serialization.
- [ ] Frontend TypeScript types + upload service khớp contract.
- [ ] Có integration tests cho success và các lỗi.
- [ ] Làm rõ upload endpoint có khởi chạy pipeline hay chỉ tiếp nhận file.
- [ ] Hai thành viên Team B review và ghi nhận sign-off.

## 7. Hướng dẫn cho người tiếp quản

1. Đọc contract draft và route hiện tại song song.
2. Không copy nguyên draft vào frontend trước khi Team B chốt các khác biệt.
3. Chốt một response shape duy nhất.
4. Viết Pydantic request/response/error schemas.
5. Viết validation ở backend và custom exception handler.
6. Thêm tests cho từng HTTP status/error code.
7. Đồng bộ TypeScript types và UI error handling.
8. Chỉ đổi trạng thái task sang Done sau khi có test và review evidence.
