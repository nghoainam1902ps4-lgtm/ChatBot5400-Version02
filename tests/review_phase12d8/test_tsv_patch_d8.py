"""Phase 12D8 final review: the Tesseract TSV text patch (E0-07) and what
Docling does with the OCR cells AFTER it.

Review only: runtime code is not modified. Conventions of this directory:
``xfail(strict=True)`` = expected safe behaviour that fails today (finding id
in the reason); ``test_verified_*`` / ``test_control_*`` = passes, records
something the review checked for itself.

Unlike tests/test_ocr_tesseract_tsv_text.py (which re-runs Tesseract a second
time to get the "raw" words), the real-Tesseract checks here compare the raw
TSV bytes of THE SAME invocation that produced the cells.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import io
import random
import re
import shutil
import subprocess
import sys
import textwrap
import threading
from pathlib import Path
from typing import Any, cast

import pytest

pytest.importorskip("docling")

from docling.datamodel.accelerator_options import AcceleratorOptions  # noqa: E402
from docling.datamodel.pipeline_options import TesseractCliOcrOptions  # noqa: E402
from docling.models.stages.ocr import (
    tesseract_ocr_cli_model as upstream_mod,  # noqa: E402
)

from open_notebook.ocr import docling_patches as P  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
STRUCTURE = [
    "1\t1\t0\t0\t0\t0\t0\t0\t600\t80\t-1\t",
    "2\t1\t1\t0\t0\t0\t10\t10\t580\t60\t-1\t",
    "3\t1\t1\t1\t0\t0\t10\t10\t580\t60\t-1\t",
    "4\t1\t1\t1\t1\t0\t10\t10\t580\t60\t-1\t",
]

# The owner's list (section 4 of the 12D8 brief) plus forms pandas would parse.
TOKENS = [
    "1.", "123.", "2024.", "9.", "12.50", "NA", "N/A", "NULL", "NaN", "true",
    "false", "True", "FALSE", "0001", "000123", "Điều", "khoản", "đ)", "1e5",
    "inf", "-inf", "Infinity", "+5", "-5", ".5", "5.", "0x1F", "1_000", "1,234",
    "１２３", '"', '"abc', "a\"b", "'", "#", "\\N", "1.0", "1e400", "-0", "00",
    "9999999999999999999999", "None", "null", "n/a", "nan", "#N/A", "<NA>",
    "-1.#IND", "1.#QNAN", "NaT", "…", "½", "12/2024/NĐ-CP", "é", "TRUE",
]  # fmt: skip


def _tsv(words: list[str], nl: str = "\n", conf: str = "96.25") -> str:
    rows = [HEADER, *STRUCTURE]
    for i, w in enumerate(words, 1):
        rows.append(f"5\t1\t1\t1\t1\t{i}\t{10 + 60 * i}\t12\t50\t40\t{conf}\t{w}")
    return nl.join(rows) + nl


def _upstream_parse(raw: str) -> Any:
    import pandas as pd

    return pd.read_csv(io.StringIO(raw), quoting=csv.QUOTE_NONE, sep="\t")


def _filtered_texts(df: Any) -> list[str]:
    """Exactly the upstream filter + ``str(row['text'])`` of ``__call__``."""
    kept = df[df["text"].notna() & (df["text"].apply(str).str.strip() != "")]
    return [str(row["text"]) for _, row in kept.iterrows()]


def _raw_word_fields(raw: str) -> list[str]:
    """Text field of every TSV row whose text is not blank, straight from the bytes."""
    out = []
    for line in raw.replace("\r\n", "\n").split("\n")[1:]:
        fields = line.split("\t")
        if len(fields) == 12 and fields[11].strip() != "":
            out.append(fields[11])
    return out


@pytest.fixture(autouse=True)
def _patch_state():
    """Leave the Docling class exactly as this test found it."""
    cls = upstream_mod.TesseractOcrCliModel
    saved = cls.__dict__["_run_tesseract"]
    yield
    setattr(cls, "_run_tesseract", saved)  # noqa: B010


# --------------------------------------------------------------------------- #
# Parse level: every token, alone (numeric-only crop) and in a mixed line
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("nl", ["\n", "\r\n"])
@pytest.mark.parametrize("token", TOKENS)
def test_verified_single_token_crop_keeps_the_raw_field(token, nl):
    raw = _tsv([token], nl=nl)
    assert _filtered_texts(P.read_tesseract_tsv(raw)) == [token]


def test_verified_mixed_line_keeps_every_field_in_order():
    raw = _tsv(TOKENS)
    assert _filtered_texts(P.read_tesseract_tsv(raw)) == TOKENS == _raw_word_fields(raw)


def test_verified_blank_and_whitespace_text_rows_are_filtered_like_upstream():
    raw = _tsv(["0001", " ", "", " ", "9."])
    assert _filtered_texts(P.read_tesseract_tsv(raw)) == ["0001", "9."]


def test_verified_fuzz_other_columns_are_upstream_and_text_is_the_raw_field():
    """2000 random TSVs (junk in numeric columns, short rows): every column
    except ``text`` has the upstream dtype and values, parse errors are the
    same errors, and ``text`` is the raw field."""
    rng = random.Random(12)
    junk = ["NA", "nan", "", "-1", "96.25", "x", "1e3", "inf", "0x10", "5", "  7",
            "7  ", "1.5", "TRUE", "None", "-0", "1,5"]  # fmt: skip
    for _ in range(2000):
        rows, texts = [HEADER], []
        for _i in range(rng.randint(1, 6)):
            f = [
                rng.choice(junk) if rng.random() < 0.15 else str(rng.randint(0, 500))
                for _k in range(11)
            ]
            word = rng.choice(TOKENS)
            f.append(word)
            if rng.random() < 0.05:
                f = f[: rng.randint(1, 11)]
            rows.append("\t".join(f))
            texts.append(word if len(f) == 12 else None)
        raw = "\n".join(rows) + "\n"
        try:
            a, ea = _upstream_parse(raw), None
        except Exception as e:  # noqa: BLE001 - compared below
            a, ea = None, type(e).__name__
        try:
            b, eb = P.read_tesseract_tsv(raw), None
        except Exception as e:  # noqa: BLE001 - compared below
            b, eb = None, type(e).__name__
        assert ea == eb, raw
        if a is None:
            continue
        assert list(a.columns) == list(b.columns) and list(a.index) == list(b.index)
        for c in a.columns:
            if c != "text":
                assert a[c].dtype == b[c].dtype and a[c].equals(b[c]), (c, raw)
        if all(t is not None for t in texts) and list(b.columns) == HEADER.split("\t"):
            assert [str(x) for x in b["text"]] == texts, raw


def test_control_d8_08_extra_field_rows_type_the_implicit_index_differently():
    """D8-08 (P4, no observable effect on cells): when EVERY row has a 13th
    field (a tab inside the text - Tesseract never writes one), pandas takes the
    first field as the index. Upstream types it with its default NA strings
    (float, NaN for an empty field); the patch reads it with no NA strings
    (str, "") because ``na_values`` is keyed by column NAME and the implicit
    index has none. Columns and the text are still the upstream ones."""
    raw = HEADER + "\n" + "202\t1\t1\t1\t1\t1\t0\t0\t9\t9\t90\ta\tb\n\t1\t1\t1\t1\t2\t0\t0\t9\t9\t90\tc\td\n"
    a, b = _upstream_parse(raw), P.read_tesseract_tsv(raw)
    assert list(a.columns) == list(b.columns)
    assert [str(x) for x in a["text"]] == [str(x) for x in b["text"]] == ["b", "d"]
    assert str(a.index.dtype) == "float64" and str(b.index.dtype) != "float64"


# --------------------------------------------------------------------------- #
# Real Tesseract: raw TSV of THE SAME invocation == cells
# --------------------------------------------------------------------------- #


def _tessdata() -> str | None:
    exe = shutil.which("tesseract")
    if not exe or not Path(FONT).is_file():
        return None
    out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True)
    text = out.stdout + out.stderr
    where = re.search(r'"([^"]+)"', text)
    return where.group(1) if where and "vie" in text.split() else None


TESSDATA = _tessdata()
needs_tesseract = pytest.mark.skipif(
    TESSDATA is None, reason="needs the tesseract binary with 'vie' and DejaVu"
)


def _render(path: Path, lines: list[str], font_px: int = 64) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(FONT, font_px)
    width = 120 + max(int(font.getlength(line)) for line in lines)
    img = Image.new("L", (max(width, 600), 80 + len(lines) * (font_px + 50)), 255)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((60, 40 + i * (font_px + 50)), line, font=font, fill=0)
    img.save(path, dpi=(300, 300))
    return path


def _model(cmd: str = "tesseract") -> Any:
    return upstream_mod.TesseractOcrCliModel(
        enabled=True,
        artifacts_path=None,
        options=TesseractCliOcrOptions(lang=["vie"], path=TESSDATA, tesseract_cmd=cmd),
        accelerator_options=AcceleratorOptions(),
    )


class _Spy:
    """Records the stdout of every ``... stdout tsv`` call made through
    ``docling_patches.subprocess.run`` (the call of the patched method)."""

    def __init__(self, monkeypatch) -> None:
        self.raw: list[str] = []
        real = subprocess.run

        def run(cmd, *a, **kw):
            res = real(cmd, *a, **kw)
            if list(cmd[-2:]) == ["stdout", "tsv"]:
                self.raw.append(res.stdout.decode("utf-8"))
            return res

        monkeypatch.setattr(P.subprocess, "run", run)


@needs_tesseract
@pytest.mark.parametrize(
    "lines",
    [
        ["0001"],  # numeric-only crops
        ["000123 2024"],
        ["12.50"],
        ["2024."],
        ["Số: 0001/2024"],  # mixed crops
        ["Mã NA, N/A và NULL"],
        ["true false"],
        ["Điều 9. khoản 1. điểm đ)"],
        ["0001", "Trang 2", "NA"],  # several lines in one crop
    ],
)
def test_verified_real_tesseract_cells_equal_the_raw_tsv_of_the_same_call(
    tmp_path, monkeypatch, lines
):
    spy = _Spy(monkeypatch)
    image = _render(tmp_path / "crop.png", lines)
    df = P._run_tesseract(_model(), str(image), None)
    assert len(spy.raw) == 1, "exactly one Tesseract TSV invocation"
    raw_fields = _raw_word_fields(spy.raw[0])
    assert raw_fields, "Tesseract recognised nothing on the rendered crop"
    cells = [str(row["text"]) for _, row in df.iterrows()]
    assert cells == raw_fields
    # every other column is what upstream would have parsed from the same bytes
    up = _upstream_parse(spy.raw[0])
    for c in HEADER.split("\t")[:-1]:
        assert up[c].loc[df.index].equals(df[c]), c


@needs_tesseract
def test_control_the_numeric_crop_really_is_the_e0_07_case(tmp_path, monkeypatch):
    """The same raw bytes through the upstream parse: the defect is live, so the
    test above is not vacuous."""
    spy = _Spy(monkeypatch)
    image = _render(tmp_path / "crop.png", ["0001"])
    P._run_tesseract(_model(), str(image), None)
    assert _raw_word_fields(spy.raw[0]) == ["0001"]
    assert _filtered_texts(_upstream_parse(spy.raw[0])) == ["1.0"]


@needs_tesseract
def test_verified_tsv_through_the_orientation_gate_is_byte_identical(
    tmp_path, monkeypatch
):
    """The gate (tesseract_cmd in production) must not touch a TSV call."""
    from open_notebook.ocr import tesseract_gate

    gate = Path(tesseract_gate.__file__).resolve()
    monkeypatch.setenv(tesseract_gate.REAL_ENV, shutil.which("tesseract") or "")
    image = _render(tmp_path / "crop.png", ["Số: 0001/2024 NA"])
    args = ["-l", "vie", "--tessdata-dir", str(TESSDATA), str(image), "stdout", "tsv"]
    direct = subprocess.run(["tesseract", *args], capture_output=True, check=True)
    gated = subprocess.run([str(gate), *args], capture_output=True, check=True)
    assert gated.stdout == direct.stdout and gated.stdout


# --------------------------------------------------------------------------- #
# Where / when the patch is in force
# --------------------------------------------------------------------------- #


def _fake_tesseract(tmp_path: Path) -> Path:
    exe = tmp_path / "tesseract"
    exe.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import os, sys
            a = sys.argv[1:]
            if a[:1] == ["--version"]:
                print("tesseract 5.3.4"); sys.exit(0)
            if a[:1] == ["--list-langs"]:
                print('List of available languages in "x" (2):'); print("osd"); print("vie"); sys.exit(0)
            sys.stdout.write(open(os.environ["FAKE_TSV"], encoding="utf-8").read())
            """
        )
    )
    exe.chmod(0o755)
    return exe


def test_verified_a_model_built_before_apply_runs_the_patched_parse(
    tmp_path, monkeypatch
):
    """Converter caching: the patch is on the class, so an OCR model instance
    created BEFORE ``apply()`` uses it too."""
    cls = upstream_mod.TesseractOcrCliModel
    setattr(cls, "_run_tesseract", P.upstream_function())  # noqa: B010
    assert not P.is_applied()
    exe = _fake_tesseract(tmp_path)
    model = cls(
        enabled=True,
        artifacts_path=None,
        options=TesseractCliOcrOptions(lang=["vie"], tesseract_cmd=str(exe)),
        accelerator_options=AcceleratorOptions(),
    )
    data = tmp_path / "raw.tsv"
    data.write_text(_tsv(["0001"]), encoding="utf-8")
    monkeypatch.setenv("FAKE_TSV", str(data))
    image = tmp_path / "crop.png"
    image.write_bytes(b"")
    assert [str(t) for t in model._run_tesseract(str(image), None)["text"]] == ["1.0"]
    P.apply()
    assert [str(t) for t in model._run_tesseract(str(image), None)["text"]] == ["0001"]


def test_verified_concurrent_apply_patches_once():
    cls = upstream_mod.TesseractOcrCliModel
    upstream = P.upstream_function()
    setattr(cls, "_run_tesseract", upstream)  # noqa: B010
    errors: list[BaseException] = []
    start = threading.Barrier(16)

    def work():
        try:
            start.wait(timeout=10)
            for _ in range(50):
                P.apply()
        except BaseException as e:  # noqa: BLE001 - reported below
            errors.append(e)

    threads = [threading.Thread(target=work) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors
    current = cls.__dict__["_run_tesseract"]
    assert P.is_applied() and current.__cb5400_upstream__ is upstream  # one layer


CHILD = """
import sys
from open_notebook.ocr import docling_patches as P, options, runtime
runtime.ensure_tessdata_prefix = lambda: (True, "")
runtime.ensure_tessdata_layout = lambda: None
options.tesseract_command = lambda real: real
before = P.is_applied()
options.build_ocr_options("rapidocr")
after_rapid = P.is_applied()
options.build_ocr_options(sys.argv[1])
print("RESULT", before, after_rapid, P.is_applied())
"""


@pytest.mark.parametrize("engine", ["tesseract_fast", "tesseract_best"])
def test_verified_a_fresh_worker_process_gets_the_patch_from_build_ocr_options(engine):
    """A new interpreter (worker start, spawn): nothing is patched at import,
    RapidOCR options do not patch, the first Tesseract options do."""
    out = subprocess.run(
        [sys.executable, "-c", CHILD, engine],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=300,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    line = [ln for ln in out.stdout.splitlines() if ln.startswith("RESULT")][-1]
    assert line == "RESULT False False True"


def test_verified_ingestion_and_readiness_only_build_options_in_one_place():
    """Every production conversion (worker ingestion, readiness probe, engine
    test) goes through ``build_ocr_options``; no other code creates Tesseract
    options or imports the Docling Tesseract model."""
    hits = []
    for base in ("open_notebook", "api", "commands"):
        for path in (ROOT / base).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"TesseractCliOcrOptions\(|TesseractOcrOptions\(", text):
                hits.append(str(path.relative_to(ROOT)))
    assert hits == ["open_notebook/ocr/options.py"]
    extract = (ROOT / "open_notebook/ocr/docling_extract.py").read_text("utf-8")
    assert extract.count("build_ocr_options(") == 1  # build_pipeline_options only


def test_verified_failure_path_never_returns_tesseract_options(monkeypatch):
    """Another Docling: the engine refuses (ValueError - a permanent job
    failure), nothing is patched, and the dependency override does not help."""
    from open_notebook.ocr import options, runtime

    cls = upstream_mod.TesseractOcrCliModel
    setattr(cls, "_run_tesseract", P.upstream_function())  # noqa: B010
    monkeypatch.setattr(runtime, "ensure_tessdata_prefix", lambda: (True, ""))
    monkeypatch.setattr(runtime, "ensure_tessdata_layout", lambda: None)
    monkeypatch.setattr(P, "_installed_docling", lambda: "2.130.0")
    monkeypatch.setenv("OCR_ALLOW_UNVERIFIED_DEPENDENCIES", "true")
    for engine in ("tesseract_fast", "tesseract_best"):
        with pytest.raises(P.TsvPatchError):
            options.build_ocr_options(engine)
    assert not P.is_applied()
    assert isinstance(P.TsvPatchError("x"), ValueError)


def test_verified_installed_upstream_file_is_the_published_wheel_content():
    """AST / source comparison is only meaningful against the REAL upstream:
    the installed file has the hash its wheel RECORD lists (the wheel itself is
    hash-pinned in uv.lock), docling-slim is pinned by the docling meta package,
    and the function source has the guarded SHA-256."""
    import base64

    dist = importlib.metadata.distribution("docling-slim")
    entry = next(
        f for f in (dist.files or []) if str(f).endswith("ocr/tesseract_ocr_cli_model.py")
    )
    algo, _, digest = cast(Any, entry.hash).mode, None, cast(Any, entry.hash).value
    data = Path(str(entry.locate())).read_bytes()
    actual = base64.urlsafe_b64encode(hashlib.new(algo, data).digest()).rstrip(b"=")
    assert actual.decode() == digest
    assert dist.version == P.DOCLING_VERSION == importlib.metadata.version("docling")
    assert f"docling-slim[standard]=={P.DOCLING_VERSION}" in (
        importlib.metadata.requires("docling") or []
    )
    assert P.problems() == []


# --------------------------------------------------------------------------- #
# D8-03: after the cells, Docling's page assembly still rewrites identifiers
# --------------------------------------------------------------------------- #

HYPHEN_CASES = [
    # (cell / line texts of one layout element, text a reader must find)
    (["Căn cứ Thông tư số 05/2024/TT-", "BNNPTNT ngày 01/02/2024;"], "TT-BNNPTNT"),
    (["Kế hoạch giai đoạn 2021-", "2025 của tỉnh"], "2021-"),
    (["tỉnh Bà Rịa-", "Vũng Tàu"], "Rịa-"),
    (["mã số 0001-", "0002."], "0001-"),
    (["Nghị quyết số 15-", "NQ/TW"], "15-"),
]


@pytest.mark.parametrize("lines, _must", HYPHEN_CASES)
def test_control_docling_page_assembly_drops_the_hyphen_of_identifiers(lines, _must):
    """What Docling 2.129.0 does today (v1.2.0 and the candidate alike, every
    OCR engine and PDF text layers): recorded so a change is noticed.
    Phase 12D9: the application patches this (D8-03); the control runs the
    UPSTREAM functions so that it still documents upstream behaviour."""
    from docling.models.stages.page_assemble.page_assemble_model import (
        PageAssembleModel,
        PageAssembleOptions,
    )

    with P.upstream_text_preservation():
        text = PageAssembleModel(options=PageAssembleOptions()).sanitize_text(
            list(lines)
        )
    assert text == lines[0][:-1] + lines[1]


# was: xfail(strict) D8-03 - fixed in Phase 12D9 (docling_patches, D8-03 patch)
# Phase 12D9 owner decision (12D9A): without the cells' own boxes two cells are
# never assumed to be one word - the hyphen AND the cell boundary are kept; the
# parts close up only across a line break the boxes show, which is what Docling's
# page assembly passes for cells on two lines (``same_line=[False]``).
# was: text = ....sanitize_text(list(lines)); assert must in text
@pytest.mark.parametrize("lines, must", HYPHEN_CASES)
def test_d8_03_identifiers_keep_their_hyphen_through_page_assembly(lines, must):
    from docling.models.stages.page_assemble.page_assemble_model import (
        PageAssembleModel,
        PageAssembleOptions,
    )

    assert P.apply_text_preservation()  # what every conversion does (12D9)
    model = PageAssembleModel(options=PageAssembleOptions())
    text = model.sanitize_text(list(lines), same_line=[False])  # a line break
    assert must in text
    assert model.sanitize_text(list(lines)) == f"{lines[0]} {lines[1]}"  # no boxes


def _ocr_then_assemble(tmp_path: Path, monkeypatch, paragraphs: list[list[str]]):
    """Rendered page -> real Tesseract through Docling's real OCR stage (patched
    TSV parse) -> Docling's real LayoutPostprocessor -> real PageAssembleModel.
    Returns (raw TSV word fields of the OCR invocations, OCR cell texts,
    element texts)."""
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.base_models import (
        BoundingBox,
        Cluster,
        InputFormat,
        LayoutPrediction,
        Page,
    )
    from docling.datamodel.document import ConversionResult, InputDocument
    from docling.datamodel.pipeline_options import LayoutOptions, OcrMode
    from docling.models.stages.page_assemble.page_assemble_model import (
        PageAssembleModel,
        PageAssembleOptions,
    )
    from docling.utils.layout_postprocessor import LayoutPostprocessor
    from docling_core.types.doc import DocItemLabel
    from PIL import Image, ImageDraw, ImageFont

    P.apply()
    spy = _Spy(monkeypatch)
    font = ImageFont.truetype(FONT, 40)
    k = 72 / 300
    img = Image.new("L", (2480, 3508), 255)
    draw = ImageDraw.Draw(img)
    regions, y = [], 200
    for lines in paragraphs:
        top, width = y, 0
        for line in lines:
            draw.text((160, y), line, font=font, fill=0)
            width = max(width, int(font.getlength(line)))
            y += 70
        regions.append(
            BoundingBox(
                l=(160 - 30) * k, t=(top - 20) * k, r=(160 + width + 30) * k, b=(y + 10) * k
            )
        )
        y += 260  # > 20 pt apart: one OCR crop per region
    pdf = tmp_path / "page.pdf"
    img.save(pdf, "PDF", resolution=300)
    in_doc = InputDocument(
        path_or_stream=pdf, format=InputFormat.PDF, backend=PyPdfiumDocumentBackend
    )
    conv = ConversionResult(input=in_doc)
    page = Page(page_no=1)
    page._backend = cast(Any, in_doc._backend).load_page(0)
    page.size = page._backend.get_size()
    clusters = [
        Cluster(id=i, label=DocItemLabel.TEXT, bbox=b, confidence=0.9, cells=[])
        for i, b in enumerate(regions)
    ]
    page.predictions.layout = LayoutPrediction(clusters=clusters)
    model = upstream_mod.TesseractOcrCliModel(
        enabled=True,
        artifacts_path=None,
        options=TesseractCliOcrOptions(
            lang=["vie"],
            path=TESSDATA,
            tesseract_cmd="tesseract",
            mode=OcrMode.LAYOUT_REGIONS,
        ),
        accelerator_options=AcceleratorOptions(),
    )
    list(model(conv, [page]))
    cells = [c.text for c in page.cells]
    processed = LayoutPostprocessor(page, clusters, LayoutOptions()).postprocess()
    page.predictions.layout = LayoutPrediction(clusters=processed)
    list(PageAssembleModel(options=PageAssembleOptions())(conv, [page]))
    raw = [w for r in spy.raw for w in _raw_word_fields(r)]
    assert page.assembled is not None
    return raw, cells, [e.text for e in page.assembled.elements]


REAL_PARAGRAPHS = [
    ["Căn cứ Thông tư số 05/2024/TT-", "BNNPTNT ngày 01 tháng 02 năm 2024;"],
    ["Kế hoạch phát triển giai đoạn 2021-", "2025 và mã số 0001-", "0002."],
    ["Nơi nhận: Lưu VT- KHTC; giai đoạn 2021- 2025; khoản 1- Điều 5."],
]


@needs_tesseract
def test_control_real_ocr_cells_are_raw_but_element_text_loses_hyphens(
    tmp_path, monkeypatch
):
    """End to end with the real binary: the cells equal the raw TSV of their own
    invocation (E0-07 holds), and the element text that becomes the Source
    content has lost the hyphens."""
    with P.upstream_text_preservation():  # Phase 12D9: documents UPSTREAM
        raw, cells, texts = _ocr_then_assemble(tmp_path, monkeypatch, REAL_PARAGRAPHS)
    assert cells == raw  # the patch: cell text = raw TSV text, in order
    for token in ("05/2024/TT-", "BNNPTNT", "2021-", "2025", "0001-", "VT-", "1-"):
        assert token in raw, (token, raw)
    joined = "\n".join(texts)
    assert "05/2024/TTBNNPTNT" in joined  # was TT- + BNNPTNT
    assert "20212025" in joined  # was 2021- + 2025 (line end AND mid-line)
    assert "00010002" in joined
    assert "VTKHTC" in joined and "1Điều" in joined  # mid-line, word cells


@needs_tesseract
# was: xfail(strict) D8-03 - fixed in Phase 12D9 (docling_patches, D8-03 patch)
def test_d8_03_real_ocr_element_text_keeps_every_hyphen_of_the_raw_tsv(
    tmp_path, monkeypatch
):
    assert P.apply_text_preservation()  # what every conversion does (12D9)
    raw, _cells, texts = _ocr_then_assemble(tmp_path, monkeypatch, REAL_PARAGRAPHS)
    joined = "\n".join(texts)
    assert joined.count("-") == sum(w.count("-") for w in raw)
