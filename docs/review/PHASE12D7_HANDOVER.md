# Phase 12D7 — Bàn giao (sửa lỗi runtime cuối sau nghiệm thu Windows)

## 1. Trạng thái

| | |
|---|---|
| Nhánh làm việc | `claude/jolly-pasteur-youiae`, đẩy nhanh (fast-forward) lên `feature/legal-document-normalization` |
| Gốc | v1.2.0 `f2fdf27`; ứng viên 12D5 `904c15c` (giữ để so sánh) |
| PR #50 | Draft; không approve, không merge |
| `VERSION` / tag / release | 1.2.0 / không tạo / không tạo |
| Production | không kết nối, không thay đổi |
| Không đổi | RapidOCR, EasyOCR, PDF Prep, Auto Full Page on Watermark, Layout Heron, TableFormer, model Agri / traineddata, schema database, dependency (không thêm gói), ngưỡng hướng xoay 2.0, state machine của updater tự động (vẫn EXPERIMENTAL) |
| Đầu vào | Kết quả Windows 12E0 / 12E1 (22 PDF thật, 71 trang, Agri v1 / v2, Tesseract Best) do chủ dự án tóm tắt; **báo cáo 12E1 đã làm sạch không có trong repo** ⇒ E1-01, E1-02, E1-06 và P3 / P4 khác: EVIDENCE REQUIRED |

**Tính độc lập:** phía sửa lỗi tự kiểm, cùng phiên với 12D5. Review độc lập phải làm ở phiên khác; xác minh trên
Windows phải làm trên máy Windows. Cloud không có Windows, PowerShell, model layout của Docling, tài liệu thật.

## 2. Thứ tự commit (từ `904c15c`)

| Commit | Nhóm | Finding |
|---|---|---|
| `70a0339` | 1 — **Tesseract TSV preservation**: bản vá có kiểm soát Docling 2.129.0, gói offline NOT_READY khi không áp được | E0-07 |
| `02d2907` | 2 — **Conservative Legal cross-page behavior**: normalizer 1.3.0, không nối qua trang, tách phép nối của Docling khi có bằng chứng, UI | E1-09 |
| `f6ec492` | 3 — **OCR orientation diagnostics**: cổng hướng xoay chạy được trong image build từ Windows, trạng thái cổng, công cụ chẩn đoán từng vùng | E1-05 |
| `4622376` | 4 — **Cross-platform build lock** (+ gói cũ giữ cặp hash, `.partial-*` dọn, đầu ra LF) | E1-04 |
| `edc6d9c` | 5 — **PowerShell invocation**: `-ComposeArgs @(...)`, hành động `orientation` | E0-05 |
| `dde8645` | 3 (bổ sung) — chế độ `--crops` của công cụ hướng xoay chuẩn bị tessdata như ingestion | E1-05 |
| `2938100` | 6 — **Regression tests**: E1-03, Standard parity trên stage OCR thật | E1-03, §9 |
| `ef7daa7` | 7 — **Documentation**: tài liệu PHASE12D7 + D-38 / D-39 / D-40, release notes, hướng dẫn Windows | |
| `c4ed2b3` | mypy: không lỗi mới (81, như 12D5) — sửa kiểu trong file mới, không đổi hành vi | |
| (commit cuối) | 7 (tiếp) — báo cáo hồi quy với số liệu cuối; trạng thái finding theo commit mã cuối | |

## 3. Tóm tắt từng finding

| Finding | Nguyên nhân | Sửa | Kiểm ở Cloud | Còn phải kiểm |
|---|---|---|---|---|
| **E0-07** (P1) | `pd.read_csv` suy diễn kiểu trong `_run_tesseract` | `docling_patches.py`: cột `text` là chuỗi; chặn phiên bản + SHA-256 | TSV thô = ô OCR; Tesseract thật; stage OCR thật (FULL_PAGE, LAYOUT_REGIONS) | 22 PDF, Agri v1/v2, Best (W-12D7-02) |
| **E1-09** (P1) | phép nối của Docling (B) không được hoàn tác; Legal cũng tự nối (A) | 1.3.0: không A; B tách khi charspan khớp | 92 fixture: 0 xóa / nối sai / chèn, 0/8 phép nối, không mất nội dung mới | phản ví dụ scan thật (W-12D7-03b) |
| **E1-04** (P1) | `import fcntl` | `exclusive_lock`: flock / msvcrt | tiến trình thật trên Linux (nhánh flock) | PS 5.1, PS 7, Python Windows (W-12D7-04) |
| **E1-03** | E0-07 (không phải Legal) | không đổi Legal | chuỗi TSV → ô OCR → Legal | 22 PDF (W-12D7-03a) |
| **E1-05** | khả dĩ nhất: cổng CRLF trong image build từ checkout Windows ⇒ Tesseract chạy không cổng | `.gitattributes`, Dockerfile chuẩn hóa + tự kiểm, trạng thái cổng, công cụ | tái hiện cơ chế; OSD sai ≥ 2.0 không tái hiện được trên vùng tổng hợp | xác nhận nguyên nhân + 11 cụm (W-12D7-01) |
| **E0-05** | `ValueFromRemainingArguments` ⇒ `-d` thành `-Debug` | mảng tường minh | kiểm cấu trúc script | PS 5.1, PS 7 (W-12D7-05) |
| E1-01, E1-02, E1-06, P3/P4 | — | không đổi | — | cần báo cáo 12E1 đã làm sạch |

## 4. Sản phẩm

| File | Nội dung |
|---|---|
| [PHASE12D7_FINDING_STATUS.json](PHASE12D7_FINDING_STATUS.json) | mọi finding: nguyên nhân, trạng thái, thay đổi, test (tên test được kiểm là có thật), mục kiểm Windows |
| [PHASE12D7_E0_07_DOCLING_PATCH.md](PHASE12D7_E0_07_DOCLING_PATCH.md) | bản vá Docling: nguyên nhân, thiết kế, chốt chặn, phạm vi, kết quả, nâng cấp, rollback |
| [PHASE12D7_LEGAL_SAFETY_REPORT.md](PHASE12D7_LEGAL_SAFETY_REPORT.md) | E1-09 (A / B), benchmark 1.3.0, E1-03 |
| [PHASE12D7_WINDOWS_BUILD_REPORT.md](PHASE12D7_WINDOWS_BUILD_REPORT.md) | E1-04, E0-05, cổng hướng xoay phía build, gói offline |
| [PHASE12D7_REGRESSION_REPORT.md](PHASE12D7_REGRESSION_REPORT.md) | mọi bộ test so với baseline 12D5 |
| [PHASE12D7_LOCAL_ACCEPTANCE_CHECKLIST.md](PHASE12D7_LOCAL_ACCEPTANCE_CHECKLIST.md) | danh sách kiểm lại trên Windows (W-12D7-*) |
| `phase12d7/benchmark_legal_1_3_0.json` | benchmark Legal 1.3.0 (92 fixture) |
| `phase12d7/standard_diff_synthetic/` | báo cáo Standard expected-diff trên stage OCR thật (tổng hợp) |
| [../ocr/DECISIONS.md](../ocr/DECISIONS.md) | D-38 (Legal không nối qua trang), D-39 (bản vá Docling), D-40 (cổng hướng xoay trong image Windows) |

## 5. Hướng dẫn cho Windows retest

[PHASE12D7_LOCAL_ACCEPTANCE_CHECKLIST.md](PHASE12D7_LOCAL_ACCEPTANCE_CHECKLIST.md). Trước hết: giữ image v1.2.0 và
`904c15c`, ghi `git ls-files --eol` của file cổng, **build lại image** (Dockerfile đổi), `status` phải in
`orientation gate: active`. Không xóa image hay volume; không upload tài liệu, kết quả OCR hay model Agri.

## 6. Kết luận

Hồi quy: backend **3047 passed / 10 failed (cùng tên với 12D5) / 73 skipped / 3 deselected**; bảng mã thật 17/17 và
110/110; offline + review 12D2 / 12D4 409/409; Docker thật 3/3; test mới 125/125; frontend 438/438, `tsc` sạch, lint
0 lỗi; `mypy` 81 (không lỗi mới); benchmark tái lập giống hệt. Chi tiết: [PHASE12D7_REGRESSION_REPORT.md](PHASE12D7_REGRESSION_REPORT.md).

```
PHASE 12D7: COMPLETED
E0-07 TSV PRESERVATION: VERIFIED
E1-04 CROSS-PLATFORM BUILD LOCK: LOCAL VERIFICATION REQUIRED
E1-09 UNSAFE LEGAL JOIN: FIXED
E1-03 NUMERIC PRESERVATION: PARTIAL
E1-05 ORIENTATION: NEEDS LOCAL EVIDENCE
STANDARD EXPECTED-DIFF PARITY: PARTIAL
LEGAL CONTENT PRESERVATION: PASS ON SYNTHETIC
OFFLINE PACKAGE: NOT VERIFIED ON WINDOWS
READY FOR INDEPENDENT REVIEW: YES
READY FOR WINDOWS RETEST: YES
READY FOR RELEASE: NO
READY FOR PRODUCTION: NO
PRODUCTION UNCHANGED
```

E0-07 VERIFIED = TSV thô bằng chữ của ô OCR Docling, kiểm ở Cloud; ingestion của 22 PDF thật vẫn là mục W-12D7-02.
E1-09 FIXED và LEGAL CONTENT PRESERVATION dựa trên fixture tổng hợp; phản ví dụ scan thật: W-12D7-03b. Không phát hành,
không merge, không triển khai production. Dừng ở đây để review độc lập và Windows retest.
