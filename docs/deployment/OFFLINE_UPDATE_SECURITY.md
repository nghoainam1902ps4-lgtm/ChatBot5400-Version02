# Bảo mật gói cập nhật offline

## 1. Tài sản và mối đe dọa

| Mối đe dọa | Hậu quả | Biện pháp |
|---|---|---|
| Gói bị sửa trên đường vận chuyển (lỗi hoặc cố ý) | chạy image / script lạ | SHA-256 từng file + cả gói; chữ ký hoặc hash qua kênh tin cậy; công cụ đã cài trước kiểm tra gói mới |
| Gói giả mạo (người khác tạo) | toàn quyền trên máy chủ | **xác thực nguồn bắt buộc**: chữ ký `ssh-keygen -Y` với khóa công khai cài sẵn, hoặc SHA-256 nhận qua kênh **khác** kênh mang gói; thiếu cả hai ⇒ từ chối |
| Archive độc (`../`, đường dẫn tuyệt đối, symlink, hardlink, device) | ghi đè file hệ thống | kiểm tra **mọi** entry trước khi ghi; tự giải nén từng file vào thư mục mới, kiểm tra đích nằm trong thư mục |
| Zip/tar bomb | đầy đĩa | giới hạn 5000 entry, 64 GiB, tỷ lệ nén 200× |
| Image sai nền tảng / sai phiên bản | dịch vụ hỏng | kiểm tra `linux/amd64` vs `docker info`, image ID sau `docker load`, phiên bản nguồn được hỗ trợ, schema DB |
| Gói chứa bí mật | lộ thông tin | gói không chứa `.env`, DB, backup, model Agri, dữ liệu; manifest bị từ chối nếu có mẫu `password=`/`token:`…; config server chỉ có đường dẫn |
| Script cập nhật làm hỏng dữ liệu | mất dữ liệu | không `down`, không `-v`, không `rm`, không `prune`, chỉ tạo lại container ứng dụng; so cấu hình hiệu lực: dịch vụ DB phải giống hệt; backup + xác minh khôi phục trước khi tạo lại |
| Cập nhật đồng thời | trạng thái lẫn lộn | `flock` trên `STATE_DIR/update.lock`; journal từ chối gói khác khi đang dang dở |
| Tải từ Internet ngầm | vi phạm chính sách offline, treo | Docling/EasyOCR/Tesseract trong image; RapidOCR lên volume; `OCR_OFFLINE=true`; `--pull never`, `pull_policy: never`; `--prove-offline` |
| Log lộ bí mật | lộ thông tin | công cụ không đọc `.env`, không in biến môi trường; log chỉ bước, ID image, kết quả kiểm tra |
| Leo thang qua override | mở cổng / quyền | override do công cụ sinh chỉ có `image`, `pull_policy`, biến môi trường thuộc danh sách ký tự an toàn; so cổng trước/sau; bảo trì chỉ loopback |

## 2. Khóa ký

- Tạo trên máy build (khuyến nghị máy riêng của người phát hành), `ssh-keygen -t ed25519`, có passphrase.
- Khóa riêng **không bao giờ** nằm trong Git, trong gói, trên máy chủ production.
- Khóa công khai cài vào `/etc/chatbot5400/allowed_signers` (`release@chatbot5400 ssh-ed25519 …`), quyền root, nhận
  qua kênh tin cậy.
- Thay khóa: cài khóa mới song song (nhiều dòng trong `allowed_signers`), ký gói tiếp theo bằng khóa mới, rồi gỡ khóa cũ.
- **Hiện trạng: chưa có khóa ký chính thức** ⇒ authenticity của gói 1.3.0-rc.1 chỉ có thể dựa trên hash kênh tin cậy.
  Phải thiết lập khóa (hoặc quy trình đối chiếu hash có biên bản) **trước** triển khai thật.

## 3. Chuỗi tin cậy của chính công cụ

Một gói giả có thể kèm script giả. Vì vậy:
1. Lần đầu: so `sha256sum` của gói bằng tay với giá trị kênh tin cậy **trước** khi chạy bất kỳ script nào trong gói,
   rồi cài công cụ vào `/opt/chatbot5400-offline-tools` (root:root, 0755).
2. Các lần sau: **luôn** dùng công cụ đã cài để `verify` gói mới; chỉ cập nhật công cụ từ một gói đã được verify.

## 4. Giới hạn còn lại

- Build image không tái lập bit-by-bit (`uv:latest`, `apt-get upgrade` trong Dockerfile có từ trước): tin cậy dựa
  trên image ID + SHA-256 ghi trong manifest đã ký/đã đối chiếu, không dựa trên khả năng build lại giống hệt.
- Không quét lỗ hổng image trong Phase 12 (Phase 11).
- `docker load` chạy với quyền daemon Docker: chỉ load image từ gói đã verify.
- Các bước backup/restore phụ thuộc quy trình của máy chủ (`BACKUP_CMD`) — công cụ chỉ gọi và kiểm tra mã thoát.
