# Phase 12D9 — Checklist nghiệm thu Local (Windows) trên commit cuối

Bổ sung và **không thay thế** [PHASE12D8_LOCAL_GATE_CHECKLIST.md](PHASE12D8_LOCAL_GATE_CHECKLIST.md) (G-01 … G-12, vẫn
hiệu lực), [PHASE12D7_LOCAL_ACCEPTANCE_CHECKLIST.md](PHASE12D7_LOCAL_ACCEPTANCE_CHECKLIST.md) và
[PHASE12D5_LOCAL_ACCEPTANCE_CHECKLIST.md](PHASE12D5_LOCAL_ACCEPTANCE_CHECKLIST.md).

## 0. Quy tắc

* **Một commit:** mọi cổng chạy trên **cùng một commit cuối** của 12D9 (đầu nhánh `feature/legal-document-normalization`
  trong PR #50). Ghi commit ở đầu biên bản. Cổng chạy trên commit khác ⇒ chạy lại.
* **Cloud ≠ Windows.** Cột "Cloud" chỉ nói Cloud đã kiểm gì bằng dữ liệu tổng hợp. Không cổng nào được đóng từ Cloud;
  không mô phỏng `sys.platform`.
* Stack thử `chatbot5400-phase12-test`, chỉ loopback; không database / credential / dữ liệu production; không xóa volume,
  không recreate DB, không pull image ngoài dự kiến (`--pull never`).
* **Chỉ số liệu ra khỏi máy:** loại token, số lượng, trang, bbox, loại lỗi, thống kê confidence, trạng thái, mã thoát.
  PDF nghiệp vụ, kết quả OCR, thư mục `*.evidence`, model Agri ở lại máy Local; không upload, không commit, không dán chữ
  tài liệu vào báo cáo hay vào cửa sổ chat với AI. Mặc định mọi công cụ 12D9 chỉ in số đếm.
* Ghi **Đạt / Không đạt / Không chạy** từng mục; kết quả khác kỳ vọng ghi nguyên trạng, không sửa tiêu chí.

Biến dùng trong PowerShell (chạy ở thư mục gốc repo; lệnh Compose là mảng tường minh như E0-05):

```powershell
$dc = @('compose', '-p', 'chatbot5400-phase12-test', '-f', 'deploy\phase12-test\docker-compose.yml')
$root = (Resolve-Path 'deploy\phase12-test').Path
$new = 'chatbot5400:phase12-test'          # image build từ commit cuối (G-01)
$old = '<ID image v1.2.0 đã ghi ở W-12D7-00a>'
```

## 1. Chuẩn bị (G-01) và trạng thái bản vá

| # | Việc | Kỳ vọng | Cloud |
|---|---|---|---|
| D9-00a | checkout commit cuối; `.\scripts\windows\phase12-test.ps1 build`; `restart-app` | build đạt (có bước tự kiểm cổng); ghi image ID | — |
| D9-00b | `.\scripts\windows\phase12-test.ps1 status` | có 3 dòng: `docling Tesseract patches (E0-07 TSV text, E2-04 failed OCR region): ready (applied at conversion time)`, `docling text preservation (D8-03 hyphens, D8-02 table / picture footnotes): ready (applied at conversion time)`, dòng cuối `orientation gate: active (min confidence 2.0)` | đạt (container Cloud) |
| D9-00c | G-01a của 12D8 (làm hỏng bước tự kiểm trong bản sao Dockerfile) | `docker build` **thất bại** | test tĩnh đạt (D8-ORI-05) |

## 2. Bảo toàn nội dung

Dùng công cụ xuất Standard **cùng lần chuyển đổi** (D8-STD-03). Hàm chạy một container một lần, cùng cờ cho hai phía,
không mạng, dữ liệu ứng dụng chỉ đọc:

```powershell
$tool = (Resolve-Path 'scripts\ocr\phase12d9_standard_export.py').Path
function Export-Standard([string]$Image, [string]$Engine, [string]$Out, [string[]]$Extra = @()) {
    $a = @('run', '--rm', '--pull', 'never', '--network', 'none',
        '-e', 'OPEN_NOTEBOOK_ENABLE_DOCLING=true', '-e', 'OPEN_NOTEBOOK_ENABLE_OCR_TESSERACT=true',
        '-e', 'OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR=true', '-e', 'OCR_RAPIDOCR_PERSISTENT=true',
        '-e', 'OCR_OFFLINE=true', '-e', 'OCR_AUTO_FULL_PAGE_ON_WATERMARK=false', '-e', 'OCR_AGRI_WITH_ENGLISH=false',
        '-v', "${root}\notebook_data:/app/data:ro", '-v', "${root}\import:/import:ro",
        '-v', "${root}\diagnostics:/phase12-out",
        '-v', "${tool}:/app/scripts/ocr/phase12d9_standard_export.py:ro",
        '--entrypoint', '/app/.venv/bin/python', $Image, '/app/scripts/ocr/phase12d9_standard_export.py',
        '--input', '/import/pdf22', '--engine', $Engine, '--out', "/phase12-out/$Out") + $Extra
    docker @a
    "exit code: $LASTEXITCODE"
}
Export-Standard $old 'tesseract_best' 'std-v120-best'
Export-Standard $new 'tesseract_best' 'std-new-best'
```

22 PDF đặt ở `deploy\phase12-test\import\pdf22\`. Lặp cho `tesseract_fast`, `tesseract_agri` (`@('--custom-version','v1')`
và `v2`), `rapidocr`, `easyocr`; mỗi lần một thư mục `--out` **mới**. Nếu container dừng vì ghi vào `/app/data`
(chỉ đọc): chép `notebook_data` sang thư mục tạm và mount bản chép — không bao giờ mount bản gốc read-write.

| # | Việc | Kỳ vọng | Cloud |
|---|---|---|---|
| **G-H1** gạch nối đầu-cuối (D8-03) | engine Tesseract: đọc tổng `tsv_hyphen_words` / `tsv_hyphen_words_in_output` trong `manifest.json` của phía mới: `$m = Get-Content "$root\diagnostics\std-new-best\manifest.json" -Raw \| ConvertFrom-Json; $m.documents \| Measure-Object tsv_hyphen_words, tsv_hyphen_words_in_output -Sum` | hai tổng **bằng nhau** ở mọi engine Tesseract; nhỏ hơn ⇒ mở tài liệu đó **cục bộ**, ghi số chỗ thiếu | đạt (Tesseract thật, tổng hợp) |
| G-H1b | RapidOCR, EasyOCR, PDF có lớp chữ | mọi khác biệt so với v1.2.0 thuộc `expected hyphen fix` (G-04); không chỗ nào mất `-` | đạt (lớp chữ docling-parse, tổng hợp) |
| G-H1c | Legal trên cùng tài liệu (`compare`) | `upstream_dehyphenation` chỉ còn ở chỗ không có bằng chứng; số hiệu dạng `05/2024/TT-BNNPTNT` giữ `-` | đạt (tổng hợp) |
| **G-H2** footnote gắn kèm (D8-02) | PDF có bảng / ảnh với ghi chú ngay dưới | Standard **và** Legal có ghi chú, **một lần**, ngay sau bảng / ảnh; v1.2.0 thiếu ⇒ hunk `expected attached footnote fix` | đạt (tổng hợp) |
| **G-H3** khổ trang khác nhau (D8-01) | PDF ghép nhiều văn bản, scan tự cắt lề, phụ lục khổ ngang; Legal | mỗi `upstream_merge_undone` trong `09_legal_report.json`: phần tách đứng **ngay sau** phần đầu | đạt (fixture) |
| **G-H4** hai cột (D8-01) | PDF trang hai cột; Legal | như G-H3; ghi riêng số cặp đảo "do Docling" (Standard cũng đảo) và "do Legal" | đạt: Legal không thêm cặp đảo nào (benchmark 92 fixture) |
| **G-H5** bằng chứng mức crop (G-03a) | với ≥ 3 tài liệu: thư mục `<tên>.evidence\tesseract\` có TSV thô của **từng lần gọi** + sidecar (trang, vùng, bbox, SHA-256 model) | G-04 không có `not verified` vì thiếu bằng chứng | đạt (tổng hợp) |
| G-03 (giữ) | `docling_patches.status()`, 22 PDF Best / Agri v1 / v2 | như 12D8 G-03; `0001` không thành `1.0` | Windows 12E2: 383 / 383 |

## 3. E2-04 — vùng OCR lỗi (P1)

| # | Việc | Kỳ vọng | Cloud |
|---|---|---|---|
| **E2-G1** lỗi thật của môi trường | 3 tài liệu đã mất chữ ở 12E2 (fixture Best 49 token, fixture Agri v2 100 token, D22 1 220 token), Source **mới**, cùng engine, thư mục dữ liệu trên **cùng** mount như 12E2 | mỗi tài liệu: hoặc `completed` với **đủ** token (đếm như 12E2), hoặc `failed` với "Nhận dạng tài liệu chưa hoàn tất do một vùng OCR gặp lỗi." — **không bao giờ** `completed` thiếu token. Ghi số dòng `Tesseract recognition failed` và category / exit code của chúng (dòng log không có chữ, không có stderr) | không có (lỗi là của môi trường Windows) |

Các mục còn lại dùng công cụ tiêm lỗi **chỉ của stack thử** (`scripts/ocr/phase12d9_tesseract_fault.sh`, đứng trước
binary `tesseract` thật; không file điều khiển ⇒ không đổi gì):

```powershell
Add-Content deploy\phase12-test\.env 'PHASE12_TESSERACT_CMD=/app/scripts/ocr/phase12d9_tesseract_fault.sh'
.\scripts\windows\phase12-test.ps1 restart-app
New-Item -ItemType Directory -Force deploy\phase12-test\diagnostics\fault | Out-Null
.\scripts\windows\phase12-test.ps1 status     # vẫn 3 dòng "ready" / "active" như D9-00b
```

| # | Việc | Kỳ vọng | Cloud |
|---|---|---|---|
| **E2-G2** lỗi tạm thời, thử lại thành công | xuất một fixture 2 lần trong container đang chạy: `docker @dc exec -T open_notebook /app/.venv/bin/python scripts/ocr/phase12d9_standard_export.py --input /import/e2 --engine tesseract_best --out /phase12-out/e2-a`; tạo `diagnostics\fault\fail-once`; chạy lại với `--out /phase12-out/e2-b`; rồi tạo lại `fail-once` và tải fixture lên làm Source mới | `output_sha256` của hai manifest **bằng nhau**; log có dòng `… attempt 1 of 3 … retrying the same crop` (đúng 1 dòng nếu môi trường không tự sinh lỗi thật); file `fail-once` đã biến mất; Source `completed`, nội dung đầy đủ | đạt (pipeline thật + Source + SurrealDB thật) |
| **E2-G3** thử lại vẫn lỗi, Source mới | tạo `fail-always`; tải một fixture lên làm Source mới | Source `failed`; thông báo có "Nhận dạng tài liệu chưa hoàn tất…" và "Tài liệu chưa được đưa vào kho tri thức."; không nội dung, không embedding (tìm một từ của fixture: không ra) | đạt |
| **E2-G4** không ghi đè Source cũ | giữ `fail-always`; chạy lại xử lý một Source **đã hoàn tất và đã embed** (nút retry / reprocess, hoặc `POST /api/sources/{id}/retry` với quyền admin) | `failed`; thông báo có "Nội dung cũ của tài liệu vẫn được giữ nguyên."; nội dung và số chunk embedding **không đổi** | đạt |
| **E2-G5** OSD lỗi một mình | xóa `fail-always`; tạo `fail-osd`; tải fixture lên | Source `completed`, nội dung đầy đủ (OSD lỗi không làm mất vùng khi nhận dạng thành công); log OSD ghi `[stderr withheld: N bytes, …]` | đạt |
| **E2-G6** không lộ stderr / chữ | `docker @dc logs open_notebook \| Select-String 'cb5400 injected'` | **0 dòng** (stderr của công cụ tiêm lỗi không bao giờ vào log hay giao diện) | đạt |
| E2-G9 tắt | xóa các file trong `diagnostics\fault`; xóa dòng `PHASE12_TESSERACT_CMD` khỏi `.env`; `restart-app`; `status` | như D9-00b | — |

## 4. E2-01 / E2-02 — chỉ chẩn đoán (NEEDS LOCAL EVIDENCE)

| # | Việc | Kỳ vọng | Cloud |
|---|---|---|---|
| **E2-G7** token ngắn | `docker @dc exec -T open_notebook /app/.venv/bin/python scripts/ocr/phase12d9_crop_diagnose.py benchmark --lang best/vie --tessdata /app/data/ocr/models/tesseract --out /phase12-out/e2-01-best`; lặp `fast/vie`, `custom/agri/v1/vie_agri`, `custom/agri/v2/vie_agri`; rồi `crops /phase12-out/e2-01-crops …` với 15 crop của 12E2 | ghi bảng đúng / rỗng / nhận sai / chèn chữ giả theo PSM 3 / 6 / 7 và luật fallback thử nghiệm. **Không đổi PSM, không bật fallback** — số liệu cho quyết định sau | đạt trên tổng hợp (PSM 7 chèn chữ giả 5 / 6 crop không chữ) |
| **E2-G8** 11 cụm nhiễu | `crops /phase12-out/e2-02-crops` với ảnh crop của 11 cụm (`--with-text` chỉ khi cần, file quyền chủ sở hữu) | ghi kích thước, dpi, độ tương phản, mực chạm mép, số từ / confidence theo PSM. **Không** đổi Layout Heron, TableFormer, ngưỡng OSD; không xóa theo confidence | công cụ đạt trên tổng hợp |

## 5. Cổng Standard expected-diff (G-04) — mã thoát

```powershell
docker run --rm --pull never --network none -v "${root}\diagnostics:/phase12-out" --entrypoint /app/.venv/bin/python $new `
    /app/scripts/ocr/phase12_standard_diff.py --before /phase12-out/std-v120-best --after /phase12-out/std-new-best `
    --out /phase12-out/std-diff-best
"exit code: $LASTEXITCODE"
```

| # | Việc | Kỳ vọng | Cloud |
|---|---|---|---|
| **G-04-EXIT** | mỗi engine | mã thoát **0**; console chỉ in `{"summary": …, "run_problems": 0}`. 1 = hồi quy, 2 = chưa kiểm, 3 = run không chứng minh gì — ghi lại, không chấp nhận | đạt (tổng hợp, 5 đột biến bị bắt) |
| G-04a / 04b (giữ) | `fc /b` từng cặp `unchanged`; đếm tài liệu hai phía | giống từng byte; số tài liệu bằng nhau | — |
| G-04c (giữ) | mỗi hunk được chấp nhận | lớp TSV / gạch nối / footnote có bằng chứng; hunk do cổng hướng xoay là `not verified` (chưa có công cụ ghi bằng chứng hướng xoay) ⇒ xem tay với ảnh crop | — |
| G-04-MIX (E2-03) | fixture tổng hợp có hai nguyên nhân trong một hunk | cả hai lớp được ghi, mã 0; một phần không chứng minh ⇒ mã 2 | đạt |

## 6. Gói offline và đường production

| # | Việc | Kỳ vọng | Cloud |
|---|---|---|---|
| **G-07a** PowerShell không có `uv` (D8-OFF-11) | máy có Python, **không** có `uv`: `build-package.ps1` trên PS 5.1 và PS 7, đường dẫn có dấu cách | build đạt, `readiness: READY`; không lỗi lệnh `p` | chỉ kiểm tĩnh |
| G-07c (D8-OFF-03 / 04) | ngắt build ở các bước khác nhau rồi build lại | thư mục `dist\offline` không có gói thiếu `.sha256`, không file `*.partial-*` / `*.previous-*` còn sót sau lần build kế; cặp gói + hash luôn khớp (`Get-FileHash`) | đạt (POSIX) |
| G-07d (D8-OFF-09) | `--out` trên ổ mạng / exFAT | lỗi nói thư mục không hỗ trợ khóa, **không** nói "đang bị tiến trình PID giữ" | đạt (POSIX) |
| G-08a (D8-OFF-12) | `phase12-test.ps1 check` / `up` khi Docker Desktop tắt, PS 5.1 | thông báo "Docker is not running" rõ ràng, không `NativeCommandError` | chỉ kiểm tĩnh |
| **G-09-TRUST** tin cậy gói | Ubuntu thử: `verify-package.sh` (chữ ký); §3.4 của quy trình thủ công; thay một file rồi sinh lại `SHA256SUMS` | chữ ký đạt; `manifest: every file OK`; file bị thay ⇒ **dừng** | đạt (lệnh đúng như tài liệu) |
| **G-09-RB** rollback thủ công | §10: 10.1 mã nguồn về trước, 10.2 ứng dụng trên image cũ | sau rollback: commit, image và container đang chạy đều là bản cũ; ID container DB không đổi | đạt (Docker giả) |
| G-09 (giữ) | W-FB-*, W-INT-*, G-09a … e của 12D8 | như đã ghi | một phần |
| G-12 (giữ) | updater | EXPERIMENTAL trong `--help`, log mỗi lần chạy, release notes; không lệnh updater nào trong đường production | đạt |

## 7. Hồi quy tự động trên máy có đủ model (G-06)

`uv run pytest tests/ -q -p no:cacheprovider -rxXs` (với bảng mã tiktoken thật): 10 lỗi cũ cùng tên (9 ×
`test_models_api.py::TestModelsProviderAvailability`, `test_domain.py::TestContentSettings::test_content_settings_defaults`),
0 xpassed; `tests/review_phase12d8` 0 failed; `tests/test_phase12d9_*` đạt (có `tesseract` với `vie` + `osd`, DejaVu).
`OCR_FULL_PIPELINE=1`: pipeline OCR đầy đủ với Layout Heron / TableFormer.

## 8. Điều kiện chuyển sang phát hành

Mọi mục trên **Đạt** trên cùng một commit; E2-G1 không có Source `completed` thiếu nội dung; G-04 mã thoát 0 ở mọi engine;
không finding P0 / P1 mới. Cho tới khi đó: READY FOR RELEASE = NO, READY FOR PRODUCTION = NO. Không merge, không đổi
VERSION, không tag, không kết nối production.
