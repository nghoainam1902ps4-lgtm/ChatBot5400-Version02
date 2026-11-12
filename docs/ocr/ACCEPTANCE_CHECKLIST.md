# Acceptance Checklist

Trạng thái: **PASS** (có bằng chứng thực tế) · **FAIL** · **NOT VERIFIED** (chưa chạy được thực tế).

| Tiêu chí | Trạng thái | Bằng chứng |
|---|---|---|
| OCR Engine Manager có trong Settings | PASS | `settings/page.tsx` + `OcrEngineManager.tsx`; test `page.test.tsx` (admin thấy, user thường không); screenshot `docs/ocr/images/` |
| Đúng 3 engine, 4 lựa chọn | PASS | `catalog.ENGINE_IDS`; `TestCatalog::test_exactly_three_engines_four_choices`; UI test 4 dòng |
| Tất cả lựa chọn hỗ trợ CPU | PASS | Benchmark chạy CPU-only cả 4 (RapidOCR qua backend onnx — xem ghi chú benchmark); EasyOCR `use_gpu=False` (`test_easyocr_forced_to_cpu_and_offline_models`) |
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
| Regression: không lỗi mới | PASS (trong phạm vi chạy được) | So sánh với commit gốc: 0 lỗi mới sau sửa; 4 file cần tiktoken NOT VERIFIED (mạng) |
| Backend test | PASS | 114 test OCR + `test_graphs.py` 22/22 + suite chung (Test Report §3) |
| Frontend build | PASS | `npm run build` |
| Docker test | NOT VERIFIED | Mạng Cloud chặn ghcr blob / Debian apt; Docker Hub 429. Script `scripts/ocr/docker-acceptance.sh` |
| Security review | PASS | `OCR_SECURITY_REVIEW.md` + review độc lập (§ CHECKPOINT) |
| Rollback có tài liệu | PASS | `OCR_ROLLBACK.md` |
| Dữ liệu người dùng không bị xoá | PASS | Không migration; không lệnh xoá volume; script Docker dùng thư mục tạm riêng |
| Không triển khai production | PASS | Chỉ push branch `claude/friendly-mendel-a2b6m5` |
| Full pipeline Docling với từng engine | NOT VERIFIED | huggingface.co bị chặn; `OCR_FULL_PIPELINE=1 pytest tests/test_ocr_integration.py` trên máy thật |
| RapidOCR backend torch (cấu hình production) chạy thực | NOT VERIFIED | modelscope.cn bị chặn trong Cloud |
