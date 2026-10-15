# Hướng dẫn cập nhật lên ChatBot 5400 v1.0.6

Bản **v1.0.6** là bản vá tiếp nối v1.0.5:

- Sửa lỗi trang **Cài đặt** tự kéo dài vô hạn khi cuộn (thanh "Lưu thay đổi"
  dùng `backdrop-blur` gây lỗi compositor Chromium).
- Ẩn nút **"Nâng cao"** chọn mô hình ở **Hỏi & Tìm kiếm** với người dùng
  thường (mô hình do admin cài đặt).

> ✅ **An toàn để nâng cấp:** KHÔNG có migration DB mới, KHÔNG đổi schema. Dữ
> liệu giữ nguyên khi build lại.

Các bước cập nhật **giống hệt** [UPDATE-v1.0.5.md](UPDATE-v1.0.5.md), chỉ thay
`v1.0.5` → **`v1.0.6`**. Tóm tắt nhanh:

## VPS (production)

```bash
cd /opt/chatbot5400/deploy
docker compose -f docker-compose.prod.yml down
tar czf backup-$(date +%F-%H%M).tgz surreal_data notebook_data .env   # sao lưu

cd /opt/chatbot5400
git fetch origin --tags
git checkout v1.0.6
cd deploy
docker compose -f docker-compose.prod.yml up -d --build

curl -sS https://api.5491sotay.io.vn/health    # {"status":"healthy"}
```

## Máy chủ local (Docker)

```bash
cd <repo>
docker compose down
git fetch origin --tags
git checkout v1.0.6
docker compose up -d --build
curl -sS http://localhost:5055/health
```

## Máy local (dev)

```bash
cd <repo>
make stop-all 2>/dev/null || true
git fetch origin --tags
git checkout v1.0.6
uv sync
cd frontend && npm ci && npm run build && cd ..
make start-all
```

## Kiểm tra sau khi lên bản

- Góc dưới sidebar hiển thị **Phiên bản 1.0.6**.
- Vào **Cài đặt** (admin): bật/tắt công tắc rồi cuộn — trang **không** còn tự
  kéo dài; thanh "Lưu thay đổi" nền đặc, đứng yên ở đáy.
- **Hỏi & Tìm kiếm** (tab Hỏi): tài khoản **user thường** không còn nút
  "Nâng cao"; tài khoản **admin** vẫn có.

> Nếu chưa tạo tag `v1.0.6`, xem mục 0 trong UPDATE-v1.0.5.md (cách tạo tag),
> hoặc tạo tag ngay khi Publish GitHub Release.
