# Custom Tesseract Model Manager — thiết kế và vận hành

Cập nhật: 2026-11-16 (Phase 10) · Áp dụng cho engine **Tesseract Vietnamese Agri** (`tesseract_agri`).

Tài liệu này công khai: không chứa mật khẩu, khóa, model, dữ liệu huấn luyện hay tài liệu nội bộ.
Hướng dẫn thao tác từng bước cho người vận hành: [OCR_AGRI_MODEL_GUIDE.md](OCR_AGRI_MODEL_GUIDE.md).
Kết quả đo: [OCR_AGRI_BENCHMARK.md](OCR_AGRI_BENCHMARK.md). Báo cáo giai đoạn: [OCR_PHASE10_REPORT.md](OCR_PHASE10_REPORT.md).

## 1. Mục tiêu

Cho phép dùng một model Tesseract **tự fine-tune** (`vie_agri.traineddata`) như lựa chọn thứ năm của OCR
Engine Manager, và thay model bằng bản fine-tune mới hơn **mà không sửa mã nguồn, không build lại Docker
image, không khởi động lại**: chỉ cần import file mới thành một phiên bản mới.

Những gì **không** thay đổi: bốn lựa chọn chính thức (RapidOCR, Tesseract Fast, Tesseract Best, EasyOCR), model
và checksum của chúng, engine mặc định (RapidOCR), Open Notebook 1.14.0, Content Core 2.0.7, Docling 2.129.0,
Layout Heron, TableFormer Accurate, tiền xử lý PDF, cổng OSD của Tesseract, Force Full Page OCR, số luồng CPU,
lược đồ cơ sở dữ liệu. Không có OCR adapter mới: Agri dùng đúng `TesseractCliOcrOptions` chính thức của
Docling và đúng binary Tesseract mà Fast/Best đang dùng.

## 2. Kiến trúc

| Thành phần | Tệp | Vai trò |
|---|---|---|
| Catalog | `open_notebook/ocr/catalog.py` | `ENGINE_IDS` giữ nguyên 4 lựa chọn chính thức; `CUSTOM_ENGINE_IDS = ("tesseract_agri",)`; `ALL_ENGINE_IDS` là danh sách hiển thị. Engine Agri chỉ ghim (pin) dữ liệu định hướng `osd` dùng chung — **không có checksum hay URL nào của model custom trong mã nguồn** |
| Quản lý phiên bản | `open_notebook/ocr/custom_models.py` | Import, manifest, kiểm tra, kích hoạt, rollback, trạng thái |
| Tùy chọn OCR | `open_notebook/ocr/options.py` | `engine_langs()` trả ngôn ngữ của phiên bản; `OcrSettings.custom_version` đóng băng phiên bản cho từng job |
| Trạng thái / readiness | `status.py`, `store.py`, `readiness.py` | Model status = file chính thức + phiên bản đang hoạt động; fingerprint readiness gồm phiên bản + SHA-256 |
| CLI | `open_notebook/ocr/cli.py` | Nhóm lệnh `custom` |
| API | `api/routers/ocr.py`, `api/ocr_service.py` | 3 endpoint quản trị (không có upload) |
| Giao diện | `frontend/.../OcrEngineManager.tsx` | Card Tesseract Vietnamese Agri |

### 2.1 Bố cục lưu trữ (trên volume dữ liệu, tồn tại qua restart / recreate / nâng cấp image)

```text
<data>/ocr/
├── models/tesseract/                      == TESSDATA_PREFIX (không đổi, D-04)
│   ├── osd.traineddata                    chính thức, dùng chung
│   ├── fast/…  best/…                     chính thức, KHÔNG bao giờ bị ghi đè
│   └── custom/agri/
│       ├── v1/vie_agri.traineddata        mỗi phiên bản một thư mục, chỉ đọc (0444)
│       ├── v2/vie_agri.traineddata
│       └── v3/vie_agri.traineddata
├── manifests/custom/agri/
│   ├── versions/v1.json  v2.json  …       manifest từng phiên bản
│   └── registry.json                      phiên bản đang hoạt động / phiên bản trước / lịch sử
└── downloads/custom-staging/              vùng staging khi import (ngoài TESSDATA_PREFIX)
```

Trong Docker `<data>` là `/app/data` (trên máy chủ: thư mục `notebook_data` cạnh file compose).

Mỗi phiên bản là một **ngôn ngữ Tesseract riêng**: `custom/agri/<phiên bản>/vie_agri` (đường dẫn con dưới
TESSDATA_PREFIX, đúng cơ chế Fast/Best đã dùng — `fast/vie`, `best/vie`). Vì vậy file của phiên bản cũ không bao
giờ bị sửa hay thay thế khi có phiên bản mới.

### 2.2 Manifest của một phiên bản

`manifests/custom/agri/versions/<phiên bản>.json`:

| Trường | Ý nghĩa |
|---|---|
| `version` | Mã phiên bản (do người import đặt) |
| `sha256`, `size` | SHA-256 và dung lượng của file đã lưu — **điểm neo tin cậy** của phiên bản |
| `imported_at`, `imported_at_iso` | Thời điểm import |
| `source_name`, `notes` | Tên file nguồn (không lưu đường dẫn), ghi chú tự do |
| `duplicate_of` | Các phiên bản khác có nội dung giống hệt (cảnh báo import nhầm file cũ) |
| `traineddata` | Cấu trúc file: các thành phần, chuỗi phiên bản của Tesseract |
| `smoke` | Kết quả smoke test bằng Tesseract thật: `ok`, CER trên mẫu, phiên bản Tesseract |
| `verification` | `verified` / `corrupted` / `missing`, thời điểm kiểm tra gần nhất, chi tiết |
| `readiness` | Kết quả kiểm tra pipeline (online / local_only / offline) **của riêng phiên bản này** |

`registry.json`: `active_version`, `previous_version` (đích rollback), `activated_at`, `history` (50 lần chuyển
gần nhất: thời điểm, hành động, từ → đến, SHA-256, người thực hiện).

## 3. Quy trình import

`custom import --file FILE --version ID` thực hiện tuần tự; lỗi ở bước nào thì dừng ở bước đó, **không có gì
được lưu** và phiên bản cũ không bị ảnh hưởng:

1. **Kiểm tra file**: phải là file thường trên máy (không phải symlink, thư mục, URL), đuôi `.traineddata`,
   kích thước từ 4 KiB đến 512 MiB; mã phiên bản hợp lệ và chưa tồn tại. Mã đang là phiên bản hoạt động hoặc phiên
   bản rollback mà manifest không đọc được → từ chối (không bao giờ thay file "tại chỗ"). Không thành phần nào của
   đường dẫn đích được là symlink.
2. **Staging**: chép vào `downloads/custom-staging/` — nằm ngoài TESSDATA_PREFIX nên OCR không bao giờ đọc được
   file chưa kiểm tra. File nguồn được mở **một lần** (`O_NOFOLLOW`, `O_NONBLOCK`); loại và kích thước lấy từ chính
   file đã mở, việc chép dừng ở giới hạn kích thước. Phần staging sót lại của một lần import bị ngắt được dọn ở
   lần import sau.
3. **Checksum**: tính SHA-256 của bản đã staging và so với luồng đã chép.
4. **Kiểm tra cấu trúc và tham số nhúng** — *trước khi* Tesseract được chạy trên file: đọc bảng thành phần của
   traineddata (phải có `lstm`, `lstm-unicharset`, `lstm-recoder`) và đọc thành phần `config`. `config` là tệp
   tham số mà Tesseract áp dụng **không hạn chế** mỗi lần nạp model (có thể chỉ định tệp để ghi, hoặc nạp thêm model
   khác). Chỉ các tham số tinh chỉnh nhận dạng trong danh sách cho phép (`ALLOWED_CONFIG_PARAMS`, ví dụ hai tham số
   của model tiếng Việt chính thức: `language_model_ngram_on`, `classify_misfit_junk_penalty`) với giá trị là số
   hoặc boolean được chấp nhận; tham số khác, dòng dài quá 512 byte, nội dung nhị phân hoặc tệp lớn hơn 16 KiB →
   **từ chối import**. Các tham số được ghi vào manifest và in ra khi import. Sau đó `tesseract --list-langs` trên
   thư mục staging.
5. **Smoke test**: OCR mẫu tiếng Việt có sẵn bằng đúng binary Tesseract của container; từ chối nếu Tesseract
   không nạp được model, không ra chữ, hoặc CER trên mẫu vượt 30% (giới hạn hợp lý, không phải ngưỡng chất lượng).
6. **Lưu phiên bản**: tạo thư mục phiên bản mới, chuyển file vào (đổi tên nguyên tử), đặt chỉ đọc, băm lại.
7. **Ghi manifest** (ghi tệp tạm, `fsync`, rồi đổi tên — nguyên tử và bền).
8. **Readiness**: chạy toàn bộ pipeline Docling (Layout Heron + TableFormer + Tesseract với **đúng phiên bản vừa
   import**) trong tiến trình con bị chặn mạng; kết quả ghi vào manifest của phiên bản. Bỏ qua bằng
   `--skip-readiness`.
9. **Không kích hoạt**: lệnh kết thúc với thông báo phiên bản đã import nhưng **chưa hoạt động**.

Import không bao giờ: tải từ Internet, ghi đè một phiên bản (mã đã tồn tại → báo lỗi), ghi đè
`best/vie.traineddata`, đổi phiên bản đang hoạt động.

## 4. Kích hoạt, rollback và tính nhất quán của job

- `custom activate --version ID` (hoặc nút **Chuyển sang phiên bản này**): băm lại toàn bộ file, so với
  manifest; chỉ khi khớp và smoke test đã đạt mới ghi `registry.json`. Phiên bản đang hoạt động trước đó trở
  thành đích rollback. Nếu kiểm tra thất bại: phiên bản đang hoạt động **không đổi**, manifest ghi `corrupted`.
- `custom rollback` (hoặc nút **Rollback**): kiểm tra rồi quay về `previous_version`. Rollback lần nữa quay lại
  phiên bản vừa rời.
- `custom remove --version ID`: xoá một phiên bản không hoạt động. Lệnh kiểm tra hàng đợi job trong cơ sở dữ liệu
  và từ chối nếu còn job OCR đang chạy (một job giữ phiên bản lúc bắt đầu) hoặc nếu không đọc được hàng đợi. Phiên
  bản đang hoạt động không xoá được; nếu phiên bản bị xoá là đích rollback thì đích rollback được để trống. Không
  có endpoint API hay nút giao diện cho thao tác này.
- **Một job — một phiên bản.** Khi một tài liệu bắt đầu xử lý, phiên bản đang hoạt động được ghi vào
  `OcrSettings.custom_version` (đối tượng bất biến). Mọi lần gọi Tesseract của job đó dùng ngôn ngữ
  `custom/agri/<phiên bản đó>/vie_agri`. Chuyển phiên bản giữa chừng **không** ảnh hưởng job đang chạy (file của
  phiên bản cũ vẫn nguyên); job bắt đầu sau đó dùng phiên bản mới. Log worker ghi
  `OCR custom model used for the whole document: … version=… sha256=…`.
- Hai cấp "kích hoạt" độc lập: (1) **phiên bản** nào của Agri đang hoạt động — `registry.json` trên volume;
  (2) **engine** nào đang dùng cho OCR — `ContentSettings.docling_ocr_engine` trong cơ sở dữ liệu, đổi bằng nút
  **Sử dụng** như bốn engine khác. Không có thay đổi lược đồ cơ sở dữ liệu; giá trị `tesseract_agri` chỉ là một
  chuỗi mới của trường sẵn có.

## 5. Readiness theo phiên bản

Fingerprint readiness của `tesseract_agri` gồm mọi thứ của engine Tesseract (phiên bản Docling, Content Core,
Tesseract, cache Layout/TableFormer, cấu hình chất lượng) **cộng** `custom_model = {version, sha256, size,
langs}`. Hệ quả:

- kết quả kiểm tra của v1 không bao giờ được tính cho v2 (đổi phiên bản → trạng thái "Chưa kiểm tra toàn bộ
  pipeline" cho tới khi v2 được kiểm tra);
- nếu SHA-256 trong manifest đổi (file bị thay), kết quả cũ thành `stale`;
- bật/tắt `OCR_AGRI_WITH_ENGLISH` cũng làm kết quả cũ mất hiệu lực;
- quay về v1 thì kết quả của chính v1 vẫn dùng được, vì đúng là cùng file, cùng môi trường.

Một lần kiểm tra ghi rõ phiên bản nó chạy; nếu tiến trình kiểm tra chạy nhầm phiên bản khác, kết quả bị hủy.

## 6. Phát hiện file bị sửa ngoài manifest

| Thời điểm | Kiểm tra |
|---|---|
| Mỗi lần xem trạng thái (UI / `custom status`) | So kích thước + SHA-256 với manifest (dùng cache theo kích thước + mtime) |
| Trước mỗi job OCR | `assert_engine_ready` — phiên bản của job phải khớp manifest, nếu không job dừng với lỗi rõ ràng (không bao giờ tự chuyển engine) |
| `custom verify`, kích hoạt, rollback | Băm lại **toàn bộ** file (không dùng cache) + nạp lại bằng Tesseract |
| Mọi lần kiểm tra ở trên | Đọc lại thành phần `config` của file (vài trăm byte): tham số ngoài danh sách cho phép → phiên bản không được xác minh. Áp dụng cả cho phiên bản đã import bằng bản phát hành cũ hơn |

File bị sửa / thiếu → engine chuyển trạng thái **Lỗi**, card hiện "File đã bị thay đổi sau khi import", không
thể kích hoạt phiên bản đó. Cách khắc phục: `custom rollback`, hoặc import lại file tốt thành phiên bản mới.

Giới hạn đã biết: manifest và model nằm trên cùng một volume. Người có quyền ghi vào volume có thể sửa cả hai;
điểm neo độc lập là SHA-256 mà chủ model tự lưu khi fine-tune — hãy so với cột SHA-256 của `custom list`.

**Manifest hoặc registry bị hỏng / bị sửa tay.** Mọi giá trị đọc từ hai loại tệp này được chuẩn hóa kiểu trước khi
dùng: giá trị sai kiểu trở thành "không biết" (lịch sử rỗng, không có phiên bản rollback, phiên bản không được
kích hoạt) thay vì làm lỗi trang OCR Engine Manager, worker hay lần import kế tiếp. Manifest ghi một mã phiên bản
khác với tên tệp của nó không được coi là một phiên bản. Kết quả readiness được ghi vào manifest dưới cùng khóa
của họ model với import / verify / activate / rollback / remove.

## 7. Lệnh CLI

Quy ước (chạy trên máy chủ, trong thư mục chứa file compose của stack):

```bash
ocr() { docker compose exec open_notebook /app/.venv/bin/python -m open_notebook.ocr.cli "$@"; }
```

| Lệnh | Tác dụng |
|---|---|
| `ocr custom import --file FILE --version v1 [--notes "…"] [--skip-readiness]` | Kiểm tra và lưu thành phiên bản mới, **không** kích hoạt |
| `ocr custom list [--json]` | Danh sách phiên bản: SHA-256, dung lượng, ngày import, kiểm tra, readiness |
| `ocr custom status [--json] [--no-db]` | Trạng thái engine, phiên bản đang hoạt động / rollback, thư mục lưu |
| `ocr custom verify [--version v1]` | Băm lại + nạp bằng Tesseract (không có `--version`: mọi phiên bản) |
| `ocr custom activate --version v1` | Kích hoạt phiên bản đã xác minh |
| `ocr custom rollback` | Quay về phiên bản trước |
| `ocr custom remove --version v1` | Xoá một phiên bản **không** hoạt động (file + manifest). Từ chối khi còn tài liệu đang xử lý; không bao giờ đụng model chính thức |
| `ocr readiness --engines tesseract_agri --check` | Kiểm tra readiness offline của phiên bản đang hoạt động |

Mọi lệnh có `--help`; lỗi in `[ocr] ERROR: …` và trả mã thoát 1. Mã phiên bản: 1–32 ký tự chữ, số, `-`, `_`
(bắt đầu bằng chữ hoặc số) — ví dụ `v2`, `2026-12-01`, `agri_v3`.

## 8. API (chỉ quản trị viên)

| Endpoint | Tác dụng |
|---|---|
| `GET /api/ocr/engines` | Engine thứ năm có thêm khối `custom` (phiên bản, SHA-256, readiness, hướng dẫn import). Bốn engine cũ: `custom = null` |
| `POST /api/ocr/engines/tesseract_agri/custom/activate` `{"version": "v2"}` | Chuyển phiên bản |
| `POST /api/ocr/engines/tesseract_agri/custom/rollback` | Quay về phiên bản trước |
| `POST /api/ocr/engines/tesseract_agri/custom/verify` `{"version": "v2"}` | Xác minh lại một phiên bản |
| `POST /api/ocr/engines/tesseract_agri/activate` · `/test` · `/readiness-check` | Như bốn engine khác |

Toàn bộ router `/api/ocr` yêu cầu `require_admin` ở backend (401 khi chưa đăng nhập, 403 với vai trò user /
contributor / approver). **Không có endpoint upload file model qua HTTP** — giai đoạn này file chỉ vào hệ thống
qua CLI trên máy chủ. `DELETE …/tesseract_agri/model` bị từ chối (400).

## 9. Giao diện

**Cài đặt → OCR Engine Manager → Tesseract Vietnamese Agri** hiển thị: nhãn "Model tự fine-tune" + chất lượng
"Thử nghiệm"; phiên bản đang hoạt động, phiên bản rollback, dung lượng, SHA-256 đầy đủ, ngày import, trạng thái
kiểm tra, readiness offline; danh sách phiên bản; các nút **Sử dụng** (chọn engine), **Kiểm tra** (chạy pipeline
trên mẫu), **Chuyển sang phiên bản này**, **Rollback về …**, **Xác minh**, **Kiểm tra sẵn sàng offline**; và hướng
dẫn import bằng CLI. Giao diện của bốn engine cũ không đổi.

## 10. Cấu hình

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `OCR_AGRI_WITH_ENGLISH` | `false` | `true` thêm `best/eng` làm ngôn ngữ thứ hai. Khi bật, cần model tiếng Anh của Tesseract Vietnamese Best đã cài (kiểm theo checksum chính thức). Mặc định tắt theo kết quả đo ở Phase 10E |

Các biến `OCR_DATA_DIR`, `OCR_MODELS_DIR`, `OCR_MANIFESTS_DIR`, `TESSDATA_PREFIX` áp dụng như cũ.

## 11. Bảo mật

| Rủi ro | Biện pháp |
|---|---|
| Path traversal qua mã phiên bản | Chỉ nhận `\A[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z`; mọi đường dẫn được dựng lại và kiểm bằng `safe_child` (không thoát khỏi thư mục models) |
| Symlink | File nguồn là symlink → từ chối. **Bất kỳ** thành phần nào của đường dẫn model dưới thư mục models (`tesseract`, `custom`, họ model, thư mục phiên bản, file) là symlink → import và remove từ chối, phiên bản không được xác minh và không được dùng. (`safe_child` chỉ bảo đảm không thoát khỏi thư mục models; kiểm tra này chặn cả liên kết trỏ sang `best/` hoặc sang một phiên bản khác) |
| Model tự đặt tham số Tesseract | Thành phần `config` nhúng trong file chỉ được chứa tham số trong danh sách cho phép, giá trị số / boolean (mục 3, bước 4); kiểm tra trước khi Tesseract nạp file và ở mọi lần xác minh |
| File nguồn bị đổi giữa lúc kiểm tra và lúc chép | Mở một lần, lấy loại / kích thước từ file đã mở, chép có giới hạn |
| Manifest / registry bị sửa tay | Chuẩn hóa kiểu khi đọc; sai kiểu ⇒ đóng (mục 6) |
| URL tùy ý / tải từ Internet | Không có mã tải mạng trong `custom_models.py`; đường dẫn chứa `://` bị từ chối |
| File độc hại / hỏng | Kiểm cấu trúc + nạp bằng Tesseract trong staging trước khi file vào TESSDATA_PREFIX |
| Người dùng thường thao tác | Mọi endpoint yêu cầu quản trị viên ở backend; import chỉ qua CLI trên máy chủ |
| Ghi đè model chính thức | Phiên bản chỉ được ghi dưới `custom/agri/<phiên bản>/`, và thư mục đó không được là liên kết; không có đường mã nào ghi vào `best/` hay `fast/`. Model tiếng Anh của Best không gỡ được khi Agri đang dùng nó làm ngôn ngữ thứ hai |
| Đưa model lên Git | Model, manifest, `.env` và thư mục dữ liệu nằm ngoài kho mã; `deploy/agri-test/.gitignore` và `.dockerignore` loại trừ chúng |

## 12. Sao lưu và khôi phục

Sao lưu **hai thư mục** (cùng lúc, khi không có lệnh import đang chạy):

```bash
tar -C ./notebook_data/ocr -czf agri-models-$(date +%Y%m%d).tgz \
  models/tesseract/custom manifests/custom
sha256sum agri-models-$(date +%Y%m%d).tgz
```

Khôi phục: giải nén vào đúng `./notebook_data/ocr`, rồi `ocr custom verify` (mọi phiên bản phải `verified`) và
`ocr custom status`. Bản sao lưu chứa model nội bộ: lưu ở nơi có kiểm soát truy cập, không đưa lên GitHub.

## 13. Nâng cấp ứng dụng mà không mất model

Model và manifest nằm trên volume dữ liệu, không nằm trong image. Nâng cấp = build image mới + tạo lại **riêng**
container ứng dụng (`docker compose up -d --no-deps open_notebook`): các phiên bản, phiên bản đang hoạt động và
lịch sử còn nguyên. Sau nâng cấp chạy `ocr custom verify` và `ocr readiness --engines tesseract_agri --check`
(fingerprint đổi nếu phiên bản Docling/Tesseract đổi).

## 14. Hạ cấp về bản không có engine Agri (v1.1.0-rc.1)

Bản cũ không biết giá trị `tesseract_agri`. **Trước khi** hạ cấp, chọn lại một engine mà bản cũ hỗ trợ (ví dụ
Tesseract Vietnamese Best hoặc RapidOCR) trong OCR Engine Manager. Nếu quên: bản cũ vẫn chạy nhưng xử lý tài liệu
mới bằng RapidOCR mặc định cho tới khi một engine được chọn lại (đã kiểm thử, Phase 10F). Thư mục `custom/` và manifest trên volume
được bản cũ bỏ qua và vẫn còn nguyên để dùng lại khi nâng cấp trở lại. Chi tiết và kết quả kiểm thử:
[OCR_ROLLBACK.md](OCR_ROLLBACK.md), [OCR_PHASE10_REPORT.md](OCR_PHASE10_REPORT.md).
