# Phase 12D — Rà soát bảo mật (Legal Normalization + công cụ cập nhật offline)

Phạm vi: mọi mã mới / sửa của Phase 12. Không thuộc phạm vi: Phase 11 Security Hardening (chưa bắt đầu), các giới
hạn bảo mật đã biết của v1.2.0 (CORS mở, xác thực đơn giản — `AGENTS.md`).

## 1. Kết luận

**Không có lỗ hổng HIGH / CRITICAL mới do Phase 12** (theo rà soát thủ công + bandit + test). Hai phát hiện mức thấp
đã sửa trong phase (§4). Cơ chế sanitization hiện có không bị nới lỏng.

## 2. Legal normalizer

| Hạng mục | Đánh giá | Bằng chứng |
|---|---|---|
| XSS / HTML injection | Docling escape `<`, `>`, `&` trong chữ; normalizer **không** bỏ escape; frontend không dùng `rehype-raw` (HTML hiển thị như chữ) | `test_html_and_markdown_injection_not_introduced`, vitest placeholder |
| Markdown injection | chữ OCR bắt đầu bằng `#`, `>`, `-`, `1.` được escape đầu dòng ⇒ không thành tiêu đề/trích dẫn/danh sách | test `escape_block_start` (11 trường hợp) |
| Link `javascript:` | không đổi so với Standard; `react-markdown` (`urlTransform` mặc định) chặn | — |
| Prompt injection qua metadata | metadata chỉ gồm số đếm / phiên bản / trạng thái; không vào prompt; nội dung đi vào RAG như trước | `test_summary_contains_no_text` |
| Resource exhaustion | giới hạn 200k item / 10k trang / 50M ký tự ⇒ fallback; thuật toán tuyến tính (đo 300 trang: 0,75 s); duyệt cha tối đa 64 cấp | `test_limits_fall_back`, `test_large_document_is_fast`, `test_very_long_text_item` |
| DoclingDocument lỗi | mọi ngoại lệ ⇒ Standard + `status=failed`; tài liệu gốc không đổi (làm trên bản sao) | `test_malformed_object_falls_back_without_raising`, `test_source_document_untouched` |
| Gọi mạng | không import thư viện mạng; test chặn `socket.connect` / `create_connection` | `test_no_network_calls` |
| Ghi DB / file | không | đọc mã |
| Log rò rỉ nội dung | log chỉ số đếm; báo cáo có chữ chỉ ở `include_text=True` (diagnostic cục bộ) | `test_summary_contains_no_text` |
| Phân quyền cấu hình | `PUT /api/ocr/config` nằm sau `require_admin` (router `/ocr`); Legal bị từ chối khi cổng triển khai tắt; giá trị khác `standard`/`legal` bị Pydantic từ chối | `test_config_endpoint_is_admin_only`, `test_api_refuses_legal_without_gate`, `test_api_rejects_unknown_mode` |
| IDOR | không thêm endpoint theo tài liệu; cấu hình là toàn cục cho admin | — |
| PDF bất thường | normalizer không đọc PDF (chỉ `DoclingDocument`); kiểm tra "là PDF" chỉ đọc 1 KiB đầu file đã qua `resolve_upload_path` | đọc mã |

## 3. Công cụ chẩn đoán (Windows Local)

| Hạng mục | Biện pháp |
|---|---|
| Rò rỉ tài liệu | không upload/telemetry; thư mục kết quả quyền 0700, file 0600; từ chối ghi vào thư mục không rỗng |
| SSRF / đọc file qua `--api-url` | chỉ `http(s)`; chỉ loopback trừ khi `--allow-remote-api`; token đọc từ biến môi trường, không in |
| Path traversal | `phase12-test.ps1` / `.sh` từ chối tên PDF tuyệt đối hoặc chứa `..`; thư mục `import` mount **read-only** |
| Cô lập stack | compose project riêng, cổng chỉ `127.0.0.1`, DB không có cổng host, secrets sinh ngẫu nhiên tại chỗ và không in, `.env`/dữ liệu bị `.gitignore` và `.dockerignore` loại |
| Xóa dữ liệu | script không có `down -v`, không xóa thư mục |

## 4. Phát hiện và xử lý

| # | Mức | Phát hiện | Xử lý |
|---|---|---|---|
| 1 | Thấp | `phase12_diagnose.fetch_source` chỉ kiểm tra hostname; `file://localhost/…` được chấp nhận (đọc file cục bộ — chỉ trên máy của người vận hành) | bắt buộc scheme `http(s)`; test hồi quy |
| 2 | Thấp | `safe_extract` dùng `assert` để kiểm tra luồng (bị bỏ khi chạy `python -O`) | thay bằng ngoại lệ `Refused` |
| 3 | Hiệu năng / DoS | bước "ngoài cùng" của normalizer bậc hai (10 s / 300 trang) | tuyến tính hóa (0,75 s); test giới hạn |
| 4 | Dữ liệu | phiên bản đầu của nhận diện header lặp (che chữ số) xóa nhầm dòng nội dung | bỏ che chữ số + điều kiện "ngoài cùng"; fixture f14 |

bandit (cục bộ, không thêm vào dependency) trên mã mới: không có HIGH; MEDIUM B310 (`urlopen`) ở 2 chỗ đều đã giới
hạn scheme/host loopback; LOW B603/B404 (subprocess dạng danh sách, không shell, nhị phân cố định).

## 5. Gói cập nhật offline

Chi tiết threat model: [../deployment/OFFLINE_UPDATE_SECURITY.md](../deployment/OFFLINE_UPDATE_SECURITY.md). Tóm tắt
kiểm thử (`tests/test_offline_package.py`, 30 test): path traversal, đường dẫn tuyệt đối, symlink, hardlink, thiết bị,
nhiều thư mục gốc, bomb nén (tỷ lệ và tổng dung lượng), file thừa/thiếu, checksum sai, manifest hỏng/thiếu trường,
sai nền tảng, phiên bản nguồn không hỗ trợ, DB mới hơn gói, gói cần migration, chữ ký hợp lệ / sai khóa / manifest bị
sửa sau khi ký (ssh-keygen thật), thiếu cả chữ ký và hash tin cậy ⇒ từ chối, khóa cập nhật đồng thời, cấu hình làm
thay đổi dịch vụ database ⇒ từ chối, mọi lệnh Docker được ghi lại và kiểm tra không có `down`, `-v`, `pull`, `build`,
`rm`, `push`.

## 6. Rủi ro còn lại

1. **Authenticity** của gói phụ thuộc khóa ký hoặc kênh tin cậy do chủ dự án thiết lập: **chưa có khóa ký chính thức**
   ⇒ gói đầu tiên chỉ xác thực được bằng hash qua kênh tin cậy.
2. Công cụ cập nhật **phiên bản đầu tiên** phải được lấy từ nguồn tin cậy (gói đã kiểm hash), vì một gói giả có thể
   kèm script giả — hướng dẫn yêu cầu chạy `verify` từ bản công cụ đã cài trước (từ lần cập nhật sau).
3. Dockerfile dùng `ghcr.io/astral-sh/uv:latest` và `apt-get upgrade` (có từ trước) ⇒ build không tái lập bit-by-bit;
   gói ghi lại image ID + SHA-256 để xác định chính xác cái được triển khai.
4. Docker daemon thật, chặn mạng thật, khôi phục backup thật: chưa kiểm thử (Cloud không có Docker daemon).
