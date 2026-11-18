# Phase 12D7 — Danh sách kiểm lại trên Windows Local (bản ứng viên 12D7)

Thực hiện trên máy Windows của 12E0 / 12E1, stack thử nghiệm `chatbot5400-phase12-test`
([hướng dẫn](../ocr/PHASE12E_WINDOWS_LOCAL_TEST_GUIDE.md)). **Không** dùng production, database production hay tài
khoản thật. Không upload PDF, kết quả OCR, ảnh vùng hay model Agri. Kết quả chứa nội dung tài liệu ⇒ chỉ giữ trên máy;
báo cáo gửi đi chỉ ghi số liệu / mã kết quả (dùng `-NoText` khi cần).

Phân biệt khi điền: **ĐẠT** (đã chạy, đúng kỳ vọng) / **KHÔNG ĐẠT** (kèm mã finding mới) / **KHÔNG CHẠY** (lý do).
Không kết luận Agri chính xác hơn chỉ vì confidence cao hơn hay giống Direct OCR hơn.

## 0. Chuẩn bị — giữ mốc so sánh

| # | Việc | Kỳ vọng | Kết quả |
|---|---|---|---|
| W-12D7-00a | Ghi lại image ID của v1.2.0 và của ứng viên 12D5 `904c15c` (`docker image ls --no-trunc`) | còn nguyên, **không xóa** image / volume nào | ☐ |
| W-12D7-00b | `git fetch origin feature/legal-document-normalization` → checkout đầu nhánh 12D7; ghi commit | commit = đầu nhánh trong PR #50 | ☐ |
| W-12D7-00c | `git ls-files --eol open_notebook/ocr/tesseract_gate.py` **trước và sau** khi pull | ghi lại `w/crlf` hay `w/lf`. Checkout **đã có** vẫn có thể hiện `w/crlf` sau pull — bình thường, chỉ checkout mới / file được ghi lại mới hiện `w/lf` (Phase 12D9, D8-ORI-03); image build từ đó vẫn đúng nhờ bước chuẩn hóa của Dockerfile | ☐ |
| W-12D7-00d | `.\scripts\windows\phase12-test.ps1 build` rồi `restart-app` | build đạt (bước tự kiểm cổng trong Dockerfile) | ☐ |

## 1. E1-05 — cổng hướng xoay (xác nhận nguyên nhân rồi kiểm sửa)

| # | Việc | Kỳ vọng | Kết quả |
|---|---|---|---|
| W-12D7-01a | Trên image **cũ** 12E1 (nếu còn): `docker compose -p chatbot5400-phase12-test -f deploy\phase12-test\docker-compose.yml exec -T open_notebook sh -c "head -c 40 /app/open_notebook/ocr/tesseract_gate.py \| od -c"` và tìm `runs without orientation gating` trong `logs` | có `\r` và/hoặc có dòng log ⇒ chỉ xác nhận **"cổng đã tắt"** trên image đó (Phase 12D9, D8-ORI-04: không chứng minh 11 cụm bị xoay vì thế — 12E2 cho thấy OSD của chúng là 0°); không có ⇒ ghi lại, nguyên nhân khác (W-12D7-01d) | ☐ |
| W-12D7-01b | Image mới: `.\scripts\windows\phase12-test.ps1 status` | dòng cuối `orientation gate: active (min confidence 2.0)` | ☐ |
| W-12D7-01c | `orientation -Pdf <tài liệu> -Engine tesseract_best -Suspect '<trang>:<l>,<t>,<r>,<b>'` cho **11 cụm nghi ngờ** (trang / bbox từ `03_layout_clusters.json`) | mỗi cụm: `rotated` rỗng, hoặc góc xoay có `raw_confidence ≥ 2.0` và chữ đọc được đúng | ☐ |
| W-12D7-01d | Nếu vẫn còn vùng xoay sai với độ tin cậy ≥ 2.0 | ghi finding mới kèm `orientation_summary.json` (`-NoText`); **không** đổi ngưỡng khi chưa có benchmark | ☐ |
| W-12D7-01e | Chữ của 11 cụm trong Standard / Legal sau khi build lại | không còn chữ rác do xoay | ☐ |

## 2. E0-07 — số do Tesseract nhận dạng

| # | Việc | Kỳ vọng | Kết quả |
|---|---|---|---|
| W-12D7-02a | Trong container: `/app/.venv/bin/python -c "from open_notebook.ocr import docling_patches as p; p.apply(); print(p.status())"` | `applied: True`, `docling: 2.129.0`, `problems: []` | ☐ |
| W-12D7-02b | `diagnose` 22 PDF với **Tesseract Best**, **Agri v1**, **Agri v2**: so token trong `01_tesseract_pXXX.tsv` (Direct OCR, TSV thô) với `02_ocr_cells.json` | mọi token của TSV có trong ô OCR **đúng nguyên văn** (`0001`, năm, số khoản `9.`, `NA`…) | ☐ |
| W-12D7-02c | Fixture tổng hợp (`fixtures`, rồi `compare` trên `d5_f02_voucher_numbers_alone_top_right`, `d5_f02_reporting_periods_alone_bottom_centre`, `d5_f02_numbers_inside_the_body`, `d5_f02_true_page_numbers_*`, `f08_protected_fields` `.scan.pdf`) | số chỉ-một-mình đúng như ground truth; không còn `1.0`, `2024.0` | ☐ |
| W-12D7-02d | Nếu `9.` (hoặc token khác) có ở TSV và ô OCR nhưng mất ở nội dung lưu | ghi **finding riêng** (tầng layout / serializer) | ☐ |
| W-12D7-02e | Standard expected-diff: xuất Standard của 22 PDF bằng image v1.2.0 và image mới (cùng engine), chạy `python scripts/ocr/phase12_standard_diff.py --before <v120> --after <mới> --tsv <thư mục TSV của diagnose> --out <báo cáo>` | `unexpected regression` = 0; mọi khác biệt là `expected parser fix` có TSV; `not verified` được giải thích | ☐ |
| W-12D7-02f | RapidOCR và EasyOCR trên cùng tài liệu: Standard image mới vs v1.2.0 | **giống hệt từng byte** | ☐ |

## 3. E1-03 / E1-09 — Legal

| # | Việc | Kỳ vọng | Kết quả |
|---|---|---|---|
| W-12D7-03a | Legal trên 22 PDF: số trang, số chứng từ, số văn bản, kỳ báo cáo, số Điều / Khoản | đúng như bản giấy; không còn `1.0` / `2.0`; số trang được bỏ chỉ khi đủ bằng chứng | ☐ |
| W-12D7-03b | Các phản ví dụ scan thật của E1-09 / F-03 (4 trường hợp 12E1) | không đoạn nào nối hai trang; chỗ Docling đã nối được tách (`upstream_merge_undone` trong `09_legal_report.json`) hoặc giữ kèm `upstream_merge_kept` | ☐ |
| W-12D7-03c | `09_legal_report.json` của 22 PDF | không có `join_across_pages`; số từ Legal ≥ số từ Standard trừ phần tử đã bỏ có lý do | ☐ |
| W-12D7-03d | Giao diện: mô tả chế độ Văn bản pháp lý (vi / en) | không còn hứa sửa đoạn bị ngắt do phân trang | ☐ |
| W-12D7-03e | Rollback Legal → Standard (`legal-gate -State off`) | trả về dấu nhắc ngay (E0-05), nội dung Standard | ☐ |

## 4. E1-04 — build gói offline trên Windows

| # | Việc | Kỳ vọng | Kết quả |
|---|---|---|---|
| W-12D7-04a | **Windows PowerShell 5.1**: `.\scripts\offline\build-package.ps1 -Version 1.2.0-phase12.N` | build đạt, in SHA-256 và `readiness: READY` | ☐ |
| W-12D7-04b | **PowerShell 7**: cùng lệnh (phiên bản `N+1` hoặc `-NoBuild`, xóa thư mục dựng cũ) | đạt | ☐ |
| W-12D7-04c | Hai cửa sổ chạy cùng tên gói cùng lúc | cửa sổ thứ hai bị từ chối ngay, thông báo nêu file khóa và PID | ☐ |
| W-12D7-04d | Đóng cửa sổ đang build (giữa `docker save`) rồi build lại | gói tốt trước đó + `.sha256` còn nguyên; lần sau báo thư mục dựng dở, xóa nó thì build được | ☐ |
| W-12D7-04e | `python -m pytest tests\test_phase12d7_build_lock.py -q` bằng Python Windows | các test khóa đạt (nhánh `msvcrt`); test build bỏ qua | ☐ |
| W-12D7-04f | `manifest.json` trong gói (`Format-Hex` vài dòng đầu) | không có `0D 0A` | ☐ |
| W-12D7-04g | Trên máy Ubuntu thử nghiệm: `verify-package.sh` gói build từ Windows | xác thực đạt; `runtime_artifacts.docling_tsv_patch.applied: true` | ☐ |

## 5. E0-05 — `phase12-test.ps1`

| # | Việc (PowerShell 5.1 **và** 7) | Kỳ vọng | Kết quả |
|---|---|---|---|
| W-12D7-05a | `up` | trả dấu nhắc ngay, container chạy nền | ☐ |
| W-12D7-05b | `legal-gate -State off`, `legal-gate -State on`, `restart-app` | trả dấu nhắc; chỉ container ứng dụng được tạo lại: ID container `surrealdb` (`docker compose … ps -q surrealdb`) **không đổi** | ☐ |
| W-12D7-05c | `docker volume ls` và thư mục `deploy\phase12-test\{surreal_data,notebook_data}` trước / sau | không đổi | ☐ |
| W-12D7-05d | `status`, `logs`, `agri-status`, `import-agri`, `activate-agri`, `fixtures`, `compare`, `diagnose`, `orientation`, `build`, `stop` | chạy như trước; không kéo image ngoài dự kiến | ☐ |

## 6. Không đổi (kiểm nhanh)

| # | Việc | Kỳ vọng | Kết quả |
|---|---|---|---|
| W-12D7-06a | Auto Full Page on Watermark (`.watermark.pdf` của fixture) | quyết định chế độ như 12D5 | ☐ |
| W-12D7-06b | Custom Model Manager: import / kích hoạt / rollback Agri v1 ↔ v2 | như 12D5; model không bị sửa (SHA-256 khớp) | ☐ |
| W-12D7-06c | Tokenizer offline (`health` của gói) | `o200k_base` nạp được không mạng | ☐ |
| W-12D7-06d | PDF Prep (trang scan xoay ngang / ngược) | như 12D5 | ☐ |

Mục của 12D5 ([PHASE12D5_LOCAL_ACCEPTANCE_CHECKLIST.md](PHASE12D5_LOCAL_ACCEPTANCE_CHECKLIST.md)) vẫn còn hiệu lực;
danh sách này chỉ thêm các mục của 12D7.
