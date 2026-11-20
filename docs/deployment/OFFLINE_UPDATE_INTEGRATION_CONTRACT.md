# Hợp đồng tích hợp triển khai — cập nhật offline ChatBot5400 (Phase 12D5)

Tài liệu này nói **máy chủ production phải thỏa điều gì** để một bản cập nhật offline — thủ công
(`OFFLINE_UPDATE_MANUAL_FALLBACK.md`) hay bằng bộ cập nhật tự động (`offline_package.py`) — được
dùng sau MỌI đường khởi động: script vận hành (chế độ thường / bảo trì / trạng thái), boot guard sau
khi khởi động lại máy, `docker restart`, `docker compose up -d` thường, tạo lại container, lần cập
nhật thứ hai, rollback.

Repository công khai **không chứa** đường dẫn, địa chỉ, tên máy hay cấu hình thật của production.
Mọi chỗ có `LOCAL VERIFICATION REQUIRED` chỉ kiểm được trên máy chủ (danh sách W-INT-* ở
`docs/review/PHASE12D5_LOCAL_ACCEPTANCE_CHECKLIST.md`). Không thay đổi cấu hình production từ
Cloud.

## 1. Vì sao (F-11, R2-16, R2-12)

Phase 12D3 giữ "image đã duyệt" trong file override của công cụ (`image-override.yml`,
`compose-command.txt`) và một file pin tùy chọn. Production khởi động ứng dụng bằng script vận hành
riêng, boot guard, project Compose cố định, override cục bộ và một **tag image cục bộ** — các đường
đó không đọc file của công cụ, nên sau một lần khởi động lại ứng dụng có thể quay về image cũ
(F-11); pin hỏng từ lần cập nhật thứ hai (R2-16); một attempt bị từ chối ghi đè override dùng chung
(R2-12).

Phase 12D5 bỏ mọi "con trỏ" riêng của công cụ: **tag image cục bộ mà chính file compose của
triển khai dùng là con trỏ duy nhất**. Đổi image = chuyển tag đó; mọi đường khởi động đọc cùng file
compose nên đều khởi động đúng image đó, không cần file nào của công cụ. Điều này đã được chứng
minh trên Docker 29 thật (phòng thí nghiệm Cloud): `docker tag <id mới> <tag>` rồi
`docker compose up -d` thường chỉ tạo lại ứng dụng, container database giữ nguyên ID.

## 2. Các điều khoản

| # | Điều khoản | Kiểm thế nào | Trạng thái |
|---|---|---|---|
| C1 | Service ứng dụng trong file compose CỦA TRIỂN KHAI có `image: <DEPLOY_IMAGE_TAG>` — một **tag cục bộ** (ví dụ `chatbot5400:local`), không phải số phiên bản (`chatbot5400:1.2.0`), không phải digest / ID, không phải image upstream. | `docker compose -p <project> <files> config` → `services.<app>.image` | LOCAL VERIFICATION REQUIRED (W-INT-01) |
| C2 | Một tên Compose project **cố định** và một danh sách file compose cố định, giống nhau ở chế độ thường, chế độ bảo trì, boot guard. | đọc script vận hành / boot guard | LOCAL (W-INT-02) |
| C3 | Biến môi trường phiên bản mới cần (`OCR_OFFLINE=true`, `OCR_RAPIDOCR_PERSISTENT=true`) nằm trong cấu hình cục bộ của đơn vị (override / `.env`); `OCR_LEGAL_NORMALIZATION_ENABLED` vắng hoặc `false` (Legal mặc định OFF). Công cụ **không bao giờ** tiêm biến môi trường và không sửa file của đơn vị. | `docker inspect` container đang chạy (chỉ lọc 3 biến này) | LOCAL (W-INT-03) |
| C4 | Chế độ bảo trì = một override của đơn vị chỉ bind cổng ứng dụng vào `127.0.0.1` (hoặc chặn truy cập người dùng); cổng LAN / Tailscale cấu hình riêng ở chế độ thường. | `docker port <app>` ở từng chế độ | LOCAL (W-INT-04) |
| C5 | Boot guard sau khởi động lại máy khởi động bằng **cùng project + file compose** (C1, C2): không hard-code ID / phiên bản image, không `pull`, `build`, `down`, `-v`, không recreate database. | đọc boot guard; khởi động lại máy thử | LOCAL (W-INT-05, W-FB-09) |
| C6 | Database: mọi lệnh cập nhật / rollback / script vận hành tạo lại ứng dụng với `--no-deps` **và** chỉ nêu service ứng dụng (Phase 12D9, D8-OFF-15: không còn "hoặc"); container và volume database giữ nguyên. | so ID container, image, mount trước / sau | Cloud: lab Docker thật; LOCAL (W-INT-06) |
| C7 | Image ứng dụng mang sẵn bộ mã hóa token (`TIKTOKEN_CACHE_DIR=/app/tiktoken-cache`, SHA-256 đúng); trong container đang chạy, kiểm tokenizer báo `PASS` khi không có mạng. | `token_utils.main(["--check"])` trong container | Cloud: test với file thật; LOCAL (W-INT-07) |
| C8 | Không còn file pin của Phase 12D3 (`docker-compose.offline-pin.yml`) trong danh sách file của script vận hành / boot guard; không còn `image-override.yml` của công cụ trong đó. | đọc script; `status` của công cụ báo file sót lại | LOCAL (W-INT-08) |
| C9 | Tag rollback: image trước cập nhật được giữ dưới một tên (`chatbot5400:rollback-before-<ver>` khi làm thủ công; tag rollback của công cụ khi tự động) cho tới bản phát hành sau; không chạy `docker image prune -a` / `system prune -a`. | `docker image ls chatbot5400` | LOCAL (W-INT-09) |
| C10 | RB-1 cho v1.2.0: tất cả đường tạo lại ứng dụng chọn cùng override bền vững theo ID hiện tại của tag C1. Giữ ID baseline, assets và selector ngoài checkout. | Kiểm cấu hình hữu hiệu và nghiệm thu recreate, restart, đổi chế độ, rollback, boot guard | LOCAL (D11-W09, RB-G11) |

## 3. Hợp đồng adapter cho script vận hành (khi chưa biết script làm gì)

**C10 (RB-1).** `rb1_setup.py` kiểm chữ ký, định danh image và thử cache offline trước khi ghi
thư mục staging bền vững. Adapter thường, bảo trì và boot guard, sau khi chọn tag đã duyệt và trước
khi dùng Compose, phải (Phase 12D13):

1. `python3 -I "$RB1_STATE/verify_stage.py" --allowed-signers "$SIGNERS" --identity "$SIGNER" --service "$APP" || exit 1`
   (`$SIGNERS` là file khoá tin cậy nằm **ngoài** `$RB1_STATE`, do root quản lý). Bước này kiểm chủ sở
   hữu / quyền của thư mục và từng file, đúng tập file, chữ ký của manifest gói đã chép vào stage, và
   mọi file đã stage đúng kích thước + SHA-256 đã ký, override Compose đúng mẫu startup gate.
2. `rb1_file=$(sh "$RB1_STATE/select-compose.sh") || exit 1`. Metadata hỏng (ID cắt ngắn, CRLF, sai
   hoa/thường, nhiều dòng, rỗng) hoặc lỗi Docker ⇒ mã khác 0, không in gì.
3. Nếu tag đã chọn là image baseline: bắt buộc `test "$rb1_file" = "$RB1_STATE/compose.json" || exit 1`
   (đầu ra rỗng lúc này nghĩa là selector bị thay, không phải "không cần override").

Nếu `rb1_file` có giá trị, nối `-f "$rb1_file"` **cuối** danh sách file. Kiểm
`docker compose config --format json` ở cả hai chế độ. Service ứng dụng giữ nguyên image tag C1,
dùng entrypoint `[/bin/sh, /opt/cb5400-rb1/startup.sh]`, command rỗng, bind mount chỉ đọc tới
`/opt/cb5400-rb1` và `pull_policy: never`. Mọi lệnh recreate chỉ nêu service ứng dụng và dùng
`--no-deps --no-build --pull never`. Nếu không chọn được cấu hình, adapter phải dừng.

Override này đi cùng image v1.2.0 đã duyệt. Khi tag trỏ candidate, selector trả chuỗi rỗng. Docker
restart giữ nguyên mount và entrypoint đã cấu hình. Khi recreate hoặc boot dựa vào Compose phải
gọi selector như trên. Compose thông thường chỉ được gọi thông qua cùng adapter. Startup script
xác minh entrypoint baseline, yêu cầu cấu hình offline đã được duyệt, gọi entrypoint đó để cài
runtime từ uv cache, xác minh và khôi phục từ điển, rồi mới chạy `supervisord`. Cho tới khi
RB-G11 đạt, chưa nghiệm thu hành vi reboot trên VM. Không chỉnh script vận hành thật trong phase này.

Script vận hành và boot guard của production không có trong repository. Thay vì đoán, chúng phải
thỏa **adapter contract** sau (LOCAL VERIFICATION REQUIRED — W-INT-10):

1. `normal`: `docker compose -p <PROJECT> <FILES> up -d --no-deps --no-build --pull never <app>` -
   `--no-deps` và tên service ứng dụng là **bắt buộc** (Phase 12D9, D8-OFF-15: không có chúng Compose
   tạo lại cả database khi định nghĩa của nó khác, ví dụ sau §7.1 của quy trình thủ công); không
   `--pull always`, không `--build`, không `down`.
2. `maintenance`: giống `normal` nhưng thêm override bảo trì (C4) **sau** các file thường.
3. `status`: chỉ đọc.
4. Không lệnh nào đặt image bằng ID / digest / phiên bản; không lệnh nào `docker tag` hay
   `docker rmi` image `chatbot5400`.
5. Đổi chế độ (thường ↔ bảo trì) tạo lại ứng dụng trên **image mà `DEPLOY_IMAGE_TAG` chỉ tới lúc
   đó** — không mang image theo từ lần chạy trước.

Nếu script vi phạm một điểm (ví dụ hard-code `chatbot5400:1.2.0`, hay `docker compose pull`), chỉ
đơn vị vận hành sửa nó **trên máy chủ**, trước khi cập nhật: đổi image của service ứng dụng thành
`DEPLOY_IMAGE_TAG` và gắn tag đó vào image đang chạy (`docker tag <id đang chạy> <DEPLOY_IMAGE_TAG>`,
không đổi image nào). Sau thay đổi đó, chạy `normal` một lần và kiểm container vẫn cùng image ID.

## 4. Bộ cập nhật tự động dùng cùng hợp đồng

Cấu hình máy chủ (`/etc/chatbot5400/offline-update.conf`, chỉ đường dẫn, không bí mật — xem
`scripts/offline/offline-update.conf.example`): `DEPLOY_DIR`, `COMPOSE_PROJECT`, `COMPOSE_FILES`
(đúng thứ tự của script vận hành), `APP_SERVICE`, `DB_SERVICE`, `DEPLOY_IMAGE_TAG`,
`MAINTENANCE_OVERRIDE`, `REQUIRED_APP_ENV` (mặc định `OCR_RAPIDOCR_PERSISTENT=true OCR_OFFLINE=true`;
khóa cũ `APP_ENV_OVERRIDES` chỉ còn là bí danh), `STATE_DIR`, `ALLOWED_SIGNERS`, `SIGNER_IDENTITY`,
`SIGNATURE_POLICY`, `BACKUP_CMD`, `BACKUP_VERIFY_CMD`, `JOBS_WAIT_SECONDS`, `HEALTH_URL`.

- `preflight` (chỉ đọc) **từ chối** khi C1 không đúng (`image` của service ứng dụng trong cấu hình
  thực ≠ `DEPLOY_IMAGE_TAG`), khi container đang chạy không phải image mà tag chỉ tới, khi thiếu biến
  của C3 trong cấu hình hoặc trong container, khi thiếu override bảo trì.
- `update --apply`: nạp image, vào bảo trì trên image ĐÃ DUYỆT, chờ tác vụ nền, sao lưu + kiểm
  restore (mỗi lần chạy một bản sao lưu riêng, không dùng lại theo thời gian; `BACKUP_CMD` do công
  cụ chạy sau khi dừng ghi, còn backup của đơn vị theo hai lần chạy: lần đầu dừng ghi và yêu cầu
  backup, lần sau nhận mã backup mới khi dữ liệu chưa đổi), so dữ liệu trước / sau sao lưu, rồi
  tạo lại ứng dụng trên image mới bằng override **riêng của attempt**
  (`STATE_DIR/attempts/<id>/override-update.yml`). Tag triển khai **chưa** đổi: mọi đường khởi
  động khác vẫn đưa lên image đã duyệt.
- `finish --approve`: kiểm dữ liệu so với baseline bất biến của attempt, rồi mới chuyển
  `DEPLOY_IMAGE_TAG`, tạo lại ở chế độ thường bằng file của đơn vị, kiểm lại; thất bại → đưa tag
  về image đã duyệt trước.
- `rollback app`: chuyển tag về image đã duyệt trước attempt, tạo lại, kiểm.
- `status` / `health`: luôn so container đang chạy với image mong đợi lúc đó, ở mọi trạng thái;
  mã thoát 7 = lệch, 8 = attempt chưa quyết định / chuyển tiếp bị gián đoạn.
- `pin`: không còn file pin. `pin` = báo cáo; `pin --apply` = sửa tag về image đã duyệt; `pin --undo`
  bị từ chối (dùng `rollback app`).
- `rollback legal-off` / `legal-on`: bị từ chối — Legal là biến của đơn vị (C3), bật / tắt bằng cấu
  hình cục bộ và script vận hành.

**Trạng thái bộ cập nhật tự động: EXPERIMENTAL / NOT READY — không khuyến nghị cho production.**
Lý do: chỉ được diễn tập với Docker giả lập trạng thái và với Docker thật trên image thay thế
(busybox) trong Cloud; chưa chạy với script vận hành, boot guard, SurrealDB, image ứng dụng thật và
Docker của máy chủ Ubuntu. Production dùng quy trình thủ công cho tới khi W-OFF-* / W-INT-* đạt.

## 5. Những gì KHÔNG thuộc hợp đồng

Model Agri và các model OCR ở trên volume dữ liệu (không trong gói, không bị chạm); database chỉ
được restore theo quyết định của người có thẩm quyền; không OCR lại, không re-embed tài liệu cũ.
