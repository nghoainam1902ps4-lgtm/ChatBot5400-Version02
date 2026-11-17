# Hướng dẫn rollback — ChatBot5400 v1.2.0

Cập nhật: 2026-11-17 · Áp dụng cho bản chính thức `v1.2.0` · Bản rollback ứng dụng: `v1.1.0-rc.2`

Tài liệu công khai: không ghi mật khẩu, khóa, token, nội dung `.env`, đường dẫn bản sao lưu thật hay mã băm của model
nội bộ. `/srv/example/chatbot5400` (thư mục triển khai) là đường dẫn **minh họa** — thay bằng thư mục thật của nơi
triển khai. Hàm `ocr` dưới đây là quy ước của [OCR_AGRI_MODEL_GUIDE.md](OCR_AGRI_MODEL_GUIDE.md) mục 0.

Bốn mức rollback, từ nhẹ tới nặng. **Không mức nào cần xóa volume, khôi phục cơ sở dữ liệu hay xóa model.** Luôn thử
mức nhẹ nhất giải quyết được sự cố.

| Mức | Khi nào | Đổi mã / image? | Đụng dữ liệu? |
|---|---|---|---|
| A. Rollback model | phiên bản model Agri mới đọc kém hơn hoặc lỗi | không | không |
| B. Rollback engine | muốn bỏ Agri (hoặc engine đang chọn) | không | không — chỉ đổi một cài đặt |
| C. Rollback ứng dụng | lỗi của bản ứng dụng `v1.2.0` | có — về `v1.1.0-rc.2` | không |
| D. Rollback GitHub Release | bản phát hành `v1.2.0` có lỗi sau khi công bố | không (trên máy chủ) | không |

Cơ chế tự OCR toàn trang (`OCR_AUTO_FULL_PAGE_ON_WATERMARK`) có rollback riêng — tắt cờ — ở
[OCR_ROLLBACK.md](OCR_ROLLBACK.md), ghi chú Phase 10G.

```bash
ocr() { docker compose exec open_notebook /app/.venv/bin/python -m open_notebook.ocr.cli "$@"; }
```

## A. Rollback model (Agri v2 hoặc mới hơn → phiên bản trước)

Vẫn dùng engine Tesseract Vietnamese Agri, chỉ đổi phiên bản model. Không build, không restart.

```bash
cd /srv/example/chatbot5400
ocr custom status            # ghi lại phiên bản đang hoạt động và phiên bản rollback
ocr custom rollback          # về phiên bản hoạt động liền trước
ocr custom status            # active version = phiên bản trước; readiness của phiên bản đó
```

Hoặc trên giao diện (quản trị viên): card *Tesseract Vietnamese Agri* → **Rollback về …** → xác nhận.

Về một phiên bản bất kỳ đã import (không chỉ phiên bản liền trước):

```bash
ocr custom list
ocr custom activate --version v1
```

- Lệnh kiểm tra lại file của phiên bản đích (kích thước, SHA-256 so với manifest, cấu trúc) trước khi chuyển; file
  không khớp ⇒ từ chối, không có gì thay đổi.
- Có hiệu lực cho **tài liệu kế tiếp**; tài liệu đang xử lý giữ phiên bản lúc bắt đầu.
- Phiên bản vừa rời vẫn nằm nguyên trong kho model (không bị xóa) và có thể kích hoạt lại.
- Readiness gắn với từng phiên bản: nếu phiên bản đích chưa có kết quả, chạy
  `ocr readiness --engines tesseract_agri --check` hoặc bấm **Kiểm tra sẵn sàng offline**.
- Tài liệu đã xử lý trước đó **không** được OCR lại.

Kiểm tra: `ocr custom verify` báo `verification=verified file=ok` cho phiên bản đang hoạt động.

## B. Rollback engine (Agri → Tesseract Vietnamese Best hoặc RapidOCR)

Bỏ Agri nhưng giữ bản ứng dụng `v1.2.0`. OCR Engine Manager (quản trị viên): bấm **Sử dụng** trên card
*Tesseract Vietnamese Best* (khuyến nghị cho tiếng Việt) hoặc *RapidOCR – PaddleOCR* (mặc định của bản phân phối).

Tương đương qua API (cần phiên đăng nhập quản trị viên):

```bash
curl -s -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://127.0.0.1:5055/api/ocr/engines/tesseract_best/activate
```

- Model Best gốc không bị Agri ghi đè: kiểm bằng `ocr status --no-db` (`tesseract_best … model=installed`).
- Các phiên bản Agri vẫn nằm trên volume dữ liệu; chọn lại Agri sau này không cần import lại.
- RapidOCR cần đã "Chuẩn bị" (`offline_ready`) trên container hiện tại; nếu chưa, bấm **Chuẩn bị** một lần (cần
  Internet).
- Không đổi engine nào khác, không đổi Force Full Page, không OCR lại tài liệu cũ.

## C. Rollback ứng dụng (v1.2.0 → v1.1.0-rc.2)

### C.1. Vì sao rollback này an toàn

So sánh mã nguồn `v1.1.0-rc.2..v1.2.0` (kiểm khi phát hành, mục C.5): **chỉ** có số phiên bản (`VERSION`,
`frontend/package.json`, hai dòng `version` trong `frontend/package-lock.json`) và tài liệu Markdown. Không có thay đổi
nào ở mã Python, mã giao diện, migration, `uv.lock`, `pyproject.toml`, `Dockerfile`, cấu hình compose hay workflow.

Do đó:

| Hạng mục | Khi hạ về rc.2 |
|---|---|
| Phiên bản schema cơ sở dữ liệu | **không đổi** — hai bản có cùng bộ migration; không cần và **không được** khôi phục cơ sở dữ liệu |
| Dữ liệu (notebook, nguồn, ghi chú, embedding, người dùng) | giữ nguyên; không xử lý lại, không OCR lại, không dựng lại embedding |
| Model Agri, manifest, lịch sử phiên bản | giữ nguyên — rc.2 có cùng Custom Model Manager, đọc đúng kho model |
| Engine đang chọn (kể cả `tesseract_agri`) | giữ nguyên — rc.2 biết cả năm engine, **không** cần đổi engine trước khi hạ |
| Cấu hình người dùng (Force Full Page, số luồng, biến `OCR_*`, `OCR_AUTO_FULL_PAGE_ON_WATERMARK`, cổng) | giữ nguyên — cùng ý nghĩa ở hai bản |
| Giao diện | hiển thị `1.1.0-rc.2` thay vì `1.2.0` |

Lưu ý: khi bản `v1.2.0` là **Latest** trên GitHub, giao diện của bản rc.2 có thể hiện thông báo "có phiên bản mới"
(kiểm tra cập nhật đọc Latest Release). Đây chỉ là thông báo, không tự cập nhật gì.

Khác với hạ cấp về `v1.1.0-rc.1` (bản chưa có Agri — phải chọn engine khác trước, xem
[OCR_ROLLBACK.md](OCR_ROLLBACK.md) ghi chú Phase 10), hạ từ `v1.2.0` về `v1.1.0-rc.2` không có bước chuẩn bị nào.

### C.2. Cần giữ trước khi nâng cấp lên v1.2.0

1. **Commit rollback:** commit của tag `v1.1.0-rc.2` (`git rev-parse 'v1.1.0-rc.2^{commit}'`); ghi lại thêm
   `PREV_COMMIT=$(git rev-parse HEAD)` ở thư mục triển khai trước khi cập nhật mã.
2. **Image rollback:** gắn tag riêng cho **đúng image ID đang chạy** trước khi gắn image mới vào tag dùng chung:

   ```bash
   cd /srv/example/chatbot5400
   TS=$(date +%Y%m%d-%H%M%S)
   RUNNING_IMAGE=$(docker inspect -f '{{.Image}}' "$(docker compose ps -q open_notebook)")
   echo "$RUNNING_IMAGE"                                        # ghi lại image ID
   docker tag "$RUNNING_IMAGE" "chatbot5400:rollback-pre-v120-$TS"
   docker image inspect -f '{{.Id}}' "chatbot5400:rollback-pre-v120-$TS"   # phải bằng RUNNING_IMAGE
   ```

   Không xóa image này cho tới khi chủ dự án xác nhận bản mới ổn định (khuyến nghị tối thiểu 30 ngày).
3. **Sao lưu lạnh** dữ liệu và kiểm tra restore trên stack cô lập theo
   [OCR_PRODUCTION_DEPLOYMENT_PLAN.md](OCR_PRODUCTION_DEPLOYMENT_PLAN.md). Rollback ứng dụng **không** dùng tới bản
   sao lưu; nó chỉ để dự phòng sự cố dữ liệu ngoài dự kiến.

### C.3. Các bước rollback

```bash
cd /srv/example/chatbot5400
docker compose stop open_notebook
git stash push -m "v120-local-$TS" -- docker-compose.yml          # chỉ khi file này có sửa đổi cục bộ
git checkout "$PREV_COMMIT"                                         # hoặc: git checkout v1.1.0-rc.2
git stash pop
cat VERSION                                                         # 1.1.0-rc.2
docker tag "chatbot5400:rollback-pre-v120-$TS" chatbot5400:local    # image cũ, không build lại
docker compose up -d --no-deps --no-build open_notebook             # chỉ container ứng dụng
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5055/health
```

**Luôn** kèm `--no-deps` và tên dịch vụ `open_notebook`: `docker compose up -d` cho cả stack có thể pull image cơ sở
dữ liệu mới và tạo lại container cơ sở dữ liệu. Nếu nơi triển khai có script khởi động riêng (kiểm tra cổng, chế độ
bảo trì), dùng script đó thay cho lệnh `docker compose up` ở trên. Không dùng `docker compose down -v`,
`docker system prune`, `docker volume prune`, `git reset --hard`.

### C.4. Kiểm tra sau rollback

| # | Kiểm tra | Đạt khi |
|---|---|---|
| 1 | `/health`; đăng nhập quản trị viên và người dùng thường | 200; vào được; trang đăng nhập hiển thị `1.1.0-rc.2` |
| 2 | Số notebook, nguồn, ghi chú, người dùng | bằng số ghi trước khi cập nhật |
| 3 | OCR Engine Manager | engine đang chọn như trước; năm card; Agri còn nguyên phiên bản đang hoạt động |
| 4 | `ocr custom verify`; `ocr custom status` | `file=ok`; phiên bản hoạt động như trước |
| 5 | `OCR_AUTO_FULL_PAGE_ON_WATERMARK` trong container | đúng như trước cập nhật |
| 6 | RapidOCR **Chuẩn bị** một lần (container vừa được tạo lại) | `offline_ready` |
| 7 | Upload một PDF tổng hợp (`tests/fixtures/ocr/`), rồi xóa | xử lý xong |

### C.5. Xác minh khi phát hành (đã thực hiện)

- `git diff --stat v1.1.0-rc.2 v1.2.0 -- . ':(exclude)*.md'` chỉ liệt kê `VERSION`, `frontend/package.json`,
  `frontend/package-lock.json`.
- `git diff v1.1.0-rc.2 v1.2.0 -- migrations/ open_notebook/database/ uv.lock pyproject.toml Dockerfile` rỗng.
- Kết quả cụ thể: [OCR_RELEASE_NOTES_V1.2.0.md](OCR_RELEASE_NOTES_V1.2.0.md) mục 10.

## D. Rollback GitHub Release

Nếu sau khi công bố phát hiện lỗi trong `v1.2.0`:

1. **Không** xóa, di chuyển hay ghi đè tag `v1.2.0`; **không** xóa Release; **không** force-push nhánh chính thức;
   **không** viết lại lịch sử Git đã công khai. Người đã tải bản này phải tìm lại được đúng mã đó.
2. Ghi cảnh báo ở đầu phần mô tả Release `v1.2.0` (mô tả lỗi, phạm vi ảnh hưởng, cách tránh, bản thay thế):

   ```bash
   gh release view v1.2.0 --json body -q .body > notes-v1.2.0.md
   # thêm khối cảnh báo vào đầu notes-v1.2.0.md
   gh release edit v1.2.0 --notes-file notes-v1.2.0.md
   ```

3. Nếu cần, đánh dấu lại một bản chính thức cũ là Latest (Pre-release không được đánh dấu Latest):

   ```bash
   gh release edit v1.0.8 --latest
   ```

4. Sửa lỗi trên một nhánh mới từ nhánh chính thức, qua Pull Request như thường lệ, rồi phát hành **`v1.2.1`** (tag
   trên commit sau merge) và đánh dấu Latest.
5. Các nơi triển khai đã cập nhật lên `v1.2.0` dùng mức C để quay về `v1.1.0-rc.2` trong lúc chờ `v1.2.1`.

Workflow *Build and Release* không build hay push image khi một Release được publish hoặc sửa
([OCR_RELEASE_NOTES_V1.2.0.md](OCR_RELEASE_NOTES_V1.2.0.md) mục 12), nên các thao tác trên không tác động tới máy chủ
nào.
