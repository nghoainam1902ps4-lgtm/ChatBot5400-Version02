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
docker build --target runtime --build-arg OCR_INSTALL_TESSERACT=true -t chatbot5400:ocr-test .
IMAGE=chatbot5400:ocr-test scripts/ocr/docker-acceptance.sh
```

Script chạy trong compose project và thư mục dữ liệu **tạm riêng**, không đụng tới triển khai
hiện có, và kiểm tra: cài mới không tải engine; cài một engine không tải engine khác; restart,
recreate, image mới giữ model (không tải lại); gỡ Fast giữ osd cho Best; cài thất bại không ảnh
hưởng engine sẵn sàng; khởi động offline.
