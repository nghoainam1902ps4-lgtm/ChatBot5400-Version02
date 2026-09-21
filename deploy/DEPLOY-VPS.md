# Triển khai ChatBot5400 lên VPS (5491sotay.io.vn)

Hướng dẫn cài đặt bản mới nhất (nhánh `claude/practical-wozniak-9s1t6z`) lên VPS
Ubuntu/Debian, chạy sau Caddy với HTTPS tự động.

- Frontend: **https://5491sotay.io.vn**
- API: **https://api.5491sotay.io.vn**

> ⚠️ **BẢO MẬT — làm ngay:** mật khẩu `root` của VPS đã bị lộ (gõ trong chat dạng
> văn bản thuần). Sau khi đăng nhập được, hãy **đổi mật khẩu root** (`passwd`) và
> nên **chuyển sang đăng nhập bằng SSH key** rồi tắt đăng nhập bằng mật khẩu.
>
> ⚠️ **Vì sao phải build từ mã nguồn:** image công bố `lfnovo/open_notebook:v1-latest`
> **không** chứa code tùy biến của dự án (đăng nhập/RBAC, cô lập dữ liệu theo
> người dùng, tiếng Việt, docling mặc định, giao diện Agribank). Bắt buộc build
> từ nhánh này.
>
> ℹ️ **Về docling (giữ đúng Điều/Khoản):** để image **nhẹ, build được trên VPS
> nhỏ**, docling **không nhúng vào image** mà **tự cài ở lần khởi động đầu tiên**
> vào volume dữ liệu (`OPEN_NOTEBOOK_ENABLE_DOCLING=true`, đã bật sẵn trong file
> compose, dùng PyTorch bản CPU cho nhẹ). Vì vậy **lần `up` đầu tiên chạy lâu**
> (tải PyTorch + model, vài trăm MB → vài GB, cần Internet), nhưng được **lưu vào
> `notebook_data`** nên các lần sau và khi rebuild **không tải lại**. Engine tài
> liệu mặc định vẫn là `docling`; nếu vì lý do gì docling chưa cài xong, app **tự
> fallback** về bộ trích thô (vẫn chạy).

## 0. Yêu cầu VPS

- **RAM:** ≥ 2 GB để build; **≥ 4 GB khuyến nghị** để chạy docling (suy luận model
  cần RAM). Nếu RAM thấp, thêm swap (xem *Xử lý sự cố*).
- **Ổ đĩa trống:** ≥ 12 GB (image gọn + PyTorch/model docling trên volume + dữ liệu).
  VPS 28 GB của bạn **đủ dùng**.
- **Mở cổng 80 và 443** trên tường lửa/nhà cung cấp (Caddy cần để cấp chứng chỉ Let's Encrypt).
- DNS: `5491sotay.io.vn` và `api.5491sotay.io.vn` đã trỏ (A record) về IP VPS — **đã xong**.

## 1. Đăng nhập & đổi mật khẩu root

```bash
ssh root@103.20.102.89
passwd            # đặt mật khẩu root MỚI ngay
```

## 2. Cài Docker (một lần)

```bash
curl -fsSL https://get.docker.com | sh
docker version && docker compose version   # kiểm tra
```

## 3. Tải mã nguồn (đúng nhánh)

```bash
apt-get update && apt-get install -y git
git clone -b claude/practical-wozniak-9s1t6z \
  https://github.com/nghoainam1902ps4-lgtm/ChatBot5400-Version02 /opt/chatbot5400
cd /opt/chatbot5400/deploy
```

## 4. Tạo file cấu hình bí mật `.env`

```bash
cp .env.prod.example .env
# sinh 2 khóa bí mật:
echo "OPEN_NOTEBOOK_ENCRYPTION_KEY=$(openssl rand -hex 32)" >> .env.tmp
echo "OPEN_NOTEBOOK_JWT_SECRET=$(openssl rand -hex 32)"     >> .env.tmp
echo "SURREAL_PASSWORD=$(openssl rand -hex 16)"             >> .env.tmp
```

Rồi mở `.env` (`nano .env`) và **dán 3 giá trị** vừa sinh (xem `cat .env.tmp`) vào
đúng các dòng `OPEN_NOTEBOOK_ENCRYPTION_KEY=`, `OPEN_NOTEBOOK_JWT_SECRET=`,
`SURREAL_PASSWORD=`. Hai dòng `PUBLIC_FRONTEND_URL`/`PUBLIC_API_URL` giữ nguyên.

```bash
rm -f .env.tmp     # xóa file tạm sau khi đã dán
```

> 🔐 **Giữ kỹ `OPEN_NOTEBOOK_ENCRYPTION_KEY`.** Mất khóa này là không giải mã được
> các API key nhà cung cấp đã lưu. Đừng commit `.env` lên git (đã được gitignore).

## 5. Build và chạy

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Theo dõi log:

```bash
docker compose -f docker-compose.prod.yml logs -f open_notebook
```

- Build image **nhanh** (không có PyTorch).
- **Lần khởi động đầu tiên**: bạn sẽ thấy dòng `[entrypoint] Installing Docling...`
  — đây là bước cài docling + PyTorch (CPU) vào volume, **có thể mất vài phút**.
  Sau đó mới tới migration DB và API lên ở cổng 5055. Các lần khởi động sau bỏ qua
  bước này (đã cache trên `notebook_data`).
- Caddy tự xin chứng chỉ HTTPS cho cả hai domain (log riêng: `... logs -f caddy`).

## 6. Kiểm tra

```bash
curl -sS https://api.5491sotay.io.vn/health    # API sống -> {"status":"healthy"}
```

Mở trình duyệt: **https://5491sotay.io.vn**

- Đăng nhập lần đầu: **admin / admin**
- **Đổi mật khẩu admin ngay** (menu bên trái → "Đổi mật khẩu").
- Giao diện mặc định tiếng Việt; font Times New Roman, tông trắng–đỏ bọc đô Agribank.
- Vào **Cài đặt → Nhà cung cấp** để nhập API key của mô hình AI (OpenAI/Anthropic/…)
  thì chat mới hoạt động.

## 7. Nâng cấp về sau (khi có code mới)

```bash
cd /opt/chatbot5400
git pull origin claude/practical-wozniak-9s1t6z
cd deploy
docker compose -f docker-compose.prod.yml up -d --build
```

Dữ liệu (SurrealDB, uploads, chat) nằm trên các thư mục `deploy/surreal_data` và
`deploy/notebook_data` nên **không mất** khi build lại. Migration DB tự chạy khi
API khởi động.

## 8. Lệnh vận hành hữu ích

```bash
docker compose -f docker-compose.prod.yml ps          # trạng thái
docker compose -f docker-compose.prod.yml logs -f     # xem log tất cả
docker compose -f docker-compose.prod.yml restart     # khởi động lại
docker compose -f docker-compose.prod.yml down        # dừng (giữ dữ liệu)
```

## Xử lý sự cố

- **Caddy không cấp được HTTPS:** kiểm tra cổng 80/443 đã mở và DNS đã trỏ đúng
  (`dig 5491sotay.io.vn +short`). Xem `logs -f caddy`.
- **`no space left on device`:** dọn Docker cũ `docker system prune -af && docker builder prune -af`,
  kiểm tra `df -h /`. Image gọn nên hiếm khi gặp lúc build; nếu hết đĩa lúc chạy,
  thường do PyTorch/model docling — cần thêm dung lượng.
- **Lần đầu chạy rất lâu / có vẻ "treo":** đó là bước cài docling ở boot đầu tiên.
  Xem `logs -f open_notebook`, chờ dòng `[entrypoint] Docling installed`. Nếu cài
  docling **thất bại** (mất mạng...), app vẫn chạy nhưng dùng bộ trích thô; sửa
  mạng rồi `restart` để cài lại.
- **Cài docling bị kill (thiếu RAM):** tạm thêm swap rồi `restart`:
  ```bash
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  ```
- **`There was a problem with authentication` (API/worker không nối được DB):**
  `SURREAL_PASSWORD` trong `.env` bị trống hoặc đã đổi so với lúc khởi tạo DB. Đặt
  mật khẩu, **xóa DB cũ** rồi chạy lại (an toàn khi chưa có dữ liệu):
  ```bash
  docker compose -f docker-compose.prod.yml down
  sed -i "s|^SURREAL_PASSWORD=.*|SURREAL_PASSWORD=$(openssl rand -hex 16)|" .env
  rm -rf surreal_data
  docker compose -f docker-compose.prod.yml up -d
  ```
  (Từ bản mới, compose sẽ **báo lỗi ngay** nếu `SURREAL_PASSWORD` trống thay vì
  khởi tạo DB với mật khẩu rỗng.)
- **Đăng nhập bị đăng xuất sau mỗi lần restart:** chưa đặt `OPEN_NOTEBOOK_JWT_SECRET`
  trong `.env` — đặt rồi `up -d`.
- **Chat báo lỗi cấu hình mô hình:** chưa nhập API key nhà cung cấp (bước 6).
- **Tài liệu vẫn mất Điều/Khoản:** docling chưa cài xong hoặc đang fallback. Kiểm
  tra trong container:
  ```bash
  docker compose -f docker-compose.prod.yml exec open_notebook \
    /app/.venv/bin/python -c "import importlib.util as u; print('docling:', u.find_spec('docling') is not None)"
  ```
  Phải in `docling: True`. Nếu `False`, xem log boot và `restart`.

## Bí quyết cho VPS yếu (build tại nơi khác)

Nếu muốn build image ở máy mạnh rồi đẩy lên:
`docker build -t <registry>/chatbot5400:latest ..` → `docker push` → trên VPS đổi
service `open_notebook` từ `build:` sang `image: <registry>/chatbot5400:latest`.
Docling vẫn tự cài ở boot đầu (nhờ `OPEN_NOTEBOOK_ENABLE_DOCLING=true`).
