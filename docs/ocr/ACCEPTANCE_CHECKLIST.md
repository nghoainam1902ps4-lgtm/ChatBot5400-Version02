# Acceptance Checklist

Trạng thái: **PASS** (có bằng chứng thực tế) · **FAIL** · **NOT VERIFIED** (chưa chạy được thực tế).

| Tiêu chí | Trạng thái | Bằng chứng |
|---|---|---|
| OCR Engine Manager có trong Settings | PASS | `settings/page.tsx` + `OcrEngineManager.tsx`; test `page.test.tsx` (admin thấy, user thường không); screenshot `docs/ocr/images/` |
| Đúng 3 engine, 4 lựa chọn | PASS | `catalog.ENGINE_IDS`; `TestCatalog::test_exactly_three_engines_four_choices`; UI test 4 dòng |
| Tất cả lựa chọn hỗ trợ CPU | PASS | Tesseract/EasyOCR CPU (EasyOCR `reader.device == "cpu"` đo thật); RapidOCR: torch CPU trên production (`UV_TORCH_BACKEND=cpu`), trên máy GPU giữ hành vi cũ (CUDA) — opt-in `OCR_RAPIDOCR_FORCE_CPU` chỉ cho OCR (`TestCpuMode`) |
| Tiếng Việt cấu hình đúng (Tesseract, EasyOCR) | PASS | `fast/vie+fast/eng`, `best/vie+best/eng`, `vi+en`; `test_docling_uses_selected_engine_and_reads_vietnamese[*]` (CER, dấu ≥ 0.95/0.8) |
| RapidOCR tương thích ngược | PASS | Mặc định đi nguyên đường Content Core (`test_default_settings_use_content_core`, `test_default_config_keeps_content_core_path`); ghim đúng options Auto (`test_rapidocr_option_reproduces_docling_auto`) chống đổi ngầm sang EasyOCR |
| Layout giữ nguyên | PASS | `test_only_ocr_options_differ` (layout_options bằng nhau); probe `layout_heron` |
| TableFormer giữ nguyên | PASS | như trên (`table_structure_options` bằng nhau); probe `docling_tableformer (accurate)` |
| Không custom adapter | PASS | Chỉ dùng `RapidOcrOptions`/`TesseractCliOcrOptions`/`EasyOcrOptions`; không subclass `BaseOcrModel`; `allow_external_plugins=False` |
| Không sửa lõi Docling | PASS | Không file nào trong site-packages bị sửa; không monkey patch trong mã production |
| Cài đặt theo nhu cầu | PASS | Job `ocr_install_model` do admin kích hoạt; `test_install_queues_job_with_nonce`; cài thật §2.1 Test Report |
| Không tải engine lúc startup | PASS (mã) / NOT VERIFIED (Docker) | Entrypoint chỉ khôi phục runtime khi bật cờ, không tải model; kịch bản 1 của `docker-acceptance.sh` chưa chạy được trong Cloud |
| Persistent model storage | PASS (mã + FS) / NOT VERIFIED (Docker) | Model dưới `/app/data/ocr` (volume); cài lại dùng `existing`; restart/recreate trong Docker chưa chạy được |
| Runtime recovery | PASS (ngoài Docker) | `runtime ensure --offline` khôi phục tesseract (`dpkg`) + easyocr (wheel staged) thật; entrypoint gọi lệnh này |
| Offline installation | PASS | Bundle thật, mạng bị chặn, 4/4 ready; bundle giả mạo bị từ chối |
| Chuyển engine an toàn | PASS | Settings đọc lại mỗi job (`test_settings_reloaded_for_every_job`); activate từ chối engine chưa ready (`test_activate_refuses_not_ready_engine_and_keeps_current`); chạy Fast+Best đồng thời |
| Gỡ model đang dùng bị chặn | PASS | `test_active_engine_cannot_be_removed`, `test_delete_active_model_refused`, UI ẩn nút |
| Regression: không lỗi mới | PASS (trong phạm vi chạy được) | Phase 8A: 1053 passed / 10 failed so với `e32eae8`: 951 passed / 10 failed — đúng 10 lỗi có sẵn, 0 lỗi mới; 4 file cần tiktoken NOT VERIFIED (mạng) |
| Backend test | PASS | Phase 7: 167 test OCR (+39 full pipeline NOT VERIFIED) + `test_graphs.py` 22/22 (Test Report §7.2) |
| Frontend build | PASS | `npm run build` |
| Docker test | NOT VERIFIED | Script viết lại (mạng internal, upgrade, rebuild thật, E2E API+worker) — chưa chạy: Docker Hub 429 / ghcr 403 / Debian apt 403 trong Cloud. Chạy theo `OCR_LOCAL_ACCEPTANCE.md` §5 |
| Security review | PASS | `OCR_SECURITY_REVIEW.md` (gồm Phase 7, 8A). Lỗ hổng `/api/commands/jobs` **đã sửa** ở Phase 8A (`docs/security/BACKGROUND_JOB_SECURITY.md`, 57 test) |
| Rollback có tài liệu | PASS | `OCR_ROLLBACK.md` |
| Dữ liệu người dùng không bị xoá | PASS | Không migration; không lệnh xoá volume; script Docker dùng thư mục tạm riêng |
| Không triển khai production | PASS | Chỉ push branch `claude/friendly-mendel-a2b6m5` |
| Full pipeline Docling với từng engine | NOT VERIFIED | Bộ nghiệm thu nghiêm ngặt 4 engine × 7 fixture có ground truth sẵn sàng; Cloud chặn huggingface.co. `OCR_LOCAL_ACCEPTANCE.md` §4.3 |
| RapidOCR backend torch (cấu hình production) chạy thực | NOT VERIFIED | modelscope.cn bị chặn trong Cloud |
| Khoá phiên bản dependency khi build/khởi động | PASS | Constraints từ `uv.lock` (Dockerfile/entrypoint/CLI); `uv pip compile` có `-c` ⇒ docling 2.129.0; entrypoint thật chạy với stub (`test_ocr_dependency_compat.py`) |
| Guard API nội bộ Content Core/Docling | PASS | Phiên bản + dấu vân tay mã nguồn khớp môi trường đã kiểm chứng; lệch ⇒ `incompatible` (12 test) |
| Parity hành vi với Content Core (title, MIME, URL, ảnh, OCR tắt, simple, cleanup, lỗi) | PASS | `test_ocr_docling_parity.py` (24) |
| Offline khôi phục runtime từ cache | PASS (ngoài Docker) | Mạng chặn: EasyOCR cài lại từ cache uv/gói staged với constraints |
| Upgrade từ phiên bản hiện tại (5e04227) giữ dữ liệu/settings | NOT VERIFIED | `docker-acceptance.sh` bước 0–1 (cần Docker có mạng) |
| Tài liệu nghiệm thu máy thật | PASS | `OCR_LOCAL_ACCEPTANCE.md`; 24 khối bash qua `bash -n`; ShellCheck sạch |

## Phase 8A — Bảo mật cuối, chuẩn bị online / vận hành offline

Test mô phỏng (mock/stub) **không** thay thế nghiệm thu runtime: tiêu chí runtime chỉ PASS khi đã
chạy thật.

| Tiêu chí | Trạng thái | Bằng chứng |
|---|---|---|
| `/api/commands/*` chỉ admin; submit tổng quát bị tắt | PASS | `api/routers/commands.py`; `test_background_job_security.py` (user thường 403 mọi route, admin bị từ chối submit tổng quát) |
| Worker không tin API: path traversal, xoá file ngoài uploads, SSRF qua redirect, id sai bảng | PASS | `job_input_guard.py`; 57 test với file canary trong tmp: ngoài uploads, `../`, symlink thoát, NUL; URL `file://`, metadata 169.254.169.254, redirect tới metadata |
| Không chạy pip/apt từ HTTP; web app không root mới; không mount Docker socket | PASS | prepare qua API không cài runtime (`--install-runtime` chỉ ở CLI); compose không đổi user/socket |
| Prepare online tải đúng phần thiếu, dùng lại model đã có | PASS (mã + test) / NOT VERIFIED (Docker) | `test_prepare_online_runs_online_then_local_only`, `test_prepare_offline_with_missing_model_fails_fast`, `test_prepare_never_installs_runtime`; Docker bước 2 (prepare lần 2: checksum không đổi) chưa chạy |
| Không báo OFFLINE READY chỉ từ file/checksum | PASS | `test_files_present_are_not_enough`, `test_online_check_alone_is_not_offline_ready` |
| Phân biệt OCR-only / full pipeline / local-only / offline thật | PASS (mã + test) | `readiness_status` (`ocr_ok`, `pipeline_ok`, `local_only_verified`, `offline_verified`); UI hiển thị riêng từng dòng |
| Kết quả lỗi thời sau cập nhật / mất cache / mất trọng số RapidOCR | PASS | `test_changed_dependencies_make_verdict_stale`, `test_cleared_docling_cache_makes_verdict_stale`, `test_pruned_docling_blobs_make_verdict_stale`, `test_lost_rapidocr_weights_make_verdict_stale`, `test_newer_failed_check_wins_over_older_offline_pass` |
| Chạy thật `prepare` khi model Docling không tải được ⇒ không báo sẵn sàng | PASS (Cloud, thật) | `prepare --engines tesseract_best` ⇒ `not_offline_ready` kèm lỗi Hugging Face chính xác, exit ≠ 0 |
| Thiếu model khi offline ⇒ lỗi rõ ràng, không treo, không fallback | PASS (mã + test) / NOT VERIFIED (E2E) | `explain_offline_failure` ⇒ `ValueError` (không retry); `test_content_process_fails_fast_without_retry`, `test_ordinary_url_errors_untouched` |
| RapidOCR lưu bền vững qua tham số chính thức | PASS (onnx, thật) / NOT VERIFIED (torch) | `Global.model_root_dir`; chạy offline với overlay onnxruntime: log RapidOCR "File exists and is valid" từ thư mục bền vững; torch cần modelscope (bị chặn) |
| RapidOCR mặc định không đổi | PASS | `test_default_unchanged`; mặc định vẫn đi Content Core |
| UI trạng thái sẵn sàng + nút Chuẩn bị / Kiểm tra (vi/en) | PASS | `ReadinessPanel`; 3 test UI; tsc/lint/vitest 404/build |
| Full pipeline 4 engine | NOT VERIFIED | huggingface.co / modelscope.cn 403 trong Cloud; `OCR_LOCAL_ACCEPTANCE.md` §4.3–4.4 |
| Docker: cập nhật online → chuẩn bị → offline (mọi engine) → restart offline → cập nhật online | NOT VERIFIED | Script hoàn chỉnh (`bash -n`, ShellCheck sạch, driver 9 test với stub); Docker Hub 429 / ghcr 403 / apt 403 |
| API + worker E2E thật | NOT VERIFIED | Tải SurrealDB binary bị chính sách phiên từ chối — không vượt qua |
| Regression so với `e32eae8` | PASS | 1053 passed / 10 failed vs 951 / 10, cùng 10 lỗi có sẵn |
| Review độc lập diff 8A | PASS | 8 phát hiện: 7 đã sửa kèm test, 1 giữ nguyên có lý do (`OCR_TEST_REPORT.md` §8.4) |
| Tài liệu `OCR_ONLINE_PREPARATION.md` (15 chủ đề), lệnh qua `bash -n` | PASS | `check_doc_commands.py` |

## Phase 8C — Chất lượng OCR và nghiệm thu cuối

| Hạng mục | Kết quả | Bằng chứng |
|---|---|---|
| Bảo toàn commit Phase 8B, bundle đã verify | PASS | `phase8b-backup.bundle` |
| Nguyên nhân gốc 15 bài, phân nhóm A–J | PASS | `OCR_FAILURE_ANALYSIS.md` |
| Không đổi ngưỡng / fixture / ground truth; không `xfail` / `skip` | PASS | diff `tests/test_ocr_integration.py`, `tests/fixtures/ocr` không đổi |
| Tesseract: bảng scan không còn bị lật; trang xoay 90/180/270° | PASS | `OCR_QUALITY_BENCHMARK.md` §2, §5 |
| Tesseract Best: trường khóa 1,00 trên fixture và holdout | PASS | như trên |
| Full pipeline lộ trình nhanh `FAIL == 0` | **FAIL** — 6 PASS / 3 FAIL (tiêu đề in đậm, giới hạn model) | `runs/ocr-acceptance-quick-8c.json` |
| Full pipeline 48 bài | 38 PASS / 10 FAIL / 0 NOT VERIFIED | `runs/ocr-acceptance-full-8c.json` |
| EasyOCR đạt ngưỡng trên scan 150 DPI | **FAIL** — giới hạn model | `OCR_FAILURE_ANALYSIS.md` §5.5 |
| RapidOCR trang xoay | PASS (8/8) | như trên |
| Holdout độc lập, chạy một lần, không regression | PASS | `holdout-baseline/`, `holdout-after/` |
| Docker: online → chuẩn bị → offline → restart offline → cập nhật → offline, 4 engine | PASS hạ tầng (72 PASS); 1 FAIL nội dung EasyOCR | `runs/docker-acceptance-full-8c.log` |
| Không tải lại model hợp lệ (checksum, cache HF không đổi) | PASS | như trên |
| Backend regression: không lỗi mới | PASS — 1211 / 10, cùng 10 lỗi của `main` | `runs/pytest-full-8c.txt` |
| Frontend lint / tsc / vitest / build | PASS — 0 error / 0 / 404 / OK | `runs/frontend-8c.txt` |
| Bảo mật trực tiếp | PASS — 16/16 | `runs/security-live-8c.json` |
| Review độc lập | PASS — 0 High; 3 Medium đã sửa | `OCR_PHASE8C_REPORT.md` §8 |
| Production không bị ảnh hưởng; không xóa volume | PASS | `preflight/production-{before,after}.txt` |

## Phase 8D — Kiểm tra phát hành cuối và phân loại chất lượng

Bộ gốc và bộ có điều kiện được báo **riêng**; bộ có điều kiện không thay thế bộ gốc.

| Hạng mục | Kết quả | Bằng chứng (`evidence/phase8d/`) |
|---|---|---|
| **A. Bộ gốc** 48 bài | 38 PASS / 10 FAIL / 0 NOT VERIFIED (không đổi) | `runs/ocr-acceptance-full-8d.json` |
| A. Lộ trình nhanh (Tesseract Best) `FAIL == 0` | **FAIL** — 6 PASS / 3 FAIL | `runs/ocr-acceptance-quick-8d.json` |
| 48 bài, fixture, ground truth, ngưỡng không đổi; không skip/xfail | PASS | `git diff 16fc623..HEAD -- tests/test_ocr_integration.py tests/fixtures` rỗng |
| **B. Có điều kiện** — Tesseract Best: critical 7/7, mọi FAIL gốc chỉ do KL-1 | **PASS** — 4 PASS + 3 PASS_WITH_KNOWN_LIMITATION | `runs/release-criteria.{json,md}` |
| B. Tesseract Fast | **FAIL** 2/7 (nhãn `Tổng cộng`); critical 7/7 | như trên |
| B. RapidOCR | PASS 7/7 | như trên |
| B. EasyOCR | **FAIL** 5/7; critical 2/7 | như trên |
| Công cụ có điều kiện không nới hơn dự định (sai số tiền, sai nhãn, mất chữ ⇒ FAIL) | PASS | `tests/test_ocr_release_criteria.py` (13) |
| `tesseract_gate.py`: 11 điều kiện của chủ dự án | PASS | `OCR_PHASE8D_REPORT.md` §2 |
| Gate không đổi kết quả nhận dạng (so byte với Tesseract thật) | PASS | `test_gate_does_not_change_recognition_output` |
| `pdf_prep.py`: file gốc, text layer, metadata, ảnh không đổi | PASS | `test_rotated_copy_keeps_text_layer_images_and_metadata` |
| Tọa độ sau xoay 90 / 180 / 270° | PASS — lệch ≤ 0,4 pt | `runs/coordinates-after-rotation.json` |
| Xử lý sync + async, 3 job song song, dọn file tạm | PASS | `runs/concurrency-live.json` |
| Readiness hết hiệu lực khi cấu hình chất lượng đổi | PASS | `test_readiness_fingerprint_follows_the_quality_configuration` |
| Trạng thái hướng trang báo đúng (không báo khả dụng khi thiếu Tesseract/osd) | PASS | unit test + Docker |
| RapidOCR / EasyOCR không cần Tesseract; không cài ngầm | PASS — cục bộ: RapidOCR trùng 7/7 với baseline 8B; Docker: 50 PASS / 1 FAIL (nội dung EasyOCR), không có binary Tesseract trước và sau | `runs/no-tesseract/`, `runs/docker-no-tesseract-8d.log` |
| Phân loại 4 lựa chọn trong catalog, API, giao diện vi/en, tài liệu vi/en | PASS | `OCR_ENGINE_MANAGER.md` §8, ADR-013 |
| EasyOCR: cảnh báo xác nhận trước khi bật; không mặc định; không fallback | PASS | `OcrEngineManager.test.tsx`, `test_quality_tiers` |
| Docker lộ trình nhanh (Tesseract Best) | PASS — 42 PASS / 0 FAIL (lượt đầu 41 / 1 do lỗi script P8D-1, đã sửa) | `runs/docker-quick-8d.log` |
| Docker 4 engine, online → offline → restart → update → offline | Hạ tầng PASS (74 PASS); **1 FAIL nội dung EasyOCR** | `runs/docker-full-8d.log` |
| RapidOCR persistent, backend torch | PASS — 42 / 0 | `runs/docker-rapidocr-persistent-8d.log` |
| Backend regression | PASS — 1239 / 10, cùng 10 lỗi của `main` | `runs/pytest-full-8d.txt` |
| Frontend lint / tsc / vitest / build | PASS — 0 error / 0 / 408 / OK | `runs/frontend-8d.txt` |
| Bảo mật: test + kiểm tra trực tiếp | PASS — 142 passed; 16/16 | `runs/security-live-8d.json` |
| SSRF qua redirect đã khắc phục | **KHÔNG** — rủi ro còn lại, cần biện pháp được duyệt | `OCR_SECURITY_REVIEW.md` |
| `offline_verified` ngoài Docker | NOT VERIFIED — cần ngắt mạng máy chủ | — |
| Production không bị ảnh hưởng; không xóa volume/image/cache | PASS | `preflight/production-{before,after}.txt` |

## Phase 9A — Cổng bảo mật cuối và Release Candidate

| Hạng mục | Kết quả | Bằng chứng (`evidence/phase9a/`) |
|---|---|---|
| Công tắc URL ingestion: mặc định tắt; thiếu / sai giá trị ⇒ tắt | PASS | `test_switch_parsing` |
| API tạo nguồn URL bị chặn (multipart sync + async, JSON) | PASS — 403 | `tests/test_url_ingestion_switch.py` |
| Retry / xử lý lại nguồn URL cũ bị chặn | PASS — 403 | như trên |
| Worker và graph từ chối trước mọi hoạt động mạng | PASS | như trên (fixture chặn DNS / kết nối) |
| Admin cũng bị chặn | PASS | như trên + kiểm tra trực tiếp |
| Nguồn URL cũ vẫn đọc được nội dung đã lưu | PASS | như trên |
| Upload file, nhập văn bản, OCR không bị ảnh hưởng | PASS | như trên + `runs/url_switch_live-9a.json` |
| Khi bật: chính sách kiểm tra URL hiện có vẫn áp dụng | PASS | như trên |
| LLM, embedding, chuẩn bị model không đọc công tắc | PASS | `test_switch_is_only_used_by_url_ingestion_code` |
| Giao diện: tab URL vô hiệu hóa theo backend, thông báo vi/en | PASS | `SourceTypeStep.test.tsx` |
| Kiểm tra trực tiếp trên stack cô lập (biến không đặt ⇒ tắt) | 7/7 PASS | `runs/url_switch_live-9a.json` |
| Bộ gốc 48 bài (chạy lại trên mã cuối) | 38 PASS / 10 FAIL / 0 NOT VERIFIED — không đổi | `runs/ocr-acceptance-full-9a.json` |
| Lộ trình nhanh gốc | 6 PASS / 3 FAIL — không đổi | `runs/ocr-acceptance-quick-9a.json` |
| Tiêu chí có điều kiện, Tesseract Best | 7/7 (4 PASS + 3 PASS kèm KL-1), critical 7/7 | `runs/release-criteria-9a.json` |
| Docker quick (Tesseract Best), URL ingestion tắt | 42 PASS / 0 FAIL | `runs/docker-quick-9a.log` |
| Backend regression | PASS — 1288 / 10, cùng 10 lỗi của `main` | `runs/pytest-full-9a.txt` |
| Frontend lint / tsc / vitest / build | PASS — 0 error / 0 / 411 / OK | `runs/frontend-9a.txt` |
| Bảo mật: test + trực tiếp | PASS — 185 passed; 16/16 | `runs/security_live-9a.json` |
| Review độc lập cuối `45e2254..HEAD` | PASS — 0 High, 0 Medium | `OCR_PHASE9A_REPORT.md` §G |
| Không bí mật, model, cache, wheel, DB, tài liệu thật trong branch | PASS | `OCR_PHASE9A_REPORT.md` §K |
| SSRF đã sửa triệt để | **KHÔNG** — giảm thiểu khi tắt, còn tồn tại khi bật | `BACKGROUND_JOB_SECURITY.md` §5–6 |
| Benchmark tài liệu nghiệp vụ thật | **CHƯA THỰC HIỆN** — việc của chủ dự án | `OCR_REAL_DOCUMENT_BENCHMARK.md` |
| Backup / restore / triển khai production | **CHƯA THỰC HIỆN** — chỉ có kế hoạch | `OCR_PRODUCTION_DEPLOYMENT_PLAN.md` |
| Production không bị ảnh hưởng | PASS — container ID, image, thời điểm start, restart (0), mount giống hệt; `/health` 200 | `preflight/production-{before,after}.txt` |
