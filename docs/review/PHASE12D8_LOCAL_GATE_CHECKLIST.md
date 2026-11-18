# Phase 12D8 — Local gate checklist

Bổ sung cho [PHASE12D7_LOCAL_ACCEPTANCE_CHECKLIST.md](PHASE12D7_LOCAL_ACCEPTANCE_CHECKLIST.md) (W-12D7-*) và
[PHASE12D5_LOCAL_ACCEPTANCE_CHECKLIST.md](PHASE12D5_LOCAL_ACCEPTANCE_CHECKLIST.md) (W-RC, W-LEG, W-TOK, W-OFF, W-INT,
W-FB): các mục đó vẫn còn hiệu lực. Tài liệu này gom chúng thành 12 cổng, sửa kỳ vọng ở những chỗ review 12D8 thấy
sai, và thêm mục mới (đánh dấu **[mới]**).

Quy tắc giữ nguyên: stack thử `chatbot5400-phase12-test`, chỉ loopback, không dùng database / credential / dữ liệu
production; PDF nghiệp vụ, kết quả OCR, model Agri, khóa ký ở lại máy Local; báo cáo gửi đi chỉ có số liệu và mã kết
quả. Ghi **Đạt / Không đạt / Không chạy** cho từng mục. Kết quả khác kỳ vọng: ghi nguyên trạng, không sửa tiêu chí.

**Thứ tự.** Nhóm 1 thu bằng chứng, có thể chạy ngay trên `4587eb7`. Nhóm 2 là nghiệm thu cuối: chỉ chạy trên commit
đã xử lý các blocker của [PHASE12D8_RELEASE_BLOCKERS.md](PHASE12D8_RELEASE_BLOCKERS.md), vì runtime sẽ đổi.

## Nhóm 1 — chạy được ngay

### G-01 — Mốc so sánh và build image

| # | Việc | Kỳ vọng |
|---|---|---|
| W-12D7-00a, 00b, 00d | giữ image v1.2.0 và `904c15c`; checkout đầu nhánh; `phase12-test.ps1 build` | build đạt, có bước tự kiểm cổng |
| W-12D7-00c (sửa kỳ vọng) | `git ls-files --eol open_notebook/ocr/tesseract_gate.py` trước và sau pull | checkout **đã có** vẫn hiện `w/crlf` sau pull — bình thường (D8-ORI-03); checkout mới hiện `w/lf` |
| **[mới]** G-01a | sửa một dòng của bước tự kiểm trong bản sao Dockerfile để cổng không chạy được (ví dụ bỏ bước `sed`, build từ checkout `w/crlf`) | `docker build` **thất bại** ở bước đó — bằng chứng build thật mà Cloud không có |

### G-02 — Cổng hướng xoay và nguyên nhân E1-05

| # | Việc | Kỳ vọng |
|---|---|---|
| W-12D7-01a (sửa kết luận) | image cũ 12E1: `od -c` đầu file cổng; tìm `runs without orientation gating` trong log | có `\r` / dòng log ⇒ chỉ kết luận **"cổng đã tắt"**, chưa kết luận nguyên nhân (D8-ORI-04) |
| W-12D7-01b | image mới: `phase12-test.ps1 status` | `orientation gate: active (min confidence 2.0)` |
| W-12D7-01c | `orientation` cho 11 cụm nghi ngờ | **Nguyên nhân E1-05 chỉ được xác nhận khi** 01a có `\r` **và** từng cụm có góc xoay với `raw_confidence < 2.0` mà cổng từ chối |
| **[mới]** G-02a | cụm nào có góc thô 90 / 270 | **không dùng** kết luận "alternative reads better" của công cụ (D8-ORI-01); so tay chữ của ingestion với ảnh vùng |
| W-12D7-01d | còn vùng xoay sai với confidence ≥ 2.0 | finding mới kèm `orientation_summary.json` (`-NoText`); **không đổi ngưỡng** |
| W-12D7-01e | chữ của 11 cụm sau build lại | không còn chữ rác do xoay |

### G-03 — E0-07 trên tài liệu thật

| # | Việc | Kỳ vọng |
|---|---|---|
| W-12D7-02a | `docling_patches.status()` trong container | `applied: True`, `docling: 2.129.0`, `problems: []` |
| W-12D7-02b | 22 PDF với Tesseract Best, Agri v1, Agri v2 | mọi token của TSV có trong ô OCR đúng nguyên văn |
| **[mới]** G-03a | với ít nhất 3 tài liệu: lưu TSV thô của **chính lần gọi** theo từng crop (không phải Direct OCR toàn trang của `diagnose`) và so với ô OCR của crop đó | bằng nhau theo thứ tự. Direct OCR toàn trang và OCR theo vùng là hai lần gọi khác nhau, không dùng lẫn làm bằng chứng |
| W-12D7-02c | fixture `d5_f02_*`, `f08_protected_fields` | không còn `1.0`, `2024.0` |
| **[mới]** G-03b (D8-03) | trong 22 PDF, tìm số hiệu / khoảng năm / mã số ngắt dòng tại `-`, và dạng `a- b` giữa dòng; so TSV với nội dung lưu | **ghi lại số chỗ mất `-`** ở Standard và Legal, trên image v1.2.0 và image mới — số liệu để chủ dự án quyết định D8-03 |

### G-07 — Build gói offline trên Windows

| # | Việc | Kỳ vọng |
|---|---|---|
| W-12D7-04a, 04b | `build-package.ps1` trên PowerShell 5.1 và 7 | đạt, `readiness: READY` |
| **[mới]** G-07a (D8-OFF-11) | cùng lệnh trên máy **có Python, không có `uv`** | hiện tại dự kiến dừng ở `check-version` với lỗi không tìm thấy lệnh `p` — ghi lại; sau khi sửa: đạt |
| **[mới]** G-07b | đường dẫn checkout có dấu cách; `-SignKey` | đạt |
| W-12D7-04c | hai cửa sổ cùng tên gói | cửa sổ thứ hai bị từ chối ngay, nêu file khóa và PID |
| W-12D7-04d | đóng cửa sổ giữa `docker save` rồi build lại | gói tốt trước đó + `.sha256` còn nguyên |
| **[mới]** G-07c (D8-OFF-03, 04) | sau mỗi lần build bị ngắt: liệt kê `dist\offline` | ghi lại mọi file `*.sha256.previous-*` và gói không có `.sha256` |
| W-12D7-04e | `pytest tests\test_phase12d7_build_lock.py` bằng Python Windows | đạt (nhánh `msvcrt` — chưa từng chạy thật) |
| W-12D7-04f, 04g | `manifest.json` không có `0D 0A`; `verify-package.sh` trên Ubuntu thử | đạt; `docling_tsv_patch.applied: true` |
| **[mới]** G-07d | `--out` trên ổ mạng / exFAT; WSL và PowerShell cùng build vào một thư mục | ghi lại hành vi khóa (giả thuyết chưa kiểm: hai cơ chế khóa không thấy nhau) |

### G-08 — `phase12-test.ps1`

W-12D7-05a … 05d trên PowerShell 5.1 **và** 7. **[mới]** G-08a (D8-OFF-12): chạy `check` và `up` khi Docker Desktop
đang tắt trên 5.1 — script phải báo lỗi rõ, không dừng bằng `NativeCommandError` ở lệnh có `2>$null`.

## Nhóm 2 — nghiệm thu cuối, sau khi xử lý blocker

### G-04 — Standard expected-diff

Điều kiện: D8-STD-01 / 02 / 03 / 04 đã sửa. Nếu chưa, kết quả công cụ chỉ có giá trị khi kèm G-04a và G-04b.

| # | Việc | Kỳ vọng |
|---|---|---|
| W-12D7-02e | Standard của 22 PDF bằng image v1.2.0 và image mới, cùng engine; chạy `phase12_standard_diff.py` với TSV theo từng crop | `unexpected regression` = 0; `not verified` = 0 hoặc từng trường hợp được giải thích bằng TSV của đúng crop |
| **[mới]** G-04a | so byte trực tiếp từng cặp file (`fc /b`) | tài liệu công cụ báo `unchanged` phải **giống từng byte** |
| **[mới]** G-04b | đếm tài liệu | số file hai phía bằng nhau và bằng số tài liệu công cụ báo |
| **[mới]** G-04c | mỗi khác biệt được chấp nhận | có liên kết nhân quả với (A) bản vá TSV, (B) sửa cổng hướng xoay đã xác nhận ở G-02, hoặc (C) bản vá gạch nối nếu D8-03 được vá. Không miễn trừ cả tài liệu |
| W-12D7-02f | RapidOCR và EasyOCR, image mới so với v1.2.0 | **giống hệt từng byte** (nếu D8-03 được vá: trừ đúng các chỗ gạch nối, có danh sách) |

### G-05 — Legal trên scan thật

| # | Việc | Kỳ vọng |
|---|---|---|
| W-12D7-03a … 03e, W-RC-07, W-RC-08, W-LEG-* | như checklist 12D7 / 12D5 | như đã ghi |
| **[mới]** G-05a (D8-01) | PDF có trang khác kích thước (scan tự cắt lề, phụ lục khổ ngang, PDF ghép nhiều văn bản) và PDF có trang hai cột; với mỗi `upstream_merge_undone` trong `09_legal_report.json` | phần tách đứng **ngay sau** phần đầu của nó; không đoạn nào bị đẩy ra sau tiêu đề / đoạn kế tiếp |
| **[mới]** G-05b (D8-02) | bảng và ảnh có ghi chú ngay bên dưới | ghi chú có trong nội dung Legal (sau khi sửa) hoặc có cảnh báo; ghi lại hành vi Standard |
| **[mới]** G-05c | mỗi cảnh báo `upstream_dehyphenation` | đọc từng chỗ: ghi lại đoạn liên trang còn dính (rủi ro còn lại đã biết) |
| **[mới]** G-05d | W-LEG-25 (in rồi scan fixture `d5_*`) | thêm cột "đảo thứ tự do Legal" tách khỏi "đảo thứ tự do Docling" |

### G-06 — Hồi quy tự động trên máy có đủ model

| # | Việc | Kỳ vọng |
|---|---|---|
| W-RC (mục 1 của 12D5) | `uv run pytest tests/ -q -p no:cacheprovider -rxXs` | 10 lỗi cũ cùng tên; 0 xpassed |
| **[mới]** G-06a | `uv run pytest tests/review_phase12d8 -q` | 0 failed; mọi `xfail` còn lại ứng với finding chưa sửa. Test strict-xfail đạt sau khi sửa ⇒ gỡ marker |
| **[mới]** G-06b | máy có cache tiktoken thật | 3 test `test_chunking` (`test_cjk_text_is_chunked_by_tokens`, `test_explicit_content_type_plain`, `test_secondary_chunking_for_large_sections`) chạy và đạt |
| W-PIPE, `OCR_FULL_PIPELINE=1` | pipeline OCR đầy đủ với Layout Heron / TableFormer | 55 test bị skip ở Cloud chạy và đạt |

### G-09 — Quy trình thủ công offline trên Ubuntu thử (đường production)

W-FB-*, W-INT-* của 12D5, với Docker và Compose thật, dữ liệu giả. Thêm:

| # | Việc | Kỳ vọng |
|---|---|---|
| **[mới]** G-09a (D8-OFF-13) | chép lệnh từ file `.md` **thô** trong gói, không qua trình hiển thị Markdown | mọi lệnh chạy được, kể cả hai khối `python -c` nhiều dòng (§4, §6) |
| **[mới]** G-09b (D8-OFF-05) | thay một file trong gói đã giải nén rồi sinh lại `SHA256SUMS` | hiện tại §3.4 vẫn đạt — ghi lại; sau khi sửa: bị từ chối |
| **[mới]** G-09c (D8-OFF-10) | rollback sau khi đã đồng bộ mã nguồn (§7.1) | sau rollback: image **và** commit **và** container đang chạy đều là bản cũ |
| **[mới]** G-09d (D8-OFF-14, 08) | làm hỏng việc đọc dữ liệu ở F1 / F2; sửa một bản ghi tại chỗ sau F1 | phép so phải **không đạt** |
| **[mới]** G-09e (D8-OFF-15) | script vận hành `$OPS normal / maintenance` của đơn vị | ID container database không đổi; không `pull`, không `build` kể cả khi compose có `build:` |
| W-FB-09 | khởi động lại máy chủ | boot guard đưa lên đúng image mới |

### G-10 — Tokenizer và artifact OCR offline

W-TOK-01 … 06, W-12D7-06c; `inventory` / `health` của gói trên container thật với `--network none`: bảng mã
`o200k_base` nạp được, model OCR có đủ và khớp SHA-256, `docling_tsv_patch.applied: true`.

### G-11 — Không đổi

W-12D7-06a, 06b, 06d (Auto Full Page on Watermark, Custom Model Manager, PDF Prep); giao diện vi / en.

### G-12 — Updater tự động vẫn ngoài production

| # | Việc | Kỳ vọng |
|---|---|---|
| **[mới]** G-12a | đọc gói đã build: `docs/RELEASE_NOTES.md`, `offline_package.py --help` | dẫn production tới quy trình thủ công; updater ghi rõ EXPERIMENTAL (sau khi sửa D8-OFF-01 / 02) |
| **[mới]** G-12b | biên bản nghiệm thu | không lệnh `update.sh` / `finish.sh` / `rollback.sh` nào được chạy trong đường production |

## Điều kiện để chuyển sang phát hành

Mọi cổng G-01 … G-12 **Đạt** trên cùng một commit; ba blocker D8-03, D8-01, D8-02 đã sửa hoặc đã có quyết định ghi
nhận của chủ dự án; không finding P0 / P1 mới từ Local. Cho tới khi đó: READY FOR RELEASE = NO, READY FOR PRODUCTION = NO.
