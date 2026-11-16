# Kế hoạch cập nhật production — ChatBot5400 v1.1.0-rc.2

Cập nhật: 2026-11-16 (Phase 10I, sau khi gắn tag `v1.1.0-rc.2`) · **KẾ HOẠCH — CHƯA THỰC HIỆN.** Cần chủ dự án phê duyệt trước khi làm bất kỳ bước
nào trên production. Tài liệu này bổ sung cho quy trình chung ở
[OCR_PRODUCTION_DEPLOYMENT_PLAN.md](OCR_PRODUCTION_DEPLOYMENT_PLAN.md) (sao lưu lạnh, kiểm tra restore, chế độ bảo
trì) và chỉ ghi những gì **riêng** cho lần cập nhật từ bản đang chạy lên `v1.1.0-rc.2`.

Tài liệu công khai: không ghi mật khẩu, khóa, token, nội dung `.env`, đường dẫn bản sao lưu thật, tên tài liệu hay
thông tin khách hàng. `BACKUP_DIR` và `/duong/dan/…` là đường dẫn do người vận hành chọn, ngoài repository; `/srv/example/chatbot5400`
(thư mục triển khai) và `/srv/example/cb5400-rc2-build` (thư mục dựng image) là đường dẫn **minh họa** — thay bằng
thư mục thật. Bản kế hoạch với giá trị thật của nơi triển khai do chủ dự án lưu ngoài repository.

## 1. Lần cập nhật này thay đổi gì trên production

| | Hiện tại | Sau cập nhật |
|---|---|---|
| Thư mục, compose project | thư mục triển khai hiện có (ví dụ `/srv/example/chatbot5400`) và compose project của nó | không đổi |
| Commit | commit đang chạy — mã ứng dụng của `v1.1.0-rc.1` | commit của tag `v1.1.0-rc.2` (giao diện hiển thị `1.1.0-rc.2`) |
| Image ứng dụng | `chatbot5400:local` (bản dựng 2026-11-14) | image dựng từ tag `v1.1.0-rc.2`, có Tesseract; gắn thêm tag `chatbot5400:rc2-<ngày>` |
| Container và image cơ sở dữ liệu | đang chạy | **giữ nguyên** — không pull, không tạo lại |
| Dữ liệu | `./notebook_data`, `./surreal_data` | không đổi; **không có migration** |
| Phụ thuộc Python / hệ thống | theo `uv.lock`, `Dockerfile` của rc.1 | **không đổi** (`uv.lock`, `Dockerfile` giống hệt rc.1) |
| Engine OCR đang chọn, Force Full Page, số luồng | giá trị đã lưu | **giữ nguyên** — bản mới không tự chuyển engine |
| OCR Engine Manager | bốn lựa chọn | thêm card thứ năm *Tesseract Vietnamese Agri* ở trạng thái "Chưa cài đặt", nhãn **Thử nghiệm** |
| `OCR_AUTO_FULL_PAGE_ON_WATERMARK` | không đặt | **không đặt (tắt)** — hành vi OCR giống hệt rc.1 |
| Cổng, mạng, khóa mã hóa, mật khẩu DB, nhà cung cấp LLM / embedding, URL ingestion (tắt) | — | không đổi |

Không có biến môi trường mới nào **bắt buộc**. Hai việc sau là **tùy chọn**, mỗi việc cần một quyết định riêng của
chủ dự án và có thể làm vào ngày khác: import model Agri (mục 8) và bật cơ chế tự OCR toàn trang (mục 9).

Đã kiểm chứng trước (không đụng production):

- nâng cấp `v1.1.0-rc.1` → bản mới trên stack cô lập: dữ liệu và cài đặt được giữ, chuẩn bị online, vận hành
  offline, restart khi offline, cập nhật rồi offline lại — Docker acceptance 53 PASS / 0 FAIL
  ([OCR_PHASE10H_REPORT.md](OCR_PHASE10H_REPORT.md));
- quay lại image `v1.1.0-rc.1` rồi tiến lại bản mới trên cùng dữ liệu ([OCR_PHASE10_REPORT.md](OCR_PHASE10_REPORT.md), T16);
- sửa đổi cục bộ của `docker-compose.yml` ở nơi triển khai áp sạch lên bản của rc.2: thử chỉ-đọc bằng
  `git apply --check`, không ghi gì vào thư mục production.

## 2. Điều kiện trước khi bắt đầu

1. Nhánh đã merge vào nhánh chính thức; tag `v1.1.0-rc.2` đã được tạo **trên commit sau merge** và chủ dự án đã ghi
   lại mã commit đó. Chủ dự án phê duyệt kế hoạch này.
2. Cửa sổ bảo trì đã thông báo: dịch vụ ngừng khoảng 20–30 phút (phần lớn là sao lưu lạnh và kiểm tra restore).
3. Máy chủ có Internet trong lúc cập nhật (RapidOCR cần "Chuẩn bị" lại một lần sau khi container được tạo lại).
4. Có tài khoản kiểm thử: một quản trị viên, một người dùng thường.
5. Đã quyết định: có import model Agri trong đợt này hay không (mục 8). Cờ ở mục 9 **giữ tắt** trong đợt này.
6. Người thực hiện đã đọc [OCR_ROLLBACK.md](OCR_ROLLBACK.md) (các ghi chú Phase 10 và Phase 10G).

## 3. Chuẩn bị trước khi dừng dịch vụ (không gián đoạn)

Dựng image trong một thư mục **riêng**, tag riêng; không ghi đè `chatbot5400:local`.

```bash
TAG=v1.1.0-rc.2
BUILD=/srv/example/cb5400-rc2-build
git clone --no-checkout /srv/example/chatbot5400 "$BUILD"
git -C "$BUILD" fetch "$(git -C /srv/example/chatbot5400 remote get-url origin)" "refs/tags/$TAG:refs/tags/$TAG"
git -C "$BUILD" checkout --detach "$TAG"
git -C "$BUILD" rev-parse HEAD                 # phải bằng commit chủ dự án đã ghi lại ở điều kiện 2.1
cat "$BUILD/VERSION"                           # 1.1.0-rc.2
RC_TAG="chatbot5400:rc2-$(date +%Y%m%d)"
docker build --target runtime --build-arg OCR_INSTALL_TESSERACT=true -t "$RC_TAG" "$BUILD"
docker image inspect "$RC_TAG" --format '{{.Id}}'
docker run --rm --network none --entrypoint sh "$RC_TAG" -c 'tesseract --version | head -1'
```

Ghi lại trước khi dừng (để so sau cập nhật): số notebook, nguồn, ghi chú, người dùng; engine OCR đang chọn và trạng
thái readiness của từng engine trong OCR Engine Manager.

## 4. Sao lưu lạnh và kiểm tra restore

Làm đúng [OCR_PRODUCTION_DEPLOYMENT_PLAN.md](OCR_PRODUCTION_DEPLOYMENT_PLAN.md) mục 4 và mục 5, với tên tag rollback
của đợt này:

```bash
cd /srv/example/chatbot5400
TS=$(date +%Y%m%d-%H%M%S)
docker tag chatbot5400:local "chatbot5400:rollback-pre-rc2-$TS"     # image đang chạy, giữ để rollback
```

Sao lưu hoặc kiểm tra restore không đạt ⇒ **không cập nhật**; `docker compose start` để bản cũ chạy lại.

## 5. Cập nhật mã

```bash
cd /srv/example/chatbot5400
PREV_COMMIT=$(git rev-parse HEAD); echo "$PREV_COMMIT"                # ghi lại: đích của rollback mã (mục 10)
git fetch origin "refs/tags/$TAG:refs/tags/$TAG"
git stash push -m "local-before-rc2-$TS" -- docker-compose.yml       # chỉ file theo dõi đã sửa cục bộ
git merge --ff-only "$TAG" && git rev-parse HEAD                     # phải bằng commit của tag
git stash pop                                                        # áp lại sửa đổi cục bộ
git status --short                                                   # 1 file sửa + các file không theo dõi như trước
```

Nếu `git stash pop` báo xung đột: **không** tự giải quyết bằng cách ghi đè; khôi phục `docker-compose.yml` từ bản
sao lưu và đối chiếu thủ công. Không dùng `git reset --hard`, không `git pull` mù.

Cấu hình: **không sửa gì** trong `docker-compose.override.yml` và `.env`. Cụ thể là **không** thêm
`OCR_AUTO_FULL_PAGE_ON_WATERMARK` và không thêm `OCR_AGRI_WITH_ENGLISH`.

## 6. Khởi động bản mới

```bash
cd /srv/example/chatbot5400
docker tag "$RC_TAG" chatbot5400:local                       # image cũ vẫn còn dưới tag rollback-pre-rc2-$TS
docker compose start surrealdb                               # CÙNG container DB, không pull, không tạo lại
docker compose up -d --no-deps --no-build open_notebook      # chỉ tạo lại container ứng dụng
docker compose logs -f --tail 50 open_notebook               # chờ "Application startup complete"
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5055/health
docker compose ps
```

**Luôn** kèm `--no-deps open_notebook`: `docker compose up -d` không có tên dịch vụ sẽ pull image cơ sở dữ liệu mới
và tạo lại container DB. Nếu chủ dự án muốn kiểm tra trước khi mở lại cho người dùng, khởi động ở **chế độ bảo trì**
([OCR_OPERATOR_GUIDE.md](OCR_OPERATOR_GUIDE.md) mục 11).

## 7. Kiểm tra sau cập nhật

Chỉ dùng tài liệu tổng hợp trong `tests/fixtures/ocr/`; xóa nguồn thử sau khi xong.

| # | Kiểm tra | Đạt khi |
|---|---|---|
| 1 | `/health`; đăng nhập quản trị viên và người dùng thường | 200; vào được; trang đăng nhập hiển thị `1.1.0-rc.2` |
| 2 | Số notebook, nguồn, ghi chú, người dùng | bằng số ghi ở mục 3 |
| 3 | OCR Engine Manager | engine đang chọn **không đổi**; bốn card cũ như trước; không có cảnh báo phiên bản phụ thuộc |
| 4 | Card *Tesseract Vietnamese Agri* | "Chưa cài đặt", nhãn **Thử nghiệm**, không có nút **Sử dụng** |
| 5 | RapidOCR: bấm **Chuẩn bị** một lần (container vừa được tạo lại) | `offline_ready` |
| 6 | Readiness của Tesseract Vietnamese Best | vẫn như trước; nếu về "chưa kiểm tra" thì bấm **Chuẩn bị** một lần |
| 7 | Upload `vb_text.pdf` và `vb_scan.pdf` | xử lý xong; nội dung như trước cập nhật |
| 8 | Cơ chế tự OCR toàn trang đang **tắt** | hai lệnh dưới bảng in `[]` và `0` |
| 9 | Phân quyền: người dùng thường gọi `POST /api/ocr/engines/tesseract_agri/custom/activate` | 403 |
| 10 | Thêm nguồn từ URL | vẫn bị từ chối (403) |
| 11 | `docker compose logs` 15 phút; `docker compose ps` | không lỗi lặp lại, restart = 0 |

```bash
docker compose exec open_notebook sh -c 'echo "[$OCR_AUTO_FULL_PAGE_ON_WATERMARK]"'
docker compose logs --since 30m open_notebook | grep -c "OCR mode:"
```

## 8. Tùy chọn — import model Tesseract Vietnamese Agri

Chỉ làm khi chủ dự án quyết định. Agri là engine **Thử nghiệm**: chất lượng mới được đo trên văn bản tổng hợp
([OCR_AGRI_BENCHMARK.md](OCR_AGRI_BENCHMARK.md)); import không làm đổi engine đang chọn.

Compose production không có thư mục `/import`. Cách không phải sửa cấu hình: chép file vào một thư mục tạm **trong
container**, import, rồi xóa bản tạm (bản đã import nằm bền trong `/app/data`).

```bash
cd /srv/example/chatbot5400
ocr() { docker compose exec open_notebook /app/.venv/bin/python -m open_notebook.ocr.cli "$@"; }
C=$(docker compose ps -q open_notebook)
sha256sum /duong/dan/vie_agri.traineddata                          # so với SHA-256 ghi tại máy fine-tune
docker exec "$C" mkdir -p /tmp/agri-import
docker cp /duong/dan/vie_agri.traineddata "$C":/tmp/agri-import/vie_agri.traineddata
ocr custom import --file /tmp/agri-import/vie_agri.traineddata --version v1 --notes "Agri fine-tune lan 1"
docker exec "$C" rm -rf /tmp/agri-import
ocr custom activate --version v1
ocr custom status                                                  # ready · active version v1 · offline_ready
```

Dòng `stored … sha256 …` của lệnh import phải trùng SHA-256 vừa tính. Sau đó card Agri có nút **Sử dụng**; việc
**chọn** Agri làm engine xử lý tài liệu là một quyết định riêng nữa của quản trị viên. Chi tiết, phiên bản tiếp theo
và rollback phiên bản model: [OCR_AGRI_MODEL_GUIDE.md](OCR_AGRI_MODEL_GUIDE.md).

Model, dữ liệu huấn luyện và tài liệu nội bộ **không** được đưa vào repository hay image.

## 9. Tùy chọn — bật tự OCR toàn trang cho PDF scan có watermark chéo

Mặc định **tắt** và không thuộc đợt cập nhật này. Khi chủ dự án phê duyệt:

1. Thêm vào mục `environment` của `open_notebook` trong `docker-compose.override.yml` dòng
   `- OCR_AUTO_FULL_PAGE_ON_WATERMARK=true`.
2. `docker compose up -d --no-deps open_notebook`, rồi kiểm tra biến đã tới container (lệnh ở mục 7).
3. Theo dõi `docker compose logs open_notebook | grep "OCR mode:"`: mỗi PDF một dòng, chỉ gồm số đo.
   `reason=mixed_document` kèm `WARNING` = tài liệu hỗn hợp, **không** được sửa tự động.

Giới hạn (PDF hỗn hợp, watermark ngang, ngưỡng mới hiệu chuẩn trên PDF tổng hợp và một tài liệu thật):
[OCR_PHASE10G_REPORT.md](OCR_PHASE10G_REPORT.md) mục 6.3 và 13. Tắt lại: xóa dòng đó và tạo lại container ứng dụng.

## 10. Tiêu chí dừng và rollback

Dừng và rollback mã nếu sau khi khởi động bản mới có **bất kỳ** điều nào: `/health` không 200 trong 15 phút hoặc
container restart lặp lại; đăng nhập thất bại; số bản ghi thiếu; engine đang chọn bị đổi; kiểm tra 7, 9 hoặc 10 ở
mục 7 không đạt; OCR Engine Manager báo phiên bản phụ thuộc khác bộ đã kiểm chứng.

**Rollback mã (dữ liệu giữ nguyên):**

```bash
cd /srv/example/chatbot5400
# Nếu Agri đang là engine được chọn: chọn lại một engine khác TRƯỚC khi hạ image (OCR_ROLLBACK.md, ghi chú Phase 10)
docker compose stop open_notebook
git stash push -m "rc2-local-$TS" -- docker-compose.yml
git checkout "$PREV_COMMIT"                                         # commit đã ghi ở mục 5
git stash pop
docker tag "chatbot5400:rollback-pre-rc2-$TS" chatbot5400:local      # image cũ, không build lại
docker compose up -d --no-deps --no-build open_notebook
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5055/health
```

Bản cũ bỏ qua thư mục model custom, manifest và các biến `OCR_AUTO_FULL_PAGE_*` / `OCR_AGRI_*`; không có dữ liệu nào
cần hoàn tác. Khác với lần triển khai rc.1, bản đích của rollback (mã ứng dụng của rc.1) đã có đủ các bản vá phân quyền và công
tắc URL ingestion, nên rollback không mở lại các rủi ro đó.

**Rollback không đổi mã** (dùng trước tiên khi lỗi chỉ thuộc phần mới): tắt cờ ở mục 9; chọn lại engine cũ trong OCR
Engine Manager; `ocr custom rollback` để quay về phiên bản model trước.

**Rollback dữ liệu** chỉ khi dữ liệu hỏng và do chủ dự án quyết định: theo
[OCR_PRODUCTION_DEPLOYMENT_PLAN.md](OCR_PRODUCTION_DEPLOYMENT_PLAN.md) mục 10.

Không dùng `docker compose down -v`, `docker system prune`, `docker volume prune` trong bất kỳ bước nào.

## 11. Sau cập nhật

- Theo dõi 24 giờ bằng `scripts/ocr/production_health_check.sh` (không in biến môi trường hay nội dung tài liệu).
- Giữ bản sao lưu và image `chatbot5400:rollback-pre-rc2-<ts>` tối thiểu 30 ngày; thư mục dựng `cb5400-rc2-build` có
  thể xóa sau khi chủ dự án xác nhận.
- Ghi kết quả thực tế vào một báo cáo riêng (không ghi vào file này).

## 12. Checklist rút gọn

| # | Việc | Bắt buộc | Kết quả |
|---|---|---|---|
| 1 | Chủ dự án phê duyệt kế hoạch; ghi commit của tag `v1.1.0-rc.2` | Có | |
| 2 | Cửa sổ bảo trì đã thông báo; có Internet; có tài khoản kiểm thử | Có | |
| 3 | Image rc.2 dựng ở thư mục riêng, tag riêng, có Tesseract; `VERSION` = `1.1.0-rc.2` | Có | |
| 4 | Ghi số bản ghi, engine đang chọn, readiness trước khi dừng | Có | |
| 5 | Tag rollback cho image đang chạy; sao lưu lạnh; `SHA256SUMS`; kiểm tra restore trên stack cô lập | Có | |
| 6 | Cập nhật mã bằng `git merge --ff-only <tag>`; `git stash` / `git stash pop` cho `docker-compose.yml`; không sửa override và `.env` | Có | |
| 7 | Chỉ tạo lại container ứng dụng (`--no-deps --no-build open_notebook`); container DB giữ nguyên | Có | |
| 8 | Mục 7: cả 11 kiểm tra đạt | Có | |
| 9 | `OCR_AUTO_FULL_PAGE_ON_WATERMARK` không có trong container | Có | |
| 10 | Import model Agri (mục 8) | Tùy chọn — quyết định riêng | |
| 11 | Bật cờ (mục 9) | Tùy chọn — quyết định riêng, không thuộc đợt này | |
| 12 | Theo dõi 24 giờ; giữ sao lưu và image rollback 30 ngày | Có | |
