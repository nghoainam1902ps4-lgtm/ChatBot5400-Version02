# Phase 12D13 — Bàn giao (Claude Code, Windows Local)

Phạm vi: sửa D12-03, cứng hoá RB-1, RapidOCR offline cho candidate, nghiệm thu Local D12-L1…L5 với dữ liệu tổng hợp.
Không audit toàn dự án. Không truy cập production, không SSH, không dùng DB / PDF nghiệp vụ / model Agri thật, không
bật Hyper-V, không reboot Windows, không xoá volume, không prune, không đổi `VERSION`, không merge PR #50, không
phát hành.

## Commit (trên `18eeecb`, fast-forward)

| Commit | Nội dung |
|---|---|
| `44b0182` … `26ff1c1` | Hồ sơ và test kiểm soát review 12D12 (nhánh `claude/jolly-knuth-rivla0`, giữ nguyên) |
| `842c9b5` | **D12-03**: `verify_bound_output` dựng lại cả văn bản candidate từ dòng TSV + hộp đã ghi |
| `fd058b9` | **RB-1 hardening**: selector chặt, payload đọc một lần, `verify_stage.py`, nhãn Compose, vị trí stage |
| `8b94a3f` | **RapidOCR offline cho candidate** (D12-L1): khôi phục từ điển đã duyệt lúc khởi động và trước khi cấu hình RapidOCR |
| `f165399` | Phương pháp snapshot 22 bảng vào repo (D12-L3); chỉ chú thích kiểu |
| đầu nhánh | Tài liệu `docs/review/PHASE12D13_*` |

Nhánh làm việc: worktree riêng `E:\ProjectWeb\CHATBOT5400\wt-d13`, nhánh cục bộ `phase12d13-remediation`; không
đụng worktree hay tiến trình của Codex. Image test: `chatbot5400:phase12-test-8b94a3f` (`sha256:f03828c5…`).

## Kết quả

| Hạng mục | Kết quả |
|---|---|
| D12-03 | **FIXED** — 4 / 4 control gốc (RED trên `26ff1c1`, GREEN trên bản sửa); ca hợp lệ vẫn đạt |
| Control D10 | **16 / 16** (13 control gốc + 3 control đạt) |
| RB-1 hardening | **PASS** — 7 / 7 điểm, test chữ ký thật; startup gate giữ nguyên, fail-closed |
| Candidate RapidOCR offline | **PASS** trên Docker Desktop (cold start, recreate × 3, restart, cold start cả stack, 2 Source thật qua API, đối chứng âm) |
| SurrealDB 2.7.0 concurrency | **PASS** (D12-L2, 3 / 3 lượt) |
| 22 bảng | **PASS** (D12-L1 và D12-L3: update + rollback qua cổng RB-1) |
| G-04 | **READY FOR LOCAL** (không hạ tiêu chí; quy trình riêng cho NOT VERIFIED) |
| Full regression | xem [báo cáo hồi quy](PHASE12D13_REGRESSION_REPORT.md) |
| D12-01, D12-02 | P3, ghi nhận, test giữ `xfail(strict)` |
| D13-OBS-01 (mới, P3, có sẵn) | worker bị SIGKILL ⇒ job kẹt `running`, Source không có text (không có text thiếu) |

## Còn PENDING

- RB-G11 reboot Ubuntu VM và phần reboot guest của D12-L1 (Phase 12F1-B chờ phê duyệt).
- D12-L4 trên gói ký chính thức: `rb1_setup.py` với Docker thật, `RB1_STATE` do root sở hữu, adapter và boot guard
  (gọi `verify_stage.py` + selector theo C10), khôi phục đúng restart policy đích trước khi thử boot guard.
- D12-L5: lỗi DB đúng lúc xoá Source khi timeout; đổi tiêu đề khi đang embedding (cần provider embedding).
- D11-W09 diễn tập gói ký; G-07 / G-09; E2-01 / E2-02 giữ `NEEDS LOCAL EVIDENCE`.
- G-04 trên 22 PDF pháp lý thật (Local, không đưa ra khỏi máy): tài liệu NOT VERIFIED cần quyết định của chủ dự án.

## Tài liệu

[D12-03](PHASE12D13_D12_03_FIX_REPORT.md) · [RB-1 hardening](PHASE12D13_RB1_HARDENING_REPORT.md) ·
[Checklist Local](PHASE12D13_LOCAL_ACCEPTANCE_CHECKLIST.md) · [Hồi quy](PHASE12D13_REGRESSION_REPORT.md) ·
[Trạng thái JSON](PHASE12D13_FINDING_STATUS.json)

```text
D12-03: FIXED
D12-03 ORIGINAL CONTROLS: 4/4
D10 CONTROLS: 16/16
RB-1 HARDENING: PASS
CANDIDATE RAPIDOCR OFFLINE: PASS (Docker Desktop; Ubuntu VM reboot PENDING)
SURREALDB 2.7.0 CONCURRENCY: PASS
22-TABLE PRESERVATION: PASS (Docker Desktop; signed-package rehearsal PENDING)
G-04: READY FOR LOCAL
READY FOR WINDOWS ACCEPTANCE: YES (conditional on the PENDING items above)
READY FOR RELEASE: NO
READY FOR PRODUCTION: NO
PRODUCTION UNCHANGED.
```
