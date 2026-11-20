# Phase 12D7 — Báo cáo build và công cụ trên Windows (E1-04, E0-05, E1-05 phía build)

Cloud không có Windows / PowerShell (lần thử tải PowerShell 7 cho Linux để chạy thử bị cơ chế phê duyệt chặn; không
tìm cách khác). Mọi kiểm dưới đây chạy trên **Linux**; không mock `sys.platform`; **không tuyên bố Windows đạt.**

## 1. E1-04 — khóa build của gói offline

**Lỗi:** `build_lock` (và `update_lock`) `import fcntl` — module không có trên Windows ⇒ `build` dừng trên Windows
PowerShell 5.1 và 7. Tái hiện ở Cloud: chặn `fcntl` (`sys.modules["fcntl"] = None`) ⇒ mã cũ `ModuleNotFoundError`.

**Sửa (`scripts/offline/offline_package.py`, không thêm dependency):** `exclusive_lock(path, busy)` dùng chung —
Linux / macOS: `flock(LOCK_EX | LOCK_NB)`; Windows: `msvcrt.locking(LK_NBLCK)` trên một byte ở offset 2³⁰ (ngoài vùng
PID, nên tiến trình khác vẫn đọc được PID của người giữ). Cả hai: độc quyền giữa các tiến trình, gắn với file đang mở,
**hệ điều hành tự nhả khi tiến trình chết**, không chờ (người thứ hai bị từ chối ngay, mã `EXIT_LOCK`, thông báo nêu
file khóa và PID người giữ). File khóa mở **không truncate** và **không bao giờ bị xóa** (xóa file khóa người khác đang
giữ hoặc sắp lấy sẽ tạo hai người giữ). `update_lock` dùng cùng cơ chế — trên Ubuntu vẫn là `flock` như trước.

Kèm theo (cùng đường build trên Windows):

| | Trước | Sau |
|---|---|---|
| Tiến trình bị từ chối | `open(..., "w")` xóa trắng PID của người giữ (tái hiện: `'5237'` → `''`) | không đụng tới file |
| `.partial-*` của lần build bị kill | ở lại mãi | lần build sau (đang giữ khóa ⇒ không ai khác đang build tên đó) xóa; gói tên khác không bị đụng |
| Thư mục dựng dở sau khi bị kill | từ chối, thông báo chung | từ chối, thông báo nói rõ "của lần build trước hoặc bị ngắt" — người vận hành tự xóa |
| Đổi tên gói cuối thất bại (Windows: file bị chương trình khác mở) | `.sha256` cũ đã bị xóa trước ⇒ gói cũ mất hash | `.sha256` được để riêng rồi trả lại ⇒ gói cũ **giữ nguyên cặp** |
| `manifest.json`, `SHA256SUMS`, `.sha256` trên Windows | chế độ chữ của Python ⇒ CRLF | luôn LF (giống hệt build Linux) |

Mã vẫn parse với Python 3.8; `mypy` sạch cả `--platform linux` lẫn `--platform win32` cho phần mới (lỗi `geteuid`
khi kiểm `win32` nằm ở các hàm chỉ chạy trên máy chủ Ubuntu, không thuộc đường build).

**Test (`tests/test_phase12d7_build_lock.py`, 12, tiến trình thật):** người thứ hai bị từ chối và nêu PID (build và
update), file khóa của người giữ không đổi; khóa được nhả khi người giữ bị `SIGKILL` (lấy lại < 5 s, file khóa còn);
8 tiến trình đua cùng lúc ⇒ đúng 1 thắng, 7 bị từ chối `EXIT_LOCK`; cùng tiến trình mở lần hai cũng bị từ chối; file
khóa không mở được ⇒ từ chối rõ; không import module chỉ-POSIX ở cấp module; build bị `SIGKILL` giữa `docker save`
(cả nhóm tiến trình) ⇒ gói cũ + `.sha256` giữ nguyên từng byte, khóa nhả, lần build sau báo thư mục dựng dở, sau khi xóa
thì build được và dọn `.partial-*` cũ của đúng tên đó; đổi tên cuối thất bại ⇒ gói cũ và `.sha256` cũ còn nguyên, không
còn `.partial-*` / `.previous-*`, thư mục dựng của lần chạy đó bị xóa; đầu ra build không có `\r`.

Các test khóa viết để chạy nguyên trên Windows (`python -m pytest tests/test_phase12d7_build_lock.py` trong PowerShell
— nhánh `msvcrt`); test build cần Docker giả lập POSIX nên bỏ qua trên Windows. W-12D7-04.

## 2. E0-05 — `phase12-test.ps1 up -d`

**Lỗi:** `Invoke-Compose` nhận tham số bằng `ValueFromRemainingArguments` ⇒ là *advanced function*, có các common
parameter của PowerShell ⇒ trong `Invoke-Compose up -d`, PowerShell gán `-d` cho `-Debug`, docker nhận `up` **không
có** `-d`, script bám vào log container (và Ctrl+C dừng container).

**Sửa:** `Invoke-Compose -ComposeArgs @(...)` và `Invoke-Exec -Cmd @(...)` — một mảng tường minh; trong mảng mọi phần tử
là giá trị, không bao giờ là tên tham số. Mọi lời gọi đã chuyển: `build`, `up`, `status`, `logs`, `import-agri`,
`activate-agri`, `agri-status`, `fixtures`, `compare`, `diagnose`, `orientation` (mới), `legal-gate`, `restart-app`,
`stop`. Tham số giữ **đúng như trước**: `legal-gate` / `restart-app` = `up -d --no-deps --no-build --force-recreate
open_notebook` (chỉ container ứng dụng, database không bị tạo lại); không `down`, không `-v`, không `pull`, không xóa
volume / thư mục. Compose của stack vẫn `pull_policy: never` cho ứng dụng.

**Test (`tests/test_phase12d7_powershell.py`, 6, kiểm cấu trúc văn bản script — không có PowerShell):** không hàm nào
dùng `ValueFromRemainingArguments` (cả `build-package.ps1`); mọi lời gọi truyền đúng một mảng; mảng của từng hành động
đúng như kỳ vọng (`up` = `['up','-d']`…); không tham số phá hủy / kéo image; `exec -T open_notebook`; hành động
`orientation` kiểm dạng `-Suspect`. Chạy với script cũ: 5/6 test thất bại (ĐỎ), test "không phá hủy" đạt ở cả hai.
Hành vi gán tham số thật trên PowerShell 5.1 và 7: W-12D7-05.

## 3. E1-05 phía build — cổng hướng xoay trong image build từ Windows

`build-package.ps1` và `phase12-test.ps1 build` build image từ checkout Windows. `.gitattributes` chỉ ép LF cho `*.sh`
⇒ với `core.autocrlf=true` file `tesseract_gate.py` có CRLF ⇒ dòng `#!` không chạy ⇒ ứng dụng chạy Tesseract không
cổng ([D-40](../ocr/DECISIONS.md)). Sửa: `.gitattributes` cho cổng `eol=lf`; Dockerfile chuẩn hóa đuôi dòng, đặt quyền
thực thi và tự kiểm tra cổng lúc build (lỗi ⇒ build dừng). Kiểm ở Cloud: phát lại đúng lệnh của Dockerfile trên bản
CRLF + 0644 ⇒ file thành đúng blob của git và chạy được (`tests/test_phase12d7_orientation.py`). Docker build đầy đủ
image ứng dụng **không chạy** ở Cloud (không có model, mất nhiều giờ) — W-12D7-01.

## 4. Gói offline

Không chạy build gói thật trên Windows. Gói build trên Linux (Docker giả lập) đạt mọi test cũ (§ báo cáo hồi quy).
Gói phải chứa image có bản vá E0-07 (`inventory` ghi `docling_tsv_patch`; không áp được ⇒ `NOT_READY`); máy chủ không
build, không tải dependency; không có Agri / DB / credential / tài liệu nội bộ (danh sách file cố định trong
`_build_stage`, không đổi). Updater tự động vẫn **EXPERIMENTAL**; đường khuyến nghị vẫn là
[OFFLINE_UPDATE_MANUAL_FALLBACK.md](../deployment/OFFLINE_UPDATE_MANUAL_FALLBACK.md); state machine không mở rộng;
rollback về v1.2.0 giữ nguyên. **OFFLINE PACKAGE: NOT VERIFIED ON WINDOWS.**

## 5. Còn rủi ro

- `subprocess.run(text=True)` của công cụ giải mã đầu ra git / docker bằng bảng mã ANSI của Windows; đầu ra ở đường
  build là ASCII (JSON `inventory` dùng `ensure_ascii`), nên không lỗi đã biết. Nếu chuyển hướng log của
  `build-package.ps1` sang file với đường dẫn có chữ tiếng Việt và gặp `UnicodeEncodeError`: `$env:PYTHONUTF8 = '1'`.
- Các `2>$null` với lệnh native trong `Invoke-Check` có thể thành lỗi dừng trên PowerShell 5.1 nếu docker ghi stderr
  (cùng loại R2-22); không có bằng chứng lỗi từ 12E0 / 12E1 nên giữ nguyên.
