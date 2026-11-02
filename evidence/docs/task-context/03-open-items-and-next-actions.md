# Open Items — Handoff / Next Actions

## Ưu tiên 1 — Upload API contract

1. Mở code hiện tại `backend/application/api/analyses.py`.
2. Cùng Team B quyết định contract cuối:
   - `201 {id, status}` theo code hiện tại, hay
   - `202 {analysis_id, status}` theo draft.
3. Quyết định upload endpoint có chỉ tiếp nhận file hay tiếp tục khởi chạy pipeline background.
4. Tạo/bổ sung Pydantic schemas (archive draft hiện tại không có file schema dù README có liệt kê).
5. Thực hiện validation type/size, normalized error handler và tests.
6. Đồng bộ frontend TypeScript types/service.
7. Lưu review evidence: reviewer, ngày, commit/PR, các điểm đã duyệt.

## Ưu tiên 2 — Taxonomy

1. Team B/Product review 77 labels.
2. Lập bảng mapping giữa mã PRD cũ và taxonomy code mới; không tự suy đoán mapping.
3. Legal/Data xác minh 6 legal references chưa resolve.
4. Đảm bảo legal corpus/test corpus hiện diện để chạy citation test.
5. Chốt examples có được dùng trong dataset hay chỉ là ví dụ minh họa.
6. Sau review, cập nhật version/status/changelog và commit.

## Evidence nên lưu cho mỗi task trong các sprint tiếp theo

- Task ID và mô tả yêu cầu gốc.
- Link PR/commit và branch.
- Danh sách file thay đổi.
- Lệnh chạy và log test.
- Ảnh chụp kết quả UI/API nếu task có giao diện.
- Reviewer và kết quả review.
- Các điểm còn mở / quyết định chưa chốt.
- Mức hoàn thành và lý do tính phần trăm.

## Cách tính phần trăm

Không lấy phần trăm chỉ từ số file đã tạo. Chia task thành deliverables/acceptance criteria, đánh trọng số, rồi đánh dấu:
- Done: có artifact/implementation và bằng chứng.
- Partial: đã có draft hoặc code nhưng chưa tích hợp/test/review.
- Blocked: phụ thuộc quyết định hoặc dữ liệu bên ngoài.
