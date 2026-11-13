# Kế hoạch triển khai production — OCR Engine Manager RC1

Cập nhật: 2026-11-13 (Phase 9A) · **Chỉ là kế hoạch. Chưa bước nào được thực hiện trên production.**

Phase 9A không backup, không restart, không sửa compose / `.env`, không triển khai production. Mọi lệnh dưới
đây do người vận hành chạy, sau khi chủ dự án phê duyệt. Danh sách kiểm tra đi kèm:
[OCR_PRODUCTION_CHECKLIST.md](OCR_PRODUCTION_CHECKLIST.md).

## 1. Hiện trạng và đích

| | Hiện tại (production) | Release Candidate |
|---|---|---|
| Thư mục | `/home/admin/ChatBot5400-Version02` | cùng thư mục, sau khi cập nhật mã |
| Compose project | `chatbot5400-version02` (`docker-compose.yml` + `docker-compose.override.yml`) | không đổi tên project |
| Commit | `5e042279439302d3ccf39bef4d1d8d402314d194` (v1.0.8, trước tính năng OCR) | `@@RC_SHA@@` — branch `release/ocr-engine-manager-rc1` |
| Image ứng dụng | `chatbot5400:local`, ID `sha256:7d26c1203a65…` (build 2026-11-12) | build lại từ commit RC, gắn thêm tag `chatbot5400:rc1-<ngày>` |
| Image DB | `surrealdb/surrealdb:v2` | không đổi |
| Dữ liệu | bind mount `./notebook_data` → `/app/data`, `./surreal_data` → `/mydata` | không đổi; không có migration DB |
| Engine OCR | RapidOCR qua Docling Auto | mặc định vẫn RapidOCR; khuyến nghị chuyển sang Tesseract Vietnamese Best sau khi chuẩn bị |

Ghi chú: cây làm việc production có 5 file sửa cục bộ (trong đó có compose). Phải xem `git status` và
`git diff` trước khi cập nhật mã; không ghi đè thay đổi cục bộ.

## 2. Điều kiện phải có trước khi bắt đầu

1. Chủ dự án đã phê duyệt RC và kế hoạch này.
2. Benchmark trên tài liệu nghiệp vụ thật đã do chủ dự án thực hiện tại chỗ và xác nhận
   ([OCR_REAL_DOCUMENT_BENCHMARK.md](OCR_REAL_DOCUMENT_BENCHMARK.md)).
3. Cửa sổ bảo trì đã thông báo (dịch vụ ngừng khoảng 20–40 phút; lần khởi động đầu cài Docling lâu hơn).
4. Máy chủ **có Internet** trong lúc cập nhật và chuẩn bị model.
5. Ổ đĩa trống ≥ 3 lần dung lượng `notebook_data` + `surreal_data`, cộng 10 GB cho image.
6. Cấu hình bảo mật đã quyết định: **URL ingestion tắt** (mục 5).

## 3. Backup nhất quán

SurrealDB ghi liên tục vào `surreal_data`; sao chép khi đang chạy có thể cho bản không nhất quán. Backup
lạnh: dừng cả hai container, sao chép, rồi mới làm tiếp.

```bash
cd /home/admin/ChatBot5400-Version02
TS=$(date +%Y%m%d-%H%M%S); BK=/home/admin/backups/cb5400-$TS; mkdir -p "$BK"
git rev-parse HEAD > "$BK/commit.txt"; git status --short > "$BK/git-status.txt"; git diff > "$BK/local-changes.diff"
cp docker-compose.yml docker-compose.override.yml "$BK/"          # cấu hình hiện tại
docker image inspect chatbot5400:local --format '{{.Id}}' > "$BK/image-id.txt"
docker tag chatbot5400:local "chatbot5400:rollback-$TS"            # giữ image hiện tại để rollback
docker compose stop                                                # dừng app + DB, KHÔNG dùng down -v
sudo tar --numeric-owner -czf "$BK/notebook_data.tgz" notebook_data
sudo tar --numeric-owner -czf "$BK/surreal_data.tgz" surreal_data
( cd "$BK" && sha256sum notebook_data.tgz surreal_data.tgz > SHA256SUMS && ls -la )
```

File `.env` chứa bí mật: sao lưu riêng theo quy định của đơn vị, không để chung thư mục có thể chia sẻ.
Nếu chỉ backup rồi chưa triển khai ngay: `docker compose start` để dịch vụ chạy lại.

## 4. Kiểm tra khả năng restore (trước khi đổi bất cứ thứ gì)

Giải nén backup vào thư mục tạm và khởi động một stack **cô lập** (project khác, không publish cổng ra
ngoài, không đụng dữ liệu thật) bằng chính image hiện tại.

```bash
RT=/home/admin/restore-test-$TS; mkdir -p "$RT" && cd "$RT"
( cd "$BK" && sha256sum -c SHA256SUMS )
sudo tar --numeric-owner -xzf "$BK/notebook_data.tgz" && sudo tar --numeric-owner -xzf "$BK/surreal_data.tgz"
cp /home/admin/ChatBot5400-Version02/docker-compose.yml .          # rồi sửa bản SAO này:
# - đổi cổng publish sang cổng khác chỉ nghe 127.0.0.1 (ví dụ 127.0.0.1:15055:5055, 127.0.0.1:18502:8502), bỏ cổng DB
# - đặt image: chatbot5400:rollback-$TS, bỏ khối build
# - dùng cùng các biến môi trường bắt buộc (khóa mã hóa, mật khẩu DB) như production
docker compose -p cb5400-restore-test up -d
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:15055/health     # mong đợi 200
# đăng nhập, mở một notebook, một source, thử một câu chat; so số notebook/source với production
docker compose -p cb5400-restore-test down                         # không -v; rồi xóa thư mục $RT khi xong
```

Đạt khi: `/health` 200, đăng nhập được, dữ liệu hiển thị đủ, credential AI đọc được (khóa mã hóa đúng).
Không đạt ⇒ **dừng**, không triển khai.

## 5. Cấu hình RC

Thêm vào khối `environment` của service `open_notebook` (trong `docker-compose.override.yml` để không
xung đột với file được theo dõi):

```yaml
      - OPEN_NOTEBOOK_ENABLE_URL_INGESTION=false     # TẮT nhập nguồn từ URL (mặc định cũng là tắt)
      - OPEN_NOTEBOOK_ENABLE_DOCLING=true            # đã có trên production
      - OPEN_NOTEBOOK_ENABLE_OCR_TESSERACT=true      # runtime Tesseract (hoặc build với OCR_INSTALL_TESSERACT=true)
```

- **URL ingestion:** để tắt. Thiếu biến cũng là tắt; ghi tường minh để người đọc cấu hình thấy rõ. Nguồn URL
  cũ vẫn đọc và tìm kiếm được, chỉ không tải lại được. Bật lại = chấp nhận rủi ro SSRF còn lại
  (`docs/security/BACKGROUND_JOB_SECURITY.md` §5–6), cần phê duyệt và biện pháp bổ sung.
- Không bật `OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR` (EasyOCR ở mức thử nghiệm).
- Nếu sẽ vận hành offline với RapidOCR và container có thể bị recreate: thêm `OCR_RAPIDOCR_PERSISTENT=true`.
- Giữ nguyên mọi biến khác (khóa mã hóa, mật khẩu, JWT, CORS).

## 6. Cập nhật (máy chủ có Internet)

```bash
cd /home/admin/ChatBot5400-Version02
git status --short && git diff --stat                              # xem thay đổi cục bộ trước
git fetch origin release/ocr-engine-manager-rc1
git stash push -m "local-before-rc1-$TS"                           # nếu có thay đổi cục bộ; áp lại sau, từng file
git checkout -B rc1 FETCH_HEAD && git rev-parse HEAD               # phải bằng commit RC ở mục 1
# áp lại thay đổi cục bộ cần giữ (compose/override), thêm cấu hình mục 5
docker compose build --build-arg OCR_INSTALL_TESSERACT=true open_notebook
docker tag chatbot5400:local "chatbot5400:rc1-$TS"
docker compose up -d
docker compose logs -f open_notebook                               # chờ "Application startup complete"; lần đầu cài Docling
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5055/health
```

Không có migration cơ sở dữ liệu trong RC này. Settings, notebook, source, embedding giữ nguyên (đã kiểm
chứng trong Docker acceptance: nâng cấp từ đúng commit `5e04227`).

## 7. Chuẩn bị Tesseract Vietnamese Best và xác minh offline

Trong giao diện (admin): **Cài đặt → OCR Engine Manager**.

1. "Thông tin chung": Docling khả dụng; Layout Heron; TableFormer accurate; không có cảnh báo phiên bản.
2. Tesseract Vietnamese Best → **Cài đặt** (tải model, có kiểm tra checksum) → trạng thái "Sẵn sàng".
3. **Chuẩn bị** → chờ `offline_ready` (tải Layout Heron / TableFormer nếu chưa có, chạy thử pipeline với
   mạng bị chặn trong tiến trình con).
4. **Kiểm tra** (Test) → thành công, model thực tế là `TesseractOcrCliModel`.
5. Dòng "Tự sửa hướng trang scan": **Khả dụng**.
6. **Sử dụng** → Tesseract Vietnamese Best thành engine đang dùng. (RapidOCR vẫn là mặc định nếu không đổi.)
7. Nếu vận hành offline: ngắt Internet theo quy trình của đơn vị → **Kiểm tra offline** → `offline_verified`.

Dòng lệnh tương đương: `docs/ocr/OCR_ONLINE_PREPARATION.md`.

## 8. Smoke test sau triển khai

Chỉ dùng tài liệu không nhạy cảm (ví dụ các fixture tổng hợp trong `tests/fixtures/ocr/`).

| # | Kiểm tra | Đạt khi |
|---|---|---|
| 1 | `/health`, đăng nhập admin và một người dùng thường | 200; vào được |
| 2 | Dữ liệu cũ: mở notebook, source, lịch sử chat | hiển thị như trước |
| 3 | Upload PDF có text layer (`vb_text.pdf`) | xử lý xong, nội dung đúng |
| 4 | Upload PDF scan tiếng Việt (`vb_scan.pdf`) | có `1234/2024/QĐ-MẪU` và `1.250.000.000`; log ghi `engine=tesseract_best actual_models=['TesseractOcrCliModel']` |
| 5 | Upload PDF scan có bảng (`bang_gop_scan.pdf`) | bảng 5 cột, đủ 4 dòng số liệu, số tiền và ngày đúng |
| 6 | Upload trang scan nằm ngang (`vb_xoay_scan.pdf`) | đọc được như trang thẳng; metadata `rotated_pages` có trang 1 |
| 7 | Nhập văn bản thủ công | lưu và tìm được |
| 8 | Thêm nguồn từ URL | tab "Thêm URL" bị vô hiệu hóa; gọi API trực tiếp trả 403 |
| 9 | Embedding + tìm kiếm trên tài liệu vừa upload | tìm ra đoạn đúng |
| 10 | Chat / hỏi đáp (RAG) trên tài liệu vừa upload | trả lời có trích dẫn nguồn |
| 11 | Transformation mặc định | chạy xong |
| 12 | Phân quyền: người dùng thường gọi API OCR / commands | 403 |
| 13 | `docker compose logs` 15 phút | không có lỗi lặp lại, không restart |

Xóa các tài liệu thử sau khi kiểm tra.

## 9. Tiêu chí dừng triển khai

Dừng và rollback (mục 10) nếu có **bất kỳ** điều nào:

- Backup hoặc kiểm tra restore (mục 3–4) không đạt.
- Sau `up -d`, `/health` không 200 trong 15 phút, hoặc container restart lặp lại.
- Đăng nhập thất bại, hoặc dữ liệu cũ thiếu / không đọc được, hoặc credential AI không giải mã được.
- Engine OCR mặc định (RapidOCR) không xử lý được PDF mà bản cũ xử lý được.
- Smoke test 1–3, 7, 9, 10 hoặc 12 không đạt.
- Thêm nguồn từ URL vẫn thực hiện được khi cấu hình tắt.
- Cảnh báo "phiên bản phụ thuộc khác bộ đã kiểm chứng" xuất hiện trong OCR Engine Manager.

Lỗi chỉ ở Tesseract (smoke 4–6) không bắt buộc rollback: chuyển lại RapidOCR trong OCR Engine Manager, ghi
nhận, và quyết định sau. Có thể tắt riêng từng cải tiến chất lượng: `OCR_TESSERACT_OSD_GATE=false`,
`OCR_PDF_PREP=false`.

## 10. Rollback

Dữ liệu OCR mới nằm trong `notebook_data/ocr` và trong một bản ghi cấu hình; bản cũ bỏ qua chúng
(`docs/ocr/OCR_ROLLBACK.md`). Không có migration cần hoàn tác.

**Rollback mã (dữ liệu giữ nguyên) — dùng trước tiên:**

```bash
cd /home/admin/ChatBot5400-Version02
docker compose stop
git checkout 5e042279439302d3ccf39bef4d1d8d402314d194             # hoặc branch cũ
cp "$BK/docker-compose.yml" "$BK/docker-compose.override.yml" .    # cấu hình trước triển khai
docker tag "chatbot5400:rollback-$TS" chatbot5400:local            # image cũ, không cần build lại
docker compose up -d
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5055/health
```

Lưu ý: bản cũ không có công tắc URL ingestion, nên sau rollback mã chức năng thêm nguồn từ URL hoạt động
trở lại (cùng rủi ro SSRF còn lại). Nếu môi trường yêu cầu tắt, áp biện pháp tạm thời ở tầng mạng cho tới khi
triển khai lại.

**Rollback dữ liệu — chỉ khi dữ liệu hỏng:** dừng stack, đổi tên `notebook_data` và `surreal_data` hiện tại
(không xóa), giải nén hai file `.tgz` từ `$BK` (kiểm tra `SHA256SUMS` trước), rồi khởi động bằng image cũ.
Mọi thay đổi sau thời điểm backup sẽ mất; cần chủ dự án quyết định.

## 11. Khôi phục dịch vụ khi sự cố ngoài kế hoạch

1. Ghi lại hiện trạng: `docker compose ps`, 200 dòng log cuối của từng container, dung lượng đĩa.
2. Nếu chỉ container ứng dụng lỗi: `docker compose up -d open_notebook`; DB không đụng tới.
3. Nếu không lên sau 10 phút: rollback mã (mục 10).
4. Nếu DB không lên: **không** xóa `surreal_data`; giữ nguyên, báo chủ dự án, cân nhắc rollback dữ liệu.
5. Không dùng `docker compose down -v`, không `docker system prune`, không xóa volume trong lúc xử lý sự cố.
6. Sau khi ổn định: ghi biên bản (thời điểm, triệu chứng, bước đã làm, trạng thái dữ liệu).

## 12. Sau triển khai

- Theo dõi 24 giờ: log lỗi, thời gian xử lý tài liệu, RAM (pipeline Docling dùng 3–6 GB khi OCR).
- Giữ `$BK` và image `chatbot5400:rollback-$TS` tối thiểu 30 ngày.
- Cập nhật `docs/ocr/CHECKPOINT.md` với commit, image ID và kết quả smoke test.
- Dọn tài nguyên nghiệm thu trên máy (image `chatbot5400:ocr-accept*`, thư mục `work/`, volume ẩn danh) chỉ
  sau khi chủ dự án phê duyệt danh sách ở `OCR_PHASE9A_REPORT.md` §I.
