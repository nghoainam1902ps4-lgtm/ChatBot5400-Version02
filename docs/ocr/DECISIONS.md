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

## D-19. Khoá API job nền và kiểm tra lại đầu vào trong worker (Phase 8A)

- `/api/commands/*` chỉ dành cho admin (`require_admin` ở cấp router). Submit command tổng quát bị
  **tắt**: allowlist `GENERIC_SUBMIT_ALLOWLIST` để trống. Mọi tính năng đều có endpoint riêng, nên
  không cần đường tổng quát.
- Worker áp dụng phòng thủ nhiều lớp, không tin API (`open_notebook/utils/job_input_guard.py`):
  - `file_path` phải nằm trong `UPLOADS_FOLDER` (kiểm tra bằng `realpath`);
  - chỉ xoá file nằm trong uploads;
  - URL được `validate_url()` kiểm tra lại, kèm pre-check từng bước redirect. Đây là phòng thủ
    nhiều lớp: lần tải thật vẫn tự theo redirect, xem `BACKGROUND_JOB_SECURITY.md` §5;
  - record id phải đúng bảng;
  - với `process_source`, file/URL phải trùng với asset của chính source đó.
- Không tiếp tục chặn ở API rồi tin tưởng worker. Chi tiết: `docs/security/BACKGROUND_JOB_SECURITY.md`.

## D-20. Mô hình sẵn sàng offline: chứng minh bằng chạy pipeline thật

- Có thể chẩn đoán từ file và checksum, nhưng **không bao giờ** được coi đó là "sẵn sàng". Sẵn sàng
  chỉ xác định bằng cách chạy pipeline production (Heron + TableFormer accurate + OCR đã chọn) trong
  tiến trình con. Có ba mức `online` / `local_only` / `offline`; `local_only` cho mọi proxy trỏ tới
  một cổng đóng.
- Kết quả kiểm tra gắn với một fingerprint, gồm:
  - phiên bản các thành phần;
  - checksum model;
  - snapshot Heron/TableFormer trong cache;
  - trọng số RapidOCR;
  - các cờ RapidOCR.

  Bất kỳ thay đổi nào cũng làm kết quả **lỗi thời**.
- Phân biệt rõ OCR-only, full pipeline, local-only và offline thật.
- Lý do chọn cách này thay vì `HF_HUB_OFFLINE=1`: biến đó chỉ chặn được Hugging Face. Proxy chết chặn
  được cả modelscope (RapidOCR) và mọi lần tải khác.

## D-21. RapidOCR lưu bền vững là tuỳ chọn (`OCR_RAPIDOCR_PERSISTENT`)

- Mặc định giữ nguyên hành vi: trọng số nằm trong thư mục gói của venv, warm-up bằng `prepare`. Hệ quả
  là trọng số mất khi recreate, và readiness phát hiện được việc này.
- Khi bật tuỳ chọn, dùng tham số chính thức `RapidOcrOptions.rapidocr_params["Global.model_root_dir"]`,
  trỏ tới `<OCR_MODELS_DIR>/rapidocr`. Vẫn cùng model và backend. Trọng số được nhập từ venv, chỉ nhận
  file có SHA-256 khớp `default_models.yaml` của RapidOCR. Đường Content Core mặc định không bị ảnh hưởng.
- Không bật làm mặc định vì hai lý do:
  - đổi đường xử lý mặc định (phải đi lớp OCR thay vì Content Core);
  - backend torch chưa được kiểm chứng thực tế (modelscope bị chặn trong Cloud).

## D-22. Thiếu model khi offline ⇒ lỗi vĩnh viễn, có hướng dẫn

- Lỗi tải model (`LocalEntryNotFoundError`, `OfflineModeIsEnabled`, `DownloadFileException`, hoặc lỗi
  nhắc tới host HF/modelscope) trong `content_process` được đổi thành `ValueError` kèm hướng dẫn
  "Prepare models". Job vì vậy `failed` ngay, không retry vô ích và không treo.
- Không fallback sang engine khác (vẫn giữ D-07).

## D-23. Docker acceptance: offline bằng cách ngắt mạng egress của container đang chạy

- `docker network disconnect`, không recreate. Lý do: recreate khi offline đã thay đổi đúng thứ cần
  kiểm tra, cụ thể là trọng số RapidOCR trong layer container.
- App và DB dùng chung mạng `internal: true`, nên DB vẫn tới được. Script kiểm tra cả hai chiều:
  Internet bị chặn, DB vẫn tới được.
- Restart khi offline cũng thực hiện trên cùng container. Recreate/cập nhật thực hiện khi online, rồi
  chạy thêm một vòng offline.

## D-24. Timeout có giới hạn cho mọi request Hugging Face Hub (Phase 8B)

- Bối cảnh (nghiệm thu thật, Docker bước 3): sau khi server mất Internet, job OCR đầu tiên của worker
  treo ~16 phút. `snapshot_download` (huggingface_hub 0.36) gọi `repo_info()` **không có timeout**
  trên kết nối keep-alive còn sót từ pha online; request chờ tới khi TCP bỏ cuộc (`tcp_retries2`).
- Quyết định: `open_notebook/ocr/hub_http.py` cài một backend session cho Hub, gán timeout mặc định
  (`OCR_HF_HUB_TIMEOUT`, mặc định 20 s) cho request **không** tự chọn timeout. Hub coi
  `requests.Timeout` là "offline" và dùng cache. Request có timeout riêng (tải file khi chuẩn bị
  online) giữ nguyên. Cài ở `content_process` (mọi đường xử lý, kể cả RapidOCR mặc định qua
  content-core) và `build_converter` (test engine, readiness, test tích hợp).
- Phạm vi: backend session của huggingface_hub là **toàn tiến trình** (API và worker), không chỉ
  Docling. Mọi request Hub không tự đặt timeout đều nhận 20 s chờ byte đầu tiên (timeout đọc, không
  phải tổng thời gian; tải file lớn không bị ảnh hưởng). Hub phản hồi chậm hơn 20 s khi `prepare`
  online ⇒ Hub client coi như offline và dùng cache / báo thiếu model; tăng `OCR_HF_HUB_TIMEOUT` nếu
  cần.
- Không chọn `HF_HUB_OFFLINE=1` cho worker: biến này được đọc lúc import, buộc phải recreate container
  để đổi, trái với mô hình "cùng container, online rồi offline" (D-20, D-23).
- Test: `tests/test_ocr_hub_http.py` dùng socket thật nhận kết nối nhưng không trả lời; không có bản
  sửa thì test treo (FAIL sau 30 s).

## D-25. Tesseract: lọc OSD độ tin cậy thấp, chuẩn hóa hướng trang, scale theo độ phân giải scan (Phase 8C)

- Bối cảnh: Docling 2.129 dò hướng (`tesseract --psm 0`) trên **từng vùng OCR** và xoay vùng theo kết
  quả bất kể `Orientation confidence`; không có tùy chọn chính thức để tắt hay đặt ngưỡng. Bảng scan
  đứng thẳng bị lật 180° (confidence 0,16), trang xoay bị đoán sai (0,02). Ảnh scan 150 DPI bị phóng
  lên 216 DPI và crop PNG không có DPI. Chi tiết: [OCR_FAILURE_ANALYSIS.md](OCR_FAILURE_ANALYSIS.md).
- Quyết định, bốn phần độc lập (chi tiết và số đo: [OCR_QUALITY_OPTIMIZATION.md](OCR_QUALITY_OPTIMIZATION.md)):
  1. `open_notebook/ocr/tesseract_gate.py` đặt qua tùy chọn chính thức `tesseract_cmd`: kết quả OSD có
     hướng ≠ 0 và confidence < 2,0 được trả về là 0°; mọi lệnh khác chuyển nguyên vẹn cho Tesseract.
  2. `open_notebook/ocr/pdf_prep.py`: dò hướng **cả trang** scan, sửa `/Rotate` trong bản sao tạm khi
     confidence ≥ 2,0. Áp cho mọi engine khi có `osd.traineddata`. File gốc không bị sửa; không render
     lại; lỗi bất kỳ → chuyển đổi file gốc như trước.
  3. `OcrOptions.scale = max(2,0; DPI_scan/72)`, không vượt mặc định 3; chỉ Tesseract. `DPI_scan` là độ
     phân giải **cao nhất** trong các trang scan của tài liệu, để không trang nào bị render thấp hơn trước.
  4. `user_defined_dpi 216` trong file config `tsv` của thư mục tessdata riêng.
- Vì sao không chọn phương án khác:
  - Thêm lề cho crop: 1 340 phép đo cho thấy lề không cải thiện OSD; và chỉ làm được bằng adapter.
  - `OcrMode.FULL_PAGE` toàn hệ thống: không tốt hơn, và OCR đè lên text layer của PDF sinh từ phần mềm.
  - PSM khác mặc định: 6/11/12 phá bảng; 1/4 không khác.
  - Rasterize lại PDF đã xoay: làm mất text layer và đổi tọa độ; `/Rotate` thì không.
- Ngưỡng 2,0 lấy từ số đo: OSD trên vùng sai có confidence ≤ 1,44; OSD trên trang sai ≤ 0,66 và đúng
  ≥ 4,77 (scale 3).
- Ranh giới: phần 1 là một file thực thi đứng giữa Docling và Tesseract. Nó không phải OCR adapter
  (không subclass, không xử lý ảnh/tọa độ/văn bản) và không sửa Docling, nhưng **cần chủ dự án xác
  nhận** là nằm trong giới hạn "chỉ dùng API chính thức". Tắt: `OCR_TESSERACT_OSD_GATE=false`.
- Giới hạn chi phí: dò hướng tối đa 200 trang đầu (`OCR_PAGE_OSD_MAX_PAGES`), 30 giây mỗi trang, và từ Phase 9B
  tối đa 600 giây cho cả bước (`OCR_PAGE_OSD_BUDGET_SECONDS`, D-30); lỗi ở
  một trang không ảnh hưởng trang khác. Gate chỉ được dùng khi `gate --version` chạy được (cần bit thực
  thi và `python3` trên PATH); không thì gọi thẳng Tesseract và ghi cảnh báo.
- Tắt phần 2–3: `OCR_PDF_PREP=false`. Biến môi trường là cấu hình toàn deployment, không đổi theo job.
- Test: `tests/test_ocr_quality_prep.py` (45 test, không cần engine thật) + 48 bài full pipeline chạy
  qua `convert_document` (điểm vào production).

## D-26. EasyOCR: `confidence_threshold` 0,2 (Phase 8C)

- Bối cảnh: mặc định 0,5 của Docling loại 10/15 dòng của một công văn scan 150 DPI, không dòng nào
  là rác (CER 0,85). Decoder / beam / contrast không chỉnh được qua API chính thức vì Docling gọi
  `readtext(im)` không tham số.
- Quyết định: `EasyOcrOptions.confidence_threshold = 0,2`; đổi bằng `OCR_EASYOCR_CONFIDENCE` (0–1,
  sai định dạng → 0,2). Không thêm trường Settings/UI.
- Vì sao 0,2 mà không phải 0: dưới 0,2 chỉ quan sát thấy dòng rác; 0,0 / 0,1 / 0,2 cho cùng kết quả
  trên trang đứng thẳng, nên 0,2 không mất gì mà vẫn lọc rác trên trang nhiễu.
- Giới hạn không sửa được: ở 150 DPI model Latin Gen2 đọc sai chữ số và dấu kể cả khi giữ mọi dòng.
  5 bài nghiệm thu của EasyOCR vẫn FAIL; không hạ ngưỡng, không thay model.

## D-27. Phân loại chất lượng và tiêu chí phát hành có điều kiện (Phase 8D)

Quyết định của chủ dự án, thực hiện trong Phase 8D:

1. **Ba trạng thái tách biệt:** (1) runtime/model sẵn sàng; (2) đã xác minh offline; (3) phân loại chất
   lượng. `EngineSpec.quality` ∈ `recommended` (Tesseract Best) · `speed` (Tesseract Fast) ·
   `compatibility` (RapidOCR) · `experimental` (EasyOCR). API trả `quality`; giao diện hiển thị riêng,
   không gộp vào trạng thái "Sẵn sàng". Giữ đủ 3 engine / 4 lựa chọn.
2. **EasyOCR = thử nghiệm:** giao diện hỏi xác nhận trước khi bật; không bao giờ là mặc định; không có
   fallback tự động sang engine nào (D-07 giữ nguyên). Không tuyên bố tăng DPI là sửa được mọi lỗi.
3. **Tiêu chí phát hành có điều kiện** (`scripts/ocr/release_criteria.py`): bổ sung, **không thay thế**
   48 bài gốc. Với mỗi engine × fixture, công cụ đánh giá lại *mọi* assertion của bài gốc rồi phân loại:
   - *Critical* — mọi số tiền, ngày, số hiệu; hình dạng bảng; giá trị số của từng dòng bảng; tiêu đề có
     mặt đúng vị trí khi không xét dấu. Không bao giờ được miễn.
   - *General* — CER, dấu tiếng Việt, tiêu đề đúng từng dấu, nhãn dòng bảng.
   - *Giới hạn đã chấp nhận* — **KL-1**: Tesseract mất dấu ở tiêu đề in đậm
     `BẢNG KÊ CHI TIẾT KHOẢN MỤC MẪU`. Chỉ áp dụng khi cụm đó vẫn có mặt, đúng vị trí, nếu so không dấu;
     và khi đó là lỗi **duy nhất** của bài. Bất kỳ lỗi nào khác ⇒ ngoại lệ không áp dụng.
   Kết quả: `PASS` · `PASS_WITH_KNOWN_LIMITATION` · `FAIL`. Kết quả bài gốc luôn được báo cùng.
4. Không sửa fixture, ground truth, ngưỡng; không `skip`/`xfail`; không sửa văn bản OCR; không từ điển
   sửa lỗi. Ngưỡng trong công cụ được một unit test giữ bằng ngưỡng của bài gốc.
5. **Chấp nhận `tesseract_gate.py`** (D-25 phần 1) sau review ở Phase 8D (`OCR_PHASE8D_REPORT.md` §2);
   rollback `OCR_TESSERACT_OSD_GATE=false` giữ nguyên.
6. **Chấp nhận `pdf_prep.py`** phạm vi hiện có. Trạng thái khả dụng của chuẩn hóa hướng trang được báo
   trung thực (`general.page_orientation`, metadata `page_orientation`, log); không cài hay tải Tesseract
   ngầm; RapidOCR / EasyOCR chạy bình thường khi thiếu Tesseract.
7. **Readiness theo cấu hình chất lượng:** fingerprint gồm `quality` (gate, ngưỡng, trạng thái hướng
   trang, ngưỡng EasyOCR). Đổi một trong số đó, hoặc cài/gỡ `osd.traineddata`, làm verdict cũ hết hiệu lực.

## D-28. SSRF qua redirect: rủi ro còn lại, điều kiện production (Phase 8D)

- Kiểm tra URL của worker là **pre-check**: Content Core / Docling tải lại URL và tự đi theo redirect, nên
  redirect khác ở lần tải thật và DNS rebinding **không** được chặn (`BACKGROUND_JOB_SECURITY.md` §5).
  Phase 8D **không** sửa điều này và không tuyên bố đã khắc phục.
- Không đổi firewall, mạng production hay kiến trúc URL ingestion trong phase này.
- Production readiness **phụ thuộc** một trong hai biện pháp được chủ dự án phê duyệt:
  (a) tắt URL ingestion với nguồn không tin cậy bằng cơ chế thực thi ở backend (chưa có trong mã — cần
  một thay đổi riêng); hoặc (b) chính sách egress của mạng do quản trị viên phê duyệt (chặn dải nội bộ,
  metadata, chỉ cho phép đích cần thiết) áp cho container ứng dụng.

## D-29. Công tắc tắt URL ingestion, mặc định TẮT (Phase 9A)

- Bối cảnh: rủi ro SSRF còn lại (D-28) — worker chỉ kiểm tra URL trước; Content Core / Docling tải lại và
  tự đi theo redirect; DNS rebinding không bị chặn. Chủ dự án chọn giảm thiểu bằng cách cho phép tắt hẳn
  chức năng thêm nguồn từ URL, không viết lại HTTP client của Content Core.
- Quyết định: biến môi trường `OPEN_NOTEBOOK_ENABLE_URL_INGESTION` (theo convention `OPEN_NOTEBOOK_ENABLE_*`
  của dự án). **Chỉ bật khi giá trị là `true` / `1` / `yes` / `on`.** Thiếu, rỗng hoặc sai chính tả ⇒ tắt.
  Không có API hay trường Settings để đổi; không vai trò nào được miễn (kể cả admin). Đọc ở mỗi lần gọi.
- **Vì sao mặc định tắt:** repository này là bản triển khai nội bộ; yêu cầu là không được âm thầm bật khi
  thiếu cấu hình. Hệ quả tương thích: bản triển khai nào đang dùng nguồn URL phải đặt
  `OPEN_NOTEBOOK_ENABLE_URL_INGESTION=true` khi nâng cấp (ghi trong `environment-reference.md`,
  `.env.example`, `docker-compose.yml`). Dữ liệu không đổi, không migration.
- Thực thi bốn tầng, mỗi tầng từ chối **trước** mọi truy vấn DNS hay request: API tạo nguồn (multipart và
  JSON, sync và async) → 403; API retry nguồn URL cũ → 403; lệnh worker `process_source` (gồm job đã xếp
  hàng trước khi tắt và job không đi qua API) → lỗi vĩnh viễn; nút graph `content_process` và hai hàm URL
  của lớp OCR.
- Giữ nguyên: nội dung đã trích xuất của nguồn URL cũ vẫn đọc, tìm kiếm, chat được; không xóa gì. Upload
  file, nhập văn bản, OCR, transformation, embedding, RAG, chat, gọi LLM, chuẩn bị model không bị ảnh hưởng.
- Frontend: lấy trạng thái từ `GET /api/capabilities` (`url_ingestion_enabled`); tab "Thêm URL" bị vô hiệu
  hóa kèm thông báo (vi/en). Trạng thái chưa biết (đang tải, backend cũ) ⇒ coi như tắt.
- **Không tuyên bố đã sửa SSRF.** Khi tắt: rủi ro được giảm thiểu vì chức năng không còn. Khi bật: hành vi
  và chính sách như cũ, rủi ro còn lại xuất hiện trở lại.
- Test: `tests/test_url_ingestion_switch.py` (43 test, có fixture chặn mọi truy vấn DNS/kết nối).

## D-30. Giới hạn tổng thời gian bước dò hướng trang (Phase 9B)

- Bối cảnh: bước dò hướng (`pdf_prep.py`) chạy trước Docling, trên vòng lặp sự kiện của worker; worker
  (surreal-commands) không có timeout cho job và production chạy `OPEN_NOTEBOOK_WORKER_MAX_TASKS=1`. Giới hạn
  cũ là 200 trang × 30 giây mỗi trang ⇒ trường hợp xấu nhất khoảng 100 phút trước khi Docling bắt đầu, và mọi
  job nền khác phải chờ. Nếu job thất bại rồi được thử lại, bước này lặp lại.
- Số đo trên máy nghiệm thu (8 CPU, fixture scan 150 DPI): 0,55–0,65 giây mỗi lần gọi OSD, khoảng 0,7 giây mỗi
  trang kể cả render ⇒ 200 trang cần khoảng 2,5 phút trong điều kiện bình thường.
- Quyết định: thêm ngân sách thời gian cho **cả bước** của một tài liệu, `OCR_PAGE_OSD_BUDGET_SECONDS`, mặc định
  **600 giây** (gấp khoảng 4 lần nhu cầu bình thường của 200 trang, để máy đang bận vẫn kiểm đủ). Giá trị sai,
  `nan`, `inf`, 0 hoặc âm ⇒ mặc định; tối đa 6000 giây (bằng trường hợp xấu nhất cũ). Timeout mỗi trang giữ 30
  giây. Trang đang kiểm được chạy nốt, nên giới hạn cứng là ngân sách + 30 giây (10,5 phút thay cho 100 phút).
- Khi hết ngân sách hoặc chạm giới hạn số trang: các trang còn lại **được chuyển đổi nguyên trạng** (không dò
  hướng); trang đã sửa trước đó được giữ; tài liệu **không** thất bại; file gốc không bị sửa. Metadata và log
  ghi `page_orientation_limit` = `time_budget` / `max_pages` và `orientation_checked_pages`.
- Không đổi chất lượng OCR trong điều kiện bình thường: ngân sách chỉ có tác dụng khi bước này chậm bất thường.
  Fingerprint readiness **không** gồm ngân sách (nó giới hạn thời gian, không đổi kết quả).
- Cùng đợt: `page.get_size()` được đưa vào trong khóa pdfium của Docling (mọi lời gọi pdfium của `pdf_prep`
  giờ đều giữ khóa; có test dò từng lời gọi); tài liệu luôn được đóng trong khóa; một trang pdfium không nạp
  được chỉ bị bỏ qua, không làm mất kết quả các trang khác.
- `OCR_HF_HUB_TIMEOUT` (D-24): từ chối `inf` và giá trị quá lớn (`inf` làm mọi request Hub lỗi ở tầng socket;
  giá trị lớn đưa hiện tượng treo 15 phút trở lại), tối đa 300 giây.
- Test: `tests/test_ocr_quality_prep.py` (ngân sách, giới hạn số trang, khóa pdfium, trang lỗi),
  `tests/test_ocr_hub_http.py`.

## D-31. Thực thi vai trò ở backend cho credential, model và các chức năng bảo trì (Phase 9B)

- Bối cảnh: review độc lập Phase 9B phát hiện lỗi **có sẵn từ trước tính năng OCR** (có ở `5e04227`): các
  route `/api/credentials/*` và `/api/models/*` chỉ yêu cầu đăng nhập. Tài khoản bất kỳ (kể cả vai trò chỉ xem)
  có thể tạo / sửa / xóa / kiểm tra credential nhà cung cấp. Hệ quả: (1) đổi `base_url` của một credential rồi
  bấm kiểm tra ⇒ khóa API đang lưu và toàn bộ lưu lượng chat về sau được gửi tới máy chủ khác; (2) "kiểm tra
  kết nối" tới địa chỉ nội bộ ⇒ dò mạng nội bộ **bất kể** `OPEN_NOTEBOOK_ENABLE_URL_INGESTION`. Điều này mâu
  thuẫn với mô tả "URL do quản trị viên cấu hình" của D-29. Giao diện vốn đã ẩn các trang này với người không
  phải quản trị viên; tài liệu `docs/7-DEVELOPMENT/authentication.md` nêu backend mới là nơi quyết định.
- Quyết định (sửa tối thiểu, không đổi mô hình vai trò): thêm `require_admin` cho
  - credential: tạo, sửa, xóa, test, discover, register-models, hai route migrate;
  - model: tạo, xóa, test, đổi mặc định, sync (2), auto-assign;
  - các route mà giao diện chỉ hiện cho quản trị viên: transformation tạo / sửa / xóa / execute /
    default-prompt, `POST /api/embed`, `POST /api/embeddings/rebuild`, `DELETE /api/insights/{id}`.
  Route chỉ đọc mà mọi tài khoản cần (danh sách model, mặc định, trạng thái credential, danh sách
  transformation) không đổi.
- `POST /api/sources/json` nhận `file_path` do người gọi đưa vào, miễn nằm trong thư mục uploads ⇒ một cộng
  tác viên có thể đọc (và với `delete_source` thì xóa) file do người khác tải lên, kể cả bài đang chờ duyệt.
  Từ nay người không phải quản trị viên phải tải file kèm request; quản trị viên giữ hành vi cũ.
- **Giữ nguyên, cần chủ dự án quyết định:** các route podcast (tạo, thử lại, xóa tập, hồ sơ tập / người nói)
  vẫn mở cho mọi tài khoản vì trang Podcast nằm ở mục "Tạo" hiển thị cho mọi người dùng; `GET
  /api/podcasts/jobs/{id}` trả trạng thái job cho mọi tài khoản. Xem `OCR_PHASE9B_REPORT.md`.
- Test: `tests/test_admin_route_authorization.py` — 401 / 403 cho từng route, quản trị viên vẫn dùng được, và
  một test ghim toàn bộ bề mặt: mọi route POST / PUT / DELETE hoặc có kiểm tra vai trò, hoặc nằm trong danh
  sách "cố ý mở".
- Thay đổi hành vi: script hoặc tài khoản không phải quản trị viên đang gọi các route trên sẽ nhận 403.

## D-32. Kết quả chuyển đổi một phần, từ điển RapidOCR, build arg Tesseract (Phase 9B)

- **Chuyển đổi một phần:** Docling không ném lỗi khi một trang hoặc một vùng OCR hỏng; nó trả kết quả với
  `PARTIAL_SUCCESS` và danh sách lỗi. Trước đây nguồn vẫn được lưu "hoàn tất" mà không có dấu vết. Từ nay
  `convert_file` ghi cảnh báo vào log và thêm `conversion_status`, `conversion_errors` vào metadata. Kết quả
  **không đổi** (không làm thất bại tài liệu — đó sẽ là thay đổi hành vi so với đường Content Core).
- **RapidOCR lưu bền (`OCR_RAPIDOCR_PERSISTENT=true`), backend torch:** trọng số `.pth` nằm trên data volume,
  nhưng RapidOCR 3.9 luôn giữ **file từ điển nhận dạng** (`ppocrv6_dict.txt`) trong thư mục gói ở layer
  container và tự tải lại khi thiếu. Sau khi recreate container **lúc không có Internet**, tài liệu đầu tiên
  sẽ lỗi tải từ điển. Phase 9B không đổi cách gọi RapidOCR (không đổi tham số model sát ngày phát hành); thay
  vào đó file từ điển được đưa vào fingerprint readiness, nên sau recreate trạng thái trở về "chưa kiểm tra"
  thay vì báo sai `offline_ready`. Cách vận hành: sau mỗi lần recreate, chạy "Chuẩn bị" một lần khi có
  Internet (kể cả ở chế độ lưu bền). Giới hạn này được ghi nhận, chưa khắc phục triệt để.
  **Phase 12D13 (D12-L1):** image mang sẵn từ điển đã kiểm ở Windows (`scripts/offline/rb1/`, cùng artifact
  của rollback RB-1, SHA-256 ghim, Apache-2.0). Entrypoint khôi phục nó **sau** khi runtime được cài và
  **trước** supervisord (`open_notebook/ocr/rapidocr_dictionary.py`, helper đã duyệt), và `build_ocr_options`
  kiểm lại trước mỗi lần cấu hình RapidOCR. Chỉ cho đúng RapidOCR 3.9.2 / torch / Docling 2.129.0 / model đã
  ghim, đúng vị trí RapidOCR tự tính, không ghi đè file lạ. `OCR_OFFLINE=true` mà không chứng minh được ⇒
  chuyển đổi dừng (ValueError), không tải, không đổi engine. Không đổi RapidOCR, model hay tham số gọi.
- **Build arg:** `OCR_INSTALL_TESSERACT` được nối vào khối `build.args` của cả hai file compose (mặc định
  `false`, đọc từ `.env`). Trước đây chỉ truyền được bằng `--build-arg`, nên một lần `up -d --build` sau này
  sẽ dựng lại image không có Tesseract trong khi engine đang chọn vẫn là Tesseract.
- `OCR_READINESS_TIMEOUT` sai định dạng không còn làm lỗi lúc import (trước đây làm API và worker không xử lý
  được nguồn); giá trị sai ⇒ 1800 giây.

## D-33. Tự dùng Full Page OCR cho trang scan nằm dưới khung bao text hiển thị bị nghiêng (Phase 10G)

**Vấn đề.** Docling 2.129.0, chế độ OCR mặc định (`BaseOcrModel.post_process_cells` → `_merge_ocr_and_pdf_cells`,
ưu tiên `PDF_FIRST`): mọi ô text PDF *hiển thị* được giữ, và mọi ô OCR có bbox giao với bbox **thẳng trục** của
một ô như vậy bị bỏ (mã nguồn tự ghi chú *"The R-tree bbox intersection is a weak criterion"*). Một dòng watermark
chéo là một ô có bbox thẳng trục phủ gần hết trang, nên toàn bộ chữ OCR bên dưới bị loại; lớp OCR ẩn cũng bị loại
theo cùng quy tắc. Đo trên PDF tổng hợp tái hiện cấu trúc (scan + lớp OCR ẩn + watermark 55°): giữ 0% ô OCR, 0% nội
dung. Không phụ thuộc engine.

**Quyết định.** Không sửa Docling, không sửa PDF. `pdf_prep.overlay_scan` đo từng trang bằng pdfium (hình học và
số đếm, không đọc nội dung chữ); `pdf_prep.decide_ocr_mode` quyết định chế độ OCR **cho riêng tài liệu**;
`docling_extract.convert_document` áp dụng bằng `OcrOptions.mode = FULL_PAGE` chính thức. Tính năng **opt-in**:
`OCR_AUTO_FULL_PAGE_ON_WATERMARK=true`; mặc định tắt ⇒ không một dòng mã mới nào ảnh hưởng kết quả.

**Bốn loại lớp được phân biệt**

| Lớp | Nhận biết | Vai trò trong quyết định |
|---|---|---|
| Ảnh scan | hợp các ảnh phủ ≥ 50% trang (ngưỡng sẵn có của `pdf_prep`) | điều kiện cần |
| Lớp OCR ẩn | text render mode 3 / 7 | không bao giờ gây nguy cơ; số ký tự ẩn là bằng chứng "nội dung nằm trong ảnh" |
| Text hiển thị thông thường | bbox của đối tượng = tổng ô ký tự của chính nó (tỷ lệ 1,00 với mọi chữ song song trục, mọi cỡ chữ). Chữ **nghiêng** cũng là text thông thường khi các khung bao nghiêng của trang chứa ký tự hiển thị nhiều hơn khoảng trống (lớp văn bản hiển thị đi theo một bản scan bị lệch) | ≥ 400 ký tự và nhiều hơn ký tự ẩn ⇒ "trang văn bản điện tử": không có nguy cơ |
| Khung bao nghiêng (watermark chéo) | bbox ≥ 1,5 lần tổng ô ký tự của chính nó **và** nghiêng ≥ 1° so với trục gần nhất | phần chúng chiếm trên ảnh, ngoài mọi ký tự hiển thị, ≥ 2% trang ⇒ trang có nguy cơ |

**Vì sao không dùng ngưỡng góc cố định, và ngưỡng 50% / 10% ban đầu được thay thế nào.** Đo thực tế: mất nội dung
tỷ lệ với *diện tích khung bao*, không với góc — một dòng dài nghiêng 2° đã mất 3,9 điểm phần trăm số từ, 5° mất
11, 85° mất 24,5. Ngưỡng góc 10° dự định ban đầu sẽ bỏ sót các trường hợp này. Góc vì thế chỉ là điều kiện phụ
(≥ 1°, loại phông chữ có số đo bất thường); đại lượng quyết định là *diện tích bị chiếm mà không có chữ* trên ảnh
scan. Quan hệ đo được: số từ mất tăng đều theo diện tích đó, bằng 0,6–2,6 lần tùy khung bao nằm trên vùng nhiều
hay ít chữ (dòng 55°: 1,1% → mất 3,0 điểm; 3,0% → 7,7; 13% → 27; 31% → 61; 56% → 91,5; 93% → 95,6). Ngưỡng 2% tách hai điểm đo gần nhau nhất (1,1% không kích hoạt, 3,0% kích hoạt). Ngưỡng
scan giữ 50% vì với điều kiện "trên ảnh" phía trên nó không còn là ngưỡng nhạy.

**Quy tắc cấp tài liệu** (Docling chỉ có một chế độ OCR cho cả tài liệu):

- có ≥ 1 trang có nguy cơ và **không** có trang văn bản điện tử ⇒ `FULL_PAGE` cho tài liệu này;
- có trang có nguy cơ **và** có trang văn bản điện tử ⇒ tài liệu **hỗn hợp**: giữ chế độ đã cấu hình, ghi `WARNING`.
  Lý do: ép toàn trang làm trang điện tử mất 1,1–1,9 điểm phần trăm số từ (đo), và chưa có API chính thức để đặt
  chế độ theo từng trang; không xây cơ chế tách / ghép PDF trong phase này;
- OCR đang tắt ⇒ không làm gì (không tự bật OCR); Force Full Page đã bật thủ công ⇒ giữ nguyên, không phân tích;
- giá trị Force Full Page trong cơ sở dữ liệu không bao giờ bị ghi.

**Đường RapidOCR mặc định.** Cấu hình mặc định vẫn gọi nguyên `content_core.extract_content` (D-03). Content Core
không nhận tham số chế độ OCR, nên khi cờ bật và tài liệu được quyết định `FULL_PAGE`, `should_use_native_ocr`
chuyển **riêng tài liệu đó** sang lớp OCR của dự án với cùng engine RapidOCR — đúng đường đã dùng khi quản trị
viên tự bật Force Full Page. Mọi tài liệu khác vẫn đi Content Core.

**Chữ nghiêng lấp đầy khung bao.** Rà soát sau hiệu chuẩn cho thấy một trang scan mang lớp văn bản *hiển thị* có các
dòng nghiêng từ 1,5° (đi theo độ lệch của bản scan) thỏa cả ba điều kiện góc / phình / chiếm trống, và sẽ bị OCR
toàn trang xuyên qua chính lớp văn bản mà Docling đang giữ. Phân biệt bằng hình học: ở lớp văn bản như vậy phần
diện tích khung bao **có** ký tự hiển thị lớn hơn phần trống (đo: 22,8% so với 3,1% ở 2°; 23,4% so với 5,2% ở 5°),
còn ở watermark thì ngược lại dù nhiều ký tự đến đâu (watermark 9 dòng 30°, 486 ký tự: 18,3% so với 59,4%;
cấu trúc gây lỗi: phần trống gấp hơn 10 lần). Trang "đầy hơn trống" tính các ký tự nghiêng là văn bản của trang.
Không quyết định nào trên 38 PDF hiệu chuẩn thay đổi.

**Không làm.** Không so khớp nội dung hay tên watermark; không hardcode tên tổ chức; không xoá watermark khỏi PDF;
không dùng lớp OCR ẩn làm kết quả (đo trên tài liệu thật: chỉ 36–38% số từ trùng với Tesseract).

**Hệ tọa độ và giới hạn đọc (bổ sung ở Phase 10H, sau review độc lập).** Khung bao được đo trong không gian người
dùng **chưa xoay** của trang, lấy gốc là góc của page box: trang có `/Rotate` và trang có MediaBox không bắt đầu ở
(0, 0) cho cùng số đo với trang thường (trước đó phần nằm ngoài chiều cao đã hoán đổi bị cắt, khiến quy tắc lặng lẽ
không áp dụng). Vì bước này đọc một tệp tải lên **chưa tin cậy** trước cả Docling, nó có giới hạn như bước dò hướng
trang: tối đa 2.000 trang, 20.000 đối tượng và 100.000 ký tự mỗi trang, 20 giây cho cả tài liệu; vượt giới hạn ⇒
dừng, ghi một dòng cảnh báo chỉ gồm số, và tài liệu được chuyển đổi với chế độ đã cấu hình (`check_failed`). Trang
không đọc được chỉ được ghi log ba lần đầu rồi một dòng tổng.

**Giới hạn đã biết.** (0) Watermark được ghi **mỗi ký tự một đối tượng text** không tạo ra khung bao nghiêng nào ở
mức đối tượng nên không được phát hiện, trong khi Docling vẫn ghép chúng thành các ô nghiêng (hướng an toàn: tài
liệu được xử lý như trước). (1) Watermark **ngang** cỡ lớn có bbox khít chữ nên không được phát hiện; mức mất đo được
3,3 điểm (chỉ các dòng nằm trong dải chữ watermark). (2) Khung bao nghiêng chiếm < 2% trang: không kích hoạt, mất
tối đa khoảng 3 điểm. (3) Tài liệu hỗn hợp: không sửa, có cảnh báo. (4) Nguồn từ URL với cấu hình RapidOCR mặc định
do Content Core tự tải và xử lý, không qua bước này (URL ingestion mặc định tắt, D-29). (5) Các ngưỡng được hiệu
chuẩn trên PDF tổng hợp và một tài liệu thật; chúng là giá trị khởi điểm, chỉnh được bằng biến môi trường.

Chi tiết số đo: [OCR_PHASE10G_REPORT.md](OCR_PHASE10G_REPORT.md).


## D-34. Chuẩn hóa văn bản pháp lý sau OCR trên DoclingDocument, opt-in hai lớp (Phase 12)

**Bối cảnh.** Văn bản pháp lý OCR bị chèn `<!-- image -->` (chữ ký, con dấu, logo), số trang lọt giữa câu, khoản
bị cắt qua trang, số khoản/điểm bị đánh lại hoặc bị chèn số vị trí (`5. đ)`). Phân tích (Phase 12A) cho thấy các lỗi
nằm **sau OCR**: nhãn layout (số trang = TEXT), serializer Markdown (placeholder, số chèn khi Docling không nhận marker
`đ)` / `a.1)`, cú pháp danh sách bị CommonMark đánh lại số), cơ chế ghép liên trang của Docling chỉ khớp chữ ASCII
và chỉ TEXT→TEXT; ngoài ra chữ OCR nằm trong vùng ảnh bị bỏ khi xuất (`traverse_pictures=False`).

**Quyết định.** Thêm chế độ "Văn bản pháp lý" (`open_notebook/ocr/legal_normalizer.py`) chạy trên **bản sao
`DoclingDocument`** của PDF, sau chuyển đổi và trước khi lưu Source: chuyển số trang/header lặp (đủ bằng chứng hình
học + mẫu lặp) sang lớp furniture của Docling; bỏ placeholder ảnh không mang thông tin (giữ ảnh lớn không chữ + cảnh
báo); xuất chữ OCR trong vùng ảnh; ghép đoạn liên trang theo quy tắc bảo thủ Unicode-aware; xuất marker gốc dạng
chữ có escape. Bật bằng **hai lớp**: cổng triển khai `OCR_LEGAL_NORMALIZATION_ENABLED` (mặc định tắt) **và** lựa
chọn quản trị `ocr_text_normalization` (mặc định `standard`, bảng SCHEMALESS ⇒ không migration). Khi bật, PDF luôn
đi qua lớp Docling của ChatBot5400 (cùng options với content-core) vì content-core không trả về `DoclingDocument`.
Lỗi ⇒ fallback Standard, có metadata `failed`.

**Không làm.** Không dùng LLM/AI sửa chữ; không regex trên toàn văn; không đổi Docling/Heron/TableFormer/engine/
model/RAG/schema/dependency; không áp dụng cho ảnh và định dạng khác PDF; không tự xử lý lại tài liệu cũ; không
tuyên bố trích dẫn số trang (provenance chưa được lưu theo chunk); không sửa thứ tự đọc.

Chi tiết: [PHASE12B_LEGAL_NORMALIZATION_DESIGN.md](PHASE12B_LEGAL_NORMALIZATION_DESIGN.md).

## D-35. Gói cập nhật offline: image dựng sẵn + git bundle, xác thực bằng chữ ký hoặc hash kênh tin cậy (Phase 12F)

**Quyết định.** Máy chủ Ubuntu offline được cập nhật bằng một gói `.tar.gz` chứa Docker image (`docker save`, dựng
trên máy có Internet với `OCR_PREINSTALL_RUNTIMES=true` + `OCR_INSTALL_TESSERACT=true` để không phải cài gì lúc khởi
động), git bundle `v1.2.0..<release>`, archive mã nguồn, manifest, SHA256SUMS và chữ ký tùy chọn
(`ssh-keygen -Y sign`, namespace `chatbot5400-offline`, khóa công khai cài trước ở máy chủ). Công cụ
`scripts/offline/offline_package.py` (chỉ thư viện chuẩn Python) kiểm tra an toàn archive trước khi giải nén, toàn
vẹn, xác thực (chữ ký **hoặc** SHA-256 nhận qua kênh tin cậy — thiếu cả hai ⇒ từ chối), nền tảng, phiên bản, schema;
cập nhật chỉ tạo lại container ứng dụng (`--no-deps --no-build --pull never`), không đụng database; trọng số RapidOCR
được chuyển lên volume (SHA-256) trước khi tạo lại để không phải tải lại.

Chi tiết: [../deployment/OFFLINE_UPDATE_PACKAGE.md](../deployment/OFFLINE_UPDATE_PACKAGE.md).

## D-36. Sửa đổi D-34 sau audit độc lập: giữ nội dung trừ khi có bằng chứng mạnh (Phase 12D3)

**Bối cảnh.** Audit Phase 12D2 (`docs/review/PHASE12D2_FINDINGS.json`: F-01, F-02, F-03, F-06, F-07, F-10, F-17,
T-01) cho thấy bộ chuẩn hóa v1.0.0 xóa nhầm nội dung hợp lệ (dòng lặp, năm, số khoản), nối sai qua trang, và phép đo
"0 từ bị mất" là vòng tròn (cộng lại chính phần đã xóa).

**Quyết định (normalizer v1.1.0).**

1. **Nguyên tắc số 0**: mọi phép biến đổi phải có bằng chứng mạnh; nghi ngờ ⇒ giữ nguyên và ghi cảnh báo. Xóa nhầm
   nội dung pháp lý nặng hơn để sót artifact.
2. Dòng chữ lặp lại **không bao giờ** bị bỏ dựa trên suy luận tần suất; chỉ item mà layout model gắn nhãn
   PAGE_HEADER/PAGE_FOOTER mới chuyển furniture. Giữ mọi lần xuất hiện, không chỉ lần đầu.
3. Số trang chỉ bị bỏ khi: ≥ 3 trang cùng độ lệch **và** ≥ 60% số trang, cùng dải, cùng vị trí ngang (hoặc đối xứng
   lẻ-chẵn), ngoài mép thân, giá trị phù hợp số trang. Văn bản 1-2 trang: giữ.
4. Nối qua trang chỉ khi đoạn trước là đoạn thân bị cắt thật và trang sau không mở đơn vị mới; mọi lý do từ chối được
   ghi. Phần được nối chuyển sang lớp INVISIBLE (không xóa item ⇒ tuyến tính).
5. Ảnh không chữ: chỉ ảnh < 4% diện tích trang mới bỏ placeholder (có ghi lại); còn lại giữ + cảnh báo có vị trí.
6. **Văn bản lưu không chứa ký tự thoát Markdown của marker danh sách**; việc thoát chỉ làm lúc hiển thị ở frontend
   (`legalDisplayMarkdown`). Nội dung hiển thị, sao chép và RAG là cùng một văn bản.
7. **Bản ghi chuẩn hóa** (chế độ, trạng thái applied/failed/skipped, phiên bản, bộ đếm, cảnh báo, phép biến đổi =
   loại + trang + SHA-256, không có văn bản) lưu trong `source.asset.extraction` — trường `asset` là
   `FLEXIBLE option<object>` từ migration 1 nên **không cần migration**; Source Standard không có khóa này (lưu giống
   hệt v1.2.0). Phương án thay thế đã cân nhắc và loại: bảng/trường mới (cần migration — bị cấm trong Phase 12).
8. Ngân sách thời gian 30 s và giới hạn kích thước ⇒ fallback Standard với trạng thái `failed` hiển thị cho người dùng.
9. **Oracle kiểm thử** dùng ground truth khai báo trong fixture, không dùng đầu ra hay báo cáo của normalizer.

**Hệ quả chấp nhận.** Ít artifact được loại hơn v1.0.0 (24/47 so với 45/47 trên bộ fixture) và ít phép nối hơn
(3/5), đổi lại 0 xóa nhầm / 0 nối sai trên cùng bộ đo. Văn bản 2 trang giữ số trang nghi ngờ. Header chạy mà layout
gắn nhãn TEXT được giữ trong nội dung.

Chi tiết: [../review/PHASE12D3_REMEDIATION_REPORT.md](../review/PHASE12D3_REMEDIATION_REPORT.md),
[../review/PHASE12D3_QUALITY_BENCHMARK.md](../review/PHASE12D3_QUALITY_BENCHMARK.md).

## D-37. Sửa đổi D-35 sau audit độc lập: attempt, phát hiện lệch, ghim image, xác thực trước khi giải nén (Phase 12D3)

**Bối cảnh.** Audit Phase 12D2 (F-04, F-05, F-08, F-09, F-11..F-14, F-20..F-27): lệnh build theo tài liệu không tạo
được bundle; lần cập nhật thứ hai dùng lại backup cũ; `docker compose up -d` thông thường đưa bản cũ trở lại mà
không ai biết; `finish`/`rollback` báo thành công không kiểm tra; archive được giải nén trước khi xác thực.

**Quyết định (định dạng gói 2).**

1. Bundle mang **ref có tên** (`refs/cb5400-offline/build/<version>`, tạo tạm lúc build); máy chủ fetch đúng một ref,
   chỉ fast-forward. `VERSION` của commit được kiểm trước mọi lệnh Docker; `VERSION` của repository vẫn `1.2.0` cho
   tới commit phát hành nên gói thử nghiệm mang tên `1.2.0-<hậu tố>`.
2. Mỗi lần cập nhật là một **attempt** (mã, baseline, tag rollback, backup + xác minh khôi phục riêng); không dùng lại
   gì của attempt đã kết thúc; trạng thái chưa quyết định chặn mọi update.
3. `status`/`health` so container đang chạy với journal, **mã thoát 7** khi lệch; `finish` ghi lệnh Compose duy nhất.
4. **Ghim image là tùy chọn và do người vận hành quyết định** (`pin`: dry-run → `--apply` → `--undo`): trỏ tên image
   của triển khai tới image mới và tạo một file override riêng. Công cụ **không sửa `.env` hay file compose có sẵn**
   (ràng buộc dự án); phương án "tự sửa `.env`" bị loại vì công cụ không được đọc/ghi file chứa secret.
5. `finish` và `rollback` chỉ báo thành công sau health check; rollback theo **image ID** đã kiểm chứng; mã nguồn được
   khôi phục khi an toàn; không bao giờ restore database.
6. **Xác thực trước, giải nén sau**; từ chối entry trùng; giải nén vào thư mục tạm; file image được đọc trước
   `docker load` (đúng một tag đã duyệt); image được nhận diện bằng ID, digest cấu hình hoặc danh sách layer.
7. Container database được chứng minh không đổi bằng `docker inspect` trước/sau mỗi lần tạo lại.
8. Model vẫn **không** được đóng gói (giữ D-35): gói chỉ **kiểm tra** (readiness đã ghi, kết quả chép RapidOCR, danh
   sách file model trước/sau, bộ mã hóa token trong image); máy chủ thiếu model bị từ chối.

**Trạng thái.** Logic đã kiểm thử với Docker giả lập + git/tar/ssh-keygen thật. Docker, Compose, PowerShell thật
**chưa chạy**: [../review/PHASE12D3_WINDOWS_ACCEPTANCE_CHECKLIST.md](../review/PHASE12D3_WINDOWS_ACCEPTANCE_CHECKLIST.md).

Chi tiết: [../review/PHASE12D3_OFFLINE_SAFETY_REPORT.md](../review/PHASE12D3_OFFLINE_SAFETY_REPORT.md),
[../deployment/OFFLINE_UPDATE_PACKAGE.md](../deployment/OFFLINE_UPDATE_PACKAGE.md).

## D-38. Legal không tự nối đoạn văn qua trang; tách phép nối của Docling qua trang khi có bằng chứng (Phase 12D7)

**Bối cảnh.** Phase 12E1 (Windows, 22 PDF thật) cho thấy quy tắc nối của bộ chuẩn hóa 1.2.0 sai 3/4 phép trên các
phản ví dụ scan thật của F-03 (finding E1-09): điểm mất ký hiệu do OCR, dòng đơn vị tính bị OCR làm hỏng, tiêu đề
chạy viết thường. Tái hiện ở Cloud: trong cả ba dạng, câu ghép sai đến từ **phép nối của chính Docling** mà quy tắc
1.2.0 không hoàn tác, không phải từ phép nối của Legal.

**Quyết định (chủ dự án).** Không bổ sung thêm heuristic đoán đoạn văn. Bộ chuẩn hóa 1.3.0:

1. **Không bao giờ tự nối** đoạn của hai trang (A). Hai phần giữ thành hai đoạn theo thứ tự đọc đã có; không tạo câu.
2. Phép nối **của Docling** (B) qua ranh giới trang được **tách lại** mỗi khi charspan của provenance khớp (bằng chứng
   trực tiếp); trong cùng một trang (cột) chỉ tách khi quy tắc cũ từ chối. Dấu gạch nối bị Docling bỏ chỉ được khôi
   phục khi phần tử trước khi ghép của pipeline cho thấy; nếu không: giữ, cảnh báo `upstream_dehyphenation`. Charspan
   không khớp: giữ nội dung, cảnh báo `upstream_merge_kept` — không tuyên bố bảo toàn tuyệt đối.
3. Từ bị cắt bởi gạch nối ở cuối trang: giữ nguyên hai phần, cảnh báo `hyphen_at_page_break_not_joined`.

**Hệ quả.** Ground truth của fixture không đổi; phép nối được phép (8) giờ không được thực hiện (0) — đánh giá riêng
trong benchmark (`docs/review/phase12d7/benchmark_legal_1_3_0.json`). 0 xóa / nối sai / chèn trên 92 fixture.
Mô tả trên giao diện không còn hứa "cải thiện đoạn văn bị ngắt do phân trang".

## D-39. Bản vá có kiểm soát cho Docling 2.129.0: chữ trong TSV của Tesseract giữ nguyên (Phase 12D7)

**Bối cảnh.** E0-07: `TesseractOcrCliModel._run_tesseract` đọc TSV bằng `pd.read_csv` với suy diễn kiểu; vùng OCR chỉ có
số thành cột `float64` (`0001` → `1.0`), chuỗi NA của pandas (`NA`, `N/A`, `NULL`, …) bị bỏ ở mọi vùng.

**Quyết định (được chủ dự án phê duyệt).** Module `open_notebook/ocr/docling_patches.py`: bản sao đúng của hàm
upstream, chỉ đổi phép đọc TSV (cột `text` là chuỗi, không chuyển NA; các cột khác giữ NA mặc định của pandas theo
từng cột); áp dụng tại `build_ocr_options` cho mọi engine Tesseract; chặn bằng phiên bản (`docling == 2.129.0`) và
SHA-256 mã nguồn upstream — không khớp thì Tesseract từ chối chạy. Không sửa site-packages, không vá pandas, không
fork, không thêm dependency; giữ thông báo MIT. Chọn thay cho vá file lúc build vì Docling là extra tùy chọn được
cài ở hai nơi (image dựng sẵn và entrypoint lúc chạy) — bản vá trong mã ứng dụng đi cùng image và gói offline ở mọi
đường cài. `inventory` của image ghi `docling_tsv_patch`; gói không áp được bản vá là NOT_READY.

**Hệ quả.** Standard không còn giống v1.2.0 từng byte ở những chỗ parser cũ làm sai; mọi khác biệt khác là lỗi
(công cụ `scripts/ocr/phase12_standard_diff.py`).

## D-40. Cổng hướng xoay (D-25) phải chạy được trong mọi image, kể cả image build từ máy Windows (Phase 12D7)

**Bối cảnh.** E1-05 (Windows 12E1): các vùng OCR nhỏ bị xoay 180° và đọc thành chữ rác — đúng lỗi mà cổng hướng xoay
(D-25) được tạo ra để chặn. `tesseract_gate.py` được Docling gọi như một chương trình, chạy qua dòng `#!`.
`.gitattributes` chỉ ép LF cho `*.sh`; checkout bằng Git for Windows (`core.autocrlf=true`, mặc định) cho file cổng
đuôi dòng CRLF, `docker compose build` / `build-package.ps1` chép nguyên vào image, dòng `#!/usr/bin/env python3\r`
không chạy được, `tesseract_command()` lùi về Tesseract thật (thiết kế: không bao giờ làm hỏng OCR) và Docling áp
dụng lại mọi góc xoay độ tin cậy thấp cho từng vùng layout. Tái hiện ở Cloud (bản CRLF thoát 126/127, ứng dụng chạy
không cổng). **Chưa được xác nhận trên máy Windows** (log "runs without orientation gating", hoặc ký tự CR trong file
cổng bên trong container) — nguyên nhân khả dĩ nhất, không phải đã chứng minh.

**Quyết định.** Không đổi ngưỡng (2.0), không đổi logic xoay, không tắt xoay. (1) `.gitattributes`: cổng luôn LF.
(2) Dockerfile: chuẩn hóa đuôi dòng, đặt quyền thực thi và tự kiểm tra cổng khi build (`/bin/true` thay cho
Tesseract) — build Linux không đổi file, build Windows cho đúng blob của git; build hỏng thì dừng. (3)
`options.tesseract_gate_state()` cho biết cổng có THỰC SỰ chạy không và vì sao; `ocr.cli status` in ra (chỉ dạng
chữ, không thuộc fingerprint readiness). (4) `scripts/ocr/phase12_orientation_diagnose.py`: ghi từng vùng OCR (hướng,
độ tin cậy, kích thước, PSM, góc đã xoay, chữ đọc được theo cả hai hướng) để Windows kiểm lại 11 cụm nghi ngờ.

**Hệ quả.** Nếu Windows xác nhận cổng đã chạy mà vẫn còn vùng xoay sai với độ tin cậy ≥ 2.0, đó là một finding mới cần
benchmark trước khi đổi ngưỡng (D-25: mọi câu trả lời sai đo được đều ≤ 1.44 trên 1 340 hướng).

**Cập nhật Phase 12D9 (bằng chứng Windows 12E2).** Đuôi CRLF của image cũ đã được xác nhận và đã sửa (cổng chạy được).
CRLF **không** phải nguyên nhân của 11 cụm chữ rác: OSD của các vùng đó trả 0° và Windows xác nhận không cụm nào do hướng
xoay hay watermark. Hai finding tách riêng: (a) lỗi build của cổng hướng xoay (E1-05, toàn vẹn lúc chạy) — ĐÃ SỬA;
(b) chất lượng OCR của 11 vùng (E2-02: crop / layout / nhận dạng) — CHƯA XÁC MINH, cần bằng chứng Local. Một checkout
Windows đã có vẫn có thể hiện `w/crlf` sau khi pull (blob không đổi nên Git không ghi lại file) — điều đó chỉ chứng minh
khả năng, không chứng minh nguyên nhân (D8-ORI-03 / 04).

## D-41. Giữ mọi dấu gạch nối mà Docling bỏ khi ghép chữ (Phase 12D9, D8-03)

**Bối cảnh.** Review 12D8 (D8-03, P1): Docling 2.129.0 bỏ dấu `-` của số hiệu văn bản ở hai chỗ —
`PageAssembleModel.sanitize_text` khi ghép các ô của một vùng layout (`05/2024/TT-` + `BNNPTNT` →
`05/2024/TTBNNPTNT`, `2021-` + `2025` → `20212025`; ô Tesseract là TỪ nên bỏ cả giữa dòng: `VT- KHTC` → `VTKHTC`,
`1- Điều 5` → `1Điều 5`) và `ReadingOrderModel._merge_elements` khi nối hai khối qua trang / cột trước chữ thường.
Có từ v1.2.0, mọi engine và lớp chữ PDF, cả Standard lẫn Legal.

**Quyết định (chủ dự án, 12D9).** Bản vá có kiểm soát thứ hai, cùng khuôn D-39 (đúng `docling 2.129.0`, SHA-256 của
từng hàm upstream, tất cả hoặc không gì, idempotent, có khóa, fingerprint theo nguồn upstream, test AST so từng hàm
với upstream): không bao giờ bỏ `-`. Hai phần chỉ ghép liền khi **hộp chữ của chính các ô** cho thấy xuống dòng
(ô sau bắt đầu một dòng thấp hơn); hai ô cạnh nhau trên một dòng, hoặc không có bằng chứng hình học, giữ ranh giới ô
là một khoảng trắng — không bao giờ suy diễn hai ô là một từ. Khối nối qua trang giữ `-`, charspan ghi đúng chỗ phần
tiếp bắt đầu. Gạch nối mềm (U+00AD), dấu nháy, bullet, ligature: giữ quy tắc upstream (giới hạn riêng, có test ghi
nhận). Không thêm `-`, không sửa theo từ điển (`docu-` + `ment` → `docu-ment`). Áp dụng trước MỌI chuyển đổi Docling
của ứng dụng (`build_converter`, đồ thị source trước đường content-core, Legal); Docling khác phiên bản ⇒ PDF / scan bị
từ chối (không chạy khi chưa vá).

**Hệ quả.** Standard khác v1.2.0 đúng ở các chỗ này (lớp `expected hyphen fix` của cổng D-44). Legal 1.3.1 hiểu phép
nối có giữ `-` và vẫn tách mọi phép nối qua trang (D-38).

## D-42. Footnote gắn với bảng / ảnh có trong nội dung Markdown — Standard và Legal (Phase 12D9, D8-02)

**Bối cảnh.** docling-core 2.96.0 viết caption của bảng / ảnh nhưng không viết footnote của chúng, còn footnote bị bỏ
qua tại chỗ của nó ("do item chứa nó xử lý"): footnote ngay dưới bảng biến mất khỏi mọi đầu ra Markdown.

**Quyết định.** Bản vá có kiểm soát (đúng `docling-core 2.96.0` + SHA-256 của hai serializer): mỗi footnote gắn vào
bảng / ảnh được viết **một lần**, ngay sau item, bằng đúng cách Docling viết một đoạn văn (escape như đoạn văn của
chế độ đó); tham chiếu hỏng bị bỏ qua, không lặp; bộ lọc nhãn của người gọi được tôn trọng. Chỉ Markdown: đầu ra
HTML vẫn như upstream (giới hạn ghi nhận); JSON vốn giữ mọi text item.

## D-43. Legal 1.3.1: phần tách ra đứng ngay sau phần đầu theo thứ tự đọc của chính Docling (Phase 12D9, D8-01)

**Quyết định.** Khi tách một phép nối qua trang của Docling, phần sau được đặt ngay sau phần trước, chỉ vượt qua các
item mà phép nối của Docling bỏ qua (header, footer, bảng, ảnh, caption, footnote) VÀ đứng trước nó trong thứ tự đọc
mà Docling tự tính cho trang đó; không bao giờ vượt qua đoạn văn, list item hay tiêu đề. Hộp của phần sau được giải mã
bằng chiều cao trang của phần đầu (quy ước của Docling). Không xác định được vị trí ⇒ giữ phép nối và cảnh báo
(`upstream_merge_kept`). Không sắp lại tài liệu theo tọa độ.

## D-44. Cổng Standard expected-diff: mọi khác biệt phải được chứng minh bằng bằng chứng của chính lần chuyển đổi (Phase 12D9, D8-STD-01..05, E2-03)

**Quyết định.** `phase12_standard_diff.py` v2: `unchanged` chỉ khi byte giống hệt; khoảng trắng và cấu trúc là token.
Bằng chứng do `phase12d9_standard_export.py` ghi trong cùng lần chuyển đổi tạo ra đầu ra (TSV thô từng lần gọi
Tesseract + provenance, văn bản v1.2.0 / ứng viên của từng vùng, phép nối khối, footnote đã viết; quyền chủ sở hữu,
chỉ cục bộ). Văn bản v1.2.0 được TÍNH LẠI bằng chính mã upstream (pandas, `sanitize_text`), mỗi thay đổi được duyệt
dùng một lần và gắn với ngữ cảnh crop; crop "sở hữu" vị trí mà không dự đoán thay đổi ⇒ hồi quy. Một hunk có thể mang
nhiều nguyên nhân nhưng phải được lát kín bởi các thay đổi được duyệt. Lớp hướng xoay chỉ khi có bằng chứng hướng
xoay (chưa có công cụ ghi ⇒ hunk đó `not verified`, xem tay). Mã thoát khác 0 cho mọi kết quả không chứng minh được
gì. Báo cáo mặc định không chứa chữ.

## D-45. Lỗi thực thi OCR không bao giờ cho ra Source "hoàn tất" thiếu nội dung (Phase 12D9, E2-04)

**Bối cảnh.** Windows 12E2: khi tiến trình NHẬN DẠNG của Tesseract lỗi, Docling bỏ cả vùng và vẫn báo SUCCESS,
errors = 0; Source hoàn tất thiếu chữ (Best 13/49, Agri v2 63/100, tài liệu thật 445/1220 token). OSD lỗi một mình
không làm mất vùng khi nhận dạng thành công. Nguyên nhân cụ thể chưa rõ (stderr bị bỏ); mount 9p **không** được kết
luận là nguyên nhân.

**Quyết định.** Bản vá có kiểm soát của vòng OCR Tesseract (cùng khuôn D-39): lỗi có thể tạm thời được thử lại tối đa
2 lần trên CÙNG crop, lệnh, ngôn ngữ và file model (phiên bản model của job không đổi); thiếu chương trình / thiếu
file model thì không thử lại; vẫn lỗi ⇒ vùng không bị bỏ mà trang thất bại. Ứng dụng từ chối mọi kết quả Docling
không phải SUCCESS không lỗi — **kể cả `PARTIAL_SUCCESS` của mọi engine, trước đây được lưu kèm cảnh báo** (thay đổi
hành vi có chủ đích): `IncompleteConversionError` (ValueError: job dừng, không tự thử lại, người dùng thử lại bằng cơ
chế sẵn có), thông báo tiếng Việt, không lưu nội dung, không tạo embedding, Source cũ hợp lệ giữ nguyên. stderr chỉ
được đọc (phần cuối) để phân loại; log chỉ ghi trang, vùng, ngôn ngữ / model, loại lỗi, mã thoát, số lần thử, kết quả.

## D-46. Không mở rộng bộ cập nhật tự động; production dùng quy trình thủ công (Phase 12D9, D8-OFF-01 / 02)

**Quyết định.** `update` / `finish` / `rollback` / `pin` vẫn EXPERIMENTAL; chính công cụ nói điều đó (`--help`, mỗi
lần chạy, các wrapper), release notes dẫn production tới `OFFLINE_UPDATE_MANUAL_FALLBACK.md`. Không mở rộng state
machine. Các sửa trong 12D9 chỉ là an toàn: cặp gói + hash luôn nhất quán (D8-OFF-03 / 04), khóa báo đúng lỗi
(D8-OFF-09), `migration_required` tự phát hiện migration mới so với base-ref (D8-OFF-06), và quy trình thủ công ràng
buộc file với manifest đã ký, thư mục làm việc mới, so dữ liệu không ghi sau §7, rollback mã nguồn trước ứng dụng.

## D-47. Công cụ chẩn đoán mặc định chỉ ghi metadata; không có fallback chữ ngắn trong 1.3.0 (Phase 12D9)

**Quyết định.** Sau sự cố 12E2 (một vùng OCR thật lọt vào ngữ cảnh AI), mọi công cụ chẩn đoán mới hoặc sửa trong 12D9
mặc định không ghi chữ của tài liệu ra stdout / stderr / báo cáo: chỉ loại token, số lượng, trang, bbox, loại lỗi,
thống kê độ tin cậy, trạng thái. Chữ chỉ có khi người vận hành yêu cầu rõ (`--with-text`), ghi vào file quyền chủ sở
hữu, cục bộ, không upload, không commit. E2-01 (token ngắn một mình trong crop): không đổi PSM mặc định; fallback PSM 7
**không được cài** — benchmark tổng hợp ở Cloud cho thấy nó chèn chữ lên 4 / 6 crop không có chữ (con dấu, chữ ký, ảnh,
nhiễu); cần benchmark Windows trước mọi đề xuất bật.
