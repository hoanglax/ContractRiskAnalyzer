# Contributing to ContractRiskAnalyzer

Tài liệu này quy định cách các thành viên làm việc chung trên repository.

## 1. Môi trường phát triển

- Python 3.12.x
- Node.js 24 LTS và npm
- Git
- Visual Studio Code (khuyến nghị)

Tham khảo `README.md` để cài đặt môi trường.

## 2. Quy tắc Git

- Không commit trực tiếp lên nhánh `main`.
- Mỗi tính năng hoặc lỗi nên được thực hiện trên một nhánh riêng.
- Đồng bộ nhánh `main` trước khi bắt đầu công việc mới.
- Tạo Pull Request (PR) để đưa thay đổi vào `main`.
- Kiểm tra code và chạy các bài test liên quan trước khi tạo PR.

## 3. Quy tắc đặt tên nhánh

Sử dụng các tiền tố sau:

- `feature/`: thêm chức năng, ví dụ `feature/health-check`
- `fix/`: sửa lỗi, ví dụ `fix/parser-error`
- `docs/`: cập nhật tài liệu, ví dụ `docs/setup-guide`
- `test/`: thêm hoặc sửa kiểm thử, ví dụ `test/health-check`

## 4. Quy tắc commit

Viết thông điệp commit ngắn gọn, mô tả đúng thay đổi.

Ví dụ:

- `feat: add health check endpoint`
- `fix: handle invalid document input`
- `docs: update setup instructions`
- `test: add health check tests`

## 5. Quy tắc code

- Giữ thay đổi tập trung vào một nhiệm vụ.
- Không commit `.venv/`, `node_modules/`, file `.env` hoặc API key.
- Cập nhật `backend/requirements.txt` khi thêm dependency backend.
- Commit `package.json` và `package-lock.json` khi thay đổi dependency frontend.
- Cập nhật tài liệu nếu thay đổi cách cài đặt, API hoặc kiến trúc.

## 6. Trước khi tạo Pull Request

- Kiểm tra `git status`.
- Xem lại thay đổi bằng `git diff`.
- Chạy các bài test liên quan.
- Mô tả rõ mục tiêu, thay đổi chính và kết quả kiểm thử trong PR.
