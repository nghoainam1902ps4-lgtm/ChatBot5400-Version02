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

## Ghi chú Phase 9A — URL ingestion khi rollback

- Bản trước RC (`5e04227`) **không có** công tắc `OPEN_NOTEBOOK_ENABLE_URL_INGESTION`: rollback mã về bản đó
  đồng nghĩa chức năng thêm nguồn từ URL **hoạt động trở lại**, cùng với rủi ro SSRF còn lại. Nếu phải
  rollback trong môi trường yêu cầu tắt URL ingestion, cần biện pháp tạm thời ở tầng mạng (chính sách egress
  cho container ứng dụng) cho tới khi triển khai lại.
- Công tắc không tạo dữ liệu mới và không cần hoàn tác: nguồn URL cũ không bị sửa hay xóa.
- Tắt riêng công tắc trên bản RC (bật lại URL ingestion): đặt `OPEN_NOTEBOOK_ENABLE_URL_INGESTION=true` và
  recreate container; cần phê duyệt vì rủi ro còn lại xuất hiện trở lại.

## Ghi chú Phase 9B

- Rollback mã về `5e04227` cũng làm mất các bản vá phân quyền của D-31: route credential / model lại chỉ yêu
  cầu đăng nhập. Trong thời gian chạy bản cũ, chỉ để quản trị viên thao tác và triển khai lại bản RC sớm nhất
  có thể.
- Trên production, tạo lại container ứng dụng bằng `docker compose up -d --no-deps --no-build open_notebook`
  (không `--build`, không bỏ `--no-deps`): lệnh ở mục 2 phía trên là lệnh chung cho bản `deploy/`; quy trình
  cụ thể cho máy chủ hiện tại ở `OCR_PRODUCTION_DEPLOYMENT_PLAN.md` mục 10.
- Image trước khi triển khai được giữ dưới một tag riêng `chatbot5400:rollback-pre-ocr-<thời điểm>`; không dựa
  vào tag `chatbot5400:local` (bị ghi đè khi triển khai).
- Ngân sách thời gian dò hướng và cảnh báo chuyển đổi một phần (D-30, D-32) không tạo dữ liệu mới; không cần
  hoàn tác.
