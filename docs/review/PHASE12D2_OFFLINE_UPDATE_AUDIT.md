# Phase 12D2 — Kiểm toán công cụ cập nhật offline

Phạm vi: `scripts/offline/` tại commit `2ef0074` (PR #50, Draft). Đây là báo cáo review, **không sửa mã chạy**.
Mã định danh finding khớp với [PHASE12D2_FINDINGS.json](PHASE12D2_FINDINGS.json).

## 0. Giới hạn của lần kiểm toán này

| Việc | Trạng thái |
|---|---|
| Đọc toàn bộ `offline_package.py` (1784 dòng), 9 wrapper, file cấu hình mẫu, 5 tài liệu `docs/deployment/OFFLINE_UPDATE_*` | Đã làm |
| Chạy 30 test hiện có và 13 test phản ví dụ mới (docker giả; git, tar, SHA-256 thật) | Đã làm: 29 PASS + 1 SKIP |
| Kiểm tra chữ ký `ssh-keygen -Y verify` | **Chỉ đọc mã**: Cloud không có `ssh-keygen`, test chữ ký bị SKIP |
| Chạy `git bundle` thật để kiểm tra đường build và đường đồng bộ mã nguồn | Đã làm |
| Docker daemon thật (`docker load`, Compose merge, tạo lại container, rollback) | **Không thể**: Cloud không có Docker daemon |
| PowerShell (`build-package.ps1`) | **Không thể**: Cloud không có PowerShell; chỉ đọc mã |
| Build image thật, đo kích thước gói | **Không thể** |

Hệ quả: **OFFLINE ROLLBACK: NOT VERIFIED**. Mọi kết luận về hành vi của Docker/Compose thật được ghi "cần xác minh cục bộ" và
có mục tương ứng trong [PHASE12D2_WINDOWS_ACCEPTANCE_CHECKLIST.md](PHASE12D2_WINDOWS_ACCEPTANCE_CHECKLIST.md).

## 1. Kết luận ngắn

- **Thiết kế: PARTIAL.** Các nguyên tắc đúng: fail-closed, chỉ tạo lại container ứng dụng, bắt buộc xác thực nguồn gói, không
  đọc `.env`, khóa `flock`, có journal. Ba khoảng trống thiết kế: trạng thái mong muốn nằm ngoài thư mục triển khai (F-11),
  "DB không đổi" chỉ được kiểm ở tầng cấu hình (F-21), gói không mang và không kiểm kê trước các model (F-22).
- **Triển khai: FAIL.** Lệnh build theo tài liệu không tạo được gói (F-04); lần cập nhật thứ hai dùng lại backup cũ (F-08).
- **Bảo mật: PARTIAL.** Kiểm tra archive và xác thực nguồn làm đúng phần chính; còn các lỗ phòng thủ theo chiều sâu (F-12, F-14,
  F-25, F-26).

## 2. Những điều đã xác minh là ĐÚNG

| Yêu cầu | Kết quả | Bằng chứng |
|---|---|---|
| Mọi đường tạo lại ứng dụng dùng `up -d --no-deps --no-build --pull never --force-recreate <app>` | Đúng ở cả 4 chỗ gọi (`cmd_update` 1335, `cmd_finish` 1528, `cmd_rollback` 1586 và 1626) | `test_verified_every_compose_up_is_app_only_no_deps_no_build_pull_never` (so nguyên đuôi lệnh) |
| Không có `compose down`, `pull`, `build`, `rm`, `prune`, `-v`, `restart` trong công cụ và wrapper | Đúng | `test_verified_source_repo_scripts_never_call_destructive_docker_commands`; đọc 9 wrapper (chỉ `exec python3 … <lệnh>`) |
| Gói không ký và không có SHA-256 kênh tin cậy bị từ chối | Đúng | `test_verified_unsigned_package_without_trusted_hash_is_refused` |
| Sai nền tảng, checksum sai, file thừa/thiếu, manifest sai, gói có migration bị từ chối | Đúng | test hiện có, đã chạy lại: PASS |
| Chữ ký sai bị từ chối; gói có chữ ký nhưng máy chủ chưa cài khóa bị từ chối | Đúng **theo mã** (`verify_signature` 371-406); chưa thực thi trong phiên review | test chữ ký SKIP vì thiếu `ssh-keygen` |
| Đường dẫn tuyệt đối, `..`, symlink, hardlink, device, entry ngoài thư mục gói bị từ chối trước khi ghi | Đúng | `_check_member` 245-258; `test_archive_safety` |
| Giới hạn giải nén: 5000 entry, 64 GiB, tỷ lệ 200× | Có | `inspect_archive` 261-282 |
| Không gọi shell cho lệnh Docker/git (danh sách đối số) | Đúng, trừ `BACKUP_CMD`/`BACKUP_VERIFY_CMD` chạy qua `/bin/sh -c` theo chủ ý | `run()` 90-116; 1284, 1301 |
| Không đọc `.env`, không in biến môi trường | Đúng | đọc mã; `test_update_apply_full_flow` |
| Một cập nhật tại một thời điểm | Đúng (`flock`, tự nhả khi tiến trình chết) | `update_lock` 191-209; `test_update_lock` |
| Gói có migration và schema khác bị chặn ở preflight (schema DB thật đọc từ `_sbl_migrations`) | Đúng; truy vấn lỗi trả 0 ⇒ FAIL (fail-closed) | `current_schema` 961-971; `async_migrate.get_latest_version` |
| Chuỗi tin cậy của công cụ: lần đầu so SHA-256 bằng tay, các lần sau dùng công cụ đã cài | Có trong hướng dẫn §1.1 và tài liệu bảo mật §3 | xem F-26 về các điểm yếu còn lại |
| tiktoken khi offline | Bảng mã `o200k_base` được nướng sẵn vào image (`/app/tiktoken-cache`, Dockerfile 71-77, 106-107, 122-123); `token_count` có fallback | xem §8 |
| `RecordModel` của v1.2.0 chấp nhận trường `ocr_text_normalization` lạ (`extra="allow"`) nên rollback về 1.2.0 không lỗi khi DB đã có cấu hình Legal | Đúng theo mã | `open_notebook/domain/base.py` 242-245 |

## 3. Tin cậy gói (9.1)

| Hạng mục | Đánh giá |
|---|---|
| Manifest | Kiểm tra kiểu và trường bắt buộc; **không** kiểm tra hình dạng của `image.tag`, `source.commit`, `release_tag` (F-12) |
| SHA-256 | Từng file + `SHA256SUMS` + cả gói. SHA-256 chỉ chứng minh **toàn vẹn**; tính xác thực phụ thuộc vào việc giá trị đến qua kênh khác kênh mang gói. File `.sha256` sinh cạnh gói không phải kênh tin cậy (F-26e) |
| Chữ ký | `ssh-keygen -Y verify` trên `manifest.json`, namespace riêng, danh tính cố định. Đúng. **Chưa có khóa phát hành chính thức** (tài liệu đã nêu) |
| Thứ tự | Gói được giải nén ra đĩa **trước** khi kiểm chữ ký (F-14) |
| Thay thế sau verify | `update` kiểm lại toàn vẹn theo manifest nhưng không kiểm lại xác thực; dấu "đã verify" là file `verify-report.json` không gắn với hash (F-26a) |
| Entry trùng tên | Được chấp nhận (F-14) |
| Giới hạn đĩa | Có giới hạn tổng, **không** kiểm tra dung lượng trống của `--extract-to` (F-14) |
| Script trong gói chưa xác thực | Hướng dẫn xử lý đúng nguyên tắc; đường dẫn `/tmp/cb5400-tools` cố định (F-26b) |

## 4. An toàn Docker (9.2)

| Rủi ro | Hiện trạng |
|---|---|
| Sai image / sai tag | Tag đích đã tồn tại với ID khác ⇒ preflight FAIL. Sau load so ID với manifest |
| Sai image ID giữa hai image store | **Nghi ngờ** so sánh luôn sai khi máy build và máy chủ dùng store khác nhau (F-20) — cần xác minh |
| Sai kiến trúc | Kiểm ở build (image), verify (máy), preflight (`docker info`) |
| Sai phiên bản / sai commit | Nhãn `image.revision` chỉ được so khi có nhãn; build tay không nhãn thì image và bundle có thể lệch commit mà không ai biết. VERSION hiện là 1.2.0 nên không build được `1.3.0-rc.1` (F-27) |
| `docker load` ghi đè tag khác | Không kiểm tra RepoTags trong archive (F-25) |
| Sai project / service / đường dẫn | Sai project ⇒ không tìm thấy container ⇒ preflight FAIL (đúng). Nhánh `rollback` không chạy preflight |
| Tạo lại DB ngoài ý muốn | Công cụ không tự gây ra (`--no-deps`, tên dịch vụ cố định). Nhưng không có kiểm tra thực thi và đường cơ sở lấy sau khi đồng bộ mã nguồn (F-21) |
| Pull / build ngoài ý muốn | `--pull never`, `--no-build`, `pull_policy: never` trong override. Sau khi cập nhật, định nghĩa trong thư mục triển khai vẫn có `build:` và không có `pull_policy` (F-11) |
| Migration ngoài ý muốn | Preflight yêu cầu schema DB = schema gói; sau khi khởi động không kiểm lại (F-21) |

## 5. Kiểm kê artifact offline (9.3)

Gói chứa: image (`docker save`), git bundle, bản `git archive`, script, tài liệu, manifest. Gói **không** chứa model nào.

| Artifact | Nằm ở đâu | Gói có mang? | Preflight kiểm trước? | Ghi chú |
|---|---|---|---|---|
| Docling + Torch + EasyOCR (thư viện) | image (`OCR_PREINSTALL_RUNTIMES=true`) | Có | readiness của gói | Chưa build thật |
| Tesseract (binary) | image (`OCR_INSTALL_TESSERACT=true`) | Có | readiness của gói | |
| Layout Heron, TableFormer | volume `HF_HOME` | Không | **Không** (F-22) | Chỉ kiểm sau khi tạo lại |
| Tesseract fast / best / OSD | volume `/app/data/ocr/models/tesseract` | Không | **Không** | |
| EasyOCR weights | volume | Không | **Không** | |
| Model Agri | volume `custom/agri/<version>` | Không (đúng: không được đóng gói) | Không; công cụ không ghi vào thư mục này | Không tìm thấy đường nào ghi đè model Agri |
| RapidOCR weights | venv của container **cũ** → chép sang volume | Không | Không | Kết quả chép bị bỏ qua; `{}` vẫn đi tiếp (F-22) |
| tiktoken `o200k_base` | image | Có | — | Xem §8 |
| Manifest/readiness OCR | volume `/app/data/ocr` | Không | Không | |

`installer.import_rapidocr_weights` (mã 1.2.0, không đổi) chép đúng cách: chỉ file có SHA-256 khớp danh sách của RapidOCR, bỏ
symlink, ghi file tạm rồi `os.replace` (không để file dở), không ghi đè file đích đã đúng. Điểm yếu nằm ở phía gọi: nguồn là venv
của container đang chạy; nếu container đó chưa từng tải trọng số (máy chủ chỉ dùng Agri, hoặc container vừa được tạo lại) thì
không có gì để chép và công cụ không coi đó là lỗi.

## 6. Máy trạng thái và gián đoạn (9.4)

Trạng thái journal: `in_progress → deployed_pending_checks → awaiting_approval | failed → completed | rolled_back`.

| Gián đoạn tại | Sau đó | Đánh giá |
|---|---|---|
| verify | Thư mục giải nén dở còn lại, không có `verify-report.json`; chạy lại cần thư mục mới | An toàn; không tự dọn (F-14) |
| preflight | Chỉ đọc | An toàn |
| G `docker load` | Chạy lại load lại (idempotent) | An toàn. Nếu ID không khớp: image đã load nằm lại (F-20) |
| H gắn tag rollback | Chạy lại tạo thêm một tag | An toàn |
| I/J backup | Chạy lại làm lại bước chưa ghi | An toàn trong cùng lần thử; **dùng lại backup cũ ở lần thử sau** (F-08) |
| K đồng bộ mã nguồn | Hiện luôn từ chối với gói mặc định (F-05); nếu chạy được: fast-forward, không có bước hoàn tác tự động (F-24) | |
| giữa `up` (Ctrl+C, kill, mất điện) | Container có thể không tồn tại; journal `in_progress` không có `N_recreated`. `update` lại bị preflight chặn (không thấy container). Phải dùng `rollback interrupted` | Phục hồi được nhưng thông báo dễ gây nhầm; tài liệu §4 ghi "chạy lại update" cho trường hợp chưa có `N_recreated` là **không đúng** khi container đã bị gỡ |
| sau `up`, trước khi ghi journal | Container ở bản mới, journal chưa có `N_recreated`. `update` lại bị chặn vì phiên bản hiện tại không còn trong danh sách hỗ trợ | Phục hồi bằng `rollback interrupted`; trạng thái lệch **không được báo rõ** |
| health check thất bại | `failed`, giữ bảo trì, có hướng dẫn | Đúng |
| finish | Tạo lại lần hai, ghi `completed` không kiểm tra (F-09) | |
| rollback | Ghi `rolled_back` không kiểm tra (F-09); gọi nhiều lần: idempotent | |
| Mất điện khi ghi journal | Journal có thể hỏng ⇒ mọi lệnh dừng bằng traceback (F-13) | |
| Docker daemon khởi động lại | Container giữ nguyên (restart policy của triển khai) | Không có vấn đề từ công cụ |
| Hai tiến trình cùng lúc | Tiến trình thứ hai nhận mã 6 | Đúng. `health`, `status`, `preflight`, `rollback agri` không lấy khóa (chấp nhận được) |
| Cấu hình cục bộ bị đổi giữa chừng | Không phát hiện (không so config-hash của container với cấu hình hiệu lực) | Thuộc F-11/F-21 |
| Gói khác khi bản trước `awaiting_approval`/`deployed_pending_checks` | **Không bị chặn**; journal bị thay (F-24c) | |

Yêu cầu "không để source commit, image tag, app container và journal lệch nhau mà không phát hiện" hiện **chưa đạt**: không có
lệnh nào so image ID của container đang chạy với journal (F-11), và journal không ghi trạng thái mã nguồn.

## 7. Bảo toàn database (9.5) và rollback (9.6)

- Công cụ không có lệnh nào tác động tới dịch vụ DB (đã xác minh trên toàn bộ lời gọi Docker ghi lại được).
- **Chưa có** kiểm tra thực thi: ID container DB, image ID DB, mount, `StartedAt`, số bản ghi trước/sau (F-21).
- "Schema tương thích" được kiểm thật ở preflight (đọc DB). Sau cập nhật không kiểm lại.
- Rollback:

| Hạng mục cần khôi phục | Hiện trạng |
|---|---|
| Image cũ theo ID | Theo **tag** `rollback-<thời điểm>`; ID có ghi trong journal nhưng không được đối chiếu (F-24a) |
| Source commit | Không tự khôi phục (F-24b) |
| Cấu hình cục bộ, `.env`, file compose | Không bị đụng tới nên không cần khôi phục |
| Compose override | Ghi đè `image-override.yml` bằng image cũ; biến `APP_ENV_OVERRIDES` vẫn áp cho bản 1.2.0 (bản 1.2.0 hiểu `OCR_RAPIDOCR_PERSISTENT`, `OCR_OFFLINE`) |
| OCR engine, phiên bản Agri | Nằm trong DB/volume, không đổi |
| Tương thích Legal | DB giữ `ocr_text_normalization=legal`; bản 1.2.0 bỏ qua trường này ⇒ Standard. Source đã chuẩn hóa giữ nguyên, **không** OCR lại, **không** re-embed (đã xác minh theo mã). Không thể liệt kê Source nào đã qua Legal (F-07) |
| Chế độ bảo trì / bình thường | Rollback để lại bảo trì; mở lại bằng lệnh thứ hai; không health check (F-09). `legal-off` mặc định đưa hệ thống đang chạy vào bảo trì (F-23) |

## 8. Không cần Internet (9.7)

| Giai đoạn | Phụ thuộc mạng | Ghi chú |
|---|---|---|
| Build gói (máy có Internet) | Docker build, PyPI, apt | Được phép |
| `inventory` trong image | Không (`--network none`) | Đúng |
| verify / preflight / update / rollback / status | Không; URL duy nhất là health trên loopback (bị kiểm bằng regex) | urllib tôn trọng `http_proxy` (F-26d) |
| Khởi động container mới | `docker-entrypoint.sh`: Docling đã có trong image ⇒ bỏ qua cài đặt. **Crawl4AI**: nếu `OPEN_NOTEBOOK_ENABLE_CRAWL4AI=true` và không có `CRAWL4AI_API_URL`, entrypoint gọi `uv pip install` và `playwright install` (hành vi có từ trước, không có cờ offline) | Kiểm tra cấu hình máy chủ trước khi cập nhật |
| OCR | `OCR_OFFLINE=true` + model trên volume | Phụ thuộc F-22 |
| Chunking / embedding | tiktoken `o200k_base` trong image; `token_count` rơi về đếm từ khi lỗi. Lưu ý: fallback bắt **ngoại lệ**, không bắt **treo**. Trong Cloud, `tests/test_chunking.py` treo (không lỗi) khi proxy chặn host tải bảng mã. Trên máy chủ, nếu `/app/tiktoken-cache` thiếu file và tường lửa DROP gói tin thì chunking có thể treo thay vì fallback | Mục W-OFF-09 của checklist: xác nhận file cache có trong image offline |
| Embedding / LLM | Theo nhà cung cấp đã cấu hình (ngoài phạm vi gói) | |
| `--prove-offline` | Thử kết nối `huggingface.co:443` từ trong container | Chỉ chạy khi gọi `healthcheck.sh --prove-offline`, không nằm trong `update` |

Không thể kết luận "offline-ready" từ test với docker giả. Điều kiện để kết luận: checklist Windows/Ubuntu thử nghiệm đạt toàn bộ
mục W-OFF.

## 9. Bảng finding của công cụ offline

| ID | Mức | Chặn phát hành | Tóm tắt | Xác minh |
|---|---|---|---|---|
| F-04 | P1 | Có | Wrapper build truyền SHA ⇒ `git bundle` từ chối ⇒ không tạo được gói | Đã chạy |
| F-08 | P1 | Có | Lần thử thứ hai dùng lại backup cũ | Đã chạy |
| F-11 | P1 | Có | Override nằm ngoài thư mục triển khai ⇒ `compose up` thường đưa về bản cũ; không phát hiện trôi | Theo mã; Compose thật cần xác minh |
| F-05 | P2 | Không | `--sync-source` không dùng được với gói mặc định | Đã chạy |
| F-09 | P2 | Không | `finish`/`rollback` báo thành công không kiểm tra | Đã chạy |
| F-20 | P2 | Không | So image ID giữa hai image store | Nghi ngờ |
| F-21 | P2 | Không | DB chỉ được kiểm ở tầng cấu hình; đường cơ sở sau sync | Theo mã |
| F-22 | P2 | Không | Không kiểm kê model trước; bỏ qua kết quả chép RapidOCR | Theo mã |
| F-12 | P3 | Không | Giá trị manifest không kiểm định dạng (chèn YAML / đối số git) | Đã chạy |
| F-13 | P3 | Không | Journal hỏng ⇒ traceback | Đã chạy |
| F-14 | P3 | Không | Entry trùng; giải nén trước chữ ký; không kiểm đĩa trống | Đã chạy (trùng tên) |
| F-23 | P3 | Không | `legal-off` mặc định vào bảo trì | Theo mã |
| F-24 | P3 | Không | Rollback theo tag; không khôi phục mã nguồn; journal bị ghi đè | Theo mã |
| F-25 | P3 | Không | `docker load` có thể gắn lại tag khác | Nghi ngờ |
| F-26 | P3 | Không | Các điểm yếu chuỗi tin cậy / cấu hình / proxy | Theo mã |
| F-27 | P3 | Không | VERSION 1.2.0 chặn build `1.3.0-rc.1` | Theo mã |
| T-02 | P3 | Không | Oracle an toàn lệnh Docker của test hiện có luôn đúng | Đã chạy |

## 10. Lệnh đã dùng để tái hiện F-04 và F-05 (git thật)

```bash
git bundle create /tmp/x.bundle v1.2.0..2ef007417eaca0ce41e7aba2e32a201fa243ebf1
```

Kết quả: `fatal: Refusing to create empty bundle.` (đây là đối số mà `build-package.sh` dòng 34/49 và `build-package.ps1` dòng 36/50
truyền vào).

```bash
git bundle create /tmp/head.bundle v1.2.0..HEAD
```

```bash
git fetch --no-tags /tmp/head.bundle "+refs/*:refs/cb5400-offline/1.3.0/*"
```

Trên một checkout dừng ở v1.2.0: lệnh fetch kết thúc mã 0 nhưng không lấy gì; `git cat-file -e <commit>` báo thiếu ⇒
`sync_source` dừng với "the bundle does not contain the release commit".
