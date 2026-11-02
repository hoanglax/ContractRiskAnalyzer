# Taxonomy changelog

## 1.0.0 — 2026-11-02 (draft; pending Team B/Product review)

- Chuẩn hóa mã nhãn theo mẫu `A-XXX-NN` / `B-XXX-NN`; canonical group codes lấy từ workbook hiện tại: `AUT`, `DEP`, `MNT`, `TRM`, `PEN`, `RES`, `TAX`.
- Sửa severity typo trong workbook: `MEDUIUM` và `MEIDUM` thành `MEDIUM`; cả 77 nhãn dùng đúng một trong `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
- Sửa lỗi gõ rõ ràng trong workbook: `tải sản`, `Phái`, `giũ/trừ`, `quyêt`, `khuyêt`, `BLDC`, `BDLS`; chuẩn hóa tên văn bản `Bộ luật Kinh doanh bất động sản 2023` thành `Luật Kinh doanh bất động sản 2023`.
- Bổ sung `definition`, `applicability_conditions`, `examples` cho từng nhãn. Ví dụ được ghi rõ là tình huống giả định, diễn giải từ tên nhãn/dấu hiệu, không phải câu trích hợp đồng thật.
- Xuất `taxonomy.json` và `taxonomy.csv`; gắn version và trạng thái chờ review.
- Giữ lại 6 tham chiếu chưa resolve trong legal KB ở `data_quality_issues`; không tự đoán hoặc xóa căn cứ pháp lý.

## Pending before approval

- Team B review toàn bộ 77 nhãn, đặc biệt severity, điều kiện áp dụng và ví dụ.
- Product/Team B đối chiếu PRD/SRS: PRD còn ví dụ mã cũ như `PAY-01`, `DEP-01`, `TRM-01`, `LIA-01`, `PEN-01`; thống nhất mapping/cập nhật tài liệu trước khi đánh dấu approved.
- Legal/Data xác minh 6 tham chiếu còn trong `data_quality_issues` với nguồn pháp luật chính thức và legal corpus.
- Chạy test trong repo và commit workbook + JSON + CSV + changelog + generator cùng một PR.
