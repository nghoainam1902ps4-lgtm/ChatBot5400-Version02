# Báo cáo Phase 8D — Kiểm tra phát hành cuối và phân loại chất lượng

Ngày: 2026-11-13 · Máy nghiệm thu: Ubuntu Server, 8 CPU, 30 GB RAM, không GPU
Branch: `local/ocr-phase8c` (giữ nguyên toàn bộ commit Phase 8B và 8C) · Chưa push, chưa merge, chưa triển khai

Phase 8D không phát triển OCR engine mới. Nó thực hiện bốn quyết định của chủ dự án, nghiệm thu các
phần còn thiếu và chốt tiêu chuẩn phát hành. Số liệu lịch sử của Phase 8B/8C không bị sửa.

## Kết luận

| Trạng thái | Kết luận | Lý do |
|---|---|---|
| Merge | **READY FOR MERGE (có điều kiện)** — chờ chủ dự án xác nhận | Tesseract Best đạt tiêu chí phát hành có điều kiện 7/7 (3 bài áp dụng KL-1, đã xác minh là lỗi duy nhất); không lỗi mới ở backend, frontend, bảo mật. Bộ gốc **vẫn là 38/48**, lộ trình nhanh gốc **vẫn là 6/3** |
| Phát hành có điều kiện | **READY FOR CONDITIONAL RELEASE** — chỉ với Tesseract Vietnamese Best (khuyến nghị) và RapidOCR (tương thích ngược) | Xem mục 4 và 6. Tesseract Fast: dùng được, có giới hạn ngoài KL-1. EasyOCR: thử nghiệm, không đạt |
| Production | **NOT READY FOR PRODUCTION** | (1) Rủi ro SSRF qua redirect chưa có biện pháp được phê duyệt (mục 10); (2) chưa benchmark trên tài liệu thật; (3) chưa có backup và quy trình vận hành được duyệt |

## 1. Các quyết định của chủ dự án đã thực hiện

| # | Quyết định | Đã làm | Kết quả |
|---|---|---|---|
| 1 | Chấp nhận có điều kiện lỗi mất dấu ở tiêu đề `BẢNG KÊ` **nếu** đó là nguyên nhân duy nhất | `scripts/ocr/release_criteria.py` đánh giá lại **mọi** assertion của bài gốc cho từng engine × fixture | **Tesseract Best: đúng là nguyên nhân duy nhất ở cả 3 bài** → ngoại lệ áp dụng. **Tesseract Fast: KHÔNG** — 2 bài còn sai thêm nhãn dòng `Tổng cộng` → ngoại lệ không áp dụng |
| 2 | Chấp nhận `tesseract_gate.py` nếu đạt đủ điều kiện | Review toàn bộ, thêm chốt chặn và test | Đạt đủ 11 điều kiện (mục 2) |
| 3 | Giữ `pdf_prep.py`; RapidOCR/EasyOCR không bắt buộc Tesseract; readiness phản ánh đúng | Trạng thái khả dụng qua API, metadata, log; fingerprint readiness theo cấu hình chất lượng | Đạt (mục 3) |
| 4 | Phân loại 4 lựa chọn; EasyOCR là thử nghiệm | `quality` trong catalog, API, giao diện vi/en; xác nhận trước khi bật EasyOCR | Đạt (mục 4) |

Không sửa 48 bài gốc, fixture, ground truth hay ngưỡng. Không `skip`/`xfail`. Không sửa expected text.
Không có từ điển sửa OCR. Không hạ ngưỡng CER/WER.

## 2. Review `tesseract_gate.py`

File 135 dòng, chỉ dùng thư viện chuẩn, được đặt qua tùy chọn chính thức `TesseractCliOcrOptions.tesseract_cmd`.

| Điều kiện | Kết quả | Bằng chứng |
|---|---|---|
| Không kế thừa `BaseOcrModel` | Đạt | Không import Docling |
| Không thay Tesseract, không đổi thuật toán nhận dạng | Đạt | Lệnh nhận dạng được `exec` thẳng sang Tesseract thật |
| Không sửa Docling / Content Core / site-packages; không monkey patch | Đạt | Không file nào ngoài `open_notebook/ocr/` thay đổi |
| Không xử lý văn bản OCR theo từ khóa; không hardcode fixture | Đạt | `test_gate_holds_no_text_or_fixture_knowledge` |
| Không đổi kết quả ở chế độ không liên quan hướng | Đạt | So **từng byte** với Tesseract thật: TSV nhận dạng, `--version`, `--list-langs` giống hệt (`test_gate_does_not_change_recognition_output`) |
| Không lỗi tọa độ sau xoay | Đạt | Gate chỉ biến OSD thành "đứng thẳng"; Docling quy đổi tọa độ như khi OSD trả 0° |
| Chuyển tiếp tham số, exit code, stdout, stderr | Đạt | `test_gate_process_passes_other_calls_through` |
| Timeout | Đạt (bổ sung ở 8D) | Lệnh OSD giới hạn 120 s → exit 124; Docling coi là OSD lỗi và OCR tiếp, không treo |
| Command injection | Đạt | Không `shell=True`; tham số dạng danh sách do Docling tạo |
| Đường dẫn binary là cấu hình quản trị | Đạt | `OCR_TESSERACT_REAL` do ứng dụng đặt từ `OCR_TESSERACT_CMD`/PATH |
| Không đệ quy gọi lại chính nó | Đạt (bổ sung ở 8D) | exit 126 (`test_gate_refuses_to_call_itself`) |
| Frontend không truyền được command | Đạt | `test_tesseract_cmd_never_comes_from_a_request` |
| Rollback | Đạt | `OCR_TESSERACT_OSD_GATE=false`; gate không chạy được ⇒ tự gọi thẳng Tesseract kèm cảnh báo |

**Ngưỡng 2,0:** 1 340 phép đo OSD trên crop thật — mọi câu sai có confidence ≤ 1,44; ở ngưỡng 2,0 không
câu sai nào lọt qua. Trên holdout (không dùng để chọn ngưỡng): không tài liệu nào xấu đi, dòng bảng
đúng 3/42 → 38/42 (Best), 3/42 → 41/42 (Fast).

## 3. Review `pdf_prep.py`

| Yêu cầu | Kết quả | Bằng chứng |
|---|---|---|
| Chỉ xử lý bản PDF tạm; không sửa file gốc | Đạt | SHA-256 trước/sau |
| Không rasterize PDF có text layer | Đạt | Văn bản text layer của từng trang giống hệt trước/sau; trang không phải scan không bị đụng tới |
| Không mất metadata | Đạt | Metadata, số trang, MediaBox, kích thước ảnh nhúng giống hệt; khác biệt duy nhất là `/Rotate` của trang scan (`test_rotated_copy_keeps_text_layer_images_and_metadata`, 90/180/270°) |
| Không sai bbox / tọa độ | Đạt | So với bản đứng thẳng của cùng tài liệu: bbox lệch tối đa 0,4 pt ở 90°, 180°, 270° |
| Không hỏng bảng | Đạt | Bảng xoay 180°/270° cho cùng hình dạng 8×4 và cùng bbox với bản đứng thẳng |
| Không ảnh hưởng PDF hỗn hợp | Đạt | `hon_hop.pdf` (trang text + trang scan): trang text nguyên vẹn; fixture này PASS như trước |
| Dọn file tạm an toàn | Đạt | Xóa ở mọi đường thoát (cả khi Docling lỗi); trên container: 3 job song song + 1 job sync, không sót `ocr-prep-*` |

Ghi chú trung thực: ở một trong sáu cặp so sánh (thư xoay 270°) Layout chia một khối đoạn văn khác đi
(6 khối thay cho 5, lệch 20 pt ở một khối); văn bản và các khối còn lại trùng khớp. Đây là dao động của
Layout trên ảnh JPEG đã mã hóa lại, không phải sai tọa độ do xoay.

**RapidOCR và EasyOCR khi không có Tesseract:**

- Không bắt buộc cài Tesseract. Đo cục bộ với Tesseract bị ẩn: RapidOCR cho kết quả **trùng 7/7** với
  baseline Phase 8B; metadata ghi `page_orientation: tesseract_missing`. EasyOCR chỉ khác baseline ở
  ngưỡng confidence (D-26), không liên quan Tesseract.
- Docker với image **không có Tesseract**: xem mục 7.
- Không tải hay cài Tesseract ngầm (kiểm tra trong container sau khi xử lý).
- Trạng thái hiển thị ở "Thông tin chung" của OCR Engine Manager và trong API
  (`general.page_orientation`): `ok` / `disabled` / `tesseract_missing` / `osd_data_missing`.
- Tắt: `OCR_PDF_PREP=false`.

**Readiness:** fingerprint của mỗi engine giờ gồm cấu hình chất lượng (gate, các ngưỡng, trạng thái hướng
trang, ngưỡng EasyOCR). Đổi một giá trị, hoặc cài/gỡ `osd.traineddata`, làm verdict `offline_ready` cũ
hết hiệu lực. Tính năng hướng trang không bao giờ được báo khả dụng khi thiếu runtime hoặc
`osd.traineddata` (`test_orientation_status`, `test_readiness_fingerprint_follows_the_quality_configuration`).

## 4. Phân loại chất lượng 4 lựa chọn

Ba trạng thái được báo riêng: **(1) Sẵn sàng** (runtime/model) · **(2) Đã xác minh offline** ·
**(3) Chất lượng**. Một engine có thể chạy offline mà chưa đạt chất lượng nghiệp vụ.

| Lựa chọn | Phân loại | (1) | (2) Offline (Docker) | (3) Critical 7 fixture | Tiêu chí có điều kiện | Ghi chú hiển thị |
|---|---|---|---|---|---|---|
| Tesseract Vietnamese Best | Khuyến nghị cho tiếng Việt | đạt | đạt | **7/7** | **7/7** (4 PASS + 3 KL-1) | Một số tiêu đề in đậm chữ hoa mất dấu |
| Tesseract Vietnamese Fast | Ưu tiên tốc độ | đạt | đạt | **7/7** | 5/7 | Bảng tốt trên holdout; một số nhãn chữ trong bảng và tiêu đề mất dấu |
| RapidOCR – PaddleOCR | Tương thích ngược | đạt | đạt | 7/7 (theo tiêu chí riêng: chỉ trường số) | 7/7 | Không đổi model/cấu hình; mất dấu tiếng Việt, không khớp nhãn bảng tiếng Việt |
| EasyOCR Vietnamese | **Thử nghiệm** | đạt | đạt | **2/7** | 2/7 | Không dùng cho văn bản tài chính; cảnh báo trước khi bật |

- Thể hiện ở: catalog (`quality`), API, giao diện vi-VN và en-US, tài liệu tiếng Việt
  (`OCR_ENGINE_MANAGER.md` §8) và tiếng Anh (ADR-013, Addendum).
- EasyOCR: hỏi xác nhận trước khi bật; không bao giờ là mặc định; không có fallback tự động.
  Không tuyên bố tăng DPI sửa được mọi lỗi.
- "Critical 7/7" của RapidOCR dùng tiêu chí gốc dành cho nó (không xét số hiệu có dấu và nhãn tiếng Việt)
  nên **không** so sánh ngang với Tesseract.

## 5. Kết quả bộ 48 test gốc (A)

Không thay đổi so với Phase 8C. **Không phải 48/48.**

| Bộ | Kết quả |
|---|---|
| 48 bài, 4 lựa chọn, strict | **38 PASS / 10 FAIL / 0 NOT VERIFIED** |
| Lộ trình nhanh (Tesseract Best, 9 bài) | **6 PASS / 3 FAIL** |
| RapidOCR 8/8 · Tesseract Fast 7/9 · Tesseract Best 6/9 · EasyOCR 4/9 · bài chung 13/13 | |

10 bài FAIL: tesseract_best × 3 và tesseract_fast × 2 (`bang_gop_scan`, `nhieu_trang_scan`, và `hon_hop`
với Best); easyocr × 5.

## 6. Kết quả tiêu chí phát hành bổ sung (B)

`scripts/ocr/release_criteria.py` — 4 engine × 7 fixture, đánh giá lại mọi assertion gốc. Kết quả gốc
luôn được in cạnh kết quả có điều kiện.

| Engine | Gốc PASS | Có điều kiện PASS | PASS kèm KL-1 | FAIL | Critical đạt |
|---|---|---|---|---|---|
| Tesseract Best | 4/7 | 4 | **3** | **0** | **7/7** |
| Tesseract Fast | 5/7 | 5 | 0 | 2 | **7/7** |
| RapidOCR | 7/7 | 7 | 0 | 0 | 7/7 |
| EasyOCR | 2/7 | 2 | 0 | 5 | 2/7 |

Xác minh từng bài Tesseract đang FAIL:

| Bài | Assertion gốc thất bại | Phần còn lại | Ngoại lệ |
|---|---|---|---|
| tesseract_best – bang_gop_scan | chỉ `ordered_phrases` (tiêu đề `BẢNG KÊ …` mất dấu) | số tiền 8/8, ngày 4/4, bảng 6×5, 4/4 dòng đủ nhãn và giá trị, ô gộp | **KL-1 áp dụng** |
| tesseract_best – nhieu_trang_scan | chỉ `ordered_phrases` (cùng tiêu đề) | số tiền 9/9, ngày 7/7, số hiệu 2/2, bảng 6×5, 4/4 dòng, ô gộp | **KL-1 áp dụng** |
| tesseract_best – hon_hop | chỉ `ordered_phrases` (cùng tiêu đề) | số tiền 8/8, ngày 5/5, số hiệu 1/1, bảng 6×5, 4/4 dòng, ô gộp | **KL-1 áp dụng** |
| tesseract_fast – bang_gop_scan | `ordered_phrases` **và** `table_rows` (nhãn `Tổng cộng` sai dấu; giá trị số đúng) | số tiền, ngày đủ; giá trị 4/4 dòng | **Không áp dụng** — có lỗi ngoài tiêu đề |
| tesseract_fast – nhieu_trang_scan | như trên | như trên | **Không áp dụng** |

Critical gồm: mọi số tiền, mọi ngày, mọi số hiệu (không gộp, không nới theo engine), hình dạng bảng, giá
trị số của từng dòng bảng, ô tiêu đề gộp, tiêu đề có mặt đúng vị trí khi không xét dấu. General gồm: CER,
tiêu đề đúng từng dấu, nhãn dòng bảng, word recall trang xoay.

**Holdout (13 tài liệu, tham khảo — không phải một phần của nghiệm thu):** Critical đạt **13/13** cho cả
Tesseract Best và Fast. Về General, 4 tài liệu (Best) và 3 tài liệu (Fast) có lỗi dấu ở một tiêu đề hoặc
một nhãn dòng bảng khác. Tức là hiện tượng mất dấu ở chữ in đậm/nhãn bảng **rộng hơn** đúng một cụm
`BẢNG KÊ`; KL-1 chỉ phủ cụm đã được chấp nhận (mục 11 F).

## 7. Docker (D)

Mọi lượt dùng project compose riêng, mạng nội bộ riêng; offline bằng cách ngắt mạng egress của container
nghiệm thu. Không ngắt Internet của máy chủ.

| Lượt | Kịch bản | Kết quả |
|---|---|---|
| Quick | Tesseract Best, nâng cấp từ `5e04227` | **42 PASS / 0 FAIL / 0 NOT VERIFIED** (chạy lại sau khi sửa script; lượt đầu 41/1 do lỗi script) |
| Full | 4 lựa chọn, nâng cấp từ `5e04227` | **74 PASS / 1 FAIL / 0 NOT VERIFIED** — FAIL duy nhất: nội dung OCR của EasyOCR |
| RapidOCR persistent | `OCR_RAPIDOCR_PERSISTENT=true`, backend torch | **42 PASS / 0 FAIL** |
| Không có Tesseract | image không có Tesseract, không bật cờ cài; RapidOCR + EasyOCR | **50 PASS / 1 FAIL / 0 NOT VERIFIED** — FAIL duy nhất: nội dung OCR của EasyOCR. Không có binary Tesseract trong container trước và sau; API báo `tesseract_missing`; cả hai engine chuẩn bị, chạy online, offline, restart offline và sau cập nhật |

**Không phải "Docker toàn bộ PASS":** EasyOCR vẫn FAIL về nội dung ở bước E2E online (thiếu
`1234/2024/QĐ-MẪU` và câu có số tiền).

Chuỗi vận hành, lượt Full (cả 4 lựa chọn):

| Bước | RapidOCR | Tesseract Fast | Tesseract Best | EasyOCR |
|---|---|---|---|---|
| Chuẩn bị online → `offline_ready` | PASS | PASS | PASS | PASS |
| E2E online qua API + worker (nội dung) | PASS | PASS | PASS | **FAIL nội dung** |
| Chuẩn bị lần hai dùng lại model | PASS | PASS | PASS | PASS |
| Offline: `offline_verified` + xử lý PDF | PASS | PASS | PASS | PASS (trùng kết quả online, so hash) |
| Restart khi offline | PASS | PASS | PASS | PASS (như trên) |
| Cập nhật online: rebuild, recreate, model dùng lại, chuẩn bị lại | PASS | PASS | PASS | PASS |
| Offline lại sau cập nhật | PASS | PASS | PASS | PASS (như trên) |

Chung cho cả ba vòng offline: Internet không tới được từ container, DB vẫn tới được, checksum model và
cache Hugging Face không đổi, không có lần tải nào trong log. Nâng cấp từ bản production `5e04227`:
settings và dữ liệu giữ nguyên. Trạng thái hướng trang: "không khả dụng" trước khi cài model Tesseract,
"khả dụng" sau khi cài.

Kiểm tra bổ sung trên stack cô lập (`runs/concurrency-live.json`): 3 job async song song + 1 job sync
(`async_processing=false`) trên trang scan xoay 90° — cả 4 hoàn tất, cùng một văn bản, có số hiệu và số
tiền đúng; không sót thư mục tạm.

**Lỗi của script nghiệm thu tìm thấy và đã sửa (`c5162df`):** bước "worker log shows …" dùng
`docker logs | grep -q` dưới `set -o pipefail`, nên đôi khi báo FAIL dù dòng log có thật. Lượt quick đầu
tiên dính lỗi này (41 PASS / 1 FAIL, log giữ ở `docker-quick-8d.run1-script-race.log`); đã kiểm tra dòng
log tồn tại trong container, sửa script và chạy lại.

Phạm vi **chưa** kiểm chứng: `offline_verified` ngoài Docker (cần ngắt mạng máy chủ, sẽ ảnh hưởng
production). Offline thật chỉ được chứng minh trong container nghiệm thu cô lập.

## 8. RapidOCR persistent, backend torch

Chạy lại sau các thay đổi Phase 8C/8D, không đổi trọng số hay dependency lock:
`OCR_RAPIDOCR_PERSISTENT=true SCENARIOS=rapidocr OLD_REF=5e04227` → **42 PASS / 0 FAIL / 0 NOT VERIFIED**.

- Trọng số `.pth` nằm trên data volume; sau rebuild + recreate container, checksum không đổi và không
  tải lại ("update: OCR models reused").
- `offline_ready` → `offline_verified`; xử lý PDF khi offline, sau restart offline và sau cập nhật.
- Lượt này cũng là một trường hợp RapidOCR chạy khi **chưa cài model Tesseract nào**: trạng thái hướng
  trang được báo "không khả dụng" trước và sau, RapidOCR vẫn xử lý tài liệu bình thường.

Log: `runs/docker-rapidocr-persistent-8d.log`.

## 9. Regression

| Hạng mục | Kết quả |
|---|---|
| Backend `pytest tests/` | 1239 passed / 10 failed / 44 skipped — **cùng đúng 10 lỗi có sẵn trên `main`**, 0 lỗi mới |
| Test mới của Phase 8D | 15 (gate, hướng trang, fingerprint, phân loại, bảo toàn text layer) + 13 (tiêu chí phát hành) |
| Frontend | lint 0 error (7 warning có sẵn) · tsc 0 lỗi · vitest **408/408** (4 test mới) · production build OK |
| mypy / ruff | 33 / 1 — đều có sẵn, không lỗi mới |

## 10. Security

- Test bảo mật backend (job guard, commands, auth, URL validation): 142 passed.
- Kiểm tra trực tiếp trên stack nghiệm thu cô lập: **16/16** (không đăng nhập → 401; non-admin → 403 trên
  mọi endpoint OCR và commands; admin gửi job tổng quát / nonce giả → từ chối).
- Bề mặt mới của Phase 8D: hai trường chỉ đọc trong API (`quality`, `page_orientation`). Không endpoint,
  không job, không quyền mới. Command Tesseract không đến từ request.

**Rủi ro còn lại — SSRF qua redirect (CHƯA khắc phục, D-28).** Worker kiểm tra URL và từng bước redirect
trước, nhưng Content Core / Docling tải lại URL và tự đi theo redirect. Redirect khác ở lần tải thật và DNS
rebinding không bị chặn. Phase 8D không đổi firewall, mạng production hay kiến trúc URL ingestion.

Biện pháp đề xuất cho môi trường ngân hàng (cần chủ dự án phê duyệt ít nhất một):

1. Tắt URL ingestion với nguồn không tin cậy bằng cơ chế thực thi ở backend. Chưa có trong mã; cần một
   thay đổi riêng, nhỏ, có test.
2. Chính sách egress do quản trị viên phê duyệt cho container ứng dụng: chặn dải nội bộ, link-local,
   metadata; chỉ cho phép đích cần thiết.
3. Vận hành offline sau khi chuẩn bị online: trong thời gian ngắt mạng, bề mặt này bằng 0.

Các hạn chế có sẵn, không đổi: CORS mở, xác thực mật khẩu đơn giản, image chạy root.

## 11. Giới hạn

**E. Đã được chấp nhận**

| ID | Giới hạn | Phạm vi |
|---|---|---|
| KL-1 | Tesseract mất dấu ở tiêu đề in đậm `BẢNG KÊ CHI TIẾT KHOẢN MỤC MẪU` | Chỉ cụm này, chỉ lỗi dấu, chỉ khi là lỗi duy nhất của bài. Tesseract Best: 3 bài |
| — | `tesseract_gate.py` đứng giữa Docling và Tesseract | Đã review; rollback bằng biến môi trường |
| — | RapidOCR mất dấu tiếng Việt (model mặc định) | Engine tương thích ngược, không đổi model |

**F. Chưa được chấp nhận / còn mở**

| Giới hạn | Bằng chứng | Hệ quả |
|---|---|---|
| Tesseract Fast sai dấu ở nhãn dòng bảng (`Tổng cộng`) | 2 bài gốc; critical vẫn 7/7 | Fast không đạt tiêu chí có điều kiện ở 2/7 bài |
| Mất dấu ở tiêu đề/nhãn in đậm rộng hơn cụm `BẢNG KÊ` | Holdout: 4/13 (Best), 3/13 (Fast) tài liệu có lỗi dấu ở tiêu đề hoặc nhãn khác; critical 13/13 | Cần chủ dự án quyết định có mở rộng KL-1 thành "lỗi dấu ở tiêu đề/nhãn khi critical đạt" hay không. Chưa mở rộng |
| EasyOCR sai chữ số và dấu ở scan 150 DPI | 5 bài gốc; critical 2/7 | Thử nghiệm; không dùng cho tài liệu tài chính |
| SSRF qua redirect | mục 10 | Chặn production cho tới khi có biện pháp được duyệt |
| Trang vừa có text layer vừa có ảnh scan nằm ngang so với text | Chưa có fixture | Không được tự xoay |
| `offline_verified` ngoài Docker | Chưa chạy | Chỉ kiểm chứng trong container |
| Benchmark trên tài liệu thật | Chưa làm (không dùng dữ liệu nghiệp vụ) | Việc của người vận hành, làm cục bộ |

## 12. An toàn production

- Deployment `chatbot5400-version02`: container ID, image, thời điểm start (2026-11-12 14:41 UTC) và
  restart count (0) **giống hệt** trước và sau Phase 8D; `/health` trả 200
  (`evidence/phase8d/preflight/production-{before,after}.txt`).
- 22 volume có trước Phase 8D còn nguyên (0 volume mất). Phase 8D tạo thêm 16 volume ẩn danh từ các lượt
  Docker; không xóa volume nào.
- Không xóa image, model cache, evidence hay workspace. Không `docker system prune`, không `down -v`.
- Không ngắt Internet của máy chủ; offline chỉ trong container nghiệm thu cô lập.
- Không dùng dữ liệu nghiệp vụ thật; mọi tài liệu đo là tổng hợp.
- Hai lần chuỗi Docker bị ngắt (phiên làm việc kết thúc; một lượt tôi chủ động dừng vì cấu hình kịch bản
  sai). Lần đầu script tự dọn; lần sau còn sót 2 container nghiệm thu `ocraccept927043-*`, đã gỡ bằng
  `docker compose -p ocraccept927043 down --remove-orphans` (không `-v`). Production không bị đụng tới.
- Tài nguyên phát sinh, **chưa xóa**: thư mục `work/` 17 GB → 36 GB (7 thư mục mới), image
  `chatbot5400:ocr-accept-notess` (2,5 GB), 16 volume ẩn danh, build cache. Ổ đĩa trống 345 GB → 310 GB.

## 13. Git

- Branch: `local/ocr-phase8c` (cục bộ). Không tạo branch mới, không reset, không push, không merge.
- Commit Phase 8D sau `16fc623`: `09231ee` (phân loại chất lượng, trạng thái hướng trang, tiêu chí phát
  hành có điều kiện), `c5162df` (sửa race của script Docker), và commit tài liệu + kịch bản không có
  Tesseract của phase này (HEAD của branch; ghi trong `evidence/phase8d/commits.txt`).
- Toàn bộ commit Phase 8B (`5e6522e` … `f172645`) và Phase 8C (`e6f2bbb`, `755b637`, `6f1c811`, `16fc623`)
  còn nguyên trong lịch sử.
- Bundle mới: `/home/admin/cb5400-ocr-accept/phase8d-backup.bundle` (chứa `local/ocr-phase8c` và
  `local/ocr-phase8b`, đã `git bundle verify`). Các bundle cũ `phase8b-backup.bundle`,
  `phase8c-backup.bundle` không bị ghi đè.

## 14. Hướng dẫn cập nhật khi có Internet

Chi tiết: `OCR_ONLINE_PREPARATION.md`. Tóm tắt cho bản này:

1. Backup `notebook_data` và `surreal_data`. Không dùng `docker compose down -v`.
2. Cập nhật mã và image khi máy chủ **có Internet**; khởi động lại. Settings, dữ liệu và model OCR đã
   cài được giữ nguyên (đã kiểm chứng: checksum model không đổi sau cập nhật).
3. Mở OCR Engine Manager. Với engine sẽ dùng: **Cài đặt** (nếu chưa) → **Chuẩn bị** → chờ `offline_ready`.
   Sau bản cập nhật này, kết quả readiness cũ hết hiệu lực (fingerprint có thêm cấu hình chất lượng) nên
   **phải chạy lại "Chuẩn bị"** một lần.
4. Khuyến nghị cài Tesseract Vietnamese Best. Việc này đồng thời bật "Tự sửa hướng trang scan" cho mọi
   engine (kiểm tra dòng trạng thái ở "Thông tin chung").
5. Chọn engine: **Sử dụng**. EasyOCR sẽ hỏi xác nhận vì ở mức thử nghiệm.
6. Ngắt Internet → **Kiểm tra offline** → `offline_verified` → vận hành.
7. Nếu container có thể bị recreate khi offline và đang dùng RapidOCR: bật `OCR_RAPIDOCR_PERSISTENT=true`
   trước bước 3.
8. Rollback: `OCR_ROLLBACK.md`. Tắt riêng từng cải tiến chất lượng: `OCR_TESSERACT_OSD_GATE=false`,
   `OCR_PDF_PREP=false`, `OCR_EASYOCR_CONFIDENCE=0.5`.

## 15. Điều kiện trước merge và production

**Trước merge `main`:**

1. Chủ dự án xác nhận tiêu chí phát hành có điều kiện (D-27) thay cho điều kiện `FAIL == 0` của lộ trình
   nhanh: Tesseract Best 7/7 theo tiêu chí có điều kiện, critical 7/7; bộ gốc vẫn báo 6/3.
2. Quyết định về hai điểm ở mục 11 F liên quan Tesseract (nhãn bảng của Fast; lỗi dấu rộng hơn KL-1).
3. Đọc lại diff `45e2254..HEAD`.
4. Push branch và mở PR là thao tác của chủ dự án; chưa thực hiện.

**Trước production:**

1. Biện pháp cho SSRF qua redirect được phê duyệt và áp dụng (mục 10).
2. Benchmark trên tài liệu thật, làm cục bộ, bằng `scripts/ocr/quality_eval.py`; chọn engine theo kết quả.
3. Backup và kế hoạch rollback đã duyệt.
4. Quy trình online preparation → `offline_ready` → ngắt mạng → `offline_verified` chạy trên máy đích.
5. Các hạn chế dev-default (CORS, xác thực, root) được đánh giá cho môi trường đích.
