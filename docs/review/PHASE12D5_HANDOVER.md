# Phase 12D5 — Bàn giao (sửa có trọng tâm và đơn giản hóa)

## 1. Trạng thái

| | |
|---|---|
| Nhánh làm việc | `claude/jolly-pasteur-youiae`, đẩy nhanh (fast-forward) lên `feature/legal-document-normalization` |
| Gốc | v1.2.0 `f2fdf27`; feature trước 12D5 `8d0c438`; review 12D4 `review/phase12d4-fable-reaudit` `2a26ce1` (không đổi) |
| PR #50 | Draft; mô tả được viết lại (bỏ kết luận lạc quan cũ); không approve, không merge |
| `VERSION` / tag / release | 1.2.0 / không tạo / không tạo |
| Nhánh mặc định, nhánh audit cũ | không đổi |
| Production | không kết nối, không thay đổi |
| Không đổi | OCR engine, model Agri, Docling, Layout Heron, TableFormer, dependency, schema database, LLM, embedding, kiến trúc RAG; không LLM sửa chữ; không OCR lại; không re-embed; Legal mặc định OFF; Standard giữ hành vi v1.2.0 |

**Tính độc lập:** 12D5 làm trong một phiên khác 12D3 / 12D4, nhưng vẫn là phía sửa lỗi tự kiểm. Phần công cụ
offline do một tác nhân con thực hiện theo bản thiết kế ràng buộc của lead; lead rà lại sau khi gộp và sửa thêm 5
điểm (§3). Review độc lập phải làm ở phiên khác.

## 2. Thứ tự commit (từ `8d0c438`)

| Commit | Nhóm |
|---|---|
| `bc7236e` | nhập nguyên trạng tài liệu + test của 12D4 |
| `2c79f37` | **Oracle**: oracle theo định danh, 47 fixture `d5_*`, benchmark ĐỎ trên `8d0c438` (R2-14, T-01, T-03) |
| `3526e44`, `5aa4684` | **Legal preservation**: normalizer 1.2.0 (F-02, F-03, R2-01, R2-11, F-06, F-17, R2-02, R2-03); bằng chứng nối không bao giờ làm hỏng chuyển đổi |
| `bb8b513` | **Tokenizer** (F-22, R2-10 phía ứng dụng) |
| `b30a6ec` | test: TESSDATA_PREFIX (R2-21) |
| `facea2f` | **Package trust** (R2-07, R2-06, R2-08, R2-09, R2-18, R2-19) |
| `84a25fb` | **Offline transactions + deployment contract** (R2-12, R2-05, R2-04/F-08, R2-13, R2-15, R2-17, R2-20, F-11, R2-16) — một commit vì R2-12 chính là hợp đồng tag triển khai |
| `021ce49` | R2-10 phía công cụ, model băm SHA-256 (F-22) |
| `e651522` | diễn tập Docker thật của bộ tự động |
| `aec0320` | R2-22 (`build-package.ps1`) |
| `9bf4b99` | R2-04: backup của đơn vị gắn với lúc dừng ghi; bộ giả lập trả ID container thật |
| `ae05179` | F-26 phần còn lại; mọi gói mang quy trình thủ công |
| `482a5d6` | mypy: không lỗi mới (81, baseline 82) |
| `6edd7b6` | **Deployment integration**: hợp đồng tích hợp, quy trình thủ công, diễn tập thủ công trên Docker thật, tài liệu triển khai cập nhật |
| (commit cuối) | **Regression and documentation**: 6 tài liệu PHASE12D5 + FINDING_STATUS |

Commit trung gian của nhóm offline chỉ kiểm import + ruff (ghi trong thân commit); bộ test đầy đủ đạt ở đầu nhánh.

## 3. Lead rà sau khi gộp — 5 sửa thêm

1. **R2-04**: `--backup-reference` đưa vào cùng lần chạy vừa dừng ghi là bản backup làm TRƯỚC khi dừng ghi ⇒ giao
   thức hai lần chạy (yêu cầu backup → mã mới chỉ được nhận khi dữ liệu và container bảo trì không đổi).
2. **Độ trung thực của Docker giả lập**: `compose ps -q` trả khóa cố định, nên logic "vẫn là container bảo trì" chưa
   từng được kiểm; giờ trả ID đổi theo mỗi lần tạo lại.
3. **F-26** (agent để PARTIAL): thư mục cha của cấu hình / allowed_signers; file compose và override bảo trì; gói
   luôn mang quy trình thủ công.
4. **R2-01** (trước khi gộp): đọc bằng chứng nối của Docling nằm ngoài `normalize_or_fallback` ⇒ một lỗi ở đó làm
   hỏng cả chuyển đổi thay vì quay về Standard.
5. mypy: 14 lỗi mới trong công cụ / oracle và 8 trong test ⇒ sửa (không đổi hành vi).

## 4. Sản phẩm

| File | Nội dung |
|---|---|
| [PHASE12D5_FINDING_STATUS.json](PHASE12D5_FINDING_STATUS.json) | 51 finding: trạng thái 12D4 → 12D5, thay đổi, test (mọi tên test được kiểm là có thật), cổng Local |
| [PHASE12D5_REGRESSION_REPORT.md](PHASE12D5_REGRESSION_REPORT.md) | Kết quả mọi bộ test, so với baseline |
| [PHASE12D5_QUALITY_BENCHMARK.md](PHASE12D5_QUALITY_BENCHMARK.md) | Oracle độc lập, đột biến, benchmark 92 fixture |
| [PHASE12D5_OFFLINE_SAFETY_REPORT.md](PHASE12D5_OFFLINE_SAFETY_REPORT.md) | Công cụ offline, đánh giá độ phức tạp, Docker thật, rủi ro còn lại |
| [PHASE12D5_LOCAL_ACCEPTANCE_CHECKLIST.md](PHASE12D5_LOCAL_ACCEPTANCE_CHECKLIST.md) | Nghiệm thu Local: W-TOK, W-PS, W-INT, W-FB + kỳ vọng mới của mục 12D4 |
| [../deployment/OFFLINE_UPDATE_INTEGRATION_CONTRACT.md](../deployment/OFFLINE_UPDATE_INTEGRATION_CONTRACT.md) | Hợp đồng tích hợp triển khai (C1–C9, adapter cho script vận hành) |
| [../deployment/OFFLINE_UPDATE_MANUAL_FALLBACK.md](../deployment/OFFLINE_UPDATE_MANUAL_FALLBACK.md) | Quy trình cập nhật offline thủ công (đường production) |
| `docs/review/phase12d5/` | benchmark JSON (trước / sau), kết quả đột biến, 74 cặp test đỏ trên `8d0c438`, tỷ lệ token thật |

## 5. Chạy lại

```bash
uv run pytest tests/ -q -p no:cacheprovider
```

```bash
uv run pytest tests/review_phase12d4 tests/review_phase12d2 -q -rxX -p no:cacheprovider
```

Kỳ vọng: 0 xfail, 0 xpass trong hai thư mục review (mọi xfail strict của 12D4 đã gỡ; 32 test evidence đảo thành
test hồi quy, có dòng `# was:`). Docker thật: `CB5400_REAL_DOCKER=1 uv run pytest tests/test_offline_real_docker.py
tests/test_offline_manual_fallback_real_docker.py -q`. Bảng mã thật: đặt `CB5400_TIKTOKEN_CACHE_DIR` trỏ tới thư
mục chứa file `fb374d41…` có SHA-256 `446a9538…`.

## 6. Việc người review độc lập nên soi kỹ

- `scripts/offline/offline_package.py` (~5 200 dòng): thứ tự ghi `approved.json` / journal trong `finish`; trạng thái
  `FINISH_FAILED` (container mới chạy ở chế độ thường cho tới khi rollback); giao thức hai lần chạy của backup.
- Oracle (`scripts/ocr/phase12_oracle.py`): quy tắc gán định danh khi nhiều dòng giống hệt nhau.
- Normalizer 1.2.0: `_pair_refusal`, tách lại phép nối của Docling theo charspan.
- Đường online của tokenizer giữ ước lượng v1.2.0 (có chủ ý, xem R2-10 trong FINDING_STATUS).

## 7. Kết luận

```
PHASE 12D5: COMPLETED
FINDINGS REVIEWED: 51/51
P0 OPEN: 0
P1 OPEN: 0
CODE RELEASE BLOCKERS: 0
LOCAL RELEASE BLOCKERS: 27
LEGAL CONTENT PRESERVATION: PARTIAL
INDEPENDENT ORACLE: PASS
OFFLINE UPDATE SAFETY: PARTIAL
SIMPLIFIED OFFLINE FALLBACK: IMPLEMENTED
AUTOMATIC OFFLINE UPDATER: EXPERIMENTAL
READY FOR INDEPENDENT REVIEW: YES
READY FOR WINDOWS LOCAL ACCEPTANCE: CONDITIONAL
READY FOR RELEASE: NO
READY FOR PRODUCTION: NO
PRODUCTION UNCHANGED
```

- LEGAL CONTENT PRESERVATION **PARTIAL**: 0 xóa / nối / chèn / đổi chữ / mất placeholder trên 92 fixture tổng hợp,
  nhưng chưa có bằng chứng trên scan thật, và thứ tự đọc sai của Docling (3 fixture, giống Standard) không được cảnh
  báo lúc chạy.
- INDEPENDENT ORACLE **PASS**: chân lý khai báo trước, gán theo định danh, đột biến 10 lớp phát hiện 100 %.
- OFFLINE UPDATE SAFETY **PARTIAL**: sửa và kiểm ở Cloud (giả lập + Docker thật với image thay thế); môi trường
  thật chưa chứng minh.
- READY FOR WINDOWS LOCAL ACCEPTANCE **CONDITIONAL**: sau review độc lập của 12D5; chạy theo checklist 12D5.
