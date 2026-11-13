# ADR-013: OCR Engine Manager — native Docling OCR engines, selected per install

- **Status**: Accepted
- **Date**: 2026-11
- **Related**: [ADR-007](ADR-007-optin-runtimes.md) (opt-in runtimes), [docs/ocr/DECISIONS.md](../../ocr/DECISIONS.md) (detailed decisions D-01…D-10)

## Context

Vietnamese scanned documents were OCR'd by whatever Docling's `OcrAutoOptions` picked — in
practice RapidOCR (torch backend) with its default Chinese/Latin PP-OCR model, which drops most
Vietnamese tone-marked letters. content-core 2.0.7 builds Docling's pipeline options itself and
exposes no way to pass `ocr_options`.

## Decision

- Offer exactly 4 OCR choices, all through Docling's own option classes: RapidOCR (default,
  pinned to what Auto selects today), Tesseract Vietnamese Fast/Best (`TesseractCliOcrOptions`,
  tessdata_fast/best under one fixed `TESSDATA_PREFIX`) and EasyOCR Vietnamese
  (`EasyOcrOptions`, CPU, no runtime downloads). No custom adapters, no Docling/content-core
  patches.
- A minimal layer (`open_notebook/ocr/docling_extract.py`) builds the same
  `PdfPipelineOptions` as content-core plus `ocr_options`, used only for Docling-routed
  PDFs/images when the OCR configuration differs from the default; a parity test guards it.
- Model weights are pinned (URL + SHA-256) and installed on demand by worker jobs into the
  data volume; runtimes (Tesseract apt package, `easyocr` wheel) follow ADR-007: build arg /
  entrypoint flags / admin CLI, never from an HTTP request. Offline bundles cover air-gapped
  servers.

## Consequences

- Default behaviour is unchanged; no DB migration.
- The layer must be re-aligned (or removed) if content-core changes its Docling options or
  gains OCR options upstream.
- Worker now re-reads content settings per job (fixes stale settings in the worker).
- Runtime installs (Docling, EasyOCR) are constrained to `uv.lock` via an exported constraints file,
  and a compatibility guard (versions + source fingerprints of the content-core internals the layer
  mirrors) disables non-default engines on drift instead of failing silently (docs/ocr D-14).

## Addendum (Phase 8C / 8D): OCR quality and release classification

Measured on synthetic Vietnamese business documents (details, in Vietnamese:
`docs/ocr/OCR_QUALITY_BENCHMARK.md`, `docs/ocr/OCR_PHASE8D_REPORT.md`).

Three states are reported separately and must not be merged:

1. **Runtime / model ready** — the engine is installed and can be selected.
2. **Offline verified** — the whole pipeline (Layout Heron + TableFormer + OCR) ran
   with the network blocked.
3. **Quality qualification** — what was measured for Vietnamese documents. An
   engine can be ready and offline-verified and still not qualify.

| Choice | Quality tier | Use for | Known limits |
|---|---|---|---|
| Tesseract Vietnamese Best | `recommended` | Scanned Vietnamese text and tables; best overall quality | Some bold upper-case headings lose diacritics (accepted, non-blocking) |
| Tesseract Vietnamese Fast | `speed` | Faster; good table results on the holdout set | Some table labels and bold headings lose diacritics |
| RapidOCR – PaddleOCR | `compatibility` | The original engine; model and defaults unchanged | Loses Vietnamese diacritics on scans; cannot match Vietnamese table labels |
| EasyOCR Vietnamese | `experimental` | Evaluation only | Wrong digits and diacritics on 150 DPI scans; not for financial documents. A higher scan resolution helps but does not fix every error |

Rules: the default engine is never changed automatically; there is no automatic
fallback to another engine (in particular never to an experimental one); the UI asks
for confirmation before an experimental engine is activated.

Quality corrections (all through official Docling options, no Docling / content-core
change): `tesseract_gate.py` (set as `TesseractCliOcrOptions.tesseract_cmd`) ignores
low-confidence orientation guesses; `pdf_prep.py` corrects the orientation of scanned
pages in a temporary copy (needs the Tesseract binary and `osd.traineddata`; when they
are missing the engines work as before and the API reports the feature as unavailable);
OCR render scale follows the scan resolution for Tesseract; EasyOCR confidence
threshold 0.2. Switches: `OCR_TESSERACT_OSD_GATE=false`, `OCR_PDF_PREP=false`,
`OCR_EASYOCR_CONFIDENCE`.
