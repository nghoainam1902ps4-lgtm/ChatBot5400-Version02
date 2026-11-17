# Rollback — ChatBot5400 (cập nhật offline, gói định dạng 2)

Bốn mức rollback, từ nhẹ đến nặng. **Không mức nào khôi phục database** khi schema không đổi (Phase 12: schema 33 ở
cả bản 1.2.0 và bản Phase 12; không migration). Công cụ: `/opt/chatbot5400-offline-tools` (gọi là `$T`).

```bash
T=/opt/chatbot5400-offline-tools
```

> Trạng thái xác minh: logic đã kiểm thử với Docker giả lập. Rollback trên Docker thật **chưa chạy** — nghiệm thu
> trên stack cô lập trước (`docs/review/PHASE12D3_WINDOWS_ACCEPTANCE_CHECKLIST.md`, W-OFF).

## 1. Chế độ Legal Document → Standard (không đổi phiên bản)

Cách A — giao diện (không tạo lại container): Cài đặt → OCR Engine Manager → *Chuẩn hóa văn bản sau OCR* →
**Tiêu chuẩn** → *Lưu chế độ chuẩn hóa*. Áp dụng cho tài liệu xử lý **sau** thời điểm này.

Cách B — tắt cổng triển khai (toàn hệ thống dùng Standard, kể cả khi lựa chọn đã lưu là Legal):

```bash
sudo $T/rollback.sh legal-off
```

Tạo lại **chỉ** container ứng dụng với `OCR_LEGAL_NORMALIZATION_ENABLED=false` trong override do công cụ quản lý.
Lệnh **giữ nguyên chế độ mạng hiện tại** của container: đang chạy bình thường thì vẫn bình thường, đang bảo trì
(cổng chỉ loopback) thì vẫn bảo trì. Ép chế độ bằng `--maintenance` hoặc `--no-maintenance`. Cấu hình hiệu lực được
so trước/sau (database, volume, network không đổi), container database được kiểm bằng `docker inspect` trước và
sau, và ứng dụng được health-check; mã thoát khác 0 nếu không đạt. Quyết định bật/tắt cổng được ghi vào journal và
**được giữ lại ở lần cập nhật kế tiếp**.

Tài liệu đã xử lý bằng Legal **giữ nguyên** nội dung đã lưu (trang Source ghi nhãn *Đã chuẩn hóa văn bản pháp lý* và
phiên bản bộ chuẩn hóa); muốn có bản Standard của một tài liệu thì xử lý lại tài liệu đó (thủ công, theo quyết định
của người dùng). Không có xử lý lại hàng loạt, không tự OCR lại, không tự re-embed.

Trên stack thử nghiệm Windows: `.\scripts\windows\phase12-test.ps1 legal-gate -State off`.

## 2. Model Agri về phiên bản trước

```bash
sudo $T/rollback.sh agri
```

(= `ocr custom rollback`: về phiên bản đã hoạt động trước lần chuyển gần nhất; model nằm trên volume, không bị gói
cập nhật đụng tới.) Kiểm tra: `docker compose exec open_notebook /app/.venv/bin/python -m open_notebook.ocr.cli custom status`.

## 3. Phiên bản ứng dụng → image trước lần cập nhật

```bash
sudo $T/rollback.sh app --package-dir <DIR>
```

- **Theo image ID đã kiểm chứng, không theo tag.** Journal ghi image ID của container *trước* attempt (baseline).
  Tag `chatbot5400:rollback-<attempt>` chỉ được dùng nếu nó **vẫn trỏ đúng ID đó**; nếu tag đã bị đổi/xóa, công cụ
  gắn một tag mới vào đúng ID baseline rồi mới dùng. Image baseline không còn trên máy ⇒ từ chối, không đổi gì.
- `--to-image <tag>`: được kiểm định dạng; phải tồn tại; nếu khác image baseline của journal thì bị từ chối trừ khi
  thêm `--force-image` (quyết định của người vận hành, ví dụ về thẳng image v1.2.0 gốc).
- `--package-dir`: gói được xác thực lại; manifest báo `migration_required` ⇒ từ chối (cần quy trình restore riêng).
- **Mã nguồn** (nếu đã `--sync-source`): được đưa về commit ghi trong journal **trước** khi tạo lại container
  (`git checkout --detach <commit cũ>`), chỉ khi checkout đang ở đúng commit phát hành và **không có thay đổi cục bộ**
  trên file theo dõi. Có thay đổi cục bộ ⇒ **không đụng** mã nguồn, in lệnh để người vận hành tự làm. Không
  `reset --hard`, không di chuyển nhánh, không đụng `.env`/file không theo dõi.
- Tạo lại **chỉ** container ứng dụng (`--no-deps --no-build --pull never`), mặc định ở chế độ bảo trì.
- Sau đó: container database phải vẫn là container **của ngay trước lần rollback** (mốc đối chiếu chụp lại lúc này,
  nên một lần reboot hay dữ liệu mới từ sau khi cập nhật không gây báo lỗi sai); container ứng dụng phải chạy đúng
  image ID baseline; health, `import docling`, `ocr.cli status`, readiness cục bộ, Agri, tách đoạn offline, schema, số
  bản ghi (bảo trì: bằng nhau; bình thường: không bảng nào đang có dữ liệu trở thành rỗng) đều phải đạt. Đạt ⇒ `rolled_back`
  (mã 0). Không đạt ⇒ `rollback_failed` (mã 5): **không** báo thành công; điều tra rồi chạy lại.
- Nếu đã ghim image (`pin.sh --apply`): tên image của triển khai được trỏ về image baseline.
- Database: **không** dừng, **không** restore.
- Mở lại cho người dùng sau khi kiểm tra:

```bash
sudo $T/rollback.sh app --no-maintenance
```

Sau rollback, lần cập nhật kế tiếp là **attempt mới**: backup mới, xác minh khôi phục mới, tag rollback mới — không
dùng lại gì của attempt cũ (dữ liệu có thể đã thay đổi từ lúc backup cũ).

## 4. Cập nhật bị gián đoạn

```bash
sudo $T/status.sh
```

| Trạng thái journal | Làm gì |
|---|---|
| `in_progress`, chưa có `N_recreated` | ứng dụng cũ vẫn chạy; chạy lại `update.sh … --apply` với cùng gói (tiếp tục cùng attempt) **hoặc** `rollback.sh interrupted` để đóng attempt: ứng dụng **không** bị tạo lại hay khởi động lại, mã nguồn (nếu đã đồng bộ) được đưa về commit cũ. Bắt buộc dùng cách thứ hai nếu attempt đã đồng bộ mã nguồn |
| `in_progress`, đã có `N_recreated` | `sudo $T/rollback.sh interrupted` |
| `deployed_pending_checks` / `failed` | `sudo $T/rollback.sh interrupted` → về image baseline, giữ bảo trì |
| `awaiting_approval` | đang ở bản mới, bảo trì; nghiệm thu rồi `finish.sh --approve`, hoặc `rollback.sh app` |
| `finish_failed` | đã ở chế độ bình thường nhưng kiểm tra không đạt; sửa rồi `finish.sh --approve`, hoặc `rollback.sh app` |
| `completed` | bản mới đang chạy bình thường; rollback theo §3 |
| `rollback_failed` | image cũ đã khởi động nhưng chưa đạt kiểm tra; điều tra, rồi `rollback.sh app` lại |

`rollback.sh interrupted` giống `app` khi container đã được tạo lại. Nếu lần cập nhật từng báo `DATABASE CONTAINER CHANGED`, rollback vẫn đưa ứng
dụng về image cũ nhưng **không báo thành công** (`rollback_failed`, mã 5) cho tới khi người vận hành đã điều tra
container database và chạy lại với `--acknowledge-db-change`. Cờ này chỉ ghi nhận việc đã điều tra; nó **không** sửa
gì ở database.

Journal hỏng: xem Ubuntu guide §5 (không tự tạo journal mới; có bản sao `journal.json.bak`; đường cuối cùng là đổi
tên hai file hỏng rồi `rollback.sh app --to-image <tag rollback>`).

## 5. Khi nào cần restore database (ngoài phạm vi công cụ)

Chỉ khi một bản phát hành **có migration** hoặc dữ liệu bị hỏng. Công cụ từ chối mọi gói `migration_required: true`
và từ chối rollback ứng dụng khi manifest báo đổi schema. Khi đó: **dừng**, lập phương án restore riêng (backup đã
kiểm tra khôi phục, thời điểm, dữ liệu mới phát sinh sau backup sẽ mất) và xin phê duyệt. Công cụ **không bao giờ**
restore database, kể cả khi rollback không đạt kiểm tra.
