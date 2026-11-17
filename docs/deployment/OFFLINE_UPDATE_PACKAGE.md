# Gói cập nhật offline ChatBot5400 — kiến trúc và định dạng

Quyết định: D-35 ([../ocr/DECISIONS.md](../ocr/DECISIONS.md)). Công cụ: `scripts/offline/`.
Trạng thái Phase 12: **tooling hoàn thành + kiểm thử với Docker giả lập; gói thật CHƯA BUILD** (Cloud không có Docker
daemon) — build trên Windows: [OFFLINE_UPDATE_WINDOWS_BUILD.md](OFFLINE_UPDATE_WINDOWS_BUILD.md).

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
    ├── source/chatbot5400-<version>.bundle       git bundle v1.2.0..<release>
    ├── source/chatbot5400-<version>-src.tar.gz   git archive (máy chủ không dùng git)
    ├── scripts/  offline_package.py verify-package.sh preflight.sh update.sh rollback.sh healthcheck.sh offline-update.conf.example
    └── docs/     OFFLINE_UPDATE_*.md, RELEASE_NOTES.md
```

Kèm theo bên ngoài: `<gói>.tar.gz.sha256` — giá trị gửi cho người vận hành qua **kênh tin cậy**.

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
- Xuất bằng `docker save` (giữ layer, config, label, ID); **không** dùng `docker export/import`.
- `inventory` chạy **bên trong image với `--network none`**: phiên bản Python/thư viện (docling, docling-core,
  content-core, torch, rapidocr, easyocr…), Tesseract, số phiên bản schema (số migration), artifact runtime, có/không
  Docling ⇒ ghi vào manifest. Thiếu Docling hoặc Tesseract trong image ⇒ `readiness: NOT_READY` và cập nhật bị từ
  chối (trừ khi người vận hành chủ động `--accept-not-ready`).

## 4. Artifact runtime (không nằm trong image, tái sử dụng trên volume)

| Artifact | Vị trí trên volume dữ liệu | Cách gói xử lý |
|---|---|---|
| Docling Layout Heron, TableFormer accurate | `/app/data/.cache/huggingface` | giữ nguyên; không tải lại |
| Tesseract fast/best, `osd.traineddata` | `/app/data/ocr/models/tesseract` | giữ nguyên |
| Model Agri (người dùng import, có phiên bản) | `/app/data/ocr/models/tesseract/custom/agri/<version>` | giữ nguyên; không bao giờ đóng gói |
| EasyOCR | `/app/data/ocr/models/easyocr` | giữ nguyên |
| RapidOCR (PP-OCR onnx) | trong venv của container cũ | **trước khi tạo lại**: `installer.import_rapidocr_weights()` chạy trong container CŨ, chép sang `/app/data/ocr/models/rapidocr` sau khi kiểm SHA-256 theo danh sách của chính RapidOCR; container mới chạy với `OCR_RAPIDOCR_PERSISTENT=true` |
| Manifest / readiness / phiên bản custom | `/app/data/ocr` | giữ nguyên |

Override do công cụ sinh cho container ứng dụng: `OCR_RAPIDOCR_PERSISTENT=true`, `OCR_OFFLINE=true` (cấu hình được
qua `APP_ENV_OVERRIDES`). Không ghi đè model đang dùng; không tải gì khi khởi động.

**`docker load` thành công không chứng minh pipeline OCR chạy offline**: bước O chạy `ocr.cli readiness --check` (chỉ
cục bộ) và `healthcheck.sh --prove-offline` kiểm tra container không kết nối được ra ngoài.

Nếu sau này có artifact chính thức mới bắt buộc (ví dụ Docling đổi phiên bản layout) phải đóng gói riêng có checksum
+ giấy phép và **không** đánh dấu READY cho tới khi readiness offline đạt — Phase 12 không đổi Docling nên không cần.

## 5. Manifest (rút gọn)

```json
{
  "package_format_version": 1,
  "application": {"name": "ChatBot5400", "version": "1.3.0-rc.1", "release_tag": "v1.3.0-rc.1", "supported_source_versions": ["1.2.0"]},
  "platform": "linux/amd64",
  "image": {"tag": "chatbot5400:1.3.0-rc.1", "id": "sha256:…", "archive": "images/chatbot5400-1.3.0-rc.1.tar", "archive_sha256": "…", "labels": {…}},
  "source": {"commit": "…", "base_ref": "v1.2.0", "base_commit": "f2fdf27…", "git_bundle": "source/…bundle", "archive": "source/…-src.tar.gz"},
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

## 6. Toàn vẹn và xác thực

- SHA-256 cho từng file (manifest + SHA256SUMS) và cho cả gói.
- Xác thực nguồn: **chữ ký** `ssh-keygen -Y sign` (khóa riêng giữ trên máy build, không bao giờ trong Git hay gói;
  khóa công khai cài trước ở `/etc/chatbot5400/allowed_signers`) **hoặc** SHA-256 của gói nhận qua kênh tin cậy
  (`--expected-sha256`). Thiếu cả hai ⇒ **từ chối**. Hiện **chưa có khóa ký chính thức** ⇒ phải dùng hash.
- Kiểm tra archive **trước** khi ghi đĩa: đường dẫn tuyệt đối, `..`, symlink, hardlink, file đặc biệt, nhiều thư mục
  gốc, > 5000 mục, > 64 GiB khi giải nén, tỷ lệ nén > 200×. Tự giải nén từng file (không `extractall`).
- Từ chối: checksum sai, thiếu/thừa file, manifest lỗi, sai nền tảng, phiên bản nguồn không hỗ trợ, schema không
  tương thích, chữ ký sai.

Chi tiết: [OFFLINE_UPDATE_SECURITY.md](OFFLINE_UPDATE_SECURITY.md). Vận hành:
[OFFLINE_UPDATE_UBUNTU_GUIDE.md](OFFLINE_UPDATE_UBUNTU_GUIDE.md), rollback: [OFFLINE_UPDATE_ROLLBACK.md](OFFLINE_UPDATE_ROLLBACK.md).

## 7. Trạng thái xác minh (Phase 12, Cloud)

| Hạng mục | Trạng thái |
|---|---|
| Logic build / verify / preflight / update / finish / rollback / health | MOCK VERIFIED (30 test, Docker giả lập ghi lại mọi lệnh; git, tar, SHA-256, ssh-keygen thật) |
| Shell wrapper | `bash -n` + shellcheck sạch |
| PowerShell (`build-package.ps1`, `phase12-test.ps1`) | NOT EXECUTED (Cloud không có PowerShell) |
| Build image với `OCR_PREINSTALL_RUNTIMES=true` | NOT BUILT |
| Gói thật, `docker load`, nâng cấp/rollback thật, chặn mạng thật | NOT VERIFIED |
