# Báo cáo Phase 9C — Triển khai production (thí điểm phi nghiệp vụ)

Ngày: 2026-11-14 · Tài liệu **công khai**: không chứa đường dẫn sao lưu, thông tin hạ tầng nội bộ, credential,
kết quả kiểm tra tài khoản hay nội dung dữ liệu. Các chi tiết đó nằm trong báo cáo vận hành riêng lưu trên máy chủ.

Phase 9C thực hiện theo kế hoạch đã được chủ dự án phê duyệt
([OCR_PRODUCTION_DEPLOYMENT_PLAN.md](OCR_PRODUCTION_DEPLOYMENT_PLAN.md)) cùng các điều kiện bổ sung: triển khai **thí
điểm phi nghiệp vụ**, RapidOCR giữ làm engine được chọn, hệ thống chỉ mở lại cho người dùng sau khi các kiểm tra
bảo mật bắt buộc đạt, rollback (nếu cần) chỉ ở chế độ cô lập. Không nghiên cứu hay phát triển OCR thêm; không thay
đổi mã nguồn.

## Kết luận

| Trạng thái | Kết luận |
|---|---|
| Phase 9A / 9B | COMPLETED · MERGED (PR #42, #43) |
| Triển khai | **DEPLOYED** — production chạy mã `3ca6428` (mã được nghiệm thu `6f6b424`), image dựng sẵn và đã nghiệm thu |
| Phần mềm production | **PRODUCTION SOFTWARE VERIFIED** — 135 kiểm tra smoke test trên chính production đạt, dữ liệu cũ nguyên vẹn |
| Thí điểm OCR | **OCR PILOT VERIFIED** — RapidOCR và Tesseract Vietnamese Best, trên tài liệu **tổng hợp** |
| OCR cho tài liệu nghiệp vụ thật | **OCR REAL-DOCUMENT QUALIFICATION: PENDING** — chưa có benchmark tài liệu thật; chưa được dùng OCR mới cho tài liệu nghiệp vụ |
| Sẵn sàng offline | **OFFLINE READY** — cả hai engine đạt `offline_ready` trên production (kiểm tra chặn mạng trong tiến trình con) |
| Offline đã xác minh — stack cô lập | **PASS** — bằng chính image triển khai (mục 9) |
| Offline đã xác minh — production | **NOT VERIFIED** — không ngắt Internet máy chủ |
| Mở lại cho người dùng | **CHƯA** — hệ thống đang ở chế độ bảo trì theo quyết định của chủ dự án, cho tới khi kiểm tra bảo mật bắt buộc trước khi mở lại hoàn tất (báo cáo vận hành riêng). Vì vậy **PHASE 9C: BLOCKED ở bước mở lại**; mọi bước khác đã xong |
| Bàn giao | **PENDING** — chờ bước mở lại và theo dõi 24 giờ của người vận hành |

Ba trạng thái sau **không** đồng nghĩa: *phần mềm production đã cập nhật* (đạt), *thí điểm OCR đã xác minh* (đạt,
dữ liệu tổng hợp), *OCR đủ điều kiện cho tài liệu nghiệp vụ thật* (chưa — chờ benchmark do chủ dự án thực hiện).

## 1. Kiểm tra trước bảo trì

| Kiểm tra | Kết quả |
|---|---|
| Commit production trước triển khai | `5e04227` — đúng như kế hoạch |
| Nhánh chính thức | `3ca6428`; khác commit merge `3819c2a` và mã nghiệm thu `6f6b424` **chỉ trong `docs/`** |
| Image triển khai | Dựng trước ở thư mục riêng; 221 file mã nguồn backend trong image (API, commands, `open_notebook`, prompts, scripts, `pyproject.toml`, `uv.lock`…) **trùng từng byte** với `6f6b424`; mã frontend giữa `6f6b424` và commit dựng image không đổi |
| 5 file thay đổi cục bộ | Còn nguyên như lúc lập kế hoạch; đã sao chép vào bản sao lưu |
| Mount và volume | 2 bind mount dữ liệu; 2 volume ẩn danh của container DB rỗng |
| Dung lượng | Đủ (nhu cầu sao lưu + restore < 10 GB) |
| Job nền | 0 job đang chạy (kiểm tra lại ngay trước khi dừng) |
| Người dùng đang sử dụng | 0 request API trong 60 phút trước bảo trì |
| Image DB | Ghi lại ID và phiên bản (SurrealDB 2.7.0); lưu thêm bản tar |
| Auth, CORS, mức phơi nhiễm API | Đã đánh giá — kết quả trong báo cáo riêng |
| Image rollback | Gắn tag riêng + lưu bản tar có checksum |
| Khả năng rollback an toàn | Có: bản cũ chỉ được chạy ở chế độ bảo trì (mục 10) |

## 2. Sao lưu

Sao lưu **lạnh** (ứng dụng và DB đã dừng bằng `docker compose stop`; không `down`, không `-v`, không xóa volume).

| Thành phần | Kết quả |
|---|---|
| `notebook_data` (upload, checkpoint chat, cache) | archive 836 MB; số mục trong archive = số mục nguồn |
| `surreal_data` (SurrealDB) | archive 50 MB; số mục = nguồn |
| Image ứng dụng hiện tại và image DB | tag rollback riêng + 2 file tar |
| Compose, override, diff cục bộ, bản sao `.env` | lưu ở thư mục con quyền hạn chế (file 600) |
| Checksum | SHA-256 cho mọi archive; `sha256sum -c` đạt sau khi tạo và đạt lại khi kiểm tra sẵn sàng rollback |
| Manifest | danh sách thành phần, kích thước, checksum, commit, ID container / image, phiên bản DB |
| Bảo vệ | thư mục 700, file 600, một chủ sở hữu; **không mã hóa** (chưa có quy trình quản lý khóa của đơn vị) |
| Vị trí | trên máy chủ, vị trí chủ dự án cho phép; **chưa** chép ra ngoài máy chủ (việc của người vận hành được ủy quyền) |

## 3. Kiểm tra restore

Stack cô lập: project riêng, thư mục dữ liệu riêng giải nén từ bản sao lưu, mạng `internal`, không publish cổng.

| Kiểm tra | Image cũ | Image triển khai (diễn tập nâng cấp) |
|---|---|---|
| `/health` | 200 | 200 |
| Request không token | 401 | 401 |
| Tới được Internet từ stack | không | không |
| Số bản ghi từng bảng so với production trước khi dừng | bằng | bằng |
| Credential nhà cung cấp giải mã được | 2/2 | 2/2 |
| File upload (số file, tổng byte) | bằng | bằng |
| Job tồn đọng có thể gọi ra ngoài | không có (0 job chờ) | không có |

Không đọc hay in nội dung tài liệu; chỉ số đếm. Stack được gỡ sau khi kiểm tra (không có volume).

## 4. Cập nhật

| | |
|---|---|
| Mã | `git stash` → `git merge --ff-only` tới `3ca6428` → `git stash pop` (không xung đột); không `reset --hard`; 5 file cục bộ còn nguyên |
| Image | dùng image đã dựng và nghiệm thu; không dựng lại |
| DB | cùng container, cùng image; chỉ `stop` / `start`; không migration (schema ở phiên bản 33, "không cần migration") |
| Override | bỏ đúng 3 biến `UV_OFFLINE`, `UV_EXCLUDE_NEWER`, `HF_HUB_OFFLINE`; thêm `OPEN_NOTEBOOK_ENABLE_URL_INGESTION=false`, `OPEN_NOTEBOOK_ENABLE_OCR_TESSERACT=true` |
| `.env` | thêm 1 dòng `OCR_INSTALL_TESSERACT=true` |
| Giữ nguyên | `OPEN_NOTEBOOK_ENABLE_DOCLING=true`, `UV_TORCH_BACKEND=cpu`, `OPEN_NOTEBOOK_WORKER_MAX_TASKS=1`, cổng, mạng, khóa mã hóa, tài khoản DB, khóa API, nhà cung cấp LLM / embedding |
| Khởi động | **chế độ bảo trì**: cùng service, cổng chỉ nghe loopback (file override thứ ba dùng `ports: !override`); file compose của production không đổi |

**Thời gian ứng dụng ngừng hoàn toàn: 4 phút 02 giây** (dừng → sao lưu → 2 lượt restore → cập nhật → `/health` 200).
Từ thời điểm dừng, người dùng chưa truy cập lại được vì hệ thống còn ở chế độ bảo trì.

Sau khởi động: `/health` 200; không restart; Docling **2.129.0** cài thành công theo constraints của `uv.lock`
(trước triển khai production không có Docling); Content Core 2.0.7; RapidOCR 3.9.2; torch 2.14.0 bản CPU; Tesseract
5.5.0; EasyOCR không cài; worker chạy; số bản ghi mọi bảng bằng trước triển khai; không lỗi trong log khởi động.

## 5. OCR Engine Manager trên production

| Kiểm tra | Kết quả |
|---|---|
| Docling khả dụng; Layout Heron; TableFormer accurate; không cảnh báo tương thích; CPU | đạt |
| Đúng 4 lựa chọn; phân loại chất lượng đúng | đạt |
| Tesseract Vietnamese Best: cài model `vie` + `eng` + `osd` (kiểm SHA-256) | đạt — lưu trên thư mục dữ liệu (37 MB) |
| "Chuẩn bị" Tesseract Best → `offline_ready` (kiểm tra chặn mạng, Heron + TableFormer accurate) | đạt |
| "Kiểm tra" Tesseract Best | đạt — CER 0,00; model thực tế `TesseractOcrCliModel` |
| "Chuẩn bị" + "Kiểm tra" RapidOCR | đạt — `offline_ready`; `RapidOcrModel` |
| Tự sửa hướng trang scan | khả dụng |
| Tesseract Fast, EasyOCR | không cài |
| Engine được chọn sau nghiệm thu | **RapidOCR** (Tesseract Best chỉ được chọn tạm trong lúc thử rồi trả lại) |

Không xử lý lại nguồn cũ, không OCR lại, không dựng lại embedding.

## 6. Smoke test trên production (tài liệu tổng hợp, hai tài khoản tạm)

| Nhóm | Kết quả |
|---|---|
| A. OCR Engine Manager | **23 / 23** |
| B. Chức năng | **29 / 29** |
| C. Xác thực, phân quyền, bảo mật | **68 / 68** |
| D. Dọn dữ liệu và tài khoản thử | **15 / 15** |

**B — chức năng** (mọi tìm kiếm / hỏi đáp / chat đều giới hạn trong notebook thử nghiệm; không tài liệu có sẵn nào
được truy xuất hay gửi tới mô hình):

| Kiểm tra | RapidOCR (engine được chọn) | Tesseract Vietnamese Best (chọn tạm) |
|---|---|---|
| PDF có text layer | số hiệu, ngày, số tiền đúng tuyệt đối; tiêu đề giữ dấu | — |
| PDF scan tiếng Việt | số tiền đúng | số hiệu (có dấu), ngày, số tiền đúng tuyệt đối |
| PDF scan có bảng | bảng 5 cột; 8/8 số tiền, 4/4 ngày | bảng 5 cột; 8/8 số tiền, 4/4 ngày |
| PDF scan xoay 90° | số tiền đúng | văn bản **trùng** kết quả của bản đứng thẳng; log ghi trang 1 được sửa hướng |
| Word, ảnh, văn bản nhập tay | xử lý xong, nội dung đúng | — |

Log của ba tài liệu Tesseract: `engine=tesseract_best actual_models=['TesseractOcrCliModel']`,
`conversion_status=success`, `page_orientation=ok`. Embedding, tìm kiếm vector và toàn văn, hỏi đáp RAG (trả lời
đúng số tiền tổng hợp), chat (trả lời đúng mã thử nghiệm), transformation, tạo insight qua worker: đạt. Không sót
thư mục tạm; không restart; không lỗi ngoài các dòng 404 do chính bước dọn dẹp tạo ra.

**C — bảo mật:**

| Kiểm tra | Kết quả |
|---|---|
| Không đăng nhập / token sai / sai mật khẩu | 401 / 401 / từ chối |
| Người dùng thường vẫn đọc được phần của mình (notebook, model, transformation, trạng thái) | 200 |
| Người dùng thường ghi / kiểm tra / dò credential và model của nhà cung cấp (14 route) | **403** |
| Người dùng thường: transformation, embed, dựng lại embedding, xóa insight | **403** |
| Người dùng thường: API OCR, commands, users, settings; tạo / xóa notebook và nguồn; retry | **403** |
| Người dùng thường tạo nguồn từ một file đã có trên máy chủ (kèm cờ xóa) | **403**; file đích còn nguyên |
| Thêm nguồn từ URL — quản trị viên (JSON và form) và người dùng thường | **403**; không bản ghi nào được tạo |
| API job tổng quát — kể cả quản trị viên | **403** |

Các request phải bị từ chối chỉ nhắm vào id không tồn tại hoặc đối tượng do chính lượt thử tạo ra; không credential,
model, nguồn, file hay tài khoản có sẵn nào bị đụng tới.

**D — dọn dẹp:** đã xóa đúng 10 nguồn tổng hợp (kèm file), 1 phiên chat, 1 insight, 1 notebook và **2 tài khoản
tạm**. Sau khi dọn: số bản ghi mọi bảng bằng trước triển khai, trừ nhật ký job (+20 job của tài liệu tổng hợp); số
tài khoản theo vai trò như cũ; số file upload và tổng byte như cũ. Mật khẩu của tài khoản tạm không được ghi vào
log, báo cáo hay Git; file chứa chúng đã bị xóa. Token của chúng không thể thu hồi riêng lẻ (JWT không trạng thái)
và tự hết hạn sau tối đa 12 giờ.

## 7. Dữ liệu trước và sau (chỉ số đếm)

| | Trước | Sau triển khai | Sau khi dọn dữ liệu thử |
|---|---|---|---|
| Tổng bản ghi các bảng nghiệp vụ | như nhau | như nhau | như nhau |
| Nhật ký job | 518 | 518 | 538 |
| Credential giải mã được | 2/2 | 2/2 | 2/2 |
| File upload | 45 | 45 | 45 (cùng tổng byte) |
| Thư mục model OCR | chưa có | — | 37 MB (Tesseract best + osd) |

## 8. Offline

- **Sẵn sàng offline trên production:** RapidOCR và Tesseract Best đều `offline_ready` — pipeline đầy đủ (Heron +
  TableFormer accurate + OCR) chạy đạt trong tiến trình con bị chặn mạng. `offline_verified` (ngắt Internet thật)
  trên production: **chưa**, vì không ngắt Internet máy chủ.
- **Stack cô lập, bằng chính image triển khai** (nâng cấp từ `5e04227` → chuẩn bị online → ngắt mạng egress của
  container → xử lý PDF → restart khi offline → xử lý lại → cập nhật → offline lại):

  | Engine | Kết quả |
  |---|---|
  | Tesseract Vietnamese Best | 42 PASS / 0 FAIL / 0 NOT VERIFIED |
  | RapidOCR | 42 PASS / 0 FAIL / 0 NOT VERIFIED |

  Trong các vòng offline: Internet không tới được, DB vẫn tới được, checksum model và cache Hugging Face không đổi,
  không có lần tải nào trong log, không treo chờ Hugging Face.
- LLM và embedding không được yêu cầu chạy offline (nhà cung cấp cần mạng).

## 9. Sẵn sàng rollback (đã kiểm tra, không thực hiện)

| Kiểm tra | Kết quả |
|---|---|
| Image rollback (tag + tar) | còn nguyên; checksum đạt |
| Archive dữ liệu | checksum đạt |
| Cấu hình trước triển khai | đủ (compose, override, diff cục bộ, `.env`) |
| Commit rollback | `5e04227`, có trong repository production |
| Image DB | không đổi |
| Bản cũ chạy cô lập | cấu hình cũ + override bảo trì hợp lệ; cổng ứng dụng chỉ nghe loopback |

Rollback, nếu cần, chỉ đưa bản cũ lên **ở chế độ bảo trì** (chỉ người quản trị trên máy chủ tới được): bản cũ có
lỗi phân quyền đã biết và không có công tắc URL ingestion, nên không được mở cho người dùng. Không restore DB khi
chỉ cần rollback ứng dụng; rollback dữ liệu cần phê duyệt riêng.

## 10. Theo dõi sau triển khai

Trong phiên triển khai (khoảng 20 phút sau khi khởi động): `/health` 200; restart 0; RAM ứng dụng ~2,9 GB / 30 GB
sau các lượt OCR; không sót thư mục tạm; không lỗi lặp lại. **Chưa** theo dõi 24 giờ — đó là việc của người vận
hành, bằng `scripts/ocr/production_health_check.sh` (hướng dẫn: [OCR_OPERATOR_GUIDE.md](OCR_OPERATOR_GUIDE.md) §6).

## 11. Giới hạn còn tồn tại

- Hệ thống chưa mở lại cho người dùng (xem Kết luận). Khi mở lại, container ứng dụng được tạo lại một lần: Docling
  được cài lại từ cache và RapidOCR cần "Chuẩn bị" lại (bước mở lại đã gồm việc này).
- OCR chưa được thẩm định trên tài liệu nghiệp vụ thật. Số liệu từ tài liệu scan phải đối chiếu bản gốc.
- Giới hạn OCR đã biết: xem [OCR_RELEASE_NOTES.md](OCR_RELEASE_NOTES.md) §5 (KL-1, lỗi dấu ở tiêu đề in đậm, RapidOCR
  mất dấu tiếng Việt).
- Route podcast vẫn mở cho mọi tài khoản đăng nhập (giữ nguyên theo quyết định của chủ dự án; đánh giá riêng sau).
- Token đăng nhập không thu hồi được riêng lẻ; đổi mật khẩu không vô hiệu token đã cấp (tối đa 12 giờ).
- Tạo nhiều nguồn cùng một thời điểm có thể làm một request lỗi 500 (xung đột ghi của DB, có sẵn).
- Bản sao lưu nằm trên cùng máy chủ và chưa mã hóa cho tới khi người vận hành xử lý theo quy định.
- Offline trên production và theo dõi 24 giờ: chưa thực hiện.

## 12. Tài nguyên chưa dọn

Chưa xóa gì. Danh sách đề xuất dọn dẹp (thư mục nghiệm thu, build cache, volume ẩn danh của các lượt nghiệm thu,
image nghiệm thu, bản giải nén của kiểm tra restore) nằm trong báo cáo vận hành riêng và chờ chủ dự án phê duyệt.
Giữ lại: bản sao lưu production, image rollback, git bundle, bằng chứng nghiệm thu, cache model production.
