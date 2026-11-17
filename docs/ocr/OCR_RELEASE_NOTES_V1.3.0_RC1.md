# ChatBot5400 1.3.0-rc.1 — Ghi chú phát hành (BẢN NHÁP, chưa phát hành)

> Trạng thái: **bản nháp chuẩn bị (Phase 12G)**. Chỉ được hoàn thiện, gắn tag và phát hành **sau** khi nghiệm thu
> Windows Local đạt ([PHASE12E_WINDOWS_LOCAL_TEST_GUIDE.md](PHASE12E_WINDOWS_LOCAL_TEST_GUIDE.md)). Không merge vào
> nhánh mặc định, không tạo GitHub Release, không push Docker image, không bật `CB5400_PUBLISH_IMAGES` cho tới khi
> chủ dự án phê duyệt. Release 1.2.0 giữ nguyên.

## 1. Điểm mới

### Chuẩn hóa văn bản pháp lý sau OCR (Legal Document Normalization)

- Chế độ mới **Văn bản pháp lý** trong *Cài đặt → OCR Engine Manager → Chuẩn hóa văn bản sau OCR*, áp dụng cho PDF:
  - bỏ dòng `<!-- image -->` của chữ ký, con dấu, logo; ảnh lớn không chữ (sơ đồ, biểu đồ) vẫn được đánh dấu;
  - loại số trang và header/footer lặp khi có đủ bằng chứng (vị trí trên trang + mẫu lặp giữa các trang);
  - nối đoạn văn / khoản bị cắt bởi phân trang theo quy tắc bảo thủ (không nối khi bắt đầu Điều/Khoản/Điểm mới,
    bảng, tiêu đề, trang trắng, câu đã kết thúc);
  - giữ **đúng số** Điều, Khoản, Điểm gốc (`9.`, `a)`, `đ)`, `1.1`, `a.1)`, gạch đầu dòng) — không còn bị đánh lại
    số hay chèn số vị trí;
  - lấy lại chữ OCR mà bố cục đặt trong vùng ảnh (trước đây bị bỏ);
  - bảng giữ nguyên.
- **Không dùng AI / LLM sửa nội dung**, không tự thêm từ bị thiếu, không đổi số liệu.
- Mặc định **Tiêu chuẩn** (kết quả giống hệt 1.2.0). Bật cần **cả hai**: `OCR_LEGAL_NORMALIZATION_ENABLED=true` trên
  máy chủ và lựa chọn của quản trị viên.

### Gói cập nhật offline

- Công cụ `scripts/offline/` để cập nhật máy chủ Ubuntu **không có Internet**: gói gồm Docker image dựng sẵn (Docling,
  EasyOCR, Tesseract có sẵn trong image), git bundle, manifest, SHA256SUMS, chữ ký tùy chọn; kiểm tra toàn vẹn và
  nguồn gốc, preflight chỉ đọc, cập nhật chỉ tạo lại container ứng dụng (database không bị đụng), rollback.

### Chẩn đoán

- `scripts/ocr/phase12_diagnose.py` / `phase12_compare.py`: theo dõi một PDF qua từng tầng (Tesseract trực tiếp → ô
  OCR → layout → DoclingDocument → Markdown → nội dung lưu → hiển thị), chạy cục bộ.

## 2. Nâng cấp từ 1.2.0

- **Không có migration**; không đổi dependency.
- Không có việc bắt buộc: sau nâng cấp mọi thứ chạy như 1.2.0 cho tới khi bật Legal.
- Tài liệu đã xử lý **không** tự xử lý lại; muốn áp dụng Legal cho tài liệu cũ thì xử lý lại tài liệu đó.
- Máy chủ offline: [../deployment/OFFLINE_UPDATE_UBUNTU_GUIDE.md](../deployment/OFFLINE_UPDATE_UBUNTU_GUIDE.md).

## 3. Rollback

[../deployment/OFFLINE_UPDATE_ROLLBACK.md](../deployment/OFFLINE_UPDATE_ROLLBACK.md): Legal → Standard (giao diện hoặc
cổng), Agri về phiên bản trước, ứng dụng về 1.2.0 (không khôi phục database).

## 4. Giới hạn đã biết

1. Phụ thuộc nhãn của Layout Heron: số trang bị gộp chung khối với đoạn văn không tách được.
2. Thứ tự đọc của Docling không thay đổi (văn bản hai cột có thể đọc theo hàng).
3. Không trích dẫn số trang trong câu trả lời RAG (provenance chưa lưu theo chunk).
4. Chưa có lựa chọn theo từng tài liệu; chưa hiển thị trạng thái "đã chuẩn hóa" trên trang Source.
5. Chất lượng trên tài liệu thật và với model Agri: [điền sau nghiệm thu Local].
6. Gói offline chưa có khóa ký chính thức: xác thực bằng SHA-256 qua kênh tin cậy.

## 5. Kết quả kiểm thử

[Điền sau nghiệm thu Windows Local — số liệu Cloud: `PHASE12D_TEST_REPORT.md`, `PHASE12D_QUALITY_BENCHMARK.md`.]
