# OCR — Docker, lưu trữ bền vững và cập nhật

## 1. Phân loại thành phần

| Thành phần | Nơi lưu | Restart | Recreate / image mới | Khôi phục |
|---|---|---|---|---|
| Model OCR (tessdata, EasyOCR .pth) | `/app/data/ocr/models` (volume `./notebook_data`) | giữ | giữ | không cần, không tải lại (kiểm tra SHA-256) |
| Trạng thái cài đặt | `/app/data/ocr/manifests` | giữ | giữ | – |
| Wheel/.deb offline | `/app/data/ocr/packages` | giữ | giữ | entrypoint cài lại offline |
| Wheel cache uv | `/app/data/.cache/uv` (có sẵn) | giữ | giữ | entrypoint cài lại không tải |
| Python `easyocr` | venv trong layer image | giữ | **mất** | `OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR=true` |
| `tesseract-ocr` | filesystem container | giữ | **mất** (trừ build arg) | build arg `OCR_INSTALL_TESSERACT=true` (khuyến nghị) hoặc `OPEN_NOTEBOOK_ENABLE_OCR_TESSERACT=true` |
| Layout/TableFormer | `HF_HOME=/app/data/.cache/huggingface` (có sẵn) | giữ | giữ | không đổi |
| Trọng số RapidOCR (mặc định) | thư mục gói `rapidocr/models` trong venv | giữ | **mất** | `prepare` khi có Internet; hoặc `OCR_RAPIDOCR_PERSISTENT=true` |
| Trọng số RapidOCR (`OCR_RAPIDOCR_PERSISTENT=true`) | `/app/data/ocr/models/rapidocr` | giữ | giữ | không cần |
| Từ điển nhận dạng RapidOCR (backend torch, cả hai chế độ) | thư mục gói `rapidocr/models` trong venv | giữ | **mất** | `prepare` một lần khi có Internet sau recreate (D-32) |
| Kết quả readiness | `/app/data/ocr/manifests` | giữ | giữ (lỗi thời nếu phiên bản / cache / trọng số đổi) | `readiness --check` |
| Cấu hình OCR | SurrealDB | giữ | giữ | – |

Không có thành phần OCR nào được tải khi cài mới hay khi khởi động: entrypoint chỉ khôi phục
*runtime* của engine mà admin đã bật bằng biến môi trường.

## 2. Bật engine trên server hiện có (production)

`deploy/docker-compose.prod.yml` → service `open_notebook`:

```yaml
    build:
      context: ..
      dockerfile: Dockerfile
      target: runtime
      args:
        OCR_INSTALL_TESSERACT: "true"   # nếu dùng Tesseract Fast/Best
    environment:
      # ...các biến hiện có...
      - OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR=true   # nếu dùng EasyOCR
```

```bash
cd deploy
docker compose -f docker-compose.prod.yml up -d --build      # KHÔNG dùng "down -v"
```

Sau đó vào Settings → OCR Engine Manager → **Cài đặt** model → **Kiểm tra** → **Sử dụng**.

## 3. Cập nhật ChatBot5400

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

Volume `./notebook_data` giữ model, manifest, wheel cache; entrypoint khôi phục runtime; cấu
hình nằm trong SurrealDB. Phiên bản Docling/Tesseract/EasyOCR mới được kiểm tra lúc chạy (trạng
thái `incompatible` kèm lý do nếu không phù hợp). **Không** chạy `docker compose down -v`,
không xoá `notebook_data` hay `surreal_data`.

## 4. Nghiệm thu Docker trên máy nội bộ

```bash
SCENARIOS="tesseract_best easyocr" OLD_REF=5e042279439302d3ccf39bef4d1d8d402314d194 bash scripts/ocr/docker-acceptance.sh
```

Script tự build image, dùng compose project + thư mục dữ liệu **tạm riêng** (không đụng triển khai
hiện có), và kiểm tra qua **API + worker thật**: nâng cấp từ bản đang chạy, không tải engine lúc khởi
động, cài/kích hoạt/test/upload/xử lý từng engine, restart, offline bằng mạng `internal` (DB vẫn kết
nối, Internet bị chặn), build lại image thật và recreate. Chi tiết: `OCR_LOCAL_ACCEPTANCE.md` §5.

## 5. Phase 7 — khoá phiên bản và offline

- Image có `/app/runtime-constraints.txt` (xuất từ `uv.lock` lúc build). Entrypoint cài Docling và CLI
  cài EasyOCR với `-c` file này ⇒ container mới luôn nhận `docling==2.129.0`, `rapidocr==3.9.2`,
  `torch==2.14.0` (+cpu với `UV_TORCH_BACKEND=cpu`), `easyocr==1.7.2`. Log khởi động in
  `Using locked runtime constraints: ...`.
- Máy không Internet: đặt `OCR_OFFLINE=true` (Docling/EasyOCR cài lại từ cache uv trên volume với
  `--offline`) và `HF_HUB_OFFLINE=1` (Docling dùng Heron/TableFormer đã có trong `HF_HOME`).
- **Giới hạn có sẵn (không do tính năng này):** RapidOCR backend torch tải trọng số PP-OCR từ
  modelscope.cn vào **thư mục gói trong venv** ⇒ mất khi recreate container. Trên máy không Internet,
  engine mặc định RapidOCR sẽ không tải lại được sau recreate. Engine Tesseract/EasyOCR không bị ảnh
  hưởng (model nằm trên volume). Không thay đổi trong phạm vi này để giữ nguyên hành vi mặc định.
- Nghiệm thu thực tế: `docs/ocr/OCR_LOCAL_ACCEPTANCE.md`.

## 6. Phase 8A — chuẩn bị online, vận hành offline

- Quy trình đầy đủ: `OCR_ONLINE_PREPARATION.md`. Tóm tắt: cập nhật khi online →
  `cli prepare --engines ...` → trạng thái `offline_ready` → ngắt Internet ở tầng mạng của server.
- **Restart** khi offline: an toàn với mọi engine đã chuẩn bị.
- **Recreate** khi offline cần `OCR_OFFLINE=true` (cài lại Docling / EasyOCR từ cache uv). RapidOCR
  mặc định mất trọng số khi recreate; readiness phát hiện và báo lại "chưa kiểm tra". Muốn giữ trọng số:
  `OCR_RAPIDOCR_PERSISTENT=true` (backend torch NOT VERIFIED trong Cloud).
- Nghiệm thu Docker theo mô hình này: `OCR_LOCAL_ACCEPTANCE.md` §5. Offline được giả lập bằng
  `docker network disconnect` của container đang chạy (D-23).
- Đoạn "Giới hạn có sẵn" ở §5 vẫn đúng với chế độ mặc định. Tuỳ chọn `OCR_RAPIDOCR_PERSISTENT` là cách
  khắc phục, không bật mặc định.
