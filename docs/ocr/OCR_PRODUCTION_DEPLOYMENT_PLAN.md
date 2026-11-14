# Kế hoạch triển khai production — OCR Engine Manager RC1

Cập nhật: 2026-11-14 (Phase 9B/9C) · **Đã thực hiện ngày 2026-11-14** theo phê duyệt của chủ dự án — kết quả:
[OCR_PHASE9C_REPORT.md](OCR_PHASE9C_REPORT.md). Giữ làm quy trình cho các lần cập nhật sau.

Điều chỉnh khi thực hiện so với kế hoạch dưới đây: ứng dụng được khởi động ở **chế độ bảo trì** (cổng chỉ nghe
loopback) và chỉ mở lại sau khi các kiểm tra bảo mật đạt; rollback chỉ đưa bản cũ lên ở chế độ bảo trì; thêm
`OPEN_NOTEBOOK_ENABLE_OCR_TESSERACT=true`; lưu thêm bản tar của image ứng dụng và image DB cùng manifest. Xem
[OCR_OPERATOR_GUIDE.md](OCR_OPERATOR_GUIDE.md) §11.

Bản này thay bản Phase 9A: đã đối chiếu với kết quả kiểm tra **chỉ đọc** trên production (mục 1.1) và điều
chỉnh các bước cho đúng hiện trạng. Danh sách kiểm tra đi kèm:
[OCR_PRODUCTION_CHECKLIST.md](OCR_PRODUCTION_CHECKLIST.md). Hướng dẫn vận hành hằng ngày:
[OCR_OPERATOR_GUIDE.md](OCR_OPERATOR_GUIDE.md).

Tài liệu này công khai: không ghi mật khẩu, khóa, token, nội dung `.env`, đường dẫn bản sao lưu thật hay thông
tin khách hàng. `BACKUP_DIR` là thư mục sao lưu do người vận hành chọn, quyền `700`, ngoài repository.

## 1. Hiện trạng và đích

| | Hiện tại (production) | Sau triển khai |
|---|---|---|
| Thư mục | `/home/admin/ChatBot5400-Version02` | không đổi |
| Compose project | `chatbot5400-version02` (`docker-compose.yml` + `docker-compose.override.yml`) | không đổi |
| Commit | `5e042279439302d3ccf39bef4d1d8d402314d194` (v1.0.8) | commit merge của PR #42 vào `claude/practical-wozniak-9s1t6z` (`git rev-parse origin/claude/practical-wozniak-9s1t6z` sau khi merge; ghi trong `OCR_FINAL_ACCEPTANCE.md`) |
| Image ứng dụng | `chatbot5400:local` | image dựng từ commit merge, có Tesseract; gắn thêm tag `chatbot5400:rc1-<ngày>` (đã dựng và xác minh trên stack cô lập: `OCR_FINAL_ACCEPTANCE.md` §4–5) |
| Image DB | `surrealdb/surrealdb:v2` (đang chạy: bản tạo 2026-09-23) | **đúng image đang chạy** — không pull, không recreate container DB |
| Dữ liệu | bind mount `./notebook_data` → `/app/data`, `./surreal_data` → `/mydata` | không đổi; không có migration DB |
| Cổng, mạng, khóa mã hóa, mật khẩu DB, nhà cung cấp LLM / embedding | — | không đổi |
| Engine OCR | xem mục 1.1 | mặc định vẫn RapidOCR; Tesseract Vietnamese Best sau khi chuẩn bị và nghiệm thu |

### 1.1 Kết quả kiểm tra chỉ đọc trên production (2026-11-13)

1. **Docling hiện không được cài trong container production.** File override đặt `UV_OFFLINE=1`,
   `UV_EXCLUDE_NEWER=…` và `HF_HUB_OFFLINE=1` (ghi chú ngày 2026-11-03: khi đó máy chủ không tới được
   huggingface.co và kho PyTorch). Container được tạo lại ngày 2026-11-12 cho v1.0.8; lúc khởi động, bước cài
   Docling thất bại (`docling was not found in the cache`) và ứng dụng chạy tiếp **không có Docling**: không
   OCR, không Layout Heron, không TableFormer. Tức là từ 2026-11-12, PDF scan không được nhận dạng.
2. Hiện tại máy chủ tới được huggingface.co, pypi.org, download.pytorch.org, deb.debian.org, modelscope.cn (đã
   kiểm tra bằng request HEAD; các stack nghiệm thu trên chính máy này đã tải đủ trong ngày 2026-11-13).
3. Thay đổi cục bộ trong thư mục production (phải giữ): `docker-compose.yml` (bật Docling, `UV_TORCH_BACKEND=cpu`,
   `OPEN_NOTEBOOK_WORKER_MAX_TASKS=1`); file không theo dõi: `docker-compose.yml.bak`, `.env.save`, hai file
   `backup-*.tgz`; file bị git bỏ qua nhưng thiết yếu: `.env`, `docker-compose.override.yml`. Bản vá cục bộ của
   `docker-compose.yml` áp sạch lên bản của RC (đã thử trên bản sao).
4. Container DB có hai volume ẩn danh (`/data`, `/logs`) **rỗng** (0 file); dữ liệu DB nằm trọn trong
   `surreal_data/mydatabase.db`. `docker-compose.yml` đặt `pull_policy: always` cho tag `v2`: một lệnh
   `docker compose up -d` không kèm tên service sẽ kéo bản `v2` mới nhất và tạo lại container DB.
5. Dung lượng: `notebook_data` 1,8 GB (trong đó cache 1,7 GB), `surreal_data` 225 MB; ổ đĩa trống 300 GB.
6. `sudo` cần mật khẩu; hai thư mục dữ liệu thuộc `root` ⇒ sao lưu bằng một container tạm chạy root, mount chỉ đọc.
7. Cấu hình dev-default: các hạng mục ở mục 13; kết quả cụ thể nằm trong báo cáo riêng cho chủ dự án.

## 2. Điều kiện phải có trước khi bắt đầu

1. PR đã merge vào nhánh chính thức; chủ dự án phê duyệt kế hoạch này (một lần, cho toàn bộ chuỗi bước).
2. Benchmark trên tài liệu nghiệp vụ thật đã do người vận hành thực hiện tại chỗ và xác nhận
   ([OCR_REAL_DOCUMENT_BENCHMARK.md](OCR_REAL_DOCUMENT_BENCHMARK.md)), **hoặc** chủ dự án phê duyệt rõ phạm vi
   thí điểm phi nghiệp vụ: triển khai, engine đang dùng vẫn là RapidOCR, chỉ chuyển sang Tesseract Vietnamese
   Best sau khi có biên bản benchmark.
3. Cửa sổ bảo trì đã thông báo: dịch vụ ngừng khoảng 20–40 phút.
4. Máy chủ **có Internet** trong lúc cập nhật và chuẩn bị model.
5. Tài khoản kiểm thử cho smoke test: một quản trị viên và một người dùng thường (hoặc chủ dự án cho phép cách
   kiểm tra thay thế nêu ở mục 8).
6. Cấu hình bảo mật đã quyết định: **URL ingestion tắt**; biện pháp khi rollback (mục 10).

## 3. Chuẩn bị trước khi dừng dịch vụ (không gián đoạn)

Dựng image từ commit đã merge trong một thư mục **riêng**, tag riêng; không ghi đè `chatbot5400:local`.

```bash
MERGE=3819c2a7068916bf7cd2d5bc9c71cfe73b76dfbc       # commit merge của PR #42
BUILD=/home/admin/cb5400-rc1-build
git clone --no-checkout /home/admin/ChatBot5400-Version02 "$BUILD"
git -C "$BUILD" fetch https://github.com/nghoainam1902ps4-lgtm/ChatBot5400-Version02.git "$MERGE"
git -C "$BUILD" checkout --detach "$MERGE"
RC_TAG="chatbot5400:rc1-$(date +%Y%m%d)"
docker build --target runtime --build-arg OCR_INSTALL_TESSERACT=true -t "$RC_TAG" "$BUILD"
docker image inspect "$RC_TAG" --format '{{.Id}}'
docker run --rm --network none --entrypoint sh "$RC_TAG" -c 'tesseract --version | head -1'
```

## 4. Sao lưu nhất quán (bắt đầu gián đoạn)

SurrealDB ghi liên tục vào `surreal_data`: sao lưu **lạnh**, dừng cả hai container rồi mới sao chép.

```bash
cd /home/admin/ChatBot5400-Version02
BACKUP_DIR=/duong/dan/sao-luu                          # thay bằng thư mục sao lưu của đơn vị
TS=$(date +%Y%m%d-%H%M%S); BK=$BACKUP_DIR/cb5400-$TS; mkdir -p "$BK"; chmod 700 "$BK"
git rev-parse HEAD > "$BK/commit.txt"; git status --short > "$BK/git-status.txt"
git diff > "$BK/local-changes.diff"
cp -p docker-compose.yml docker-compose.override.yml docker-compose.yml.bak "$BK/"
cp -p .env "$BK/env.backup"; chmod 600 "$BK/env.backup"       # chứa bí mật: không rời máy, không commit
docker image inspect chatbot5400:local --format '{{.Id}}' > "$BK/app-image-id.txt"
docker image inspect surrealdb/surrealdb:v2 --format '{{.Id}}' > "$BK/db-image-id.txt"
docker tag chatbot5400:local "chatbot5400:rollback-pre-ocr-$TS"   # tag riêng, không bị ghi đè
docker compose stop                                               # dừng app + DB; KHÔNG dùng down, KHÔNG -v
docker run --rm --network none \
  -v "$PWD/notebook_data:/src/notebook_data:ro" -v "$PWD/surreal_data:/src/surreal_data:ro" \
  -v "$BK:/bk" --entrypoint sh "chatbot5400:rollback-pre-ocr-$TS" -c \
  'cd /src && tar --numeric-owner -czf /bk/notebook_data.tgz notebook_data \
          && tar --numeric-owner -czf /bk/surreal_data.tgz surreal_data \
          && cd /bk && sha256sum notebook_data.tgz surreal_data.tgz > SHA256SUMS \
          && tar -tzf notebook_data.tgz > /dev/null && tar -tzf surreal_data.tgz > /dev/null \
          && chown -R 1001:1001 /bk'
( cd "$BK" && sha256sum -c SHA256SUMS && ls -la )
```

Hai volume ẩn danh của container DB rỗng nên không cần sao lưu. Nếu bước nào lỗi: **không cập nhật**,
`docker compose start` để dịch vụ cũ chạy lại, báo cáo.

## 5. Kiểm tra khả năng restore (trước khi đổi bất cứ thứ gì)

Stack **cô lập**: project riêng, thư mục dữ liệu riêng (giải nén từ bản sao lưu), mạng `internal` (không
Internet, không publish cổng), image cũ. Không mount dữ liệu production. Không gọi LLM / embedding. Không ai
đọc nội dung nghiệp vụ; chỉ lấy **số đếm**.

```bash
RT=$BACKUP_DIR/restore-test-$TS; mkdir -p "$RT"; chmod 700 "$RT"
docker run --rm --network none -v "$BK:/bk:ro" -v "$RT:/rt" --entrypoint sh \
  "chatbot5400:rollback-pre-ocr-$TS" -c 'cd /rt && tar --numeric-owner -xzf /bk/notebook_data.tgz \
  && tar --numeric-owner -xzf /bk/surreal_data.tgz'
# compose của stack restore: sinh từ compose production bằng script (đổi image, bỏ ports, bỏ build,
# mạng internal, đường dẫn dữ liệu = $RT); biến bí mật lấy qua --env-file, không in ra màn hình
docker compose -p cb5400-restore-test --env-file "$BK/env.backup" -f "$RT/compose.restore.yml" up -d
docker compose -p cb5400-restore-test -f "$RT/compose.restore.yml" ps
```

Đạt khi (tất cả kiểm tra chạy bằng `docker exec` bên trong stack cô lập):

| Kiểm tra | Đạt khi |
|---|---|
| DB khởi động, ứng dụng `/health` | 200 |
| Xác thực | request không token ⇒ 401; `/api/auth/status` báo bật xác thực |
| Số bản ghi (notebook, source, note, người dùng, phiên chat, credential, model, embedding) | **bằng** số đếm lấy trên production ngay trước khi dừng |
| Khóa mã hóa đúng | giải mã được mọi credential nhà cung cấp (chỉ in số lượng đạt / lỗi, không in giá trị) |
| File upload, checkpoint chat | số file và tổng dung lượng khớp bản gốc |

Sau đó khởi động lại stack cô lập với **image RC** trên cùng bản sao dữ liệu để diễn tập nâng cấp (số đếm
không đổi, `/health` 200, không lỗi lặp trong log). Dọn: `docker compose -p cb5400-restore-test down` (không
`-v`), giữ thư mục `$RT` cho tới khi triển khai xong rồi xóa bằng container root.

Không đạt ⇒ **dừng**: `docker compose start` trên production (bản cũ), không triển khai.

## 6. Cập nhật mã và cấu hình

```bash
cd /home/admin/ChatBot5400-Version02
git fetch origin claude/practical-wozniak-9s1t6z
git stash push -m "local-before-ocr-rc1-$TS" -- docker-compose.yml      # chỉ file theo dõi đã sửa
git merge --ff-only "$MERGE" && git rev-parse HEAD                      # phải bằng $MERGE
git stash pop                                                           # áp lại 3 dòng cục bộ (đã thử: không xung đột)
git status --short                                                      # 1 file sửa + 4 file không theo dõi như trước
```

Nếu `git stash pop` báo xung đột: **không** tự giải quyết bằng cách ghi đè; khôi phục `docker-compose.yml` từ
`$BK`, đối chiếu thủ công. Không dùng `git reset --hard`, không `git pull` mù.

Cấu hình (sửa file không theo dõi `docker-compose.override.yml` và `.env`; bản cũ đã nằm trong `$BK`):

| Thay đổi | Lý do |
|---|---|
| Bỏ `UV_OFFLINE=1`, `UV_EXCLUDE_NEWER=…` khỏi override | Lần khởi động đầu của image mới phải cài Docling 2.129.0 theo `uv.lock`; để nguyên thì cài thất bại như hiện nay |
| Bỏ `HF_HUB_OFFLINE=1` khỏi override | "Chuẩn bị" cần kiểm tra / tải model Docling khi có Internet. Có thể đặt lại sau khi đã `offline_ready` nếu vận hành ngắt mạng |
| Thêm `OPEN_NOTEBOOK_ENABLE_URL_INGESTION=false` vào override | Ghi tường minh (mặc định cũng là tắt) |
| Thêm dòng `OCR_INSTALL_TESSERACT=true` vào `.env` | Mọi lần `docker compose up -d --build` về sau vẫn có Tesseract (D-32) |
| Giữ nguyên | khóa mã hóa, mật khẩu DB, cổng, `OPEN_NOTEBOOK_ENABLE_DOCLING=true`, `UV_TORCH_BACKEND=cpu`, `OPEN_NOTEBOOK_WORKER_MAX_TASKS=1` |

Không bật `OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR`. Không bật `OCR_RAPIDOCR_PERSISTENT` (engine dự kiến là Tesseract
Best; xem giới hạn D-32).

## 7. Khởi động bản mới

```bash
cd /home/admin/ChatBot5400-Version02
docker tag "$RC_TAG" chatbot5400:local                       # image cũ vẫn còn dưới tag rollback-pre-ocr-$TS
docker compose start surrealdb                               # CÙNG container DB, không pull, không recreate
docker compose up -d --no-deps --no-build open_notebook      # chỉ tạo lại container ứng dụng
docker compose logs -f --tail 50 open_notebook               # chờ cài Docling xong và "Application startup complete"
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5055/health
docker compose ps
```

**Luôn** dùng `--no-deps open_notebook` khi cập nhật ứng dụng: `docker compose up -d` không kèm tên service sẽ
pull `surrealdb:v2` mới (do `pull_policy: always`) và tạo lại container DB.

Kiểm tra ngay: `/health` 200; container không restart lặp; log có dòng cài Docling theo constraints; số bản
ghi bằng số trước khi dừng; OCR Engine Manager không báo "phiên bản phụ thuộc khác bộ đã kiểm chứng".

## 8. Chuẩn bị Tesseract Vietnamese Best, smoke test, xác minh offline

Trong giao diện (quản trị viên): **Cài đặt → OCR Engine Manager**; hoặc CLI trong container
(`docs/ocr/OCR_ONLINE_PREPARATION.md`).

1. "Thông tin chung": Docling khả dụng; Layout Heron; TableFormer accurate; không cảnh báo phiên bản.
2. Tesseract Vietnamese Best → **Cài đặt** (tải `vie`, `eng`, `osd`, có kiểm tra SHA-256) → "Sẵn sàng".
3. **Chuẩn bị** → chờ `offline_ready`.
4. **Kiểm tra** → thành công, model thực tế `TesseractOcrCliModel`.
5. "Tự sửa hướng trang scan": **Khả dụng**.
6. **Sử dụng** Tesseract Vietnamese Best — chỉ khi điều kiện 2.2 (benchmark thật) đã đạt; nếu chưa, để RapidOCR.

Smoke test — chỉ dùng tài liệu tổng hợp (`tests/fixtures/ocr/`), xóa sau khi thử:

| # | Kiểm tra | Đạt khi |
|---|---|---|
| 1 | `/health`; đăng nhập quản trị viên và người dùng thường | 200; vào được |
| 2 | Dữ liệu cũ: số notebook, source, note, phiên chat, cấu hình | bằng trước khi triển khai |
| 3 | Upload PDF có text layer (`vb_text.pdf`) | xử lý xong, nội dung đúng |
| 4 | Upload PDF scan tiếng Việt (`vb_scan.pdf`) | có `1234/2024/QĐ-MẪU` và `1.250.000.000`; log ghi `engine=tesseract_best actual_models=['TesseractOcrCliModel']` |
| 5 | Upload PDF scan có bảng (`bang_gop_scan.pdf`) | bảng 5 cột, đủ 4 dòng số liệu, số tiền và ngày đúng |
| 6 | Upload trang scan nằm ngang (`vb_xoay_scan.pdf`) | đọc như trang thẳng; log ghi trang 1 được xoay |
| 7 | Upload Word, ảnh; nhập văn bản thủ công | xử lý xong |
| 8 | Thêm nguồn từ URL | tab bị vô hiệu hóa; gọi API trực tiếp trả 403 |
| 9 | Embedding + tìm kiếm; chat / RAG; transformation — trên tài liệu tổng hợp | hoạt động |
| 10 | Phân quyền: người dùng thường gọi API OCR / commands / credentials / models (ghi) | 403 |
| 11 | Worker: 2–3 tài liệu liên tiếp; thư mục tạm `ocr-prep-*` | xử lý hết; không sót thư mục tạm |
| 12 | `docker compose logs` 15 phút; `docker compose ps` | không lỗi lặp lại, restart = 0 |

Xác minh offline: thực hiện trên **stack cô lập** dùng chính image RC và model đã chuẩn bị, mạng egress bị
chặn (đã có trong Docker acceptance; lặp lại với image triển khai). Kiểm tra offline trực tiếp trên production
(ngắt Internet máy chủ) chỉ làm khi chủ dự án và quản trị mạng phê duyệt quy trình; chưa làm thì ghi rõ
"OFFLINE VERIFIED — PRODUCTION: NOT VERIFIED".

## 9. Tiêu chí dừng triển khai

Dừng và rollback mã (mục 10) nếu có **bất kỳ** điều nào:

- Sao lưu hoặc kiểm tra restore (mục 4–5) không đạt ⇒ không cập nhật, khởi động lại bản cũ.
- Sau khi khởi động bản mới, `/health` không 200 trong 15 phút, hoặc container restart lặp lại.
- Đăng nhập thất bại; số bản ghi thiếu; credential nhà cung cấp không giải mã được.
- Smoke 1–3, 7 (nhập văn bản), 9 hoặc 10 không đạt.
- Thêm nguồn từ URL vẫn thực hiện được khi cấu hình tắt.
- Cảnh báo "phiên bản phụ thuộc khác bộ đã kiểm chứng" trong OCR Engine Manager.

Lỗi chỉ ở Tesseract (smoke 4–6) không bắt buộc rollback: chuyển lại RapidOCR trong OCR Engine Manager, ghi
nhận, quyết định sau — nhưng khi đó **không** tuyên bố OCR Engine Manager đã nghiệm thu đầy đủ. Có thể tắt riêng
từng cải tiến: `OCR_TESSERACT_OSD_GATE=false`, `OCR_PDF_PREP=false`.

## 10. Rollback

Không có migration cần hoàn tác; bản cũ bỏ qua dữ liệu OCR (`docs/ocr/OCR_ROLLBACK.md`).

**Rollback mã (dữ liệu giữ nguyên) — dùng trước tiên:**

```bash
cd /home/admin/ChatBot5400-Version02
docker compose stop open_notebook
git stash push -m "rc1-local-$TS" -- docker-compose.yml
git checkout 5e042279439302d3ccf39bef4d1d8d402314d194
cp -p "$BK/docker-compose.yml" "$BK/docker-compose.override.yml" .   # cấu hình trước triển khai
docker tag "chatbot5400:rollback-pre-ocr-$TS" chatbot5400:local      # image cũ, không build lại
docker compose up -d --no-deps --no-build open_notebook
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5055/health
```

**URL ingestion khi rollback:** bản cũ không có công tắc, nên chức năng thêm nguồn từ URL **hoạt động trở lại**
(cùng rủi ro SSRF còn lại, và cả lỗi phân quyền credential đã sửa ở D-31). Biện pháp kiểm soát cần chủ dự án
phê duyệt trước khi triển khai, chọn một:

1. Rollback chỉ là tạm thời (tối đa vài giờ), trong thời gian đó thông báo người dùng không thêm nguồn từ URL
   và chỉ quản trị viên được thao tác; triển khai lại bản RC đã sửa lỗi ngay khi có thể.
2. Chính sách egress ở tầng mạng cho container ứng dụng (do quản trị mạng thực hiện; ngoài phạm vi tài liệu này).
3. Thay vì quay về bản cũ, giữ bản RC và chỉ quay engine về RapidOCR (mục 9) — khi lỗi chỉ thuộc phần OCR.

**Rollback dữ liệu — chỉ khi dữ liệu hỏng, cần chủ dự án quyết định:** dừng stack, **đổi tên** (không xóa)
`notebook_data` và `surreal_data` hiện tại, giải nén hai file `.tgz` từ `$BK` (kiểm tra `SHA256SUMS` trước),
khởi động bằng image cũ. Mọi thay đổi sau thời điểm sao lưu sẽ mất.

## 11. Khôi phục dịch vụ khi sự cố ngoài kế hoạch

1. Ghi lại hiện trạng: `docker compose ps`, 200 dòng log cuối của từng container, dung lượng đĩa.
2. Nếu chỉ container ứng dụng lỗi: `docker compose up -d --no-deps --no-build open_notebook`; DB không đụng tới.
3. Nếu không lên sau 10 phút: rollback mã (mục 10).
4. Nếu DB không lên: **không** xóa `surreal_data`; giữ nguyên, báo chủ dự án, cân nhắc rollback dữ liệu.
5. Không dùng `docker compose down -v`, không `docker system prune`, không xóa volume khi xử lý sự cố.
6. Sau khi ổn định: ghi biên bản (thời điểm, triệu chứng, bước đã làm, trạng thái dữ liệu).

## 12. Sau triển khai

- Theo dõi 24 giờ (người vận hành): `scripts/ocr/production_health_check.sh` in trạng thái container, số lần
  restart, `/health`, RAM, đĩa và số dòng lỗi trong log — không in biến môi trường hay nội dung tài liệu.
  Pipeline Docling dùng 3–6 GB RAM khi OCR.
- Giữ `$BK` và image `chatbot5400:rollback-pre-ocr-$TS` tối thiểu 30 ngày.
- Sau mỗi lần container ứng dụng được tạo lại: kiểm tra OCR Engine Manager; nếu trạng thái readiness về "chưa
  kiểm tra", bấm **Chuẩn bị** một lần khi có Internet.
- Dọn tài nguyên nghiệm thu trên máy chỉ sau khi chủ dự án phê duyệt danh sách cụ thể.

## 13. Đánh giá cấu hình dev-default trên production

Repository này công khai, nên kết quả đánh giá cụ thể của máy chủ **không** được ghi ở đây; chúng nằm trong báo
cáo bàn giao riêng cho chủ dự án (ngoài repository). Các hạng mục đã được kiểm tra bằng phép thử chỉ trả
ĐẠT / KHÔNG ĐẠT, không hiển thị giá trị:

| Hạng mục | Cần đạt |
|---|---|
| Khóa mã hóa credential | đã đặt, không phải giá trị mẫu; được sao lưu an toàn |
| Khóa ký JWT | đặt riêng, hoặc để ứng dụng suy ra từ khóa mã hóa (phiên đăng nhập giữ qua restart) |
| Xác thực ứng dụng | bật; mật khẩu tài khoản quản trị mặc định đã được đổi |
| Tài khoản và mật khẩu cơ sở dữ liệu | không dùng giá trị mẫu; cổng DB không mở ra ngoài máy chủ |
| CORS | `CORS_ORIGINS` giới hạn theo origin của đơn vị |
| Cổng ứng dụng | chỉ mở cho mạng cần dùng (firewall của đơn vị) |
| Người dùng chạy container | đã cân nhắc (image mặc định chạy root) |
| URL ingestion | tắt (mục 6); biện pháp khi rollback (mục 10) |

Đợt triển khai này không làm xấu đi hạng mục nào và, theo yêu cầu, không đổi credential, khóa, cổng hay
firewall. Hạng mục nào chưa đạt được nêu trong báo cáo riêng kèm khuyến nghị xử lý sau triển khai.
