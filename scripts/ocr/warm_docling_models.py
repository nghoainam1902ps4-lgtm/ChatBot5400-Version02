#!/usr/bin/env python3
"""Download Docling's Layout (Heron) + TableFormer weights into HF_HOME — the way
production loads them (no artifacts_path), by initialising the PRODUCTION
converter once. Run on a machine with Internet; for air-gapped servers, copy
the resulting HF_HOME directory (see docs/ocr/OCR_LOCAL_ACCEPTANCE.md).

    HF_HOME=./data/.cache/huggingface uv run python scripts/ocr/warm_docling_models.py --engine tesseract_best

Prints the pipeline identity (layout model, table model + mode, OCR class) so it
doubles as a quick check that the selected engine is wired correctly.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--engine",
        default="rapidocr",
        choices=["rapidocr", "tesseract_fast", "tesseract_best", "easyocr"],
    )
    a = ap.parse_args()
    from content_core import ContentCoreConfig
    from docling.datamodel.base_models import InputFormat

    from open_notebook.ocr.docling_extract import build_converter
    from open_notebook.ocr.options import OcrSettings

    conv = build_converter(
        ContentCoreConfig(document_engine="docling", docling_ocr=True),
        OcrSettings(engine=a.engine),
    )
    conv.initialize_pipeline(InputFormat.PDF)
    pipe = next(iter(conv.initialized_pipelines.values()))
    po = pipe.pipeline_options
    print(
        json.dumps(
            {
                "hf_home": os.environ.get("HF_HOME", "~/.cache/huggingface (default)"),
                "layout_model": getattr(po.layout_options.model_spec, "name", None),
                "table_model": po.table_structure_options.kind,
                "table_mode": str(
                    getattr(po.table_structure_options.mode, "value", "")
                ),
                "ocr_model": type(pipe.ocr_model).__name__,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
