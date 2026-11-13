# Báo cáo Phase 8C — Sửa chất lượng OCR, tối ưu và nghiệm thu cuối

Ngày: 2026-11-13 · Máy nghiệm thu: Ubuntu Server, 8 CPU, 30 GB RAM, không GPU
Branch: `local/ocr-phase8c` (kế thừa đủ `local/ocr-phase8b`) · Chưa push, chưa merge, chưa triển khai

## 1. Kết luận

- **Tesseract Vietnamese Best và Fast: đã sửa được lỗi chính.** Bảng scan và trang xoay giờ đọc đúng.
  Trường khóa (số tiền, ngày, số hiệu) đạt 1,00 trên cả tập nghiệm thu lẫn tập holdout độc lập; dòng
  bảng đúng 8/16 → 16/16 (Best, fixture) và 3/42 → 38/42 (Best, holdout).
- **Hạ tầng online → offline → restart offline → cập nhật online: PASS cho cả 4 lựa chọn** trong Docker
  (72 PASS / 1 FAIL; Phase 8B chưa nghiệm thu được offline cho Tesseract Fast và EasyOCR).
- **Chưa đạt điều kiện merge theo đúng chữ của `RELEASE_CANDIDATE.md` §3.1:** lộ trình nhanh §4.3 còn
  3 FAIL (Phase 8B: 4). Cả 3 cùng một nguyên nhân: model Tesseract Best đọc mất dấu ở một tiêu đề in
  đậm (`BẢNG KÊ` → `BANG KE`) ngay trên ảnh gốc — giới hạn model, không phải lỗi tích hợp, và không
  sửa được bằng tùy chọn chính thức. Không hạ ngưỡng, không sửa fixture.
- **EasyOCR: không đạt** ở ảnh scan 150 DPI (giới hạn model), dù đã cải thiện (CER 0,47 → 0,17).
- **Không có regression:** backend 1211 passed / 10 failed (đúng 10 lỗi có sẵn trên `main`), frontend
  404/404, bảo mật trực tiếp 16/16, không tài liệu nào trong hai tập đo bị xấu đi.

Quyết định dành cho chủ dự án ở mục 9.

## 2. Bảng kết quả

| Hạng mục | Phase 8B | Phase 8C |
|---|---|---|
| Full pipeline, lộ trình nhanh (Tesseract Best) | 5 PASS / 4 FAIL | **6 PASS / 3 FAIL** |
| Full pipeline, 4 lựa chọn × 7 fixture | 33 PASS / 15 FAIL | **38 PASS / 10 FAIL** / 0 NOT VERIFIED |
| — RapidOCR | 7 / 8 | 8 / 8 |
| — Tesseract Fast | 4 / 9 | 7 / 9 |
| — Tesseract Best | 5 / 9 | 6 / 9 |
| — EasyOCR | 4 / 9 | 4 / 9 |
| Docker đủ 4 lựa chọn (nâng cấp từ production `5e04227`) | 53 PASS / 2 FAIL, offline chưa chạy cho 2 engine | **72 PASS / 1 FAIL / 0 NOT VERIFIED**, offline đủ 4 engine |
| Holdout 13 tài liệu — Tesseract Best: CER / trường khóa / dòng bảng | 0,394 / 0,63 / 3 trên 42 | **0,023 / 1,00 / 38 trên 42** |
| Backend regression | 1166 passed / 10 failed | 1211 passed / 10 failed (cùng 10 lỗi của `main`) |
| Lỗi backend mới | 0 | 0 |
| Frontend | 404/404, lint 0 error, tsc 0, build PASS | như cũ (không đổi mã frontend) |
| Bảo mật trực tiếp trên stack nghiệm thu | 16/16 | 16/16 |
| mypy / ruff | 33 lỗi có sẵn / 1 có sẵn | 33 / 1 (không lỗi mới) |
| Review độc lập | 0 High, 0 Medium | 0 High, 3 Medium — đã sửa |

10 bài còn FAIL:

| Bài | Nguyên nhân | Nhóm |
|---|---|---|
| tesseract_best – `bang_gop_scan`, `nhieu_trang_scan`, `hon_hop` | tiêu đề in đậm đọc thành `BANG KE …` / `… MAU` | J — giới hạn model |
| tesseract_fast – `bang_gop_scan`, `nhieu_trang_scan` | như trên | J |
| easyocr – 5 fixture scan | đọc sai chữ số và dấu ở 150 DPI (`1.250,000,000`) | J |

Trong các bài này, phần còn lại của tài liệu đúng: với Tesseract, bảng 4/4 dòng (Best), số tiền, ngày,
số hiệu đều 1,00; chỉ cụm tiêu đề không khớp từng dấu.

## 3. Đã làm gì

| Phase | Nội dung | Kết quả |
|---|---|---|
| 8C.0 | Preflight: xác minh 7 commit Phase 8B, bundle `phase8b-backup.bundle` (`git bundle verify` OK), ghi trạng thái production, dung lượng | Xong. Phát hiện một phiên trước đã làm dở Phase 8C chưa commit: đã lưu diff và toàn bộ thí nghiệm vào `evidence/phase8c/` trước khi tiếp tục |
| 8C.1 | Tái hiện baseline trên worktree `f172645`, phân loại 15 bài | [OCR_FAILURE_ANALYSIS.md](OCR_FAILURE_ANALYSIS.md) |
| 8C.2 | Tesseract OSD | D-25: gate OSD + chuẩn hóa hướng trang + scale theo DPI + `user_defined_dpi` |
| 8C.3 | EasyOCR | D-26: ngưỡng 0,2. Decoder/beam/contrast không chỉnh được qua API chính thức |
| 8C.4 | RapidOCR trang xoay | Tái dùng chuẩn hóa hướng trang; không đổi model, backend torch |
| 8C.5 | Tesseract Fast / DPI | Scale khớp độ phân giải scan; ma trận 150/200/300 DPI |
| 8C.6 | Chống overfitting | Holdout 13 tài liệu, chạy một lần; 48 bài giữ nguyên |
| 8C.7 | Triển khai | 2 module mới, 3 module sửa, 45 unit test mới |
| Nghiệm thu | Full pipeline, Docker 4 engine, regression, frontend, bảo mật, review độc lập | mục 2 |

Chi tiết kỹ thuật: [OCR_QUALITY_OPTIMIZATION.md](OCR_QUALITY_OPTIMIZATION.md). Số đo:
[OCR_QUALITY_BENCHMARK.md](OCR_QUALITY_BENCHMARK.md).

## 4. Thay đổi mã

| File | Thay đổi |
|---|---|
| `open_notebook/ocr/tesseract_gate.py` (mới) | Lọc kết quả OSD độ tin cậy thấp; đặt qua `TesseractCliOcrOptions.tesseract_cmd` |
| `open_notebook/ocr/pdf_prep.py` (mới) | Dò hướng trang scan, sửa `/Rotate` trong bản sao tạm; scale theo độ phân giải scan |
| `open_notebook/ocr/options.py` | `tesseract_command()`, `easyocr_confidence_threshold()`, tham số `scale` |
| `open_notebook/ocr/docling_extract.py` | `convert_document()` — điểm vào production; metadata và log |
| `open_notebook/ocr/runtime.py` | `user_defined_dpi 216` trong config `tsv` |
| `scripts/ocr/docker-acceptance.sh`, `acceptance_api.py` | Engine chỉ FAIL nội dung vẫn qua bước offline; so hash văn bản online/offline |
| `scripts/ocr/quality_eval.py`, `generate_holdout_fixtures.py` (mới) | Công cụ đo và tập holdout |
| `tests/test_ocr_quality_prep.py` (mới, 45 test) | Gate, pdf_prep, ngưỡng EasyOCR, vòng đời bản sao tạm |
| `tests/test_ocr_integration.py` | Bài full pipeline chạy qua `convert_document`; **ngưỡng, fixture, ground truth không đổi** |
| `tests/test_ocr_bundle_cli.py` | Nội dung config `tsv` mới |

Giữ nguyên: Layout Heron, TableFormer accurate, `DocumentConverter`, PDF backend, compatibility guard,
dependency lock, Online Preparation, Offline Readiness, lưu trữ bền, bảo mật job, transformation,
embedding, RAG, chat. Không thêm engine. Không sửa Docling / Content Core / site-packages. Không
monkey patch trong mã production. Không subclass `BaseOcrModel`.

Commit (cục bộ): `e6f2bbb` (thay đổi chính), `755b637` (sửa theo review), `6f1c811` (test), cộng commit
tài liệu của phase này.

## 5. Docker E2E

`SCENARIOS="rapidocr tesseract_fast tesseract_best easyocr" OLD_REF=5e04227` — project compose riêng,
mạng nội bộ riêng, offline bằng cách ngắt mạng egress của container đang chạy.

| Bước | Kết quả |
|---|---|
| 0–1. Nâng cấp từ bản production `5e04227`: settings và dữ liệu giữ nguyên, không tải model lúc khởi động | PASS |
| 2. Chuẩn bị online → `offline_ready`, E2E qua API + worker | PASS cho RapidOCR, Tesseract Fast, Tesseract Best; **EasyOCR FAIL nội dung** (pipeline chạy, thiếu `1234/2024/QĐ-MẪU` và câu có số tiền) |
| 2. Chuẩn bị lần hai dùng lại model (checksum không đổi) | PASS × 4 |
| 3. Offline: `offline_verified` + xử lý PDF | PASS × 4 (EasyOCR: kết quả trùng lúc online) |
| 4. Restart khi offline | PASS × 4; settings và engine đang chọn giữ nguyên |
| 5. Cập nhật online (rebuild thật, recreate), model dùng lại, chuẩn bị lại | PASS × 4 |
| 5b. Offline lại sau cập nhật | PASS × 4 |
| Checksum model và cache Hugging Face không đổi; không có lần tải nào trong log khi offline | PASS ở cả ba vòng offline |

Tổng: 72 PASS / 1 FAIL / 0 NOT VERIFIED. Log: `evidence/phase8c/runs/docker-acceptance-full-8c.log`.

Chưa chạy lại trong Phase 8C: kịch bản `OCR_RAPIDOCR_PERSISTENT=true` (36/36 ở Phase 8B; mã liên quan
không đổi) và `offline_verified` ngoài Docker (không ngắt mạng máy chủ vì sẽ ảnh hưởng production).

## 6. Hiệu năng

- Dò hướng trang: khoảng 1 giây cho mỗi trang scan, giới hạn 200 trang/tài liệu; trang có text layer
  không tốn gì.
- Tesseract trên ảnh 150 DPI nhanh hơn trước (render ít điểm ảnh hơn); trên holdout tổng thời gian
  tăng 15–20 %. Peak RSS tăng 200–800 MB trong tiến trình đo. Bảng số: OCR_QUALITY_BENCHMARK §4.

## 7. An toàn

- Deployment `chatbot5400-version02`: cùng container ID, cùng thời điểm start (2026-11-12 14:41 UTC),
  restart = 0, `/health` 200 trước và sau (`evidence/phase8c/preflight/production-{before,after}.txt`).
- 20 volume có từ trước còn nguyên. Không xóa volume, image, evidence, thư mục work hay model cache.
  Không `docker system prune`, không `down -v`.
- Không merge, không push, không triển khai. Branch `local/ocr-phase8b` còn nguyên.
- Không dùng tài liệu thật; mọi dữ liệu đo là tổng hợp.

## 8. Review độc lập (agent riêng, chỉ đọc mã, commit `e6f2bbb`)

0 High. Đã xử lý ở `755b637`:

| Mức | Phát hiện | Xử lý |
|---|---|---|
| Medium | Dò hướng không giới hạn số trang; một trang lỗi làm mất kết quả các trang khác | Giới hạn 200 trang, 30 s/trang; lỗi từng trang được cô lập |
| Medium | Scale theo trung vị DPI làm trang 300 DPI trong tài liệu hỗn hợp bị render thấp hơn trước | Dùng DPI **cao nhất** của tài liệu |
| Medium | Gate cần `python3` trên PATH; thiếu thì Tesseract hỏng hẳn | Chỉ dùng gate sau khi `gate --version` chạy được; không thì gọi thẳng Tesseract |
| Low | Script Docker so danh sách chuỗi thiếu, không so văn bản | So thêm SHA-256 của toàn bộ văn bản |
| Low | Ngưỡng `nan`/âm; thư mục tạm sót khi engine id sai; test rò biến môi trường; test chưa phủ vòng đời bản sao | Đã sửa và thêm test |

Ghi nhận, không đổi:

- Người dùng RapidOCR/EasyOCR có cài Tesseract sẽ được tự xoay trang khi OSD cả trang đạt ngưỡng; ngưỡng
  đo trên mẫu tiếng Việt/Latin. Tắt bằng `OCR_PDF_PREP=false`.
- `user_defined_dpi` cố định 216 trong khi scale thay đổi (đo cho thấy giá trị không ảnh hưởng).
- Scan lưu dạng nhiều mảnh ảnh nhỏ không được coi là trang scan (giữ hành vi cũ).
- Chiều xoay được kiểm bằng Tesseract thật trên holdout (90°, 180°, 270° và file trộn hướng), không
  bằng unit test.

## 9. Cần chủ dự án quyết định

1. **Điều kiện merge §3.1 (`FAIL == 0` ở lộ trình nhanh).** Còn 3 FAIL do giới hạn model ở một cụm tiêu
   đề. Lựa chọn:
   - (a) chấp nhận là giới hạn đã biết và điều chỉnh tiêu chí nghiệm thu cho cụm tiêu đề in đậm (ví dụ
     so không dấu, hoặc tách thành bài kiểm riêng không chặn) — cần quyết định vì đây là đổi tiêu chuẩn;
   - (b) giữ tiêu chí, coi tính năng chưa đạt, và mở phạm vi cho phương án ngoài giới hạn hiện tại
     (ví dụ model Tesseract khác);
   - Khuyến nghị: (a). Bằng chứng: trường khóa và bảng đạt 1,00 / 16 trên 16, holdout xác nhận.
2. **`tesseract_gate.py`** có nằm trong giới hạn "chỉ dùng API chính thức, không adapter" hay không
   (OCR_QUALITY_OPTIMIZATION §2.6). Nếu không: `OCR_TESSERACT_OSD_GATE=false`; khi đó bảng scan đứng
   thẳng có thể lại bị lật 180°.
3. **Tự xoay trang cho RapidOCR / EasyOCR** khi có `osd.traineddata`: giữ (mặc định hiện tại) hay chỉ
   áp cho Tesseract.
4. **EasyOCR:** giữ trong danh sách với ghi chú "cần scan ≥ 200 DPI, không khuyến nghị cho bảng", hay
   không khuyến nghị cho tiếng Việt.
5. **Dọn dẹp** (mục 10) và việc push branch.

Trước khi triển khai production vẫn cần: benchmark trên tài liệu thật (làm cục bộ), backup, và quy
trình vận hành ở `RELEASE_CANDIDATE.md` §4.

## 10. Tài nguyên còn trên máy (chưa xóa gì)

| Thành phần | Dung lượng | Ghi chú |
|---|---|---|
| `work/` (8 thư mục nghiệm thu, dữ liệu thuộc root) | 17 GB | Phase 8C thêm 1 thư mục (~3 GB) |
| Build cache Docker | ~38 GB lúc bắt đầu | không đụng tới |
| Image `chatbot5400:ocr-accept`, `ocr-accept-old`, `node:22-slim` | 2,6 + 2,5 + 0,3 GB | dùng lại từ Phase 8B |
| Volume ẩn danh do nghiệm thu | 14 (Phase 8B) + 2 (Phase 8C) | danh sách: `acceptance-anonymous-volumes.txt`, `evidence/phase8c/preflight/anonymous-volumes-created-in-8c.txt` |
| Worktree `baseline-8b-src` | nhỏ | `git worktree remove ../baseline-8b-src` khi không cần so sánh nữa |
| Ổ đĩa | 351 GB → 345 GB trống | |

## 11. Bằng chứng

`/home/admin/cb5400-ocr-accept/evidence/phase8c/`:

| Thư mục / file | Nội dung |
|---|---|
| `preflight/` | diff chưa commit lúc bắt đầu, trạng thái production trước/sau, dung lượng trước/sau, volume mới |
| `baseline/`, `after/` | 7 fixture × 4 engine, Phase 8B và Phase 8C |
| `holdout/`, `holdout-baseline/`, `holdout-after/` | tập holdout và kết quả |
| `experiments-session1/` | khảo sát OSD trên crop và trên trang, lưới PSM / mode / scale, ma trận DPI, quét ngưỡng EasyOCR |
| `easyocr-scale/` | quét scale EasyOCR |
| `runs/ocr-acceptance-{quick,full}-8c.json` | 9 và 48 bài nghiệm thu |
| `runs/docker-acceptance-full-8c.log` | Docker 4 engine |
| `runs/pytest-full-8c.txt`, `pytest-failed-{main,8c}.txt` | regression backend |
| `runs/frontend-8c.txt`, `runs/security-live-8c.json` | frontend, bảo mật trực tiếp |
| `tables.md`, `make_tables.py` | bảng trước/sau |
| `commits.txt` | thông tin commit |
