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
2. Lỗ hổng phân quyền có sẵn của `/api/commands/jobs` cho các command không phải OCR.
3. Image chạy root (có sẵn).
