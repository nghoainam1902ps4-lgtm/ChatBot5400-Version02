# Phase 12D12 — Release gate

Áp dụng cho candidate `18eeecbfd2cc42549e57cdb866a405083b41a657` trong PR #50 (Draft, head và base đã kiểm lại sau review). Nhánh `claude/jolly-knuth-rivla0` chứa hồ sơ review và test kiểm soát; nhánh feature không đổi. [Báo cáo review](PHASE12D12_TARGETED_REVIEW.md) · [Trạng thái JSON](PHASE12D12_FINDING_STATUS.json) · [Test kiểm soát](../../tests/test_phase12d12_review_controls.py)

## Cổng review

| Cổng | Kết quả | Căn cứ |
|---|---|---|
| R01 Red/green độc lập | PASS | Test gốc `abbcc37` nguyên byte: 13 failed / 3 passed trên `2cc824f`, 16/16 trên `18eeecb`. |
| R02 Toàn vẹn PDF | PASS | D10-01, D10-02 (extraction). Mọi đường PDF qua `reject_incomplete` trước serialization và trước lưu Source. Diễn tập timeout thật: Local. |
| R03 Giao dịch embedding | PASS trên server 2.3.10 | D10-02 (embedding). Engine nhúng không chứng minh được tính đồng thời; server RocksDB/SurrealKV đạt. Phiên bản server thực tế: Local (D12-L2). |
| R04 Bảo toàn chữ | PASS | D10-03, D10-04, D8-01. Sai lệch không chặn D12-02 (Legal). |
| R05 Standard expected-diff | **FAIL** | D10-05 và D10-07 đạt; D10-06 PARTIAL do D12-03 (mã 0 cho văn bản candidate không được dòng TSV nào chứng minh). |
| R06 Khôi phục gói offline | PASS | D10-08. Ba điểm tồn fail-closed. Updater tự động vẫn EXPERIMENTAL. |
| R07 Fingerprint dữ liệu | PASS cho 8 bảng | D10-09. F0 8/8, N0 đạt, cả trên server. 14 bảng ngoài fingerprint: cổng Local D12-L3. |
| R08 RB-1 | PARTIAL | Thứ tự khởi động và ràng buộc chữ ký đạt; selector, khoảng verify→stage và vị trí stage cần cứng hoá; candidate chưa có bằng chứng RapidOCR offline sau recreate (D12-L1). RB-G11 PENDING. |
| R09 Hồi quy cuối | PASS (backend, Cloud) | Xem dưới. |

## Kết quả hồi quy cuối trên đúng `18eeecb`

Lệnh: `pytest tests -q -p no:cacheprovider -rfEsxX --tb=short` trong worktree sạch của `18eeecb`, CPython 3.12.3, Tesseract 5.3.4, cache `o200k_base` đã kiểm SHA-256.

| Lượt | Kết quả |
|---|---|
| Full backend trên `18eeecb` (sau tích hợp RB-1) | **3522 passed / 10 failed / 68 skipped**, 0 xfailed, 0 xpassed, 17 phút 39 giây |
| 10 lỗi so với mốc | Trùng **theo tên** với danh sách trong báo cáo hồi quy 12D11, và trùng **theo nguyên nhân** khi chạy cùng hai file trên `2cc824f`: `test_content_settings_defaults` (`'docling' == 'auto'`), chín ca `TestModelsProviderAvailability` (`TypeError` của mock `env_side_effect`). Không liên quan diff `2cc824f..18eeecb`. |
| 68 ca skip | 55 ca cần pipeline đầy đủ (`OCR_FULL_PIPELINE`), 3 ca Docker thật, 8 ca cần model Tesseract Fast/Best, EasyOCR hoặc traineddata thật, 2 ca khác về môi trường OCR. Không ca nào thuộc D10. |
| Bộ D10/D11 trên SurrealDB server 2.3.10 (RocksDB) | 128 passed (embedding, fingerprint, control 12D10, approval, PDF integrity, OCR failure safety trừ một ca timing không dùng DB) |
| `tests/test_phase12d12_review_controls.py` | 18 passed / 6 xfailed (có server); 16 passed / 2 skipped / 6 xfailed (không có server) |
| Frontend | Không chạy lại: `git diff 2cc824f 18eeecb -- frontend` rỗng. |

Lượt chạy đầu bị treo ở một test tải `o200k_base` (host bị chặn trong môi trường review) và đã bị huỷ; số liệu trên là của lượt chạy lại đầy đủ. Không chạy được ở Cloud: Docker thật, build image, PowerShell, pipeline OCR đầy đủ với model thật — thuộc Local.

## Điều kiện trước khi chứng nhận D11-W05 / G-04

**D12-03** phải được sửa (chỉ trong comparator, xem tiêu chí ở báo cáo review) và bốn control `D12-03` trong `tests/test_phase12d12_review_controls.py` phải đạt khi bỏ marker. Cho tới lúc đó, mã 0 của `phase12_standard_diff.py --release` không đủ để đóng G-04. Checklist 12D11 yêu cầu một commit cuối cho mọi cổng, nên nên sửa D12-03 **trước** khi bắt đầu nghiệm thu Windows; nếu chủ sở hữu chọn chạy trước, W05 chỉ có giá trị chẩn đoán và các cổng phải chạy lại trên commit cuối.

Chủ sở hữu cũng cần quyết định cách xử lý tài liệu NOT VERIFIED của W05: trên pipeline thật, số hiệu gạch nối nằm trong tiêu đề, list item, footer, bảng hoặc đoạn nối qua trang không có span chứng minh, nên "mã 0 cho mọi tài liệu" nhiều khả năng không đạt trên 22 PDF pháp lý.

## Cổng Local bổ sung (cùng checklist 12D11)

| ID | Kiểm | Kết quả yêu cầu |
|---|---|---|
| D12-L1 | **Candidate** chạy RapidOCR offline sau mỗi lần recreate: sau cập nhật (chế độ bảo trì), sau `$OPS normal`, sau restart và reboot guest. Trang scan tổng hợp, không có mạng. | OCR đạt bằng `RapidOcrModel`, không fallback Tesseract, không cần "Chuẩn bị" trực tuyến. Nếu không đạt: giới hạn D-32 áp dụng cho candidate và cần quyết định của chủ sở hữu trước khi phát hành. |
| D12-L2 | Ghi `surreal version` và storage engine của server nghiệm thu và production. Chạy `tests/test_phase12d12_review_controls.py -k server` với `CB5400_D12_SURREAL_URL` trỏ tới server cô lập cùng phiên bản, cùng bộ D11-W03. | Bốn job cùng revision cho đúng một bộ chunk; job cũ không khôi phục Source đã xoá; liên kết notebook của Source khác còn nguyên. |
| D12-L3 | Bảo toàn 22 bảng: đưa phương pháp snapshot của RB-G10 vào hồ sơ (script hoặc định nghĩa digest) và áp dụng ở D11-W07/W09 cho 14 bảng ngoài fingerprint (`credential`, `model`, `open_notebook`, `chat_session`, `refers_to`, `transformation`, `episode_profile`, `speaker_profile`, `episode`, `podcast_config`, `ai_feedback`, `recently_viewed`, `command`, `_sbl_migrations`). | 22/22 bảng bằng nhau trước/sau cập nhật và rollback; nêu rõ bảng nào được coi là hoạt động runtime và vì sao. |
| D12-L4 | RB-1 trên gói ký chính thức: kiểm âm selector (ID baseline bị cắt/CRLF, script rỗng), quyền và chủ sở hữu thư mục `RB1_STATE` (root, không ghi được bởi group/other), vị trí ngoài checkout và `$WORK`, tên service khớp nhãn Compose, băm bảy file đã stage so với manifest đã ký. | Adapter và boot guard dừng khi đầu ra selector khác `compose.json` trong lúc tag trỏ baseline; file đã stage đúng byte đã ký. |
| D12-L5 | Diễn tập timeout 300 giây của API sync: worker hoàn tất muộn; lệnh xoá Source gặp lỗi DB; restart worker giữa chừng. Kèm quan sát D12-01: đổi tiêu đề Source khi đang embedding. | Không có text thiếu hay vector cũ được publish. Ghi lại trạng thái Source và job trong từng ca. |

RB-G11 (reboot Ubuntu VM), diễn tập gói ký chính thức (D11-W09), G-07/G-09 trên Windows và E2-01/E2-02 giữ nguyên trạng thái PENDING / NEEDS LOCAL EVIDENCE.

## Phán quyết

```text
FINAL VERDICT: CONDITIONAL PASS — runtime remediation verified; release gate G-04 not yet trustworthy
REVIEW TARGET SHA: 18eeecbfd2cc42549e57cdb866a405083b41a657
REVIEWER MODEL: Claude Code independent session (model identifier reported in the session handover, not recorded in the repository)
D10 VERIFIED_FIXED: 8/9
D10 PARTIAL: 1/9 (D10-06)
D10 NOT_FIXED: 0/9
NEW CODE RELEASE BLOCKERS: 1 (D12-03, release comparator only; no runtime code)
RB-1 CODE INTEGRATION: PARTIAL
RB-1 LOCAL ACCEPTANCE: PENDING
FULL FINAL REGRESSION: PASS (backend on 18eeecb: 3522 passed / 10 baseline failures / 68 skipped; Docker and full-pipeline suites remain Local)
READY FOR WINDOWS ACCEPTANCE: CONDITIONAL
READY FOR UBUNTU VM ACCEPTANCE: CONDITIONAL
READY FOR RELEASE: NO
READY FOR PRODUCTION: NO
PRODUCTION UNCHANGED.
```

Điều kiện của Windows: D12-03 được sửa trước khi chứng nhận D11-W05, và D12-L1 đến D12-L5 được thêm vào lượt nghiệm thu. Điều kiện của Ubuntu VM: các cổng Windows đạt trên cùng commit cuối, D12-L1 và D12-L4 đạt trên VM, RB-G11 được chạy.
