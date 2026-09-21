# Cài đặt & chạy trên Windows (local)

Hướng dẫn tải về `F:\projectweb\5400chatbot`, cài đặt, chạy và test dự án
ChatBot5400 (Open Notebook + Auth/RBAC + i18n Việt/Anh + giao diện Agribank).

> Kiến trúc: **SurrealDB** (database) + **API** FastAPI (cổng 5055) + **Worker**
> (xử lý nền) + **Frontend** Next.js (cổng 3000). Toàn bộ code nằm trên nhánh
> `claude/practical-wozniak-9s1t6z`.

## 1. Cài công cụ cần thiết (một lần)

- **Git**: https://git-scm.com/download/win
- **Python 3.11 hoặc 3.12**: https://www.python.org/downloads/ (tick "Add to PATH")
- **uv** (trình quản lý gói Python) — mở PowerShell:
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
- **Node.js 20 LTS trở lên**: https://nodejs.org/
- **Database — chọn 1 trong 2:**
  - **Docker Desktop** (khuyến nghị, dễ nhất): https://www.docker.com/products/docker-desktop/
  - hoặc **SurrealDB** binary: `powershell -c "irm https://windows.surrealdb.com | iex"`

Đóng và mở lại PowerShell sau khi cài để PATH cập nhật.

## 2. Tải mã nguồn về F:\projectweb\5400chatbot

```powershell
mkdir F:\projectweb -Force
git clone -b claude/practical-wozniak-9s1t6z https://github.com/nghoainam1902ps4-lgtm/ChatBot5400-Version02 F:\projectweb\5400chatbot
cd F:\projectweb\5400chatbot
```

## 3. Tạo file cấu hình .env

```powershell
Copy-Item .env.example .env
```
Mở `.env` và sửa 2 dòng sau (chạy DB ngay trên máy, không qua mạng Docker):
```
OPEN_NOTEBOOK_ENCRYPTION_KEY=doi-thanh-mot-chuoi-bi-mat-bat-ky
SURREAL_URL=ws://localhost:8000/rpc
```
(Các dòng còn lại giữ mặc định: user/pass = root/root, namespace/database = open_notebook.)

## 4. Khởi động SurrealDB

**Cách A — Docker (khuyến nghị):**
```powershell
docker compose up -d surrealdb
```
**Cách B — SurrealDB binary:**
```powershell
mkdir surreal_data -Force
surreal start --user root --pass root --bind 127.0.0.1:8000 rocksdb:surreal_data/mydatabase.db
```
(Cách B chiếm một cửa sổ PowerShell — để nguyên nó chạy, mở cửa sổ mới cho các bước sau.)

## 5. Cài đặt phụ thuộc

Backend (Python) — bản đầy đủ **có docling** (giữ đúng Điều/Khoản cho `.docx`/`.pdf`):
```powershell
uv sync --extra docling
```
> ⚠️ **Nặng:** `--extra docling` kéo về **PyTorch + model ML vài GB**, lần đầu có
> thể lâu; lần **trích xuất tài liệu đầu tiên** docling còn tải thêm model layout
> (cần Internet).
>
> Muốn cài **nhẹ** (không docling, chấp nhận mất cấu trúc Điều/Khoản) thì chạy
> `uv sync` (không có `--extra docling`) — app tự fallback về bộ trích thô. Xem
> mục *"Docling"* bên dưới.
Frontend (Node) — mở cửa sổ PowerShell mới:
```powershell
cd F:\projectweb\5400chatbot\frontend
npm install
```

## 6. Chạy ứng dụng (mỗi dịch vụ 1 cửa sổ PowerShell)

**Cửa sổ 1 — API** (tự chạy migration + tạo tài khoản admin/admin lần đầu):
```powershell
cd F:\projectweb\5400chatbot
uv run --env-file .env run_api.py
```
→ API: http://localhost:5055 · Swagger: http://localhost:5055/docs

**Cửa sổ 2 — Worker nền:**
```powershell
cd F:\projectweb\5400chatbot
uv run --env-file .env surreal-commands-worker --import-modules commands --max-tasks 5
```

**Cửa sổ 3 — Frontend:**
```powershell
cd F:\projectweb\5400chatbot\frontend
npm run dev
```
→ Mở trình duyệt: **http://localhost:3000**

**Đăng nhập lần đầu:** `admin` / `admin` → hãy đổi mật khẩu ngay trong mục
"Đổi mật khẩu" ở thanh bên. Giao diện mặc định là tiếng Việt.

## 7. Chạy test

**Backend (pytest):**
```powershell
cd F:\projectweb\5400chatbot
uv run pytest tests/test_auth.py tests/test_passwords.py tests/test_user_domain.py tests/test_preferences_api.py -q
```
(Chạy toàn bộ: `uv run pytest -q`. Lưu ý: một số test khác cần tải model/mạng
và có thể chậm hoặc cần Internet — nhóm test auth ở trên chạy nhanh, không cần mạng.)

**Frontend:**
```powershell
cd F:\projectweb\5400chatbot\frontend
npm run test        # vitest (auth store, i18n parity, ...)
npm run lint        # eslint
npx tsc --noEmit    # kiểm tra kiểu TypeScript
```

## 8. Dừng dịch vụ

- Nhấn `Ctrl + C` ở từng cửa sổ PowerShell đang chạy API/Worker/Frontend/SurrealDB.
- Nếu dùng Docker cho DB: `docker compose down`.

## Docling — trích xuất tài liệu giữ đúng Điều/Khoản

File Word/PDF (nhất là văn bản pháp lý nhiều cấp: Chương → Điều → Khoản → điểm
a/b/c) dùng **đánh số tự động của Word**. Bộ trích "thô" (`python-docx`/`pdfplumber`)
không tính lại được số này → **mất/sai** Điều/Khoản. **Docling** (parser hiểu bố
cục) giữ đúng cấu trúc.

Cấu hình dự án:
- **Engine tài liệu mặc định = `docling`** (migration tự đặt); nếu docling vắng
  mặt, app **tự fallback** về bộ thô (vẫn chạy, chỉ mất cấu trúc).
- Docling nằm trong **extra `docling`** (không cài mặc định để `uv sync` nhẹ). Cài
  bằng:
  ```powershell
  uv sync --extra docling
  ```

**Bắt buộc:** sau khi cài, phải chạy **cả API lẫn worker** bằng `.venv` đã có
docling (đúng như bước 6). Nếu bạn từng chạy worker trước khi cài docling, hãy
**tắt và mở lại worker**.

**Kiểm tra docling đã sẵn sàng:**
```powershell
uv run python -c "import importlib.util as u; print('docling:', u.find_spec('docling') is not None)"
```
Phải in `docling: True`.

**Nếu muốn cài NHẸ (không docling, chấp nhận mất cấu trúc Điều/Khoản):**
- Chỉ chạy `uv sync` (bỏ `--extra docling`) — tài liệu sẽ **tự fallback** về bộ
  trích thô, hoặc đặt engine tài liệu = `simple` trong Cài đặt → xử lý nội dung.

## Xử lý sự cố thường gặp

- **`uv` / `node` / `surreal` không nhận lệnh:** đóng & mở lại PowerShell (PATH), hoặc cài lại.
- **API báo không kết nối được DB:** đảm bảo SurrealDB đang chạy (bước 4) và
  `SURREAL_URL=ws://localhost:8000/rpc` trong `.env`.
- **Cổng bị chiếm (5055/3000/8000):** đóng tiến trình cũ hoặc đổi cổng
  (`API_PORT` trong `.env`; frontend: `npm run dev -- -p 3001`).
- **Muốn tắt xác thực (1 người dùng, tin cậy):** đặt `OPEN_NOTEBOOK_DISABLE_AUTH=true`
  trong `.env` (mặc định là bật xác thực).
