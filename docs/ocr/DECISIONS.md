# OCR Engine Manager — Quyết định kiến trúc

Mỗi quyết định: bối cảnh → quyết định → phương án bị loại. Bản tóm tắt dạng ADR nằm ở
`docs/7-DEVELOPMENT/decisions/ADR-013-ocr-engine-manager.md`.

## D-01. Chỉ dùng OCR model class có sẵn của Docling

- **Quyết định:** 4 lựa chọn ánh xạ trực tiếp sang `RapidOcrOptions`, `TesseractCliOcrOptions`
  (×2: fast/best), `EasyOcrOptions`. Không plugin, không kế thừa `BaseOcrModel`, không monkey
  patch.
- **Loại bỏ:** VietOCR/TrueOCR/… (cần adapter — cấm); `TesseractOcrOptions` (tesserocr, cần
  build C-extension, không cần thiết vì đã có CLI).

## D-02. Truyền `ocr_options` bằng lớp cấu hình tối thiểu trong ChatBot5400

- **Bối cảnh:** Content Core 2.0.7 không nhận `ocr_options` (Audit §5).
- **Quyết định:** module `open_notebook/ocr/docling_extract.py` dựng **đúng** các
  `PdfPipelineOptions` mà Content Core dựng (`do_ocr`, `do_formula_enrichment`,
  `do_picture_description`, `do_chart_extraction`, output markdown) **cộng thêm**
  `ocr_options` (+ `accelerator_options` khi người dùng đặt số luồng). Chỉ áp dụng cho file
  mà Content Core cũng sẽ định tuyến sang Docling *và* là PDF/ảnh. Mọi loại nguồn khác, và
  cấu hình mặc định (xem D-03), vẫn gọi nguyên `content_core.extract_content`.
- Test `tests/test_ocr_docling_parity.py` so khớp tham số với `extract_docling` của Content
  Core đang cài để phát hiện lệch khi nâng cấp.
- **Loại bỏ:** fork Content Core (cần repo fork + bảo trì, phiên không được tạo repo); vá
  site-packages / monkey patch (cấm); viết lại pipeline (cấm).
- **Bảo trì:** khi Content Core upstream hỗ trợ `ocr_options`, thay lớp này bằng
  `ContentCoreConfig(...)` và xoá `docling_extract.py`.

## D-03. RapidOCR: tương thích ngược tuyệt đối

- **Quyết định:** `rapidocr` = cấu hình *đã xác minh* mà `OcrAutoOptions` đang cho ra:
  `RapidOcrOptions(backend="onnxruntime" nếu có onnxruntime, ngược lại "torch", lang=[])`.
  Khi môi trường khiến Auto vẫn chọn đúng RapidOCR (không nemotron, không EasyOCR hoặc có
  onnxruntime, không macOS) *và* người dùng không đổi số luồng / full-page ⇒ **đi nguyên
  đường Content Core** (không đổi một dòng hành vi). Ngược lại (vd. đã cài EasyOCR) ⇒ dùng
  lớp D-02 với `RapidOcrOptions` ghim ⇒ Auto không thể âm thầm đổi sang EasyOCR.
- Không nâng cấp PP-OCR, không đổi backend, không đổi nơi RapidOCR lưu model.
- **Loại bỏ:** luôn truyền `OcrAutoOptions` (rủi ro đổi engine khi cài EasyOCR).

## D-04. Tesseract Fast/Best: một `TESSDATA_PREFIX` cố định, mã ngôn ngữ theo thư mục con

- **Bối cảnh:** Docling 2.129 chỉ dùng `TesseractCliOcrOptions.path` cho lệnh OCR chính;
  `tesseract --list-langs` (kiểm tra ngôn ngữ) và OSD (`-l osd`, xoay trang) chạy **không**
  có `--tessdata-dir` ⇒ chỉ dùng `path` thì `vie` bị báo "not installed".
- **Quyết định:** đặt `TESSDATA_PREFIX=<OCR_MODELS_DIR>/tesseract` **một lần cho cả process**
  (Dockerfile `ENV` + `setdefault` khi khởi tạo) — giá trị không đổi theo request nên không
  có race giữa các job. Trọng số: `tesseract/fast/{vie,eng}.traineddata`,
  `tesseract/best/{vie,eng}.traineddata`, `tesseract/osd.traineddata` (dùng chung, sha256 hai
  repo giống hệt). Ngôn ngữ: `["fast/vie","fast/eng"]` hoặc `["best/vie","best/eng"]`;
  `path` cũng trỏ cùng thư mục. Đã kiểm chứng `tesseract --list-langs` liệt kê `fast/vie`…
- Nếu operator đặt `TESSDATA_PREFIX` khác ⇒ trạng thái `incompatible` kèm hướng dẫn, không
  ghi đè.
- **Loại bỏ:** đổi `os.environ` theo từng job (race); wrapper script `tesseract_cmd` (hack);
  copy vào tessdata hệ thống (fast/best trùng tên file).

## D-05. Worker đọc Settings mới mỗi lần xử lý nguồn

- **Bối cảnh:** `RecordModel` singleton nạp DB một lần/process ⇒ worker dùng Settings cũ.
- **Quyết định:** `content_process` gọi `ContentSettings.clear_instance()` trước
  `get_instance()` ⇒ chuyển engine có hiệu lực ở job kế tiếp, không cần restart. Job đang
  chạy giữ nguyên engine đã chọn lúc bắt đầu (chuyển engine an toàn).

## D-06. Cài đặt theo nhu cầu, tách model / runtime

| Thành phần | Cách cài | Lưu ở đâu | Sống sót recreate? |
|---|---|---|---|
| Model weights (tessdata, EasyOCR .pth) | Job worker do admin bấm "Cài đặt" (URL + sha256 ghim cứng trong mã) | `/app/data/ocr/models` (volume) | Có |
| Python package `easyocr==1.7.2` | Entrypoint (`OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR=true`) hoặc admin CLI; `uv pip` dùng `UV_CACHE_DIR` trên volume; offline `--no-index --find-links` | venv (image layer) + cache wheel trên volume | Khôi phục tự động từ cache/bundle |
| System package `tesseract-ocr` | Build arg `OCR_INSTALL_TESSERACT=true` **hoặc** entrypoint (`OPEN_NOTEBOOK_ENABLE_OCR_TESSERACT=true`, apt hoặc `.deb` offline) | filesystem container | Khôi phục tự động mỗi container |
| Cấu hình | `ContentSettings` (SurrealDB) | DB | Có |

- **Không** chạy `pip`/`apt` từ HTTP request; web chỉ tải *model* có checksum ghim cứng.
- **Loại bỏ:** cài runtime từ UI (cần root/pip tuỳ ý từ web); mount Docker socket; đưa
  EasyOCR vào dependency bắt buộc.

## D-07. Không âm thầm fallback

- Engine được chọn nhưng không sẵn sàng lúc xử lý ⇒ job lỗi với thông báo rõ ràng
  (`ValueError` ⇒ không retry vô ích), log engine thực tế. Kích hoạt engine (`activate`) bị từ
  chối nếu engine chưa `ready` ⇒ engine đang dùng không bị thay đổi.
- Không có cấu hình fallback (không cần cho phạm vi này).

## D-08. Xác thực job OCR bằng nonce

- `POST /api/commands/jobs` (có sẵn) cho mọi user đăng nhập submit command bất kỳ. Command
  `ocr_install_model` / `ocr_test_engine` chỉ chạy khi `nonce` khớp file trạng thái do API
  admin tạo ⇒ user thường không thể kích hoạt cài đặt qua endpoint chung.

## D-09. CPU cho OCR, không ép phần khác

- EasyOCR: `use_gpu=False`. Tesseract: CPU bẩm sinh. RapidOCR: giữ hành vi gốc (device auto ⇒
  CPU trên máy không GPU như VPS hiện tại). Không đặt `accelerator_options.device` (tránh ép
  Layout/TableFormer); `num_threads` chỉ đặt khi admin chọn giá trị (mặc định giữ của Docling).

## D-11. Nguồn URL là PDF/ảnh cũng theo engine đã chọn

- Content Core tải file từ URL (PDF/ảnh) rồi chạy Docling Auto. Khi cấu hình OCR khác mặc định,
  ChatBot5400 HEAD-check bằng `detect_remote_mime` của Content Core và tải bằng chính
  `_download_remote_file` của Content Core, rồi dùng lớp D-02. Trang web/YouTube không đổi. Test
  `test_content_core_url_helpers_still_exist` canh chừng khi nâng cấp.

## D-12. Ảnh giữ nguyên mặc định Docling

- Content Core không đặt format option cho ảnh ⇒ ảnh dùng mặc định Docling (OCR bật, enrichment
  tắt). Lớp D-02 cho ảnh chỉ thêm `ocr_options` (`test_images_keep_docling_defaults_except_ocr`).

## D-13. Gói runtime staged cần digest ghim ngoài volume

- `OCR_TRUSTED_WHEELS_SHA256` / `OCR_TRUSTED_DEBS_SHA256` (in ra bởi `bundle install`) là mỏ neo
  tin cậy; không khớp ⇒ không cài, engine báo runtime thiếu.

## D-10. Kiểm thử trong Cloud ở mức OCR stage

- Hugging Face & modelscope bị chặn ⇒ không chạy được full pipeline. Integration test chạy OCR
  model của Docling qua `get_ocr_factory()` (factory chính thức) trên trang đã render bởi
  backend PDF của Docling. Full pipeline: `scripts/ocr/acceptance_full_pipeline.py` chạy trên
  máy triển khai. Kết quả Cloud ghi rõ phạm vi.

## D-14. Khoá phiên bản runtime + guard tương thích (Phase 7)

- **Bối cảnh:** image cơ sở theo `uv.lock` (`uv sync --frozen`), nhưng Docling được entrypoint cài lúc
  khởi động bằng `uv pip install content-core[docling]==2.0.7` **không theo lock** ⇒ một container mới
  hôm nay sẽ nhận Docling **2.150.0**, RapidOCR 3.10.0, torch 2.15.0 (đã kiểm chứng bằng
  `uv pip compile`), không phải 2.129.0 / 3.9.2 / 2.14.0 đã kiểm thử. EasyOCR cũng không được khoá.
- **Quyết định:**
  1. Thêm extra `ocr-easyocr = ["easyocr==1.7.2"]` vào `pyproject.toml` ⇒ EasyOCR và phụ thuộc nằm
     trong `uv.lock` (không phiên bản cũ nào thay đổi — đã so sánh).
  2. Dockerfile `uv export --frozen ... --extra docling --extra ocr-easyocr` ⇒
     `/app/runtime-constraints.txt`; entrypoint (Docling) và CLI (EasyOCR) cài với `-c` ⇒ container
     mới nhận đúng phiên bản trong lock. Dev: CLI tự export từ `uv.lock`. Không có constraints ⇒ CLI
     từ chối cài EasyOCR (trừ khi override).
  3. `open_notebook/ocr/compat.py`: phiên bản đã kiểm chứng + **dấu vân tay mã nguồn** (SHA-256 của
     `inspect.getsource`) của các hàm nội bộ Content Core mà lớp OCR mô phỏng/tái dùng
     (`extract_docling`, `_extract_file`, `_extract_url`, `_route_for_mime`, `_download_remote_file`,
     `_fetch_remote_file`, `detect_remote_mime`) và hành vi Docling dựa vào (Auto OCR, Tesseract CLI
     list-langs/run). Lệch ⇒ engine khác RapidOCR = `incompatible`, đường mặc định vẫn đi Content Core;
     chỉ bỏ qua bằng `OCR_ALLOW_UNVERIFIED_DEPENDENCIES=true` (tường minh).
- **Loại bỏ:** siết `content-core==2.0.7` trong `pyproject.toml` (lock đã khoá; guard bắt cả bản vá
  cùng số phiên bản); fork Content Core (chưa cần).

## D-15. Ảnh luôn theo engine đã chọn

- Content Core không đặt option cho ảnh ⇒ Docling luôn OCR ảnh (kể cả khi tắt `docling_ocr`). Nếu
  giữ đường Content Core cho ảnh khi OCR tắt, cài EasyOCR sẽ khiến Auto chọn EasyOCR và **tải trọng số
  khi xử lý**. ⇒ Ảnh luôn đi lớp OCR với engine đã chọn; PDF khi tắt OCR vẫn đi Content Core.

## D-16. RapidOCR trên CPU: giữ mặc định, thêm lựa chọn tường minh

- Docling đặt thiết bị RapidOCR theo `accelerator_options.device` (AUTO ⇒ CUDA nếu torch thấy GPU).
  Production dùng torch CPU (`UV_TORCH_BACKEND=cpu`) ⇒ chạy CPU. Ép CPU mặc định sẽ đổi hành vi trên
  máy có GPU ⇒ **không làm mặc định**. `OCR_RAPIDOCR_FORCE_CPU=true` dùng `RapidOcrOptions.rapidocr_params`
  (API chính thức) tắt `use_cuda`/`use_dml` **chỉ cho OCR**; Layout/TableFormer giữ thiết bị của Docling.

## D-17. Không gỡ model khi tài liệu đang được xử lý

- Tesseract đọc traineddata ở mỗi trang ⇒ job đang chạy (bắt đầu trước khi đổi engine) có thể hỏng
  nếu gỡ model. API từ chối gỡ khi có `process_source` đang `running`, hoặc đang có test của engine;
  không kiểm tra được DB ⇒ từ chối (fail closed). Job đang chờ (`new`) an toàn vì đọc Settings khi bắt đầu.

## D-18. Khôi phục offline từ cache

- `OCR_OFFLINE=true`: entrypoint cài Docling với `uv --offline` (cache uv trên volume); CLI cài
  EasyOCR từ gói staged (cần digest ghim) hoặc, nếu không có, từ cache uv với `--offline`. Docker
  acceptance kiểm tra bằng mạng `internal` (DB vẫn tới được, Internet bị chặn).
