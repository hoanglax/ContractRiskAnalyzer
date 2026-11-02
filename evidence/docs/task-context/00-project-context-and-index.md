# Legal AI — Task Context & Evidence Pack

**Snapshot date:** 2026-11-02  
**Purpose:** Lưu lại bối cảnh, phạm vi, kết quả, bằng chứng và phần còn mở của các task đã thực hiện. Tài liệu này phục vụ:
1. Onboarding thành viên mới / cài đặt và tiếp tục phát triển.
2. Làm căn cứ báo cáo tiến độ và chứng minh task.
3. Tránh nhầm lẫn giữa hiện trạng repo, bản nháp đề xuất và quyết định đã được duyệt.

## 1. Phạm vi tài liệu đã xác minh

| Task | Nội dung | Trạng thái ghi nhận |
|---|---|---|
| TASK-API-01 | Draft upload API contract | Draft đã soạn; chưa tích hợp và chưa được Team B duyệt |
| TASK-DATA-01 | Risk Taxonomy v1.0.0 | Đã tạo dữ liệu và generator, kiểm thử đạt; còn chờ review/đối chiếu |

Đây là các task gần nhất có đủ tài liệu và artifact để lập hồ sơ bằng chứng. Không suy diễn rằng các task khác trong kế hoạch Scrum đã hoàn thành.

## 2. Nguyên tắc đọc trạng thái

- **Đã có trong repo/snapshot:** có thể kiểm tra trực tiếp bằng file hoặc code.
- **Đã tạo bản nháp:** artifact đã tồn tại nhưng chưa được xem là quyết định cuối.
- **Chờ xác nhận:** cần Team B/Product/Legal xác nhận.
- **Chưa thực hiện:** không có bằng chứng trong snapshot hiện tại.
- Không đánh dấu “Done” chỉ vì tài liệu đã mô tả một hành vi; phải kiểm tra implementation và test tương ứng.

## 3. Kiến trúc / bối cảnh dự án đang dùng

Dự án: Vietnamese Legal AI / Contract Risk Analyzer, tập trung phân tích rủi ro hợp đồng thuê nhà/phòng tại Việt Nam.

Các quyết định nền đã được ghi nhận trong tài liệu dự án:
- Kiến trúc Modular Monolith.
- Backend FastAPI.
- Frontend React + TypeScript + Vite.
- AI/model calls đi qua adapter thống nhất.
- Các quyết định đã chốt và các đề xuất đang chờ duyệt phải được phân biệt rõ trong tài liệu.

Không dùng tài liệu context này thay cho PRD/SRS/SAD hoặc Decision Log/ADR. Khi có thay đổi, cập nhật nguồn chuẩn trước, sau đó đồng bộ context pack.

## 4. Thư mục trong gói

```text
docs/task-context/
  00-project-context-and-index.md
  01-upload-api-task-record.md
  02-taxonomy-task-record.md
  03-open-items-and-next-actions.md

evidence/
  upload-api-draft/
    api-contract.md
    README.md
    examples/*.json
  taxonomy-v1/
    taxonomy.json
    taxonomy.csv
    README.md
    CHANGELOG.md
    Risk-Taxonomy.xlsx
    taxonomy.py
    test_taxonomy.py
```

## 5. Cách dùng khi onboarding

1. Đọc file này để nắm phạm vi và cách phân biệt trạng thái.
2. Đọc `01-upload-api-task-record.md` trước khi sửa upload endpoint hoặc frontend upload service.
3. Đọc `02-taxonomy-task-record.md` trước khi sửa taxonomy, risk labels hoặc pipeline nạp taxonomy.
4. Đọc `03-open-items-and-next-actions.md` để biết những gì chưa được coi là hoàn tất.
5. Trước khi code, kiểm tra lại repo branch mới nhất vì evidence trong gói là snapshot tại ngày 2026-11-02, không đảm bảo phản ánh các commit phát sinh sau thời điểm đó.

## 6. Giới hạn bằng chứng

Gói này chứng minh các artifact và test có trong snapshot. Nó **không** chứng minh:
- Các file đã được commit/push lên GitHub.
- Team B đã review hoặc phê duyệt.
- Frontend và backend đã tích hợp contract upload.
- Taxonomy đã được Legal/Product phê duyệt.
- Các tham chiếu pháp luật còn thiếu đã được xác minh.
