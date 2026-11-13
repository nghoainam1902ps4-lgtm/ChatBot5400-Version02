# Release Candidate — OCR Engine Manager (Phase 0 → 9B)

- **Branch phát hành:** `release/ocr-engine-manager-rc1` (branch phát triển ban đầu: `claude/friendly-mendel-a2b6m5`).
- **Gốc so sánh:** `5e04227` (trước tính năng) và `e32eae8` (Phase 7).
- **Không merge main, không triển khai production** trong phiên phát triển.

Trạng thái (sau Phase 9B, 2026-11-14) — chi tiết ở §10:

- **Đủ điều kiện merge** theo cổng merge của Phase 9B: review độc lập đã xử lý mọi phát hiện mức Cao; không lỗi
  mới; Tesseract Best đạt tiêu chí có điều kiện 7/7; Docker không có lỗi mới. Trạng thái PR và merge:
  `OCR_PHASE9B_REPORT.md` §G.
- **NOT DEPLOYED.** Triển khai production chờ phê duyệt, benchmark tài liệu thật, sao lưu và kiểm tra restore.
- Bộ nghiệm thu gốc không đổi: 38 PASS / 10 FAIL.

Trạng thái sau Phase 9A (2026-11-13, giữ để đối chiếu) — chi tiết ở §9:

- **READY FOR MERGE** — theo tiêu chí phát hành có điều kiện (D-27) đã được chủ dự án chấp nhận; review cuối
  0 High / 0 Medium.
- **READY FOR CONDITIONAL RELEASE** — Tesseract Vietnamese Best và RapidOCR, **với URL ingestion tắt** (D-29).
- **NOT READY FOR PRODUCTION** — còn thiếu benchmark tài liệu thật, backup + kiểm tra restore, kiểm tra trên
  môi trường đích, phê duyệt kế hoạch triển khai.
- Branch phát hành: `release/ocr-engine-manager-rc1`. Bộ nghiệm thu gốc không đổi: 38 PASS / 10 FAIL.

Trạng thái sau Phase 8D (giữ để đối chiếu) — chi tiết ở §8:

- **READY FOR MERGE (có điều kiện)** — theo tiêu chí phát hành có điều kiện D-27; chờ chủ dự án xác nhận.
- **READY FOR CONDITIONAL RELEASE** — Tesseract Vietnamese Best (khuyến nghị) và RapidOCR (tương thích ngược).
- **NOT READY FOR PRODUCTION** — rủi ro SSRF qua redirect chưa có biện pháp được phê duyệt; chưa benchmark
  trên tài liệu thật.
- Bộ nghiệm thu gốc **không đổi**: 38 PASS / 10 FAIL; lộ trình nhanh 6 PASS / 3 FAIL.

Trạng thái sau Phase 8C (giữ để đối chiếu): **CHỜ QUYẾT ĐỊNH CỦA CHỦ DỰ ÁN — xem §7.** Lỗi chất lượng chính
(P8B-4, P8B-5, P8B-6) đã xử lý; điều kiện §3.1 còn 3 FAIL do giới hạn model. Chưa merge, chưa push, chưa
triển khai.

Trạng thái sau Phase 8B (giữ để đối chiếu): **CHƯA ĐỦ ĐIỀU KIỆN MERGE `main`, CHƯA ĐỦ ĐIỀU KIỆN PRODUCTION.**

- Nghiệm thu runtime trên máy thật đã chạy (`OCR_TEST_REPORT.md` §9).
- Hạ tầng online → offline đã PASS sau ba bản sửa. Hai trong số đó là lỗi chặn: P8B-2 và P8B-3.
- Chất lượng full pipeline **FAIL** ở điều kiện bắt buộc §3.1: §4.3 lộ trình nhanh có 4 FAIL do OSD
  của Tesseract (P8B-4).
- Lỗi chất lượng OCR (P8B-4, P8B-5) chưa sửa: cần quyết định thiết kế, xem §6.

## 1. Đã xác nhận (có bằng chứng thực tế)

| Hạng mục | Bằng chứng |
|---|---|
| 3 engine / 4 lựa chọn, chỉ dùng class OCR chính thức của Docling; Layout Heron / TableFormer không đổi; RapidOCR mặc định không đổi | `ACCEPTANCE_CHECKLIST.md` |
| OCR tiếng Việt thật qua Docling (OCR stage): Tesseract Fast / Best, EasyOCR trên CPU | `OCR_TEST_REPORT.md` §2.3; `OCR_BENCHMARK.md` |
| Cài model theo nhu cầu, ghim checksum, lưu bền vững, offline bundle (máy air-gapped) | §2.1–2.2 Test Report |
| Khoá dependency theo `uv.lock` + guard tương thích | D-14; 12 test |
| Bảo mật job nền: `/api/commands/*` chỉ admin, tắt submit tổng quát, worker kiểm tra lại đầu vào | ADR-014, D-19; 57 test với file canary |
| Readiness không bao giờ dựa vào file; kết quả lỗi thời khi phiên bản / cache / trọng số đổi | D-20; 39 test; chạy thật: `prepare` trả `not_offline_ready` đúng khi HF bị chặn |
| RapidOCR lưu bền vững qua `Global.model_root_dir` | Chạy thật với onnxruntime khi mạng bị chặn |
| Regression | 1053 passed / 10 failed so với 951 / 10 ở `e32eae8`: cùng 10 lỗi có sẵn, 0 lỗi mới |
| Review độc lập diff 8A | 7/8 phát hiện đã sửa kèm test, gồm một lỗi Cao: tạo nguồn upload/link qua đường **sync** bị guard mới chặn (`OCR_TEST_REPORT.md` §8.4) |
| Frontend | tsc 0 lỗi, lint 0 error, vitest 404 passed, build PASS |
| Tài liệu | `OCR_ONLINE_PREPARATION.md`, `OCR_LOCAL_ACCEPTANCE.md` (lệnh qua `bash -n`); ShellCheck sạch |
| **Phase 8B — máy thật** | Ubuntu 26.04, 8 CPU; Docker 29.8 / Compose 5.6 (`OCR_TEST_REPORT.md` §9) |
| Full pipeline Docling thật (Heron + TableFormer accurate + OCR), 4 engine | §4.1, §4.2 PASS. §4.3: 33/48 PASS, **15 FAIL** (chất lượng OCR, §6) |
| Prepare online → `offline_ready` (4 engine) → `offline_verified` (offline thật trong container) | PASS sau sửa P8B-2 |
| Docker lộ trình nhanh: cập nhật online từ `e32eae8` → chuẩn bị → offline → restart offline → cập nhật online → offline | **40/40 PASS** |
| Docker đầy đủ: cập nhật từ production `5e04227`, 4 engine | 53 PASS / **2 FAIL** (E2E nội dung: Tesseract Fast, EasyOCR). Hạ tầng PASS; offline E2E PASS cho RapidOCR và Tesseract Best |
| RapidOCR backend torch | Chạy thật: trọng số từ modelscope.cn; offline E2E PASS ở chế độ mặc định. `OCR_RAPIDOCR_PERSISTENT=true`: 36/36 PASS sau sửa P8B-8, trọng số giữ qua recreate |
| API + worker E2E thật (upload → xử lý → Markdown) | PASS (trong Docker acceptance) |
| Bảo mật trực tiếp trên stack nghiệm thu | 16/16 PASS |
| Regression máy thật | 1166 passed / 10 failed; `main`: cùng đúng 10 lỗi ⇒ 0 lỗi mới |
| Benchmark full pipeline | `OCR_BENCHMARK.md` §6 |

## 2. NOT VERIFIED (chưa chạy thật — lý do: mạng Cloud)

> **Phase 8B:** các mục dưới đây đã chạy trên máy thật, kết quả ở §1 và `OCR_TEST_REPORT.md` §9.
> Còn chưa nghiệm thu sau 8B:
> - `offline_verified` ngoài Docker: không ngắt mạng máy có deployment đang chạy; đã nghiệm thu trong
>   container;
> - vận hành offline E2E của Tesseract Fast và EasyOCR: E2E online FAIL nội dung nên script không chạy
>   bước offline cho hai engine này;

| Hạng mục | Chặn bởi | Cách nghiệm thu |
|---|---|---|
| Full pipeline Docling (Heron + TableFormer + OCR) với cả 4 engine, 7 fixture có ground truth | huggingface.co 403 | `OCR_LOCAL_ACCEPTANCE.md` §4.3 |
| Prepare online → `offline_ready` → `offline_verified` | huggingface.co, modelscope.cn 403 | §4.4 |
| RapidOCR backend torch (production), mặc định và `OCR_RAPIDOCR_PERSISTENT=true` | modelscope.cn 403 | §4.4, §5 |
| Docker: cập nhật online từ bản đang chạy → chuẩn bị → offline (mọi engine) → restart offline → cập nhật online + rebuild thật | Docker Hub 429, ghcr 403, Debian apt 403 | §5 |
| API + worker E2E thật (upload → xử lý → Markdown) | tải SurrealDB binary bị chính sách phiên từ chối | §5 (chạy cùng script) |
| Benchmark full pipeline | huggingface.co | §8 |

## 3. Điều kiện trước khi merge `main`

1. Chạy `OCR_LOCAL_ACCEPTANCE.md` lộ trình **nhanh** (Tesseract Best). Kết quả bắt buộc:
   - §4.3: `FAIL == 0`;
   - §5: không có dòng `FAIL`.
2. Đọc lại diff `e32eae8..HEAD`, đặc biệt `api/routers/commands.py` và `open_notebook/utils/job_input_guard.py`.
   Thay đổi ở commands là **thay đổi hành vi**: script ngoài nào gọi `POST /api/commands/jobs` sẽ bị từ chối.
3. Xác nhận lại trên máy thật: 10 lỗi test có sẵn (`test_models_api` ×9, `test_domain` ×1) đều có ở
   `main`, không phải do branch này.

## 4. Điều kiện trước khi triển khai production

1. Lộ trình nghiệm thu **đầy đủ**: 4 engine; Docker §5 với `OLD_REF` = commit production thật. Mọi bước
   PASS, không có NOT VERIFIED ngoài engine cố ý bỏ qua.
2. Benchmark trên tài liệu thật **làm cục bộ**, không đưa lên GitHub. Chọn engine trong Settings dựa trên
   kết quả benchmark.
3. Backup trước khi cập nhật: `notebook_data` và `surreal_data`. **Không** dùng `docker compose down -v`.
4. Quy trình vận hành:
   - cập nhật khi online;
   - `prepare` cho engine dùng thật;
   - chờ trạng thái `offline_ready`;
   - ngắt Internet;
   - `readiness --check` ⇒ `offline_verified`.

   Chi tiết: `OCR_ONLINE_PREPARATION.md`.
5. Nếu container có thể bị recreate trong lúc offline: đặt `OCR_OFFLINE=true`. Nếu dùng RapidOCR, chạy
   `prepare` lại sau mỗi lần recreate khi có mạng, hoặc bật `OCR_RAPIDOCR_PERSISTENT=true` sau khi đã nghiệm
   thu chế độ này (backend torch).
6. Hạn chế đã biết (dev defaults, không đổi trong phạm vi này): CORS mở, auth mật khẩu đơn giản, image
   chạy root.
7. Kế hoạch rollback đã đọc: `OCR_ROLLBACK.md`. Volume giữ nguyên; bản cũ bỏ qua dữ liệu OCR.

## 5. Phạm vi không hứa

- LLM / embedding offline: phụ thuộc nhà cung cấp mô hình.
- Cài đặt / cập nhật hoàn toàn offline: không bắt buộc. Offline bundle chỉ giữ cho máy air-gapped.
- GPU: mọi engine được cấu hình và kiểm thử trên CPU.

## 6. Phase 8B — đối chiếu điều kiện và việc còn lại

**§3 Điều kiện merge `main`:**

| Điều kiện | Kết quả |
|---|---|
| 3.1 §4.3 lộ trình nhanh: `FAIL == 0` | **KHÔNG ĐẠT** — 4 FAIL (`bang_gop_scan`, `hon_hop`, `nhieu_trang_scan`, `vb_xoay_scan`) |
| 3.1 §5 lộ trình nhanh: không có `FAIL` | **ĐẠT** — 40/40 PASS |
| 3.2 Đọc lại `api/routers/commands.py`, `job_input_guard.py` | **ĐẠT**: router commands chỉ admin, submit tổng quát bị tắt (kiểm tra trực tiếp: 403), guard đúng thiết kế. Thay đổi hành vi `POST /api/commands/jobs` (luôn 403) vẫn phải thông báo cho ai có script ngoài |
| 3.3 10 lỗi test có sẵn cũng có trên `main` | **ĐẠT** — cùng đúng 10 lỗi |

**§4 Điều kiện production:** **KHÔNG ĐẠT** — §4.1: Docker đầy đủ còn 2 FAIL; full pipeline còn 15 FAIL.

**Sửa trong 8B (commit cục bộ, chưa push):**

- `5e6522e` — P8B-1, script nghiệm thu;
- `5cbcb37` — P8B-2, **chặn**: readiness không bao giờ đạt `offline_ready`;
- `4a0b00f` — P8B-3, **chặn**: treo ~16 phút khi mất mạng (D-24);
- `d9652c0` — P8B-8: `OCR_RAPIDOCR_PERSISTENT=true` lỗi với backend torch;
- `a8a30c0`, `2128587` — test / review.

**Việc cần quyết định trước khi merge:**

1. **P8B-4 (Tesseract OSD):** chọn cách xử lý OSD trên crop. Phương án đã đo: thêm lề trắng trước OSD
   và/hoặc bỏ qua hướng có độ tin cậy thấp (vá hành vi Docling, cần ghim hash như D-14). Sau đó chạy
   lại §4.3.
2. **P8B-5 (EasyOCR):** quyết định ngưỡng `confidence_threshold` (cần benchmark trên tài liệu thật),
   hoặc không khuyến nghị EasyOCR cho tiếng Việt.
3. **P8B-6 / P8B-7:** chấp nhận là giới hạn đã biết (RapidOCR không xử lý trang xoay; Tesseract Fast ở
   150 DPI), **hoặc** đổi ngưỡng test sau khi ghi số đo. Không tự hạ ngưỡng trong 8B.
4. Chạy lại `OCR_LOCAL_ACCEPTANCE.md` lộ trình đầy đủ sau khi sửa.

## 7. Phase 8C — đối chiếu điều kiện và quyết định còn lại

Branch cục bộ `local/ocr-phase8c`. Báo cáo: [OCR_PHASE8C_REPORT.md](OCR_PHASE8C_REPORT.md).

**§3 Điều kiện merge `main`:**

| Điều kiện | Kết quả |
|---|---|
| 3.1 §4.3 lộ trình nhanh: `FAIL == 0` | **KHÔNG ĐẠT theo đúng chữ** — 6 PASS / 3 FAIL (8B: 5 / 4). Cả 3 do model Tesseract Best đọc mất dấu ở một tiêu đề in đậm; trường khóa 1,00, bảng 4/4 dòng |
| 3.1 §5: không có `FAIL` (Tesseract Best) | **ĐẠT** — mọi dòng của Tesseract Best PASS trong lượt Docker 4 engine |
| 3.2 Đọc lại commands / job guard | **ĐẠT** (Phase 8B); Phase 8C không đụng tới; bảo mật trực tiếp 16/16 |
| 3.3 10 lỗi test có sẵn cũng có trên `main` | **ĐẠT** — cùng đúng 10 lỗi |

**§4 Điều kiện production:**

| Điều kiện | Kết quả |
|---|---|
| 4.1 Docker đủ 4 engine, `OLD_REF` = production thật, mọi bước PASS | Hạ tầng **ĐẠT** cho cả 4 engine (72 PASS, 0 NOT VERIFIED). 1 FAIL: nội dung EasyOCR |
| 4.1 Full pipeline đủ 4 engine | **KHÔNG ĐẠT** — 38 PASS / 10 FAIL (giới hạn model: tiêu đề Tesseract ×5, EasyOCR ×5) |
| 4.2 Benchmark trên tài liệu thật | **CHƯA LÀM** — việc của người vận hành, làm cục bộ |
| 4.3–4.7 Backup, quy trình vận hành, rollback | Chưa tới bước này |

**Việc của Phase 8B đã đóng:** P8B-4 (OSD Tesseract) — D-25; P8B-5 (ngưỡng EasyOCR) — D-26; P8B-6
(RapidOCR trang xoay) — chuẩn hóa hướng trang; P8B-7 (Tesseract Fast 150 DPI) — scale theo độ phân giải
scan, trường khóa đạt 1,00.

**Cần quyết định trước khi merge** (chi tiết và khuyến nghị: `OCR_PHASE8C_REPORT.md` §9):

1. Tiêu chí §3.1 với 3 FAIL do giới hạn model: điều chỉnh tiêu chí cho cụm tiêu đề in đậm, hay giữ và
   coi là chưa đạt.
2. `tesseract_gate.py` có nằm trong giới hạn "chỉ dùng API chính thức" hay không.
3. Tự xoay trang cho RapidOCR / EasyOCR khi có `osd.traineddata`.
4. Vị trí của EasyOCR (ghi chú giới hạn, hay không khuyến nghị cho tiếng Việt).

**Khuyến nghị sử dụng sau Phase 8C:** Tesseract Vietnamese Best cho văn bản và bảng scan tiếng Việt;
RapidOCR giữ làm mặc định để tương thích ngược; EasyOCR không khuyến nghị cho scan dưới 200 DPI.

## 8. Phase 8D — tiêu chí phát hành có điều kiện và trạng thái cuối

Branch cục bộ `local/ocr-phase8c`. Báo cáo: [OCR_PHASE8D_REPORT.md](OCR_PHASE8D_REPORT.md). Quyết định: D-27, D-28.

### 8.1 Tiêu chí phát hành có điều kiện (bổ sung, không thay §3)

Điều kiện §3.1 gốc (`FAIL == 0` ở lộ trình nhanh) **vẫn được đo và báo**. Chủ dự án chấp nhận phát hành
khi **tất cả** các điều sau đúng cho engine được phát hành:

1. Mọi kiểm tra **Critical** đạt trên cả 7 fixture: mọi số tiền, mọi ngày, mọi số hiệu; hình dạng bảng;
   giá trị số của từng dòng bảng; ô tiêu đề gộp; tiêu đề có mặt đúng vị trí khi không xét dấu.
2. Mỗi bài gốc còn FAIL chỉ thất bại ở assertion tiêu đề, và lỗi đó là **KL-1** (mất dấu ở
   `BẢNG KÊ CHI TIẾT KHOẢN MỤC MẪU`). Có bất kỳ lỗi nào khác ⇒ bài đó FAIL, ngoại lệ không áp dụng.
3. 48 bài gốc, fixture, ground truth, ngưỡng không đổi; không `skip` / `xfail`.
4. Công cụ: `uv run python scripts/ocr/release_criteria.py --out … --markdown …`.

### 8.2 Kết quả

| Engine | Bộ gốc | Critical | Có điều kiện | Kết luận |
|---|---|---|---|---|
| Tesseract Vietnamese Best | 6/9 (3 FAIL) | 7/7 | 7/7 (3 bài áp dụng KL-1) | **Đạt tiêu chí có điều kiện** |
| Tesseract Vietnamese Fast | 7/9 (2 FAIL) | 7/7 | 5/7 — 2 bài còn sai nhãn dòng `Tổng cộng` | **Không đạt** tiêu chí có điều kiện; dùng được với giới hạn đã ghi |
| RapidOCR – PaddleOCR | 8/8 | 7/7 (tiêu chí riêng: trường số) | 7/7 | Đạt — engine tương thích ngược |
| EasyOCR Vietnamese | 4/9 (5 FAIL) | 2/7 | 2/7 | **Không đạt** — thử nghiệm |

| Điều kiện | Kết quả |
|---|---|
| §3.1 gốc, §4.3 lộ trình nhanh `FAIL == 0` | **KHÔNG ĐẠT theo đúng chữ** — 6 PASS / 3 FAIL |
| §3.1 theo tiêu chí có điều kiện (Tesseract Best) | **ĐẠT** — 7/7, critical 7/7 |
| §3.1 §5 Docker lộ trình nhanh không có `FAIL` | **ĐẠT** — 42 PASS / 0 FAIL (lượt đầu 41/1 do lỗi của script nghiệm thu, đã sửa `c5162df`) |
| §3.2, §3.3 | **ĐẠT** — bảo mật trực tiếp 16/16; backend cùng 10 lỗi của `main` |
| §4.1 Docker 4 engine | Hạ tầng **ĐẠT** — 74 PASS / 1 FAIL (nội dung EasyOCR) / 0 NOT VERIFIED |
| §4.1 `OCR_RAPIDOCR_PERSISTENT=true`, backend torch (chạy lại sau Phase 8C) | **ĐẠT** — 42 PASS / 0 FAIL |
| RapidOCR / EasyOCR khi image không có Tesseract | **ĐẠT** — 50 PASS / 1 FAIL (nội dung EasyOCR); không có Tesseract trong container, không cài ngầm; hướng trang báo `tesseract_missing` |
| §4.2 Benchmark trên tài liệu thật | **CHƯA LÀM** |
| Bảo mật: SSRF qua redirect | **CÒN MỞ** — cần biện pháp được phê duyệt (D-28) |

### 8.3 Giới hạn

- **Đã chấp nhận:** KL-1; `tesseract_gate.py` (đã review, rollback `OCR_TESSERACT_OSD_GATE=false`);
  RapidOCR mất dấu tiếng Việt.
- **Chưa chấp nhận / còn mở:** nhãn dòng bảng của Tesseract Fast; lỗi dấu ở tiêu đề/nhãn in đậm rộng hơn
  cụm `BẢNG KÊ` (holdout: 4/13 tài liệu với Best, 3/13 với Fast; critical vẫn 13/13); EasyOCR; SSRF qua
  redirect; `offline_verified` ngoài Docker; benchmark tài liệu thật.

### 8.4 Trước merge và trước production

Xem `OCR_PHASE8D_REPORT.md` §15. Tóm tắt: merge cần chủ dự án xác nhận D-27 và hai điểm còn mở về Tesseract;
production cần thêm biện pháp SSRF được duyệt, benchmark tài liệu thật, backup và quy trình vận hành.

## 9. Phase 9A — cổng bảo mật cuối và Release Candidate

Báo cáo: [OCR_PHASE9A_REPORT.md](OCR_PHASE9A_REPORT.md). Quyết định: D-29.

### 9.1 Phạm vi phát hành đã chốt

- **Engine:** Tesseract Vietnamese Best (khuyến nghị), RapidOCR (mặc định, tương thích ngược). Tesseract Fast
  và EasyOCR vẫn có trong OCR Engine Manager nhưng chưa đạt chuẩn phát hành nghiệp vụ / ở mức thử nghiệm.
- **Ngoại lệ duy nhất được chấp nhận:** KL-1 — mất dấu ở tiêu đề in đậm `BẢNG KÊ CHI TIẾT KHOẢN MỤC MẪU`.
  Không mở rộng sang số tiền, ngày, số hiệu, nhãn dòng bảng hay nội dung nghiệp vụ.
- **Cấu hình bảo mật:** `OPEN_NOTEBOOK_ENABLE_URL_INGESTION` **tắt** (mặc định). Bản phát hành cho môi trường
  ngân hàng chỉ được đánh giá ở cấu hình này.

### 9.2 Đối chiếu điều kiện

| Điều kiện | Kết quả Phase 9A |
|---|---|
| §3.1 gốc: lộ trình nhanh `FAIL == 0` | **KHÔNG ĐẠT theo đúng chữ** — 6 PASS / 3 FAIL (giới hạn đã ghi nhận) |
| §3.1 theo tiêu chí có điều kiện (Tesseract Best) | **ĐẠT** — 7/7 (4 PASS + 3 PASS kèm KL-1), critical 7/7 |
| §3.1 §5 Docker lộ trình nhanh | **ĐẠT** — 42 PASS / 0 FAIL |
| §3.2 commands / job guard | **ĐẠT** — không commit nào đụng tới kể từ `45e2254`; bảo mật trực tiếp 16/16 |
| §3.3 10 lỗi backend có sẵn | **ĐẠT** — 1288 passed / 10 failed, cùng 10 lỗi của `main` |
| Rủi ro SSRF qua redirect (D-28) | **Giảm thiểu khi URL ingestion tắt** (mặc định); **còn tồn tại khi bật**. Không tuyên bố đã sửa triệt để |
| Review độc lập cuối `45e2254..HEAD` | **ĐẠT** — 0 High, 0 Medium; 9 Low (6 đã sửa, 2 ghi nhận, 1 có sẵn ngoài phạm vi) |
| §4.2 Benchmark tài liệu thật | **CHƯA** — có công cụ và hướng dẫn; chủ dự án thực hiện tại chỗ |
| §4.3 Backup, restore, môi trường đích | **CHƯA** — chỉ có kế hoạch và checklist |

### 9.3 Thay đổi hành vi khi nâng cấp

1. Thêm nguồn từ URL (kể cả YouTube) **bị tắt** cho tới khi đặt `OPEN_NOTEBOOK_ENABLE_URL_INGESTION=true`.
   Nguồn URL cũ vẫn đọc được; không xử lý lại được.
2. Kết quả readiness cũ hết hiệu lực: chạy lại "Chuẩn bị" một lần.
3. `POST /api/commands/jobs` luôn bị từ chối (từ Phase 8A).

### 9.4 Tài liệu phát hành

`OCR_PRODUCTION_DEPLOYMENT_PLAN.md`, `OCR_PRODUCTION_CHECKLIST.md`, `OCR_REAL_DOCUMENT_BENCHMARK.md`,
`OCR_ONLINE_PREPARATION.md`, `OCR_ROLLBACK.md`, `CHANGELOG.md`.

## 10. Phase 9B — nghiệm thu phát hành cuối

Báo cáo: [OCR_PHASE9B_REPORT.md](OCR_PHASE9B_REPORT.md). Quyết định: D-30, D-31, D-32. Mã được nghiệm thu: `6f6b424`.

### 10.1 Đối chiếu cổng merge

| # | Điều kiện | Kết quả |
|---|---|---|
| 1 | Đã review toàn bộ diff | **ĐẠT** — 3 agent độc lập trên `5e04227..76b63b5`, 1 agent rà lại phần sửa |
| 2 | Không còn lỗi Cao / Trung bình chưa xử lý | **ĐẠT với một điểm cần chủ dự án quyết định**: mọi lỗi Cao đã sửa; Trung bình đã sửa hoặc giảm thiểu; còn các route podcast mở cho mọi tài khoản (có sẵn, có thể là chủ ý sản phẩm) |
| 3 | Không có regression mới | **ĐẠT** — backend cùng 10 lỗi có sẵn; frontend 411/411 |
| 4 | Tesseract Best đạt tiêu chí có điều kiện | **ĐẠT** — 7/7, critical 7/7 (bộ gốc vẫn 6/9) |
| 5 | Docker acceptance không có lỗi mới | **ĐẠT** — quick 42/0; full 74/1 và không-Tesseract 50/1 (FAIL đã biết của EasyOCR) |
| 6 | RapidOCR persistent đạt | **ĐẠT** — 42/0 (giới hạn recreate offline: D-32) |
| 7 | Image không Tesseract đạt về runtime | **ĐẠT** |
| 8 | URL ingestion tắt được nghiệm thu | **ĐẠT** — 43 test + 7/7 trực tiếp + review săn bypass |
| 9 | GitHub Actions không gây triển khai ngoài ý muốn | **ĐẠT** — không workflow triển khai; merge không kích hoạt build / publish |
| 10 | Required checks và branch protection | **ĐẠT** — không có quy tắc nào được cấu hình; `docs-links.yml` chạy trên PR |
| 11 | Không conflict | **ĐẠT** — RC đi trước nhánh chính thức, không đi sau |
| 12 | Branch RC kế thừa nhánh chính thức | **ĐẠT** — merge-base `5e04227` |
| 13 | Không có dữ liệu nhạy cảm trong commit | **ĐẠT** — quét mẫu bí mật và file lớn trên toàn diff |

### 10.2 Thay đổi hành vi bổ sung so với §9.3

4. Chỉ quản trị viên được ghi / kiểm tra credential và model, quản lý transformation, embed / dựng lại embedding,
   xóa insight; người không phải quản trị viên không tạo được nguồn từ file đã có trên máy chủ (D-31).
5. Lần khởi động đầu của image mới cần Internet để cài Docling đúng phiên bản đã khóa.

### 10.3 Trước production

Benchmark tài liệu thật (hoặc phạm vi thí điểm phi nghiệp vụ được phê duyệt), phê duyệt kế hoạch
[OCR_PRODUCTION_DEPLOYMENT_PLAN.md](OCR_PRODUCTION_DEPLOYMENT_PLAN.md), sao lưu lạnh và kiểm tra restore, biện pháp
kiểm soát khi rollback. Hiện trạng production đáng chú ý: container đang chạy không có Docling (kế hoạch §1.1).
