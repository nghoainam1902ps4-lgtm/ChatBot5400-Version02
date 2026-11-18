# Phase 12D7 — E0-07: bản vá có kiểm soát cho Docling 2.129.0 (chữ trong TSV của Tesseract giữ nguyên)

Quyết định: [D-39](../ocr/DECISIONS.md). Mã: [`open_notebook/ocr/docling_patches.py`](../../open_notebook/ocr/docling_patches.py).
Test: [`tests/test_ocr_tesseract_tsv_text.py`](../../tests/test_ocr_tesseract_tsv_text.py) (74),
[`tests/test_phase12d7_standard_parity.py`](../../tests/test_phase12d7_standard_parity.py),
[`tests/test_phase12d7_numeric_preservation.py`](../../tests/test_phase12d7_numeric_preservation.py).

## 1. Nguyên nhân (đã đọc toàn bộ hàm upstream)

`docling/models/stages/ocr/tesseract_ocr_cli_model.py`, `TesseractOcrCliModel._run_tesseract` (Docling 2.129.0,
docling-core 2.96.0):

```python
df_result = pd.read_csv(io.StringIO(decoded_data), quoting=csv.QUOTE_NONE, sep="\t")
df_filtered = df_result[df_result["text"].notna() & (df_result["text"].apply(str).str.strip() != "")]
```

`__call__` dựng mỗi ô OCR bằng `TextCell(text=str(row["text"]))`. pandas **suy diễn kiểu theo từng vùng OCR** (mỗi
vùng layout là một lần gọi Tesseract ở chế độ OCR mặc định):

| TSV thô (Tesseract đọc đúng) | Ô OCR upstream | Điều kiện |
|---|---|---|
| `0001`, `000123`, `000000000000000123` | `1.0`, `123.0`, `123.0` | mọi từ của vùng là số (dòng page/block/par/line không có chữ ⇒ NaN ⇒ cột `float64`) |
| `2024`, `9.`, `0.`, `12.50` | `2024.0`, `9.0`, `0.0`, `12.5` | như trên |
| `true`, `false` | `True`, `False` | mọi từ là boolean |
| `NA`, `N/A`, `NULL`, `NaN`, `None`, `nan`, … (19 chuỗi NA mặc định) | **mất** | ở **mọi** vùng, kể cả dòng hỗn hợp |

Tái hiện ĐỎ ba cách: TSV thô chọn trước qua lớp Docling thật (`test_red_upstream_*`, 15 test); Tesseract thật trên
vùng render (`test_real_tesseract_numeric_crop_is_rewritten_by_upstream`); stage OCR thật của Docling trên trang PDF
(`test_real_full_page_ocr_through_doclings_ocr_stage`, `test_phase12d7_standard_parity.py`).

## 2. Bản vá

- `read_tesseract_tsv()`: `pd.read_csv(..., quoting=csv.QUOTE_NONE, sep="\t", dtype={"text": str},
  keep_default_na=False, na_values={<mọi cột khác>: <19 chuỗi NA mặc định của pandas>})`. Cột `text` là chuỗi, không
  chuyển NA; **mọi cột khác** (level…conf) giữ đúng kiểu và giá trị upstream, kể cả trường số hỏng (test so từng cột,
  `dtype` và `equals`). Danh sách NA được kiểm bằng `pandas._libs.parsers.STR_NA_VALUES` (`test_default_na_list_is_pandas_own`).
- `_run_tesseract()`: bản sao đúng của hàm upstream, chỉ thay dòng đọc TSV. Bộ lọc dòng rỗng, dòng lệnh, log không
  đổi (test so AST với upstream: `test_patched_method_is_upstream_except_the_tsv_parse`).
- Không vá pandas, không sửa site-packages, không fork Docling, không thêm dependency, không sửa traineddata, không
  tạo engine mới. Thông báo bản quyền MIT của Docling nằm trong docstring module.

### Chặn phiên bản và mã nguồn

`apply()` chỉ chạy khi `docling == 2.129.0` **và** SHA-256 của `inspect.getsource` hàm upstream đúng
`e0623aa9…de233c` (cùng giá trị `compat.DOCLING_FINGERPRINTS` kiểm). Không khớp ⇒ `TsvPatchError` (một
`ValueError`): engine Tesseract **từ chối chạy** với thông báo rõ — không bao giờ chạy không vá, không áp bản vá vào
mã khác (`test_another_docling_version_is_refused_not_patched`, `test_changed_upstream_source_is_refused_not_patched`).
Idempotent; hàm upstream vẫn truy cập được (`__cb5400_upstream__`) để fingerprint luôn kiểm mã thật
(`compat.source_fingerprint`).

### Phạm vi áp dụng

`open_notebook.ocr.options.build_ocr_options` — nơi duy nhất tạo `TesseractCliOcrOptions` — gọi `apply()` cho mọi
engine Tesseract: Fast, Best, custom (Agri), ở cả Standard và Legal (`test_the_patch_is_applied_by_every_tesseract_engine_and_no_other`).
RapidOCR, EasyOCR không dùng mã này và không đổi. PDF Prep, Auto Full Page on Watermark, Layout Heron, TableFormer
không đổi.

### Build chính thức và gói offline

Bản vá là mã ứng dụng ⇒ có trong image (cả profile `OCR_PREINSTALL_RUNTIMES=true` lẫn Docling cài lúc khởi động) và
trong gói offline; máy chủ không tải gì. `offline_package.py inventory` (chạy trong image) áp bản vá với Docling thật
của image và ghi `runtimes_baked.docling_tsv_patch` + `runtime_artifacts.docling_tsv_patch`; image có Docling mà
không áp được bản vá ⇒ gói `NOT_READY` (`test_inventory_probe_applies_the_tsv_patch_with_the_real_docling`,
`test_an_image_whose_docling_cannot_take_the_tsv_patch_is_not_ready`).

## 3. Kết quả (Cloud)

| Kiểm | Kết quả |
|---|---|
| 33 token (danh sách E0-07 + tiếng Việt, ngoặc kép, `…`): một token / vùng, cả dòng | ô OCR = TSV thô, đúng thứ tự |
| Vùng chỉ có số (`0001 000123`, `2024 9.`, `12.50 0.`) | giữ số 0 đầu, dấu chấm cuối |
| Tab thừa trong trường, TSV rỗng, dòng chữ rỗng / khoảng trắng | giống hệt upstream |
| Tesseract thật, 8 vùng (`0001`, `000123`, `2024`, `12.50`, `NA`, `Số: 0001/2024`, `Mã NA, N/A`, `Trang 2`) | ô OCR = TSV thô |
| Stage OCR thật của Docling, toàn trang (FULL_PAGE) | mọi token có mặt; khác upstream đúng ở `NA` / `N/A` |
| Stage OCR thật của Docling, một vùng / dòng (LAYOUT_REGIONS — như ingestion), gồm vùng đầu trang (quốc hiệu) và vùng số trang (`Trang 2`) | upstream: `1.0`, `123.0`, `2024.0`, `12.5`, mất `NA N/A`; bản vá: chữ thật; 6 vùng còn lại giống hệt từng byte |
| `9.` qua Legal | giữ nguyên (`test_numbers_and_codes_in_the_body_are_kept_verbatim`) |

`9.` không bị mất ở tầng ô OCR hay Legal. Ở chế độ Standard, Docling / CommonMark có thể hiển thị dòng chỉ gồm `9.`
như một mục danh sách rỗng — hành vi hiển thị v1.2.0, không phải mất chữ; nếu Windows thấy `9.` mất trong nội dung
lưu thì ghi thành finding riêng (tầng layout / serializer), đúng chỉ thị.

## 4. Standard: khác biệt có chủ đích

Standard không còn giống v1.2.0 từng byte ở đúng những token parser cũ làm sai. `scripts/ocr/phase12_standard_diff.py`
phân loại mọi khác biệt: **unchanged** / **expected parser fix** (chữ cũ đúng là dạng pandas tạo ra từ token mới
**và** token mới có trong TSV thô của tài liệu) / **not verified** (đúng dạng nhưng không có TSV chứng minh) /
**unexpected regression** (mọi thứ khác — chặn phát hành). Trên trang tổng hợp qua stage OCR thật:
`docs/review/phase12d7/standard_diff_synthetic/` — 1 tài liệu, 3 hunk, tất cả `expected parser fix`, 0 hồi quy.
22 PDF thật: mục W-12D7-02 của [checklist](PHASE12D7_LOCAL_ACCEPTANCE_CHECKLIST.md). Tiêu chí parity không bị hạ:
mọi byte khác vẫn phải giống.

## 5. Nâng Docling sau này

Bản vá chặn mọi phiên bản khác 2.129.0. Nâng Docling ⇒ đọc lại `_run_tesseract` mới; nếu upstream đã sửa phép đọc
TSV thì bỏ bản vá; nếu chưa thì cập nhật `DOCLING_VERSION`, `UPSTREAM_SHA256`, bản sao hàm, rồi chạy lại toàn bộ test
trên. `OCR_ALLOW_UNVERIFIED_DEPENDENCIES` **không** bỏ qua chốt này.

## 6. Rollback

Image v1.2.0 (không có bản vá) vẫn dùng được như trước; dữ liệu không đổi. Tài liệu đã xử lý không tự xử lý lại.
