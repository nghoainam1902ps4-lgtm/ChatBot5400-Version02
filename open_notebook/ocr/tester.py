"""'Test' action of the OCR Engine Manager.

Runs the REAL production conversion path (``docling_extract.convert_file``:
Docling + Layout + TableFormer + the selected OCR engine) on a built-in,
synthetic, non-sensitive Vietnamese sample image, and reports which OCR model
Docling actually instantiated. Runs in the worker (where documents are
processed), never in the API request.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from open_notebook.ocr import catalog, metrics
from open_notebook.ocr.options import OcrSettings, describe

SAMPLE = Path(__file__).parent / "assets" / "sample_vi.png"
SAMPLE_GT = Path(__file__).parent / "assets" / "sample_vi.gt.txt"


def run_engine_test(engine_id: str, base: OcrSettings | None = None) -> dict[str, Any]:
    from content_core import ContentCoreConfig

    from open_notebook.ocr.docling_extract import convert_file
    from open_notebook.ocr.status import assert_engine_ready

    spec = catalog.get_engine(engine_id)
    base = base or OcrSettings()
    ocr = OcrSettings(
        enabled=True,
        engine=engine_id,
        num_threads=base.num_threads,
        force_full_page=base.force_full_page,
    )
    info = describe(engine_id)
    result: dict[str, Any] = {
        "engine": engine_id,
        "display_name": spec.display_name,
        "model": info["model"],
        "languages": info["lang"] or list(spec.languages),
        "device": info["device"],
        "docling_class": info["docling_class"],
        "success": False,
        "tested_at": time.time(),
    }
    started = time.time()
    try:
        if engine_id != "rapidocr":
            assert_engine_ready(engine_id)
        text, meta = convert_file(
            str(SAMPLE),
            ContentCoreConfig(document_engine="docling", docling_ocr=True),
            ocr,
        )
        result["ocr_models"] = meta.get("ocr_models")
        for key in ("layout_model", "table_model", "table_mode"):
            result[key] = meta.get(key)
        result["text"] = text[:4000]
        gt = SAMPLE_GT.read_text(encoding="utf-8")
        result["cer"] = round(metrics.cer(gt, text), 4)
        result["success"] = bool(text.strip())
        if not result["success"]:
            result["error"] = "No text recognised from the sample."
    except Exception as e:  # reported to the admin, never raised to the worker
        result["error"] = f"{type(e).__name__}: {e}"[:1000]
    result["elapsed_seconds"] = round(time.time() - started, 2)
    return result
