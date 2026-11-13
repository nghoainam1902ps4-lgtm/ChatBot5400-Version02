# Benchmark chất lượng OCR trước/sau Phase 8C

Cập nhật: 2026-11-13 · Máy nghiệm thu: Ubuntu, 8 CPU, 30 GB RAM, không GPU · Baseline: `f172645`

Bổ sung cho [OCR_BENCHMARK.md](OCR_BENCHMARK.md) (benchmark tốc độ và OCR-stage của Phase 7/8B).
Tài liệu này chỉ so sánh **chất lượng full pipeline** trước và sau các thay đổi của Phase 8C
([OCR_QUALITY_OPTIMIZATION.md](OCR_QUALITY_OPTIMIZATION.md)).

## 1. Phương pháp

- Công cụ: `scripts/ocr/quality_eval.py` — chạy đúng điểm vào production (`convert_document`: Docling +
  Layout Heron + TableFormer accurate + engine đã chọn) và đo CER, WER, word recall, độ chính xác dấu,
  recall số tiền / ngày / số hiệu, hình dạng bảng, số dòng bảng khớp đủ nhãn và ô, thời gian, peak RSS.
- "Trước" = git worktree của commit cuối Phase 8B, cùng môi trường Python, cùng model.
- Hai tập dữ liệu, đều tổng hợp, không có tài liệu thật:
  - **7 fixture nghiệm thu** (`tests/fixtures/ocr`) — tập đã dùng để phân tích và tinh chỉnh.
  - **Holdout 13 tài liệu** (`scripts/ocr/generate_holdout_fixtures.py`) — nội dung khác (thông báo,
    báo cáo thu chi), font serif (Liberation Serif, Noto Serif), bảng 8×4 không ô gộp, số tiền khác,
    khổ A4 / A5 / Letter ngang, 150 / 200 / 300 DPI, bản photocopy kém (nghiêng 0,6°, nhòe, nền xám,
    nhiễu, JPEG 40), trang xoay 90° / 180° / 270°, một file 3 trang có hướng khác nhau.
    Holdout được sinh **sau khi** cấu hình đã chốt và chỉ chạy **một lần**; không có vòng tinh chỉnh
    nào dựa trên kết quả holdout.
- Thời gian đo khi có tác vụ khác chạy song song ở một số lượt, nên chỉ dùng để so sánh tương đối.

## 2. Kết quả tổng hợp


### 7 fixture nghiệm thu (Phase 8B → 8C) — trung bình

| Engine | CER | Word recall | Trường khóa (số tiền+ngày+số hiệu) | Dòng bảng đúng | Tổng giây |
|---|---|---|---|---|---|
| tesseract_best | 0.274 → 0.042 | 0.68 → 0.96 | 0.62 → 1.00 | 8/16 → 16/16 | 49 → 37 |
| tesseract_fast | 0.289 → 0.044 | 0.66 → 0.98 | 0.58 → 1.00 | 7/16 → 14/16 | 48 → 35 |
| rapidocr | 0.178 → 0.118 | 0.61 → 0.63 | 0.84 → 0.89 | 4/16 → 4/16 | 80 → 71 |
| easyocr | 0.472 → 0.168 | 0.50 → 0.66 | 0.54 → 0.63 | 6/16 → 6/16 | 62 → 66 |

### Holdout 13 tài liệu (Phase 8B → 8C) — trung bình

| Engine | CER | Word recall | Trường khóa (số tiền+ngày+số hiệu) | Dòng bảng đúng | Tổng giây |
|---|---|---|---|---|---|
| tesseract_best | 0.394 → 0.023 | 0.67 → 0.97 | 0.63 → 1.00 | 3/42 → 38/42 | 66 → 80 |
| tesseract_fast | 0.392 → 0.026 | 0.67 → 0.96 | 0.62 → 1.00 | 3/42 → 41/42 | 63 → 74 |
| rapidocr | 0.355 → 0.098 | 0.53 → 0.55 | 0.95 → 1.00 | 0/42 → 0/42 | 123 → 135 |
| easyocr | 0.639 → 0.198 | 0.30 → 0.72 | 0.35 → 0.80 | 7/42 → 13/42 | 139 → 162 |

Đọc kết quả:

- **Tesseract Best / Fast:** trường khóa đạt 1,00 trên cả hai tập; dòng bảng đúng tăng từ 8/16 lên
  16/16 (Best, fixture) và từ 3/42 lên 38/42 (Best, holdout). Mức cải thiện trên holdout bằng hoặc lớn
  hơn trên tập tinh chỉnh → không phải overfitting.
- **RapidOCR:** thay đổi duy nhất là trang xoay được chuẩn hóa hướng; tài liệu đứng thẳng cho số đo y
  hệt. Model vẫn mất dấu tiếng Việt (word recall ~0,55–0,63) và không khớp được nhãn dòng bảng.
- **EasyOCR:** CER giảm mạnh nhờ ngưỡng 0,2 nhưng chất lượng vẫn thấp ở 150 DPI (trường khóa 0,63 /
  0,80); không đạt ngưỡng nghiệm thu.
- **Không có regression:** không tài liệu nào của engine nào xấu đi quá 0,02 CER, mất trường khóa,
  mất dòng bảng hay giảm word recall quá 0,03 (kiểm bằng script, `evidence/phase8c/`).

### 2.1. 48 bài nghiệm thu (không đổi ngưỡng, fixture, ground truth)

| Engine | Phase 8B | Phase 8C | Bài còn FAIL |
|---|---|---|---|
| RapidOCR | 7 / 8 | **8 / 8** | – |
| Tesseract Fast | 4 / 9 | 7 / 9 | `bang_gop_scan`, `nhieu_trang_scan` — tiêu đề `BANG KE` |
| Tesseract Best | 5 / 9 | 6 / 9 | `bang_gop_scan`, `nhieu_trang_scan`, `hon_hop` — tiêu đề `BANG KE` / `MAU` |
| EasyOCR | 4 / 9 | 4 / 9 | 5 fixture scan — đọc sai số và dấu ở 150 DPI |
| Bài chung (attribution text layer / OCR, …) | 13 / 13 | 13 / 13 | – |
| **Tổng** | **33 / 48** | **38 / 48** | 10 |

Tesseract Best có ít bài PASS hơn Fast dù số đo tốt hơn vì ngưỡng của Best chặt hơn (recall 1,0) và
cả ba bài đều rớt ở cùng một cụm tiêu đề (OCR_FAILURE_ANALYSIS §5.3).

## 3. Độ phân giải và scale (Tesseract)

Cùng nội dung fixture sinh lại ở 150 / 200 / 300 DPI **thật** (bản 150 DPI trùng từng pixel với
fixture đã commit). Số dòng bảng khớp trên 12, có ngưỡng OSD, chưa có chuẩn hóa hướng trang
(`evidence/phase8c/experiments-session1/dpi2/`):

| Ảnh scan | scale 2,08 (150 DPI) | scale 2,78 (200 DPI) | scale 3,0 (216 DPI) | scale 4,17 (300 DPI) |
|---|---|---|---|---|
| 150 DPI – Best | **10** | 7 | 9 | 6 |
| 150 DPI – Fast | 6 | 7 | **9** | 4 |
| 200 DPI – Best | **12** | 10 | 2 | 4 |
| 200 DPI – Fast | **12** | 11 | 2 | 8 |
| 300 DPI – Best | 3 | 4 | **11** | 9 |
| 300 DPI – Fast | 4 | 4 | **7** | 6 |

- Phóng ảnh (scale lớn hơn độ phân giải scan) không khôi phục chi tiết; thường làm kém đi.
- Quy tắc đã triển khai — `scale = DPI_scan / 72`, tối thiểu 2,0, không vượt 3,0 — chọn đúng hoặc sát
  cột tốt nhất ở cả ba độ phân giải cho Best. Với Fast ở 150 DPI, scale 3 cho nhiều dòng bảng hơn ở
  lượt đo này; số đo cuối cùng (có đủ 4 thay đổi) của Fast là 14/16 trên fixture và 41/42 trên holdout.
- Kết quả từng ô dao động theo bbox layout; nên đọc theo xu hướng, không theo từng số.

## 4. Hiệu năng và bộ nhớ

| Engine | Fixture: tổng giây (7 file) | Holdout: tổng giây (13 file) | Peak RSS fixture (MB) | Peak RSS holdout (MB) |
|---|---|---|---|---|
| tesseract_best | 49 → 37 | 66 → 80 | 3152 → 3412 | 4192 → 4626 |
| tesseract_fast | 48 → 35 | 63 → 74 | 3021 → 3415 | 4337 → 4510 |
| rapidocr | 80 → 71 | 123 → 135 | 3800 → 4607 | 5759 → 6118 |
| easyocr | 62 → 66 | 139 → 162 | 4031 → 4366 | 5821 → 6197 |

- Bước dò hướng trang tốn khoảng **1 giây mỗi trang scan** (render + `tesseract --psm 0`); trang có
  text layer không tốn gì. Giới hạn 200 trang đầu mỗi tài liệu (`OCR_PAGE_OSD_MAX_PAGES`), 30 giây mỗi
  trang.
- Trên fixture 150 DPI, Tesseract nhanh hơn trước vì render ở scale 2,08 thay cho 3,0 (ít điểm ảnh
  hơn 2 lần). Trên holdout (đa số 200 DPI) tổng thời gian tăng 15–20 %.
- Peak RSS tăng 200–800 MB trong tiến trình đo (một tiến trình xử lý liên tiếp nhiều tài liệu). Mức
  tuyệt đối 3,4–6,2 GB vẫn do Docling + torch quyết định.
- EasyOCR chậm hơn một chút vì giữ lại nhiều dòng hơn cho các bước sau.

## 5. Chi tiết từng tài liệu

Mỗi ô: *trước → sau*. "Dấu" = độ chính xác dấu tiếng Việt; "Dòng bảng" = số dòng khớp đủ nhãn và ô.

### 7 fixture nghiệm thu (Phase 8B → 8C)


**tesseract_best** — peak RSS 3152 → 3412 MB

| Tài liệu | CER | WER | Word recall | Dấu | Số tiền | Ngày | Số hiệu | Dòng bảng | Giây |
|---|---|---|---|---|---|---|---|---|---|
| bang_gop_scan | 0.685 → 0.097 | 0.979 → 0.208 | 0.10 → 0.88 | 0.75 → 0.92 | 0.00 → 1.00 | 0.00 → 1.00 | – → – | 0/4 → 4/4 | 9.8 → 6.4 |
| bang_gop_text | 0.093 → 0.093 | 0.125 → 0.125 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – → – | 4/4 → 4/4 | 7.1 → 4.6 |
| hon_hop | 0.053 → 0.057 | 0.088 → 0.110 | 0.96 → 0.93 | 0.97 → 0.93 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 4/4 → 4/4 | 9.6 → 6.8 |
| nhieu_trang_scan | 0.259 → 0.037 | 0.331 → 0.080 | 0.71 → 0.95 | 0.93 → 0.94 | 0.11 → 1.00 | 0.43 → 1.00 | 1.00 → 1.00 | 0/4 → 4/4 | 8.5 → 8.2 |
| vb_scan | 0.004 → 0.004 | 0.019 → 0.019 | 0.98 → 0.98 | 0.98 → 0.98 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 4.5 → 4.4 |
| vb_text | 0.000 → 0.000 | 0.000 → 0.000 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 2.9 → 2.3 |
| vb_xoay_scan | 0.824 → 0.004 | 0.990 → 0.019 | 0.02 → 0.98 | 0.00 → 0.98 | 0.00 → 1.00 | 0.00 → 1.00 | 0.00 → 1.00 | – | 6.3 → 4.3 |

**tesseract_fast** — peak RSS 3021 → 3415 MB

| Tài liệu | CER | WER | Word recall | Dấu | Số tiền | Ngày | Số hiệu | Dòng bảng | Giây |
|---|---|---|---|---|---|---|---|---|---|
| bang_gop_scan | 0.710 → 0.107 | 1.083 → 0.208 | 0.10 → 0.92 | 0.75 → 0.88 | 0.00 → 1.00 | 0.00 → 1.00 | – → – | 0/4 → 3/4 | 7.5 → 6.2 |
| bang_gop_text | 0.093 → 0.093 | 0.125 → 0.125 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – → – | 4/4 → 4/4 | 6.9 → 4.5 |
| hon_hop | 0.121 → 0.055 | 0.209 → 0.066 | 0.85 → 1.00 | 0.97 → 1.00 | 0.88 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 3/4 → 4/4 | 8.3 → 6.5 |
| nhieu_trang_scan | 0.261 → 0.041 | 0.364 → 0.080 | 0.70 → 0.96 | 0.92 → 0.95 | 0.11 → 1.00 | 0.43 → 1.00 | 0.50 → 1.00 | 0/4 → 3/4 | 11.5 → 7.5 |
| vb_scan | 0.008 → 0.004 | 0.029 → 0.019 | 0.97 → 0.98 | 0.96 → 0.98 | 1.00 → 1.00 | 1.00 → 1.00 | 0.50 → 1.00 | – | 5.7 → 4.3 |
| vb_text | 0.000 → 0.000 | 0.000 → 0.000 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 2.5 → 2.2 |
| vb_xoay_scan | 0.830 → 0.004 | 1.000 → 0.019 | 0.02 → 0.98 | 0.00 → 0.98 | 0.00 → 1.00 | 0.00 → 1.00 | 0.00 → 1.00 | – | 5.3 → 4.1 |

**rapidocr** — peak RSS 3800 → 4607 MB

| Tài liệu | CER | WER | Word recall | Dấu | Số tiền | Ngày | Số hiệu | Dòng bảng | Giây |
|---|---|---|---|---|---|---|---|---|---|
| bang_gop_scan | 0.204 → 0.204 | 0.667 → 0.667 | 0.48 → 0.48 | 0.18 → 0.18 | 1.00 → 1.00 | 1.00 → 1.00 | – → – | 0/4 → 0/4 | 20.0 → 15.2 |
| bang_gop_text | 0.093 → 0.093 | 0.125 → 0.125 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – → – | 4/4 → 4/4 | 13.6 → 8.4 |
| hon_hop | 0.096 → 0.096 | 0.308 → 0.308 | 0.76 → 0.76 | 0.92 → 0.92 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 0/4 → 0/4 | 16.5 → 15.1 |
| nhieu_trang_scan | 0.160 → 0.160 | 0.629 → 0.629 | 0.42 → 0.42 | 0.30 → 0.30 | 1.00 → 1.00 | 1.00 → 1.00 | 0.00 → 0.00 | 0/4 → 0/4 | 16.4 → 18.0 |
| vb_scan | 0.136 → 0.136 | 0.612 → 0.612 | 0.39 → 0.39 | 0.37 → 0.37 | 1.00 → 1.00 | 1.00 → 1.00 | 0.00 → 0.00 | – | 5.4 → 6.2 |
| vb_text | 0.000 → 0.000 | 0.000 → 0.000 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 2.6 → 2.5 |
| vb_xoay_scan | 0.558 → 0.136 | 0.835 → 0.621 | 0.22 → 0.38 | 0.43 → 0.38 | 1.00 → 1.00 | 0.33 → 1.00 | 0.00 → 0.00 | – | 5.1 → 5.9 |

**easyocr** — peak RSS 4031 → 4366 MB

| Tài liệu | CER | WER | Word recall | Dấu | Số tiền | Ngày | Số hiệu | Dòng bảng | Giây |
|---|---|---|---|---|---|---|---|---|---|
| bang_gop_scan | 0.591 → 0.330 | 0.729 → 0.833 | 0.29 → 0.40 | 0.33 → 0.26 | 0.00 → 0.00 | 1.00 → 1.00 | – → – | 0/4 → 0/4 | 9.9 → 10.7 |
| bang_gop_text | 0.093 → 0.093 | 0.125 → 0.125 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – → – | 4/4 → 4/4 | 7.8 → 7.9 |
| hon_hop | 0.087 → 0.087 | 0.143 → 0.143 | 0.97 → 0.97 | 0.97 → 0.97 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 2/4 → 2/4 | 10.4 → 11.2 |
| nhieu_trang_scan | 0.754 → 0.221 | 0.868 → 0.669 | 0.15 → 0.43 | 0.45 → 0.47 | 0.00 → 0.00 | 0.71 → 1.00 | 0.00 → 0.00 | 0/4 → 0/4 | 13.7 → 15.1 |
| vb_scan | 0.848 → 0.160 | 0.932 → 0.592 | 0.07 → 0.43 | 0.48 → 0.54 | 0.00 → 0.00 | 0.33 → 1.00 | 0.00 → 0.00 | – | 8.1 → 8.7 |
| vb_text | 0.000 → 0.000 | 0.000 → 0.000 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 3.9 → 4.1 |
| vb_xoay_scan | 0.933 → 0.288 | 1.000 → 0.621 | 0.00 → 0.43 | 0.00 → 0.54 | 0.00 → 0.00 | 0.00 → 0.33 | 0.00 → 0.00 | – | 8.3 → 8.6 |

### Holdout (Phase 8B → 8C)


**tesseract_best** — peak RSS 4192 → 4626 MB

| Tài liệu | CER | WER | Word recall | Dấu | Số tiền | Ngày | Số hiệu | Dòng bảng | Giây |
|---|---|---|---|---|---|---|---|---|---|
| ho_letter_150 | 0.003 → 0.003 | 0.015 → 0.015 | 0.98 → 0.98 | 0.99 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 4.5 → 5.3 |
| ho_letter_200 | 0.002 → 0.003 | 0.008 → 0.015 | 0.99 → 0.98 | 0.99 → 0.99 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 3.8 → 4.8 |
| ho_letter_a5_300 | 0.024 → 0.024 | 0.107 → 0.107 | 0.89 → 0.89 | 0.88 → 0.88 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 3.9 → 5.9 |
| ho_letter_lowq_150 | 0.026 → 0.006 | 0.076 → 0.030 | 0.95 → 0.97 | 0.97 → 0.97 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 4.0 → 5.0 |
| ho_letter_rot180_200 | 0.256 → 0.003 | 0.244 → 0.015 | 0.99 → 0.98 | 0.99 → 0.99 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 4.1 → 4.8 |
| ho_letter_rot270_200 | 0.746 → 0.003 | 0.901 → 0.015 | 0.99 → 0.98 | 0.99 → 0.99 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 3.9 → 4.8 |
| ho_letter_rot90_200 | 0.080 → 0.002 | 0.130 → 0.008 | 0.99 → 0.99 | 0.99 → 0.99 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 3.9 → 4.9 |
| ho_mixed_rot_200 | 0.272 → 0.003 | 0.286 → 0.012 | 0.81 → 0.99 | 0.99 → 0.99 | 0.11 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 0/7 → 7/7 | 10.3 → 12.6 |
| ho_table_150 | 0.598 → 0.154 | 0.733 → 0.283 | 0.33 → 0.92 | 0.80 → 0.88 | 0.25 → 1.00 | – → – | – → – | 2/7 → 4/7 | 5.8 → 6.2 |
| ho_table_200 | 0.526 → 0.033 | 0.533 → 0.067 | 0.47 → 0.97 | 1.00 → 1.00 | 0.25 → 1.00 | – → – | – → – | 1/7 → 7/7 | 5.2 → 6.2 |
| ho_table_landscape_200 | 0.758 → 0.052 | 0.883 → 0.100 | 0.12 → 0.97 | 1.00 → 0.97 | 0.00 → 1.00 | – → – | – → – | 0/7 → 6/7 | 6.2 → 6.4 |
| ho_table_rot180_200 | 0.935 → 0.003 | 1.000 → 0.017 | 0.00 → 0.98 | 0.00 → 1.00 | 0.00 → 1.00 | – → – | – → – | 0/7 → 7/7 | 5.5 → 6.2 |
| ho_table_rot270_200 | 0.892 → 0.010 | 0.950 → 0.033 | 0.15 → 0.97 | 1.00 → 1.00 | 0.25 → 1.00 | – → – | – → – | 0/7 → 7/7 | 5.2 → 7.2 |

**tesseract_fast** — peak RSS 4337 → 4510 MB

| Tài liệu | CER | WER | Word recall | Dấu | Số tiền | Ngày | Số hiệu | Dòng bảng | Giây |
|---|---|---|---|---|---|---|---|---|---|
| ho_letter_150 | 0.002 → 0.002 | 0.008 → 0.008 | 0.99 → 0.99 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 4.2 → 5.1 |
| ho_letter_200 | 0.003 → 0.006 | 0.015 → 0.030 | 0.98 → 0.97 | 0.98 → 0.96 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 3.6 → 4.4 |
| ho_letter_a5_300 | 0.036 → 0.036 | 0.145 → 0.145 | 0.85 → 0.85 | 0.90 → 0.90 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 3.6 → 4.5 |
| ho_letter_lowq_150 | 0.016 → 0.013 | 0.053 → 0.053 | 0.96 → 0.95 | 0.97 → 0.96 | 1.00 → 1.00 | 0.67 → 1.00 | 1.00 → 1.00 | – | 3.6 → 4.6 |
| ho_letter_rot180_200 | 0.256 → 0.005 | 0.244 → 0.023 | 0.99 → 0.98 | 0.99 → 0.97 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 3.9 → 4.4 |
| ho_letter_rot270_200 | 0.746 → 0.003 | 0.901 → 0.015 | 0.99 → 0.98 | 0.99 → 0.98 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 3.6 → 4.4 |
| ho_letter_rot90_200 | 0.080 → 0.005 | 0.130 → 0.023 | 0.99 → 0.98 | 0.99 → 0.97 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 3.7 → 4.5 |
| ho_mixed_rot_200 | 0.270 → 0.006 | 0.289 → 0.028 | 0.80 → 0.97 | 0.99 → 0.98 | 0.11 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 0/7 → 7/7 | 9.8 → 11.8 |
| ho_table_150 | 0.562 → 0.141 | 0.700 → 0.217 | 0.38 → 0.98 | 1.00 → 1.00 | 0.25 → 1.00 | – → – | – → – | 2/7 → 7/7 | 5.6 → 6.1 |
| ho_table_200 | 0.529 → 0.043 | 0.533 → 0.117 | 0.47 → 0.92 | 1.00 → 0.91 | 0.25 → 1.00 | – → – | – → – | 1/7 → 7/7 | 5.1 → 6.0 |
| ho_table_landscape_200 | 0.745 → 0.049 | 0.883 → 0.100 | 0.12 → 0.97 | 1.00 → 1.00 | 0.00 → 1.00 | – → – | – → – | 0/7 → 6/7 | 5.7 → 6.0 |
| ho_table_rot180_200 | 0.954 → 0.010 | 1.000 → 0.033 | 0.00 → 0.97 | 0.00 → 1.00 | 0.00 → 1.00 | – → – | – → – | 0/7 → 7/7 | 5.3 → 5.9 |
| ho_table_rot270_200 | 0.892 → 0.016 | 0.983 → 0.067 | 0.15 → 0.93 | 0.80 → 0.94 | 0.25 → 1.00 | – → – | – → – | 0/7 → 7/7 | 5.0 → 6.3 |

**rapidocr** — peak RSS 5759 → 6118 MB

| Tài liệu | CER | WER | Word recall | Dấu | Số tiền | Ngày | Số hiệu | Dòng bảng | Giây |
|---|---|---|---|---|---|---|---|---|---|
| ho_letter_150 | 0.111 → 0.111 | 0.519 → 0.519 | 0.48 → 0.48 | 0.60 → 0.60 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 6.5 → 7.3 |
| ho_letter_200 | 0.104 → 0.104 | 0.488 → 0.488 | 0.51 → 0.51 | 0.72 → 0.72 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 5.2 → 6.4 |
| ho_letter_a5_300 | 0.153 → 0.153 | 0.634 → 0.634 | 0.37 → 0.37 | 0.40 → 0.40 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 4.9 → 5.5 |
| ho_letter_lowq_150 | 0.132 → 0.132 | 0.565 → 0.565 | 0.44 → 0.44 | 0.47 → 0.47 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 5.2 → 6.2 |
| ho_letter_rot180_200 | 0.726 → 0.104 | 0.985 → 0.488 | 0.46 → 0.51 | 0.76 → 0.76 | 1.00 → 1.00 | 0.67 → 1.00 | 1.00 → 1.00 | – | 5.5 → 6.4 |
| ho_letter_rot270_200 | 0.713 → 0.104 | 0.931 → 0.488 | 0.52 → 0.51 | 0.77 → 0.72 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | – | 5.5 → 6.0 |
| ho_letter_rot90_200 | 0.570 → 0.106 | 0.824 → 0.496 | 0.41 → 0.50 | 0.78 → 0.72 | 1.00 → 1.00 | 0.33 → 1.00 | 0.50 → 1.00 | – | 5.3 → 6.1 |
| ho_mixed_rot_200 | 0.466 → 0.098 | 0.758 → 0.466 | 0.52 → 0.53 | 0.72 → 0.68 | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 | 0/7 → 0/7 | 19.6 → 21.8 |
| ho_table_150 | 0.075 → 0.075 | 0.367 → 0.367 | 0.65 → 0.65 | 0.75 → 0.75 | 1.00 → 1.00 | – → – | – → – | 0/7 → 0/7 | 12.6 → 13.3 |
| ho_table_200 | 0.075 → 0.075 | 0.350 → 0.350 | 0.65 → 0.65 | 0.71 → 0.71 | 1.00 → 1.00 | – → – | – → – | 0/7 → 0/7 | 12.8 → 13.6 |
| ho_table_landscape_200 | 0.072 → 0.072 | 0.350 → 0.350 | 0.67 → 0.67 | 0.78 → 0.78 | 1.00 → 1.00 | – → – | – → – | 0/7 → 0/7 | 13.8 → 14.8 |
| ho_table_rot180_200 | 0.709 → 0.072 | 0.917 → 0.350 | 0.55 → 0.65 | 0.62 → 0.67 | 1.00 → 1.00 | – → – | – → – | 0/7 → 0/7 | 13.0 → 13.7 |
| ho_table_rot270_200 | 0.712 → 0.072 | 0.967 → 0.350 | 0.65 → 0.65 | 0.76 → 0.67 | 1.00 → 1.00 | – → – | – → – | 0/7 → 0/7 | 12.9 → 13.6 |

**easyocr** — peak RSS 5821 → 6197 MB

| Tài liệu | CER | WER | Word recall | Dấu | Số tiền | Ngày | Số hiệu | Dòng bảng | Giây |
|---|---|---|---|---|---|---|---|---|---|
| ho_letter_150 | 0.410 → 0.127 | 0.519 → 0.298 | 0.53 → 0.76 | 0.81 → 0.84 | 1.00 → 1.00 | 1.00 → 1.00 | 0.50 → 0.50 | – | 9.7 → 12.5 |
| ho_letter_200 | 0.184 → 0.122 | 0.237 → 0.176 | 0.85 → 0.91 | 0.93 → 0.93 | 1.00 → 1.00 | 0.67 → 1.00 | 1.00 → 1.00 | – | 8.5 → 11.5 |
| ho_letter_a5_300 | 0.971 → 0.778 | 0.992 → 0.931 | 0.02 → 0.08 | 0.00 → 0.29 | 0.00 → 0.00 | 0.00 → 0.00 | 0.00 → 0.00 | – | 7.4 → 11.6 |
| ho_letter_lowq_150 | 0.798 → 0.414 | 0.863 → 0.672 | 0.14 → 0.34 | 0.90 → 0.54 | 0.00 → 0.00 | 0.33 → 0.67 | 0.00 → 0.50 | – | 8.4 → 13.4 |
| ho_letter_rot180_200 | 0.990 → 0.134 | 1.000 → 0.176 | 0.00 → 0.92 | 0.00 → 0.92 | 0.00 → 1.00 | 0.00 → 1.00 | 0.00 → 1.00 | – | 9.1 → 11.3 |
| ho_letter_rot270_200 | 0.930 → 0.117 | 1.000 → 0.176 | 0.00 → 0.91 | 0.00 → 0.92 | 0.00 → 1.00 | 0.00 → 0.67 | 0.00 → 1.00 | – | 9.1 → 9.9 |
| ho_letter_rot90_200 | 0.930 → 0.120 | 0.992 → 0.168 | 0.01 → 0.91 | 0.00 → 0.92 | 0.00 → 1.00 | 0.00 → 1.00 | 0.00 → 1.00 | – | 9.0 → 10.0 |
| ho_mixed_rot_200 | 0.620 → 0.128 | 0.671 → 0.205 | 0.34 → 0.88 | 0.92 → 0.91 | 0.11 → 0.89 | 0.67 → 1.00 | 1.00 → 1.00 | 0/7 → 2/7 | 22.5 → 25.1 |
| ho_table_150 | 0.281 → 0.167 | 0.467 → 0.400 | 0.57 → 0.65 | 0.65 → 0.66 | 0.50 → 0.62 | – → – | – → – | 0/7 → 0/7 | 10.2 → 11.2 |
| ho_table_200 | 0.216 → 0.111 | 0.417 → 0.333 | 0.62 → 0.70 | 0.85 → 0.82 | 0.88 → 0.88 | – → – | – → – | 2/7 → 2/7 | 10.5 → 10.9 |
| ho_table_landscape_200 | 0.101 → 0.091 | 0.200 → 0.200 | 0.87 → 0.87 | 0.97 → 0.97 | 1.00 → 1.00 | – → – | – → – | 5/7 → 5/7 | 12.3 → 13.1 |
| ho_table_rot180_200 | 0.948 → 0.134 | 0.983 → 0.350 | 0.02 → 0.72 | 0.00 → 0.85 | 0.00 → 0.88 | – → – | – → – | 0/7 → 2/7 | 10.5 → 10.9 |
| ho_table_rot270_200 | 0.931 → 0.131 | 1.000 → 0.350 | 0.00 → 0.72 | 0.00 → 0.85 | 0.00 → 0.88 | – → – | – → – | 0/7 → 2/7 | 11.8 → 11.0 |

## 6. Tái hiện

```bash
source "$ACCEPT_DIR/env.sh"; cd "$ACCEPT_DIR/src"; E="$ACCEPT_DIR/evidence/phase8c"
uv run python scripts/ocr/generate_holdout_fixtures.py --out "$E/holdout"
git worktree add --detach "$ACCEPT_DIR/baseline-8b-src" f172645
for eng in tesseract_best tesseract_fast rapidocr easyocr; do
  uv run python scripts/ocr/quality_eval.py --src "$ACCEPT_DIR/baseline-8b-src" --engine $eng \
      --dir "$E/holdout" --out "$E/holdout-baseline/$eng.json"
  uv run python scripts/ocr/quality_eval.py --engine $eng --dir "$E/holdout" --out "$E/holdout-after/$eng.json"
done
python3 "$E/make_tables.py"
```
