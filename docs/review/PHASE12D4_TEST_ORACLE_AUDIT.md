# Phase 12D4 — Rà soát oracle và chất lượng test (T-01, T-02, T-03)

Giới hạn về tính độc lập: xem [PHASE12D4_FABLE_RE_REVIEW.md](PHASE12D4_FABLE_RE_REVIEW.md) §0.

## 1. Chạy lại số liệu của 12D3

`scripts/ocr/phase12_benchmark.py --before <legal_normalizer.py của 2ef0074>` chạy lại trên nhánh review; bản đông lạnh
được lấy lại từ git và so byte với bản 12D3 đã dùng (giống nhau).

| | Standard | Legal v1.0.0 | Legal v1.1.0 | Khớp file đã commit |
|---|---|---|---|---|
| Đơn vị bắt buộc | 273 | 273 | 273 | có |
| False deletion (đơn vị / token) | 27 / 39 | 53 / 170 | 0 / 0 | có |
| False merge | 0 | 6 | 0 | có |
| False insertion | 22 | 0 | 0 | có |
| False reordering | 1 | 1 | 1 | có |
| Trường trọng yếu | 44 / 47 | 36 / 47 | 47 / 47 | có |
| Artifact đã loại | 0 / 47 | 45 / 47 | 24 / 47 | có |
| Phép nối đã làm | 1 / 5 | 5 / 5 | 3 / 5 | có |

**Số liệu tái lập được.** Vấn đề không nằm ở việc đo sai trên 45 fixture, mà ở chỗ 45 fixture không đại diện (§4) và
oracle có điểm mù (§3).

## 2. Tám câu hỏi về oracle

| # | Câu hỏi | Trả lời | Bằng chứng |
|---|---|---|---|
| 1 | Kiểm số lần xuất hiện của nội dung lặp? | **Có** | xóa một lần xuất hiện của dòng lặp: 39 / 39 được phát hiện |
| 2 | Kiểm thứ tự đọc? | **Một phần** | `false_reordering` = dãy con tăng dài nhất; nhưng test chỉ khẳng định `Legal ≤ Standard`, `fixture["order"]` / `order_accuracy` không được assert ở đâu |
| 3 | Thấy nội dung bị xóa ở một trang nhưng còn ở trang khác? | **Có, trừ khi** chữ trùng một artifact khai báo (số khoản "2" và số trang "2") | `test_r2_14_oracle_sees_a_required_number_deleted_while_its_twin_artifact_stays` (xfail) |
| 4 | Thấy false insertion? | **Có**, trừ dòng chèn trùng chữ một artifact (19 / 43) | bảng đột biến |
| 5 | Thấy false merge? | **Có** (210 / 210) — với phép nối giữa hai đơn vị khai báo | |
| 6 | Thấy false reordering? | **Một phần**: hoán đổi hai đoạn bắt buộc 207 / 210; hoán đổi với artifact 0 / 35; dời dòng chỉ qua artifact / placeholder 0 / 12 | |
| 7 | Thấy mất nội dung bảng? | **Có** ở mức dòng và ô (ô bị xóa 33 / 33, ô bị đổi 33 / 33) | |
| 8 | Thấy thay đổi nghĩa pháp lý? | **Không** — oracle so chữ; đổi số 192 / 192 được bắt vì chữ khác; mọi thay đổi giữ nguyên chữ (ví dụ thứ tự so với artifact) không được bắt | |

## 3. Đột biến có hệ thống (negative controls)

Lấy đầu ra Legal thật của cả 45 fixture, làm hỏng có chủ đích danh sách dòng hiển thị (không sửa mã trong repository),
rồi chạy đúng các assert của `tests/test_ocr_legal_normalizer.py`:

| Đột biến | Phát hiện |
|---|---|
| Xóa một dòng nghiệp vụ | 270 / 270 |
| Xóa số khoản / marker | 82 / 82 |
| Xóa một lần xuất hiện của dòng lặp | 39 / 39 |
| Ghép hai đoạn không liên quan | 210 / 210 |
| Thêm dòng không tồn tại | 297 / 297 |
| Xóa trắng một ô bảng | 33 / 33 |
| Đổi một ô bảng | 33 / 33 |
| Đổi một con số (ví dụ 11.000 → 11.00) | 192 / 192 |
| Hoán đổi hai đoạn bắt buộc kề nhau | 207 / 210 (3 trượt đều ở f12) |
| Dời một dòng bắt buộc qua các dòng bắt buộc | 446 / 450 (trượt ở f12) |
| **Hoán đổi một đoạn với dòng artifact** | **0 / 35** |
| **Thêm dòng trùng chữ một artifact khai báo** | **19 / 43** |
| **Dời dòng bắt buộc chỉ qua artifact / placeholder** | **0 / 12** |

Ba điểm mù thêm, từ đọc mã `preservation()`:

- dòng `<!-- image -->` bị bỏ qua hoàn toàn (thêm / mất placeholder không đổi chỉ số nào);
- nội dung khai báo `gt="furniture"` không bao giờ được đo;
- danh tính đơn vị chỉ là **chữ**: artifact và đơn vị bắt buộc cùng chữ dùng chung một bể.

Hệ quả cụ thể: lỗi F-02 thật (normalizer xóa số khoản 2, 3, 4 trong khi số trang vẫn còn) được oracle báo
`false_deletion: 0, false_deletion_tokens: 0, false_reordering: 3`. Test vẫn đỏ (do reordering) nhưng **chỉ số "xóa
nhầm" — con số được đưa vào báo cáo — bằng 0**.

## 4. Fixture đã thay đổi trong remediation

Bộ fixture trước remediation (24 fixture tại `2ef0074`) được khôi phục nguyên văn vào
`tests/review_phase12d4/fixtures_phase12_pre_remediation.py` và chạy song song với normalizer hiện tại, bằng một phép
kiểm **không dùng oracle mới** (mọi phần tử thân phải là chuỗi con của văn bản hiển thị):

| Kết quả trên 24 fixture gốc | |
|---|---|
| Nội dung thân bị mất dưới v1.1.0 | **0** |
| Dòng ghép sai do normalizer | 0 |
| Kỳ vọng "phải nối" cũ nay không đạt | 2 (f02, f03 — văn bản 2 trang) |
| Kỳ vọng "phải vắng" cũ nay còn | 15 số trang + header chạy (f02, f03, f07, f08, f10, f11, f13, f14) |

Đánh giá từng thay đổi:

| Thay đổi | Hợp lý theo nguyên tắc bảo thủ? | Che lỗi? | Làm benchmark dễ đạt hơn? |
|---|---|---|---|
| f02, f03: bỏ `must_join`, `absent_lines` (văn bản 2 trang giữ số trang, không nối) | **Có** — hướng an toàn | Không | **Có**: "nối" và "loại artifact" chuyển từ *bắt buộc* sang *được phép*; thước đo chỉ còn phạt sai, không phạt thiếu. Phải đọc kèm 24 / 47 và 3 / 5 |
| f07–f14: bỏ `absent_lines` | Có | Không | Như trên |
| f19: phần đầu đổi từ `text` sang `list_item`, số trang sang `page_footer` | — | **Có**: với nhãn `text`, Docling xóa gạch nối ("phingân hàng"); đổi nhãn làm hành vi này biến mất khỏi bộ đo | Có |
| f38 (mới): đoạn cuối trang kết thúc bằng "và" | — | **Có**: kết thúc bằng chữ ASCII ("theo") thì Docling nối qua cột | Có |
| f35 (mới): tiêu đề cột viết hoa | — | **Có**: như trên | Có |
| f34 (mới): số khoản đặt đúng tại lề x = 70 | — | **Có**: tại x = 98 normalizer xóa cả ba số (F-02) | Có |
| f29 (mới): footnote ký hiệu `1 `, hẹp, kết thúc "TT-NHNN" | — | **Có**: ký hiệu `(*)` / `1.` rộng hết cột ⇒ normalizer nối sai; kết thúc "Nhà nước" ⇒ Docling nối | Có |
| f31_* (mới): câu dẫn kết thúc "giấy tờ" | — | **Có**: kết thúc "bao gồm" ⇒ Docling nối với điểm `đ)` | Có |
| f39, f11: số trang nhãn TEXT | — | **Có**: nhãn `page_footer` ⇒ Docling nối qua bảng / qua trang trắng | Có |
| f26: dòng cuối trong ngoặc | — | **Có**: dòng cuối là tên người ký ⇒ "Nguyễn Văn An NGÂN HÀNG THƯƠNG MẠI MẪU…" | Có |
| f40: không khai báo `expect_placeholders` | — | **Có**: ảnh 12% có caption mất placeholder | Có |
| f12: khai báo thứ tự trái-trái-phải-phải, đầu ra trái-phải-trái-phải | — | Lỗi thứ tự được chấp nhận vì test chỉ so `≤ Standard` | — |

Kết luận: thay đổi kỳ vọng (cột 1–2) là chính đáng; nhưng **cách đặt chữ, nhãn và vị trí** trong các fixture mới và
fixture đã chỉnh khiến bộ đo không chạm tới (a) phép nối của Docling, (b) các điểm ngưỡng mà normalizer còn sai.
Không có bằng chứng về chủ ý che giấu — các chỉnh sửa f19 / f35 / f38 được chính 12D3 ghi lại — nhưng hệ quả khách
quan là benchmark dễ đạt hơn thực tế.

## 5. T-02, T-03 và chất lượng test còn lại

| Mục | Kết quả |
|---|---|
| T-02 `_assert_safe_calls` | Đứng vững: `up` phải đúng bằng lệnh an toàn; 19 dạng nguy hiểm đều bị từ chối |
| T-03 ca tham số hóa rỗng | Hết |
| Bằng chứng RED | Tái hiện độc lập trên worktree `fcd0c45`: 18 failed / 14 passed với `--runxfail`; không có marker: 14 passed / **18** xfailed (báo cáo 12D3 ghi 17) |
| Thân test của audit | Giữ nguyên, **trừ** `test_f01_f02_existing_oracle_cannot_see_these_deletions` (viết lại; có lý do) |
| Docker giả lập | Do tác giả công cụ viết; mô phỏng `compose config` bằng regex. Các lỗi R2-05, R2-12, R2-13, R2-15, R2-16 đều tái hiện được bằng chính nó — tức bộ 172 test **không hỏi đúng câu hỏi**, không phải vì giả lập yếu |
| Phụ thuộc thứ tự chạy | R2-21: mã OCR ghi `TESSDATA_PREFIX` toàn tiến trình; `test_direct_tesseract_layer_is_real` bị skip trong lượt chạy toàn bộ, đạt khi chạy riêng (có từ v1.2.0) |
| Test có thể treo | 3 test `test_chunking` chờ tới timeout vì tiktoken tải bảng mã; không skip, không mock — đúng |
| Kiểm PowerShell | Chỉ so thứ tự dòng: **không phải** kiểm thử thực thi |

## 6. Test của 12D4

`tests/review_phase12d4/` — 139 test: **97 passed, 42 xfail(strict)**; cùng `tests/review_phase12d2` 32 passed.

| File | Nội dung | Quy ước |
|---|---|---|
| `test_normalizer_counterexamples.py` | F-02 (3), F-03 (14), F-06 (2), oracle (2) + đối chứng | `xfail(strict)` nêu hành vi mong đợi |
| `test_legal_reaudit.py` | R2-01, R2-02, R2-03, R2-11, F-17; 24 fixture gốc; tương thích v1.2.0 | như trên + `test_verified_*`, `test_control_*` |
| `test_offline_reaudit.py` | R2-04..R2-10; kiểm chứng gián đoạn, nhiều lần cập nhật, pin | như trên |
| `test_offline_evidence_{data,pin_drift,state,trust_build}.py` | 32 tái hiện của sub-reviewer | **test tái hiện**: đạt khi lỗi còn; khi sửa phải đảo thành test hồi quy |
| `fixtures_phase12_pre_remediation.py` | 24 fixture tại `2ef0074`, nguyên văn | fixture tổng hợp |

## 7. Đánh giá

| Mục | Kết luận |
|---|---|
| T-01 (oracle vòng tròn) | Phần gốc: **đã sửa, xác minh ở Cloud** |
| T-02 | **Đã sửa, xác minh ở Cloud** |
| T-03 | **Sửa một phần**: ca rỗng hết; fixture ngưỡng vẫn chỉ thử tại điểm an toàn của implementation |
| INDEPENDENT TEST ORACLE | **PARTIAL** — đo đúng những gì nó đo; không đủ để tuyên bố "0 xóa nhầm" (aliasing, furniture, placeholder, ground truth tự khai báo) |
