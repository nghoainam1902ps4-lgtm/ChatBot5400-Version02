# Changelog

Tất cả thay đổi đáng chú ý của ChatBot 5400 (Agribank Chi nhánh Lâm Đồng) được ghi ở đây.

## [Unreleased] — 1.3.0-rc.1 (đang nghiệm thu, CHƯA phát hành)

Phase 12 — Legal Document Normalization & Offline Update Package. Chi tiết: `docs/ocr/PHASE12_CLOUD_HANDOVER.md`,
bản nháp ghi chú phát hành `docs/ocr/OCR_RELEASE_NOTES_V1.3.0_RC1.md`. Chỉ phát hành sau nghiệm thu Windows Local.
**Phase 12D3** (sau audit độc lập 12D2, 29 finding): `docs/review/PHASE12D3_REMEDIATION_REPORT.md`. Chưa merge, chưa
phát hành RC, chưa triển khai production; còn chờ review 12D4 và nghiệm thu Local.

- **Chuẩn hóa văn bản pháp lý sau OCR (opt-in), bộ chuẩn hóa v1.1.0**: chế độ "Văn bản pháp lý" cho PDF — giữ nội
  dung trừ khi có bằng chứng mạnh. Bỏ số trang chỉ khi ≥ 3 trang cùng mẫu (≥ 60% số trang, cùng vị trí, ngoài thân);
  **không bao giờ bỏ dòng chữ lặp lại** (chỉ header/footer do layout gắn nhãn); nối đoạn bị cắt qua trang theo quy tắc
  bảo thủ và ghi lý do khi không nối; bỏ `<!-- image -->` chỉ với ảnh rất nhỏ, ảnh lớn hơn giữ kèm cảnh báo; giữ
  nguyên số Điều/Khoản/Điểm gốc; lấy lại chữ và bảng nằm trong vùng ảnh; bảng giữ nguyên. Không dùng AI sửa chữ. Bật
  bằng `OCR_LEGAL_NORMALIZATION_ENABLED=true` **và** chọn trong Cài đặt → OCR Engine Manager; mặc định Tiêu chuẩn
  (kết quả giống hệt 1.2.0).
- **Trang Source ghi rõ cách văn bản được tạo**: *Tiêu chuẩn* / *Đã chuẩn hóa văn bản pháp lý* / *Chuẩn hóa thất bại,
  sử dụng bản tiêu chuẩn*, kèm phiên bản và số cảnh báo; định dạng phân cấp Điều/Khoản/điểm. Văn bản lưu không còn ký
  tự thoát Markdown (`9\.`): hiển thị, sao chép và RAG dùng cùng một văn bản.
- **Cải thiện bố cục OCR / giảm artifact trang**: phân tích nguyên nhân gốc và công cụ chẩn đoán từng tầng
  (`scripts/ocr/phase12_diagnose.py`, `phase12_compare.py`).
- **Gói cập nhật offline (định dạng 2)**: `scripts/offline/` — build trên Windows/Linux có Internet (kiểm `VERSION`
  trước mọi lệnh Docker; bundle git có ref đặt tên), **xác thực trước khi giải nén** (chữ ký hoặc hash kênh tin cậy
  riêng), preflight chỉ đọc, mỗi lần cập nhật là một *attempt* có backup riêng, cập nhật chỉ tạo lại container ứng
  dụng và chứng minh container database không đổi, `finish`/`rollback` có health check, phát hiện lệch (`status` /
  `health` mã thoát 7), ghim image tùy chọn (`pin.sh`), rollback theo image ID. Build arg mới
  `OCR_PREINSTALL_RUNTIMES` (mặc định `false`). **Mới kiểm thử với Docker giả lập** — Docker/Compose/PowerShell thật
  chưa chạy.
- Đếm token không còn chờ mạng khi `OCR_OFFLINE=true` và thiếu cache tiktoken (dùng ước lượng theo từ).
- **Không có migration cơ sở dữ liệu; không đổi phụ thuộc** (`uv.lock`, `pyproject.toml`, `package-lock.json` không
  đổi; schema vẫn 33). Trường cài đặt `ocr_text_normalization` nằm trên bảng SCHEMALESS (thiếu = Tiêu chuẩn); bản ghi
  chuẩn hóa nằm trong `source.asset.extraction` (trường `asset` linh hoạt có từ migration 1; Source Tiêu chuẩn không
  có khóa này).

## [1.2.0] - 2026-11-17 — Advanced OCR & Custom Model Manager (bản chính thức)

Bản **chính thức** đầu tiên có OCR Engine Manager và Custom Tesseract Model Manager; gom toàn bộ nội dung của
1.1.0-rc.1 và 1.1.0-rc.2 (các mục bên dưới). Chi tiết: `docs/ocr/OCR_RELEASE_NOTES_V1.2.0.md`; rollback:
`docs/ocr/OCR_V120_ROLLBACK_GUIDE.md`.

- **Mã ứng dụng giống hệt 1.1.0-rc.2**: chỉ đổi số phiên bản (`VERSION`, `frontend/package.json`,
  `frontend/package-lock.json`) và tài liệu. Không có tính năng mới, không đổi thuật toán OCR hay pipeline.
- **Không có migration cơ sở dữ liệu; không đổi phụ thuộc** (`uv.lock`, `pyproject.toml`, `Dockerfile` giống hệt
  rc.2; Open Notebook 1.14.0, Content Core 2.0.7, Docling 2.129.0).
- RapidOCR vẫn là engine mặc định; Tesseract Vietnamese Agri vẫn **Thử nghiệm** và bản phát hành không kèm model;
  `OCR_AUTO_FULL_PAGE_ON_WATERMARK` vẫn mặc định tắt.
- Nâng cấp từ 1.1.0-rc.2: không có việc bắt buộc; hạ cấp về rc.2 không cần đổi engine hay khôi phục cơ sở dữ liệu.
- Phát hành dưới dạng mã nguồn, không kèm Docker image hay model. Bản chính thức **không** phải xác nhận an toàn bảo
  mật cho nghiệp vụ (giới hạn: ghi chú phát hành mục 11–12).

## [1.1.0-rc.2] - 2026-11-16 — Model Tesseract tùy biến, tự OCR toàn trang (Pre-release)

Bản **Pre-release** (Release Candidate) thứ hai; bản ổn định gần nhất vẫn là 1.0.8. Phát hành dưới dạng
mã nguồn, không kèm Docker image hay model. Chi tiết: `docs/ocr/OCR_RELEASE_NOTES_RC2.md`, `docs/ocr/OCR_PHASE10H_REPORT.md`,
`docs/ocr/OCR_RC2_PRODUCTION_UPDATE_PLAN.md`. **Không có migration cơ sở dữ liệu; không đổi phụ thuộc**
(`uv.lock`, `Dockerfile` giống hệt 1.1.0-rc.1; Open Notebook 1.14.0, Docling 2.129.0, Content Core 2.0.7).

### Thay đổi hành vi khi nâng cấp — cần đọc

- Không có việc bắt buộc nào. Engine OCR đang chọn, Force Full Page và mọi cài đặt được giữ nguyên; engine mặc
  định vẫn là RapidOCR.
- OCR Engine Manager có thêm card **Tesseract Vietnamese Agri** (Thử nghiệm) ở trạng thái "Chưa cài đặt".
- **Trước khi hạ cấp** về 1.1.0-rc.1: nếu Agri đang được chọn, chọn lại một engine khác (bản cũ không biết giá
  trị `tesseract_agri` và sẽ lặng lẽ dùng RapidOCR).
- Publish một GitHub Release / Pre-release không còn khởi chạy build và push Docker image (xem "Phát hành").

### Model Tesseract tùy biến (Custom Tesseract Model Manager)

- Engine thứ năm **Tesseract Vietnamese Agri** dùng model Tesseract tự fine-tune do đơn vị cung cấp. Repository
  và image **không** chứa model.
- Import bằng CLI trên máy chủ (`ocr custom import --file … --version …`): mỗi lần import là một phiên bản bất
  biến có manifest, kích thước và SHA-256; file được kiểm tra cấu trúc, nạp thử bằng Tesseract và kiểm tra toàn
  bộ pipeline. Không upload model qua HTTP, không tải model tùy biến từ Internet.
- Quản lý phiên bản: `list`, `verify`, `activate`, `rollback`, `status`, `remove`; kích hoạt / rollback / kiểm
  tra cũng có trên card Agri (chỉ quản trị viên).
- Thay model **không cần build lại image hay restart**; tài liệu đang xử lý giữ phiên bản lúc bắt đầu; readiness
  gắn với từng phiên bản.
- Hướng dẫn: `docs/ocr/OCR_AGRI_MODEL_GUIDE.md`; thiết kế: `docs/ocr/OCR_CUSTOM_MODEL_MANAGER.md`; benchmark trên
  văn bản pháp lý tổng hợp: `docs/ocr/OCR_AGRI_BENCHMARK.md`.

### Tự OCR toàn trang cho PDF scan nằm dưới watermark chéo (opt-in, mặc định TẮT)

- Biến mới `OCR_AUTO_FULL_PAGE_ON_WATERMARK` (chỉ bật khi là `true` / `1` / `yes` / `on`). Khi bật: PDF scan có
  một dòng text hiển thị bị nghiêng phủ lên trang — cấu trúc khiến Docling bỏ gần hết chữ OCR — được OCR ở chế
  độ toàn trang chính thức của Docling, cho riêng tài liệu đó, với mọi engine. Không sửa PDF, không ghi đè tùy
  chọn Force Full Page đã lưu, không tự bật OCR khi OCR đang tắt.
- Chỉ đọc hình học và số đếm của PDF; log một dòng `OCR mode:` cho mỗi PDF, không có nội dung hay tên tệp.
- **PDF hỗn hợp** (trang scan dưới watermark + trang văn bản điện tử) **không** được sửa tự động: giữ chế độ đã
  cấu hình, ghi `WARNING`.
- Ngưỡng tinh chỉnh: `OCR_AUTO_FULL_PAGE_MIN_COVERAGE`, `OCR_AUTO_FULL_PAGE_TEXT_PAGE_CHARS`,
  `OCR_AUTO_FULL_PAGE_MIN_ANGLE` (`docs/ocr/OCR_CONFIGURATION.md`, quyết định D-33).

### Bảo mật và độ bền (sau review độc lập toàn bộ diff)

- File model chỉ được mang **tham số tinh chỉnh nhận dạng** trong thành phần `config` nhúng của nó (danh sách cho
  phép, giá trị số / boolean): một model không thể bảo Tesseract ghi ra tệp hay nạp thêm model khác. Kiểm tra trước
  khi Tesseract nạp file lúc import và ở mọi lần xác minh, kể cả với phiên bản đã import trước đó.
- Import / remove từ chối mọi đường dẫn có liên kết tượng trưng trong kho model; không thay "tại chỗ" file của
  phiên bản đang hoạt động khi manifest của nó bị mất; file nguồn được mở một lần và chép có giới hạn.
- Manifest / registry bị hỏng hoặc bị sửa tay không còn làm lỗi trang OCR Engine Manager hay worker: giá trị sai
  kiểu được coi là "không biết" và phiên bản liên quan không dùng được.
- Bước đo PDF của cơ chế tự OCR toàn trang có giới hạn (trang, đối tượng, ký tự, thời gian) và đo đúng trên trang
  xoay (`/Rotate`) và trang có page box không bắt đầu ở (0, 0).
- Card Agri giữ nút **Thử lại** khi lần cài / kiểm tra trước thất bại; file model bị thiếu được ghi đúng là "Thiếu
  file"; không gỡ được model tiếng Anh của Tesseract Best khi Agri đang dùng nó (`OCR_AGRI_WITH_ENGLISH=true`);
  `ocr readiness` không tham số chỉ tính engine tùy biến khi nó đã có phiên bản hoạt động.
- Bộ test backend được **cô lập khỏi mọi cơ sở dữ liệu thật** theo hướng fail-closed (`tests/db_isolation.py`): các
  biến `SURREAL_*` thông thường (từ shell hay `.env`) không bao giờ chọn cơ sở dữ liệu của bộ test; mặc định mọi kết
  nối đi tới một cổng đóng; muốn dùng cơ sở dữ liệu dùng tạm phải chỉ định riêng bằng `OPEN_NOTEBOOK_TEST_SURREAL_*`
  (loopback, không phải cổng mặc định, tên có `test`, credential riêng) — cấu hình không chứng minh được tính cô lập
  làm bộ test dừng trước khi chạy. Lúc kết nối, mọi địa chỉ khác địa chỉ đã quyết định đều bị từ chối. Xem
  `tests/README.md`.

### Phát hành

- Workflow *Build and Release*: trong repository này mọi job build / push bị bỏ qua trừ khi workflow được chạy
  tay **và** biến repository `CB5400_PUBLISH_IMAGES` bằng `true`. Bản phát hành là mã nguồn; không kèm image.
- Số phiên bản riêng của ChatBot 5400 (`frontend/package.json`, `VERSION`) là `1.1.0-rc.2`; phiên bản nền Open
  Notebook trong `pyproject.toml` (1.14.0) không đổi.

### Giới hạn đã biết

- Agri là **Thử nghiệm**: mới đo trên văn bản tổng hợp; chưa có số đo trên tài liệu nghiệp vụ thật và **chưa chứng
  minh được** là tốt hơn Tesseract Vietnamese Best.
- Tự OCR toàn trang **mặc định tắt**; một số kiểu watermark không được phát hiện.
- OCR không thay thế việc đối chiếu tài liệu gốc.
- PDF hỗn hợp, watermark ngang cỡ lớn và khung bao nghiêng dưới 2% trang: xem
  `docs/ocr/OCR_PHASE10G_REPORT.md` mục 13.

## [1.1.0-rc.1] - 2026-11-15 — OCR Engine Manager (Pre-release)

Bản **Pre-release** (Release Candidate), chưa phải bản ổn định; bản ổn định gần nhất vẫn là 1.0.8.
Chi tiết: `docs/ocr/OCR_RELEASE_NOTES.md`, `docs/ocr/OCR_PHASE9B_REPORT.md`,
`docs/ocr/RELEASE_CANDIDATE.md`. Không có migration cơ sở dữ liệu.

Số phiên bản riêng của ChatBot 5400 (`frontend/package.json`, `VERSION`) là `1.1.0-rc.1`; phiên bản nền
Open Notebook trong `pyproject.toml` (1.14.0) không đổi. So với mã đã nghiệm thu ở Phase 9B, bản này chỉ
khác ở tài liệu và số phiên bản — không đổi phụ thuộc, model hay logic xử lý OCR.

### Thay đổi hành vi khi nâng cấp — cần đọc

- **Thêm nguồn từ URL mặc định bị TẮT.** Biến mới `OPEN_NOTEBOOK_ENABLE_URL_INGESTION`
  chỉ bật khi đặt `true` / `1` / `yes` / `on`; thiếu hoặc sai giá trị ⇒ tắt, áp dụng
  cho mọi vai trò kể cả Quản trị viên. Khi tắt: không tạo được nguồn từ URL (kể cả
  YouTube), không xử lý lại được nguồn URL cũ; nội dung đã lưu của nguồn URL cũ vẫn
  đọc, tìm kiếm và chat được. Upload file, nhập văn bản, OCR, chat không bị ảnh hưởng.
  Bản triển khai nào cần nguồn URL phải đặt biến này thành `true` — việc đó làm xuất
  hiện lại rủi ro SSRF còn tồn tại (`docs/security/BACKGROUND_JOB_SECURITY.md` §5–6).
- **Kết quả "Sẵn sàng offline" cũ hết hiệu lực** sau khi nâng cấp: chạy lại "Chuẩn bị"
  hoặc "Kiểm tra offline" một lần cho engine đang dùng. Việc xử lý tài liệu không bị chặn.
- **Chỉ quản trị viên** được ghi / kiểm tra credential nhà cung cấp và model, quản lý
  transformation, embed và dựng lại embedding, xóa insight (trước đây backend chỉ yêu
  cầu đăng nhập; giao diện vốn đã ẩn các trang này). Tài khoản khác gọi trực tiếp các
  API đó nhận 403. Người không phải quản trị viên không còn tạo được nguồn từ một file
  đã nằm sẵn trên máy chủ (`POST /api/sources/json` với `file_path`).
- **Lần khởi động đầu của image mới cần Internet** để cài Docling đúng phiên bản đã khóa.
  Nếu file override đang đặt `UV_OFFLINE=1` / `HF_HUB_OFFLINE=1`, bỏ chúng trước khi nâng cấp.

### OCR Engine Manager

- Chọn engine OCR cho Docling: RapidOCR (mặc định, không đổi), Tesseract Vietnamese
  Fast / Best, EasyOCR Vietnamese. Layout Heron và TableFormer giữ nguyên.
- Phân loại chất lượng hiển thị riêng với trạng thái sẵn sàng và xác minh offline:
  Tesseract Best — khuyến nghị cho tiếng Việt; Tesseract Fast — ưu tiên tốc độ;
  RapidOCR — tương thích ngược; EasyOCR — thử nghiệm (hỏi xác nhận trước khi bật).
- Chuẩn bị model khi có Internet, vận hành khi ngắt Internet
  (`docs/ocr/OCR_ONLINE_PREPARATION.md`).
- Tự sửa hướng trang scan nằm ngang/ngược khi đã cài Tesseract Fast hoặc Best.
- Bước dò hướng trang có giới hạn tổng thời gian (`OCR_PAGE_OSD_BUDGET_SECONDS`, mặc định
  600 giây mỗi tài liệu): hết thời gian thì các trang còn lại giữ nguyên hướng, tài liệu
  vẫn được xử lý; log ghi `page_orientation_limit`.
- Log ghi `conversion_status` / `conversion_errors`: Docling chuyển đổi một phần không
  còn im lặng.
- `OCR_INSTALL_TESSERACT=true` trong `.env` giữ Tesseract qua mọi lần `up -d --build`.
- Công cụ benchmark cục bộ cho tài liệu của đơn vị (`scripts/ocr/local_document_benchmark.py`)
  và script kiểm tra sức khỏe chỉ đọc (`scripts/ocr/production_health_check.sh`).
- Giới hạn đã biết: xem `docs/ocr/OCR_ENGINE_MANAGER.md` §8.

### Bảo mật

- API job nền tổng quát bị khóa; job xử lý nguồn kiểm tra lại đường dẫn file và URL.
- Công tắc tắt URL ingestion (ở trên).
- Thực thi vai trò quản trị viên ở backend cho credential, model và các chức năng bảo trì
  (ở trên): đóng đường đổi `base_url` của credential để lấy khóa API và đường dò địa chỉ
  nội bộ qua "kiểm tra kết nối".

## [1.0.8] - 2026-11-12

Bổ sung **quy trình duyệt văn bản** và **phân quyền 4 vai trò**. Bản này **có
migration cơ sở dữ liệu (31, 32, 33)**, chạy tự động khi API khởi động; chỉ thêm
trường mới, dữ liệu cũ giữ nguyên (nguồn hiện có được đánh dấu "đã duyệt"). Xem
[deploy/UPDATE-v1.0.8.md](deploy/UPDATE-v1.0.8.md) trước khi nâng cấp.

### Vai trò và phân quyền

- Thêm hai vai trò bên cạnh Quản trị viên và Người dùng:
  - **Quản lý sổ tay**: gửi văn bản/nguồn vào hệ thống; văn bản phải được duyệt.
  - **Kiểm soát**: duyệt văn bản, quản lý các chuyên mục được Quản trị viên
    giao, tạo sổ tay con, gắn nguồn có sẵn vào sổ tay (không cần duyệt lại).
    Kiểm soát không tự thêm nguồn mới.
- Quản trị viên gán chuyên mục cho Kiểm soát trong **Quản lý người dùng**. Khi
  hạ vai trò hoặc xóa tài khoản Kiểm soát, hệ thống tự gỡ họ khỏi các chuyên mục
  và bỏ gán các văn bản đang chờ họ duyệt.

### Sổ tay cha–con

- Sổ tay cấp cao nhất là **chuyên mục**; bên trong có **sổ tay con** (đúng 2
  cấp). Trang Sổ tay hiển thị sổ tay con lồng dưới chuyên mục.

### Quy trình duyệt văn bản

- Văn bản do Quản lý sổ tay gửi ở trạng thái **chờ duyệt**: không hiển thị với
  người khác, không vào tìm kiếm, Hỏi đáp hay trò chuyện, và chưa được embed.
  Người gửi chọn **người phê duyệt** ở bước cuối khi thêm nguồn.
- Trang **Duyệt văn bản** cho Kiểm soát và Quản trị viên: số đếm ở menu, thông
  báo khi đăng nhập. Bấm Duyệt/Từ chối hoặc double-click để mở **cửa sổ duyệt**
  (xem nội dung, insight, đổi sổ tay ngay khi duyệt).
- **Duyệt**: văn bản hiển thị và được embed để tìm kiếm. **Từ chối**: văn bản bị
  **xóa hẳn** (bản ghi, file, embedding, insight, liên kết sổ tay).

### Sửa lỗi

- Gắn một nguồn đã có trong sổ tay không còn tạo liên kết trùng (trước đây làm
  số nguồn của sổ tay bị đếm sai).
- Xóa nguồn giờ dọn luôn các liên kết sổ tay của nguồn đó.
- Khi khởi động, hệ thống tự dọn các liên kết sổ tay bị trùng đã tạo trước đây.
- Chỉ văn bản đang **chờ duyệt** mới duyệt hoặc từ chối được; văn bản đã duyệt
  chỉ Quản trị viên xóa được.
- Build Docker không còn hỏng với lỗi "Turbopack is not supported on this
  platform" khi mạng chập chờn làm `npm ci` bỏ sót trình biên dịch của Next.js;
  bước cài đặt tự thử lại.

> Không có bản phát hành 1.0.7: số phiên bản này chỉ dùng khi thử nghiệm trên
> máy chủ test, bản chính thức là 1.0.8.

## [1.0.6] - 2026-10-15

Bản vá giao diện và phân quyền tiếp nối v1.0.5. **Không** thay đổi
RAG/GraphRAG, embedding, cách nạp nguồn hay schema cơ sở dữ liệu và **không có
migration mới**.

### Sửa lỗi giao diện

- Sửa lỗi trang **Cài đặt** tự kéo dài vô hạn khi cuộn: thanh "Lưu thay đổi"
  dạng `sticky` dùng `backdrop-blur` gây lỗi compositor của Chromium làm chiều
  cao vùng cuộn tăng liên tục. Đổi sang nền đặc (bỏ `backdrop-filter`), vẫn giữ
  thanh luôn hiển thị ở đáy.

### Chọn mô hình trong Hỏi & Tìm kiếm chỉ dành cho admin

- Ẩn nút **"Nâng cao"** (chọn mô hình) ở trang Hỏi & Tìm kiếm đối với người
  dùng thường; chỉ quản trị viên mới mở được hộp thoại chọn mô hình.
- Người dùng thường hỏi bằng mô hình do quản trị viên cấu hình (mô hình mặc
  định); vẫn hiển thị tên mô hình đang dùng (chỉ đọc).

## [1.0.5] - 2026-10-15

Phân quyền chặt hơn cho chọn mô hình khi trò chuyện, thêm công tắc bật/tắt
tính năng Podcast cho quản trị viên, và đồng bộ lại tài liệu API theo cơ chế
đăng nhập tài khoản (JWT). Bản cập nhật **không** thay đổi RAG/GraphRAG,
embedding, cách nạp nguồn hay schema cơ sở dữ liệu và **không có migration mới**
(tùy chọn Podcast lưu trong bản ghi cấu hình, mặc định Bật nên tương thích
ngược).

### Chọn mô hình khi chat chỉ dành cho admin

- Ẩn phần chọn mô hình trong Trò chuyện Sổ tay và Trò chuyện theo Nguồn đối
  với người dùng thường; chỉ quản trị viên mới thấy và chọn được.
- Người dùng thường trò chuyện bằng mô hình do quản trị viên cấu hình (mô hình
  mặc định); không gửi `model_override` thay cho họ.

### Bật/tắt tính năng Podcast (quản trị viên)

- Thêm công tắc **"Bật Podcast"** trong **Cài đặt** (chỉ quản trị viên).
- Khi bật: menu Podcast, thao tác "Tạo podcast" và lối tắt nhanh (Ctrl+K) hiển
  thị cho mọi người dùng. Khi tắt: ẩn trên toàn ứng dụng và chặn truy cập trực
  tiếp `/podcasts` (hiện thông báo "Podcast đã bị tắt").
- `GET /api/settings` trả thêm `podcast_enabled` (mọi người dùng đọc được);
  `PUT /api/settings` nay chỉ dành cho quản trị viên.

### Tài liệu

- Cập nhật `docs/7-DEVELOPMENT/api-reference.md` (mục Authentication) theo cơ chế
  đăng nhập tài khoản bằng JWT: đăng nhập `POST /api/auth/login` lấy token rồi
  gửi `Authorization: Bearer <token>`; bỏ mô tả cơ chế mật khẩu tĩnh cũ.

## [1.0.4] - 2026-10-08

Cập nhật hệ thống câu lệnh nền cho Trò chuyện Sổ tay và Trò chuyện theo
Nguồn, định hướng trợ lý chuyên biệt cho Agribank Lâm Đồng. Bản cập nhật
không thay đổi RAG/GraphRAG, embedding, cách nạp nguồn, API hay cơ sở dữ
liệu và không có migration mới.

### Trợ lý ảo Agribank Lâm Đồng

- Cập nhật system prompt của Trò chuyện Sổ tay thành
  "Trợ lý ảo Agribank Lâm Đồng", phục vụ cán bộ và người lao động.
- Cập nhật system prompt của Trò chuyện theo Nguồn, giữ nguyên nguyên tắc
  phân tích một Source cụ thể.
- Bổ sung nguyên tắc ưu tiên nguồn văn bản theo thẩm quyền và phạm vi áp
  dụng; phân biệt quy định chung với nội dung triển khai tại Agribank
  Lâm Đồng.
- Bổ sung cách xử lý văn bản sửa đổi, bổ sung, thay thế, bãi bỏ và hiệu
  lực theo thời điểm; không mặc định văn bản mới hơn luôn thay toàn bộ
  văn bản cũ.
- Yêu cầu giữ nguyên số hiệu văn bản, Điều, Khoản, Điểm, Mục và ngày
  tháng khi tài liệu cung cấp.
- Phân biệt rõ nội dung "Theo tài liệu", "Có thể suy ra" và
  "Chưa đủ căn cứ".
- Tăng cường ranh giới chống prompt injection: tên Sổ tay, Source, Note,
  Insight và nội dung tài liệu được coi là dữ liệu, không phải chỉ thị
  hệ thống.
- Loại bỏ các mô tả cũ về công cụ tìm kiếm/retrieval mà hai luồng chat
  thực tế không sử dụng.

### Phạm vi kỹ thuật

- Không thay đổi RAG hoặc GraphRAG.
- Không thay đổi embedding.
- Không thay đổi pipeline nạp hoặc xử lý Source.
- Không thay đổi API.
- Không thay đổi schema cơ sở dữ liệu.
- Không có migration mới.
- Không thay đổi cấu hình mô hình AI.

## [1.0.3] - 2026-10-07

Hoàn tất đổi thương hiệu hiển thị sang "Chatbot - 5400" trên toàn bộ phần
giao diện người dùng, và chuẩn hoá hướng dẫn cài đặt/triển khai theo nguồn
ChatBot 5400. Bản cập nhật không thay đổi RAG/GraphRAG, embedding, cách nạp
nguồn hay cơ sở dữ liệu, và không có migration mới.

### Đổi thương hiệu giao diện
- Trang lỗi kết nối API: thay "Open Notebook" bằng "Chatbot - 5400" và cập
  nhật liên kết tài liệu trỏ về kho mã của dự án.
- Trang Cài đặt: cập nhật các mô tả (tự động xóa tệp đã tải lên, gán mô hình
  mặc định, cảnh báo thiếu mô hình bắt buộc) sang tên "Chatbot - 5400" cho cả
  tiếng Việt và tiếng Anh.
- Hướng dẫn nhà cung cấp AI trong ứng dụng: thay toàn bộ "Open Notebook" bằng
  "Chatbot - 5400".
- Banner thiết lập mã hóa: liên kết "Xem tài liệu" trỏ về kho mã của dự án.

### Cài đặt và triển khai
- Chuẩn hoá quy trình cài đặt mới trên nguồn ChatBot 5400 (`.env.example`,
  `docker-compose.yml`, tài liệu triển khai VPS, README).
- Hoàn thiện hướng dẫn xác thực cho lần cài đặt mới và thống nhất hướng dẫn
  giữa môi trường phát triển và sản xuất.
- Bổ sung kiểm thử hợp đồng cài đặt (`tests/test_install_contract.py`).

## [1.0.2] - 2026-10-07

Bổ sung hệ thống phản hồi chất lượng câu trả lời AI cho Trò chuyện trong Sổ tay
và Trò chuyện theo Nguồn, kèm màn hình quản trị tổng hợp phản hồi. Bản cập nhật
không thay đổi RAG/GraphRAG, embedding hoặc cách nạp nguồn.

### Phản hồi câu trả lời AI
- Thêm các thao tác Thích, Không thích và Báo cáo cho câu trả lời AI đã được lưu
  trong Trò chuyện Sổ tay và Trò chuyện theo Nguồn.
- Thích và Không thích loại trừ lẫn nhau; người dùng có thể bỏ lựa chọn đã đánh
  giá.
- Báo cáo hoạt động độc lập với Thích/Không thích và yêu cầu nhập lý do.
- Báo cáo đã gửi là bất biến trong phiên bản này: người dùng không thể gửi lại
  để sửa nội dung hoặc thời điểm báo cáo.
- Các thao tác phản hồi chỉ khả dụng với câu trả lời AI đã được lưu; không cho
  thao tác khi câu trả lời còn đang sinh hoặc đang dùng mã tạm thời.

### Quản trị phản hồi AI
- Thêm trang Cài đặt → Phản hồi AI dành cho quản trị viên.
- Hiển thị thống kê Tổng phản hồi, Thích, Không thích và Báo cáo.
- Danh sách hỗ trợ tìm kiếm, lọc theo loại phản hồi và ngữ cảnh Sổ tay/Nguồn,
  cùng phân trang phía máy chủ.
- Có thể mở chi tiết để xem ảnh chụp thông tin người dùng, ngữ cảnh, câu hỏi,
  câu trả lời AI và lý do báo cáo tại thời điểm người dùng gửi phản hồi.
- Thêm nút "Làm mới" để cập nhật đồng thời thống kê và danh sách hiện tại mà
  không phải tải lại toàn bộ trang; giữ nguyên tìm kiếm, bộ lọc, trang đang xem
  và hộp thoại chi tiết đang mở.

### Quyền riêng tư và dữ liệu
- Người dùng chỉ được đọc hoặc thay đổi phản hồi thuộc các phiên trò chuyện của
  chính mình.
- Quản trị viên xem dữ liệu phản hồi đã được người dùng chủ động tạo, không dùng
  chức năng này để duyệt tùy ý lịch sử trò chuyện riêng tư.
- Máy chủ tự lấy và lưu ảnh chụp câu hỏi, câu trả lời, người dùng và ngữ cảnh;
  trình duyệt không gửi các nội dung này làm nguồn dữ liệu tin cậy.
- Khi một bản ghi không còn Thích/Không thích và cũng chưa được Báo cáo, bản ghi
  phản hồi được loại bỏ.

### Cơ sở dữ liệu
- Thêm migration 30 với bảng `ai_feedback` và các chỉ mục phục vụ thống kê, lọc
  và tra cứu phản hồi.
- Migration được áp dụng tự động khi ứng dụng khởi động theo cơ chế migration
  hiện có.

## [1.0.1] - 2026-10-04

Làm mới toàn bộ lớp giao diện cho chín trang chính trên nền "hệ trang dùng
chung" (SPS) và chuẩn hoá hệ thông báo theo màu ngữ nghĩa. Chỉ thay lớp trình
bày phía frontend; không đổi API, backend, cơ sở dữ liệu, RAG/GraphRAG, embedding
hay cách nạp nguồn, và không có migration mới.

### Thông báo và màu ngữ nghĩa
- Thông báo (toast) hiện ở góc dưới bên phải, có nút đóng, và không che ô soạn
  tin khi đang chat (kể cả trên điện thoại khi bàn phím ảo bật lên).
- Màu trạng thái thống nhất: thành công (xanh lá), thông tin/sẵn sàng (xanh
  teal), cảnh báo (vàng đất), lỗi (đỏ). Bỏ việc dùng màu đỏ đô thương hiệu cho
  trạng thái.
- Tạo podcast và dựng lại embedding báo "đã nhận yêu cầu" ở dạng thông tin, không
  còn báo nhầm là đã hoàn tất.

### Chín trang trên hệ trang dùng chung
- Tiêu đề trang, thanh công cụ, bảng/danh sách, trạng thái đang tải, trống, lỗi
  và kết quả rỗng dùng chung một bộ thành phần; tiêu đề trang luôn hiển thị ở mọi
  trạng thái.
- Nguồn: tìm kiếm giữ nguyên hành vi máy chủ; bảng có đủ cột, trên điện thoại
  chuyển sang danh sách; xoá nằm trong menu "…".
- Sổ tay: tìm theo tên hoặc mô tả; mặc định xem dạng danh sách.
- Tìm kiếm: bố cục vùng đọc gọn hơn, ô tuỳ chọn thu gọn trên điện thoại; giữ
  nguyên giới hạn và ngưỡng điểm.
- Podcast: thống nhất thứ tự trạng thái; sửa lỗi khiến trang treo khi tập có
  trạng thái lạ.
- Mô hình / Chuyển đổi: gom thao tác vào menu "…"; trình bày kết quả gọn lại.
- Cài đặt: thanh Lưu/Hoàn tác dính đáy khi có thay đổi chưa lưu.
- Nâng cao: khu hệ thống và khu bảo trì tách bạch, không có "vùng nguy hiểm";
  sửa lỗi tiến trình dựng lại embedding không tự dừng khi đã xong.
- Người dùng: tìm theo tên đăng nhập, gom thao tác vào menu "…", chặn xoá/hạ
  quyền quản trị viên cuối cùng và tài khoản của chính mình.

### Quyền truy cập
- Trang chỉ dành cho quản trị viên hiển thị thông báo "không có quyền" ngay trong
  trang thay vì chuyển hướng im lặng.

## [1.0.0] - 2026-09-28

Tìm kiếm nguồn (SOURCE_SEARCH_V1) ở trang "Tất cả nguồn" và tab Nguồn của từng
sổ tay. Không đổi RAG/GraphRAG, embedding, cách nạp nguồn hay ngữ cảnh sổ tay;
không có migration hay index mới.

### Tìm kiếm nguồn
- Ô "Tìm kiếm nguồn..." có biểu tượng kính lúp, nút X để xóa, phím Esc để xóa;
  cao 44px trên điện thoại.
- Tìm theo tiêu đề nguồn và tên file đã tải lên, không phân biệt hoa/thường và
  không cần gõ dấu: "quy dinh" tìm được "Quy định", "641" tìm được
  "Quy định số 641...".
- Tìm trên toàn bộ nguồn ở máy chủ, kể cả nguồn chưa được tải khi cuộn; kết quả
  vẫn tải thêm khi cuộn và giữ đúng cách sắp xếp đang chọn.
- Chỉ gửi yêu cầu sau khi ngừng gõ 300ms, không gửi theo từng phím.
- Không có kết quả thì hiện "Không tìm thấy nguồn phù hợp.".
- Trong sổ tay, ô tìm kiếm nằm ngay trên dòng Ngữ cảnh; số nguồn trên tab và số
  nguồn trong ngữ cảnh không đổi khi đang lọc; đổi sổ tay thì ô tìm kiếm tự xóa.
- API: `GET /api/sources` nhận thêm tham số tùy chọn `q`; không có `q` thì hoạt
  động như cũ.

### Hạn chế đã biết
- Số nguồn trên tab và trong ngữ cảnh là số nguồn đã tải (30 mỗi lần cuộn), chưa
  phải tổng số ở máy chủ.
- Kết quả tìm nằm ngoài các trang đã tải chưa có nút bật/tắt ngữ cảnh.
- Trên điện thoại, ô tìm kiếm tự xóa khi rời tab Nguồn rồi quay lại.

## [0.0.9] - 2026-09-27

Giao diện điện thoại và máy tính bảng (M1) cho màn hình dưới 1024px. Chỉ thay
lớp trình bày; giao diện máy tính (Design B) và hệ hộp thoại B2 giữ nguyên, không
đổi API, backend, RAG/GraphRAG, trích dẫn hay phiên trò chuyện.

### Điện thoại (dưới 640px)
- Thanh bên thay bằng ngăn điều hướng mở từ nút ☰: đủ mục Mới, các nhóm điều
  hướng, giao diện, ngôn ngữ, đổi mật khẩu, đăng xuất.
- Thanh trên gọn: tên sổ tay một dòng, nút Phiên, menu ⋮ chứa mô tả, ngày tạo/cập
  nhật, Lưu trữ và Xóa.
- Ba tab Nguồn · Ghi chú · Trò chuyện chia đều, có số đếm.
- Nguồn và Ghi chú là danh sách đầy màn hình; nút ngữ cảnh và menu đủ lớn để chạm.
- Trò chuyện không còn khung thẻ, chữ dễ đọc hơn; nguồn dẫn thành dải chip cuộn ngang.
- Ô nhập dính đáy màn hình, tự cao dần (tối đa 148px), luôn nhìn thấy khi bàn phím
  mở; tôn trọng vùng an toàn của iPhone.
- Chi tiết nguồn và thông tin chi tiết mở dạng bảng trượt từ dưới lên.

### Máy tính bảng (640–1023px)
- Cùng bố cục với điện thoại, nội dung canh giữa, hiện lại thời gian cập nhật cạnh
  tên sổ tay.

## [0.0.8] - 2026-09-27

Giao diện B2: trang đăng nhập mới và hệ thống hộp thoại thống nhất. Chỉ thay lớp
trình bày, không đổi API, backend, xác thực hay logic nghiệp vụ.

### Trang đăng nhập
- Logo và wordmark Agribank Lâm Đồng, tiêu đề "ChatBot 5400", nhãn cho ô tên
  đăng nhập và mật khẩu, khối báo lỗi rõ ràng, chân trang hiện phiên bản.
- Luồng đăng nhập, kiểm tra phiên và màn hình lỗi kết nối giữ nguyên.

### Hệ thống hộp thoại
- Mọi hộp thoại dùng chung một khung với 4 cỡ: nhỏ 420px, vừa 560px, lớn 760px,
  rất lớn 1040px; cao tối đa 88% màn hình; dưới 640px rộng bằng màn hình trừ lề.
- Tiêu đề và hàng nút luôn cố định, chỉ phần nội dung cuộn, nên nút "Hủy",
  "Lưu", "Xóa"… không bao giờ bị che trên màn hình thấp.
- Hộp thoại xác nhận và xóa không còn nút X; nút xóa màu đỏ thống nhất.
- Cấu hình mô hình: "Đặt lại mặc định" bên trái, "Hủy" | "Lưu thay đổi" bên
  phải; bấm Hủy sẽ bỏ lựa chọn chưa lưu.
- Thêm/Sửa chuyển đổi: hộp thoại rộng, có tiêu đề rõ ràng, ô prompt tối thiểu
  320px và co giãn theo màn hình.
- Hộp thoại xóa cấu hình AI được dịch đầy đủ tiếng Việt/tiếng Anh; hộp thoại xóa
  chuyển đổi hiện đúng tiêu đề "Xóa chuyển đổi".

### Sửa lỗi
- Trang sổ tay không còn bị đẩy lệch lên khiến thanh tiêu đề bị che một phần.

## [0.0.7] - 2026-09-26

Giao diện mới theo phương án B (Modern Knowledge Assistant) — chỉ thay lớp
trình bày, không đổi API, backend, RAG/GraphRAG hay logic nghiệp vụ.

### Font chữ (tự host, chạy offline)
- Be Vietnam Pro cho toàn bộ giao diện, Bricolage Grotesque cho tiêu đề; tệp
  WOFF2 kèm giấy phép OFL nằm trong mã nguồn, không tải font từ Internet.
- Font mã/số dùng font monospace của hệ thống (Spline Sans Mono thiếu dấu
  tiếng Việt).

### Bố cục trang sổ tay (màn hình ≥ lg)
- Thanh bên thu gọn thành rail 64px (mặc định); vẫn mở rộng được và nhớ lựa
  chọn. Khi thu gọn, rê chuột vào logo để hiện nút "Mở rộng thanh bên".
- Nguồn và Ghi chú gộp thành một bảng Ngữ cảnh 340px có tab; mỗi mục là một
  hàng gọn có đường phân cách.
- Tiêu đề sổ tay thành thanh trên 56px.
- Khung trò chuyện phẳng, cột đọc 760px, câu trả lời AI không đóng khung,
  ô nhập mới có chip mô hình và chip ngữ cảnh. Áp dụng cho cả trò chuyện theo
  nguồn.
- Màn hình nhỏ hơn lg giữ nguyên bố cục cũ.

### Trích dẫn
- Khối "Nguồn dẫn": mỗi trích dẫn là một hàng riêng gồm số, tên và loại
  (Nguồn / Chi tiết / Ghi chú), không còn hiện mã ID thô. Tên lấy từ dữ liệu đã
  tải sẵn, không phát sinh thêm request.
- Số trích dẫn trong câu trả lời hiển thị dạng chip nhỏ; bấm vẫn mở đúng nguồn.

### Sửa lỗi
- Hộp thoại "Cấu hình mô hình" rộng hơn, tên mô hình dài không bị tràn.
- Hộp thoại Thêm/Sửa chuyển đổi luôn hiện nút "Hủy" và "Thêm"/"Lưu thay đổi"
  trên màn hình thấp (phần nội dung tự cuộn).

## [0.0.6] - 2026-09-25

Sửa thông báo bản cập nhật mới.

### Thông báo cập nhật
- Thông báo hiện lại **mỗi lần mở/tải lại ứng dụng** cho tới khi hệ thống được
  cập nhật (trước đây chỉ hiện một lần do cờ `sessionStorage` bị trình duyệt giữ
  lại); vẫn không hiện lại khi chuyển trang trong ứng dụng.
- Giao diện đồng bộ với các thông báo khác: nền đỏ bordeaux Agribank, bố cục tiêu
  đề + mô tả, nút "Nâng cao" nền trắng.

## [0.0.5] - 2026-09-24

Khôi phục thông báo bản cập nhật mới khi mở ứng dụng.

### Thông báo cập nhật
- Khi quản trị viên mở ứng dụng, hệ thống kiểm tra ngầm bản Release mới nhất trên
  GitHub; nếu có bản mới hơn, hiện thông báo ở **góc dưới bên phải**: "Có bản cập
  nhật mới (vX.Y.Z). Vui lòng kiểm tra trong Công cụ nâng cao." kèm nút mở nhanh
  trang *Công cụ nâng cao*.
- Chỉ hiện **một lần mỗi phiên** (lưu cờ `update_notified` trong `sessionStorage`),
  không hiện lại khi chuyển trang. Lỗi mạng được bỏ qua, không làm phiền người dùng.

## [0.0.4] - 2026-09-24

Khôi phục tính năng tự động kiểm tra phiên bản mới.

### Kiểm tra phiên bản
- *Công cụ nâng cao → Thông tin hệ thống* hiển thị lại dòng "Phiên bản mới nhất",
  lấy từ bản Release mới nhất trên GitHub của dự án
  (`nghoainam1902ps4-lgtm/ChatBot5400-Version02`).
- So sánh phiên bản theo chuẩn SemVer (so từng phần dạng số, `0.0.10` > `0.0.9`;
  bản thử nghiệm `-rc` thấp hơn bản chính thức).
- Ba trạng thái: **Có bản cập nhật mới** (màu cam, biểu tượng chuông),
  **Đã cập nhật** (đỏ bordeaux), **Lỗi kết nối** khi không gọi được GitHub.

## [0.0.3] - 2026-09-24

Bản cập nhật nhận diện thương hiệu và hiển thị phiên bản.

### Giao diện & nhận diện thương hiệu
- **Trang đăng nhập**: tiêu đề đổi thành "AGRIBANK CHI NHÁNH LÂM ĐỒNG"; bỏ dòng
  gợi ý tài khoản mặc định (admin / admin) và dòng hiển thị địa chỉ API.
- **Phiên bản** hiển thị ở trang đăng nhập và *Công cụ nâng cao → Thông tin hệ
  thống* được đọc tự động từ `frontend/package.json` (không còn viết cứng).

### Kiểm tra phiên bản
- Bỏ cơ chế kiểm tra bản cập nhật từ repository gốc (open-notebook trên GitHub):
  backend không còn gọi ra GitHub, bỏ thông báo nổi "có bản mới".
- *Thông tin hệ thống* ẩn dòng "Phiên bản mới nhất"; trạng thái luôn "Đã cập nhật".

## [0.0.2] - 2026-09-24

Bản vá tập trung vào cô lập dữ liệu theo người dùng, trải nghiệm xem tài liệu và
triển khai.

### Sửa lỗi cô lập dữ liệu theo người dùng
- **Chat theo từng Nguồn (Chat with Source)**: lọc theo `user_id` ở tầng CSDL và
  chuẩn hóa kiểm tra chủ sở hữu — user không còn nhìn thấy lịch sử chat của nhau.
  Query key React Query kèm `userId`, xóa cache khi đăng xuất.
- **Số lượng Ghi chú trên thẻ Notebook (Notes count)**: chỉ đếm ghi chú của user
  đang đăng nhập (trước đây cộng gộp ghi chú của mọi user). Số lượng Nguồn giữ
  nguyên là dữ liệu chung. Áp dụng cho danh sách và chi tiết notebook.

### Giao diện & trải nghiệm
- **Modal xem Nguồn (Source preview)** khi mở từ trong Notebook: phóng lớn
  (rộng/cao hơn), ghim tiêu đề, chỉ cuộn phần nội dung.
- **Hướng dẫn kết nối nhà cung cấp AI**: thay liên kết trỏ ra GitHub bằng modal
  hiển thị ngay trong ứng dụng (bản dịch tiếng Việt của `ai-providers.md`), tiêu
  đề/liên kết màu đỏ bordeaux; sửa lỗi modal kẹt ở trạng thái "Đang tải…".

### Triển khai
- Sửa lỗi Docker build "no space left on device": loại dữ liệu runtime trong
  `deploy/` (CSDL, model docling/torch, chứng chỉ) khỏi build context.

## [0.0.1] - 2026-09-22

Bản phát hành đầu tiên — nền tảng Open Notebook được tùy biến cho Agribank Chi
nhánh Lâm Đồng.

### Xác thực & phân quyền (Auth / RBAC)
- Đăng nhập bằng tài khoản (JWT), mật khẩu băm bcrypt; tự tạo admin/admin lần đầu.
- Vai trò **admin** (quản trị người dùng, notebook, source) và **user thường**
  (chỉ xem, chat, tạo ghi chú). Ẩn menu quản trị (Cài đặt/Mô hình/Chuyển đổi/
  Nâng cao) khỏi sidebar và Command Palette với user thường.
- Trang quản lý người dùng cho admin: thêm/sửa/xóa, đặt lại mật khẩu, đổi mật khẩu.

### Cô lập dữ liệu theo người dùng
- Chat và ghi chú riêng tư theo từng user.
- "Xem gần đây" (Recently Viewed) theo từng user (bảng `recently_viewed`).
- Xóa sạch cache (React Query) + state khi đăng xuất/đăng nhập, giữ lại cài đặt
  giao diện (theme/ngôn ngữ).

### Giao diện & thương hiệu
- Tông màu trắng + đỏ bọc đô + vàng chuẩn Agribank; font Times New Roman.
- Logo Agribank + chữ "Agribank Lâm Đồng" ở sidebar (thu gọn hiện logo); favicon
  và tiêu đề "ChatBot 5400 - Agribank Chi Nhánh Lâm Đồng".
- Toast "Thành công" nền đỏ bordeaux; các modal (đăng nhập/đổi mật khẩu/quản lý
  user) thu gọn, căn giữa.
- Song ngữ: chỉ giữ Tiếng Việt + English, mặc định Tiếng Việt; lưu ngôn ngữ và
  theme theo từng user.

### Xử lý tài liệu (Điều/Khoản)
- Bật **docling** mặc định để giữ đúng cấu trúc Điều → Khoản → điểm cho .docx/.pdf.
- Hiển thị source kiểu công văn: căn đều hai bên, thụt đầu dòng, in đậm "Điều n.",
  căn giữa Chương/Mục, thụt Khoản/điểm theo cấp, bỏ dấu chấm thừa do trích xuất.

### Triển khai
- Bộ triển khai VPS (`deploy/`): Docker Compose (SurrealDB + app + Caddy HTTPS),
  build từ mã nguồn, docling cài ở lần chạy đầu (PyTorch CPU), tài liệu
  `DEPLOY-VPS.md`. Hướng dẫn chạy local trên Windows (`SETUP-WINDOWS.md`).

### Kiểm thử
- Bộ test backend (auth/RBAC/isolation/recently-viewed) và frontend (vitest)
  đều xanh.
