# Phase 12D4 — Bàn giao

## 1. Trạng thái

| | |
|---|---|
| Nhánh review | `review/phase12d4-fable-reaudit` (từ `8d0c438`); chỉ thêm `docs/review/PHASE12D4_*` và `tests/review_phase12d4/` |
| Mã runtime | **không đổi** (`git diff --name-only 8d0c438 HEAD` chỉ liệt kê hai nhóm file trên) |
| Nhánh feature / nhánh audit cũ / nhánh mặc định / tag | không đổi |
| PR #50 | Draft; không approve, không merge |
| `VERSION` | 1.2.0 |
| Production | không kết nối, không thay đổi |

**Tính độc lập:** Phase 12D3 và 12D4 được làm trong cùng một phiên, bởi cùng model (`claude-fable-5-2`). Đây là tự
rà soát có hỗ trợ của sub-agent ngữ cảnh mới, **không phải** review độc lập. Chi tiết:
[PHASE12D4_FABLE_RE_REVIEW.md](PHASE12D4_FABLE_RE_REVIEW.md) §0.

## 2. Sản phẩm

| File | Nội dung |
|---|---|
| [PHASE12D4_FABLE_RE_REVIEW.md](PHASE12D4_FABLE_RE_REVIEW.md) | Báo cáo chính |
| [PHASE12D4_FINDING_CLOSURE_MATRIX.json](PHASE12D4_FINDING_CLOSURE_MATRIX.json) | 29 finding gốc: bản sửa, test, RED / GREEN, test độc lập, kết quả, cổng Local, hồi quy, điều kiện đóng |
| [PHASE12D4_NEW_FINDINGS.json](PHASE12D4_NEW_FINDINGS.json) | 22 finding mới R2-01 … R2-22 |
| [PHASE12D4_TEST_ORACLE_AUDIT.md](PHASE12D4_TEST_ORACLE_AUDIT.md) | Oracle, đột biến, fixture đã chỉnh |
| [PHASE12D4_OFFLINE_UPDATE_REAUDIT.md](PHASE12D4_OFFLINE_UPDATE_REAUDIT.md) | Công cụ offline |
| [PHASE12D4_WINDOWS_ACCEPTANCE_CHECKLIST.md](PHASE12D4_WINDOWS_ACCEPTANCE_CHECKLIST.md) | Thứ tự nghiệm thu, cổng RC / production |
| `tests/review_phase12d4/` | 139 test: 97 passed, 42 `xfail(strict)` |

## 3. Chạy lại

```bash
uv run pytest tests/review_phase12d4 tests/review_phase12d2 -q -rxX -p no:cacheprovider
```

Kỳ vọng trên `8d0c438`: **129 passed, 42 xfailed, 0 xpassed** (khoảng 3 phút).

```bash
uv run pytest tests/ -q -p no:cacheprovider --timeout=120
```

Kỳ vọng (không tính `tests/review_phase12d4`): 2424 passed / 13 failed / 65 skipped; 13 tên lỗi trùng v1.2.0.

Quy ước test: `xfail(strict=True)` nêu hành vi mong đợi (đỏ hôm nay; khi sửa xong sẽ thành XPASS ⇒ gỡ marker).
Bốn file `test_offline_evidence_*.py` theo quy ước ngược: mỗi test **tái hiện** một lỗi và đạt khi lỗi còn; khi sửa
phải đảo thành test hồi quy.

## 4. Đề xuất Phase 12D5 — sửa lỗi, không thêm tính năng

Thứ tự theo rủi ro. Mỗi mục: gỡ `xfail` / đảo test evidence tương ứng, đỏ trước, xanh sau.

### Nhóm A — an toàn giao dịch của công cụ offline (P1)

1. **R2-12** — override theo attempt; `compose-command.txt` và con trỏ "hiện hành" chỉ đổi ở `finish` / `rollback`
   thành công; dọn khi bị từ chối.
2. **R2-05** — hai mốc: mốc của bước update (bất biến của attempt) + mốc trước mỗi `up`. `finish` / `rollback` so
   với mốc update: container DB cùng ID / image / mount; số bản ghi chỉ được tăng; giảm, hoặc không đọc được ⇒ dừng,
   cần xác nhận rõ. `finish` đọc `db_changed`. Băm danh sách id theo bảng thay cho chỉ đếm.
3. **R2-04** (F-08) — bỏ dùng lại backup theo TTL; vào bảo trì (hoặc xác nhận đã ngừng ghi) **trước** backup; ghi
   mốc dữ liệu lúc backup và so trước `up`; từ chối mã tham chiếu đã dùng.
4. **R2-13**, **R2-15** — `status` so với "phiên bản được duyệt gần nhất" ở mọi trạng thái; ghi ý định trước hành
   động (`K_intent`, `Q_intent`); ghi journal mới trước khi lưu trữ bản cũ.

### Nhóm B — bảo toàn nội dung pháp lý (P1)

5. **F-02** — số trang: yêu cầu thêm bằng chứng ngữ nghĩa (không có item nhãn cùng dòng; không dạng `n/yyyy`; không
   số 0 đứng đầu; vị trí giữa hoặc sát mép ngoài trang) hoặc nhãn layout; còn lại giữ + cảnh báo.
6. **F-03** — nối: footnote mọi dạng ký hiệu và footnote không ký hiệu (item cuối trang nằm dưới đoạn bị cắt thì
   không bao giờ là vế trái); marker hỏng do OCR (`c )`, `a,`, `a-`, `o `); dòng ngày / đơn vị / `trong đó:`; dòng
   đầu trang không phải dòng thân đầu tiên. Nguyên tắc: **không nối khi trang sau có hơn một ứng viên**.
7. **R2-01** — với TEXT nhiều provenance do Docling nối: áp cùng quy tắc từ chối, tách lại theo charspan khi từ chối,
   khôi phục gạch nối; tối thiểu là cảnh báo có trang.
8. **R2-11**, **F-06** — cảnh báo cho furniture có chữ không lặp; caption / một từ lạc không được coi là chữ của ảnh.

### Nhóm C — thước đo (làm trước nhóm B)

9. **R2-14** (T-01, T-03) — oracle so theo (trang, chữ, thứ tự); tách bể artifact; đo placeholder và furniture;
   assert thứ tự tuyệt đối; thêm biến thể vị trí / đuôi chữ / nhãn cho mọi fixture ngưỡng; đưa các phản ví dụ của
   12D4 vào benchmark. **Ground truth của fixture mới nên do người không viết normalizer khai báo.**

### Nhóm D — chuỗi tin cậy và danh tính (P2 / P3)

10. **R2-07** — báo cáo verify trong `STATE_DIR`; kiểm quyền thư mục gói; có khóa ký thì luôn kiểm lại chữ ký.
11. **R2-06**, **R2-08** — danh tính image gồm cấu hình chạy; bắt buộc nhãn `revision` khớp commit.
12. **R2-10** (F-22) — health khẳng định chính bảng mã nạp được; offline thiếu cache ⇒ thất bại rõ ràng;
    `context_builder` dùng chung hàm có guard.
13. **F-11 / R2-16** — thay pin tùy chọn bằng hợp đồng tích hợp (cần mô tả script vận hành thật từ chủ dự án).

### Nhóm E — còn lại (P3 / P4)

R2-02, R2-03, R2-09, R2-17, R2-18, R2-19, R2-20, R2-21, R2-22, F-17 (phần còn lại).

Không thuộc 12D5: tính năng mới, đổi Docling / engine / model / schema / dependency, đóng gói model.

## 5. Việc chủ dự án có thể làm ngay tại Windows Local

Không cần chờ 12D5 (xem checklist): bước 1–4, 6–12, 17–19 và W-PIPE. Ba việc có giá trị nhất, vì chúng quyết định
phạm vi 12D5:

1. Layout Heron gắn nhãn gì cho số trang, header, footer, số hiệu văn bản trên scan thật (W-RC-01, W-RC-07, W-RC-09).
2. Phép nối của Docling có xảy ra trên scan thật không (W-RC-04, W-RC-08).
3. `build-package.ps1` có chạy được không trên PowerShell 5.1 và 7; bố cục thật của `docker save`; image ID giữa hai
   image store (W-OFF-01, 04, 05, 06).

Và một việc không cần máy: mô tả lệnh / script Compose mà máy chủ thật dùng (chạy thường, bảo trì, restart, reboot).

## 6. Điều tôi không biết

- Tần suất thật của mọi lỗi Legal ở trên: phụ thuộc hoàn toàn vào nhãn và bbox của Layout Heron trên scan thật.
- Tỷ lệ token / từ của tiếng Việt với `o200k_base`.
- Hành vi của Docker / Compose thật ở mọi điểm công cụ offline dựa vào.
- `build-package.ps1` có chạy được không.
- Còn bao nhiêu lỗi mà cả tôi lẫn hai sub-agent cùng họ model đều không nhìn thấy.

## 7. Không được làm khi tiếp nhận

Không merge / approve PR #50; không phát hành RC; không triển khai production; không force-push; không sửa nhánh
feature từ nhánh review; không đổi `VERSION`, tag cũ, nhánh audit cũ; không đưa PDF nghiệp vụ, model Agri, secret,
khóa ký lên Cloud hay vào Git.
