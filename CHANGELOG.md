# Changelog

Tất cả thay đổi đáng chú ý của ChatBot 5400 (Agribank Chi nhánh Lâm Đồng) được ghi ở đây.

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
