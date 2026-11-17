# Phase 12D — Quality benchmark (bộ fixture tổng hợp)

Số liệu thô: [`phase12/benchmark_synthetic.json`](phase12/benchmark_synthetic.json) — tạo lại bằng
`uv run python scripts/ocr/phase12_benchmark.py --out … --pdf-dir <thư mục generate_phase12_fixtures.py>`.

## 1. Phạm vi và cách đo — đọc trước khi dùng số liệu

| Phép đo | Đầu vào | Đo cái gì | Không đo cái gì |
|---|---|---|---|
| **Cấu trúc** (Standard vs Legal) | 24 fixture; `DoclingDocument` tạo bởi **ReadingOrderModel thật của Docling 2.129** từ bố cục tổng hợp | tác động của serializer/normalizer lên **văn bản đúng 100%** | OCR, Layout Heron, TableFormer |
| **Nhận dạng** (Direct OCR) | PDF scan 200 DPI vẽ từ cùng fixture | Tesseract **5.3.4** (Ubuntu) `vie`, `--psm 3`, cả trang | không phải Tesseract 5.5.0 + tessdata fast/best/Agri của production |

Hai phép đo **tách biệt có chủ ý**: chuẩn hóa không thể (và không được) cải thiện nhận dạng; CER của Legal thấp hơn
vì bớt artifact, **không** vì xóa nội dung khó đọc (kiểm tra bằng `false_deleted_words` = 0).

**Pipeline đầy đủ (Heron + TableFormer + engine + Agri) trên PDF: NOT VERIFIED trên Cloud** (Hugging Face bị chặn) —
đo trên Windows Local bằng `scripts/ocr/phase12_compare.py` (cùng chỉ số) theo
[PHASE12E_WINDOWS_LOCAL_TEST_GUIDE.md](PHASE12E_WINDOWS_LOCAL_TEST_GUIDE.md).

"Hiển thị" = văn bản người dùng đọc trên frontend, dựng lại bằng CommonMark (markdown-it) gồm cả số thứ tự danh
sách mà trình duyệt vẽ (`scripts/ocr/phase12_metrics.py::display_lines`).

## 2. Kết quả tổng hợp (24 fixture)

| Chỉ số | Direct OCR (Tesseract) | Standard (v1.2.0) | Legal Normalized |
|---|---|---|---|
| CER trung bình (so với ground truth) | 0,1005 | 0,1470 | **0,0178** |
| WER trung bình | 0,1235 | 0,1849 | **0,0215** |
| Text recall (từ của ground truth có mặt) | 0,9625 | 0,9418 | **0,9980** |
| Trường nghiệp vụ khớp tuyệt đối (số hiệu, ngày, tiền, %, URL, mã) | 21/24 | 23/24 | **24/24** |
| Marker Khoản/Điểm hiển thị đúng như gốc | — | 14/33 | **33/33** |
| Mục danh sách bị trình duyệt đánh lại số | — | 3/20 | **0** |
| Reading-order accuracy (cặp cụm từ đúng thứ tự) | — | 0,95 | 0,95 (không đổi — đúng thiết kế) |
| Dòng chỉ có chữ số trong nội dung | — | 27 | 3 (đều là nội dung hợp lệ: `2024`, `15`, số trang của tài liệu 1 trang) |
| Dòng artifact phải vắng mặt (số trang, header lặp) | — | 0/23 | **23/23** |
| `<!-- image -->` | — | 8 | 1 (ảnh lớn không chữ — giữ có chủ ý, kèm cảnh báo) |
| Ghép liên trang cần có | — | 0/3 | **3/3** |
| Join precision | — | — | **1,00** (3 ghép, 0 sai) |
| False merge (ghép sai) | — | 0 | **0** |
| False deletion (từ hợp lệ bị mất so với Standard) | — | — | **0** |
| Bảng giống hệt Standard | — | — | **có** (2/2 fixture bảng) |
| Thời gian (tổng 24 fixture, trung vị 5 lần) | — | 25,7 ms | 53,2 ms |
| Peak RAM của normalizer (tracemalloc) | — | — | 151 KiB (fixture lớn nhất) |

Ghi chú:
- CER Direct OCR cao ở f14 (đo cả header/footer mà ground truth không tính), f12 (hai cột), f16/f17 (con dấu đỏ,
  chữ ký) — đó là chất lượng **nhận dạng**, không liên quan normalizer.
- Fixture f03 (OCR mất chữ "số"): Legal ghép đoạn nhưng **không thêm** chữ; CER 0,033 do chính chữ thiếu.
- Fixture f12 (hai cột): cả Standard và Legal đọc theo hàng — giới hạn thứ tự đọc của Docling, Legal không sửa.
- Fixture f15: ảnh sơ đồ lớn không chữ giữ placeholder + cảnh báo `picture_without_text` (đúng yêu cầu "không bỏ
  qua biểu đồ/sơ đồ một cách âm thầm").

## 3. Chi phí xử lý

| Tài liệu | Standard export | Legal | Ghi chú |
|---|---|---|---|
| 24 fixture (1–4 trang) | 0,3–2,3 ms / tài liệu | 1,1–4,0 ms / tài liệu | |
| 300 trang, 4.800 item | 541 ms | 747 ms | ~2,5 ms/trang |

Phiên bản đầu có bước "ngoài cùng" bậc hai (10,3 s cho 300 trang) — đã sửa thành tuyến tính trước khi chốt (đo lại
ở dòng trên). So với thời gian OCR của Docling trên CPU (cỡ giây mỗi trang — số đo production ở
[OCR_REAL_DOCUMENT_BENCHMARK.md](OCR_REAL_DOCUMENT_BENCHMARK.md)), chi phí chuẩn hóa ước tính **< 1%** thời gian pipeline,
dưới ngưỡng 10% của release gate. Đây là **ước tính** — overhead thực trên pipeline đầy đủ: NOT VERIFIED, đo bằng
`docling_s` và `legal_ms` trong `compare.json` trên Windows Local. Lưu ý: khi bật Legal với RapidOCR mặc định, tài
liệu đi qua lớp Docling của ChatBot5400 có thêm `pdf_prep` (dò hướng trang) — chi phí này cũng phải đo ở Local.

## 4. Theo từng fixture (rút gọn)

| Fixture | CER Std → Legal | Marker | `<!-- image -->` | Dòng số | Đánh số lại |
|---|---|---|---|---|---|
| f01 quyết định 1 trang | 0,089 → 0 | 2/5 → 5/5 | 2 → 0 | 0 → 0 | 0 |
| f02 khoản 9 qua trang (ví dụ người dùng) | 0,082 → 0 | 3/3 → 3/3 | 1 → 0 | 2 → 0 | 0 |
| f03 OCR mất chữ cuối trang | 0,044 → 0,033 | 1/1 | 0 | 2 → 0 | 0 |
| f04 khoản mới không được nối | 0,059 → 0 | 2/4 → 4/4 | 0 | 3 → 0 | 0 |
| f05 danh sách bắt đầu 5/10, không liên tục | 0,008 → 0 | 3/5 → 5/5 | 0 | 0 | 2 → 0 |
| f06 danh sách nhiều cấp | 0,070 → 0 | 2/12 → 12/12 | 0 | 0 | 0 |
| f07 Phần/Chương/Mục/Điều | 0,021 → 0 | — | 0 | 2 → 0 | 0 |
| f08 trường nghiệp vụ | 0,011 → 0 | — | 0 | 4 → 2 (`2024`, `15` giữ) | 0 |
| f09 bảng | 0 → 0 | — | 0 | 0 | 0 |
| f10 bảng qua 2 trang | 0,026 → 0 | — | 0 | 2 → 0 | 0 |
| f13 footnote | 0,028 → 0 | — | 0 | 2 → 0 | 0 |
| f14 header/footer lặp 4 trang | 1,143 → 0 | — | 0 | 0 | 0 |
| f15 ảnh lớn + con dấu có chữ | 0,293 → 0,163 | — | 2 → 1 | 0 | 0 |
| f16 chữ OCR nằm trong ảnh | 0,918 → 0 | — | 1 → 0 | 0 | 0 |
| f17 khối chữ ký | 0,269 → 0 | — | 2 → 0 | 0 | 0 |
| f21 đoạn bắt đầu bằng gạch/số | 0,022 → 0 | 1/3 → 3/3 | 0 | 0 | 1 → 0 |

Các fixture còn lại (f11, f12, f18, f19, f20, f22, f23, f24) — xem JSON.

## 5. Kết luận

Trên bộ fixture tổng hợp, chế độ Legal đạt mọi tiêu chí **bảo toàn** (0 từ bị mất, 24/24 trường nghiệp vụ, 33/33
marker, bảng giống hệt, 0 ghép sai) và loại bỏ toàn bộ artifact có đủ bằng chứng. Chất lượng trên **tài liệu thật**
và với **Agri**: chưa đo (PENDING Windows Local).
