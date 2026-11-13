"""Routing of the source graph's content_process with the OCR Engine Manager.

Default configuration must keep calling content-core unchanged; a selected
engine uses the Docling OCR layer; settings are re-read on every job (D-05).
"""

import pytest

from open_notebook.graphs import source as source_graph
from open_notebook.ocr.options import OcrSettings


@pytest.fixture(autouse=True)
def _url_ingestion_enabled(monkeypatch):
    """This module covers behaviour WITH URL ingestion switched on (URL policy,
    engine routing). The deployment default is OFF (D-29); the switched-off
    behaviour is covered by tests/test_url_ingestion_switch.py."""
    monkeypatch.setenv("OPEN_NOTEBOOK_ENABLE_URL_INGESTION", "true")


class _Settings:
    youtube_preferred_languages = None
    default_content_processing_engine_url = None
    default_content_processing_engine_doc = "docling"
    docling_ocr = True
    docling_formulas = False
    docling_vision = False
    docling_ocr_engine = "rapidocr"
    docling_ocr_num_threads = None
    docling_ocr_force_full_page = False


class _Out:
    title = "doc.pdf"
    content = "Nội dung"


@pytest.fixture
def wired(monkeypatch):
    calls = {"content_core": 0, "native": [], "loads": 0, "clears": 0}
    settings = _Settings()

    async def get_instance():
        calls["loads"] += 1
        return settings

    monkeypatch.setattr(source_graph.ContentSettings, "get_instance", get_instance)
    monkeypatch.setattr(
        source_graph.ContentSettings,
        "clear_instance",
        classmethod(lambda cls: calls.__setitem__("clears", calls["clears"] + 1)),
    )
    monkeypatch.setattr(source_graph, "_usable_engine", lambda e, k: e)
    # Routing tests only: the input guards have dedicated tests
    # (tests/test_background_job_security.py).
    monkeypatch.setattr(source_graph, "resolve_upload_path", lambda p: p)

    async def _url_ok(url):
        return None

    monkeypatch.setattr(source_graph, "validate_source_url", _url_ok)

    class _MM:
        async def get_defaults(self):
            class D:
                default_speech_to_text_model = None

            return D()

    monkeypatch.setattr(source_graph, "ModelManager", _MM)

    async def fake_extract_content(**kw):
        calls["content_core"] += 1
        return _Out()

    async def fake_native(path, cfg, ocr):
        calls["native"].append(ocr)
        return _Out()

    monkeypatch.setattr(source_graph, "extract_content", fake_extract_content)
    monkeypatch.setattr(source_graph, "extract_with_selected_ocr", fake_native)
    return calls, settings


@pytest.mark.asyncio
async def test_default_settings_use_content_core(wired, monkeypatch):
    calls, _ = wired

    async def never(*a):
        return False

    monkeypatch.setattr(source_graph, "should_use_native_ocr", never)
    await source_graph.content_process({"content_state": {"file_path": "/tmp/a.pdf"}})
    assert calls["content_core"] == 1 and calls["native"] == []


@pytest.mark.asyncio
async def test_selected_engine_uses_docling_ocr_layer(wired, monkeypatch):
    calls, settings = wired
    settings.docling_ocr_engine = "tesseract_best"
    seen = {}

    async def decide(path, engine, ocr):
        seen.update(path=path, engine=engine, ocr=ocr)
        return True

    monkeypatch.setattr(source_graph, "should_use_native_ocr", decide)
    await source_graph.content_process({"content_state": {"file_path": "/tmp/a.pdf"}})
    assert calls["content_core"] == 0
    assert calls["native"] == [OcrSettings(engine="tesseract_best")]
    assert seen["engine"] == "docling"


@pytest.mark.asyncio
async def test_url_scan_uses_selected_engine(wired, monkeypatch):
    calls, settings = wired
    settings.docling_ocr_engine = "tesseract_best"
    got = {}

    async def decide_url(url, engine, ocr):
        return url.endswith(".pdf")

    async def fake_url_native(url, cfg, ocr):
        got.update(url=url, ocr=ocr)
        return _Out()

    monkeypatch.setattr(source_graph, "should_use_native_ocr_for_url", decide_url)
    monkeypatch.setattr(source_graph, "extract_url_with_selected_ocr", fake_url_native)
    await source_graph.content_process({"content_state": {"url": "https://x/scan.pdf"}})
    assert got["url"] == "https://x/scan.pdf" and calls["content_core"] == 0
    await source_graph.content_process({"content_state": {"url": "https://x/page"}})
    assert calls["content_core"] == 1


@pytest.mark.asyncio
async def test_urls_and_text_never_take_ocr_path(wired, monkeypatch):
    calls, settings = wired
    settings.docling_ocr_engine = "easyocr"

    async def boom(*a):
        raise AssertionError("must not be consulted")

    async def not_a_scan(*a):
        return False

    monkeypatch.setattr(source_graph, "should_use_native_ocr", boom)
    monkeypatch.setattr(source_graph, "should_use_native_ocr_for_url", not_a_scan)
    await source_graph.content_process(
        {"content_state": {"url": "https://example.com"}}
    )
    await source_graph.content_process({"content_state": {"content": "plain text"}})
    assert calls["content_core"] == 2 and calls["native"] == []


@pytest.mark.asyncio
async def test_settings_reloaded_for_every_job(wired, monkeypatch):
    calls, _ = wired

    async def never(*a):
        return False

    monkeypatch.setattr(source_graph, "should_use_native_ocr", never)
    await source_graph.content_process({"content_state": {"file_path": "/tmp/a.pdf"}})
    await source_graph.content_process({"content_state": {"file_path": "/tmp/b.pdf"}})
    assert calls["clears"] == 2 and calls["loads"] == 2
