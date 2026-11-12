# OCR Engine Manager — Rollback

Mốc rollback: commit `5e042279439302d3ccf39bef4d1d8d402314d194` (release v1.0.8, trước tính năng).
**Không cần** xoá volume, database hay model; không dùng `docker compose down -v`.

## 1. Rollback nhanh không đổi mã (giữ bản mới)

Trong Settings → OCR Engine Manager bấm **Sử dụng** trên *RapidOCR – PaddleOCR* (hoặc
`POST /api/ocr/engines/rapidocr/activate`). Với cấu hình mặc định (không đặt số luồng, không
bắt buộc full-page) và khi Auto của Docling vẫn chọn RapidOCR, tài liệu lại đi **nguyên đường
Content Core** như trước.

## 2. Rollback mã nguồn

```bash
git checkout 5e042279439302d3ccf39bef4d1d8d402314d194   # hoặc revert các commit OCR
docker compose -f deploy/docker-compose.prod.yml up -d --build
```

An toàn vì:
- **Không có migration DB.** Các trường mới (`docling_ocr_engine`, `docling_ocr_device`,
  `docling_ocr_num_threads`, `docling_ocr_force_full_page`) nằm trong record schemaless
  `open_notebook:content_settings`; bản cũ bỏ qua chúng (`RecordModel` chỉ nạp thuộc tính nó
  biết). Không cần xoá.
- Thư mục `/app/data/ocr` không được bản cũ đọc; có thể giữ để tiến lên lại, hoặc xoá thủ công
  nếu muốn thu hồi dung lượng (`./notebook_data/ocr`, chỉ chứa model OCR/manifest/wheel).
- Biến `OPEN_NOTEBOOK_ENABLE_OCR_*`, `OCR_*`, build arg `OCR_INSTALL_TESSERACT` bị bản cũ bỏ
  qua; nên gỡ khỏi compose cho gọn. `TESSDATA_PREFIX` chỉ ảnh hưởng Tesseract.
- Nếu đã cài `easyocr` vào venv của container: recreate container (venv từ image) sẽ loại bỏ
  nó; nếu không recreate, cần biết rằng khi có `easyocr`, **Auto của Docling ở bản cũ sẽ chọn
  EasyOCR** — vì vậy sau rollback mã hãy recreate container (hoặc `uv pip uninstall easyocr`).

## 3. Rollback một phần

| Muốn | Cách |
|---|---|
| Tắt một engine | Gỡ model (Settings) và bỏ biến `OPEN_NOTEBOOK_ENABLE_OCR_*` tương ứng |
| Bỏ Tesseract khỏi image | Build lại không có `OCR_INSTALL_TESSERACT=true` |
| Về lại engine mặc định | §1 |
