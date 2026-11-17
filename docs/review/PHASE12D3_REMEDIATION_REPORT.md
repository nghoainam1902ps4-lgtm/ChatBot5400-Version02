# Phase 12D3 — Báo cáo khắc phục sau audit độc lập (Fable, Phase 12D2)

| | |
|---|---|
| Nhánh | `feature/legal-document-normalization` (PR #50, **Draft**) |
| HEAD được audit | `2ef007417eaca0ce41e7aba2e32a201fa243ebf1` |
| Nhánh audit | `review/phase12-fable-audit` — **không thay đổi**; nội dung được đưa vào nhánh feature bằng merge commit `d28bca8` |
| Baseline | v1.2.0 (`f2fdf2714a7c0b5b196132f71cfc091928befc06`) |
| Kết quả audit | 29 finding: 0 P0 · 6 P1 · 10 P2 · 12 P3 · 1 P4 |
| `VERSION` | vẫn `1.2.0` |
| Trạng thái từng finding (máy đọc được) | [PHASE12D3_FINDING_STATUS.json](PHASE12D3_FINDING_STATUS.json) |

**Không merge. Không phát hành RC. Không triển khai production.** Production không bị đụng tới. Không có PDF nghiệp
vụ, model Agri, secret hay khóa ký nào được đưa lên Cloud hoặc vào Git.

## 1. Tóm tắt

| Mức | Số finding | OPEN | PARTIAL | DEFERRED | FIXED — VERIFIED | FIXED — LOCAL VERIFICATION REQUIRED |
|---|---|---|---|---|---|---|
| P0 | 0 | 0 | 0 | 0 | 0 | 0 |
| P1 | 6 | 0 | 0 | 0 | 0 | **6** |
| P2 | 10 | 0 | 0 | 0 | 4 | 6 |
| P3 | 12 | 0 | 0 | 0 | 5 | 7 |
| P4 | 1 | 0 | 0 | 0 | 1 | 0 |
| **Cộng** | **29** | **0** | **0** | **0** | **10** | **19** |

Cách đọc bảng — để không hiểu nhầm:

- **FIXED** = mã đã sửa, có test hồi quy, test đỏ trước khi sửa và xanh sau khi sửa **ở Cloud**. Không finding nào
  được "tự đóng": việc đóng thuộc về review độc lập Phase 12D4 và nghiệm thu Local.
- **LOCAL VERIFICATION REQUIRED** = phần còn lại chỉ kiểm được trên máy có Docker / PowerShell / model OCR thật /
  SurrealDB thật. **Cả 6 finding P1 đều ở trạng thái này**: chúng vẫn **chặn phát hành** cho tới khi cổng Local tương
  ứng đạt.
- Chưa có gì được xác minh trên **Docker thật, Compose thật, PowerShell, pipeline OCR thật (Layout Heron, TableFormer,
  các engine, Agri), SurrealDB thật, hay một lần cập nhật offline thật**.
- Một mục **tùy chọn** của audit không được làm, có lý do: đóng gói thư mục model vào gói (`--with-artifacts`, F-22) —
  xem §4.

Nguyên tắc đã theo: sửa oracle **trước** normalizer; chép test phản ví dụ của audit sang nhánh feature, gỡ `xfail`
theo từng finding, giữ nguyên thân test và ghi nguồn; không sửa test để né finding; không dùng mock/skip để che lỗi;
không hạ tiêu chí an toàn; không đổi dependency, schema, engine OCR, model, kiến trúc RAG.

## 2. Thứ tự thực hiện và bằng chứng RED → GREEN

| Bước | Việc | Bằng chứng |
|---|---|---|
| 12D3A | Oracle độc lập (T-01), oracle an toàn Docker (T-02), bỏ tham số hóa rỗng (T-03) | `phase12d3/red_new_oracle_before_fix.txt`: oracle mới trên implementation **chưa sửa** ⇒ **83 failed / 297 passed**; `phase12d3/oracle_before_remediation.json`: 53 đơn vị / 170 token xóa nhầm, 6 nối sai, 11 trường trọng yếu sai |
| | Test phản ví dụ của audit, gỡ `xfail` | `phase12d3/red_audit_tests_before_fix.txt`: **18 failed / 14 passed** (`--runxfail`) trên mã chưa sửa |
| 12D3B | Normalizer v1.1.0 (F-01, F-02, F-03, F-06, F-10, F-17), metadata Source (F-07), F-15, F-16, F-18 | `phase12d3/oracle_after_remediation.json`: 0 / 0 / 0 / 0; 385 test normalizer + 35 test pipeline xanh |
| 12D3C | Build gói và đồng bộ mã nguồn (F-04, F-05, F-27) | git thật; `tests/test_offline_package.py` |
| 12D3D | Máy trạng thái (F-08, F-09, F-11, F-13, F-23, F-24) | Docker giả lập có trạng thái |
| 12D3E | An toàn (F-12, F-14, F-20, F-21, F-22, F-25, F-26) | tar / SHA-256 / ssh-keygen thật + Docker giả lập |
| 12D3F | Còn lại + benchmark mới + tài liệu | §5–§6 |

Sau khi sửa: `tests/review_phase12d2` **32 passed, 0 xfail, 0 xpass, 0 skip**.

## 3. Bảng 29 finding

Chi tiết đầy đủ (root cause, bản sửa đề xuất, before/after, mã tham chiếu, từng test, cổng Local) nằm trong
[PHASE12D3_FINDING_STATUS.json](PHASE12D3_FINDING_STATUS.json). Bảng dưới là bản rút gọn. "Chặn phát hành" ở cột cuối:
**Có** = audit đánh dấu release blocker; mọi mục "LOCAL" còn chặn cho tới khi cổng Local đạt.

Ký hiệu trạng thái: **V** = FIXED — VERIFIED · **L** = FIXED — LOCAL VERIFICATION REQUIRED.

### P1

| ID | Vấn đề | Bản sửa thực tế | Test chính | TT | Cổng Local | Chặn |
|---|---|---|---|---|---|---|
| F-01 | Dòng lặp hợp lệ (Đơn vị tính, tên đơn vị, ghi chú ký…) bị xóa như header/footer | Không bao giờ bỏ dòng chữ lặp theo tần suất; chỉ item layout gắn nhãn PAGE_HEADER/FOOTER; giữ **mọi** lần xuất hiện; cảnh báo `repeated_line_kept` | `test_f01_*` (audit), `test_repeated_text_lines_are_reported_never_removed`, fixture f25 f26 f35 f37 | L | W-LEG-01, 02, 13; W-RC-01 | Có |
| F-02 | Năm, số khoản, số lượng bị xóa như số trang | ≥ 3 trang **và** ≥ 60%, cùng dải, cùng vị trí ngang / lẻ-chẵn, ngoài thân, giá trị phù hợp; 1–2 trang giữ + cảnh báo | `test_f02_*` (audit), 9 test ngưỡng, fixture f27 f28 f33 f34 f36 | L | W-LEG-03, 04, 05 | Có |
| F-03 | Nối footnote / footer / điểm `a.` `a/` `đ.` vào đoạn trước | `_join_refusal`: marker nhiều cấp, footnote, đoạn thân bị cắt thật, cùng cột, không bảng/ảnh/trang trắng; từ chối có lý do | `test_f03_*` (audit), 6 test nối, fixture f29 f30 f31_* f38 f39 | L | W-LEG-06, 07, 10, 11 | Có |
| F-04 | Lệnh build luôn thất bại ở `git bundle` | Ref tạm có tên, verify, list-heads, xóa ref trong `finally`, bundle trước Docker, dọn stage khi lỗi | `test_f04_*` (audit), 6 test build, `build-package.sh` chạy thật | L | W-OFF-01, 02, 03 | Có |
| F-08 | Lần cập nhật thứ hai dùng lại backup cũ | Attempt có mã, baseline, tag rollback, backup + xác minh riêng; lưu trữ journal cũ; trạng thái chưa quyết định chặn update | `test_f08_*` (audit), 10 test attempt | L | W-OFF-17, 18 | Có |
| F-11 | `docker compose up -d` thường âm thầm đưa bản cũ trở lại | Phát hiện lệch (mã thoát 7), `compose-command.txt`, ghim tùy chọn `pin` (dry-run / apply / undo) không sửa `.env` | 9 test drift / pin | L | W-OFF-14, 15, 16 | Có |

### P2

| ID | Vấn đề | Bản sửa thực tế | Test chính | TT | Cổng Local | Chặn |
|---|---|---|---|---|---|---|
| F-05 | `--sync-source` không fetch được commit phát hành | Fetch đúng một ref ghi trong manifest; kiểm commit; chỉ fast-forward; ghi commit cũ | `test_f05_*` (audit), 8 test git thật | V | W-OFF-26 (xác nhận) | Có |
| F-06 | Ảnh < 15% trang bị bỏ không dấu vết | Ngưỡng 4% và phép bỏ được ghi; ≥ 4% giữ + cảnh báo có trang/bbox; giữ caption, chữ và bảng trong ảnh | `test_f06_*` (audit), 4 test ảnh, fixture f32 f40 | L | W-LEG-08; W-RC-02 | Có |
| F-07 | Không lưu bằng chứng chuẩn hóa | Bản ghi trong `source.asset.extraction` (không migration), API, nhãn trên trang Source cho applied / failed / skipped | 7 test backend, 4 test frontend | L | W-LEG-16; W-STD-06 | Có |
| F-09 | finish / rollback báo thành công không kiểm tra | Health check đầy đủ; `finish_failed` / `rollback_failed`, mã 5 | `test_f09_*` (audit), 4 test | L | W-OFF-19 | Có |
| F-10 | Chi phí bậc hai, không có ngân sách thời gian | Không `delete_items` (INVISIBLE), chỉ mục hình học, ngân sách 30 s ⇒ fallback | 7 test hiệu năng / giới hạn | V | W-LEG-14 (ghi nhận) | Có |
| F-20 | So image ID giữa hai image store | Manifest ghi digest cấu hình + layer; nhận diện bằng ID / digest / layer; journal ghi ID phía máy chủ | 5 test | L | W-OFF-04, 05, 06 | Có |
| F-21 | "DB không bị đụng" chỉ kiểm trên cấu hình | `docker inspect` container DB trong baseline (trước sync) và sau mỗi `up`; schema + số bản ghi; so toàn bộ cấu hình | 6 test | L | W-OFF-13 | Có |
| F-22 | Không kiểm model offline; bỏ qua kết quả chép RapidOCR | Readiness trong preflight; kiểm kết quả RapidOCR; so danh sách file model trước/sau; inventory + guard tiktoken | 10 test công cụ + 4 test `token_utils` | L | W-OFF-08, 21, 22; W-RAG-06 | Có |
| T-01 | Oracle "0 từ bị mất" vòng tròn | Oracle trên ground truth khai báo; đo deletion / insertion / merge / reordering / trường trọng yếu / bảng | 7 test oracle | V | — | Có |
| T-03 | Tham số hóa rỗng, fixture nhỏ, đường mã không có test | Lọc theo khóa; 45 fixture; tài liệu 100–300 trang; test cho mọi đường mã chạy được ở Cloud | 385 + 166 + 35 test | V | W-PIPE | Có |

### P3 / P4

| ID | Vấn đề | Bản sửa thực tế | Test chính | TT | Cổng Local | Chặn |
|---|---|---|---|---|---|---|
| F-12 | Giá trị manifest / `--to-image` không kiểm định dạng | Kiểm mọi trường; override trong ngoặc kép; so toàn bộ cấu hình | `test_f12_*` (audit), 21 ca manifest | V | — | Có |
| F-13 | Journal hỏng ⇒ traceback | Ghi nguyên tử + fsync + bản sao; dừng với hướng dẫn, không tự tạo lại | `test_f13_*` (audit), 4 test | V | W-OFF-20 (xác nhận) | Có |
| F-14 | Entry trùng; giải nén trước khi kiểm chữ ký; không kiểm dung lượng; cây dở | Xác thực trước; từ chối trùng; kiểm dung lượng; thư mục tạm; dọn khi lỗi | `test_f14_*` (audit), 7 test | V | — | Có |
| F-15 | Legal đổi đường OCR của PDF | Cảnh báo trong log khi Legal ép lớp native; nhãn chế độ trên trang Source; phép so vào checklist | 1 test | L | W-RC-05 | Có |
| F-16 | Legal mất định dạng phân cấp | Component `p` nhận diện marker để định dạng theo cấp | 4 test frontend | L | W-LEG-17 | Có |
| F-17 | Ký tự thoát Markdown đi vào full_text / chunk / embedding | Văn bản lưu không thoát marker; thoát lúc hiển thị; 26 vector dùng chung Python / TypeScript | 5 test | L | W-RAG-01..04 | Có |
| F-23 | legal-on/off đưa ứng dụng vào bảo trì | Giữ chế độ mạng hiện tại; so cấu hình; health check | 4 test | L | W-OFF-23 | Có |
| F-24 | Rollback theo tag, không khôi phục mã nguồn, journal bị ghi đè | Rollback theo image ID; khôi phục mã nguồn khi an toàn; chặn mọi trạng thái chưa quyết định | 8 test | L | W-OFF-16, 26, 27 | Có |
| F-25 | `docker load` gắn lại tag khác | Đọc file image trước khi load: đúng một tag đã duyệt; preflight kiểm xung đột tag | 6 ca | L | W-OFF-06, 07 | Có |
| F-26 | Chuỗi tin cậy và cấu hình | Báo cáo verify gắn hash + kiểm lại; `mktemp`; quyền file; bỏ `CB5400_*`; không proxy; `.sha256` không phải kênh tin cậy | 8 test | V | W-OFF-24, 25 (xác nhận) | Có |
| F-27 | Không build được 1.3.0-rc.1 từ HEAD | `check-version` trước mọi lệnh Docker ở cả hai wrapper | 7 ca | L | W-OFF-01 | Có |
| T-02 | Oracle an toàn Docker luôn đúng | Mỗi điều kiện một assert; `up` phải đúng bằng lệnh an toàn; chứng minh oracle thất bại với 19 dạng | 4 test | V | — | Có |
| F-18 | PDF có byte lạ trước `%PDF-` | Tìm trong 1024 byte đầu; trạng thái `skipped` được lưu và hiển thị | 2 test | V | — | Có |

## 4. Những gì KHÔNG làm, và vì sao

| Việc | Lý do |
|---|---|
| Đóng gói thư mục model vào gói offline (`build --with-artifacts`, mục *tùy chọn* trong bản sửa đề xuất của F-22) | Giữ quyết định D-35: model ở lại volume của máy chủ, không phân phối lại (giấy phép, dung lượng), Agri là tài sản nội bộ không bao giờ rời máy chủ. Phần **kiểm tra** của F-22 đã làm đầy đủ; máy chủ thiếu model bị preflight từ chối chứ không được gói tự bổ sung |
| Tiêu chí "footnote có cỡ chữ nhỏ hơn" cho F-03 | `DoclingDocument` không mang cỡ chữ theo dòng; các tiêu chí khác (mẫu footnote, dải cuối, bề rộng cột, footer bên dưới) đã bao phủ các phản ví dụ |
| Sửa việc Docling tự nối TEXT→TEXT qua trang / tự bỏ gạch nối | Hành vi upstream của Docling 2.129, có ở cả chế độ Tiêu chuẩn và v1.2.0; không được đổi Docling. Ghi ở W-RC-04 |
| Sửa thứ tự đọc hai cột (fixture f12: 1 lỗi thứ tự ở cả Standard và Legal) | Thứ tự đọc là của Docling; normalizer không sắp xếp lại (chủ ý) |
| Tự sửa `.env` / file compose để ghim image | Ràng buộc dự án: công cụ không đọc, không ghi file có thể chứa secret. Thay bằng phát hiện lệch + ghim tách biệt do người vận hành quyết định |
| Trích dẫn theo trang | Hệ thống không lưu provenance theo chunk; bản ghi chuẩn hóa chỉ nêu trang của phép biến đổi |
| Đổi `VERSION` sang 1.3.0 | Theo chỉ thị: giữ 1.2.0. Gói thử nghiệm mang tên `1.2.0-phase12.N` |
| Tách commit công cụ offline thành 4 commit theo nhóm | `offline_package.py` được cấu trúc lại toàn bộ (định dạng gói 2) nên bốn nhóm (build, transaction, pin/drift, safety) nằm trong một commit có mô tả chia theo nhóm; test nằm ở commit riêng |

## 5. Thay đổi hành vi người dùng cần biết (so với Phase 12 trước audit)

1. Legal **bảo thủ hơn**: trên bộ fixture, số artifact được loại giảm từ 45/47 xuống 24/47 và số phép nối từ 5/5
   xuống 3/5, đổi lại **0** xóa nhầm (trước: 53 đơn vị) và **0** nối sai (trước: 6).
2. Văn bản 1–2 trang giữ số trang nghi ngờ; khoản bị cắt qua trang ở các văn bản này không được nối.
3. Dòng chữ lặp lại (kể cả header chạy mà layout không gắn nhãn) được giữ trong nội dung, kèm cảnh báo.
4. Ảnh không chữ từ 4% diện tích trang trở lên để lại `<!-- image -->`.
5. Văn bản lưu của Source Legal không còn `\` trước marker; hiển thị không đổi.
6. Trang Source có nhãn chế độ chuẩn hóa.
7. Gói offline: định dạng 2; `status` có thể trả mã 7; `finish` / `rollback` có thể trả mã 5 khi kiểm tra không đạt;
   mỗi lần cập nhật đều backup lại.

Chế độ **Tiêu chuẩn** không đổi: `test_convert_file_standard_is_byte_identical` giữ nguyên và đạt; Source Tiêu chuẩn
được lưu không có khóa mới.

## 6. Kết quả kiểm thử và chất lượng

- Hồi quy: [PHASE12D3_REGRESSION_REPORT.md](PHASE12D3_REGRESSION_REPORT.md).
- Chất lượng BEFORE / AFTER với oracle đã sửa: [PHASE12D3_QUALITY_BENCHMARK.md](PHASE12D3_QUALITY_BENCHMARK.md).
- An toàn công cụ offline: [PHASE12D3_OFFLINE_SAFETY_REPORT.md](PHASE12D3_OFFLINE_SAFETY_REPORT.md).
- Nghiệm thu Local: [PHASE12D3_WINDOWS_ACCEPTANCE_CHECKLIST.md](PHASE12D3_WINDOWS_ACCEPTANCE_CHECKLIST.md).
- Bàn giao cho review 12D4: [PHASE12D3_HANDOVER.md](PHASE12D3_HANDOVER.md).

## 7. Tài liệu Phase 12 đã cập nhật

| Tài liệu | Thay đổi |
|---|---|
| `docs/ocr/PHASE12D_QUALITY_BENCHMARK.md`, `PHASE12D_TEST_REPORT.md` | đánh dấu **đã bị thay thế**; số liệu cũ không còn được trích dẫn |
| `docs/ocr/PHASE12B_LEGAL_NORMALIZATION_DESIGN.md` | bảng khác biệt v1.0.0 → v1.1.0 ở đầu tài liệu |
| `docs/ocr/PHASE12C_IMPLEMENTATION_REPORT.md`, `PHASE12D_SECURITY_REVIEW.md`, `PHASE12_CLOUD_HANDOVER.md`, `PHASE12E_WINDOWS_LOCAL_TEST_GUIDE.md` | ghi chú cập nhật trỏ tới tài liệu 12D3 |
| `docs/ocr/DECISIONS.md` | D-36 (sửa đổi D-34), D-37 (sửa đổi D-35) |
| `docs/deployment/OFFLINE_UPDATE_*.md` (5 file) | viết lại / cập nhật theo định dạng gói 2: xác thực trước khi giải nén, attempt, bảng gián đoạn đã sửa, drift + pin, `mktemp`, `.sha256` không phải kênh tin cậy, phiên bản gói thử |
| `CHANGELOG.md`, `docs/ocr/OCR_RELEASE_NOTES_V1.3.0_RC1.md` (nháp) | cập nhật, vẫn ghi rõ CHƯA phát hành |
| `docs/ocr/phase12/benchmark_synthetic.json` | tạo lại, schema /2 |
