# Cập nhật ChatBot5400 trên máy chủ Ubuntu offline

Áp dụng cho gói định dạng **2** (Phase 12D3). Mọi lệnh chạy **trên máy chủ**, không cần Internet, không cần registry,
không build, không đụng tới firewall/Tailscale/LAN/mật khẩu.

> **Trạng thái xác minh.** Toàn bộ logic dưới đây đã được kiểm thử với Docker **giả lập** (git, tar, SHA-256,
> ssh-keygen thật). Hành vi của Docker Engine / Compose thật, PowerShell, OCR thật **chưa được chạy** ở Cloud —
> bắt buộc nghiệm thu trên stack cô lập (§9, `docs/review/PHASE12D3_WINDOWS_ACCEPTANCE_CHECKLIST.md`) trước khi dùng
> cho production.

Ký hiệu (thay bằng giá trị thật của máy chủ — **không** ghi vào repository):

| Ký hiệu | Ý nghĩa | Ví dụ minh họa |
|---|---|---|
| `<DEPLOY>` | thư mục chứa file compose đang chạy | `/srv/example/chatbot5400` |
| `<PROJECT>` | tên compose project | `chatbot5400-example` |
| `<VERSION>` | phiên bản của gói | `1.2.0-phase12.1` (gói thử) · `1.3.0-rc.1` (chỉ từ commit phát hành) |
| `<PKG>` | file gói đã chép lên máy chủ | `/srv/example/incoming/ChatBot5400-<VERSION>-linux-amd64-offline.tar.gz` |
| `<SHA>` | SHA-256 nhận qua **kênh tin cậy riêng** | 64 ký tự hex |

**Kênh tin cậy** là kênh *khác* với kênh mang gói (đọc qua điện thoại, tin nhắn nội bộ đã xác thực, biên bản giấy).
File `*.sha256` đi cùng gói trên cùng USB/thư mục **không** phải kênh tin cậy: ai sửa được gói cũng sửa được file đó.

## 1. Thiết lập một lần

### 1.1 Công cụ

Lần đầu, công cụ được lấy **từ chính gói** sau khi so SHA-256 bằng tay:

```bash
sha256sum <PKG>
```

So sánh với `<SHA>`. Khớp thì giải nén **chỉ thư mục scripts** vào một thư mục tạm **do `mktemp` tạo** (không dùng
đường dẫn cố định trong `/tmp`: người dùng cục bộ khác có thể đặt sẵn file ở đó):

```bash
TOOLS_TMP="$(mktemp -d)"
```

```bash
tar -xzf <PKG> -C "$TOOLS_TMP" --wildcards '*/scripts/*' --no-same-owner
```

```bash
sudo install -d -o root -g root -m 0755 /opt/chatbot5400-offline-tools
```

```bash
sudo install -o root -g root -m 0755 "$TOOLS_TMP"/*/scripts/* /opt/chatbot5400-offline-tools/
```

```bash
rm -r "$TOOLS_TMP"
```

Từ lần cập nhật sau, luôn dùng công cụ **đã cài** để kiểm tra gói mới. Script nằm trong một gói chưa được xác thực
**không bao giờ** được chạy; công cụ nằm trong gói không phải là gốc tin cậy.

### 1.2 Cấu hình cục bộ

```bash
sudo install -d -o root -g root -m 0750 /etc/chatbot5400
```

```bash
sudo install -o root -g root -m 0640 /opt/chatbot5400-offline-tools/offline-update.conf.example /etc/chatbot5400/offline-update.conf
```

```bash
sudo nano /etc/chatbot5400/offline-update.conf
```

Điền `DEPLOY_DIR`, `COMPOSE_PROJECT`, `COMPOSE_FILES` (đúng thứ tự file máy chủ đang dùng), `MAINTENANCE_OVERRIDE`
(file override bảo trì đã có — OCR_OPERATOR_GUIDE §11), `BACKUP_CMD` / `BACKUP_VERIFY_CMD` (quy trình backup đã phê
duyệt), `HEALTH_URL`. File chỉ chứa đường dẫn, không chứa mật khẩu.

File này quyết định lệnh nào chạy với quyền root (`BACKUP_CMD`). Công cụ **từ chối chạy** nếu file cấu hình hoặc
`allowed_signers` thuộc người dùng khác hoặc ghi được bởi nhóm/người khác. Không còn ghi đè từng khóa bằng biến môi
trường `CB5400_*`; chỉ `CB5400_OFFLINE_CONFIG` (đường dẫn file) được đọc.

### 1.3 Khóa công khai phát hành (nếu gói được ký)

```bash
echo 'release@chatbot5400 ssh-ed25519 AAAA…(nội dung cb5400_release.pub)' | sudo tee /etc/chatbot5400/allowed_signers
```

```bash
sudo chown root:root /etc/chatbot5400/allowed_signers && sudo chmod 0644 /etc/chatbot5400/allowed_signers
```

Khóa công khai phải nhận qua kênh tin cậy. Chưa có khóa ⇒ dùng `--expected-sha256`. Hiện **chưa có khóa ký chính
thức**: không có gói nào được coi là "đã xác thực bằng chữ ký".

## 2. Quy trình cập nhật

```bash
T=/opt/chatbot5400-offline-tools
```

### A. Chép gói lên máy chủ

Vào thư mục có đủ dung lượng (gói ~5–10 GB; giải nén cần thêm cùng cỡ — công cụ kiểm tra trước khi ghi).

### B. Xác thực rồi mới giải nén

```bash
sudo $T/verify-package.sh <PKG> --extract-to /srv/example/incoming/cb5400-<VERSION> --expected-sha256 <SHA> --current-version 1.2.0
```

Thứ tự bên trong (không bước nào ghi ra đĩa trước khi gói được xác thực):

1. SHA-256 của cả gói so với `--expected-sha256` (nếu có).
2. Duyệt **mọi** entry của archive trong bộ nhớ: từ chối đường dẫn tuyệt đối, `..`, `.`, `\`, symlink, hardlink,
   file đặc biệt, **tên trùng**, nhiều thư mục gốc, quá số entry / dung lượng / tỷ lệ nén.
3. Đọc `manifest.json` và chữ ký **từ archive vào bộ nhớ**, kiểm chữ ký với khóa đã cài.
4. Không có hash kênh tin cậy **và** không có chữ ký hợp lệ ⇒ **từ chối, không giải nén gì**.
5. Kiểm dung lượng trống, giải nén vào thư mục tạm `…partial-<pid>`; với gói có chữ ký hợp lệ, **từng file** được so
   SHA-256 với manifest ngay khi ghi. Lỗi bất kỳ ⇒ xóa thư mục tạm.
6. Kiểm toàn vẹn (thiếu/thừa file, SHA256SUMS), định dạng mọi trường manifest, nền tảng, phiên bản nguồn, schema.
7. Đọc **bên trong file image** (không `docker load`): chỉ được chứa đúng **một** image với đúng **một** tag ghi
   trong manifest; digest cấu hình và danh sách layer phải khớp manifest. Archive chứa tag khác (ví dụ tag của image
   database) ⇒ từ chối.

Kết quả mong đợi `"result": "VERIFIED"`; mọi lỗi ⇒ dừng, không còn thư mục giải nén. Thư mục giải nén:
`/srv/example/incoming/cb5400-<VERSION>/ChatBot5400-<VERSION>-linux-amd64-offline` (gọi là `<DIR>`).
`verify-report.json` ghi SHA-256 của gói và của manifest; `preflight`/`update` **kiểm lại** manifest, chữ ký và mọi
file mỗi lần chạy — sửa gói sau khi verify sẽ bị phát hiện.

### C–F. Preflight (chỉ đọc)

```bash
sudo $T/preflight.sh --package-dir <DIR> --backup-reference "<mã backup đã phê duyệt hoặc để trống nếu dùng BACKUP_CMD>"
```

Kiểm tra: nền tảng; readiness của gói (gồm **tiktoken `o200k_base` nạp được khi không có mạng** trong image);
compose config hợp lệ; container ứng dụng đang chạy; phiên bản hiện tại được hỗ trợ; **schema database** = schema
của gói; **không có job nền**; **trạng thái sẵn sàng offline của OCR đã ghi nhận trong container hiện tại**
(`ocr.cli readiness`, chỉ đọc); **container database thật** (`docker inspect`) tồn tại và đang chạy; tag image chưa
bị chiếm bởi image khác; dung lượng; RAM; override bảo trì; quy trình backup; không có lần cập nhật chưa quyết định.
Mọi `FAIL` ⇒ dừng.

Xem trước kế hoạch (dry-run, không đổi gì):

```bash
sudo $T/update.sh --package-dir <DIR> --backup-reference "<mã backup>"
```

### G → P. Thực hiện

```bash
sudo $T/update.sh --package-dir <DIR> --apply --backup-reference "<mã backup của LẦN NÀY>" --backup-verified
```

Mỗi lần cập nhật là một **attempt** có mã riêng, baseline riêng và **backup riêng**:

| Bước | Việc | Ứng dụng cũ |
|---|---|---|
| – | xác thực lại gói; mở attempt mới (hoặc tiếp tục đúng attempt dang dở — xem §5); ghi **baseline**: image ID + tên image của container đang chạy, phiên bản, snapshot **container database thật** (ID, image ID, mount, thời điểm khởi động), hash cấu hình Compose hiệu lực, schema, số bản ghi các bảng chính, commit mã nguồn | vẫn chạy |
| G | kiểm lại file image; `docker load`; nhận diện image bằng ID, digest cấu hình **hoặc danh sách layer** (image store khác nhau cho ID khác nhau); ghi `expected_image_id` phía máy chủ | vẫn chạy |
| H | gắn tag `chatbot5400:rollback-<attempt>` cho **image ID baseline** | vẫn chạy |
| I | `BACKUP_CMD` (hoặc ghi lại `--backup-reference`) — **luôn làm mới cho mỗi attempt** | vẫn chạy |
| J | `BACKUP_VERIFY_CMD` (hoặc `--backup-verified`) | vẫn chạy |
| K | (chỉ với `--sync-source`) đồng bộ mã nguồn — §4 | vẫn chạy |
| L | sinh override riêng trong `STATE_DIR` (image mới, `pull_policy: never`, biến offline; mọi giá trị được kiểm định dạng và đặt trong ngoặc kép); **không sửa** `.env` hay file compose; so cấu hình hiệu lực **với baseline lấy trước bước K**: mọi dịch vụ khác, volume, network giống hệt; dịch vụ ứng dụng chỉ khác `image`, `pull_policy`, các biến đã khai báo (và cổng loopback khi bảo trì) | vẫn chạy |
| – | chép trọng số RapidOCR lên volume **và kiểm kết quả** (lỗi/thiếu ⇒ dừng, trừ khi `--accept-missing-rapidocr`) | vẫn chạy |
| – | chụp danh sách file model trên volume như container cũ nhìn thấy (Layout Heron, TableFormer, Tesseract fast/best/OSD, Agri, RapidOCR, EasyOCR: tên + kích thước) | vẫn chạy |
| – | kiểm container database **chưa đổi** so với baseline | vẫn chạy |
| M+N | tạo lại **chỉ** container ứng dụng: `up -d --no-deps --no-build --pull never --force-recreate open_notebook` kèm override bảo trì; ngay sau đó kiểm container database **vẫn là container cũ** (ID, image, mount, thời điểm khởi động) | thay bằng bản mới, bảo trì |
| O | image ID của container = `expected_image_id`; API health (loopback, **không qua proxy**); `import docling`; `ocr.cli status`; `ocr.cli readiness --check`; `ocr.cli custom status`; **tách đoạn/đếm token khi không có mạng**; schema; **số bản ghi không đổi**; **file model trên volume không mất/không đổi kích thước**; container database không đổi | |
| P | `awaiting_approval` (OK) hoặc `failed` (giữ bảo trì, hướng dẫn rollback) | |

Database container **không** bị dừng hay tạo lại ở bất kỳ bước nào; nếu Compose vẫn làm điều đó, công cụ phát hiện
bằng `docker inspect`, dừng lại với `DATABASE CONTAINER CHANGED` và không cho `finish`.

### P (tiếp). Nghiệm thu chức năng trong chế độ bảo trì

Qua SSH tunnel tới `127.0.0.1:8502` / `:5055`:

1. Đăng nhập admin → OCR Engine Manager: engine đang dùng, Agri (phiên bản, SHA-256), "Sẵn sàng xử lý offline".
2. Tải một PDF không nhạy cảm, chế độ **Tiêu chuẩn** — kết quả như trước.
3. (Nếu được phê duyệt) bật cổng Legal — lệnh **giữ nguyên** chế độ mạng hiện tại của container (đang bảo trì thì
   vẫn bảo trì, đang bình thường thì vẫn bình thường; ép bằng `--maintenance` / `--no-maintenance`):

```bash
sudo $T/rollback.sh legal-on
```

   rồi chọn "Văn bản pháp lý" trong cài đặt, tải lại PDF thử. Trang Source hiển thị nhãn *Đã chuẩn hóa văn bản pháp lý*.
4. Kiểm tra mạng bị chặn thật:

```bash
sudo $T/healthcheck.sh --prove-offline
```

### Q. Mở lại cho người dùng (sau phê duyệt)

```bash
sudo $T/finish.sh --approve "<người phê duyệt>"
```

Tạo lại container ứng dụng **không** kèm override bảo trì, rồi **chạy lại toàn bộ kiểm tra của bước O**. Chỉ khi đạt
mới ghi `completed`. Không đạt ⇒ `finish_failed` (mã thoát 5): sửa nguyên nhân rồi chạy lại `finish.sh`, hoặc
`rollback.sh app`.

## 3. Sau khi hoàn tất: lệnh được phép, kiểm tra lệch, ghim image

`finish` ghi lệnh Compose **duy nhất** được dùng để tạo lại ứng dụng vào `STATE_DIR/compose-command.txt` (có override
của công cụ). Thư mục triển khai **không** tự mô tả bản đang chạy: một lệnh `docker compose up -d` thông thường trong
`<DEPLOY>` dùng định nghĩa cũ (image cũ, không có biến offline).

**Phát hiện lệch** — chạy định kỳ và sau mọi thao tác Docker:

```bash
sudo $T/status.sh
```

```bash
sudo $T/healthcheck.sh
```

Cả hai so **image ID của container đang chạy** và các biến môi trường của override với journal; lệch ⇒ in
`IMAGE DRIFT` / `ENVIRONMENT DRIFT` và trả **mã thoát 7**. Khắc phục: chạy lệnh trong `compose-command.txt`.

**Ghim image (tùy chọn, cần quyết định của người vận hành)** để `docker compose up -d` thông thường, khởi động lại
hoặc reboot không quay về bản cũ:

```bash
sudo $T/pin.sh
```

(dry-run: in tên image mà file compose của triển khai đang dùng, image nó sẽ trỏ tới, nội dung file sẽ tạo, và dòng
`COMPOSE_FILE`; không đổi gì.)

```bash
sudo $T/pin.sh --apply
```

Việc `--apply` làm, và chỉ làm:

1. `docker tag <image ID mới> <tên image của triển khai>` — tên này phải đúng là tên mà container **trước khi cập
   nhật** được tạo ra từ đó, nếu không công cụ từ chối. Image cũ vẫn truy cập được qua tag `rollback-<attempt>`.
2. Tạo `<DEPLOY>/docker-compose.offline-pin.yml` (image + `pull_policy: never` + biến offline). File có sẵn cùng tên
   được sao lưu vào `STATE_DIR/config-backups/<attempt>/`.
3. **Không** sửa `.env`, không sửa file compose có sẵn, không đổi cổng, không đổi cấu hình database. Công cụ in dòng
   `COMPOSE_FILE=…:docker-compose.offline-pin.yml`; **người vận hành** tự thêm vào `<DEPLOY>/.env` nếu muốn cả biến
   offline cũng bền vững. Chưa thêm ⇒ image vẫn đúng nhưng `status` báo `ENVIRONMENT DRIFT` sau một lệnh `up` thường.

Hoàn tác: `sudo $T/pin.sh --undo`. `rollback.sh app` tự trỏ tên image về image baseline (giữ file pin, vì file chỉ
nêu tên image của triển khai). Ghim **không** bảo vệ trước `docker compose up --build` / `docker compose build`.

## 4. Đồng bộ mã nguồn offline (tùy chọn)

Chỉ cần nếu `<DEPLOY>` là git checkout và muốn file trong đó khớp phiên bản mới. `--sync-source`:

1. `git bundle verify`; bundle phải chứa đúng ref `refs/cb5400-offline/build/<VERSION>` trỏ đúng commit ghi trong
   manifest (commit và ref đều được kiểm định dạng).
2. `git fetch` **đúng một ref đó** vào `refs/cb5400-offline/incoming/<VERSION>` (không wildcard, không tag khác).
3. Ghi commit/nhánh hiện tại vào journal; tạo tag release nếu chưa có.
4. **Chỉ fast-forward** (`merge --ff-only` trên nhánh, `checkout --detach` nếu đang detached).

Lịch sử khác nhánh, commit cục bộ, hoặc thay đổi cục bộ **xung đột** ⇒ git từ chối, công cụ dừng, checkout giữ
nguyên. Thay đổi cục bộ không xung đột và file không theo dõi (`.env`, override) được giữ nguyên. Không
`reset --hard`, không ghi đè thay đổi cục bộ, không tạo nhánh `main`, không cần remote.

Nếu file compose của bản mới làm đổi dịch vụ database/volume/network so với baseline (lấy **trước** khi đồng bộ),
cập nhật bị từ chối trước khi tạo lại container; `rollback.sh interrupted` đưa mã nguồn về commit cũ.

Không dùng git: `source/…-src.tar.gz` là bản `git archive` để so sánh / chép thủ công.

## 5. Gián đoạn, thử lại, journal

```bash
sudo $T/status.sh
```

| Trạng thái journal | Ý nghĩa | Làm gì |
|---|---|---|
| `in_progress`, chưa có `N_recreated` | ứng dụng cũ vẫn chạy | chạy lại đúng lệnh `update.sh … --apply …` với **cùng gói**: tiếp tục **cùng attempt**; backup của attempt chỉ được dùng lại nếu còn mới (`BACKUP_MAX_AGE_MINUTES`, mặc định 120), quá hạn ⇒ backup lại |
| `in_progress`, đã có `N_recreated` | dừng giữa lúc/ sau khi tạo lại | `rollback.sh interrupted` |
| `deployed_pending_checks` / `failed` | bản mới chạy ở chế độ bảo trì, kiểm tra không đạt | `rollback.sh interrupted` |
| `awaiting_approval` | bản mới, bảo trì, kiểm tra đạt | nghiệm thu rồi `finish.sh --approve`, hoặc `rollback.sh app` |
| `finish_failed` | đã chuyển sang chế độ bình thường nhưng kiểm tra không đạt | sửa nguyên nhân rồi `finish.sh --approve`, hoặc `rollback.sh app` |
| `completed` | bản mới chạy bình thường | cập nhật tiếp theo = **attempt mới** |
| `rolled_back` | đã về image baseline, đã kiểm tra | cập nhật lại = **attempt mới, backup mới** |
| `rollback_failed` | image cũ đã được khởi động nhưng kiểm tra không đạt (hoặc container database bị báo đổi) | điều tra; `rollback.sh app` lại (thêm `--acknowledge-db-change` chỉ sau khi đã điều tra container database) |

Quy tắc:

- Attempt đã kết thúc (`completed`, `rolled_back`, hoặc `failed` mà container đã về image baseline) ⇒ journal cũ được
  **lưu trữ** vào `STATE_DIR/journals/journal-<attempt>.json`; attempt mới **không bao giờ** dùng lại backup, tag
  rollback hay bước nào của attempt cũ.
- Khi còn attempt chưa quyết định (`awaiting_approval`, `deployed_pending_checks`, `finish_failed`,
  `rollback_failed`) mọi `update` — kể cả cùng gói — bị từ chối.
- Một gói **khác** bị từ chối khi attempt dang dở.
- Journal ghi nguyên tử (file tạm + `fsync` + `rename`) và có bản sao `journal.json.bak`. Journal **hỏng** ⇒ mọi lệnh
  dừng với hướng dẫn khôi phục, **không** tự tạo journal mới (đó là bản ghi duy nhất về image để rollback):
  1. giữ nguyên cả hai file; 2. xem image đang chạy: `docker inspect <container> --format '{{.Image}}'`;
  3. nếu `journal.json.bak` đọc được và khớp thực tế: chép đè lên `journal.json`; 4. không còn bản nào đọc được: đổi
  tên cả hai file sang `journal.damaged-<ngày>.*` rồi `rollback.sh app --to-image <tag rollback>`.

## 6. Không làm

`git pull`, `docker compose up` không qua `compose-command.txt` (trừ khi đã ghim), `docker compose down` (nhất là
`-v`), `docker compose up --build`, `docker pull`, `docker system prune`, xóa image cũ, mở Internet, đổi firewall, đổi
mật khẩu, mở thêm cổng, restore database khi schema không đổi.

## 7. Dọn dẹp (thủ công, sau khi ổn định một thời gian)

Giữ image `rollback-*` và image v1.2.0 tới khi chủ dự án quyết định. Thư mục giải nén gói có thể xóa bằng tay sau
nghiệm thu; công cụ không tự xóa gì.

## 8. Mã thoát

0 OK · 2 tham số/cấu hình · 3 kiểm tra gói thất bại · 4 preflight thất bại · 5 cập nhật/finish/rollback thất bại ·
6 đang có cập nhật khác (lock) · **7 lệch (drift) giữa journal và container đang chạy**.

## 9. Kiểm thử gói trên stack cô lập (bắt buộc trước production)

Danh sách đầy đủ, có lệnh PowerShell và WSL2: `docs/review/PHASE12D3_WINDOWS_ACCEPTANCE_CHECKLIST.md` (nhóm W-OFF).
Tóm tắt trên một máy Ubuntu thử nghiệm / VM / WSL2 **không phải production**, dữ liệu giả:

1. Dựng stack v1.2.0 với volume dữ liệu thử, import một model Agri được phép dùng để thử, xử lý vài PDF tổng hợp.
2. **Chặn mạng thật** (`sudo iptables -I DOCKER-USER -j DROP`, gỡ bằng `-D`; hoặc tắt NIC của VM) và chứng minh:
   `healthcheck.sh --prove-offline`, `curl -sS --max-time 5 https://huggingface.co` thất bại.
3. verify → preflight → update `--apply` → nghiệm thu OCR (Tiêu chuẩn, Legal, Agri, tách đoạn) → dữ liệu cũ còn
   nguyên → `finish` → `status` = 0 → `docker compose up -d` thường ⇒ `status` = 7 → lệnh trong
   `compose-command.txt` ⇒ `status` = 0 → `pin.sh --apply` ⇒ `docker compose up -d` thường và **reboot** vẫn ở bản mới.
4. `rollback.sh app` → kiểm tra → thêm dữ liệu → update lại: **backup mới**, attempt mới.
5. Kiểm thử lỗi (mỗi trường hợp phải bị **từ chối** và không đổi gì): sửa 1 byte trong gói; `--platform
   linux/arm64`; manifest bị sửa; chữ ký khóa khác; file image có thêm tag; archive có entry trùng; đĩa đầy
   (`MIN_FREE_GB_EXTRA=100000`); `kill` tiến trình update sau bước G rồi chạy lại; cắt ngắn `journal.json`.
6. Chỉ khi tất cả đạt mới được đánh giá "OFFLINE UPGRADE AND ROLLBACK: VERIFIED".
