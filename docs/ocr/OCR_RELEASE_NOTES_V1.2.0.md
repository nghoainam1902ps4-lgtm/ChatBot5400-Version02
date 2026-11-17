# Ghi chú phát hành — ChatBot5400 v1.2.0 — Advanced OCR & Custom Model Manager

Ngày phát hành: 2026-11-17 · Tag `v1.2.0` trên nhánh `claude/practical-wozniak-9s1t6z` · **Bản phát hành chính thức
(Official Release)**

| | |
|---|---|
| Phiên bản | `1.2.0` (bản trước: `1.1.0-rc.2` — Pre-release; bản chính thức trước: `1.0.8`) |
| Loại phát hành | **Bản chính thức**, GitHub Release đánh dấu **Latest** |
| Mã ứng dụng | **giống hệt** `v1.1.0-rc.2` — từ rc.2 tới bản này chỉ đổi số phiên bản và tài liệu (mục 10) |
| Nền | Open Notebook 1.14.0, Content Core 2.0.7, Docling 2.129.0, Tesseract 5.5.0, RapidOCR 3.9.2 — **không đổi** |
| Phụ thuộc | `uv.lock`, `pyproject.toml`, `Dockerfile`, `frontend/package-lock.json` (ngoài dòng `version`) giống hệt rc.2 |
| Cơ sở dữ liệu | **không có migration**; schema giống rc.2 và rc.1 |
| Phát hành | **chỉ mã nguồn**; không kèm Docker image, cơ sở dữ liệu hay model (mục 12) |
| Triển khai | bản phát hành này **không** cập nhật hệ thống nào; cập nhật một nơi triển khai cần phê duyệt riêng |
| Rollback | [OCR_V120_ROLLBACK_GUIDE.md](OCR_V120_ROLLBACK_GUIDE.md) |

### Bản phát hành phần mềm chính thức ≠ sẵn sàng an ninh cho nghiệp vụ

`v1.2.0` là **bản phát hành phần mềm chính thức** (*Official Software Release*): bộ tính năng của Phase 9 và Phase 10
đã được nghiệm thu kỹ thuật, ổn định về mã, có hướng dẫn nâng cấp và rollback. Điều đó **không** có nghĩa hệ thống đã
đạt **nghiệm thu bảo mật cho nghiệp vụ** (*Production Security Readiness*). Các giới hạn bảo mật ở mục 11–12 vẫn còn;
mỗi nơi triển khai phải tự đánh giá và gia cố trước khi dùng cho dữ liệu nghiệp vụ chính thức. CORS mở và xác thực bằng
mật khẩu đơn giản là **mặc định cho phát triển**, không phải cấu hình gia cố.

## 1. Tổng quan

`v1.2.0` gom thành một bản chính thức toàn bộ phần OCR đã phát triển và nghiệm thu qua hai bản thử nghiệm
`v1.1.0-rc.1` (OCR Engine Manager) và `v1.1.0-rc.2` (Custom Model Manager, tự OCR toàn trang dưới watermark):

- năm lựa chọn OCR cho tài liệu scan, quản lý trên giao diện (OCR Engine Manager);
- đưa model Tesseract do đơn vị tự fine-tune vào hệ thống, quản lý nhiều phiên bản, thay và rollback không cần build
  lại image hay restart (Custom Tesseract Model Manager);
- chuẩn bị online, vận hành offline có kiểm chứng;
- tùy chọn tự OCR toàn trang cho PDF scan bị watermark chéo làm mất nội dung;
- các bản vá bảo mật, cô lập cơ sở dữ liệu của bộ test và tài liệu vận hành.

**Không có tính năng mới so với rc.2.** Không fine-tune model, không đổi thuật toán OCR hay pipeline xử lý tài liệu.

## 2. Cải tiến so với v1.0.8

| Lĩnh vực | v1.0.8 | v1.2.0 |
|---|---|---|
| OCR tài liệu scan | một engine (RapidOCR, cấu hình cố định) | năm lựa chọn, chọn trên giao diện (mục 3); RapidOCR vẫn mặc định |
| Tiếng Việt trên trang scan | RapidOCR thường mất dấu | Tesseract Vietnamese Best (`vie` + `eng`, tessdata_best) khuyến nghị cho tiếng Việt |
| Trang scan xoay ngang / lộn ngược | không xử lý | tự dò và xoay lại trước khi OCR (khi đã cài Tesseract), có giới hạn thời gian |
| Model tự fine-tune | không hỗ trợ | Custom Model Manager: import bằng CLI, nhiều phiên bản, checksum, rollback (mục 4) |
| Vận hành offline | không kiểm chứng | "Chuẩn bị" khi có Internet, rồi chạy lại toàn pipeline với mạng bị chặn; chỉ khi đó mới báo `offline_ready` |
| Model và cache | có thể tải lại sau khi tạo lại container | nằm trên volume dữ liệu, kiểm SHA-256, giữ qua restart / tạo lại container / nâng cấp |
| PDF scan dưới watermark chéo | Docling có thể bỏ gần hết chữ OCR | tùy chọn tự OCR toàn trang cho riêng tài liệu đó (mặc định tắt, mục 7) |
| Thêm nguồn từ URL | bật | **tắt mặc định** (giảm rủi ro SSRF) |
| Phân quyền backend | một số thao tác quản trị mở cho mọi tài khoản | credential, model, transformation, embedding, quản lý OCR: chỉ quản trị viên |
| Bộ test | có thể chạm vào cơ sở dữ liệu cấu hình trong `.env` | cô lập fail-closed khỏi mọi cơ sở dữ liệu thật (`tests/README.md`) |
| Phát hành | publish Release khởi chạy build / push image | publish Release **không** build / push image (mục 12) |

Chi tiết từng bước: [OCR_RELEASE_NOTES.md](OCR_RELEASE_NOTES.md) (rc.1), [OCR_RELEASE_NOTES_RC2.md](OCR_RELEASE_NOTES_RC2.md)
(rc.2), [CHANGELOG](../../CHANGELOG.md).

## 3. Năm lựa chọn OCR

Quản lý trong *Cài đặt → OCR Engine Manager* (chỉ quản trị viên): cài, chuẩn bị, kiểm tra, chọn và gỡ. Mỗi card hiển
thị riêng *Sẵn sàng*, *Đã xác minh offline* và *Chất lượng*. Tất cả chạy CPU; Layout Heron và TableFormer Accurate dùng
chung cho mọi lựa chọn.

| Lựa chọn | Phân loại | Ghi chú |
|---|---|---|
| RapidOCR – PaddleOCR | **Mặc định** của bản phân phối, tương thích ngược | model và cấu hình như v1.0.8 |
| Tesseract Vietnamese Best | Khuyến nghị cho tiếng Việt | `vie` + `eng` (tessdata_best) |
| Tesseract Vietnamese Fast | Ưu tiên tốc độ | chưa đạt chuẩn nghiệp vụ |
| EasyOCR Vietnamese | Thử nghiệm | hỏi xác nhận trước khi bật |
| Tesseract Vietnamese Agri | **Thử nghiệm** | dùng model do đơn vị tự fine-tune; bản phát hành **không** kèm model (mục 4) |

Nâng cấp không bao giờ tự đổi engine đang chọn; Agri không bao giờ được chọn tự động. Hướng dẫn: [OCR_ENGINE_MANAGER.md](OCR_ENGINE_MANAGER.md),
[OCR_OPERATOR_GUIDE.md](OCR_OPERATOR_GUIDE.md).

## 4. Custom Tesseract Model Manager

- **Bản phát hành không kèm model Agri tự fine-tune.** Repository, source archive và mọi image dựng từ chúng đều
  không chứa model, dữ liệu huấn luyện hay tài liệu nội bộ. Card Agri ở trạng thái "Chưa cài đặt" cho tới khi quản trị
  viên import và kích hoạt một phiên bản.
- Model chỉ vào hệ thống bằng **CLI trên máy chủ**. Không có upload model qua trình duyệt / HTTP; không bao giờ tải
  model tùy biến từ Internet.
- Mỗi lần import là một **phiên bản bất biến** có manifest, kích thước và SHA-256. File được kiểm tra cấu trúc
  `traineddata`, kiểm tra tham số nhúng (mục 12), nạp thử bằng Tesseract và chạy thử toàn pipeline trước khi được coi
  là dùng được. Mỗi tài liệu được xử lý với file đã đối chiếu SHA-256 với manifest.
- Lệnh: `import` · `list` · `verify` · `activate` · `rollback` · `status` · `remove`. Kích hoạt, rollback và kiểm tra
  cũng có trên card Agri (chỉ quản trị viên).
- Kết quả "Sẵn sàng offline" gắn với từng phiên bản (mã phiên bản + SHA-256), không dùng chung giữa các phiên bản.

Thiết kế: [OCR_CUSTOM_MODEL_MANAGER.md](OCR_CUSTOM_MODEL_MANAGER.md).

## 5. Import model Agri

Tóm tắt; đầy đủ ở [OCR_AGRI_MODEL_GUIDE.md](OCR_AGRI_MODEL_GUIDE.md).

```bash
ocr() { docker compose exec open_notebook /app/.venv/bin/python -m open_notebook.ocr.cli "$@"; }
sha256sum /duong/dan/vie_agri.traineddata        # so với SHA-256 ghi tại máy fine-tune
ocr custom import --file /import/vie_agri.traineddata --version v1 --notes "Agri fine-tune lan 1"
ocr custom activate --version v1
ocr custom status                                # ready · active version v1
ocr readiness --engines tesseract_agri --check   # offline_ready
```

- Dòng `stored … sha256 …` của lệnh import phải trùng SHA-256 vừa tính. File hỏng hoặc Tesseract không đọc được ⇒
  `ERROR`, không có gì thay đổi.
- Import và kích hoạt **không** đổi engine đang chọn; chọn Agri làm engine xử lý là thao tác riêng (nút **Sử dụng**).
- Lưu model, bản sao lưu model và mã băm của chúng ở nơi có kiểm soát truy cập; **không** đưa vào repository, issue,
  Pull Request hay log công khai.

## 6. Thay model không cần restart

```bash
ocr custom import --file /import/vie_agri.traineddata --version v2 --notes "Agri fine-tune lan 2"
ocr custom activate --version v2    # hoặc card Agri → "Chuyển sang phiên bản này"
ocr custom rollback                 # quay về phiên bản trước nếu cần
```

- Không sửa mã, không build image, không restart. Có hiệu lực cho **tài liệu kế tiếp**; tài liệu đang xử lý giữ phiên
  bản lúc bắt đầu.
- Model nằm trên volume dữ liệu nên giữ được qua restart, tạo lại container và nâng cấp image.
- `ocr custom verify` băm lại từng phiên bản; `file=CHANGED` / `corrupted` ⇒ engine chuyển sang Lỗi và từ chối xử lý
  (không tự đổi engine).

## 7. Tự OCR toàn trang cho PDF scan dưới watermark (Auto Full Page on Watermark)

- Biến `OCR_AUTO_FULL_PAGE_ON_WATERMARK` — **mặc định TẮT** trong bản phân phối; chỉ bật khi giá trị là `true` / `1` /
  `yes` / `on`.
- Khi bật: một PDF scan có một dòng text hiển thị bị nghiêng phủ lên trang — cấu trúc khiến Docling bỏ gần hết chữ OCR —
  được OCR ở chế độ toàn trang chính thức của Docling, **cho riêng tài liệu đó**, với mọi engine. Không sửa PDF, không ghi
  đè Force Full Page đã lưu, không tự bật OCR khi OCR đang tắt.
- Chỉ đọc hình học và số đếm của PDF (không đọc nội dung chữ, không so khớp chuỗi watermark); mỗi PDF một dòng log
  `OCR mode:` chỉ gồm số đo, không có tên tệp hay nội dung.
- PDF hỗn hợp (trang scan dưới watermark + trang văn bản điện tử) **không** được sửa tự động: giữ chế độ đã cấu hình và
  ghi `WARNING`.
- Bật / tắt: thêm hoặc xóa `OCR_AUTO_FULL_PAGE_ON_WATERMARK=true` trong `environment` của dịch vụ `open_notebook`, rồi
  tạo lại riêng container ứng dụng. Ngưỡng tinh chỉnh: [OCR_CONFIGURATION.md](OCR_CONFIGURATION.md); vận hành:
  [OCR_OPERATOR_GUIDE.md](OCR_OPERATOR_GUIDE.md); phân tích: [OCR_PHASE10G_REPORT.md](OCR_PHASE10G_REPORT.md).

Nơi triển khai đã bật cờ này ở rc.2 thì giữ nguyên khi lên v1.2.0 (cấu hình không đổi).

## 8. Hướng dẫn nâng cấp

**Từ v1.1.0-rc.2:** chỉ đổi số phiên bản. Không có việc bắt buộc nào ngoài quy trình chuẩn:

1. Gắn tag rollback cho **đúng image ID đang chạy**; sao lưu lạnh và kiểm tra restore
   ([OCR_V120_ROLLBACK_GUIDE.md](OCR_V120_ROLLBACK_GUIDE.md) mục C.2).
2. Dựng image từ tag `v1.2.0` ở thư mục riêng, tag riêng; kiểm `VERSION` = `1.2.0`.
3. Cập nhật mã ở thư mục triển khai bằng `git merge --ff-only v1.2.0` (giữ sửa đổi cục bộ bằng `git stash` /
   `git stash pop`); không `git reset --hard`, không `git pull` mù.
4. Chỉ tạo lại container ứng dụng: `docker compose up -d --no-deps --no-build open_notebook` (hoặc script khởi động
   của nơi triển khai). **Không** tạo lại container cơ sở dữ liệu.
5. Kiểm tra: `/health`; đăng nhập; giao diện hiển thị `1.2.0`; số bản ghi không đổi; engine đang chọn, phiên bản model
   Agri và cờ Auto Full Page như trước; RapidOCR **Chuẩn bị** một lần (container vừa được tạo lại).

Không có migration; không OCR lại tài liệu cũ; không dựng lại embedding; không đổi `.env` hay file override.

**Từ v1.1.0-rc.1:** như trên, cộng các thay đổi hành vi của rc.2 ([OCR_RELEASE_NOTES_RC2.md](OCR_RELEASE_NOTES_RC2.md)
mục 4) và kế hoạch [OCR_RC2_PRODUCTION_UPDATE_PLAN.md](OCR_RC2_PRODUCTION_UPDATE_PLAN.md).

**Từ v1.0.8 hoặc cũ hơn:** đọc lần lượt mục "Thay đổi hành vi khi nâng cấp" của rc.1 ([OCR_RELEASE_NOTES.md](OCR_RELEASE_NOTES.md)
mục 4) và rc.2; quy trình chung ở [OCR_PRODUCTION_DEPLOYMENT_PLAN.md](OCR_PRODUCTION_DEPLOYMENT_PLAN.md). Lưu ý riêng:
thêm nguồn từ URL bị tắt mặc định và một số thao tác chuyển sang chỉ quản trị viên.

Cài đặt mới: [README](../../README.md) (Quick Start) → [OCR_ONLINE_PREPARATION.md](OCR_ONLINE_PREPARATION.md).

## 9. Hướng dẫn rollback

Đầy đủ: [OCR_V120_ROLLBACK_GUIDE.md](OCR_V120_ROLLBACK_GUIDE.md). Từ nhẹ tới nặng, không mức nào đụng tới dữ liệu:

| Mức | Cách làm |
|---|---|
| Tắt Auto Full Page | xóa `OCR_AUTO_FULL_PAGE_ON_WATERMARK=true`, tạo lại riêng container ứng dụng |
| A. Model | `ocr custom rollback` hoặc nút **Rollback về …** trên card Agri |
| B. Engine | **Sử dụng** trên Tesseract Vietnamese Best hoặc RapidOCR |
| C. Ứng dụng | về `v1.1.0-rc.2` bằng image rollback đã gắn tag; schema, dữ liệu, model Agri, engine đang chọn và cấu hình giữ nguyên; **không** cần khôi phục cơ sở dữ liệu |
| D. GitHub Release | không xóa / di chuyển tag; ghi cảnh báo vào Release; có thể đánh dấu lại bản cũ là Latest; phát hành `v1.2.1` |

## 10. Kết quả kiểm thử

Chạy trên commit phát hành, trong môi trường phát triển (không có kết nối tới cơ sở dữ liệu nào ngoài cơ chế cô lập
của bộ test; frontend chạy trong container không có mạng). So với lượt chạy trên `v1.1.0-rc.2` (Phase 10I):

| Bộ kiểm | Baseline rc.2 | v1.2.0 | Nhận xét |
|---|---|---|---|
| `pytest tests/` (backend, toàn bộ) | 1.792 đạt · 10 lỗi · 64 bỏ qua | **1.792 đạt · 10 lỗi · 64 bỏ qua** | 10 lỗi là đúng 10 lỗi **có sẵn** (`test_domain` ×1, `test_models_api` ×9 — test cũ không còn khớp mã hiện tại: giá trị mặc định, chữ ký hàm mock); không có lỗi mới |
| Test OCR (`-k ocr`) | 640 đạt | **640 đạt** · 64 bỏ qua | gồm Custom Model Manager và Auto Full Page |
| Custom Model Manager + Auto Full Page + cô lập DB (4 tệp) | — | **360 đạt** · 17 bỏ qua | |
| Cô lập cơ sở dữ liệu của bộ test (`-k isolation`) | — | **60 đạt** | |
| Frontend `vitest` | 423 đạt | **423 đạt** (63 tệp) | gồm test hiển thị phiên bản và kiểm tra cập nhật |
| TypeScript `tsc --noEmit` | 0 lỗi | **0 lỗi** | |
| ESLint | 0 lỗi · 7 cảnh báo | **0 lỗi · 7 cảnh báo** | cảnh báo có sẵn |
| `ruff check .` | 2 lỗi có sẵn trong `tests/` | **2 lỗi** — giống hệt | ngoài phạm vi bản phát hành |
| Liên kết Markdown tương đối (`scripts/check_md_links.py`) | đạt | **đạt** | |
| Khối lệnh `bash` trong `docs/ocr` (`check_doc_commands.py`) | đạt | **đạt** | |

So sánh mã nguồn `v1.1.0-rc.2..v1.2.0`:

| Loại thay đổi | Tệp |
|---|---|
| Số phiên bản | `VERSION`, `frontend/package.json`, `frontend/package-lock.json` (2 dòng `version`) |
| Tài liệu | `README.md`, `CHANGELOG.md`, `docs/ocr/*.md` |
| Test | không có |
| Mã chạy (runtime) | **không có** — số hiển thị trên giao diện và trường `version` của API đọc từ `frontend/package.json` |

Vì mã chạy không đổi, các kết quả nghiệm thu chức năng của rc.2 (Docker acceptance 53 PASS / 0 FAIL, thay model /
rollback / nâng cấp / hạ cấp trên stack thử nghiệm, tài liệu scan dưới watermark) áp dụng nguyên cho bản này —
[OCR_RELEASE_NOTES_RC2.md](OCR_RELEASE_NOTES_RC2.md) mục 8, [OCR_PHASE10H_REPORT.md](OCR_PHASE10H_REPORT.md).

## 11. Giới hạn còn tồn tại

- **Tesseract Vietnamese Agri là Thử nghiệm.** Trên văn bản pháp lý tổng hợp, chất lượng tổng thể tương đương
  Tesseract Vietnamese Best; Agri đọc một số trường tốt hơn và một số trường kém hơn (ví dụ giá trị phần trăm) —
  [OCR_AGRI_BENCHMARK.md](OCR_AGRI_BENCHMARK.md). **Không** có cơ sở để nói Agri tốt hơn Best trên mọi tài liệu.
  Chất lượng phụ thuộc phiên bản model được import.
- Chất lượng OCR **chưa** được thẩm định bằng benchmark trên tài liệu nghiệp vụ thật; có thể sai dấu, sai chữ số,
  sai cấu trúc bảng. **OCR không thay thế việc đối chiếu tài liệu gốc** — lãi suất, tỷ lệ, số tiền phải đối chiếu.
- Auto Full Page **mặc định tắt**; không phát hiện watermark ngang cỡ lớn, khung bao nghiêng dưới 2% trang, watermark
  ghi mỗi ký tự một đối tượng; PDF hỗn hợp không được sửa tự động; ngưỡng mới hiệu chuẩn trên PDF tổng hợp và một tài
  liệu thật ([OCR_PHASE10G_REPORT.md](OCR_PHASE10G_REPORT.md) mục 13).
- Model fine-tune mang tham số nhúng ngoài danh sách cho phép bị từ chối import cho tới khi tham số đó được xem xét.
- EasyOCR là Thử nghiệm. Vận hành offline được xác minh trên stack cô lập.
- Thêm nguồn từ URL tắt mặc định; bật lại thì rủi ro SSRF còn lại của bộ tải HTTP xuất hiện trở lại.
- 10 test backend và 2 lỗi `ruff` có sẵn (mục 10) chưa được xử lý.

## 12. Cảnh báo bảo mật và bảo vệ dữ liệu

**Giới hạn bảo mật còn tồn tại** — bản này **không** phải là xác nhận an toàn cho nghiệp vụ:

- CORS mở cho mọi nguồn và xác thực bằng mật khẩu đơn giản là mặc định cho phát triển. Không đặt hệ thống ra Internet
  công khai; chỉ cho truy cập qua mạng nội bộ / VPN có kiểm soát; đổi mọi mật khẩu mặc định trước khi có người dùng thật.
- Container ứng dụng chạy bằng `root`; các route podcast mở cho mọi tài khoản đã đăng nhập.
- Credential nhà cung cấp AI được mã hóa khi lưu và cần `OPEN_NOTEBOOK_ENCRYPTION_KEY`; mất khóa thì không giải mã được.
  Không đưa khóa, `.env` hay bản sao lưu vào Git.
- Nội dung tài liệu được gửi tới nhà cung cấp LLM / embedding đã cấu hình; chọn nhà cung cấp phù hợp với chính sách dữ
  liệu của đơn vị.

**Biện pháp đã có trong bản này:**

- Quản lý OCR và model chỉ dành cho quản trị viên (tài khoản thường 403, không token 401).
- File model không thể tự đặt tham số nguy hiểm cho Tesseract: thành phần `config` nhúng chỉ được chứa tham số tinh
  chỉnh nhận dạng trong danh sách cho phép, giá trị số / boolean; kiểm tra trước khi Tesseract nạp file và ở mọi lần
  xác minh. Kho model từ chối liên kết tượng trưng; manifest / registry hỏng được xử lý theo hướng đóng.
- Bộ test cô lập fail-closed khỏi mọi cơ sở dữ liệu thật.
- Workflow *Build and Release*: publish một Release **không** build hay push Docker image; mọi job bị bỏ qua trừ khi
  workflow được chạy tay **và** biến repository `CB5400_PUBLISH_IMAGES` bằng `true` (không được đặt). Tên image trong
  workflow vẫn là của dự án gốc và phải được đổi trước khi bật biến.

**Bảo vệ dữ liệu khi dùng repository công khai:** không đưa lên GitHub (commit, issue, Pull Request, Release, log) model
tự fine-tune, file `traineddata` nội bộ hay mã băm của chúng, dữ liệu huấn luyện, PDF nội bộ, nội dung OCR, watermark
nội bộ, credential, `.env`, cơ sở dữ liệu, bản sao lưu, địa chỉ IP nội bộ, đường dẫn triển khai thật hay báo cáo vận
hành. Đường dẫn `/srv/example/…` và `/duong/dan/…` trong tài liệu là **minh họa**. Tệp `tests/fixtures/ocr/` là tài liệu
tổng hợp.

Lịch sử commit của bản này được quét trước khi công bố (nội dung diff, thông điệp commit, mô tả Pull Request, ghi chú
phát hành): không có model, dữ liệu nội bộ, credential hay đường dẫn triển khai thật.
