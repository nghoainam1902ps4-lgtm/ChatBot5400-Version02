# Phase 12D2 — Checklist nghiệm thu Windows Local (bổ sung sau review)

Các mục dưới đây là những gì **không thể chạy trong Cloud** (không có Docker daemon, không tải được Layout Heron/TableFormer,
không có PowerShell, không có model Agri) hoặc là những nghi ngờ của review cần xác minh trên máy thật. Checklist này **bổ sung**
cho `docs/ocr/PHASE12E_WINDOWS_LOCAL_TEST_GUIDE.md`, không thay thế.

Quy ước: mỗi mục ghi **Đạt / Không đạt / Không chạy được** và đính kèm log. Không commit nội dung tài liệu thật, không dùng PDF
nghiệp vụ trong repository. Stack thử nghiệm là `deploy/phase12-test` (cổng loopback), **không phải production**.

Trạng thái sẵn sàng: **CONDITIONAL**.

- Chạy được ngay (không phụ thuộc bản sửa): nhóm W-STD, W-RC, W-PIPE, W-RAG, W-OFF-01..04, W-OFF-09.
- Chỉ chạy **sau Phase 12D3**: nghiệm thu chất lượng Legal (W-LEG), build gói bằng wrapper (W-OFF-05), cập nhật/rollback offline
  đầy đủ (W-OFF-06..08).

## 0. Chuẩn bị

Lấy nhánh review để có test phản ví dụ:

```powershell
git fetch origin review/phase12-fable-audit
```

```powershell
git switch review/phase12-fable-audit
```

Kiểm tra môi trường stack thử nghiệm:

```powershell
.\scripts\windows\phase12-test.ps1 check
```

## 1. W-STD — Standard không đổi so với v1.2.0

| Mã | Việc | Kỳ vọng |
|---|---|---|
| W-STD-01 | Xử lý cùng một PDF tổng hợp (`.\scripts\windows\phase12-test.ps1 fixtures`) trên image v1.2.0 và image Phase 12, cờ Legal **tắt** | `full_text` giống nhau từng byte |
| W-STD-02 | Cờ Legal **bật**, admin chọn **Tiêu chuẩn** | Giống W-STD-01 |
| W-STD-03 | Lặp lại W-STD-02 với từng engine: RapidOCR, Tesseract Fast, Tesseract Best, EasyOCR, Agri | Giống bản v1.2.0 cùng engine |
| W-STD-04 | OCR tắt; Force Full Page; `OCR_AUTO_FULL_PAGE_ON_WATERMARK=true` | Giống v1.2.0 |
| W-STD-05 | DOCX, ảnh PNG/JPEG, URL trang web khi Legal bật | Không đổi; log ghi "not applied" với nguồn không phải PDF |

## 2. W-RC — Xác minh nguyên nhân gốc trên pipeline thật

Dùng công cụ chẩn đoán từng tầng (mục 5 của hướng dẫn 12E) trên PDF tổng hợp dạng scan.

| Mã | Câu hỏi review chưa trả lời được | Cách kiểm |
|---|---|---|
| W-RC-01 | Layout Heron có gắn nhãn TEXT cho số trang không, tần suất? | Đếm item số trang theo nhãn trong `DoclingDocument` (JSON tầng layout) trên ≥ 20 trang |
| W-RC-02 | OCR có đặt text vào vùng PICTURE (con dấu, chữ ký) không; text đó là nội dung hay rác? | So `traverse_pictures` bật/tắt; liệt kê text con của ảnh |
| W-RC-03 | "Mất từ cuối trang": mất ở tầng nào (OCR, layout, reading order, serialize)? | So số từ từng tầng của công cụ chẩn đoán trên trang bị mất |
| W-RC-04 | Docling có tự ghép đoạn qua trang với từ tiếng Việt kết thúc bằng chữ có dấu không? | Fixture f02: bản Standard còn hai đoạn tách |
| W-RC-05 | Hai đường OCR (content-core Auto và lớp native RapidOCR) cho cùng văn bản thô? (F-15) | Standard với cấu hình mặc định so với Standard khi ép lớp native (đặt số luồng = 1) |

## 3. W-LEG — Chất lượng Legal (sau Phase 12D3)

Trước khi chạy: `uv run pytest tests/review_phase12d2 -q` phải PASS và **không còn** `xfail` cho F-01, F-02, F-03.

| Mã | Tình huống (PDF tổng hợp, in ra rồi scan hoặc render ảnh) | Kỳ vọng |
|---|---|---|
| W-LEG-01 | Phụ lục 3 trang, mỗi trang có "Đơn vị tính: triệu đồng" ở đầu (F-01) | Dòng đơn vị còn trong nội dung |
| W-LEG-02 | Bộ 4 thông báo một trang, cùng tên đơn vị ban hành và cùng ghi chú ký (F-01) | Còn đủ ở mỗi thông báo hoặc ít nhất lần đầu |
| W-LEG-03 | Bảng không kẻ khung có cột Năm/STT kết thúc ở cuối trang (F-02) | Không số nào bị mất |
| W-LEG-04 | Trang có footnote; trang 2 trang có footer "Lưu hành nội bộ" (F-03) | Không có câu ghép footnote/footer với thân |
| W-LEG-05 | Điểm đánh kiểu `a.`, `a/`, `đ.`, `(a)`, `a.1)` qua trang (F-03) | Mỗi điểm là một dòng riêng |
| W-LEG-06 | Ảnh 5%, 12%, 20% diện tích trang không có chữ (F-06) | Có placeholder hoặc cảnh báo cho 12% và 20% |
| W-LEG-07 | Khoản bắt đầu từ 5, 7, 13; danh sách không liên tục; lồng 1.1 / 1.1.1 | Số hiển thị đúng như bản gốc |
| W-LEG-08 | Văn bản hai cột; bảng kéo dài qua trang; trang trắng ở giữa; trang xoay 90°; trang khổ A3 lẫn A4 | Thứ tự đọc không đổi so với Standard; bảng giống hệt |
| W-LEG-09 | PDF hỗn hợp (trang điện tử + trang scan) | Không ghép sai giữa hai loại trang |
| W-LEG-10 | PDF 300 trang có nhiều đoạn cắt trang (F-10) | Ghi thời gian riêng của normalizer (dòng log "… in N ms") và tổng thời gian job |
| W-LEG-11 | Đổi chế độ Legal ↔ Tiêu chuẩn **trong lúc** một PDF dài đang xử lý | Job đang chạy giữ chế độ lúc bắt đầu; job sau dùng chế độ mới |
| W-LEG-12 | Hai tab trình duyệt admin cùng lưu chế độ khác nhau | Giá trị cuối cùng hiển thị nhất quán sau tải lại; khởi động lại container vẫn giữ |
| W-LEG-13 | Xem Source Legal trên trình duyệt thật, cả màn hình hẹp (F-16) | Ghi nhận mất thụt lề phân cấp; không có `\` hiển thị; không có `<!-- image -->` thừa; không thực thi HTML |

## 4. W-RAG — Nội dung lưu, chunk, embedding, chat

| Mã | Việc | Kỳ vọng |
|---|---|---|
| W-RAG-01 | Sau khi xử lý Legal: so nội dung trang Source, nội dung API `GET /api/sources/{id}`, và các chunk đã embed | Cùng một văn bản; không có bản Standard trong embedding |
| W-RAG-02 | Hỏi "khoản 9 quy định gì" ở Standard và Legal trên cùng tài liệu (F-17) | Truy hồi đúng chunk ở cả hai; câu trả lời không chứa `9\.` |
| W-RAG-03 | Đổi chế độ rồi mở lại Source cũ | Source cũ không đổi, không tự re-embed |
| W-RAG-04 | Ghi nhận: hệ thống **không** lưu số trang theo chunk | Không coi "trích dẫn trang" là tính năng đã có |

## 5. W-OFF — Gói cập nhật offline (Docker thật)

Thực hiện trên máy thử (Windows + Docker Desktop để build; Ubuntu/WSL2 thử nghiệm để cập nhật). **Không** chạy trên production.

| Mã | Việc | Kỳ vọng / điều cần ghi lại |
|---|---|---|
| W-OFF-01 | `docker info --format '{{.Driver}} {{.DriverStatus}}'` trên máy build và máy chủ thử | Ghi lại loại image store của hai bên |
| W-OFF-02 | Build image offline (`OCR_PREINSTALL_RUNTIMES=true`, `OCR_INSTALL_TESSERACT=true`); `docker run --rm --network none` chạy `inventory` | Docling, EasyOCR, Tesseract có trong image; ghi kích thước image |
| W-OFF-03 | **F-20**: `docker image inspect --format '{{.Id}}' <tag>` trên máy build; `docker save`; chép; `docker load`; inspect lại trên máy chủ thử | Hai ID **giống nhau**? Nếu khác: F-20 xác nhận, công cụ sẽ từ chối ở bước G |
| W-OFF-04 | **F-25**: tạo archive có 2 tag (`docker save tagA tagB`), load trên máy thử đã có `tagB` trỏ image khác | Ghi nhận `tagB` có bị đổi không |
| W-OFF-05 | **F-04** (sau 12D3): chạy `.\scripts\offline\build-package.ps1 -Version <ver>` và `build-package.sh` trong WSL2 | Tạo được gói; trước 12D3 dự kiến dừng ở "Refusing to create empty bundle" |
| W-OFF-06 | Chuỗi đầy đủ theo hướng dẫn Ubuntu §8: verify → preflight → update `--apply` → nghiệm thu → rollback app → update lại → finish | Trước/sau mỗi bước ghi `docker inspect` của container DB: `Id`, `Image`, `Mounts`, `State.StartedAt` **không đổi** (F-21); số Source/Notebook không đổi |
| W-OFF-07 | **F-11**: sau `finish`, chạy `docker compose -p <PROJECT> -f docker-compose.yml up -d` trong thư mục triển khai thử | Ghi nhận: container ứng dụng có bị tạo lại về image cũ không; `status.sh` có báo gì không |
| W-OFF-08 | Gián đoạn: `kill -9` tiến trình update ngay trong lúc `compose up`; rút nguồn VM khi đang ghi journal (F-13); chạy hai update song song; gọi rollback hai lần | Hệ thống phục hồi được bằng `rollback interrupted`; ghi lại thông báo |
| W-OFF-09 | Trong image offline: `ls /app/tiktoken-cache` và `python -c "import tiktoken; tiktoken.get_encoding('o200k_base')"` với `--network none` | Có file; lệnh chạy xong dưới 5 giây |
| W-OFF-10 | Chặn mạng thật (iptables DROP) rồi xử lý PDF với từng engine đã cài; `healthcheck.sh --prove-offline` | OCR chạy; không treo; log không có yêu cầu ra ngoài |
| W-OFF-11 | Máy chủ thử **chưa từng** dùng RapidOCR (F-22): cập nhật rồi chọn RapidOCR | Ghi nhận engine có dùng được offline không; journal bước `RAPIDOCR_weights` ghi gì |
| W-OFF-12 | Biến `http_proxy` đặt trong shell của root (F-26d) | Health check có báo sai không |
| W-OFF-13 | Rollback 1.3.0 → 1.2.0 khi DB đã lưu `ocr_text_normalization=legal` và có Source Legal | Bản 1.2.0 khởi động, cài đặt OCR mở được, Source Legal giữ nguyên nội dung, không OCR lại |
| W-OFF-14 | `ENABLE_CRAWL4AI=true` không có `CRAWL4AI_API_URL` trên máy offline | Ghi thời gian khởi động và log entrypoint (cố cài từ mạng) |

## 6. W-PIPE — Bộ test tự động trên máy có đủ model

```powershell
uv sync --extra docling
```

```powershell
uv run pytest tests/ -q
```

```powershell
uv run pytest tests/review_phase12d2 -q -rxX
```

Ghi lại: tổng PASS/FAIL/SKIP; danh sách FAIL theo tên; `test_signature_valid_and_invalid` phải **chạy** (cần `ssh-keygen`), không
được SKIP; `tests/test_chunking.py` có chạy xong không (trong Cloud file này treo vì
proxy chặn host tải bảng mã tiktoken).

## 7. Biên bản

| Nhóm | Đạt | Không đạt | Không chạy được | Ghi chú |
|---|---|---|---|---|
| W-STD | | | | |
| W-RC | | | | |
| W-LEG | | | | |
| W-RAG | | | | |
| W-OFF | | | | |
| W-PIPE | | | | |

Chỉ khi W-OFF-06, 07, 08, 13 đạt mới được ghi "OFFLINE UPGRADE AND ROLLBACK: VERIFIED". Chỉ khi W-RC và W-LEG đạt mới được ghi
"REAL OCR PIPELINE: VERIFIED".
