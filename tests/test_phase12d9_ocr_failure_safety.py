"""Phase 12D9, E2-04 (P1): a failed OCR region never reaches a Source as
complete content.

Windows (Phase 12E2): when the Tesseract RECOGNITION subprocess fails, upstream
Docling 2.129.0 drops the whole region and reports SUCCESS, errors=0; the Source
was completed with the region missing (13 of 49 tokens with Best, 63 of 100
with Agri v2, 445 of 1220 on a real document). A failed OSD run alone loses
nothing when recognition succeeds.

These tests inject faults with a wrapper in front of the REAL ``tesseract``
binary (it fails chosen invocations and otherwise ``exec``s the real one) and
run the REAL conversion path: Docling's threaded PDF pipeline (preprocessing,
OCR, layout post-processing, page assembly, reading order - only the layout
model is a stub that returns fixed regions, as its weights are not available
here), the application's ``convert_file``, the source graph, the
``process_source`` command, ``Source`` persistence and the ``embed_source``
queue on a REAL SurrealDB (the embedded engine of the surrealdb SDK, with the
application's migrations). The embedding model itself is not run (no provider
here): the check is that no embedding job is queued and that existing
``source_embedding`` rows stay untouched.

Nothing real is used: synthetic rendered pages, no network.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import textwrap
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("docling")

from open_notebook.ocr import docling_patches as P  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
REAL = shutil.which("tesseract")


def _tessdata() -> str | None:
    if not REAL or not Path(FONT).is_file():
        return None
    out = subprocess.run([REAL, "--list-langs"], capture_output=True, text=True)
    where = re.search(r'"([^"]+)"', out.stdout + out.stderr)
    langs = (out.stdout + out.stderr).split()
    return where.group(1) if where and "vie" in langs and "osd" in langs else None


TESSDATA = _tessdata()
pytestmark = [
    pytest.mark.skipif(
        TESSDATA is None,
        reason="needs the tesseract binary with 'vie' + 'osd' and DejaVu",
    ),
    pytest.mark.skipif(os.name != "posix", reason="the fault wrapper uses fcntl"),
]

# Each region of a rendered page is one line: "Vung <WORD> 2024", <WORD> unique.
WORDS = {
    (1, 1): "ALPHA",
    (1, 2): "BRAVO",
    (1, 3): "CHARLIE",
    (2, 1): "LIMA",
    (2, 2): "KILO",
    (3, 1): "OSCAR",
    (3, 2): "HOTEL",
}
# Regions rendered as a much longer line: their crop is the only one wider than
# WIDE_PX, so the wrapper can fail exactly them (pages are OCRed in any order).
WIDE = {(2, 1)}
WIDE_PX = 600

WRAPPER = """#!{python}
import fcntl, json, os, signal, sys, time
REAL, PLAN, LOG, COUNT = {real!r}, {plan!r}, {log!r}, {count!r}
a = sys.argv[1:]
if a[:1] == ["--version"]:
    os.execv(REAL, [REAL, *a])
if a[:1] == ["--list-langs"]:
    print('List of available languages in "x" (3):')
    print("eng"); print("osd"); print("vie")
    sys.exit(0)
kind = "osd" if "--psm" in a and a[a.index("--psm") + 1] == "0" else "recognition"
with open(COUNT + "." + kind, "a+") as fh:
    fcntl.flock(fh, fcntl.LOCK_EX)
    fh.seek(0)
    n = len(fh.read())
    fh.write("x")
with open(PLAN) as fh:
    steps = json.load(fh).get(kind, [])
outcome = steps[n] if n < len(steps) else "ok"
wide = json.load(open(PLAN)).get("fail_wider_than")
if kind == "recognition" and wide:
    img = [x for x in a if x.endswith(".png")][0]
    with open(img, "rb") as fh:
        width = int.from_bytes(fh.read(24)[16:20], "big")
    outcome = "fail_exit" if width > wide else "ok"
with open(LOG, "a") as fh:
    fcntl.flock(fh, fcntl.LOCK_EX)
    fh.write(json.dumps({{"kind": kind, "n": n, "outcome": outcome, "argv": a}}) + "\\n")
data = os.path.join(a[a.index("--tessdata-dir") + 1] if "--tessdata-dir" in a else "", "vie.traineddata")
if outcome == "ok" and kind == "osd":  # upright (no orientation gate in front)
    print("Page number: 0\\nOrientation in degrees: 0\\nRotate: 0\\n"
          "Orientation confidence: 9.9\\nScript: Latin\\nScript confidence: 9.9")
    sys.exit(0)
if outcome == "ok":
    os.execv(REAL, [REAL, *a])
if outcome == "fail_data":  # what Tesseract writes when it cannot read a model file
    sys.stderr.write("Error opening data file " + data + "\\n"
                     "Please make sure the TESSDATA_PREFIX environment variable is set\\n"
                     "Failed loading language 'vie'\\nTesseract couldn't load any languages!\\n"
                     "Could not initialize tesseract.\\n")
    sys.exit(1)
if outcome == "fail_exit":
    sys.stderr.write("SECRET-STDERR-LINE internal failure\\n")
    sys.exit(1)
if outcome == "crash":
    os.kill(os.getpid(), signal.SIGSEGV)
if outcome == "hang":
    time.sleep(60)
if outcome == "empty":  # recognition ran, no word found
    print("level\\tpage_num\\tblock_num\\tpar_num\\tline_num\\tword_num\\tleft\\ttop\\twidth\\theight\\tconf\\ttext")
    sys.exit(0)
sys.exit(3)
"""


class Rig:
    """One fault-injecting Tesseract: wrapper + plan + invocation log."""

    def __init__(
        self,
        root: Path,
        plan: dict[str, list[str]],
        with_model: bool = True,
        lang: tuple[str, ...] = ("vie",),
    ):
        root.mkdir(parents=True, exist_ok=True)
        self.root, self.lang = root, lang
        self.tessdata = root / "tessdata"
        self.tessdata.mkdir()
        for src in Path(str(TESSDATA)).iterdir():  # models, configs/tsv, ...
            if with_model or src.name != "vie.traineddata":
                (self.tessdata / src.name).symlink_to(src)
        self.plan = root / "plan.json"
        self.plan.write_text(json.dumps(plan))
        self.log = root / "calls.jsonl"
        self.wrapper = root / "tesseract"
        self.wrapper.write_text(
            WRAPPER.format(
                python=sys.executable,
                real=REAL,
                plan=str(self.plan),
                log=str(self.log),
                count=str(root / "count"),
            )
        )
        self.wrapper.chmod(0o755)

    def calls(self, kind: str = "recognition") -> list[dict[str, Any]]:
        if not self.log.is_file():
            return []
        rows = [json.loads(line) for line in self.log.read_text().splitlines()]
        return [r for r in rows if r["kind"] == kind]

    def options(self) -> Any:
        from docling.datamodel.pipeline_options import (
            OcrMode,
            PdfPipelineOptions,
            TesseractCliOcrOptions,
        )

        return PdfPipelineOptions(
            do_ocr=True,
            do_table_structure=False,
            ocr_options=TesseractCliOcrOptions(
                lang=list(self.lang),
                path=str(self.tessdata),
                tesseract_cmd=str(self.wrapper),
                mode=OcrMode.LAYOUT_REGIONS,
            ),
        )


def render(path: Path, pages: list[list[tuple[str, bool]]]) -> dict[int, list[Any]]:
    """Scanned pages (image only, 300 dpi): one line of text per region.
    Returns the layout regions (PDF points, top-left) per page number."""
    from docling_core.types.doc import BoundingBox
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(FONT, 48)
    k = 72 / 300
    images, regions = [], {}
    for page_no, texts in enumerate(pages, start=1):
        img = Image.new("L", (2480, 3508), 255)
        draw = ImageDraw.Draw(img)
        boxes, y = [], 200
        for word, wide in texts:
            text = f"Vung {word} 2024" + (
                " 2025 2026 2027 2028 2029 2030" if wide else ""
            )
            draw.text((160, y), text, font=font, fill=0)
            width = int(font.getlength(text))
            boxes.append(
                BoundingBox(
                    l=130 * k, t=(y - 20) * k, r=(190 + width) * k, b=(y + 60) * k
                )
            )
            y += 330
        images.append(img)
        regions[page_no] = boxes
    images[0].save(path, "PDF", resolution=300, save_all=True, append_images=images[1:])
    return regions


class _StubLayout:
    """Stands in for Layout Heron (weights not available here): the fixed
    regions of the rendered page, found by document name."""

    requires_layout_postprocessing = True

    def __init__(self, registry: dict[str, dict[int, list[Any]]]) -> None:
        self.registry = registry

    def __call__(self, conv_res: Any, page_batch: Any) -> Any:
        from docling.datamodel.base_models import Cluster, LayoutPrediction
        from docling_core.types.doc import DocItemLabel

        regions = self.registry[Path(str(conv_res.input.file)).name]
        for page in page_batch:
            page.predictions.layout = LayoutPrediction(
                clusters=[
                    Cluster(
                        id=i, label=DocItemLabel.TEXT, bbox=b, confidence=0.9, cells=[]
                    )
                    for i, b in enumerate(regions.get(page.page_no, []))
                ]
            )
            yield page


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    """The application's conversion path with the stub layout; engines map to
    rigs (one fault-injecting Tesseract per engine id)."""
    import docling.pipeline.standard_pdf_pipeline as spp

    from open_notebook.ocr import docling_extract, pdf_prep

    registry: dict[str, dict[int, list[Any]]] = {}
    rigs: dict[str, Rig] = {}

    class _Factory:
        def create_instance(self, **_kw: Any) -> Any:
            return _StubLayout(registry)

    monkeypatch.setattr(spp, "get_layout_factory", lambda **_kw: _Factory())
    monkeypatch.setattr(
        docling_extract,
        "build_pipeline_options",
        lambda _cc, ocr, scale=None, for_image=False: rigs[ocr.engine].options(),
    )
    monkeypatch.setattr(docling_extract, "assert_engine_ready", lambda *a, **k: None)
    monkeypatch.setattr(pdf_prep, "prepare", lambda *_a, **_k: pdf_prep.PdfPrep())
    # raising=False: the same tests run on a candidate without E2-04 (RED)
    monkeypatch.setattr(P, "RETRY_BACKOFF_SECONDS", (0.01, 0.01), raising=False)
    P.apply()  # what build_ocr_options does for every Tesseract engine

    class Pipeline:
        def __init__(self) -> None:
            self.registry, self.rigs = registry, rigs
            self.uploads = tmp_path / "uploads"
            self.uploads.mkdir()

        def rig(self, engine: str, plan: dict[str, list[str]], **kw: Any) -> Rig:
            rigs[engine] = Rig(tmp_path / f"rig_{engine}", plan, **kw)
            return rigs[engine]

        def document(self, name: str, pages: list[list[tuple[int, int]]]) -> Path:
            path = self.uploads / name
            registry[name] = render(
                path, [[(WORDS[k], k in WIDE) for k in page] for page in pages]
            )
            return path

        def convert(
            self, path: Path, engine: str = "tesseract_best"
        ) -> tuple[str, dict]:
            from content_core import ContentCoreConfig

            from open_notebook.ocr.options import OcrSettings

            return docling_extract.convert_file(
                str(path), ContentCoreConfig(), OcrSettings(engine=engine)
            )

    return Pipeline()


THREE_PAGES = [[(1, 1), (1, 2)], [(2, 1), (2, 2)], [(3, 1), (3, 2)]]


def _words(text: str, keys) -> dict[tuple[int, int], bool]:
    return {k: WORDS[k] in text for k in keys}


# --------------------------------------------------------------------------- #
# A. The Docling level: retry, fail the region, never drop it
# --------------------------------------------------------------------------- #


def test_control_upstream_drops_the_failed_region_and_reports_success(
    pipeline, monkeypatch
):
    """RED evidence (v1.2.0 / 4587eb7): upstream's OCR loop skips the region
    whose recognition failed; the conversion is SUCCESS with errors=0 and the
    stored text lacks it."""
    from docling.models.stages.ocr.tesseract_ocr_cli_model import TesseractOcrCliModel

    monkeypatch.setattr(TesseractOcrCliModel, "__call__", P.call_upstream())
    pipeline.rig("tesseract_best", {"recognition": ["ok", "fail_exit"]})
    path = pipeline.document("upstream.pdf", [[(1, 1), (1, 2), (1, 3)]])
    content, meta = pipeline.convert(path)
    assert meta["conversion_status"] == "success" and meta["conversion_errors"] == 0
    assert _words(content, [(1, 1), (1, 2), (1, 3)]) == {
        (1, 1): True,
        (1, 2): False,  # silently lost
        (1, 3): True,
    }


def test_a_transient_failure_is_retried_on_the_same_crop_and_model(pipeline):
    """A model file that could not be read this time (it is there): retried,
    with the same command line, language, model folder and crop image."""
    rig = pipeline.rig("tesseract_best", {"recognition": ["fail_data", "ok"]})
    path = pipeline.document("transient.pdf", [[(1, 1), (1, 2)]])
    content, meta = pipeline.convert(path)
    assert meta["conversion_status"] == "success"
    assert all(_words(content, [(1, 1), (1, 2)]).values())
    calls = rig.calls()
    assert [c["outcome"] for c in calls] == ["fail_data", "ok", "ok"]
    assert calls[0]["argv"] == calls[1]["argv"]  # same image file, -l, --tessdata-dir
    assert "-l" in calls[0]["argv"] and "--tessdata-dir" in calls[0]["argv"]


@pytest.mark.parametrize("fault", ["crash", "fail_exit"])
def test_a_crash_or_an_error_exit_is_retried(pipeline, fault):
    rig = pipeline.rig("tesseract_best", {"recognition": [fault, "ok"]})
    path = pipeline.document(f"{fault}.pdf", [[(1, 1)]])
    content, _ = pipeline.convert(path)
    assert WORDS[(1, 1)] in content
    assert [c["outcome"] for c in rig.calls()] == [fault, "ok"]


def test_a_hung_tesseract_times_out_and_is_retried(pipeline, monkeypatch):
    monkeypatch.setattr(P, "RECOGNITION_TIMEOUT_SECONDS", 2.0, raising=False)
    rig = pipeline.rig("tesseract_best", {"recognition": ["hang", "ok"]})
    path = pipeline.document("hang.pdf", [[(1, 1)]])
    content, _ = pipeline.convert(path)
    assert WORDS[(1, 1)] in content
    assert [c["outcome"] for c in rig.calls()] == ["hang", "ok"]


def test_a_region_that_always_fails_rejects_the_document(pipeline):
    """First region fine, the second fails three times: the page fails, the
    result is refused - no partial content comes back."""

    rig = pipeline.rig(
        "tesseract_best", {"recognition": ["ok", "fail_exit", "fail_exit", "fail_exit"]}
    )
    path = pipeline.document("always.pdf", [[(1, 1), (1, 2), (1, 3)]])
    with pytest.raises(ValueError, match="chưa hoàn tất") as err:
        pipeline.convert(path)
    assert str(err.value).startswith(
        "Nhận dạng tài liệu chưa hoàn tất do một vùng OCR gặp lỗi. "
        "Tài liệu chưa được đưa vào kho tri thức. Vui lòng thử lại."
    )
    assert "page 1, region 2" in str(err.value) and "attempts 3" in str(err.value)
    assert "category exit_nonzero, exit code 1" in str(err.value)
    assert [c["outcome"] for c in rig.calls()][:4] == [
        "ok",
        "fail_exit",
        "fail_exit",
        "fail_exit",
    ]
    assert isinstance(err.value, ValueError)  # the job stops, no automatic retry


def test_a_middle_page_failure_is_named_and_refused(pipeline):
    # page 2 region 1 (the only wide crop) fails every time; pages 1 / 3 fine
    rig = pipeline.rig("tesseract_best", {"fail_wider_than": WIDE_PX})
    path = pipeline.document("middle.pdf", THREE_PAGES)
    with pytest.raises(ValueError, match="chưa hoàn tất") as err:
        pipeline.convert(path)
    assert "page 2, region 1" in str(err.value) and "attempts 3" in str(err.value)
    # Docling fails every page of the OCR batch the failing page was in
    assert re.search(r"pages=[0-9,]*2", str(err.value)) or "status=failure" in str(
        err.value
    )
    assert sum(c["outcome"] == "fail_exit" for c in rig.calls()) == 3


def test_every_page_failing_is_refused_not_retried_as_a_job(pipeline):
    """Docling raises ConversionError when no page succeeds; the OCR reason is
    kept and the error is a permanent one (ValueError)."""

    pipeline.rig("tesseract_best", {"recognition": ["fail_exit"] * 3})
    path = pipeline.document("single.pdf", [[(1, 1)]])
    with pytest.raises(ValueError, match="chưa hoàn tất") as err:
        pipeline.convert(path)
    assert "status=failure" in str(err.value) and "page 1, region 1" in str(err.value)


def test_a_missing_model_file_is_not_retried(pipeline):
    """The model file is not there: a configuration error - one attempt, the
    real Tesseract's own failure, category model_missing."""

    rig = pipeline.rig("tesseract_best", {"recognition": []}, with_model=False)
    path = pipeline.document("nomodel.pdf", [[(1, 1)]])
    with pytest.raises(ValueError, match="chưa hoàn tất") as err:
        pipeline.convert(path)
    assert "category model_missing" in str(err.value) and "attempts 1" in str(err.value)
    assert len(rig.calls()) == 1


def test_osd_failure_alone_keeps_the_region_and_the_document(pipeline, caplog):
    """OSD fails, recognition works (explicit language, as every engine of the
    application): nothing is lost, the document is converted. Its log line
    carries no raw stderr."""
    rig = pipeline.rig("tesseract_best", {"osd": ["fail_exit", "fail_data"]})
    path = pipeline.document("osd.pdf", [[(1, 1), (1, 2)]])
    with caplog.at_level(logging.ERROR):
        content, meta = pipeline.convert(path)
    assert meta["conversion_status"] == "success"
    assert all(_words(content, [(1, 1), (1, 2)]).values())
    assert [c["outcome"] for c in rig.calls("osd")] == ["fail_exit", "fail_data"]
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "OSD failed" in logged and "[stderr withheld:" in logged
    assert (
        "SECRET-STDERR-LINE" not in logged and "Error opening data file" not in logged
    )


def test_osd_failure_in_auto_script_mode_fails_the_region_instead_of_dropping_it(
    pipeline,
):
    """Without a language list upstream skips a region whose OSD failed (the
    script is unknown). The patch fails it: refused, not silently shorter."""

    rig = pipeline.rig("tesseract_best", {"osd": ["fail_exit"]}, lang=())
    path = pipeline.document("auto.pdf", [[(1, 1), (1, 2)]])
    with pytest.raises(ValueError, match="chưa hoàn tất") as err:
        pipeline.convert(path)
    assert "category osd_failed_auto_script_other" in str(err.value)
    assert rig.calls("recognition") == []  # region 1 never recognised blind


def test_ocr_that_succeeds_without_text_is_not_a_failure(pipeline):
    """Recognition ran and found nothing (E2-01 short tokens, blank crops): no
    execution failure, the document is converted with the other regions."""
    pipeline.rig("tesseract_best", {"recognition": ["empty"]})
    path = pipeline.document("empty.pdf", [[(1, 1), (1, 2)]])
    content, meta = pipeline.convert(path)
    assert meta["conversion_status"] == "success"
    assert _words(content, [(1, 1), (1, 2)]) == {(1, 1): False, (1, 2): True}


def test_two_concurrent_conversions_keep_their_own_outcome(pipeline):
    pipeline.rig(
        "tesseract_best", {"recognition": ["ok", "fail_exit", "fail_exit", "fail_exit"]}
    )
    pipeline.rig("tesseract_fast", {"recognition": ["fail_data", "ok"]})
    bad = pipeline.document("bad.pdf", [[(1, 1), (1, 2)]])
    good = pipeline.document("good.pdf", [[(2, 1), (2, 2)]])
    start = threading.Barrier(2)

    def run(path: Path, engine: str) -> Any:
        start.wait(timeout=30)
        try:
            return pipeline.convert(path, engine)
        except ValueError as e:
            return e

    with ThreadPoolExecutor(2) as pool:
        a = pool.submit(run, bad, "tesseract_best")
        b = pool.submit(run, good, "tesseract_fast")
        bad_res, good_res = a.result(timeout=300), b.result(timeout=300)
    assert type(bad_res).__name__ == "IncompleteConversionError"
    assert "page 1, region 2" in str(bad_res)
    content, meta = good_res
    assert meta["conversion_status"] == "success"
    assert all(_words(content, [(2, 1), (2, 2)]).values())


# --------------------------------------------------------------------------- #
# B. The application level: Source persistence and the embedding queue on a
#    real (embedded) SurrealDB, through the process_source command
# --------------------------------------------------------------------------- #


@pytest.fixture
def database(monkeypatch, tmp_path):
    """An embedded SurrealDB file with the application's migrations."""
    import surreal_commands.core.service as cmd_service
    from surrealdb import AsyncSurreal

    url = f"surrealkv://{tmp_path / 'db'}"
    for key, value in {
        "SURREAL_URL": url,
        "SURREAL_USER": "root",
        "SURREAL_PASSWORD": "root",
        "SURREAL_NAMESPACE": "open_notebook",
        "SURREAL_DATABASE": "open_notebook",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(cmd_service, "_command_service", None)  # reads the URL again

    async def boot() -> None:
        db = AsyncSurreal(url)
        await db.query("DEFINE USER root ON ROOT PASSWORD 'root' ROLES OWNER;")
        await db.close()
        from open_notebook.database.async_migrate import AsyncMigrationManager

        await AsyncMigrationManager().run_migration_up()

    # tests/db_isolation.py refuses every endpoint but the run's planned one;
    # this test's OWN embedded database file (under tmp_path) is let through -
    # every other endpoint still meets the guard.
    from open_notebook.database import repository

    guarded = repository.AsyncSurreal
    assert url.startswith(f"surrealkv://{tmp_path}")

    def embedded_only(u: Any, *a: Any, **k: Any) -> Any:
        if u == url:
            return getattr(guarded, "original", guarded)(u, *a, **k)
        return guarded(u, *a, **k)

    monkeypatch.setattr(repository, "AsyncSurreal", embedded_only)
    asyncio.run(boot())
    sys.path.insert(0, str(ROOT))
    import commands.embedding_commands  # noqa: F401 - registers embed_source

    yield url
    monkeypatch.setattr(cmd_service, "_command_service", None)


@pytest.fixture
def worker(pipeline, database, monkeypatch):
    """Runs the real process_source command on an uploaded PDF."""
    from open_notebook.graphs import source as graph
    from open_notebook.ocr.options import OcrSettings

    monkeypatch.setattr("open_notebook.config.UPLOADS_FOLDER", str(pipeline.uploads))

    async def native(*_a: Any, **_k: Any) -> bool:
        return True

    monkeypatch.setattr(graph, "should_use_native_ocr", native)
    monkeypatch.setattr(
        OcrSettings,
        "from_content_settings",
        classmethod(lambda cls, _s: OcrSettings(engine="tesseract_best")),
    )

    class Worker:
        async def new_source(self, path: Path, full_text: str | None = None) -> Any:
            from open_notebook.domain.notebook import Asset, Source

            src = Source(title="Processing...", asset=Asset(file_path=str(path)))
            src.full_text = full_text
            await src.save()
            return src

        async def embeddings(self, source_id: str) -> list[dict[str, Any]]:
            from open_notebook.database.repository import ensure_record_id, repo_query

            return await repo_query(
                "SELECT order, content FROM source_embedding WHERE source = $s ORDER BY order;",
                {"s": ensure_record_id(source_id)},
            )

        async def embed_jobs(self, source_id: str) -> list[dict[str, Any]]:
            from open_notebook.database.repository import repo_query

            rows = await repo_query("SELECT name, args, status FROM command;")
            return [
                r
                for r in rows
                if r.get("name") == "embed_source"
                and (r.get("args") or {}).get("source_id") == source_id
            ]

        async def process(self, source_id: str, path: Path, embed: bool = True) -> Any:
            from commands.source_commands import (
                SourceProcessingInput,
                process_source_command,
            )

            return await process_source_command(
                SourceProcessingInput(
                    source_id=source_id,
                    content_state={"file_path": str(path)},
                    notebook_ids=[],
                    transformations=[],
                    embed=embed,
                )
            )

        async def reload(self, source_id: str) -> Any:
            from open_notebook.domain.notebook import Source

            return await Source.get(source_id)

    return Worker()


def test_a_complete_conversion_is_stored_and_queued_for_embedding(pipeline, worker):
    pipeline.rig("tesseract_best", {"recognition": ["fail_data", "ok"]})  # one retry
    path = pipeline.document("complete.pdf", [[(1, 1), (1, 2)]])

    async def run() -> tuple[Any, Any, list]:
        src = await worker.new_source(path)
        out = await worker.process(str(src.id), path)
        return (
            out,
            await worker.reload(str(src.id)),
            await worker.embed_jobs(str(src.id)),
        )

    out, stored, jobs = asyncio.run(run())
    assert out.success
    assert all(_words(stored.full_text, [(1, 1), (1, 2)]).values())
    assert len(jobs) == 1 and jobs[0]["status"] == "new"


def test_a_new_source_whose_region_fails_gets_no_content_and_no_embedding(
    pipeline, worker
):
    pipeline.rig("tesseract_best", {"recognition": ["ok"] + ["fail_exit"] * 3})
    path = pipeline.document("newfail.pdf", [[(1, 1), (1, 2)]])

    async def run() -> tuple[Any, Any, list, list]:
        src = await worker.new_source(path)
        with pytest.raises(ValueError, match="chưa hoàn tất") as err:
            await worker.process(str(src.id), path)
        sid = str(src.id)
        return (
            err.value,
            await worker.reload(sid),
            await worker.embed_jobs(sid),
            await worker.embeddings(sid),
        )

    err, stored, jobs, rows = asyncio.run(run())
    assert "Tài liệu chưa được đưa vào kho tri thức." in str(err)
    assert stored.full_text is None  # nothing partial stored
    assert stored.title == "Processing..."
    assert jobs == [] and rows == []


def test_a_failed_reprocess_keeps_the_previous_content_and_embeddings(pipeline, worker):
    from open_notebook.database.repository import ensure_record_id, repo_query

    pipeline.rig("tesseract_best", {"recognition": ["fail_exit"] * 3})
    path = pipeline.document("reprocess.pdf", [[(1, 1)]])
    previous = "Nội dung hợp lệ trước đó: Điều 1. Phạm vi điều chỉnh."

    async def run() -> tuple[Any, Any, list, list]:
        src = await worker.new_source(path, full_text=previous)
        sid = str(src.id)
        for order, content in enumerate(["đoạn 1", "đoạn 2"]):
            await repo_query(
                "CREATE source_embedding SET source = $s, order = $o, content = $c, "
                "embedding = [0.1, 0.2, 0.3];",
                {"s": ensure_record_id(sid), "o": order, "c": content},
            )
        with pytest.raises(ValueError, match="chưa hoàn tất") as err:
            await worker.process(sid, path)
        return (
            err.value,
            await worker.reload(sid),
            await worker.embeddings(sid),
            await worker.embed_jobs(sid),
        )

    err, stored, rows, jobs = asyncio.run(run())
    assert "Nội dung cũ của tài liệu vẫn được giữ nguyên." in str(err)
    assert "Tài liệu chưa được đưa vào kho tri thức." not in str(err)
    assert stored.full_text == previous
    assert rows == [
        {"order": 0, "content": "đoạn 1"},
        {"order": 1, "content": "đoạn 2"},
    ]
    assert jobs == []


def test_a_partial_result_with_data_is_refused_before_storage(
    pipeline, worker, monkeypatch
):
    """PARTIAL_SUCCESS (a page Docling could not process, any engine) with a
    document that HAS text: refused all the same - never stored as complete."""
    from docling.datamodel.base_models import (
        ConversionStatus,
        DoclingComponentType,
        ErrorItem,
    )
    from docling_core.types.doc import DocItemLabel, DoclingDocument

    from open_notebook.ocr import docling_extract

    path = pipeline.document("partial.pdf", [[(1, 1)]])

    class _Result:
        status = ConversionStatus.PARTIAL_SUCCESS
        errors = [
            ErrorItem(
                component_type=DoclingComponentType.MODEL,
                module_name="layout",
                error_message="Page 2 failed: RuntimeError",
                page_no=2,
            )
        ]
        document = DoclingDocument(name="x")

    _Result.document.add_text(label=DocItemLabel.TEXT, text="Trang 1 vẫn còn")

    class _Converter:
        initialized_pipelines: dict = {}

    from open_notebook.ocr import pdf_prep

    monkeypatch.setattr(
        docling_extract,
        "convert_document",
        lambda *_a, **_k: (_Result(), _Converter(), pdf_prep.PdfPrep()),
    )

    async def run() -> tuple[Any, Any]:
        src = await worker.new_source(path)
        with pytest.raises(ValueError, match="chưa hoàn tất") as err:
            await worker.process(str(src.id), path)
        return err.value, await worker.reload(str(src.id))

    err, stored = asyncio.run(run())
    assert str(err).startswith(
        "Chuyển đổi tài liệu chưa hoàn tất do một trang không xử lý được."
    )
    assert "status=partial_success" in str(err) and "pages=2" in str(err)
    assert "components=layout" in str(err)
    assert "RuntimeError" not in str(err)  # another component's message is not shown
    assert stored.full_text is None


def test_logs_and_the_source_error_carry_no_stderr_and_no_document_text(
    pipeline, worker, caplog
):
    from loguru import logger

    pipeline.rig("tesseract_best", {"recognition": ["ok"] + ["fail_exit"] * 3})
    path = pipeline.document("logs.pdf", [[(1, 1), (1, 2)]])
    lines: list[str] = []
    sink = logger.add(lambda m: lines.append(str(m)), level="DEBUG")
    try:

        async def run() -> Any:
            src = await worker.new_source(path)
            with pytest.raises(ValueError, match="chưa hoàn tất") as err:
                await worker.process(str(src.id), path)
            return err.value

        with caplog.at_level(logging.DEBUG):
            err = asyncio.run(run())
    finally:
        logger.remove(sink)
    logged = "\n".join(lines) + "\n".join(r.getMessage() for r in caplog.records)
    for secret in ("SECRET-STDERR-LINE", WORDS[(1, 1)], WORDS[(1, 2)]):
        assert secret not in logged, secret
        assert secret not in str(err), secret
    for field in (
        "page 1",
        "region 2",
        "category exit_nonzero",
        "exit code 1",
        "attempt",
    ):
        assert field in logged, field


# --------------------------------------------------------------------------- #
# C. Classification, guards, faithfulness to upstream
# --------------------------------------------------------------------------- #


def _cpe(code: int, stderr: bytes, cmd: list[str] | None = None) -> Any:
    return subprocess.CalledProcessError(code, cmd or ["tesseract"], stderr=stderr)


def test_failure_categories_and_what_is_retried(tmp_path):
    (tmp_path / "best").mkdir()
    (tmp_path / "best" / "vie.traineddata").write_bytes(b"x")
    cmd = [
        "t",
        "-l",
        "best/vie",
        "--tessdata-dir",
        str(tmp_path),
        "img.png",
        "stdout",
        "tsv",
    ]
    missing = [
        "t",
        "-l",
        "best/eng",
        "--tessdata-dir",
        str(tmp_path),
        "i",
        "stdout",
        "tsv",
    ]
    data = b"Error opening data file x\nFailed loading language 'vie'\n"
    cases = [
        (_cpe(1, data, cmd), "data_file_unreadable", True),
        (_cpe(1, data, missing), "model_missing", False),
        (_cpe(1, b"std::bad_alloc\n"), "out_of_memory", True),
        (
            _cpe(1, b"Error in pixReadStream: Unknown format\n"),
            "image_unreadable",
            True,
        ),
        (_cpe(-11, b""), "killed_by_signal", True),
        (_cpe(1, b"whatever\n"), "exit_nonzero", True),
        (subprocess.TimeoutExpired(["t"], 1.0), "timeout", True),
        (FileNotFoundError(2, "no such file"), "executable_missing", False),
        (PermissionError(13, "denied"), "executable_not_permitted", False),
        (OSError(5, "I/O error"), "os_error", True),
    ]
    for exc, category, retry in cases:
        got = P.classify_recognition_failure(exc)
        assert (got.category, got.retryable) == (category, retry), (exc, got)
    assert P.classify_recognition_failure(_cpe(1, data, cmd)).exit_code == 1
    assert (
        P.stderr_category(b"x" * 10 + b"Error opening data file")
        == "data_file_unreadable"
    )
    assert P.stderr_category(None) == "no_stderr"
    assert P._withheld(b"SECRET\n") == "[stderr withheld: 7 bytes, other]"


def test_only_the_tail_of_stderr_is_read(monkeypatch):
    monkeypatch.setattr(P, "STDERR_TAIL_BYTES", 16)
    assert P._stderr_tail(b"A" * 100 + b"0123456789abcdef") == "0123456789abcdef"


def test_ocr_region_error_is_not_a_called_process_error():
    """Upstream catches CalledProcessError and skips the region: the region
    error must travel past that handler."""
    err = P.OcrRegionError(
        page_no=2,
        region=3,
        engine="best/vie",
        category="timeout",
        exit_code=None,
        attempts=3,
    )
    assert not isinstance(err, subprocess.CalledProcessError)
    assert str(err) == (
        "OCR_REGION_FAILED: page 2, region 3, engine Tesseract (best/vie), "
        "category timeout, exit code None, attempts 3"
    )


def _tree(fn: Any) -> ast.FunctionDef:
    node = ast.parse(textwrap.dedent(inspect.getsource(fn))).body[0]
    assert isinstance(node, ast.FunctionDef)
    node.name, node.returns = "F", None
    for a in node.args.args:
        a.annotation = None
    body = [n for n in node.body if not isinstance(n, (ast.ImportFrom, ast.Import))]
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(getattr(body[0], "value", None), ast.Constant)
    ):
        body = body[1:]
    node.body = body
    return node


def test_the_ocr_loop_is_upstream_except_the_two_e2_04_changes():
    ours, theirs = _tree(P._tesseract_call), _tree(P.call_upstream())

    def handlers(tree: ast.AST) -> list[ast.ExceptHandler]:
        return [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]

    # 1. the OSD failure: stderr withheld; auto-script: the region fails
    o_osd, t_osd = handlers(ours)[0], handlers(theirs)[0]
    assert ast.unparse(t_osd.body[0].value.args[-1]) == "exc.stderr"  # type: ignore[attr-defined]
    assert ast.unparse(o_osd.body[0].value.args[-1]) == "_withheld(exc.stderr)"  # type: ignore[attr-defined]
    assert ast.unparse(t_osd.body[1]) == "if self._auto_script:\n    continue"
    assert ast.unparse(o_osd.body[1]) == (
        "if self._auto_script:\n"
        "    raise _osd_region_error(self, page, ocr_rect_i, exc.stderr) from None"
    )
    o_osd.body[0].value.args[-1] = t_osd.body[0].value.args[-1]  # type: ignore[attr-defined]
    o_osd.body[1] = t_osd.body[1]
    # 2. recognition: upstream's try / except-continue becomes _recognize_region
    t_try = [
        n
        for n in ast.walk(theirs)
        if isinstance(n, ast.Try) and "self._run_tesseract" in ast.unparse(n.body[0])
    ]
    assert len(t_try) == 1
    assert ast.unparse(t_try[0].handlers[0].body[-1]) == "continue"
    o_rec = [
        n
        for n in ast.walk(ours)
        if isinstance(n, ast.Assign) and "_recognize_region" in ast.unparse(n)
    ]
    assert [ast.unparse(n) for n in o_rec] == [
        "df_result = _recognize_region(self, fname, df_osd, page=page, "
        "region=ocr_rect_i, rect=ocr_rect)"
    ]
    diagnostic = [
        n
        for n in ast.walk(ours)
        if isinstance(n, ast.If) and ast.unparse(n.test) == "_evidence is not None"
    ]
    assert [ast.unparse(n) for n in diagnostic] == [
        "if _evidence is not None:\n    _evidence.recognition_cell(page.page_no, ocr_rect_i, cell)"
    ]

    class Swap(ast.NodeTransformer):
        def visit_Assign(self, node: ast.Assign) -> Any:
            return t_try[0] if node is o_rec[0] else node

        def visit_If(self, node: ast.If) -> Any:
            return None if node is diagnostic[0] else self.generic_visit(node)

    ours = Swap().visit(ours)
    assert ast.dump(ours, include_attributes=False) == ast.dump(
        theirs, include_attributes=False
    )


def test_recognize_region_retries_exactly_the_policy(monkeypatch):
    monkeypatch.setattr(P, "RETRY_BACKOFF_SECONDS", (0.01, 0.01))
    calls = []

    class _Model:
        _native_codes = ["best/vie"]

        def _run_tesseract(self, fname, osd):
            calls.append((fname, osd))
            raise _cpe(1, b"x")

    class _Page:
        page_no = 4

    with pytest.raises(P.OcrRegionError) as err:
        P._recognize_region(_Model(), "crop.png", None, page=_Page(), region=0)
    assert len(calls) == 1 + P.RECOGNITION_RETRIES == 3
    assert set(calls) == {("crop.png", None)}
    assert (err.value.page_no, err.value.region, err.value.attempts) == (4, 1, 3)


def test_guards_cover_the_ocr_loop(monkeypatch):
    from docling.models.stages.ocr.tesseract_ocr_cli_model import TesseractOcrCliModel

    from open_notebook.ocr import compat

    P.apply()
    assert P.is_applied()
    status = P.status()
    assert status["patches"] == [P.PATCH_ID, P.REGION_PATCH_ID] and status["applied"]
    assert compat.source_fingerprint(P.CALL_TARGET) == P.CALL_SHA256
    assert compat.DOCLING_FINGERPRINTS[P.CALL_TARGET] == P.CALL_SHA256
    monkeypatch.setattr(TesseractOcrCliModel, "__call__", P.call_upstream())
    assert not P.is_applied()  # both targets are required
    monkeypatch.setattr(P, "CALL_SHA256", "0" * 64)
    with pytest.raises(P.TsvPatchError, match="OCR region failure patch"):
        P.apply()
    assert not P.is_applied()


def test_the_status_command_names_the_e2_04_patch(capsys):
    """The Windows gate reads it from ``ocr.cli status`` (text and --json)."""
    from open_notebook.ocr import cli

    assert cli.main(["status", "--no-db"]) == 0
    text = capsys.readouterr().out
    line = next(x for x in text.splitlines() if x.startswith("docling Tesseract"))
    assert "E2-04" in line and "ready (applied at conversion time)" in line
    assert cli.main(["status", "--no-db", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    tess = [r for r in rows if "docling_tsv_patch" in r]
    assert tess and all(
        P.REGION_PATCH_ID in r["docling_tsv_patch"]["patches"] for r in tess
    )
