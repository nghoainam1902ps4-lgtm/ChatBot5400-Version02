"""Legal Document normalization in the ingestion pipeline (Phase 12, D-34).

MOCK VERIFIED level: the Docling conversion itself is replaced by a document
built with Docling's real ReadingOrderModel (tests/legal_harness.py); routing,
serialization, metadata, the source graph, the stored text and the admin API
are the production code.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("docling")

sys.path.insert(0, str(Path(__file__).parent))

import legal_harness as H  # noqa: E402

from open_notebook.ocr import docling_extract, legal_normalizer  # noqa: E402
from open_notebook.ocr import pdf_prep as pdf_prep_mod  # noqa: E402
from open_notebook.ocr.options import OcrSettings  # noqa: E402

FX = H.load_fixtures()


@pytest.fixture
def gate_on(monkeypatch):
    monkeypatch.setenv(legal_normalizer.ENV_FLAG, "true")


@pytest.fixture
def gate_off(monkeypatch):
    monkeypatch.delenv(legal_normalizer.ENV_FLAG, raising=False)


class _Cs:
    docling_ocr = True
    docling_ocr_engine = "rapidocr"
    docling_ocr_num_threads = None
    docling_ocr_force_full_page = False

    def __init__(self, mode=None):
        self.ocr_text_normalization = mode


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #


def test_settings_default_is_standard(gate_on):
    assert OcrSettings.from_content_settings(_Cs()).text_normalization == "standard"
    assert OcrSettings().legal_normalization is False


def test_settings_legal_needs_the_gate(gate_off):
    assert (
        OcrSettings.from_content_settings(_Cs("legal")).text_normalization == "standard"
    )


def test_settings_legal_with_gate(gate_on):
    s = OcrSettings.from_content_settings(_Cs("legal"))
    assert s.legal_normalization and s.engine == "rapidocr"


def test_legacy_record_without_field(gate_on):
    class Legacy:
        docling_ocr = True
        docling_ocr_engine = "rapidocr"

    assert OcrSettings.from_content_settings(Legacy()).text_normalization == "standard"


# --------------------------------------------------------------------------- #
# Routing: the default RapidOCR configuration must not skip normalization
# --------------------------------------------------------------------------- #


@pytest.fixture
def routing(monkeypatch):
    mimes = {"value": "application/pdf"}

    async def file_type(path):
        return mimes["value"]

    import content_core.content.identification as ident

    monkeypatch.setattr(ident, "get_file_type", file_type)
    monkeypatch.setattr(docling_extract, "_docling_routes", lambda mime, eng: True)
    monkeypatch.setattr(
        docling_extract.runtime, "auto_resolves_to_rapidocr", lambda: True
    )
    monkeypatch.setattr(docling_extract, "_auto_full_page_enabled", lambda: False)
    monkeypatch.delenv("OCR_RAPIDOCR_FORCE_CPU", raising=False)
    monkeypatch.delenv("OCR_RAPIDOCR_PERSISTENT", raising=False)
    return mimes


@pytest.mark.asyncio
async def test_default_config_standard_keeps_content_core(routing):
    assert (
        await docling_extract.should_use_native_ocr("x.pdf", "docling", OcrSettings())
        is False
    )


@pytest.mark.asyncio
async def test_default_config_legal_pdf_takes_docling_layer(routing):
    ocr = OcrSettings(text_normalization="legal")
    assert await docling_extract.should_use_native_ocr("x.pdf", "docling", ocr) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mime",
    [
        "image/png",
        "image/jpeg",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/html",
        "text/markdown",
    ],
)
async def test_legal_does_not_reroute_other_formats(routing, mime):
    routing["value"] = mime
    ocr = OcrSettings(text_normalization="legal")
    assert await docling_extract.should_use_native_ocr("x", "docling", ocr) is False


@pytest.mark.asyncio
async def test_legal_with_ocr_disabled_still_normalizes_pdf(routing):
    ocr = OcrSettings(enabled=False, text_normalization="legal")
    assert await docling_extract.should_use_native_ocr("x.pdf", "docling", ocr) is True


@pytest.mark.asyncio
@pytest.mark.parametrize("engine", ["tesseract_fast", "tesseract_best", "easyocr"])
async def test_selected_engines_unchanged(routing, engine):
    for mode in ("standard", "legal"):
        ocr = OcrSettings(engine=engine, text_normalization=mode)
        assert (
            await docling_extract.should_use_native_ocr("x.pdf", "docling", ocr) is True
        )


@pytest.mark.asyncio
async def test_url_pdf_legal(routing, monkeypatch):
    monkeypatch.setenv("OPEN_NOTEBOOK_ENABLE_URL_INGESTION", "true")

    async def remote(url):
        return "application/pdf"

    import content_core.processors.url as cc_url

    monkeypatch.setattr(cc_url, "detect_remote_mime", remote)
    assert (
        await docling_extract.should_use_native_ocr_for_url(
            "https://x/y.pdf", "docling", OcrSettings()
        )
        is False
    )
    ocr = OcrSettings(text_normalization="legal")
    assert (
        await docling_extract.should_use_native_ocr_for_url(
            "https://x/y.pdf", "docling", ocr
        )
        is True
    )


# --------------------------------------------------------------------------- #
# convert_file: OFF is byte-identical, ON normalizes, failures fall back
# --------------------------------------------------------------------------- #


@pytest.fixture
def converted(monkeypatch, tmp_path):
    fixture = FX.by_name("f02_clause_across_pages")
    doc = H.build_document(fixture)
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%synthetic\n")

    def fake_convert(path, cfg, ocr):
        result = SimpleNamespace(
            document=doc, status=SimpleNamespace(value="success"), errors=[]
        )
        return result, SimpleNamespace(initialized_pipelines={}), pdf_prep_mod.PdfPrep()

    monkeypatch.setattr(docling_extract, "convert_document", fake_convert)
    return doc, str(pdf), tmp_path


def _cfg(fmt="markdown"):
    return SimpleNamespace(docling_output_format=fmt)


def test_convert_file_standard_is_byte_identical(converted):
    doc, pdf, _ = converted
    out, meta = docling_extract.convert_file(pdf, _cfg(), OcrSettings())
    assert out == doc.export_to_markdown()
    assert not any(k.startswith("legal_") or k == "text_normalization" for k in meta)


def test_convert_file_legal(converted):
    doc, pdf, _ = converted
    out, meta = docling_extract.convert_file(
        pdf, _cfg(), OcrSettings(text_normalization="legal")
    )
    assert out == legal_normalizer.normalize_document(doc).content
    assert out != doc.export_to_markdown()
    assert meta["legal_normalization_status"] == "applied"
    assert meta["legal_normalizer_version"] == legal_normalizer.NORMALIZER_VERSION
    assert meta["legal_normalization_counts"]["join_across_pages"] == 1


def test_convert_file_legal_failure_keeps_standard(converted, monkeypatch):
    doc, pdf, _ = converted

    def boom(d, include_text=False):
        raise RuntimeError("bad document")

    monkeypatch.setattr(legal_normalizer, "normalize_document", boom)
    out, meta = docling_extract.convert_file(
        pdf, _cfg(), OcrSettings(text_normalization="legal")
    )
    assert out == doc.export_to_markdown()
    assert meta["legal_normalization_status"] == "failed"


def test_convert_file_legal_skips_non_pdf_and_non_markdown(converted):
    doc, _, tmp_path = converted
    png = tmp_path / "scan.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    out, meta = docling_extract.convert_file(
        str(png), _cfg(), OcrSettings(text_normalization="legal")
    )
    assert out == doc.export_to_markdown() and "legal_normalization_status" not in meta
    out, meta = docling_extract.convert_file(
        str(png), _cfg("html"), OcrSettings(text_normalization="legal")
    )
    assert out == doc.export_to_html()


# --------------------------------------------------------------------------- #
# Source graph: one text for display, chunking and embedding
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_source_graph_stores_normalized_text_and_embeds_it(
    monkeypatch, converted, gate_on
):
    from open_notebook.graphs import source as source_graph

    doc, pdf, _ = converted
    settings = SimpleNamespace(
        youtube_preferred_languages=None,
        default_content_processing_engine_url=None,
        default_content_processing_engine_doc="docling",
        docling_ocr=True,
        docling_formulas=False,
        docling_vision=False,
        docling_ocr_engine="rapidocr",
        docling_ocr_num_threads=None,
        docling_ocr_force_full_page=False,
        ocr_text_normalization="legal",
    )

    async def get_instance():
        return settings

    monkeypatch.setattr(source_graph.ContentSettings, "get_instance", get_instance)
    monkeypatch.setattr(
        source_graph.ContentSettings, "clear_instance", classmethod(lambda cls: None)
    )
    monkeypatch.setattr(source_graph, "_usable_engine", lambda e, k: e)
    monkeypatch.setattr(source_graph, "resolve_upload_path", lambda p: p)

    class _MM:
        async def get_defaults(self):
            return SimpleNamespace(default_speech_to_text_model=None)

    monkeypatch.setattr(source_graph, "ModelManager", _MM)
    calls = {"content_core": 0, "native": []}

    async def fake_cc(**kw):
        calls["content_core"] += 1
        raise AssertionError("content-core path must not be used")

    async def should_native(path, engine, ocr):
        return ocr.legal_normalization

    async def fake_native(path, cfg, ocr):
        calls["native"].append(ocr)
        from content_core.common import ExtractionOutput

        content, meta = docling_extract.convert_file(pdf, _cfg(), ocr)
        return ExtractionOutput(
            content=content,
            title="doc.pdf",
            source_type="file",
            identified_type="application/pdf",
            metadata=meta,
        )

    monkeypatch.setattr(source_graph, "extract_content", fake_cc)
    monkeypatch.setattr(source_graph, "should_use_native_ocr", should_native)
    monkeypatch.setattr(source_graph, "extract_with_selected_ocr", fake_native)

    out = await source_graph.content_process({"content_state": {"file_path": pdf}})
    extraction = out["extraction"]
    assert calls["native"][0].legal_normalization
    assert extraction.metadata["legal_normalization_status"] == "applied"

    class FakeSource:
        id = "source:1"
        title = "Processing..."
        full_text = None
        vectorized_with = None

        async def save(self):
            pass

        async def vectorize(self):
            FakeSource.vectorized_with = self.full_text

    async def get_source(sid):
        return FakeSource()

    monkeypatch.setattr(source_graph.Source, "get", get_source)
    saved = await source_graph.save_source(
        {
            "content_state": {"file_path": pdf},
            "extraction": extraction,
            "source_id": "source:1",
            "embed": True,
        }
    )
    assert saved["source"].full_text == extraction.content
    assert (
        FakeSource.vectorized_with == extraction.content
    )  # embedding reads the same text
    assert "<!-- image -->" not in saved["source"].full_text


def test_normalized_text_chunks_without_losing_content():
    from open_notebook.utils.chunking import chunk_text

    doc = H.build_document(FX.by_name("f06_multilevel_list"))
    content = legal_normalizer.normalize_document(doc).content
    chunks = chunk_text(content)
    joined = " ".join(chunks)
    for marker in ("1.1", "2.1", "đ)", "a.1)"):
        assert marker in joined


# --------------------------------------------------------------------------- #
# Admin API
# --------------------------------------------------------------------------- #


@pytest.fixture
def api_settings(monkeypatch):
    fake = SimpleNamespace(
        docling_ocr=True,
        docling_ocr_engine="rapidocr",
        docling_ocr_num_threads=None,
        docling_ocr_force_full_page=False,
        ocr_text_normalization="standard",
        saved=0,
    )

    async def update():
        fake.saved += 1

    fake.update = update

    async def get_settings():
        return fake

    monkeypatch.setattr("api.ocr_service._settings", get_settings)
    return fake


@pytest.mark.asyncio
async def test_api_refuses_legal_without_gate(api_settings, gate_off):
    from api import ocr_service
    from api.models import OcrConfigUpdate
    from open_notebook.exceptions import InvalidInputError

    with pytest.raises(InvalidInputError):
        await ocr_service.update_config(OcrConfigUpdate(ocr_text_normalization="legal"))
    assert api_settings.ocr_text_normalization == "standard" and api_settings.saved == 0
    cfg = await ocr_service.get_config()
    assert cfg.legal_normalization_available is False
    assert cfg.ocr_text_normalization_effective == "standard"


@pytest.mark.asyncio
async def test_api_sets_and_rolls_back_legal(api_settings, gate_on):
    from api import ocr_service
    from api.models import OcrConfigUpdate

    cfg = await ocr_service.update_config(
        OcrConfigUpdate(ocr_text_normalization="legal")
    )
    assert (
        cfg.ocr_text_normalization == "legal"
        and cfg.ocr_text_normalization_effective == "legal"
    )
    cfg = await ocr_service.update_config(
        OcrConfigUpdate(ocr_text_normalization="standard")
    )
    assert (
        cfg.ocr_text_normalization == "standard"
        and cfg.ocr_text_normalization_effective == "standard"
    )


@pytest.mark.asyncio
async def test_api_gate_closed_after_choice_means_standard(
    api_settings, gate_on, monkeypatch
):
    from api import ocr_service
    from api.models import OcrConfigUpdate

    await ocr_service.update_config(OcrConfigUpdate(ocr_text_normalization="legal"))
    monkeypatch.delenv(legal_normalizer.ENV_FLAG)
    cfg = await ocr_service.get_config()
    assert cfg.ocr_text_normalization == "legal"
    assert cfg.ocr_text_normalization_effective == "standard"


def test_api_rejects_unknown_mode():
    from pydantic import ValidationError

    from api.models import OcrConfigUpdate

    with pytest.raises(ValidationError):
        OcrConfigUpdate(ocr_text_normalization="ai")


def test_config_endpoint_is_admin_only():
    from api.routers import ocr

    deps = [d.dependency.__name__ for d in ocr.router.dependencies]
    assert "require_admin" in deps
