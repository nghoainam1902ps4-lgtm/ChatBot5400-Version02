# Release Candidate — OCR Engine Manager (Phase 0 → 8C)

- **Branch:** `claude/friendly-mendel-a2b6m5`.
- **Gốc so sánh:** `5e04227` (trước tính năng) và `e32eae8` (Phase 7).
- **Không merge main, không triển khai production** trong phiên phát triển.

Trạng thái (sau Phase 8C, 2026-11-13): **CHỜ QUYẾT ĐỊNH CỦA CHỦ DỰ ÁN — xem §7.** Lỗi chất lượng chính
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

