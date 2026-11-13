# Chuẩn bị ONLINE — vận hành OCR OFFLINE

Mô hình vận hành từ Phase 8A:

- **ONLINE** (có Internet) để cài đặt, cập nhật và chuẩn bị model.
- **OFFLINE** (không Internet) để xử lý tài liệu: OCR, Layout Heron, TableFormer, trích xuất và
  xuất Markdown.

Chỉ phần xử lý tài liệu được bảo đảm chạy offline. **Không** hứa LLM / embedding chạy offline:
chúng phụ thuộc nhà cung cấp mô hình bạn cấu hình (Ollama nội bộ thì chạy được, API đám mây thì không).

Cài đặt hoặc cập nhật hoàn toàn offline **không bắt buộc**. Offline bundle (`OCR_OFFLINE_INSTALLATION.md`)
vẫn còn cho máy air-gapped, nhưng không được mở rộng thêm.

> **An toàn dữ liệu:** mọi lệnh dưới đây không xoá database, volume hay `notebook_data`.
> **Không** dùng `docker compose down -v`.

## 0. Biến dùng chung

Các lệnh chạy trên server, trong thư mục `deploy/` của mã nguồn đang triển khai.

```bash
cd deploy
ocr() { docker compose -f docker-compose.prod.yml exec open_notebook /app/.venv/bin/python -m open_notebook.ocr.cli "$@"; }
ocr status --no-db
```

Có thể thao tác trên giao diện thay cho CLI. Vào **Settings → Content Processing → OCR Engine
Manager**, khung "Trạng thái sẵn sàng xử lý ngoại tuyến" có hai nút:

- **Chuẩn bị model** — gọi `POST /api/ocr/engines/{id}/prepare`.
- **Kiểm tra sẵn sàng offline** — gọi `POST /api/ocr/engines/{id}/readiness-check`.

Cả hai đều cần quyền admin và chạy bằng job nền của worker.

## 1. Cài đặt khi có Internet

Bật runtime cho engine cần dùng: Docling luôn bắt buộc; Tesseract và EasyOCR chỉ bật khi dùng.
Xem `OCR_DOCKER_STORAGE.md` §2. Với Tesseract, khuyến nghị bake binary vào image bằng build arg
`OCR_INSTALL_TESSERACT=true`.

```bash
cd deploy
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs --tail 200 open_notebook | grep -E "Using locked runtime constraints|Docling"
```

Khi khởi động, entrypoint cài Docling (và EasyOCR nếu bật) vào venv. Gói tải xuống được lưu trong
cache uv trên volume (`/app/data/.cache/uv`). Khởi động **không** tải model OCR nào.

## 2. Cập nhật khi có Internet

```bash
git pull
cd deploy
docker compose -f docker-compose.prod.yml up -d --build
```

Những thứ được giữ nguyên qua bản cập nhật:

- model OCR (`/app/data/ocr/models`, kiểm tra SHA-256, không tải lại);
- cache Docling Hugging Face (`/app/data/.cache/huggingface`);
- cache uv;
- cấu hình trong SurrealDB.

Sau khi cập nhật, phiên bản Docling / RapidOCR / torch / EasyOCR / Tesseract đã thay đổi. Kết quả
"sẵn sàng offline" cũ vì thế bị đánh dấu **lỗi thời**. Chạy lại §5–§7.

## 3. Cài runtime

Runtime có hai nhóm:

- **Python:** `docling` và `easyocr`. Cài với phiên bản khoá theo `/app/runtime-constraints.txt`
  (sinh từ `uv.lock`).
- **Hệ thống:** binary `tesseract`.

Prepare **không** tự cài runtime qua HTTP: web application không có quyền root và không chạy
`pip` / `apt` theo yêu cầu. Muốn cài runtime còn thiếu, admin dùng CLI (`--install-runtime`) hoặc
build image với build arg.

```bash
cd deploy
ocr status --no-db
ocr prepare --engines easyocr --install-runtime
```

## 4. Cài engine

Mỗi engine có model riêng. Model được ghim phiên bản và kiểm tra checksum:

- `tesseract_fast` / `tesseract_best`: `vie` + `eng` traineddata trong `/app/data/ocr/models/tesseract/{fast,best}`;
- `easyocr`: `craft_mlt_25k.pth` + `latin_g2.pth` trong `/app/data/ocr/models/easyocr`;
- `rapidocr`: không có model do OCR Engine Manager quản lý (xem §7).

```bash
cd deploy
ocr install-model tesseract_best
ocr status --no-db
```

## 5. Tải model

Lệnh `prepare` gộp toàn bộ các bước chuẩn bị:

1. tải model OCR còn thiếu;
2. chạy pipeline thật khi đang có Internet (tải Heron / TableFormer / trọng số RapidOCR nếu thiếu);
3. chạy lại pipeline khi **đã chặn mạng** để xác minh mọi thứ đã nằm sẵn trên máy.

Chạy lại `prepare` chỉ tải phần còn thiếu; model đã có và hợp lệ sẽ được dùng lại.

```bash
cd deploy
ocr prepare --engines tesseract_best
ocr prepare --engines rapidocr tesseract_fast tesseract_best easyocr
```

Thêm `--no-download` để chỉ kiểm tra mà không bao giờ tải.

## 6. Chuẩn bị Layout Heron và TableFormer

Docling tải `docling-project/docling-layout-heron` và `docling-project/docling-models` (TableFormer
accurate) từ Hugging Face vào `HF_HOME=/app/data/.cache/huggingface`, tức là nằm trên volume.
`prepare` kích hoạt việc tải này bằng chính cách production nạp model: pipeline Docling thật trên
tài liệu mẫu. Không có bước tải riêng hay đường dẫn model tự chế. Layout Heron và TableFormer **không**
bị thay đổi.

Kết quả kiểm tra phải có đủ ba trường `layout_model=layout_heron`, `table_model=docling_tableformer`,
`table_mode=accurate`. Thiếu bất kỳ trường nào thì `pipeline_ok=false`.

## 7. Chuẩn bị RapidOCR

RapidOCR là engine mặc định và giữ nguyên hành vi: Docling Auto chọn RapidOCR, model PP-OCR mặc định,
backend torch.

- **Mặc định — warm-up.** `prepare --engines rapidocr` chạy pipeline một lần khi có Internet để RapidOCR
  tự tải trọng số vào **thư mục gói trong venv**. Thư mục này nằm ở *layer container*: còn lại khi
  restart, **mất khi recreate** (cập nhật image, đổi cấu hình compose). Sau khi recreate cần có Internet
  để chạy `prepare` lại. Readiness tự phát hiện việc mất trọng số (fingerprint thay đổi) và chuyển về
  "Chưa kiểm tra toàn bộ pipeline", không báo sai là sẵn sàng.
- **Tuỳ chọn — lưu bền vững.** Đặt `OCR_RAPIDOCR_PERSISTENT=true`. Khi đó trọng số được lưu ở
  `/app/data/ocr/models/rapidocr` và truyền vào RapidOCR qua tham số chính thức
  `RapidOcrOptions.rapidocr_params["Global.model_root_dir"]`.
  - Vẫn cùng model và cùng backend; trọng số đã có trong venv được sao chép sang, chỉ những file có
    SHA-256 khớp danh sách `default_models.yaml` của RapidOCR.
  - Với cách này, RapidOCR vẫn chạy offline sau recreate.
  - Trạng thái kiểm chứng: đã kiểm chứng với backend onnxruntime; với backend torch (production) là
    **NOT VERIFIED** trong Cloud (xem `OCR_TEST_REPORT.md` §8).

```bash
cd deploy
ocr prepare --engines rapidocr
```

## 8. Kiểm tra toàn bộ pipeline

```bash
cd deploy
ocr readiness --engines tesseract_best
ocr readiness --engines tesseract_best --check --json
```

`--check` chạy pipeline production (Heron + TableFormer + OCR đã chọn) trên tài liệu mẫu trong một
tiến trình con. Lệnh này **không bao giờ tải** gì.

Có ba mức kiểm tra:

| Mức kiểm tra | Cách chạy | Ý nghĩa |
|---|---|---|
| `online` | khi `prepare` có Internet | pipeline chạy được; có thể vừa tải model |
| `local_only` | tiến trình con với mọi proxy trỏ tới cổng đóng `127.0.0.1:9` | mọi lần tải đều thất bại ⇒ pass chứng minh mọi thứ đã nằm sẵn trên máy |
| `offline` | khi Internet thật sự không tới được | bằng chứng mạnh nhất |

## 9. Xác nhận sẵn sàng offline

| Trạng thái | Nghĩa |
|---|---|
| `runtime_missing` | thiếu Docling / Tesseract / EasyOCR |
| `incompatible` | phiên bản khác bộ đã kiểm chứng |
| `model_missing` / `model_incomplete` | thiếu model OCR, hoặc model sai checksum |
| `pipeline_not_verified` | chưa có lần kiểm tra chặn mạng nào còn hiệu lực; có thể đã pass `online` (OCR-only) |
| `not_offline_ready` | lần kiểm tra chặn mạng hoặc offline gần nhất thất bại |
| `offline_ready` | lần kiểm tra `local_only` hoặc `offline` gần nhất pass toàn bộ pipeline, và chưa có gì thay đổi |

Các nguyên tắc khi xác định trạng thái:

- Chỉ có file hoặc checksum **không bao giờ** đủ để được `offline_ready`.
- Kiểm tra OCR thành công (nút **Kiểm tra**) chỉ chứng minh riêng phần OCR.
- `offline_verified=true` chỉ được đặt khi đã kiểm tra lúc thật sự ngắt Internet.
- Kết quả bị coi là **lỗi thời** khi một trong các thứ sau thay đổi:
  - phiên bản Docling / Content Core / RapidOCR / torch / Tesseract / EasyOCR;
  - checksum model;
  - snapshot Heron / TableFormer trong cache;
  - trọng số RapidOCR;
  - `OCR_RAPIDOCR_PERSISTENT` hoặc `OCR_RAPIDOCR_FORCE_CPU`.

## 10. Ngắt Internet

Ngắt ở **tầng mạng của server**: firewall hoặc chính sách egress, hoặc rút kết nối WAN. Phải giữ kết
nối tới SurrealDB và tới người dùng nội bộ. Không cần sửa image hay compose.

Trường hợp container sẽ bị **recreate** trong lúc offline, thêm hai biến sau vào service `open_notebook`
trước khi ngắt mạng (xem `OCR_DOCKER_STORAGE.md` §5):

- `OCR_OFFLINE=true` — entrypoint cài lại Docling / EasyOCR từ cache uv bằng `--offline`;
- `HF_HUB_OFFLINE=1` — tuỳ chọn; Docling không thử mạng.

Chỉ restart thì không cần hai biến này.

## 11. Kiểm tra OCR sau khi ngắt Internet

```bash
cd deploy
ocr readiness --check
ocr readiness --json
```

Khi Internet không tới được, kiểm tra chạy ở mức `offline` và đặt `offline_verified=true`. Sau đó tải
lên một PDF scan mẫu (không chứa dữ liệu nhạy cảm) trong notebook và kiểm tra nội dung Markdown.

## 12. Restart container khi offline

```bash
cd deploy
docker compose -f docker-compose.prod.yml restart open_notebook
ocr readiness --check
```

Restart giữ nguyên venv, model, cache và cấu hình, nên mọi engine đã chuẩn bị đều tiếp tục chạy.

Recreate khi offline cũng được, với điều kiện có `OCR_OFFLINE=true` và cache uv chứa đúng phiên bản.
Riêng RapidOCR ở chế độ mặc định thì **mất trọng số** khi recreate (xem §7).

## 13. Khi thiếu model lúc offline

Nếu tài liệu cần một model không có sẵn trên máy (ví dụ cache Heron bị xoá, hoặc RapidOCR sau recreate):

- job xử lý nguồn **thất bại ngay** và không thử lại. Lỗi được đổi thành `ValueError`, nên worker
  không retry;
- thông báo hiển thị: "An OCR/Docling model needed for this document is not available locally and
  cannot be downloaded now (no Internet). Connect to the Internet and run 'Prepare models'…";
- **không** âm thầm chuyển sang engine khác, **không** treo chờ tải.

Engine đã chọn mà chưa cài (thiếu model hoặc runtime) cũng báo lỗi rõ ràng như từ Phase 1 (D-07).

Cách xử lý: kết nối Internet, chạy §5 cho engine đó, rồi xử lý lại nguồn.

## 14. Kết nối lại để cập nhật

```bash
cd deploy
git pull
docker compose -f docker-compose.prod.yml up -d --build
ocr prepare --engines tesseract_best
ocr readiness --engines tesseract_best --json
```

Cần làm thêm hai việc:

- Bỏ `OCR_OFFLINE=true` khỏi compose trong lúc cập nhật, nếu bản mới cần tải gói mới.
- Sau khi cập nhật, các kết quả cũ đã lỗi thời: `prepare` chỉ tải phần còn thiếu (model cũ được dùng
  lại theo checksum), rồi chạy lại kiểm tra chặn mạng.

Ngắt Internet lại chỉ khi trạng thái là `offline_ready`.

## 15. Rollback

Xem `OCR_ROLLBACK.md`. Tóm tắt: checkout commit trước, `docker compose -f docker-compose.prod.yml up -d --build`,
**không** xoá volume.

- Model, cache và manifest trên volume không gây hại cho bản cũ.
- Trạng thái readiness lưu trong `/app/data/ocr/manifests`. Bản cũ bỏ qua dữ liệu này; khi quay lại
  bản mới, kết quả được tính lại theo fingerprint.

Nghiệm thu toàn bộ quy trình trên máy nội bộ (online → chuẩn bị → offline → restart → cập nhật):
`OCR_LOCAL_ACCEPTANCE.md` §5.
