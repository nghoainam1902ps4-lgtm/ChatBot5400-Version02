# OCR Engine Manager — Security Review (Phase 6)

Phạm vi: toàn bộ diff của tính năng (`open_notebook/ocr/`, `api/routers/ocr.py`,
`api/ocr_service.py`, `commands/ocr_commands.py`, thay đổi ở `open_notebook/graphs/source.py`,
`content_settings.py`, Dockerfile/entrypoint/compose, frontend OCR Engine Manager).

| # | Hạng mục | Kết luận | Bằng chứng / biện pháp |
|---|---|---|---|
| 1 | Command injection | Không có | Mọi `subprocess.run` dùng list, `shell=False` (test `test_docling_probe_script_is_static` kiểm tra không có `shell=True` trong `runtime.py`); spec gói cố định (`easyocr==1.7.2`, `tesseract-ocr`); `engine_id` chỉ chấp nhận giá trị trong catalog; Docling tự sanitize đối số Tesseract. Không có input nào từ frontend đi vào lệnh. |
| 2 | Path traversal | Chặn | `paths.safe_child()` cho mọi đường dẫn model/bundle; tên manifest từ `engine_id` đã kiểm tra (`test_state_file_name_cannot_be_injected`, `test_safe_child_blocks_traversal`). |
| 3 | Symlink escape | Chặn | Model là symlink ⇒ `corrupted`; thư mục cha symlink thoát volume ⇒ từ chối (`test_symlinked_model_rejected`, `test_safe_child_blocks_symlink_escape`); bundle/staged package không chấp nhận symlink. |
| 4 | SSRF | Không có | Không endpoint nào nhận URL. URL tải chỉ lấy từ `catalog.py`, chỉ `https`, host allowlist kiểm tra ở **mỗi** bước redirect (`test_host_allowlist` gồm 169.254.169.254, `file://`, `http://`). |
| 5 | Archive traversal | Chặn | Chỉ giải nén **một** member đúng tên, không có `/`, kích thước đúng bằng giá trị ghim, giới hạn khi copy (`test_zip_extraction_only_expected_member`). |
| 6 | Cài package tuỳ ý | Không có | Web không chạy pip/apt. CLI/entrypoint chỉ cài spec ghim; gói staged (wheel/.deb) chỉ được cài khi digest danh sách checksum khớp `OCR_TRUSTED_WHEELS_SHA256`/`OCR_TRUSTED_DEBS_SHA256` ghim ngoài volume (`test_staged_package_verification`, kiểm chứng thật: thiếu pin ⇒ từ chối); wheel `easyocr` phải khớp SHA-256 ghim trong mã (`test_pinned_easyocr_wheel_enforced`). Không có upload bundle qua web. |
| 7 | Toàn vẹn model | Bảo đảm | SHA-256 + kích thước ghim cho mọi tệp; staging + `os.replace` nguyên tử; tệp sai không bao giờ xuất hiện trong `models/` (`test_tampered_bundle_never_becomes_visible`); bundle tráo trọng số rồi tính lại checksum vẫn bị từ chối (`test_consistent_but_unpinned_model_rejected`); trạng thái `ready` tính lại từ checksum mỗi lần. |
| 8 | Quyền API | Admin | Router `/api/ocr` gắn `Depends(require_admin)` (cơ chế có sẵn); test 401 không token / 403 role `user` cho mọi endpoint ghi (`TestOcrApiRequiresAdmin`). `PUT /api/settings` không nhận `docling_ocr_engine`. |
| 9 | Bỏ qua quyền qua `/api/commands/jobs` | Đã chặn cho OCR | Endpoint chung (có sẵn) cho mọi user submit mọi command. Command OCR yêu cầu nonce ngẫu nhiên 256-bit do API admin ghi vào manifest, so sánh `hmac.compare_digest`, dùng một lần (`TestCommandNonce`). **Rủi ro có sẵn ngoài phạm vi**: các command khác vẫn bị ảnh hưởng — đề xuất khắc phục riêng. |
| 10 | Race / đồng thời | Xử lý | File lock không chặn theo engine + lock riêng cho tệp dùng chung (osd); `asyncio.Lock` trong API; API từ chối cài trùng khi job đang chạy; job chết được phát hiện (stale) và cho phép thử lại; ghi manifest nguyên tử. `TESSDATA_PREFIX` là hằng số theo process — không đổi biến môi trường theo job (`test_concurrent_jobs_with_different_engines_do_not_interfere` chạy Fast+Best song song). |
| 11 | Gỡ model đang dùng | Chặn | `delete_models` từ chối engine đang active/đang cài; CLI từ chối khi không xác định được engine active (DB không truy cập được). Không xoá osd khi engine kia còn dùng; không đụng Layout/TableFormer/RapidOCR/tesseract binary. |
| 12 | Log dữ liệu nhạy cảm | Không | Log chỉ có engine, class, thời gian, đường dẫn model, URL model công khai. Không log nội dung tài liệu. Bài kiểm tra chỉ dùng ảnh mẫu tổng hợp; văn bản kết quả lưu trong manifest là của ảnh mẫu. |
| 13 | Secrets | Không có | Không thêm secret; `.env.example` chỉ có biến không bí mật. |
| 14 | Gửi tài liệu ra ngoài | Không | Ba engine chạy cục bộ; EasyOCR `download_enabled=False`. Lưu ý (có sẵn, không đổi): RapidOCR backend torch tự tải **trọng số model** (không phải tài liệu) từ modelscope.cn ở lần dùng đầu. |
| 15 | Docker socket / root | Không thêm | Không mount Docker socket. Image hiện tại vốn chạy root (có sẵn, ngoài phạm vi); tính năng không thêm đặc quyền; apt chỉ chạy ở build arg hoặc entrypoint/CLI do operator bật. |
| 16 | DoS do tải | Giới hạn | Kích thước tải bị chặn theo giá trị ghim; kiểm tra dung lượng trống trước khi tải; một job cài/engine. |
| 17 | Subprocess probe Docling | An toàn | Script cố định trong mã (`runtime._DOCLING_PROBE`), không nội suy input, timeout 180 s. |

## Giấy phép

| Thành phần | Giấy phép | Phân phối trong bundle |
|---|---|---|
| tessdata_fast / tessdata_best 4.1.0 | Apache-2.0 | Được phép |
| Tesseract 5.x (gói Debian) | Apache-2.0 | Được phép |
| EasyOCR 1.7.2 + craft_mlt_25k + latin_g2 | Apache-2.0 | Được phép |
| Phụ thuộc wheel (scikit-image BSD-3, opencv-python-headless Apache-2.0/MIT, python-bidi LGPL-3.0, ninja Apache-2.0, tifffile BSD-3, lazy-loader BSD-3) | xem metadata wheel | Được phép phân phối nội bộ; giữ nguyên tệp license trong wheel. python-bidi (LGPL) dùng dạng thư viện động, không sửa đổi. |
| RapidOCR / PP-OCR | Apache-2.0 | Không đóng gói (dùng gói có sẵn) |

## Rủi ro còn lại

1. Wheel phụ thuộc (ngoài `easyocr`) và `.deb` được tin theo bundle digest / digest ghim do
   operator đối chiếu qua kênh tin cậy. Cài online `easyocr==1.7.2` dựa vào TLS của PyPI (không
   ghim hash phụ thuộc).
4. Gỡ model của engine vừa bị bỏ kích hoạt trong lúc một job xử lý nguồn còn đang chạy với engine
   đó có thể làm job đó lỗi (job lỗi rõ ràng, có thể xử lý lại). Khuyến nghị: gỡ model khi hàng
   đợi trống.
5. Khi bật cờ Tesseract mà không có mạng và không có gói staged, entrypoint chờ `apt-get update`
   hết thời gian rồi mới khởi động (không chặn boot). Dùng build arg hoặc `OCR_OFFLINE=true`.
2. ~~Lỗ hổng phân quyền có sẵn của `/api/commands/jobs`~~ — **đã sửa ở Phase 8A** (xem mục Phase 8A).
3. Image chạy root (có sẵn).

## Phase 7 — Bổ sung

| # | Tình huống | Đánh giá | Biện pháp / bằng chứng |
|---|---|---|---|
| 18 | Job OCR đang chạy, admin chuyển engine rồi gỡ model cũ | Job lấy snapshot Settings lúc bắt đầu ⇒ vẫn dùng engine cũ; Tesseract đọc traineddata **mỗi trang** ⇒ gỡ giữa chừng làm job lỗi | API từ chối gỡ khi có `process_source` đang `running` hoặc test đang chờ; không truy vấn được DB ⇒ từ chối (D-17). `test_delete_refused_while_documents_processing`, `test_delete_refused_while_engine_test_pending` |
| 19 | Nhiều worker cùng tải / cài / gỡ | `flock` theo engine + lock riêng tệp dùng chung (osd, có chờ); ghi model bằng `os.replace` nguyên tử; job trùng ⇒ `LockBusy` ⇒ `failed` có thể thử lại; API đối chiếu job đã kết thúc | Hợp lệ khi các worker dùng chung volume trên **cùng máy** (flock). Volume mạng (NFS) không bảo đảm flock ⇒ chỉ chạy một worker cài đặt |
| 20 | Settings thay đổi đồng thời | `ContentSettings.update()` ghi toàn bộ bản ghi (có sẵn, cũng áp dụng cho `/api/settings`) ⇒ hai admin sửa cùng lúc có thể mất một thay đổi | Rủi ro thấp (chỉ admin); job xử lý đọc snapshot nhất quán. Ghi nhận, không đổi trong phạm vi này |
| 21 | Model được cập nhật khi đang xử lý PDF | Cài/sửa model: staging + checksum + `os.replace` ⇒ tiến trình đang đọc thấy inode cũ hoặc mới, nội dung giống hệt (sha256 ghim) | An toàn; EasyOCR nạp trọng số vào RAM khi khởi tạo |
| 22 | Nguồn URL đi qua lớp OCR mới | Cùng URL đã qua `validate_url()` ở API; tải bằng chính `_download_remote_file` của Content Core (aiohttp, theo redirect như trước), thêm 1 HEAD như Content Core vốn làm; tệp tạm luôn bị xoá (kể cả khi lỗi) | Không thêm bề mặt SSRF mới; `test_url_output_and_cleanup_match_content_core`, `test_url_temp_file_removed_when_conversion_fails`. Rủi ro có sẵn: worker không kiểm tra lại URL — xem `OCR_COMMANDS_JOBS_RISK.md` |
| 23 | Dependency runtime bị thay đổi | Container mới trước đây cài Docling mới nhất (2.150) ⇒ hành vi khác bản đã kiểm thử | Constraints từ `uv.lock` + guard phiên bản/dấu vân tay (D-14); override phải tường minh; gói staged cần digest ghim |
| 24 | `POST /api/commands/jobs` (có sẵn) | **Cao**: user thường có thể chạy `process_source` với `file_path`/`delete_source` ⇒ đọc/xoá file tuỳ ý dưới quyền root, SSRF; các command khác ⇒ chi phí/ghi dữ liệu | Không sửa trong Phase 7 (ngoài phạm vi). Phân tích + phương án: `OCR_COMMANDS_JOBS_RISK.md`. **Khuyến nghị bắt buộc xử lý trước production** |

## Phase 8A — Bảo mật cuối

| # | Tình huống | Đánh giá | Biện pháp / bằng chứng |
|---|---|---|---|
| 25 | `/api/commands/jobs` (#24): user thường chạy `process_source` với `file_path` / `delete_source` / URL tuỳ ý | **Đã sửa** | Router `commands` chỉ admin; submit tổng quát bị tắt (allowlist rỗng) kể cả với admin; list / status không lộ payload. `tests/test_background_job_security.py` |
| 26 | Worker tin dữ liệu job (phòng thủ nhiều lớp) | **Đã sửa** | `job_input_guard`: `realpath` nằm trong `UPLOADS_FOLDER`; xoá chỉ trong uploads (symlink: xoá link, không xoá đích); `validate_url()` + pre-check từng hop redirect (tối đa 5; lần tải thật vẫn tự theo redirect: rủi ro còn lại); id đúng bảng; `process_source` chỉ nhận file / URL trùng asset của source. Test dùng file canary trong thư mục tạm |
| 27 | Job prepare / readiness qua API | Không cài runtime (không `pip` / `apt` từ HTTP); không nhận tham số nào ngoài engine id (catalog); chạy tiến trình con `shell=False`, argv cố định | `test_prepare_never_installs_runtime`; nonce riêng cho mỗi command (`test_commands_require_their_own_nonce`) |
| 28 | Proxy chết trong kiểm tra `local_only` | Chỉ áp dụng trong tiến trình con kiểm tra; không đổi mạng của app hay môi trường | `_child_env` |
| 29 | Nhập trọng số RapidOCR vào thư mục bền vững | Chỉ file có tên và SHA-256 khớp `default_models.yaml` của RapidOCR; bỏ qua symlink; ghi nguyên tử | `test_import_copies_only_checksum_valid_weights` |
| 30 | Lỗi offline lộ thông tin | Thông báo cố định, không chứa đường dẫn nội bộ hay token | `explain_offline_failure` |

Rủi ro còn lại (ghi trong `docs/security/BACKGROUND_JOB_SECURITY.md` §5):

- **DNS rebinding:** có cửa sổ giữa lúc worker kiểm tra URL và lúc Content Core tải (cửa sổ này đã có
  từ trước ở API).
- **Host nội bộ:** vẫn tới được, theo thiết kế (Ollama nội bộ).
- **Image chạy root:** có sẵn, không đổi.

## Phase 8C — Chất lượng OCR

Bề mặt mới: hai module (`pdf_prep.py`, `tesseract_gate.py`), không endpoint, không job, không quyền mới.

| Điểm | Đánh giá |
|---|---|
| Tiến trình con | `subprocess.run` dạng danh sách tham số, không `shell=True`. Tham số cố định; đường dẫn ảnh là file tạm do ứng dụng tạo. Tên file người dùng tải lên chỉ đi qua `Path(path).name` bên trong thư mục `mkdtemp` riêng. |
| Binary được chạy | Gate chạy `OCR_TESSERACT_REAL`, biến do ứng dụng đặt từ `OCR_TESSERACT_CMD`/PATH (cấu hình của người vận hành, như trước). Người dùng không tác động được. |
| File tải lên | Không bao giờ bị sửa (test so SHA-256). Bản sao đã xoay nằm trong thư mục tạm quyền riêng, xóa ở mọi đường thoát của `convert_document`. Nếu worker bị kill giữa chừng, thư mục `ocr-prep-*` có thể sót lại trong thư mục tạm — rủi ro thấp, cùng mức với file tạm của Docling. |
| PDF độc hại / hỏng / có mật khẩu | pypdfium2 (đã là dependency của Docling) mở file; mọi lỗi → bỏ qua bước chuẩn bị, chuyển đổi như trước. Không thêm parser mới. |
| Từ chối dịch vụ | Dò hướng giới hạn 200 trang/tài liệu, 30 giây/trang, ảnh render tối đa 4000 px mỗi cạnh. Giới hạn kích thước upload hiện có vẫn áp dụng. |
| Log / metadata | Chỉ ghi số trang đã xoay, scale, DPI. Không ghi nội dung OCR. |
| Biến môi trường | Giá trị không hợp lệ (`nan`, âm, ngoài 0–1) → dùng mặc định. |
| Mạng | Không có request mạng mới; không tải gì thêm (dùng `osd.traineddata` đã cài). |

Review độc lập diff Phase 8C: 0 High; 3 Medium và các điểm Low đã xử lý ở `755b637`
(`OCR_PHASE8C_REPORT.md` §8). Kiểm tra bảo mật trực tiếp lặp lại trên stack nghiệm thu: xem báo cáo.

## Phase 8D — Review trước phát hành

### `tesseract_gate.py` (đã được chủ dự án chấp nhận có điều kiện)

| Yêu cầu | Kết quả | Bằng chứng |
|---|---|---|
| Không kế thừa `BaseOcrModel`, không thay Tesseract, không đổi thuật toán nhận dạng | Đạt | File 135 dòng, chỉ thư viện chuẩn; không import Docling |
| Không sửa Docling / Content Core / site-packages, không monkey patch | Đạt | Đặt qua `TesseractCliOcrOptions.tesseract_cmd` |
| Không xử lý văn bản OCR, không từ khóa, không hardcode fixture | Đạt | `test_gate_holds_no_text_or_fixture_knowledge` |
| Chuyển tiếp tham số, exit code, stdout, stderr | Đạt | `test_gate_process_passes_other_calls_through`; so byte-với-byte với Tesseract thật (`test_gate_does_not_change_recognition_output`: TSV, `--version`, `--list-langs`) |
| Timeout | Đạt | Lệnh OSD giới hạn 120 s → exit 124, Docling coi là OSD lỗi và OCR tiếp; lệnh khác `exec` thẳng (như trước) |
| Command injection | Đạt | Không `shell=True`; tham số dạng danh sách, do Docling tạo |
| Đường dẫn binary | Đạt | `OCR_TESSERACT_REAL` do ứng dụng đặt từ `OCR_TESSERACT_CMD`/PATH — cấu hình của người vận hành |
| Không đệ quy gọi lại chính nó | Đạt | exit 126 (`test_gate_refuses_to_call_itself`) |
| Frontend không truyền được command | Đạt | Không trường nào trong `OcrConfig` / `OcrConfigUpdate` (`test_tesseract_cmd_never_comes_from_a_request`) |
| Không lỗi tọa độ sau xoay | Đạt | Gate chỉ đổi OSD thành "đứng thẳng"; Docling tự quy đổi tọa độ như khi OSD trả 0 |
| Rollback | Đạt | `OCR_TESSERACT_OSD_GATE=false`; gate không chạy được ⇒ tự gọi thẳng Tesseract |

### `pdf_prep.py`

| Yêu cầu | Kết quả | Bằng chứng |
|---|---|---|
| Chỉ xử lý bản tạm, không sửa file gốc | Đạt | SHA-256 trước/sau |
| Không rasterize, giữ text layer, ảnh, MediaBox, metadata | Đạt | `test_rotated_copy_keeps_text_layer_images_and_metadata` (90/180/270°) |
| Không sai bbox, không hỏng bảng | Đạt | bbox lệch ≤ 0,4 pt so với bản đứng thẳng; bảng cùng hình dạng (`runs/coordinates-after-rotation.json`) |
| Dọn file tạm | Đạt | unit test + kiểm tra trên container: 3 job song song + 1 job sync, không sót `ocr-prep-*` |
| Không cài / tải Tesseract ngầm | Đạt | Docker image không có Tesseract: không xuất hiện binary sau khi xử lý |

### SSRF qua redirect — rủi ro CÒN LẠI (D-28)

Không thay đổi trong Phase 8C/8D. Kiểm tra URL của worker là pre-check; Content Core / Docling tải lại và
tự đi theo redirect, nên redirect khác ở lần tải thật và DNS rebinding không bị chặn. **Chưa khắc phục.**
Biện pháp đề xuất cho môi trường ngân hàng (chọn ít nhất một, cần chủ dự án phê duyệt):

1. Tắt URL ingestion với nguồn không tin cậy bằng cơ chế thực thi ở backend (từ chối `url` trong
   `content_process` và ở API nguồn theo cấu hình). Chưa có trong mã; là một thay đổi riêng.
2. Chính sách egress do quản trị viên phê duyệt cho container ứng dụng: chặn dải nội bộ, link-local và
   metadata, chỉ cho phép các đích cần thiết (nhà cung cấp mô hình, Hugging Face khi chuẩn bị online).
3. Vận hành offline sau khi chuẩn bị (mô hình online preparation → offline operation) thu hẹp bề mặt này
   về 0 trong thời gian ngắt mạng.

Production readiness phụ thuộc vào việc một biện pháp được phê duyệt và áp dụng.
