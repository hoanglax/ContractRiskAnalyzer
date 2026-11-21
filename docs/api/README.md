# API hiện hành

Cập nhật 19/11/2026 sau khi bỏ OCR và luồng retrieval cũ. Entrypoint: `application.main:app`.

| Method | Route | Kết quả |
|---|---|---|
| GET | `/health` | 200, `{"status":"ok"}` |
| POST | `/analyses` | Multipart `file`; 201, `{"id":"<12 ký tự hex>","status":"queued"}` |
| GET | `/analyses/{id}` | 200 với run record; 404 nếu không tồn tại/ID sai |
| GET | `/demo` | Giao diện HTML upload và polling |

Định dạng hỗ trợ: TXT, DOCX, DOC và PDF có lớp chữ sử dụng được.
Ảnh PNG/JPEG/WEBP/TIFF/HEIC bị từ chối bằng `unsupported_type`, kể cả đổi tên sang PDF/TXT.
PDF có trang không có chữ hoặc lớp chữ hỏng bị từ chối bằng `no_text`, kể cả PDF trộn chữ/scan.
Trang chỉ chứa header/footer cũng không được bỏ qua âm thầm. Trang chữ ngắn có thể được giữ
kèm cảnh báo; trang ký tên ngắn ở cuối vẫn được chấp nhận. Trang trắng thật cần được bỏ trước
khi gửi vì không phân biệt chắc chắn với trang scan chỉ bằng bộ trích xuất chữ.

Việc kiểm tra nội dung diễn ra trong background task: request hợp lệ có thể nhận **201 queued**
rồi polling trả `status=failed`, `stage=ingest`, `error={code,message}`. Không tự đổi thành
phản hồi 415 đồng bộ. File rỗng nhận 400 `detail`; thiếu field nhận lỗi validation FastAPI.
Các trạng thái vẫn là `queued`, `running`, `done`, `failed`; các stage là `ingest`, `detect`,
`legal_basis`, `explain`. Các trường kết quả `document`, `items`, `warnings`, `usage` giữ nguyên.

```json
{"status":"failed","stage":"ingest","error":{"code":"unsupported_type","message":"image input is not supported; provide a text-layer PDF, DOCX, DOC or TXT file"}}
```

Ví dụ trên chỉ minh họa một phần run record, không phải toàn bộ response.

Bản [đối chiếu ngày 09/11](implemented-contract-2026-11-09.md) được giữ làm lịch sử trước khi bỏ OCR.
Draft 202/UUID `analysis_id`, schema không dùng và các ví dụ dự thảo đã được lưu trữ ngoài repo;
chúng không phải contract runtime. Backend vẫn chưa có cơ chế làm sạch PII hoặc retention policy
được xác nhận; chỉ dùng dữ liệu mẫu/được phép khi gọi model từ xa.
