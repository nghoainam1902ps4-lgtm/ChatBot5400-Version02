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

import asyncio
import hashlib
import inspect
import os
import re
import threading
import time
from dataclasses import replace
from importlib.metadata import PackageNotFoundError, version
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


def native_path_required(ocr: OcrSettings, is_image: bool = False) -> bool:
    """Whether the selected OCR configuration differs from content-core's default.

    Images: content-core sets no Docling option for images, so Docling OCRs
    them even when ``docling_ocr`` is off — the engine choice applies to them
    regardless of that toggle (otherwise an installed EasyOCR could be picked
    by Auto and download weights while processing).
    """
    if not ocr.enabled and not is_image:
        return False
    if ocr.engine != "rapidocr":
        return True
    if not ocr.uses_default_tuning:
        return True
    from open_notebook.ocr.options import rapidocr_force_cpu, rapidocr_persistent

    if rapidocr_force_cpu() or rapidocr_persistent():
        return True  # needs explicit ocr_options (content-core cannot pass them)
    # RapidOCR + default tuning: content-core's Auto path is identical only while
    # Auto would really pick RapidOCR (e.g. not after EasyOCR was installed).
    if runtime.auto_resolves_to_rapidocr():
        return False
    from open_notebook.ocr import compat

    found = compat.problems("rapidocr")
    if found and not compat.override_enabled():
        # Cannot pin safely on unverified dependencies: keep content-core's
        # behaviour (the pre-existing default) and say so loudly.
        logger.warning(
            "OCR: Docling Auto may not select RapidOCR here, but dependencies are "
            f"unverified ({'; '.join(found)}); using content-core's default path."
        )
        return False
    return True


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
    if not file_path:
        return False
    from content_core.content.identification import get_file_type

    # Cheap pre-check (is_image=True is the most permissive case). Legal
    # Document normalization (D-34) needs the DoclingDocument, which only this
    # layer has: a PDF then takes it even with the default configuration.
    if native_path_required(ocr, is_image=True) or ocr.legal_normalization:
        mime = await get_file_type(file_path)
        decided = _decide(mime, document_engine, ocr)
        if decided:
            _warn_if_legal_changes_the_ocr_path(ocr, mime)
        return decided
    # Default configuration: content-core's own path, with ONE exception (D-33).
    # content-core cannot be given an OCR mode, so a PDF that the opt-in rule
    # wants read in full-page mode is converted here, with the same engine.
    if not (ocr.enabled and _auto_full_page_enabled()):
        return False
    decision = await asyncio.to_thread(_decide_ocr_mode, file_path, ocr)
    if not decision.triggered:
        _log_ocr_mode(ocr.engine, decision)
        return False
    mime = await get_file_type(file_path)
    return _decide(mime, document_engine, replace(ocr, force_full_page=True))


def _auto_full_page_enabled() -> bool:
    from open_notebook.ocr import pdf_prep

    return pdf_prep.auto_full_page_enabled()


def _decide_ocr_mode(path: str, ocr: OcrSettings) -> Any:
    from open_notebook.ocr import pdf_prep

    return pdf_prep.decide_ocr_mode(path, ocr.enabled, ocr.force_full_page)


def _log_ocr_mode(engine: str, decision: Any) -> None:
    """Engine, configured / effective mode, reason and ratios — never any text."""
    from open_notebook.ocr import pdf_prep

    if decision.reason == pdf_prep.REASON_MIXED:
        logger.warning(
            decision.describe(engine)
            + " — the document mixes scanned pages under tilted visible text with "
            "pages of ordinary PDF text. Docling has one OCR mode per document, so "
            "the configured mode is kept; text under the tilted boxes may be "
            "missing. Process such a file with Force Full Page OCR if the scanned "
            "pages matter more than the text layer."
        )
    elif decision.reason not in (
        pdf_prep.REASON_FLAG_OFF,
        pdf_prep.REASON_OCR_DISABLED,
        pdf_prep.REASON_NOT_A_PDF,
    ):
        logger.info(decision.describe(engine))


def _decide(mime: str, document_engine: str, ocr: OcrSettings) -> bool:
    return (
        mime in OCR_MIME_TYPES
        and (
            native_path_required(ocr, is_image=mime.startswith("image/"))
            or _legal_applies(ocr, mime)
        )
        and _docling_routes(mime, document_engine)
    )


def _warn_if_legal_changes_the_ocr_path(ocr: OcrSettings, mime: str) -> None:
    """Legal mode moves a default-configuration PDF from content-core to this layer.

    Same pipeline options, but RapidOCR is named explicitly instead of being
    picked by Docling's Auto mode, and pdf_prep runs (finding F-15). Say so, and
    say it loudly when the RapidOCR dependencies are not the verified set - the
    case the default routing deliberately leaves to content-core.
    """
    if not _legal_applies(ocr, mime) or native_path_required(
        ocr, is_image=mime.startswith("image/")
    ):
        return  # this configuration takes the Docling layer anyway
    from open_notebook.ocr import compat

    found = compat.problems("rapidocr")
    if found and not compat.override_enabled():
        logger.warning(
            "Legal Document mode routes this PDF through the ChatBot5400 Docling "
            "layer with explicit RapidOCR options although its dependencies are "
            f"unverified ({'; '.join(found)}); the OCR text may differ from the "
            "Standard (content-core) path."
        )
    else:
        logger.info(
            "Legal Document mode: this PDF is converted by the ChatBot5400 Docling "
            "layer (explicit RapidOCR options, page preparation) instead of "
            "content-core's default path."
        )


def _legal_applies(ocr: OcrSettings, mime: str) -> bool:
    """Legal Document normalization covers PDFs only (D-34); images unchanged."""
    from open_notebook.ocr import legal_normalizer

    return ocr.legal_normalization and legal_normalizer.applies_to(mime)


async def should_use_native_ocr_for_url(
    url: str, document_engine: str, ocr: OcrSettings
) -> bool:
    """Same decision for URL sources that content-core would download as files.

    content-core's ``_extract_url`` HEAD-checks the URL and, for PDFs/images,
    downloads them and runs Docling with Auto OCR. Without this, a URL-sourced
    scan would bypass the selected engine (and, once EasyOCR is installed,
    silently switch to it). Web pages / YouTube are unaffected (not OCR MIME).
    """
    if not url or not (
        native_path_required(ocr, is_image=True) or ocr.legal_normalization
    ):
        return False
    from content_core.processors.url import detect_remote_mime

    from open_notebook.utils.url_ingestion import assert_url_ingestion_enabled

    assert_url_ingestion_enabled()  # D-29: no outbound fetch when switched off

    mime = await detect_remote_mime(url)
    return _decide(mime, document_engine, ocr)


async def extract_url_with_selected_ocr(
    url: str, cc_config: Any, ocr: OcrSettings
) -> Any:
    """Download exactly like content-core does, then extract with the selected OCR."""
    # Same downloader content-core's _extract_url uses (aiohttp, trust_env,
    # retry policy); guarded by tests/test_ocr_docling_parity.py on upgrades.
    from content_core.extraction import _download_remote_file

    from open_notebook.utils.url_ingestion import assert_url_ingestion_enabled

    assert_url_ingestion_enabled()  # D-29: no download when switched off

    tmp = await _download_remote_file(url)
    try:
        result = await extract_with_selected_ocr(tmp, cc_config, ocr)
        result.source_type = "url"
        return result
    finally:
        try:
            os.remove(tmp)
        except OSError:
            logger.warning(f"Failed to delete temp file: {tmp}")


def build_pipeline_options(
    cc_config: Any,
    ocr: OcrSettings,
    for_image: bool = False,
    scale: float | None = None,
) -> Any:
    """content-core's pipeline options + the selected ocr_options.

    PDFs: exactly the options content-core's ``extract_docling`` sets.
    Images: content-core sets NO format option for images, so Docling's
    defaults apply (OCR on, enrichments off) — keep those defaults and only add
    ``ocr_options`` (the enrichment toggles must not start applying to images).
    """
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    kwargs: dict[str, Any] = {
        "ocr_options": build_ocr_options(
            ocr.engine,
            ocr.force_full_page,
            scale=scale,
            custom_version=ocr.custom_version,
        )
    }
    if not for_image:
        kwargs.update(
            do_ocr=bool(cc_config.docling_ocr),
            do_formula_enrichment=cc_config.docling_formulas,
            do_picture_description=cc_config.docling_vision,
            do_chart_extraction=cc_config.docling_vision,
        )
    accel = build_accelerator_options(ocr.num_threads)
    if accel is not None:
        kwargs["accelerator_options"] = accel
    return PdfPipelineOptions(**kwargs)


def build_converter(
    cc_config: Any, ocr: OcrSettings, scale: float | None = None
) -> Any:
    """``scale``: OCR render scale for PDFs (see ``pdf_prep``); None = Docling default."""
    from docling.datamodel.base_models import InputFormat

    from open_notebook.ocr.hub_http import bound_hub_timeouts

    bound_hub_timeouts()  # no 15-minute hang on a dead keep-alive link (D-24)
    # D8-03 / D8-02 (Phase 12D9): Docling keeps every hyphen the document has
    # and the footnotes of tables / pictures, for every engine and text layers.
    # Guarded: refuses (ValueError) on a Docling it was not written for.
    from open_notebook.ocr import docling_patches

    docling_patches.apply_text_preservation(required=True)
    from docling.document_converter import (
        DocumentConverter,
        ImageFormatOption,
        PdfFormatOption,
    )

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=build_pipeline_options(cc_config, ocr, scale=scale)
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


_NATIVE_EXTRACT_SHA256 = (
    "62a0daf9b0f616f2138a7d5e1a01dc97de19a28f97e9990d136d02b686279528"
)
_NATIVE_DISPATCH_SHA256 = (
    "4214ea6f55ffc6607c7e4c283e684315c7d285c9e0860fa292a368e23f81b1fb"
)
_native_lock = threading.Lock()


def install_native_pdf_integrity() -> bool:
    """Guard content-core's local Docling callback, after URL download/routing."""
    from content_core import extraction

    with _native_lock:
        original = extraction.extract_docling
        if original is None:
            return False
        if getattr(original, "__cb5400_native_pdf__", False):
            return bool(getattr(original, "__cb5400_native_pdf_verified__", False))
        from open_notebook.ocr.docling_patches import TextPreservationPatchError

        try:
            dispatch = hashlib.sha256(
                inspect.getsource(extraction._extract_file).encode()
            ).hexdigest()
            if dispatch != _NATIVE_DISPATCH_SHA256:
                raise TextPreservationPatchError(
                    "Unverified content-core Docling dispatch"
                )
            verified = (
                version("content-core") == "2.0.7"
                and hashlib.sha256(inspect.getsource(original).encode()).hexdigest()
                == _NATIVE_EXTRACT_SHA256
            )
        except TextPreservationPatchError:
            raise
        except (PackageNotFoundError, OSError, TypeError, ValueError):
            raise TextPreservationPatchError(
                "Cannot verify content-core Docling dispatch"
            ) from None

        async def extract(source: str, config: Any) -> Any:
            if not _is_pdf(source):
                return await original(source, config)
            if not verified:
                raise TextPreservationPatchError(
                    "Unverified content-core PDF integration"
                )
            return await asyncio.to_thread(_extract_native_pdf, source, config)

        extract.__cb5400_native_pdf__ = True  # type: ignore[attr-defined]
        extract.__cb5400_native_pdf_verified__ = verified  # type: ignore[attr-defined]
        extraction.extract_docling = extract
        return verified


def _extract_native_pdf(path: str, config: Any) -> Any:
    from content_core.common import ExtractionOutput
    from content_core.processors.document import docling as native

    from open_notebook.ocr import docling_patches

    if not docling_patches.apply_text_preservation(required=True):
        raise docling_patches.TextPreservationPatchError("PDF patches are not active")

    # Preserve content-core's own default OCR Auto and its PDF pipeline options.
    converter = native.DocumentConverter(
        format_options={
            native.InputFormat.PDF: native.PdfFormatOption(
                pipeline_options=native.PdfPipelineOptions(
                    do_ocr=config.docling_ocr,
                    do_formula_enrichment=config.docling_formulas,
                    do_picture_description=config.docling_vision,
                    do_chart_extraction=config.docling_vision,
                )
            )
        }
    )
    result = _convert(converter, path)
    reject_incomplete(result, path)
    fmt = config.docling_output_format
    return ExtractionOutput(
        content=_require_text(_export(result.document, fmt)),
        source_type="file",
        identified_type="",
        metadata={"docling_format": fmt},
    )


def _export(doc: Any, fmt: str) -> str:
    if fmt in ("html", "json"):
        _require_text(doc.export_to_text(traverse_pictures=True))
    if fmt == "html":
        return doc.export_to_html()
    if fmt == "json":
        return doc.export_to_json()
    from open_notebook.ocr.docling_patches import export_standard_markdown

    return export_standard_markdown(doc)


def _convert(converter: Any, path: str) -> Any:
    try:
        return converter.convert(path)
    except Exception as exc:
        failures = _ocr_region_failures(str(exc))
        if failures:
            raise IncompleteConversionError(
                ocr_region=True, details=f"status=failure, {failures[0]}"
            ) from None
        raise


def convert_document(
    path: str, cc_config: Any, ocr: OcrSettings
) -> tuple[Any, Any, Any]:
    """The production conversion: (Docling result, converter, PdfPrep).

    A PDF is first inspected by ``pdf_prep`` (D-25): scanned pages that are
    sideways or upside down are corrected in a temporary copy (every engine,
    when Tesseract's orientation data is installed), and with a Tesseract
    engine the OCR render scale follows the scan resolution. Other file types
    are converted exactly as before. With ``OCR_AUTO_FULL_PAGE_ON_WATERMARK``
    the OCR mode of the document is decided here too (D-33).
    """
    from open_notebook.ocr import pdf_prep, runtime

    # D-33 (opt-in): a scan under tilted visible text boxes is read in Docling's
    # full-page OCR mode. Only the mode of THIS conversion changes; the saved
    # setting, the file and every other document are untouched.
    decision = _decide_ocr_mode(path, ocr)
    _log_ocr_mode(ocr.engine, decision)
    if decision.triggered:
        ocr = replace(ocr, force_full_page=True)
    prep = pdf_prep.PdfPrep()
    try:
        if ocr.enabled:
            prep = pdf_prep.prepare(path, runtime.tesseract_cmd())
            if catalog.get_engine(ocr.engine).docling_kind != "tesseract":
                prep.scale = None  # measured for Tesseract only
        prep.mode = decision
        converter = build_converter(cc_config, ocr, scale=prep.scale)
        result = _convert(converter, prep.path or path)
    finally:
        prep.cleanup()
    return result, converter, prep


def convert_file(
    path: str, cc_config: Any, ocr: OcrSettings
) -> tuple[str, dict[str, Any]]:
    """Synchronous conversion (same blocking behaviour as content-core)."""
    started = time.time()
    ocr = ocr.pinned()  # a custom engine reads ONE model version for the whole file
    result, converter, prep = convert_document(path, cc_config, ocr)
    # E2-04: a result with a failed OCR region / page is never stored as complete
    reject_incomplete(result, path)
    doc = result.document
    fmt = getattr(cc_config, "docling_output_format", "markdown")
    normalization: dict[str, Any] = {}
    if fmt not in ("html", "json") and ocr.legal_normalization and _is_pdf(path):
        # D-34: same DoclingDocument, serialized by the Legal Document
        # normalizer; any failure falls back to the standard export below.
        from open_notebook.ocr import legal_normalizer

        # The element texts before Docling's own merge (R2-01): evidence that
        # confirms the parts of an item Docling merged, nothing else. Reading
        # it never fails the conversion: without it a merge is only reported.
        try:
            evidence = legal_normalizer.source_evidence(result)
        except Exception as e:  # noqa: BLE001 - evidence is optional
            logger.warning(
                "Legal normalization: no merge evidence ({}: {})", type(e).__name__, e
            )
            evidence = None
        output, normalization = legal_normalizer.normalize_or_fallback(
            doc, evidence=evidence
        )
    else:
        output = _export(doc, fmt)
    if ocr.legal_normalization and not normalization:
        # Legal was requested but this conversion is outside its scope (not a
        # PDF, or HTML / JSON output): say so, do not look normalized (F-07).
        from open_notebook.ocr import legal_normalizer

        why = "not a PDF" if fmt not in ("html", "json") else f"{fmt} output"
        normalization = {
            "text_normalization": legal_normalizer.MODE_LEGAL,
            "legal_normalization_status": "skipped",
            "legal_normalization_record": legal_normalizer.skipped_record(why),
        }
    meta = {
        "docling_format": fmt,
        "ocr_engine": ocr.engine,
        "ocr_models": actual_ocr_models(converter),
        "ocr_seconds": round(time.time() - started, 2),
        **_custom_meta(ocr),
        **prep.as_meta(),
        **pipeline_identity(converter),
        **conversion_outcome(result, path),
        **normalization,
    }
    return _require_text(output), meta


def _require_text(output: str) -> str:
    if not output or not output.replace("<!-- image -->", "").strip():
        raise IncompleteConversionError(ocr_region=False, details="empty document")
    return output


def _is_pdf(path: str) -> bool:
    """PDF by content, whatever the file name says.

    The PDF specification allows the header anywhere in the first 1024 bytes
    (some scanners write a few bytes before it), and the MIME sniffing that
    routed the file here accepts that too (finding F-18).
    """
    try:
        with open(path, "rb") as f:
            return b"%PDF-" in f.read(1024)
    except OSError:
        return False


def _custom_meta(ocr: OcrSettings) -> dict[str, Any]:
    """Which custom model version produced the text (evidence; custom engines only)."""
    info = describe(ocr.engine, ocr.custom_version).get("custom_model")
    if not info:
        return {}
    return {
        "ocr_model_version": info.get("version"),
        "ocr_model_sha256": info.get("sha256"),
    }


# E2-04 (Phase 12D9): what the Source shows when a conversion is incomplete.
INCOMPLETE_OCR = "Nhận dạng tài liệu chưa hoàn tất do một vùng OCR gặp lỗi."
INCOMPLETE_PAGE = "Chuyển đổi tài liệu chưa hoàn tất do một trang không xử lý được."
NOT_STORED = "Tài liệu chưa được đưa vào kho tri thức."
PREVIOUS_KEPT = "Nội dung cũ của tài liệu vẫn được giữ nguyên."
PLEASE_RETRY = "Vui lòng thử lại."


class IncompleteConversionError(ValueError):
    """E2-04 (Phase 12D9): Docling's result is incomplete - an OCR region or a
    page could not be processed. Nothing is stored or embedded; the job fails
    without automatic retry (ValueError, D-08) and the user can retry it. The
    message is metadata only (no document text, no stderr)."""

    def __init__(
        self, *, ocr_region: bool, details: str, kept_previous: bool = False
    ) -> None:
        self.ocr_region, self.details, self.kept_previous = (
            ocr_region,
            details,
            kept_previous,
        )
        head = INCOMPLETE_OCR if ocr_region else INCOMPLETE_PAGE
        middle = PREVIOUS_KEPT if kept_previous else NOT_STORED
        super().__init__(f"{head} {middle} {PLEASE_RETRY} [{details}]")

    def keeping_previous(self) -> "IncompleteConversionError":
        """The same failure, for a Source whose earlier content stays."""
        return IncompleteConversionError(
            ocr_region=self.ocr_region, details=self.details, kept_previous=True
        )


def _ocr_region_failures(text: str) -> list[str]:
    """The OCR region failures (docling_patches.OcrRegionError, metadata only)
    named in ``text``."""
    from open_notebook.ocr.docling_patches import OCR_REGION_FAILED

    return re.findall(re.escape(OCR_REGION_FAILED) + r": [^;\n\]]*", text or "")


def reject_incomplete(result: Any, path: str) -> None:
    """E2-04 (Phase 12D9, owner decision): raise IncompleteConversionError unless
    Docling converted EVERY page without an error.

    Before 12D9 a partial result (``PARTIAL_SUCCESS``: a page or an OCR region
    Docling could not process) was stored with a warning; a Tesseract region
    whose recognition failed was even dropped with SUCCESS. Neither is stored
    as a complete Source any more: no content, no embedding, an earlier valid
    version of the Source stays as it is.
    """
    status = getattr(result, "status", None)
    name = str(getattr(status, "value", status) or "").lower() or None
    errors = list(getattr(result, "errors", None) or [])
    if name == "success" and not errors:
        return
    ocr = [
        found
        for e in errors
        for found in _ocr_region_failures(str(getattr(e, "error_message", "")))
    ]
    pages = sorted({e.page_no for e in errors if getattr(e, "page_no", None)})
    parts = [f"status={name}", f"errors={len(errors)}"]
    if pages:
        parts.append("pages=" + ",".join(str(p) for p in pages))
    if ocr:
        parts.append(ocr[0])
    else:
        modules = sorted(
            {str(getattr(e, "module_name", "") or "?") for e in errors} - {""}
        )
        if modules:
            parts.append("components=" + ",".join(modules))
    details = ", ".join(parts)
    logger.error(
        f"Docling result of {os.path.basename(path)} refused (incomplete): {details}"
    )
    raise IncompleteConversionError(ocr_region=bool(ocr), details=details)


def conversion_outcome(result: Any, path: str) -> dict[str, Any]:
    """Docling's own verdict on the conversion, made visible.

    Docling does not raise for a partial conversion (a page or an OCR region it
    could not process): it returns what it has with ``PARTIAL_SUCCESS`` and an
    error list. Since Phase 12D9 (E2-04) such a result is refused before this
    is reached (``reject_incomplete``); stored Sources record success / 0.
    """
    status = getattr(result, "status", None)
    name = str(getattr(status, "value", status) or "").lower() or None
    errors = len(getattr(result, "errors", None) or [])
    if errors or (name is not None and name != "success"):
        logger.warning(
            f"Docling finished {os.path.basename(path)} with status={name} and "
            f"{errors} error(s): part of the document may be missing from the result"
        )
    return {"conversion_status": name, "conversion_errors": errors}


def pipeline_identity(converter: Any) -> dict[str, Any]:
    """Layout / table models Docling actually configured (evidence for readiness)."""
    for pipeline in getattr(converter, "initialized_pipelines", {}).values():
        po = getattr(pipeline, "pipeline_options", None)
        if po is None:
            continue
        lo = getattr(po, "layout_options", None)
        to = getattr(po, "table_structure_options", None)
        mode = getattr(to, "mode", None)
        return {
            "layout_model": getattr(getattr(lo, "model_spec", None), "name", None),
            "table_model": getattr(to, "kind", None),
            "table_mode": getattr(mode, "value", mode),
        }
    return {}


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

    ocr = ocr.pinned()
    if ocr.custom_version is not None:
        # Custom engine: the frozen version is verified against its manifest.
        assert_engine_ready(ocr.engine, ocr.custom_version)
    elif ocr.engine != "rapidocr":
        assert_engine_ready(
            ocr.engine
        )  # explicit error, never a silent fallback (D-07)
    mime = await get_file_type(file_path)
    info = describe(ocr.engine, ocr.custom_version)
    logger.info(
        f"Extracting document via Docling with OCR engine={ocr.engine} "
        f"({info['docling_class']}, model={info['model']}, lang={info['lang']}, "
        f"device={info['device']}, "
        f"threads={ocr.num_threads or 'docling-default'}, full_page={ocr.force_full_page})"
    )
    content, meta = await asyncio.to_thread(convert_file, file_path, cc_config, ocr)
    logger.info(
        f"Docling OCR finished: engine={ocr.engine} actual_models={meta.get('ocr_models')} "
        f"in {meta.get('ocr_seconds')}s (ocr_scale={meta.get('ocr_scale')}, "
        f"scan_dpi={meta.get('scan_dpi')}, "
        f"page_orientation={meta.get('page_orientation')}, "
        f"orientation_checked_pages={meta.get('orientation_checked_pages')}, "
        f"page_orientation_limit={meta.get('page_orientation_limit')}, "
        f"conversion_status={meta.get('conversion_status')}, "
        f"conversion_errors={meta.get('conversion_errors')}, "
        f"orientation_corrected_pages={sorted(meta.get('rotated_pages') or {})})"
    )
    if ocr.custom_version is not None:
        # One version from the first page to the last, whatever was activated
        # meanwhile (evidence for docs/ocr/OCR_CUSTOM_MODEL_MANAGER.md).
        logger.info(
            f"OCR custom model used for the whole document: engine={ocr.engine} "
            f"version={meta.get('ocr_model_version')} "
            f"sha256={meta.get('ocr_model_sha256')} lang={info['lang']}"
        )
    expected = {
        "rapidocr": "RapidOcrModel",
        "tesseract": "TesseractOcrCliModel",
        "easyocr": "EasyOcrModel",
    }[catalog.get_engine(ocr.engine).docling_kind]
    if meta.get("ocr_models") and expected not in meta["ocr_models"]:
        # Defensive: Docling instantiated something other than what we asked for.
        raise ValueError(
            f"Docling used OCR model(s) {meta.get('ocr_models')} instead of {expected}; refusing the result."
        )
    return ExtractionOutput(
        content=content,
        title=os.path.basename(file_path),
        source_type="file",
        identified_type=mime,
        metadata=meta,
    )
