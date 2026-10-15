# Hướng dẫn triển khai dự án

## 1. Mục đích

Tài liệu này là nơi tổng hợp thông tin phục vụ quá trình triển khai ContractRiskAnalyzer.

Tài liệu giúp các thành viên xác định:
- Kiến trúc hệ thống và luồng xử lý hợp đồng.
- Trách nhiệm và phạm vi của từng mô-đun.
- Dữ liệu đầu vào, đầu ra và nơi lưu trữ dữ liệu.
- Các công việc cần thực hiện, sự phụ thuộc giữa các công việc và tiêu chí hoàn thành.

Tài liệu này đóng vai trò điều hướng triển khai, không thay thế PRD, SRS, SAD, tài liệu đặc tả API hoặc mã nguồn của dự án.

## 2. Hiện trạng triển khai

Nhóm đã xây dựng cấu trúc cơ bản của dự án, chuẩn bị các tài liệu nền tảng và có bản demo ban đầu của Risk Taxonomy.

Các nội dung cần tiếp tục hoàn thiện hoặc kiểm chứng gồm:
- Sơ đồ kiến trúc và các mô-đun của hệ thống.
- Luồng xử lý hợp đồng và luồng dữ liệu.
- Thiết kế cơ sở dữ liệu ứng dụng và kho tri thức pháp luật.
- Giao diện trao đổi dữ liệu giữa các mô-đun.
- Kế hoạch triển khai chi tiết và danh sách công việc.

Trạng thái triển khai phải phản ánh kết quả thực tế, dựa trên mã nguồn, kết quả kiểm thử và các sản phẩm đã được rà soát.

## 3. Thiết kế hệ thống

| Tài liệu | Nội dung | Trạng thái |
|---|---|---|
| [Kiến trúc hệ thống](../architecture/system-architecture.md) | Các thành phần, trách nhiệm và quan hệ giữa các mô-đun | Dự kiến thực hiện |
| [Luồng xử lý](../architecture/processing-flow.md) | Các bước từ tải hợp đồng đến trả kết quả phân tích | Dự kiến thực hiện |
| [Luồng dữ liệu](../architecture/data-flow.md) | Cách dữ liệu được tạo, biến đổi, truyền và lưu trữ | Dự kiến thực hiện |
| Thiết kế cơ sở dữ liệu | Dữ liệu ứng dụng và kho tri thức pháp luật | Cần xác định |
| Đặc tả API | Giao diện trao đổi dữ liệu giữa frontend và backend | Cần rà soát |

## 4. Các nhánh công việc

### 4.1. Nhánh Dữ liệu

Các nhiệm vụ dự kiến:
- Thu thập và xác minh văn bản pháp luật liên quan.
- Xác định cấu trúc metadata và định dạng lưu trữ văn bản.
- Chuẩn bị kho tri thức pháp luật phục vụ truy xuất.
- Quản lý Risk Taxonomy và bộ dữ liệu đánh giá.
- Ghi nhận nguồn dữ liệu và kiểm tra chất lượng dữ liệu.

Các vị trí liên quan trong repo:
- `data/legal_corpus/`
- `data/taxonomy/`
- `data/samples/`

### 4.2. Nhánh Mô hình

Các nhiệm vụ dự kiến:
- Thử nghiệm trích xuất văn bản từ hợp đồng.
- Xây dựng hoặc tích hợp chức năng chia hợp đồng thành điều khoản.
- Phát hiện rủi ro và phân loại theo nhiều nhóm rủi ro.
- Đánh giá mức độ nghiêm trọng và khả năng truy xuất căn cứ pháp luật.
- Bảo đảm đầu ra của mô hình tuân theo cấu trúc dữ liệu đã thống nhất.

Vị trí triển khai chính dự kiến:
- `backend/app/`

Ranh giới mô-đun, giao diện dữ liệu và phân công cụ thể cần được nhóm thống nhất trước khi chốt các công việc triển khai.

## 5. Quy trình phát triển

1. Đọc yêu cầu và tài liệu thiết kế liên quan.
2. Chọn một công việc có đầu vào và đầu ra rõ ràng.
3. Xác nhận các công việc phụ thuộc và tiêu chí hoàn thành.
4. Phát triển trên nhánh Git riêng.
5. Bổ sung hoặc cập nhật kiểm thử và tài liệu liên quan.
6. Tạo Pull Request để các thành viên rà soát.
7. Chỉ hợp nhất khi đáp ứng các điều kiện kiểm tra và rà soát đã thống nhất.
8. Cập nhật GitHub Issue và trạng thái triển khai.

## 6. Quản lý công việc

GitHub Issues được sử dụng để ghi nhận và theo dõi các nhiệm vụ triển khai.

Mỗi nhiệm vụ cần có:
- Mục tiêu và phạm vi công việc.
- Người phụ trách.
- File hoặc thư mục liên quan.
- Công việc phụ thuộc.
- Sản phẩm đầu ra cần bàn giao.
- Tiêu chí hoàn thành.
- Thời hạn và trạng thái hiện tại.

Một nhiệm vụ không được coi là hoàn thành chỉ vì đã viết xong mã nguồn. Kết quả phải đáp ứng tiêu chí nghiệm thu và được rà soát.

## 7. Nguyên tắc triển khai

- Bám sát phạm vi MVP đã thống nhất.
- Ưu tiên kiến trúc nguyên khối mô-đun, trừ khi nhóm thống nhất thay đổi.
- Xác định giao diện giữa các mô-đun trước khi tích hợp công việc song song.
- Bảo đảm có thể truy xuất nguồn gốc của văn bản pháp luật và căn cứ được sử dụng.
- Kiểm tra đầu ra có cấu trúc của mô hình, không mặc định kết quả luôn chính xác.
- Ghi lại các quyết định kỹ thuật quan trọng trong `docs/decisions/`.
- Cập nhật tài liệu khi thiết kế hoặc cấu trúc repo thay đổi.

## 8. Mốc triển khai tiếp theo

Mục tiêu trước mắt là thiết lập cơ sở triển khai thống nhất cho cả nhóm:

1. Rà soát và thống nhất trách nhiệm của từng mô-đun.
2. Hoàn thiện sơ đồ kiến trúc và luồng xử lý.
3. Xác định luồng dữ liệu và thiết kế cơ sở dữ liệu ban đầu.
4. Thống nhất giao diện trao đổi dữ liệu giữa các nhánh Dữ liệu, Mô hình và Backend.
5. Tạo GitHub Issues với người phụ trách, sản phẩm đầu ra, công việc phụ thuộc và tiêu chí hoàn thành.

Mốc này được coi là hoàn thành khi các thành viên có thể xác định công việc của mình nằm ở đâu trong repo, cần bàn giao sản phẩm gì và cách kiểm tra kết quả đó.