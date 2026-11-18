# Phase 12D8 — Release blockers

Đối tượng review: `4587eb7` (`feature/legal-document-normalization`). Báo cáo đầy đủ:
[PHASE12D8_CODEX_FINAL_REVIEW.md](PHASE12D8_CODEX_FINAL_REVIEW.md). Review không sửa runtime code; các hướng sửa dưới
đây là đề xuất tối thiểu cho phase sau.

Tiêu chí của đề bài (§10): không còn P0 / P1 mở; không còn lỗi xác nhận được làm mất hoặc thay đổi nội dung pháp lý;
không có regression ngoài phạm vi bản sửa được phê duyệt; không có lỗi nghiêm trọng trong manual offline fallback;
Local gate được ghi đầy đủ.

| Tiêu chí | Kết quả |
|---|---|
| Không còn P0 / P1 mở | **Không đạt** — D8-03 (P1) |
| Không còn lỗi làm mất / đổi nội dung pháp lý | **Không đạt** — D8-03, D8-01, D8-02 |
| Không có regression ngoài phạm vi | Đạt ở Cloud (10 lỗi backend cùng tên với baseline; frontend 438 / 438) |
| Không có lỗi nghiêm trọng trong manual fallback | Đạt (chỉ P3 trong tài liệu; chưa chạy với Docker thật) |
| Local gate được ghi đầy đủ | Đạt — [PHASE12D8_LOCAL_GATE_CHECKLIST.md](PHASE12D8_LOCAL_GATE_CHECKLIST.md) |

## A. Code release blockers (3)

### D8-03 — P1 — Docling bỏ dấu gạch nối của số hiệu khi ghép chữ một vùng

| | |
|---|---|
| File | upstream `docling/models/stages/page_assemble/page_assemble_model.py:115-153` (`PageAssembleModel.sanitize_text`), Docling 2.129.0; ứng dụng chưa có bản vá (`open_notebook/ocr/docling_patches.py` chỉ vá `_run_tesseract`) |
| Nguyên nhân | Quy tắc nối từ bị ngắt dòng: ô kết thúc bằng `-` dính liền chữ / số + ô sau bắt đầu bằng chữ / số ⇒ bỏ `-`, nối liền. Với RapidOCR / EasyOCR / lớp chữ PDF mỗi ô là một dòng; với Tesseract mỗi ô là một từ nên áp dụng cả giữa dòng |
| Tái hiện | `uv run pytest tests/review_phase12d8/test_tsv_patch_d8.py -k "d8_03 or hyphen" -q` (cần `tesseract` + `vie` cho hai test đầu-cuối; năm test mức hàm chạy ở mọi nơi) |
| Thực tế | `05/2024/TT-` + `BNNPTNT` → `05/2024/TTBNNPTNT`; `2021-` + `2025` → `20212025`; `0001-` + `0002.` → `00010002.`; `VT- KHTC` → `VTKHTC`; `1- Điều 5` → `1Điều 5`. TSV thô và ô OCR vẫn đúng |
| Mong đợi | Mọi ký tự trong TSV của Tesseract có trong nội dung lưu |
| Phạm vi | Standard **và** Legal; v1.2.0 **và** ứng viên (không phải hồi quy); mọi engine ở trường hợp ngắt dòng |
| Sửa tối thiểu | Bản vá có kiểm soát thứ hai, cùng khuôn với D-39: chốt `docling == 2.129.0` + SHA-256 của `sanitize_text`; trong hàm, thay "bỏ `-`" bằng "giữ `-`" (không thêm khoảng trắng khi ô sau là phần nối của cùng dòng in). Thêm lớp "expected hyphen fix" vào công cụ standard-diff vì Standard sẽ khác v1.2.0 ở đúng các chỗ này |
| Phương án khác | Chủ dự án chấp nhận bằng văn bản là giới hạn đã biết có từ v1.2.0 (quyết định mới trong `docs/ocr/DECISIONS.md`), ghi vào release notes; tối thiểu Legal cảnh báo khi chữ phần tử khác chữ các ô gốc (`conv_res.assembled.elements[*].cluster.cells` có sẵn trong `source_evidence`) |
| Vì sao là blocker | P1 mở; cùng loại với E0-07 (Docling đổi chữ Tesseract đã đọc đúng), và E0-07 đã được coi là phải sửa |

**Cần quyết định của chủ dự án:** vá (Standard sẽ khác v1.2.0, có chủ đích) hay chấp nhận có ghi nhận.

### D8-01 — P2 — Legal đảo thứ tự đọc khi tách phép nối liên trang của Docling

| | |
|---|---|
| File | `open_notebook/ocr/legal_normalizer.py:1480-1562` (`_split_item`, vòng lặp 1548-1559), `:1364-1366` (`_reading_key`) |
| Nguyên nhân | Phần tách ra được chèn lại sau mọi anh em có `(trang, top)` nhỏ hơn — kể cả đoạn văn và tiêu đề. Bbox của phần ở trang sau do Docling ghi bằng chiều cao của trang đầu (`readingorder_model.py:657-670`) ⇒ `top` lệch `H2 − H1` |
| Tái hiện | `uv run pytest tests/review_phase12d8/test_legal_d8.py -k d8_01 -q` |
| Thực tế | Trang 820 pt → 842 pt: `…theo quy định` / `Điều 6. Hiệu lực thi hành` / `của pháp luật hiện hành…` / `Thông tư này có hiệu lực…`. Ngang → dọc: phần nối nằm sau cả Điều 6 và nội dung của nó. Trang hai cột: đoạn đầu cột phải đứng trước phần nối ở cột trái. Không mất chữ; cảnh báo không nhắc tới vị trí |
| Mong đợi | Phần tách đứng ngay sau phần đầu; chỉ vượt qua item Docling đã bỏ qua khi nối |
| Sửa tối thiểu | (1) Dừng vòng lặp khi anh em kế tiếp có nhãn ngoài {`PAGE_HEADER`, `PAGE_FOOTER`, `TABLE`, `PICTURE`, `CAPTION`, `FOOTNOTE`}. (2) Khi tính vị trí của provenance thứ ≥ 2, đổi bbox bằng chiều cao trang của provenance đầu. (3) Thêm fixture trang khác kích thước và hai cột vào oracle |
| Có từ | 12D5 (`_split_item` của R2-01); 12D7 tách **mọi** phép nối liên trang nên lỗi lộ rộng hơn |
| Vì sao là blocker | Thứ tự nội dung pháp lý bị đổi trong chế độ có cam kết "không đảo thứ tự"; PDF ghép từ nhiều nguồn và phụ lục khổ ngang là tình huống thường gặp |

### D8-02 — P2 — Footnote gắn vào bảng / ảnh không có trong nội dung

| | |
|---|---|
| File | `open_notebook/ocr/legal_normalizer.py:539-672` (`_build_serializer` không xuất `item.footnotes`); upstream `docling_core/transforms/serializer/common.py:434-435` |
| Nguyên nhân | Docling gắn `FOOTNOTE` đứng ngay sau bảng / ảnh vào item đó; serializer Markdown không xuất footnote của bảng / ảnh; Legal không cứu |
| Tái hiện | `uv run pytest tests/review_phase12d8/test_legal_d8.py -k "d8_02 or attaches" -q` |
| Thực tế | `(1) Theo Thông tư số 15/2024/TT-BNNPTNT ngày 01/02/2024.` dưới bảng: có trong `doc.texts`, không có trong Standard, không có trong Legal, không cảnh báo |
| Mong đợi | Legal: có trong nội dung ngay sau bảng / ảnh, hoặc tối thiểu có cảnh báo có trang. Standard: giữ hành vi v1.2.0 |
| Sửa tối thiểu | Trong `LegalDocSerializer`, xuất footnote của `TableItem` / `PictureItem` sau item (docling-core có sẵn `serialize_footnotes`), thêm cảnh báo `attached_footnote_kept`; thêm fixture "footnote ngay dưới bảng" |
| Có từ | v1.2.0 (upstream); Legal chưa bao giờ xử lý |
| Vì sao là blocker | Mất nội dung pháp lý, im lặng, trong chế độ có cam kết bảo toàn nội dung. Với Standard: giới hạn đã biết, cần ghi nhận |

## B. Phải xong trước khi kết quả Local gate tương ứng có giá trị (không phải runtime)

| Mã | Mức | Việc | Local gate bị ảnh hưởng |
|---|---|---|---|
| D8-STD-01 | P2 | `phase12_standard_diff.py`: khác byte nhưng cùng token phải là lớp thất bại | G-04 (W-12D7-02e) |
| D8-STD-02 | P2 | Bằng chứng theo từng crop, mỗi lần xuất hiện dùng một lần | G-04 |
| D8-STD-04 | P2 | rc ≠ 0 khi `not verified`, tài liệu thiếu một phía, hoặc 0 tài liệu | G-04 |
| D8-STD-03 | P2 | Bước xuất tạo TSV thô của **chính lần gọi** ingestion theo từng crop; khớp tên chính xác | G-04 |
| D8-ORI-01 | P2 | `rotated_copy` theo quy ước góc của Docling | G-02 với vùng 90° / 270° |
| D8-OFF-11 | P2 (đọc mã) | `[string[]]$python = …` trong `build-package.ps1` | G-07 trên máy không có `uv` |

Cho tới khi B xong, G-04 chỉ có giá trị nếu kèm so byte trực tiếp (`fc /b` hoặc `cmp`) và đọc tay từng hunk.

## C. Nên sửa trước phát hành (không chặn)

| Mã | Mức | Việc |
|---|---|---|
| D8-OFF-01 | P2 | Banner EXPERIMENTAL trong `--help` và khi chạy `update` / `finish` / `rollback` |
| D8-OFF-02 | P2 | Release notes 1.3.0-rc.1 dẫn production tới `OFFLINE_UPDATE_MANUAL_FALLBACK.md` |
| D8-OFF-05, 07, 08, 10, 13, 14, 15 | P3 | Bảy chỗ sửa trong tài liệu quy trình thủ công / hợp đồng tích hợp |
| D8-OFF-03, 04 | P3 | Hai cửa sổ đổi tên chưa nguyên tử trong `build` |
| D8-ORI-02, 03, 04 | P3 | Trạng thái cổng trong readiness / JSON; ghi chú về checkout Windows đã có; sửa câu kết luận của W-12D7-01a |
| D8-OFF-06 | P2 (tiềm ẩn) | `migration_required` — không ảnh hưởng rc.1 (không có migration mới) |

P3 / P4 còn lại (oracle, test): [PHASE12D8_FINDING_STATUS.json](PHASE12D8_FINDING_STATUS.json). Không đề xuất mở
thêm vòng audit tổng quát; sau khi A và B được xử lý chỉ cần một lượt kiểm lại có mục tiêu trên đúng các test
`xfail(strict=True)` của `tests/review_phase12d8/` (test đạt ⇒ strict xfail báo lỗi ⇒ gỡ marker).

## D. Rủi ro còn lại, không phải blocker

- Legal vẫn để một đoạn liên trang khi Docling đã bỏ gạch nối mà không có bằng chứng trước khi ghép (cảnh báo
  `upstream_dehyphenation`).
- Nhánh khóa `msvcrt`, `build-package.ps1`, `phase12-test.ps1` chưa từng chạy trong review này.
- Nguyên nhân của 11 vùng xoay sai trên Windows chưa được xác nhận.
- State machine của updater tự động không được review lại; nó phải giữ nhãn EXPERIMENTAL.
