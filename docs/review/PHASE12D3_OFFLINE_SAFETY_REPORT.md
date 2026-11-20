# Phase 12D3 — Báo cáo an toàn công cụ cập nhật offline

Phạm vi: `scripts/offline/offline_package.py` (định dạng gói **2**) và các wrapper, sau khi sửa theo audit độc lập
Phase 12D2 (`PHASE12D2_OFFLINE_UPDATE_AUDIT.md`). Finding liên quan: F-04, F-05, F-08, F-09, F-11, F-12, F-13, F-14,
F-20, F-21, F-22, F-23, F-24, F-25, F-26, F-27, T-02.

## 0. Trạng thái xác minh — đọc trước

| Thành phần | Đã chạy thật ở Cloud | Chưa chạy |
|---|---|---|
| git (bundle, update-ref, fetch một ref, fast-forward, checkout) | **Có** — git thật | — |
| tar, SHA-256, ssh-keygen ký / kiểm chữ ký | **Có** | — |
| `build-package.sh` | **Có** (với Docker giả lập) | với Docker thật |
| `build-package.ps1` | Không — chỉ kiểm tĩnh thứ tự lệnh | **PowerShell chưa từng chạy** |
| Docker Engine, `docker save` / `load`, image store | Không — **Docker giả lập có trạng thái** | **toàn bộ** |
| Docker Compose (gộp override, `--no-deps`, `pull_policy`, tên image dịch vụ `build:`) | Không — mô phỏng | **toàn bộ** |
| Nâng cấp / rollback / ghim image / reboot trên máy thật | Không | **toàn bộ** |
| Chặn mạng thật | Không | **toàn bộ** |

Vì vậy mọi kết luận dưới đây là **MOCK VERIFIED**. Không có mục nào được tuyên bố "VERIFIED trên Docker thật". Các
cổng còn mở nằm ở `PHASE12D3_WINDOWS_ACCEPTANCE_CHECKLIST.md` nhóm W-OFF.

Docker giả lập (trong `tests/test_offline_package.py`) mô hình hóa: kho image (tag → ID, cấu hình, danh sách layer),
`save` ghi file **docker-archive thật** và `load` đọc lại nó, một chế độ "image store khác" cho ID khác với cùng layer,
container ứng dụng (image, biến môi trường, cổng publish) và container database (ID, image, mount, thời điểm khởi
động), `docker compose up -d` thông thường (không override), lỗi có chủ đích theo lệnh / theo image. Nó **không**
kiểm chứng cách Compose thật gộp override; trên máy chủ công cụ dùng kết quả `docker compose config` thật để so nên
sai lệch gộp bị từ chối lúc chạy, nhưng điều này chưa được quan sát trên Compose thật.

## 1. Bất biến an toàn (không thay đổi so với Phase 12, nay có oracle đúng)

Công cụ **không bao giờ**: `docker compose down`, `-v` / `--volumes`, `pull`, `build` trên máy chủ, `prune`, `rm`,
`rmi`, `restart`/`stop` database, `exec` vào database, tạo lại container database, đọc hay in `.env` / secret, mở
mạng, restore database, `git reset --hard`, ghi đè thay đổi cục bộ, fetch wildcard.

Bằng chứng:

- `_assert_safe_calls` (T-02 đã sửa): mỗi lệnh Docker ghi lại phải thuộc danh sách cho phép; lệnh Compose chỉ được
  `config` / `ps` / `exec` / `up`; `up` phải **đúng bằng**
  `up -d --no-deps --no-build --pull never --force-recreate open_notebook`; `exec` chỉ vào dịch vụ ứng dụng.
  `test_safe_calls_oracle_can_fail` chứng minh oracle **thất bại** với 19 dạng nguy hiểm (trước đây `compose down
  --pull never` lọt qua).
- `test_tool_source_has_no_destructive_or_wildcard_commands`: mã nguồn công cụ không chứa các lệnh trên, không có
  `reset`, `--hard`, `--force`, `refs/*`.
- Áp dụng trên mọi luồng: update, finish, legal-on/off, rollback, pin.

## 2. Build gói (F-04, F-05, F-27)

| Trước | Sau |
|---|---|
| `git bundle create base..<sha>` ⇒ git từ chối ("empty bundle"): lệnh build theo tài liệu luôn thất bại | ref tạm `refs/cb5400-offline/build/<version>` trỏ đúng commit → bundle `base..ref` → `git bundle verify` → `list-heads` phải chứa đúng ref trỏ đúng commit → xóa ref tạm trong `finally` |
| Lỗi VERSION chỉ lộ sau khi build image nhiều GB | `check-version` chạy **trước mọi lệnh Docker** ở cả hai wrapper; `cmd_build` kiểm lại (VERSION của commit và VERSION trong image) |
| Thư mục stage dở chặn lần chạy sau | bundle chạy trước `docker save`; lỗi bất kỳ ⇒ xóa stage và file gói dở |
| Bundle không có ref ⇒ `--sync-source` không fetch được | manifest ghi `source.bundle_ref`; máy chủ fetch đúng một ref đó |
| Không kiểm base | base phải tồn tại và là tổ tiên của commit |

Kiểm thử với **git thật**: thành công (SHA và tên ref), sai phiên bản (4 dạng, 0 lệnh Docker), base không tồn tại,
base không phải tổ tiên, checkout bẩn, image build từ commit khác, build bị ngắt giữa chừng rồi chạy lại, file image
có thêm tag, `build-package.sh` chạy thật. `VERSION` của repository **vẫn là 1.2.0** — kiểm bằng
`test_version_rule_on_the_real_repository`: `1.3.0-rc.1` bị từ chối, `1.2.0-phase12.1` được chấp nhận.

Đồng bộ mã nguồn trên máy chủ (git thật): fast-forward trên nhánh và trên detached HEAD; chỉ thêm đúng 2 ref (ref
incoming + tag release); lịch sử phân nhánh ⇒ từ chối, HEAD nguyên; thay đổi cục bộ xung đột ⇒ từ chối, file nguyên;
thay đổi cục bộ không xung đột được giữ; commit sai ⇒ từ chối; bundle hỏng ⇒ từ chối; bundle thiếu ref ⇒ từ chối;
bundle có base mà máy chủ không có ⇒ từ chối; `.env` và file không theo dõi không đổi.

## 3. Máy trạng thái cập nhật (F-08, F-09, F-13, F-23, F-24)

### 3.1 Attempt

Mỗi `update --apply` thuộc về một **attempt**: `attempt_id`, baseline (image ID + tên image của container đang chạy,
phiên bản, snapshot container database, hash cấu hình Compose, schema, số bản ghi, commit mã nguồn), tag rollback
riêng, backup + xác minh khôi phục riêng.

| Trạng thái khi chạy `update --apply` | Hành vi |
|---|---|
| không có journal | attempt mới |
| `completed`, `rolled_back` | lưu trữ journal cũ → **attempt mới, backup mới** |
| `failed` và container đã về image baseline | lưu trữ → attempt mới, backup mới |
| `failed` / `in_progress` nhưng container **không** ở image baseline | từ chối: rollback trước |
| `in_progress`, cùng gói, chưa tạo lại container, baseline còn đúng | tiếp tục **cùng attempt**; backup chỉ dùng lại khi còn trong `BACKUP_MAX_AGE_MINUTES`. Ngoại lệ: attempt đã đồng bộ mã nguồn ⇒ **không** tiếp tục (cấu hình trên đĩa đã là của bản mới, phép so database sẽ sai phía) — phải `rollback interrupted` rồi bắt đầu lại |
| `in_progress` / `failed`, **gói khác** | từ chối |
| `awaiting_approval`, `deployed_pending_checks`, `finish_failed`, `rollback_failed` | từ chối mọi update (kể cả cùng gói) |
| journal của công cụ Phase 12 (không có attempt_id / baseline) | `rolled_back`/`completed` ⇒ lưu trữ, attempt mới, **không tin** bước backup cũ; `awaiting_approval` ⇒ `finish` từ chối (không có image ID để xác nhận), rollback cần `--to-image` |
| journal hỏng | mọi lệnh dừng với hướng dẫn; không tự tạo journal mới |

Kịch bản đã kiểm thử: upgrade → rollback → dữ liệu mới → upgrade lại (2 backup, attempt khác, tag rollback khác,
baseline mới có số bản ghi mới); completed → gói phiên bản kế tiếp (baseline là image của lần một; rollback về image
đó, không về v1.2.0; cổng Legal được giữ); failed → rollback → thử lại; tiếp tục attempt với backup còn mới / quá hạn;
backup không hoàn tất; xác minh khôi phục thất bại; rollback bị gián đoạn rồi chạy lại; tag rollback bị đổi; image
baseline bị xóa; journal cũ.

### 3.2 finish, rollback, cổng Legal

- `finish`: tạo lại ở chế độ bình thường rồi chạy lại toàn bộ kiểm tra (image ID, health, Docling, engine, readiness
  cục bộ, Agri, tách đoạn offline, schema, số bản ghi, file model, container database). Không đạt ⇒ `finish_failed`,
  mã 5 — **không** `completed`. Ghi `compose-command.txt`.
- `rollback app|interrupted`: theo **image ID baseline**; khôi phục mã nguồn trước (chỉ khi an toàn); health check với
  image ID kỳ vọng; không đạt ⇒ `rollback_failed`, mã 5. Không bao giờ restore database.
- `rollback legal-on|legal-off`: giữ chế độ mạng hiện tại của container; so cấu hình; kiểm container database;
  health check.

`rollback interrupted` khi **chưa** có gì được tạo lại: không chạy `up`, ứng dụng không bị khởi động lại; chỉ đóng
attempt và khôi phục mã nguồn (đã kiểm thử).

Cổng Legal do người vận hành bật được **giữ qua** lần cập nhật kế tiếp, kể cả sau rollback hay attempt thất bại: giá
trị được đọc từ container đang chạy lúc mở attempt, không từ lịch sử journal (đã kiểm thử: completed → gói kế tiếp →
rollback → cập nhật lại).

### 3.3 Journal

`STATE_DIR` là `0700`, journal / bản sao / override / danh sách file model là `0600` (đã kiểm thử).


Ghi nguyên tử (file tạm, `fsync`, `rename`, `fsync` thư mục) + bản sao `journal.json.bak`. Đã kiểm 4 dạng hỏng (cắt
ngắn, rỗng, sai kiểu, byte rác) trên 5 lệnh (status, update, finish, rollback, pin): tất cả dừng với mã 5 và hướng
dẫn, không traceback, file hỏng không bị thay, không lệnh `up` nào chạy. Đường khôi phục theo hướng dẫn (chép `.bak`)
được kiểm thử; đường cuối (đổi tên hai file hỏng rồi `rollback --to-image`) được kiểm thử.

## 4. Ghim image và phát hiện lệch (F-11)

Công cụ **không** sửa `.env` hay file compose của triển khai (ràng buộc của dự án), nên thư mục triển khai không tự
mô tả bản đang chạy. Ba lớp bảo vệ:

1. **Phát hiện** — `status` và `health` so image ID và biến môi trường của container đang chạy với journal:
   `IMAGE DRIFT` / `ENVIRONMENT DRIFT`, **mã thoát 7**. Áp dụng cho cả trạng thái `rolled_back` (kỳ vọng image
   baseline).
2. **Lệnh duy nhất** — `compose-command.txt` trong `STATE_DIR`.
3. **Ghim (tùy chọn, người vận hành quyết định)** — `pin.sh` dry-run; `--apply`:
   - `docker tag <ID mới> <tên image của triển khai>`; tên này phải đúng là tên mà container trước cập nhật được tạo
     từ đó (nếu không: từ chối, không đoán);
   - tạo `docker-compose.offline-pin.yml` trong thư mục triển khai (file trùng tên được sao lưu);
   - in dòng `COMPOSE_FILE` để **người vận hành** tự thêm vào `.env`;
   - `--undo` và `rollback app` hoàn tác việc trỏ tên image.

Kiểm thử (mock): `docker compose up -d` thường sau `finish` ⇒ image cũ ⇒ `status`/`health` = 7 ⇒ lệnh trong
`compose-command.txt` ⇒ 0; sau `pin --apply`, `up -d` thường giữ image mới; không có file pin trong `COMPOSE_FILE` ⇒
chỉ `ENVIRONMENT DRIFT`; có ⇒ không lệch; `.env` và `docker-compose.yml` không đổi từng byte; rollback sau khi ghim
trỏ tên image về baseline.

**Chưa xác minh trên Compose thật** (cổng W-OFF-14..16): tên image Compose dùng cho dịch vụ `build:`; `up -d` có dùng
image đã gắn tag hay build lại; hành vi sau restart / reboot. Ghim không bảo vệ trước `docker compose up --build`.

## 5. Xác thực gói và archive (F-12, F-14, F-25, F-26)

Thứ tự `verify`: hash cả gói → duyệt archive trong bộ nhớ → đọc manifest + chữ ký từ archive vào bộ nhớ → kiểm chữ ký
→ **không có hash kênh tin cậy và không có chữ ký hợp lệ ⇒ từ chối, chưa ghi gì** → kiểm dung lượng → giải nén vào
thư mục tạm (gói có chữ ký: băm từng file khi ghi) → kiểm toàn vẹn + định dạng manifest → đọc file image → đổi tên
thư mục. Lỗi ở đâu cũng không để lại cây giải nén.

| Tấn công / lỗi đã kiểm thử | Kết quả |
|---|---|
| traversal `..`, `.`, `\`, đường dẫn tuyệt đối, symlink, hardlink, device, FIFO, hai thư mục gốc, **entry trùng tên**, thư mục trùng file | từ chối, không ghi gì |
| bomb: tỷ lệ nén, tổng dung lượng, số entry | từ chối |
| thiếu dung lượng trống; lỗi I/O giữa chừng | từ chối có thông báo, không còn thư mục tạm |
| gói không ký, không có hash | từ chối, thư mục đích không tồn tại |
| chữ ký khóa khác; manifest sửa sau khi ký; file sửa / thêm trong gói đã ký | từ chối, không còn thư mục |
| file `allowed_signers` ghi được bởi người khác | từ chối |
| file image hỏng; file image chứa thêm tag (kể cả tag image database); file image là image khác | từ chối |
| manifest: 21 dạng trường sai định dạng (tag chèn YAML, commit là tùy chọn lệnh, ref ngoài namespace, …) | từ chối |
| gói / payload sửa sau khi verify; báo cáo verify của gói khác | từ chối |
| tag của gói đã thuộc image khác trên máy chủ | preflight từ chối |
| image nạp vào image store khác (ID khác, cùng layer) | **chấp nhận**, nhận diện bằng layer |
| file cấu hình ghi được bởi người khác; ghi đè `BACKUP_CMD` qua biến môi trường | từ chối / bị bỏ qua |
| `http_proxy` chết trong môi trường | health vẫn đạt (không dùng proxy) |

Chuỗi tin cậy: chưa có **khóa ký chính thức** ⇒ authenticity hiện chỉ có thể dựa trên SHA-256 qua kênh tin cậy
riêng; file `.sha256` đi cùng gói không phải kênh tin cậy; công cụ trong gói không phải gốc tin cậy. Không khóa riêng
nào được commit; khóa trong test được tạo tạm trong thư mục test.

## 6. Database và artifact (F-21, F-22)

- Container database: `docker inspect` (ID, image ID, mount, `StartedAt`, đang chạy) trong baseline của attempt (trước
  `--sync-source`) và kiểm lại trước khi tạo lại; **mỗi lần tạo lại** (update, finish, rollback) chụp một **mốc đối
  chiếu ngay trước `up`** (container database, schema, số bản ghi) và so ngay sau `up` cũng như trong health check.
  Mốc theo từng lần tạo lại — không phải mốc đầu attempt — vì giữa cập nhật và `finish`/`rollback` có tài liệu nghiệm
  thu được tải lên và máy chủ có thể reboot (lỗi thiết kế tôi tự phát hiện khi rà lại và đã sửa: bản đầu của 12D3 so
  với mốc đầu attempt nên sẽ báo lỗi sai trong hai tình huống đó). Đã kiểm thử: Compose tạo lại database ⇒
  dừng, `db_changed`, không cho `finish`; database khởi động lại giữa hai lần chạy ⇒ dừng trước khi tạo lại; file
  compose của bản mới đổi dịch vụ database ⇒ từ chối trước khi tạo lại.
- Schema và số bản ghi 5 bảng (`source`, `notebook`, `note`, `source_embedding`, `source_insight`) trước/sau mỗi lần
  tạo lại: ở chế độ bảo trì phải bằng nhau; ở chế độ bình thường chỉ ghi nhận, và thất bại khi một bảng đang có dữ
  liệu trở thành rỗng. Kiểm thử: tải tài liệu nghiệm thu + reboot trước `finish`, rollback nhiều tuần sau, bảng bị
  rỗng sau `finish`.
- RapidOCR: kết quả chép được kiểm; lỗi ⇒ dừng trước khi tạo lại.
- File model trên volume (Heron, TableFormer, Tesseract fast/best/OSD, Agri, RapidOCR, EasyOCR): chụp trước, so sau;
  mất / đổi kích thước / liên kết hỏng ⇒ `failed`.
- tiktoken `o200k_base`: inventory trong image (`--network none`) ghi thư mục cache, từng file + SHA-256, file và
  SHA-256 kỳ vọng, nạp được hay không ⇒ thiếu thì gói `NOT_READY`; health kiểm tách đoạn offline; ứng dụng không tải
  khi `OCR_OFFLINE=true`.

Không làm (có lý do): đóng gói thư mục model vào gói (`--with-artifacts`, mục tùy chọn của audit) — giữ quyết định
D-35: model ở lại volume, không phân phối lại, Agri không bao giờ được đóng gói. Hệ quả: máy chủ thiếu model bị
preflight **từ chối**, không được gói tự bổ sung.

## 7. Kiểm tra tĩnh

| Công cụ | Kết quả |
|---|---|
| `ruff check` / `ruff format --check` trên `scripts/offline`, test | sạch |
| `mypy scripts/offline/offline_package.py` | 0 lỗi |
| `shellcheck scripts/offline/*.sh`, `bash -n` | sạch |
| `bandit -ll scripts/offline/offline_package.py` | 0 High; 1 Medium (B608: chuỗi `SELECT count() … FROM {t}` với `t` lấy từ hằng số `RECORD_TABLES`, chạy bên trong container qua `python -c` — không có đầu vào người dùng) |
| Python của máy chủ | chỉ thư viện chuẩn; ngữ pháp phân tích được ở mức Python 3.8 (`ast.parse(feature_version=(3, 8))`), không dùng API ≥ 3.9; biên dịch và chạy trên 3.11, 3.12, 3.13. **Python 3.8 / 3.10 không có ở Cloud nên chưa chạy thật** trên đúng phiên bản của Ubuntu 20.04 / 22.04 |

## 8. Rủi ro còn lại

1. Toàn bộ mục §0 "Chưa chạy". Đây là rủi ro chính: logic đúng trên mô hình không chứng minh hành vi trên Docker /
   Compose thật.
2. Ghim image phụ thuộc quy ước đặt tên image của Compose cho dịch vụ `build:` và không bảo vệ trước `--build`.
3. Biến offline chỉ bền vững khi người vận hành tự thêm dòng `COMPOSE_FILE` (công cụ cố ý không sửa `.env`).
4. Danh sách file model chỉ so tên + kích thước.
5. Cổng Legal của lần cập nhật kế tiếp được đọc từ **container đang chạy** (chỉ nhận `true` / `false`); giá trị khác
   bị bỏ qua và cổng trở về mặc định của cấu hình triển khai.
6. Chưa có khóa ký chính thức.
7. Build image không tái lập bit-by-bit (có từ trước Phase 12).
