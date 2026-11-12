"""Real-engine OCR integration + full-pipeline acceptance — no mocks.

Two levels (docs/ocr/OCR_LOCAL_ACCEPTANCE.md):

* OCR stage — Docling's own OCR model classes (official ``get_ocr_factory()``)
  with our options on a synthetic Vietnamese sample. Needs Docling + engine
  runtime + installed models (``OCR_TEST_DATA_DIR`` = OCR data dir).
* Full pipeline — the production converter (Docling + Layout Heron +
  TableFormer accurate + selected OCR) on committed synthetic fixtures
  (tests/fixtures/ocr, ground truth in manifest.json): engine/model identity,
  Markdown content, reading order, key numbers, table count/shape, row cells,
  merged header cell, and text-layer-vs-OCR attribution.
  Enable with ``OCR_FULL_PIPELINE=1`` (needs Docling's Hugging Face models).

Strict acceptance: ``OCR_ACCEPTANCE_STRICT=1`` turns every missing
prerequisite (Docling, engine runtime, model, HF models) into a FAILED test
labelled "NOT VERIFIED" instead of a skip, and implies ``OCR_FULL_PIPELINE=1``.
``OCR_ACCEPTANCE_REPORT=<file.json>`` writes PASS / FAIL / NOT VERIFIED per test.
"""

import importlib.util
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

STRICT = os.environ.get("OCR_ACCEPTANCE_STRICT") == "1"
FULL_PIPELINE = STRICT or os.environ.get("OCR_FULL_PIPELINE") == "1"
REPORT_PATH = os.environ.get("OCR_ACCEPTANCE_REPORT")
_RESULTS: dict[str, dict] = {}


def not_verified(reason: str):
    """Missing prerequisite: explicit NOT VERIFIED (skip, or FAIL when strict)."""
    if STRICT:
        pytest.fail(f"NOT VERIFIED (strict acceptance): {reason}", pytrace=False)
    pytest.skip(f"NOT VERIFIED: {reason}")


if importlib.util.find_spec("docling") is None:
    if STRICT:
        raise RuntimeError("NOT VERIFIED (strict acceptance): Docling is not installed")
    pytest.skip("NOT VERIFIED: Docling is not installed", allow_module_level=True)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ocr"))

from open_notebook.ocr import catalog, metrics, paths  # noqa: E402
from open_notebook.ocr.status import assert_engine_ready  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "ocr"
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
        not_verified(f"{engine_id} not ready here: {e}")


@pytest.fixture(autouse=True)
def _record_result(request):
    """Collect PASS / FAIL / NOT VERIFIED per test for the acceptance report."""
    yield
    rep = getattr(request.node, "rep_call", None) or getattr(
        request.node, "rep_setup", None
    )
    if rep is None:
        return
    if rep.passed:
        status, detail = "PASS", ""
    elif rep.skipped:
        status, detail = (
            "NOT VERIFIED",
            str(rep.longrepr[-1])
            if isinstance(rep.longrepr, tuple)
            else str(rep.longrepr),
        )
    else:
        text = str(rep.longrepr)
        status = "NOT VERIFIED" if "NOT VERIFIED" in text else "FAIL"
        detail = text.splitlines()[-1][:500] if text else ""
    _RESULTS[request.node.nodeid] = {"status": status, "detail": detail}


@pytest.fixture(scope="session", autouse=True)
def _write_report():
    yield
    if REPORT_PATH and _RESULTS:
        summary = {
            k: sum(1 for r in _RESULTS.values() if r["status"] == k)
            for k in ("PASS", "FAIL", "NOT VERIFIED")
        }
        Path(REPORT_PATH).write_text(
            json.dumps(
                {"strict": STRICT, "summary": summary, "tests": _RESULTS},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


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


def test_easyocr_reader_actually_runs_on_cpu():
    """CPU mode is effective, not just configured: the EasyOCR reader's device."""
    import benchmark

    _require("easyocr")
    model = benchmark.make_ocr_model("easyocr")
    assert str(model.reader.device) == "cpu"


# =============================================================================
# Full pipeline acceptance (Layout Heron + TableFormer accurate + selected OCR)
# =============================================================================

MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
VIETNAMESE_ENGINES = ("tesseract_fast", "tesseract_best", "easyocr")
# Minimum quality on IMAGE-ONLY pages (calibrated from the Cloud OCR-stage
# benchmark; recorded in the report either way). RapidOCR's default model
# cannot read Vietnamese diacritics (see OCR_BENCHMARK.md), so for it only the
# numeric fields and the pipeline/table structure are asserted.
MAX_CER = {"tesseract_best": 0.08, "tesseract_fast": 0.10, "easyocr": 0.15}
MIN_FIELD_RECALL = {
    "tesseract_best": 1.0,
    "tesseract_fast": 0.9,
    "easyocr": 0.9,
    "rapidocr": 0.8,
}
NUMERIC_KEYS = ("amounts", "dates")


def _norm(s: str) -> str:
    return metrics.normalize(s).lower()


@pytest.fixture(scope="module")
def full_pipeline_enabled():
    if not FULL_PIPELINE:
        not_verified(
            "full pipeline not enabled (set OCR_FULL_PIPELINE=1 or OCR_ACCEPTANCE_STRICT=1)"
        )


_CONVERTERS: dict[tuple[str, bool], object] = {}
_INIT_ERRORS: dict[tuple[str, bool], str] = {}


def _converter(engine_id: str, do_ocr: bool = True):
    """The PRODUCTION converter (docling_extract.build_converter), initialised once."""
    from content_core import ContentCoreConfig
    from docling.datamodel.base_models import InputFormat

    from open_notebook.ocr.docling_extract import build_converter
    from open_notebook.ocr.options import OcrSettings

    key = (engine_id, do_ocr)
    if key in _INIT_ERRORS:
        not_verified(_INIT_ERRORS[key])
    if key not in _CONVERTERS:
        if engine_id != "rapidocr":
            _require(engine_id)
        conv = build_converter(
            ContentCoreConfig(document_engine="docling", docling_ocr=do_ocr),
            OcrSettings(engine=engine_id),
        )
        try:
            conv.initialize_pipeline(InputFormat.PDF)
        except Exception as e:  # HF models / RapidOCR weights unavailable, …
            _INIT_ERRORS[key] = (
                f"Docling pipeline for {engine_id} could not be initialised: {type(e).__name__}: {str(e)[:300]}"
            )
            not_verified(
                f"Docling pipeline for {engine_id} could not be initialised: {type(e).__name__}: {str(e)[:300]}"
            )
        _CONVERTERS[key] = conv
    return _CONVERTERS[key]


def _pdf_pipeline(conv):
    pipes = list(getattr(conv, "initialized_pipelines", {}).values())
    assert pipes, "no initialised Docling pipeline"
    return pipes[0]


def _tables(doc):
    out = []
    for t in doc.tables:
        cells = [
            (
                c.start_row_offset_idx,
                c.start_col_offset_idx,
                c.row_span,
                c.col_span,
                c.text,
            )
            for c in t.data.table_cells
        ]
        out.append({"rows": t.data.num_rows, "cols": t.data.num_cols, "cells": cells})
    return out


def _row_texts(table) -> list[list[str]]:
    rows: dict[int, list[tuple[int, str]]] = {}
    for r, c, _rs, _cs, text in table["cells"]:
        rows.setdefault(r, []).append((c, text))
    return [[t for _c, t in sorted(v)] for _r, v in sorted(rows.items())]


ENGINES = list(catalog.ENGINE_IDS)


@pytest.mark.parametrize("engine_id", ENGINES)
def test_pipeline_identity_heron_tableformer_and_engine(
    engine_id, full_pipeline_enabled
):
    """The pipeline really instantiates Layout Heron, TableFormer accurate and the selected OCR."""
    from docling.datamodel.pipeline_options import TableFormerMode

    pipe = _pdf_pipeline(_converter(engine_id))
    assert type(pipe.ocr_model).__name__ == EXPECTED_CLASS[engine_id]
    po = pipe.pipeline_options
    assert getattr(po.layout_options.model_spec, "name", None) == "layout_heron"
    assert po.table_structure_options.kind == "docling_tableformer"
    assert po.table_structure_options.mode == TableFormerMode.ACCURATE
    assert type(pipe.table_model).__name__ == "TableStructureModel"
    assert pipe.layout_model is not None


@pytest.mark.parametrize("fixture", sorted(MANIFEST))
@pytest.mark.parametrize("engine_id", ENGINES)
def test_full_pipeline_content(engine_id, fixture, full_pipeline_enabled):
    spec = MANIFEST[fixture]
    conv = _converter(engine_id)
    result = conv.convert(str(FIXTURES / spec["file"]))
    doc = result.document
    md = doc.export_to_markdown()
    nmd = _norm(md)
    ocr_pages = [not tl for tl in spec["text_layer"]]
    needs_ocr = any(ocr_pages)
    vietnamese_ok = engine_id in VIETNAMESE_ENGINES or not needs_ocr

    # 1. The OCR engine that ran is the selected one.
    assert type(_pdf_pipeline(conv).ocr_model).__name__ == EXPECTED_CLASS[engine_id]
    assert len(result.pages) == spec["pages"]

    # 2. Exact key numbers (amounts, dates); document numbers need diacritics.
    keys = list(NUMERIC_KEYS) + (["doc_numbers"] if vietnamese_ok else [])
    fields = [f for k in keys for f in spec["key_fields"].get(k, [])]
    if not vietnamese_ok:
        fields = [
            f for f in fields if f.isascii()
        ]  # e.g. "15 tháng 03 năm 2024" needs diacritics
    recall = metrics.field_recall(fields, md) if fields else None
    if recall is not None:
        need = 1.0 if not needs_ocr else MIN_FIELD_RECALL[engine_id]
        assert recall >= need, f"key-field recall {recall:.2f} < {need}: {md[:600]}"

    # 3. Reading order of headings / articles (rotated pages: content, not order).
    if vietnamese_ok and not spec["rotated"]:
        positions = [nmd.find(_norm(p)) for p in spec["ordered_phrases"]]
        assert all(p >= 0 for p in positions), (spec["ordered_phrases"], md[:800])
        assert positions == sorted(positions), f"reading order broken: {positions}"
    if spec["rotated"] and engine_id.startswith("tesseract"):
        assert metrics.word_recall(spec["ground_truth"], md) >= 0.85

    # 4. Character accuracy on OCR'd pages (Vietnamese engines).
    if (
        needs_ocr
        and engine_id in MAX_CER
        and not spec["rotated"]
        and not spec["tables"]
    ):
        assert metrics.cer(spec["ground_truth"], md) <= MAX_CER[engine_id]

    # 5. Tables: count, shape, row contents, merged header.
    tables = _tables(doc)
    for expect in spec["tables"]:
        cands = [t for t in tables if t["cols"] == expect["cols"]]
        assert cands, (
            f"no table with {expect['cols']} columns; got {[(t['rows'], t['cols']) for t in tables]}"
        )
        t = cands[0]
        assert expect["rows_min"] <= t["rows"] <= expect["rows_max"], (
            t["rows"],
            t["cols"],
        )
        rows = [" | ".join(r) for r in _row_texts(t)]
        for check in expect["row_checks"]:
            label_ok = vietnamese_ok or check["label"].isascii()
            match = [
                r
                for r in rows
                if all(c in r for c in check["cells"])
                and (not label_ok or _norm(check["label"]) in _norm(r))
            ]
            assert match, f"row {check} not found in {rows}"
        if vietnamese_ok:
            merged = [
                c for c in t["cells"] if _norm(expect["merged_header"]) in _norm(c[4])
            ]
            assert merged and max(c[3] for c in merged) >= 2, (
                f"merged header not detected: {merged}"
            )
    assert len(tables) >= len(spec["tables"])


@pytest.mark.parametrize("fixture", sorted(MANIFEST))
def test_text_layer_vs_ocr_attribution(fixture, full_pipeline_enabled):
    """With OCR OFF: text-layer pages still pass, image-only pages lose their text.

    Proves which passes above come from OCR and which only from the text layer.
    """
    spec = MANIFEST[fixture]
    result = _converter("rapidocr", do_ocr=False).convert(str(FIXTURES / spec["file"]))
    md = result.document.export_to_markdown()
    amounts = spec["key_fields"].get("amounts", [])
    if all(spec["text_layer"]):
        assert metrics.field_recall(amounts, md) in (None, 1.0), (
            "text layer alone must carry the numbers"
        )
    elif not any(spec["text_layer"]):
        assert (metrics.field_recall(amounts, md) or 0) == 0, (
            "image-only page produced text without OCR"
        )
