# Phase 12D3 — Checklist nghiệm thu Windows Local

Thay thế `PHASE12D2_WINDOWS_ACCEPTANCE_CHECKLIST.md` cho lần nghiệm thu sau remediation (checklist D2 được giữ nguyên
làm hồ sơ audit). Bổ sung cho `docs/ocr/PHASE12E_WINDOWS_LOCAL_TEST_GUIDE.md`.

**Vì sao cần:** ở Cloud không có Docker daemon, không có PowerShell, không tải được Layout Heron / TableFormer, không
có model Agri, không có PDF nghiệp vụ. Mọi mục dưới đây là **cổng còn mở**: chưa mục nào được coi là đạt.

## Quy ước

- Mỗi mục ghi **Đạt / Không đạt / Không chạy được** kèm log. Kết quả nào khác kỳ vọng ⇒ dừng nhóm đó, ghi lại, báo
  cho bước review 12D4 — **không** sửa tiêu chí cho khớp kết quả.
- Stack thử nghiệm: compose project **`chatbot5400-phase12-test`**, web **`127.0.0.1:8504`**, API
  **`127.0.0.1:5057`**, chỉ loopback, database và thư mục riêng (`deploy/phase12-test`). **Không phải production**,
  không dùng credential production, không kết nối production.
- Công cụ Local **không tự upload** dữ liệu, **không có telemetry**. PDF nghiệp vụ và model Agri ở lại máy Local:
  không commit, không đưa lên Cloud, không dán nội dung vào issue/PR. Thư mục kết quả `diagnose`/`compare` chứa văn
  bản tài liệu ⇒ chỉ giữ cục bộ; khi báo cáo chỉ gửi số liệu (`compare.json` không chứa văn bản).
- PowerShell: chạy từ thư mục gốc repository. WSL2: Ubuntu trong WSL2 với Docker Desktop integration.

## 0. Chuẩn bị

```powershell
git fetch origin feature/legal-document-normalization
```

```powershell
git switch feature/legal-document-normalization
```

```powershell
git log -1 --format="%H %s"
```

(ghi lại commit được nghiệm thu)

```powershell
.\scripts\windows\phase12-test.ps1 check
```

```powershell
.\scripts\windows\phase12-test.ps1 init-env
```

```powershell
.\scripts\windows\phase12-test.ps1 build
```

```powershell
.\scripts\windows\phase12-test.ps1 up
```

```powershell
.\scripts\windows\phase12-test.ps1 status
```

Xác nhận chỉ nghe trên loopback:

```powershell
docker ps --filter "label=com.docker.compose.project=chatbot5400-phase12-test" --format "{{.Names}}  {{.Ports}}"
```

Kỳ vọng: mọi cổng dạng `127.0.0.1:8504->…`, `127.0.0.1:5057->…`; không có `0.0.0.0`.

Sinh PDF tổng hợp (45 tình huống, có ground truth):

```powershell
.\scripts\windows\phase12-test.ps1 fixtures
```

## 1. W-PIPE — Bộ test tự động trên máy có đủ model

```powershell
uv sync --extra docling
```

```powershell
uv run pytest tests/ -q -p no:cacheprovider
```

```powershell
uv run pytest tests/review_phase12d2 tests/test_ocr_legal_normalizer.py tests/test_offline_package.py -q -rxXs
```

WSL2 tương đương:

```bash
uv sync --extra docling && uv run pytest tests/ -q -p no:cacheprovider
```

| Mã | Kỳ vọng |
|---|---|
| W-PIPE-01 | `tests/review_phase12d2`: 32 PASS, **0 xfail, 0 xpass, 0 skip** |
| W-PIPE-02 | `tests/test_ocr_legal_normalizer.py`: toàn bộ PASS; `tests/test_offline_package.py`: toàn bộ PASS, các test chữ ký **chạy** (cần `ssh-keygen`), không SKIP |
| W-PIPE-03 | Toàn bộ backend: danh sách FAIL theo tên ⊆ 10 lỗi nền đã biết của v1.2.0 (xem `PHASE12D3_REGRESSION_REPORT.md` §2). Ở Cloud còn 3 lỗi `tests/test_chunking.py` do proxy chặn host bảng mã tiktoken — **trên máy có Internet 3 test này phải PASS** |
| W-PIPE-04 | `cd frontend; npm ci; npm run test; npx tsc --noEmit; npm run lint` — 0 lỗi |
| W-PIPE-05 | Benchmark tổng hợp trong container (có model thật): `docker compose -p chatbot5400-phase12-test exec open_notebook /app/.venv/bin/python scripts/ocr/phase12_benchmark.py --out /phase12-out/benchmark.json --pdf-dir /phase12-out/fixtures` — `legal.false_deletion_units = 0`, `false_merge = 0`, `false_insertion = 0`, `critical_fields` đủ |

## 2. W-STD — Standard không đổi so với v1.2.0

| Mã | Việc | Kỳ vọng |
|---|---|---|
| W-STD-01 | Xử lý cùng một PDF tổng hợp trên image v1.2.0 và image Phase 12, cờ Legal **tắt** | `full_text` giống nhau từng byte |
| W-STD-02 | Cờ Legal **bật**, admin chọn **Tiêu chuẩn** | Giống W-STD-01 |
| W-STD-03 | Lặp lại với từng engine: RapidOCR, Tesseract Fast, Tesseract Best, EasyOCR, Agri | Giống bản v1.2.0 cùng engine |
| W-STD-04 | OCR tắt; Force Full Page; `OCR_AUTO_FULL_PAGE_ON_WATERMARK=true` | Giống v1.2.0 |
| W-STD-05 | DOCX, ảnh PNG/JPEG, URL trang web khi Legal bật | Nội dung không đổi; trang Source ghi nhãn **Tiêu chuẩn** hoặc *Không áp dụng chuẩn hóa pháp lý, sử dụng bản tiêu chuẩn* (không bao giờ ghi "Đã chuẩn hóa") |
| W-STD-06 | Source Standard tạo bằng bản Phase 12: `GET http://127.0.0.1:5057/api/sources/{id}` | `asset` không có khóa `extraction` (bản ghi lưu giống hệt v1.2.0) |

So byte hai lần chạy (PowerShell):

```powershell
(Get-FileHash .\out-v120.txt -Algorithm SHA256).Hash -eq (Get-FileHash .\out-phase12.txt -Algorithm SHA256).Hash
```

## 3. W-RC — Xác minh nguyên nhân gốc trên pipeline thật (scan thật)

Chép PDF scan vào `deploy\phase12-test\import\` (ở lại máy Local).

```powershell
.\scripts\windows\phase12-test.ps1 diagnose -Pdf <tên file>.pdf -Engine tesseract_agri
```

```powershell
.\scripts\windows\phase12-test.ps1 compare -Pdf <thư mục con> -Engine rapidocr
```

| Mã | Câu hỏi | Cách kiểm |
|---|---|---|
| W-RC-01 | Layout Heron gắn nhãn gì cho số trang, header, footer trên **scan thật**? | `06_items.json`: đếm theo nhãn trên ≥ 20 trang. Ghi tỷ lệ `PAGE_HEADER/PAGE_FOOTER` so với `TEXT` |
| W-RC-02 | OCR có đặt chữ vào vùng PICTURE (con dấu, chữ ký)? | `12_summary.json` → `text_items_under_pictures_dropped_by_standard_export`; đọc cảnh báo `picture_without_text` |
| W-RC-03 | "Mất từ cuối trang" xảy ra ở tầng nào? | `12_summary.json` → `words_per_layer`, `page_end_words_in_standard`, `page_end_words_in_legal` |
| W-RC-04 | Docling tự ghép đoạn qua trang khi đoạn trước kết thúc bằng chữ ASCII thường / dấu phẩy / gạch nối (kể cả giữa hai cột)? | Fixture `f38_two_columns_across_pages`, `f19_hyphen_at_page_break`: bản **Standard** có ghép không. Đây là hành vi upstream, có ở cả v1.2.0 |
| W-RC-05 | Hai đường OCR (content-core Auto và lớp native) cho cùng văn bản thô? (F-15) | Standard mặc định so với Standard khi ép lớp native (số luồng OCR = 1); log có dòng cảnh báo `Legal Document mode changes the OCR path` khi Legal ép lớp native trong lúc cấu hình tương thích có vấn đề |
| W-RC-06 | **OCR trực tiếp bằng Agri** trên scan thật | `diagnose` với `-Engine tesseract_agri`: file `01_tesseract_p*.txt` đọc được; so `cer` (nếu có ground truth tự gõ, đặt cạnh PDF tên `<tên>.gt.txt`) |

## 4. W-LEG — Chất lượng Legal trên pipeline thật

Điều kiện: W-PIPE-01 đạt. Dùng PDF tổng hợp từ `fixtures` (in ra rồi scan, hoặc dùng bản `.scan.pdf`) **và** PDF scan
thật. Bật cổng rồi chọn *Văn bản pháp lý* trong OCR Engine Manager:

```powershell
.\scripts\windows\phase12-test.ps1 legal-gate -State on
```

| Mã | Tình huống | Kỳ vọng |
|---|---|---|
| W-LEG-01 | `f25` phụ lục 3 trang, mỗi trang có "Đơn vị tính: triệu đồng" (F-01) | Dòng đơn vị còn đủ **3 lần** |
| W-LEG-02 | `f26` bộ thông báo một trang: tên đơn vị ban hành, "Kính gửi", "Nơi nhận", ghi chú ký lặp lại (F-01) | Còn đủ ở **mỗi** thông báo; cảnh báo `repeated_line_kept` |
| W-LEG-03 | `f27`, `f28`, `f34` năm / số khoản / số lượng ở đầu-cuối trang (F-02) | Không số nào bị mất; cảnh báo `page_number_kept` khi có nghi ngờ |
| W-LEG-04 | `f33`, `f36` 5–6 trang có số trang thật (giữa, hoặc lẻ-chẵn hai bên) | Số trang được bỏ; khoản bị cắt qua trang được nối |
| W-LEG-05 | `f02`, `f03` văn bản **2 trang** có số trang | Số trang **được giữ**, không nối (thiếu bằng chứng — chủ ý); có cảnh báo |
| W-LEG-06 | `f29`, `f30` footnote, footer "Lưu hành nội bộ" (F-03) | Không có câu ghép footnote/footer với thân |
| W-LEG-07 | `f31_*` điểm `a.`, `a/`, `đ.`, `(a)`, `a.1)`, `đ)` qua trang (F-03) | Mỗi điểm một dòng riêng, đúng ký hiệu |
| W-LEG-08 | `f32` ảnh 5% / 12% / 20% trang, `f40` ảnh có caption và chữ OCR (F-06) | 5%: bỏ im lặng; 12%, 20%: còn `<!-- image -->` + cảnh báo có trang/bbox; caption và chữ trong ảnh còn |
| W-LEG-09 | Khoản bắt đầu từ 5, 7, 13; danh sách không liên tục; lồng 1.1 / 1.1.1 | Số hiển thị đúng như bản gốc |
| W-LEG-10 | `f38` hai cột; `f39` văn bản rồi bảng qua trang; `f35` bảng không kẻ khung lặp tiêu đề cột; trang trắng giữa; trang xoay; A3 lẫn A4 | Không nối qua cột/bảng/trang trắng; bảng giống hệt Standard |
| W-LEG-11 | PDF hỗn hợp (trang điện tử + trang scan) | Không ghép sai giữa hai loại trang |
| W-LEG-12 | **Từ cuối trang**: 10 trang scan thật, đối chiếu 3 từ cuối mỗi trang với nội dung Source | Không từ nào mất so với Standard |
| W-LEG-13 | **Header/footer thật** của văn bản nội bộ (số hiệu văn bản lặp ở đầu trang, "Trang x/y") | "Trang x/y" được bỏ khi ≥ 3 trang cùng mẫu; dòng chữ lặp lại **được giữ** kèm cảnh báo (trừ khi layout gắn nhãn PAGE_HEADER/FOOTER) |
| W-LEG-14 | PDF 300 trang nhiều đoạn cắt trang (F-10) | Dòng log `Legal normalization … in N ms`; N tăng tuyến tính theo số trang; quá 30 s ⇒ nhãn *Chuẩn hóa thất bại, sử dụng bản tiêu chuẩn* và nội dung = Standard |
| W-LEG-15 | Đổi Legal ↔ Tiêu chuẩn **trong lúc** một PDF dài đang xử lý; hai tab admin lưu khác nhau | Job đang chạy giữ chế độ lúc bắt đầu; giá trị cuối nhất quán sau tải lại và sau khi tạo lại container |
| W-LEG-16 | **Metadata Source** (F-07): `GET http://127.0.0.1:5057/api/sources/{id}` của một Source Legal | `asset.extraction` có `mode = legal`, `status = applied`, `version = 1.1.0`, `counts`, `warnings` (mã + trang), `operations` (loại + trang + SHA-256, **không** có văn bản); khởi động lại container vẫn đọc được; xóa Source ⇒ bản ghi mất theo |
| W-LEG-17 | **Giao diện** (F-16): mở Source Legal trên trình duyệt thật, cả màn hình hẹp | Nhãn *Đã chuẩn hóa văn bản pháp lý*; "Điều n" đậm; khoản / điểm / gạch đầu dòng thụt lề theo cấp; không có `\` hiển thị; không thực thi HTML |
| W-LEG-18 | Ép lỗi chuẩn hóa (đặt `TIME_BUDGET_SECONDS` rất nhỏ trong một container thử, hoặc PDF hỏng cấu trúc) | Nhãn *Chuẩn hóa thất bại, sử dụng bản tiêu chuẩn*; nội dung đúng bằng Standard |

## 5. W-RAG — Nội dung lưu, chunk, embedding, chat

| Mã | Việc | Kỳ vọng |
|---|---|---|
| W-RAG-01 | Sau khi xử lý Legal: so nội dung trang Source, API `GET /api/sources/{id}` (`full_text`), và các chunk đã embed | Cùng một văn bản; không có bản Standard trong embedding |
| W-RAG-02 | (F-17) `full_text` của Source Legal | **Không** chứa `9\.`, `\-`, `\+`, `\)`; dòng bắt đầu bằng `9. …`, `- …` nguyên văn |
| W-RAG-03 | Hỏi "khoản 9 quy định gì" ở Standard và Legal trên cùng tài liệu | Truy hồi đúng chunk ở cả hai; câu trả lời không chứa `\.` |
| W-RAG-04 | Sao chép (copy) đoạn văn từ trang Source Legal rồi dán vào trình soạn thảo | Giống `full_text` (không có `\`) |
| W-RAG-05 | Đổi chế độ rồi mở lại Source cũ | Source cũ không đổi, không tự OCR lại, không tự re-embed |
| W-RAG-06 | **Tách đoạn khi không có mạng**: chặn mạng thật (W-OFF-12) rồi tải một PDF | Job hoàn tất không treo; số chunk > 0; log không có yêu cầu tới `openaipublic.blob.core.windows.net` |
| W-RAG-07 | Ghi nhận: hệ thống **không** lưu số trang theo chunk | Không coi "trích dẫn trang" là tính năng đã có |

## 6. W-OFF — Gói cập nhật offline (Docker thật)

Build trên Windows (Docker Desktop); cập nhật trên Ubuntu/WSL2 **thử nghiệm**. **Không** chạy trên production.
Lệnh máy chủ: `docs/deployment/OFFLINE_UPDATE_UBUNTU_GUIDE.md`.

### 6.1 Build

```powershell
.\scripts\offline\build-package.ps1 -Version 1.3.0-rc.1
```

Kỳ vọng W-OFF-01a: **bị từ chối ngay** (mã 2, `VERSION of the checkout is 1.2.0`), không có lệnh `docker build` nào chạy.

```powershell
.\scripts\offline\build-package.ps1 -Version 1.2.0-phase12.1
```

WSL2:

```bash
scripts/offline/build-package.sh --version 1.2.0-phase12.1
```

| Mã | Việc | Kỳ vọng |
|---|---|---|
| W-OFF-01 | **PowerShell build** (lần chạy đầu tiên của `build-package.ps1`) và bản Bash trong WSL2 | Cả hai tạo được gói + `.sha256`; in `readiness: READY`; không dừng ở "Refusing to create empty bundle" |
| W-OFF-02 | `git for-each-ref refs/cb5400-offline` sau khi build | Rỗng (ref tạm đã xóa) |
| W-OFF-03 | Ngắt build giữa chừng (Ctrl+C trong lúc `docker save`) rồi chạy lại | Không còn thư mục `dist\offline\ChatBot5400-…-offline\`; chạy lại thành công |
| W-OFF-04 | `docker info --format '{{.Driver}} {{.DriverStatus}}'` trên máy build và máy chủ thử | Ghi loại image store của hai bên |
| W-OFF-05 | **`docker save` / `docker load` thật** (F-20): `docker image inspect --format '{{.Id}}' chatbot5400:1.2.0-phase12.1` trên máy build; sau `update --apply` xem `journal.json` → `steps[0].identified_by` và `expected_image_id` | Ghi lại ID hai bên; công cụ nhận diện được image (`image id`, `config digest` hoặc `layer digests`) — **không** từ chối gói hợp lệ |
| W-OFF-06 | Đọc file image thật: `python scripts\offline\offline_package.py verify <gói> --extract-to $env:TEMP\cb5400-verify --expected-sha256 <SHA> --platform linux/amd64` | `VERIFIED`; `manifest.json` → `image.archive_layout` ghi `docker-archive` hoặc `oci` (ghi lại giá trị thật) |
| W-OFF-07 | (F-25) tạo archive 2 tag `docker save -o two.tar chatbot5400:1.2.0-phase12.1 surrealdb/surrealdb:v2`, thay vào bản sao gói, cập nhật manifest cho khớp checksum | `verify` từ chối: `only [...] is approved by the manifest` |
| W-OFF-08 | Trong image: `docker run --rm --network none --entrypoint /app/.venv/bin/python chatbot5400:1.2.0-phase12.1 -c "import tiktoken; print(len(tiktoken.get_encoding('o200k_base').encode('kiểm tra')))"` | In ra một số trong < 5 giây |
| W-OFF-09 | **Chữ ký gói** (khóa thử, tạo riêng cho bài test, không phải khóa phát hành): `ssh-keygen -t ed25519 -f $HOME\.ssh\cb5400_test`; build với `-SignKey`; cài khóa công khai vào `allowed_signers` của máy thử | `verify` không cần `--expected-sha256`: `authenticity: ["signature valid"]`; sửa 1 byte bất kỳ file nào ⇒ từ chối, **không** còn thư mục giải nén; khóa khác ⇒ `INVALID signature` |

### 6.2 Cập nhật trên máy chủ thử (Ubuntu / WSL2)

| Mã | Việc | Kỳ vọng |
|---|---|---|
| W-OFF-10 | `verify-package.sh` không có `--expected-sha256` và không có khóa | Từ chối; thư mục `--extract-to` **không tồn tại** |
| W-OFF-11 | Chuỗi đầy đủ: verify → preflight → update (dry-run) → update `--apply` → nghiệm thu → `finish --approve` | Mỗi bước mã 0; `journal.json`: `status: completed`, có `attempt_id`, `baseline`, `expected_image_id` |
| W-OFF-12 | Chặn mạng thật: `sudo iptables -I DOCKER-USER -j DROP`; `healthcheck.sh --prove-offline`; xử lý PDF với từng engine đã cài; gỡ: `sudo iptables -D DOCKER-USER -j DROP` | `outbound network blocked`; OCR chạy, không treo |
| W-OFF-13 | (F-21) Trước và sau **mỗi** bước của W-OFF-11: `docker inspect <container DB> --format '{{.Id}} {{.Image}} {{.State.StartedAt}}'` và số Source/Notebook | Không đổi; log bước O có `database container unchanged`, `row counts unchanged` |
| W-OFF-14 | (F-11) Sau `finish`: `status.sh` → 0. Chạy `docker compose -p <PROJECT> -f docker-compose.yml up -d` trong thư mục triển khai thử. `status.sh`, `healthcheck.sh` | Ghi nhận container có về image cũ không; nếu có: `IMAGE DRIFT`, **mã thoát 7**. Chạy lệnh trong `compose-command.txt` ⇒ `status.sh` = 0 |
| W-OFF-15 | **Ghim image bền vững**: `pin.sh` (dry-run) → `pin.sh --apply` → `docker compose … up -d` thường → **khởi động lại Docker / reboot máy thử** → `status.sh` | Dry-run không đổi gì; sau `--apply` container vẫn ở **image mới** qua `up -d`, restart, reboot; `.env` và file compose có sẵn **không** bị sửa; `status.sh` báo `ENVIRONMENT DRIFT` cho tới khi người vận hành thêm dòng `COMPOSE_FILE` đã in, sau đó = 0. Ghi lại tên image mà Compose thật dùng cho dịch vụ `build:` (kỳ vọng `<project>-<service>`); nếu công cụ từ chối ghim vì tên không khớp ⇒ ghi thông báo |
| W-OFF-16 | `pin.sh --undo`; và `rollback.sh app` sau khi đã ghim | Tên image của triển khai trỏ về image trước cập nhật; `up -d` thường ⇒ image cũ |
| W-OFF-17 | **Cập nhật lần hai với backup mới** (F-08): update `--apply` → `rollback.sh app` → thêm 1 Source → update `--apply` lại (cùng gói), `BACKUP_CMD` ghi một dòng vào file log thử | Hai dòng backup; `attempt_id` khác; `STATE_DIR/journals/` có journal lần một; tag `rollback-…` khác |
| W-OFF-18 | completed → build gói tiếp theo (`-Version 1.2.0-phase12.2`) → update | Attempt mới, backup mới; rollback của lần hai về image `…phase12.1`, không về v1.2.0 |
| W-OFF-19 | (F-09) Trong lúc `awaiting_approval`, làm hỏng health (đổi `HEALTH_URL` sang cổng không nghe) rồi `finish --approve` | Mã 5, `status: finish_failed`, **không** `completed`; sửa lại rồi `finish` ⇒ `completed` |
| W-OFF-20 | (F-13) `kill -9` tiến trình update ngay trong lúc `compose up`; cắt ngắn `journal.json` (`truncate -s 40`); chạy hai update song song; gọi rollback hai lần | `status.sh` báo journal hỏng + hướng dẫn, không traceback, **không** tự tạo journal mới; chép `journal.json.bak` đè lên ⇒ hoạt động lại; update song song ⇒ mã 6 |
| W-OFF-21 | (F-22) Máy chủ thử **chưa từng** dùng RapidOCR: update `--apply` | Dừng trước khi tạo lại container với thông báo RapidOCR; thêm `--accept-missing-rapidocr` ⇒ tiếp tục; journal bước `RAPIDOCR_weights` có `ok: false` |
| W-OFF-22 | (F-22) Journal bước `ARTIFACTS_snapshot` và log bước O | Số file `ocr_models`, `huggingface_hub` > 0; `model files on the data volume unchanged` |
| W-OFF-23 | (F-23) Đang chạy bình thường: `rollback.sh legal-on`, rồi `legal-off` | Container vẫn ở chế độ bình thường (cổng như cũ); đang bảo trì thì vẫn bảo trì |
| W-OFF-24 | (F-26d) `export http_proxy=http://127.0.0.1:9` trong shell root rồi `healthcheck.sh` | Vẫn đạt |
| W-OFF-25 | (F-26c) `chmod 666 /etc/chatbot5400/offline-update.conf` trên máy thử | Mọi lệnh từ chối (mã 2); `chmod 640` ⇒ hoạt động lại |
| W-OFF-26 | (F-05) `<DEPLOY>` là git checkout ở v1.2.0: update `--apply --sync-source`; sau đó `rollback.sh app` | Checkout tới commit của gói bằng fast-forward; `.env` nguyên; rollback đưa checkout về commit cũ. Lặp lại với một commit cục bộ ⇒ từ chối, checkout nguyên; với thay đổi cục bộ xung đột ⇒ từ chối, file nguyên |
| W-OFF-27 | **Rollback về v1.2.0** khi DB đã lưu `ocr_text_normalization=legal` và có Source Legal (có `asset.extraction`) | Bản 1.2.0 khởi động, health đạt, cài đặt OCR mở được, Source Legal mở được và giữ nguyên nội dung, không OCR lại; `status.sh` = 0 (`rolled_back`) |
| W-OFF-28 | `ENABLE_CRAWL4AI=true` không có `CRAWL4AI_API_URL` trên máy offline | Ghi thời gian khởi động và log entrypoint |
| W-OFF-29 | Sau `update --apply` (đang bảo trì): tải 1 PDF thử, **khởi động lại Docker / reboot máy thử**, rồi `finish --approve` | `finish` đạt (`completed`): tài liệu nghiệm thu và reboot không bị báo là hư hại; log có `row counts before …, now … (normal mode: informational)` và `database container unchanged` |
| W-OFF-30 | Dừng update trước khi tạo lại container (ví dụ `BACKUP_VERIFY_CMD=false`), ghi `docker inspect <container ứng dụng> --format '{{.Id}} {{.State.StartedAt}}'`, chạy `rollback.sh interrupted`, ghi lại lần nữa | Mã 0, `rolled_back`; ID và `StartedAt` của container ứng dụng **không đổi** (không bị khởi động lại). Lặp lại với `--sync-source`: chạy lại `update` bị từ chối cho tới khi `rollback.sh interrupted`; checkout về commit cũ |
| W-OFF-31 | `ls -ld <STATE_DIR>`; `ls -l <STATE_DIR>` | thư mục `drwx------`, file journal / override `-rw-------` |

## 7. Biên bản

| Nhóm | Đạt | Không đạt | Không chạy được | Ghi chú |
|---|---|---|---|---|
| W-PIPE | | | | |
| W-STD | | | | |
| W-RC | | | | |
| W-LEG | | | | |
| W-RAG | | | | |
| W-OFF | | | | |

Quy tắc kết luận:

- "REAL DOCKER BUILD: VERIFIED" chỉ khi W-OFF-01..09 đạt.
- "REAL OCR PIPELINE: VERIFIED" chỉ khi W-RC và W-LEG đạt trên scan thật.
- "OFFLINE UPGRADE AND ROLLBACK: VERIFIED" chỉ khi W-OFF-10..27 và W-OFF-29..31 đạt.
- Bất kỳ mục **Không đạt** nào ở W-STD, W-LEG-01..08, W-OFF-11..20, W-OFF-27, W-OFF-29 là **release blocker**.
- Checklist này không thay cho review độc lập Phase 12D4 và không cho phép phát hành RC hay triển khai production.
