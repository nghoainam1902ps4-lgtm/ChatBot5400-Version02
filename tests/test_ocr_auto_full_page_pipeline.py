"""Real-pipeline checks of the automatic full-page rule (D-33).

Runs the PRODUCTION conversion (Docling + Layout Heron + TableFormer + the OCR
engine) on synthetic PDFs, so it needs the Docling stack, the engine and its
model. Like ``tests/test_ocr_integration.py`` it only runs when asked::

    OCR_FULL_PIPELINE=1 OCR_TEST_DATA_DIR=<ocr data dir> \
        uv run pytest tests/test_ocr_auto_full_page_pipeline.py

An engine that is not installed here is skipped, never faked.
"""

import collections
import os
import re
import sys
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ocr"))

pytestmark = pytest.mark.skipif(
    os.environ.get("OCR_FULL_PIPELINE") != "1",
    reason="full pipeline not enabled (set OCR_FULL_PIPELINE=1)",
)

ENGINES = ["rapidocr", "tesseract_fast", "tesseract_best", "easyocr", "tesseract_agri"]
# Share of the ground-truth words that must be back, letter for letter, once the
# rule applies. The default RapidOCR model writes no Vietnamese diacritics (its
# recall against accented text is below 50% on a clean scan too) and EasyOCR is
# experimental: for them the test is the AMOUNT of text that is back, and
# "exactly what the manual Force Full Page setting gives".
MIN_RECALL = {"tesseract_fast": 0.85, "tesseract_best": 0.90, "tesseract_agri": 0.90}
MIN_WORDS_BACK = 0.8  # of the number of words on the page, every engine


@pytest.fixture(scope="module", autouse=True)
def ocr_data_dir():
    data = os.environ.get("OCR_TEST_DATA_DIR")
    old = os.environ.get("OCR_DATA_DIR")
    if data:
        os.environ["OCR_DATA_DIR"] = data
    yield
    if old is None:
        os.environ.pop("OCR_DATA_DIR", None)
    else:
        os.environ["OCR_DATA_DIR"] = old


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    try:
        import generate_overlay_fixtures as fx

        cases = {c["name"]: c for c in fx.corpus()}
    except SystemExit as e:  # fonts for the synthetic scans are missing
        pytest.skip(str(e))
    out = tmp_path_factory.mktemp("overlay")
    files = {}
    for name in (
        "scan200_hidden_wm55",
        "scan300_1bit_hidden_wm55",
        "scan200_hidden",
        "scan200_only",
        "text_only",
        "text_wm55",
        "doc_mixed_digital_and_scan_wm",
    ):
        path = out / f"{name}.pdf"
        path.write_bytes(fx.build_pdf(cases[name]["pages"]))
        files[name] = (
            str(path),
            "\n".join(t for t in cases[name]["ground_truth"] if t),
        )
    return files


def _words(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text or "").lower()
    return [w for w in re.split(r"[^0-9a-zà-ỹđ]+", text) if w]


def _recall(truth: str, text: str) -> float:
    ref, hyp = collections.Counter(_words(truth)), collections.Counter(_words(text))
    return sum(min(n, hyp[w]) for w, n in ref.items()) / max(1, sum(ref.values()))


def _convert(path: str, engine: str, monkeypatch, flag: bool, full_page: bool = False):
    from content_core import ContentCoreConfig

    from open_notebook.ocr import pdf_prep
    from open_notebook.ocr.docling_extract import convert_file
    from open_notebook.ocr.options import OcrSettings

    monkeypatch.setenv(pdf_prep.AUTO_FULL_PAGE_ENV, "true" if flag else "false")
    pdf_prep._overlay_scan_cached.cache_clear()
    return convert_file(
        path,
        ContentCoreConfig(document_engine="docling", docling_ocr=True),
        OcrSettings(engine=engine, force_full_page=full_page),
    )


def _require(engine: str) -> None:
    from open_notebook.ocr.status import assert_engine_ready

    if engine == "rapidocr":
        pytest.importorskip("rapidocr")
        return
    try:
        assert_engine_ready(engine)
    except ValueError as e:
        pytest.skip(f"{engine} not ready here: {e}")


@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("case", ["scan200_hidden_wm55", "scan300_1bit_hidden_wm55"])
def test_content_under_the_watermark_is_back(corpus, monkeypatch, engine, case):
    _require(engine)
    path, truth = corpus[case]
    off, off_meta = _convert(path, engine, monkeypatch, flag=False)
    auto, auto_meta = _convert(path, engine, monkeypatch, flag=True)
    manual, _ = _convert(path, engine, monkeypatch, flag=False, full_page=True)
    page_words = len(_words(truth))
    # Before: Docling throws the recognised text away.
    assert _recall(truth, off) < 0.25
    assert len(_words(off)) < 0.25 * page_words
    assert "auto_full_page" not in off_meta
    # After: exactly what the manual Force Full Page setting gives.
    assert auto == manual
    assert auto_meta["auto_full_page"] is True
    assert auto_meta["ocr_mode_configured"] == "default"
    assert auto_meta["ocr_mode_effective"] == "full_page"
    assert len(_words(auto)) >= MIN_WORDS_BACK * page_words
    if engine in MIN_RECALL:
        assert _recall(truth, auto) >= MIN_RECALL[engine]
        assert _recall(truth, auto) > _recall(truth, off) + 0.4


@pytest.mark.parametrize(
    "case", ["scan200_hidden", "scan200_only", "text_only", "text_wm55"]
)
def test_ordinary_documents_give_the_same_bytes(corpus, monkeypatch, case):
    _require("tesseract_best")
    path, _ = corpus[case]
    off, _ = _convert(path, "tesseract_best", monkeypatch, flag=False)
    on, meta = _convert(path, "tesseract_best", monkeypatch, flag=True)
    assert on == off
    assert meta["auto_full_page"] is False and meta["ocr_mode_effective"] == "default"


def test_project_fixtures_give_the_same_bytes(monkeypatch):
    _require("tesseract_best")
    fixtures = sorted((ROOT / "tests" / "fixtures" / "ocr").glob("*.pdf"))
    assert fixtures
    for pdf in fixtures:
        off, _ = _convert(str(pdf), "tesseract_best", monkeypatch, flag=False)
        on, meta = _convert(str(pdf), "tesseract_best", monkeypatch, flag=True)
        assert on == off, pdf.name
        assert meta["auto_full_page"] is False, pdf.name


def test_mixed_document_is_converted_as_before(corpus, monkeypatch):
    _require("tesseract_best")
    path, _ = corpus["doc_mixed_digital_and_scan_wm"]
    off, _ = _convert(path, "tesseract_best", monkeypatch, flag=False)
    on, meta = _convert(path, "tesseract_best", monkeypatch, flag=True)
    assert on == off
    assert meta["auto_full_page"] is False
    assert meta["auto_full_page_reason"] == "mixed_document"
    assert meta["auto_full_page_risk_pages"] == 2
