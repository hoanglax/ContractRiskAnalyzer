# Kiến trúc hiện hành

Cập nhật 19/11/2026. Đây là mô tả implementation sau đợt dọn repo, thay cho phần hiện trạng
trong các tài liệu thiết kế ban đầu.

React hoặc `/demo` → FastAPI `/analyses` → `analysis/run.py` → ingestion → detection →
legal basis → explanation → JSON run record → polling và hiển thị.

- Ingestion nhận TXT/DOCX/DOC/PDF có lớp chữ. Không có OCR/vision hoặc ghép bộ ảnh.
- PDF không trích xuất được đầy đủ các trang bị từ chối; không tiếp tục với phần hợp đồng còn lại.
  Trang chữ ngắn được giữ kèm cảnh báo, không tự coi là scan; không bảo đảm nhận diện mọi nội dung
  chỉ có trong ảnh của một PDF vẫn có lớp chữ.
- Phân đoạn sử dụng quy tắc và LLM văn bản dự phòng. Đây không phải tính năng OCR và vẫn được giữ.
- Detection trả mã taxonomy và trích dẫn đã kiểm tra; mức độ lấy từ taxonomy.
- Legal basis lấy nguồn từ SQLite FTS5 và Qdrant nhúng, rồi LLM chọn căn cứ trong ứng viên.
- Explanation tạo giải thích theo căn cứ. Các bước gọi model qua adapter LLM văn bản.
- Run record/upload lưu trong `RUNS_DIR`, mặc định `backend/runs`; Docker dùng volume `runs`.
- Taxonomy nguồn và JSON ở `data/` cấp gốc. Corpus TXT và vector đã commit được giữ nguyên.
  Nguồn luật từng OCR vẫn là dữ liệu TXT cần thiết; giữ provenance trong SOURCES.md.

Không còn `backend/modules`, `backend/scripts`, SQLite `app.db` của luồng thử nghiệm, hay
service Qdrant riêng trong Compose. Không xóa Docker volume Qdrant cũ trong đợt dọn này.

Các sơ đồ `.mmd` trong `../diagrams` là source; PNG có thể dựng lại khi cần.
Tài liệu `system-architecture.md`, `data-flow.md`, `processing-flow.md`, `proposal.md` là
thiết kế qua các thời điểm, không thay thế [API hiện hành](../api/README.md) và
[hướng dẫn chạy](../setup.md). [Legal KB](legal-kb.md) mô tả dữ liệu truy xuất.
