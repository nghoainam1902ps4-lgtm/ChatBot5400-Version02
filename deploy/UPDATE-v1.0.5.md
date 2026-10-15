# Hướng dẫn cập nhật lên ChatBot 5400 v1.0.5

Bản **v1.0.5** gồm: chọn mô hình khi chat chỉ dành cho admin, công tắc bật/tắt
tính năng Podcast cho quản trị viên, và cập nhật tài liệu API theo đăng nhập JWT.

> ✅ **An toàn để nâng cấp:** KHÔNG có migration cơ sở dữ liệu mới, KHÔNG đổi
> schema, embedding hay cách nạp nguồn. Dữ liệu (SurrealDB, uploads, chat) **giữ
> nguyên** khi build lại. Tùy chọn Podcast mặc định **Bật** nên hành vi không đổi
> sau khi cập nhật (admin có thể tắt trong *Cài đặt* nếu muốn).

Chọn đúng phần theo nơi bạn đang chạy:

- **A. VPS production** (chạy sau Caddy, dùng `deploy/docker-compose.prod.yml`)
- **B. Máy chủ local bằng Docker** (dùng `docker-compose.yml` ở thư mục gốc)
- **C. Máy local chạy chế độ dev** (`make` + `uv` + `npm`, không Docker)

---

## A. Cập nhật trên VPS (production)

Thư mục cài đặt giả định là `/opt/chatbot5400` (theo `deploy/DEPLOY-VPS.md`).

### A.1. Sao lưu trước khi nâng cấp (bắt buộc)

```bash
cd /opt/chatbot5400/deploy
docker compose -f docker-compose.prod.yml down
tar czf backup-$(date +%F-%H%M).tgz surreal_data notebook_data .env
ls -lh backup-*.tgz      # kiểm tra file sao lưu đã tạo
```

### A.2. Lấy mã nguồn v1.0.5 và build lại

```bash
cd /opt/chatbot5400
git fetch origin --tags

# (tùy chọn) xác nhận tag ổn định mới nhất:
git tag -l 'v[0-9]*' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -n1   # -> v1.0.5

git checkout v1.0.5

cd deploy
docker compose -f docker-compose.prod.yml up -d --build
```

### A.3. Theo dõi và kiểm tra

```bash
docker compose -f docker-compose.prod.yml logs -f open_notebook   # chờ "API initialization completed"
curl -sS https://api.5491sotay.io.vn/health                        # -> {"status":"healthy"}
```

Mở **https://5491sotay.io.vn**, đăng nhập và kiểm tra:

- Vào một Sổ tay → **Trò chuyện**: tài khoản **user thường** không còn thấy nút
  chọn mô hình; tài khoản **admin** vẫn thấy.
- **Cài đặt** (admin) → mục **Tính năng** → có công tắc **"Bật Podcast"**.
- Ở góc dưới sidebar hiển thị **Phiên bản 1.0.5**.

> ⚙️ Migration tự chạy khi API khởi động. Lần này **không có migration mới** nên
> khởi động nhanh (bỏ qua bước cài docling vì đã cache trên `notebook_data`).

---

## B. Cập nhật máy chủ local chạy bằng Docker

Dùng `docker-compose.yml` ở thư mục gốc repo (service `open_notebook` +
`surrealdb`, dữ liệu ở `./surreal_data` và `./notebook_data`). Giả sử repo nằm ở
`/opt/chatbot5400` (đổi cho đúng máy bạn).

### B.1. Sao lưu

```bash
cd /opt/chatbot5400
docker compose down
tar czf backup-local-$(date +%F-%H%M).tgz surreal_data notebook_data .env 2>/dev/null
```

### B.2. Lấy v1.0.5 và build lại

```bash
git fetch origin --tags
git checkout v1.0.5
docker compose up -d --build
```

### B.3. Kiểm tra

```bash
docker compose logs -f open_notebook      # chờ "API initialization completed"
curl -sS http://localhost:5055/health     # -> {"status":"healthy"}
```

Mở giao diện ở **http://localhost:8502** (hoặc cổng bạn cấu hình) và kiểm tra 3
điểm như mục A.3.

---

## C. Cập nhật máy local chạy chế độ dev (make / uv / npm)

Dành cho máy chạy trực tiếp bằng `make start-all` (SurrealDB qua Docker, API bằng
`uv`, frontend bằng `npm`), không đóng gói toàn bộ trong Docker.

### C.1. Dừng tiến trình đang chạy và sao lưu

```bash
cd <thư-mục-repo>
make stop-all 2>/dev/null || true
# Nếu DB chạy bằng docker-compose.dev.yml, dữ liệu nằm ở ./surreal_data:
tar czf backup-dev-$(date +%F-%H%M).tgz surreal_data .env 2>/dev/null || true
```

### C.2. Lấy mã nguồn v1.0.5

```bash
git fetch origin --tags
git checkout v1.0.5
```

### C.3. Cập nhật phụ thuộc rồi chạy lại

```bash
# Backend
uv sync

# Frontend
cd frontend
npm ci
npm run build          # build bản production; hoặc bỏ qua nếu bạn chạy npm run dev
cd ..

# Khởi động lại toàn bộ (DB + API + worker + frontend)
make start-all
```

### C.4. Kiểm tra

```bash
curl -sS http://localhost:5055/health     # -> {"status":"healthy"}
```

Mở **http://localhost:3000** và kiểm tra 3 điểm như mục A.3.

> 💡 Nếu dùng tài khoản dev không bật xác thực (`OPEN_NOTEBOOK_DISABLE_AUTH=true`),
> mọi phiên chạy dưới quyền admin nên bạn sẽ luôn thấy nút chọn mô hình và công
> tắc Podcast. Để thử vai trò **user thường**, hãy tắt biến này và đăng nhập bằng
> một tài khoản `user`.

---

## Quay lui (rollback) nếu cần

Chỉ nên **nâng cấp tiến**. Nếu buộc phải quay lại bản cũ:

```bash
# Về đúng bản trước đó
git checkout v1.0.4
# rồi build lại theo đúng mục A.2 / B.2 / C.3 tương ứng
```

Nếu đã lỡ có sự cố dữ liệu, khôi phục từ file sao lưu đã tạo ở bước đầu:

```bash
# Ví dụ cho production (đã down trước):
cd /opt/chatbot5400/deploy
tar xzf backup-YYYY-MM-DD-HHMM.tgz
docker compose -f docker-compose.prod.yml up -d
```

> ⚠️ Không hạ cấp (down-migrate) tùy tiện giữa các bản có migration khác nhau.
> Riêng v1.0.4 ↔ v1.0.5 **không có thay đổi schema** nên quay lui an toàn.
