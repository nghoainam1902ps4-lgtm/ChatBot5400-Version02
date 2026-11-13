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


@pytest.fixture(autouse=True)
def _url_ingestion_enabled(monkeypatch):
    """This module covers behaviour WITH URL ingestion switched on (URL policy,
    engine routing). The deployment default is OFF (D-29); the switched-off
    behaviour is covered by tests/test_url_ingestion_switch.py."""
    monkeypatch.setenv("OPEN_NOTEBOOK_ENABLE_URL_INGESTION", "true")


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


# --- Behavioural parity of the post-processing (title, MIME, source type, cleanup)


def _fake_docling_output():
    from content_core.common import ExtractionOutput

    return ExtractionOutput(
        content="# Nội dung\n\nSố: 1234/2024",
        source_type="file",
        identified_type="",
        metadata={"docling_format": "markdown"},
    )


@pytest.fixture
def stubbed(monkeypatch, tmp_path):
    """Stub only the Docling conversion on BOTH sides; everything else is real."""
    import content_core.extraction as cc

    from open_notebook.ocr import docling_extract

    async def cc_docling(path, cfg):
        return _fake_docling_output()

    monkeypatch.setattr(cc, "extract_docling", cc_docling)
    monkeypatch.setattr(
        docling_extract,
        "convert_file",
        lambda path, cfg, ocr: (
            _fake_docling_output().content,
            {"docling_format": "markdown", "ocr_models": []},
        ),
    )
    monkeypatch.setattr(docling_extract, "assert_engine_ready", lambda e: None)
    monkeypatch.setenv("OCR_DATA_DIR", str(tmp_path / "ocr"))
    return cc, docling_extract


def _write_sample(tmp_path, name):
    from PIL import Image

    img = Image.new("RGB", (60, 40), "white")
    path = tmp_path / name
    if name.endswith(".pdf"):
        img.save(path, "PDF")
    else:
        img.save(path)
    return path


@pytest.mark.parametrize("name", ["scan.pdf", "photo.png", "photo.jpg"])
def test_file_output_matches_content_core(stubbed, tmp_path, name):
    import asyncio

    cc, de = stubbed
    path = _write_sample(tmp_path, name)
    cfg = ContentCoreConfig(document_engine="docling")
    theirs = asyncio.run(cc._extract_file(str(path), cfg))
    ours = asyncio.run(
        de.extract_with_selected_ocr(
            str(path), cfg, OcrSettings(engine="tesseract_best")
        )
    )
    for field in ("content", "title", "source_type", "identified_type"):
        assert getattr(ours, field) == getattr(theirs, field), field
    assert ours.metadata["docling_format"] == theirs.metadata["docling_format"]


@pytest.mark.parametrize(
    "name,mime", [("doc.pdf", "application/pdf"), ("scan.png", "image/png")]
)
def test_url_output_and_cleanup_match_content_core(
    stubbed, tmp_path, monkeypatch, name, mime
):
    import asyncio
    import shutil

    cc, de = stubbed
    src = _write_sample(tmp_path, name)
    downloaded = []

    async def fake_download(url):
        dst = tmp_path / f"dl-{len(downloaded)}{src.suffix}"
        shutil.copyfile(src, dst)
        downloaded.append(dst)
        return str(dst)

    async def fake_mime(url):
        return mime

    monkeypatch.setattr(cc, "_download_remote_file", fake_download)
    monkeypatch.setattr(cc, "detect_remote_mime", fake_mime)
    cfg = ContentCoreConfig(document_engine="docling")
    theirs = asyncio.run(cc._extract_url(f"https://example.org/{name}", cfg))
    ours = asyncio.run(
        de.extract_url_with_selected_ocr(
            f"https://example.org/{name}", cfg, OcrSettings(engine="easyocr")
        )
    )
    assert ours.source_type == theirs.source_type == "url"
    assert ours.identified_type == theirs.identified_type
    assert ours.content == theirs.content
    # Title = basename of the temp download on both sides (same naming scheme).
    assert theirs.title == downloaded[0].name and ours.title == downloaded[1].name
    assert not downloaded[0].exists() and not downloaded[1].exists()  # both cleaned up


def test_url_temp_file_removed_when_conversion_fails(stubbed, tmp_path, monkeypatch):
    import asyncio

    cc, de = stubbed
    src = _write_sample(tmp_path, "doc.pdf")
    dl = tmp_path / "dl.pdf"

    async def fake_download(url):
        dl.write_bytes(src.read_bytes())
        return str(dl)

    def boom(path, cfg, ocr):
        raise RuntimeError("docling failed")

    monkeypatch.setattr(cc, "_download_remote_file", fake_download)
    monkeypatch.setattr(de, "convert_file", boom)
    with pytest.raises(RuntimeError, match="docling failed"):
        asyncio.run(
            de.extract_url_with_selected_ocr(
                "https://example.org/doc.pdf",
                ContentCoreConfig(),
                OcrSettings(engine="easyocr"),
            )
        )
    assert not dl.exists()


def test_routing_matches_content_core_for_every_engine_setting(monkeypatch):
    """_docling_routes must agree with content-core's _route_for_mime."""
    import content_core.extraction as cc

    from open_notebook.ocr import docling_extract

    mimes = [
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/tiff",
        "image/bmp",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
    ]
    for engine in ("auto", "docling", "simple"):
        cfg = ContentCoreConfig(document_engine=engine)
        for mime in mimes:
            assert docling_extract._docling_routes(mime, engine) == (
                cc._route_for_mime(mime, cfg) == "docling"
            ), (engine, mime)


@pytest.mark.parametrize(
    "enabled,mime,expected",
    [
        (False, "application/pdf", False),  # OCR off: PDF stays on content-core
        (False, "image/png", True),  # images are always OCR'd -> selected engine
        (True, "application/pdf", True),
        (True, "text/plain", False),
    ],
)
def test_ocr_disabled_semantics(enabled, mime, expected):
    from open_notebook.ocr import docling_extract

    assert (
        docling_extract._decide(
            mime, "docling", OcrSettings(enabled=enabled, engine="tesseract_best")
        )
        is expected
    )


def test_simple_engine_never_uses_ocr_layer():
    from open_notebook.ocr import docling_extract

    for mime in ("application/pdf", "image/png"):
        assert (
            docling_extract._decide(mime, "simple", OcrSettings(engine="easyocr"))
            is False
        )


def test_content_core_internal_signatures_unchanged():
    import inspect

    import content_core.extraction as cc
    from content_core.processors.url import detect_remote_mime

    assert list(inspect.signature(cc._download_remote_file).parameters) == ["url"]
    assert list(inspect.signature(cc._route_for_mime).parameters) == ["mime", "cfg"]
    assert list(inspect.signature(detect_remote_mime).parameters) == ["url"]
    assert list(inspect.signature(cc._extract_file).parameters)[:2] == ["path", "cfg"]
