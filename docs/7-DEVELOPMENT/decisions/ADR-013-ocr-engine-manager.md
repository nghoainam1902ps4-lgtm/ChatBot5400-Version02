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
