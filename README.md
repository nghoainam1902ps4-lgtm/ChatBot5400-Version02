<a id="readme-top"></a>

[![MIT License][license-shield]][license-url]

# ChatBot 5400

**ChatBot 5400** là trợ lý tri thức nội bộ, tùy biến — một bản fork/customize của
dự án mã nguồn mở [Open Notebook](https://github.com/lfnovo/open-notebook).

So với bản gốc, ChatBot 5400 bổ sung và tùy biến:

- 🔐 **Đăng nhập / phân quyền (auth + RBAC)** và **cô lập dữ liệu theo người dùng**
- 🇻🇳 **Giao diện tiếng Việt** và **giao diện (UI) tùy biến**
- 📄 Trích xuất tài liệu giữ đúng **Điều / Khoản** (docling bật mặc định)
- 🤖 Giữ nguyên năng lực lõi của Open Notebook: hỏi–đáp theo nguồn, tạo podcast,
  tìm kiếm full-text + vector, hỗ trợ nhiều nhà cung cấp AI

> Phiên bản ổn định hiện tại được quản lý bằng tag `v*` và tệp [`VERSION`](VERSION).

---

## ⚠️ Quan trọng trước khi cài

**ChatBot 5400 phải được build từ mã nguồn của chính kho này.**

**KHÔNG** dùng image công bố của bản gốc:

```
lfnovo/open_notebook:v1-latest
```

Image đó **không chứa** các tùy biến của ChatBot 5400 (đăng nhập/RBAC, cô lập dữ
liệu theo người dùng, tiếng Việt, giao diện tùy biến). Nếu chạy bằng image đó, bạn
sẽ nhận **Open Notebook gốc**, không phải ChatBot 5400.

File [`docker-compose.yml`](docker-compose.yml) ở thư mục gốc đã được cấu hình để
**build từ `Dockerfile` trong kho này** (dịch vụ `open_notebook` dùng `build:`, gắn
tên image cục bộ `chatbot5400:local`). Bạn chỉ cần `docker compose up -d --build`.

> ℹ️ **Docker vẫn tải các image nền và phần phụ thuộc — đó là bình thường.**
> Khi build lần đầu, Docker sẽ kéo `node`, `python`, `surrealdb/surrealdb`, `uv`…
> và tải gói npm/Python. Thấy Docker tải các thứ này **không** có nghĩa là hệ thống
> đang thay ChatBot 5400 bằng Open Notebook bản gốc — nó đang **build ChatBot 5400
> từ mã nguồn của kho này**.

---

## 🚀 Cài nhanh trên máy mới

### Yêu cầu

- **Git**
- **Docker Desktop** (Windows / macOS) **hoặc** Docker Engine + Docker Compose (Linux)
- Đủ RAM/đĩa trống (khuyến nghị ≥ 4 GB RAM; vài GB đĩa trống cho image + phụ thuộc)

### 1. Tải mã nguồn

```bash
git clone https://github.com/nghoainam1902ps4-lgtm/ChatBot5400-Version02.git
cd ChatBot5400-Version02
```

### 2. Chọn phiên bản mã nguồn

**Bản ổn định (khuyến nghị cho cài mới).** Dùng tag phát hành `v*` mới nhất:

```bash
git fetch --tags
# Chọn tag vX.Y.Z ổn định mới nhất (bỏ qua bản prerelease / tag không hợp lệ):
LATEST=$(git tag -l 'v[0-9]*' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -n1)
echo "Checkout $LATEST"
git checkout "$LATEST"
```

> Tại thời điểm viết tài liệu, bản ổn định là **v1.0.2**. Nếu muốn ghim cứng:
> `git checkout v1.0.2`.

**Bản phát triển / mới nhất (dành cho người thử nghiệm, lập trình viên):**

```bash
git checkout claude/practical-wozniak-9s1t6z
```

Nhánh này có thể chứa thay đổi **mới hơn** bản ổn định gần nhất.

### 3. Tạo cấu hình bí mật

```bash
cp .env.example .env
```

Mở `.env` và đặt `OPEN_NOTEBOOK_ENCRYPTION_KEY` thành một chuỗi bí mật của bạn
(ví dụ `openssl rand -hex 32`). Các giá trị khác có thể giữ mặc định cho dùng cục bộ.

> 🔐 Giữ kỹ `OPEN_NOTEBOOK_ENCRYPTION_KEY`: mất khóa này là không giải mã lại được
> các API key nhà cung cấp đã lưu. Đừng commit `.env` (đã được gitignore).

### 4. Build và chạy

```bash
docker compose up -d --build
```

### 5. Kiểm tra

```bash
docker compose ps
curl http://localhost:5055/health      # API sống -> {"status":"healthy"}
```

Mở trình duyệt: **http://localhost:8502**

Sau đó vào mục **Models / Nhà cung cấp** để nhập API key của mô hình AI
(OpenAI / Anthropic / Google …) thì chức năng chat mới hoạt động.

> ⚠️ **Mặc định cục bộ, KHÔNG dùng cho production.** SurrealDB chỉ mở ở `127.0.0.1`
> với tài khoản mặc định `root:root`; CORS mở rộng; auth là middleware mật khẩu đơn
> giản. Trước khi phơi ra mạng, xem phần production bên dưới.

### Lần build đầu tiên diễn ra gì?

1. Docker **kéo các image nền/hạ tầng** (node, python, surrealdb, uv…).
2. Docker **build ChatBot 5400 từ `Dockerfile` của kho này**.
3. Gói **npm/Python được tải** trong lúc build.
4. **SurrealDB** khởi động.
5. **Migration cơ sở dữ liệu chạy tự động** khi API khởi động (xem log).
6. Một số thành phần nặng tùy chọn (Docling/PyTorch/model) có thể **tải khi lần đầu
   bật/dùng** nếu bạn kích hoạt.

Nhắc lại: thấy Docker tải Python, Node, SurrealDB, uv hay các gói phụ thuộc **không**
nghĩa là hệ thống đang thay ChatBot 5400 bằng Open Notebook bản gốc.

---

## 🖥️ Cài trên VPS (HTTPS / production)

Cho cài đặt máy chủ thật với Caddy + HTTPS tự động, xem runbook đầy đủ:

👉 **[deploy/DEPLOY-VPS.md](deploy/DEPLOY-VPS.md)**

Topology production: Caddy → ChatBot 5400 (frontend + API) → SurrealDB, dùng
[`deploy/docker-compose.prod.yml`](deploy/docker-compose.prod.yml) (cũng build từ
mã nguồn kho này).

- **Cài production mới:** nên dùng **tag phát hành ổn định mới nhất**.
- **Phát triển / thử nghiệm:** dùng nhánh mặc định.

---

## ✨ Tính năng chính (kế thừa từ Open Notebook)

- 📚 **Nhiều loại nguồn**: PDF, trang web, video, audio, tài liệu Office…
- 💬 **Chat theo ngữ cảnh** dựa trên nguồn của bạn, kèm **trích dẫn**
- 🔍 **Tìm kiếm** full-text và vector
- 🎙️ **Tạo podcast** đa người nói
- 🔧 **Content Transformations** (tóm tắt, trích xuất tùy biến)
- 🤖 **Nhiều nhà cung cấp AI** (OpenAI, Anthropic, Google, Ollama, LM Studio…)

Tài liệu tính năng/sử dụng chi tiết nằm trong thư mục [`docs/`](docs/index.md)
(phần lớn kế thừa từ dự án gốc).

---

## 🙏 Nguồn dự án / Upstream

ChatBot 5400 được xây dựng dựa trên và tùy biến từ dự án mã nguồn mở:

**Open Notebook** — https://github.com/lfnovo/open-notebook

Xin cảm ơn [@lfnovo](https://github.com/lfnovo) và cộng đồng Open Notebook. Các liên
kết tới Open Notebook ở đây là để **ghi nhận nguồn gốc**; chúng **không** phải là
đường cài đặt của ChatBot 5400 (xem phần "Quan trọng trước khi cài" ở trên).

## 📄 Giấy phép

Dự án được phát hành theo giấy phép **MIT**, kế thừa từ Open Notebook. Xem tệp
[LICENSE](LICENSE) để biết chi tiết.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- MARKDOWN LINKS & IMAGES -->
[license-shield]: https://img.shields.io/github/license/lfnovo/open-notebook.svg?style=for-the-badge
[license-url]: https://github.com/lfnovo/open-notebook/blob/master/LICENSE.txt
