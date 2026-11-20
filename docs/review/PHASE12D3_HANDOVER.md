# Phase 12D3 — Bàn giao cho review độc lập Phase 12D4 và nghiệm thu Windows Local

Người nhận: (1) phiên review độc lập Phase 12D4 (Fable); (2) người vận hành nghiệm thu Windows Local.

## 1. Trạng thái

| | |
|---|---|
| Nhánh làm việc | `feature/legal-document-normalization` (đồng bộ với `claude/sweet-feynman-92jg8j`) |
| PR | #50 — **Draft**, không merge |
| Nhánh mặc định | `claude/practical-wozniak-9s1t6z` — không đụng; không tạo `main`; không đổi tag cũ |
| Nhánh audit | `review/phase12-fable-audit` — **không thay đổi** (nội dung được merge vào nhánh feature bằng `d28bca8`) |
| HEAD đã audit ở 12D2 | `2ef007417eaca0ce41e7aba2e32a201fa243ebf1` |
| `VERSION` | `1.2.0` (không đổi) |
| Legal Normalization | mặc định **OFF**, cần hai công tắc (`OCR_LEGAL_NORMALIZATION_ENABLED` + lựa chọn quản trị) |
| Migration / dependency | không có migration (schema 33); `pyproject.toml`, `uv.lock`, `frontend/package*.json` không đổi |
| Production | **không bị đụng tới**; không kết nối; không dữ liệu / model / secret nào rời máy chủ |

## 2. Commit của Phase 12D3 (theo thứ tự)

| Commit | Nội dung | Finding |
|---|---|---|
| `d28bca8` | merge nhánh audit (báo cáo + test phản ví dụ) | — |
| `1d7513b` | oracle độc lập, oracle an toàn Docker, bỏ tham số hóa rỗng | T-01, T-02, T-03 |
| `a694300` | normalizer v1.1.0 | F-01, F-02, F-03, F-06, F-10, F-17 |
| `849f0d0` | bản ghi chuẩn hóa trên Source, nhãn trang Source, thoát marker lúc hiển thị | F-07, F-15, F-16, F-17, F-18 |
| `ea9a90d` | API chịu được `asset.extraction` không phải mapping | F-07 |
| `4bf5d91` | đếm token không chờ mạng khi offline | F-22 |
| `1bbc644` | công cụ offline định dạng 2 (build, attempt, drift/pin, an toàn, rollback) | F-04, F-05, F-08, F-09, F-11..F-14, F-20..F-27 |
| `caa73d7` | test đối kháng cho công cụ offline; gỡ 8 `xfail` còn lại | các finding trên, T-02, T-03 |
| `f7d19b9` | inventory kiểm checksum bảng mã token | F-22 |
| `e8f0885` | benchmark trên ground truth khai báo; test bố cục biên | T-01, T-03 |
| `830e13b` | định dạng + một chú thích kiểu (không đổi hành vi) | — |
| `e84d854` | báo cáo 12D3, tài liệu triển khai, quyết định D-36 / D-37 | — |
| `7c23329` | lỗi tự phát hiện khi rà lại công cụ offline: (1) mốc đối chiếu theo từng lần tạo lại container thay cho mốc đầu attempt (tránh báo lỗi sai sau nghiệm thu / reboot); (2) không tiếp tục attempt đã đồng bộ mã nguồn; (3) `rollback interrupted` không khởi động lại ứng dụng khi chưa có gì được tạo lại; (4) cổng Legal đọc từ container đang chạy; (5) baseline được lấy trước khi lưu trữ journal cũ; (6) `STATE_DIR` riêng tư | F-08, F-09, F-21, F-23 |
| (commit cuối) | báo cáo hồi quy, bàn giao | — |

Công cụ offline nằm trong **một** commit (`1bbc644`) thay vì bốn như gợi ý: file được cấu trúc lại toàn bộ nên không
tách theo nhóm được mà vẫn chạy được ở từng commit; mô tả commit chia theo bốn nhóm.

## 3. Đọc gì, theo thứ tự nào

1. [PHASE12D3_REMEDIATION_REPORT.md](PHASE12D3_REMEDIATION_REPORT.md) — bảng 29 finding, những gì không làm.
2. [PHASE12D3_FINDING_STATUS.json](PHASE12D3_FINDING_STATUS.json) — từng finding: before / after, mã, test, cổng Local.
3. [PHASE12D3_QUALITY_BENCHMARK.md](PHASE12D3_QUALITY_BENCHMARK.md) — số liệu BEFORE / AFTER với oracle đã sửa.
4. [PHASE12D3_REGRESSION_REPORT.md](PHASE12D3_REGRESSION_REPORT.md) — so tên test lỗi với v1.2.0 và Phase 12.
5. [PHASE12D3_OFFLINE_SAFETY_REPORT.md](PHASE12D3_OFFLINE_SAFETY_REPORT.md) — công cụ offline.
6. [PHASE12D3_WINDOWS_ACCEPTANCE_CHECKLIST.md](PHASE12D3_WINDOWS_ACCEPTANCE_CHECKLIST.md) — cổng Local.
7. Bằng chứng RED: `docs/review/phase12d3/` (4 file).

## 4. Chạy lại ở Cloud (không cần Docker)

Môi trường: `uv sync --extra docling` (Docling 2.129.0, docling-core 2.96.0), Tesseract có `vie`, `ssh-keygen`.

```bash
uv run pytest tests/review_phase12d2 -q -rxXs -p no:cacheprovider
```

```bash
uv run pytest tests/test_ocr_legal_normalizer.py tests/test_ocr_legal_pipeline.py tests/test_ocr_phase12_scripts.py tests/test_token_utils_offline.py -q -p no:cacheprovider
```

```bash
uv run pytest tests/test_offline_package.py -q -p no:cacheprovider
```

(khoảng 5 phút: Docker giả lập là một tiến trình Python cho mỗi lệnh)

```bash
uv run python scripts/ocr/phase12_benchmark.py --out /tmp/benchmark.json --repeats 3
```

Đo lại implementation trước remediation bằng cùng oracle:

```bash
git show 2ef0074:open_notebook/ocr/legal_normalizer.py > /tmp/legal_normalizer_v100.py
```

```bash
uv run python scripts/ocr/phase12_benchmark.py --out /tmp/benchmark.json --repeats 3 --before /tmp/legal_normalizer_v100.py
```

Frontend:

```bash
cd frontend && npm ci && npm run test && npx tsc --noEmit && npm run lint
```

Kết quả ghi nhận của phiên này: backend **2 424 passed / 13 failed / 65 skipped** (2 502 test, tại `7c23329`); 13 test lỗi trùng từng tên với v1.2.0 (10 lỗi nền + 3 `test_chunking` do proxy chặn host bảng mã tiktoken); 0 xfail; `tests/review_phase12d2` 32 / 32; frontend 437 / 437, `tsc` 0 lỗi, lint 0 lỗi. Chi tiết: [PHASE12D3_REGRESSION_REPORT.md](PHASE12D3_REGRESSION_REPORT.md).

## 5. Gợi ý cho review 12D4 — những chỗ nên tấn công

Tôi không tự chấm điểm mình; đây là những điểm tôi cho là yếu nhất hoặc dễ sai nhất:

1. **Oracle mới có thật sự độc lập không.** `scripts/ocr/phase12_metrics.py::preservation` so từng dòng hiển thị với
   danh sách đơn vị khai báo trong fixture. Ground truth do chính tôi khai báo (`gt` trong
   `tests/fixtures/legal/legal_fixtures.py`): fixture sai thì oracle sai. Đáng kiểm: 16 fixture mới (f25–f40) có phản
   ánh đúng văn bản pháp lý thật không; `expect_removed` / `expect_joined` có bị tôi nới theo implementation không
   (f02, f03 đã đổi kỳ vọng từ "nối" sang "không nối" — chủ ý, do quy tắc ≥ 3 trang).
2. **Fixture do tôi chỉnh để tránh hành vi upstream của Docling**: f38 (đoạn kết thúc bằng "và" để Docling không tự
   nối qua cột), f35 (tiêu đề cột viết hoa), f19 (phần đầu là `list_item`). Các hành vi upstream đó vẫn tồn tại ở
   Standard và chưa được đánh giá trên tài liệu thật.
3. **Ngưỡng của normalizer là hằng số tôi chọn** (3 trang, 60%, 5% bề rộng, 85% cột, 4% diện tích). Chúng được thử
   quanh biên bằng tài liệu tổng hợp, chưa hề được hiệu chỉnh trên scan thật.
4. **Hệ quả của việc bảo thủ**: 24/47 artifact và 3/5 phép nối trên bộ fixture. Có thể với tài liệu thật, Legal gần
   như không khác Standard ở phần số trang/nối đoạn (nếu Heron gắn nhãn TEXT cho header). Đây là câu hỏi về giá trị
   của tính năng, không phải về an toàn.
5. **Docker giả lập là mô hình do tôi viết** — nó có thể sai theo cùng cách với công cụ. Đặc biệt: gộp override của
   Compose, tên image của dịch vụ `build:`, `RootFS.Layers` so với `diff_ids`, bố cục thật của `docker save` trên
   containerd image store, `NetworkSettings.Ports` khi container không publish cổng.
6. **Ghim image** (`pin`) là phần mới nhất và ít được kiểm chứng nhất; `deploy_image_ref` từ chối khi không chắc,
   nhưng trường hợp "chắc mà sai" chỉ lộ ra trên Compose thật.
7. **Các lỗi tôi tự tìm thấy ở lượt rà cuối** (đã sửa, xem bảng commit) cho thấy máy trạng thái vẫn có thể còn trường
   hợp biên chưa nghĩ tới — đặc biệt các chuỗi sự kiện kéo dài nhiều ngày (reboot, dữ liệu mới, đổi `.env`) giữa hai
   lệnh.
8. **`start_attempt` với trạng thái `failed`**: quyết định "attempt mới" dựa trên việc container đang chạy image
   baseline — nếu ai đó tự tay đưa container về image cũ theo cách khác, attempt mới vẫn được mở (có backup mới).
9. **F-07 chưa chạy trên SurrealDB thật**: tôi dựa vào định nghĩa `DEFINE FIELD asset ON source FLEXIBLE TYPE
   option<object>` trong migration 1 và test ở tầng model.
10. **Kiểm thử frontend** dùng jsdom; định dạng phân cấp chưa được nhìn trên trình duyệt thật.
11. **Bảng trong ảnh**: Legal giữ nội dung bảng nhưng vẫn sinh cảnh báo `picture_without_text` (cảnh báo thừa, không
    mất nội dung).
12. **Python 3.8 / 3.10** (Ubuntu 20.04 / 22.04) không có ở Cloud: công cụ offline chỉ được kiểm ngữ pháp ở mức 3.8
    và chạy trên 3.11–3.13.

## 6. Cổng còn mở (chưa có mục nào đạt)

| Cổng | Điều kiện đóng |
|---|---|
| Review độc lập 12D4 | Fable xác nhận từng finding; không tự đóng |
| REAL DOCKER BUILD | W-OFF-01..09 |
| REAL OCR PIPELINE | W-RC, W-LEG trên scan thật (gồm OCR trực tiếp bằng Agri) |
| OFFLINE UPGRADE AND ROLLBACK | W-OFF-10..27, W-OFF-29..31 trên stack cô lập, mạng bị chặn thật |
| SurrealDB thật cho bản ghi chuẩn hóa | W-LEG-16, W-STD-06 |
| Khóa ký phát hành | chưa có; không gói nào được coi là xác thực bằng chữ ký |
| Phát hành RC / merge / production | chỉ sau tất cả các cổng trên **và** phê duyệt của chủ dự án |

## 7. Không được làm khi tiếp nhận

Không merge PR #50; không phát hành RC; không triển khai production; không force-push; không sửa nhánh audit; không
đổi tag cũ; không tạo `main`; không bật `CB5400_PUBLISH_IMAGES`; không tạo GitHub Release; không push image; không
đưa PDF nghiệp vụ, model Agri, secret, khóa ký lên Cloud hay vào Git; không nâng dependency; không đổi `VERSION`.
