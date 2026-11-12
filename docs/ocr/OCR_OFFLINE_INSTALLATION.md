# OCR — Cài đặt offline (môi trường hạn chế Internet)

## 1. Chuẩn bị bundle trên máy có Internet

Chạy **trong container dựng từ cùng image** (để bộ wheel/.deb khớp đúng cái máy đích thiếu):

```bash
docker compose run --rm --no-deps -v "$PWD/ocr-offline-bundle:/bundle" open_notebook \
  uv run --no-sync python -m open_notebook.ocr.cli bundle create \
  --engines tesseract_best easyocr --out /bundle
```

- Có thể chọn một hoặc nhiều engine (`tesseract_fast`, `tesseract_best`, `easyocr`).
- `--models-only`: chỉ model (khi máy đích đã có runtime, ví dụ image nướng sẵn Tesseract).
- Lệnh in ra **bundle digest** — ghi lại để đối chiếu qua kênh tin cậy.

Cấu trúc:

```
ocr-offline-bundle/
├── manifest.json        engine, model/version, Python, CPU, OS, Docling, license, danh sách tệp
├── models/              tessdata / EasyOCR .pth (sha256 khớp catalog trong mã nguồn)
├── wheels/              easyocr==1.7.2 + phụ thuộc còn thiếu (đúng phiên bản uv tính ra)
├── system-packages/     .deb cho tesseract-ocr (apt-get --simulate trong cùng image)
├── checksums.sha256
└── README.md
```

Giấy phép: tessdata_fast/best, Tesseract, EasyOCR + model: Apache-2.0; phụ thuộc Python theo
giấy phép của từng gói (BSD/MIT/Apache, xem metadata wheel). Phân phối nội bộ được phép; giữ
nguyên tệp giấy phép trong wheel.

## 2. Cài trên máy đích (không Internet)

```bash
cp -r ocr-offline-bundle ./notebook_data/ocr-bundle
docker compose exec open_notebook uv run --no-sync python -m open_notebook.ocr.cli bundle verify /app/data/ocr-bundle
docker compose exec open_notebook uv run --no-sync python -m open_notebook.ocr.cli bundle install /app/data/ocr-bundle
```

`bundle install` in ra hai dòng `OCR_TRUSTED_WHEELS_SHA256=…` / `OCR_TRUSTED_DEBS_SHA256=…`.
Thêm chúng và các cờ vào service (để khôi phục runtime mỗi lần recreate, hoàn toàn offline).
Gói đã stage **chỉ được cài khi digest khớp giá trị ghim trong compose** (nằm ngoài volume dữ
liệu) — người có quyền ghi volume không thể khiến container cài gói tuỳ ý bằng root.

```yaml
      - OCR_TRUSTED_WHEELS_SHA256=<giá trị in ra>
      - OCR_TRUSTED_DEBS_SHA256=<giá trị in ra>
      - OCR_OFFLINE=true
      - OPEN_NOTEBOOK_ENABLE_OCR_TESSERACT=true   # nếu bundle có tesseract
      - OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR=true     # nếu bundle có easyocr
```

```bash
docker compose up -d
rm -rf ./notebook_data/ocr-bundle    # tuỳ chọn: wheel/.deb đã được stage vào /app/data/ocr/packages
```

## 3. Bảo đảm

- `bundle verify`/`install` **không** gọi mạng (không PyPI, không Hugging Face, không GitHub).
- Model chỉ được chấp nhận nếu khớp SHA-256 **ghim trong mã nguồn** (`catalog.py`) — bundle bị
  đánh tráo trọng số rồi tính lại checksum vẫn bị từ chối.
- Wheel/.deb được kiểm tra theo `checksums.sha256` của bundle, và được stage kèm checksum; khi
  khôi phục runtime, digest của danh sách checksum phải khớp `OCR_TRUSTED_WHEELS_SHA256` /
  `OCR_TRUSTED_DEBS_SHA256` do operator ghim; wheel `easyocr` còn phải khớp SHA-256 ghim trong mã.
- Tệp thừa, symlink, đường dẫn `../` trong bundle ⇒ từ chối.
- Thiếu thành phần ⇒ báo rõ thành phần nào; không tự tải.
- Không có chức năng upload bundle qua giao diện web.

## 4. Đã kiểm chứng trong Cloud

Bundle 3 engine (15 tệp, 211 MB) tạo online; cài vào data dir mới với proxy bị chặn
(`HTTPS_PROXY=http://127.0.0.1:9`, `UV_OFFLINE=1`, `OCR_OFFLINE=true`): model từ `bundle`,
`dpkg -i` tesseract-ocr, `uv pip install --offline --no-index` 7 wheel ⇒ 4/4 engine `ready`.
Bundle bị sửa 1 byte ⇒ `verify` và `install` exit 1, không ghi gì. Chi tiết: `OCR_TEST_REPORT.md`.
