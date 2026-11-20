"""E0-07 (Phase 12D7): Docling must keep Tesseract's TSV ``text`` verbatim.

Upstream Docling 2.129.0 reads the TSV with pandas' type inference: a crop whose
words are all numbers becomes a float column (0001 -> 1.0), NA-like words are
dropped. ``open_notebook.ocr.docling_patches`` reads the text column as text and
leaves every other column as upstream parses it. These tests drive the REAL
Docling class: with a fake ``tesseract`` that prints a chosen raw TSV (every
token exactly), and with the real Tesseract binary on rendered crops / a
rendered PDF page through Docling's real OCR stage.
"""

from __future__ import annotations

import ast
import csv
import inspect
import io
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, cast

import pytest

pytest.importorskip("docling")

from docling.datamodel.accelerator_options import AcceleratorOptions  # noqa: E402
from docling.datamodel.pipeline_options import (  # noqa: E402
    OcrMode,
    TesseractCliOcrOptions,
)
from docling.models.stages.ocr import (
    tesseract_ocr_cli_model as upstream_mod,  # noqa: E402
)

from open_notebook.ocr import compat  # noqa: E402
from open_notebook.ocr import docling_patches as P  # noqa: E402

HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
STRUCTURE = [  # the page / block / paragraph / line rows Tesseract always writes (no text)
    "1\t1\t0\t0\t0\t0\t0\t0\t600\t80\t-1\t",
    "2\t1\t1\t0\t0\t0\t10\t10\t580\t60\t-1\t",
    "3\t1\t1\t1\t0\t0\t10\t10\t580\t60\t-1\t",
    "4\t1\t1\t1\t1\t0\t10\t10\t580\t60\t-1\t",
]


def tsv(*words: str) -> str:
    rows = [HEADER, *STRUCTURE]
    for i, w in enumerate(words, 1):
        rows.append(f"5\t1\t1\t1\t1\t{i}\t{10 + 60 * i}\t12\t50\t40\t96.25\t{w}")
    return "\n".join(rows) + "\n"


FAKE = textwrap.dedent(
    """\
    #!{python}
    import os, sys
    a = sys.argv[1:]
    if a[:1] == ["--version"]:
        print("tesseract 5.3.4"); sys.exit(0)
    if a[:1] == ["--list-langs"]:
        print('List of available languages in "x" (3):'); print("eng"); print("osd"); print("vie"); sys.exit(0)
    if "--psm" in a and a[a.index("--psm") + 1] == "0":
        print("Page number: 0\\nOrientation in degrees: 0\\nRotate: 0\\nOrientation confidence: 9.9\\nScript: Latin\\nScript confidence: 9.9")
        sys.exit(0)
    with open(os.environ["FAKE_TSV"], "rb") as fh:
        sys.stdout.buffer.write(fh.read())
    """
)


@pytest.fixture
def fake_model(tmp_path, monkeypatch):
    exe = tmp_path / "tesseract"
    exe.write_text(FAKE.format(python=sys.executable))
    exe.chmod(0o755)
    model = upstream_mod.TesseractOcrCliModel(
        enabled=True,
        artifacts_path=None,
        options=TesseractCliOcrOptions(lang=["vie"], tesseract_cmd=str(exe)),
        accelerator_options=AcceleratorOptions(),
    )
    image = tmp_path / "crop.png"
    image.write_bytes(b"")  # never read: the fake prints the TSV

    def run(raw: str, patched: bool = True) -> list[str]:
        data = tmp_path / "raw.tsv"
        data.write_text(raw, encoding="utf-8")
        monkeypatch.setenv("FAKE_TSV", str(data))
        fn = P._run_tesseract if patched else P.upstream_function()
        return [str(t) for t in fn(model, str(image), None)["text"]]

    return run


# --------------------------------------------------------------------------- #
# RED: what upstream Docling 2.129.0 does with the raw TSV
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "token, upstream",
    [
        ("0001", "1.0"),
        ("000123", "123.0"),
        ("2024", "2024.0"),
        ("9.", "9.0"),
        ("0.", "0.0"),
        ("12.50", "12.5"),
        ("000000000000000123", "123.0"),
        ("true", "True"),
        ("false", "False"),
    ],
)
def test_red_upstream_rewrites_a_numeric_only_crop(fake_model, token, upstream):
    """The bug, reproduced from the raw TSV through the real Docling method."""
    assert fake_model(tsv(token), patched=False) == [upstream]


@pytest.mark.parametrize("token", ["NA", "N/A", "NULL", "NaN", "None", "nan"])
def test_red_upstream_drops_na_like_words_even_in_a_mixed_line(fake_model, token):
    assert fake_model(tsv(token), patched=False) == []
    assert fake_model(tsv("Mã", token, "0001"), patched=False) == ["Mã", "0001"]


# --------------------------------------------------------------------------- #
# GREEN: the raw TSV string is the cell text
# --------------------------------------------------------------------------- #

TOKENS = [
    "0001", "000123", "2024", "9.", "1.0", "0.", "0,5", "12.50", "1/2024",
    "001/2024", "05%", "000000000000000123", "NA", "N/A", "NULL", "NaN", "None",
    "nan", "true", "false", "TRUE", '"Điều"', '1"', "Điều", "khoản", "đ)",
    "Lãi", "suất", "4,5%/năm", "Số:", "QĐ-NHNo", "-", "…",
]  # fmt: skip


@pytest.mark.parametrize("token", TOKENS)
def test_a_crop_of_one_token_keeps_it_verbatim(fake_model, token):
    assert fake_model(tsv(token)) == [token]


def test_a_line_of_every_token_keeps_them_all_in_order(fake_model):
    assert fake_model(tsv(*TOKENS)) == TOKENS


def test_numeric_only_crops_keep_leading_zeros_and_trailing_dots(fake_model):
    for words in (["0001"], ["0001", "000123"], ["2024", "9."], ["12.50", "0."]):
        assert fake_model(tsv(*words)) == words


def test_empty_text_rows_are_still_filtered_like_upstream(fake_model):
    raw = (
        tsv("0001")
        + "5\t1\t1\t1\t1\t2\t200\t12\t50\t40\t96\t\n5\t1\t1\t1\t1\t3\t300\t12\t50\t40\t96\t   \n"
    )
    assert fake_model(raw) == ["0001"]
    assert fake_model(tsv()) == [] and fake_model(tsv(), patched=False) == []


def test_unicode_vietnamese_is_unchanged(fake_model):
    words = ["Điều", "5.", "Ngân", "hàng", "Nông", "nghiệp", "và", "Phát", "triển"]
    assert fake_model(tsv(*words)) == words == fake_model(tsv(*words), patched=False)


# --------------------------------------------------------------------------- #
# Every other column: exactly as upstream parses it
# --------------------------------------------------------------------------- #

NUMERIC = [c for c in HEADER.split("\t") if c != "text"]


def _upstream_parse(raw):
    import pandas as pd

    return pd.read_csv(io.StringIO(raw), quoting=csv.QUOTE_NONE, sep="\t")


@pytest.mark.parametrize(
    "raw",
    [
        tsv("0001"),
        tsv("Điều", "1."),
        tsv(*TOKENS),
        # malformed numeric fields: NA / empty / nan keep their upstream meaning (NaN)
        HEADER
        + "\n"
        + "5\t1\t1\t1\t1\t1\tNA\t1\t\t30\tnan\t0001\n5\t1\t1\t1\t1\t2\t5\t1\t9\t30\t91\tNA\n",
    ],
)
def test_numeric_columns_have_the_upstream_types_and_values(raw):
    a, b = _upstream_parse(raw), P.read_tesseract_tsv(raw)
    assert list(a.columns) == list(b.columns)
    for c in NUMERIC:
        assert a[c].dtype == b[c].dtype, c
        assert a[c].equals(b[c]), c


def test_a_tab_inside_a_text_field_is_parsed_like_upstream():
    """Tesseract never writes a tab inside a word; if a line has an extra field,
    the patch parses it exactly as upstream does (no new behaviour)."""
    raw = HEADER + "\n" + "5\t1\t1\t1\t1\t1\t0\t0\t9\t9\t90\ta\tb\n"
    a, b = _upstream_parse(raw), P.read_tesseract_tsv(raw)
    assert list(a.columns) == list(b.columns) and list(a.index) == list(b.index)
    assert [str(x) for x in a["text"]] == [str(x) for x in b["text"]]


def test_empty_output_fails_like_upstream():
    import pandas as pd

    for raw in ("", "\n"):
        with pytest.raises(pd.errors.EmptyDataError):
            _upstream_parse(raw)
        with pytest.raises(pd.errors.EmptyDataError):
            P.read_tesseract_tsv(raw)


def test_default_na_list_is_pandas_own():
    from pandas._libs.parsers import STR_NA_VALUES

    assert set(P.PANDAS_DEFAULT_NA) == set(STR_NA_VALUES)


# --------------------------------------------------------------------------- #
# The patched method IS the upstream method except for the TSV parse
# --------------------------------------------------------------------------- #


class _Normalise(ast.NodeTransformer):
    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        node.returns = None
        for arg in node.args.args:
            arg.annotation = None
        return node

    def visit_Call(self, node):
        self.generic_visit(node)
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "read_csv":
            return ast.Call(
                func=ast.Name(id="TSV_PARSE", ctx=ast.Load()), args=[], keywords=[]
            )
        if isinstance(func, ast.Name) and func.id == "read_tesseract_tsv":
            return ast.Call(
                func=ast.Name(id="TSV_PARSE", ctx=ast.Load()), args=[], keywords=[]
            )
        return node


def _normalised(fn) -> str:
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    body = tree.body[0].body  # type: ignore[attr-defined]
    # our copy imports the upstream module logger; nothing else is added
    tree.body[0].body = [  # type: ignore[attr-defined]
        n for n in body if not isinstance(n, ast.ImportFrom)
    ]
    return ast.dump(_Normalise().visit(tree), include_attributes=False)


class _E204(ast.NodeTransformer):
    """Phase 12D9 (E2-04): the patched run keeps stderr (to classify a failure,
    never logged) and has a timeout; everything else is upstream's."""

    seen: list[str] = []

    def visit_Call(self, node):
        self.generic_visit(node)
        if ast.unparse(node.func) == "subprocess.run":
            kept = []
            for kw in node.keywords:
                if kw.arg == "timeout":
                    self.seen.append(f"timeout={ast.unparse(kw.value)}")
                    continue
                if kw.arg == "stderr" and ast.unparse(kw.value) == "PIPE":
                    self.seen.append("stderr=PIPE")
                    kw = ast.keyword(
                        arg="stderr", value=ast.Name(id="DEVNULL", ctx=ast.Load())
                    )
                kept.append(kw)
            node.keywords = kept
        return node


def test_patched_method_is_upstream_except_the_tsv_parse():
    # was: assert _normalised(P._run_tesseract) == _normalised(P.upstream_function())
    tree = ast.parse(textwrap.dedent(inspect.getsource(P._run_tesseract)))
    _E204.seen = []
    ours = ast.unparse(_E204().visit(tree))
    assert _E204.seen == ["stderr=PIPE", "timeout=RECOGNITION_TIMEOUT_SECONDS"]
    assert _normalised_source(ours) == _normalised(P.upstream_function())


def _normalised_source(source: str) -> str:
    tree = ast.parse(source)
    body = tree.body[0].body  # type: ignore[attr-defined]
    tree.body[0].body = [  # type: ignore[attr-defined]
        n for n in body if not isinstance(n, ast.ImportFrom)
    ]
    return ast.dump(_Normalise().visit(tree), include_attributes=False)


# --------------------------------------------------------------------------- #
# Guards, idempotence, compat fingerprints, where it is applied
# --------------------------------------------------------------------------- #


@pytest.fixture
def unpatched(monkeypatch):
    """The upstream class as installed, before the patch (restored afterwards)."""
    cls = upstream_mod.TesseractOcrCliModel
    monkeypatch.setattr(cls, "_run_tesseract", P.upstream_function())
    assert not P.is_applied()
    return cls


def test_apply_is_idempotent_and_keeps_the_upstream_for_fingerprints(unpatched):
    P.apply()
    first = unpatched.__dict__["_run_tesseract"]
    P.apply()
    assert unpatched.__dict__["_run_tesseract"] is first and P.is_applied()
    assert compat.source_fingerprint(P.UPSTREAM_TARGET) == P.UPSTREAM_SHA256
    assert compat.check_fingerprints(compat.DOCLING_FINGERPRINTS) == []
    assert P.status()["applied"] is True


def test_another_docling_version_is_refused_not_patched(unpatched, monkeypatch):
    monkeypatch.setattr(P, "_installed_docling", lambda: "2.130.0")
    with pytest.raises(P.TsvPatchError, match="written for docling 2.129.0 only"):
        P.apply()
    assert not P.is_applied()
    assert isinstance(P.TsvPatchError("x"), ValueError)  # jobs stop, no retry


def test_changed_upstream_source_is_refused_not_patched(unpatched, monkeypatch):
    monkeypatch.setattr(P, "UPSTREAM_SHA256", "0" * 64)
    with pytest.raises(P.TsvPatchError, match="not the verified docling"):
        P.apply()
    assert not P.is_applied()


def test_the_patch_is_applied_by_every_tesseract_engine_and_no_other(monkeypatch):
    from open_notebook.ocr import catalog, options, runtime

    calls = []
    monkeypatch.setattr(P, "apply", lambda: calls.append("apply"))
    monkeypatch.setattr(runtime, "ensure_tessdata_prefix", lambda: (True, ""))
    monkeypatch.setattr(runtime, "ensure_tessdata_layout", lambda: None)
    monkeypatch.setattr(options, "engine_langs", lambda e, v=None: ["vie"])
    for spec in catalog.ENGINES.values():
        calls.clear()
        try:
            options.build_ocr_options(spec.id)
        except Exception:  # noqa: BLE001 - other engines may need their runtime
            pass
        assert calls == (["apply"] if spec.docling_kind == "tesseract" else []), spec.id


# --------------------------------------------------------------------------- #
# Real Tesseract: rendered crops and a rendered PDF page through Docling's OCR stage
# --------------------------------------------------------------------------- #


def _real_tesseract_with_vie() -> bool:
    if not shutil.which("tesseract"):
        return False
    out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True)
    return "vie" in out.stdout.split()


needs_tesseract = pytest.mark.skipif(
    not _real_tesseract_with_vie(), reason="needs the tesseract binary with 'vie'"
)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _render(path: Path, lines: list[str], size=(1400, 160), font_px=64):
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.truetype(FONT, font_px)
    img = Image.new("L", (size[0], max(size[1], 60 + len(lines) * (font_px + 60))), 255)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((60, 40 + i * (font_px + 60)), line, font=font, fill=0)
    img.save(path, dpi=(300, 300))
    return path


@pytest.fixture
def real_model():
    if not Path(FONT).is_file():
        pytest.skip("DejaVuSans font not installed")
    return upstream_mod.TesseractOcrCliModel(
        enabled=True,
        artifacts_path=None,
        options=TesseractCliOcrOptions(lang=["vie"], tesseract_cmd="tesseract"),
        accelerator_options=AcceleratorOptions(),
    )


def _raw_words(image: Path) -> list[str]:
    out = subprocess.run(
        ["tesseract", str(image), "stdout", "-l", "vie", "tsv"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    rows = [r.split("\t") for r in out.splitlines()[1:]]
    return [r[-1] for r in rows if r[0] == "5" and r[-1].strip()]


@needs_tesseract
@pytest.mark.parametrize(
    "text",
    ["0001", "000123", "2024", "12.50", "NA", "Số: 0001/2024", "Mã NA, N/A", "Trang 2"],
)
def test_real_tesseract_crop_cells_equal_the_raw_tsv(real_model, tmp_path, text):
    image = _render(tmp_path / "crop.png", [text])
    raw = _raw_words(image)
    assert raw, "Tesseract recognised nothing on the rendered crop"
    patched = [str(t) for t in P._run_tesseract(real_model, str(image), None)["text"]]
    assert patched == raw


@needs_tesseract
def test_real_tesseract_numeric_crop_is_rewritten_by_upstream(real_model, tmp_path):
    image = _render(tmp_path / "crop.png", ["0001"])
    assert _raw_words(image) == ["0001"]
    upstream = [
        str(t) for t in P.upstream_function()(real_model, str(image), None)["text"]
    ]
    assert upstream == ["1.0"]  # the E0-07 defect with the real binary


@needs_tesseract
def test_real_full_page_ocr_through_doclings_ocr_stage(tmp_path):
    """Docling's real OCR stage (TesseractOcrCliModel.__call__) on a rendered PDF
    page: the cells it hands to layout analysis are the raw TSV words."""
    if not Path(FONT).is_file():
        pytest.skip("DejaVuSans font not installed")
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.base_models import InputFormat, Page
    from docling.datamodel.document import ConversionResult, InputDocument
    from PIL import Image

    lines = [
        "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
        "Số: 0001/2024/QĐ-NHNo",
        "0001",
        "Điều 1. Lãi suất tối đa 12.50%/năm.",
        "000123",
        "Mã sản phẩm NA và N/A",
        "Trang 2",
    ]
    png = _render(tmp_path / "page.png", lines, size=(2480, 1200), font_px=40)
    pdf = tmp_path / "page.pdf"
    Image.open(png).save(pdf, "PDF", resolution=300)

    def cells(patched: bool) -> list[str]:
        cls = upstream_mod.TesseractOcrCliModel
        saved = cls.__dict__["_run_tesseract"]
        setattr(  # noqa: B010 - a class attribute, restored in finally
            cls, "_run_tesseract", P.upstream_function() if not patched else saved
        )
        if patched:
            P.apply()
        try:
            in_doc = InputDocument(
                path_or_stream=pdf,
                format=InputFormat.PDF,
                backend=PyPdfiumDocumentBackend,
            )
            conv = ConversionResult(input=in_doc)
            page = Page(page_no=0)
            page._backend = cast(Any, in_doc._backend).load_page(0)
            page.size = page._backend.get_size()
            model = cls(
                enabled=True,
                artifacts_path=None,
                options=TesseractCliOcrOptions(
                    lang=["vie"], tesseract_cmd="tesseract", mode=OcrMode.FULL_PAGE
                ),
                accelerator_options=AcceleratorOptions(),
            )
            list(model(conv, [page]))
            return [c.text for c in page.cells]
        finally:
            setattr(cls, "_run_tesseract", saved)  # noqa: B010

    up, fixed = cells(False), cells(True)
    for token in ("0001/2024/QĐ-NHNo", "0001", "12.50%/năm.", "000123"):
        assert token in fixed
    assert "NA" in fixed and "N/A" in fixed
    assert (
        "NA" not in up and "N/A" not in up
    )  # upstream drops them on the full page too
    assert [t for t in fixed if t not in ("NA", "N/A")] == up
