# Phase 12D2 — Kế hoạch khắc phục cho Phase 12D3

Dành cho phiên phát triển (Opus) thực hiện Phase 12D3 trên nhánh `feature/legal-document-normalization`.
Chi tiết từng finding: [PHASE12D2_FINDINGS.json](PHASE12D2_FINDINGS.json). Test phản ví dụ:
`tests/review_phase12d2/` trên nhánh `review/phase12-fable-audit`.

## 0. Nguyên tắc

1. Sửa nhỏ, có test, không viết lại kiến trúc. Không finding nào đòi hỏi thay đổi kiến trúc.
2. Mỗi bản sửa bắt đầu bằng việc **chép test phản ví dụ tương ứng** sang nhánh feature và **gỡ `xfail`**: test phải đỏ trước khi
   sửa, xanh sau khi sửa. Các test `xfail(strict=True)` sẽ tự báo lỗi nếu còn marker sau khi đã sửa.
3. Khi không chắc thì **giữ nội dung** và ghi cảnh báo. Xóa nhầm nội dung pháp lý nặng hơn để sót một số trang.
4. Chế độ Standard phải tiếp tục giống v1.2.0 từng byte (`test_convert_file_standard_is_byte_identical` giữ nguyên).
5. Không đổi mặc định: Legal vẫn tắt, cần hai công tắc.

## 1. Nhóm A — bắt buộc sửa (chặn phát hành)

### A1. F-01 — dòng lặp bị coi là header/footer (`_find_repeated`)

Hướng sửa tối thiểu, theo thứ tự ưu tiên:

1. Luôn **giữ lần xuất hiện đầu tiên** của mỗi nhóm lặp (chỉ chuyển furniture từ lần thứ hai). Một mình bước này đã loại bỏ mất
   mát thông tin trong mọi phản ví dụ của F-01.
2. Thêm bằng chứng vị trí: item phải nằm **ngoài hộp bao của phần thân trang**. Tính hộp bao thân bằng trung vị mép trên/mép dưới
   của các item thân trên toàn tài liệu; ứng viên header phải kết thúc phía trên trung vị mép trên một khoảng ≥ 1 chiều cao dòng.
   Dòng thân đầu tiên của trang (đúng tại mép thân) không còn là ứng viên.
3. Nâng `REPEATED_MIN_SHARE` lên 0,8 và yêu cầu cùng vị trí ngang (lệch ≤ 5% bề rộng trang).
4. Mẫu loại trừ: `^(đơn vị tính|đvt|kính gửi|nơi nhận|căn cứ|\(ký)` (không phân biệt hoa thường).

Test: gỡ `xfail` của `test_f01_*`; thêm fixture f25 (phụ lục có dòng đơn vị tính), f26 (bộ 4 thông báo một trang).

### A2. F-02 — số bị coi là số trang (`_find_page_numbers`)

1. Yêu cầu nhóm cùng offset có **≥ 3 trang và ≥ 60% số trang** của tài liệu (tài liệu 2 trang: không suy diễn, giữ và cảnh báo).
2. Yêu cầu **cùng dải** và tâm ngang gần nhau (cho phép hai cụm đối xứng cho lề chẵn/lẻ).
3. Giá trị phải nằm trong `[1, số_trang + 50]` trừ khi item đã mang nhãn `PAGE_HEADER`/`PAGE_FOOTER`.
4. Áp dụng cùng tiêu chí "ngoài hộp bao thân" của A1.

Test: gỡ `xfail` của `test_f02_*`; fixture f22 hiện có (`single_page_number_kept`) phải tiếp tục đạt; thêm tài liệu 5 trang có số
trang thật để chắc chắn không làm mất tính năng.

### A3. F-03 — ghép sai liên trang (`_join_allowed`)

1. `_STRUCTURE_START`: thêm `[a-zđ](?:\.\d+)*[.)/]\s`, `\([a-zđ0-9]{1,3}\)\s`, `[a-zđ]\.\d+[.)]`.
2. Vế trái `a` phải là **đoạn bị cắt thật**: bề rộng bbox ≥ 85% bề rộng cột thân (trung vị bề rộng các item TEXT của trang) và
   không nằm hoàn toàn trong dải dưới (`_band(...) != "bottom"`).
3. Không ghép khi `a.text` khớp mẫu footnote `^\d{1,2}[\s)\.]` hoặc `^[*†]`.
4. Không ghép khi text của `a` xuất hiện nguyên văn trong dải của trang kế tiếp (footer lặp của tài liệu 2 trang).
5. Giữ nguyên toàn bộ điều kiện hiện có.

Test: gỡ `xfail` của `test_f03_*`; 3 fixture `must_join` hiện có phải tiếp tục đạt.

### A4. F-04 (+F-05, F-27) — build gói và git bundle

Trong `cmd_build`:

1. Kiểm tra `VERSION` của checkout so với `--version` **trước** mọi lệnh Docker (F-27).
2. Tạo ref tạm `refs/cb5400-offline/build/<version>` trỏ tới commit; bundle `"<base>..refs/cb5400-offline/build/<version>"`;
   xóa ref tạm trong `finally`. Chạy bước này **trước** `docker save`.
3. Sau khi tạo: `git bundle list-heads` phải chứa commit của manifest, nếu không thì dừng.
4. Thất bại ở bất kỳ bước nào: xóa thư mục stage.

Trong `sync_source`: fetch đúng ref đó (`refs/cb5400-offline/build/<version>`), không dùng `refs/*`.

Test: gỡ `xfail` của `test_f04_*`, `test_f05_*`; thêm test chạy `build-package.sh --no-build` với docker giả; thêm 4 test cho
`sync_source` (thành công, phân nhánh, xung đột cục bộ, không phải git).

### A5. F-08 — backup cũ được dùng lại

Khi `update --apply` thấy `status ∈ {rolled_back, failed, completed}`: lưu journal sang `journal-<thời điểm>.json`, tạo journal
mới, **chép `previous_image` và `rollback_tag` gốc** sang, rồi chạy lại từ G (load là idempotent; H bỏ qua nếu tag gốc còn trỏ đúng
ID). Bước I và J luôn chạy lại.

Test: gỡ `xfail` của `test_f08_*`; thêm kịch bản `failed → rollback interrupted → update`.

### A6. F-11 — trôi cấu hình sau cập nhật

Tối thiểu để gỡ chặn:

1. `status` và `health`: so image ID của container đang chạy với ID trong journal (và danh sách biến `APP_ENV_OVERRIDES`); khác
   ⇒ in `DRIFT` và trả mã ≠ 0.
2. `finish` in ra và ghi `STATE_DIR/compose-command.txt` lệnh Compose đầy đủ (có `-f` override) là lệnh duy nhất được dùng.
3. Tài liệu Ubuntu: thêm mục "Sau khi cập nhật" nêu rõ hậu quả của `docker compose up -d` trần và cách chốt lâu dài (thêm
   override vào `COMPOSE_FILE` trong `.env` của triển khai — thao tác thủ công của người vận hành).

Tùy chọn (hoãn được): cờ `--pin-in-deploy-dir` chép override vào thư mục triển khai.

## 2. Nhóm B — bắt buộc trước khi bật Legal hoặc cập nhật offline trên production (không chặn RC)

| ID | Việc | Ghi chú |
|---|---|---|
| F-06 | Ngưỡng bỏ placeholder im lặng ≤ 4% + cảnh báo có trang cho phần còn lại | Một hằng số + một nhánh cảnh báo |
| F-07 | Lưu `extraction_meta` trên Source; nhãn trạng thái ở trang Source | Bảng schemaless, không migration |
| F-09 | `health_checks` sau `finish` và `rollback`; ghi trạng thái theo kết quả | Dùng lại hàm sẵn có |
| F-21 | Snapshot `docker inspect` của container DB ở preflight; khẳng định không đổi sau mỗi `up`; lấy đường cơ sở trước bước K; kiểm schema + đếm bản ghi sau khởi động | |
| F-22 | Preflight chạy `ocr.cli readiness --check` trong container cũ; xét kết quả chép RapidOCR | |
| F-20 | Xác minh trên Docker thật; nếu đúng thì so thêm digest config đọc từ file tar | Chờ kết quả checklist W-OFF-03 |
| T-01 | Đổi oracle "0 từ mất" sang so với `ground_truth` của fixture | Phải làm **trước** A1-A3 để các bản sửa được đo đúng |
| T-03 | Lọc tham số hóa theo khóa fixture; thêm fixture phản ví dụ | |
| F-10 | Thay `delete_items` bằng đánh dấu bỏ qua; ngân sách thời gian ⇒ fallback | |

## 3. Nhóm C — có thể hoãn sau RC

F-12, F-13, F-14, F-15, F-16, F-17, F-18, F-23, F-24, F-25, F-26, T-02. Mỗi mục có "proposed_minimal_fix" trong file JSON. Khuyến
nghị làm F-12, F-13, T-02 cùng đợt vì mỗi mục dưới 20 dòng.

## 4. Thứ tự thực hiện đề xuất

1. T-01 (oracle) → chép fixture phản ví dụ → xác nhận đỏ.
2. A1, A2, A3 (normalizer) → chạy lại `scripts/ocr/phase12_benchmark.py` với oracle mới; cập nhật số liệu trong báo cáo 12D.
3. A4 (build/bundle) → thử `build-package.sh --no-build` với docker giả.
4. A5, A6, F-09 (máy trạng thái).
5. F-21, F-22 (preflight/kiểm tra DB).
6. F-06, F-07, F-10.
7. Chạy toàn bộ: backend, frontend, `tests/review_phase12d2` (không còn `xfail`).
8. Bàn giao Windows Local theo [PHASE12D2_WINDOWS_ACCEPTANCE_CHECKLIST.md](PHASE12D2_WINDOWS_ACCEPTANCE_CHECKLIST.md).

## 5. Tiêu chí hoàn thành Phase 12D3

- `tests/review_phase12d2/` không còn marker `xfail` cho F-01, F-02, F-03, F-04, F-05, F-08, F-09, T-01, T-02 và toàn bộ PASS.
- 24 fixture cũ vẫn đạt; Standard vẫn giống v1.2.0 từng byte.
- Báo cáo 12D cập nhật: số "từ bị mất" đo bằng ground truth; số đo hiệu năng có trường hợp nhiều phép ghép.
- Tài liệu offline cập nhật mục drift, mục build, và bảng gián đoạn (§4 của hướng dẫn Ubuntu hiện ghi sai trường hợp container đã
  bị gỡ).
- Không thay đổi: VERSION (trừ khi chủ dự án quyết định cho RC), tag, release, default branch, production.

## 6. Những việc KHÔNG làm trong 12D3

Phase 11 Security Hardening; thay kiến trúc OCR; tự động xử lý lại Source cũ; tăng VERSION/tạo tag/release khi chưa có quyết định;
kết nối production; dùng PDF nghiệp vụ thật hoặc model Agri nội bộ trong Cloud.
