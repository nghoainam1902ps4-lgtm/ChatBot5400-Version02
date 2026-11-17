# Build gói cập nhật offline trên Windows (máy có Internet)

Đầu ra: `dist\offline\ChatBot5400-<version>-linux-amd64-offline.tar.gz` + `.sha256`. Không đụng tới production.

## 1. Chuẩn bị (một lần)

- Windows 10/11, **Docker Desktop** chạy **Linux containers** (WSL2 backend), ≥ 40 GB trống (image ~10–15 GB + bản
  `docker save` + nén).
- Git for Windows; Python 3.10+ hoặc `uv` (`winget install astral-sh.uv`).
- (Khuyến nghị) OpenSSH client của Windows (có sẵn) để ký gói.

### 1.1 Xác định nền tảng máy chủ Ubuntu **trước khi build**

Người vận hành chạy trên Ubuntu (chỉ đọc):

```bash
uname -m
```

```bash
docker info --format '{{.Architecture}} {{.OSType}}'
```

`x86_64` ⇒ `linux/amd64` (mặc định); `aarch64` ⇒ dùng `-Platform linux/arm64` (build chéo chậm hơn nhiều).
Ghi lại cả phiên bản đang chạy (`docker compose exec open_notebook cat /app/VERSION`, phải là `1.2.0`).

### 1.2 Khóa ký (khuyến nghị, làm một lần, giữ khóa riêng ngoài repository)

```powershell
ssh-keygen -t ed25519 -C "release@chatbot5400" -f $HOME\.ssh\cb5400_release
```

Gửi **khóa công khai** `cb5400_release.pub` cho người vận hành qua kênh tin cậy (gặp trực tiếp / USB đã kiểm soát)
để cài vào `/etc/chatbot5400/allowed_signers` (xem Ubuntu guide §1). Không commit, không đưa vào gói. Chưa có khóa
⇒ vẫn build được, gói **không ký**, máy chủ chỉ chấp nhận khi có SHA-256 nhận qua kênh tin cậy.

## 2. Lấy đúng mã nguồn

```powershell
git clone https://github.com/nghoainam1902ps4-lgtm/ChatBot5400-Version02.git
cd ChatBot5400-Version02
git fetch --tags origin
git checkout <nhánh hoặc tag đã nghiệm thu, ví dụ v1.3.0-rc.1>
git status
```

`git status` phải sạch (script từ chối checkout có thay đổi chưa commit).

## 3. Build image + gói (một lệnh)

> **Phiên bản.** Công cụ kiểm tra `VERSION` trong image khớp `-Version`. Trên nhánh Phase 12 `VERSION` vẫn là
> `1.2.0` cho tới commit phát hành RC (Phase 12G, **sau** nghiệm thu Local). Gói **thử nghiệm** trước thời điểm đó
> dùng `-Version 1.2.0-phase12.1` (tăng số cuối mỗi lần build); gói `1.3.0-rc.1` chỉ build từ commit phát hành RC.

```powershell
.\scripts\offline\build-package.ps1 -Version 1.3.0-rc.1 -SignKey $HOME\.ssh\cb5400_release
```

Không ký:

```powershell
.\scripts\offline\build-package.ps1 -Version 1.3.0-rc.1
```

Script: kiểm tra Docker (Linux containers), checkout sạch, tag chưa tồn tại → `docker buildx build` với
`OCR_PREINSTALL_RUNTIMES=true`, `OCR_INSTALL_TESSERACT=true`, label phiên bản + commit → `offline_package.py build`:
inventory trong image (`--network none`), `docker save`, git bundle `v1.2.0..HEAD` (+ tag nếu đã tạo), `git bundle
verify`, archive nguồn, chép script + tài liệu, manifest, SHA256SUMS, chữ ký, nén. Dòng cuối in **SHA-256** và
`readiness` (phải là `READY`).

Bash (WSL2 / Linux) tương đương:

```bash
scripts/offline/build-package.sh --version 1.3.0-rc.1 --sign-key ~/.ssh/cb5400_release
```

Đã build image trước đó (chỉ đóng gói lại):

```powershell
.\scripts\offline\build-package.ps1 -Version 1.3.0-rc.1 -NoBuild
```

## 4. Tự kiểm tra gói trên máy build (trước khi mang đi)

```powershell
Get-Content dist\offline\ChatBot5400-1.3.0-rc.1-linux-amd64-offline.tar.gz.sha256
```

```powershell
uv run --no-project python scripts\offline\offline_package.py verify dist\offline\ChatBot5400-1.3.0-rc.1-linux-amd64-offline.tar.gz --extract-to $env:TEMP\cb5400-verify --expected-sha256 <giá trị ở trên> --platform linux/amd64
```

Kết quả `"result": "VERIFIED"`. Kiểm tra nhanh image chạy được mà **không có mạng**:

```powershell
docker run --rm --network none --entrypoint /app/.venv/bin/python chatbot5400:1.3.0-rc.1 -c "import docling, easyocr; print('ok')"
```

```powershell
docker run --rm --network none --entrypoint tesseract chatbot5400:1.3.0-rc.1 --version
```

Nên chạy thêm bài kiểm thử gói trên stack cô lập (Ubuntu guide §8) trước khi mang sang production.

## 5. Chuyển gói

Chép `*.tar.gz` (và tùy chọn `*.sha256`) bằng phương tiện được phép. Gửi **SHA-256** cho người vận hành bằng kênh
**khác** với kênh mang gói (ví dụ đọc qua điện thoại / tin nhắn nội bộ đã xác thực). Không gửi `.env`, mật khẩu,
model Agri, dữ liệu.

## 6. Không làm

Không push image lên registry, không bật `CB5400_PUBLISH_IMAGES`, không tạo GitHub Release, không xóa image cũ trên
máy build nếu còn cần, không dùng `docker export`.
