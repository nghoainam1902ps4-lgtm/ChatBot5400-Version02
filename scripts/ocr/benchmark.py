#!/usr/bin/env python3
"""OCR benchmark for the 4 OCR choices — same dataset, real engines, no mocks.

Two modes (MASTER_PLAN 5.4 asks to keep them apart):

* ``--mode ocr-stage`` — PURE OCR. Each page is loaded through Docling's own
  PDF backend and preprocessing, then the OCR model that Docling's official
  ``get_ocr_factory()`` instantiates for our options runs with
  ``OcrMode.FULL_PAGE``. No Layout/TableFormer weights are needed, so this runs
  in sandboxes where Hugging Face is unreachable.
* ``--mode pipeline`` — the FULL production path
  (``open_notebook.ocr.docling_extract.convert_file``: Docling + Layout Heron +
  TableFormer + selected OCR → markdown). Needs Docling's HF models.

Ground truth comes from ``scripts/ocr/generate_samples.py`` (synthetic,
fictional, non-sensitive). CER/WER are computed only where ground truth exists.

    uv run python scripts/ocr/benchmark.py --samples ./data/ocr-samples \\
        --mode ocr-stage --engines rapidocr tesseract_fast tesseract_best easyocr \\
        --out bench.json
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from open_notebook.ocr import catalog, metrics  # noqa: E402
from open_notebook.ocr.options import OcrSettings, build_ocr_options  # noqa: E402


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _input_format(path: Path) -> Any:
    from docling.datamodel.base_models import InputFormat

    return InputFormat.PDF if path.suffix.lower() == ".pdf" else InputFormat.IMAGE


def make_ocr_model(engine_id: str, num_threads: int | None = None) -> Any:
    """Instantiate the OCR model exactly as Docling's pipeline does (official factory)."""
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.models.factories import get_ocr_factory

    options = build_ocr_options(engine_id, force_full_page=True)
    accel = (
        AcceleratorOptions(num_threads=num_threads)
        if num_threads
        else AcceleratorOptions()
    )
    return get_ocr_factory(allow_external_plugins=False).create_instance(
        options=options, enabled=True, artifacts_path=None, accelerator_options=accel
    )


def ocr_stage_text(model: Any, path: Path) -> tuple[str, int]:
    """Run ``model`` over every page of ``path``; return text + page count."""
    from docling.backend.image_backend import ImageDocumentBackend
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.base_models import Page
    from docling.datamodel.document import ConversionResult, InputDocument
    from docling.models.stages.page_preprocessing.page_preprocessing_model import (
        PagePreprocessingModel,
        PagePreprocessingOptions,
    )

    fmt = _input_format(path)
    backend_cls = (
        PyPdfiumDocumentBackend
        if path.suffix.lower() == ".pdf"
        else ImageDocumentBackend
    )
    in_doc = InputDocument(path_or_stream=path, format=fmt, backend=backend_cls)
    conv_res = ConversionResult(input=in_doc)
    pre = PagePreprocessingModel(options=PagePreprocessingOptions(images_scale=1.0))
    texts: list[str] = []
    for i in range(in_doc.page_count):
        page = Page(page_no=i + 1)
        page._backend = in_doc._backend.load_page(i)
        page.size = page._backend.get_size()
        pages = list(pre(conv_res, [page]))
        pages = list(model(conv_res, pages))
        cells = [c for c in pages[0].cells if getattr(c, "from_ocr", False)]
        # Reading order: group cells into lines by vertical centre, then left→right.
        rows: list[list[Any]] = []
        for c in sorted(
            cells,
            key=lambda c: (c.rect.to_bounding_box().t, c.rect.to_bounding_box().l),
        ):
            bb = c.rect.to_bounding_box()
            mid = (bb.t + bb.b) / 2
            if rows:
                last = rows[-1][0].rect.to_bounding_box()
                if abs(((last.t + last.b) / 2) - mid) < max(
                    6.0, abs(last.b - last.t) * 0.5
                ):
                    rows[-1].append(c)
                    continue
            rows.append([c])
        for row in rows:
            row.sort(key=lambda c: c.rect.to_bounding_box().l)
            texts.append(" ".join(c.text for c in row))
        page._backend.unload()
    in_doc._backend.unload()
    return "\n".join(texts), in_doc.page_count


def pipeline_text(
    engine_id: str, path: Path, num_threads: int | None
) -> tuple[str, list[str]]:
    from content_core import ContentCoreConfig

    from open_notebook.ocr.docling_extract import convert_file

    text, meta = convert_file(
        str(path),
        ContentCoreConfig(document_engine="docling", docling_ocr=True),
        OcrSettings(engine=engine_id, num_threads=num_threads),
    )
    return text, meta.get("ocr_models", [])


def score(gt: str, hyp: str, fields: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "cer": round(metrics.cer(gt, hyp), 4),
        "wer": round(metrics.wer(gt, hyp), 4),
        "word_recall": round(metrics.word_recall(gt, hyp), 4),
        "diacritics": metrics.diacritic_accuracy(gt, hyp),
        "amounts": metrics.field_recall(fields.get("amounts", []), hyp),
        "dates": metrics.field_recall(fields.get("dates", []), hyp),
        "doc_numbers": metrics.field_recall(fields.get("doc_numbers", []), hyp),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", required=True, type=Path)
    ap.add_argument("--mode", choices=["ocr-stage", "pipeline"], default="ocr-stage")
    ap.add_argument("--engines", nargs="+", default=list(catalog.ENGINE_IDS))
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--only", nargs="*", help="Subset of sample names")
    ap.add_argument("--out", type=Path)
    ap.add_argument(
        "--rescore",
        type=Path,
        help="Recompute metrics from the texts saved in an earlier --out report (no OCR run).",
    )
    args = ap.parse_args()

    if args.rescore:
        manifest = json.loads(
            (args.samples / "manifest.json").read_text(encoding="utf-8")
        )
        report = json.loads(args.rescore.read_text(encoding="utf-8"))
        for er in report["results"].values():
            for name, s in er.get("samples", {}).items():
                if "text" in s:
                    gt = (args.samples / f"{name}.gt.txt").read_text(encoding="utf-8")
                    s.update(score(gt, s["text"], manifest[name].get("key_fields", {})))
        (args.out or args.rescore).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return

    manifest = json.loads((args.samples / "manifest.json").read_text(encoding="utf-8"))
    names = [n for n in manifest if not args.only or n in args.only]
    report: dict[str, Any] = {
        "mode": args.mode,
        "threads": args.threads or "docling-default",
        "cpu_count": os.cpu_count(),
        "results": {},
    }
    for engine_id in args.engines:
        er: dict[str, Any] = {"samples": {}}
        rss0 = _rss_mb()
        t0 = time.time()
        try:
            model = (
                make_ocr_model(engine_id, args.threads)
                if args.mode == "ocr-stage"
                else None
            )
        except Exception as e:
            er["error"] = f"{type(e).__name__}: {e}"[:500]
            report["results"][engine_id] = er
            print(f"[{engine_id}] init failed: {er['error']}", flush=True)
            continue
        er["cold_start_seconds"] = round(time.time() - t0, 2)
        if model is not None:
            er["docling_ocr_model"] = type(model).__name__
        for name in names:
            meta = manifest[name]
            path = args.samples / meta["file"]
            gt = (args.samples / f"{name}.gt.txt").read_text(encoding="utf-8")
            t1 = time.time()
            try:
                if args.mode == "ocr-stage":
                    hyp, pages = ocr_stage_text(model, path)
                    used = [type(model).__name__]
                else:
                    hyp, used = pipeline_text(engine_id, path, args.threads)
                    pages = meta["pages"]
            except Exception as e:
                er["samples"][name] = {"error": f"{type(e).__name__}: {e}"[:500]}
                print(f"[{engine_id}] {name}: ERROR {e}", flush=True)
                continue
            elapsed = time.time() - t1
            s = score(gt, hyp, meta.get("key_fields", {}))
            s.update(
                seconds=round(elapsed, 2),
                seconds_per_page=round(elapsed / max(pages, 1), 2),
                pages=pages,
                ocr_models=used,
                text=hyp,
            )
            er["samples"][name] = s
            print(
                f"[{engine_id}] {name}: CER={s['cer']} WER={s['wer']} t={s['seconds']}s",
                flush=True,
            )
        er["total_seconds"] = round(time.time() - t0, 2)
        er["peak_rss_mb_delta"] = round(_rss_mb() - rss0, 1)
        report["results"][engine_id] = er
    report["peak_rss_mb"] = round(_rss_mb(), 1)
    if args.out:
        args.out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps({k: v for k, v in report.items() if k != "results"}))


if __name__ == "__main__":
    main()
