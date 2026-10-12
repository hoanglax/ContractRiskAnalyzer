# ContractRiskAnalyzer

Hệ thống phân tích rủi ro hợp đồng.

## 1. Yêu cầu môi trường

- Git
- Python 3.12.x
- Node.js 24 LTS và npm
- Visual Studio Code (khuyến nghị)

## 2. Clone repository

Thay `<REPOSITORY_URL>` bằng URL repository GitHub của nhóm.

```bash
git clone <REPOSITORY_URL>
cd ContractRiskAnalyzer
```

## 3. Cài đặt Backend

### Windows CMD

Tại thư mục gốc của dự án:

```cmd
py -3.12 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Chạy backend:

```cmd
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
```

### Linux / WSL

Tại thư mục gốc của dự án:

```bash
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
```

Chạy backend:

```bash
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload
```

### Kiểm tra API

Sau khi backend chạy, truy cập:

- Health check: http://127.0.0.1:8000/health
- API documentation: http://127.0.0.1:8000/docs

Dừng server bằng `Ctrl + C`.

## 4. Cài đặt Frontend

```bash
cd frontend
npm ci
```

Lệnh `npm ci` yêu cầu repository có `package.json` và `package-lock.json` hợp lệ.

## 5. Công nghệ sử dụng

- Backend: Python, FastAPI, Uvicorn
- Frontend: React, TypeScript, Vite
- Version control: Git và GitHub
- API testing: Swagger UI của FastAPI
- IDE: Visual Studio Code

## 6. Lưu ý khi phát triển

- Không commit thư mục `.venv/` hoặc `node_modules/`.
- Không commit file `.env` chứa thông tin bí mật hoặc API key.
- Dùng `.env.example` làm mẫu cấu hình khi cần.
- Khi thêm dependency backend, cập nhật `backend/requirements.txt`.
- Khi thay đổi dependency frontend, commit cả `package.json` và `package-lock.json`.
