# Benchmark Tesseract Vietnamese Agri (Phase 10E)

Cập nhật: 2026-11-16 · Model được đo: **Agri v1** — `vie_agri.traineddata`, 12.435.550 byte
(SHA-256 do chủ model lưu; không ghi trong tài liệu công khai).

Tài liệu này công khai: chỉ chứa số liệu tổng hợp trên dữ liệu **tổng hợp**; không có model, dữ liệu huấn luyện
hay tài liệu nội bộ.

## 1. Kết luận ngắn

**Chất lượng: TƯƠNG ĐƯƠNG (EQUIVALENT) trong pipeline xử lý tài liệu thật của ứng dụng, trên dữ liệu tổng hợp —
không chứng minh được là tốt hơn. Trên tài liệu thật: CHƯA KIỂM CHỨNG.**

| Câu hỏi | Trả lời từ số đo |
|---|---|
| Model có nạp và chạy đúng không? | Có. Tesseract 5.5.0 nạp được, pipeline Docling chạy đủ (Layout Heron + TableFormer Accurate + `TesseractOcrCliModel`), 0 lỗi trên 102 lượt chuyển đổi |
| Gọi Tesseract **trực tiếp** (cô lập model) | Agri **tốt hơn** Best: CER 1,72% so với 2,78%; WER 4,96% so với 8,24%; trên scan mờ CER 6,10% so với 9,83% |
| Qua **pipeline Docling hoàn chỉnh** (đường xử lý thật) | **Tương đương**: CER 3,40% so với 3,51% (Full Page OFF); khi Full Page ON Best còn tốt hơn (2,96% so với 3,47%) |
| Agri tốt hơn rõ ở đâu? | **Số hiệu văn bản** (86,7% so với 60,0% đọc nguyên văn) và **chữ Đ hoa** (151/152 so với 143/152): Best hay đọc `QĐ` thành `QÐ` / `QD`. Tiêu đề in hoa in đậm nhỉnh hơn (79,2% so với 74,0%) |
| Agri **kém hơn** ở đâu? | **Giá trị phần trăm**: chỉ đọc đúng 20/28 (Best 28/28) — ví dụ `20%;` → `2096;`, `5%;` → `596;`, `4,5%/năm` → `4,59%6/năm`. Đây là lỗi làm đổi nghĩa (lãi suất, tỷ lệ trích lập). Tổng lỗi làm đổi nghĩa pháp lý qua pipeline: Agri 38, Best 33 |
| Từ phủ định / nghĩa vụ / ngoại lệ | Hai model như nhau: `không` 67/68, `phải` 32/32, `trừ` 24/24, `chưa` 20/20. `cấm`: Agri 14/16, Best 15/16 |
| Thêm tiếng Anh (cấu hình C) có lợi không? | Không: kém hơn Agri đơn ở CER, WER, dấu, tiêu đề, và đọc sai `cấm` nhiều hơn (10/16); chỉ sửa được lỗi phần trăm (27/28) |
| Tốc độ / tài nguyên | Agri nhanh hơn Best khoảng 7% qua pipeline (một ngôn ngữ thay vì hai); RAM như nhau (≈ 4,1–4,3 GB, do Docling chi phối) |

Hệ quả: Agri v1 **chưa nên thay** Tesseract Vietnamese Best cho tài liệu nghiệp vụ. Nó đáng dùng thử song song và
là nền tốt cho bản fine-tune kế tiếp — với việc cần làm rõ ràng nhất là bổ sung mẫu có ký hiệu `%` (mục 6.6).

## 2. Ba cấu hình được so sánh

| Ký hiệu | Engine | Ngôn ngữ Tesseract | Ghi chú |
|---|---|---|---|
| **A — best** | Tesseract Vietnamese Best (không đổi) | `best/vie + best/eng` | tessdata_best 4.1.0, checksum chính thức |
| **B — agri** | Tesseract Vietnamese Agri | `custom/agri/v1/vie_agri` | chỉ model Agri |
| **C — agri_eng** | Tesseract Vietnamese Agri, `OCR_AGRI_WITH_ENGLISH=true` | `custom/agri/v1/vie_agri + best/eng` | Agri + tiếng Anh chính thức |

Cùng một binary Tesseract 5.5.0, cùng Docling 2.129.0 / Layout Heron / TableFormer Accurate, cùng tiền xử lý PDF
và cổng OSD. Khác nhau duy nhất là danh sách ngôn ngữ truyền cho Tesseract.

Cấu trúc model Agri v1 (đọc bằng `combine_tessdata -d`): cùng kiến trúc mạng, cùng unicharset, recoder và các
từ điển (dawg) với `tessdata_best/vie` — **chỉ khác trọng số LSTM**. Tức là một bản fine-tune của Tesseract Best,
không thêm ký tự mới.

## 3. Dữ liệu

Sinh bằng `scripts/ocr/generate_agri_benchmark_fixtures.py` (tái lập được, seed cố định):

- **4 văn bản pháp lý hư cấu** do người viết benchmark soạn riêng ("Ngân hàng Thương mại Mẫu", "Cơ quan quản lý
  mẫu"): một Quyết định ban hành quy định, một Quy định (Chương / Điều / Khoản / Điểm), một Thông tư, một chương về
  quyền – nghĩa vụ – hành vi bị cấm. Tổng cộng 1.475 từ tham chiếu, 11 tiêu đề in hoa in đậm, 16 Điều, 23 Khoản,
  13 Điểm, 9 số hiệu văn bản, 13 ngày tháng — cho **mỗi** mức chất lượng scan (×4 mức = 5.900 từ, 44 lượt tiêu đề).
- Nội dung nhắm đúng các điểm cần đo: tiêu đề in hoa in đậm; dấu tiếng Việt; Điều, Khoản, Điểm; thuật ngữ nghiệp
  vụ ngân hàng (cho vay, bảo đảm tiền vay, cơ cấu lại thời hạn trả nợ, trích lập dự phòng…); số hiệu; ngày tháng;
  từ phủ định, nghĩa vụ, ngoại lệ (không, chưa, phải, bắt buộc, trừ, ngoại trừ, chỉ, nghiêm cấm…).
- Mỗi văn bản dựng ở **4 chất lượng scan** → 16 PDF chỉ có ảnh (28 trang):

  | Biến thể | DPI | Xử lý ảnh |
  |---|---|---|
  | `sach_300` | 300 | sạch |
  | `scan_200` | 200 | mờ nhẹ, nhiễu hạt, nghiêng −0,4°, JPEG 60 |
  | `mo_150` (**scan mờ**) | 150 | mờ mạnh, mực nhạt, nền xám, nhiễu, nghiêng 0,7°, JPEG 35 |
  | `photocopy_200` | 200 | nhị phân hóa sau khi mờ (nét dày / đứt), nhiễu hạt, nghiêng 0,5° |

- Phông: Liberation Serif (tương đương Times New Roman) cho 3 văn bản, Liberation Sans cho 1 văn bản.
- Thêm 1 PDF **có lớp văn bản** (`vb_text_layer.pdf`) để kiểm chứng PDF loại này không bị engine ảnh hưởng.
- Không có bảng báo cáo tài chính hay biểu đồ (ngoài phạm vi Phase 10).

### Tính độc lập của ground truth — giới hạn phải nêu rõ

- **Nội dung chữ** của bộ dữ liệu được viết mới cho benchmark này, không lấy từ bất kỳ văn bản thật nào, nên độc
  lập với dữ liệu fine-tune *về mặt nội dung*.
- **Không xác minh được** sự độc lập về *hình thức*: người đo không có dữ liệu fine-tune của Agri v1. Nếu model
  được fine-tune trên ảnh dựng từ phông họ Times / Liberation hoặc trên văn bản có cùng từ vựng pháp lý – ngân
  hàng, bộ dữ liệu này gần với phân phối huấn luyện và có thể **có lợi cho Agri**.
- Đây là ảnh **dựng từ phông chữ rồi làm xấu**, không phải bản scan giấy thật: không có dấu đỏ, chữ ký, tiêu đề
  hai cột, nếp gấp, nền giấy không đều.

- Bộ đo **nhỏ**: 44 lượt tiêu đề, 64 lượt Điều, 52 lượt Điểm. Một tiêu đề sai làm chỉ số "Tiêu đề đúng" đổi hơn
  2 điểm phần trăm; các chênh lệch nhỏ giữa cấu hình không có ý nghĩa thống kê.

Vì vậy mọi kết luận dưới đây chỉ có giá trị cho **văn bản pháp lý tổng hợp**. Chất lượng trên tài liệu thật của
đơn vị là **CHƯA KIỂM CHỨNG** (mục 8).

## 4. Chỉ số

Tính bằng `scripts/ocr/agri_benchmark.py` (dùng `open_notebook/ocr/metrics.py` có sẵn cho CER / WER / dấu):

| Chỉ số | Cách tính | Tốt hơn khi |
|---|---|---|
| CER, WER | Khoảng cách Levenshtein ký tự / từ sau chuẩn hóa NFC và khoảng trắng | thấp |
| Dấu tiếng Việt | Tỷ lệ từ có dấu được nhận đúng dấu, trong số các từ tìm thấy theo dạng bỏ dấu | cao |
| Tiêu đề đúng | Tỷ lệ tiêu đề in hoa in đậm xuất hiện **nguyên văn** trong kết quả | cao |
| CER tiêu đề | CER nhỏ nhất của tiêu đề so với một cửa sổ từ cùng độ dài trong kết quả | thấp |
| Điều / Khoản / Điểm | Tỷ lệ "mỏ neo" (ví dụ `Điều 3. Điều kiện vay vốn`, 5 từ đầu của khoản / điểm) xuất hiện nguyên văn | cao |
| Số hiệu, Ngày | Tỷ lệ số hiệu văn bản / ngày tháng xuất hiện nguyên văn | cao |
| **Lỗi pháp lý** | Số từ tham chiếu **bị thay hoặc bị mất** thuộc nhóm làm đổi nghĩa pháp lý — phủ định (không, chưa, cấm, nghiêm), nghĩa vụ (phải, buộc, bắt, nghĩa, vụ, trách, nhiệm), ngoại lệ (trừ, ngoại, chỉ, ngoài), cho phép (được, quyền), giới hạn (tối, đa, quá, vượt, ít, nhất, chậm) và **mọi từ chứa chữ số**; cộng số từ phủ định bị chèn thừa. Không tính sai hoa/thường hay dấu câu bao quanh | thấp |
| Bỏ sót | Tỷ lệ từ tham chiếu bị mất hẳn (thao tác xóa trong căn chỉnh từ) | thấp |
| Giây, CPU-giây, RSS | Thời gian thực, thời gian CPU (tiến trình + tiến trình con), đỉnh bộ nhớ | thấp |

## 5. Môi trường đo

| Hạng mục | Giá trị |
|---|---|
| Nơi đo | Bên trong container ứng dụng của stack thử nghiệm `chatbot5400-agri-test` (image `chatbot5400:agri-test`) — đúng runtime sẽ xử lý tài liệu |
| Giới hạn container | 4 CPU, 10 GB RAM (máy chủ: Intel Core i7-4790, 8 luồng, 30 GB RAM; production chạy song song, gần như rảnh) |
| Phần mềm | Tesseract 5.5.0 (leptonica 1.84.1), Docling 2.129.0, Content Core 2.0.7, torch 2.14.0+cpu |
| Tesseract trực tiếp | `tesseract <ảnh trang> stdout -l <ngôn ngữ> --dpi <DPI của bản scan>`, PSM mặc định, trên ảnh trang lấy đúng từ PDF |
| Pipeline | `docling_extract.convert_file` — đường xử lý của worker: tiền xử lý PDF (dò hướng trang, tỷ lệ render theo DPI scan), Layout Heron, TableFormer Accurate, Tesseract qua cổng OSD, xuất Markdown. Mỗi tổ hợp (cấu hình × Full Page) chạy trong một tiến trình riêng |
| Số lượt | Trực tiếp: 3 cấu hình × 16 PDF (28 trang). Pipeline: 3 cấu hình × 2 chế độ Full Page × 17 PDF = 102 lượt, 0 lỗi |
| Thời điểm | 2026-11-16, một lần chạy cho mỗi tổ hợp (Tesseract và Docling tất định trên CPU; số đo trực tiếp lặp lại y hệt giữa máy chủ và container) |

Dữ liệu thô (kèm văn bản nhận dạng của dữ liệu tổng hợp) được giữ ngoài kho mã, trên máy chủ thử nghiệm.

## 6. Kết quả

### 6.1 Tổng hợp (16 PDF scan)

| Giai đoạn | Full Page | Cấu hình | CER | WER | Dấu TV | Tiêu đề đúng | CER tiêu đề | Điều | Khoản | Điểm | Số hiệu | Ngày | Lỗi pháp lý | Bỏ sót | Giây | CPU-giây | RSS MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Tesseract trực tiếp | — | **B — agri** | 1.72% | 4.96% | 99.22% | 72.92% | 3.61% | 85.21% | 86.61% | 85.83% | 83.89% | 91.90% | 34 (5.76/1000 từ) | 0.17% | 32.2 | 77.0 | 138.0 |
| Tesseract trực tiếp | — | C — agri_eng | 2.04% | 6.10% | 98.66% | 67.71% | 5.38% | 78.75% | 82.44% | 85.83% | 85.56% | 92.62% | 41 (6.95/1000 từ) | 0.13% | 39.6 | 94.9 | 170.4 |
| Tesseract trực tiếp | — | A — best | 2.78% | 8.24% | 98.34% | 59.38% | 7.45% | 82.50% | 83.48% | 82.92% | 53.33% | 74.29% | 48 (8.14/1000 từ) | 0.14% | 41.0 | 99.8 | 173.3 |
| Pipeline Docling | OFF | **B — agri** | 3.40% | 6.64% | 98.57% | 79.17% | 2.50% | 87.60% | 84.23% | 86.67% | 86.67% | 97.62% | 38 (6.44/1000 từ) | 0.62% | 119.9 | 247.0 | 4276.7 |
| Pipeline Docling | OFF | C — agri_eng | 3.72% | 7.80% | 97.53% | 68.75% | 4.75% | 82.92% | 84.38% | 82.92% | 86.67% | 97.62% | 41 (6.95/1000 từ) | 0.62% | 128.6 | 267.7 | 4149.4 |
| Pipeline Docling | OFF | A — best | 3.51% | 7.11% | 98.30% | 73.96% | 3.09% | 84.79% | 86.46% | 84.17% | 60.00% | 95.95% | 33 (5.59/1000 từ) | 0.62% | 129.1 | 269.9 | 4053.1 |
| Pipeline Docling | ON | **B — agri** | 3.47% | 6.60% | 98.50% | 76.04% | 2.89% | 86.04% | 81.99% | 86.67% | 86.67% | 97.62% | 38 (6.44/1000 từ) | 1.03% | 126.7 | 256.1 | 4230.3 |
| Pipeline Docling | ON | C — agri_eng | 3.76% | 7.68% | 97.43% | 68.75% | 4.13% | 82.92% | 83.18% | 82.92% | 86.67% | 97.62% | 42 (7.12/1000 từ) | 1.00% | 135.2 | 277.9 | 4167.6 |
| Pipeline Docling | ON | A — best | 2.96% | 6.50% | 98.20% | 70.83% | 4.31% | 84.79% | 85.57% | 84.17% | 60.00% | 95.95% | 31 (5.25/1000 từ) | 0.51% | 132.6 | 270.4 | 4305.0 |

Đọc bảng: "Tiêu đề đúng", "Điều", "Khoản", "Điểm", "Số hiệu", "Ngày" là tỷ lệ xuất hiện **nguyên văn**; "Lỗi pháp
lý" là số tuyệt đối trên 5.900 từ tham chiếu (và mật độ trên 1.000 từ). CER của pipeline cao hơn gọi trực tiếp ở
mọi cấu hình vì còn gồm sai khác do dựng lại bố cục (thứ tự đọc, gạch đầu dòng, phần bị bỏ) — phần này không phụ
thuộc model OCR và làm nhỏ đi chênh lệch giữa các model.

### 6.2 Theo chất lượng scan

| Giai đoạn | Full Page | Chất lượng scan | Cấu hình | CER | WER | Dấu TV | Tiêu đề đúng | Lỗi pháp lý | Bỏ sót |
|---|---|---|---|---|---|---|---|---|---|
| Tesseract trực tiếp | — | mo_150 | **B — agri** | 6.10% | 16.45% | 97.89% | 50.00% | 27 | 0.60% |
| Tesseract trực tiếp | — | mo_150 | C — agri_eng | 6.95% | 19.68% | 96.56% | 41.67% | 29 | 0.54% |
| Tesseract trực tiếp | — | mo_150 | A — best | 9.83% | 27.77% | 95.16% | 33.33% | 38 | 0.49% |
| Tesseract trực tiếp | — | photocopy_200 | **B — agri** | 0.31% | 1.32% | 99.58% | 79.17% | 3 | 0.00% |
| Tesseract trực tiếp | — | photocopy_200 | C — agri_eng | 0.50% | 1.93% | 99.15% | 79.17% | 4 | 0.00% |
| Tesseract trực tiếp | — | photocopy_200 | A — best | 0.34% | 1.37% | 99.31% | 87.50% | 3 | 0.00% |
| Tesseract trực tiếp | — | sach_300 | **B — agri** | 0.31% | 1.30% | 99.51% | 87.50% | 3 | 0.00% |
| Tesseract trực tiếp | — | sach_300 | C — agri_eng | 0.49% | 1.90% | 99.10% | 75.00% | 6 | 0.00% |
| Tesseract trực tiếp | — | sach_300 | A — best | 0.52% | 2.15% | 99.57% | 50.00% | 4 | 0.00% |
| Tesseract trực tiếp | — | scan_200 | **B — agri** | 0.15% | 0.77% | 99.91% | 75.00% | 1 | 0.07% |
| Tesseract trực tiếp | — | scan_200 | C — agri_eng | 0.23% | 0.88% | 99.82% | 75.00% | 2 | 0.00% |
| Tesseract trực tiếp | — | scan_200 | A — best | 0.43% | 1.68% | 99.32% | 66.67% | 3 | 0.07% |
| Pipeline Docling | OFF | mo_150 | **B — agri** | 10.29% | 17.09% | 96.71% | 70.84% | 22 | 2.20% |
| Pipeline Docling | OFF | mo_150 | C — agri_eng | 10.81% | 18.93% | 95.13% | 50.00% | 28 | 2.20% |
| Pipeline Docling | OFF | mo_150 | A — best | 10.47% | 17.98% | 96.69% | 62.50% | 24 | 2.21% |
| Pipeline Docling | OFF | photocopy_200 | **B — agri** | 1.00% | 2.69% | 99.42% | 79.17% | 3 | 0.07% |
| Pipeline Docling | OFF | photocopy_200 | C — agri_eng | 1.29% | 3.64% | 98.67% | 79.17% | 3 | 0.07% |
| Pipeline Docling | OFF | photocopy_200 | A — best | 1.11% | 3.08% | 99.08% | 87.50% | 3 | 0.07% |
| Pipeline Docling | OFF | sach_300 | **B — agri** | 1.48% | 4.42% | 98.58% | 91.67% | 7 | 0.22% |
| Pipeline Docling | OFF | sach_300 | C — agri_eng | 2.04% | 6.49% | 96.84% | 70.84% | 8 | 0.22% |
| Pipeline Docling | OFF | sach_300 | A — best | 1.60% | 4.84% | 97.87% | 70.83% | 3 | 0.22% |
| Pipeline Docling | OFF | scan_200 | **B — agri** | 0.82% | 2.36% | 99.56% | 75.00% | 6 | 0.00% |
| Pipeline Docling | OFF | scan_200 | C — agri_eng | 0.75% | 2.14% | 99.48% | 75.00% | 2 | 0.00% |
| Pipeline Docling | OFF | scan_200 | A — best | 0.85% | 2.55% | 99.56% | 75.00% | 3 | 0.00% |
| Pipeline Docling | ON | mo_150 | **B — agri** | 10.65% | 17.19% | 96.61% | 58.34% | 24 | 3.83% |
| Pipeline Docling | ON | mo_150 | C — agri_eng | 11.04% | 18.71% | 94.76% | 50.00% | 31 | 3.70% |
| Pipeline Docling | ON | mo_150 | A — best | 8.32% | 15.80% | 96.20% | 50.00% | 22 | 1.77% |
| Pipeline Docling | ON | photocopy_200 | **B — agri** | 0.99% | 2.62% | 99.42% | 79.17% | 3 | 0.07% |
| Pipeline Docling | ON | photocopy_200 | C — agri_eng | 1.25% | 3.50% | 98.67% | 79.17% | 3 | 0.07% |
| Pipeline Docling | ON | photocopy_200 | A — best | 1.08% | 2.95% | 99.08% | 87.50% | 3 | 0.07% |
| Pipeline Docling | ON | sach_300 | **B — agri** | 1.46% | 4.35% | 98.49% | 91.67% | 7 | 0.22% |
| Pipeline Docling | ON | sach_300 | C — agri_eng | 2.00% | 6.35% | 96.83% | 70.84% | 7 | 0.22% |
| Pipeline Docling | ON | sach_300 | A — best | 1.58% | 4.77% | 97.87% | 70.83% | 3 | 0.22% |
| Pipeline Docling | ON | scan_200 | **B — agri** | 0.79% | 2.22% | 99.47% | 75.00% | 4 | 0.00% |
| Pipeline Docling | ON | scan_200 | C — agri_eng | 0.76% | 2.15% | 99.47% | 75.00% | 1 | 0.00% |
| Pipeline Docling | ON | scan_200 | A — best | 0.85% | 2.49% | 99.64% | 75.00% | 3 | 0.00% |

- **Scan rõ (`sach_300`, `scan_200`, `photocopy_200`)**: ba cấu hình sát nhau; qua pipeline Agri nhỉnh hơn Best ở
  CER / WER nhưng có nhiều lỗi làm đổi nghĩa hơn ở `sach_300` (7 so với 3) — chủ yếu là giá trị phần trăm.
- **Scan mờ (`mo_150`)**: gọi trực tiếp Agri tốt hơn rõ (CER 6,10% so với 9,83%; lỗi pháp lý 27 so với 38). Qua
  pipeline hai model ngang nhau khi Full Page OFF (10,29% so với 10,47%); khi Full Page ON Best tốt hơn (8,32% so
  với 10,65%) và Agri bỏ sót nhiều hơn (3,83% so với 1,77%). Chỉ có 4 tài liệu ở mức này: dao động lớn, không đủ
  để kết luận bên nào tốt hơn trên scan mờ thật.

### 6.3 PDF có lớp văn bản

| PDF có lớp văn bản | Full Page | Cấu hình | CER | WER | Giây |
|---|---|---|---|---|---|
| vb_text_layer.pdf | OFF | A — best | 0.22% | 0.49% | 2.37 |
| vb_text_layer.pdf | ON | A — best | 0.38% | 1.21% | 5.52 |
| vb_text_layer.pdf | OFF | **B — agri** | 0.22% | 0.49% | 2.34 |
| vb_text_layer.pdf | ON | **B — agri** | 0.22% | 0.73% | 5.3 |
| vb_text_layer.pdf | OFF | C — agri_eng | 0.22% | 0.49% | 2.32 |
| vb_text_layer.pdf | ON | C — agri_eng | 0.87% | 3.16% | 5.6 |

Với Full Page **OFF**, văn bản xuất ra của PDF có lớp văn bản **giống hệt nhau từng byte** ở cả ba cấu hình
(SHA-256 của kết quả bắt đầu bằng `55ad386eb5c7a75d` cho cả ba): Docling lấy chữ từ lớp văn bản, engine OCR không
tham gia. **PDF có lớp văn bản không bị Agri ảnh hưởng.** Chỉ khi quản trị viên bật Force Full Page OCR thì trang
mới được OCR lại và kết quả phụ thuộc engine.

### 6.4 Force Full Page OCR: OFF so với ON

| Cấu hình | CER OFF | CER ON | WER OFF | WER ON | Lỗi pháp lý OFF | Lỗi pháp lý ON | Bỏ sót OFF | Bỏ sót ON |
|---|---|---|---|---|---|---|---|---|
| A — best | 3,51% | 2,96% | 7,11% | 6,50% | 33 | 31 | 0,62% | 0,51% |
| **B — agri** | 3,40% | 3,47% | 6,64% | 6,60% | 38 | 38 | 0,62% | 1,03% |
| C — agri_eng | 3,72% | 3,76% | 7,80% | 7,68% | 41 | 42 | 0,62% | 1,00% |

Với PDF chỉ có ảnh scan, hai chế độ cho kết quả gần như nhau ở các mức scan rõ (khác biệt ≤ 0,05 điểm phần trăm
CER). Khác biệt ở tổng thể đến từ 4 tài liệu scan mờ, nơi vùng OCR do bố cục xác định (OFF) và OCR toàn trang (ON)
cắt trang khác nhau. Không có cơ sở để khuyến nghị bật Force Full Page OCR cho Agri; mặc định (OFF) được giữ.

### 6.5 Tài nguyên

| Giai đoạn | Cấu hình | Thời gian (giây, tổng 16 PDF / 28 trang) | CPU-giây | Đỉnh RSS |
|---|---|---|---|---|
| Tesseract trực tiếp | A — best | 41,0 | 99,8 | 173 MB |
| Tesseract trực tiếp | **B — agri** | 32,2 | 77,0 | 138 MB |
| Tesseract trực tiếp | C — agri_eng | 39,6 | 94,9 | 170 MB |
| Pipeline, Full Page OFF | A — best | 129,1 | 269,9 | 4.053 MB |
| Pipeline, Full Page OFF | **B — agri** | 119,9 | 247,0 | 4.277 MB |
| Pipeline, Full Page OFF | C — agri_eng | 128,6 | 267,7 | 4.149 MB |
| Pipeline, Full Page ON | A — best | 132,6 | 270,4 | 4.305 MB |
| Pipeline, Full Page ON | **B — agri** | 126,7 | 256,1 | 4.230 MB |
| Pipeline, Full Page ON | C — agri_eng | 135,2 | 277,9 | 4.168 MB |

- Agri đơn nạp một model thay vì hai nên Tesseract nhanh hơn khoảng 21% và dùng ít RAM hơn khoảng 35 MB mỗi lần
  gọi; qua pipeline lợi thế còn khoảng 7% thời gian vì Layout / TableFormer chiếm phần lớn.
- Đỉnh RSS của pipeline (≈ 4,1–4,3 GB) là mức cao nhất của cả tiến trình, gồm model Docling nạp một lần; chênh
  lệch giữa cấu hình nằm trong dao động giữa các lần chạy.
- Trung bình khoảng 4,3–4,8 giây mỗi trang scan qua pipeline với giới hạn 4 CPU.

### 6.6 Ví dụ lỗi làm đổi nghĩa pháp lý

Từ căn chỉnh từ giữa ground truth và kết quả pipeline (Full Page OFF), các mức scan rõ:

| Model | Văn bản gốc → kết quả | Loại lỗi |
|---|---|---|
| A — best | `468/QĐ-HĐTV-TD` → `468/QÐ-HĐTV-TD` / `468/QD-HDTV-TD` (5 tài liệu) | Số hiệu: chữ Đ thành Ð / D |
| A — best | `1532/TTr-TGĐ` → `1532/TTT-TGĐ` | Số hiệu |
| A — best | `chỉ` → `chi`; `CẤM` → `CAM` | Mất dấu ở từ ngoại lệ / cấm (tiêu đề in hoa) |
| B — agri | `20%;` → `2096;` · `5%;` → `596;` · `50%;` → `7.` · `4,5%/năm;` → `4,59%6/năm;` | **Giá trị phần trăm** |
| B — agri | `Nghiêm` → `Nghiệm`; `cấm` → `cẩm`; `CẤM` → `CÃM` | Sai dấu ở từ cấm |
| B — agri | `6` → `G`; `01` → `O1`; `115/NQ-HĐTV` → `115/NQ-HĐDTV` | Chữ số / số hiệu |

Số lượt đọc đúng trên toàn bộ 16 PDF (pipeline, Full Page OFF):

| Mục | A — best | B — agri | C — agri_eng |
|---|---|---|---|
| Giá trị phần trăm (`4,5%`, `150%`, `20%`…) | **28/28** | 20/28 | 27/28 |
| Chữ Đ hoa | 143/152 | **151/152** | 146/152 |
| `nghiêm` | 15/16 | 15/16 | 15/16 |
| `cấm` | 15/16 | 14/16 | 10/16 |
| `không` | 67/68 | 67/68 | 67/68 |
| `phải` | 32/32 | 32/32 | 32/32 |
| `trừ` | 24/24 | 24/24 | 24/24 |
| `chỉ` | 7/8 | **8/8** | 6/8 |
| `chưa` | 20/20 | 20/20 | 20/20 |

Phép thử bổ sung (ngoài bộ đo): một khối 9 dòng chứa nhiều giá trị phần trăm, dựng ở 3 phông × 2 DPI, đọc trực
tiếp bằng Tesseract: Best đúng 78/78, Agri đúng 76/78. Tức là Agri **không mất hẳn** ký hiệu `%`; lỗi tập trung ở
dòng liệt kê ngắn kết thúc bằng `%;` (như `c) Nhóm 3 (…): 20%;`). Gợi ý cho bản fine-tune kế tiếp: bổ sung dòng
huấn luyện có `%` ở cuối dòng, sau dấu hai chấm và trong mẫu `x,y%/năm`; và cặp từ `nghiêm cấm`.

## 7. Chọn cấu hình mặc định cho Agri

**Mặc định: B — chỉ `vie_agri`** (`OCR_AGRI_WITH_ENGLISH=false`).

| Tiêu chí (pipeline, Full Page OFF) | B — agri | C — agri_eng | Tốt hơn |
|---|---|---|---|
| CER / WER | 3,40% / 6,64% | 3,72% / 7,80% | B |
| Dấu tiếng Việt | 98,57% | 97,53% | B |
| Tiêu đề đúng | 79,17% | 68,75% | B |
| Điều / Khoản / Điểm | 87,6% / 84,2% / 86,7% | 82,9% / 84,4% / 82,9% | B |
| Số hiệu / Ngày | 86,7% / 97,6% | 86,7% / 97,6% | bằng |
| Lỗi pháp lý | 38 | 41 | B |
| `cấm` đọc đúng | 14/16 | 10/16 | B |
| Giá trị phần trăm | 20/28 | 27/28 | **C** |
| Thời gian / RAM mỗi lần gọi Tesseract | 32,2 s / 138 MB | 39,6 s / 170 MB | B |

C chỉ thắng ở giá trị phần trăm và thua ở mọi tiêu chí còn lại, kể cả một từ mang nghĩa cấm đoán. Ngoài ra B không
phụ thuộc model tiếng Anh của Tesseract Best. Cấu hình C vẫn bật được bằng `OCR_AGRI_WITH_ENGLISH=true` (cần cài
Tesseract Vietnamese Best; readiness cũ mất hiệu lực khi đổi) để đo lại với các bản fine-tune sau.

## 8. Những gì CHƯA được kiểm chứng

- Chất lượng trên **bản scan giấy thật** của văn bản Agribank (dấu đỏ, chữ ký đè lên chữ, tiêu đề hai cột, bảng,
  fax, ảnh chụp điện thoại).
- Tính độc lập về hình thức giữa bộ đo và dữ liệu fine-tune (mục 3).
- Bảng biểu, số liệu tài chính, biểu đồ — ngoài phạm vi; kết quả nghiệm thu bảng của Tesseract Best ở Phase 8/9
  **không** tự động áp dụng cho Agri.
- Văn bản song ngữ hoặc nhiều thuật ngữ tiếng Anh.

Cách kiểm chứng trên tài liệu thật mà không để lộ nội dung: công cụ có sẵn
`scripts/ocr/local_document_benchmark.py` (chỉ ghi số liệu tổng hợp, không ghi văn bản hay tên file) chấp nhận
engine Agri:

```bash
docker compose exec open_notebook /app/.venv/bin/python scripts/ocr/local_document_benchmark.py \
  --dir /app/data/benchmark-docs --engines tesseract_best tesseract_agri \
  --out /app/data/benchmark-agri.json --markdown /app/data/benchmark-agri.md
```

Xem [OCR_REAL_DOCUMENT_BENCHMARK.md](OCR_REAL_DOCUMENT_BENCHMARK.md) về cách chuẩn bị thư mục tài liệu và ground
truth. Chạy trên máy chủ, **không** dán tài liệu hay nội dung của chúng vào bất kỳ công cụ nào khác.

## 9. Tái lập

```bash
# 1. Sinh dữ liệu (cần reportlab cho PDF có lớp văn bản)
uv run --with reportlab python scripts/ocr/generate_agri_benchmark_fixtures.py --out /tmp/agri-bench

# 2. Trong container ứng dụng, đã import và kích hoạt Agri v1, đã cài Tesseract Vietnamese Best
python scripts/ocr/agri_benchmark.py direct --dir /tmp/agri-bench --out /tmp/direct.json \
  --tessdata /app/data/ocr/models/tesseract --agri-version v1
python scripts/ocr/agri_benchmark.py pipeline --dir /tmp/agri-bench --out /tmp/pipeline.json
python scripts/ocr/agri_benchmark.py report /tmp/direct.json /tmp/pipeline.json
```
