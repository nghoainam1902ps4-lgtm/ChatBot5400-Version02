# Hướng dẫn vận hành OCR Engine Manager — ChatBot5400

Cập nhật: 2026-11-14 (Phase 9B/9C) · Dành cho người vận hành máy chủ và quản trị viên ứng dụng.

Tài liệu này công khai: không chứa mật khẩu, khóa, đường dẫn bản sao lưu thật. Chi tiết kỹ thuật nằm ở các
tài liệu được dẫn; ở đây là việc cần làm, theo từng tình huống.

Quy ước lệnh — chạy trên máy chủ, trong thư mục production:

```bash
cd /srv/example/chatbot5400
ocr() { docker compose exec open_notebook /app/.venv/bin/python -m open_notebook.ocr.cli "$@"; }
```

**Ba điều không bao giờ làm:** `docker compose down -v` · `docker system prune` · `docker compose up -d` không
kèm tên service (sẽ kéo bản SurrealDB mới và tạo lại container DB — luôn dùng
`docker compose up -d --no-deps open_notebook`).

## 1. Bốn lựa chọn OCR

| Lựa chọn | Dùng khi | Lưu ý |
|---|---|---|
| **Tesseract Vietnamese Best** | Văn bản và bảng scan tiếng Việt — **khuyến nghị** | Một số tiêu đề in đậm chữ hoa có thể mất dấu (đã chấp nhận). Số tiền, ngày, số hiệu đạt trên bộ kiểm thử tổng hợp |
| Tesseract Vietnamese Fast | Cần tốc độ | **Chưa đạt** chuẩn nghiệp vụ: có thể sai dấu ở nhãn dòng bảng |
| RapidOCR – PaddleOCR | Mặc định, tương thích ngược | Mất dấu tiếng Việt trên trang scan; không dùng để đối chiếu nhãn bảng tiếng Việt |
| EasyOCR Vietnamese | Chỉ để thử nghiệm | Không dùng cho tài liệu tài chính. Không cài trên production nếu không có yêu cầu |

Engine mặc định trong mã nguồn là RapidOCR và không tự đổi. Không có chuyển engine tự động.

**Lựa chọn thứ năm (Phase 10, chưa triển khai production): Tesseract Vietnamese Agri** — model Tesseract tự
fine-tune cho văn bản pháp lý, xếp loại **Thử nghiệm**, quản lý theo phiên bản và import bằng CLI. Bốn lựa chọn
trên không thay đổi. Thao tác: [OCR_AGRI_MODEL_GUIDE.md](OCR_AGRI_MODEL_GUIDE.md); thiết kế:
[OCR_CUSTOM_MODEL_MANAGER.md](OCR_CUSTOM_MODEL_MANAGER.md); kết quả đo: [OCR_AGRI_BENCHMARK.md](OCR_AGRI_BENCHMARK.md).

**Trạng thái trên production (2026-11-14, thí điểm phi nghiệp vụ):** engine được chọn là **RapidOCR**. Tesseract
Vietnamese Best đã cài, đã "Chuẩn bị" và đã thử bằng tài liệu tổng hợp, nhưng **chưa được phép dùng cho tài liệu
nghiệp vụ thật** cho tới khi chủ dự án hoàn thành benchmark cục bộ (mục 2) và quyết định kích hoạt.

## 2. Cảnh báo về số liệu tài chính

- OCR là nhận dạng tự động, **không** phải bản sao có giá trị pháp lý. Số tiền, ngày, số hiệu, số tài khoản lấy
  từ tài liệu scan **phải được đối chiếu với bản gốc** trước khi dùng cho nghiệp vụ.
- Kết quả nghiệm thu đến nay đo trên tài liệu **tổng hợp**. Chất lượng trên tài liệu thật của đơn vị chỉ được
  biết sau benchmark tại chỗ ([OCR_REAL_DOCUMENT_BENCHMARK.md](OCR_REAL_DOCUMENT_BENCHMARK.md)).
- Bản scan mờ, nghiêng, fax, độ phân giải dưới 150 DPI cho kết quả kém hơn. Nên scan 200–300 DPI.
- Nếu log ghi `conversion_status=partial_success`, một phần tài liệu có thể thiếu trong kết quả: xử lý lại
  hoặc kiểm tra bản gốc.
- Trang nằm ngang / lộn ngược chỉ được tự sửa khi dòng "Tự sửa hướng trang scan" báo **Khả dụng**; với tài liệu
  rất dài, các trang vượt giới hạn (200 trang scan hoặc 10 phút dò hướng) được giữ nguyên hướng — log ghi
  `page_orientation_limit`.

## 3. Cài một engine

Vào **Cài đặt → OCR Engine Manager** (chỉ quản trị viên).

| Engine | Runtime | Model | Thao tác |
|---|---|---|---|
| Tesseract Best / Fast | binary `tesseract` — đã nướng trong image (`OCR_INSTALL_TESSERACT=true` trong `.env`) | `vie`, `eng`, `osd` (tải từ GitHub chính thức, kiểm SHA-256) | bấm **Cài đặt**, chờ "Sẵn sàng" |
| RapidOCR | đi cùng Docling | tự tải ở bước "Chuẩn bị" | không cần cài |
| EasyOCR | cần `OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR=true` và tạo lại container | 2 file `.pth` | chỉ khi được yêu cầu |

CLI tương đương: `ocr install-model tesseract_best` rồi `ocr status --no-db`.

Model nằm ở `./notebook_data/ocr/models` trên máy chủ (trong container: `/app/data/ocr/models`); cache Layout
Heron / TableFormer ở `./notebook_data/.cache/huggingface`. Cả hai nằm trên thư mục dữ liệu nên còn nguyên sau
restart, tạo lại container và cập nhật.

## 4. Chuẩn bị (Prepare) và chọn engine

1. Máy chủ **có Internet**.
2. Bấm **Chuẩn bị** ở engine cần dùng → chờ trạng thái `offline_ready`. Bước này tải phần còn thiếu, chạy thử
   toàn bộ pipeline, rồi chạy lại với mạng bị chặn để chắc mọi thứ đã nằm trên máy. Trong lúc chạy (vài phút)
   worker bận, tài liệu mới phải chờ.
3. Bấm **Kiểm tra** → thành công; với Tesseract, model thực tế là `TesseractOcrCliModel`.
4. Bấm **Sử dụng** để engine thành engine đang dùng. Có hiệu lực từ tài liệu kế tiếp, không cần restart.

CLI: `ocr prepare --engines tesseract_best` · `ocr readiness --engines tesseract_best --json`.

**Khi nào phải Chuẩn bị lại** (trạng thái tự chuyển về "chưa kiểm tra", việc xử lý tài liệu không bị chặn):

- sau khi cập nhật phiên bản ứng dụng (phiên bản Docling / torch / Tesseract đổi);
- sau khi cài hoặc gỡ model, hoặc cache Hugging Face bị dọn;
- sau khi container ứng dụng được **tạo lại** nếu đang dùng RapidOCR (trọng số và file từ điển của RapidOCR nằm
  trong container; kể cả khi bật `OCR_RAPIDOCR_PERSISTENT=true` vẫn cần một lần Chuẩn bị — xem `DECISIONS.md` D-32);
- sau khi đổi một biến cấu hình chất lượng (`OCR_PDF_PREP`, `OCR_TESSERACT_OSD_GATE`, các ngưỡng).

**Khi nào phải cài lại runtime:** container ứng dụng được tạo lại từ một image **không** có Tesseract (dựng
thiếu `OCR_INSTALL_TESSERACT=true`). Dấu hiệu: engine Tesseract báo "thiếu runtime". Cách sửa: dựng lại image
đúng build arg (mục 7), không cài tay trong container.

## 5. Vận hành khi không có Internet

Chỉ **xử lý tài liệu** (OCR, Layout, TableFormer, xuất Markdown) được bảo đảm chạy offline. Chat, hỏi đáp,
embedding phụ thuộc nhà cung cấp mô hình đang cấu hình. Cập nhật, cài đặt, Chuẩn bị luôn cần Internet.

1. Khi còn Internet: engine đang dùng phải ở `offline_ready`.
2. Ngắt Internet ở tầng mạng theo quy trình của đơn vị (không sửa image hay compose). Ứng dụng vẫn phải tới
   được SurrealDB và người dùng nội bộ.
3. Bấm **Kiểm tra offline** (hoặc `ocr readiness --check`) → `offline_verified`.
4. Restart container khi offline: an toàn (`docker compose restart open_notebook`).
5. **Tạo lại** container khi offline: chỉ làm khi đã đặt `OCR_OFFLINE=true` và `HF_HUB_OFFLINE=1` từ trước, và
   engine đang dùng không phải RapidOCR. Nếu không chắc, đừng tạo lại container khi không có Internet.
6. Nếu một tài liệu báo "OCR/Docling model … is not available locally": nối Internet, Chuẩn bị lại, xử lý lại
   nguồn. Hệ thống không tự chuyển engine và không treo chờ tải.

Trạng thái kiểm chứng: xem `OCR_FINAL_ACCEPTANCE.md` — offline đã kiểm trên stack cô lập; kiểm trên production
chỉ được ghi là đạt sau khi thực hiện theo quy trình mạng được phê duyệt.

## 6. Kiểm tra nhanh tình trạng hệ thống

```bash
cd /srv/example/chatbot5400
bash scripts/ocr/production_health_check.sh           # container, restart, /health, RAM, đĩa, số dòng lỗi
docker compose ps
docker compose logs --tail 100 open_notebook | grep -E "Docling OCR finished|WARNING|ERROR" | tail -20
du -sh notebook_data/ocr notebook_data/.cache/huggingface 2>/dev/null   # model cache (cần quyền đọc)
```

Dòng log `Docling OCR finished: engine=… actual_models=[…] in …s (… page_orientation=…, …)` cho biết engine
thực tế, thời gian, số trang được sửa hướng và trạng thái chuyển đổi của từng tài liệu.

Trong 24 giờ đầu sau một lần cập nhật: chạy script trên vài lần; `RestartCount` phải là 0, `/health` 200, RAM
khả dụng không cạn (pipeline dùng 3–6 GB khi OCR), không có lỗi lặp lại.

## 7. Cập nhật phiên bản (khi có Internet)

Làm theo [OCR_PRODUCTION_DEPLOYMENT_PLAN.md](OCR_PRODUCTION_DEPLOYMENT_PLAN.md) mục 3–7. Tóm tắt:

1. Dựng image mới ở thư mục riêng, tag riêng — chưa dừng dịch vụ.
2. Gắn tag rollback cho image đang chạy; `docker compose stop`; sao lưu lạnh `notebook_data` và
   `surreal_data`; kiểm tra restore trên stack cô lập.
3. Cập nhật mã bằng `git merge --ff-only <commit>` (giữ thay đổi cục bộ bằng `git stash` / `git stash pop`);
   không `git reset --hard`.
4. `docker compose start surrealdb` rồi `docker compose up -d --no-deps --no-build open_notebook`.
5. Mở OCR Engine Manager: không có cảnh báo phiên bản; **Chuẩn bị** lại engine đang dùng; chạy smoke test.

## 8. Bảo toàn dữ liệu

| Dữ liệu | Ở đâu | Sao lưu |
|---|---|---|
| Cơ sở dữ liệu (notebook, nguồn, ghi chú, người dùng, cấu hình, credential đã mã hóa) | `./surreal_data` | sao lưu **lạnh** (dừng container trước) |
| File tải lên, lịch sử chat (checkpoint), podcast, model OCR, cache | `./notebook_data` | cùng lúc với DB |
| Khóa mã hóa và cấu hình | `.env`, `docker-compose.yml`, `docker-compose.override.yml` | bản sao quyền `600`, không rời máy chủ, không commit |

Mất khóa mã hóa = không giải mã được credential nhà cung cấp đã lưu. Bản sao lưu chỉ có giá trị khi đã thử
restore (kế hoạch mục 5). Không đưa bản sao lưu lên GitHub hay dịch vụ bên ngoài.

## 9. Khi nào rollback và rollback thế nào

| Tình huống | Hành động |
|---|---|
| Chỉ kết quả OCR của Tesseract có vấn đề | OCR Engine Manager → **Sử dụng** RapidOCR. Không cần đổi mã |
| Một cải tiến chất lượng gây lỗi | đặt `OCR_PDF_PREP=false` hoặc `OCR_TESSERACT_OSD_GATE=false`, tạo lại container ứng dụng |
| Ứng dụng không lên, đăng nhập lỗi, thiếu dữ liệu, URL vẫn thêm được | rollback mã về bản trước — kế hoạch mục 10 |
| Dữ liệu hỏng | rollback dữ liệu từ bản sao lưu — **chỉ khi chủ dự án quyết định**; thay đổi sau thời điểm sao lưu sẽ mất |

Rollback mã về bản trước tính năng OCR làm chức năng thêm nguồn từ URL hoạt động trở lại và làm mất các bản vá
phân quyền (D-31): áp biện pháp đã được phê duyệt trong kế hoạch mục 10.

## 10. Cấu hình cần nhớ

| Biến | Giá trị trên production | Ý nghĩa |
|---|---|---|
| `OPEN_NOTEBOOK_ENABLE_URL_INGESTION` | `false` | **Giữ tắt.** Thêm nguồn từ URL bị từ chối cho mọi vai trò. Đây là giảm thiểu rủi ro SSRF bằng cách gỡ chức năng, không phải sửa bộ tải. Bật lại cần phê duyệt |
| `OPEN_NOTEBOOK_ENABLE_DOCLING` | `true` | Docling (OCR, Layout Heron, TableFormer) |
| `OCR_INSTALL_TESSERACT` (trong `.env`) | `true` | Image dựng lại luôn có Tesseract |
| `UV_TORCH_BACKEND` | `cpu` | torch bản CPU |
| `OPEN_NOTEBOOK_WORKER_MAX_TASKS` | `1` | mỗi lúc một job nền |
| `OPEN_NOTEBOOK_ENABLE_OCR_TESSERACT` | `true` | khôi phục runtime Tesseract khi container được tạo lại (binary đã có sẵn trong image) |
| `OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR` | không đặt | EasyOCR không cài |
| `OCR_RAPIDOCR_PERSISTENT` | không đặt | xem D-32 |
| `OCR_OFFLINE`, `HF_HUB_OFFLINE` | không đặt | chỉ đặt khi vận hành ngắt mạng, **sau khi** đã `offline_ready` |
| `OCR_AUTO_FULL_PAGE_ON_WATERMARK` | **không đặt** (tắt) | Phase 10G: tự OCR toàn trang cho PDF scan nằm dưới watermark chéo. Mặc định tắt trong bản phát hành; bật trên production cần phê duyệt của chủ dự án (xem Phụ lục Phase 10G) |

Đầy đủ: [OCR_CONFIGURATION.md](OCR_CONFIGURATION.md). Quyền: mọi thao tác trong OCR Engine Manager, quản lý
model / credential nhà cung cấp, transformation và dựng lại embedding chỉ dành cho **quản trị viên** (D-31).

## 11. Chế độ bảo trì và mở lại hệ thống

Chế độ bảo trì = ứng dụng vẫn chạy nhưng cổng web (8502) và API (5055) chỉ nghe trên `127.0.0.1` của máy chủ:
người dùng trong mạng không truy cập được, người quản trị vẫn làm việc được trên máy chủ hoặc qua SSH tunnel. Dùng
khi cập nhật, khi cần kiểm tra bảo mật trước khi mở lại, và **bắt buộc** nếu phải chạy lại bản cũ (bản trước tính
năng OCR có lỗi phân quyền đã biết, không được mở cho người dùng).

File override bảo trì (đặt ngoài thư mục production, không sửa file compose nào):

```yaml
services:
  open_notebook:
    ports: !override
      - "127.0.0.1:8502:8502"
      - "127.0.0.1:5055:5055"
```

```bash
cd /srv/example/chatbot5400
MAINT=/duong/dan/docker-compose.maintenance.yml
# vào chế độ bảo trì (tạo lại container ứng dụng; DB không đụng tới)
docker compose -p chatbot5400-version02 -f docker-compose.yml -f docker-compose.override.yml -f "$MAINT" \
    up -d --no-deps --no-build open_notebook
docker compose ps                         # cột PORTS phải là 127.0.0.1:…
# làm việc từ máy của quản trị viên qua SSH tunnel, rồi mở http://localhost:8502
#   ssh -L 8502:127.0.0.1:8502 -L 5055:127.0.0.1:5055 <tài khoản>@<máy chủ>
# mở lại cho người dùng
docker compose up -d --no-deps --no-build open_notebook
docker compose exec open_notebook /app/.venv/bin/python -m open_notebook.ocr.cli prepare --engines rapidocr
```

Trước khi mở lại, kiểm tra: các hạng mục bảo mật ở `OCR_PRODUCTION_DEPLOYMENT_PLAN.md` §13 đã đạt; `/health` 200;
OCR Engine Manager không có cảnh báo. Mỗi lần container ứng dụng được tạo lại (vào / ra chế độ bảo trì, cập nhật), RapidOCR cần
"Chuẩn bị" lại một lần khi có Internet; Tesseract không bị ảnh hưởng.

Phiên đăng nhập: token có hiệu lực tối đa 12 giờ và không thu hồi được riêng lẻ; đổi mật khẩu không vô hiệu token đã
cấp. Muốn buộc mọi người đăng nhập lại, đặt một giá trị riêng cho `OPEN_NOTEBOOK_JWT_SECRET` rồi tạo lại container
ứng dụng (quyết định của chủ dự án).

## 12. Tài liệu liên quan

[OCR_ENGINE_MANAGER.md](OCR_ENGINE_MANAGER.md) · [OCR_ONLINE_PREPARATION.md](OCR_ONLINE_PREPARATION.md) ·
[OCR_ROLLBACK.md](OCR_ROLLBACK.md) · [OCR_PRODUCTION_CHECKLIST.md](OCR_PRODUCTION_CHECKLIST.md) ·
[OCR_FINAL_ACCEPTANCE.md](OCR_FINAL_ACCEPTANCE.md) · [OCR_PHASE9C_REPORT.md](OCR_PHASE9C_REPORT.md) ·
[`docs/security/BACKGROUND_JOB_SECURITY.md`](../security/BACKGROUND_JOB_SECURITY.md)

## Phụ lục Phase 10 — Model custom Tesseract Vietnamese Agri

Tóm tắt cho người vận hành (chi tiết ở [OCR_AGRI_MODEL_GUIDE.md](OCR_AGRI_MODEL_GUIDE.md)):

| Việc | Lệnh / thao tác |
|---|---|
| Import model lần đầu hoặc bản fine-tune mới | `ocr custom import --file /import/vie_agri.traineddata --version v2` — không kích hoạt, không cần build image |
| Xem các phiên bản | `ocr custom list` · `ocr custom status` · card Agri trong OCR Engine Manager |
| Kích hoạt phiên bản | `ocr custom activate --version v2` hoặc nút **Chuyển sang phiên bản này** |
| Rollback phiên bản model | `ocr custom rollback` hoặc nút **Rollback về …** |
| Kiểm tra toàn vẹn | `ocr custom verify` |
| Chọn / bỏ engine Agri | nút **Sử dụng** trên card Agri / trên card Tesseract Vietnamese Best |
| Sao lưu model + manifest | `tar` hai thư mục `ocr/models/tesseract/custom` và `ocr/manifests/custom` |

- Model custom **không bao giờ** được tải từ Internet và **không** upload qua trình duyệt: file chỉ vào hệ thống
  qua lệnh import chạy trên máy chủ.
- Tài liệu đang xử lý giữ nguyên phiên bản model lúc bắt đầu; chuyển phiên bản chỉ áp dụng cho tài liệu sau đó.
- Đổi phiên bản làm kết quả "Sẵn sàng offline" của phiên bản khác không còn được tính: chạy
  `ocr readiness --engines tesseract_agri --check`.
- **Trước khi hạ cấp** image về bản chưa có Agri (`v1.1.0-rc.1`), chọn lại Tesseract Vietnamese Best hoặc RapidOCR
  (xem [OCR_ROLLBACK.md](OCR_ROLLBACK.md), "Ghi chú Phase 10"); nếu quên, bản cũ âm thầm dùng RapidOCR.

## Phụ lục Phase 10G — PDF scan có watermark chéo

**Hiện tượng.** Một PDF scan sau khi xử lý chỉ còn tiêu đề, vài dòng, chuỗi watermark lặp lại và các chỗ giữ ảnh,
dù OCR đang bật. Xảy ra với **mọi** engine.

**Nguyên nhân.** Trang là ảnh scan, bên trên có một dòng watermark chéo dạng *text hiển thị*. Docling giữ dòng text
đó và bỏ mọi chữ OCR nằm trong khung bao của nó — với dòng chéo, khung bao là gần hết trang
([OCR_PHASE10G_REPORT.md](OCR_PHASE10G_REPORT.md), mục 2).

**Cơ chế tự động (opt-in).** Với `OCR_AUTO_FULL_PAGE_ON_WATERMARK=true`, trước khi OCR hệ thống đo hình học từng
trang (không đọc nội dung chữ) và dùng chế độ OCR toàn trang cho **riêng** tài liệu có nguy cơ.

| Điều người vận hành cần biết | |
|---|---|
| Mặc định | **Tắt.** Tắt ⇒ hành vi giống hệt các phiên bản trước |
| Tùy chọn Force Full Page đã lưu | Không bao giờ bị thay đổi; bật thủ công thì được giữ nguyên |
| OCR đang tắt | Cơ chế không làm gì, không tự bật OCR |
| PDF thường (scan không watermark, văn bản điện tử, header / footer, dấu nhỏ) | Không bị ảnh hưởng — kết quả giống hệt từng byte |
| PDF hỗn hợp (trang scan dưới watermark + trang văn bản điện tử) | **Không** được sửa tự động; log có `WARNING … reason=mixed_document`. Nếu các trang scan quan trọng hơn: bật Force Full Page OCR, xử lý lại nguồn đó, rồi tắt lại |
| Tài liệu đã xử lý trước khi bật | Không tự đổi; xử lý lại nguồn để có nội dung đầy đủ |

**Xem hệ thống đã quyết định gì** (dòng log chỉ có số đo, không có tên file hay nội dung):

```bash
docker compose logs --since 1h open_notebook | grep "OCR mode:"
```

| `reason=` | Ý nghĩa |
|---|---|
| `tilted_text_box_over_scan` | Đã tự OCR toàn trang cho tài liệu này |
| `no_risk` | Tài liệu thường, xử lý như trước |
| `mixed_document` | Tài liệu hỗn hợp, giữ chế độ đã cấu hình (kèm cảnh báo) |
| `manual_full_page` | Force Full Page đang bật thủ công |
| `check_failed` | Không đo được tệp; xử lý như trước |

**Bật / tắt** (không cần build lại image; chỉ tạo lại container ứng dụng). Biến chỉ có hiệu lực khi nó thực sự
được truyền vào container, tức là có trong mục `environment` của dịch vụ `open_notebook`:

- **Production** (`docker-compose.yml` + `docker-compose.override.yml`): thêm vào mục `environment` của
  `open_notebook` trong file **override** dòng `- OCR_AUTO_FULL_PAGE_ON_WATERMARK=true`; tắt = xoá dòng đó hoặc đổi
  thành `false`. Compose mẫu ở gốc kho mã và `deploy/docker-compose.prod.yml` có sẵn dòng chú thích tương ứng.
- **Stack thử nghiệm** (`deploy/agri-test/docker-compose.yml` đã khai báo `${OCR_AUTO_FULL_PAGE_ON_WATERMARK:-false}`):
  đặt giá trị trong `.env` của stack.

```bash
# sau khi sửa file override (production) hoặc .env (stack thử nghiệm):
docker compose up -d --no-deps open_notebook
docker compose exec open_notebook sh -c 'echo "OCR_AUTO_FULL_PAGE_ON_WATERMARK=$OCR_AUTO_FULL_PAGE_ON_WATERMARK"'
```

Dòng thứ hai phải in đúng giá trị vừa đặt; in ra rỗng nghĩa là biến chưa tới container và tính năng đang **tắt**.
Luôn kèm `--no-deps open_notebook`: lệnh `up -d` không có tên dịch vụ sẽ tạo lại cả container cơ sở dữ liệu.

Giới hạn và ngưỡng: [OCR_PHASE10G_REPORT.md](OCR_PHASE10G_REPORT.md), mục 4 và 13; quyết định thiết kế:
[DECISIONS.md](DECISIONS.md) D-33.

