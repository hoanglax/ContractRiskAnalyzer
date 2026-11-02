# Risk Taxonomy v1.0.0

**Status:** `draft_pending_team_review` — chưa phải taxonomy đã được Team B phê duyệt.

## Files
- `taxonomy.json`: canonical machine-readable taxonomy, gồm metadata version và 77 nhãn.
- `taxonomy.csv`: bảng phẳng để review/chỉnh sửa; các trường mảng/object được lưu dưới dạng JSON string.
- `CHANGELOG.md`: thay đổi và việc còn chờ.
- `../Risk Taxonomy.xlsx`: workbook nguồn.

## Quy ước mã
- `A-XXX-NN`: rủi ro đối với Bên cho thuê.
- `B-XXX-NN`: rủi ro đối với Bên thuê.
- `XXX`: mã nhóm `AUT`, `DEP`, `MNT`, `TRM`, `PEN`, `RES`, `TAX`.
- `NN`: số thứ tự hai chữ số trong nhóm/bên.
- Mỗi mã duy nhất. Severity chỉ nhận `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.

## Các trường
- `definition`: diễn giải ngắn từ tên nhãn, không phải kết luận pháp lý.
- `applicability_conditions`: dấu hiệu/điều kiện lấy từ workbook gốc.
- `examples`: tình huống giả định được diễn giải từ tên nhãn/dấu hiệu; không phải câu trích hợp đồng thật và cần review trước khi dùng làm dữ liệu huấn luyện.
- `data_quality_issues`: 6 tham chiếu pháp lý không resolve được với legal KB hiện có. Không được hiểu là căn cứ đã được xác minh.

## PRD/SRS alignment
Bộ mã hiện tại trong repo là canonical tạm thời theo đề xuất DEC-01/R-03: `A-XXX-NN` / `B-XXX-NN`. PRD còn ví dụ mã cũ (`PAY-01`, `DEP-01`, `TRM-01`, `LIA-01`, `PEN-01`). Không tự động map mã không rõ nghĩa; Product và Team B cần duyệt mapping rồi cập nhật PRD/SRS đồng bộ.

## Regenerate
Từ thư mục `backend`:

```bash
python -m application.modules.taxonomy.taxonomy build
```

Lệnh đọc workbook, chuẩn hóa/kiểm tra mã và severity, sau đó sinh cả `data/taxonomy/taxonomy.json` và `taxonomy.csv`.

## Approval
Chỉ chuyển `status` sang `approved` sau khi Team B review đủ 77 nhãn và Legal/Data có quyết định rõ ràng cho 6 tham chiếu chưa resolve.
