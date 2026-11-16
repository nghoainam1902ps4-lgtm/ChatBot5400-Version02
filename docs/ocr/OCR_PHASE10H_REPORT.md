# Báo cáo Phase 10H — Review cuối và chuẩn bị phát hành ChatBot5400 v1.1.0-rc.2

Ngày: 2026-11-16 · Nhánh: `feature/tesseract-agri-custom-model` (từ tag `v1.1.0-rc.1`) · Stack thử nghiệm:
`chatbot5400-agri-test` · **Chưa push, chưa merge, chưa gắn tag, chưa tạo GitHub Release, production không thay đổi.**

Tài liệu công khai: chỉ gồm số liệu tổng hợp; không có nội dung hay tên tài liệu nội bộ, nội dung watermark, model,
mật khẩu, khóa hay cấu hình bí mật của bất kỳ hệ thống nào.

> **Bản công khai (rà soát ở Phase 10I).** Báo cáo ghi nhận trạng thái tại thời điểm viết. Chi tiết hạ tầng
> (đường dẫn máy chủ, mã container / image, tài khoản, SHA-256 của model riêng) đã được lược bỏ hoặc thay bằng giá trị
> minh họa (`/srv/example/…`); bản vận hành đầy đủ do chủ dự án lưu ngoài repository. Các mã commit ngắn trong báo cáo
> là commit cục bộ của nhánh phát triển trước khi gộp — chúng không có trên GitHub. Trạng thái phát hành hiện tại:
> [OCR_RELEASE_NOTES_RC2.md](OCR_RELEASE_NOTES_RC2.md).

## 1. Kết luận

| | Kết luận | Điều kiện |
|---|---|---|
| Merge | **READY FOR MERGE** | Fast-forward vào `claude/practical-wozniak-9s1t6z` (nhánh chính thức vẫn ở đúng `v1.1.0-rc.1`, không xung đột); không còn phát hiện mức Cao / Trung bình chưa xử lý (mục 3) |
| Phát hành | **READY FOR PRE-RELEASE v1.1.0-rc.2** | Tag tạo trên commit **sau merge**; phát hành dạng Pre-release, chỉ mã nguồn (mục 7) |
| Production | **PRODUCTION UNCHANGED** | Mục 10 — kèm một ghi nhận về các kết nối của bộ test tới cổng cơ sở dữ liệu trên máy chủ này (đều bị từ chối) |
| | **AWAITING OWNER APPROVAL** | Mọi bước tiếp theo (push, merge, tag, Release, cập nhật production) chờ chủ dự án |

Phạm vi phát hành đã chốt, không mở rộng:

| # | Hạng mục | Trạng thái |
|---|---|---|
| 1 | Custom Tesseract Model Manager | Đạt — [OCR_PHASE10_REPORT.md](OCR_PHASE10_REPORT.md); được gia cố ở phase này (mục 3) |
| 2 | Tesseract Vietnamese Agri | Đạt — vẫn là **Thử nghiệm** (`quality = experimental`, hỏi xác nhận trước khi dùng); không bao giờ được chọn tự động |
| 3 | Quản lý phiên bản model | Đạt |
| 4 | Thay model không cần rebuild / restart | Đạt — kiểm lại trên image cuối (mục 5) |
| 5 | Rollback model | Đạt |
| 6 | Tự OCR toàn trang cho PDF scan có watermark gây mất nội dung | Đạt — [OCR_PHASE10G_REPORT.md](OCR_PHASE10G_REPORT.md); cờ `OCR_AUTO_FULL_PAGE_ON_WATERMARK` **mặc định tắt** trong ứng dụng và trong mọi tệp cấu hình của kho mã |

Không đổi: engine mặc định (`rapidocr`), bốn engine cũ và checksum model chính thức, Layout Heron, TableFormer,
Embedding, RAG, Chat, Transformation, `uv.lock`, `Dockerfile`, lược đồ cơ sở dữ liệu. Không nghiên cứu Vintern, không
fine-tune model.

## 2. Việc đã làm trong Phase 10H

1. Hai phiên **review độc lập** trên toàn bộ diff `v1.1.0-rc.1..` (bảo mật; tính đúng đắn và hồi quy), cộng phần
   kiểm tra của người thực hiện. Mọi phát hiện mức Trung bình và gần hết mức Thấp được sửa kèm test (mục 3).
2. Quét **toàn bộ lịch sử Git** của nhánh (mục 4).
3. Chạy lại nghiệm thu Phase 10A–10G trên commit và image cuối (mục 5); kiểm tra giới hạn PDF hỗn hợp (mục 6).
4. **Chốt chặn workflow Build and Release** (mục 7).
5. Cờ mặc định **tắt** trong mọi tệp compose được theo dõi; hướng dẫn bật riêng (mục 8).
6. Tài liệu cài đặt / nâng cấp / vận hành / rollback, ghi chú phát hành, kế hoạch cập nhật production (mục 8–9).
7. Số phiên bản `1.1.0-rc.2` (`VERSION`, `frontend/package.json`, lockfile, README, CHANGELOG) — một commit riêng.

## 3. Review toàn bộ diff

Phương pháp: hai reviewer độc lập (không dùng chung ngữ cảnh với người viết mã), mỗi người đọc diff đã commit, tự
viết kịch bản tái hiện trong thư mục tạm và chạy với Tesseract 5.5.0 thật; chỉ đọc, không Docker, không mạng. Diff
được review: 45 tệp, +9.307 / −68 dòng. Sau khi sửa, các kịch bản tái hiện của reviewer được chạy lại trên mã mới.

**Kết quả: 0 phát hiện mức Cao.** Phân quyền (mọi route OCR chỉ dành cho quản trị viên), kiểm tra mã phiên bản, lời
gọi tiến trình con (không shell), việc không có đường tải từ Internet, đóng băng phiên bản theo job và đường mã khi
cờ tắt được cả hai reviewer xác nhận là đúng.

| # | Mức | Phát hiện | Xử lý |
|---|---|---|---|
| S-M1 | Trung bình | Thành phần `config` nhúng trong file `.traineddata` là tệp tham số mà Tesseract áp dụng không hạn chế mỗi lần nạp: một file model từ máy fine-tune bị xâm hại có thể bảo Tesseract ghi đè một tệp (đã tái hiện ngay ở bước smoke test của import) hoặc nạp thêm một model ngoài manifest | **Đã sửa.** Chỉ tham số tinh chỉnh nhận dạng trong danh sách cho phép, giá trị số / boolean; kiểm tra **trước khi** Tesseract nạp file lúc import và ở mọi lần xác minh, kể cả phiên bản đã import trước đó; tham số được ghi vào manifest và in ra. Model thật của chủ dự án và model `vie` chính thức mang đúng hai tham số hợp lệ. 17 test |
| S-M2 | Trung bình | Bước đo PDF của cơ chế tự OCR toàn trang (chỉ khi cờ bật) không có giới hạn: một PDF nhỏ được tạo có chủ đích làm worker dừng hàng chục giây hoặc tốn hàng GB bộ nhớ trước khi Docling chạy | **Đã sửa.** Giới hạn 2.000 trang, 20.000 đối tượng và 100.000 ký tự mỗi trang, 20 giây; vượt ⇒ giữ chế độ đã cấu hình (`check_failed`), một dòng log chỉ gồm số. 7 test |
| C-M1 | Trung bình | Trên trang có `/Rotate 90 / 270` hoặc page box không bắt đầu ở (0, 0), khung bao bị cắt nên quy tắc lặng lẽ không áp dụng (hướng an toàn, nhưng tính năng không có tác dụng) | **Đã sửa.** Đo trong không gian người dùng chưa xoay của trang. 8 test; hai kịch bản của reviewer cho kết quả đúng |
| C-M2 | Trung bình | Card Agri có thể kẹt ở "Lỗi" mà không có nút Thử lại (khi lần cài trước thất bại nhưng dữ liệu định hướng đã có qua đường khác) | **Đã sửa** ở giao diện. 2 test |
| S-L1 | Thấp | Kiểm tra "thư mục phiên bản là symlink" của import không bao giờ đúng: một liên kết `custom/agri/v2 → ../../best` đặt sẵn trong volume khiến import xóa model chính thức | **Đã sửa.** Import / remove từ chối mọi liên kết trên đường dẫn dưới thư mục models. 4 test |
| S-L2 / C-M3 | Thấp / Trung bình | Import lại đúng mã của phiên bản đang hoạt động khi manifest của nó không đọc được sẽ thay file "tại chỗ", không qua bước kích hoạt | **Đã sửa.** Từ chối khi mã là phiên bản hoạt động / rollback; manifest được `fsync`. 2 test |
| S-L3 / C-L1 | Thấp | Registry / manifest sai kiểu (hỏng hoặc sửa tay) làm lỗi cả trang OCR Engine Manager, hoặc khiến worker lặng lẽ dùng cài đặt mặc định | **Đã sửa.** Chuẩn hóa kiểu khi đọc; sai kiểu ⇒ đóng. 17 test |
| S-L4 | Thấp | Kết quả readiness được ghi vào manifest không dưới khóa của họ model | **Đã sửa.** 2 test |
| S-L5 | Thấp | Import kiểm tra file nguồn theo đường dẫn rồi mới mở lại để chép | **Đã sửa.** Mở một lần, chép có giới hạn. 1 test |
| C-L2 | Thấp | Gỡ model Tesseract Best xóa luôn model tiếng Anh mà Agri đang dùng khi `OCR_AGRI_WITH_ENGLISH=true` | **Đã sửa.** 3 test |
| C-L3 | Thấp | `ocr readiness` không tham số trả mã thoát 1 trên hệ thống không dùng Agri (thay đổi so với rc.1) | **Đã sửa.** 2 test |
| C-L5 | Thấp | File model bị thiếu được ghi nhãn "File đã bị thay đổi" | **Đã sửa.** 1 test |
| C-L4 | Thấp | Watermark ghi mỗi ký tự một đối tượng text không được quy tắc phát hiện (hướng an toàn) | **Không sửa — ghi vào giới hạn** (D-33; [OCR_PHASE10G_REPORT.md](OCR_PHASE10G_REPORT.md) mục 13) |
| S-I1 | Thông tin | Manifest ghi không `fsync`; thư mục staging sót lại sau import bị ngắt | **Đã sửa** |
| S-I2 | Thông tin | Hai quy ước thư mục đặt file model (`/import` chỉ đọc trong stack thử nghiệm; `/app/data/ocr-import` trong gợi ý của giao diện) | Giữ gợi ý của giao diện (đúng với mọi triển khai); hướng dẫn nêu rõ cả hai và cách dùng `docker cp` |
| S-I3 | Thông tin | Giá trị ngưỡng ngoài khoảng bị thay bằng mặc định mà không báo | **Đã sửa** (ghi log một lần). 4 test |
| C-I1 | Thông tin | Script benchmark: hai giai đoạn có thể đo hai phiên bản Agri khác nhau dưới cùng một nhãn; lượt lỗi vẫn thoát mã 0 | **Đã sửa.** Chạy lại cho đúng kết quả cũ (mục 5) |

Phát hiện của người thực hiện trong phase này:

| Phát hiện | Xử lý |
|---|---|
| Workflow *Build and Release* chạy (và thất bại ở bước push) ở mỗi lần publish Release | Chốt chặn — mục 7 |
| Bộ test backend mở kết nối tới cổng cơ sở dữ liệu mặc định của máy đang chạy nó | Chặn trong `tests/conftest.py` — mục 10 |
| Test giao diện chứa SHA-256 và kích thước của model thật | Thay bằng giá trị giả lập |
| Báo cáo Phase 10G ghi tiền tố SHA-256 của một tài liệu thật | Đã bỏ |
| Tệp compose của stack thử nghiệm đặt mặc định cờ là bật | Đổi thành tắt; stack thử nghiệm bật bằng `.env` riêng (không commit) |

Ghi nhận ở thời điểm đó: các báo cáo Phase 10 trên nhánh cục bộ còn đường dẫn máy chủ, tên tài khoản thử nghiệm và vị
trí tệp tài khoản của stack thử nghiệm (không có giá trị bí mật nào). **Đã xử lý ở Phase 10I** theo quyết định của chủ
dự án: các chi tiết đó được lược bỏ và lịch sử nhánh được gộp thành lịch sử sạch trước khi đưa lên kho công khai.

## 4. Lịch sử Git

Quét mọi commit `v1.1.0-rc.1..HEAD` của nhánh cục bộ (kể cả nội dung đã bị thay ở commit sau). Lần quét này được
làm lại ở Phase 10I trên nhánh đã làm sạch, với thêm các mẫu về hạ tầng (đường dẫn máy chủ, tên tài khoản, mã định
danh container / image); kết quả của lần quét cuối nằm trong ghi chú phát hành.

| Kiểm tra | Kết quả |
|---|---|
| Loại tệp trong toàn bộ lịch sử nhánh | chỉ `.py`, `.md`, `.ts`, `.tsx`, `.yml`, `.json`, `.gitignore`, `.dockerignore`, `.env.example`, `VERSION` và **một** tệp nhị phân: ảnh chụp card Agri (120 KB) |
| `.traineddata`, PDF, ảnh tài liệu, tệp nén, cơ sở dữ liệu, `.env`, khóa | **không có** |
| Ảnh chụp màn hình | chỉ có card Agri của giao diện: không có tên tài liệu, tên người dùng hay tên máy chủ (ảnh hiển thị SHA-256 của model riêng nên đã được gỡ khỏi repository ở Phase 10I) |
| Mẫu bí mật trong mọi dòng được thêm (khóa API, token, khóa riêng, JWT, `Bearer …`) | 0 |
| Gán mật khẩu / secret / token bằng giá trị cố định | 0 (một kết quả duy nhất là tên biến trong test với đường dẫn giả) |
| Tệp compose của stack thử nghiệm | mọi giá trị nhạy cảm đều là tham chiếu `${BIẾN}`; `.env`, `TEST_ACCOUNT.txt`, thư mục dữ liệu bị `.gitignore` và `.dockerignore` loại trừ |
| Nội dung watermark thật | 0 lần xuất hiện, trong cây mã và trong mọi commit |
| Địa chỉ IP nội bộ, địa chỉ thư điện tử | 0 |
| SHA-256 của model Agri v1 | **không** có trong mã nguồn hay test; ở Phase 10I được gỡ nốt khỏi tài liệu benchmark / báo cáo |
| Tác giả commit | `Claude <noreply@anthropic.com>` |

## 5. Nghiệm thu lại và hồi quy trên commit cuối

Mã chạy cuối: commit `82bea1e`; image stack thử nghiệm dựng từ commit đó (hiển thị `1.1.0-rc.2`).

| Kiểm tra | Phase 10 / 10G | Phase 10H (commit cuối) |
|---|---|---|
| `pytest tests/` (backend) | 1.665 đạt · 10 lỗi có sẵn · 64 bỏ qua | **1.733 đạt · 10 lỗi · 64 bỏ qua** — cùng đúng 10 lỗi có sẵn của `v1.1.0-rc.1` |
| `pytest tests/ -k ocr` | 572 đạt | **640 đạt**, 0 lỗi |
| Test pipeline thật (`OCR_FULL_PIPELINE=1`) | 12 đạt · 4 bỏ qua | **12 đạt · 4 bỏ qua** (Tesseract Fast, EasyOCR không cài trên máy phát triển) |
| `ruff` · `mypy` | sạch cho mã của nhánh · sạch | như cũ (2 lỗi `ruff` sẵn có trong `tests/` của baseline) |
| Frontend: `tsc` · lint · vitest | 0 lỗi · 0 lỗi, 7 cảnh báo sẵn có · 419 đạt | 0 lỗi · 0 lỗi, 7 cảnh báo sẵn có · **423 đạt** |
| Build image (`next build` + image) | đạt | **đạt** |
| Docker acceptance của dự án (nâng cấp từ `v1.1.0-rc.1`: online → offline → restart → update; `rapidocr` + `tesseract_best`; cờ tắt) | 53 PASS · 0 FAIL | **53 PASS · 0 FAIL · 0 NOT VERIFIED (`EXIT=0`), cùng đúng 53 kiểm tra** |
| Quyết định của bộ phát hiện trên 42 PDF tổng hợp, trong container | khớp | **khớp 42 / 42**; 24 PDF mẫu khác: 0 kích hoạt |
| Tài liệu thật 5 trang, cờ bật (Agri · Best) | 974 → 10.606 · 975 → 10.636 ký tự, giống hệt Force Full Page thủ công | **giống hệt** (cùng mã băm kết quả) |
| Năm engine + 14 tình huống qua API + worker | đạt | **19 / 19 giống hệt** lượt Phase 10G |
| Đường RapidOCR mặc định qua Content Core, cờ bật / tắt | đạt | **12 / 12 giống hệt** |
| Benchmark Phase 10E chạy lại với cờ bật (102 lượt) | 102 / 102 giống hệt | **102 / 102 lượt giống hệt** (văn bản và mọi chỉ số) kết quả đã lưu của Phase 10E; script đã sửa ghi rõ phiên bản Agri được đo (`v1`) |
| Model Agri sau nâng cấp image | v1 `offline_ready` | **v1 đang hoạt động, `verified`, `offline_ready`** — phiên bản import trước khi có bước kiểm tra tham số vẫn đạt bước kiểm tra mới |
| Import model thật bằng `docker cp` + xóa (lệnh trong kế hoạch production) | — | **đạt** — in hai tham số nhúng, `offline_ready`, không kích hoạt; sau khi xóa chỉ `registry.json` thay đổi |
| Phân quyền trên stack | đạt | người dùng thường **403** ở cả 10 route OCR đã thử; không token **401** |

## 6. PDF hỗn hợp

Giới hạn giữ nguyên như đã phê duyệt ở Phase 10G và đã được kiểm lại:

- Tài liệu vừa có trang scan dưới watermark vừa có trang văn bản điện tử **không** được OCR toàn trang tự động: cả năm
  engine giữ chế độ đã cấu hình, kết quả giống hệt từng byte khi cờ tắt (recall 33,3% trên PDF tổng hợp 3 trang).
- Log có một dòng `WARNING … reason=mixed_document` kèm số trang hai loại (đã thấy trong log của stack).
- Cách xử lý thủ công được tài liệu hóa: bật Force Full Page OCR, xử lý lại riêng tệp đó, rồi tắt. Đo trên cùng PDF:
  95,7–98,4% với bốn engine đọc được dấu tiếng Việt.
- Không có cơ chế tách / ghép PDF. Docling 2.129.0 không có API chính thức đặt chế độ OCR theo từng trang.

## 7. Workflow Build and Release

Hiện trạng (đọc từ GitHub, không thay đổi gì): repository **công khai**, Actions đang bật. Workflow *Build and Release*
có trigger `release: published` — áp dụng cho cả Pre-release — và đã chạy rồi **thất bại** ở mỗi lần publish từ v1.0.2
tới v1.0.8 (bước push tới registry của dự án gốc bị từ chối; không image nào được phát hành, nhưng mỗi lần là một lượt
build nhiều kiến trúc bị bỏ phí). Hai workflow build / test khác chỉ chạy với nhánh `main`, vốn không tồn tại ở đây.

Biện pháp trong nhánh này (`.github/workflows/build-and-release.yml`): mọi job bị **bỏ qua** trừ khi workflow được chạy
tay **và** biến repository `CB5400_PUBLISH_IMAGES` bằng `true` (mặc định không tồn tại). Publish một Release /
Pre-release chỉ tạo một lượt chạy có kết luận `skipped`.

Điều chủ dự án cần biết:

1. Chốt chặn nằm trong tệp workflow của **commit được gắn tag**. Tạo tag `v1.1.0-rc.2` sau khi merge.
2. Sau khi publish: `gh run list --workflow build-and-release.yml --limit 1` phải cho kết luận `skipped`.
3. Tùy chọn, do chủ dự án thực hiện trên GitHub: `gh workflow disable "Build and Release"` trước khi publish.
4. Tên image trong workflow vẫn là của dự án gốc: phải đổi trước khi có ý định phát hành image.

## 8. Tài liệu

| Việc | Tài liệu |
|---|---|
| Ghi chú phát hành | [OCR_RELEASE_NOTES_RC2.md](OCR_RELEASE_NOTES_RC2.md); `CHANGELOG.md` mục `1.1.0-rc.2` |
| Cài đặt mới | README (Quick Start) → [OCR_ONLINE_PREPARATION.md](OCR_ONLINE_PREPARATION.md) |
| Nâng cấp một hệ thống đang chạy | [OCR_RC2_PRODUCTION_UPDATE_PLAN.md](OCR_RC2_PRODUCTION_UPDATE_PLAN.md) |
| Model Agri: import, kích hoạt, thay, rollback, sự cố | [OCR_AGRI_MODEL_GUIDE.md](OCR_AGRI_MODEL_GUIDE.md), [OCR_CUSTOM_MODEL_MANAGER.md](OCR_CUSTOM_MODEL_MANAGER.md) |
| Bật / tắt cờ, đọc log `OCR mode:` | [OCR_OPERATOR_GUIDE.md](OCR_OPERATOR_GUIDE.md) (Phụ lục Phase 10G), [OCR_CONFIGURATION.md](OCR_CONFIGURATION.md) |
| Rollback | [OCR_ROLLBACK.md](OCR_ROLLBACK.md) (ghi chú Phase 10 và 10G) |
| Quyết định thiết kế | [DECISIONS.md](DECISIONS.md) D-33 (bổ sung hệ tọa độ, giới hạn đọc) |

**Cờ mặc định tắt.** Ứng dụng coi cờ là bật chỉ khi giá trị là `true` / `1` / `yes` / `on`. Trong kho mã: `.env.example`,
`docker-compose.yml` và `deploy/docker-compose.prod.yml` chỉ có dòng chú thích; `deploy/agri-test/docker-compose.yml`
khai báo `${OCR_AUTO_FULL_PAGE_ON_WATERMARK:-false}`. Stack thử nghiệm tiếp tục bật cờ bằng `.env` riêng của nó.

## 9. Kế hoạch cập nhật production

[OCR_RC2_PRODUCTION_UPDATE_PLAN.md](OCR_RC2_PRODUCTION_UPDATE_PLAN.md) — **chưa thực hiện**. Điểm chính: dựng image ở thư
mục riêng từ tag; sao lưu lạnh và kiểm tra restore như lần rc.1; `git merge --ff-only <tag>` với `git stash` /
`git stash pop` cho ba dòng cấu hình cục bộ (đã thử chỉ-đọc: áp sạch); chỉ tạo lại container ứng dụng; không sửa file
override và `.env`; cờ **không** được đặt; import model Agri và bật cờ là hai quyết định riêng, làm sau. Rollback mã
về commit đang chạy không mở lại rủi ro nào (bản đó đã có các bản vá phân quyền và công tắc URL ingestion).

## 10. Production

Đối chiếu chỉ-đọc với mốc ghi trước Phase 10, lần cuối 2026-11-16 22:56, sau mọi kiểm thử của phase này:

| Hạng mục | Kết quả |
|---|---|
| Git HEAD và trạng thái working tree của thư mục production | giống hệt mốc |
| Container ứng dụng và cơ sở dữ liệu | cùng id, cùng image, cùng thời điểm khởi động (2026-11-14), `restarts=0` |
| `docker-compose.yml`, `docker-compose.override.yml`, `.env` | SHA-256 giống hệt mốc |
| `/health` · web | 200 · 307 |
| Danh sách image (ngoài image của stack thử nghiệm) | cùng tên, cùng id |
| `OCR_AUTO_FULL_PAGE_ON_WATERMARK` trong production | không có |

Mọi thao tác với production trong phase này là chỉ-đọc; không có gì được ghi.

**Ghi nhận: cô lập cơ sở dữ liệu của bộ test.** Bộ test của dự án (từ trước nhánh này) cho phép một số test đi tới lớp
cơ sở dữ liệu và chấp nhận lỗi kết nối, với địa chỉ mặc định của ứng dụng (`ws://localhost:8000`). Trên một máy đồng
thời chạy một bản triển khai, địa chỉ mặc định đó có thể là một cơ sở dữ liệu thật — bộ test không được phép dựa vào
việc "không có gì nghe ở đó". Trong phase này `tests/conftest.py` được sửa để trỏ mọi kết nối của bộ test tới một cổng
đóng. Phase 10I thay cách làm đó bằng cơ chế fail-closed đầy đủ (`tests/db_isolation.py`, kèm regression test): các
biến `SURREAL_*` thông thường không bao giờ được dùng để chọn cơ sở dữ liệu của bộ test; muốn dùng một cơ sở dữ liệu
dùng tạm thì phải chỉ định riêng và chứng minh được tính cô lập, nếu không bộ test dừng trước khi chạy. Diễn biến cụ
thể trên môi trường phát triển được ghi trong báo cáo vận hành riêng, ngoài repository.

## 11. Thay đổi trong Phase 10H

Commit cục bộ sau `f1cdbe3` (cuối Phase 10G), chưa push:

| Commit | Nội dung |
|---|---|
| `b0efeb6` | Sửa lỗi theo review: quản lý model tùy biến, bước đo PDF, giao diện, bộ test, script benchmark — kèm tài liệu thiết kế |
| `e1668d1` | Chốt chặn workflow publish image; cờ mặc định tắt trong các tệp compose |
| `82bea1e` | Số phiên bản `1.1.0-rc.2` và CHANGELOG |
| commit tài liệu | Báo cáo này, ghi chú phát hành, kế hoạch cập nhật production, hướng dẫn vận hành / rollback |

So với `v1.1.0-rc.1`: 61 tệp, +11.267 / −76 dòng. Không đổi: `pyproject.toml`, `uv.lock`, `Dockerfile`, lược đồ cơ sở dữ liệu,
`open_notebook/graphs`, `commands/`, các module Embedding / RAG / Chat / Transformation.

Trạng thái stack thử nghiệm khi bàn giao: image dựng từ `82bea1e`, cờ bật qua `.env` riêng, engine đang chọn
Tesseract Vietnamese Agri v1, Force Full Page tắt. (Trong lúc kiểm tra phân quyền, một lời gọi `PUT /ocr/config` bằng
tài khoản quản trị đã bật Force Full Page trên stack thử nghiệm trong khoảng một phút; đã trả về `false`, không tài
liệu nào được xử lý trong khoảng đó.)

## 12. Các bước tiếp theo — do chủ dự án quyết định

1. Xem lại báo cáo này và [OCR_RELEASE_NOTES_RC2.md](OCR_RELEASE_NOTES_RC2.md); quyết định có lược bớt chi tiết stack thử
   nghiệm trong báo cáo Phase 10 trước khi công khai hay không (mục 3) — đã quyết định và thực hiện ở Phase 10I.
2. Push nhánh, mở Pull Request vào `claude/practical-wozniak-9s1t6z`, merge (fast-forward được). `docs-links.yml` sẽ chạy
   trên PR (đã kiểm tra cục bộ: mọi liên kết tương đối hợp lệ).
3. Gắn tag `v1.1.0-rc.2` trên commit sau merge; điền ngày vào `CHANGELOG.md` nếu muốn; publish **Pre-release**; kiểm
   tra lượt chạy workflow là `skipped`.
4. Cập nhật production theo kế hoạch — một phê duyệt riêng.

## 13. Giới hạn còn lại

- Tesseract Vietnamese Agri: Thử nghiệm; chỉ có số đo trên văn bản tổng hợp; đọc sai một phần giá trị phần trăm.
- Tự OCR toàn trang: PDF hỗn hợp không được sửa; không phát hiện watermark ngang cỡ lớn, khung bao nghiêng dưới 2% trang,
  watermark ghi mỗi ký tự một đối tượng; ngưỡng hiệu chuẩn trên PDF tổng hợp và một tài liệu thật; tài liệu vượt giới hạn
  đọc giữ chế độ đã cấu hình.
- Manifest và model nằm trên cùng một volume: người có quyền ghi vào volume có thể sửa cả hai; điểm neo độc lập là SHA-256
  do chủ model tự lưu.
- Danh sách tham số nhúng được phép là danh sách đóng: một model fine-tune từ ngôn ngữ gốc khác có thể bị từ chối cho tới
  khi tham số của nó được xem xét và thêm vào.
- Hai reviewer không chạy Docker và không chạy giao diện; phần đó được kiểm bằng nghiệm thu trên stack (mục 5).
- Các giới hạn của `v1.1.0-rc.1` vẫn còn ([OCR_RELEASE_NOTES.md](OCR_RELEASE_NOTES.md) mục 5).
