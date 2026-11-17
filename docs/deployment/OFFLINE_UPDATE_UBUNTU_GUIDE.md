# Cập nhật ChatBot5400 trên máy chủ Ubuntu offline

Áp dụng cho nâng cấp **1.2.0 → 1.3.0-rc.1** (và các gói định dạng 1 sau này). Mọi lệnh chạy **trên máy chủ**, không
cần Internet, không cần registry, không build, không đụng tới firewall/Tailscale/LAN/mật khẩu.

Ký hiệu trong tài liệu (thay bằng giá trị thật của máy chủ — **không** ghi vào repository):

| Ký hiệu | Ý nghĩa | Ví dụ minh họa |
|---|---|---|
| `<DEPLOY>` | thư mục chứa file compose đang chạy | `/srv/example/chatbot5400` |
| `<PROJECT>` | tên compose project | `chatbot5400-example` |
| `<PKG>` | file gói đã chép lên máy chủ | `/srv/example/incoming/ChatBot5400-1.3.0-rc.1-linux-amd64-offline.tar.gz` |
| `<SHA>` | SHA-256 nhận qua kênh tin cậy | 64 ký tự hex |

## 1. Thiết lập một lần

### 1.1 Công cụ

Lần đầu, công cụ được lấy **từ chính gói** sau khi so SHA-256 bằng tay:

```bash
sha256sum <PKG>
```

So sánh với `<SHA>` (kênh tin cậy). Khớp thì giải nén **chỉ thư mục scripts** vào một thư mục tạm và cài:

```bash
mkdir -p /tmp/cb5400-tools && tar -xzf <PKG> -C /tmp/cb5400-tools --wildcards '*/scripts/*' --no-same-owner
```

```bash
sudo install -d -m 0755 /opt/chatbot5400-offline-tools
```

```bash
sudo install -m 0755 /tmp/cb5400-tools/*/scripts/* /opt/chatbot5400-offline-tools/
```

Từ lần cập nhật sau, luôn dùng công cụ **đã cài** (`/opt/chatbot5400-offline-tools`) để kiểm tra gói mới — không chạy
script nằm trong một gói chưa được kiểm tra.

### 1.2 Cấu hình cục bộ

```bash
sudo install -d -m 0750 /etc/chatbot5400
```

```bash
sudo cp /opt/chatbot5400-offline-tools/offline-update.conf.example /etc/chatbot5400/offline-update.conf
```

```bash
sudo nano /etc/chatbot5400/offline-update.conf
```

Điền `DEPLOY_DIR`, `COMPOSE_PROJECT`, `COMPOSE_FILES` (đúng thứ tự file mà máy chủ đang dùng, ví dụ
`docker-compose.yml docker-compose.override.yml`), `MAINTENANCE_OVERRIDE` (file override bảo trì đã có —
OCR_OPERATOR_GUIDE §11), `BACKUP_CMD` / `BACKUP_VERIFY_CMD` (quy trình backup đã phê duyệt của máy chủ, nếu đã có
script), `HEALTH_URL`. File chỉ chứa đường dẫn, không chứa mật khẩu.

Kiểm tra cấu hình compose hiệu lực khớp máy chủ (chỉ đọc):

```bash
cd <DEPLOY> && docker compose -p <PROJECT> -f docker-compose.yml -f docker-compose.override.yml config --services
```

### 1.3 Khóa công khai phát hành (nếu gói được ký)

```bash
echo 'release@chatbot5400 ssh-ed25519 AAAA…(nội dung cb5400_release.pub)' | sudo tee /etc/chatbot5400/allowed_signers
```

Khóa công khai phải nhận qua kênh tin cậy. Chưa có khóa ⇒ bỏ qua, dùng `--expected-sha256`.

## 2. Quy trình cập nhật (A → Q)

Đặt biến phiên làm việc (chỉ trong shell hiện tại):

```bash
T=/opt/chatbot5400-offline-tools
```

### A. Chép gói lên máy chủ

Qua phương tiện được phép, vào thư mục có đủ dung lượng (gói ~5–10 GB; giải nén cần thêm cùng cỡ).

### B. Kiểm tra checksum / chữ ký và giải nén an toàn

```bash
sudo $T/verify-package.sh <PKG> --extract-to /srv/example/incoming/cb5400-1.3.0-rc.1 --expected-sha256 <SHA> --current-version 1.2.0
```

Gói có ký và đã cài khóa: có thể bỏ `--expected-sha256` (chữ ký được kiểm tra tự động; dùng cả hai thì tốt hơn).
Kết quả mong đợi `"result": "VERIFIED"`; mọi lỗi ⇒ dừng, **không** dùng gói. Thư mục giải nén:
`/srv/example/incoming/cb5400-1.3.0-rc.1/ChatBot5400-1.3.0-rc.1-linux-amd64-offline` (gọi là `<DIR>`).

### C–F. Preflight (chỉ đọc)

```bash
sudo $T/preflight.sh --package-dir <DIR> --backup-reference "<mã backup đã phê duyệt hoặc để trống nếu dùng BACKUP_CMD>"
```

Kiểm tra: nền tảng, readiness của gói, compose config hợp lệ, container ứng dụng đang chạy, phiên bản hiện tại được
hỗ trợ, **schema database** = schema của gói, **không có job nền đang chạy/đợi**, tag image chưa bị chiếm, dung lượng
Docker root (≥ 2,5 × image + dự phòng), RAM, override bảo trì, quy trình backup, không có lần cập nhật dang dở. Mọi
`FAIL` ⇒ dừng. Job đang chạy ⇒ đợi xong (hoặc dừng nhận tài liệu mới) rồi chạy lại.

Xem trước kế hoạch (dry-run, không đổi gì):

```bash
sudo $T/update.sh --package-dir <DIR> --backup-reference "<mã backup>"
```

### G → P. Thực hiện

```bash
sudo $T/update.sh --package-dir <DIR> --apply --backup-reference "<mã backup>" --backup-verified
```

(`--backup-verified` chỉ dùng khi người vận hành **đã** kiểm tra khôi phục bản backup theo quy trình phê duyệt và
`BACKUP_VERIFY_CMD` chưa được cấu hình.) Các bước, có ghi nhật ký `STATE_DIR/journal.json`, chạy lại được nếu bị
gián đoạn:

| Bước | Việc | Ứng dụng cũ |
|---|---|---|
| G | `docker load -i images/…tar`; kiểm tra image ID = manifest | vẫn chạy |
| H | gắn tag `chatbot5400:rollback-<thời điểm>` cho image ĐANG chạy | vẫn chạy |
| I | `BACKUP_CMD` (hoặc ghi lại `--backup-reference`) | vẫn chạy |
| J | `BACKUP_VERIFY_CMD` (hoặc `--backup-verified`) | vẫn chạy |
| K | (chỉ với `--sync-source`) đồng bộ mã nguồn từ git bundle — xem §3 | vẫn chạy |
| L | sinh override riêng trong `STATE_DIR` (image mới, `pull_policy: never`, `OCR_RAPIDOCR_PERSISTENT=true`, `OCR_OFFLINE=true`); **không sửa** `.env` hay file compose; so cấu hình hiệu lực trước/sau: dịch vụ DB phải **giống hệt**, không thêm cổng/dịch vụ | vẫn chạy |
| – | chép trọng số RapidOCR từ venv của container **cũ** lên volume (kiểm SHA-256) | vẫn chạy |
| M+N | tạo lại **chỉ** container ứng dụng: `up -d --no-deps --no-build --pull never --force-recreate open_notebook` kèm override bảo trì (cổng chỉ 127.0.0.1) | thay bằng bản mới, ở chế độ bảo trì |
| O | API health (loopback), `import docling`, `ocr.cli status`, `ocr.cli readiness --check` (chỉ cục bộ), `ocr.cli custom status` | |
| P | kết quả `awaiting_approval` (OK) hoặc `failed` (giữ chế độ bảo trì, hướng dẫn rollback) | |

Database container **không** bị dừng hay tạo lại ở bất kỳ bước nào.

### P (tiếp). Nghiệm thu chức năng trong chế độ bảo trì

Qua SSH tunnel tới `127.0.0.1:8502` / `:5055`:

1. Đăng nhập admin → OCR Engine Manager: engine đang dùng, Agri (phiên bản, SHA-256), "Sẵn sàng xử lý offline".
2. Tải một PDF không nhạy cảm, chế độ **Tiêu chuẩn** — kết quả như trước.
3. (Nếu được phê duyệt) bật Legal: thêm `OCR_LEGAL_NORMALIZATION_ENABLED=true` vào `APP_ENV_OVERRIDES` của file cấu
   hình rồi `sudo $T/rollback.sh legal-on` (tạo lại container ứng dụng), chọn "Văn bản pháp lý" trong cài đặt, tải
   lại PDF thử.
4. Kiểm tra mạng bị chặn thật:

```bash
sudo $T/healthcheck.sh --prove-offline
```

### Q. Mở lại cho người dùng (sau phê duyệt)

```bash
sudo $T/finish.sh --approve "<người phê duyệt>"
```

Tạo lại container ứng dụng **không** kèm override bảo trì (cổng như cũ).

## 3. Đồng bộ mã nguồn offline (tùy chọn)

Chỉ cần nếu thư mục triển khai là git checkout và muốn file compose/script khớp phiên bản mới. `--sync-source`:
`git bundle verify` → `git fetch` bundle vào `refs/cb5400-offline/<version>/*` → tạo tag release nếu chưa có →
**chỉ fast-forward** (`merge --ff-only` trên nhánh, `checkout --detach` nếu đang detached). Lịch sử khác nhánh, commit
cục bộ hoặc thay đổi cục bộ xung đột ⇒ git từ chối, công cụ dừng, không đổi gì. `.env`, override và file không theo
dõi không bị đụng. Không `reset --hard`, không tạo nhánh `main`, không cần remote.

Không dùng git: `source/…-src.tar.gz` là bản `git archive` để so sánh / chép thủ công file cần thiết.

## 4. Gián đoạn giữa chừng

```bash
sudo $T/status.sh
```

- Dừng trước M+N: chạy lại đúng lệnh `update.sh … --apply …` — các bước đã xong được bỏ qua (image không load lại).
- Dừng sau M+N hoặc kiểm tra thất bại: `sudo $T/rollback.sh interrupted` (về image cũ, chế độ bảo trì) — xem
  [OFFLINE_UPDATE_ROLLBACK.md](OFFLINE_UPDATE_ROLLBACK.md).
- Một gói **khác** sẽ bị từ chối cho tới khi lần cập nhật dang dở được kết thúc hoặc rollback.

## 5. Không làm

`git pull`, `docker compose up` không kiểm soát, `docker compose down` (nhất là `-v`), `docker pull`, `docker system
prune`, xóa image cũ, mở Internet, đổi firewall, đổi mật khẩu, mở thêm cổng, restore database khi schema không đổi.

## 6. Dọn dẹp (thủ công, sau khi ổn định một thời gian)

Giữ image `rollback-*` và image v1.2.0 tới khi chủ dự án quyết định. Thư mục giải nén gói có thể xóa bằng tay sau
nghiệm thu; công cụ không tự xóa gì.

## 7. Mã thoát

0 OK · 2 tham số/cấu hình · 3 kiểm tra gói thất bại · 4 preflight thất bại · 5 cập nhật/rollback thất bại · 6 đang có
cập nhật khác (lock).

## 8. Kiểm thử gói trên stack cô lập (bắt buộc trước production)

Trên một máy Ubuntu thử nghiệm (hoặc VM / WSL2) **không phải production**, dữ liệu giả:

1. Dựng stack v1.2.0 (image v1.2.0 đã có sẵn từ trước) với volume dữ liệu thử, import một model Agri hợp lệ được phép
   dùng để thử (hoặc bản sao `vie.traineddata` đặt tên khác), xử lý vài PDF tổng hợp
   (`scripts/ocr/generate_phase12_fixtures.py`).
2. **Chặn mạng thật** — một trong hai cách, có bằng chứng:
   - chặn egress của Docker bridge: `sudo iptables -I DOCKER-USER -j DROP` (ghi lại để gỡ: `sudo iptables -D DOCKER-USER -j DROP`),
     hoặc rút cáp/tắt NIC của VM;
   - xác nhận: `sudo $T/healthcheck.sh --prove-offline` báo `outbound network blocked`, và từ máy chủ
     `curl -sS --max-time 5 https://huggingface.co` thất bại.
3. Chạy lần lượt và lưu log: verify → preflight → update `--apply` → nghiệm thu OCR (Tiêu chuẩn, Legal, Agri) →
   kiểm tra dữ liệu cũ còn nguyên (số Source, nội dung, notebook) → `rollback.sh app` → kiểm tra lại → update lại
   (cùng gói; journal cho phép) → `finish --approve`.
4. Kiểm thử lỗi (mỗi trường hợp phải bị **từ chối** và không đổi gì):
   - sửa 1 byte trong gói (`printf x >> <bản sao>.tar.gz`) → verify thất bại;
   - `--platform linux/arm64` → sai nền tảng;
   - manifest bị sửa trong bản sao gói → checksum/chữ ký sai;
   - chữ ký với khóa khác → INVALID signature;
   - ổ đĩa đầy: dùng `MIN_FREE_GB_EXTRA=100000` trong cấu hình thử → preflight FAIL;
   - gián đoạn: `kill` tiến trình update sau bước G → chạy lại tiếp tục, không load lại.
5. Ghi kết quả vào báo cáo nghiệm thu (mẫu ở `docs/ocr/PHASE12_CLOUD_HANDOVER.md` §17). Chỉ khi tất cả đạt mới được
   đánh giá "OFFLINE UPGRADE AND ROLLBACK: VERIFIED".
