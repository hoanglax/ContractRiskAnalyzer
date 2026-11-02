# Legal AI — Upload API contract draft

Gói này là bản nháp để đưa vào repo và review, không phải contract đã được phê duyệt.

## Nội dung
- `docs/api/api-contract.md`: endpoint, multipart, response, validation, error schema, examples và open decisions.
- `backend/app/api/schemas/analysis.py`: Pydantic v2 response/error models.
- `docs/api/examples/*.json`: fixtures cho success và lỗi cơ bản.

## Tích hợp
Copy các file vào repo tương ứng. Route upload cần khai báo `UploadFile = File(...)`, validate file thực tế và trả `UploadAnalysisResponse`. Cần custom exception handler để trả `ApiErrorResponse`; chỉ thêm schema không tự động thay đổi response của route.

**Chưa gồm:** implementation route, frontend TypeScript types, tests, review sign-off.
