"""Minimal configuration layer that hands Docling the selected OCR engine.

WHY THIS EXISTS (DECISIONS D-02): content-core 2.0.7 builds Docling's
``PdfPipelineOptions`` itself and offers no way to pass ``ocr_options``. This
module builds the SAME options content-core builds
(``content_core/processors/document/docling.py::extract_docling``) and adds
only ``ocr_options`` (+ ``accelerator_options`` when the admin set a thread
count). Layout (Heron), TableFormer, the PDF backend, enrichment flags and the
markdown export are left exactly as content-core leaves them.
``tests/test_ocr_docling_parity.py`` guards that parity across upgrades.

It is used ONLY for files content-core would itself route to Docling AND that
can need OCR (PDF / images). The default configuration (RapidOCR, default
tuning, and an environment where Docling's Auto mode really picks RapidOCR)
keeps calling ``content_core.extract_content`` untouched (D-03).

Remove this module once content-core accepts OCR options upstream.
"""

from __future__ import annotations

import os
import time
from typing import Any

from loguru import logger

from open_notebook.ocr import catalog, runtime
from open_notebook.ocr.options import (
    OcrSettings,
    build_accelerator_options,
    build_ocr_options,
    describe,
)
from open_notebook.ocr.status import assert_engine_ready

# Formats where Docling runs OCR. Office/HTML/Markdown never OCR.
OCR_MIME_TYPES = frozenset(
    {"application/pdf", "image/png", "image/jpeg", "image/tiff", "image/bmp"}
)


def native_path_required(ocr: OcrSettings) -> bool:
    """Whether the selected OCR configuration differs from content-core's default."""
    if not ocr.enabled:
        return False
    if ocr.engine != "rapidocr":
        return True
    if not ocr.uses_default_tuning:
        return True
    # RapidOCR + default tuning: content-core's Auto path is identical only while
    # Auto would really pick RapidOCR (e.g. not after EasyOCR was installed).
    return not runtime.auto_resolves_to_rapidocr()


def _docling_routes(mime: str, document_engine: str) -> bool:
    """Mirror content-core's ``_route_for_mime`` decision for Docling."""
    try:
        from content_core.extraction import DOCLING_AVAILABLE, DOCLING_SUPPORTED
    except ImportError:
        return False
    if not DOCLING_AVAILABLE:
        return False
    if document_engine == "docling":
        return True
    return document_engine == "auto" and mime in DOCLING_SUPPORTED


async def should_use_native_ocr(
    file_path: str, document_engine: str, ocr: OcrSettings
) -> bool:
    if not file_path or not native_path_required(ocr):
        return False
    from content_core.content.identification import get_file_type

    mime = await get_file_type(file_path)
    return mime in OCR_MIME_TYPES and _docling_routes(mime, document_engine)


def build_pipeline_options(
    cc_config: Any, ocr: OcrSettings, for_image: bool = False
) -> Any:
    """content-core's PdfPipelineOptions + the selected ocr_options."""
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    kwargs: dict[str, Any] = dict(
        # Images always OCR (Docling's default, what content-core gets today);
        # PDFs honour the docling_ocr toggle exactly like content-core.
        do_ocr=True if for_image else bool(cc_config.docling_ocr),
        do_formula_enrichment=cc_config.docling_formulas,
        do_picture_description=cc_config.docling_vision,
        do_chart_extraction=cc_config.docling_vision,
        ocr_options=build_ocr_options(ocr.engine, ocr.force_full_page),
    )
    accel = build_accelerator_options(ocr.num_threads)
    if accel is not None:
        kwargs["accelerator_options"] = accel
    return PdfPipelineOptions(**kwargs)


def build_converter(cc_config: Any, ocr: OcrSettings) -> Any:
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import (
        DocumentConverter,
        ImageFormatOption,
        PdfFormatOption,
    )

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=build_pipeline_options(cc_config, ocr)
            ),
            InputFormat.IMAGE: ImageFormatOption(
                pipeline_options=build_pipeline_options(cc_config, ocr, for_image=True)
            ),
        }
    )


def actual_ocr_models(converter: Any) -> list[str]:
    """Class names of the OCR models Docling actually instantiated (evidence)."""
    names: list[str] = []
    for pipeline in getattr(converter, "initialized_pipelines", {}).values():
        model = getattr(pipeline, "ocr_model", None)
        if model is not None:
            engine = getattr(model, "_engine", None)  # Auto wrapper, if ever used
            names.append(type(engine or model).__name__)
    return sorted(set(names))


def convert_file(
    path: str, cc_config: Any, ocr: OcrSettings
) -> tuple[str, dict[str, Any]]:
    """Synchronous conversion (same blocking behaviour as content-core)."""
    converter = build_converter(cc_config, ocr)
    started = time.time()
    result = converter.convert(path)
    doc = result.document
    fmt = getattr(cc_config, "docling_output_format", "markdown")
    if fmt == "html":
        output = doc.export_to_html()
    elif fmt == "json":
        output = doc.export_to_json()
    else:
        output = doc.export_to_markdown()
    meta = {
        "docling_format": fmt,
        "ocr_engine": ocr.engine,
        "ocr_models": actual_ocr_models(converter),
        "ocr_seconds": round(time.time() - started, 2),
    }
    return output, meta


async def extract_with_selected_ocr(
    file_path: str, cc_config: Any, ocr: OcrSettings
) -> Any:
    """Extract ``file_path`` with Docling + the selected OCR engine.

    Returns content-core's ``ExtractionOutput`` shaped like ``extract_docling``
    output post-processed by ``_extract_file`` (title, identified_type,
    source_type), so the rest of the source graph is unaffected.
    """
    from content_core.common import ExtractionOutput
    from content_core.content.identification import get_file_type

    if ocr.engine != "rapidocr":
        assert_engine_ready(
            ocr.engine
        )  # explicit error, never a silent fallback (D-07)
    mime = await get_file_type(file_path)
    info = describe(ocr.engine)
    logger.info(
        f"Extracting document via Docling with OCR engine={ocr.engine} "
        f"({info['docling_class']}, lang={info['lang']}, device={info['device']}, "
        f"threads={ocr.num_threads or 'docling-default'}, full_page={ocr.force_full_page})"
    )
    content, meta = convert_file(file_path, cc_config, ocr)
    logger.info(
        f"Docling OCR finished: engine={ocr.engine} actual_models={meta['ocr_models']} "
        f"in {meta['ocr_seconds']}s"
    )
    expected = {
        "rapidocr": "RapidOcrModel",
        "tesseract": "TesseractOcrCliModel",
        "easyocr": "EasyOcrModel",
    }[catalog.get_engine(ocr.engine).docling_kind]
    if meta["ocr_models"] and expected not in meta["ocr_models"]:
        # Defensive: Docling instantiated something other than what we asked for.
        raise ValueError(
            f"Docling used OCR model(s) {meta['ocr_models']} instead of {expected}; refusing the result."
        )
    return ExtractionOutput(
        content=content,
        title=os.path.basename(file_path),
        source_type="file",
        identified_type=mime,
        metadata=meta,
    )
