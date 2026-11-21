# Dọn repo theo báo cáo A, B và E

Ngày thực hiện: 19/11/2026. Nhánh: `repo-cleanup`.

## Phạm vi đã thực hiện

| Nhóm | Thay đổi | Lý do và phần được giữ |
|---|---|---|
| A01–A08 | Xóa `backend/tests_backup`, cache cũ trong `backend/app`, ảnh mẫu trong `frontend/src/assets`, `frontend/public/icons.svg`, `backend/application/config.py`, `frontend/.env.example` | Bản sao, tài nguyên không dùng hoặc file rỗng. Giữ `data/README.md` theo bản báo cáo đã chỉnh. |
| B — dữ liệu và code cũ | Xóa `backend/data/Risk Taxonomy.xlsx`, `backend/data/taxonomy`, `backend/modules`, `backend/scripts`, `backend/tests/test_legal_retrieval.py`, `data/legal_corpus/legal_corpus.json` | Luồng thử nghiệm cũ. Giữ taxonomy cấp gốc, corpus TXT, vector và retrieval trong `backend/application/modules`. |
| B — API và tài liệu | Xóa schema `backend/application/api/schemas/analysis.py`, API draft và examples cũ, `docs/api/IMPLEMENTED-README.txt`, `evidence`, PNG sơ đồ | Không dùng trong runtime hiện hành. Giữ bản đối chiếu API lịch sử, source `.mmd`; bổ sung API và kiến trúc hiện hành. |
| B — môi trường | Bỏ service Qdrant riêng và khai báo volume của service khỏi Compose; bỏ dependency `sentence-transformers` của retrieval cũ | Qdrant nhúng vẫn được giữ cùng thư viện `qdrant-client`. Không xóa Docker volume đang tồn tại. |
| E — bỏ OCR/ảnh | Xóa `vlm.py`, `test_ocr.py`; gỡ render ảnh PDF, gọi vision, route ảnh và ghép nhiều ảnh; bỏ biến OCR trong cấu hình mẫu và `.env` cục bộ | LLM văn bản, phân đoạn, detection, căn cứ pháp lý và giải thích vẫn giữ. |
| E — giao diện và tài liệu | Giới hạn bộ chọn file; cập nhật demo, hướng dẫn, API, sơ đồ; bổ sung kiểm thử từ chối ảnh/PDF thiếu chữ | TXT, DOCX, DOC và PDF có lớp chữ vẫn được hỗ trợ. |

Sửa các lệnh khởi động còn trỏ tới `app.main:app` thành `application.main:app`; bỏ dấu rào Markdown
trong `run-frontend.bat` để file có thể chạy như lệnh Windows.

## Quy tắc PDF sau thay đổi

- Ảnh bị từ chối bằng `unsupported_type`, kể cả đổi đuôi thành PDF/TXT/DOCX.
- PDF có trang không có chữ hoặc chữ không đọc được bị từ chối toàn bộ bằng `no_text`.
- Trang trắng thật cũng bị từ chối; cần bỏ trang trắng trước khi gửi lại.
- Trang chỉ còn header/footer sau khi làm sạch không bị bỏ qua âm thầm.
- Trang ít chữ vẫn được giữ; trang ngắn không phải trang cuối có cảnh báo để người dùng đối chiếu.
- Không thể bảo đảm phát hiện mọi phần nội dung nằm trong ảnh nếu cùng trang vẫn có chữ đọc được.
- PDF đã được công cụ bên ngoài thêm lớp chữ có thể vẫn đọc được. Hệ thống không tự OCR hay đối chiếu ảnh gốc.
- API vẫn nhận request hợp lệ bằng 201 và báo lỗi ingestion qua kết quả polling.

## Bản sao lưu và khôi phục

86 file đã được lưu trước khi xóa, kèm đường dẫn, kích thước và SHA-256.
Bản sao nằm ngoài repo trong thư mục kết quả của phiên làm việc:

- `repo-cleanup-backup-2026-11-19.zip`
- `cleanup-delete-manifest.json`

ZIP đã kiểm tra toàn vẹn. Đường dẫn trong ZIP tính từ gốc repo; nên giải nén vào thư mục riêng để
đối chiếu trước khi chép lại những file muốn khôi phục. ZIP lưu các file đã xóa, không phải ảnh chụp
toàn bộ repo. Các chỉnh sửa code/tài liệu được xem bằng `git diff`.

Không thay đổi `docs/plans`, dữ liệu nguồn hiện hành, vector đã commit, run record, model cache
hoặc Docker volume. Chưa commit hoặc push các thay đổi.

## Kiểm chứng

| Kiểm tra | Kết quả |
|---|---|
| Frontend `npm run build` và `npm run lint` | Đạt. |
| `docker compose config --quiet` | Đạt. |
| `git diff --check` | Đạt. |
| Test liên quan trực tiếp: `tests.test_analysis`, `tests.test_pdf`, `tests.test_sniff` | 46 test: 41 đạt, 5 bỏ qua do thiếu công cụ/fixture tùy chọn; không có lỗi. |
| Toàn bộ backend: `unittest discover -s tests -t . -v` | 212 test: 192 đạt, 19 bỏ qua, 1 thất bại; thêm 1 lỗi khi dọn tài nguyên sau nhóm test Qdrant. Chưa phải lượt kiểm thử xanh hoàn toàn. |
| Bản sao lưu | Kiểm tra ZIP và SHA-256 của đủ 86 file; các đường dẫn tương ứng đã được xóa khỏi repo. |

Hai vấn đề của bộ test đầy đủ nằm ở các file không thay đổi so với HEAD:

1. `tests.test_taxonomy.RealWorkbook.test_committed_json_is_current` so sánh chuỗi JSON chính xác.
   File JSON hiện hành khác độ thụt lề với kết quả sinh từ Excel. Đã đối chiếu dữ liệu sau parse JSON:
   hai bên bằng nhau. Giữ nguyên workbook, JSON, bộ sinh và test này.
2. `tests.test_qdrant_store.Qdrant.tearDownClass` gặp `WinError 32` khi xóa `kb.db` tạm vì kết nối
   còn giữ file trên Windows. Các test chức năng Qdrant chạy qua; lỗi xuất hiện ở bước dọn tài nguyên.
   Test và code retrieval liên quan không đổi trong đợt này.

Log: `cleanup-backend-tests-final.log` và `cleanup-changed-tests.log`, cùng thư mục với ZIP sao lưu.
Các test API dùng LLM/retriever giả lập, không xác nhận chất lượng model thật. Kiểm tra PDF chữ trong
test API giả lập kết quả trích xuất; các test chuyển đổi file thật cần Poppler/LibreOffice bị bỏ qua.
Docker daemon không chạy nên chưa build/khởi động container hoặc xác nhận pipeline với model thật.
