# TASK-DATA-01 — Risk Taxonomy v1.0.0

**Snapshot:** 2026-11-02  
**Mức tiến độ tham chiếu:** 75%  
**Trạng thái artifact:** `draft_pending_team_review` — chưa phải taxonomy được phê duyệt.

## 1. Mục tiêu task

Hoàn thiện Taxonomy v1 ở mức dữ liệu và công cụ:
- Sửa lỗi nhập liệu rõ ràng trong workbook.
- Chuẩn hóa severity.
- Kiểm tra mã nhãn duy nhất.
- Bổ sung definition, applicability conditions và examples.
- Xuất JSON/CSV có version.
- Có changelog và test để tái tạo/kiểm tra dữ liệu.

## 2. Artifact đã tạo/cập nhật

| File | Vai trò |
|---|---|
| `data/Risk Taxonomy.xlsx` | Workbook nguồn đã sửa lỗi nhập liệu |
| `data/taxonomy/taxonomy.json` | Dữ liệu machine-readable chính |
| `data/taxonomy/taxonomy.csv` | Bản phẳng phục vụ review |
| `data/taxonomy/README.md` | Quy ước, cấu trúc, cách regenerate |
| `data/taxonomy/CHANGELOG.md` | Lịch sử thay đổi và việc còn mở |
| `backend/application/modules/taxonomy/taxonomy.py` | Generator, chuẩn hóa, validation, load |
| `backend/tests/test_taxonomy.py` | Unit/integration tests cho taxonomy |

## 3. Kết quả dữ liệu trong snapshot

- Version: `1.0.0`
- Status: `draft_pending_team_review`
- Tổng số nhãn: **77**
- Số nhóm: **7**
- Mã duy nhất: **77/77**
- Severity hợp lệ: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`
- Phân bố severity:
  - LOW: 5
  - MEDIUM: 21
  - HIGH: 45
  - CRITICAL: 6

Các nhóm mã hiện có: `AUT`, `DEP`, `MNT`, `TRM`, `PEN`, `RES`, `TAX`.

Quy ước mã hiện tại:
- `A-XXX-NN`: rủi ro đối với Bên cho thuê.
- `B-XXX-NN`: rủi ro đối với Bên thuê.
- `XXX`: mã nhóm.
- `NN`: số thứ tự hai chữ số.

## 4. Nội dung đã chuẩn hóa/bổ sung

- Sửa typo severity `MEDUIUM` và `MEIDUM` thành `MEDIUM`.
- Sửa các lỗi gõ rõ ràng như `tải sản`, `Phái`, `giũ/trừ`, `quyêt`, `khuyêt`, `BLDC`, `BDLS`.
- Chuẩn hóa tên văn bản `Bộ luật Kinh doanh bất động sản 2023` thành `Luật Kinh doanh bất động sản 2023`.
- Bổ sung cho mỗi nhãn:
  - `definition`: diễn giải ngắn từ tên nhãn, không phải kết luận pháp lý.
  - `applicability_conditions`: dấu hiệu/điều kiện từ workbook.
  - `examples`: tình huống giả định diễn giải từ tên nhãn/dấu hiệu; không phải trích dẫn hợp đồng thật.

## 5. Kiểm thử đã chạy

Lệnh:
```bash
cd backend
PYTHONPATH=. python -m unittest tests.test_taxonomy -v
```

Kết quả snapshot:
- 9 tests được phát hiện.
- 8 passed.
- 1 skipped: `test_cited_articles_exist`, do `data/test/kb` không có trong snapshot.
- Các test còn lại xác nhận:
  - Severity scale và group parsing.
  - Chuẩn hóa code và tách fields.
  - Các giá trị không nhận diện được được ghi nhận thành issues.
  - Severity sai bị từ chối.
  - Duplicate code bị từ chối.
  - JSON hiện tại khớp dữ liệu tái sinh từ workbook.
  - Metadata version/status, 77 labels, fields bổ sung và CSV tồn tại.
  - `load()` đọc được taxonomy.

Không diễn giải test skipped thành passed. Kiểm tra legal citations vẫn chưa được xác minh bởi corpus trong snapshot.

## 6. Các vấn đề chưa giải quyết

### 6.1. Đối chiếu PRD/SRS

PRD còn các ví dụ mã cũ như `PAY-01`, `DEP-01`, `TRM-01`, `LIA-01`, `PEN-01`, trong khi taxonomy hiện tại dùng `A-XXX-NN` / `B-XXX-NN`.

Chưa tự động mapping vì chưa có quyết định chính thức về quan hệ giữa mã cũ và mã mới. Product/Team B cần duyệt mapping và đồng bộ PRD/SRS.

### 6.2. Tham chiếu pháp lý

Còn 6 tham chiếu không resolve được trong legal KB hiện có, được giữ trong `data_quality_issues`. Các nhóm liên quan gồm:
- B-AUT-03: Luật Nhà ở 2013.
- B-TAX-01: Nghị định 123/2020/NĐ-CP và Thông tư 96/2015/TT-BTC.
- B-TAX-04: Thông tư 96/2015/TT-BTC.
- B-TAX-05: Nghị định 123/2020/NĐ-CP và Nghị định 70/2025/NĐ-CP.

Không xem các tham chiếu này là đã được xác minh. Cần Legal/Data kiểm tra văn bản chính thức và quyết định có đưa vào corpus hay không.

### 6.3. Review nội dung

Definition, applicability conditions và examples được tạo theo dữ liệu workbook và cần Team B/Legal review. Không dùng examples làm ground-truth training labels trước khi review.

## 7. Hướng dẫn regenerate

Từ thư mục `backend`:
```bash
python -m application.modules.taxonomy.taxonomy build
```

Lệnh đọc workbook, chuẩn hóa/kiểm tra và sinh:
- `data/taxonomy/taxonomy.json`
- `data/taxonomy/taxonomy.csv`

Sau khi thay đổi workbook:
1. Chạy generator.
2. Chạy test suite taxonomy.
3. Review diff của JSON/CSV.
4. Cập nhật changelog.
5. Commit workbook + generated files + generator + tests cùng một PR.

## 8. Điều kiện chuyển sang Approved

- [ ] Team B review đủ 77 nhãn.
- [ ] Product xác nhận mapping mã với PRD/SRS.
- [ ] Legal/Data xử lý 6 tham chiếu chưa resolve.
- [ ] Review severity, applicability và examples.
- [ ] Legal corpus có mặt để chạy kiểm tra citation.
- [ ] CI/test pass trên môi trường repo chuẩn.
- [ ] Taxonomy được commit và có reviewer sign-off.
- [ ] Chỉ sau đó mới đổi status từ `draft_pending_team_review` sang `approved`.
