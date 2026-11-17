# ChatBot5400 1.3.0-rc.1 — Ghi chú phát hành (BẢN NHÁP, chưa phát hành)

> Trạng thái: **bản nháp chuẩn bị (Phase 12G)**. Chỉ được hoàn thiện, gắn tag và phát hành **sau** khi nghiệm thu
> Windows Local đạt ([PHASE12E_WINDOWS_LOCAL_TEST_GUIDE.md](PHASE12E_WINDOWS_LOCAL_TEST_GUIDE.md)). Không merge vào
> nhánh mặc định, không tạo GitHub Release, không push Docker image, không bật `CB5400_PUBLISH_IMAGES` cho tới khi
> chủ dự án phê duyệt. Release 1.2.0 giữ nguyên.
>
> **Cập nhật Phase 12D3**: nội dung dưới đây đã được chỉnh theo bộ chuẩn hóa v1.1.0 và công cụ offline định dạng 2
> (sau audit độc lập 12D2). Điều kiện phát hành thêm: review độc lập 12D4 và checklist
> [../review/PHASE12D3_WINDOWS_ACCEPTANCE_CHECKLIST.md](../review/PHASE12D3_WINDOWS_ACCEPTANCE_CHECKLIST.md). `VERSION`
> vẫn là `1.2.0`; gói thử nghiệm mang tên `1.2.0-phase12.N`.

## 1. Điểm mới

### Chuẩn hóa văn bản pháp lý sau OCR (Legal Document Normalization)

- Chế độ mới **Văn bản pháp lý** trong *Cài đặt → OCR Engine Manager → Chuẩn hóa văn bản sau OCR*, áp dụng cho PDF:
  - nguyên tắc: **giữ nội dung trừ khi có bằng chứng mạnh**; mọi trường hợp nghi ngờ được giữ nguyên kèm cảnh báo;
  - bỏ dòng `<!-- image -->` chỉ với ảnh rất nhỏ (< 4% trang) không có chữ; ảnh lớn hơn không chữ vẫn được đánh dấu
    kèm cảnh báo có vị trí;
  - loại số trang khi có đủ bằng chứng (≥ 3 trang cùng mẫu, ≥ 60% số trang, cùng vị trí, ngoài phần thân); văn bản
    1–2 trang giữ nguyên; **dòng chữ lặp lại không bao giờ bị bỏ** trừ khi bố cục đã gắn nhãn header/footer;
  - nối đoạn văn / khoản bị cắt bởi phân trang theo quy tắc bảo thủ (không nối khi bắt đầu Điều/Khoản/Điểm mới kể
    cả `a.`, `a/`, `đ)`, `(a)`, `a.1)`; footnote; footer; khác cột; bảng, ảnh, trang trắng; câu đã kết thúc);
  - giữ **đúng số** Điều, Khoản, Điểm gốc (`9.`, `a)`, `đ)`, `1.1`, `a.1)`, gạch đầu dòng) — không còn bị đánh lại
    số hay chèn số vị trí;
  - lấy lại chữ OCR và bảng mà bố cục đặt trong vùng ảnh (trước đây bị bỏ);
  - bảng giữ nguyên.
- Trang Source ghi nhãn *Tiêu chuẩn* / *Đã chuẩn hóa văn bản pháp lý* / *Chuẩn hóa thất bại, sử dụng bản tiêu chuẩn*
  kèm phiên bản bộ chuẩn hóa và số cảnh báo; hiển thị phân cấp Điều/Khoản/điểm. Văn bản lưu (và đưa vào RAG) không
  chứa ký tự thoát Markdown.
- **Không dùng AI / LLM sửa nội dung**, không tự thêm từ bị thiếu, không đổi số liệu.
- Mặc định **Tiêu chuẩn** (kết quả giống hệt 1.2.0). Bật cần **cả hai**: `OCR_LEGAL_NORMALIZATION_ENABLED=true` trên
  máy chủ và lựa chọn của quản trị viên.

### Gói cập nhật offline

- Công cụ `scripts/offline/` để cập nhật máy chủ Ubuntu **không có Internet**: gói gồm Docker image dựng sẵn (Docling,
  EasyOCR, Tesseract, bộ mã hóa token có sẵn trong image), git bundle, manifest, SHA256SUMS, chữ ký tùy chọn; xác
  thực nguồn gốc **trước khi giải nén**, preflight chỉ đọc, mỗi lần cập nhật có backup riêng, cập nhật chỉ tạo lại
  container ứng dụng (container database được kiểm chứng không đổi), `finish`/`rollback` có health check, phát hiện
  lệch giữa bản đang chạy và bản đã duyệt, ghim image tùy chọn, rollback theo image ID.

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

1. Phụ thuộc nhãn của Layout Heron: số trang bị gộp chung khối với đoạn văn không tách được; header/footer mà bố cục
   gắn nhãn là đoạn văn thường được **giữ lại** trong nội dung (kèm cảnh báo) và chặn phép nối ở trang đó.
2. Thứ tự đọc của Docling không thay đổi (văn bản hai cột có thể đọc theo hàng). Docling tự nối một số đoạn qua trang
   khi đoạn trước kết thúc bằng chữ ASCII thường / dấu phẩy / gạch nối — có ở cả chế độ Tiêu chuẩn và 1.2.0.
3. Văn bản 1–2 trang giữ số trang nghi ngờ, nên khoản bị cắt qua trang ở các văn bản này không được nối.
4. Không trích dẫn số trang trong câu trả lời RAG (provenance chưa lưu theo chunk).
5. Chưa có lựa chọn theo từng tài liệu.
6. Chất lượng trên tài liệu thật và với model Agri: [điền sau nghiệm thu Local].
7. Gói offline chưa có khóa ký chính thức: xác thực bằng SHA-256 qua kênh tin cậy riêng (file `.sha256` đi kèm gói
   không tính). Thư mục triển khai không tự mô tả bản đang chạy: dùng lệnh trong `compose-command.txt`, kiểm bằng
   `status.sh`, hoặc ghim bằng `pin.sh`. Model OCR không nằm trong gói.

## 5. Kết quả kiểm thử

[Điền sau nghiệm thu Windows Local — số liệu Cloud: `../review/PHASE12D3_REGRESSION_REPORT.md`,
`../review/PHASE12D3_QUALITY_BENCHMARK.md`. Số liệu của `PHASE12D_QUALITY_BENCHMARK.md` (Phase 12) đã bị thay thế.]
