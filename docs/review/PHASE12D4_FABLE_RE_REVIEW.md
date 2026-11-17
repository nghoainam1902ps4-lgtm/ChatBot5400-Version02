# Phase 12D4 — Re-review sau remediation

| | |
|---|---|
| Đối tượng review | `8d0c438a4653a9d98bf32860d2ac2355967fd9df` trên `feature/legal-document-normalization` (đã xác minh trùng `origin/…`) |
| Baseline | v1.2.0 = `f2fdf2714a7c0b5b196132f71cfc091928befc06` (đã xác minh) |
| Trước remediation | `2ef007417eaca0ce41e7aba2e32a201fa243ebf1` |
| Nhánh review | `review/phase12d4-fable-reaudit` (tạo từ `8d0c438`) |
| Nhánh feature, nhánh audit cũ (`fcd0c45`), PR #50 | **không thay đổi**; PR vẫn Draft, không approve, không merge |
| `VERSION` | `1.2.0` (không đổi) |
| Mã runtime | **không sửa** — nhánh review chỉ thêm `docs/review/PHASE12D4_*` và `tests/review_phase12d4/` |

## 0. Giới hạn về tính độc lập — đọc trước

Chỉ thị giả định Phase 12D3 do Claude Opus làm và Phase 12D4 do một reviewer độc lập làm. **Thực tế không phải vậy:**
cả 16 commit của Phase 12D3 mang `Co-Authored-By: Claude Fable 5.2` và được tạo **trong chính phiên Claude Code này**;
phiên đang chạy `claude-fable-5-2` (cấu hình ban đầu `claude-opus-5-5`, đã được chuyển model). Người rà soát ở đây vì
vậy là **tác giả của mã được rà soát**, có đầy đủ thiên kiến của tác giả.

Biện pháp giảm thiên kiến đã dùng:

1. Hai lượt tấn công (normalizer + oracle; công cụ offline) được giao cho **sub-agent có ngữ cảnh mới**: chúng chỉ
   nhận mã nguồn và mục tiêu, được yêu cầu **không đọc** các báo cáo `docs/review/*.md`, và không nhận kết luận nào.
2. Mọi tái hiện của sub-agent được **chạy lại và đọc lại** trước khi ghi nhận.
3. Bằng chứng RED được tái hiện lại từ đầu trên worktree của mã trước remediation.

Kết quả cho thấy thiên kiến là có thật: các lỗi nặng nhất của báo cáo này (normalizer vẫn xóa nhầm số, vẫn tự nối
sai; lệnh Compose "duy nhất được phép" khởi động image chưa duyệt; finish báo thành công trên database rỗng) do
sub-agent tìm ra, không phải do lượt rà của tác giả. **Nếu cần một review độc lập đúng nghĩa, hãy chạy lại 12D4
trong một phiên khác, với model khác nếu có thể.** Sub-agent vẫn cùng họ model với tác giả.

## 1. Kết luận

Phase 12D3 đã sửa đúng phần lớn phản ví dụ của audit 12D2, nhưng **kết luận của báo cáo 12D3 là quá lạc quan**:

- **"0 xóa nhầm / 0 nối sai" không đúng ngoài 45 fixture của chính tác giả.** Normalizer v1.1.0 vẫn xóa số là nội
  dung (F-02) và vẫn tự tạo câu không có trong nguồn (F-03). Các fixture ngưỡng đặt đúng tại điểm mà implementation
  an toàn.
- **Công cụ offline có hai lỗi P1 mới do chính 12D3 đưa vào** (R2-05, R2-12) và nhiều trạng thái mà "phát hiện
  lệch" không hoạt động.
- **Không có finding P1 nào đủ điều kiện đóng.** 4 / 6 P1 gốc chỉ được sửa một phần.

| | Số lượng |
|---|---|
| Finding gốc đã rà | 29 / 29 |
| VERIFIED FIXED IN CLOUD | 8 (F-05, F-10, F-12, F-13, F-14, F-18, T-01, T-02) |
| FIXED IN CODE — LOCAL VERIFICATION REQUIRED | 10 (F-01, F-04, F-07, F-09, F-15, F-16, F-23, F-24, F-25, F-27) |
| PARTIALLY FIXED | **11** (F-02, F-03, F-06, F-08, F-11, F-17, F-20, F-21, F-22, F-26, T-03) |
| NOT FIXED | 0 |
| Finding mới | 22: **2 P1**, 7 P2, 10 P3, 3 P4 (R2-22 là nghi ngờ chưa xác minh) |
| Đã xác minh trên runtime thật | **0** |

Chi tiết từng finding gốc: [PHASE12D4_FINDING_CLOSURE_MATRIX.json](PHASE12D4_FINDING_CLOSURE_MATRIX.json). Finding
mới: [PHASE12D4_NEW_FINDINGS.json](PHASE12D4_NEW_FINDINGS.json).

## 2. Ba mốc so sánh

| | A. v1.2.0 | B. Phase 12 trước remediation | C. Sau remediation (`8d0c438`) |
|---|---|---|---|
| Backend (chạy lại ở 12D4 cho C) | 1789 / 13 / 64 | 2122 / 13 / 65 | **2424 passed / 13 failed / 65 skipped**, 0 xfail |
| Tên 13 test lỗi | — | trùng A | **trùng A từng tên** (`diff` rỗng): 3 `test_chunking` (tiktoken bị proxy chặn) + 1 `test_domain` + 9 `test_models_api` |
| Frontend | 423 | 430 | **437 / 437**, `tsc` 0 lỗi, lint 0 lỗi / 7 cảnh báo cũ |
| `tests/review_phase12d2` | — | 18 failed / 14 passed với `--runxfail` (tái hiện lại ở 12D4 trên worktree `fcd0c45`) | 32 passed, 0 xfail |
| Legal: xóa nhầm / nối sai trên 45 fixture của 12D3 | — | 53 đơn vị / 6 | 0 / 0 (chạy lại, khớp file đã commit) |
| Legal: phản ví dụ MỚI của 12D4 | — | — | **3 / 3 xóa nhầm, 14 / 14 nối sai, 2 / 2 ảnh mất dấu vết** |
| Standard so với v1.2.0 | — | giống | giống (`test_convert_file_standard_is_byte_identical` đạt) |

Sai lệch nhỏ trong báo cáo 12D3 (không đổi kết luận): nhánh audit có **18** `xfail`, không phải 17; "giữ nguyên thân
test của audit" không hoàn toàn đúng — thân `test_f01_f02_existing_oracle_cannot_see_these_deletions` được viết lại
(có lý do: test cũ khẳng định hành vi lỗi còn tồn tại); các thân khác chỉ mất marker `xfail`.

## 3. Legal Normalizer v1.1.0

Tài liệu được dựng bằng `ReadingOrderModel` thật của Docling từ bố cục khai báo; **không có** Layout Heron, OCR, model
Agri hay PDF thật. Mọi kết luận dưới đây là về hành vi của mã trên bố cục tổng hợp.

### 3.1 F-02 — xóa nhầm số: PARTIALLY FIXED, **vẫn mất dữ liệu (P1)**

Phản ví dụ của audit (năm ở cuối trang, số khoản tại lề) đã đạt. Cùng nguyên nhân gốc vẫn xóa nội dung, không cảnh
báo (`tests/review_phase12d4/test_normalizer_counterexamples.py`):

| Tình huống | Standard | Legal v1.1.0 |
|---|---|---|
| Số khoản 2, 3, 4 bị OCR tách rời, in ở vị trí thụt đầu dòng (x = 98; đoạn văn ở x = 70) | còn | **mất cả 3** |
| Bộ chứng từ một trang: "Số:" và "0001"…"0004" là hai ô | còn | **mất cả 4**, còn lại "Số:" trơ trọi |
| "Kỳ báo cáo:" và "1/2024"…"4/2024" | còn | **mất cả 4** |

Quy tắc hiện tại (số trần, dải đầu / cuối 10%, cùng độ lệch với số trang trên ≥ 3 trang và ≥ 60%, cùng vị trí
ngang, không nằm trong 1% lề đoạn văn) là **ngưỡng số học, không phải bằng chứng ngữ nghĩa**: bất kỳ số nào là nội
dung mà tăng theo trang đều thỏa. Fixture f34 của 12D3 đặt số khoản đúng tại lề (x = 70) — vị trí duy nhất được loại
trừ. Hướng sửa (12D5): chỉ bỏ khi item mang nhãn PAGE_HEADER / PAGE_FOOTER của layout, **hoặc** khi không có item
nào khác cùng dòng (nhãn "Số:", "Kỳ báo cáo:" bên cạnh ⇒ giữ), giá trị không có dạng `n/yyyy`, không có số 0 đứng
đầu, và vị trí ngang nằm ở giữa hoặc sát mép ngoài trang; còn lại giữ + cảnh báo.

### 3.2 F-03 — nối sai: PARTIALLY FIXED, **vẫn tạo câu không có trong nguồn (P1)**

Trong cả 14 trường hợp dưới đây Standard giữ hai dòng tách biệt, Legal nối (`join_across_pages = 1`), 13 trường hợp
không có cảnh báo:

- Footnote nhãn TEXT, rộng hết cột, ký hiệu `(*)`, `1.`, `¹` hoặc không ký hiệu, nằm giữa đoạn bị cắt và phần tiếp
  theo: footnote nhận phần tiếp theo, đoạn thật vẫn bị cắt. Chỉ `1 `, `(1) `, `[1] `, `*` được nhận diện.
- Điểm cuối trang mất dấu `;` và trang sau mở đơn vị mới mà regex không biết: `c )` (OCR chèn khoảng trắng), mất
  marker, bullet rỗng đọc thành `o`, `a,`, `a-`, `trong đó:`, `ngày 15 tháng 7 năm 2024`, `đvt: triệu đồng`.
- Dòng viết thường ở đầu trang sau (tiêu đề chạy, địa chỉ web, `trang 2/3`) bị nuốt vào đoạn trước.

Ngoài ra **phép nối của chính Docling đi thẳng vào Legal** (R2-01): Docling nối một TEXT kết thúc bằng `[a-z,-]` với
TEXT kế tiếp bắt đầu bằng bất kỳ chữ Latin nào — qua trang, qua cột, bỏ qua bảng / ảnh / footer — và xóa dấu gạch
nối. Ví dụ đã tái hiện: `Nguyễn Văn An Phụ lục 01 ban hành kèm theo…` (hai văn bản độc lập), `…toàn bộ khách hàng
Điều 5. Hiệu lực thi hành…`, `tín dụng phingân hàng`, `39/2016/TT- NHNN`. Có ở cả Standard và v1.2.0; Legal không
hoàn tác, không cảnh báo. Fixture f19, f35, f38 (và theo cách đặt chữ: f12, f26, f29, f31, f39, f11) không kích hoạt
phép nối này, nên "0 nối sai" của benchmark không đo nó.

### 3.3 Các finding Legal khác

| Finding | Kết quả |
|---|---|
| F-01 | Đứng vững trước phản ví dụ mới (đơn vị tính, tên đơn vị, dòng ký lặp lại đều được giữ). Còn lại: nội dung nhãn furniture xuất hiện **một lần** (số hiệu văn bản, tên đơn vị ở trang 1, footnote nhãn footer) vắng mặt ở cả hai chế độ, không cảnh báo — R2-11 |
| F-06 | PARTIALLY FIXED: ảnh 36% trang có caption, hoặc có một từ OCR lạc bên trong, mất placeholder không cảnh báo |
| F-07 | Model v1.2.0 đọc được Source có khóa mới; xử lý lại thay bản ghi; `full_text` không sửa được qua API. Chưa chạy SurrealDB thật. R2-03 (P4): giá trị không phải mapping làm hỏng model miền |
| F-10 | VERIFIED: 250 / 500 / 1000 trang (nối + bảng + ảnh) = 1,0 / 2,6 / 4,8 s; đỉnh RAM 92 MiB; 6 luồng đồng thời cho cùng kết quả; không đổi tài liệu nguồn; vượt ngân sách ⇒ fallback `failed` |
| F-15, F-18 | Đúng với bản sửa đề xuất |
| F-16 | Phân cấp có (jsdom). R2-02: `5*3% (tối đa 15*2)` hiển thị `53% (tối đa 152)`; `(*) … (*)` mất cả hai dấu; có ở cả Standard |
| F-17 | PARTIALLY FIXED: marker danh sách hết thoát; nhưng `full_text` (và chunk, embedding, ngữ cảnh LLM) vẫn chứa `TK\_VND\_01`, `ho\_tro@…`, `&lt;`, `&amp;` trong URL. HTML trong chữ OCR vô hại (frontend không có `rehype-raw`) |

### 3.4 Lỗi upstream so với lỗi normalizer

| Tầng | Trạng thái |
|---|---|
| Tesseract / ô OCR / Layout Heron | **chưa quan sát** (không có ở Cloud) |
| Thứ tự đọc + phép nối của Docling | tái hiện bằng model thật: R2-01; f12 hai cột đọc theo hàng |
| Furniture / công thức không được xuất | tái hiện: R2-11 |
| Normalizer | F-02, F-03, F-06 còn lỗi |
| Serializer / hiển thị | F-17 còn lại, R2-02 |

Normalizer **không** phát hiện hay cảnh báo khi đầu vào đã mất hoặc đã bị nối sai nội dung, và không thể khôi phục
chữ chưa từng được OCR nhận dạng.

## 4. Oracle và test — xem [PHASE12D4_TEST_ORACLE_AUDIT.md](PHASE12D4_TEST_ORACLE_AUDIT.md)

Tóm tắt: tính vòng tròn của oracle cũ đã hết; oracle mới bắt 100% các đột biến xóa / chèn / ghép / đổi số / ô bảng,
nhưng so khớp chỉ theo chữ (artifact trùng chữ che đơn vị bắt buộc bị xóa), không đo furniture và placeholder, và
ground truth cùng vị trí trong fixture do chính tác giả normalizer đặt. **INDEPENDENT TEST ORACLE: PARTIAL.**

## 5. Công cụ offline — xem [PHASE12D4_OFFLINE_UPDATE_REAUDIT.md](PHASE12D4_OFFLINE_UPDATE_REAUDIT.md)

Tóm tắt: build / bundle / xác thực archive đứng vững; máy trạng thái, kiểm tra dữ liệu, pin và chuỗi tin cậy sau
verify còn lỗi, trong đó hai lỗi P1 mới:

- **R2-12**: một lần update bị từ chối vẫn ghi đè `image-override.yml` dùng chung ⇒ `compose-command.txt` (lệnh
  "duy nhất được phép") khởi động image chưa duyệt, không bảo trì, `status` và `health` trả 0.
- **R2-05**: mốc đối chiếu theo từng lần tạo lại (commit `7c23329`) làm `finish` báo `completed` khi database đã bị
  thay bằng database rỗng giữa update và finish.

## 6. tiktoken và artifact offline (F-22)

- Chunking dùng `token_count` ⇒ guard của `4bf5d91` có tác dụng với tách đoạn; `OCR_OFFLINE` tắt thì hành vi không đổi.
- `open_notebook/utils/context_builder.py` gọi `tiktoken.get_encoding("o200k_base")` trực tiếp ở hai chỗ, không qua
  guard (có từ v1.2.0).
- Ước lượng dự phòng `số từ × 1,3`: chuỗi 160 000 ký tự không có khoảng trắng = 1 token ⇒ một chunk; một tài liệu
  sinh 1 832 dòng cảnh báo. Tỷ lệ token / từ thật của tiếng Việt **không đo được ở Cloud** (không có bảng mã).
- Bước health của công cụ offline gọi `chunk_text()` nên **đạt cả khi đang dùng ước lượng**.
- Chỉ một bảng mã (`o200k_base`) được dùng trong mã của dự án; thư viện bên thứ ba có nạp bảng mã khác khi chat
  không thì chưa kiểm được (cổng Local, mạng bị chặn thật).
- File model chỉ được so tên + kích thước: file bị sửa cùng kích thước không bị phát hiện.
- Không đóng gói model: chấp nhận được **với điều kiện** preflight thật sự từ chối máy chủ thiếu model — điều này dựa
  trên trạng thái readiness do ứng dụng tự ghi và chưa được kiểm trên máy thật.

## 7. Điều kiện chuyển tiếp

| Câu hỏi | Trả lời |
|---|---|
| Có cần Phase 12D5? | **Có.** Phạm vi đề xuất ở [PHASE12D4_HANDOVER.md](PHASE12D4_HANDOVER.md) §4 — sửa lỗi, không thêm tính năng |
| Chuyển sang Windows Local được chưa? | **Có điều kiện.** Chạy được ngay và hữu ích: môi trường, build image, Standard parity, quan sát pipeline thật (W-RC), build gói, save / load. **Chưa nên** nghiệm thu chất lượng Legal và chuỗi cập nhật offline đầy đủ trước 12D5: các lỗi đã biết sẽ làm chúng không đạt |
| Phát hành RC / production | **Không** |

## 8. Chưa xác minh

Docker thật · Compose thật · PowerShell (`build-package.ps1` chưa từng chạy; kiểm thứ tự dòng không phải kiểm thử
thực thi) · Layout Heron · TableFormer · các engine OCR · model Agri · SurrealDB thật · trình duyệt thật · nâng cấp /
rollback offline thật · mạng bị chặn thật · Python 3.8 / 3.10 · khóa ký phát hành (chưa có ⇒ authenticity của gói
phát hành **NOT VERIFIED**).
