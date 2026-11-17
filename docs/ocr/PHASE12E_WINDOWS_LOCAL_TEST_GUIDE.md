# Phase 12E — Hướng dẫn nghiệm thu trên Windows Local

Mục tiêu: chạy **pipeline thật** (Layout Heron, TableFormer, các engine, **Agri của bạn**) trên tài liệu thật, **chỉ
trên máy Windows**, với một stack thử nghiệm cô lập, rồi so sánh Direct OCR / Standard / Legal. Không dùng database,
tài khoản hay dữ liệu production. Kết quả chứa nội dung tài liệu ⇒ **chỉ lưu trên máy này**, không upload.

Stack: compose project `chatbot5400-phase12-test`, web `http://127.0.0.1:8504`, API `http://127.0.0.1:5057`,
database riêng (không có cổng host), thư mục dữ liệu `deploy\phase12-test\{surreal_data,notebook_data}`.

## 0. Yêu cầu

- Windows 10/11, Docker Desktop (WSL2, **Linux containers**), Git for Windows, PowerShell 5.1+ hoặc 7.
- ≥ 30 GB trống, ≥ 16 GB RAM (stack giới hạn 10 GB cho ứng dụng; chỉnh `PHASE12_MEMORY` trong `.env`).
- Internet cho lần build đầu (pip/npm/Hugging Face) — đây là máy thử nghiệm, không phải production.
- Nếu PowerShell chặn script: `Set-ExecutionPolicy -Scope Process Bypass` (chỉ phiên hiện tại).

## 1. Lấy nhánh Phase 12

```powershell
git clone https://github.com/nghoainam1902ps4-lgtm/ChatBot5400-Version02.git
cd ChatBot5400-Version02
git fetch origin
git checkout claude/sweet-feynman-92jg8j
git log -1 --oneline
```

(Nếu nhánh `feature/legal-document-normalization` đã được đẩy lên, có thể checkout nhánh đó — cùng nội dung.)

## 2. Khởi động stack thử nghiệm

```powershell
.\scripts\windows\phase12-test.ps1 check
```

```powershell
.\scripts\windows\phase12-test.ps1 init-env
```

`init-env` tạo `deploy\phase12-test\.env` với mật khẩu / khóa **ngẫu nhiên mới** (không hiển thị), cổng 8504/5057,
`OCR_LEGAL_NORMALIZATION_ENABLED=true`, `PHASE12_FONT_DIR=C:/Windows/Fonts`, và các thư mục `import\`,
`diagnostics\`. Không dùng lại thông tin production.

```powershell
.\scripts\windows\phase12-test.ps1 build
```

```powershell
.\scripts\windows\phase12-test.ps1 up
```

Build lần đầu 20–60 phút (image có sẵn Docling + EasyOCR + Tesseract — cùng profile với gói offline). Mở
`http://127.0.0.1:8504`, tạo tài khoản quản trị **thử nghiệm** (không dùng tài khoản production).

Lần đầu cần tải model Docling/RapidOCR/Tesseract (có Internet): **Cài đặt → OCR Engine Manager** → *Cài đặt* /
*Chuẩn bị* cho Tesseract Fast, Best (và EasyOCR nếu muốn so) → đợi "Sẵn sàng". Hoặc:

```powershell
docker compose -p chatbot5400-phase12-test -f deploy\phase12-test\docker-compose.yml exec -T open_notebook /app/.venv/bin/python -m open_notebook.ocr.cli prepare --engines rapidocr tesseract_fast tesseract_best
```

Bash (WSL2) tương đương: `scripts/ocr/phase12-test.sh check|init-env|build|up …` (cùng tên hành động).

## 3. Import và chọn model Agri

```powershell
.\scripts\windows\phase12-test.ps1 import-agri -Model C:\duong\dan\vie_agri.traineddata -Version v1
```

Script in SHA-256 của file trên máy bạn, chép vào `import\` (mount **chỉ đọc** trong container) và chạy
`ocr custom import`. So dòng `stored … sha256 …` với SHA-256 vừa in. Rồi kích hoạt:

```powershell
.\scripts\windows\phase12-test.ps1 activate-agri -Version v1
```

Trên giao diện: card **Tesseract Vietnamese Agri** → *Kiểm tra* → *Sử dụng* (xác nhận "Thử nghiệm"). Model chỉ nằm
trong `deploy\phase12-test\notebook_data` (bị `.gitignore`).

## 4. So sánh ba chế độ bằng một lệnh

Chép PDF cần thử vào `deploy\phase12-test\import\` (có thể kèm `ten.gt.txt` là văn bản đúng để tính CER/WER):

```powershell
.\scripts\windows\phase12-test.ps1 compare -Pdf qd-mau.pdf -Engine tesseract_agri
```

Cả thư mục:

```powershell
.\scripts\windows\phase12-test.ps1 compare -Pdf . -Engine tesseract_agri
```

Với tài liệu có watermark nghiêng, thêm `-FullPage` để so chế độ OCR toàn trang. Lặp lại với `-Engine
tesseract_best`, `rapidocr`, `tesseract_fast`, `easyocr` để đối chiếu.

Kết quả: `deploy\phase12-test\diagnostics\compare-<thời điểm>\compare.md` (bảng) + một thư mục chẩn đoán cho
mỗi PDF. **Một lần OCR** cho mỗi tài liệu; Standard và Legal được tạo từ **cùng** `DoclingDocument`; Tesseract chạy
trực tiếp trên cùng trang để tham chiếu.

| Cột trong `compare.md` | Ý nghĩa | Kỳ vọng ở Legal |
|---|---|---|
| `placeholders_*` | số `<!-- image -->` | chỉ còn ảnh lớn không chữ |
| `numeric_lines_*` | dòng chỉ có chữ số (số trang lọt) | giảm; số còn lại phải là nội dung thật |
| `renumbered_*` | mục danh sách trình duyệt vẽ khác số gốc | 0 |
| `joins`, `page_numbers_removed`, `headers_footers_removed` | phép biến đổi | kiểm từng phép trong `09_legal_report.json` |
| `picture_text_recovered` | chữ OCR nằm trong vùng ảnh mà Standard bỏ | — |
| `page_end_words_lost_*` | số trang mà từ cuối trang của Tesseract trực tiếp không có trong kết quả | phải giải thích được (xem §5) |
| `cer_*`, `wer_*` | khi có `.gt.txt` | Legal ≤ Standard; không thấp hơn nhờ xóa nội dung |
| `legal_ms`, `docling_s` | chi phí | `legal_ms` ≪ 10% của `docling_s` |

## 5. Chẩn đoán từng tầng (một tài liệu)

```powershell
.\scripts\windows\phase12-test.ps1 diagnose -Pdf qd-mau.pdf -Engine tesseract_agri
```

Đọc theo thứ tự (`diagnostics\diagnose-<thời điểm>\`):

1. `12_summary.json` → `words_per_layer`: số từ ở Tesseract trực tiếp → ô OCR → cluster layout → phần tử ghép →
   item Docling → hiển thị Standard → hiển thị Legal. **Tầng đầu tiên số từ giảm mạnh là nơi mất chữ.**
2. "Thiếu từ cuối trang": `page_end_words_in_standard` → trang nào `last_words_found: false`, từ nào `missing`;
   tìm từ đó trong `01_tesseract_pXXX.txt` (không có ⇒ lỗi nhận dạng, tầng A), `02_ocr_cells.json` (có ở cells
   nhưng không ở `03_layout_clusters.json` ⇒ ô nằm ngoài vùng layout, tầng C/D), `06_items.json` (con của
   `#/pictures/…` ⇒ chữ trong vùng ảnh, Legal đã lấy lại).
3. Số trang lọt: tìm dòng số trong `06_items.json` → `label` (TEXT ⇒ layout gán sai), `prov.bbox`.
4. Marker: `06_items.json` → `marker`, `enumerated` của từng `ListItem`; so `10_display_standard.txt` với
   `10_display_legal.txt`.
5. Mỗi phép của Legal: `09_legal_report.json` (`op`, `reason`, `pages`, `bboxes`, `text_before`, `text_after`).
6. Tầng H/I (đã lưu và hiển thị): tải PDF lên giao diện ở chế độ cần thử, lấy Source ID trong URL, rồi chạy trong
   container (token quản trị lấy từ trình duyệt, đặt vào biến môi trường, không in ra):

```powershell
docker compose -p chatbot5400-phase12-test -f deploy\phase12-test\docker-compose.yml exec -T -e PHASE12_API_TOKEN=<token> open_notebook /app/.venv/bin/python scripts/ocr/phase12_diagnose.py /import/qd-mau.pdf --engine tesseract_agri --out /phase12-out/stored-1 --source-id source:<id> --api-url http://127.0.0.1:5055
```

`12_summary.json` → `stored_source_equals` = `legal` / `standard` (nội dung đã lưu và được embedding là bản nào).

## 6. Kiểm tra chế độ trên giao diện

1. **Cài đặt → OCR Engine Manager → Chuẩn hóa văn bản sau OCR**: mặc định **Tiêu chuẩn**.
2. Tải PDF ở chế độ Tiêu chuẩn → xem nội dung (giống v1.2.0).
3. Chọn **Văn bản pháp lý** → *Lưu chế độ chuẩn hóa* → tải lại cùng PDF (tài liệu cũ không tự xử lý lại) → so sánh.
4. Hỏi chat trong notebook/Source về một khoản cụ thể (ví dụ "khoản 9 Điều 3 nói gì?") cho cả hai bản.
5. Mobile: mở cùng trang trên điện thoại (hoặc DevTools 390 px) — mục cài đặt và nội dung hiển thị đúng.

## 7. Rollback về Standard

Giao diện: chọn **Tiêu chuẩn** → Lưu. Hoặc tắt cổng (toàn stack):

```powershell
.\scripts\windows\phase12-test.ps1 legal-gate -State off
```

Kiểm tra: mục cài đặt báo "Chưa bật trên máy chủ này", tài liệu mới được xử lý Standard. Bật lại: `-State on`.

## 8. Fixture tổng hợp (không chứa dữ liệu thật)

```powershell
.\scripts\windows\phase12-test.ps1 fixtures
```

Tạo `diagnostics\fixtures\*.scan.pdf`, `*.watermark.pdf` + `*.gt.txt` (24 tài liệu, font Windows mount chỉ đọc).
Biến thể có lớp text / OCR ẩn / hỗn hợp cần `reportlab` trên máy host:
`uv run --with reportlab python scripts/ocr/generate_phase12_fixtures.py --out .\phase12-fixtures --all --font-dir C:\Windows\Fonts`.
Chép các PDF muốn thử vào `import\` rồi `compare -Pdf <tên>`.

## 9. Dừng / dọn

```powershell
.\scripts\windows\phase12-test.ps1 stop
```

Dữ liệu được giữ. Script **không** xóa volume hay thư mục; muốn xóa hẳn stack thử nghiệm thì tự xóa
`deploy\phase12-test\{surreal_data,notebook_data,diagnostics,import}` bằng tay sau khi chắc chắn.

## 10. Biên bản nghiệm thu (điền trên máy Local, không commit nội dung tài liệu)

| Hạng mục | Kết quả |
|---|---|
| Stack cô lập, cổng 8504/5057 loopback, DB riêng | ☐ |
| Agri import, SHA-256 khớp, kích hoạt, "Sẵn sàng offline" | ☐ |
| Standard = kết quả v1.2.0 (cùng tài liệu) | ☐ |
| Legal: không mất nội dung hợp lệ (so `10_display_*`) | ☐ |
| Legal: số điều/khoản/điểm đúng như bản giấy | ☐ |
| Legal: trường nghiệp vụ (số hiệu, ngày, tiền, %) khớp | ☐ |
| Legal: bảng không hỏng | ☐ |
| Legal: không ghép sai đoạn (kiểm `join_across_pages` trong `09_legal_report.json`) | ☐ |
| Nguyên nhân "thiếu từ cuối trang" đã xác định (tầng nào) | ☐ |
| `legal_ms` < 10% `docling_s` | ☐ |
| Rollback về Standard hoạt động | ☐ |
