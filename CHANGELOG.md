# Changelog

Tất cả thay đổi đáng chú ý của ChatBot 5400 (Agribank Chi nhánh Lâm Đồng) được ghi ở đây.

## [0.0.7] - 2026-09-26

Giao diện mới theo phương án B (Modern Knowledge Assistant) — chỉ thay lớp
trình bày, không đổi API, backend, RAG/GraphRAG hay logic nghiệp vụ.

### Font chữ (tự host, chạy offline)
- Be Vietnam Pro cho toàn bộ giao diện, Bricolage Grotesque cho tiêu đề; tệp
  WOFF2 kèm giấy phép OFL nằm trong mã nguồn, không tải font từ Internet.
- Font mã/số dùng font monospace của hệ thống (Spline Sans Mono thiếu dấu
  tiếng Việt).

### Bố cục trang sổ tay (màn hình ≥ lg)
- Thanh bên thu gọn thành rail 64px (mặc định); vẫn mở rộng được và nhớ lựa
  chọn. Khi thu gọn, rê chuột vào logo để hiện nút "Mở rộng thanh bên".
- Nguồn và Ghi chú gộp thành một bảng Ngữ cảnh 340px có tab; mỗi mục là một
  hàng gọn có đường phân cách.
- Tiêu đề sổ tay thành thanh trên 56px.
- Khung trò chuyện phẳng, cột đọc 760px, câu trả lời AI không đóng khung,
  ô nhập mới có chip mô hình và chip ngữ cảnh. Áp dụng cho cả trò chuyện theo
  nguồn.
- Màn hình nhỏ hơn lg giữ nguyên bố cục cũ.

### Trích dẫn
- Khối "Nguồn dẫn": mỗi trích dẫn là một hàng riêng gồm số, tên và loại
  (Nguồn / Chi tiết / Ghi chú), không còn hiện mã ID thô. Tên lấy từ dữ liệu đã
  tải sẵn, không phát sinh thêm request.
- Số trích dẫn trong câu trả lời hiển thị dạng chip nhỏ; bấm vẫn mở đúng nguồn.

### Sửa lỗi
- Hộp thoại "Cấu hình mô hình" rộng hơn, tên mô hình dài không bị tràn.
- Hộp thoại Thêm/Sửa chuyển đổi luôn hiện nút "Hủy" và "Thêm"/"Lưu thay đổi"
  trên màn hình thấp (phần nội dung tự cuộn).

## [0.0.6] - 2026-09-25

Sửa thông báo bản cập nhật mới.

### Thông báo cập nhật
- Thông báo hiện lại **mỗi lần mở/tải lại ứng dụng** cho tới khi hệ thống được
  cập nhật (trước đây chỉ hiện một lần do cờ `sessionStorage` bị trình duyệt giữ
  lại); vẫn không hiện lại khi chuyển trang trong ứng dụng.
- Giao diện đồng bộ với các thông báo khác: nền đỏ bordeaux Agribank, bố cục tiêu
  đề + mô tả, nút "Nâng cao" nền trắng.

## [0.0.5] - 2026-09-24

Khôi phục thông báo bản cập nhật mới khi mở ứng dụng.

### Thông báo cập nhật
- Khi quản trị viên mở ứng dụng, hệ thống kiểm tra ngầm bản Release mới nhất trên
  GitHub; nếu có bản mới hơn, hiện thông báo ở **góc dưới bên phải**: "Có bản cập
  nhật mới (vX.Y.Z). Vui lòng kiểm tra trong Công cụ nâng cao." kèm nút mở nhanh
  trang *Công cụ nâng cao*.
- Chỉ hiện **một lần mỗi phiên** (lưu cờ `update_notified` trong `sessionStorage`),
  không hiện lại khi chuyển trang. Lỗi mạng được bỏ qua, không làm phiền người dùng.

## [0.0.4] - 2026-09-24

Khôi phục tính năng tự động kiểm tra phiên bản mới.

### Kiểm tra phiên bản
- *Công cụ nâng cao → Thông tin hệ thống* hiển thị lại dòng "Phiên bản mới nhất",
  lấy từ bản Release mới nhất trên GitHub của dự án
  (`nghoainam1902ps4-lgtm/ChatBot5400-Version02`).
- So sánh phiên bản theo chuẩn SemVer (so từng phần dạng số, `0.0.10` > `0.0.9`;
  bản thử nghiệm `-rc` thấp hơn bản chính thức).
- Ba trạng thái: **Có bản cập nhật mới** (màu cam, biểu tượng chuông),
  **Đã cập nhật** (đỏ bordeaux), **Lỗi kết nối** khi không gọi được GitHub.

## [0.0.3] - 2026-09-24

Bản cập nhật nhận diện thương hiệu và hiển thị phiên bản.

### Giao diện & nhận diện thương hiệu
- **Trang đăng nhập**: tiêu đề đổi thành "AGRIBANK CHI NHÁNH LÂM ĐỒNG"; bỏ dòng
  gợi ý tài khoản mặc định (admin / admin) và dòng hiển thị địa chỉ API.
- **Phiên bản** hiển thị ở trang đăng nhập và *Công cụ nâng cao → Thông tin hệ
  thống* được đọc tự động từ `frontend/package.json` (không còn viết cứng).

### Kiểm tra phiên bản
- Bỏ cơ chế kiểm tra bản cập nhật từ repository gốc (open-notebook trên GitHub):
  backend không còn gọi ra GitHub, bỏ thông báo nổi "có bản mới".
- *Thông tin hệ thống* ẩn dòng "Phiên bản mới nhất"; trạng thái luôn "Đã cập nhật".

## [0.0.2] - 2026-09-24

Bản vá tập trung vào cô lập dữ liệu theo người dùng, trải nghiệm xem tài liệu và
triển khai.

### Sửa lỗi cô lập dữ liệu theo người dùng
- **Chat theo từng Nguồn (Chat with Source)**: lọc theo `user_id` ở tầng CSDL và
  chuẩn hóa kiểm tra chủ sở hữu — user không còn nhìn thấy lịch sử chat của nhau.
  Query key React Query kèm `userId`, xóa cache khi đăng xuất.
- **Số lượng Ghi chú trên thẻ Notebook (Notes count)**: chỉ đếm ghi chú của user
  đang đăng nhập (trước đây cộng gộp ghi chú của mọi user). Số lượng Nguồn giữ
  nguyên là dữ liệu chung. Áp dụng cho danh sách và chi tiết notebook.

### Giao diện & trải nghiệm
- **Modal xem Nguồn (Source preview)** khi mở từ trong Notebook: phóng lớn
  (rộng/cao hơn), ghim tiêu đề, chỉ cuộn phần nội dung.
- **Hướng dẫn kết nối nhà cung cấp AI**: thay liên kết trỏ ra GitHub bằng modal
  hiển thị ngay trong ứng dụng (bản dịch tiếng Việt của `ai-providers.md`), tiêu
  đề/liên kết màu đỏ bordeaux; sửa lỗi modal kẹt ở trạng thái "Đang tải…".

### Triển khai
- Sửa lỗi Docker build "no space left on device": loại dữ liệu runtime trong
  `deploy/` (CSDL, model docling/torch, chứng chỉ) khỏi build context.

## [0.0.1] - 2026-09-22

Bản phát hành đầu tiên — nền tảng Open Notebook được tùy biến cho Agribank Chi
nhánh Lâm Đồng.

### Xác thực & phân quyền (Auth / RBAC)
- Đăng nhập bằng tài khoản (JWT), mật khẩu băm bcrypt; tự tạo admin/admin lần đầu.
- Vai trò **admin** (quản trị người dùng, notebook, source) và **user thường**
  (chỉ xem, chat, tạo ghi chú). Ẩn menu quản trị (Cài đặt/Mô hình/Chuyển đổi/
  Nâng cao) khỏi sidebar và Command Palette với user thường.
- Trang quản lý người dùng cho admin: thêm/sửa/xóa, đặt lại mật khẩu, đổi mật khẩu.

### Cô lập dữ liệu theo người dùng
- Chat và ghi chú riêng tư theo từng user.
- "Xem gần đây" (Recently Viewed) theo từng user (bảng `recently_viewed`).
- Xóa sạch cache (React Query) + state khi đăng xuất/đăng nhập, giữ lại cài đặt
  giao diện (theme/ngôn ngữ).

### Giao diện & thương hiệu
- Tông màu trắng + đỏ bọc đô + vàng chuẩn Agribank; font Times New Roman.
- Logo Agribank + chữ "Agribank Lâm Đồng" ở sidebar (thu gọn hiện logo); favicon
  và tiêu đề "ChatBot 5400 - Agribank Chi Nhánh Lâm Đồng".
- Toast "Thành công" nền đỏ bordeaux; các modal (đăng nhập/đổi mật khẩu/quản lý
  user) thu gọn, căn giữa.
- Song ngữ: chỉ giữ Tiếng Việt + English, mặc định Tiếng Việt; lưu ngôn ngữ và
  theme theo từng user.

### Xử lý tài liệu (Điều/Khoản)
- Bật **docling** mặc định để giữ đúng cấu trúc Điều → Khoản → điểm cho .docx/.pdf.
- Hiển thị source kiểu công văn: căn đều hai bên, thụt đầu dòng, in đậm "Điều n.",
  căn giữa Chương/Mục, thụt Khoản/điểm theo cấp, bỏ dấu chấm thừa do trích xuất.

### Triển khai
- Bộ triển khai VPS (`deploy/`): Docker Compose (SurrealDB + app + Caddy HTTPS),
  build từ mã nguồn, docling cài ở lần chạy đầu (PyTorch CPU), tài liệu
  `DEPLOY-VPS.md`. Hướng dẫn chạy local trên Windows (`SETUP-WINDOWS.md`).

### Kiểm thử
- Bộ test backend (auth/RBAC/isolation/recently-viewed) và frontend (vitest)
  đều xanh.
