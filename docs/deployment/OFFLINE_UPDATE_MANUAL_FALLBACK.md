# Cập nhật offline thủ công — phương án dự phòng đơn giản (ChatBot5400)

> **Trạng thái (Phase 12D5): IMPLEMENTED — CHƯA VERIFIED.** Quy trình và gói đã có; các lệnh
> Docker cốt lõi (load, chuyển tag, recreate `--no-deps`, rollback bằng tag) đã chạy trên Docker
> thật trong phòng thí nghiệm Cloud với image thay thế (xem §12). Quy trình **chưa được diễn tập
> trên máy chủ Ubuntu offline thật**, với script vận hành, boot guard, SurrealDB và image ứng dụng
> thật. Chỉ được gọi là VERIFIED sau khi các mục W-FB-* trong
> `docs/review/PHASE12D5_LOCAL_ACCEPTANCE_CHECKLIST.md` đạt trên stack cô lập rồi trên production.
>
> **Đây là đường cập nhật khuyến nghị cho production** cho đến khi bộ cập nhật tự động
> (`offline_package.py update/finish/rollback`) được nghiệm thu cục bộ. Bộ cập nhật tự động hiện ở
> trạng thái **EXPERIMENTAL / NOT READY — không khuyến nghị cho production**.

## 0. Nguyên tắc

- **Độc lập với bộ cập nhật tự động**: không journal, không state machine, không lock của công cụ.
  Chỉ dùng `sha256sum`, `ssh-keygen`, `tar`, `python3` (đọc manifest), `docker`, `docker compose`,
  `git` (tùy chọn) và **script vận hành có sẵn của máy chủ**. Hai lệnh chỉ-đọc của công cụ
  (`snapshot`, `inventory`) là tùy chọn, có lệnh thay thế không cần công cụ.
- **Không bao giờ**: `docker compose down`, `-v`, `docker volume rm/prune`, `docker system prune`,
  `pull`, `build`, `git pull`, cài gói từ mạng (pip, npm, apt), truy cập Internet.
- **Database**: container DB không bao giờ bị tạo lại (`--no-deps`), không bao giờ restore tự động.
  Restore chỉ do người có thẩm quyền quyết định, theo quy trình của đơn vị (§10.3).
- **Không OCR lại, không re-embed** tài liệu cũ. Chế độ **Legal mặc định OFF** sau cập nhật.
- **Gói không chứa** database, model Agri, `.env`, khóa hay mật khẩu (kiểm ở §2.3).
- Dừng ngay khi một bước kiểm tra không đạt. "Dừng" nghĩa là: không làm bước tiếp theo, ghi lại
  kết quả, nếu đã chuyển image thì làm rollback (§10).

## 1. Điền một lần (LOCAL — không ghi vào repository công khai)

Các giá trị dưới đây là của máy chủ; repository chỉ chứa chỗ trống. Điền trong một file ghi chú
chỉ root đọc được (ví dụ trong thư mục quản trị của đơn vị), **không** commit.

| Biến | Ý nghĩa | Lấy từ đâu |
|---|---|---|
| `DEPLOY_DIR` | thư mục chứa các file compose của triển khai | script vận hành |
| `PROJECT` | tên Compose project **cố định** | script vận hành (`-p` / `name:`) |
| `FILES` | danh sách `-f …` **đúng thứ tự** script vận hành dùng ở chế độ thường — **đường dẫn tuyệt đối** | script vận hành |
| `MAINT` | `-f <override bảo trì>` (cổng chỉ loopback) — đường dẫn tuyệt đối | script vận hành (chế độ bảo trì) |
| `APP`, `DB` | tên service ứng dụng / database | file compose |
| `DEPLOY_TAG` | tham chiếu image mà compose của triển khai giao cho `APP` (ví dụ `chatbot5400:local`) | `docker compose config` |
| `OPS` | script vận hành và các lệnh `normal` / `maintenance` / `status` | đơn vị vận hành |
| `HEALTH_URL` | URL health loopback của API (ví dụ `http://127.0.0.1:5055/health`) | cấu hình |
| `SIGNERS`, `SIGNER` | file allowed_signers và danh tính người ký (nếu gói được ký) | §1.3 Ubuntu guide |
| Quy trình backup + kiểm restore | quy trình sao lưu SurrealDB của đơn vị | đơn vị vận hành |

**Điều kiện tiên quyết** (hợp đồng tích hợp, `OFFLINE_UPDATE_INTEGRATION_CONTRACT.md`):
C1 (`APP` dùng `DEPLOY_TAG`, không dùng số phiên bản hay digest), C2 (project cố định), C3 (biến môi
trường bắt buộc nằm trong cấu hình của đơn vị), C4 (chế độ bảo trì), C5 (boot guard khởi động qua
cùng file compose). Nếu một điều kiện chưa đúng: **không dùng quy trình này** cho đến khi đơn vị
sửa cục bộ (LOCAL VERIFICATION REQUIRED).

Mỗi phiên làm việc (root, `bash`), đặt biến cho phiên:

```bash
VER=1.3.0                                   # phiên bản trong gói
PKG=ChatBot5400-$VER-linux-amd64-offline     # tên gói, không có .tar.gz
WORK=/var/tmp/cb5400-$VER                    # thư mục làm việc MỚI (§3)
NOTES=$WORK/notes.txt
# DEPLOY_DIR, PROJECT, FILES, MAINT, APP, DB, DEPLOY_TAG, HEALTH_URL: giá trị của §1
cd "$DEPLOY_DIR"
DC="docker compose --project-directory $DEPLOY_DIR -p $PROJECT $FILES"
```

`docker compose` hiểu đường dẫn `-f` tương đối theo **thư mục hiện tại**, không theo
`--project-directory`: một đường dẫn tương đối gõ từ thư mục khác sẽ chọn file compose khác (đã
gặp khi diễn tập — nó kéo image và build theo file của thư mục đó). Vì vậy `FILES` và `MAINT` luôn
là đường dẫn tuyệt đối.

## 2. Máy build (có Internet) — tạo gói

1. Build bằng script chính thức: Windows `scripts\offline\build-package.ps1 -Version <ver>`
   (`OFFLINE_UPDATE_WINDOWS_BUILD.md`) hoặc Linux `scripts/offline/build-package.sh`. Gói gồm:
   `images/chatbot5400-<ver>.tar` (`docker save`), `source/chatbot5400-<ver>.bundle` (git bundle),
   `source/chatbot5400-<ver>-src.tar.gz`, `manifest.json`, `SHA256SUMS`, `manifest.json.sig`
   (nếu ký), `scripts/`, `docs/` (gồm tài liệu này).
2. Gửi giá trị SHA-256 của file `.tar.gz` cho người vận hành qua **kênh tin cậy riêng** (không
   gửi cùng gói).
3. Kiểm gói không chứa dữ liệu nội bộ:

   ```bash
   tar -tzf "$PKG.tar.gz" | grep -Ei '(^|/)\.env|traineddata|\.surql$|\.db$|secret|id_(rsa|ed25519)|\.pem$|\.key$' \
     && echo "STOP: gói chứa file không được phép" || echo "OK: không có file cấm"
   ```

## 3. Máy chủ — xác thực TRƯỚC khi giải nén

```bash
install -d -m 700 "$WORK"
# 3.1 SHA-256 so với giá trị nhận qua kênh tin cậy: phải in "<file>: OK"
echo "<SHA-256 nhận qua kênh tin cậy>  $PKG.tar.gz" | sha256sum -c -
```

Chỉ khi 3.1 in `OK`:

```bash
# 3.2 giải nén vào thư mục mới, không giữ chủ sở hữu / quyền từ archive
tar -xzf "$PKG.tar.gz" -C "$WORK" --no-same-owner --no-same-permissions
cd "$WORK/$PKG"
# 3.3 chữ ký (BẮT BUỘC khi máy chủ đã cài khóa công khai phát hành): phải in "Good ... signature"
ssh-keygen -Y verify -f "$SIGNERS" -I "$SIGNER" -n chatbot5400-offline -s manifest.json.sig < manifest.json
# 3.4 toàn vẹn từng file: mọi dòng "OK"
sha256sum -c SHA256SUMS
# 3.5 thông tin gói
python3 -I -c 'import json,sys; m=json.load(open(sys.argv[1])); a,i,s,d,r=m["application"],m["image"],m["source"],m["database"],m["readiness"]
print("version", a["version"], "| supported from", a["supported_source_versions"])
print("image", i["tag"], i["id"], "| provenance", i.get("provenance"))
print("commit", s["commit"], "| bundle ref", s["bundle_ref"])
print("schema", d["schema_version"], "| migration_required", d["migration_required"])
print("readiness", r["status"], r["problems"])' manifest.json | tee -a "$NOTES"
cd "$DEPLOY_DIR"
```

Dừng nếu: 3.3 không in `Good` khi khóa đã cài (hoặc thiếu `manifest.json.sig`); 3.4 có dòng
không `OK`; `readiness` khác `READY`; `provenance` khác `verified`; `migration_required` là
`True` (rollback không restore không còn đúng — cần kế hoạch riêng, ngoài quy trình này); phiên
bản đang chạy không nằm trong `supported from`.

## 4. Ghi trạng thái trước cập nhật (chưa ảnh hưởng người dùng)

```bash
APP_CID=$($DC ps -q "$APP"); DB_CID=$($DC ps -q "$DB")
{
  echo "taken_at=$(date -Is)"
  echo "app_container=$APP_CID"
  echo "app_image=$(docker inspect --format '{{.Image}}' "$APP_CID")"
  echo "deploy_tag_image=$(docker image inspect --format '{{.Id}}' "$DEPLOY_TAG")"
  echo "db_container=$DB_CID"
  echo "db_image=$(docker inspect --format '{{.Image}}' "$DB_CID")"
  echo "db_mounts=$(docker inspect --format '{{json .Mounts}}' "$DB_CID")"
  echo "git_head=$(git -C "$DEPLOY_DIR" rev-parse HEAD 2>/dev/null || echo none)"
} | tee -a "$NOTES"
```

- `app_image` phải bằng `deploy_tag_image`. Khác nhau = ứng dụng đang chạy không phải image mà tag
  chỉ tới (lệch từ trước): **dừng**, tìm nguyên nhân trước.
- Biến môi trường bắt buộc trong container đang chạy (chỉ in 3 biến này, không in biến khác):

  ```bash
  docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$APP_CID" \
    | grep -E '^OCR_(OFFLINE|RAPIDOCR_PERSISTENT|LEGAL_NORMALIZATION_ENABLED)='
  ```

  Cần `OCR_OFFLINE=true` và `OCR_RAPIDOCR_PERSISTENT=true`; `OCR_LEGAL_NORMALIZATION_ENABLED`
  vắng hoặc `false`. Thiếu: thêm vào cấu hình cục bộ của đơn vị (override / `.env`) trước §7 —
  v1.2.0 đã hiểu hai biến này, thêm trước không ảnh hưởng.
- Model trên volume (gồm model Agri) — danh sách SHA-256:

  ```bash
  MODELS=$(docker exec "$APP_CID" /app/.venv/bin/python -c 'from open_notebook.ocr import paths; print(paths.models_dir())')
  docker exec "$APP_CID" sh -c "cd '$MODELS' && find . -type f -print0 | sort -z | xargs -0 -r sha256sum" > "$WORK/models-before.sha256"
  wc -l "$WORK/models-before.sha256"
  ```

- Dữ liệu. Cách khuyến nghị (chỉ đọc, so cả định danh bản ghi): lệnh `snapshot` của gói, với file
  cấu hình chỉ chứa đường dẫn (`scripts/offline-update.conf.example`):

  ```bash
  python3 "$WORK/$PKG/scripts/offline_package.py" snapshot --config /etc/chatbot5400/offline-update.conf --out "$WORK/before.json"
  ```

  Không dùng công cụ: số bản ghi từng bảng (yếu hơn — chỉ số lượng):

  ```bash
  docker exec "$APP_CID" /app/.venv/bin/python -c '
  import asyncio
  from open_notebook.database.repository import repo_query
  async def m():
      for t in ("source", "notebook", "note", "source_embedding", "source_insight"):
          r = await repo_query(f"SELECT count() AS n FROM {t} GROUP ALL")
          print(t, r[0]["n"] if r else 0)
  asyncio.run(m())' | tee "$WORK/counts-before.txt"
  ```

- Dung lượng trống: `df -h /var/lib/docker` ≥ 2 × kích thước `images/*.tar` + 5 GB.

## 5. Nạp image mới (chưa ảnh hưởng người dùng)

```bash
docker load -i "$WORK/$PKG/images/chatbot5400-$VER.tar"          # "Loaded image: chatbot5400:<ver>"
NEW_ID=$(docker image inspect --format '{{.Id}}' "chatbot5400:$VER"); echo "new_image=$NEW_ID" | tee -a "$NOTES"
# nhãn của image phải là commit và phiên bản của manifest (§3.5)
docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}} {{index .Config.Labels "org.opencontainers.image.version"}}' "chatbot5400:$VER"
# giữ image đang chạy dưới một tên để rollback (và để không bị dọn nhầm)
OLD_ID=$(grep '^app_image=' "$NOTES" | cut -d= -f2)
docker tag "$OLD_ID" "chatbot5400:rollback-before-$VER"
# image mới đếm token được KHÔNG cần mạng: phải in "result": "PASS"
docker run --rm --network none -e OCR_OFFLINE=true --entrypoint /app/.venv/bin/python "chatbot5400:$VER" \
  -c 'from open_notebook.utils.token_utils import main; raise SystemExit(main(["--check"]))'
```

Dừng nếu nhãn không khớp manifest, hoặc kiểm tokenizer không `PASS`. (ID có thể khác `image.id`
của manifest khi máy build và máy chủ dùng kho image khác nhau — containerd và overlay2 —
vì archive đã được xác thực ở §3 nên đó không phải lỗi; nhãn phải khớp.)

## 6. Dừng ghi và sao lưu (bắt đầu cửa sổ bảo trì)

1. Thông báo cửa sổ bảo trì. Chuyển sang chế độ bảo trì bằng script vận hành: `$OPS maintenance`
   (ứng dụng vẫn chạy image cũ; chỉ quản trị truy cập được).
2. Kiểm cổng: `docker port "$($DC ps -q "$APP")"` — mọi dòng là `127.0.0.1:…` (hoặc không có cổng).
   Triển khai sau reverse proxy (không publish cổng): cổng không chứng minh được gì — chặn truy
   cập của người dùng theo quy trình của đơn vị và dựa vào phép so F1 == F2 ở bước 6.
3. Chờ tác vụ nền xong — lệnh sau phải in `0`:

   ```bash
   docker exec "$($DC ps -q "$APP")" /app/.venv/bin/python -c '
   import asyncio
   from open_notebook.database.repository import repo_query
   async def m():
       r = await repo_query("SELECT count() AS n FROM command WHERE status IN [\"running\",\"queued\",\"new\"] GROUP ALL")
       print(r[0]["n"] if r else 0)
   asyncio.run(m())'
   ```

4. Ảnh chụp dữ liệu F1 — trạng thái mà bản sao lưu sẽ chứa (từ đây không còn ai ghi):

   ```bash
   # ghi f1.json và so với §4: mã thoát 0 = không mất gì (bản ghi thêm từ §4 tới giờ là bình thường)
   python3 "$WORK/$PKG/scripts/offline_package.py" snapshot --config /etc/chatbot5400/offline-update.conf --out "$WORK/f1.json" --compare "$WORK/before.json"
   ```

5. Sao lưu theo quy trình của đơn vị; ghi mã tham chiếu bản sao lưu vào `$NOTES`. Kiểm restore trên
   **bản sao dùng một lần** (không bao giờ trên DB production). Chưa kiểm được: **dừng**.
6. Không có gì ghi trong lúc sao lưu — ảnh chụp F2 phải **giống hệt** F1 (số lượng, định danh và
   dấu thời gian cập nhật của bản ghi):

   ```bash
   python3 "$WORK/$PKG/scripts/offline_package.py" snapshot --config /etc/chatbot5400/offline-update.conf --out "$WORK/f2.json"
   python3 -I -c 'import json,sys; a,b=(json.load(open(f))["data"] for f in sys.argv[1:]); print("F1 == F2" if a == b else "DIFFERENT: something wrote during the backup"); sys.exit(a != b)' "$WORK/f1.json" "$WORK/f2.json"
   ```

   Không dùng công cụ: đếm như §4 ngay trước (F1) và ngay sau (F2) sao lưu, phải bằng nhau (chỉ
   số lượng — yếu hơn). Khác nhau: có ghi trong lúc sao lưu — chặn ghi rồi sao lưu lại.

## 7. Chuyển sang image mới trong chế độ bảo trì

```bash
# 7.1 (chỉ khi ghi chú phát hành yêu cầu thay file compose / script) mã nguồn từ bundle, KHÔNG git pull
git -C "$DEPLOY_DIR" bundle verify "$WORK/$PKG/source/chatbot5400-$VER.bundle"
git -C "$DEPLOY_DIR" fetch "$WORK/$PKG/source/chatbot5400-$VER.bundle" "refs/cb5400-offline/build/$VER:refs/cb5400-offline/build/$VER"
git -C "$DEPLOY_DIR" merge --ff-only "<commit của manifest>"   # không fast-forward được: DỪNG
# 7.2 chuyển tag triển khai sang image mới (con trỏ DUY NHẤT tới image được dùng)
docker tag "chatbot5400:$VER" "$DEPLOY_TAG"
docker image inspect --format '{{.Id}}' "$DEPLOY_TAG"          # phải bằng new_image
# 7.3 tạo lại CHỈ ứng dụng, chế độ bảo trì: bằng script vận hành ...
$OPS maintenance
# ... hoặc lệnh tương đương (đúng file của script vận hành):
# $DC $MAINT up -d --no-deps --no-build --pull never --force-recreate "$APP"
```

Kiểm ngay sau 7.3 (đạt hết mới sang §8):

```bash
APP_CID=$($DC ps -q "$APP")
docker inspect --format '{{.Image}}' "$APP_CID"                  # = new_image
[ "$($DC ps -q "$DB")" = "$(grep '^db_container=' "$NOTES" | cut -d= -f2)" ] && echo "DB container unchanged" || echo "STOP: DB container changed"
docker inspect --format '{{.Image}} {{json .Mounts}}' "$($DC ps -q "$DB")"   # = db_image, db_mounts
curl -fsS --noproxy '*' "$HEALTH_URL" && echo
docker exec "$APP_CID" /app/.venv/bin/python -c 'from open_notebook.utils.token_utils import main; raise SystemExit(main(["--check"]))'   # "PASS"
docker exec -i "$APP_CID" sh -c "cd '$MODELS' && sha256sum --quiet -c -" < "$WORK/models-before.sha256" && echo "models unchanged"
python3 "$WORK/$PKG/scripts/offline_package.py" snapshot --config /etc/chatbot5400/offline-update.conf --out "$WORK/after-update.json" --compare "$WORK/f1.json"   # 0 = không mất gì
$DC logs --tail 200 "$APP" | grep -iE 'migration|error' || true
```

Mọi khác biệt (DB container khác, bản ghi mất, model đổi, health lỗi, tokenizer không PASS):
**rollback ngay (§10)**, không mở cho người dùng.

## 8. Nghiệm thu chức năng (vẫn bảo trì, quản trị truy cập qua loopback / SSH tunnel)

Đăng nhập; mở sổ ghi chép và nguồn cũ (nội dung còn nguyên); tìm kiếm; chat có trích dẫn; tải lên
một PDF thử **tổng hợp** (không phải tài liệu nghiệp vụ) và chờ xử lý xong (worker chạy); OCR ở
chế độ Standard cho kết quả như trước; Legal vẫn OFF. Không đạt: §10.

## 9. Mở lại cho người dùng

```bash
$OPS normal          # tạo lại ứng dụng ở chế độ thường; tag đã chỉ image mới nên KHÔNG đổi image
APP_CID=$($DC ps -q "$APP"); docker inspect --format '{{.Image}}' "$APP_CID"   # = new_image
docker port "$APP_CID"                                                          # cổng LAN / Tailscale như cấu hình
curl -fsS --noproxy '*' "$HEALTH_URL" && echo
$OPS status
```

Ghi vào `$NOTES`: thời điểm, người phê duyệt, `new_image`, mã bản sao lưu. Khi có cửa sổ: khởi động
lại máy chủ một lần và kiểm boot guard đưa lên đúng `new_image` (W-FB-09).

## 10. Rollback

### 10.1 Ứng dụng (bất kỳ lúc nào sau §7)

```bash
docker tag "chatbot5400:rollback-before-$VER" "$DEPLOY_TAG"     # hoặc: docker tag "$OLD_ID" "$DEPLOY_TAG"
docker image inspect --format '{{.Id}}' "$DEPLOY_TAG"            # = app_image của §4
$OPS maintenance                                                 # hoặc lệnh tương đương ở §7.3
# kiểm như sau 7.3: image = app_image của §4, DB container không đổi, health, snapshot --compare f1.json
$OPS normal
```

### 10.2 Mã nguồn (chỉ khi đã làm 7.1)

```bash
git -C "$DEPLOY_DIR" reset --keep "$(grep '^git_head=' "$NOTES" | cut -d= -f2)"   # --keep: dừng nếu có thay đổi cục bộ bị ghi đè
```

Biến môi trường đã thêm ở §4 có thể giữ (v1.2.0 hiểu chúng).

### 10.3 Database — KHÔNG thuộc rollback

Rollback ứng dụng không chạm database. Chỉ khi phép so dữ liệu cho thấy mất / đổi dữ liệu, người
có thẩm quyền mới quyết định restore từ bản sao lưu của §6 theo quy trình của đơn vị. Gói có
`migration_required: True` không thuộc phạm vi quy trình này.

### 10.4 Chế độ Legal

Legal OFF là mặc định. Bật Legal là quyết định riêng sau nghiệm thu: đặt
`OCR_LEGAL_NORMALIZATION_ENABLED=true` trong cấu hình cục bộ, tạo lại ứng dụng bằng script vận
hành; tắt: xóa biến hoặc đặt `false`, tạo lại. Chỉ ảnh hưởng tài liệu xử lý SAU đó; tài liệu cũ
không bị OCR lại.

## 11. Dọn dẹp (sau thời gian ổn định)

Giữ `chatbot5400:rollback-before-$VER` tới bản phát hành sau. Xóa `$WORK` (ghi chú đã lưu nơi
khác). Không `docker system prune -a`, không `docker volume prune`.

## 12. Trạng thái xác minh

| Phần | Trạng thái |
|---|---|
| Gói (image archive, bundle, manifest, SHA256SUMS, chữ ký, tài liệu) | do `build` tạo; test tự động `tests/test_offline_package.py` (Cloud) |
| §2 `docker save` → §3 `sha256sum -c` (gói bị sửa 1 byte bị chặn) → §5 `docker load` + nhãn + tag rollback → §6 bảo trì chỉ loopback → §7 chuyển `DEPLOY_TAG`, `up -d --no-deps … app` → §9 chế độ thường; `docker compose up -d` thường, `docker restart`, recreate giữ image của tag → §10.1 rollback bằng tag; DB container giữ ID, image, mount và dữ liệu suốt quá trình; tag phiên bản trong compose (vi phạm C1) không bị chuyển | chạy trên Docker 29.10 thật (containerd image store, Compose v5), image thay thế tạo bằng `docker commit` từ busybox, Cloud — `tests/test_offline_manual_fallback_real_docker.py` (`CB5400_REAL_DOCKER=1`, 2 passed) |
| Tokenizer offline (`token_utils --check`) | test Cloud với file mã hóa thật đã kiểm SHA-256; image thật: LOCAL (W-FB-04) |
| Script vận hành, boot guard, SurrealDB thật, image ứng dụng thật, Ubuntu production, quy trình backup / restore của đơn vị | **LOCAL VERIFICATION REQUIRED** (W-FB-01…12) |
