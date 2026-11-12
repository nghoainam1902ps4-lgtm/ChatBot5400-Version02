"""Parity guard for DECISIONS D-02.

Our minimal layer must build exactly the Docling options content-core builds
(``content_core.processors.document.docling.extract_docling``) and differ ONLY
in ``ocr_options`` (+ ``accelerator_options`` when threads are set). If a
content-core upgrade changes its options, this test fails and the layer must be
re-aligned (or removed if content-core gained OCR options).
"""

import pytest

pytest.importorskip("docling")

from content_core import ContentCoreConfig  # noqa: E402

from open_notebook.ocr.docling_extract import build_pipeline_options  # noqa: E402
from open_notebook.ocr.options import OcrSettings  # noqa: E402

_ALLOWED_DIFF = {"ocr_options", "accelerator_options"}


def _content_core_options(monkeypatch, cfg):
    from content_core.processors.document import docling as cc_docling

    captured = {}

    class Recorder:
        def __init__(self, format_options=None, **kw):
            captured["format_options"] = format_options

        def convert(self, source):
            raise RuntimeError("stop")

    monkeypatch.setattr(cc_docling, "DocumentConverter", Recorder)
    import asyncio

    with pytest.raises(RuntimeError, match="stop"):
        asyncio.run(cc_docling.extract_docling("x.pdf", cfg))
    from docling.datamodel.base_models import InputFormat

    return captured["format_options"][InputFormat.PDF].pipeline_options


@pytest.mark.parametrize(
    "engine", ["rapidocr", "tesseract_fast", "tesseract_best", "easyocr"]
)
@pytest.mark.parametrize(
    "flags",
    [
        dict(docling_ocr=True, docling_formulas=False, docling_vision=False),
        dict(docling_ocr=False, docling_formulas=True, docling_vision=True),
    ],
)
def test_only_ocr_options_differ(monkeypatch, engine, flags, tmp_path):
    monkeypatch.setenv("OCR_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TESSDATA_PREFIX", str(tmp_path / "models" / "tesseract"))
    cfg = ContentCoreConfig(document_engine="docling", **flags)
    theirs = _content_core_options(monkeypatch, cfg).model_dump()
    ours = build_pipeline_options(cfg, OcrSettings(engine=engine)).model_dump()
    diff = {k for k in set(theirs) | set(ours) if theirs.get(k) != ours.get(k)}
    assert diff <= {"ocr_options"}, diff
    # Layout (Heron) and TableFormer untouched.
    assert ours["layout_options"] == theirs["layout_options"]
    assert ours["table_structure_options"] == theirs["table_structure_options"]


def test_threads_only_add_accelerator_options(monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TESSDATA_PREFIX", str(tmp_path / "models" / "tesseract"))
    cfg = ContentCoreConfig(document_engine="docling")
    theirs = _content_core_options(monkeypatch, cfg).model_dump()
    ours = build_pipeline_options(
        cfg, OcrSettings(engine="tesseract_best", num_threads=2)
    ).model_dump()
    diff = {k for k in set(theirs) | set(ours) if theirs.get(k) != ours.get(k)}
    assert diff <= _ALLOWED_DIFF
    assert ours["accelerator_options"]["num_threads"] == 2
    # Device left to Docling (layout/table devices are not forced).
    assert (
        ours["accelerator_options"]["device"] == theirs["accelerator_options"]["device"]
    )


def test_images_keep_docling_defaults_except_ocr(monkeypatch, tmp_path):
    """content-core sets no image format option: only ocr_options may differ."""
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    monkeypatch.setenv("OCR_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TESSDATA_PREFIX", str(tmp_path / "models" / "tesseract"))
    cfg = ContentCoreConfig(
        document_engine="docling",
        docling_vision=True,
        docling_formulas=True,
        docling_ocr=False,
    )
    ours = build_pipeline_options(
        cfg, OcrSettings(engine="easyocr"), for_image=True
    ).model_dump()
    defaults = PdfPipelineOptions().model_dump()
    diff = {k for k in set(ours) | set(defaults) if ours.get(k) != defaults.get(k)}
    assert diff <= {"ocr_options"}, diff


def test_content_core_url_helpers_still_exist():
    """extract_url_with_selected_ocr reuses content-core's own URL helpers."""
    from content_core.extraction import _download_remote_file
    from content_core.processors.url import detect_remote_mime

    assert callable(_download_remote_file) and callable(detect_remote_mime)
