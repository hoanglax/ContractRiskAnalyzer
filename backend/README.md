# Backend — ContractRiskAnalyzer

Tài liệu này hướng dẫn thiết lập môi trường backend, khởi chạy Qdrant, khởi tạo SQLite và chạy thử chức năng truy xuất dữ liệu pháp luật.

## 1. Công nghệ sử dụng

- Python 3.12
- FastAPI
- Uvicorn
- SQLite (`sqlite3`)
- Qdrant chạy local bằng Docker
- Sentence Transformers để tạo embedding local

## 2. Cấu trúc liên quan

```text
backend/
├── modules/
│   └── legal_retrieval/
│       ├── __init__.py
│       ├── database.py
│       ├── embeddings.py
│       ├── vector_store.py
│       └── service.py
├── scripts/
│   ├── __init__.py
│   ├── import_legal_data.py
│   └── index_legal_data.py
├── tests/
├── data/
│   └── app.db
├── requirements.txt
└── README.md
```

`app.db` được tạo tự động khi khởi tạo SQLite. Không commit file database runtime lên Git.

## 3. Chuẩn bị môi trường

Các lệnh dưới đây dành cho Windows Command Prompt (CMD).

Từ thư mục gốc repo:

```bat
cd /d D:\ContractRiskAnalyzer
```

Nếu chưa có môi trường ảo:

```bat
py -3.12 -m venv backend\.venv
```

Kích hoạt môi trường ảo:

```bat
backend\.venv\Scripts\activate.bat
```

Cài các thư viện:

```bat
cd backend
python -m pip install -r requirements.txt
```

Kiểm tra Python:

```bat
python --version
```

## 4. Khởi chạy Qdrant

Mở CMD tại thư mục gốc repo:

```bat
cd /d D:\ContractRiskAnalyzer
docker compose up -d
docker compose ps
```

Kiểm tra dịch vụ:

```bat
curl http://localhost:6333/healthz
```

Qdrant sử dụng cổng `6333` cho HTTP API.

Dừng Qdrant khi không sử dụng:

```bat
docker compose down
```

Lệnh trên không xóa volume dữ liệu. Không dùng `docker compose down -v` nếu muốn giữ dữ liệu Qdrant.

## 5. Khởi tạo SQLite

Tại thư mục `backend` và trong môi trường ảo:

```bat
python -m modules.legal_retrieval.database
```

Database mặc định:

```text
backend/data/app.db
```

## 6. Nhập dữ liệu pháp luật

Đảm bảo dữ liệu đã được chuẩn hóa tại:

```text
data/legal_corpus/legal_corpus.json
```

Sau đó chạy từ thư mục `backend`:

```bat
python -m scripts.import_legal_data
```

Dữ liệu đầu vào cần có hai danh sách `documents` và `legal_articles`. Mỗi điều luật phải tham chiếu đến một `doc_id` tồn tại.

## 7. Tạo Qdrant collection

```bat
python -m modules.legal_retrieval.vector_store
```

Collection mặc định:

```text
legal_articles
```

## 8. Tạo embedding và lập chỉ mục

```bat
python -m scripts.index_legal_data
```

Lệnh này đọc điều luật từ SQLite, tạo embedding bằng model đã cấu hình và ghi vector vào Qdrant.

Lần chạy đầu tiên có thể tải model về máy và mất thêm thời gian.

## 9. Thử tìm kiếm điều luật

```bat
python -m modules.legal_retrieval.service
```

Nhập một câu truy vấn khi chương trình yêu cầu.

Kết quả bao gồm thông tin văn bản, điều luật, nội dung gốc, nguồn tham chiếu và điểm tương đồng.

Điểm tương đồng chỉ phục vụ xếp hạng tìm kiếm, không phải xác suất đúng hoặc kết luận pháp lý.

## 10. Chạy kiểm thử

```bat
python -m pip install pytest
python -m pytest tests -v
```

## 11. Quy trình cập nhật dữ liệu

Khi cập nhật dữ liệu pháp luật:

1. Kiểm tra nguồn và trạng thái pháp lý.
2. Cập nhật file JSON theo schema thống nhất.
3. Nhập/cập nhật SQLite.
4. Chạy lại bước lập chỉ mục Qdrant.
5. Kiểm tra các kết quả truy xuất liên quan.

Lưu ý: cơ chế lập chỉ mục hiện tại cần được bổ sung xử lý xóa vector cũ khi điều luật bị xóa khỏi nguồn dữ liệu.

## 12. Xử lý lỗi thường gặp

### Không tìm thấy module `modules`

Đảm bảo đang chạy lệnh từ thư mục `backend`:

```bat
cd /d D:\ContractRiskAnalyzer\backend
```

### Không kết nối được Qdrant

Kiểm tra Docker:

```bat
docker compose ps
docker compose logs qdrant
```

### Lỗi thiếu thư viện Python

Kiểm tra môi trường ảo đã được kích hoạt và chạy:

```bat
python -m pip install -r requirements.txt
```

### Lỗi khi tải embedding model

Kiểm tra kết nối mạng, dung lượng ổ đĩa, RAM và thông báo lỗi từ thư viện.

## 13. Nguyên tắc làm việc

- Chạy lệnh Python theo module từ thư mục `backend`.
- Sử dụng cùng phiên bản Python và dependency đã thống nhất trong nhóm.
- Không commit `.venv`, `.env`, database runtime hoặc dữ liệu bí mật.
- Không coi dữ liệu demo là căn cứ pháp lý thật.
- Kiểm tra kết quả truy xuất trước khi tích hợp với LLM.

**Trạng thái:** Tài liệu hướng dẫn triển khai ban đầu. Cần cập nhật sau khi nhóm kiểm thử và chốt các cấu hình thực tế.