# Rollback — ChatBot5400 1.3.0-rc.1 (offline)

Bốn mức rollback, từ nhẹ đến nặng. **Không mức nào khôi phục database** khi schema không đổi (Phase 12: schema 33 ở
cả 1.2.0 và 1.3.0-rc.1; không migration). Công cụ: `/opt/chatbot5400-offline-tools` (gọi là `$T`).

```bash
T=/opt/chatbot5400-offline-tools
```

## 1. Chế độ Legal Document → Standard (không đổi phiên bản)

Cách A — giao diện (không tạo lại container): Cài đặt → OCR Engine Manager → *Chuẩn hóa văn bản sau OCR* →
**Tiêu chuẩn** → *Lưu chế độ chuẩn hóa*. Áp dụng cho tài liệu xử lý **sau** thời điểm này.

Cách B — tắt cổng triển khai (toàn hệ thống dùng Standard, kể cả khi lựa chọn đã lưu là Legal):

```bash
sudo $T/rollback.sh legal-off
```

(tạo lại **chỉ** container ứng dụng với `OCR_LEGAL_NORMALIZATION_ENABLED=false` trong override do công cụ quản lý; giữ
chế độ bảo trì nếu `MAINTENANCE_OVERRIDE` được cấu hình — thêm `--no-maintenance` khi đang ở chế độ bình thường.)

Tài liệu đã xử lý bằng Legal **giữ nguyên** nội dung đã lưu; muốn có bản Standard của một tài liệu thì xử lý lại tài
liệu đó (thủ công, theo quyết định của người dùng). Không có xử lý lại hàng loạt tự động.

Trên stack thử nghiệm Windows: `.\scripts\windows\phase12-test.ps1 legal-gate -State off`.

## 2. Model Agri về phiên bản trước

```bash
sudo $T/rollback.sh agri
```

(= `ocr custom rollback`: về phiên bản đã hoạt động trước lần chuyển gần nhất; model nằm trên volume, không bị gói
cập nhật đụng tới.) Kiểm tra: `docker compose exec open_notebook /app/.venv/bin/python -m open_notebook.ocr.cli custom status`.

## 3. Phiên bản ứng dụng 1.3.0-rc.1 → 1.2.0

Điều kiện: image cũ còn (tag `chatbot5400:rollback-<thời điểm>` do bước H tạo, hoặc image 1.2.0 đang có), manifest
xác nhận `migration_required: false`.

```bash
sudo $T/rollback.sh app --package-dir <DIR>
```

- Dùng tag rollback ghi trong journal (hoặc `--to-image chatbot5400:<tag>`), kiểm tra image tồn tại, so cấu hình hiệu
  lực (DB không đổi, cổng không đổi / chỉ loopback khi bảo trì), tạo lại **chỉ** container ứng dụng với
  `--no-deps --no-build --pull never`.
- Database: **không** dừng, **không** restore.
- Trọng số RapidOCR đã nằm trên volume; bản 1.2.0 với `OCR_RAPIDOCR_PERSISTENT=true` (override vẫn giữ) đọc từ volume
  ⇒ không cần Internet.
- Mã nguồn (nếu đã `--sync-source`): `git -C <DEPLOY> checkout --detach v1.2.0` (git từ chối nếu thay đổi cục bộ xung
  đột; không reset).
- Mở lại cho người dùng sau khi kiểm tra:

```bash
sudo $T/rollback.sh app --to-image <tag rollback> --no-maintenance
```

## 4. Cập nhật bị gián đoạn

```bash
sudo $T/status.sh
```

| Trạng thái journal | Làm gì |
|---|---|
| `in_progress`, chưa có `N_recreated` | ứng dụng cũ vẫn chạy; chạy lại `update.sh … --apply` (tiếp tục) **hoặc** bỏ dở: không cần rollback (image mới chỉ được load thêm) |
| `deployed_pending_checks` / `failed` | `sudo $T/rollback.sh interrupted` → về image trước, giữ bảo trì |
| `awaiting_approval` | đang ở bản mới, bảo trì; nghiệm thu rồi `finish.sh --approve`, hoặc `rollback.sh app` |
| `completed` | bản mới đang chạy bình thường; rollback theo §3 |

## 5. Khi nào cần restore database (ngoài phạm vi công cụ)

Chỉ khi một bản phát hành **có migration** hoặc dữ liệu bị hỏng. Công cụ từ chối mọi gói `migration_required: true`
và từ chối rollback ứng dụng khi manifest báo đổi schema. Khi đó: **dừng**, lập phương án restore riêng (backup đã
kiểm tra khôi phục, thời điểm, dữ liệu mới phát sinh sau backup sẽ mất) và xin phê duyệt. Không bao giờ restore đè
database đang có dữ liệu mới một cách tự động.
