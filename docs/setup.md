# Cài đặt và chạy thử (Docker)

Hướng dẫn chạy toàn bộ pipeline phân tích hợp đồng (đọc file → phát hiện rủi ro → căn cứ pháp lý → giải thích) trên
máy của bạn. Không cần GPU: mô hình ngôn ngữ chạy trên OpenRouter, chỉ có mô hình embedding nhỏ (80M) chạy bằng CPU
trong container.

## 1. Cần có

- Docker Desktop (Windows/macOS) hoặc Docker Engine + Compose v2 (Linux). Kiểm tra: `docker compose version`.
- Khoảng 4 GB dung lượng trống cho image.
- Một API key OpenRouter (https://openrouter.ai/keys). Một lần phân tích hợp đồng ~10–15 nghìn ký tự tốn khoảng
  $0.01–0.06.

> **Lưu ý về dữ liệu:** nội dung hợp đồng được gửi tới OpenRouter và nhà cung cấp mô hình phía sau. Chỉ dùng hợp
> đồng mẫu hoặc hợp đồng đã được phép chia sẻ.

## 2. Cấu hình

Tại thư mục gốc của repo:

```bash
cp .env.example .env        # Windows CMD: copy .env.example .env
```

Mở `.env` và điền `OPENROUTER_API_KEY=...`. Nếu cổng 8000 trên máy đã bị dùng, thêm `PORT=8765` (hoặc cổng khác).

## 3. Build và chạy

```bash
docker compose up -d --build backend
```

Lần build đầu mất khoảng 5–10 phút (tải PyTorch bản CPU, LibreOffice, và dựng sẵn cơ sở dữ liệu văn bản pháp luật +
chỉ mục vector bên trong image). Các lần sau chỉ build lại phần code đã đổi.

Kiểm tra:

- http://localhost:8000/health → `{"status":"ok"}`
- http://localhost:8000/demo → giao diện demo: tải file hợp đồng lên, xem tiến độ và kết quả
- http://localhost:8000/docs → tài liệu API (Swagger)

(Thay `8000` bằng `PORT` nếu bạn đã đổi.)

Lệnh thường dùng:

```bash
docker compose logs -f backend      # xem log (mỗi lệnh gọi LLM: thời gian, token, chi phí)
docker compose stop backend         # dừng
docker compose up -d --build backend  # chạy lại sau khi pull code mới
```

Chỉ cần chạy service `backend`. Service `qdrant` trong `docker-compose.yml` là Qdrant dạng server, pipeline không
dùng đến (chỉ mục vector đã nằm sẵn trong image backend).

## 4. Dùng

### Giao diện demo

Mở `/demo`, chọn file, bấm phân tích. Một hợp đồng ~12 nghìn ký tự mất khoảng 1 phút. Mỗi lần chạy có một mã
(`id`); mở lại kết quả cũ bằng `/demo?id=<id>`.

### Qua API

```bash
curl -F "file=@hop_dong.docx" http://localhost:8000/analyses          # → {"id": "..."}
curl http://localhost:8000/analyses/<id>                              # trạng thái + kết quả
```

`status` đi từ `queued` → `running` → `done` (hoặc `failed`, kèm `error`). Kết quả gồm `items` (mỗi điều khoản có rủi
ro: mã rủi ro, mức độ, trích dẫn, căn cứ pháp lý, giải thích), `warnings`, `usage` (số lệnh gọi, token, chi phí) và
`stage_seconds` (thời gian từng bước). Mỗi lần chỉ chạy một phân tích; các lần gửi sau sẽ chờ ở trạng thái `queued`.

Bản ghi các lần chạy được lưu trong volume Docker `runs`, nên vẫn còn sau khi khởi động lại hoặc build lại.

### Định dạng file hỗ trợ

| File | Ghi chú |
|---|---|
| `.docx` | Tốt nhất. |
| `.pdf` có lớp chữ | Đọc trực tiếp. |
| `.doc` (Word cũ) | Chuyển sang `.docx` bằng LibreOffice trong container. |
| PDF scan, ảnh `.png` | Cần OCR, mặc định **chưa bật**: điền `OCR_API_KEY` và `OCR_MODEL` (mô hình thị giác bất kỳ có API kiểu OpenAI) trong `.env`, rồi `docker compose up -d backend`. |

## 5. Tùy chỉnh

- **Đổi mô hình LLM:** sửa `backend/llm.openrouter.toml` (model, số lệnh gọi song song, mức reasoning) rồi build lại.
  Các tùy chọn khác và nhà cung cấp khác: `backend/llm.example.toml`.
- **Bỏ LibreOffice** (image nhỏ hơn ~370 MB, nhưng `.doc` sẽ báo lỗi):
  `docker compose build --build-arg WITH_LIBREOFFICE=0 backend`.
- **Thêm văn bản pháp luật:** thêm file `.txt` vào `data/legal_corpus/` (ghi nguồn vào `SOURCES.md`) rồi build lại;
  cơ sở dữ liệu và chỉ mục vector được dựng lại trong lúc build.

## 6. Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `env file .env not found` | Chưa tạo `.env` (bước 2). |
| `port is already allocated` | Đặt `PORT=` sang cổng khác trong `.env`. |
| Phân tích `failed`, lỗi 401 trong log | `OPENROUTER_API_KEY` sai hoặc hết hạn mức. |
| `image input needs OCR` | File là bản scan/ảnh; bật OCR (mục 4) hoặc dùng `.docx`. |
| Cảnh báo `cited law not in the KB` | Bình thường: văn bản đó chưa có trong bộ luật (`data/legal_corpus/SOURCES.md`). |

## Chạy không dùng Docker (phát triển)

Python 3.12, cài poppler-utils (và LibreOffice nếu cần `.doc`). Từ thư mục gốc:

```bash
python3.12 -m venv backend/.venv
backend/.venv/bin/pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
backend/.venv/bin/pip install -r backend/requirements.txt
cp backend/llm.openrouter.toml backend/llm.toml
cd backend
.venv/bin/python -m application.modules.legal_retrieval.kb build
.venv/bin/python -m application.modules.legal_retrieval.dense embed --model codefuse-ai/F2LLM-v2-80M --tag 80m
.venv/bin/python -m application.modules.legal_retrieval.qdrant_store index --tag 80m
.venv/bin/python -m uvicorn application.main:app --port 8000
```

(Windows: `backend\.venv\Scripts\python.exe` thay cho `backend/.venv/bin/python`.)
