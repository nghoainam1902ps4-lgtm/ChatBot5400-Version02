# Hướng dẫn benchmark trên tài liệu nghiệp vụ thật (thực hiện tại chỗ)

Cập nhật: 2026-11-13 (Phase 9A)

**Trạng thái: CHƯA THỰC HIỆN.** Mọi số liệu trong `docs/ocr/` đến nay là trên dữ liệu **tổng hợp**. Không
tài liệu nghiệp vụ thật nào được tìm, đọc hay đo trong quá trình phát triển. Benchmark này do chủ dự án tự
chọn tài liệu và tự chạy trên máy chủ.

## 1. Nguyên tắc an toàn

- Chạy trong một phiên shell thường trên máy chủ. **Không** chạy bên trong phiên trợ lý AI có kết nối ra
  ngoài, không dán tài liệu, văn bản OCR, số tài khoản, số tiền hay tên khách hàng vào bất kỳ prompt, chat,
  ticket hay log nào gửi ra ngoài.
- Công cụ `scripts/ocr/local_document_benchmark.py` chỉ ghi **số liệu tổng hợp**: tỉ lệ, số đếm, thời gian.
  Nó không lưu văn bản nhận dạng được, không lưu ground truth, không lưu giá trị trường khóa, và thay tên
  file bằng `doc-001`, `doc-002`… (unit test `tests/test_ocr_local_benchmark.py` giữ bảo đảm này).
- Thư mục tài liệu và các file `.gt.txt` nằm ngoài repository, quyền chỉ người thực hiện đọc được, và được
  xóa hoặc lưu theo quy định của đơn vị sau khi đo.
- Không commit tài liệu, ground truth hay kết quả chi tiết. Chỉ bảng tổng hợp mới được đưa vào biên bản.
- Không dùng `--keep-names` với tài liệu thật.

## 2. Chọn tài liệu

Đề xuất 5–10 tài liệu mỗi nhóm, đặt mỗi nhóm một thư mục con (tên thư mục là tên nhóm trong báo cáo):

| Thư mục | Loại | Cần xem gì |
|---|---|---|
| `cong_van/` | Công văn | Số hiệu, ngày, nội dung chính |
| `quyet_dinh/` | Quyết định | Tiêu đề in đậm, điều khoản, số hiệu |
| `quy_dinh/` | Quy định, quy chế nhiều trang | Thứ tự đọc, thời gian mỗi trang |
| `bang_scan/` | PDF scan có bảng | Số tiền, ngày, nhãn dòng, cấu trúc bảng |
| `so_hieu_ngay/` | Văn bản nhiều số hiệu và ngày tháng | Trường khóa |
| `tieu_de_dam/` | Văn bản có tiêu đề in đậm chữ hoa | Mất dấu ở tiêu đề (giới hạn KL-1) |
| `chat_luong_thap/` | Bản photo, fax, scan mờ hoặc nghiêng | Mức suy giảm |

Nên có cả bản scan 150, 200 và 300 DPI nếu thực tế đơn vị có.

## 3. Chuẩn bị dữ liệu đối chiếu (tùy chọn nhưng nên có)

Bên cạnh mỗi `ten.pdf`, người thực hiện có thể tạo:

| File | Nội dung | Cho ra chỉ số |
|---|---|---|
| `ten.gt.txt` | Văn bản đúng, do người gõ lại (không lấy từ kết quả OCR) | CER, WER, word recall, độ chính xác dấu |
| `ten.fields.txt` | Mỗi dòng một giá trị **phải đọc đúng tuyệt đối**: số tiền, ngày, số hiệu | số trường tìm thấy / tổng số |
| `ten.headings.txt` | Mỗi dòng một tiêu đề in đậm | đúng / chỉ mất dấu / mất hẳn |

Không có file nào thì công cụ vẫn chạy và báo số trang, thời gian, số bảng, số trang được xoay. Chỉ
`fields.txt` cho 3–5 tài liệu mỗi nhóm đã đủ để trả lời câu hỏi quan trọng nhất: số tiền, ngày và số hiệu
có được đọc đúng không.

## 4. Chạy

Trên máy chủ, trong môi trường đã cài engine cần đo (hoặc trong container ứng dụng):

```bash
cd /app                                   # trong container; hoặc thư mục mã nguồn
DOCS=/duong/dan/rieng/tai-lieu-benchmark   # thư mục ngoài repository
OUT=/duong/dan/rieng/ket-qua; mkdir -p "$OUT"
uv run --no-sync python scripts/ocr/local_document_benchmark.py --dir "$DOCS" \
    --engines tesseract_best rapidocr \
    --out "$OUT/benchmark.json" --markdown "$OUT/benchmark.md"
```

Thêm `tesseract_fast` vào `--engines` nếu muốn so tốc độ. Không cần đo EasyOCR (mức thử nghiệm).

## 5. Đọc kết quả

Bảng `benchmark.md` có một dòng cho mỗi engine × nhóm:

| Cột | Ý nghĩa | Gợi ý đánh giá |
|---|---|---|
| Trường khóa | số giá trị trong `fields.txt` được đọc đúng tuyệt đối | Mục tiêu cho tài liệu tài chính: **tất cả**. Bất kỳ số tiền, ngày hay số hiệu nào sai cần được xem xét trước khi dùng engine đó cho loại tài liệu này |
| CER / WER / Word recall | độ chính xác ký tự / từ so với `gt.txt` | Trên dữ liệu tổng hợp, Tesseract Best đạt CER 0,00–0,03 với văn bản và 0,03–0,15 với bảng |
| Dấu | tỉ lệ từ có dấu được giữ đúng dấu | Thấp ở RapidOCR là đã biết |
| Tiêu đề đúng / mất dấu / mất | theo `headings.txt` | "Mất dấu" là giới hạn đã chấp nhận (KL-1) khi nội dung còn lại đúng; "mất" thì không |
| Bảng | số bảng nhận ra | So với số bảng thật trong tài liệu |
| Giây/trang | thời gian trung bình | Tham khảo: 4–7 giây/trang trên máy 8 CPU |
| Lỗi | tài liệu không xử lý được | Phải bằng 0; nếu không, xem log ứng dụng (không sao chép nội dung tài liệu) |

Tiêu chí chấp nhận là quyết định của chủ dự án. Đề xuất tối thiểu cho Tesseract Vietnamese Best: trường
khóa đạt 100 % ở các nhóm công văn, quyết định, bảng scan chất lượng thường; không có tài liệu lỗi; tiêu đề
không "mất".

## 6. Biên bản

Ghi vào biên bản nội bộ (không cần đưa lên GitHub): ngày, người thực hiện, commit, engine, số tài liệu mỗi
nhóm, bảng `benchmark.md`, kết luận chọn engine, các loại tài liệu không nên dùng OCR tự động. Chỉ sau khi
có biên bản này mới đánh dấu mục A2 trong [OCR_PRODUCTION_CHECKLIST.md](OCR_PRODUCTION_CHECKLIST.md).
