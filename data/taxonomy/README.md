# Risk Taxonomy

`data/Risk Taxonomy.xlsx` là bản gốc; nhóm dữ liệu chỉnh sửa trên tệp này. `taxonomy.json` được sinh tự động từ workbook và commit cùng, để ứng dụng chỉ đọc JSON và mọi thay đổi taxonomy đều hiện ra khi review.

Không sửa tay `taxonomy.json`; mọi thay đổi sẽ bị ghi đè ở lần sinh tiếp theo.

## Sau mỗi lần sửa workbook

```
cd backend
.venv/bin/python -m application.modules.taxonomy.taxonomy build
```

Lệnh in ra số mã theo từng nhóm và danh sách **issues**: những chỗ đã tự sửa (lỗi chính tả mức độ, tên luật viết sai) hoặc không xử lý được (luật chưa có trong kho). Hãy sửa các issue đó trong workbook rồi chạy lại. Commit cả `Risk Taxonomy.xlsx` lẫn `taxonomy.json` trong cùng một commit.

Lệnh dừng với lỗi nếu có mã sai định dạng, mã trùng, mức độ không đọc được hoặc tiêu đề nhóm sai mẫu.

## Quy ước trong workbook

- **Mỗi nhóm rủi ro một sheet.**
  - Tiêu đề nhóm nằm phía trên bảng, theo mẫu `N. NHÓM Tên nhóm (English name)`.
  - Dòng tiêu đề bảng có các cột `Mã`, `Tên`, `Mức độ`, `Dấu hiệu nhận biết`, `Căn cứ pháp lý`, `Rủi ro thực tế`, `Nhãn`.
- **Sheet `Quy ước`** chứa thang mức độ (`1. LOW:` rồi mô tả ở ô kế tiếp, tương tự cho MEDIUM, HIGH, CRITICAL).
- **Mã:** `A-XXX-NN` hoặc `B-XXX-NN`. A là rủi ro của bên cho thuê, B là của bên thuê; `XXX` là mã nhóm, mọi dòng trong một sheet dùng chung mã nhóm. Khoảng trắng trong mã được bỏ qua.
- **Mức độ:** `LOW`, `MEDIUM`, `HIGH` hoặc `CRITICAL`.
- **Căn cứ pháp lý:** mỗi dòng một văn bản, dạng `Điều 117, 141 BLDS 2015`. Tên văn bản phải là một trong các tên đã khai báo trong `LAWS` (`backend/application/modules/taxonomy/taxonomy.py`), ví dụ `BLDS 2015`, `Luật Nhà ở 2023`, `Luật KDBĐS 2023`, `Nghị định 125/2020/NĐ-CP`. Muốn trích một văn bản mới, cần thêm văn bản đó vào `data/legal_corpus/` và vào `LAWS`.
- **Rủi ro thực tế:** mỗi hậu quả một dòng trong ô.
- **Nhãn:** các nhãn cách nhau bằng dấu phẩy hoặc xuống dòng.

## Taxonomy được dùng thế nào

Theo đề xuất kiến trúc (`docs/architecture/proposal.md`, mục 3.2), hệ thống chỉ báo những rủi ro có mã trong taxonomy:
- Mô hình đọc **tên** và **dấu hiệu nhận biết** để nhận ra rủi ro trong hợp đồng. Hai mã gần nhau cần có dấu hiệu đủ khác để phân biệt được.
- **Mức độ**, **bên chịu rủi ro** và **hậu quả** hiển thị cho người dùng lấy nguyên từ dòng taxonomy.
- **Căn cứ pháp lý** là nguồn đầu tiên khi gắn điều luật cho mỗi kết quả.

Rủi ro chưa có mã thì hệ thống không báo được.
