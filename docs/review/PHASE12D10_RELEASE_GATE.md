# Phase 12D10 — Release gate

Áp dụng cho `2cc824f66638d6db229993b4cc98948300e6bd8b` trong PR #50 Draft. Nhánh `review/phase12d10-codex-targeted` chứa bàn giao và test phản ví dụ. Kết quả nghiệm thu cuối Windows hiện **NO**, với 9 blocker mở. [Báo cáo review](PHASE12D10_CODEX_TARGETED_REVIEW.md) · [Trạng thái JSON](PHASE12D10_FINDING_STATUS.json)

| Cổng | Kết quả | Bằng chứng để đóng |
|---|---|---|
| Áp dụng upstream patches | FAIL | D10-01. Selected và native PDF, cả upload và URL, từ chối khi guard không qua. Chạy fresh worker, cached converter, concurrent calls, readiness offline, compat hash và kiểm phạm vi serializer toàn process. |
| D8-03 | FAIL | D10-03, D10-07. Xác minh đầy đủ mã gồm khoảng trắng và dấu gạch theo từng vị trí, cả cột, cuối dòng, qua trang, PDF text layer và bảng. |
| D8-01 | PASS trong review | Chạy G-H3/G-H4 trên commit nghiệm thu với PDF nhiều khổ và nhiều cột. So chuỗi khối theo thứ tự khai báo, gồm bảng, chú thích, phụ lục và provenance thiếu. |
| D8-02 | FAIL | D10-04. Giữ đúng cấu trúc literal Markdown ở Legal, vị trí và số lần của footnote trong Standard/Legal, kiểm cùng caption và bảng/ảnh. |
| E2-04 | FAIL | D10-02. Kiểm selected và native, cả async và sync, lỗi trang giữa, kết quả success có lỗi, tài liệu rỗng, reprocess và job embedding đang chạy. Xác minh không publish dữ liệu hoặc vector thiếu. Theo dõi stderr thực thu theo lượng byte. |
| Standard expected-diff / G-04 | FAIL | D10-05, D10-06, D10-07. Thử các mã 0/1/2/3 với manifest đầy đủ; ràng buộc bằng chứng đúng tài liệu, lần chạy, trang/crop, model và span. Ca chỉ biết tên loại khác biệt hướng xoay phải giữ chưa xác minh. |
| Offline manual fallback | FAIL | D10-08, D10-09. Diễn tập publish lỗi, gói/chữ ký và restore bản sao thử, kiểm dữ liệu kể cả bảng không có `updated`. Chạy G-07 đến G-09, ghi image ID, DB ID/mount và kết quả rollback tái lập được bằng deploy tag. |

Sau khi các phản ví dụ đạt với assertion nguyên trạng, chạy lại các mục Local trên cùng commit ứng viên và lưu mã thoát, ID image và kết quả kiểm DB. E2-01 và E2-02 tiếp tục theo dõi chất lượng nhận dạng. Updater tự động giữ **EXPERIMENTAL**. [Checklist Local 12D9](PHASE12D9_LOCAL_ACCEPTANCE_CHECKLIST.md)

```text
TARGETED INDEPENDENT REVIEW: PARTIAL
D8-03: FAIL
D8-01: PASS
D8-02: FAIL
E2-04: FAIL
STANDARD EXPECTED-DIFF: FAIL
OFFLINE MANUAL FALLBACK: FAIL
NEW RELEASE BLOCKERS: 9 (D10-01 through D10-09)
READY FOR FINAL WINDOWS ACCEPTANCE: NO
READY FOR RELEASE: NO
PRODUCTION UNCHANGED
```
