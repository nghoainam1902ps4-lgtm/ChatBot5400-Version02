# Phase 12D13 — RB-1 hardening và RapidOCR offline của candidate

Commit: `fd058b9` (cứng hoá rollback RB-1), `8b94a3f` (RapidOCR offline cho candidate). Startup gate đã được chủ dự
án duyệt giữ nguyên: **entrypoint baseline → chuẩn bị runtime → restore helper → kiểm SHA-256 → supervisord →
API / worker**, fail-closed. Không sửa image baseline v1.2.0, không nâng RapidOCR hay model, không đổi engine OCR
mặc định (`rapidocr`). Artifact Windows (từ điển `b5f2bfe2…`, manifest `6b51f903…`, helper `eb494481…`, LICENSE
`3e0af25f…`) giữ nguyên byte.

## 1. Bảy điểm của review 12D12 (R08)

| # | Điểm hở (12D12) | Bản sửa | Kiểm chứng |
|---|---|---|---|
| 1 | Selector trả thành công rỗng khi metadata baseline hỏng | `select-compose.sh`: mỗi pin phải đúng **một dòng LF** khớp regex chặt (`sha256:[0-9a-f]{64}`, tag); ID Docker trả về cũng phải đúng dạng. ID cắt ngắn, CRLF, sai hoa/thường, hai dòng, thiếu LF, rỗng, lỗi Docker, thiếu `compose.json` ⇒ mã khác 0, không in gì. Hợp đồng đầu ra giữ nguyên (đường dẫn override, hoặc rỗng khi tag trỏ image khác). Selector bị **làm rỗng** vẫn thoát 0 ⇒ C10 bắt buộc chạy `verify_stage.py` trước và, khi tag đã chọn là baseline, bắt buộc đầu ra = `$RB1_STATE/compose.json`. | 8 ca metadata hỏng × 2 trạng thái tag; lỗi Docker; thiếu override; selector rỗng bị `verify_stage.py` bắt |
| 2 | Không kiểm đủ file sau khi stage | Sau khi ghi, so **cả tám** file RB-1 với payload đã xác thực (trước đây chỉ 4/7 file có pin); stage chứa `signed-manifest.json` + `.sig` và được `verify_stage.py` kiểm **trước** khi đặt vào chỗ và **lại** tại chỗ: đúng tập file, mọi file = kích thước + SHA-256 đã ký. | 12 ca sửa sau khi stage (byte từ điển, runtime gate, startup, verifier, file thừa, thiếu file, override đổi image, mount ghi được, file group-writable, symlink, chữ ký khoá khác, thay **cả** từ điển và `manifest.json` cạnh nó) ⇒ đều bị từ chối |
| 3 | Khoảng verify → probe → stage | Manifest và chữ ký đọc **một lần**; `verify_tree` phải cho đúng manifest mà chữ ký bao. Mỗi file RB-1 đọc **một lần** ngay sau xác thực, so với manifest đã ký + pin + quyền file; probe và stage dùng **chính các byte đó**, không đọc lại đĩa. | Sửa `runtime_gate.py` trên đĩa sau khi xác thực ⇒ file stage và chương trình probe vẫn là byte đã xác thực; mỗi file lệch manifest ký / thiếu entry / file ghi được bởi others ⇒ từ chối |
| 4 | Thư mục state persistent và trust boundary | Sau khi stage, gốc tin cậy là **khoá ký của đơn vị vận hành nằm ngoài stage** (`verify_stage.py --allowed-signers`), không chỉ quyền thư mục. Verifier kiểm chủ sở hữu (root / user chạy) và quyền (không group/other-writable) của thư mục, thư mục con, từng file và mọi thư mục cha (trừ sticky), không symlink. Stage đặt chỉ đọc (`0555` / `0444`). | Như mục 2; quyền đọc-ghi kiểm trong test |
| 5 | Tên service không đối chiếu nhãn Compose | `preflight(..., service=)`: `--app-service` phải bằng nhãn `com.docker.compose.service` của container đang chạy; override và verifier cũng phải đúng service đó. | Nhãn đúng ⇒ `A-valid`; nhãn khác / thiếu nhãn / không có `Labels` ⇒ từ chối |
| 6 | Phụ thuộc checkout candidate khi rollback | Stage tự chứa (helper, gate, startup, selector, verifier, manifest ký); override chỉ trỏ tới chính stage. Stage **không được** nằm trong thư mục gói, `$WORK` hay bất kỳ checkout git nào. Verifier chạy từ stage, chỉ dùng stdlib + `ssh-keygen`. | Stage trong `$WORK` / checkout bị từ chối, không để lại gì; verifier chạy được khi chỉ có stage |
| 7 | Giữ fail-closed | Không đổi `startup.sh` / `runtime_gate.py`; test 12D11 (`test_startup_runs_after_stock_entrypoint_and_fail_closed`) giữ nguyên và đạt. Verifier / selector lỗi ⇒ adapter dừng (C10). | Bộ RB-1 hiện có đạt nguyên trạng |

Test mới: `tests/test_phase12d13_rb1_hardening.py` (chữ ký ssh-keygen thật, Docker giả). Hợp đồng cập nhật:
`docs/deployment/OFFLINE_UPDATE_INTEGRATION_CONTRACT.md` (C10), `docs/deployment/OFFLINE_UPDATE_MANUAL_FALLBACK.md`.

Giới hạn: người có quyền root trên host có thể thay cả verifier trong stage; bảo vệ là quyền root-only và khoá
ký ngoài stage. Boot guard vẫn là hợp đồng tài liệu (chưa có adapter thật): D12-L4 trên Ubuntu VM.

## 2. RapidOCR offline của candidate (D12-L1)

Candidate có cùng giới hạn D-32 với v1.2.0: wheel `rapidocr` 3.9.2 không kèm `ppocrv6_dict.txt`, RapidOCR đọc nó
trong thư mục gói (lớp container) và tải lại **không kiểm checksum** khi thiếu. Đã xác nhận trên image candidate:
thư mục gói **không** có từ điển.

Bản sửa tái sử dụng đúng artifact và helper đã nghiệm thu Windows (có sẵn trong image ở `scripts/offline/rb1/`):

- `scripts/docker-entrypoint.sh`: sau khi runtime OCR được cài / xác nhận, **trước** `exec` supervisord, chạy
  `python -m open_notebook.ocr.rapidocr_dictionary` (startup gate cùng thứ tự đã duyệt).
- `open_notebook/ocr/options.py::build_ocr_options("rapidocr")` gọi lại `ensure_dictionary()` trước khi cấu hình
  RapidOCR (có cache theo `stat`), nên một container mà ai đó đã làm hỏng từ điển sau khởi động vẫn bị chặn.
- Chỉ cho đúng RapidOCR 3.9.2 / torch 2.14.0 / Docling 2.129.0 / `default_models.yaml` / model nhận dạng đã ghim,
  đúng vị trí RapidOCR tự tính, không ghi đè file lạ, chịu được hai tiến trình (API, worker) cài cùng lúc.
- `OCR_OFFLINE=true` mà không chứng minh được ⇒ chuyển đổi dừng (`ValueError`, không retry): **không tải**, **không
  chuyển sang Tesseract**. Online: giữ hành vi upstream, ghi log cảnh báo.
- Không đổi dependency, model, tham số RapidOCR hay engine mặc định.

Kiểm chứng: unit test `tests/test_phase12d13_rapidocr_dictionary.py` và **chạy thật trên Docker Desktop** (mục 3).

## 3. Bằng chứng Local trên Docker Desktop

Image candidate `chatbot5400:phase12-test-8b94a3f` (`sha256:f03828c5…`, nhãn revision `8b94a3f5…`, build từ commit
với `OCR_INSTALL_TESSERACT=true`, `OCR_PREINSTALL_RUNTIMES=true`). Runtime trong image: rapidocr 3.9.2, torch
2.14.0+cpu, docling 2.129.0, content-core 2.0.7, backend torch. Lab `cb5400-d13-l1`: mạng internal (DNS / HTTPS ra
ngoài thất bại), không publish port, `OCR_OFFLINE=true`, `OCR_RAPIDOCR_PERSISTENT=true`, dữ liệu tổng hợp F0,
fixture `e2_tokens.pdf` (10 token ground truth). Chi tiết số liệu: [checklist nghiệm thu Local](PHASE12D13_LOCAL_ACCEPTANCE_CHECKLIST.md), mục D12-L1.

## 4. Trạng thái

| Hạng mục | Trạng thái |
|---|---|
| 7 điểm hardening RB-1 | Sửa, có test; adapter / boot guard thật: D12-L4 PENDING (Ubuntu VM) |
| Candidate RapidOCR offline sau cold start / recreate / restart | PASS trên Docker Desktop (D12-L1) |
| Reboot Ubuntu VM (RB-G11, D12-L1 phần reboot guest) | **PENDING** |
| Gói ký chính thức (D11-W09) | PENDING |
