# Nghiệm thu cuối — OCR Engine Manager

Cập nhật: 2026-11-14 · Trạng thái sau khi merge Pull Request #42, **trước** khi triển khai production.

File này là bảng trạng thái tổng hợp của toàn dự án. Nó được cập nhật sau mỗi mốc (merge, triển khai, bàn
giao) qua một Pull Request tài liệu; mỗi dòng chỉ được ghi PASS khi đã có bằng chứng chạy thật. Chi tiết:
[OCR_PHASE9B_REPORT.md](OCR_PHASE9B_REPORT.md), [ACCEPTANCE_CHECKLIST.md](ACCEPTANCE_CHECKLIST.md).

Quy ước: **PASS** · **FAIL** · **NOT VERIFIED** (chưa chạy thật) · **NOT APPLICABLE** · **PENDING** (chưa tới bước).

## 1. Trạng thái các phase

| Mốc | Trạng thái |
|---|---|
| Phase 9A — cổng bảo mật, Release Candidate | **COMPLETED AND VERIFIED** |
| Phase 9B — review cuối, nghiệm thu cuối, Pull Request | **COMPLETED** — nghiệm thu PASS; PR #42 **MERGED** bằng merge commit `3819c2a` |
| Phase 9C — triển khai production | **NOT DEPLOYED** — đã chuẩn bị xong phần không gián đoạn; dừng ở cổng phê duyệt (**READY FOR DEPLOYMENT APPROVAL**), còn thiếu benchmark tài liệu thật hoặc phê duyệt phạm vi thí điểm |
| Production được xác minh | **NOT VERIFIED** |
| Sẵn sàng offline (stack nghiệm thu cô lập) | **PASS** — cả 4 lựa chọn đạt `offline_ready` → `offline_verified` trong Docker acceptance |
| Offline đã xác minh — stack cô lập | **PASS** — image nghiệm thu (`6f6b424`) và **chính image triển khai** (mục 5): nâng cấp từ `5e04227`, chuẩn bị Tesseract Best, xử lý PDF khi offline, restart offline, sau cập nhật — 42 PASS / 0 FAIL |
| Offline đã xác minh — production | **NOT VERIFIED** — cần quy trình ngắt mạng được phê duyệt |
| Bàn giao | **PENDING** |

## 2. Bảng nghiệm thu

| Hạng mục | Baseline 9A | Kết quả cuối | Trạng thái |
|---|---|---|---|
| Backend | 1288 passed / 10 failed | 1435 passed / 10 failed — cùng đúng 10 lỗi có sẵn | PASS (không lỗi mới) |
| Frontend | 411/411 | 411/411; lint 0 error; tsc 0; build OK | PASS |
| Security (test) | 185 passed | 335 passed; trực tiếp 7/7 và 16/16 | PASS |
| Bộ OCR gốc | 38/48 | 38/48 — đúng 10 bài cũ | Không đổi (**không** phải 48/48) |
| Tesseract Best — có điều kiện | 7/7 | 7/7, critical 7/7 (bộ gốc 6/9) | PASS |
| Docker quick | 42/42 | 42/42 | PASS |
| Docker full | 74/75 ở 8D | 74/75 — FAIL: nội dung EasyOCR | Không lỗi mới |
| RapidOCR persistent | 42/42 ở 8D | 42/42 | PASS (giới hạn recreate offline: D-32) |
| Image không có Tesseract | 50/51 ở 8D | 50/51 — FAIL: nội dung EasyOCR | Runtime PASS |
| Đồng thời + dọn file tạm (trực tiếp) | 6/6 | lượt 1: 3/6 (xung đột ghi SurrealDB, có sẵn); chạy lại 6/6 | PASS khi chạy lại; lỗi không ổn định được ghi nhận |
| Benchmark tài liệu nghiệp vụ thật | Chưa thực hiện | Chưa thực hiện (công cụ đã kiểm bằng tài liệu tổng hợp) | **NOT VERIFIED** |
| Backup production | Chưa thực hiện | Chưa thực hiện | **PENDING** |
| Restore | Chưa thực hiện | Chưa thực hiện | **PENDING** |
| Production | Chưa triển khai | Chưa triển khai | **NOT DEPLOYED** |
| Offline production | Chưa xác minh | Chưa xác minh | **NOT VERIFIED** |

## 3. Giới hạn đã chấp nhận và còn mở

- Đã chấp nhận: KL-1 (mất dấu ở tiêu đề in đậm `BẢNG KÊ CHI TIẾT KHOẢN MỤC MẪU`); `tesseract_gate.py`; RapidOCR
  mất dấu tiếng Việt; EasyOCR ở mức thử nghiệm; Tesseract Fast chưa đạt chuẩn nghiệp vụ.
- Còn mở: benchmark tài liệu thật; route podcast mở cho mọi tài khoản (quyết định sản phẩm); RapidOCR lưu bền
  cần "Chuẩn bị" sau recreate; xung đột ghi khi tạo nhiều nguồn cùng lúc; các điểm mức Thấp ở
  `OCR_PHASE9B_REPORT.md` §B.3.
- SSRF: giảm thiểu bằng cách tắt URL ingestion và thực thi vai trò quản trị viên; **không** tuyên bố đã sửa triệt để.

## 4. Commit

| | |
|---|---|
| Production trước tính năng | `5e042279439302d3ccf39bef4d1d8d402314d194` |
| Mã được nghiệm thu | `6f6b42429da3b0a48eee6044a2cc7d12cadecdfc` |
| Pull Request | [#42](https://github.com/nghoainam1902ps4-lgtm/ChatBot5400-Version02/pull/42) |
| Commit merge trên nhánh chính thức | `3819c2a7068916bf7cd2d5bc9c71cfe73b76dfbc` (2026-11-13 18:57 UTC; cha: `5e04227` + `8ba2483`; cây mã giống hệt `8ba2483`) |
| Image triển khai đã dựng (chưa triển khai) | `chatbot5400:rc1-20261114` = `sha256:240bb692922101385c8a4fcb0aaf15451f4ba345ae027e232265e37005d58f56`, dựng từ commit merge ở thư mục riêng, có Tesseract 5.5.0 |
| Commit và image đang chạy trên production | chưa đổi: `5e04227`, image cũ |

## 5. Chuẩn bị Phase 9C đã hoàn tất (không gián đoạn, không thay đổi production)

| Việc | Kết quả |
|---|---|
| Kiểm tra chỉ đọc production | Xong — `OCR_PRODUCTION_DEPLOYMENT_PLAN.md` §1.1 |
| Số bản ghi gốc (chỉ số đếm) và trạng thái job | Đã ghi; 0 job đang chạy |
| Image triển khai dựng trước, tag riêng | `chatbot5400:rc1-20261114`; `chatbot5400:local` của production không bị ghi đè |
| Xác minh image triển khai trên stack cô lập (online → chuẩn bị → offline → restart offline → cập nhật) | 42 PASS / 0 FAIL / 0 NOT VERIFIED |
| Bản vá cục bộ của `docker-compose.yml` production áp lên bản đã merge | Áp sạch (thử trên bản sao) |
| Công cụ: đếm bản ghi, sinh compose cho stack restore cô lập, script kiểm tra sức khỏe, script triển khai từng bước | Sẵn sàng; chưa chạy bước nào làm thay đổi production |
| Công cụ benchmark tài liệu thật | Đã kiểm bằng tài liệu tổng hợp; hướng dẫn copy-paste ở `OCR_REAL_DOCUMENT_BENCHMARK.md` §4 |

Chưa làm và **không** được coi là đạt: benchmark tài liệu thật, sao lưu, kiểm tra restore, triển khai, cài và
chuẩn bị Tesseract Best trên production, smoke test production, offline trên production, theo dõi 24 giờ.
