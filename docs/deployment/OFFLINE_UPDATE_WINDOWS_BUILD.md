# Build gói cập nhật offline trên Windows (máy có Internet)

> **Phase 12D5.** Gói định dạng 3. `build-package.ps1` không còn dừng trên Windows PowerShell 5.1 khi tag chưa tồn
> tại (R2-22: kiểm tag bằng `docker image ls -q`; chưa chạy được ở Cloud — W-PS-01..03). `build` từ chối image không
> có nhãn `org.opencontainers.image.revision` = commit (R2-08); build lại thất bại không xóa gói tốt trước đó, hai lần
> build đồng thời bị chặn (R2-18). Gói kèm [quy trình thủ công](OFFLINE_UPDATE_MANUAL_FALLBACK.md) — đường cập nhật
> khuyến nghị cho production.

> **Phase 12D7.** `offline_package.py build` không còn dừng trên Windows vì `fcntl` (E1-04): khóa build dùng
> `msvcrt.locking` trên Windows, `flock` trên Linux — độc quyền giữa các tiến trình, hệ điều hành tự nhả khi tiến
> trình chết, file khóa không bao giờ bị xóa. Lần build sau dọn file `.partial-*` của lần build bị ngắt (cùng tên
> gói); thư mục dựng dở thì phải tự xóa (thông báo nói rõ). Nếu bước đổi tên cuối thất bại (Windows: file đang bị
> chương trình khác mở) gói cũ **giữ cả `.sha256`**. `manifest.json`, `SHA256SUMS`, `.sha256` luôn ghi LF. Image
> build từ checkout Windows giờ có cổng hướng xoay chạy được (D-40). Đã kiểm trên Linux với tiến trình thật;
> **chưa chạy trên Windows** — mục W-12D7-04 của
> [../review/PHASE12D7_LOCAL_ACCEPTANCE_CHECKLIST.md](../review/PHASE12D7_LOCAL_ACCEPTANCE_CHECKLIST.md).

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

> **Phiên bản — kiểm TRƯỚC mọi thao tác Docker.** File `VERSION` của commit phải khớp `-Version`: với
> `VERSION=1.2.0` chỉ đóng gói được `1.2.0` hoặc `1.2.0-<hậu tố>`. Trên nhánh Phase 12 `VERSION` vẫn là `1.2.0` cho
> tới commit phát hành RC (**sau** nghiệm thu Local), nên gói **thử nghiệm** dùng `-Version 1.2.0-phase12.1` (tăng
> số cuối mỗi lần build). `-Version 1.3.0-rc.1` trên nhánh hiện tại bị **từ chối ngay** (mã 2), không build image.

Gói thử nghiệm (nhánh Phase 12 hiện tại):

```powershell
.\scripts\offline\build-package.ps1 -Version 1.2.0-phase12.1
```

Có ký:

```powershell
.\scripts\offline\build-package.ps1 -Version 1.2.0-phase12.1 -SignKey $HOME\.ssh\cb5400_release
```

Thứ tự của script: kiểm tra Docker (Linux containers), checkout sạch → **`check-version`** (VERSION của commit) →
base (`-BaseRef`, mặc định `v1.2.0`) tồn tại và là tổ tiên của HEAD → tag image chưa tồn tại → `docker buildx build`
với `OCR_PREINSTALL_RUNTIMES=true`, `OCR_INSTALL_TESSERACT=true`, label phiên bản + commit → `offline_package.py
build`: **git bundle trước** (ref tạm `refs/cb5400-offline/build/<version>` trỏ đúng commit, `git bundle verify`,
`git bundle list-heads`, xóa ref tạm kể cả khi lỗi), archive nguồn, kiểm image, inventory trong image
(`--network none`), `docker save`, kiểm file image chỉ chứa đúng một tag, chép script + tài liệu, manifest,
SHA256SUMS, chữ ký, nén. Lỗi ở bất kỳ bước nào ⇒ thư mục đang dựng bị xóa (chạy lại được ngay). Dòng cuối in
**SHA-256** và `readiness` (phải là `READY`; `NOT_READY` nếu thiếu Docling, Tesseract hoặc bộ mã hóa token
`o200k_base` không nạp được khi không có mạng).

> `build-package.ps1` **chưa từng được chạy** (Cloud không có PowerShell): lần chạy đầu trên Windows là một mục
> nghiệm thu (W-OFF-01). Bản Bash đã được kiểm thử với git thật và Docker giả lập.

Bash (WSL2 / Linux) tương đương:

```bash
scripts/offline/build-package.sh --version 1.2.0-phase12.1 --sign-key ~/.ssh/cb5400_release
```

Đã build image trước đó (chỉ đóng gói lại):

```powershell
.\scripts\offline\build-package.ps1 -Version 1.2.0-phase12.1 -NoBuild
```

## 4. Tự kiểm tra gói trên máy build (trước khi mang đi)

```powershell
Get-Content dist\offline\ChatBot5400-1.2.0-phase12.1-linux-amd64-offline.tar.gz.sha256
```

```powershell
uv run --no-project python scripts\offline\offline_package.py verify dist\offline\ChatBot5400-1.2.0-phase12.1-linux-amd64-offline.tar.gz --extract-to $env:TEMP\cb5400-verify --expected-sha256 <giá trị ở trên> --platform linux/amd64
```

Kết quả `"result": "VERIFIED"`. Kiểm tra nhanh image chạy được mà **không có mạng**:

```powershell
docker run --rm --network none --entrypoint /app/.venv/bin/python chatbot5400:1.2.0-phase12.1 -c "import docling, easyocr; print('ok')"
```

```powershell
docker run --rm --network none --entrypoint tesseract chatbot5400:1.2.0-phase12.1 --version
```

Kiểm bộ mã hóa token nạp được khi không có mạng (nếu lệnh treo hoặc lỗi, gói sẽ là `NOT_READY`):

```powershell
docker run --rm --network none --entrypoint /app/.venv/bin/python chatbot5400:1.2.0-phase12.1 -c "import tiktoken; print(len(tiktoken.get_encoding('o200k_base').encode('kiểm tra')))"
```

Bắt buộc chạy bài kiểm thử gói trên stack cô lập (Ubuntu guide §9, checklist W-OFF) trước khi mang sang production.

## 5. Chuyển gói

Chép `*.tar.gz` bằng phương tiện được phép. Gửi **SHA-256** cho người vận hành bằng kênh **khác** với kênh mang gói
(ví dụ đọc qua điện thoại / tin nhắn nội bộ đã xác thực). File `*.sha256` chép cùng gói **không** thay được bước
này: ai sửa được gói cũng sửa được file đó. Không gửi `.env`, mật khẩu, model Agri, dữ liệu.

## 6. Không làm

Không push image lên registry, không bật `CB5400_PUBLISH_IMAGES`, không tạo GitHub Release, không xóa image cũ trên
máy build nếu còn cần, không dùng `docker export`.
