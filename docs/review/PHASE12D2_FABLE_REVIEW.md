# CHATBOT5400 — Phase 12D2: Review độc lập và kiểm toán đối kháng

| | |
|---|---|
| Repository | `nghoainam1902ps4-lgtm/ChatBot5400-Version02` |
| Baseline | `v1.2.0` = `f2fdf2714a7c0b5b196132f71cfc091928befc06` (đã xác minh: tag và nhánh `claude/practical-wozniak-9s1t6z` cùng trỏ commit này) |
| Đối tượng review | `feature/legal-document-normalization` @ `2ef007417eaca0ce41e7aba2e32a201fa243ebf1` (đã xác minh: HEAD không đổi so với yêu cầu; 7 commit, 60 file, +11 667 / −7) |
| PR | #50, **Draft**, base `claude/practical-wozniak-9s1t6z`; không approve, không merge |
| Nhánh review | `review/phase12-fable-audit` (chỉ thêm `docs/review/` và `tests/review_phase12d2/`) |
| Mã chạy | **Không thay đổi** |
| Phiên bản thư viện đã đọc mã | Docling 2.129.0, Docling Core 2.96.0, Content Core 2.0.7 (cài từ `uv.lock`, đọc trực tiếp trong `site-packages`) |

Tài liệu kèm theo: [FINDINGS.json](PHASE12D2_FINDINGS.json) · [OFFLINE_UPDATE_AUDIT](PHASE12D2_OFFLINE_UPDATE_AUDIT.md) ·
[TEST_GAPS](PHASE12D2_TEST_GAPS.md) · [REMEDIATION_PLAN](PHASE12D2_REMEDIATION_PLAN.md) ·
[WINDOWS_ACCEPTANCE_CHECKLIST](PHASE12D2_WINDOWS_ACCEPTANCE_CHECKLIST.md)

## 1. Kết luận

Phase 12 **chưa sẵn sàng phát hành**. Review tìm thấy 6 finding mức P1, tất cả tái hiện được hoặc suy ra trực tiếp từ mã:

1. **Chế độ Legal xóa nội dung hợp lệ.** Dòng lặp ở đầu/cuối trang (đơn vị tính, tên đơn vị ban hành, ghi chú ký) bị coi là
   header/footer (F-01); số năm, số khoản, số liệu đứng riêng bị coi là số trang (F-02).
2. **Chế độ Legal tạo ra câu không có trong bản gốc** bằng cách ghép footnote/footer với đoạn văn trang sau, và nhập điểm
   `a.`/`a/` vào câu dẫn (F-03).
3. **Lệnh build gói offline theo tài liệu không chạy được**: `git bundle` từ chối đối số mà cả hai wrapper truyền vào (F-04).
4. **Lần cập nhật thứ hai sau rollback dùng lại backup cũ** (F-08).
5. **Sau khi cập nhật, một lệnh `docker compose up -d` thông thường đưa ứng dụng về bản cũ** và công cụ không phát hiện (F-11).

Con số "0 từ bị mất, 24/24" trong PR được đo bằng một oracle tự cộng lại phần đã xóa nên không thể phát hiện các lỗi ở mục 1
(T-01).

Những gì làm đúng: chế độ Standard không đổi so với v1.2.0 (cùng lời gọi `export_to_markdown()`), cổng hai lớp hoạt động đúng,
một job giữ một chế độ từ đầu đến cuối, model Agri không bị đụng tới, normalizer xác định/idempotent/an toàn luồng và không gọi
mạng hay LLM, mọi lệnh tạo lại container đều chỉ nhằm vào ứng dụng với `--no-deps --no-build --pull never`, gói không xác thực
bị từ chối.

## 2. Phạm vi và giới hạn

Đã đọc toàn bộ diff `v1.2.0..2ef0074` và mã cũ liên quan (`docling_extract.py`, `options.py`, `source.py`, `chunking.py`,
`token_utils.py`, `installer.py`, `docker-entrypoint.sh`, `async_migrate.py`, `domain/base.py`, compose production, CSS và
component trang Source), cùng mã nguồn Docling/Docling Core đúng phiên bản.

| Không làm được trong Cloud | Hệ quả |
|---|---|
| Không có Docker daemon | Không chạy được build image, `docker load`, Compose thật, cập nhật, rollback ⇒ **OFFLINE ROLLBACK: NOT VERIFIED** |
| Không tải được Layout Heron/TableFormer; không có model Agri; không dùng PDF thật | Không chạy pipeline OCR thật ⇒ **REAL OCR PIPELINE: NOT VERIFIED**. Tài liệu thử được dựng như test của Phase 12: layout tổng hợp → `ReadingOrderModel` thật của Docling |
| Không có PowerShell | `build-package.ps1`, `phase12-test.ps1` chỉ được đọc |
| Proxy chặn host tải bảng mã tiktoken | `tests/test_chunking.py` treo trong Cloud (xem TEST_GAPS §6) |

Phân loại 60 file thay đổi: A/C runtime backend và OCR (7: `legal_normalizer.py` mới; `docling_extract.py`, `options.py`,
`source.py`, `content_settings.py`, `api/ocr_service.py`, `api/models.py` sửa) · B frontend (7) · D test, fixture, benchmark và
script chẩn đoán (12) · E offline tooling (11) · F Docker và stack thử nghiệm (5 + 2 script điều khiển) · G tài liệu (16) ·
H nhạy cảm bảo mật: `offline_package.py`, `api/ocr_service.py`, `Dockerfile`, compose thử nghiệm.

## 3. Lớp 1 — Xác minh nguyên nhân gốc

| # | Kết luận của Phase 12A | Phân loại | Căn cứ |
|---|---|---|---|
| 1 | `<!-- image -->` do serializer Markdown của Docling sinh ra | **VERIFIED BY SOURCE + EXECUTION** | `MarkdownParams.image_placeholder = "<!-- image -->"`, `image_mode = PLACEHOLDER` (`docling_core/transforms/serializer/markdown.py` 155-156, 863-864); tái hiện trong phản ví dụ F-06 |
| 2 | Số trang bị layout model gắn nhãn TEXT | **NOT VERIFIED** (hành vi của Layout Heron, cần model thật). Phần cơ chế đã xác minh theo mã: chỉ nhãn `PAGE_HEADER`/`PAGE_FOOTER` mới vào lớp furniture (`readingorder_model.py` 643-645) |
| 3 | Docling không ghép một số từ tiếng Việt qua trang | **VERIFIED BY SOURCE + EXECUTION** | `predict_merges` yêu cầu vế trước kết thúc bằng `[a-z,\-­]` và vế sau bắt đầu bằng `[a-zA-ZÀ-ɏ]` (`reading_order_rb.py` 238-244): chữ có dấu vùng U+1EA0–U+1EF9 (ộ, ế, ờ…) và chữ `đ` ở cuối từ không khớp. Thực nghiệm: footer kết thúc bằng "Mẫu" được Docling ghép, kết thúc bằng "bộ" thì không |
| 4 | Danh sách bị đánh lại số | **VERIFIED BY SOURCE**; frontend test xác nhận trình duyệt đánh lại số | Serializer tự sinh `{pos+1}.` khi item đầu là dạng đánh số và marker rỗng (`markdown.py` 305-327); `ListItem` luôn được tạo với `enumerated=False` rồi suy diễn lại (`readingorder_model.py` 613-622) |
| 5 | Marker `đ)`, `a.1)` xử lý sai | **VERIFIED BY SOURCE** | `ListItemMarkerProcessor` chỉ có `[a-z]\)` (không gồm `đ`) và không có mẫu `a.1)` (`list_marker_processor.py` 52-68) |
| 6 | Text OCR trong vùng picture bị bỏ khi xuất Markdown | **PARTIAL** | Theo mã: Docling thêm text con vào `PictureItem` (`_add_child_elements`) và `export_to_markdown` mặc định `traverse_pictures=False` — đúng. Chưa xác minh OCR thật có đặt nội dung có nghĩa vào đó hay chỉ là rác từ con dấu/chữ ký |
| 7 | Mất từ cuối trang, chưa rõ nguyên nhân | **NOT VERIFIED** | Không thể tái hiện nếu không có pipeline thật; Phase 12 không sửa hiện tượng này |

**ROOT CAUSE VERIFIED: PARTIAL.**

Giải pháp sửa gốc hay che triệu chứng?

| Triệu chứng | Giải pháp Phase 12 | Nhận định |
|---|---|---|
| Đánh lại số, marker `đ)` | Serializer riêng ghi marker gốc dạng văn bản | Xử lý đúng chỗ. Marker được ghi là marker Docling tách ra từ chính văn bản OCR; normalizer **không** tự sinh số (đã xác minh: `ensure_valid_list_item_marker=False`, `OrigListItemMarkerMode.NEVER`) |
| Số trang, header/footer nhãn TEXT | Suy diễn sau từ vị trí + lặp lại | Che triệu chứng của lỗi gắn nhãn; bằng chứng quá yếu ⇒ F-01, F-02 |
| Không ghép qua trang | Bộ ghép thứ hai với quy tắc riêng | Bổ sung hợp lý nhưng chọn sai vế trái ⇒ F-03 |
| Placeholder ảnh | Bỏ placeholder | Che tín hiệu "có vùng chưa trích xuất" ⇒ F-06 |
| Mất từ cuối trang | Không xử lý | Còn nguyên |

## 4. Lớp 2 — Legal normalizer

**LEGAL NORMALIZER CORRECTNESS: FAIL · LEGAL CONTENT PRESERVATION: FAIL.**

### 4.1 Phản ví dụ đã tái hiện (so sánh Standard ↔ Legal trên cùng `DoclingDocument`)

| Finding | Đầu vào (tổng hợp) | Standard | Legal |
|---|---|---|---|
| F-01 | 3 trang phụ lục, mỗi trang bắt đầu bằng `Đơn vị tính: triệu đồng` | 3 lần | **0 lần** |
| F-01 | 4 thông báo một trang: tên chi nhánh ở đầu, `(Ký, ghi rõ họ tên và đóng dấu)` ở cuối | đủ | **mất cả 8 dòng** |
| F-02 | Trang 1 kết thúc `2024`, trang 2 kết thúc `2025` | còn | **mất cả hai** |
| F-02 | Số khoản `2`, `3` đứng riêng đầu trang 2, 3 | còn | **mất** |
| F-03 | Đoạn bị cắt + footnote `1 Thông tư số 39/2016/TT-NHNN` + phần nối ở trang sau | 3 dòng riêng | `1 Thông tư số 39/2016/TT-NHNN khách hàng theo quy định…`; đoạn thật vẫn bị cắt |
| F-03 | Tài liệu 2 trang có footer `Lưu hành nội bộ` | riêng | `Lưu hành nội bộ trong trường hợp đặc biệt, Tổng Giám đốc…` |
| F-03 | `2. Hồ sơ vay vốn bao gồm các giấy tờ` / `a. Giấy đề nghị vay vốn;` (và `a/`) | 2 dòng | `2\. Hồ sơ vay vốn bao gồm các giấy tờ a. Giấy đề nghị vay vốn;` |
| F-06 | Ảnh 300×200 pt (12% trang) không có text | `<!-- image -->` | không có gì, không cảnh báo |

Vì sao các trường hợp này thực tế: với lề 2 cm trên giấy A4, dòng thân đầu tiên và cuối cùng của mọi trang đều nằm trong "dải
10%" mà normalizer coi là vùng header/footer; điều kiện "ngoài cùng của trang" luôn đúng với dòng đầu/cuối.

### 4.2 Điểm kiểm tra theo yêu cầu

| Yêu cầu | Kết quả |
|---|---|
| Xóa nhầm số Điều | Dòng bắt đầu `Điều/Chương/Mục/Phần` được loại khỏi phát hiện dòng lặp (`_STRUCTURE_WORDS`); **không** được bảo vệ khi là số đứng riêng (F-02) |
| Xóa nhầm số Khoản / số năm / số liệu | **Có** (F-02) |
| Số tiền, lãi suất, %, số hiệu văn bản, URL **bên trong đoạn văn** | Không bị đổi: normalizer chỉ di chuyển hoặc ghép nguyên item, không sửa ký tự (đã xác minh; `test_verified_protected_values_survive_in_counterexamples`) |
| Footnote | Nhãn `FOOTNOTE`: giữ nguyên, chặn phép ghép (bỏ sót, an toàn). Nhãn `TEXT`: bị ghép sai (F-03) |
| Nội dung trong hình | Text con được giữ (`traverse_pictures=True`); ảnh không text < 15% bị bỏ im lặng (F-06) |
| Dấu tiếng Việt | Không có phép biến đổi Unicode nào trong normalizer; so khóa lặp chỉ dùng `lower()` cho việc so sánh |
| Tạo nội dung không có trong OCR | Không thêm từ; **có** tạo câu mới bằng phép ghép sai (F-03); thêm ký tự `\` (F-17) |
| Nhân đôi nội dung | Không tìm thấy |
| Marker do normalizer tự tạo | Không. Marker hiển thị = `ListItem.marker` do Docling tách từ văn bản; item không có marker được ghi không số |
| Marker do trình duyệt vẽ | Loại bỏ hoàn toàn: đầu ra Legal không còn cú pháp danh sách (frontend test PASS) |
| Khoản bắt đầu từ 5, 7, 13; không liên tục; `1.1`, `1.1.1`; `đ)`, `a.1)` | Đúng trên fixture hiện có (đã chạy lại) |
| Điểm kiểu `a.`, `a/` qua trang | Sai (F-03) |
| Câu kết thúc bằng `.`, `:`, `;` | Không ghép (đúng) |
| Dấu gạch nối cuối trang | Không ghép, có cảnh báo (bỏ sót, an toàn) |
| Trang trắng ở giữa | Không ghép (không phải trang liền kề) |
| Bảng qua trang, bảng trong tài liệu | Bảng không bị đụng; bảng chặn phép ghép |
| Hai cột | Chỉ có 1 fixture; không tìm được phản ví dụ nhưng độ phủ thấp |
| Trang xoay, khổ trang khác nhau, provenance sai | Không có fixture; tọa độ được đổi về gốc trên-trái theo chiều cao từng trang (đúng theo mã). Thiếu provenance hoặc kích thước trang ⇒ giữ nguyên (đúng) |
| Thứ tự đọc | Không đổi thứ tự; chỉ bỏ/ghép item liền kề |
| Literal HTML comment | `escape_html=True` giữ nguyên như Standard |

### 4.3 Tính chất đúng đắn

| Tính chất | Kết quả | Cách xác minh |
|---|---|---|
| Xác định | Đạt | chạy lại trên 7 phản ví dụ + 24 fixture |
| Idempotent | Đạt | như trên |
| Không sửa tài liệu gốc | Đạt (`model_copy(deep=True)`) | so `export_to_markdown()` trước/sau |
| Không phụ thuộc trạng thái tài liệu trước | Đạt: không có biến toàn cục thay đổi | đọc mã |
| An toàn luồng | Đạt | 14 luồng × 3 lần, kết quả trùng |
| An toàn ngoại lệ / fallback | Đạt: mọi `Exception` ⇒ bản Standard + metadata `failed`; kết quả rỗng ⇒ Standard | đọc mã + test hiện có. Lưu ý: thất bại không được báo cho người dùng (F-07) |
| Không mạng, không LLM, không ghi DB/file | Đạt | đọc mã: chỉ `os.environ`, `re`, `time`, docling-core |
| Hiệu năng | Không đạt ở trường hợp nhiều phép ghép (F-10) | §9 |

## 5. Lớp 3 — Tích hợp pipeline OCR

**OCR INTEGRATION: PARTIAL** (logic định tuyến và cổng đúng theo mã và test; pipeline thật chưa chạy; F-07, F-15).

| # | Yêu cầu | Kết quả |
|---|---|---|
| 1 | Cờ OFF giữ hành vi v1.2.0 | Đạt theo mã: `effective_mode` trả `standard`; mọi nhánh mới đứng sau `ocr.legal_normalization`; nhánh xuất Markdown gọi đúng `doc.export_to_markdown()` như cũ |
| 2 | Cờ ON, admin chọn Standard | Đạt (cùng lý do) |
| 3 | Cờ ON + Legal kích hoạt chuẩn hóa | Đạt cho PDF đi qua Docling |
| 4 | Đường bỏ qua chuẩn hóa | PDF khi document engine không phải Docling / Docling chưa cài / định dạng xuất `html`,`json` / `_is_pdf` không nhận ra (F-18): giữ Standard, có log info, **không** báo người dùng |
| 5 | RapidOCR mặc định | Legal chuyển PDF sang lớp native với tùy chọn RapidOCR tường minh (F-15) |
| 6–9 | Tesseract Fast/Best, EasyOCR, Agri | Đường native như v1.2.0; phiên bản model Agri vẫn được đóng băng một lần cho cả file (`ocr.pinned()` không đổi) |
| 10–11 | Auto Full Page, Force Full Page | Quyết định chế độ OCR vẫn thực hiện trong `convert_document`; không bị Legal ảnh hưởng |
| 12 | OCR tắt | Legal vẫn chuẩn hóa PDF có lớp chữ (`do_ocr=False`) |
| 13–15 | PDF điện tử / scan / hỗn hợp | Cùng đường mã; chưa chạy thật |
| 16 | Không phải PDF | Không đổi (ảnh, Office, HTML, URL trang web); URL trỏ tới PDF được chuẩn hóa |

Nhất quán trong một job: `OcrSettings` là dataclass `frozen`, tạo một lần ở đầu `content_process` (đã giải quyết cả cờ môi trường)
và truyền xuống tới `convert_file`. Admin đổi chế độ khi job đang chạy không ảnh hưởng job đó. Không có cache kết quả OCR nào
phụ thuộc chế độ. Một job **retry** đọc lại cài đặt nên có thể chạy ở chế độ khác lần thử đầu (chấp nhận được; nên ghi nhận).

## 6. Lớp 4 — Source, chunking, embedding, RAG

| Câu hỏi | Trả lời |
|---|---|
| Nội dung nào được lưu? | `source.full_text = extraction.content` (bản Legal). Embedding, tìm kiếm, chat đều đọc `full_text` ⇒ **cùng một nội dung** với phần hiển thị (trước khi render Markdown) |
| UI mới, embedding cũ? | Không: chỉ có một trường |
| Chuẩn hóa hai lần? | Không: chỉ ở `convert_file` |
| Source cũ đổi khi chuyển chế độ? Tự re-embed? | Không. Chỉ khi người dùng xử lý lại Source thì chế độ hiện tại mới áp dụng |
| Fallback lưu gì? | Bản Standard, không có dấu hiệu nào trên Source (F-07) |
| Chunking làm mất số? | Không mất; nhưng chuỗi lưu có `\` (F-17) và mỗi điểm thành đoạn riêng nên dễ bị tách khỏi câu dẫn hơn |
| Truy nguyên trang / page citation ở tầng RAG | **Không có.** Provenance (trang, bbox) chỉ tồn tại trong `DoclingDocument` và báo cáo chẩn đoán cục bộ; không được lưu theo chunk. Không coi là tính năng đã hoàn thành |
| Dấu vết chuẩn hóa trên Source | **Không có** (F-07) |

## 7. Lớp 5 — Frontend

**FRONTEND INTEGRATION: PARTIAL** (logic và test đạt; chưa chạy trên trình duyệt thật; F-16).

- Đã chạy lại: **430/430 PASS** (63 file), `tsc --noEmit` sạch.
- Bảng chọn chế độ: lưu riêng, không gửi kèm tùy chọn engine; Legal bị vô hiệu khi cổng đóng; có thông báo khi lựa chọn đã lưu
  không còn hiệu lực. API từ chối `legal` khi cổng đóng (`InvalidInputError` ⇒ 400). Giá trị ngoài `standard|legal` bị Pydantic từ chối.
- RBAC: toàn bộ router `/ocr` có `Depends(require_admin)`; không có IDOR (cài đặt toàn cục, không theo đối tượng).
- XSS: không thêm `rehype-raw`; nội dung vẫn qua `MarkdownRenderer` như cũ; Docling vẫn `escape_html`. Không có bề mặt mới.
- Bản địa hóa: 10 khóa mới ở cả `vi-VN` và `en-US`. Mô tả chế độ Legal trên giao diện ("Giảm ký tự thừa, giữ số điều khoản…")
  không nói rằng chế độ này **loại bỏ** dòng lặp đầu/cuối trang, số trang và placeholder ảnh nhỏ; nên nêu rõ để admin biết
  mình đang bật điều gì (cải tiến).
- **F-16**: định dạng phân cấp của trang Source dựa trên `<li>`; đầu ra Legal không còn `<li>` nên mất thụt lề Khoản/điểm và chữ
  đậm của Điều; mọi dòng nhận `text-indent: 2em`.
- Không ghi nhận ai đã đổi chế độ chuẩn hóa (các thao tác model tùy biến có `_actor`; cập nhật cấu hình thì không) — cải tiến.
- Chưa kiểm tra trên thiết bị di động và nhiều phiên trình duyệt (checklist W-LEG-12, W-LEG-13).

## 8. Lớp 6 — Công cụ cập nhật offline

Chi tiết: [PHASE12D2_OFFLINE_UPDATE_AUDIT.md](PHASE12D2_OFFLINE_UPDATE_AUDIT.md).

**DESIGN: PARTIAL · IMPLEMENTATION: FAIL · SECURITY: PARTIAL · ROLLBACK: NOT VERIFIED.**

## 9. Lớp 8 — Hiệu năng

Đo trên máy Cloud 4 nhân, tài liệu tổng hợp tạo trực tiếp bằng docling-core, 40 item TEXT mỗi trang + 1 số trang:

| Trường hợp | `export_to_markdown` | `normalize_document` | Chênh lệch mỗi trang |
|---|---|---|---|
| 100 trang | 0,50 s | 0,91 s | 4,1 ms |
| 500 trang | 2,18 s | 4,49 s | 4,6 ms |
| 2000 trang | 9,50 s | 17,0 s | 3,8 ms |
| 500 trang, **mỗi trang một phép ghép** | 2,21 s | **23,4 s** | 42 ms |
| 125 / 250 / 500 trang có ghép | — | 2,3 s / 6,8 s / 21,7 s | tăng ~3× khi gấp đôi |
| 3 trang × 1000 / 3000 / 6000 item ngắn trong dải | — | 0,6 s / 3,3 s / 9,5 s | bậc hai |

Nhận xét:

- Con số "2,5 ms/trang" của Phase 12D chỉ đúng cho fixture nhỏ không có phép ghép. Với 40 item/trang, tổng thời gian normalizer
  khoảng 9 ms/trang, cao hơn export chuẩn 4–5 ms/trang.
- Với phép ghép, 70% thời gian nằm trong `DoclingDocument.delete_items` của docling-core (so sánh pydantic theo cặp): bậc hai
  theo số item (F-10).
- Không có regex nào có nguy cơ ReDoS: các mẫu đều neo đầu dòng, không có lượng từ lồng nhau; `fullmatch` trên chuỗi ≤ 20 ký tự.
- Bộ nhớ: một bản sao sâu của tài liệu (≈ 2× `DoclingDocument`), không sao chép lặp.
- Log: chỉ bộ đếm, không có nội dung văn bản.

**Chưa đo được:** chi phí toàn pipeline OCR (Heron + TableFormer + engine) và tỷ trọng của normalizer trong đó; hiệu năng khi
OCR đồng thời; bộ nhớ đỉnh trên PDF thật hàng nghìn trang. Số liệu trên là **overhead của normalizer trên dữ liệu tổng hợp**,
không phải số đo end-to-end.

## 10. Bảo mật

| Loại | Nội dung |
|---|---|
| Lỗ hổng mới (phòng thủ theo chiều sâu) | F-12: chèn YAML / đối số git từ manifest hoặc `--to-image` |
| Rủi ro mới | F-14 (archive), F-25 (`docker load` gắn lại tag), F-26 (chuỗi tin cậy, proxy), F-10 (từ chối dịch vụ bằng PDF cố ý) |
| Hạn chế vận hành | Chưa có khóa ký phát hành (tài liệu đã nêu); SHA-256 chỉ bảo đảm toàn vẹn |
| Nợ bảo mật có sẵn, **không** tính là lỗi mới | CORS mở, xác thực mật khẩu đơn giản, `convert_file` chạy đồng bộ, `ContentSettings` là singleton theo tiến trình, entrypoint cài Crawl4AI từ mạng khi được bật, image không tái lập bit-by-bit |
| Không tìm thấy | Rò rỉ bí mật trong log; RBAC/IDOR mới; XSS mới; subprocess qua shell ngoài `BACKUP_CMD` (chủ ý, từ cấu hình của root) |

## 11. Danh sách finding (sắp theo mức độ)

| ID | Mức | Chặn | Nhóm | Tóm tắt | Xác minh |
|---|---|---|---|---|---|
| F-01 | P1 | Có | Normalizer | Dòng lặp hợp lệ bị xóa như header/footer | Đã chạy |
| F-02 | P1 | Có | Normalizer | Số năm / số khoản / số liệu bị xóa như số trang | Đã chạy |
| F-03 | P1 | Có | Normalizer | Ghép sai liên trang (footnote, footer, điểm `a.`) | Đã chạy |
| F-04 | P1 | Có | Offline | Wrapper build không tạo được gói (`git bundle`) | Đã chạy |
| F-08 | P1 | Có | Offline | Lần thử thứ hai dùng lại backup cũ | Đã chạy |
| F-11 | P1 | Có | Offline | Trôi cấu hình: `compose up` thường đưa về bản cũ, không phát hiện | Theo mã; cần Docker thật |
| F-05 | P2 | Không | Offline | `--sync-source` không dùng được | Đã chạy |
| F-06 | P2 | Không | Normalizer | Ảnh < 15% bị bỏ im lặng | Đã chạy |
| F-07 | P2 | Không | Tích hợp | Không lưu dấu vết chuẩn hóa trên Source | Theo mã |
| F-09 | P2 | Không | Offline | `finish`/`rollback` không kiểm tra | Đã chạy |
| F-10 | P2 | Không | Hiệu năng | Bậc hai khi nhiều phép ghép / nhiều item trong dải | Đã đo |
| F-20 | P2 | Không | Offline | So image ID giữa hai image store | **Nghi ngờ** |
| F-21 | P2 | Không | Offline | DB chỉ được kiểm ở tầng cấu hình | Theo mã |
| F-22 | P2 | Không | Offline | Không kiểm kê model trước; bỏ qua kết quả chép RapidOCR | Theo mã |
| T-01 | P2 | Không | Test | Oracle "0 từ mất" vòng tròn | Đã chạy |
| T-03 | P2 | Không | Test | 101/144 ca tham số hóa rỗng; fixture nhỏ; đường quan trọng không test | Đã đếm |
| F-12 | P3 | Không | Bảo mật | Giá trị manifest không kiểm định dạng | Đã chạy |
| F-13 | P3 | Không | Offline | Journal hỏng ⇒ traceback | Đã chạy |
| F-14 | P3 | Không | Bảo mật | Archive: trùng tên, giải nén trước chữ ký | Đã chạy |
| F-15 | P3 | Không | Tích hợp | Legal đổi đường OCR của cấu hình mặc định | Theo mã |
| F-16 | P3 | Không | Frontend | Mất định dạng phân cấp ở trang Source | Theo mã |
| F-17 | P3 | Không | RAG | Ký tự `\` trong nội dung lưu và embedding | Theo mã; ảnh hưởng chưa đo |
| F-23 | P3 | Không | Offline | `legal-off` mặc định vào bảo trì | Theo mã |
| F-24 | P3 | Không | Offline | Rollback theo tag; không khôi phục mã nguồn | Theo mã |
| F-25 | P3 | Không | Offline | `docker load` gắn lại tag khác | **Nghi ngờ** |
| F-26 | P3 | Không | Bảo mật | Chuỗi tin cậy / cấu hình / proxy | Theo mã |
| F-27 | P3 | Không | Offline | VERSION 1.2.0 chặn build RC | Theo mã |
| T-02 | P3 | Không | Test | Oracle an toàn lệnh Docker luôn đúng | Đã chạy |
| F-18 | P4 | Không | Tích hợp | `_is_pdf` khác cách nhận diện MIME | Theo mã |

Phân biệt:

- **Lỗi thực sự, đã tái hiện:** F-01, F-02, F-03, F-04, F-05, F-06, F-08, F-09, F-10, F-12, F-13, F-14, T-01, T-02, T-03.
- **Khoảng trống xác định từ mã:** F-07, F-11, F-21, F-22, F-23, F-24, F-27, F-15, F-16, F-18.
- **Rủi ro chưa tái hiện (cần máy thật):** F-20, F-25; phần Compose của F-11; ảnh hưởng RAG của F-17.
- **Hạn chế môi trường:** không Docker, không model, không PowerShell, `test_chunking.py` treo.
- **Bắt buộc sửa trước RC:** 6 mục chặn. **Bắt buộc trước production:** nhóm B của kế hoạch khắc phục. **Hoãn được:** nhóm C.

## 12. Final verdict

```
INDEPENDENT REVIEW                 COMPLETED (trong giới hạn Cloud: không Docker, không model OCR thật, không PowerShell)
ROOT CAUSE                         PARTIAL (4 VERIFIED, 1 PARTIAL, 2 NOT VERIFIED)
LEGAL NORMALIZER CORRECTNESS       FAIL
LEGAL CONTENT PRESERVATION         FAIL
OCR INTEGRATION                    PARTIAL
FRONTEND INTEGRATION               PARTIAL
TEST QUALITY                       PARTIAL
OFFLINE UPDATE DESIGN              PARTIAL
OFFLINE UPDATE IMPLEMENTATION      FAIL
OFFLINE UPDATE SECURITY            PARTIAL
OFFLINE ROLLBACK                   NOT VERIFIED (chưa chạy Docker thật)
REAL OCR PIPELINE                  NOT VERIFIED (chưa chạy được)

NEW P0 FINDINGS                    0
NEW P1 FINDINGS                    6   (F-01, F-02, F-03, F-04, F-08, F-11)
NEW P2 FINDINGS                    10  (2 trong đó là lỗi test; 1 là nghi ngờ chưa tái hiện)
NEW P3 FINDINGS                    12  (1 trong đó là nghi ngờ chưa tái hiện)
NEW P4 FINDINGS                    1
RELEASE BLOCKERS                   6

READY FOR PHASE 12D3 REMEDIATION   YES
READY FOR WINDOWS LOCAL TESTING    CONDITIONAL (Standard, nguyên nhân gốc, kiểm tra Docker cơ bản: chạy được ngay;
                                               nghiệm thu Legal và cập nhật offline: sau Phase 12D3)
READY FOR RELEASE                  NO
READY FOR PRODUCTION DEPLOYMENT    NO

RUNTIME CODE UNCHANGED
PRODUCTION UNCHANGED
```
