# Phase 12D13 — Checklist nghiệm thu Local (Windows, Docker Desktop)

Candidate code: `8b94a3f` (image `chatbot5400:phase12-test-8b94a3f`, `sha256:f03828c5…`, nhãn revision
`8b94a3f5df8c6dddade673adbc2a52bc606503ce`). Các commit sau `8b94a3f` chỉ thêm tài liệu, fixture snapshot,
`.gitattributes` và chú thích kiểu (không đổi hành vi runtime). Mọi cổng chạy trên máy Windows Local, Docker Desktop 4.91.0 / Engine 29.8.0,
mạng Docker **internal** (DNS và HTTPS ra ngoài thất bại), không publish port, dữ liệu tổng hợp, không có DB, PDF
nghiệp vụ hay model Agri thật. Không truy cập production. Evidence Local (không đẩy lên GitHub):
`E:\ProjectWeb\CHATBOT5400\d13-lab\out\`, `d13-l3\out\`, `d13-evidence\`.

## Tổng hợp

| Cổng | Kết quả | Ghi chú |
|---|---|---|
| D12-L1 Candidate RapidOCR offline sau recreate | **PASS** (Docker Desktop) | Reboot Ubuntu guest: **PENDING** (RB-G11) |
| D12-L2 Giao dịch embedding trên SurrealDB 2.7.0 server cô lập | **PASS** (control `-k server`, 3/3 lượt) | Bộ D11 embedded chạy trên engine nhúng; production phải ghi version + engine thực tế |
| D12-L3 Toàn vẹn 22 bảng trước/sau update và rollback | **PASS** (Docker Desktop, chuyển image thủ công) | Trên gói ký chính thức (D11-W07/W09): **PENDING** |
| D12-L4 Gói ký, artifact đã stage, selector, startup, boot guard | **PARTIAL** | Test tích hợp (chữ ký thật, Docker giả) đạt; startup gate RB-1 thật đạt trong D12-L3; gói ký thật, adapter, boot guard, quyền root trên Ubuntu: **PENDING** (Ubuntu VM) |
| D12-L5 API sync timeout, worker hoàn tất muộn, metadata-edit embedding | **PARTIAL** | Timeout 300 s + worker muộn: PASS. Worker bị kill: không có text thiếu, nhưng job kẹt `running` (quan sát P3). Lỗi DB lúc xoá và đổi tiêu đề khi embedding (cần provider embedding): **PENDING** |
| G-04 (Standard expected-diff `--release`) | **READY FOR LOCAL** | D12-03 đã sửa; tài liệu NOT VERIFIED theo quy trình mục G-04 dưới |
| RB-G11 (reboot Ubuntu VM) | **PENDING** | Phase 12F1-B chờ phê duyệt |

## D12-L1 — RapidOCR của candidate, offline (`d13-lab\out\l1.log`)

Image candidate **không** có `ppocrv6_dict.txt` trong thư mục gói (đã kiểm). `OCR_OFFLINE=true`,
`OCR_RAPIDOCR_PERSISTENT=true`, trọng số RapidOCR / Layout Heron / TableFormer từ cache offline đã kiểm ở 12F0.

| Bước | Kết quả |
|---|---|
| S1 cold start (triển khai mới) | Thứ tự log: Docling đã có ⇒ `[rapidocr-dictionary] restored` ⇒ `supervisord started` ⇒ `spawned: 'worker'`. Từ điển `0644 root:root 74947 B b5f2bfe2…`. Egress: `Could not resolve host`, DNS fail |
| S1 Source thật qua API (sync, worker) | `completed`, **10/10** token; log `RapidOcrModel` 1, `engine_name: torch` 3, **Tesseract 0**, **tải 0**, refused 0 |
| S2 recreate app | lớp container mới ⇒ `restored` trước supervisord; RapidOCR (Docling thật, công cụ export) 1/1, 10/10, tải 0, Tesseract 0; 22 bảng so F1: `differences {}`, `preserved: true` |
| S3 restart | `already valid`; 10/10; `preserved: true` |
| S4 cold start cả stack (stop DB + app, start) | `already valid`; 10/10; `preserved: true` |
| S5 recreate lần 2 + Source thật qua API | `restored`; `completed` 10/10, `RapidOcrModel`, Tesseract 0, tải 0; so F2: chỉ **thêm** 1 source / reference / command / recently_viewed, dữ liệu cũ `preserved: true`; 12 embedding giữ nguyên |
| S6 đối chứng âm (file lạ tại đích, offline) | entrypoint `REFUSED (helper code 6)`; Source qua API ⇒ HTTP 500 `RapidOCR dictionary not verified`, **không** `RapidOcrModel`, **không** Tesseract, **không** tải; file lạ **không** bị ghi đè; DB chỉ thêm 1 command `failed` |
| S7 recreate sau đối chứng âm | `restored`, 10/10 |
| DB container | cùng ID suốt S1–S7 (chỉ app được recreate / restart) |

Lượt 1 (`d13-lab\run1\`) có cùng kết quả OCR; dòng snapshot bị lỗi in của script đo (chỉ in `}`), nên được chạy
lại toàn bộ trên dữ liệu mới. Cả hai lượt được giữ.

## D12-L2 — SurrealDB server 2.7.0 (`d13-evidence\d12-l2-server.txt`)

Server `surrealdb/surrealdb:v2` `sha256:e5d7387e…` = `2.7.0 for linux on x86_64`, RocksDB (tmpfs), `--network none`,
cổng loopback 8123 trong namespace mạng riêng của test. `tests/test_phase12d12_review_controls.py -k server`:
bốn job cùng revision ⇒ đúng **một** bộ chunk; job cũ không khôi phục Source đã xoá; liên kết notebook của Source
khác còn nguyên — **2 passed × 3 lượt**. Full regression cũng chạy với server này. Production dùng tag trôi
`surrealdb/surrealdb:v2`: phải ghi `surreal version` và engine thực tế khi nghiệm thu VM.

## D12-L3 — 22 bảng qua update và rollback (`d13-l3\out\l3.log`)

Bản sao lạnh DB lab 12F1 (tổng hợp; 22 bảng, 12 embedding). Một DB container `424461b489e2`, **không restart**.

| Bước | Kết quả |
|---|---|
| P0 v1.2.0 (`chatbot5400:f1lab`) với startup gate RB-1 của candidate (stage = `scripts/offline/rb1` của `8b94a3f`, đúng byte; override = mẫu `compose.json`) | thứ tự: uv cài `rapidocr==3.9.2` ⇒ RB1 restore ⇒ supervisord ⇒ worker; từ điển `b5f2bfe2…`; F0 |
| P1 **update** sang candidate | thứ tự Docling ⇒ dictionary ⇒ supervisord ⇒ worker; F1 so F0: `differences {}` |
| P1 RapidOCR candidate | 1/1, 10/10, tải 0, Tesseract 0; vẫn `differences {}` |
| P2 **rollback** sang v1.2.0 qua startup gate RB-1 | lớp container mới ⇒ uv cài lại ⇒ RB1 restore ⇒ supervisord; F2 so F0: `differences {}` |
| P2 RapidOCR v1.2.0 sau rollback | 1/1, 10/10, tải 0, Tesseract 0; vẫn `differences {}` |
| Digest | schema F0 = F1 = F2; digest dữ liệu F0 = F1 = F2; fingerprint công cụ (bản sửa D10-09) bằng nhau; chỉ raw `INFO FOR TABLE command` đổi (LIVE query, metadata runtime) |

Phân loại 22 bảng (không bảng nào bị loại khỏi phép so record-level): **nghiệp vụ** `source`, `notebook`, `note`,
`source_embedding`, `source_insight`, `reference`, `artifact`, `user`, `credential`, `model`, `open_notebook`,
`transformation`, `episode_profile`, `speaker_profile`, `episode`, `podcast_config`, `chat_session`, `refers_to`,
`ai_feedback`, `_sbl_migrations`; **hoạt động vận hành hợp lệ** `command`, `recently_viewed` (thay đổi chỉ khi có
upload chủ ý — trong D12-L3 không có upload nên cũng bằng nhau); **metadata runtime** LIVE subscription (không phải
dòng dữ liệu). Phương pháp snapshot đã đưa vào repo: `tests/fixtures/phase12f1/f0_preserve.py`, `f0_schema.py`,
`f0_live_control.py`, `f0_case_matrix.py`. Lab D12-L1 / L3 chạy bản gốc 12F1 (`f0-prep\vm-kit\synthetic`, SHA-256 ghi trong `PHASE12F1_RB1_GATE_STATUS.json`); bản trong repo giống byte với `f0_preserve.py` và `f0_synthetic.py`, ba file còn lại chỉ thêm `assert spec …` / chú thích kiểu để `mypy .` không tăng lỗi. Ma trận 8 / 8 D10-09 đã chạy lại bằng bản trong repo trên SurrealDB 2.7.0.

## D12-L4 — RB-1 trên gói ký

| Mục | Trạng thái |
|---|---|
| Selector âm (ID cắt / CRLF / hoa thường / nhiều dòng / rỗng, script rỗng) | PASS (test, Docker giả) |
| Quyền / chủ sở hữu stage, vị trí ngoài checkout và `$WORK` | PASS (test) |
| Tên service = nhãn Compose | PASS (test) |
| Tám file đã stage = byte đã ký (verifier với khoá ngoài stage) | PASS (test, ssh-keygen thật) |
| Startup gate RB-1 thật (entrypoint ⇒ helper ⇒ SHA ⇒ supervisord) trên Docker Desktop | PASS (D12-L3 P0 / P2) |
| Gói ký chính thức, `rb1_setup.py` với Docker thật, adapter, boot guard, root-owned `RB1_STATE` | **PENDING** (Ubuntu VM, D11-W09) |

## D12-L5 — Timeout 300 s (`d13-lab\out\l5.log`)

| Ca | Kết quả |
|---|---|
| C1 worker không trả lời (SIGSTOP), request sync | HTTP 500 sau **301 s**; Source bị xoá; command chờ ở `new`. Sau khi worker chạy lại: `Source … was deleted while processing; stopping without retry`, command `failed`; **không** Source, text, embedding hay reference nào còn lại. **PASS** |
| C2 worker bị SIGKILL giữa lúc chuyển đổi (async) | supervisord spawn lại worker; Source **không có text** (không có text thiếu), không embedding; command cũ **kẹt `running`**, không được chạy lại sau > 2 phút. Hành vi sẵn có của hàng đợi `surreal-commands` (không đổi trong D13). Quan sát **D13-OBS-01 (P3)**: cần xử lý lại thủ công Source đó |
| Lỗi DB lúc xoá Source khi timeout | **PENDING** (cần tiêm lỗi DB đúng thời điểm) |
| D12-01 đổi tiêu đề khi đang embedding | **PENDING** trên lab (cần provider embedding; lab không có mạng); control `xfail(strict)` D12-01 giữ nguyên |

Lượt 1 không hợp lệ (image không có `pkill`, worker không bị dừng) được giữ:
`out\l5-run1-invalid-no-pkill.log`.

## G-04 — quy trình cho tài liệu NOT VERIFIED

`phase12_standard_diff.py --release` sau D12-03 chỉ trả mã 0 khi mọi khác biệt được dựng lại từ dòng TSV và hộp
đã ghi. Các loại sau **thiếu provenance** nên trả NOT VERIFIED (mã 2), không được ép thành PASS: số hiệu gạch nối
trong tiêu đề mục, list item, header / footer trang, ô bảng, đoạn nối qua trang, sau token bị escape Markdown, và
gạch nối khép giữa các ô text-layer.

Quy trình kiểm chứng Local riêng (bằng chứng bổ sung cho chủ dự án, **không** đổi mã thoát):

1. Chạy export + diff `--release` trên commit cuối; ghi mã thoát và lớp của từng tài liệu.
2. Với từng tài liệu NOT VERIFIED: chạy lại diff với `--with-text` (báo cáo `0600`, chỉ trên máy Local), đối chiếu
   từng hunk với TSV gốc của đúng invocation (trang, crop, dòng), và với ảnh trang.
3. Ghi biên bản: tài liệu, hunk, loại thiếu provenance, kết luận "đúng chữ in" / "sai"; người kiểm và ngày.
4. Bất kỳ hunk "sai" nào ⇒ hồi quy, không phát hành. Chỉ chủ dự án quyết định có chấp nhận biên bản thay cho mã 0
   hay không; G-04 không được ghi PASS khi còn tài liệu NOT VERIFIED chưa có quyết định đó.

## Hồi quy

Xem [báo cáo hồi quy](PHASE12D13_REGRESSION_REPORT.md).
