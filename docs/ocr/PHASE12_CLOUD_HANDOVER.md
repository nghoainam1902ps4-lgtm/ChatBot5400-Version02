# Phase 12 — Báo cáo bàn giao từ Claude Code Cloud

> **CẬP NHẬT (Phase 12D3).** Bàn giao này thuộc về Phase 12 trước audit độc lập. Bàn giao hiện hành:
> [../review/PHASE12D3_HANDOVER.md](../review/PHASE12D3_HANDOVER.md). Các kết luận "0 từ bị mất" và số test ở đây đã
> bị thay thế.

Legal Document OCR & Layout Normalization + Offline Update Package. Phiên làm việc Cloud: không truy cập production,
không có model Agri, không có tài liệu nội bộ, không có Docker daemon, Hugging Face bị chặn.

## 1. Baseline

| Mục | Giá trị kiểm tra |
|---|---|
| Repository | `nghoainam1902ps4-lgtm/ChatBot5400-Version02` |
| Nhánh mặc định | `claude/practical-wozniak-9s1t6z` (không đổi) |
| Release / tag | `v1.2.0` → `f2fdf2714a7c0b5b196132f71cfc091928befc06` (đã xác minh; không tag nào bị sửa) |
| `VERSION` | `1.2.0` (chưa đổi — đổi ở commit phát hành RC sau nghiệm thu) |
| Phụ thuộc (uv.lock + cài thực tế) | Open Notebook 1.14.0, content-core 2.0.7, docling 2.129.0, docling-core 2.96.0, docling-ibm-models 4.0.3 |
| Backend v1.2.0 trên Cloud | **1789 pass / 13 fail / 64 skip** (1866). So với tham chiếu 1792/10/64: 10 lỗi có sẵn giống hệt (1 `test_domain` default `docling`, 9 `test_models_api`) + **3 `test_chunking` cần tải tiktoken từ host bị chặn trên Cloud** (môi trường, không phải mã) |
| Frontend v1.2.0 | **423 pass** |
| OCR (`tests/test_ocr_*.py`, worktree v1.2.0) | **633 pass / 64 skip** (tham chiếu 640: chênh do Tesseract fast/best không sẵn sàng trong sandbox) |

## 2. Nguyên nhân gốc (tóm tắt — [PHASE12A_ROOT_CAUSE_REPORT.md](PHASE12A_ROOT_CAUSE_REPORT.md))

- `<!-- image -->`: placeholder mặc định của serializer Markdown docling-core cho **mọi** ảnh (chữ ký, con dấu, logo);
  frontend hiển thị HTML comment như chữ (đúng về an toàn).
- Số trang giữa câu: Layout gán nhãn TEXT thay vì PAGE_FOOTER ⇒ không vào lớp furniture.
- Câu bị cắt qua trang: cơ chế ghép của Docling chỉ khớp chữ ASCII (`số`, `ảnh` không khớp), chỉ TEXT→TEXT (khoản là
  LIST_ITEM), bị chặn bởi số trang nhãn TEXT.
- Mất / sai số khoản: Docling không nhận marker `đ)`, `a.1)` ⇒ serializer chèn số vị trí (`5. đ)`); cú pháp danh sách
  Markdown bị CommonMark/trình duyệt đánh lại số (`5. 7. 13.` hiển thị 5, 6, 7); CSS ẩn gạch đầu dòng.
- Chữ OCR trong vùng ảnh bị bỏ khi xuất (`traverse_pictures=False`) — một nguyên nhân của "thiếu chữ".
- "Thiếu từ cuối trang" trên tài liệu thật: **chưa kết luận** (cần diagnostic trên Local).

## 3. Kiến trúc đã chọn

Normalizer thuần chạy trên **bản sao `DoclingDocument`** của PDF, sau Docling, trước khi lưu Source; dùng nhãn, lớp
furniture, marker, provenance/bbox của Docling; serializer chính thức của docling-core với 3 lớp con nhỏ. Opt-in hai
lớp (cổng `OCR_LEGAL_NORMALIZATION_ENABLED` + lựa chọn admin, mặc định Standard), không migration, lỗi ⇒ fallback
Standard. Gói offline: image dựng sẵn + git bundle + manifest/SHA256SUMS/chữ ký; công cụ Python thư viện chuẩn.
Quyết định: D-34, D-35 ([DECISIONS.md](DECISIONS.md)).

## 4. File thay đổi

Backend: `open_notebook/ocr/legal_normalizer.py` (mới), `ocr/options.py`, `ocr/docling_extract.py`,
`domain/content_settings.py`, `graphs/source.py`, `api/models.py`, `api/ocr_service.py`.
Frontend: `settings/components/OcrEngineManager.tsx` (+ test), `lib/types/api.ts`, `lib/api/ocr.ts`, locales `vi-VN`,
`en-US`, `components/ui/markdown-renderer.test.tsx`.
Công cụ: `scripts/ocr/phase12_{metrics,diagnose,compare,benchmark}.py`, `generate_phase12_fixtures.py`,
`phase12-test.sh`, `scripts/windows/phase12-test.ps1`, `scripts/offline/*`, `deploy/phase12-test/*`, `Dockerfile`
(build arg `OCR_PREINSTALL_RUNTIMES`, mặc định tắt), `.dockerignore`.
Test: `tests/legal_harness.py`, `tests/fixtures/legal/legal_fixtures.py`, `tests/test_ocr_legal_normalizer.py`,
`tests/test_ocr_legal_pipeline.py`, `tests/test_ocr_phase12_scripts.py`, `tests/test_offline_package.py`.
Tài liệu: `docs/ocr/PHASE12*.md`, `docs/ocr/phase12/benchmark_synthetic.json`, `docs/deployment/OFFLINE_UPDATE_*.md`,
`docs/ocr/OCR_RELEASE_NOTES_V1.3.0_RC1.md` (nháp), `CHANGELOG.md` (mục Unreleased), `docs/ocr/DECISIONS.md`.
Không đổi: `uv.lock`, `pyproject.toml`, `package*.json`, migration, Docling/Heron/TableFormer/engine/model/RAG.

## 5. Tính năng đã thực hiện

1. Chế độ **Văn bản pháp lý** (PDF): bỏ placeholder ảnh không mang thông tin; giữ ảnh lớn không chữ + cảnh báo; lấy
   lại chữ OCR trong vùng ảnh; số trang / header-footer lặp → furniture khi đủ bằng chứng; ghép đoạn liên trang bảo
   thủ (Unicode); marker gốc dạng chữ có escape, không chèn số; bảng giữ nguyên; giới hạn tài nguyên; fallback.
2. Định tuyến: bật Legal ⇒ PDF đi qua lớp Docling của ChatBot5400 kể cả RapidOCR mặc định và URL PDF; ảnh/định dạng
   khác không đổi.
3. API/UI quản trị: lựa chọn + trạng thái hiệu lực + cổng + phiên bản normalizer; API từ chối Legal khi cổng tắt.
4. Diagnostic từng tầng + so sánh ba chế độ một lệnh + sinh fixture PDF + benchmark.
5. Stack thử nghiệm Windows cô lập (8504/5057) + script PowerShell/Bash.
6. Công cụ gói cập nhật offline: build / inventory / verify / preflight / update / finish / rollback / health / status.

## 6. Kết quả regression (Cloud)

| Bộ | Kết quả | Ghi chú |
|---|---|---|
| Backend toàn bộ | **2122 pass / 13 fail / 65 skip** | 13 lỗi giống hệt từng tên baseline; +333 pass; +1 skip (môi trường) |
| OCR (`test_ocr_*`) | **936 pass / 65 skip** | 633 test cũ vẫn pass + 303 mới |
| Backend mới Phase 12 | 334 test (269 normalizer + 28 pipeline + 7 scripts + 30 offline) — tất cả pass (1 skip môi trường khi chạy cả bộ) | |
| Frontend | **430 pass** (423 + 7 mới), `tsc` 0 lỗi, lint 0 lỗi (7 cảnh báo có sẵn) | |
| mypy (file sửa) | sạch | |
| ruff / shellcheck | sạch | |

Chi tiết: [PHASE12D_TEST_REPORT.md](PHASE12D_TEST_REPORT.md).

## 7. Quality benchmark (24 fixture tổng hợp — [PHASE12D_QUALITY_BENCHMARK.md](PHASE12D_QUALITY_BENCHMARK.md))

Standard → Legal: CER 0,147 → 0,018; marker đúng 14/33 → 33/33; mục bị đánh lại số 3 → 0; artifact phải vắng 0/23 →
23/23; trường nghiệp vụ 23/24 → 24/24; ghép cần có 0/3 → 3/3, ghép sai 0, **từ hợp lệ bị mất 0**, bảng giống hệt.
Direct Tesseract (5.3.4, `vie`): CER 0,10 (tham chiếu nhận dạng, tách biệt). Chi phí: ~2,5 ms/trang.

## 8. Security review ([PHASE12D_SECURITY_REVIEW.md](PHASE12D_SECURITY_REVIEW.md))

Không có HIGH/CRITICAL mới. 4 phát hiện thấp/hiệu năng/dữ liệu đã sửa trong phase.

## 9. Giới hạn của Cloud

Không Docker daemon (không build image, không chạy stack, không `docker load`); Hugging Face bị chặn (không Layout
Heron/TableFormer ⇒ không chạy pipeline PDF đầy đủ); không PowerShell; host tiktoken bị chặn (3 test chunking);
Tesseract 5.3.4 thay vì 5.5.0; không có Agri và tài liệu thật (đúng yêu cầu).

## 10. VERIFIED / PARTIAL / NOT VERIFIED

| Hạng mục | Trạng thái |
|---|---|
| Nguyên nhân cấu trúc (placeholder, số trang, ghép, marker, đánh lại số, chữ trong ảnh) | VERIFIED (mã upstream + test) |
| Nguyên nhân "thiếu từ cuối trang" trên tài liệu thật | NOT VERIFIED |
| Normalizer trên DoclingDocument từ ReadingOrderModel thật | VERIFIED (fixture) |
| Định tuyến, lưu Source, embedding đọc cùng nội dung, API, UI | MOCK VERIFIED |
| Pipeline đầy đủ Heron/TableFormer/engine/Agri + Legal | NOT VERIFIED |
| Standard không đổi (byte-identical) | VERIFIED (unit) / REAL PIPELINE: NOT VERIFIED |
| Offline tooling (logic, an toàn archive, chữ ký thật, luồng update/rollback) | MOCK VERIFIED |
| Gói offline thật, docker load, nâng cấp/rollback thật, chặn mạng thật | NOT BUILT / NOT VERIFIED |
| Script PowerShell | NOT EXECUTED |

## 11. Checkout trên Windows

```powershell
git clone https://github.com/nghoainam1902ps4-lgtm/ChatBot5400-Version02.git
cd ChatBot5400-Version02
git fetch origin
git checkout claude/sweet-feynman-92jg8j
```

## 12–15. Stack thử nghiệm, Agri, diagnostic, so sánh OCR

Theo [PHASE12E_WINDOWS_LOCAL_TEST_GUIDE.md](PHASE12E_WINDOWS_LOCAL_TEST_GUIDE.md). Tóm tắt:

```powershell
.\scripts\windows\phase12-test.ps1 check
```

```powershell
.\scripts\windows\phase12-test.ps1 init-env
```

```powershell
.\scripts\windows\phase12-test.ps1 build
```

```powershell
.\scripts\windows\phase12-test.ps1 up
```

```powershell
.\scripts\windows\phase12-test.ps1 import-agri -Model C:\duong\dan\vie_agri.traineddata -Version v1
```

```powershell
.\scripts\windows\phase12-test.ps1 activate-agri -Version v1
```

```powershell
.\scripts\windows\phase12-test.ps1 compare -Pdf . -Engine tesseract_agri
```

```powershell
.\scripts\windows\phase12-test.ps1 diagnose -Pdf qd-mau.pdf -Engine tesseract_agri
```

## 16. Tạo gói cập nhật offline

[../deployment/OFFLINE_UPDATE_WINDOWS_BUILD.md](../deployment/OFFLINE_UPDATE_WINDOWS_BUILD.md). Trước commit RC dùng
phiên bản thử nghiệm:

```powershell
.\scripts\offline\build-package.ps1 -Version 1.2.0-phase12.1
```

## 17. Nghiệm thu gói offline

[../deployment/OFFLINE_UPDATE_UBUNTU_GUIDE.md](../deployment/OFFLINE_UPDATE_UBUNTU_GUIDE.md) §8 trên Ubuntu/VM thử
nghiệm có chặn mạng thật: verify → preflight → update → nghiệm thu OCR → kiểm tra dữ liệu → rollback → update lại →
các ca lỗi (gói hỏng, sai kiến trúc, gián đoạn, thiếu đĩa, manifest/chữ ký sai). Ghi biên bản cục bộ.

## 18. Rollback

[../deployment/OFFLINE_UPDATE_ROLLBACK.md](../deployment/OFFLINE_UPDATE_ROLLBACK.md): Legal→Standard (UI hoặc
`rollback.sh legal-off` / `phase12-test.ps1 legal-gate -State off`), Agri (`rollback.sh agri`), ứng dụng
(`rollback.sh app`, không restore DB), cập nhật dang dở (`rollback.sh interrupted`).

## 19. Việc còn lại trước release 1.3.0-rc.1

1. Nghiệm thu Windows Local theo biên bản §10 của guide 12E (Agri + tài liệu thật), gồm xác định nguyên nhân "thiếu
   từ cuối trang".
2. Hiệu chỉnh ngưỡng (dải 10%, ảnh lớn 15%) nếu số đo thật đòi hỏi — kèm test hồi quy.
3. Chạy PowerShell scripts thật; build image với `OCR_PREINSTALL_RUNTIMES=true` (kiểm tra kích thước, `import docling`
   không mạng).
4. Commit phát hành RC: `VERSION`, `frontend/package.json`, `package-lock.json` → `1.3.0-rc.1`; hoàn thiện ghi chú
   phát hành; chủ dự án phê duyệt; tạo tag (không sửa tag cũ). Không GitHub Release / push image khi chưa duyệt.
5. Quyết định về khóa ký phát hành.

## 20. Việc còn lại trước triển khai production

1. Xác nhận nền tảng máy chủ (`uname -m`, `docker info`), phiên bản đang chạy 1.2.0, schema 33.
2. Thiết lập kênh tin cậy cho SHA-256 / khóa công khai; cài công cụ offline + `offline-update.conf`.
3. Quy trình backup + kiểm tra khôi phục đã phê duyệt (`BACKUP_CMD`/`BACKUP_VERIFY_CMD`).
4. Nghiệm thu gói trên stack cô lập có chặn mạng thật (§17) — **bắt buộc**.
5. Phê duyệt triển khai; lịch bảo trì. Phase 12 **không** triển khai, không đổi gì trên production.

## Commit, nhánh, PR

Nhánh: `claude/sweet-feynman-92jg8j` (nhánh phát triển của phiên). Commit cuối và Draft PR: xem phần kết của phiên
làm việc.

## Đánh giá cuối (theo bằng chứng)

| Hạng mục | Kết quả |
|---|---|
| PHASE 12A ROOT CAUSE ANALYSIS | **PARTIAL** — nguyên nhân cấu trúc xác minh bằng mã upstream + test; "thiếu từ cuối trang" và tần suất trên tài liệu thật chưa đo được (không chạy được Heron) |
| PHASE 12B DESIGN | **PASS** |
| PHASE 12C IMPLEMENTATION | **PARTIAL** — đủ phạm vi bắt buộc; chưa có lựa chọn theo tài liệu và hiển thị trạng thái chuẩn hóa trên trang Source (cần lưu metadata) |
| PHASE 12D REGRESSION | **PASS** (Cloud: không regression mới; gate cần pipeline thật để PENDING) |
| LEGAL NORMALIZATION | **PARTIAL** — VERIFIED trên DoclingDocument từ ReadingOrderModel thật; pipeline PDF thật: chưa |
| DATA PRESERVATION | **NOT VERIFIED** trên tài liệu thật (VERIFIED trên 24 fixture: 0 từ mất, 24/24 trường, bảng giống hệt) |
| OCR PIPELINE | **PARTIAL** — định tuyến + parity + 633 test OCR cũ pass; Heron/TableFormer/engine/Agri thật chưa chạy |
| WINDOWS LOCAL ACCEPTANCE | **PENDING** |
| OFFLINE UPDATE TOOLING | **PARTIAL** — MOCK VERIFIED (30 test); Docker thật, PowerShell chưa chạy |
| OFFLINE PACKAGE BUILD | **NOT BUILT** |
| OFFLINE UPGRADE AND ROLLBACK | **NOT VERIFIED** |
| READY FOR WINDOWS LOCAL TESTING | **YES** |
| READY FOR RELEASE | **NO** (chờ nghiệm thu Local, commit phát hành RC, phê duyệt) |
| READY FOR PRODUCTION DEPLOYMENT | **NO** |
| PRODUCTION | **UNCHANGED** (không có thao tác nào tới production) |
