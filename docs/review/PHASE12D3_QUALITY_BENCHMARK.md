# Phase 12D3 — Quality benchmark với oracle đã sửa (BEFORE / AFTER)

Thay thế `docs/ocr/PHASE12D_QUALITY_BENCHMARK.md`. **Các con số của Phase 12 ("0 từ bị mất", "join precision 1,00",
"trường nghiệp vụ 24/24") không còn được dùng**: chúng được tạo bằng một phép đo cộng lại chính phần mà bộ chuẩn hóa
đã xóa (audit 12D2, finding T-01).

Số liệu thô: [`../ocr/phase12/benchmark_synthetic.json`](../ocr/phase12/benchmark_synthetic.json) (schema
`chatbot5400-phase12-benchmark/2`). Tạo lại:

```bash
git show 2ef0074:open_notebook/ocr/legal_normalizer.py > /tmp/legal_normalizer_v100.py
```

```bash
uv run python scripts/ocr/generate_phase12_fixtures.py --out /tmp/phase12-fixtures
```

```bash
uv run python scripts/ocr/phase12_benchmark.py --out docs/ocr/phase12/benchmark_synthetic.json --repeats 5 --before /tmp/legal_normalizer_v100.py --pdf-dir /tmp/phase12-fixtures --tesseract-lang vie
```

## 1. Đo cái gì — và không đo cái gì

| Phép đo | Đầu vào | Đo | **Không** đo |
|---|---|---|---|
| **Cấu trúc** | 45 fixture tổng hợp; `DoclingDocument` do **ReadingOrderModel thật của Docling 2.129.0** dựng từ bố cục khai báo | tác động của serializer / normalizer lên văn bản đã đúng 100% | OCR, Layout Heron, TableFormer |
| **Nhận dạng** | PDF scan 200 DPI vẽ từ cùng fixture | Tesseract 5.3.4 (Ubuntu) `vie`, `--psm 3` | Tesseract 5.5.0 + tessdata fast / best / **Agri** của production |

**Pipeline đầy đủ trên PDF thật: CHƯA ĐO.** Cloud không tải được Layout Heron / TableFormer, không có model Agri,
không có PDF nghiệp vụ. Mọi số dưới đây mô tả hành vi trên bố cục **tổng hợp do tôi khai báo**; chúng không nói gì về
việc Heron gắn nhãn gì cho header / số trang trên scan thật. Cổng: W-RC, W-LEG, W-PIPE-05.

### Oracle

Mỗi phần tử của fixture mang nhãn sự thật khai báo `gt`: bắt buộc (mặc định) · `artifact` (được phép vắng) · `join`
(được phép nối vào đơn vị trước) · `furniture`. `scripts/ocr/phase12_metrics.py::preservation` so **từng dòng người
dùng nhìn thấy** (dựng lại bằng CommonMark, gồm cả số mà trình duyệt vẽ cho danh sách) với danh sách đó:

| Chỉ số | Định nghĩa |
|---|---|
| False deletion (đơn vị / token) | đơn vị bắt buộc không được hiển thị đúng số lần khai báo; token bắt buộc vắng mặt (đa tập) |
| False insertion | dòng / token hiển thị không thuộc sự thật khai báo (ví dụ số do trình duyệt đánh lại) |
| False merge | một dòng hiển thị chứa ≥ 2 đơn vị không được phép nối |
| False reordering | số đơn vị nằm ngoài dãy con tăng dài nhất theo thứ tự khai báo |
| Trường trọng yếu | số hiệu, ngày, tiền, %, URL, mã… phải xuất hiện **đúng số lần** |
| Artifact đã loại / Phép nối đã làm | so với số được phép — **không** bắt buộc đạt tối đa |

Oracle không đọc báo cáo của normalizer và không so hai đầu ra với nhau. Nó có khả năng thất bại:
`test_oracle_sees_deletion_merge_insertion_and_reordering`, `test_oracle_sees_a_repeated_line_deleted_once`, và chính
bảng dưới (Standard và Legal v1.0.0 đều bị bắt lỗi).

## 2. Kết quả (45 fixture, 273 đơn vị bắt buộc)

| Chỉ số | Ground truth | Standard (v1.2.0) | Legal **trước** remediation (v1.0.0) | Legal **sau** remediation (v1.1.0) |
|---|---|---|---|---|
| False deletion — đơn vị | 0 | 27 | **53** | **0** |
| False deletion — token | 0 | 39 | **170** | **0** |
| Tài liệu có xóa nhầm | 0 | 9 / 45 | **13 / 45** | **0 / 45** |
| False merge | 0 | 0 | **6** (6 tài liệu) | **0** |
| False insertion — dòng / token | 0 | 22 / 22 | 0 / 0 | 0 / 0 |
| False reordering | 0 | 1 | 1 | 1 |
| Trường trọng yếu đúng số lần | 47 / 47 | 44 / 47 | **36 / 47** | **47 / 47** |
| Marker Khoản / Điểm hiển thị như gốc | 36 / 36 | 17 / 36 | 36 / 36 | 36 / 36 |
| Mục danh sách bị trình duyệt đánh lại số | 0 | 3 / 30 | 0 | 0 |
| Bảng giữ nguyên (11 dòng bảng) | có | có | có | có (và giống hệt Standard) |
| Artifact đã loại (trên 47 được phép) | — | 0 | 45 | **24** |
| Phép nối đã làm (trên 5 được phép) | — | 1 ¹ | 5 | **3** |
| `<!-- image -->` còn lại | — | 13 | 2 | 4 |
| Dòng chỉ có chữ số trong nội dung | — | 54 | 7 | 34 ² |
| CER / WER trung bình so với ground truth ³ | 0 | 0,106 / 0,126 | 0,060 / 0,061 | 0,051 / 0,060 |
| Thời gian, tổng 45 fixture (trung vị 5 lần) | — | 66,7 ms | — | 152,1 ms |
| Peak RAM của normalizer (tracemalloc) | — | — | — | 193 KiB |

¹ Phép nối của chính Docling (đoạn trước kết thúc bằng ký tự ASCII) — có ở v1.2.0.
² 34 dòng số còn lại gồm số trang được **giữ có chủ ý** (văn bản 1–2 trang, thiếu bằng chứng) và số là nội dung hợp lệ
(năm, số khoản tách rời, số lượng). 13 tài liệu có cảnh báo `page_number_kept`.
³ CER / WER là chỉ số phụ: nhạy với tiền tố danh sách và artifact được giữ; dữ liệu nghiệm thu là các dòng phía trên.

Đọc bảng:

- **Mục tiêu bảo toàn nội dung đạt trên bộ đo này**: v1.1.0 không xóa nhầm, không nối sai, không chèn thêm, đủ trường
  trọng yếu. Bản v1.0.0 (đã được báo cáo là "0 từ bị mất") thực tế xóa 53 đơn vị và làm sai 11 trường trọng yếu.
- **Cái giá**: v1.1.0 loại ít artifact hơn (24 so với 45) và nối ít hơn (3 so với 5). Đây là hệ quả trực tiếp của
  nguyên tắc "giữ nội dung trừ khi có bằng chứng mạnh" và được chấp nhận trong quyết định D-36.
- **Chế độ Standard cũng không hiển thị đúng bản gốc** ở 9 tài liệu (27 đơn vị): 3 tài liệu mất chữ OCR nằm trong
  vùng ảnh (f15, f16, f40 — 31 token thật sự vắng mặt), 6 tài liệu hiển thị dòng danh sách khác bản gốc (thêm dấu
  chấm đầu dòng trước `a)`, `1.1`, `-`; số bị trình duyệt đánh lại `7.` → `6.`, `13.` → `12.`), nên cũng có 22 dòng
  "chèn thêm". Đây là hành vi của v1.2.0, không thay đổi trong Phase 12.
- Lỗi thứ tự duy nhất (f12, hai cột) là thứ tự đọc của Docling, giống nhau ở cả ba cột.

### 2.1 Bản v1.0.0 sai ở đâu (đo bằng oracle mới)

| Fixture | Đơn vị / token bị xóa | Nối sai | Trường trọng yếu | Finding |
|---|---|---|---|---|
| f25 phụ lục, dòng "Đơn vị tính" mỗi trang | 3 / 15 | 0 | 2 / 3 | F-01 |
| f26 bộ thông báo một trang | 8 / 68 | 0 | 2 / 4 | F-01 |
| f35 bảng không kẻ khung lặp tiêu đề cột | 16 / 24 | 0 | 0 / 4 | F-01 |
| f37 dòng nghiệp vụ lặp lại | 8 / 56 | 0 | 2 / 4 | F-01 |
| f27 năm ở cuối trang | 2 / 2 | 0 | 0 / 2 | F-02 |
| f28 số khoản ở đầu trang | 2 / 2 | 0 | — | F-02 |
| f34 số khoản tách rời, 5 trang | 3 / 3 | 0 | — | F-02 |
| f29 footnote nhãn TEXT | 2 / 0 | 1 | 1 / 1 | F-03 |
| f30 footer văn bản 2 trang | 1 / 0 | 1 | — | F-03 |
| f31 điểm `a.`, `a/`, `đ.` | 2 / 0 mỗi fixture | 1 mỗi fixture | — | F-03 |
| f38 hai cột qua trang | 2 / 0 | 1 | — | F-03 |

(Với các dòng "x / 0": không token nào mất nhưng hai đơn vị bị gộp thành một dòng nên cả hai đều không còn hiển thị
như khai báo.)

### 2.2 Bản v1.1.0 cố ý KHÔNG làm gì

| Fixture | Trang | Không làm | Cảnh báo |
|---|---|---|---|
| f02, f03, f20 | 2 | không bỏ số trang; f02, f03 không nối khoản bị cắt | `page_number_kept`, `join_not_made` |
| f07, f08, f10, f13 | 2 | không bỏ số trang | `page_number_kept` |
| f11 (có trang trắng) | 3 | không bỏ số trang (chỉ 2 trang có số) | `page_number_kept` |
| f22 | 1 | không bỏ số trang | `page_number_kept` |
| f14 header / footer chạy nhãn TEXT | 4 | bỏ 4 "Trang n/4", **giữ** 4 dòng chữ lặp | `repeated_line_kept` |
| f30 footer văn bản 2 trang | 2 | giữ footer, không nối | `join_not_made` |

Số tài liệu có cảnh báo: `page_number_kept` 13 · `join_not_made` 6 · `repeated_line_kept` 5 · `picture_without_text` 2
· `hyphen_at_page_break_not_joined` 1. Cảnh báo được lưu cùng Source và hiển thị số lượng trên trang Source.

## 3. Nhận dạng trực tiếp (Tesseract 5.3.4, `vie`) — tham khảo

| Tài liệu | CER | WER | Text recall | Trường trọng yếu khớp nguyên văn |
|---|---|---|---|---|
| 45 PDF scan tổng hợp | 0,069 | 0,085 | 0,973 | 43 / 47 |

Đây là chất lượng **nhận dạng** của một engine trên ảnh tổng hợp sạch; chuẩn hóa không thể và không được cải thiện nó.
Không dùng để suy ra chất lượng trên scan thật hay với model Agri.

## 4. Hiệu năng (F-10)

Tài liệu dựng trong bộ nhớ (`tests/test_ocr_legal_normalizer.py::_big`), tốt nhất của 3 lần, một lõi, máy Cloud.

| Tài liệu | Item | Standard export | Legal v1.0.0 | Legal v1.1.0 |
|---|---|---|---|---|
| 125 trang, mỗi trang một phép nối | 1 875 | 0,19 s | 1,40 s | 0,30 s |
| 250 trang, mỗi trang một phép nối | 3 750 | 0,59 s | 3,01 s | 0,88 s |
| 500 trang, mỗi trang một phép nối | 7 500 | 1,02 s | 9,93 s | 1,76 s |
| 300 trang: nối + bảng + ảnh | 5 100 | 0,66 s | 4,94 s | 1,18 s |
| 300 trang: header chạy nhãn TEXT | 4 800 | 0,56 s | 4,60 s (299 nối) | 1,06 s (0 nối — header được giữ chặn nối) |
| 3 trang × 1 000 item ngắn trong dải | 3 045 | 0,32 s | 0,75 s | 0,68 s |
| 3 trang × 3 000 item ngắn trong dải | 9 045 | 1,06 s | 2,56 s | 2,21 s |
| 3 trang × 6 000 item ngắn trong dải | 18 045 | 2,04 s | — | 4,23 s |

- v1.0.0: gấp đôi số trang ⇒ ~3,3× thời gian (250 → 500 trang); v1.1.0: ~2,0× (tuyến tính). Nguyên nhân đã bỏ:
  `delete_items` của docling-core cho mỗi phép nối.
- Chi phí thêm của v1.1.0 so với Standard: khoảng 1,5–3,5 ms / trang ở các trường hợp trên.
- Ngân sách thời gian 30 s và giới hạn số item ⇒ vượt thì fallback Standard, trạng thái *Chuẩn hóa thất bại, sử dụng
  bản tiêu chuẩn* (`test_time_budget_falls_back`, `test_limits_fall_back`).
- Thời gian này nhỏ so với OCR + layout của cùng tài liệu (hàng phút), nhưng **tổng thời gian job trên pipeline thật
  chưa đo** (W-LEG-14).

## 5. Kết luận

| Câu hỏi | Trả lời |
|---|---|
| Legal v1.1.0 có xóa nhầm, nối sai, chèn thêm trên bộ đo không? | Không (0 / 0 / 0 trên 45 fixture, 273 đơn vị, 47 trường trọng yếu) |
| Bộ đo có thấy được lỗi không? | Có: bắt 53 xóa nhầm + 6 nối sai của v1.0.0, 27 + 22 của Standard |
| Kết quả này có chứng minh chất lượng trên văn bản thật không? | **Không.** Bố cục là tổng hợp; nhãn và bbox thật của Layout Heron, OCR thật, model Agri chưa tham gia |
| Standard có đổi so với v1.2.0 không? | Không (`test_convert_file_standard_is_byte_identical`) |
| Còn rủi ro chất lượng nào đã biết? | Ngưỡng là hằng số chưa hiệu chỉnh trên scan thật; header chạy nhãn TEXT được giữ và chặn phép nối; Docling tự nối / bỏ gạch nối ở một số đoạn (cả Standard) |
