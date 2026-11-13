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
- Giới hạn chi phí: dò hướng tối đa 200 trang đầu (`OCR_PAGE_OSD_MAX_PAGES`), 30 giây mỗi trang; lỗi ở
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
