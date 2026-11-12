# Hướng dẫn cập nhật lên ChatBot 5400 v1.0.8

Bản **v1.0.8** bổ sung **quy trình duyệt văn bản** và **phân quyền 4 vai trò**:

- Vai trò mới: **Quản lý sổ tay** (gửi văn bản, phải được duyệt) và **Kiểm
  soát** (duyệt văn bản, quản lý chuyên mục được giao, tạo sổ tay con, gắn nguồn
  có sẵn). Vẫn giữ **Quản trị viên** và **Người dùng** (chỉ xem/chat).
- Sổ tay có quan hệ **chuyên mục → sổ tay con** (2 cấp).
- Văn bản do Quản lý sổ tay gửi ở trạng thái **chờ duyệt**: không hiển thị,
  không vào tìm kiếm/Hỏi đáp cho tới khi được duyệt. **Từ chối = xóa hẳn**.
- Trang **Duyệt văn bản** (có số đếm ở menu, thông báo khi đăng nhập, cửa sổ
  duyệt xem nội dung và đổi sổ tay).

Chi tiết: xem [CHANGELOG.md](../CHANGELOG.md), mục 1.0.8.

> Máy đã chạy bản thử nghiệm của tính năng này (trước khi phát hành, sidebar
> hiện "Phiên bản 1.0.7") đã có sẵn migration 31–33: chỉ cần chạy khối lệnh
> thứ hai ở mục VPS bên dưới (`git checkout v1.0.8` rồi build lại), không cần
> sao lưu lại.

> ⚠️ **Bản này CÓ migration cơ sở dữ liệu (31, 32, 33)** — khác các bản 1.0.5 và
> 1.0.6. Migration chạy **tự động** khi API khởi động. Thay đổi chỉ **thêm**
> trường mới, dữ liệu cũ giữ nguyên: mọi nguồn hiện có được đánh dấu "đã duyệt",
> tài khoản hiện có giữ nguyên vai trò. **Bắt buộc sao lưu trước khi nâng cấp.**

## Lưu ý trước khi cập nhật

- **Dung lượng đĩa:** image của ứng dụng lớn; cần khoảng **10 GB trống** để build.
  Lệnh `docker image prune -af` ở bước dưới dọn image cũ trước khi build.
- **Sao lưu:** bỏ qua thư mục `notebook_data/.cache` (bộ thư viện Docling/PyTorch,
  vài GB, tự cài lại được) để sao lưu nhanh.

## VPS (production)

```bash
cd /opt/chatbot5400/deploy
docker compose -f docker-compose.prod.yml down
tar czf backup-$(date +%F-%H%M).tgz --exclude='notebook_data/.cache' surreal_data notebook_data .env
ls -lh backup-*.tgz
```

```bash
cd /opt/chatbot5400
git fetch origin --tags
git checkout v1.0.8
cd deploy
docker image prune -af
docker compose -f docker-compose.prod.yml up -d --build
```

Theo dõi migration (chờ dòng `Migration successful. New version: 33`, rồi Ctrl+C):

```bash
docker compose -f docker-compose.prod.yml logs -f open_notebook
```

```bash
curl -sS https://api.5491sotay.io.vn/health    # {"status":"healthy"}
```

## Máy chủ local (Docker)

```bash
cd <repo>
docker compose down
git fetch origin --tags
git checkout v1.0.8
docker compose up -d --build
curl -sS http://localhost:5055/health
```

## Máy local (dev)

```bash
cd <repo>
make stop-all 2>/dev/null || true
git fetch origin --tags
git checkout v1.0.8
uv sync
cd frontend && npm ci && npm run build && cd ..
make start-all
```

## Thiết lập sau khi lên bản

1. Đăng nhập **Quản trị viên** → **Quản lý người dùng**: tạo tài khoản vai trò
   **Kiểm soát** và **Quản lý sổ tay**.
2. Với tài khoản **Kiểm soát**: tích các **chuyên mục quản lý** (sổ tay cấp cao
   nhất, ví dụ Tín dụng, Kế toán, Tổng hợp). Cần có sẵn ít nhất một sổ tay cấp
   cao nhất.
3. Kiểm soát có thể tạo **sổ tay con** trong chuyên mục của mình (Sổ tay → Sổ
   tay mới → chọn chuyên mục cha).

## Kiểm tra sau khi lên bản

- Góc dưới sidebar hiển thị **Phiên bản 1.0.8**.
- **Quản lý sổ tay** thêm một văn bản (bước cuối chọn người phê duyệt) → văn bản
  **không** xuất hiện với người dùng thường, tìm kiếm không ra.
- **Kiểm soát** đăng nhập → có thông báo và số đếm ở menu **Duyệt văn bản** → bấm
  Duyệt/Từ chối hoặc double-click dòng để mở cửa sổ duyệt → **Duyệt**.
- Sau khi duyệt: văn bản hiện trong sổ tay và tìm kiếm ra được (chờ embed xong).
- Thử **Từ chối** một văn bản khác → văn bản biến mất khỏi hệ thống.
- Trang **Sổ tay** hiển thị sổ tay con lồng dưới chuyên mục.

## Quay lại bản cũ

Vì có migration, **không** chỉ `git checkout v1.0.6` rồi chạy tiếp: bản 1.0.6
không đọc được tài khoản mang vai trò mới (Kiểm soát, Quản lý sổ tay). Cách quay
lại an toàn là khôi phục bản sao lưu:

```bash
cd /opt/chatbot5400/deploy
docker compose -f docker-compose.prod.yml down
rm -rf surreal_data
tar xzf backup-<ngày-giờ>.tgz
cd /opt/chatbot5400 && git checkout v1.0.6
cd deploy && docker compose -f docker-compose.prod.yml up -d --build
```

> Nếu chưa tạo tag `v1.0.8`, xem mục 0 trong [UPDATE-v1.0.5.md](UPDATE-v1.0.5.md)
> (cách tạo tag), hoặc tạo tag ngay khi Publish GitHub Release.
