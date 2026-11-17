# Phase 12D4 — Rà soát lại công cụ cập nhật offline (định dạng gói 2)

Phạm vi: `scripts/offline/offline_package.py` (≈ 3 400 dòng), 9 wrapper, `offline-update.conf.example`, tại `8d0c438`.
Giới hạn về tính độc lập: [PHASE12D4_FABLE_RE_REVIEW.md](PHASE12D4_FABLE_RE_REVIEW.md) §0.

## 0. Cái gì là thật, cái gì là mô phỏng

| Thành phần | Ở 12D4 |
|---|---|
| git (bundle, update-ref, fetch, merge, checkout), tar, SHA-256, ssh-keygen | **thật** |
| `build-package.sh` | chạy thật, với Docker giả lập |
| Docker Engine, `docker save` / `load`, image store, Docker Compose | **mô phỏng** (fake `docker` của `tests/test_offline_package.py`) |
| PowerShell | **không chạy** |
| Máy chủ, reboot, script vận hành / boot guard của production | **không có thông tin, không truy cập** |

Mọi kết luận "đứng vững" dưới đây là MOCK VERIFIED. Không có gì được xác minh trên Docker thật.

Nhận xét về bộ test của 12D3: cả năm lỗi nặng nhất dưới đây đều tái hiện được **bằng chính Docker giả lập của 12D3**.
172 test của 12D3 đạt không phải vì giả lập quá yếu, mà vì chúng không hỏi các câu hỏi này.

## 1. Build gói — F-04, F-05, F-27

| Kiểm | Kết quả |
|---|---|
| Quy tắc phiên bản (`VERSION` 1.2.0 ⇒ chỉ `1.2.0` / `1.2.0-<hậu tố>`), trước mọi lệnh Docker | Đứng vững (Bash chạy thật) |
| Ref tạm, `bundle verify`, `list-heads`, base là tổ tiên | Đứng vững (git thật) |
| Ref tạm đã tồn tại | Được khôi phục sau build, không lọt vào bundle (đọc mã) |
| Fetch đúng một ref, không wildcard, fast-forward, không mất thay đổi cục bộ | Đứng vững (git thật) |
| Detached HEAD, working tree bẩn | Đứng vững |
| Nhiều build đồng thời cùng phiên bản | Bundle không lẫn (kiểm `list-heads`), **nhưng** tiến trình thứ hai chết bằng `FileExistsError` không bắt và khối dọn dẹp của nó xóa thư mục stage và gói của tiến trình thứ nhất — **R2-18** |
| Build lại thất bại | **Xóa gói tốt của lần trước**, để lại file `.sha256` mồ côi — **R2-18** |
| Tag release đã tồn tại trỏ commit khác (máy chủ) | Giữ nguyên, không báo — **R2-09** |
| Image build từ commit khác | Chỉ bị chặn khi image có nhãn `revision`; image không nhãn, thậm chí không có `/app/VERSION`, vẫn được đóng gói kèm bundle của commit này — **R2-08** |
| Kill giữa `git merge` và bước ghi `K_source` (máy chủ) | Guard "đã đồng bộ" mất tác dụng; `previous_commit` bị ghi đè bằng commit phát hành; rollback không đưa mã nguồn về — **R2-15 (P2)** |
| PowerShell | **NOT VERIFIED.** Kiểm thứ tự dòng của 12D3 không phải kiểm thử thực thi. Nghi ngờ chưa xác minh **R2-22**: `docker image inspect $tag 2>$null` với `$ErrorActionPreference = 'Stop'` có thể dừng script trên Windows PowerShell 5.1 khi tag chưa tồn tại |

**OFFLINE UPDATE BUILD LOGIC: PARTIAL.**

## 2. Attempt, backup, journal — F-08, F-13

Phần gốc của F-08 đã sửa: sau `rolled_back` / `completed` / `failed` là attempt mới với backup mới; chuỗi ba lần cập
nhật và rollback về đúng image, một backup cho mỗi attempt (`test_verified_three_updates_and_rollbacks_…`).

**R2-04 (P2) — backup không tương ứng với dữ liệu lúc tạo lại:**

| Kịch bản | Kết quả |
|---|---|
| Backup xong → update dừng trước khi tạo lại → người dùng tạo tài liệu → chạy lại trong `BACKUP_MAX_AGE_MINUTES` | **Backup cũ được chấp nhận** (1 backup lúc 120 bản ghi; tạo lại lúc 500 bản ghi; thành công) |
| Một lần chạy liền mạch | Backup và kiểm khôi phục chạy khi ứng dụng **còn mở cổng** (`0.0.0.0`); dữ liệu ghi trong lúc đó không nằm trong backup nào |
| Cùng `--backup-reference bk` cho hai attempt | Được chấp nhận |
| Bước J ghi ngày tương lai (đồng hồ bị chỉnh) | Luôn "còn mới" |
| `BACKUP_MAX_AGE_MINUTES=inf` | `OverflowError` không bắt |

TTL không chứng minh dữ liệu chưa đổi. Thiếu liên kết giữa: bằng chứng backup ↔ attempt ↔ mốc dữ liệu ↔ thời điểm
vào bảo trì. Dữ liệu đổi nhưng số bản ghi không đổi, file upload đổi cùng kích thước, model Agri đổi phiên bản,
credential hay settings đổi: **không có kiểm tra nào thấy**. Cấu hình Compose đổi giữa hai lần chạy: thấy được ở
phép so cấu hình. Reboot giữa backup và tạo lại: bị từ chối (đúng, hơi chặt).

Journal (F-13): ghi nguyên tử + bản sao, journal hỏng ⇒ dừng có hướng dẫn — đứng vững. Mô phỏng kill:

| Kill tại | Kết quả |
|---|---|
| ngay sau `compose up`, trước bước `N_recreated` | Phục hồi được: update bị từ chối, `rollback interrupted` về image cũ — **đạt** |
| giữa `archive()` và lần ghi đầu của journal mới | **Mất journal** (cả `.bak`); `status` nói "no update recorded", mã 0 — R2-13 |
| sau `compose up` của `finish`, trước bước ghi | Ứng dụng mở công khai, journal vẫn `awaiting_approval` / `maintenance: true`, `status` mã 0 — R2-13 |
| giữa `git merge` và `K_source` | R2-15 |
| sau `docker tag` của `pin`, trước khi ghi `applied` | `pin --undo` nói "nothing to undo" — R2-16 |

## 3. Ghim image — F-11: PARTIALLY FIXED

F-11 gốc (P1): một `docker compose up -d` thông thường âm thầm đưa bản cũ trở lại. 12D3 trả lời bằng ba thứ: phát hiện
lệch (mã thoát 7), `compose-command.txt`, và `pin` **tùy chọn**. Đánh giá:

| Tình huống | Hành vi | Đủ chưa? |
|---|---|---|
| Không pin; người vận hành / script / boot guard chạy `compose up -d` thường | Image cũ quay lại; chỉ `status` / `health` báo — nếu có ai chạy | **Chưa**: vẫn đúng lỗi F-11, chỉ thêm khả năng phát hiện thụ động |
| Đã pin; script dùng `docker compose -f docker-compose.yml up -d` | Image mới được giữ; **biến offline mất** (`COMPOSE_FILE` bị bỏ qua khi có `-f`); `status` = 7 | Một nửa |
| Đã pin; `up --build` | Không bảo vệ (đã ghi trong tài liệu) | Chưa |
| `docker restart`, reboot (không `compose up`) | Container giữ image đang chạy — không cần pin | Cần xác minh trên Docker thật |
| Attempt kế tiếp đang dang dở, rồi `compose up` thường | **`status` và `health` trả 0** (drift bị tắt ở `in_progress` / `failed` / `rollback_failed`) — R2-13 | **Chưa** |
| Đã rollback, rồi `compose up` thường | Cổng Legal và biến offline mất, `status` 0 — R2-13 | Chưa |
| Pin hai lần rồi undo | Tên image của triển khai **ở lại image mới** — R2-16 | Sai |
| Cập nhật lần hai rồi pin | **Bị từ chối** ("cannot pin automatically"); pin cũ âm thầm chạy 1.3.0 thay vì 1.3.1 — R2-16 | Sai |
| Update bị từ chối, rồi chạy `compose-command.txt` | **Khởi động image chưa duyệt** — R2-12 (P1) | Sai |

Kết luận về thiết kế: pin tùy chọn **không tương xứng** với mức P1 của F-11. Máy chủ production có thể dùng script
Compose và boot guard riêng; công cụ không được thiết kế dựa trên giả định rằng mọi người sẽ dùng một lệnh đặc biệt.
Cần một **hợp đồng tích hợp** (12D5), ví dụ:

1. Công cụ quản lý **một** file override cố định trong thư mục triển khai (image + biến offline), được đưa vào danh
   sách file của script vận hành **một lần** bởi người vận hành; từ đó mọi `up` (thường, bảo trì, restart, reboot)
   đều dùng nó. Nội dung file chỉ đổi ở `finish` / `rollback` thành công.
2. `preflight` từ chối khi file override đó không nằm trong cấu hình hiệu lực mà script vận hành tạo ra (so
   `docker compose config` của đúng lệnh vận hành, do người vận hành khai báo trong file cấu hình).
3. `status` luôn so với "phiên bản được duyệt gần nhất", độc lập với attempt hiện tại.

Thiếu thông tin về script vận hành thật ⇒ **LOCAL GATE** (chủ dự án mô tả lệnh / script, không cần truy cập production).

## 4. Finish, rollback, database — F-09, F-21, F-23, F-24

**R2-05 (P1) — hồi quy do commit `7c23329`.** Để tránh báo sai sau nghiệm thu / reboot, 12D3 đổi từ mốc đầu attempt
sang mốc chụp ngay trước mỗi lần tạo lại. Hệ quả:

| Kịch bản (giữa `update` và `finish`, hoặc trong lúc `finish`) | Kết quả |
|---|---|
| Container database bị thay bằng container khác, volume khác, mọi bảng 0 dòng | `finish` mã 0, **`completed`**, `status` 0 |
| 120 / 7 / 31 / 5400 / 12 dòng còn 1 / 1 / 1 / 1 / 1 trong lúc `finish` tạo lại | **`completed`** (chế độ bình thường chỉ lỗi khi bảng về 0) |
| Như trên với `update --no-maintenance` | `awaiting_approval` |
| Không đọc được số bản ghi trước khi tạo lại, sau đó mọi bảng rỗng | update mã 0, rồi `completed` (mốc `None` ⇒ bỏ qua kiểm tra) |
| Phiên bản mới không truy vấn được DB; rollback; image cũ thấy 0 dòng | `rolled_back`, mã 0 — dù baseline của journal ghi 120 nguồn |
| `finish` báo `DATABASE CONTAINER CHANGED` (mã 5); chạy `finish` lần nữa | **`completed`** — cờ `db_changed` vẫn `true` nhưng `finish` không đọc nó |

Phân biệt cần có (12D5): thay đổi hợp lệ khi nghiệm thu (số bản ghi **tăng**, container DB cùng ID) ↔ mất dữ liệu
(giảm, hoặc container / mount khác) ↔ chưa xác minh (không đọc được). Chỉ loại đầu được tự động chấp nhận. Đếm số
bản ghi không phải danh tính: nên băm danh sách id theo bảng. Volume cùng tên bị tạo lại, bind mount bị thay nội
dung: không phân biệt được bằng `docker inspect` hiện tại (cần `docker volume inspect … CreatedAt` hoặc file dấu).

Các mục khác:

| Finding | Kết quả |
|---|---|
| F-09 | Health check trước khi báo thành công: có. `finish` thất bại ở chế độ bình thường ⇒ `finish_failed`, có đường quay lại (`finish` lại hoặc `rollback app`); không tự restore DB — đúng |
| F-23 | Giữ chế độ mạng: có. Mới: dịch vụ không publish cổng (sau reverse proxy) vẫn được ghi `maintenance: true` — R2-20; cổng Legal cũ khi tiếp tục attempt — R2-17 |
| F-24 | Rollback theo image ID, chuỗi nhiều lần cập nhật về đúng image: có. Không journal ⇒ `--to-image` nhận mọi image cục bộ không cần `--force-image` — R2-20 |

**OFFLINE UPDATE TRANSACTION SAFETY: FAIL** (R2-05, R2-12 mức P1; R2-04, R2-13, R2-15, R2-16 mức P2).
**DATABASE PRESERVATION: PARTIAL** — danh tính container quanh một lần tạo lại được kiểm (mock); bảo toàn dữ liệu
giữa các bước thì không.

## 5. Danh tính image — F-20, F-25

| Kiểm | Kết quả |
|---|---|
| File archive trước `docker load`: đúng một image, đúng một tag, digest cấu hình + `diff_ids` khớp manifest | Đứng vững (archive do test tạo; bố cục docker-archive và OCI) |
| Tag của gói đã thuộc image khác | Preflight từ chối — **trừ khi** image đó có cùng layer |
| **Cùng layer, khác cấu hình** (entrypoint `sh -c …`, user root, env khác) | `same_image` trả "layer digests (other image store)"; preflight báo OK — **R2-06** |
| Tag bị đổi giữa `docker load` và `up` trong lần chạy liền mạch (giữa đó là backup nhiều giờ) | Không kiểm lại trước `up`; chỉ health check sau khi image đã chạy mới thấy |

Hai image cùng layer không nhất thiết cùng Entrypoint, Cmd, User, Env, Labels, WorkingDir, ExposedPorts. Layer không
phải danh tính đầy đủ. Mức độ thực tế hiện tại là thấp (update luôn `docker load` lại nên tag trỏ về image của
archive — trong mô phỏng), nhưng tiêu chí đã bị nới để tương thích image store và báo cáo 12D3 không nói điều đó.
Sửa: manifest ghi băm chuẩn hóa của phần `config`; sau load so với `docker image inspect --format '{{json .Config}}'`.

**OFFLINE UPDATE IMAGE IDENTITY: PARTIAL.** Docker thật: LOCAL VERIFICATION REQUIRED.

## 6. Chuỗi tin cậy — F-12, F-14, F-26

Đứng vững (tấn công trực tiếp hoặc chạy lại): traversal, đường dẫn tuyệt đối, symlink, hardlink, device, FIFO, entry
trùng, bomb theo tỷ lệ / dung lượng / số entry, đích không rỗng, thiếu dung lượng, dọn thư mục tạm; sửa payload của gói
đã ký (băm từng file khi ghi); giá trị manifest tới YAML / git / docker; đổi file image sau verify (băm lại mỗi lần);
khóa cấu hình qua biến môi trường; file cấu hình / signers ghi được bởi người khác; archive chưa xác thực không kích
hoạt mã nào và không được ghi ra đĩa; manifest và chữ ký được đọc có giới hạn 5 MiB.

Còn lỗi:

| | |
|---|---|
| **R2-07 (P2)** | `verify-report.json` nằm cạnh cây đã giải nén, không kiểm quyền, tự mang cờ `signed`. Cây giải nén bằng `tar` thường + manifest sửa + báo cáo viết tay ⇒ `preflight` 0, `update --apply` 0, image được nạp và chạy — **kể cả khi đã cài `allowed_signers`**. TOCTOU giữa verify và apply phụ thuộc hoàn toàn vào quyền của thư mục giải nén, thứ công cụ không kiểm |
| **R2-19 (P3)** | Trước khi xác thực (đường chữ ký): header GNU long-name / pax được đọc nguyên khối; gói 0,4 MB làm đỉnh RSS tăng từ 18 MB lên 533 MB (tỷ lệ với kích thước khai báo) |
| Lớp tar thứ hai (file image) | Được đọc **sau** khi gói đã xác thực; `getmembers()` nạp toàn bộ chỉ mục — chấp nhận được vì nội dung đã được tin |
| `_check_trusted_file` | Không kiểm thư mục cha, file override bảo trì, các file compose |
| File `.sha256` đi cùng gói | Mã không đọc nó; tài liệu nói rõ không phải kênh tin cậy — đạt |
| Ngoại lệ không phải `Refused` (`TimeoutExpired`, lỗi JSON của `compose config`) | Thoát bằng traceback, để journal giữa bước — chưa tái hiện, ghi nhận |
| Chống phát lại | Không có: gói cũ ký hợp lệ vẫn hợp lệ mãi; chỉ `supported_source_versions` giới hạn — ghi nhận |

Chưa có khóa ký chính thức ⇒ authenticity của gói phát hành **NOT VERIFIED**. Không khóa riêng nào được tạo ngoài
khóa tạm của test; không khóa nào được commit.

**OFFLINE UPDATE PACKAGE TRUST: PARTIAL.**

## 7. Lỗi P1 mới: `compose-command.txt` khởi động image chưa duyệt — R2-12

Mọi attempt ghi đè **cùng một** file `STATE_DIR/image-override.yml` trước các kiểm tra còn có thể từ chối. Lệnh trong
`compose-command.txt` — thứ tài liệu gọi là "lệnh duy nhất được phép" — tham chiếu đúng file đó.

1. 1.3.0 `completed`. `compose-command.txt` được ghi.
2. `update` lên 1.3.1 bị **từ chối** ở bước RapidOCR. Chưa có gì được tạo lại. Journal: `in_progress`.
3. Người vận hành (hoặc script khởi động lại) chạy `compose-command.txt` — không đổi một byte.
4. Container chạy **1.3.1** trên `0.0.0.0`: không bảo trì, không mốc database, không health check, không phê duyệt.
5. `status` mã 0. `health` mã 0. Vẫn vậy sau `rollback interrupted` (mã 0).

Đối xứng: rollback bị từ chối để lại override trỏ image cũ trong khi journal ghi `completed`; `legal-on` trên container
đã lệch ghi override trỏ image cũ. Sửa: override theo attempt; con trỏ "hiện hành" chỉ đổi ở `finish` / `rollback`
thành công; dọn khi từ chối.

## 8. Tổng hợp theo mục chỉ thị

| Mục | Đánh giá |
|---|---|
| Build | PARTIAL (R2-08, R2-09, R2-15, R2-18; PowerShell chưa chạy) |
| Transaction | **FAIL** |
| Package trust | PARTIAL (R2-07, R2-19) |
| Image identity | PARTIAL (R2-06) |
| Database | PARTIAL (R2-05) |
| Pin | PARTIAL — cần hợp đồng tích hợp |
| Artifact / tiktoken | PARTIAL (R2-10) |
| Interruption | PARTIAL (4 cửa sổ kill không an toàn trong 5 đã thử) |
