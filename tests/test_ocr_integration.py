"""Real-engine OCR integration tests — Docling's own OCR classes, no mocks.

What runs where (see docs/ocr/OCR_TEST_REPORT.md):
* OCR-stage tests need Docling + the engine runtime + installed models. They
  use Docling's official ``get_ocr_factory()`` with our options and run on the
  built-in synthetic Vietnamese sample (rendered to PDF/rotated on the fly).
  Point ``OCR_TEST_DATA_DIR`` at an OCR data dir with installed models
  (``python -m open_notebook.ocr.cli install-model <engine>``); otherwise the
  engine is skipped with the reason.
* Full-pipeline tests (Layout Heron + TableFormer + OCR) need Docling's Hugging
  Face models; enable with ``OCR_FULL_PIPELINE=1`` on a deployment machine.
"""

import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

pytest.importorskip("docling")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ocr"))

from open_notebook.ocr import catalog, metrics, paths  # noqa: E402
from open_notebook.ocr.status import assert_engine_ready  # noqa: E402

SAMPLE = ROOT / "open_notebook" / "ocr" / "assets" / "sample_vi.png"
GT = (ROOT / "open_notebook" / "ocr" / "assets" / "sample_vi.gt.txt").read_text(
    encoding="utf-8"
)
EXPECTED_CLASS = {
    "tesseract_fast": "TesseractOcrCliModel",
    "tesseract_best": "TesseractOcrCliModel",
    "easyocr": "EasyOcrModel",
    "rapidocr": "RapidOcrModel",
}


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


def _require(engine_id):
    try:
        assert_engine_ready(engine_id)
    except ValueError as e:
        pytest.skip(f"{engine_id} not installed here: {e}")


@pytest.fixture(scope="module")
def sample_pdfs(tmp_path_factory):
    from PIL import Image

    d = tmp_path_factory.mktemp("ocr")
    img = Image.open(SAMPLE).convert("RGB")
    img.save(d / "scan.pdf", resolution=150)
    img.rotate(90, expand=True, fillcolor=(255, 255, 255)).save(
        d / "rotated.pdf", resolution=150
    )
    return d


@pytest.mark.parametrize("engine_id", ["tesseract_fast", "tesseract_best", "easyocr"])
def test_docling_uses_selected_engine_and_reads_vietnamese(engine_id, sample_pdfs):
    import benchmark

    _require(engine_id)
    model = benchmark.make_ocr_model(engine_id)
    assert type(model).__name__ == EXPECTED_CLASS[engine_id]
    text, pages = benchmark.ocr_stage_text(model, sample_pdfs / "scan.pdf")
    assert pages == 1
    limit = 0.05 if engine_id.startswith("tesseract") else 0.15
    assert metrics.cer(GT, text) < limit, text
    assert (metrics.diacritic_accuracy(GT, text) or 0) >= (
        0.95 if engine_id.startswith("tesseract") else 0.8
    )
    assert "1234/2024" in text


def test_tesseract_fast_and_best_use_their_own_weights(sample_pdfs):
    import benchmark

    _require("tesseract_fast")
    _require("tesseract_best")
    fast = benchmark.make_ocr_model("tesseract_fast")
    best = benchmark.make_ocr_model("tesseract_best")
    assert fast._native_codes == ["fast/vie", "fast/eng"]
    assert best._native_codes == ["best/vie", "best/eng"]
    assert Path(fast._safe_tessdata_path) == paths.tessdata_dir()


def test_concurrent_jobs_with_different_engines_do_not_interfere(sample_pdfs):
    """Fast and Best in parallel threads (like worker jobs): no shared mutable env."""
    import benchmark

    _require("tesseract_fast")
    _require("tesseract_best")
    barrier = threading.Barrier(2)

    def run(engine_id):
        model = benchmark.make_ocr_model(engine_id)
        barrier.wait()
        return (
            engine_id,
            model._native_codes,
            benchmark.ocr_stage_text(model, sample_pdfs / "scan.pdf")[0],
        )

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(run, ["tesseract_fast", "tesseract_best"]))
    for engine_id, codes, text in results:
        assert codes[0].startswith(engine_id.split("_")[1])
        assert metrics.cer(GT, text) < 0.05


def test_rotated_scan_tesseract_osd(sample_pdfs):
    import benchmark

    _require("tesseract_best")
    text, _ = benchmark.ocr_stage_text(
        benchmark.make_ocr_model("tesseract_best"), sample_pdfs / "rotated.pdf"
    )
    # Reading order of a rotated page differs; recognition must not.
    assert metrics.word_recall(GT, text) >= 0.9


def test_rapidocr_option_reproduces_docling_auto():
    """D-03: the pinned RapidOCR options equal what OcrAutoOptions builds today."""
    from docling.models.stages.ocr import auto_ocr_model

    from open_notebook.ocr import runtime
    from open_notebook.ocr.options import build_ocr_options

    opts = build_ocr_options("rapidocr")
    assert type(opts).__name__ == "RapidOcrOptions"
    assert opts.lang == [] and opts.backend == runtime.rapidocr_backend()
    # Guard the assumption on Docling upgrades: Auto's order is
    # nemotron -> rapidocr(onnxruntime) -> easyocr -> rapidocr(torch).
    src = Path(auto_ocr_model.__file__).read_text(encoding="utf-8")
    i_onnx = src.index('backend="onnxruntime"')
    i_easy = src.index("import easyocr")
    i_torch = src.index('backend="torch"')
    assert i_onnx < i_easy < i_torch


def test_easyocr_forced_to_cpu_and_offline_models():
    from open_notebook.ocr.options import build_ocr_options

    opts = build_ocr_options("easyocr")
    assert opts.use_gpu is False
    assert opts.download_enabled is False
    assert opts.model_storage_directory == str(paths.easyocr_dir())
    assert opts.lang == ["vi", "en"]


@pytest.mark.skipif(
    os.environ.get("OCR_FULL_PIPELINE") != "1",
    reason="needs Docling HF models (set OCR_FULL_PIPELINE=1)",
)
@pytest.mark.parametrize("engine_id", list(catalog.ENGINE_IDS))
def test_full_pipeline_layout_table_unchanged(engine_id, sample_pdfs):
    from content_core import ContentCoreConfig

    from open_notebook.ocr.docling_extract import build_converter
    from open_notebook.ocr.options import OcrSettings

    if engine_id != "rapidocr":
        _require(engine_id)
    converter = build_converter(
        ContentCoreConfig(document_engine="docling"), OcrSettings(engine=engine_id)
    )
    result = converter.convert(str(sample_pdfs / "scan.pdf"))
    text = result.document.export_to_markdown()
    pipeline = next(iter(converter.initialized_pipelines.values()))
    assert type(pipeline.ocr_model).__name__ == EXPECTED_CLASS[engine_id]
    po = pipeline.pipeline_options
    assert getattr(po.layout_options.model_spec, "name", "") == "layout_heron"
    assert po.table_structure_options.kind == "docling_tableformer"
    assert text.strip()
