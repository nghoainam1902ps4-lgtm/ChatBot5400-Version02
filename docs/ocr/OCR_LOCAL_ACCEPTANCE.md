# Nghiệm thu OCR Engine Manager trên máy thật (Linux / Windows + WSL2 / Docker)

Tài liệu thống nhất để nghiệm thu những hạng mục **chưa thể chạy trong Claude Code Cloud**
(Cloud chặn Hugging Face, modelscope, Debian apt và Docker Hub): toàn bộ pipeline Docling (Layout
Heron + TableFormer + OCR), Docker end-to-end, offline, cập nhật image, benchmark thực tế.

> **An toàn dữ liệu:** mọi bước dùng **thư mục, compose project và dữ liệu tạm riêng**. Không cần
> và **không được** dừng, xoá hay sửa deployment hiện tại, database, volume `notebook_data` /
> `surreal_data`. Không dùng `docker compose down -v`.

Tất cả lệnh là bash (Linux, hoặc **Windows: chạy trong WSL2 Ubuntu** với Docker Desktop bật "WSL
integration"). Mọi khối lệnh trong tài liệu được kiểm tra cú pháp tự động bởi
`scripts/ocr/check_doc_commands.py` (test `tests/test_ocr_doc_commands.py`).

## 0. Biến dùng chung

```bash
export ACCEPT_DIR="$HOME/cb5400-ocr-accept"          # thư mục làm việc riêng
export REPO_URL="https://github.com/nghoainam1902ps4-lgtm/ChatBot5400-Version02.git"
export BRANCH="claude/friendly-mendel-a2b6m5"
export OCR_DATA="$ACCEPT_DIR/ocr-data"               # model OCR cho test ngoài Docker
export HF_HOME="$ACCEPT_DIR/hf-cache"                # model Docling Heron/TableFormer
mkdir -p "$ACCEPT_DIR"
```

## 1. Kiểm tra máy

```bash
df -h "$ACCEPT_DIR"            # cần >= 25 GB trống (image ~4 GB, Docling+torch ~3 GB, cache, model)
docker system df               # dung lượng Docker đang dùng
nproc && free -h               # khuyến nghị >= 4 CPU, >= 8 GB RAM (EasyOCR dùng ~4 GB)
docker version --format '{{.Server.Version}}'
docker compose version
git --version
```

Phiên bản cần cho test ngoài Docker (mục 4): Python 3.12, `uv` ≥ 0.5.

```bash
uv --version || curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 2. Lấy mã nguồn vào thư mục riêng

```bash
git clone --branch "$BRANCH" "$REPO_URL" "$ACCEPT_DIR/src"
cd "$ACCEPT_DIR/src" && git log -1 --oneline
```

## 3. Kiểm tra dependency (khoá phiên bản)

```bash
cd "$ACCEPT_DIR/src"
uv lock --check
uv export --frozen --no-dev --extra docling --extra ocr-easyocr --no-hashes --no-emit-project --no-header --no-annotate | grep -E '^(content-core|docling|rapidocr|easyocr|torch)=='
```

Kết quả mong đợi: `content-core==2.0.7`, `docling==2.129.0`, `rapidocr==3.9.2`, `easyocr==1.7.2`,
`torch==2.14.0` (khớp `open_notebook/ocr/compat.py`).

## 4. Test full pipeline ngoài Docker (nhanh, không cần image)

### 4.1 Cài môi trường, runtime và model

```bash
cd "$ACCEPT_DIR/src"
UV_TORCH_BACKEND=cpu uv sync --extra docling --extra ocr-easyocr
sudo apt-get update && sudo apt-get install -y --no-install-recommends tesseract-ocr
export OCR_DATA_DIR="$OCR_DATA"
uv run python -m open_notebook.ocr.cli install-model tesseract_fast
uv run python -m open_notebook.ocr.cli install-model tesseract_best
uv run python -m open_notebook.ocr.cli install-model easyocr
uv run python -m open_notebook.ocr.cli status --no-db
```

### 4.2 Chuẩn bị model Docling (Layout Heron + TableFormer) — cách production nạp

```bash
cd "$ACCEPT_DIR/src"
export OCR_DATA_DIR="$OCR_DATA"
uv run python scripts/ocr/warm_docling_models.py --engine tesseract_best
uv run python scripts/ocr/warm_docling_models.py --engine rapidocr
```

Kết quả in ra phải có `"layout_model": "layout_heron"`, `"table_model": "docling_tableformer"`,
`"table_mode": "accurate"`. (Lệnh `rapidocr` còn tải trọng số PP-OCR torch từ modelscope.cn vào
venv — hành vi gốc, không thay đổi.)

### 4.3 Chạy nghiệm thu nghiêm ngặt

```bash
cd "$ACCEPT_DIR/src"
OCR_ACCEPTANCE_STRICT=1 OCR_TEST_DATA_DIR="$OCR_DATA" OCR_ACCEPTANCE_REPORT="$ACCEPT_DIR/ocr-acceptance.json" uv run pytest tests/test_ocr_integration.py -p no:warnings -q
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d['summary'])" "$ACCEPT_DIR/ocr-acceptance.json"
```

- Strict: thiếu engine/model/model Docling ⇒ **FAIL ghi rõ "NOT VERIFIED"**, không bao giờ skip-rồi-PASS.
- Kiểm tra: engine OCR thực tế, Layout Heron, TableFormer accurate, nội dung Markdown, thứ tự đọc,
  số tiền/ngày/số hiệu, số bảng, số hàng/cột, nội dung từng hàng, ô gộp "Số tiền (đồng)", và phân
  biệt **đạt nhờ OCR** (trang chỉ có ảnh) với **đạt nhờ text layer** (`test_text_layer_vs_ocr_attribution`).
- Ngưỡng chất lượng (`MAX_CER`, `MIN_FIELD_RECALL` trong test) được hiệu chỉnh từ benchmark Cloud;
  nếu lần chạy thật cho số đo khác, ghi số đo vào `OCR_TEST_REPORT.md` trước khi đổi ngưỡng.

## 5. Docker end-to-end

```bash
cd "$ACCEPT_DIR/src"
SCENARIOS="tesseract_best easyocr" OLD_REF=5e042279439302d3ccf39bef4d1d8d402314d194 KEEP_WORK=1 bash scripts/ocr/docker-acceptance.sh 2>&1 | tee "$ACCEPT_DIR/docker-acceptance.log"
```

Script tự build image test (`chatbot5400:ocr-accept`, build arg `OCR_INSTALL_TESSERACT=true`) và image
của phiên bản đang chạy (`OLD_REF`), tạo compose project + thư mục dữ liệu tạm riêng, rồi kiểm tra
qua **API thật + worker thật**:

| Bước | Nội dung |
|---|---|
| 0 | Bản cũ chạy, lưu marker settings |
| 1 | Nâng cấp lên bản mới: DB/API/worker sẵn sàng, Docling bật, phiên bản dependency đúng, **không tải OCR model lúc khởi động**, settings cũ còn nguyên |
| 2 | Mỗi engine: cài model qua API → trạng thái job → kích hoạt → test → upload PDF → xử lý xong → có văn bản tiếng Việt mong đợi → log worker xác nhận class OCR Docling; cài 1 engine không tải engine khác |
| 3 | Restart: checksum model không đổi, settings + engine đang dùng còn nguyên |
| 4 | Offline: app chỉ nối mạng `internal` (vẫn tới SurrealDB, **không** ra Internet — được kiểm tra), recreate với `OCR_OFFLINE=true HF_HUB_OFFLINE=1`: runtime khôi phục từ cache, xử lý tài liệu, HF cache + model không đổi, không có log tải |
| 5 | Build lại image thật (`--no-cache-filter runtime-base,runtime`, image ID mới), recreate: runtime khôi phục, checksum model không đổi, settings giữ nguyên, engine vẫn xử lý tài liệu |

Kết quả cuối: bảng PASS / FAIL / NOT VERIFIED; exit code ≠ 0 nếu có FAIL.

## 6. Kiểm tra API và worker thủ công (tuỳ chọn)

Khi script chạy với `KEEP_WORK=1`, có thể gọi API bên trong container app của project nghiệm thu:

```bash
APP=$(docker ps --filter "label=com.docker.compose.service=app" --filter "name=ocraccept" --format '{{.ID}}' | head -1)
docker exec "$APP" /app/.venv/bin/python -m open_notebook.ocr.cli status --no-db
docker exec "$APP" sh -c 'grep -c . /app/runtime-constraints.txt'
docker logs "$APP" 2>&1 | grep -E "Docling OCR finished|OCR model install finished|Using locked runtime constraints" | tail -20
```

## 7. Môi trường không có Internet

### 7.1 Trên máy có Internet (cùng kiến trúc CPU, ví dụ x86_64)

```bash
cd "$ACCEPT_DIR/src"
docker build --target runtime --build-arg OCR_INSTALL_TESSERACT=true -t chatbot5400:ocr-offline .
docker save chatbot5400:ocr-offline | gzip > "$ACCEPT_DIR/chatbot5400-ocr-offline.tar.gz"
mkdir -p "$ACCEPT_DIR/bundle"
docker run --rm --entrypoint /app/.venv/bin/python -v "$ACCEPT_DIR/bundle:/bundle" chatbot5400:ocr-offline -m open_notebook.ocr.cli bundle create --engines tesseract_best easyocr --out /bundle --models-only
tar czf "$ACCEPT_DIR/hf-cache.tar.gz" -C "$HF_HOME" .
sha256sum "$ACCEPT_DIR"/chatbot5400-ocr-offline.tar.gz "$ACCEPT_DIR"/hf-cache.tar.gz > "$ACCEPT_DIR/transfer.sha256"
```

Docling (`content-core[docling]`) và `easyocr` được cài lúc container khởi động từ cache uv trên
volume. Để máy offline có cache đó, khởi động image **một lần khi có Internet** với volume sẽ mang
sang (cách đơn giản nhất), hoặc dùng bundle đầy đủ (bỏ `--models-only`, chạy trong container dựng từ
cùng image) — xem `OCR_OFFLINE_INSTALLATION.md`.

### 7.2 Trên máy offline

```bash
cd "$ACCEPT_DIR"
sha256sum -c transfer.sha256
gunzip -c chatbot5400-ocr-offline.tar.gz | docker load
mkdir -p "$ACCEPT_DIR/hf-cache" && tar xzf hf-cache.tar.gz -C "$ACCEPT_DIR/hf-cache"
```

Sau đó chạy lại mục 5 với `SKIP_BUILD=1 IMAGE=chatbot5400:ocr-offline` (bước 4 kiểm tra riêng chế độ
offline; bước 5 cần build nên đánh dấu NOT VERIFIED khi không có mạng).

## 8. Benchmark thực tế

```bash
cd "$ACCEPT_DIR/src"
export OCR_DATA_DIR="$OCR_DATA"
uv run --with reportlab python scripts/ocr/generate_samples.py --out "$ACCEPT_DIR/samples"
uv run python scripts/ocr/benchmark.py --samples "$ACCEPT_DIR/samples" --mode ocr-stage --out "$ACCEPT_DIR/bench-ocr-stage.json"
uv run python scripts/ocr/benchmark.py --samples "$ACCEPT_DIR/samples" --mode pipeline --out "$ACCEPT_DIR/bench-pipeline.json"
```

Chỉ dùng tài liệu tổng hợp ở đây. Đánh giá trên tài liệu thật của ngân hàng **làm cục bộ**, không
đưa file hay kết quả có nội dung nhạy cảm lên GitHub.

## 9. Thu thập log và kết quả

```bash
cd "$ACCEPT_DIR"
mkdir -p evidence
cp -f ocr-acceptance.json docker-acceptance.log bench-*.json evidence/ 2>/dev/null || true
docker images --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.CreatedSince}}' | grep chatbot5400 > evidence/images.txt
tar czf "ocr-acceptance-evidence-$(date +%Y%m%d).tar.gz" evidence
```

## 10. Dọn dẹp và rollback

Nghiệm thu không động vào deployment đang chạy. Dọn phần nghiệm thu:

```bash
docker image rm chatbot5400:ocr-accept chatbot5400:ocr-accept-old 2>/dev/null || true
rm -rf "$ACCEPT_DIR/src" "$ACCEPT_DIR/samples"
```

Rollback deployment thật (nếu đã cập nhật lên bản OCR): xem `OCR_ROLLBACK.md` — quay về commit
`5e04227`, `docker compose -f deploy/docker-compose.prod.yml up -d --build`, **không** xoá volume.

## 11. Tiêu chí ghi nhận

| Hạng mục | Lệnh | PASS khi |
|---|---|---|
| Full pipeline (4 engine × 7 fixture) | mục 4.3 | `summary.FAIL == 0` và `NOT VERIFIED == 0` |
| Docker E2E / restart / offline / rebuild / upgrade | mục 5 | không có dòng `FAIL`, không có `NOT VERIFIED` ngoài engine cố ý bỏ |
| Benchmark | mục 8 | có số đo `--mode pipeline`; cập nhật `OCR_BENCHMARK.md` |
