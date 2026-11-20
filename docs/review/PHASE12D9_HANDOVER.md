# Phase 12D9 — Bàn giao: giữ nguyên văn bản upstream và xử lý blocker phát hành cuối

Nhánh `claude/jolly-pasteur-youiae` (fast-forward vào `feature/legal-document-normalization`, PR #50 — Draft). Đích review:
`4587eb7` (đầu nhánh khi review 12D8). Mốc so sánh: v1.2.0 `f2fdf27`. VERSION vẫn `1.2.0`; không merge, không tag, không
release, không kết nối production. Review 12D8 do một phiên Claude mới thực hiện (không phải Codex).

**Dừng ở đây:** Phase 12D9 chỉ sửa lỗi cần thiết, không mở phase mới, không thêm tính năng. Bước tiếp theo là nghiệm thu
Windows trên **cùng một commit cuối** ([PHASE12D9_LOCAL_ACCEPTANCE_CHECKLIST.md](PHASE12D9_LOCAL_ACCEPTANCE_CHECKLIST.md)).

## 1. Không đổi

Docling 2.129.0, docling-core 2.96.0, content-core 2.0.7, Layout Heron, TableFormer Accurate, năm engine OCR, model Agri,
Custom Model Manager, PDF Prep, Auto Full Page on Watermark, DB schema, LLM, model embedding, kiến trúc RAG. Không nâng
dependency, không engine mới, không fine-tune, không AI sửa chữ, không tự OCR lại / embed lại, không Phase 11, không mở
rộng state machine của updater. Frontend không đổi.

## 2. Commit

| Commit | Nhóm | Nội dung |
|---|---|---|
| `85ada78` | audit | nhập nguyên trạng tài liệu + test review 12D8 |
| `de55d4e` | D8-03, D8-02, D8-01 | bản vá chữ có kiểm soát (gạch nối, footnote gắn kèm); Legal 1.3.1 giữ thứ tự đọc |
| `949138a` | D8-ORI-02, D8-10 | status / readiness báo bản vá và cổng **thực sự** chạy |
| `691fac9` | E2-04 | vùng OCR lỗi: thử lại có giới hạn, rồi tài liệu bị từ chối; Source / embedding an toàn |
| `75c9455` | D8-STD-01 … 05, E2-03 | cổng Standard expected-diff v2 + công cụ xuất bằng chứng |
| `6485c14` | D8-ORI-01, 05 | chẩn đoán hướng xoay xoay như Docling, một quy ước góc, mặc định không chữ |
| `d03830d` | D8-ORC-01 … 06 | oracle bảo toàn: 6 điểm mù |
| `ff68855` | E2-01, E2-02 | chẩn đoán crop metadata-only |
| `70f7325` | D8-OFF-* | publish gói an toàn, lỗi khóa đúng, phát hiện migration, nhãn EXPERIMENTAL, quy trình thủ công an toàn hơn |
| `31f72a8` | D8-STD-03 / 04 | cổng không bỏ sót tài liệu chuyển đổi lỗi; export chạy trên v1.2.0, không trộn hai lần chạy |
| `c4ea65a`, `520d3e3` | E2-04 (cổng Local) | công cụ tiêm lỗi cho stack thử: `fail-once`, `fail-always`, `fail-osd` |
| `e2d19fb` | D8-09 | test phụ thuộc môi trường skip / stub thay vì lỗi |
| `ac34bb9` | E2-04, D8-10 | `ocr.cli status` nêu bản vá E2-04 |
| `42ff481` | hồi quy | test parity 12D7 đưa bằng chứng có provenance cho cổng v2 (lỗi do lượt hồi quy đầy đủ tìm ra) |
| `662c47e` | D8-03 (cổng Local) | manifest export đếm từ có `-` của TSV thô hiện nguyên văn trong nội dung (chỉ số đếm) |
| `1f32e48`, `4b3e1d1` | lint / kiểu | không lỗi mypy mới (toàn repo 81 = mốc), file mới đã format; chỉ kiểu, không đổi hành vi |

Commit cuối của mã: `4b3e1d1`; sau đó chỉ có tài liệu. Nghiệm thu Windows chạy trên commit **đầu nhánh** (gồm tài liệu).

## 3. Kết quả

* **37 finding của 12D8** — [PHASE12D9_FINDING_STATUS.json](PHASE12D9_FINDING_STATUS.json): 28 FIXED, 8 LOCAL
  VERIFICATION REQUIRED (D8-03, D8-01, D8-02, D8-STD-03, D8-OFF-03, D8-OFF-04, D8-OFF-11, D8-OFF-12), 1 DEFERRED WITH
  JUSTIFICATION (D8-08, P4: TSV hỏng mà mọi dòng có trường thứ 13 chỉ định kiểu cột chỉ mục ngầm khác upstream — không
  ảnh hưởng chữ; Tesseract không ghi dòng như vậy), 0 OPEN. Không finding nào về mất nội dung pháp lý, sai thứ tự đọc,
  sai số, oracle báo đạt sai, an toàn gói, backup / rollback hay bảo toàn DB bị hoãn.
* **Bổ sung 12E2** — [PHASE12D9_E2_FINDING_STATUS.json](PHASE12D9_E2_FINDING_STATUS.json),
  [PHASE12D9_OCR_FAILURE_SAFETY_REPORT.md](PHASE12D9_OCR_FAILURE_SAFETY_REPORT.md).
* Bản vá upstream: [PHASE12D9_UPSTREAM_PATCH_REPORT.md](PHASE12D9_UPSTREAM_PATCH_REPORT.md). Nội dung:
  [PHASE12D9_CONTENT_PRESERVATION_REPORT.md](PHASE12D9_CONTENT_PRESERVATION_REPORT.md). Cổng Standard:
  [PHASE12D9_STANDARD_DIFF_REPORT.md](PHASE12D9_STANDARD_DIFF_REPORT.md). Offline:
  [PHASE12D9_OFFLINE_SAFETY_REPORT.md](PHASE12D9_OFFLINE_SAFETY_REPORT.md). Hồi quy:
  [PHASE12D9_REGRESSION_REPORT.md](PHASE12D9_REGRESSION_REPORT.md). Quyết định mới: D-41 … D-47 và cập nhật D-40 trong
  [DECISIONS.md](../ocr/DECISIONS.md).
* E1-01, E1-02, E1-06, E1-08: **EVIDENCE REQUIRED** (Windows chỉ tái hiện bằng fixture tổng hợp; chưa nhận báo cáo đã
  làm sạch — không suy diễn).

## 4. Bốn loại vấn đề OCR — không gộp

| Finding | Loại | Kết luận |
|---|---|---|
| E2-04 | lỗi **thực thi** OCR | FIXED IN CODE; nguyên nhân gốc trên Windows chưa biết (không kết luận mount 9p) |
| E2-01 | giới hạn **phân đoạn / nhận dạng** (PSM 3, token ngắn) | NEEDS LOCAL EVIDENCE; không đổi PSM; fallback không cài (chèn chữ giả trên crop không chữ) |
| E2-02 | chất lượng **crop / layout / nhận dạng** | NEEDS LOCAL EVIDENCE; chỉ chẩn đoán |
| E1-05 | **toàn vẹn khi chạy** của cổng hướng xoay | lỗi build cổng: FIXED; chất lượng OCR 11 vùng: chưa xác minh (⇒ E2-02) |

## 5. Rủi ro còn lại và giới hạn

* Chưa có bằng chứng Windows trên commit cuối cho mọi sửa 12D9 (máy Local có tài liệu thật, Agri, model layout thật).
* Thay đổi hành vi có chủ đích (D-45): mọi kết quả Docling `PARTIAL_SUCCESS` bị từ chối thay vì lưu kèm cảnh báo.
* Ô bảng TableFormer: `-` giữ nhưng có thể thêm khoảng trắng; footnote gắn kèm chỉ trong Markdown (HTML như upstream);
  U+00AD / nháy / bullet / ligature theo upstream.
* Khác biệt do cổng hướng xoay chưa có bằng chứng tự động ⇒ `not verified` trong cổng Standard, xem tay.
* Updater tự động vẫn EXPERIMENTAL; production chỉ dùng quy trình thủ công.

## 6. Kết luận

```
PHASE 12D9: COMPLETED
D8-03 HYPHEN PRESERVATION: PASS (trong mã; Cloud: tổng hợp + Tesseract thật + lớp chữ PDF; Windows: G-H1)
D8-01 READING ORDER: PASS (trong mã; Cloud: fixture + benchmark 92; Windows: G-H3, G-H4)
D8-02 ATTACHED FOOTNOTES: PASS (trong mã; Standard và Legal; Windows: G-H2)
E0-07 TSV PRESERVATION: PASS
STANDARD EXPECTED-DIFF GATE: PASS (Cloud, OCR thật trên trang tổng hợp; 22 PDF thật: G-04)
LEGAL CONTENT PRESERVATION: PASS ON SYNTHETIC
OFFLINE MANUAL FALLBACK: PASS ON SYNTHETIC (Docker giả + diễn tập Docker thật ở Cloud với image thử; máy chủ Ubuntu thử: G-09)
AUTOMATIC UPDATER: EXPERIMENTAL
P0/P1 OPEN: 0
CODE RELEASE BLOCKERS: 0
LOCAL GATES REMAINING: D9-00a–c (G-01), G-02, G-03, G-H1–G-H5, G-04 (G-04-EXIT, 04a–c, MIX), G-05, G-06,
  G-07 (07a, 07c, 07d), G-08a, G-09 (TRUST, RB, a–e), G-10, G-11, G-12, E2-G1–E2-G8
READY FOR TARGETED RE-REVIEW: YES
READY FOR WINDOWS RETEST: YES
READY FOR RELEASE: NO
READY FOR PRODUCTION: NO
PRODUCTION UNCHANGED
```

Bổ sung 12E2:

```
E2-04 SILENT OCR REGION LOSS: FIXED IN CODE
E2-04 SOURCE AND EMBEDDING SAFETY: VERIFIED (Cloud: Source + hàng đợi embedding trên SurrealDB thật; Windows: E2-G1–G6)
E2-01 SHORT TOKEN OCR: NEEDS LOCAL EVIDENCE
E2-02 NOISY OCR CROPS: NEEDS LOCAL EVIDENCE
E2-03 MIXED-HUNK EXPECTED-DIFF: PASS
OCR FAILURE INJECTION: PASS
WINDOWS RETEST: PENDING
READY FOR RELEASE: NO
PRODUCTION UNCHANGED
```
