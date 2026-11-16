# Báo cáo Phase 10 — Custom Tesseract Agri Model Manager

Ngày: 2026-11-16 · Nhánh phát triển: `feature/tesseract-agri-custom-model` (tạo từ tag `v1.1.0-rc.1`, commit
`ad1894ea73d0fff887b404aa3cc24f2a2b197a33`) · Trạng thái: **chờ chủ dự án phê duyệt** — chưa merge, chưa tạo
GitHub Release, chưa triển khai production.

Tài liệu này công khai: không chứa mật khẩu, khóa, model, dữ liệu huấn luyện hay tài liệu nội bộ.

> **Bản công khai (rà soát ở Phase 10I).** Báo cáo ghi nhận trạng thái tại thời điểm viết. Chi tiết hạ tầng
> (đường dẫn máy chủ, mã container / image, tài khoản, SHA-256 của model riêng) đã được lược bỏ hoặc thay bằng giá trị
> minh họa (`/srv/example/…`); bản vận hành đầy đủ do chủ dự án lưu ngoài repository. Các mã commit ngắn trong báo cáo
> là commit cục bộ của nhánh phát triển trước khi gộp — chúng không có trên GitHub. Trạng thái phát hành hiện tại:
> [OCR_RELEASE_NOTES_RC2.md](OCR_RELEASE_NOTES_RC2.md).

Tài liệu liên quan: [OCR_CUSTOM_MODEL_MANAGER.md](OCR_CUSTOM_MODEL_MANAGER.md) (thiết kế) ·
[OCR_AGRI_MODEL_GUIDE.md](OCR_AGRI_MODEL_GUIDE.md) (thao tác) · [OCR_AGRI_BENCHMARK.md](OCR_AGRI_BENCHMARK.md) (số đo).

## 1. Kết luận

| Hạng mục | Kết luận | Cơ sở |
|---|---|---|
| Hỗ trợ model Tesseract custom | **CUSTOM TESSERACT MODEL SUPPORTED** | Agri v1 nạp bằng Tesseract 5.5.0, chạy đủ pipeline Docling qua API + worker (mục 7, T3 và T3b) |
| Quản lý phiên bản | **AGRI MODEL VERSIONING VERIFIED** | Import / liệt kê / xác minh / kích hoạt / rollback / xoá; manifest và registry; readiness theo phiên bản (T4–T12) |
| Thay model không cần build lại | **MODEL REPLACEMENT WITHOUT REBUILD VERIFIED** | Import + kích hoạt phiên bản mới trong container đang chạy: container ID, image ID, thời điểm khởi động không đổi (T5). Lưu ý: phiên bản thứ hai là model *thế thân* vì hiện chỉ có một bản fine-tune thật |
| Rollback model | **MODEL ROLLBACK VERIFIED** | CLI và API; rollback kiểm tra file trước khi chuyển (T7, T10) |
| Rollback ứng dụng | **APPLICATION ROLLBACK VERIFIED** | Stack thử nghiệm chạy lại image `v1.1.0-rc.1`: dữ liệu đọc được nguyên vẹn, OCR hoạt động, rồi tiến lại bản mới với Agri còn nguyên (T16) |
| Bốn engine cũ | **EXISTING OCR ENGINES UNCHANGED** | Văn bản OCR của cả bốn engine trùng mã băm với nghiệm thu baseline Phase 9; checksum model chính thức không đổi; 469 test OCR đạt (mục 8) |
| Chất lượng OCR | **OCR QUALITY EQUIVALENT** — *không chứng minh được là tốt hơn* | Qua pipeline thật trên dữ liệu **tổng hợp**: CER 3,40% (Agri) so với 3,51% (Best). Agri tốt hơn ở số hiệu văn bản và chữ Đ, kém hơn ở giá trị phần trăm. Trên tài liệu thật: **NOT VERIFIED** (mục 6) |
| Production | **PRODUCTION UNCHANGED** | Đối chiếu trước / sau ở mục 2 |

**AWAITING OWNER APPROVAL.** Chưa merge vào `claude/practical-wozniak-9s1t6z`, chưa tạo GitHub Release, chưa triển
khai production, stack thử nghiệm được giữ chạy.

## 2. Bảo vệ production — đối chiếu trước và sau

Mọi thao tác với production trong Phase 10 là **chỉ đọc** (`git rev-parse`, `git status`, `docker inspect`,
`docker ps`, `curl /health`, `ss`, `df`, `free`). Không có lệnh `git pull` / `checkout`, build, restart, recreate,
`docker compose` nào được chạy trong `/srv/example/chatbot5400`.

| Hạng mục | Trước và sau Phase 10 |
|---|---|
| Commit và trạng thái working tree của thư mục production | không đổi |
| Container ứng dụng và container cơ sở dữ liệu | cùng container, cùng image, cùng thời điểm khởi động, số lần restart = 0 |
| Image và phiên bản cơ sở dữ liệu | không đổi |
| Thư mục dữ liệu được gắn vào container | không đổi |
| Kiểm tra sức khỏe API và giao diện | đạt trước và sau |
| Mã băm các tệp cấu hình của production | không đổi |
| Cổng đang nghe của production | không đổi; stack thử nghiệm chỉ thêm hai cổng trên loopback |
| Các tag image của production | cùng image ID |
| Tài nguyên máy chủ | bình thường; stack thử nghiệm, môi trường phát triển và dữ liệu thử dùng thêm khoảng 11 GB đĩa |

Số liệu đối chiếu chi tiết (mã định danh, mã băm, thời điểm) nằm trong hồ sơ vận hành, ngoài repository.

Ghi nhận khi khảo sát (không phải thay đổi của Phase 10): thư mục mã nguồn của production có sửa đổi cấu hình cục bộ
và tag image đang chạy không suy ra được từ commit của thư mục. Vì vậy kế hoạch triển khai (mục 9) gắn tag rollback
theo **image ID của container đang chạy**, không theo commit của thư mục.

## 3. Môi trường phát triển và thử nghiệm riêng

| Hạng mục | Giá trị |
|---|---|
| Workspace | `/srv/example/chatbot5400-agri-test` (clone mới từ GitHub, checkout tag `v1.1.0-rc.1`) |
| Nhánh | `feature/tesseract-agri-custom-model` (chỉ commit cục bộ, chưa push) |
| Compose project | `chatbot5400-agri-test` — file `deploy/agri-test/docker-compose.yml` |
| Image | `chatbot5400:agri-test` (dựng từ workspace, `OCR_INSTALL_TESSERACT=true`) |
| Cổng | Web `127.0.0.1:8503`, API `127.0.0.1:5056` — chỉ loopback, không mở ra LAN / Internet; SurrealDB thử nghiệm không publish cổng |
| Dữ liệu | `deploy/agri-test/notebook_data`, `deploy/agri-test/surreal_data` — riêng, ngoài Git và ngoài build context |
| Credential | `deploy/agri-test/.env` (quyền 600, sinh ngẫu nhiên, chỉ dùng cho stack thử nghiệm), namespace DB `agri_test` |
| Giới hạn tài nguyên | Ứng dụng: 4 CPU, 10 GB RAM · SurrealDB: 1 CPU, 2 GB RAM |
| Thư mục import model | `/srv/example/ocr-model-import` gắn **chỉ đọc** vào `/import` |
| Dữ liệu thử | Chỉ tài liệu tổng hợp (fixture của dự án và bộ benchmark Phase 10E); không có dữ liệu khách hàng |
| Image SurrealDB | `surrealdb/surrealdb:v2` có sẵn trên máy, `pull_policy: never` — không kéo bản mới, không đụng tag mà production dùng |

Giữ nguyên: Open Notebook 1.14.0, Content Core 2.0.7, Docling 2.129.0, Layout Heron, TableFormer Accurate,
RapidOCR, Tesseract Fast / Best, EasyOCR, tiền xử lý PDF, cổng OSD, Force Full Page OCR, số luồng CPU, embedding,
RAG, chat, transformation, prompt, podcast, cơ sở dữ liệu. `pyproject.toml`, `uv.lock`, `package.json`,
`package-lock.json`, `Dockerfile` **không đổi**; không monkey patch, không sửa site-packages; không có migration.

## 4. Phase 10A — Khảo sát

Đã đọc toàn bộ mã OCR Engine Manager (`catalog`, `options`, `paths`, `runtime`, `store`, `installer`, `status`,
`readiness`, `bundle`, `cli`, `tester`, `docling_extract`, `compat`), API (`api/routers/ocr.py`,
`api/ocr_service.py`, `api/models.py`), worker (`commands/ocr_commands.py`), `ContentSettings`, giao diện
(`OcrEngineManager.tsx`, hook, API client, kiểu TypeScript, bản dịch en-US / vi-VN) và các test OCR.

File model (không bị sửa — SHA-256, kích thước và mtime giống hệt trước và sau Phase 10):

| Thuộc tính | Giá trị |
|---|---|
| Đường dẫn | `/srv/example/ocr-model-import/vie_agri.traineddata` |
| Dung lượng | 12.435.550 byte |
| SHA-256 | (lược bỏ trong bản công khai — chủ model tự lưu để đối chiếu) |
| Chuỗi phiên bản | `4.00.00alpha:vie:synth20170629:[1,36,0,1Ct3,3,16Mp3,3Lfys64Lfx96Lrx96Lfx512O1c1]` |
| Thành phần | `config`, `lstm`, `lstm-punc-dawg`, `lstm-word-dawg`, `lstm-number-dawg`, `lstm-unicharset`, `lstm-recoder`, `version` |
| So với `tessdata_best/vie` | Cùng kích thước và cùng mọi thành phần **trừ `lstm`** (trọng số) — là bản fine-tune của Best, không đổi bộ ký tự |
| Nạp bằng Tesseract thật | Tesseract 5.5.0: có trong `--list-langs`, OCR mẫu tiếng Việt đạt CER 0,5% |

## 5. Phase 10B / 10C / 10D — Những gì đã xây dựng

- **Engine thứ năm** `tesseract_agri` — "Tesseract Vietnamese Agri", phân loại *Custom fine-tuned — Experimental*.
  Dùng runtime Tesseract hiện có và `TesseractCliOcrOptions` chính thức của Docling; không có adapter mới; không
  ghi đè `best/vie.traineddata`; engine mặc định vẫn là RapidOCR.
- **Quản lý phiên bản** trên volume dữ liệu: `ocr/models/tesseract/custom/agri/<phiên bản>/vie_agri.traineddata`,
  manifest từng phiên bản, registry (đang hoạt động / trước đó / lịch sử). Không có checksum model custom trong mã
  nguồn; checksum bốn model chính thức được một test mới khóa lại đúng giá trị của `v1.1.0-rc.1`.
- **Import 9 bước** (kiểm tra file → staging → checksum → kiểm tra bằng Tesseract → smoke test → lưu → manifest →
  readiness → không kích hoạt), **kích hoạt / rollback / xoá** có kiểm tra, **một job dùng một phiên bản**.
- **CLI** `custom import | list | status | verify | activate | rollback | remove`, đều có `--help`.
- **API** quản trị: `custom/activate`, `custom/rollback`, `custom/verify`; không có upload qua HTTP.
- **Giao diện**: card Agri với đủ thông tin và nút theo yêu cầu; bốn card cũ không đổi.

Chi tiết thiết kế: [OCR_CUSTOM_MODEL_MANAGER.md](OCR_CUSTOM_MODEL_MANAGER.md).

Cấu hình mặc định của Agri (chọn theo benchmark): **chỉ `vie_agri`** (cấu hình B). `vie_agri + best/eng` (cấu hình C) kém hơn ở mọi tiêu chí trừ giá
trị phần trăm, và vẫn bật được bằng `OCR_AGRI_WITH_ENGLISH=true` để đo lại với các bản fine-tune sau.

## 6. Phase 10E — Benchmark (tóm tắt)

Dữ liệu: 4 văn bản pháp lý **hư cấu** (Quyết định, Quy định, Thông tư, chương quyền – nghĩa vụ) × 4 mức chất lượng
scan = 16 PDF (28 trang, 5.900 từ) + 1 PDF có lớp văn bản. Đo trong container ứng dụng (4 CPU).

| Giai đoạn | Cấu hình | CER | WER | Dấu TV | Tiêu đề đúng | Số hiệu | Giá trị % đúng | Lỗi pháp lý | Giây |
|---|---|---|---|---|---|---|---|---|---|
| Tesseract trực tiếp | A — Best | 2,78% | 8,24% | 98,34% | 59,4% | 53,3% | 27/28 | 48 | 41,0 |
| Tesseract trực tiếp | **B — Agri** | **1,72%** | **4,96%** | 99,22% | 72,9% | 83,9% | 23/28 | 34 | 32,2 |
| Tesseract trực tiếp | C — Agri + eng | 2,04% | 6,10% | 98,66% | 67,7% | 85,6% | 26/28 | 41 | 39,6 |
| Pipeline, Full Page OFF | A — Best | 3,51% | 7,11% | 98,30% | 74,0% | 60,0% | **28/28** | **33** | 129,1 |
| Pipeline, Full Page OFF | **B — Agri** | 3,40% | 6,64% | 98,57% | 79,2% | **86,7%** | 20/28 | 38 | 119,9 |
| Pipeline, Full Page OFF | C — Agri + eng | 3,72% | 7,80% | 97,53% | 68,8% | 86,7% | 27/28 | 41 | 128,6 |
| Pipeline, Full Page ON | A — Best | **2,96%** | 6,50% | 98,20% | 70,8% | 60,0% | 27/28 | **31** | 132,6 |
| Pipeline, Full Page ON | **B — Agri** | 3,47% | 6,60% | 98,50% | 76,0% | 86,7% | 21/28 | 38 | 126,7 |
| Pipeline, Full Page ON | C — Agri + eng | 3,76% | 7,68% | 97,43% | 68,8% | 86,7% | 27/28 | 42 | 135,2 |

- Cô lập model (gọi Tesseract trực tiếp), Agri v1 **tốt hơn** Best rõ rệt, nhất là trên scan mờ.
- Qua **pipeline hoàn chỉnh** — đường mà tài liệu của người dùng đi qua — hai model **tương đương**; phần sai khác do
  dựng lại bố cục không phụ thuộc model và che bớt lợi thế của Agri.
- Agri sửa được lỗi điển hình của Best ở **số hiệu văn bản** (`QĐ` → `QÐ`/`QD`) nhưng **đọc sai một phần giá trị phần
  trăm** (`20%;` → `2096;`): 20/28 so với 28/28. Đây là lỗi làm đổi nghĩa, nên không thể kết luận Agri tốt hơn.
- PDF có lớp văn bản, Full Page OFF: kết quả **giống hệt từng byte** ở cả ba cấu hình — không bị ảnh hưởng.
- Từ phủ định / nghĩa vụ / ngoại lệ (`không`, `phải`, `trừ`, `chưa`): hai model như nhau.

Ground truth độc lập với dữ liệu fine-tune **về nội dung** (viết mới cho benchmark); **không xác minh được** độc lập
về hình thức (phông, kiểu scan) vì người đo không có dữ liệu fine-tune. Bộ đo nhỏ và là ảnh dựng, không phải scan
giấy thật.

Đầy đủ phương pháp, bảng số và giới hạn: [OCR_AGRI_BENCHMARK.md](OCR_AGRI_BENCHMARK.md).

## 7. Phase 10F — Kiểm thử thực tế trên stack thử nghiệm

Mọi kiểm thử chạy trên stack `chatbot5400-agri-test` với Tesseract thật, Docling thật, API thật và worker thật.
Log từng bước nằm ở `/srv/example/evidence/` (ngoài kho mã).

| # | Hạng mục | Cách kiểm | Kết quả | Bằng chứng |
|---|---|---|---|---|
| T1 | Bốn engine cũ vẫn hoạt động | `acceptance_api.py ocr-e2e` cho từng engine: cài model → kích hoạt → test → upload PDF scan → nguồn `completed` → model thực tế | **ĐẠT** — RapidOCR, Tesseract Fast, Tesseract Best: PASS. EasyOCR: mọi bước chạy, thiếu 2 cụm từ kỳ vọng — **giống hệt baseline** (hạn chế chất lượng đã biết, không phải hồi quy) | `e2e-old-engines.jsonl` |
| T1b | Engine cũ cho kết quả không đổi | So mã băm văn bản OCR và CER mẫu với log nghiệm thu baseline Phase 9 | **ĐẠT** — trùng tuyệt đối cả 4 engine (`8f31b457…`, `76477dbc…`, `76477dbc…`, `f43252d0…`; CER 14,14% / 0% / 0% / 6,28%) | như trên |
| T2 | Checksum Best gốc không đổi | `sha256sum` trước Agri, sau mỗi nhóm kiểm thử, sau recreate, trên image baseline | **ĐẠT** — `best/vie` luôn là `b6b49293…bb45`; `best/eng`, `fast/*`, `osd` đúng catalog | `official-checksums-before-agri.txt`, `10f-tamper.log` |
| T3 | Import Agri v1 | `custom import --file /import/vie_agri.traineddata --version v1` | **ĐẠT** — SHA-256 khớp file nguồn, smoke CER 0,5%, readiness `offline_ready`, **không** tự kích hoạt; file nguồn không đổi | `10f-import-v1.log` |
| T3b | Agri qua API + worker | `ocr-e2e --engine tesseract_agri` | **ĐẠT** — `TesseractOcrCliModel`, CER mẫu 0,52%, nguồn `completed`, đủ cụm từ kỳ vọng; log ghi `version=v1 sha256=…` đúng phiên bản | `e2e-agri.jsonl` |
| T4 | Từ chối model lỗi | Import file cắt cụt, ngẫu nhiên, 6 byte, `osd` (không có LSTM), trọng số bị xóa trắng, sai đuôi, symlink, không tồn tại, URL; ghi đè `v1` | **ĐẠT** — 10/10 bị từ chối với thông báo rõ, mã thoát 1; toàn bộ file model và manifest giống hệt trước / sau; staging trống | `10f-reject-bad.log` |
| T5 | Import phiên bản mới, không rebuild | Import `t2` (model thế thân) khi stack đang chạy | **ĐẠT** — container ID, image ID, thời điểm khởi động, số restart không đổi; `v1` vẫn hoạt động | `10f-import-new-version.log` |
| T6 | Kích hoạt phiên bản mới | CLI `custom activate` và API `custom/activate` | **ĐẠT** — có hiệu lực cho tài liệu kế tiếp, lịch sử ghi người thực hiện | `10f-switch-during-job.log`, `10f-readiness-rollback.log` |
| T7 | Rollback về phiên bản cũ | API `custom/rollback` và CLI `custom rollback` | **ĐẠT** — về đúng phiên bản trước; rollback lần nữa quay lại | `10f-readiness-rollback.log` |
| T8 | Chuyển từ Agri sang Best và ngược lại | `ocr-e2e` Best rồi Agri | **ĐẠT** — Best cho đúng mã băm baseline; Agri dùng lại `v1` không cần import lại | `10f-switch-best-restart.log` |
| T9 | Thay model khi còn job OCR | Upload PDF scan 40 trang với `v1`; kích hoạt `t2` giữa chừng; lấy mẫu dòng lệnh Tesseract trong container | **ĐẠT** — 10/10 mẫu sau thời điểm chuyển vẫn là `-l custom/agri/v1/vie_agri`; log: `used for the whole document … version=v1`; tài liệu tải lên sau đó dùng `t2` | `10f-switch-during-job.log` |
| T10 | Phát hiện file bị sửa ngoài manifest | (a) lật 1 byte của phiên bản không hoạt động, giữ nguyên kích thước và mtime; (b) nối thêm byte vào phiên bản đang hoạt động | **ĐẠT** — (a) `verify` báo `corrupted`, API từ chối kích hoạt (400), phiên bản đang hoạt động không đổi; (b) engine chuyển `failed`, tài liệu tải lên **thất bại có thông báo** (không âm thầm đổi engine), `rollback` khôi phục | `10f-tamper.log` |
| T11 | Readiness hết hiệu lực khi đổi phiên bản | Kích hoạt phiên bản chưa kiểm tra | **ĐẠT** — `offline_ready` → `pipeline_not_verified`; sau "Kiểm tra offline" → `offline_ready`; rollback về `v1` dùng lại kết quả của chính `v1` | `10f-readiness-rollback.log` |
| T12 | Offline readiness | Container thứ hai cùng image, cùng thư mục dữ liệu, `--network none` (chỉ có `lo`), chạy `readiness --check` | **ĐẠT** — Agri v1 và Best: `offline_ready`, `offline_verified=True`, Layout Heron + TableFormer accurate; stack đang chạy thấy đúng kết quả | `10f-offline.log` |
| T13 | Restart không mất model | `docker compose restart open_notebook` | **ĐẠT** — phiên bản, phiên bản đang hoạt động, readiness còn nguyên; e2e Agri PASS | `10f-switch-best-restart.log` |
| T14 | Recreate / nâng cấp image không mất model | Build image từ commit mới, `up -d --no-deps open_notebook` | **ĐẠT** — image mới, container mới; model + manifest trùng mã băm; container DB không bị tạo lại; e2e Agri PASS | `10f-rebuild-recreate.log` |
| T15 | Thay model không cần rebuild image | Như T5, T6, T9 | **ĐẠT** — mọi thao tác model diễn ra trong container đang chạy | như T5 |
| T16 | Rollback image ứng dụng về `v1.1.0-rc.1` | Chọn Best → tạo lại container ứng dụng từ `chatbot5400:rc1-20261114` | **ĐẠT** — đăng nhập được, 11 sổ tay / 12 nguồn / 2 người dùng như trước, nội dung nguồn trùng mã băm, 4 engine, Best đang dùng, OCR PDF scan PASS, DB không bị tạo lại, 0 traceback; thư mục Agri còn nguyên | `10f-app-rollback.log` |
| T16b | Hạ cấp mà **quên** đổi engine | Giữ `tesseract_agri` rồi hạ cấp | **Ghi nhận** — bản cũ không lỗi (mọi API 200) nhưng không card nào "Đang dùng" và tài liệu mới được xử lý **âm thầm bằng RapidOCR**; bấm **Sử dụng** trên Best ngay ở bản cũ là khắc phục được | `10f-app-rollback-negative.log`, `10f-app-rollback-norepair.log` |
| T16c | Tiến lại bản mới | Tạo lại container từ `chatbot5400:agri-test` | **ĐẠT** — Agri `v1` hoạt động, `verified`, `offline_ready` như lúc rời | `10f-app-rollback-norepair.log` |
| T17 | RBAC | 10 endpoint OCR (gồm 3 endpoint mới) gọi không token và với tài khoản vai trò `user` | **ĐẠT** — 401 / 403 cho tất cả; phiên bản đang hoạt động không đổi sau các lệnh bị từ chối | `10f-rbac-traversal.log` |
| T18 | Path traversal | Mã phiên bản `../v1`, `v1/../../best`, `/etc/passwd`, `v1%2F..`, `v1.0`, `v1+best/eng`…; engine id `..%2F..%2Fetc`; CLI tương tự | **ĐẠT** — API 422 / 404 / 400; CLI báo lỗi, mã thoát 1; không tệp nào được tạo | `10f-rbac-traversal.log`, `10f-reject-bad.log` |
| T19 | Không có upload model qua HTTP | Liệt kê route `/api/ocr` từ OpenAPI | **ĐẠT** — 13 route, không route nào nhận `multipart/form-data` | `10f-rbac-traversal.log` |
| T20 | PDF có lớp văn bản không bị ảnh hưởng | Pipeline trên `vb_text_layer.pdf` với Best / Agri / Agri + eng, Full Page OFF | **ĐẠT** — văn bản giống hệt từng byte ở cả ba | `bench-results/pipeline.json` |
| T21 | Xoá phiên bản | `custom remove` với phiên bản đang hoạt động, không tồn tại, và hai phiên bản thử | **ĐẠT** — từ chối hai trường hợp đầu; xoá `t2`, `t3`; chỉ còn `v1` | `10f-remove.log` |
| T22 | Giao diện thật | Trình duyệt headless đăng nhập stack thử nghiệm, mở OCR Engine Manager | **ĐẠT** — 5 card; card Agri hiện đúng dữ liệu backend; không lỗi console | ảnh chụp trong hồ sơ vận hành |

(Ảnh chụp card Agri không nằm trong repository công khai vì hiển thị SHA-256 và ghi chú import của model riêng.)

Về các model thế thân: hiện chỉ có **một** bản fine-tune thật (v1). Để kiểm thử "phiên bản mới", "rollback", "thay
model khi đang chạy" và "file bị sửa", hai model chính thức (`tessdata_best` vie, `tessdata_fast` vie) được import
dưới tên `vie_agri.traineddata` thành `t2`, `t3`, rồi đã bị xoá sau kiểm thử. Chúng chứng minh **cơ chế**, không nói
gì về chất lượng của một bản fine-tune tương lai.

## 8. Hồi quy

| Bộ kiểm | Baseline `v1.1.0-rc.1` | Nhánh Phase 10 | Nhận xét |
|---|---|---|---|
| Backend `pytest tests/` | 1432 đạt, 10 lỗi, 47 bỏ qua | **1562 đạt**, 10 lỗi, 48 bỏ qua | +130 test mới. 10 test lỗi là **cùng một tập** với baseline (`test_domain.py::…content_settings_defaults`, 9 test `test_models_api.py::TestModelsProviderAvailability`) — lỗi sẵn có của bộ test, không liên quan OCR; đã đối chiếu từng tên |
| Test OCR (`-k ocr`) | 339 đạt, 47 bỏ qua | **469 đạt**, 48 bỏ qua | Test mới: `tests/test_ocr_custom_models.py` (131 test; 1 test cần Tesseract thật — đạt khi chạy với Tesseract và model thật) |
| Test cũ phải sửa | — | 1 | `test_ocr_engine_manager.py::test_list_engines_shape`: API nay liệt kê 5 engine; phép so được viết lại thành "4 engine chính thức đứng đầu, không đổi thứ tự, rồi tới Agri". Không ngưỡng nào bị hạ |
| `ruff check` | 2 lỗi sẵn có trong `tests/` | như baseline | Mã mới: 0 lỗi; `ruff format` sạch; `mypy` sạch cho `open_notebook/ocr` và API OCR |
| Frontend `tsc --noEmit` | đạt | **đạt** | |
| Frontend `npm run lint` | 0 lỗi, 7 cảnh báo | 0 lỗi, 7 cảnh báo | Cùng 7 cảnh báo sẵn có |
| Frontend `npm run test` | 412 đạt | **419 đạt** | +7 test cho card Agri; 18 test cũ của OCR Engine Manager không sửa |
| Build image | — | **đạt** (`next build` + image `chatbot5400:agri-test`) | |
| Docker acceptance của dự án (`scripts/ocr/docker-acceptance.sh`, nâng cấp từ `v1.1.0-rc.1`, online → offline → restart → update) | Phase 9B (4 engine): 74 PASS, 1 FAIL — nội dung EasyOCR, đã biết · Phase 9C (RC1, `tesseract_best`): 42 PASS, 0 FAIL | **53 PASS, 0 FAIL, 0 NOT VERIFIED** (`EXIT=0`) — kịch bản `rapidocr` + `tesseract_best`, `OLD_REF=v1.1.0-rc.1`: dữ liệu và cấu hình của bản cũ được giữ, chuẩn bị online, vận hành offline, restart khi offline, cập nhật image rồi offline lại | Chạy trên project và thư mục tạm riêng, image tạm `chatbot5400:agri-accept`; log: `docker-acceptance-phase10.log` |

Tính nguyên vẹn của bốn engine cũ còn được bảo đảm bằng thiết kế: `catalog.ENGINE_IDS` vẫn là bốn engine chính thức
(hai test "catalog unchanged" của baseline đạt mà không sửa); với engine không phải custom, các lời gọi nội bộ giữ
đúng chữ ký cũ; `uv.lock`, `package-lock.json`, `Dockerfile` không đổi.

## 9. Kế hoạch triển khai production (CHƯA thực hiện — chờ chủ dự án phê duyệt)

Kế hoạch này dựa trên trạng thái production đọc được ngày 2026-11-16 (mục 2) và trên quy trình đã dùng ở Phase 9C
([OCR_PRODUCTION_DEPLOYMENT_PLAN.md](OCR_PRODUCTION_DEPLOYMENT_PLAN.md)). Không bước nào được thực hiện trong
Phase 10.

**Điều kiện trước khi bắt đầu**

1. Chủ dự án phê duyệt Phase 10 và quyết định cách đưa mã vào nhánh chính thức (PR từ
   `feature/tesseract-agri-custom-model`).
2. Benchmark trên tài liệu thật của đơn vị bằng `scripts/ocr/local_document_benchmark.py`
   (`--engines tesseract_best tesseract_agri`) trên stack thử nghiệm — chưa có kết quả này thì chỉ triển khai mã,
   **không** chọn Agri cho tài liệu nghiệp vụ.
3. Có cửa sổ bảo trì; máy chủ có Internet (bước dựng image).

**Bước 1 — Kiểm tra trước (chỉ đọc):** commit thư mục production, image ID và container ID của ứng dụng và của
SurrealDB, phiên bản SurrealDB, `/health`, CPU / RAM / đĩa (cần ≥ 10 GB trống), cổng đang dùng, engine OCR đang
chọn. Ghi lại để đối chiếu sau.

**Bước 2 — Dựng image mới ở thư mục riêng, tag riêng** (không dựng trong thư mục production, dịch vụ vẫn chạy):

```bash
cd /srv/example/chatbot5400-agri-test            # checkout đúng commit đã được phê duyệt
docker build --target runtime --build-arg OCR_INSTALL_TESSERACT=true -t chatbot5400:agri-$(date +%Y%m%d) .
```

**Bước 3 — Gắn tag rollback cho image ĐANG CHẠY THỰC TẾ** (theo image ID của container, không theo tên tag
`chatbot5400:local` vì tag này sẽ bị ghi đè):

```bash
RUNNING=$(docker inspect --format '{{.Image}}' "$(docker compose ps -q open_notebook)")   # chạy trong thư mục production
docker tag "$RUNNING" chatbot5400:rollback-pre-agri-$(date +%Y%m%d-%H%M%S)
docker images --no-trunc | grep rollback-pre-agri
```

**Bước 4 — Sao lưu lạnh** (theo đúng quy trình Phase 9C): dừng hai container bằng `docker compose stop`, sao lưu
`notebook_data`, `surreal_data`, `.env`, `docker-compose.yml`, `docker-compose.override.yml` ra thư mục sao lưu có
quyền `700`, ghi SHA-256; kiểm tra khôi phục được trên stack cô lập. **Không** `down`, **không** `down -v`.

**Bước 5 — Cập nhật RIÊNG ứng dụng, giữ nguyên SurrealDB:**

```bash
cd /srv/example/chatbot5400
docker tag chatbot5400:agri-YYYYMMDD chatbot5400:local
docker compose start surrealdb
docker compose up -d --no-deps --no-build open_notebook
```

- `--no-deps`: không tạo lại container SurrealDB (compose production có `pull_policy: always` cho SurrealDB — một
  lệnh `up -d` không kèm tên service sẽ kéo image DB mới và tạo lại container DB).
- `--no-build`: không dựng lại image từ thư mục production.
- Không sửa `docker-compose.yml`, `.env`, không đổi cổng 8502 / 5055, không nâng cấp SurrealDB.
- Phase 10 **không có migration cơ sở dữ liệu**.

**Bước 6 — Kiểm tra sau cập nhật:** `/health` 200; đăng nhập; mở một sổ tay và một nguồn có sẵn; OCR Engine
Manager hiện 5 engine, engine đang dùng **không đổi**; `ocr status`; không có cảnh báo phụ thuộc; chạy "Kiểm tra
offline" cho engine đang dùng; `bash scripts/ocr/production_health_check.sh`.

**Bước 7 — Import Agri v1 trên production** (chỉ sau khi bước 6 đạt):

```bash
mkdir -p notebook_data/ocr-import                      # cần quyền ghi vào notebook_data
cp /srv/example/ocr-model-import/vie_agri.traineddata notebook_data/ocr-import/
ocr() { docker compose exec open_notebook /app/.venv/bin/python -m open_notebook.ocr.cli "$@"; }
ocr custom import --file /app/data/ocr-import/vie_agri.traineddata --version v1
ocr custom activate --version v1
ocr custom status
```

SHA-256 in ra phải trùng giá trị chủ model đã lưu. Bấm **Kiểm tra** trên card Agri. **Chưa** bấm **Sử dụng** cho tới khi có
kết quả benchmark tài liệu thật và quyết định của chủ dự án.

**Bước 8 — Rollback** (từ nhẹ đến nặng):

| Mức | Khi nào | Cách |
|---|---|---|
| Phiên bản model | Bản fine-tune mới kém hơn | `ocr custom rollback` |
| Engine | Agri không đạt | Bấm **Sử dụng** trên engine trước đó (Tesseract Vietnamese Best / RapidOCR) |
| Image ứng dụng | Bản mới có lỗi | Chọn engine mà bản cũ hỗ trợ → `docker tag chatbot5400:rollback-pre-agri-<thời điểm> chatbot5400:local` → `docker compose up -d --no-deps --no-build open_notebook` |
| Cấu hình | Đã sửa `.env` / compose | Chép lại bản sao lưu ở bước 4 rồi tạo lại riêng container ứng dụng |
| Dữ liệu | Hỏng dữ liệu (không kỳ vọng) | Dừng container, khôi phục `notebook_data` + `surreal_data` từ bản sao lưu lạnh ở bước 4 |

**Bảo toàn dữ liệu:** không migration, không đụng container / volume SurrealDB, không xoá gì trong `notebook_data`;
model custom nằm ở `notebook_data/ocr/models/tesseract/custom`, manifest ở `notebook_data/ocr/manifests/custom` —
cả hai đi cùng bản sao lưu `notebook_data` và tồn tại qua mọi lần đổi image.

## 10. Bàn giao stack thử nghiệm

Stack `chatbot5400-agri-test` **được giữ chạy** để chủ dự án trực tiếp thử nghiệm (`restart: unless-stopped`).

| Hạng mục | Giá trị |
|---|---|
| URL (trên máy Windows, qua SSH tunnel) | `http://localhost:8503` |
| API (qua cùng tunnel) | `http://localhost:5056` — giao diện tự gọi địa chỉ này |
| Tài khoản thử nghiệm | Một tài khoản quản trị và một tài khoản vai trò người dùng (để kiểm tra phân quyền), ghi trong một tệp quyền 600 trên máy chủ, ngoài Git. Mật khẩu mặc định đã bị đổi |
| Trạng thái Agri | **v1 đang hoạt động** — `verified`, khớp manifest, `offline_ready` (đã kiểm cả ở chế độ không mạng); không có phiên bản rollback (các phiên bản thử đã xoá) |
| Engine OCR đang chọn | **Tesseract Vietnamese Agri** — tài liệu tải lên sẽ được OCR bằng Agri v1 ngay. Bốn engine còn lại đều ở trạng thái Sẵn sàng |

**Truy cập an toàn từ máy Windows** — stack chỉ nghe trên loopback của máy chủ, không mở ra LAN / Internet. Mở
PowerShell (Windows 10/11 có sẵn OpenSSH) và giữ cửa sổ này mở trong lúc thử:

```text
ssh -N -L 8503:127.0.0.1:8503 -L 5056:127.0.0.1:5056 <tài-khoản>@<địa-chỉ-máy-chủ>
```

Sau đó mở trình duyệt tại `http://localhost:8503`. Phải chuyển tiếp **cả hai** cổng (giao diện 8503 và API 5056).
Nếu dùng PuTTY: Connection → SSH → Tunnels, thêm `L8503 → 127.0.0.1:8503` và `L5056 → 127.0.0.1:5056`. Mật khẩu
thử nghiệm chỉ được lưu trên máy chủ, trong tệp tài khoản của stack thử nghiệm.

**Tạo thêm tài khoản thử nghiệm:** đăng nhập admin → Quản trị người dùng → thêm người dùng; hoặc đổi mật khẩu admin
trong mục tài khoản. Các tài khoản này chỉ tồn tại trong cơ sở dữ liệu thử nghiệm.

**Chọn model:** Cài đặt → OCR Engine Manager → card *Tesseract Vietnamese Agri* → **Sử dụng** (mục 2 của
[OCR_AGRI_MODEL_GUIDE.md](OCR_AGRI_MODEL_GUIDE.md)). So sánh với Best: bấm **Sử dụng** trên *Tesseract Vietnamese
Best* rồi tải lại cùng file.

**Import Agri v2 khi có bản fine-tune mới** (không build, không restart):

```bash
cp vie_agri.traineddata /srv/example/ocr-model-import/vie_agri.traineddata     # ghi đè file ở thư mục import
cd /srv/example/chatbot5400-agri-test/deploy/agri-test
ocr() { docker compose exec open_notebook /app/.venv/bin/python -m open_notebook.ocr.cli "$@"; }
ocr custom import --file /import/vie_agri.traineddata --version v2 --notes "fine-tune lần 2"
ocr custom activate --version v2      # hoặc nút "Chuyển sang phiên bản này"
```

**Rollback:** `ocr custom rollback` (hoặc nút **Rollback về v1**); bỏ Agri: bấm **Sử dụng** trên Tesseract Vietnamese
Best. Hạ cấp image ứng dụng: mục 7 và [OCR_ROLLBACK.md](OCR_ROLLBACK.md).

**Quản lý stack thử nghiệm** (chỉ trong thư mục `deploy/agri-test`, không bao giờ trong thư mục production):

```bash
cd /srv/example/chatbot5400-agri-test/deploy/agri-test
docker compose ps
docker compose logs --tail 100 open_notebook
docker compose stop        # tạm dừng, giữ dữ liệu
docker compose start
```

Không dùng `docker compose down -v`. Stack thử nghiệm dùng tối đa 4 CPU / 10 GB RAM khi OCR; khi rảnh dùng khoảng
1–3 GB RAM. Nếu production cần tài nguyên, `docker compose stop` stack thử nghiệm.

Trong cơ sở dữ liệu thử nghiệm còn các sổ tay "OCR acceptance …" và "Phase 10F …" do kiểm thử tạo ra (toàn tài liệu
tổng hợp); có thể xoá trong giao diện.

## 11. Danh sách tệp thay đổi và commit

34 tệp, +5.721 / −64 dòng so với `v1.1.0-rc.1` (trước commit tài liệu cuối).

| Nhóm | Tệp |
|---|---|
| Backend — mới | `open_notebook/ocr/custom_models.py` |
| Backend — sửa | `open_notebook/ocr/{catalog,options,store,status,readiness,installer,tester,docling_extract,cli}.py`, `open_notebook/domain/content_settings.py`, `api/models.py`, `api/ocr_service.py`, `api/routers/ocr.py` |
| Frontend | `frontend/src/app/(dashboard)/settings/components/OcrEngineManager.tsx` (+ `.test.tsx`), `frontend/src/lib/{api/ocr.ts,hooks/use-ocr.ts,types/api.ts}`, `frontend/src/lib/locales/{vi-VN,en-US}/index.ts` |
| Test | `tests/test_ocr_custom_models.py` (mới), `tests/test_ocr_engine_manager.py` (1 phép so) |
| Công cụ đo | `scripts/ocr/generate_agri_benchmark_fixtures.py`, `scripts/ocr/agri_benchmark.py` |
| Stack thử nghiệm | `deploy/agri-test/docker-compose.yml`, `deploy/agri-test/.gitignore`, `.dockerignore` (loại `.env` / thư mục import của stack thử nghiệm khỏi build context) |
| Tài liệu | `docs/ocr/OCR_CUSTOM_MODEL_MANAGER.md`, `OCR_AGRI_MODEL_GUIDE.md`, `OCR_AGRI_BENCHMARK.md`, `OCR_PHASE10_REPORT.md` (mới); `OCR_OPERATOR_GUIDE.md`, `OCR_ROLLBACK.md` (bổ sung) |

Không đổi: `pyproject.toml`, `uv.lock`, `frontend/package.json`, `frontend/package-lock.json`, `Dockerfile`,
`docker-compose.yml`, mọi migration, mọi tệp ngoài phạm vi OCR.

Commit trên `feature/tesseract-agri-custom-model` (cục bộ, **chưa push**):

| Commit | Nội dung |
|---|---|
| `5bf6874` | Engine Agri, quản lý phiên bản, CLI, API, giao diện, stack thử nghiệm, công cụ đo, test |
| `fb6c270` | Sửa script benchmark theo API cài đặt đã đóng băng |
| `cc53ee6` | Log phiên bản model đã dùng cho mỗi tài liệu; tài liệu thiết kế |
| `4abdee6` | `custom remove`; hướng dẫn Agri; bổ sung hướng dẫn vận hành / rollback |
| `3edef7f` | Kết quả benchmark; ghi chú chất lượng trên giao diện khớp số đo |
| `e101e6a` | Băm lại toàn bộ file model custom trước mỗi tài liệu |
| (commit cuối) | Báo cáo Phase 10, ảnh giao diện, sửa mô tả hạ cấp theo kết quả kiểm thử |

Image `chatbot5400:agri-test` đang chạy được dựng từ `e101e6a` (các commit sau chỉ có tài liệu). Model, `.env`,
tài khoản thử nghiệm và dữ liệu thử nghiệm **không** nằm trong bất kỳ commit nào.

## 12. Giới hạn và việc còn mở

1. **Chất lượng trên tài liệu thật chưa được kiểm chứng.** Benchmark chỉ dùng ảnh dựng từ văn bản hư cấu; không
   xác minh được độc lập về hình thức với dữ liệu fine-tune. Bước tiếp theo: chủ dự án chạy
   `scripts/ocr/local_document_benchmark.py --engines tesseract_best tesseract_agri` trên tài liệu thật, ngay trên
   stack thử nghiệm.
2. **Agri v1 đọc sai một phần giá trị phần trăm** (20/28 qua pipeline; Best 28/28) và đôi khi sai dấu ở `nghiêm cấm`.
   Nên bổ sung mẫu có `%` cho bản fine-tune kế tiếp ([OCR_AGRI_BENCHMARK.md](OCR_AGRI_BENCHMARK.md) mục 6.6).
3. **Phiên bản thứ hai dùng model thế thân** (mục 7): cơ chế đã được kiểm chứng, một bản fine-tune thật thứ hai thì
   chưa.
4. **Offline** được kiểm bằng (a) pipeline bị chặn mạng và (b) container không có mạng dùng chung thư mục dữ liệu;
   stack thử nghiệm đang chạy không bị ngắt mạng thật (nó cần mạng nội bộ tới cơ sở dữ liệu).
5. **Manifest và model nằm cùng volume.** Người có quyền ghi volume có thể sửa cả hai; điểm neo độc lập là SHA-256
   chủ model tự lưu. Màn hình trạng thái dùng cache băm theo kích thước + mtime; mỗi tài liệu, `verify`, kích hoạt
   và rollback thì băm lại toàn bộ file.
6. **Hạ cấp mà quên đổi engine** → bản cũ âm thầm dùng RapidOCR (T16b). Đã ghi vào hướng dẫn rollback.
7. **Chưa có upload model qua HTTP** (theo yêu cầu giai đoạn này) và chưa có nút / API xoá phiên bản (chỉ CLI).
8. 10 test backend lỗi và 2 lỗi `ruff` trong `tests/` là **sẵn có** ở `v1.1.0-rc.1`; ngoài phạm vi Phase 10, không
   được sửa để tránh đụng baseline.
9. Tài nguyên máy chủ: workspace (gồm `.venv`), image `chatbot5400:agri-test`, dữ liệu stack thử nghiệm và thư mục
   bằng chứng `/srv/example/evidence` chiếm khoảng 11 GB đĩa. Hai image tạm của nghiệm thu Docker
   (`chatbot5400:agri-accept*`) đã được xoá sau khi chạy. Khi không còn cần stack thử nghiệm: `docker compose stop`
   trong `deploy/agri-test` (không dùng `docker system prune`).
10. Nhánh `feature/tesseract-agri-custom-model` chỉ có trên máy chủ thử nghiệm; chưa được đẩy lên GitHub.
