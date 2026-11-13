# Báo cáo Phase 9A — Cổng bảo mật cuối và Release Candidate

Ngày: 2026-11-13 · Máy nghiệm thu: Ubuntu Server, 8 CPU, 30 GB RAM, không GPU
Branch làm việc: `local/ocr-phase8c` · Branch phát hành: `release/ocr-engine-manager-rc1`

Phase 9A không nghiên cứu hay tối ưu OCR thêm. Việc chính: cho phép tắt hẳn chức năng thêm nguồn từ URL
(giảm thiểu rủi ro SSRF còn lại), review độc lập cuối, và chuẩn bị phát hành. Số liệu lịch sử Phase 8B–8D
không bị sửa.

## Đánh giá

| Trạng thái | Kết luận | Lý do |
|---|---|---|
| Merge | **READY FOR MERGE** (theo tiêu chí phát hành có điều kiện đã được chủ dự án chấp nhận) | Review cuối: 0 High, 0 Medium. Không lỗi mới ở backend / frontend. Bộ OCR gốc vẫn 38/48 và lộ trình nhanh gốc vẫn 6/3 — đây là giới hạn đã ghi nhận, không phải "toàn bộ PASS" |
| Phát hành có điều kiện | **READY FOR CONDITIONAL RELEASE** — Tesseract Vietnamese Best (khuyến nghị) và RapidOCR (tương thích ngược), **với URL ingestion tắt** | Mục A, B |
| Production | **NOT READY FOR PRODUCTION** | Chưa có: benchmark tài liệu thật do chủ dự án thực hiện; backup và kiểm tra restore; kiểm tra trên môi trường đích; phê duyệt kế hoạch triển khai (mục L) |

## A. Quyết định chất lượng OCR (chốt ở Phase 8D, không đổi)

| Lựa chọn | Phân loại | Trạng thái phát hành |
|---|---|---|
| Tesseract Vietnamese Best | Khuyến nghị cho tiếng Việt | Đạt tiêu chí có điều kiện 7/7 (3 bài áp dụng KL-1: mất dấu ở tiêu đề in đậm `BẢNG KÊ CHI TIẾT KHOẢN MỤC MẪU`). Ngoại lệ **không** mở rộng sang số tiền, ngày, số hiệu, nhãn dòng bảng hay nội dung nghiệp vụ. Lỗi dấu ở tiêu đề/nhãn khác trên holdout (4/13 tài liệu) tiếp tục được ghi nhận và cảnh báo trong giao diện |
| Tesseract Vietnamese Fast | Ưu tiên tốc độ | Giữ trong OCR Engine Manager. **Chưa đạt** chuẩn phát hành nghiệp vụ (sai dấu ở nhãn dòng bảng). Không tối ưu thêm |
| RapidOCR – PaddleOCR | Tương thích ngược | Giữ model, backend torch, lưu trữ bền đã nghiệm thu; vẫn là mặc định. **Không** tuyên bố đạt chất lượng bảng biểu tài chính tiếng Việt |
| EasyOCR Vietnamese | Thử nghiệm | Không khuyến nghị cho tài liệu tài chính; cảnh báo trước khi bật; không fallback tự động. Không tối ưu thêm |

Giữ nguyên: 48 bài gốc, fixture, ground truth, ngưỡng, tiêu chí phát hành bổ sung, toàn bộ evidence.
Kiến trúc giữ nguyên: Docling 2.129.0, Content Core 2.0.7, RapidOCR 3.9.2, EasyOCR 1.7.2, dependency lock,
Layout Heron, TableFormer accurate, `tesseract_gate.py`, `pdf_prep.py`.

Chạy lại ở Phase 9A (sau thay đổi cuối): bộ gốc 48 bài **38 PASS / 10 FAIL / 0 NOT VERIFIED**; lộ trình nhanh **6 PASS / 3 FAIL**; tiêu chí có điều kiện — Tesseract Best 7/7 (4 PASS + 3 kèm KL-1), critical 7/7; Fast 5/7; RapidOCR 7/7; EasyOCR 2/7. Tất cả **không đổi** so với Phase 8D.

## B. Cơ chế tắt URL ingestion (D-29)

Biến môi trường `OPEN_NOTEBOOK_ENABLE_URL_INGESTION`.

| | |
|---|---|
| Mặc định | **Tắt.** Thiếu, rỗng, hoặc bất kỳ giá trị nào khác `true` / `1` / `yes` / `on` đều là tắt. Không bao giờ tự bật khi thiếu hay sai cấu hình |
| Ai đổi được | Chỉ người kiểm soát môi trường container. Không có API, không có trường Settings; frontend chỉ đọc |
| Miễn trừ | Không. Quản trị viên cũng bị từ chối |
| Thời điểm đọc | Mỗi lần gọi (không cache lúc import) |

**Các đường vào đã khảo sát và cách chặn** (mỗi tầng từ chối trước mọi truy vấn DNS hay request):

| Đường vào | Khi tắt |
|---|---|
| `POST /api/sources` với `type=link` — xử lý sync và async | 403; không tạo bản ghi nguồn; không xếp job |
| `POST /api/sources/json` (endpoint cũ) | 403 (dùng chung logic) |
| `POST /api/sources/{id}/retry` trên nguồn URL cũ (xử lý lại) | 403; không xếp job |
| Lệnh worker `process_source` có `content_state.url` — gồm job đã xếp hàng trước khi tắt, job retry, job không qua API | Lỗi vĩnh viễn (`ValueError`, không retry), trước khi nạp nguồn |
| Nút graph `content_process` có `url` (kể cả khi kèm `content`) | Từ chối trước `validate_source_url` và trước Content Core |
| Lớp OCR cho URL: `should_use_native_ocr_for_url`, `extract_url_with_selected_ocr` | Từ chối trước lệnh dò MIME và trước khi tải |
| `POST /api/commands/jobs` (job tổng quát) | Vẫn luôn bị khóa từ Phase 8A; tầng worker vẫn áp dụng |

Không có import hàng loạt riêng: giao diện "thêm nhiều URL" gọi lặp `POST /api/sources`, nên cùng bị chặn.
Các đường không tải URL (đã kiểm tra, không cần chặn): cập nhật nguồn (chỉ tiêu đề/chủ đề), duyệt/từ chối,
embedding và dựng lại embedding, transformation, insight, chat, hỏi đáp, tìm kiếm, ghi chú, podcast.

**Giữ nguyên khi tắt:** nội dung đã trích xuất của nguồn URL cũ vẫn đọc, tìm kiếm, chat được; không xóa,
không migration. Upload PDF / Word / hình ảnh, nhập văn bản, OCR, Layout Heron, TableFormer, xuất Markdown,
tải model khi chuẩn bị online, gọi LLM và embedding, transformation, RAG, chat đều không đọc công tắc này
(một test ghim danh sách module có dùng công tắc).

**Giao diện:** lấy `url_ingestion_enabled` từ `GET /api/capabilities`. Tab "Thêm URL" bị vô hiệu hóa kèm
thông báo tiếng Việt / tiếng Anh; nút "Thử lại" và "Làm mới nội dung" không hiện trên nguồn URL. Trạng thái
chưa biết (đang tải, backend cũ) ⇒ coi như tắt. Tab upload file và nhập văn bản không đổi.

**Khi bật:** hành vi và chính sách kiểm tra URL của Phase 8A giữ nguyên.

**Tương thích khi nâng cấp:** bản triển khai nào đang dùng nguồn URL (kể cả YouTube) phải đặt
`OPEN_NOTEBOOK_ENABLE_URL_INGESTION=true`. Đã ghi trong `CHANGELOG.md`, `.env.example`, `docker-compose.yml`,
`deploy/docker-compose.prod.yml`, `docs/5-CONFIGURATION/environment-reference.md`.

## C. Phạm vi rủi ro SSRF

| | URL ingestion **tắt** (mặc định) | URL ingestion **bật** |
|---|---|---|
| Máy chủ tải URL do người dùng đưa vào qua chức năng nguồn | Không còn đường nào (bảng mục B; review độc lập đã săn bypass) | Có |
| Redirect khác ở lần tải thật; DNS rebinding | Không chạm tới được qua chức năng này | **Còn tồn tại** như trước |
| Bản chất | Giảm thiểu bằng cách **gỡ chức năng** | Kiểm tra trước + pre-check redirect, không phải bảo đảm |

- **Không tuyên bố SSRF đã được sửa triệt để.** Bộ tải của Content Core / Docling không đổi.
- Ngoài phạm vi công tắc, không đổi: URL nhà cung cấp LLM / embedding và dò model do quản trị viên cấu hình
  (đã qua `validate_url`); tải model khi chuẩn bị online (URL cố định trong catalog).
- Rollback về bản trước RC đồng nghĩa URL ingestion hoạt động trở lại (bản cũ không có công tắc).
- Phát hành cho môi trường ngân hàng chỉ được đánh giá với công tắc **tắt**, trừ khi có biện pháp bổ sung
  được phê duyệt.

## D. Security test

| Kiểm thử | Kết quả |
|---|---|
| `tests/test_url_ingestion_switch.py` (mới) | 43 passed. Có fixture làm test thất bại nếu có **bất kỳ** truy vấn DNS hay kết nối nào |
| — API tạo nguồn URL bị chặn: multipart sync, async; endpoint JSON | PASS — 403, không lưu nguồn, không gọi `validate_url`, không xếp job |
| — Quản trị viên và Quản lý sổ tay đều bị chặn | PASS |
| — Retry / xử lý lại nguồn URL cũ bị chặn (kể cả admin) | PASS |
| — Worker từ chối trước khi nạp nguồn và trước graph | PASS |
| — Graph từ chối trước kiểm tra URL và trước Content Core; lớp OCR từ chối trước dò MIME và tải | PASS |
| — Nguồn URL cũ vẫn đọc được nội dung đã lưu | PASS |
| — Upload file, nhập văn bản, retry nguồn văn bản vẫn chạy | PASS |
| — Khi bật: `validate_url` được gọi; URL bị chính sách chặn trả 400 | PASS |
| — Capabilities báo đúng; không đổi được qua API; giá trị sai ⇒ tắt | PASS |
| — Công tắc chỉ được dùng trong 6 module nhập nguồn (LLM, embedding, chuẩn bị model không đọc nó) | PASS |
| Frontend `SourceTypeStep.test.tsx` (mới) | 3 passed |
| Test bảo mật backend (job guard, commands, auth, URL) | 185 passed |
| Kiểm tra trực tiếp công tắc trên stack nghiệm thu cô lập (container không đặt biến ⇒ mặc định) | 7/7 PASS |
| Kiểm tra bảo mật trực tiếp (401 / 403 trên API OCR và commands) | 16/16 PASS |
| Xử lý sync + async, 3 job song song, dọn file tạm | 6/6 PASS |

Mọi kiểm thử chỉ dùng mock, stub cục bộ và file tổng hợp; `example.com` chỉ được nêu tên và không bao giờ
được liên lạc. Bộ test đã bắt được một thiếu sót trong bản vá đầu (hàm tải của lớp OCR chưa có chốt chặn),
đã sửa trước khi commit.

## E. Regression

| Hạng mục | Phase 8D | Phase 9A |
|---|---|---|
| Backend `pytest tests/` | 1239 passed / 10 failed | **1288 passed / 10 failed / 44 skipped** — cùng đúng 10 lỗi có sẵn trên `main`, 0 lỗi mới |
| Frontend lint | 0 error (7 warning có sẵn) | 0 error (7 warning có sẵn) |
| TypeScript | 0 lỗi | 0 lỗi |
| Frontend test | 408/408 | **411/411** |
| Frontend production build | OK | OK |
| mypy / ruff | 33 / 1 (có sẵn) | 33 / 1 (có sẵn) |

13 test có sẵn kiểm tra hành vi khi URL *được bật* (chính sách SSRF, định tuyến engine cho URL); 6 module
test đó giờ bật công tắc một cách tường minh. Không test nào bị xóa, skip hay nới lỏng. 10 lỗi backend có
sẵn (`test_models_api` × 9, `test_domain` × 1) không thuộc phạm vi và không được sửa.

## F. Docker acceptance

| Lượt | Kết quả |
|---|---|
| Quick, Tesseract Best, nâng cấp từ `5e04227`, URL ingestion mặc định (tắt) — trên mã cuối | **42 PASS / 0 FAIL / 0 NOT VERIFIED** (commit `d671218`) |
| Quick — lượt trước các sửa theo review (commit `3288a73`) | 42 PASS / 0 FAIL / 0 NOT VERIFIED |
| Full 4 lựa chọn; RapidOCR persistent; image không có Tesseract | Không chạy lại ở 9A (kết quả Phase 8D: 74/1, 42/0, 50/1) |

Thay đổi của Phase 9A không đụng runtime, readiness, Dockerfile hay entrypoint. Thay đổi chạm pipeline chung
là khóa pdfium trong `pdf_prep.py` và phần bọc lỗi của `hub_http.py`; vì vậy đã chạy lại bộ OCR gốc, tiêu chí
phát hành và Docker quick trên mã cuối. Các kịch bản full / persistent / không-Tesseract không được chạy lại:
phần mã riêng của chúng (RapidOCR, EasyOCR, lưu trữ bền) không đổi kể từ Phase 8D.

## G. Review độc lập cuối

Agent riêng, chỉ đọc, trên `git diff 45e2254..HEAD` (commit `3288a73`): **NO BLOCKER — 0 High, 0 Medium, 9 Low.**

Săn bypass công tắc URL: mọi đường tới `extract_content(url=…)`, `_download_remote_file`, `detect_remote_mime`
đều được phủ; không thể "lách" bằng `type=text` có nội dung là URL, bằng `file_path` là URL, hay bằng biến
thể chữ hoa của `type`; duyệt nguồn, embedding, chat, podcast không tải URL. Công tắc được đọc lúc gọi và
không ghi được qua API.

| # | Low | Xử lý |
|---|---|---|
| 1 | `pdf_prep.py` dùng pdfium không qua khóa của Docling (rủi ro khi 2 upload sync chạy song song trong tiến trình API) | **Đã sửa** — dùng `pypdfium2_lock` cho mọi lời gọi pdfium, nhả khóa khi chạy Tesseract; có test |
| 2 | `bound_hub_timeouts()` có thể làm hỏng mọi job nếu `huggingface_hub` đổi nội bộ | **Đã sửa** — lỗi được ghi log, tài liệu vẫn xử lý; có test |
| 3 | Kết quả readiness cũ hết hiệu lực sau nâng cấp | **Đã ghi** trong CHANGELOG và kế hoạch triển khai |
| 4 | Nút "Thử lại" / "Làm mới nội dung" vẫn hiện trên nguồn URL khi tắt | **Đã sửa** — không hiển thị |
| 5 | `deploy/docker-compose.prod.yml` chưa truyền biến | **Đã sửa** |
| 6 | Thiếu mục CHANGELOG cho thay đổi mặc định | **Đã sửa** |
| 7 | Heuristic "trang scan" (ảnh ≥ 50 % trang) có thể hạ scale OCR sai với PDF có ảnh nền | Ghi nhận là giới hạn (`OCR_QUALITY_OPTIMIZATION.md` §2.5); tắt bằng `OCR_PDF_PREP=false` |
| 8 | Trường hợp xấu nhất của dò hướng: 200 trang × 30 s | Ghi nhận; chỉnh `OCR_PAGE_OSD_MAX_PAGES` |
| 9 | Có sẵn, ngoài diff: retry khi job đang chạy có thể xếp trùng job (lỗi 400 bị nuốt) | **Không sửa** (ngoài phạm vi); ghi nhận để xử lý riêng |

Kiểm tra khác đều đạt: `pyproject.toml`, `uv.lock`, `Dockerfile`, entrypoint không đổi kể từ `45e2254`; không
monkey patch ngoài factory HTTP chính thức của Hub; `compat.py` không đổi; không migration, không đổi dạng dữ
liệu, rollback an toàn; trường API mới đều có mặc định; không bí mật, không file nhị phân lớn; 48 bài gốc và
ngưỡng không đổi, không thêm skip/xfail.

Review **không** kiểm chứng (đã được kiểm chứng riêng bằng các lượt chạy ở mục A, E, F): chạy thật 48 bài OCR,
Docker, frontend.

## H. File thay đổi trong Phase 9A

| Nhóm | File |
|---|---|
| Công tắc URL — backend | `open_notebook/utils/url_ingestion.py` (mới), `api/routers/sources.py`, `api/routers/capabilities.py`, `api/models.py`, `commands/source_commands.py`, `open_notebook/graphs/source.py`, `open_notebook/ocr/docling_extract.py` |
| Công tắc URL — frontend | `frontend/src/components/sources/steps/SourceTypeStep.tsx`, `SourceCard.tsx`, `lib/types/api.ts`, `lib/locales/vi-VN/index.ts`, `lib/locales/en-US/index.ts` |
| Sửa theo review | `open_notebook/ocr/pdf_prep.py`, `open_notebook/ocr/hub_http.py` |
| Cấu hình | `docker-compose.yml`, `deploy/docker-compose.prod.yml`, `.env.example`, `CHANGELOG.md` |
| Công cụ | `scripts/ocr/local_document_benchmark.py` (mới) |
| Test mới | `tests/test_url_ingestion_switch.py`, `tests/test_ocr_local_benchmark.py`, `frontend/…/SourceTypeStep.test.tsx`; bổ sung `tests/test_ocr_quality_prep.py` |
| Test có sẵn (bật công tắc tường minh / thêm trường) | `tests/test_background_job_security.py`, `test_graphs.py`, `test_ocr_engine_manager.py`, `test_ocr_source_graph.py`, `test_ocr_docling_parity.py`, `test_sources_api.py`, `test_capabilities_api.py` |
| Tài liệu mới | `OCR_PHASE9A_REPORT.md`, `OCR_PRODUCTION_DEPLOYMENT_PLAN.md`, `OCR_PRODUCTION_CHECKLIST.md`, `OCR_REAL_DOCUMENT_BENCHMARK.md` |
| Tài liệu cập nhật | `docs/security/BACKGROUND_JOB_SECURITY.md`, `OCR_COMMANDS_JOBS_RISK.md`, `OCR_SECURITY_REVIEW.md`, `DECISIONS.md` (D-29), `OCR_ROLLBACK.md`, `OCR_QUALITY_OPTIMIZATION.md`, `RELEASE_CANDIDATE.md`, `ACCEPTANCE_CHECKLIST.md`, `OCR_TEST_REPORT.md`, `CHECKPOINT.md`, `PROGRESS.md`, `docs/5-CONFIGURATION/environment-reference.md` |

Không đổi: `tests/test_ocr_integration.py`, `tests/fixtures/ocr/`, `pyproject.toml`, `uv.lock`, `Dockerfile`,
entrypoint, mã Docling / Content Core.

## I. Trạng thái production và tài nguyên trên máy

**Production `chatbot5400-version02` — không bị đụng tới.** So sánh trước/sau Phase 9A
(`evidence/phase9a/preflight/production-{before,after}.txt`):

| | Trước | Sau |
|---|---|---|
| `open_notebook` container ID | `4af860cc7335…` | giống hệt |
| `surrealdb` container ID | `a50b689a4c41…` | giống hệt |
| Image ứng dụng | `sha256:7d26c1203a65…` (`chatbot5400:local`) | giống hệt |
| Thời điểm start | 2026-11-12 14:41 UTC | giống hệt |
| Restart count | 0 / 0 | 0 / 0 |
| `/health` | 200 | 200 |
| Mount (bind `notebook_data`, `surreal_data`; 2 volume của DB) | — | giống hệt |
| Volume có trước phase (38) | — | còn đủ 38, 0 volume mất |

Không dừng, không restart, không sửa compose / `.env` production; không xóa volume, image, workspace, evidence,
model cache; không `docker system prune`; không ngắt Internet máy chủ; không sửa firewall; không truy cập dữ liệu
thật. Chỉ đọc cấu trúc compose production (tên service, image, mount) và **tên** biến môi trường để soạn kế hoạch;
không đọc giá trị bí mật.

**Container nghiệm thu còn sót: không có** (`docker ps -a` chỉ còn 2 container production và 2 container
`branch-*` không liên quan; không còn mạng `ocraccept*`).

**Tài nguyên nghiệm thu trên máy — chưa dọn, chờ phê duyệt:**

| Thành phần | Hiện có | Ghi chú |
|---|---|---|
| Thư mục `/home/admin/cb5400-ocr-accept/work/` | 20 thư mục, 41 GB (dữ liệu thuộc root) | mỗi lượt Docker acceptance một thư mục; Phase 9A thêm 2 |
| Image `chatbot5400:ocr-accept` / `-old` / `-notess` | 2,6 + 2,5 + 2,5 GB | image nghiệm thu |
| Image `node:22-slim` | 0,3 GB | chạy test frontend |
| Volume ẩn danh do nghiệm thu tạo | 36 (8B: 14, 8C: 2, 8D: 16, 9A: 4) | danh sách: `acceptance-anonymous-volumes.txt`, `evidence/phase8c…9a/preflight/anonymous-volumes-created-in-*.txt` |
| Build cache Docker | ~40 GB | |
| Worktree `baseline-8b-src`, `hf-cache`, `ocr-data`, `evidence/`, các bundle | nhỏ | giữ làm bằng chứng |
| Ổ đĩa trống | 311 GB → 300 GB trong Phase 9A | |

Image `chatbot5400:local` và `chatbot5400:rollback-pre-v1.0.4-…` là của production — **không** thuộc danh sách dọn.

## J. Git bundle

| Bundle | Nội dung | Trạng thái |
|---|---|---|
| `/home/admin/cb5400-ocr-accept/phase9a-backup.bundle` | `release/ocr-engine-manager-rc1`, `local/ocr-phase8c`, `local/ocr-phase8b` — toàn bộ lịch sử Phase 0 → 9A | tạo mới, đã `git bundle verify` |
| `phase8b-backup.bundle`, `phase8c-backup.bundle`, `phase8d-backup.bundle` | các mốc trước | giữ nguyên, không ghi đè |

Khôi phục từ bundle trên máy khác: `git clone phase9a-backup.bundle -b release/ocr-engine-manager-rc1 <thư mục>`.

## K. Branch Release Candidate

| | |
|---|---|
| Branch | `release/ocr-engine-manager-rc1` — tạo mới từ HEAD của `local/ocr-phase8c` (cùng commit) |
| Kế thừa | Đủ Phase 0 → 9A: `5e04227` (production) → `45e2254` (RC trước nghiệm thu) → `f172645` (8B) → `16fc623` (8C) → `cfb08de` (8D) → `3288a73`, `d671218` (9A) → commit tài liệu cuối. Đã kiểm bằng `git merge-base --is-ancestor` |
| Commit | HEAD của branch; SHA đầy đủ ghi trong `evidence/phase9a/commits.txt`. Mã được kiểm thử ở `d671218`; commit sau đó chỉ thêm tài liệu |
| Trên GitHub trước đó | Chưa có branch tên này (`git ls-remote`): không ghi đè gì |
| Kiểm tra nội dung | Không có bí mật / token (quét mẫu trên toàn diff `5e04227..HEAD`: 0 kết quả); không model weights, cache, wheel, database, file backup, bundle, tài liệu ngân hàng, evidence. File nhị phân thêm mới: 7 PDF fixture tổng hợp, 1 ảnh mẫu tổng hợp, 2 ảnh chụp giao diện (≤ 0,55 MB) |
| Tag phát hành | Không tạo |
| `main` | Không push, không merge |

**Trạng thái push: CHƯA PUSH — bị chặn do thiếu quyền.** Máy chủ này không có thông tin xác thực GitHub:
`git push` (thử `--dry-run`) trả `could not read Username for 'https://github.com'`; không có credential helper,
không có SSH key được GitHub chấp nhận, không có `gh`. Theo yêu cầu, không tự lấy hay yêu cầu token bằng cách
không an toàn. Branch đã sẵn sàng cục bộ và nằm trong bundle.

Để push (chỉ branch này, không force), chủ dự án chọn một trong hai:

```bash
# (a) trên máy chủ này, sau khi tự đăng nhập GitHub theo cách của đơn vị (credential helper / SSH key / gh):
cd /home/admin/cb5400-ocr-accept/src
git push origin release/ocr-engine-manager-rc1:refs/heads/release/ocr-engine-manager-rc1

# (b) trên máy đã có quyền: sao chép phase9a-backup.bundle sang, rồi
git clone phase9a-backup.bundle -b release/ocr-engine-manager-rc1 rc1 && cd rc1
git remote set-url origin https://github.com/nghoainam1902ps4-lgtm/ChatBot5400-Version02.git
git push origin release/ocr-engine-manager-rc1:refs/heads/release/ocr-engine-manager-rc1
```

## L. Điều kiện còn thiếu trước production

1. **Benchmark tài liệu nghiệp vụ thật** do chủ dự án tự chọn tài liệu và tự chạy tại chỗ
   ([OCR_REAL_DOCUMENT_BENCHMARK.md](OCR_REAL_DOCUMENT_BENCHMARK.md)). **Chưa thực hiện.** Mọi số liệu đến nay
   là trên dữ liệu tổng hợp; không tài liệu thật nào được tìm, đọc hay đo.
2. **Backup nhất quán và kiểm tra restore** (kế hoạch §3–4). Chưa thực hiện.
3. **Phê duyệt** kế hoạch triển khai, cửa sổ bảo trì và cấu hình URL ingestion tắt.
4. **Kiểm tra trên môi trường đích**: smoke test sau triển khai (kế hoạch §8).
5. Đánh giá các hạn chế dev-default cho môi trường đích: CORS mở, xác thực, container chạy root.
6. `offline_verified` trên máy đích nếu vận hành offline (chỉ mới kiểm chứng trong container cô lập).
7. Push branch RC lên GitHub (mục K) và review của chủ dự án trước khi merge.

## M. Kế hoạch triển khai và rollback

- Kế hoạch: [OCR_PRODUCTION_DEPLOYMENT_PLAN.md](OCR_PRODUCTION_DEPLOYMENT_PLAN.md) — hiện trạng và đích, backup
  lạnh, kiểm tra restore trên stack cô lập, cấu hình RC (URL ingestion tắt), cập nhật khi có Internet, chuẩn bị
  Tesseract Best và xác minh offline, 13 bước smoke test, tiêu chí dừng, rollback mã / rollback dữ liệu, khôi
  phục dịch vụ.
- Checklist: [OCR_PRODUCTION_CHECKLIST.md](OCR_PRODUCTION_CHECKLIST.md).
- Rollback: `OCR_ROLLBACK.md`. Không có migration; rollback mã giữ nguyên dữ liệu; bản cũ bỏ qua dữ liệu OCR.
  Lưu ý: bản cũ không có công tắc URL ingestion.
- **Chỉ là kế hoạch.** Phase 9A không backup dữ liệu production, không restart, không sửa compose hay `.env`,
  không triển khai.
