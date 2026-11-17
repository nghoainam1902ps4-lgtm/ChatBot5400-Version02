# Bảo mật gói cập nhật offline

## 1. Tài sản và mối đe dọa

| Mối đe dọa | Hậu quả | Biện pháp |
|---|---|---|
| Gói bị sửa trên đường vận chuyển (lỗi hoặc cố ý) | chạy image / script lạ | SHA-256 từng file + cả gói; chữ ký hoặc hash qua kênh tin cậy; công cụ đã cài trước kiểm tra gói mới |
| Gói giả mạo (người khác tạo) | toàn quyền trên máy chủ | **xác thực nguồn bắt buộc, trước khi giải nén**: chữ ký `ssh-keygen -Y` với khóa công khai cài sẵn, hoặc SHA-256 nhận qua kênh **khác** kênh mang gói (file `.sha256` đi cùng gói không tính); thiếu cả hai ⇒ từ chối, không ghi gì ra đĩa |
| Archive độc (`../`, `.`, `\`, đường dẫn tuyệt đối, symlink, hardlink, device, FIFO, **entry trùng tên**) | ghi đè file hệ thống / file sau thay file trước | kiểm tra **mọi** entry trước khi ghi; tự giải nén từng file vào thư mục tạm, kiểm tra đích nằm trong thư mục, đổi tên khi hoàn tất; lỗi ⇒ xóa thư mục tạm |
| Zip/tar bomb, đĩa đầy | đầy đĩa, cây giải nén dở | giới hạn 5000 entry, 64 GiB, tỷ lệ nén 200×; kiểm dung lượng trống trước; lỗi I/O ⇒ từ chối có thông báo, dọn sạch |
| Gói bị sửa **sau khi** verify | chạy nội dung chưa kiểm | báo cáo verify gắn SHA-256 của gói + manifest; `preflight`/`update` kiểm lại manifest, chữ ký và mọi file mỗi lần |
| File image chứa tag khác (ví dụ tag của image database) | `docker load` âm thầm đổi image mà dịch vụ khác dùng | đọc file image **trước** `docker load`: đúng một image, đúng một tag đã duyệt, digest + layer khớp manifest; preflight từ chối nếu tag đã thuộc image khác |
| Image sai nền tảng / sai phiên bản / không phải image đã đóng gói | dịch vụ hỏng | kiểm tra `linux/amd64` vs `docker info`; sau `docker load` nhận diện bằng ID, digest cấu hình **hoặc danh sách layer** (image store khác cho ID khác); journal ghi ID phía máy chủ; phiên bản nguồn được hỗ trợ; schema DB |
| Giá trị trong manifest / tham số chèn YAML hoặc tùy chọn lệnh | override cấp quyền, lệnh git lạ | mọi trường được kiểm định dạng (tag, ID, commit 40 hex, release tag, ref bundle, phiên bản, đường dẫn); override đặt giá trị trong ngoặc kép; so **toàn bộ** cấu hình hiệu lực trước/sau |
| File cấu hình / `allowed_signers` bị người dùng khác sửa; biến môi trường thay `BACKUP_CMD` | chạy lệnh tùy ý với quyền root; chấp nhận khóa lạ | từ chối file không thuộc root/người chạy hoặc ghi được bởi nhóm/người khác; không còn ghi đè khóa cấu hình qua `CB5400_*` |
| Thư mục tạm cố định khi cài công cụ lần đầu | người dùng cục bộ đặt sẵn file | hướng dẫn dùng `mktemp -d` và `install -o root -g root` |
| Biến `http_proxy` trong shell của root | health check tới 127.0.0.1 đi qua proxy (sai kết quả, lộ yêu cầu) | health check không bao giờ dùng proxy; URL bắt buộc là loopback |
| Gói chứa bí mật | lộ thông tin | gói không chứa `.env`, DB, backup, model Agri, dữ liệu; manifest bị từ chối nếu có mẫu `password=`/`token:`…; config server chỉ có đường dẫn |
| Script cập nhật làm hỏng dữ liệu | mất dữ liệu | không `down`, không `-v`, không `rm`, không `prune`, không `exec` vào database, chỉ tạo lại container ứng dụng; so cấu hình hiệu lực với baseline lấy **trước** khi đồng bộ mã nguồn; **`docker inspect` container database** (ID, image, mount, thời điểm khởi động) trước và sau mỗi lần tạo lại; schema + số bản ghi trước/sau |
| Dùng lại backup cũ sau rollback / thất bại | restore đè dữ liệu mới bằng backup cũ | mỗi attempt có mã riêng và **backup + xác minh khôi phục riêng**; journal attempt cũ được lưu trữ, không bước nào được dùng lại; backup chỉ dùng lại khi tiếp tục **cùng** attempt, trước khi tạo lại container, trong `BACKUP_MAX_AGE_MINUTES` |
| `docker compose up -d` thông thường đưa bản cũ trở lại | người dùng chạy bản cũ mà không ai biết | `status`/`health` so image ID + biến môi trường của container với journal, mã thoát 7 khi lệch; `compose-command.txt`; `pin.sh` (dry-run, cần `--apply`, sao lưu, hoàn tác) |
| Rollback theo tag đã bị đổi | "rollback" sang image lạ | rollback theo image ID baseline; tag chỉ dùng khi còn trỏ đúng ID |
| `finish`/`rollback` báo thành công khi ứng dụng hỏng | mở cho người dùng một hệ thống lỗi | cả hai chạy đủ health check; không đạt ⇒ `finish_failed` / `rollback_failed`, mã thoát 5 |
| Journal hỏng (mất điện khi ghi) | mất bản ghi image để rollback | ghi nguyên tử + `fsync` + bản sao `.bak`; hỏng ⇒ dừng với hướng dẫn, không tự tạo lại |
| Mất model OCR sau khi tạo lại container | OCR offline ngừng hoạt động | preflight kiểm readiness đã ghi; kiểm kết quả chép RapidOCR; so danh sách file model trước/sau; kiểm tiktoken offline |
| Cập nhật đồng thời | trạng thái lẫn lộn | `flock` trên `STATE_DIR/update.lock`; journal từ chối mọi cập nhật khi còn attempt chưa quyết định, và gói khác khi attempt dang dở |
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
   giải nén thư mục `scripts` vào thư mục `mktemp -d`, rồi cài vào `/opt/chatbot5400-offline-tools` (root:root, 0755).
2. Các lần sau: **luôn** dùng công cụ đã cài để `verify` gói mới; chỉ cập nhật công cụ từ một gói đã được verify.
3. Công cụ nằm **trong** gói không phải gốc tin cậy: nó không bao giờ được dùng để xác thực chính gói đó, và công cụ
   đã cài không thực thi bất kỳ file nào của gói (script trong gói chỉ là bản để cài cho lần sau).
4. `verify` không ghi gì ra đĩa trước khi gói được xác thực; payload chưa xác thực không bao giờ được giải nén.

## 4. Giới hạn còn lại

- **Toàn bộ biện pháp trên mới được kiểm thử với Docker giả lập.** Định dạng thật của `docker save`, image ID giữa
  các image store, cách Compose thật xử lý `--no-deps`, `pull_policy`, tên image của dịch vụ `build:`, và hành vi sau
  reboot là cổng nghiệm thu Local (`docs/review/PHASE12D3_WINDOWS_ACCEPTANCE_CHECKLIST.md`).
- Chưa có khóa ký chính thức ⇒ không gói nào được coi là "authenticity verified bằng chữ ký".
- Ghim image không bảo vệ trước `docker compose up --build` / `docker compose build` chạy trong thư mục triển khai.
- Danh sách file model chỉ so tên + kích thước (không băm nội dung nhiều GB); toàn vẹn nội dung do readiness cục bộ
  và checksum của chính từng engine đảm nhiệm.

- Build image không tái lập bit-by-bit (`uv:latest`, `apt-get upgrade` trong Dockerfile có từ trước): tin cậy dựa
  trên image ID + SHA-256 ghi trong manifest đã ký/đã đối chiếu, không dựa trên khả năng build lại giống hệt.
- Không quét lỗ hổng image trong Phase 12 (Phase 11).
- `docker load` chạy với quyền daemon Docker: chỉ load image từ gói đã verify.
- Các bước backup/restore phụ thuộc quy trình của máy chủ (`BACKUP_CMD`) — công cụ chỉ gọi và kiểm tra mã thoát.
