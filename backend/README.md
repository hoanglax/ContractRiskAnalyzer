# Backend ContractRiskAnalyzer

Backend hiện tại dùng FastAPI với entrypoint `application.main:app`.
Hướng dẫn cài đặt, dựng dữ liệu và chạy Docker/local: [docs/setup.md](../docs/setup.md).
API hiện hành: [docs/api/README.md](../docs/api/README.md).

## Luồng xử lý

`POST /analyses` → lưu upload → ingestion → detection → legal basis → explanation.
`GET /analyses/{id}` trả trạng thái và kết quả; `/demo` là giao diện kiểm tra.
Đầu vào: TXT, DOCX, DOC và PDF có lớp chữ. Không còn OCR hoặc nhận ảnh hợp đồng.
PDF có trang không có chữ/lớp chữ lỗi bị từ chối toàn bộ; cần bỏ trang trắng thật trước khi gửi.

## Dữ liệu

- `../data/legal_corpus/*.txt`: nguồn dựng SQLite FTS5 trong `cache/legal_kb.db`.
- `../data/legal_vectors/`: vector đã commit để dựng Qdrant nhúng trong `cache/qdrant`.
- `../data/taxonomy/taxonomy.json`: taxonomy runtime; workbook nguồn ở `../data/Risk Taxonomy.xlsx`.
- `runs/` hoặc `RUNS_DIR`: file upload và kết quả; không phải cache để xóa tùy ý.

Không cần server Qdrant riêng. Bộ `modules/legal_retrieval`, CLI trong `scripts/` và
JSON mẫu của luồng cũ đã được gỡ; không sử dụng hướng dẫn `backend/data/app.db` nữa.

## Kiểm thử

Từ thư mục `backend`, sau khi cài dependency:

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -t . -v
```

Bộ kiểm thử API dùng model giả lập và KB trong thư mục tạm, không gọi LLM thật.
Một số test tích hợp cần Poppler, LibreOffice hoặc corpus mẫu tùy chọn tại `data/test`.
Test bị bỏ qua vì thiếu công cụ/fixture không chứng minh nhánh đó đã được kiểm thử.
