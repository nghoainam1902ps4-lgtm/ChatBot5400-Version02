# Gói cập nhật offline ChatBot5400 — kiến trúc và định dạng

Quyết định: D-35 ([../ocr/DECISIONS.md](../ocr/DECISIONS.md)). Công cụ: `scripts/offline/`.
Trạng thái Phase 12D5: tooling sửa theo hai vòng audit (12D2, 12D4), kiểm thử với Docker giả lập có trạng thái **và**
diễn tập trên Docker 29 thật với image thay thế; gói của image ứng dụng thật **chưa build** — build trên Windows:
[OFFLINE_UPDATE_WINDOWS_BUILD.md](OFFLINE_UPDATE_WINDOWS_BUILD.md). Định dạng gói: **3** (thêm
`image.run_config_sha256`, `image.provenance`; gói định dạng 1 và 2 bị từ chối với "rebuild the package").

> **Production dùng quy trình thủ công** [OFFLINE_UPDATE_MANUAL_FALLBACK.md](OFFLINE_UPDATE_MANUAL_FALLBACK.md) theo
> [hợp đồng tích hợp](OFFLINE_UPDATE_INTEGRATION_CONTRACT.md). Bộ cập nhật tự động (`update` / `finish` / `rollback`)
> là **EXPERIMENTAL / NOT READY — không khuyến nghị cho production** cho tới khi nghiệm thu cục bộ.

## 1. Vì sao cần

Máy chủ Ubuntu production đã offline hoàn toàn: không `git pull`, Docker Hub/GHCR, PyPI (`uv`/`pip`), npm, Hugging
Face, tải model Tesseract, OpenRouter. Image v1.2.0 hiện **không chứa Docling**: entrypoint cài Docling lúc khởi động
(`OPEN_NOTEBOOK_ENABLE_DOCLING`) từ Internet hoặc từ uv cache trên volume; trọng số RapidOCR nằm trong venv của
container nên **mất khi tạo lại container** (OCR_OPERATOR_GUIDE §11: "RapidOCR cần Chuẩn bị lại khi có Internet").
Gói offline xử lý cả hai.

## 2. Nội dung gói

```
ChatBot5400-<version>-linux-amd64-offline.tar.gz
└── ChatBot5400-<version>-linux-amd64-offline/
    ├── manifest.json            mô tả + SHA-256 + kích thước của MỌI file bên dưới
    ├── manifest.json.sig        (tùy chọn) chữ ký ssh-keygen -Y, namespace chatbot5400-offline
    ├── SHA256SUMS               cùng thông tin, định dạng sha256sum
    ├── images/chatbot5400-<version>.tar          docker save (giữ metadata image)
    ├── source/chatbot5400-<version>.bundle       git bundle v1.2.0..refs/cb5400-offline/build/<version>
    ├── source/chatbot5400-<version>-src.tar.gz   git archive (máy chủ không dùng git)
    ├── scripts/  offline_package.py verify-package.sh preflight.sh update.sh finish.sh pin.sh rollback.sh
    │             healthcheck.sh status.sh snapshot.sh offline-update.conf.example
    └── docs/     OFFLINE_UPDATE_*.md (gồm MANUAL_FALLBACK và INTEGRATION_CONTRACT), RELEASE_NOTES.md
```

Kèm theo bên ngoài: `<gói>.tar.gz.sha256` — để người build đọc giá trị và gửi cho người vận hành qua **kênh tin cậy
riêng**. Bản thân file `.sha256` đi cùng gói **không** phải kênh tin cậy.

**Không bao giờ có trong gói**: database, `.env`, credential, API key, mật khẩu, model Agri, PDF nội bộ, backup,
tài khoản người dùng, IP / đường dẫn triển khai nội bộ (các script nhận đường dẫn từ file cấu hình cục bộ).
`validate_manifest` từ chối manifest trông giống chứa bí mật.

## 3. Docker image trong gói

Build bằng `scripts/offline/build-package.{ps1,sh}`:

```
docker buildx build --platform linux/amd64 --load --target runtime \
  --build-arg OCR_INSTALL_TESSERACT=true --build-arg OCR_PREINSTALL_RUNTIMES=true \
  --label org.opencontainers.image.version=<version> --label org.opencontainers.image.revision=<commit> \
  -t chatbot5400:<version> .
```

- `OCR_PREINSTALL_RUNTIMES=true` (mới, mặc định `false` ⇒ build thường không đổi) cài Docling + EasyOCR **vào image**
  bằng đúng lệnh và đúng ràng buộc phiên bản mà entrypoint dùng (`uv pip install -c runtime-constraints.txt
  content-core[docling]==<bản đã khóa> easyocr==1.7.2`, torch CPU). Entrypoint thấy `docling` đã có ⇒ không cài gì.
- `OCR_INSTALL_TESSERACT=true` (có từ trước) đưa nhị phân Tesseract vào image.
- Tag rõ phiên bản `chatbot5400:<version>`; script **từ chối** ghi đè tag đã tồn tại; không dùng `latest`/`local`.
- **Phiên bản được kiểm trước mọi thao tác Docker**: file `VERSION` của commit phải khớp `--version`
  (`VERSION=1.2.0` ⇒ chỉ đóng gói được `1.2.0` hoặc `1.2.0-<hậu tố>`, ví dụ `1.2.0-phase12.1`; `1.3.0-rc.1` chỉ đóng
  gói được từ commit phát hành đã đổi `VERSION`). `VERSION` trong image cũng phải khớp.
- **Thứ tự build**: kiểm phiên bản → kiểm base là tổ tiên của commit → tạo **ref tạm**
  `refs/cb5400-offline/build/<version>` trỏ đúng commit → `git bundle create <base>..<ref>` → `git bundle verify` →
  `git bundle list-heads` phải có đúng ref đó trỏ đúng commit → **xóa ref tạm (kể cả khi lỗi)** → archive nguồn →
  kiểm image → inventory → `docker save`. Lỗi ở bất kỳ bước nào ⇒ thư mục đang dựng bị xóa, không để lại gói dở.
  (`git bundle create base..<sha>` bị git từ chối vì bundle chỉ mang *ref*; đây là lỗi F-04 của Phase 12.)
- Xuất bằng `docker save` (giữ layer, config, label, ID); **không** dùng `docker export/import`. File sau khi lưu
  được đọc lại: phải chứa đúng **một** tag là tag của gói; digest cấu hình và danh sách layer (`diff_ids`) được ghi
  vào manifest để máy chủ nhận diện image cả khi image store khác (ID khác).
- `inventory` chạy **bên trong image với `--network none`**: phiên bản Python/thư viện (docling, docling-core,
  content-core, torch, rapidocr, easyocr, tiktoken…), Tesseract, số phiên bản schema (số migration), artifact
  runtime, có/không Docling, và **bộ mã hóa token `o200k_base`**: thư mục cache, tên + kích thước + SHA-256 từng
  file cache, và việc nạp được hay không khi không có mạng ⇒ ghi vào manifest. Thiếu Docling, thiếu Tesseract hoặc
  tiktoken không nạp được offline ⇒ `readiness: NOT_READY` và cập nhật bị từ chối (trừ khi người vận hành chủ động
  `--accept-not-ready`).

## 4. Artifact runtime (không nằm trong image, tái sử dụng trên volume)

| Artifact | Vị trí trên volume dữ liệu | Cách gói xử lý |
|---|---|---|
| Docling Layout Heron, TableFormer accurate | `/app/data/.cache/huggingface` | giữ nguyên; không tải lại |
| Tesseract fast/best, `osd.traineddata` | `/app/data/ocr/models/tesseract` | giữ nguyên |
| Model Agri (người dùng import, có phiên bản) | `/app/data/ocr/models/tesseract/custom/agri/<version>` | giữ nguyên; không bao giờ đóng gói |
| EasyOCR | `/app/data/ocr/models/easyocr` | giữ nguyên |
| RapidOCR (PP-OCR onnx) | trong venv của container cũ | **trước khi tạo lại**: `installer.import_rapidocr_weights()` chạy trong container CŨ, chép sang `/app/data/ocr/models/rapidocr` sau khi kiểm SHA-256 theo danh sách của chính RapidOCR; **kết quả được kiểm** (mã thoát, từng file, có file trên volume) — lỗi ⇒ dừng trước khi tạo lại, trừ khi `--accept-missing-rapidocr`; container mới chạy với `OCR_RAPIDOCR_PERSISTENT=true` |
| Manifest / readiness / phiên bản custom | `/app/data/ocr` | giữ nguyên |
| Bộ mã hóa token tiktoken `o200k_base` | **trong image** (`/app/tiktoken-cache`, `TIKTOKEN_CACHE_DIR`) | inventory kiểm file cache (SHA-256) và nạp được khi `--network none`; bước O kiểm chính file cache + nạp bảng mã thật (không dựa vào tách đoạn); khi `OCR_OFFLINE=true` mà file cache thiếu hoặc khác SHA-256, ứng dụng **từ chối rõ ràng** (`TokenizerUnavailableError`): không tải, không ước lượng, không tạo chunk (Phase 12D5, R2-10) |

Ngoài trạng thái readiness do ứng dụng ghi, công cụ **tự chụp danh sách file model** (tên + kích thước + SHA-256) trên volume
như container cũ nhìn thấy — `ocr/models/**` (Tesseract fast/best/OSD, Agri, RapidOCR, EasyOCR) và cache Hugging Face
(Layout Heron, TableFormer) — ngay trước khi tạo lại container, rồi so lại trong container mới: file nào mất, đổi
kích thước, đổi nội dung (SHA-256) hoặc là liên kết hỏng ⇒ cập nhật `failed`. Nội dung chỉ được băm trong container,
không chép, không gửi đi.

Biến môi trường phiên bản mới cần (`OCR_RAPIDOCR_PERSISTENT=true`, `OCR_OFFLINE=true` — khóa `REQUIRED_APP_ENV`)
nằm trong **cấu hình của đơn vị** (override cục bộ / `.env`); từ Phase 12D5 công cụ không còn tiêm biến môi trường,
`preflight` từ chối khi thiếu (hợp đồng C3). Không ghi đè model đang dùng; không tải gì khi khởi động.

**`docker load` thành công không chứng minh pipeline OCR chạy offline**: bước O chạy `ocr.cli readiness --check` (chỉ
cục bộ) và `healthcheck.sh --prove-offline` kiểm tra container không kết nối được ra ngoài.

Nếu sau này có artifact chính thức mới bắt buộc (ví dụ Docling đổi phiên bản layout) phải đóng gói riêng có checksum
+ giấy phép và **không** đánh dấu READY cho tới khi readiness offline đạt — Phase 12 không đổi Docling nên không cần.

## 5. Manifest (rút gọn)

```json
{
  "package_format_version": 3,
  "application": {"name": "ChatBot5400", "version": "1.3.0-rc.1", "release_tag": "v1.3.0-rc.1", "supported_source_versions": ["1.2.0"]},
  "platform": "linux/amd64",
  "image": {"tag": "chatbot5400:1.3.0-rc.1", "id": "sha256:…", "config_digest": "sha256:…", "diff_ids": ["sha256:…"],
            "repo_tags": ["chatbot5400:1.3.0-rc.1"], "archive_layout": "docker-archive",
            "archive": "images/chatbot5400-1.3.0-rc.1.tar", "archive_sha256": "…", "labels": {…},
            "run_config_sha256": "…", "provenance": "verified", "app_version": "1.3.0-rc.1"},
  "source": {"commit": "<40 hex>", "base_ref": "v1.2.0", "base_commit": "f2fdf27…",
             "bundle_ref": "refs/cb5400-offline/build/1.3.0-rc.1", "git_bundle": "source/…bundle", "archive": "source/…-src.tar.gz"},
  "database": {"schema_version": 33, "migration_required": false, "compatible_schema_versions": [33]},
  "dependencies": {"docling": "2.129.0", "docling-core": "2.96.0", "content-core": "2.0.7", "tesseract": "…", …},
  "runtime_artifacts": {…}, "readiness": {"status": "READY", "problems": []},
  "rollback": {"app_rollback_without_restore": true, "previous_versions": ["1.2.0"]},
  "build": {"timestamp": "…"},
  "files": {"images/…tar": {"sha256": "…", "size": 0}, …}
}
```

Phase 12 **không có migration** (schema 33, giống v1.2.0) ⇒ rollback ứng dụng không cần khôi phục database. Công cụ
**từ chối mọi gói `migration_required: true`** (migration offline cần quy trình riêng được phê duyệt).

Mọi trường đi vào YAML, git hoặc docker đều được **kiểm định dạng** khi đọc manifest (F-12): tag image
(`repo:tag`, không khoảng trắng/xuống dòng/tùy chọn), ID và digest (`sha256:<64 hex>`), commit (40 hex), release tag,
ref của bundle (chỉ trong `refs/cb5400-offline/build/`), phiên bản, đường dẫn file, checksum. `--to-image` và biến
môi trường của override được kiểm tương tự; giá trị trong override được đặt trong ngoặc kép.

## 6. Toàn vẹn và xác thực

- SHA-256 cho từng file (manifest + SHA256SUMS) và cho cả gói.
- Xác thực nguồn: **chữ ký** `ssh-keygen -Y sign` (khóa riêng giữ trên máy build, không bao giờ trong Git hay gói;
  khóa công khai cài trước ở `/etc/chatbot5400/allowed_signers`) **hoặc** SHA-256 của gói nhận qua kênh tin cậy riêng
  (`--expected-sha256`). Thiếu cả hai ⇒ **từ chối và không giải nén gì**. Hiện **chưa có khóa ký chính thức** ⇒ phải
  dùng hash; không gói nào được tuyên bố "đã xác thực bằng chữ ký".
- **Xác thực trước, giải nén sau** (F-14): hash cả gói và chữ ký của manifest (đọc từ archive vào bộ nhớ) được kiểm
  trước khi bất kỳ file nào được ghi; với chữ ký hợp lệ, từng file được so SHA-256 với manifest ngay khi ghi.
- Kiểm tra archive **trước** khi ghi đĩa: đường dẫn tuyệt đối, `..`, `.`, `\`, symlink, hardlink, file đặc biệt,
  **entry trùng tên**, nhiều thư mục gốc, > 5000 mục, > 64 GiB khi giải nén, tỷ lệ nén > 200×, **thiếu dung lượng
  trống**. Giải nén vào thư mục tạm rồi mới đổi tên; lỗi ⇒ xóa thư mục tạm (không để lại cây giải nén dở).
- File image được đọc **trước `docker load`** (F-25): đúng một image, đúng một tag đã duyệt, digest và layer khớp
  manifest. Preflight từ chối nếu tag đó đã tồn tại trên máy chủ dưới dạng image khác.
- Báo cáo verify **tin cậy** nằm ở `STATE_DIR/verified/<sha256 của gói>.json` (0600, thư mục 0700), gắn với SHA-256
  của gói, thư mục giải nén và manifest; `verify-report.json` cạnh gói chỉ để người đọc, **không** được tin (R2-07).
  `preflight`/`update`/`rollback --package-dir` kiểm lại manifest và mọi file mỗi lần chạy, và từ chối thư mục gói
  (hoặc thư mục cha) mà người khác ghi được (F-26a).
- `SIGNATURE_POLICY` (`required` mặc định khi đã cài `ALLOWED_SIGNERS`, nếu không `optional`): với `required`, gói
  không ký bị từ chối kể cả có `--expected-sha256`, và chữ ký được kiểm lại ở mỗi lần dùng; báo cáo không thể hạ
  "đã ký" thành "không ký".
- Danh tính image (R2-06, R2-08): image cục bộ chỉ được coi là image của gói khi cùng ID, hoặc cùng digest cấu hình,
  hoặc cùng layer **và** cùng `run_config_sha256` (entrypoint, cmd, user, env, workdir, nhãn… + nền tảng); tag đích
  được kiểm lại ngay trước mỗi lần tạo lại. `build` từ chối image không có nhãn `revision` = commit được đóng gói.
- Từ chối: checksum sai, thiếu/thừa file, manifest lỗi, sai nền tảng, phiên bản nguồn không hỗ trợ, schema không
  tương thích, chữ ký sai, gói cần migration.

Chi tiết: [OFFLINE_UPDATE_SECURITY.md](OFFLINE_UPDATE_SECURITY.md). Vận hành:
[OFFLINE_UPDATE_UBUNTU_GUIDE.md](OFFLINE_UPDATE_UBUNTU_GUIDE.md), rollback: [OFFLINE_UPDATE_ROLLBACK.md](OFFLINE_UPDATE_ROLLBACK.md).

## 7. Trạng thái xác minh (Phase 12D5, Cloud)

| Hạng mục | Trạng thái |
|---|---|
| Logic build / verify / preflight / update / finish / pin / rollback / health / status / snapshot | MOCK VERIFIED (`tests/test_offline_package.py`, `tests/review_phase12d2/`, `tests/review_phase12d4/`: Docker giả lập có trạng thái; git, tar, SHA-256, ssh-keygen thật) |
| Hành vi Docker / Compose thật: `docker save` (bố cục OCI + docker-archive của Docker 29 containerd), `docker load`, chuyển tag triển khai, `up -d --no-deps`, override bảo trì chỉ loopback, `docker compose up -d` thường / `docker restart` giữ image của tag, DB container giữ ID | VERIFIED trên Docker 29.10 + Compose 5.7.1 thật với image thay thế (busybox) — `tests/test_offline_real_docker.py`, `tests/test_offline_manual_fallback_real_docker.py` (`CB5400_REAL_DOCKER=1`) |
| Bundle git, `build-package.sh` | VERIFIED với git thật |
| Shell wrapper | `bash -n` + shellcheck |
| PowerShell (`build-package.ps1`, `phase12-test.ps1`) | NOT EXECUTED (Cloud không có PowerShell) |
| Image ứng dụng thật với `OCR_PREINSTALL_RUNTIMES=true`, SurrealDB thật, script vận hành / boot guard thật, Docker của Ubuntu production | NOT VERIFIED — LOCAL (`docs/review/PHASE12D5_LOCAL_ACCEPTANCE_CHECKLIST.md`) |
