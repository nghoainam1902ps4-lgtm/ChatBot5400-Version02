# Phase 12D12 — Re-review độc lập có trọng tâm trước nghiệm thu Local

**Kết luận tại `18eeecbfd2cc42549e57cdb866a405083b41a657`: 8/9 phát hiện D10 đã sửa đúng nguyên nhân gốc, 1/9 (D10-06) mới sửa một phần.** Cổng Standard expected-diff ở chế độ release vẫn trả mã 0 cho một sai khác mà chính bằng chứng OCR của candidate phủ nhận (D12-03). Mã runtime (PDF, embedding, bảo toàn chữ, gói offline, fingerprint) không còn blocker đã tái hiện. Candidate đủ điều kiện chuyển sang nghiệm thu Local **có điều kiện**; chưa đủ điều kiện phát hành.

Repository `nghoainam1902ps4-lgtm/ChatBot5400-Version02`, PR #50 (Draft). Mọi ref đã được xác minh trước khi review:

| Ref | SHA | Kiểm tra |
|---|---|---|
| Candidate (`feature/legal-document-normalization`) | `18eeecbfd2cc42549e57cdb866a405083b41a657` | đầu nhánh feature trên remote, không đổi sau review |
| Candidate trước khi sửa | `2cc824f66638d6db229993b4cc98948300e6bd8b` | tổ tiên của `18eeecb` và của `abbcc37` |
| Audit độc lập (`review/phase12d10-codex-targeted`) | `abbcc37c89f5c72f14bcd3aadd52c70817f36120` | đầu nhánh review 12D10 |
| Baseline v1.2.0 / default branch | `f2fdf2714a7c0b5b196132f71cfc091928befc06` | tag `v1.2.0`, tổ tiên của candidate |
| Nhánh review 12D12 | `claude/jolly-knuth-rivla0` | xuất phát từ `18eeecb`; chỉ thêm hồ sơ review và test kiểm soát |

Phạm vi: D10-01 đến D10-09, RB-1 và hồi quy trực tiếp của các bản sửa. Đã đọc toàn bộ hồ sơ `PHASE12D10_*`, `PHASE12D11_*`, hợp đồng tích hợp, quy trình thủ công, D-32, và diff `2cc824f..18eeecb` (48 file; frontend không đổi). Không sửa mã runtime, không đụng nhánh feature, không merge, không đổi `VERSION`. Chỉ dùng fixture tổng hợp.

Môi trường review: container Linux (Ubuntu 24.04, kernel 6.18), CPython 3.12.3, Docling 2.129.0, docling-core 2.96.0, content-core 2.0.7, pandas 3.0.0, RapidOCR 3.9.2, SDK SurrealDB 1.0.8, Tesseract 5.3.4 (`eng`, `vie`, `osd`). Ngoài engine nhúng, review dùng **SurrealDB server 2.3.10 độc lập** (binary phát hành chính thức, RocksDB và SurrealKV, cổng loopback riêng). Không có Docker daemon: mọi mục cần Docker thật là `NOT_VERIFIED_ENVIRONMENT` và chuyển sang Local. Bảng mã `o200k_base` lấy từ mirror, SHA-256 `446a9538…fb1a2d` khớp giá trị ghim trong tiktoken.

## R01 — Red/green độc lập: ĐẠT

File `tests/test_phase12d10_review_controls.py` lấy nguyên từ `abbcc37` (SHA-256 `86f0101a…ecd7074`), đặt vào worktree sạch của từng commit.

| Lượt | Commit | Kết quả |
|---|---|---|
| Test gốc, có marker | `2cc824f` | 3 passed / 13 xfailed |
| Test gốc, `--runxfail` | `2cc824f` | **13 failed / 3 passed** |
| Test gốc, `--runxfail` | `18eeecb` | **16 passed** |
| Test gốc, có marker strict | `18eeecb` | 13 failed (XPASS strict) / 3 passed — marker lật đúng như thiết kế |
| Bản trên nhánh feature | `18eeecb` | 16 passed |

`git diff abbcc37 18eeecb -- tests/test_phase12d10_review_controls.py` chỉ xoá 12 decorator `xfail` (13 ca do một ca tham số hoá). Input, fixture và assertion giữ nguyên. Các test có sẵn khác bị sửa trong `18eeecb` (`test_approval_workflow`, `test_offline_package`, `test_offline_d8`, `test_offline_real_docker`, kiểm AST của vòng OCR) đều là điều chỉnh theo hợp đồng mới (xoá Source trong giao dịch, fingerprint có digest nội dung, một dòng chẩn đoán chỉ chạy khi thu bằng chứng); không có assertion nào bị nới.

## Kết quả theo phát hiện

| ID | Mức | Kết quả 12D12 | Tóm tắt |
|---|---|---|---|
| D10-01 | P1 | **VERIFIED_FIXED** | Callback Docling của content-core được bọc sau bước tải/định tuyến; PDF chỉ chạy khi nhóm bản vá chữ đã áp dụng (`required=True`). |
| D10-02 | P1 | **VERIFIED_FIXED** | Verdict được kiểm trước serialization trên cả hai đường; embedding sinh vector trước, thay trong một giao dịch có hàng rào revision. Đã chạy trên server độc lập. |
| D10-03 | P1 | **VERIFIED_FIXED** | Chỉ khép gạch nối khi có bằng chứng xuống dòng cùng lề; mọi trường hợp mơ hồ giữ khoảng trắng và giữ đủ dấu gạch. |
| D10-04 | P2 | **VERIFIED_FIXED** | Footnote gắn kèm đi qua text serializer đang dùng; `#`, `>` ở Legal được escape, không mất và không lặp. Kèm sai lệch không chặn D12-02. |
| D10-05 | P1 | **VERIFIED_FIXED** | Chế độ release so byte thật và kiểm đủ inventory manifest ở cả hai phía. |
| D10-06 | P1 | **PARTIAL** | Hai phản ví dụ gốc đã đóng (model khác, orientation rời). Văn bản phía candidate trong một span vẫn chưa được ràng buộc với dòng TSV của nó → D12-03. |
| D10-07 | P1 | **VERIFIED_FIXED** | Mỗi lần xuất hiện có gạch nối cần định danh dòng, thứ tự và vị trí riêng; không còn dùng phép đếm tổng. |
| D10-08 | P2 | **VERIFIED_FIXED** | Hash đã chuẩn bị được giữ cho tới khi có cặp hợp lệ; không tự tạo checksum mới để "chứng nhận" archive. Còn ba điểm tồn mức thấp. |
| D10-09 | P1 | **VERIFIED_FIXED** | Fingerprint băm nội dung tám bảng; F0 8/8, N0 đạt, cả trên server độc lập. Phạm vi 14 bảng còn lại là cổng Local. |

## R02 — Toàn vẹn PDF (D10-01, D10-02 phần extraction)

Đường thực thi đã lần theo mã, không dựa vào báo cáo:

```text
API async/sync → hàng đợi → process_source_command → content_process
  OCR đã chọn (upload/URL) → build_converter [apply_text_preservation(required=True)]
        → convert_document → reject_incomplete → serialize → _require_text
  native (upload/URL)     → content-core tải + định tuyến MIME → extract_docling (đã bọc)
        → _is_pdf → _extract_native_pdf [required=True] → reject_incomplete → _export → _require_text
  → save_source (một giao dịch) → vectorize (job riêng)
```

- **Guard không bị vòng qua.** `content_core.extraction._extract_file` gọi `extract_docling` qua biến toàn cục của module đã bị thay; `_route_for_mime` đọc cùng biến đó. Wrapper kiểm phiên bản `2.0.7` và SHA-256 mã nguồn của hàm dispatch lẫn hàm gốc; sai lệch ⇒ từ chối mọi PDF (`TextPreservationPatchError`, là `ValueError`, không retry). Không còn nơi nào khác trong `api/`, `commands/`, `open_notebook/` gọi Docling qua content-core.
- **Phủ đủ các đường PDF.** Native Content Core, OCR đã chọn, RapidOCR mặc định, OCR tắt, PDF có text layer, upload, URL: tất cả hội tụ về `reject_incomplete` trước serialization. Converter native được tạo mới mỗi lần; converter cũ của Docling dùng method đã vá ở cấp class. Đường async, sync và worker dùng chung một command.
- **Các trường hợp bị từ chối** (đã chạy): `PARTIAL_SUCCESS`, `SUCCESS` có lỗi, thiếu status, ngoại lệ chuyển đổi, lỗi nhận dạng đã hết retry, nội dung rỗng hoặc chỉ có placeholder ảnh (kể cả đầu ra HTML/JSON). `IncompleteConversionError` là `ValueError` nên job dừng, không lưu text, không enqueue embedding.
- **Reprocess thất bại** giữ nguyên Source và vector cũ (control gốc của audit đạt, cả trên server độc lập).
- **Timeout 300 giây của API sync.** `execute_command_sync` gửi lệnh vào hàng đợi rồi polling; quá hạn ném `TimeoutError`. API xoá Source (một giao dịch, kèm `reference`) rồi trả lỗi. Worker hoàn tất muộn gặp `Source.get → None` hoặc `THROW` trong giao dịch publish ⇒ `ValueError`, không gì được khôi phục.

Giới hạn đã xác nhận, **không phải blocker** vì đều fail-closed hoặc không tạo dữ liệu thiếu:

1. Nếu lệnh xoá Source lúc timeout gặp lỗi DB, Source còn lại và kết quả OCR muộn (đã qua kiểm verdict, đầy đủ) vẫn được publish dù client đã nhận lỗi. Không có text thiếu; cần diễn tập Local (D12-L5).
2. Ngoại lệ khác `TimeoutError`/`CancelledError` khi polling (ví dụ DB lỗi) không xoá Source — hành vi có từ trước.
3. Hai nhóm bản vá upstream (chữ, Tesseract) không cài trong một giao dịch chung; nhóm Tesseract bị từ chối thì conversion dừng, nhóm chữ đã kiểm vẫn còn trong process. Fail-closed.
4. `stderr=PIPE` vẫn có thể đệm nhiều hơn 4096 byte; 4096 chỉ là giới hạn phân loại.
5. Ảnh scan (PNG/JPEG/TIFF) đi đường native của content-core **không** qua `reject_incomplete` (wrapper chỉ nhận PDF). Đây là hành vi của baseline (D-32), ngoài phạm vi D10 "đường PDF"; đường OCR đã chọn vẫn kiểm verdict cho ảnh.
6. Sai lệch hash dispatch của content-core làm dừng mọi nguồn file/URL (kể cả không phải PDF). Fail-closed, phụ thuộc lockfile.

## R03 — Giao dịch embedding (D10-02 phần embedding)

Đã xác minh trong `commands/embedding_commands.py`, `open_notebook/database/repository.py`, `open_notebook/domain/notebook.py`:

- Sinh và kiểm vector (số lượng, số chiều, kiểu số, hữu hạn) **trước** mọi thao tác ghi; provider lỗi không chạm vector cũ.
- `DELETE` + `INSERT` nằm trong một `BEGIN … COMMIT`; `repo_transaction` đọc phản hồi thô và coi bất kỳ statement nào khác `OK` là thất bại. Lỗi ràng buộc lúc `INSERT` hoàn tác cả `DELETE`.
- Hàng rào: Source còn tồn tại, `full_text` đúng bằng văn bản đã embed, `updated` (làm tròn micro giây) đúng bằng revision đã nạp; sau đó ghi `updated` để mọi job cùng revision va chạm khi ghi. Trường `updated` của `source` có `VALUE time::now()` nên mọi lệnh ghi vào Source đều đổi revision.
- Publish text mới và thu hồi vector cũ trong cùng giao dịch (`repo_update`). Save chỉ có metadata bỏ `full_text` khỏi `MERGE`, nên bản sao cũ không ghi đè text.
- Xoá Source và gỡ liên kết notebook chung một giao dịch; chỉ xoá `reference` có `in` là Source đó.

**Phân biệt engine nhúng và server.** Bộ test 12D11 chạy trên engine nhúng của SDK. Review chạy lại nguyên các bộ đó trên **server 2.3.10 (RocksDB)**: `test_phase12d11_embedding_transactions`, `test_phase12d11_offline_fingerprint`, `test_phase12d10_review_controls`, `test_approval_workflow`, `test_phase12d11_pdf_integrity`, `test_phase12d9_ocr_failure_safety` (trừ một ca timing Tesseract không dùng DB) — **128 passed**, xác nhận qua 31 namespace thử nghiệm được tạo trên server.

Phản ví dụ đồng thời do review tự viết (4 job nạp cùng revision, cùng commit một lúc):

| Engine | Kết quả |
|---|---|
| Server 2.3.10, RocksDB (3 lượt) | đúng **một** bộ chunk; job còn lại bị từ chối revision hoặc lỗi xung đột ghi có thể retry |
| Server 2.3.10, SurrealKV (3 lượt) | đúng một bộ chunk |
| Engine nhúng của SDK 1.0.8 (`surrealkv://`) | **cả 4 job thành công, 8 dòng (4 bộ chunk trùng)** |

Hàng rào dựa vào cơ chế phát hiện xung đột ghi của storage engine; engine nhúng không cung cấp cơ chế đó giữa các kết nối. Vì vậy bằng chứng "embedded PASS" của 12D11 **không** chứng minh an toàn đồng thời; bằng chứng server của review chỉ áp dụng cho 2.3.10. Production dùng tag trôi `surrealdb/surrealdb:v2` với RocksDB: phiên bản và engine thực tế phải được ghi nhận và chạy lại control ở Local (D12-L2).

**D12-01 (P3, không chặn, sai lệch do bản sửa).** Bất kỳ lệnh ghi nào vào bản ghi Source giữa lúc job embedding nạp Source và lúc commit (đổi tiêu đề, sửa topics, thao tác duyệt) làm job kết thúc `Source changed before publication`. Lỗi này là `ValueError` nên không retry và lệnh vẫn ở trạng thái hoàn tất với `success=false`. Văn bản không đổi nhưng không có vector cho tới khi embed lại thủ công. Tái hiện trên cả engine nhúng và server. Không sai dữ liệu, có thể khôi phục, cửa sổ bằng thời gian sinh embedding. Tiêu chí sửa tối thiểu: hàng rào chỉ dừng vĩnh viễn khi Source bị xoá hoặc `full_text` đổi; trường hợp chỉ đổi revision phải retry được.

## R04 — Bảo toàn chữ (D10-03, D10-04, D8-01)

**Gạch nối.** Ma trận 12 ca hình học của review (`same_line_flags` + `sanitize_text` thật của Docling 2.129.0):

| Trường hợp | Đầu ra |
|---|---|
| Ô theo dòng, cùng lề, xuống dòng | `05/2024/TT-BNNPTNT` |
| Ô theo từ, xuống dòng | `05/2024/TT-BNNPTNT` |
| Số 0 đầu, số hiệu lặp | `05-007/QD`; `12-34 12-34` |
| Cùng dòng (kể cả lệch dọc nhỏ) | `VT- KHTC` |
| Cột khác, thấp hơn (ca D10-03) / cùng baseline | `12/AB- TERM` |
| Cuối cột phải → đầu cột trái qua gutter rộng | `12/AB- TERM` |
| Ô kế nằm phía trên / cách 5 dòng | `12/AB- TERM` |
| Dòng đầu thụt lề, tiêu đề căn giữa, gạch không dính chữ | giữ khoảng trắng |

Không ca nào nối chữ qua cột, mất dấu gạch hay sinh ký tự mới. Giới hạn theo hướng an toàn: số hiệu xuống dòng trong tiêu đề căn giữa, dòng đầu thụt lề hoặc sau một khoảng trống lớn trong dòng sẽ có thêm một khoảng trắng (`TT- BNNPTNT`). Hai cột có gutter hẹp hơn hai lần chiều cao chữ và được layout gom vào cùng một cluster theo hàng ngang vẫn có thể khép — khi đó thứ tự đọc đã sai từ trước.

**Footnote.** Footnote gắn bảng mở đầu bằng `#` hoặc `>` ở Legal được ghi `\#`, `\>`, đúng một lần, cùng dạng với đoạn thân. Tài liệu không phải PDF/ảnh giữ serializer upstream. Ở Standard, footnote gắn kèm giữ hành vi upstream (`#` vẫn là heading) như footnote rời.

**D8-01.** Control thứ tự ba cột/khổ trang hỗn hợp của audit vẫn đạt.

**D12-02 (P3, không chặn, chỉ ở Legal — mặc định tắt).** Nhánh sửa D10-04 còn escape thêm `\ ` `` ` `` `*` `_` `[` `]` `~` và ký hiệu khoản đầu dòng cho **mọi** footnote ở Legal (cả footnote rời, vốn không thuộc D10-04):

```text
thân văn bản : 1. Tai khoan TK_VND_01 theo [Dieu 5]
footnote     : 1\. Tai khoan TK\_VND\_01 theo \[Dieu 5\]      (tại 2cc824f: như thân văn bản)
```

Ký tự in không mất, nhưng text lưu của Legal không còn "như bản in" (F-17, Phase 12D5) và khác với thân văn bản; chunk/RAG nhận thêm dấu `\`. Tiêu chí sửa tối thiểu: footnote chỉ qua `escape_literal_block_syntax` như đoạn thân.

## R05 — Standard expected-diff (D10-05, D10-06, D10-07)

Đạt ở chế độ `--release`:

- So byte thật; `canonical()` chỉ còn ở chế độ chẩn đoán. Control LF/CRLF, BOM, NBSP, newline cuối đều khác 0.
- Inventory manifest ở cả hai phía: thiếu ở cả hai, thừa, trùng, hash sai, conversion lỗi ⇒ mã 3.
- Kiểm commit/image của candidate, commit baseline chính thức, run ID, đồng nhất engine/model/config theo từng tài liệu; TSV phải mang đúng invocation, trang, crop và model. `orientation.jsonl` ⇒ NOT VERIFIED.
- G-H1: mỗi dòng TSV có gạch nối cần một span riêng, đúng thứ tự, dùng một lần; 8 control bổ sung đều trả mã 2. Không còn dùng số đếm tổng.
- Thứ tự mã thoát: 1 > 3 > 2 > 0; chế độ release không bao giờ trả 1 (hồi quy thường ra 2).
- Producer và comparator cùng dùng offset ký tự Python trên cùng một chuỗi, trang đánh số từ 1, toạ độ gốc trên-trái. Các lệch pha tìm được đều fail-closed.

**D12-03 (P1 đối với cổng nghiệm thu; phần còn lại của D10-06).**

1. *Đường mã.* `scripts/ocr/phase12_standard_diff.py::verify_bound_output`: phía baseline được dựng lại từ các dòng TSV (`_upstream_join(old_cells)` phải bằng `v120_text`), nhưng phía candidate chỉ cần bằng `element["text"]` do chính candidate ghi. `cell["raw"]` được so với dòng TSV, còn `cell["text"]` và chuỗi đã ghép thì không. Vòng dò ô `break` khi lệch thay vì từ chối và không kiểm đã đi hết span. `_tsv_cause` gán `tsv` cho mọi khác biệt còn lại.
2. *Điều kiện.* Bước ghép chữ của candidate tạo token mà không dòng OCR nào có, hoặc làm rơi token, trong một span mà baseline vẫn dựng lại được.
3. *Hậu quả.* G-04 trả mã 0, lớp `expected TSV fix`, G-H1 `verified` cho một candidate đổi chữ số hoặc làm rơi phủ định trong văn bản pháp lý — đúng loại hồi quy mà cổng này phải bắt.
4. *Phản ví dụ* (đã chạy, Tesseract + Docling thật, exporter và comparator nguyên trạng; chỉ tiêm lỗi vào bước ghép của candidate sau khi xuất baseline):

   ```text
   before: Điều 5, Hiệu lực thi hành / Bên A không chịu trách nhiệm bồi thường
   after : Điều 6, Hiệu lực thi hành / Bên A chịu trách nhiệm bồi thường
   TSV của candidate có "5," và "không"; không có "6"
   release rc: 0   class: expected TSV fix   hyphen_occurrence_status: verified
   ```

   Ba biến thể tổng hợp (đổi chữ số, rơi token, thêm mệnh đề không có ô nguồn) cũng cho `expected TSV fix`. Chế độ cũ trả 0 trên cùng lượt chạy: lỗ hổng có từ trước 12D11 và đường release chưa đóng.
5. *Tiêu chí sửa tối thiểu.* Một span thay đổi chỉ được chấp nhận khi: text của mọi ô bằng dòng TSV mà ô đó trỏ tới; vòng dò đi hết span, lệch hoặc thừa ⇒ NOT VERIFIED; mỗi khác biệt so với baseline là một dòng có dạng upstream khác dạng đã vá hoặc một phép khép gạch nối; footnote gắn kèm trỏ tới phần tử nguồn đã ghi. Bốn control `D12-03` phải trả NOT VERIFIED. Có thể sửa hoàn toàn trong comparator.

Phạm vi ảnh hưởng: công cụ nghiệm thu, không phải mã runtime. Với bằng chứng trung thực, token có gạch nối vẫn được bảo vệ (lệch ở token gạch nối ⇒ NOT VERIFIED).

Ghi nhận khác, không chặn:

- **Khả năng đạt mã 0 trên văn bản thật thấp.** Với pipeline thật, 4/7 tài liệu tổng hợp có số hiệu gạch nối nằm trong tiêu đề mục, list item, footer trang hoặc sau một token bị escape cho ra NOT VERIFIED (producer không phát span/hyphen mapping cho các loại đó); bảng và đoạn nối qua trang tương tự theo mã. Yêu cầu D11-W05 "mã 0 cho mọi tài liệu" nhiều khả năng không đạt trên 22 PDF pháp lý. Fail-closed, nhưng cần quyết định của chủ sở hữu về bằng chứng thay thế cho tài liệu NOT VERIFIED.
- Export không có `--image-id` và so không có `--release` vẫn trả 0 theo đường chẩn đoán, không ràng buộc; báo cáo không ghi chế độ. Checklist Local bắt buộc `--release`.
- Manifest baseline mang cùng image ID với candidate hoặc `evidence: true` không bị từ chối (lỗi thao tác).
- Thư mục `tesseract/` là symlink: TSV được đọc mà không vào inventory hash (cần can thiệp có chủ ý; bằng chứng vốn không có chữ ký).
- Phần tử và dòng TSV không có gạch nối có thể được dùng lại cho hai span (producer hiện tại không phát bản ghi như vậy).
- Định danh model/commit/image là chuỗi tự khai; test end-to-end duy nhất ghi đè `ocr_model_files` ở cả hai manifest.

## R06 — Khôi phục gói offline (D10-08)

- Không tạo checksum mới rồi coi archive là tin cậy: hash chỉ được ghi từ archive tạm của chính lượt build; hash tính lại tại chỗ chỉ dùng để đối chiếu với vật liệu đã chuẩn bị.
- Vật liệu khớp không bị xoá trước khi có cặp hợp lệ; vật liệu không khớp không bao giờ thành `.sha256`, build bị từ chối NOT READY.
- Khoá file và thư mục staging cũ: bên build thứ hai nhận `EXIT_LOCK`, không chạm gì.
- Cổng tin cậy không bị bỏ qua: `.sha256` cạnh gói không được tin; chữ ký bắt buộc với gói RB-1; hash kênh tin cậy vẫn ở `cmd_verify` và quy trình thủ công.
- Bộ cập nhật tự động vẫn **EXPERIMENTAL / NOT READY** trong mã (`EXPERIMENTAL_NOTICE`, từ chối gói RB-1) và trong sáu tài liệu triển khai.

Điểm tồn (đã chạy, đều fail-closed, không chặn): sau lỗi ghi kéo dài, thư mục hiện archive mới không có `.sha256` cho tới lượt build kế cùng tên và không có thông báo hướng dẫn; ngắt đúng sau lệnh rename archive để lại hash cũ cạnh archive mới (không qua được `sha256sum -c`, lượt build kế tự sửa); lượt khôi phục bị từ chối vẫn xoá vật liệu không khớp. Nhánh khoá `msvcrt` và `PermissionError` thật trên Windows: Local (D11-W06).

## R07 — Fingerprint dữ liệu (D10-09)

- F0: **8/8** đột biến bị phát hiện (vector, nội dung chunk, thứ tự chunk cùng ID; thêm/xoá bản ghi; vector insight; nội dung note; `full_text` Source). N0 đạt: `LIVE SELECT` trên `command` không làm đổi fingerprint. Kết quả như nhau trên engine nhúng và trên server 2.3.10.
- Phân trang trên server: 1203 dòng `source_embedding` cho digest ổn định; đổi dòng cuối bị phát hiện. Dòng trùng/thiếu giữa các trang ⇒ từ chối. Thiếu bảng, digest thiếu hoặc sai dạng, `data: null` ⇒ mã 3 ở `--no-writes`.
- Probe chỉ đọc, chỉ xuất digest, ID, số lượng và `updated`; ID chỉ nằm trong file snapshot 0600.

Phân loại phạm vi:

- **A. Tám bảng fingerprint trực tiếp:** `source`, `notebook`, `note`, `source_embedding`, `source_insight`, `reference`, `artifact`, `user`.
- **B. 14 bảng còn lại** trong 22 bảng: `credential`, `model`, `open_notebook` (singleton cấu hình), `chat_session`, `refers_to`, `transformation`, `episode_profile`, `speaker_profile`, `episode`, `podcast_config`, `ai_feedback`, `recently_viewed`, `command`, `_sbl_migrations`. Thay đổi ở các bảng này cho `--no-writes` mã 0 (đã chạy). `command` không thuần tạm thời: `source.command` và `episode.command` trỏ tới bản ghi job đã xong.
- **C. Metadata runtime tạm thời:** LIVE subscription (không phải dòng dữ liệu), loại trừ đúng.

Nhóm B hiện dựa vào ba điều: container/volume DB không bị đụng (cập nhật chỉ tạo lại app, không có migration mới giữa `f2fdf27` và `18eeecb`), sao lưu/thử restore của đơn vị, và kết quả phòng lab RB-G10 (22/22 bảng). Phương pháp snapshot 22 bảng của RB-G10 **không có trong repository**; báo cáo 12D11 nêu "Local preservation procedure" cho credential và provider settings nhưng không có quy trình tương ứng. Đây là cổng Local (D12-L3), không phải yêu cầu mở rộng fingerprint.

Ghi nhận khác: bộ một dòng F1/F2 thủ công yếu hơn công cụ (hai file giống nhau có bảng thừa vẫn in `F1 == F2`); liên kết bản ghi và chuỗi cùng nội dung cho cùng digest ở trường không định kiểu của `reference`/`artifact`; một vector NaN làm mọi snapshot không đọc được; việc dừng writer chỉ được ghi trong quy trình, công cụ không tự cưỡng chế; §10.2 yêu cầu `--no-writes` so với F1 sau khi §8 đã upload PDF thử nên sẽ báo ADDED.

## R08 — RB-1 (rollback offline về v1.2.0)

| Mục | Kết quả | Bằng chứng |
|---|---|---|
| R08-A Tin cậy gói | PARTIAL | Bảy file RB-1 và `rb1_setup.py` nằm trong manifest đã ký; sửa bất kỳ file nào bị từ chối trước mọi lệnh Docker. Từ điển: 74.947 byte, SHA-256 `b5f2bfe2…401c5d`, khớp manifest và mã; các ghim upstream khớp gói RapidOCR 3.9.2 thật. Không có khoá riêng trong repo/gói. Điểm hở ở dưới. |
| R08-B Preflight | PARTIAL | A-valid, B-recoverable đúng; 22 ca C-refused đều thoát mã 4 và không stage gì (Docker giả). Probe dùng `--rm --pull never --network none`, mount `readonly`, không đặt tên, không tham gia project. Hành vi runtime thật: Local. |
| R08-C Thứ tự khởi động | VERIFIED (ngoài container) | Entrypoint v1.2.0 thật kết thúc bằng `exec "$@"`, SHA-256 `62371dd1…349f` đúng giá trị ghim trong `startup.sh`. Chạy `startup.sh` với nội dung entrypoint thật: uv → helper → supervisord (PID 1); helper lỗi (mã 1–8, SIGKILL) ⇒ supervisord không chạy; entrypoint đổi ⇒ không chạy gì. Không dùng `docker exec` để restore. |
| R08-D Bền vững sau rollback | PARTIAL | File đã stage không tham chiếu checkout. Selector fail-closed khi thiếu file hoặc Docker lỗi. Adapter, boot guard, reboot chỉ là hợp đồng tài liệu. RB-G11 **PENDING** ở mọi nơi nhắc tới. |
| R08-E Candidate mới | NOT_VERIFIED → cổng Local | Xem dưới. |

Điểm hở đã tái hiện (mức thấp, cần quyền ghi trên host hoặc hỏng file; không có đường fail-open trên triển khai nguyên vẹn):

- **Selector coi metadata hỏng là "tag đang trỏ candidate".** `baseline-image` bị cắt, CRLF, sai hoa/thường hoặc `select-compose.sh` rỗng ⇒ thoát 0, đầu ra rỗng; "không cần override" và "selector hỏng" không phân biệt được. Hậu quả: v1.2.0 khởi động không có wrapper và tài liệu OCR đầu tiên lỗi tải từ điển. Quy trình thủ công đã có bước `test "$(sh select-compose.sh)" = "$RB1_STATE/compose.json" || exit 1` trước rollback, giảm nhẹ cho đường thủ công; boot guard phải làm tương tự.
- **Khoảng verify → probe → stage.** `stage_assets` đọc lại file từ đĩa sau các probe (tới 2 × 900 giây) và chỉ ghim lại 4/7 file; `startup.sh`, `runtime_gate.py`, `select-compose.sh` không được băm lại. Quyền của từng file trong gói không được kiểm như `load_package`.
- **Sau khi stage không còn gốc tin cậy ngoài quyền thư mục.** Cổng khởi động so từ điển với `manifest.json` nằm cạnh; đổi cả hai cùng lúc vẫn qua. Mount chỉ đọc trong container không bảo vệ phía host.
- Vị trí stage không bị buộc nằm ngoài checkout/`$WORK`; tên service không được đối chiếu với nhãn Compose của container; image thiếu nhãn revision được chấp nhận (Dockerfile v1.2.0 không đặt nhãn).
- Manifest và helper đang phát hành vẫn tự mô tả là "TEST ARTIFACT - Local acceptance only" / "LOCAL TEST HELPER".

**R08-E — candidate phụ thuộc cùng loại artifact.** Entrypoint của candidate giống hệt baseline; đường gọi RapidOCR không đổi; mã duy nhất liên quan từ điển là fingerprint readiness (làm verdict cũ thành "chưa kiểm tra", không khôi phục); gói `rapidocr` 3.9.2 không kèm `ppocrv6_dict.txt`; selector cố ý trả rỗng khi tag trỏ candidate. Theo mã, sau mỗi lần recreate offline container candidate cũng mất từ điển như v1.2.0 (giới hạn D-32, có từ trước, không phải hồi quy). RB-1 hiện chỉ bọc baseline. Chưa có bằng chứng candidate chạy RapidOCR offline sau recreate ⇒ thêm cổng Local **D12-L1**.

## R09 — Hồi quy cuối

Xem mục "Kết quả hồi quy cuối" trong [Release gate 12D12](PHASE12D12_RELEASE_GATE.md). Frontend không thay đổi trong `2cc824f..18eeecb` nên không chạy lại.

## Phân loại

**Blocker mã cho phát hành (1):** D12-03 — cổng G-04 chế độ release báo đạt sai. Chỉ ảnh hưởng `scripts/ocr/phase12_standard_diff.py`; chặn việc chứng nhận D11-W05/G-04, không chặn các cổng runtime.

**Cổng nghiệm thu Local (bổ sung cho checklist 12D11):** D12-L1 đến D12-L5, liệt kê ở [Release gate 12D12](PHASE12D12_RELEASE_GATE.md). RB-G11 và diễn tập gói ký chính thức vẫn PENDING.

**Giới hạn đã biết:** ảnh scan qua đường native không kiểm verdict; hai nhóm bản vá không nguyên tử; đệm stderr; khoảng trắng thêm ở số hiệu xuống dòng trong tiêu đề căn giữa/dòng thụt lề; cổng release hiếm khi đạt mã 0 trên văn bản thật; fingerprint tám bảng; bằng chứng không có chữ ký; candidate chịu giới hạn D-32.

**Vấn đề hoãn, không chặn:** D12-01, D12-02; ba điểm tồn của R06; bốn điểm cứng hoá RB-1; đường chẩn đoán của cổng diff trả 0 khi thiếu `--release`.

Test kiểm soát của review: `tests/test_phase12d12_review_controls.py` — 18 passed / 6 xfailed khi có `CB5400_D12_SURREAL_URL` trỏ tới server loopback dùng một lần; 16 passed / 2 skipped / 6 xfailed khi không có. Với `--runxfail`, sáu ca D12-01, D12-02, D12-03 thất bại đúng tại assertion nghiệp vụ.

E2-01, E2-02 giữ `NEEDS LOCAL EVIDENCE`. Bộ cập nhật tự động giữ **EXPERIMENTAL**. Production không bị tác động. [Trạng thái JSON](PHASE12D12_FINDING_STATUS.json) · [Release gate](PHASE12D12_RELEASE_GATE.md)
