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
> từ nhánh này. Docling là phụ thuộc cứng nên **image nặng vài GB**, lần build đầu
> chậm.

## 0. Yêu cầu VPS

- **RAM:** ≥ 4 GB (build có PyTorch; 2 GB dễ bị OOM — nếu chỉ 2 GB xem mục *Bí quyết* cuối bài).
- **Ổ đĩa trống:** ≥ 15 GB (image + model docling + dữ liệu).
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

Lần đầu build lâu (kéo PyTorch + model docling). Theo dõi log:

```bash
docker compose -f docker-compose.prod.yml logs -f open_notebook
```

Chờ tới khi thấy migration chạy xong và API sẵn sàng ở cổng 5055. Caddy sẽ tự xin
chứng chỉ HTTPS cho cả hai domain (log của Caddy: `... logs -f caddy`).

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
- **Build bị "no space left on device":** dọn Docker cũ `docker system prune -af`,
  hoặc nâng dung lượng ổ đĩa.
- **Build bị kill khi cài PyTorch (thiếu RAM):** tạm thêm swap:
  ```bash
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  ```
- **Đăng nhập bị đăng xuất sau mỗi lần restart:** chưa đặt `OPEN_NOTEBOOK_JWT_SECRET`
  trong `.env` — đặt rồi `up -d`.
- **Chat báo lỗi cấu hình mô hình:** chưa nhập API key nhà cung cấp (bước 6).
- **Docling (giữ đúng Điều/Khoản):** đã bật sẵn (nằm trong image). Nếu tài liệu vẫn
  mất cấu trúc, xem `logs -f open_notebook` khi upload để biết engine nào được dùng.

## Bí quyết cho VPS yếu (build tại nơi khác)

Nếu VPS quá yếu để build, có thể build image ở máy mạnh rồi đẩy lên:
`docker build -t <registry>/chatbot5400:latest ..` → `docker push` → trên VPS đổi
service `open_notebook` từ `build:` sang `image: <registry>/chatbot5400:latest`.
