# Hướng dẫn sử dụng model Tesseract Vietnamese Agri

Cập nhật: 2026-11-16 (Phase 10) · Dành cho người vận hành máy chủ và quản trị viên ứng dụng.

Tài liệu này công khai: không chứa mật khẩu, khóa, model hay tài liệu nội bộ. Thiết kế chi tiết:
[OCR_CUSTOM_MODEL_MANAGER.md](OCR_CUSTOM_MODEL_MANAGER.md). Kết quả đo: [OCR_AGRI_BENCHMARK.md](OCR_AGRI_BENCHMARK.md).

**Tesseract Vietnamese Agri là model tự fine-tune, xếp loại Thử nghiệm.** Kết quả đo hiện có là trên văn bản
pháp lý **tổng hợp**; chưa nghiệm thu trên tài liệu thật. Số tiền, ngày, số hiệu văn bản lấy từ bản scan phải
được đối chiếu với bản gốc trước khi dùng cho nghiệp vụ.

## 0. Quy ước lệnh

Mọi đường dẫn dạng `/srv/example/…` trong tài liệu này là **minh họa**: thay bằng thư mục thật của nơi triển khai.

Các lệnh chạy trên máy chủ, trong thư mục chứa file compose của stack. Với stack thử nghiệm Agri:

```bash
cd /srv/example/chatbot5400-agri-test/deploy/agri-test
ocr() { docker compose exec open_notebook /app/.venv/bin/python -m open_notebook.ocr.cli "$@"; }
```

Ba điều không bao giờ làm, ở bất kỳ stack nào: `docker compose down -v` · `docker system prune` ·
`docker volume prune`.

Thư mục **chỉ đọc** để đặt file model cần import: trên máy chủ là thư mục khai báo ở `AGRI_IMPORT_DIR` trong
`.env` của stack (stack thử nghiệm: `/srv/example/ocr-model-import`); trong container là `/import`.

Stack không có thư mục `/import` (ví dụ compose mẫu ở gốc kho mã, hoặc production) có hai cách tương đương — lệnh
import chỉ cần một đường dẫn **trong container**, và luôn chép file vào kho model sau khi kiểm tra:

- chép file vào `./notebook_data/ocr-import/` trên máy chủ (trong container là `/app/data/ocr-import/`; đây là đường
  dẫn mà card Agri gợi ý) — cần quyền ghi vào `notebook_data`;
- hoặc `docker cp` file vào một thư mục tạm trong container rồi xóa sau khi import
  ([OCR_RC2_PRODUCTION_UPDATE_PLAN.md](OCR_RC2_PRODUCTION_UPDATE_PLAN.md) mục 8).

Sau khi import xong nên xóa bản sao ở thư mục tạm / `ocr-import`: bản dùng để OCR là bản đã lưu theo phiên bản.

## 1. Import model lần đầu (Agri v1)

1. Chép `vie_agri.traineddata` vào thư mục import trên máy chủ. Ghi lại SHA-256 của file tại máy fine-tune.

   ```bash
   sha256sum /srv/example/ocr-model-import/vie_agri.traineddata
   ```

2. Import thành phiên bản `v1` (kiểm tra file, nạp bằng Tesseract, smoke test, kiểm tra pipeline; khoảng 1–2 phút):

   ```bash
   ocr custom import --file /import/vie_agri.traineddata --version v1 --notes "Agri fine-tune lần 1"
   ```

   Dòng `stored … sha256 …` phải trùng SHA-256 ở bước 1. Dòng cuối báo phiên bản **chưa** hoạt động.

3. Kích hoạt phiên bản:

   ```bash
   ocr custom activate --version v1
   ocr custom status
   ```

   `engine state: ready`, `active version: v1`, `offline readiness: offline_ready` là trạng thái mong đợi.

Nếu thiếu dữ liệu định hướng trang (`osd`) — chỉ xảy ra khi chưa từng cài Tesseract Fast/Best — bấm **Cài đặt**
trên card Agri hoặc chạy `ocr install-model tesseract_agri` (tải `osd.traineddata` chính thức, có kiểm SHA-256).

## 2. Chọn Agri trên giao diện

1. Đăng nhập bằng tài khoản quản trị → **Cài đặt** → **OCR Engine Manager**.
2. Tìm card **Tesseract Vietnamese Agri** (cuối danh sách). Kiểm tra: phiên bản đang hoạt động, SHA-256, trạng
   thái "Đã xác minh", "Sẵn sàng xử lý offline".
3. Bấm **Kiểm tra** để chạy toàn bộ pipeline trên mẫu có sẵn (xem văn bản nhận dạng, CER, thời gian).
4. Bấm **Sử dụng** → xác nhận thông báo "Thử nghiệm". Card hiện nhãn **Đang dùng**.

Tài liệu tải lên **sau** thao tác này mới dùng Agri. Tài liệu đã xử lý trước đó không tự xử lý lại.

Chuyển về engine khác: bấm **Sử dụng** trên card Tesseract Vietnamese Best (hoặc RapidOCR). Các phiên bản Agri
vẫn được giữ nguyên.

## 3. OCR thử một PDF scan

1. Tạo một sổ tay thử nghiệm → **Thêm nguồn** → tải lên một PDF scan (không dùng tài liệu khách hàng thật trên
   stack thử nghiệm).
2. Chờ trạng thái xử lý hoàn tất, mở nguồn và đọc nội dung đã nhận dạng.
3. Muốn so sánh với Tesseract Best: chuyển engine (mục 2), tải lại cùng file thành nguồn mới và so hai kết quả.
4. Bằng chứng model đã dùng — log worker:

   ```bash
   docker compose logs --since 30m open_notebook | grep "OCR custom model used"
   ```

   Dòng log ghi `version=…` và `sha256=…` của model đã đọc toàn bộ tài liệu.

**Force Full Page OCR** (mục cấu hình cuối OCR Engine Manager): với PDF chỉ là ảnh scan, bật hay tắt cho kết quả
như nhau; chỉ bật khi PDF có lớp văn bản kém cần OCR lại toàn trang. PDF có lớp văn bản chuẩn không cần OCR và
không bị engine ảnh hưởng khi tùy chọn này tắt.

**PDF scan có watermark chéo** (Phase 10G). Một dòng watermark chéo dạng *text hiển thị* phủ lên ảnh scan làm
Docling bỏ gần hết chữ OCR bên dưới — kết quả chỉ còn tiêu đề, vài dòng và chuỗi watermark lặp lại. Đây không phải
lỗi của model Agri (Tesseract Vietnamese Best và RapidOCR bị y hệt). Hai cách xử lý:

- bật `OCR_AUTO_FULL_PAGE_ON_WATERMARK=true` (mặc định tắt; stack thử nghiệm bật bằng `.env` riêng): hệ thống tự OCR toàn trang cho
  **riêng** những tài liệu như vậy, tùy chọn Force Full Page đã lưu không đổi;
- hoặc bật Force Full Page OCR thủ công rồi xử lý lại nguồn.

Kiểm tra một tài liệu đã được xử lý thế nào (không lộ nội dung hay tên file):

```bash
docker compose logs --since 30m open_notebook | grep "OCR mode:"
```

`auto_full_page=True reason=tilted_text_box_over_scan` = đã tự OCR toàn trang; `reason=mixed_document` = tài liệu
vừa có trang scan dưới watermark vừa có trang văn bản điện tử, hệ thống **giữ nguyên** chế độ đã cấu hình và ghi
cảnh báo. Chi tiết: [OCR_PHASE10G_REPORT.md](OCR_PHASE10G_REPORT.md).

## 4. Import phiên bản tiếp theo (Agri v2, v3, …)

Không sửa mã nguồn, không build image, không khởi động lại.

1. Chép file fine-tune mới vào thư mục import (ghi đè file cũ ở thư mục import là được — v1 đã nằm an toàn trong
   volume dữ liệu).
2. Import với **mã phiên bản mới**:

   ```bash
   ocr custom import --file /import/vie_agri.traineddata --version v2 --notes "Agri fine-tune lần 2"
   ocr custom list
   ```

   Nếu file trùng nội dung với phiên bản cũ, lệnh cảnh báo `identical content to version(s) …`.
   Nếu file hỏng hoặc Tesseract không đọc được, lệnh báo `ERROR` và **không có gì thay đổi**.

## 5. Kích hoạt phiên bản mới

Bằng CLI:

```bash
ocr custom activate --version v2
```

Hoặc trên giao diện: card Agri → dòng `v2` → **Chuyển sang phiên bản này** → xác nhận.

- Có hiệu lực ngay cho tài liệu mới. Tài liệu đang xử lý dở vẫn dùng phiên bản cũ đến hết.
- Phiên bản vừa rời trở thành **phiên bản rollback**.
- Nếu `v2` chưa có kết quả readiness, bấm **Kiểm tra sẵn sàng offline** (hoặc
  `ocr readiness --engines tesseract_agri --check`).

## 6. Rollback phiên bản model

```bash
ocr custom rollback
ocr custom status
```

Hoặc trên giao diện: card Agri → **Rollback về v1**. Lệnh kiểm tra lại file của phiên bản đích trước khi chuyển.
Không cần khởi động lại.

Khi cần bỏ hẳn Agri: bấm **Sử dụng** trên card Tesseract Vietnamese Best. Model Best gốc không bị Agri động tới
(kiểm bằng `ocr status --no-db`: `tesseract_best … model=installed`).

## 7. Kiểm tra định kỳ và khi nghi ngờ

```bash
ocr custom verify          # băm lại toàn bộ từng phiên bản + nạp bằng Tesseract
ocr custom list            # SHA-256, dung lượng, ngày import, trạng thái
```

`verification=verified file=ok` là bình thường. `file=CHANGED` hoặc `corrupted` nghĩa là file trên đĩa không còn
khớp manifest lúc import: engine tự chuyển sang trạng thái Lỗi và từ chối xử lý tài liệu (không tự đổi engine).
Xử lý: `ocr custom rollback`, hoặc import lại file gốc thành phiên bản mới rồi kích hoạt.

### Xoá một phiên bản không còn dùng

```bash
ocr custom remove --version v2
```

Chỉ xoá được phiên bản **không** hoạt động và khi không có tài liệu nào đang xử lý. Mã phiên bản đã xoá có thể
dùng lại cho lần import sau. Lịch sử chuyển phiên bản vẫn ghi lại thao tác xoá.

## 8. Sao lưu model và manifest

```bash
tar -C ./notebook_data/ocr -czf agri-models-$(date +%Y%m%d).tgz \
  models/tesseract/custom manifests/custom
sha256sum agri-models-$(date +%Y%m%d).tgz
```

Lưu bản sao lưu ở nơi có kiểm soát truy cập (chứa model nội bộ). Khôi phục: giải nén vào đúng thư mục
`./notebook_data/ocr`, rồi `ocr custom verify` và `ocr custom status`.

## 9. Nâng cấp ứng dụng mà không mất model

Model và manifest nằm trên volume dữ liệu (`./notebook_data`), không nằm trong image:

```bash
docker compose build open_notebook
docker compose up -d --no-deps open_notebook
ocr custom verify
ocr custom status
ocr readiness --engines tesseract_agri --check
```

`--no-deps` để **không** tạo lại container cơ sở dữ liệu. Sau nâng cấp, phiên bản đang hoạt động và lịch sử chuyển
phiên bản còn nguyên; chạy lại readiness vì fingerprint có thể đổi theo phiên bản phần mềm.

## 10. Hạ cấp ứng dụng về bản chưa có Agri

Bản `v1.1.0-rc.1` không biết engine `tesseract_agri`. **Trước khi** hạ cấp image: vào OCR Engine Manager, bấm
**Sử dụng** trên một engine mà bản cũ hỗ trợ (Tesseract Vietnamese Best hoặc RapidOCR). Sau đó mới đổi image và
tạo lại riêng container ứng dụng. Nếu quên bước này, bản cũ không báo lỗi nhưng âm thầm dùng RapidOCR cho tài liệu
mới — hãy mở OCR Engine Manager và bấm **Sử dụng** trên engine mong muốn. Thư mục `custom/` vẫn nằm nguyên trên volume. Xem
[OCR_ROLLBACK.md](OCR_ROLLBACK.md).

## 11. Sự cố thường gặp

| Hiện tượng | Nguyên nhân | Xử lý |
|---|---|---|
| `ERROR: Version v1 already exists` | Phiên bản là bất biến | Import với mã mới (`v2`) |
| `ERROR: … is a symbolic link` / `not a .traineddata file` | File nguồn không hợp lệ | Chép file thật, đúng đuôi `.traineddata` |
| `ERROR: Tesseract rejected the model` | File hỏng, sai định dạng, hoặc không đọc được tiếng Việt | Xuất lại model từ máy fine-tune; kiểm SHA-256 sau khi chép |
| `ERROR: The model sets the Tesseract parameter '…' in its embedded parameter file` | Thành phần `config` trong file đặt một tham số ngoài danh sách cho phép (model chỉ được mang tham số tinh chỉnh nhận dạng, không được điều khiển tệp, đầu ra hay model khác) | Đóng gói lại model với tệp `config` chuẩn của ngôn ngữ gốc (ví dụ của `vie`), rồi import lại. Không nới danh sách cho phép khi chưa xem tham số đó làm gì |
| `ERROR: … is a symbolic link; refusing to use it` | Trong kho model có một liên kết ở vị trí thư mục phiên bản hoặc thư mục cha | Xóa liên kết (kiểm tra ai đã tạo nó), chạy lại lệnh |
| `ERROR: Version … is the active or the rollback version but its manifest cannot be read` | Manifest của phiên bản đang dùng bị mất / hỏng | Khôi phục manifest từ bản sao lưu, hoặc kích hoạt một phiên bản khác rồi import file dưới **mã mới** |
| `ERROR: The traineddata component table is inconsistent` | File bị cắt cụt khi chép | Chép lại, so SHA-256 |
| Card Agri "Chưa cài đặt", không có nút Sử dụng | Chưa có phiên bản nào được kích hoạt | `ocr custom activate --version …` |
| Card Agri "Lỗi", "File đã bị thay đổi sau khi import" | File model bị sửa/xóa ngoài hệ thống | `ocr custom rollback` hoặc import lại |
| Readiness "Chưa kiểm tra toàn bộ pipeline" sau khi đổi phiên bản | Kết quả của phiên bản khác không được tính | Bấm **Kiểm tra sẵn sàng offline** |
| PDF scan chỉ ra tiêu đề, vài dòng và chuỗi watermark lặp lại | Watermark chéo dạng text hiển thị phủ lên ảnh scan (mọi engine đều bị) | Xem "PDF scan có watermark chéo" ở mục 3: bật `OCR_AUTO_FULL_PAGE_ON_WATERMARK` hoặc Force Full Page OCR, rồi xử lý lại nguồn |
| Nguồn xử lý lỗi `OCR engine 'Tesseract Vietnamese Agri' is selected but its model is …` | Engine đang chọn nhưng model không sẵn sàng | Sửa theo các dòng trên, hoặc chọn engine khác, rồi xử lý lại nguồn |
