# Báo cáo Phase 9B — Nghiệm thu phát hành cuối, Pull Request và merge

Ngày: 2026-11-13 → 2026-11-14 · Máy nghiệm thu: Ubuntu Server 26.04, 8 CPU, 30 GB RAM, không GPU
Branch phát hành: `release/ocr-engine-manager-rc1` → nhánh chính thức `claude/practical-wozniak-9s1t6z`

Phase 9B không phát triển OCR thêm. Việc đã làm: xác minh lại Phase 9A, review độc lập toàn bộ thay đổi, sửa các
lỗi mức Cao / Trung bình tìm được, chạy lại toàn bộ nghiệm thu trên commit sẽ merge, mở Pull Request và merge.
Production **không** bị thay đổi trong Phase 9B.

## Kết luận

| Trạng thái | Kết luận |
|---|---|
| Phase 9A | **COMPLETED AND VERIFIED** (mục A) |
| Phase 9B | **Nghiệm thu hoàn tất, Pull Request #42 đã mở.** Cổng merge: đạt (mục G); một điểm mức Trung bình có sẵn được nêu để chủ dự án quyết định (route podcast, mục B.3 #1) |
| Merge | Thực hiện sau khi check của PR #42 đạt, bằng merge commit. Commit merge không thể nằm trong chính nội dung được merge: nó được ghi trong `OCR_FINAL_ACCEPTANCE.md` / `CHECKPOINT.md` ở PR tài liệu bàn giao |
| Production | **NOT DEPLOYED** trong Phase 9B. Kiểm tra chỉ đọc đã xong; triển khai chờ phê duyệt ở Phase 9C |

## A. Xác minh Phase 9A

| Kiểm tra | Kết quả |
|---|---|
| `origin/release/ocr-engine-manager-rc1` | `76b63b553c18837c6c9d28375df0191c8a3ff400` — đúng commit RC đã push |
| `origin/claude/practical-wozniak-9s1t6z` (nhánh chính thức, cũng là default branch) | `5e042279439302d3ccf39bef4d1d8d402314d194` — không có commit mới |
| Quan hệ | RC đi trước 37 commit, đi sau 0; merge-base = `5e04227` |
| GitHub | `gh` đã xác thực, quyền ADMIN; repository PUBLIC; không có branch protection, ruleset, webhook, environment, self-hosted runner; chưa có PR nào cho branch RC |
| Bundle | `phase9a-backup.bundle` — `git bundle verify` đạt, chứa `release/ocr-engine-manager-rc1`; các bundle 8B / 8C / 8D còn nguyên |
| Tài liệu | Đã đọc 15 tài liệu được yêu cầu (báo cáo 8C / 8D / 9A, RC, checklist, test report, benchmark, kế hoạch và checklist production, benchmark tài liệu thật, online preparation, rollback, checkpoint, decisions, background job security) |
| Production | Cùng container ID, image, thời điểm start (2026-11-12 14:41 UTC), restart 0, `/health` 200 như cuối Phase 9A |

## B. Review độc lập

Ba agent độc lập, chỉ đọc, trên `git diff 5e04227..76b63b5` (và `45e2254..76b63b5`), mỗi agent một phạm vi:
(A) đường xử lý tài liệu và đồng thời; (B) bảo mật; (C) cài đặt, readiness, Docker, cơ sở dữ liệu, frontend.
Sau khi sửa, một agent thứ tư rà lại riêng phần sửa (`76b63b5..d28300e`): **0 Cao, 0 Trung bình**, 13 Thấp /
Thông tin (mục B.2, B.3). Từng phát hiện mức Cao / Trung bình được kiểm chứng lại trong mã trước khi sửa.

### B.1 Mức Cao và Trung bình

| ID | Mức | Phát hiện | Nguồn gốc | Xử lý |
|---|---|---|---|---|
| P1 | **Cao** | Route `/api/credentials/*` và `/api/models/*` không kiểm tra vai trò: tài khoản bất kỳ sửa được `base_url` của credential (khóa API đang lưu và lưu lượng chat bị gửi sang máy khác) và dùng "kiểm tra kết nối" để dò địa chỉ nội bộ bất kể công tắc URL ingestion | Có sẵn ở `5e04227` | **Đã sửa** `d4b5f81` — `require_admin` (D-31); 101 test |
| P2 | **Cao** | `POST /api/sources/json` nhận `file_path` bất kỳ trong thư mục uploads: cộng tác viên đọc / xóa được file của người khác, kể cả bài chờ duyệt | Có sẵn | **Đã sửa** `d4b5f81` — người không phải quản trị viên phải tải file kèm request |
| P3 | Trung bình | Các route ghi của transformation, embed, dựng lại embedding, xóa insight, podcast, hồ sơ podcast không kiểm tra vai trò | Có sẵn | **Đã sửa một phần** `d4b5f81`: những route mà giao diện chỉ hiện cho quản trị viên. **Còn mở:** các route podcast (mục B.3) |
| A1 | Trung bình | Bước dò hướng trang không có giới hạn tổng thời gian: 200 trang × 30 s ≈ 100 phút trước khi Docling chạy, worker không có timeout | Phase 8C | **Đã sửa** `d28300e` — ngân sách 600 s (D-30), mục C |
| A2 | Trung bình | Docling trả `PARTIAL_SUCCESS` không ném lỗi; nguồn được lưu "hoàn tất" dù thiếu trang / vùng, không dấu vết | Có sẵn (cùng hành vi ở đường Content Core) | **Đã sửa** `d28300e` — cảnh báo trong log + `conversion_status`, `conversion_errors` trong metadata; kết quả không đổi (D-32) |
| M1 | Trung bình | `OCR_RAPIDOCR_PERSISTENT=true` với backend torch không giữ file từ điển của RapidOCR; sau recreate offline tài liệu lỗi trong khi readiness vẫn báo `offline_ready` | Phase 8B | **Giảm thiểu** `d28300e`: file từ điển vào fingerprint ⇒ readiness về "chưa kiểm tra" thay vì báo sai; tài liệu đã sửa. Giới hạn còn lại: cần "Chuẩn bị" một lần khi có Internet sau mỗi lần recreate (mục H) |
| M2 | Trung bình | Build arg `OCR_INSTALL_TESSERACT` không nằm trong compose: `up -d --build` sau này dựng image thiếu Tesseract | Phase 2 | **Đã sửa** `d28300e` — `build.args` trong hai file compose, đọc từ `.env` |
| M3 | Trung bình (chủ ý) | URL ingestion tắt mặc định là thay đổi hành vi | Phase 9A, D-29 | Không sửa mã — đã ghi trong CHANGELOG, kế hoạch triển khai, ghi chú phát hành |

### B.2 Mức Thấp đã sửa trong cùng đợt

Từ ba review đầu (`d28300e`): `page.get_size()` nằm ngoài khóa pdfium; tài liệu có thể được đóng ngoài khóa; một
trang không nạp được làm mất kết quả các trang khác; `OCR_HF_HUB_TIMEOUT` nhận `inf` / giá trị rất lớn;
`OCR_READINESS_TIMEOUT` sai định dạng làm lỗi lúc import (API và worker không xử lý được nguồn); công cụ
benchmark cục bộ in tên file tài liệu qua log của thư viện; trang vượt giới hạn số trang bị bỏ qua không dấu
vết; chú thích sai về luồng đồng thời.

Từ review lại phần sửa (`6f6b424`): nút "Embed" trong cảnh báo ở trang chi tiết nguồn còn hiện với người không
phải quản trị viên (bấm sẽ nhận 403 sau P3); `GET /api/models/discover/{provider}` chưa kiểm tra vai trò; công
cụ benchmark đọc file ground truth ngoài khối `try` (file không đọc được ⇒ traceback có tên tài liệu); test của
công cụ đó có thể đạt một cách rỗng khi chạy cả bộ và để lại sink loguru hỏng cho các test sau;
`OCR_PAGE_OSD_MAX_PAGES=0` bị báo như một giới hạn và ghi cảnh báo cho mọi tài liệu; `OCR_READINESS_TIMEOUT`
quá lớn làm tràn số.

### B.3 Còn tồn tại (đã ghi nhận, không chặn phát hành)

| # | Mức | Nội dung | Ghi chú |
|---|---|---|---|
| 1 | Trung bình — **cần chủ dự án quyết định** | Route podcast (tạo, thử lại, xóa tập; hồ sơ tập / người nói) mở cho mọi tài khoản đăng nhập | Có sẵn. Trang Podcast nằm ở mục "Tạo" hiển thị cho mọi người dùng, nên đây có thể là chủ ý sản phẩm; hạn chế lại là thay đổi chức năng, không tự làm. Tác động: người dùng thường tạo được podcast (tốn LLM / TTS), xóa tập, sửa hồ sơ |
| 2 | Thấp | `GET /api/podcasts/jobs/{id}` trả trạng thái và lỗi của một job bất kỳ cho mọi tài khoản | id ngẫu nhiên; id job OCR chỉ hiện cho quản trị viên |
| 3 | Thấp | Lỗi tạm thời của Hugging Face / modelscope khi đang online bị coi là "thiếu model, không có Internet" ⇒ job thất bại không thử lại | Xử lý lại nguồn là xong |
| 4 | Thấp | Không thử lại với file gốc nếu Docling lỗi trên bản sao đã sửa hướng; chưa có trường hợp thực tế | `OCR_PDF_PREP=false` là lối thoát |
| 5 | Thấp | Thư mục tạm `ocr-prep-*` không được dọn nếu tiến trình bị kill giữa chừng (mất khi tạo lại container) | Script kiểm tra sức khỏe có đếm |
| 6 | Thấp | Scale OCR giảm theo độ phân giải scan áp cho cả vùng ảnh trên trang không phải scan (chỉ Tesseract) | Giới hạn đã mô tả |
| 7 | Thấp | Readiness kiểm bằng ảnh mẫu, không gồm model công thức / mô tả hình; fingerprint không gồm phiên bản mã ứng dụng | Hai tính năng đó tắt mặc định |
| 8 | Thấp | Cài runtime online ghim phiên bản, không ghim hash; wheel stage ngoài danh sách checksum không bị từ chối; cache SHA-256 theo (đường dẫn, kích thước, mtime) | Cần quyền ghi vào data volume hoặc kho gói bị xâm nhập |
| 9 | Thấp | Trạng thái cài đặt kẹt "downloading" tối đa 15 phút khi cài từ "Chuẩn bị" thất bại; nonce của "Kiểm tra" không được dọn khi worker bị kill; hộp thoại kiểm tra không coi `canceled` là kết thúc; cập nhật manifest không khóa | Tự hồi phục theo timeout |
| 10 | Thấp | Upload xử lý đồng bộ (`async_processing=false`) chiếm worker tối đa 300 s; không hạn mức theo người dùng | Có sẵn |
| 11 | Thấp | `Source.delete()` xóa file theo đường dẫn lưu trong nguồn mà không kiểm tra lại thư mục uploads | Sau P2, đường dẫn chỉ đến từ upload của máy chủ hoặc quản trị viên |
| 13 | Thấp — không ổn định, có sẵn | Tạo nhiều nguồn **cùng một thời điểm** có thể làm một request `POST /api/sources` nhận HTTP 500 (SurrealDB v2 báo xung đột giao dịch "can be retried"); đường API không tự thử lại | Gặp 1 lần trong kiểm tra đồng thời của Phase 9B, chạy lại đạt 6/6. Tầng DB và luồng tạo nguồn không đổi kể từ `5e04227`; các lệnh nền đã có cơ chế thử lại cho cùng lỗi này. Người dùng tải lại file bị lỗi; không mất dữ liệu |
| 12 | Thông tin | JWT 12 giờ không trạng thái: hạ quyền / khóa tài khoản không có hiệu lực tức thì; tài khoản `admin/admin` được tạo trên DB trống | Có sẵn; checklist yêu cầu xác nhận đã đổi mật khẩu |

### B.4 Kết luận của review về các điểm cần kiểm theo yêu cầu

- **Lách công tắc URL ingestion:** không tìm thấy ở API, retry, worker, graph, lớp OCR; công tắc đọc ở mỗi lần
  gọi, không API nào ghi được; LLM, embedding, chuẩn bị model không đọc công tắc. Lỗ hổng duy nhất liên quan là
  P1 (ngoài chức năng nguồn), đã sửa.
- **Phân quyền endpoint mới:** mọi route `/api/ocr/*` và `/api/commands/*` đều `require_admin`.
- **Khóa pdfium:** mọi lời gọi pypdfium2 nằm trong `pdf_prep.py`; sau khi sửa, tất cả giữ khóa của Docling
  (test dò từng lời gọi); khóa không giữ trong lúc chạy Tesseract.
- **File tạm:** thư mục riêng `0700`, xóa ở mọi đường thoát bình thường và khi lỗi; file gốc không bị sửa.
- **Subprocess:** không `shell=True`; tham số dạng danh sách; binary từ cấu hình vận hành; có timeout cho OSD.
- **Dependency lock:** `uv lock --check` đạt; Docling 2.129.0, Content Core 2.0.7, RapidOCR 3.9.2, EasyOCR 1.7.2,
  torch 2.14.0 ghim trong lock và constraints; lệch ⇒ `incompatible`.
- **Tương thích cơ sở dữ liệu:** không migration, không đổi dạng bản ghi; bốn trường tùy chọn mới có mặc định;
  bản cũ bỏ qua chúng ⇒ rollback mã an toàn.
- **Frontend:** khóa i18n en-US / vi-VN trùng nhau; kiểu dữ liệu khớp backend; trạng thái chưa biết ⇒ tab URL tắt.

## C. Thời gian dò hướng PDF (yêu cầu 9B.3)

| | Trước | Sau (D-30) |
|---|---|---|
| Giới hạn số trang | 200 trang scan (`OCR_PAGE_OSD_MAX_PAGES`) | không đổi |
| Timeout mỗi trang | 30 s | không đổi |
| Tổng thời gian bước | không giới hạn ⇒ tối đa ≈ 100 phút | **600 s** (`OCR_PAGE_OSD_BUDGET_SECONDS`) + trang đang kiểm ⇒ tối đa ≈ 10,5 phút |
| Timeout toàn tài liệu / worker | không có (surreal-commands không có timeout job; Docling `document_timeout` không đặt) | không đổi — ngoài phạm vi tối thiểu |
| Khi chạm giới hạn | trang còn lại bị bỏ qua không dấu vết | trang còn lại chuyển đổi nguyên trạng; tài liệu không lỗi; log + metadata `page_orientation_limit`, `orientation_checked_pages` |
| File gốc | không sửa | không sửa |

Căn cứ thực nghiệm (máy nghiệm thu, 5 fixture scan): 0,54–0,65 giây mỗi lần gọi OSD, 0,66–0,78 giây mỗi trang
kể cả render ⇒ 200 trang ≈ 2,5 phút. 600 s gấp khoảng 4 lần nhu cầu bình thường, nên chất lượng OCR không đổi
trong điều kiện bình thường; ngân sách chỉ có tác dụng khi bước này chậm bất thường. PDF hỏng / có mật khẩu:
bước chuẩn bị bị bỏ qua kèm cảnh báo, Docling xử lý file gốc như trước. Nhiều job đồng thời: worker xử lý tuần
tự; lời gọi pdfium dùng chung khóa với Docling. Dọn file tạm: đạt ở mọi đường thoát (kiểm trực tiếp, mục E).

## D. Thay đổi mã trong Phase 9B

| Commit | Nội dung |
|---|---|
| `d4b5f81` | `fix(security)`: `require_admin` cho credential, model, transformation, embed, rebuild, xóa insight; chặn `file_path` do người gọi đưa vào với vai trò không phải quản trị viên; `tests/test_admin_route_authorization.py` |
| `d28300e` | `fix(ocr)`: ngân sách thời gian dò hướng, khóa pdfium, timeout Hub, `OCR_READINESS_TIMEOUT`, từ điển RapidOCR trong fingerprint, cảnh báo chuyển đổi một phần, build arg trong compose, công cụ benchmark tắt log; test đi kèm |
| `6f6b424` | `fix`: các điểm Thấp từ review lại (mục B.2); `scripts/ocr/production_health_check.sh`; CHANGELOG |
| commit tài liệu (HEAD của branch khi mở PR) | tài liệu Phase 9B / 9C, script kiểm tra sức khỏe production |

Không đổi: engine, model, ngưỡng, 48 bài gốc, fixture, ground truth, `pyproject.toml`, `uv.lock`, `Dockerfile`,
entrypoint, Layout Heron, TableFormer, mã Docling / Content Core, engine mặc định.

## E. Nghiệm thu cuối trên commit `6f6b424`

Toàn bộ mã, test, script và `CHANGELOG.md` được kiểm thử ở `6f6b424`; commit sau đó chỉ thay đổi thư mục
`docs/` (không nằm trong Docker build context, nên image dựng từ commit cuối giống hệt image đã nghiệm thu).
Một lượt chạy trước trên `d28300e` đã được chủ động dừng ở bước Docker đầu tiên để đưa các bản sửa của review
lại vào commit được nghiệm thu; kết quả phần đã chạy (backend, bộ OCR gốc, tiêu chí có điều kiện — giống hệt
lượt cuối về số bài OCR) được giữ ở `runs/run1-d28300e-stopped/`.

| Hạng mục | Baseline | Kết quả Phase 9B | Trạng thái |
|---|---|---|---|
| Backend `pytest tests/` | 9A: 1288 passed / 10 failed | **1435 passed / 10 failed / 44 skipped** — cùng đúng 10 lỗi có sẵn (`test_models_api` × 9, `test_domain` × 1), 0 lỗi mới; 147 test mới | PASS |
| Test bảo mật (`-k security/guard/commands/auth/url`) | 9A: 185 passed | **335 passed** (thêm test phân quyền) | PASS |
| mypy / ruff | 33 / lỗi có sẵn | 33 / chỉ lỗi có sẵn ở file không thuộc đợt này | PASS (không lỗi mới) |
| Frontend lint / tsc / vitest / build | 9A: 0 error / 0 / 411 / OK | **0 error (7 warning có sẵn) / 0 / 411 passed / build OK** | PASS |
| Bộ OCR gốc 48 bài, strict | 38 PASS / 10 FAIL | **38 PASS / 10 FAIL / 0 NOT VERIFIED** — đúng 10 bài cũ (so từng bài với 9A) | Không đổi (không phải 48/48) |
| Lộ trình nhanh gốc (Tesseract Best) | 6 PASS / 3 FAIL | **6 PASS / 3 FAIL** | Không đổi |
| Tiêu chí có điều kiện — Tesseract Best | 7/7, critical 7/7 | **7/7** (4 PASS + 3 kèm KL-1), **critical 7/7** | PASS |
| — Tesseract Fast / RapidOCR / EasyOCR | 5/7 · 7/7 · 2/7 | 5/7 · 7/7 · 2/7 (critical 7/7 · 7/7 · 2/7) | Không đổi |
| Docker quick (Tesseract Best, nâng cấp từ `5e04227`) | 42 / 0 | **42 PASS / 0 FAIL / 0 NOT VERIFIED** — cùng đúng 42 kiểm tra như 9A | PASS |
| Docker full, 4 lựa chọn | 8D: 74 PASS / 1 FAIL | **74 PASS / 1 FAIL / 0 NOT VERIFIED** — danh sách kiểm tra và kết quả từng dòng trùng 8D; FAIL duy nhất: nội dung OCR của EasyOCR ở E2E online (giới hạn đã biết) | Không lỗi mới (không phải "toàn bộ PASS") |
| RapidOCR persistent, backend torch | 8D: 42 / 0 | **42 PASS / 0 FAIL / 0 NOT VERIFIED** — trùng 8D từng dòng: trọng số trên data volume, checksum không đổi sau rebuild + recreate, không tải lại, `offline_ready` → `offline_verified`, xử lý khi offline, sau restart offline và sau cập nhật | PASS |
| Image không có Tesseract (RapidOCR, EasyOCR) | 8D: 50 PASS / 1 FAIL | **50 PASS / 1 FAIL / 0 NOT VERIFIED** — trùng 8D từng dòng: không có binary Tesseract trong image trước và sau, không cài ngầm, hướng trang báo `tesseract_missing`, RapidOCR và EasyOCR chuẩn bị / chạy online / offline / restart offline / sau cập nhật; FAIL duy nhất: nội dung EasyOCR | Runtime PASS; không lỗi mới |
| Trực tiếp trên stack cô lập: công tắc URL / bảo mật / đồng thời + dọn file tạm | 7/7 · 16/16 · 6/6 | **7/7 · 16/16** · đồng thời: lượt 1 **3/6** (một upload nhận HTTP 500 do xung đột ghi SurrealDB — có sẵn, xem ghi chú), chạy lại ngay trên cùng stack **6/6**; không sót `ocr-prep-*` ở cả hai lượt | PASS · PASS · PASS khi chạy lại — **lỗi không ổn định có sẵn được ghi nhận** |

Ghi chú trung thực về các lượt Docker:

- **Không phải "Docker toàn bộ PASS".** EasyOCR vẫn FAIL về nội dung ở bước E2E online trong hai lượt có
  EasyOCR — đúng giới hạn đã biết từ Phase 8C/8D. Không có lỗi mới về runtime, chuẩn bị online, vận hành
  offline, restart offline, cập nhật hay dữ liệu ở bất kỳ lượt nào. Cả bốn lượt có danh sách kiểm tra và kết
  quả từng dòng trùng với baseline (so bằng `diff`).
- **Kiểm tra đồng thời, lượt 1: 3/6.** Một trong ba upload gửi cùng lúc nhận HTTP 500; log của container nghiệm
  thu ghi SurrealDB báo xung đột giao dịch khi tạo bản ghi nguồn ("This transaction can be retried"). Hai kiểm
  tra phụ thuộc thất bại theo. Chạy lại ngay trên cùng stack: 6/6. Đây là hành vi **có sẵn** (tầng DB và luồng
  tạo nguồn không đổi kể từ `5e04227`), không do RC gây ra; ghi nhận ở mục B.3 #13, không sửa trong Phase 9B.
  Phần liên quan trực tiếp tới OCR — nhiều job trên trang scan xoay 90°, job đồng bộ, dọn file tạm — đạt ở cả
  hai lượt.
- Một lượt chạy thử thứ ba của kiểm tra đồng thời bị ngắt (mã 137) vì script nghiệm thu tạo lại container đúng
  lúc đó; không tính là kết quả.
- Mọi lượt dùng project compose riêng `ocraccept<pid>`, mạng nội bộ riêng; offline bằng cách ngắt mạng egress
  của container nghiệm thu. Không ngắt Internet của máy chủ.

Bảo mật — đã kiểm lại ở Phase 9B: URL ingestion tắt (API, JSON, retry, worker, graph, OCR URL); gọi API trực
tiếp; file containment, path traversal, symlink escape; command injection (review mã); xác thực 401; phân quyền
403 theo từng route; API job tổng quát. Mọi kiểm thử dùng mock, stub cục bộ, file tổng hợp và stack cô lập;
không kiểm thử hướng vào mạng thật.

## F. GitHub Actions

| Workflow | Kích hoạt | Ảnh hưởng tới PR / merge này |
|---|---|---|
| `test.yml` | `pull_request` / `push` vào `main` | Không chạy (không có branch `main`) |
| `build-dev.yml` | `pull_request` / `push` vào `main`, `workflow_dispatch` | Không chạy |
| `build-and-release.yml` | `release: published`, `workflow_dispatch` | Không chạy (không tạo release / tag) |
| `docs-links.yml` | `pull_request` có thay đổi `*.md` | **Chạy trên PR** — chỉ đọc (`contents: read`), kiểm tra link tương đối |

Không có workflow triển khai, không deployment environment, không webhook, không self-hosted runner. Merge vào
nhánh chính thức **không** kích hoạt build image, publish hay triển khai. Không có required check hay branch
protection nào bị bỏ qua.

## G. Pull Request và merge

| | |
|---|---|
| Pull Request | [#42](https://github.com/nghoainam1902ps4-lgtm/ChatBot5400-Version02/pull/42) — `feat: OCR Engine Manager — Vietnamese CPU OCR, Offline Operation and Security Hardening` |
| Base ← Head | `claude/practical-wozniak-9s1t6z` ← `release/ocr-engine-manager-rc1` |
| PR trùng | Không có PR nào khác cho branch này trước đó |
| Push | Fast-forward thường `76b63b5..6f6b424`, sau đó thêm commit tài liệu; không force push; không push trực tiếp vào nhánh chính thức |
| Quan hệ nhánh lúc mở PR | nhánh chính thức vẫn ở `5e04227`; RC đi trước, không đi sau; không conflict |
| Kiểm tra nội dung trước khi push | Quét mẫu bí mật (token, khóa riêng, mật khẩu gán cứng, khóa mã hóa) trên toàn bộ diff `76b63b5..HEAD`: 0 kết quả. Không file nhị phân mới, không file lớn, không địa chỉ IP / tên máy nội bộ, không đường dẫn sao lưu thật, không nội dung `.env`, không dữ liệu nghiệp vụ. Kết quả đánh giá cấu hình bảo mật của máy chủ không đưa vào repository |
| Phương thức merge | Merge commit (repository cho phép) — giữ nguyên lịch sử các phase; không squash |
| Sau merge | Không xóa branch RC; không tạo tag / release; không triển khai production |

Đối chiếu 13 điều kiện của cổng merge: [RELEASE_CANDIDATE.md](RELEASE_CANDIDATE.md) §10.1.

**Lưu ý cho chủ dự án:** các lỗi phân quyền P1 / P2 có trong bản đang chạy trên production (`5e04227`) và chỉ được
đóng khi triển khai bản này. Khai thác cần một tài khoản đã đăng nhập trong mạng nội bộ. Cho tới khi triển khai,
nên hạn chế việc cấp tài khoản mới và theo dõi thay đổi cấu hình model / credential.

## H. Giới hạn OCR và vận hành còn lại

- Bộ gốc 38/48; Tesseract Best 6/9 ở bộ gốc. Ngoại lệ duy nhất được chấp nhận: KL-1 (mất dấu ở tiêu đề in đậm
  `BẢNG KÊ CHI TIẾT KHOẢN MỤC MẪU`), không áp dụng cho số tiền, ngày, số hiệu, giá trị và nhãn dòng bảng.
- Lỗi dấu ở tiêu đề / nhãn in đậm khác trên holdout: 4/13 tài liệu (Best). Tesseract Fast chưa đạt chuẩn nghiệp
  vụ. RapidOCR mất dấu tiếng Việt. EasyOCR thử nghiệm.
- **Chưa có benchmark trên tài liệu nghiệp vụ thật.** Công cụ đã được kiểm bằng tài liệu tổng hợp ở Phase 9B.
- RapidOCR lưu bền: sau recreate cần "Chuẩn bị" một lần khi có Internet (D-32).
- SSRF: giảm thiểu bằng cách tắt URL ingestion và D-31; bộ tải của Content Core / Docling không đổi. Rollback
  về bản cũ làm URL ingestion và lỗi phân quyền credential xuất hiện trở lại.
- `offline_verified` trên production: chưa kiểm (chỉ kiểm trên stack cô lập).

## I. Production trong Phase 9B

Không dừng, không restart, không sửa cấu hình, không đọc dữ liệu nghiệp vụ. Đã thực hiện kiểm tra chỉ đọc cho
Phase 9C (kết quả ở [OCR_PRODUCTION_DEPLOYMENT_PLAN.md](OCR_PRODUCTION_DEPLOYMENT_PLAN.md) §1.1; phần đánh giá
cấu hình bảo mật của máy chủ nằm trong báo cáo riêng, không công khai), trong đó có
phát hiện quan trọng: **container production hiện không có Docling** (cài thất bại lúc khởi động ngày 2026-11-12
do `UV_OFFLINE=1` trong file override), tức production đang xử lý tài liệu không có OCR.

| | Đầu Phase 9B | Sau chuỗi nghiệm thu |
|---|---|---|
| `open_notebook` container ID | `4af860cc7335…` | giống hệt |
| `surrealdb` container ID | `a50b689a4c41…` | giống hệt |
| Image ứng dụng / DB | `sha256:7d26c1203a65…` / `sha256:e5d7387e3727…` | giống hệt |
| Thời điểm start | 2026-11-12 14:41:44 UTC | giống hệt |
| Restart count | 0 / 0 | 0 / 0 |
| `/health` | 200 | 200 |

Tài nguyên nghiệm thu phát sinh trong Phase 9B (chưa xóa gì; danh sách đầy đủ để phê duyệt nằm ở báo cáo Phase
9C / bàn giao): thư mục `work/` 41 GB → 53 GB (25 thư mục), 10 volume ẩn danh mới (42 → 52), build cache Docker
61 GB → 71 GB, ba image `chatbot5400:ocr-accept*` được dựng lại. Ổ đĩa trống 300 GB → 279 GB.

## J. Git bundle và bằng chứng

| Bundle | Nội dung | Trạng thái |
|---|---|---|
| `/home/admin/cb5400-ocr-accept/phase9b-backup.bundle` | `release/ocr-engine-manager-rc1` tại commit tài liệu của Phase 9B — toàn bộ lịch sử Phase 0 → 9B | tạo mới sau commit này, `git bundle verify` |
| `phase8b`, `phase8c`, `phase8d`, `phase9a-backup.bundle` | các mốc trước | giữ nguyên, không ghi đè |

Bằng chứng: `/home/admin/cb5400-ocr-accept/evidence/phase9b/` (preflight, `runs/` với log pytest, OCR, Docker,
kiểm tra trực tiếp) — nằm ngoài repository, không đưa lên GitHub.
