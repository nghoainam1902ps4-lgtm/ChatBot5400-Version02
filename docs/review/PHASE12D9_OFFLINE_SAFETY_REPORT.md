# Phase 12D9 — An toàn offline: gói, quy trình thủ công, updater EXPERIMENTAL

Quyết định: D-46 trong [DECISIONS.md](../ocr/DECISIONS.md). Commit `70f7325`. Updater tự động (`update` / `finish` /
`rollback` / `pin`) **vẫn EXPERIMENTAL**; state machine không mở rộng. Đường production là
[OFFLINE_UPDATE_MANUAL_FALLBACK.md](../deployment/OFFLINE_UPDATE_MANUAL_FALLBACK.md). Không đụng DB / volume, không pull
image ngoài dự kiến, không kết nối production.

**OFFLINE MANUAL FALLBACK: PASS ON SYNTHETIC** — mọi lệnh đã sửa được chạy đúng như văn bản của tài liệu trong test (dữ
liệu giả, Docker giả); diễn tập với Docker **thật** ở Cloud (`CB5400_REAL_DOCKER=1`, image thử `busybox:1.36`): 3 passed,
trạng thái Docker trước = sau, không kéo image. Chưa chạy trên máy chủ Ubuntu thử với ứng dụng thật (G-09).

## 1. Updater được gắn nhãn đúng

| Finding | Sửa | Test |
|---|---|---|
| D8-OFF-01 | `EXPERIMENTAL` trong `offline_package.py --help` (parser chính và subparser `update`, `finish`, `pin`, `rollback`), ghi vào log **mỗi lần chạy** các lệnh đó, và trong wrapper `update.sh`, `finish.sh`, `rollback.sh` | `tests/review_phase12d8/test_offline_d8.py` |
| D8-OFF-02 | release notes 1.3.0-rc.1 (§1–§4.7): EXPERIMENTAL, production → quy trình thủ công | như trên |

## 2. Gói: cặp gói + hash luôn nhất quán

| Finding | Sửa | Còn kiểm ở Local |
|---|---|---|
| D8-OFF-03 | hash mới được ghi (fsync) **cạnh** gói trước khi thay bất cứ gì; gói được thay bằng `os.replace`, khôi phục khi lỗi; ghi `.sha256` cuối lỗi ⇒ hash mới vẫn được đặt vào; file phụ luôn được dọn | G-07c (Windows: thay file đang mở) |
| D8-OFF-04 | build bị kill ở bất kỳ bước nào: lần build sau (giữ khóa) khôi phục hash đúng cho gói đang có và dọn phần thừa (`_recover_interrupted_publish`) | G-07c |
| D8-OFF-09 | chỉ lỗi "đang bận" (EAGAIN / EACCES / EDEADLK …) được báo là "đang bị tiến trình PID giữ"; lỗi khác (ENOLCK, EOPNOTSUPP — ổ mạng / exFAT) ⇒ "thư mục không hỗ trợ khóa file; dùng thư mục cục bộ" | G-07d (msvcrt thật) |
| D8-OFF-06 | `build` đặt `migration_required` khi commit thêm migration so với schema của `--base-ref` (đọc bằng `git ls-tree`, định dạng manifest không đổi); `update` và quy trình thủ công dừng | — |

## 3. Quy trình thủ công (đường production)

| Finding | Sửa |
|---|---|
| D8-OFF-05 | §3.4: sau `sha256sum -c SHA256SUMS`, một lệnh `python3 -I` một dòng so **mọi** file với manifest **đã ký** — file thừa, thiếu, sai hash ⇒ dừng; in `manifest: every file OK` |
| D8-OFF-07 | `WORK=/var/tmp/cb5400-$VER-<thời điểm>`; §3: `test ! -e "$WORK" && install -d -m 700 -o root -g root "$WORK"` và kiểm chủ sở hữu là root — không dùng thư mục người khác tạo sẵn |
| D8-OFF-08 | `snapshot --compare` báo cả bản ghi bị **sửa tại chỗ**; sau §7.3 so bằng `--no-writes`: có thêm / sửa / dữ liệu không đọc được ⇒ không đạt |
| D8-OFF-10 | §10 rollback: 10.1 đưa mã nguồn về (`git reset --keep`) **trước**, 10.2 mới tạo lại ứng dụng trên image cũ |
| D8-OFF-13 | các lệnh `python -c` là **một dòng** — chép từ file `.md` thô trong gói vẫn chạy |
| D8-OFF-14 | phép so F1 == F2 thất bại khi dữ liệu không đọc được (`UNREAD … STOP`) |
| D8-OFF-15 | [hợp đồng tích hợp](../deployment/OFFLINE_UPDATE_INTEGRATION_CONTRACT.md): `normal` **bắt buộc** `--no-deps --no-build --pull never <service ứng dụng>`; C6 chỉ nêu service ứng dụng |

Test: `tests/review_phase12d8/test_offline_d8.py` chạy **đúng chuỗi lệnh trong tài liệu** (trích từ file `.md`), có
bước cần root. Script vận hành production của đơn vị không có ở Cloud ⇒ W-INT-10 / G-09e.

## 4. Windows (chỉ sửa tĩnh — Cloud không có PowerShell)

| Finding | Sửa | Cổng |
|---|---|---|
| D8-OFF-11 | `build-package.ps1`: `[string[]]$python = …` giữ mảng một phần tử (trước đây máy có Python mà không có `uv` dừng với lệnh `p`) | G-07a: máy có Python, không có `uv`, PS 5.1 và 7, đường dẫn có dấu cách |
| D8-OFF-12 | `phase12-test.ps1`: bỏ `2>$null` ở `docker info` và `docker compose ps -q` | G-08a: Docker Desktop tắt ⇒ báo lỗi rõ, không `NativeCommandError` |

Kiểm tĩnh trong `tests/review_phase12d8/test_offline_d8.py`; tải PowerShell 7 về Cloud đã bị từ chối ở phiên trước và
không được lách. Không mô phỏng `sys.platform` để tuyên bố Windows đạt.

## 5. Không đổi

Định dạng manifest, chữ ký, tên gói, giao diện lệnh của updater, DB schema. Kết quả bộ offline: xem
[PHASE12D9_REGRESSION_REPORT.md](PHASE12D9_REGRESSION_REPORT.md).
