"""Phase 12D9 (D8-03, D8-02): Docling keeps the hyphens and the attached
footnotes the document has.

Upstream Docling 2.129.0 drops a hyphen the document has when it joins text:
``PageAssembleModel.sanitize_text`` (the cells of one layout region - every OCR
engine and PDF text layers; Tesseract cells are WORDS, so the rule also fires
inside a printed line) and ``ReadingOrderModel._merge_elements`` (two blocks
joined across a page / column). docling-core 2.96.0's Markdown export never
writes the footnotes Docling attaches to a table / picture.
``open_notebook.ocr.docling_patches.apply_text_preservation`` replaces those
functions under the guards of the E0-07 patch (D-39): exact versions, SHA-256
of every upstream source, all or nothing, idempotent, thread-safe.

The tests drive REAL Docling / docling-core code: the functions, Docling's page
assembly on cells with their own boxes, a PDF text layer through docling-parse,
Docling's reading order on synthetic layouts, rendered scans through the real
Tesseract binary and Docling's OCR stage, then the application's
``convert_file`` and ``save_source`` (the text a Source stores). On the
unpatched candidate the behaviour tests fail on their assertions (the RED run
is recorded in docs/review/PHASE12D9_UPSTREAM_PATCH_REPORT.md).
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
from pathlib import Path
from typing import Any, cast

import pytest

pytest.importorskip("docling")

from open_notebook.ocr import compat  # noqa: E402
from open_notebook.ocr import docling_patches as P  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ocr"))
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
A4 = (595, 842)


def _apply() -> bool:
    """What every Docling conversion of the application does since 12D9. On a
    candidate without the patch nothing happens and the behaviour tests fail
    on their own assertions (RED), not on an import."""
    apply = getattr(P, "apply_text_preservation", None)
    return bool(apply and apply(required=True))


@pytest.fixture
def unpatched(monkeypatch):
    """Every patched function back to upstream for one test (restored after)."""
    for key, target in P.TEXT_TARGETS.items():
        monkeypatch.setattr(P._text_owner(key), target[3], P.text_upstream(key))
    assert not P.text_patches_applied()


def _conv(pages: int = 1, sizes: list[tuple[int, int]] | None = None) -> Any:
    import pypdfium2 as pdfium
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.document import ConversionResult, InputDocument

    pdf = pdfium.PdfDocument.new()
    for w, h in sizes or [A4] * pages:
        pdf.new_page(w, h)
    path = tempfile.mktemp(prefix="d9_", suffix=".pdf")
    pdf.save(path)
    pdf.close()
    return ConversionResult(
        input=InputDocument(
            path_or_stream=Path(path),
            format=InputFormat.PDF,
            backend=PyPdfiumDocumentBackend,
        )
    )


class _ValidBackend:
    def is_valid(self) -> bool:
        return True


def _region(*cells: tuple[str, float, float, float, float]) -> str:
    """The element text Docling's REAL ``PageAssembleModel`` builds from ONE
    text region made of these cells (text, l, t, r, b), as an OCR engine or a
    PDF text layer gives them."""
    from docling.datamodel.base_models import Cluster, LayoutPrediction, Page
    from docling.models.stages.page_assemble.page_assemble_model import (
        PageAssembleModel,
        PageAssembleOptions,
    )
    from docling_core.types.doc import BoundingBox, CoordOrigin, DocItemLabel, Size
    from docling_core.types.doc.page import BoundingRectangle, TextCell

    co = CoordOrigin.TOPLEFT
    tcells = [
        TextCell(
            index=i,
            text=t,
            orig=t,
            from_ocr=True,
            confidence=1.0,
            rect=BoundingRectangle.from_bounding_box(
                BoundingBox(l=left, t=top, r=r, b=b, coord_origin=co)
            ),
        )
        for i, (t, left, top, r, b) in enumerate(cells)
    ]
    box = BoundingBox(
        l=min(c[1] for c in cells),
        t=min(c[2] for c in cells),
        r=max(c[3] for c in cells),
        b=max(c[4] for c in cells),
    )
    page = Page(page_no=1, size=Size(width=A4[0], height=A4[1]))
    page._backend = cast(Any, _ValidBackend())
    page.predictions.layout = LayoutPrediction(
        clusters=[
            Cluster(
                id=0, label=DocItemLabel.TEXT, bbox=box, confidence=0.9, cells=tcells
            )
        ]
    )
    list(PageAssembleModel(options=PageAssembleOptions())(_conv(), [page]))
    assert page.assembled is not None
    return page.assembled.elements[0].text


def line(
    y: float, *words: tuple[str, float, float]
) -> list[tuple[str, float, float, float, float]]:
    """Word cells of one printed line (Tesseract): (text, left, right) at y."""
    return [(w, left, y, right, y + 12) for w, left, right in words]


# --------------------------------------------------------------------------- #
# A. Page assembly: what a hyphen between two cells becomes
# --------------------------------------------------------------------------- #

# (name, cells of one region, element text the Source must store)
ASSEMBLY_CASES = [
    (
        "document number across a line break",
        [
            ("Căn cứ Thông tư số 05/2024/TT-", 70, 100, 260, 112),
            ("BNNPTNT ngày 01/02/2024;", 70, 116, 230, 128),
        ],
        "Căn cứ Thông tư số 05/2024/TT-BNNPTNT ngày 01/02/2024;",
    ),
    (
        "year range across a line break",
        [("giai đoạn 2021-", 70, 100, 170, 112), ("2025 của tỉnh", 70, 116, 160, 128)],
        "giai đoạn 2021-2025 của tỉnh",
    ),
    (
        "code with leading zeros across a line break",
        [("mã số 0001-", 70, 100, 150, 112), ("0002.", 70, 116, 110, 128)],
        "mã số 0001-0002.",
    ),
    (
        "percentage range across a line break",
        [("tăng 12-", 70, 100, 130, 112), ("15% so với cùng kỳ", 70, 116, 200, 128)],
        "tăng 12-15% so với cùng kỳ",
    ),
    (
        "multi-hyphen code across a line break",
        [
            ("Quyết định số 15/2024/QĐ-UBND-", 70, 100, 280, 112),
            ("VP ngày 2/3", 70, 116, 150, 128),
        ],
        "Quyết định số 15/2024/QĐ-UBND-VP ngày 2/3",
    ),
    (
        "place name across a line break",
        [("tỉnh Bà Rịa-", 70, 100, 160, 112), ("Vũng Tàu", 70, 116, 130, 128)],
        "tỉnh Bà Rịa-Vũng Tàu",
    ),
    (
        "URL across a line break",
        [
            ("xem https://vbpl.vn/bo-nong-", 70, 100, 260, 112),
            ("nghiep/van-ban", 70, 116, 170, 128),
        ],
        "xem https://vbpl.vn/bo-nong-nghiep/van-ban",
    ),
    (
        "Vietnamese word cut at a line end: the printed hyphen stays",
        [("phát-", 70, 100, 110, 112), ("triển nông thôn", 70, 116, 180, 128)],
        "phát-triển nông thôn",
    ),
    (
        "English word cut at a line end: kept, no dictionary repair",
        [("the docu-", 70, 100, 130, 112), ("ment is valid", 70, 116, 160, 128)],
        "the docu-ment is valid",
    ),
    (
        "word cells side by side: the printed space stays (VT- KHTC)",
        line(100, ("Lưu:", 70, 100), ("VT-", 104, 125), ("KHTC.", 129, 165)),
        "Lưu: VT- KHTC.",
    ),
    (
        "word cells side by side: 1- Điều 5",
        line(
            100,
            ("khoản", 70, 105),
            ("1-", 109, 120),
            ("Điều", 124, 150),
            ("5.", 154, 165),
        ),
        "khoản 1- Điều 5.",
    ),
    (
        "word cells side by side: 2021- 2025",
        line(
            100,
            ("giai", 70, 95),
            ("đoạn", 99, 130),
            ("2021-", 134, 170),
            ("2025;", 174, 210),
        ),
        "giai đoạn 2021- 2025;",
    ),
    (
        "a minus sign that starts a cell",
        line(100, ("nhiệt", 70, 100), ("độ", 104, 120), ("-5°C", 124, 160)),
        "nhiệt độ -5°C",
    ),
    (
        "a hyphen inside one cell",
        line(100, ("tăng", 70, 100), ("12-15%", 104, 150)),
        "tăng 12-15%",
    ),
    (
        "spaces around a hyphen (a dash cell)",
        line(100, ("VT", 70, 85), ("-", 89, 94), ("KHTC", 98, 130)),
        "VT - KHTC",
    ),
    (
        "a bullet dash before the text",
        line(100, ("-", 70, 75), ("Nội", 79, 100), ("dung", 104, 130)),
        "- Nội dung",
    ),
    (
        "a hyphen after a space (no word to attach to)",
        [("số hiệu -", 70, 100, 130, 112), ("xem phụ lục", 70, 116, 150, 128)],
        "số hiệu - xem phụ lục",
    ),
    (
        "cells whose boxes show no line break (next cell ABOVE): boundary kept",
        [("05/2024/TT-", 70, 116, 150, 128), ("BNNPTNT", 160, 100, 230, 112)],
        "05/2024/TT- BNNPTNT",
    ),
]


@pytest.mark.parametrize(
    "cells, expected",
    [c[1:] for c in ASSEMBLY_CASES],
    ids=[c[0] for c in ASSEMBLY_CASES],
)
def test_page_assembly_keeps_every_hyphen_and_the_printed_spacing(cells, expected):
    _apply()
    text = _region(*cells)
    assert text == expected
    assert text.count("-") == "".join(c[0] for c in cells).count("-")


def test_control_upstream_page_assembly_drops_these_hyphens():
    """The same regions through UPSTREAM Docling (v1.2.0 and 4587eb7): the
    hyphen is removed and the parts glued, inside a printed line too."""
    with P.upstream_text_preservation():
        assert _region(*ASSEMBLY_CASES[0][1]).startswith(
            "Căn cứ Thông tư số 05/2024/TTBNNPTNT"
        )
        assert _region(*ASSEMBLY_CASES[9][1]) == "Lưu: VTKHTC."
        assert _region(*ASSEMBLY_CASES[10][1]) == "khoản 1Điều 5."
        assert _region(*ASSEMBLY_CASES[1][1]) == "giai đoạn 20212025 của tỉnh"


def test_without_boxes_two_cells_are_never_assumed_to_be_one_word():
    """``sanitize_text(list[str])`` - upstream's own signature, no geometry: the
    hyphen and the cell boundary are both kept (owner rule, 12D9A)."""
    from docling.models.stages.page_assemble.page_assemble_model import (
        PageAssembleModel,
        PageAssembleOptions,
    )

    _apply()
    model = PageAssembleModel(options=PageAssembleOptions())
    assert model.sanitize_text(["05/2024/TT-", "BNNPTNT"]) == "05/2024/TT- BNNPTNT"
    assert model.sanitize_text(["VT-", "KHTC"]) == "VT- KHTC"
    # a line break the boxes show closes up; same line keeps the space
    assert model.sanitize_text(["05/2024/TT-", "BNNPTNT"], same_line=[False]) == (
        "05/2024/TT-BNNPTNT"
    )
    assert model.sanitize_text(["VT-", "KHTC"], same_line=[True]) == "VT- KHTC"
    assert model.sanitize_text(["VT-", "KHTC"], same_line=[None]) == "VT- KHTC"
    assert model.sanitize_text(["a-", "b", "c-", "d"], same_line=[False]) == "a-b c- d"


def test_other_upstream_text_rules_are_unchanged_and_recorded():
    """Separate, pre-existing limitation (not changed by 12D9): upstream's
    typographic conversions of sanitize_text. Recorded here so a change of
    either side is seen."""
    from docling.models.stages.page_assemble.page_assemble_model import (
        PageAssembleModel,
        PageAssembleOptions,
    )

    lines = ["“Điều 5” ’a‘ 1⁄2 • ﬁ eld", "tiếp"]  # noqa: RUF001
    model = PageAssembleModel(options=PageAssembleOptions())
    with P.upstream_text_preservation():
        upstream = model.sanitize_text(list(lines))
    _apply()
    assert (
        model.sanitize_text(list(lines))
        == upstream
        == "\"Điều 5\" 'a' 1/2 · field tiếp"
    )
    assert model.sanitize_text(["xuyên­", "biên"]) == "xuyên­ biên"  # soft hyphen kept
    with P.upstream_text_preservation():
        assert model.sanitize_text(["xuyên­", "biên"]) == "xuyên­ biên"


def test_same_line_flags_read_the_cells_own_boxes():
    from docling_core.types.doc import BoundingBox, CoordOrigin
    from docling_core.types.doc.page import BoundingRectangle, TextCell

    def cell(left, top, r, b, origin=CoordOrigin.TOPLEFT):
        return TextCell(
            index=0, text="x", orig="x", from_ocr=True, confidence=1.0,
            rect=BoundingRectangle.from_bounding_box(
                BoundingBox(l=left, t=top, r=r, b=b, coord_origin=origin)
            ),
        )  # fmt: skip

    a = cell(10, 100, 50, 112)
    assert P.same_line_flags([a, cell(55, 101, 90, 113)]) == [True]
    assert P.same_line_flags([a, cell(10, 116, 50, 128)]) == [False]  # next line
    assert P.same_line_flags([a, cell(5, 100, 9, 112)]) == [None]  # same line, left
    assert P.same_line_flags([a, cell(10, 80, 50, 92)]) == [None]  # above
    assert P.same_line_flags([a, cell(10, 100, 50, 100)]) == [None]  # no height
    bl = CoordOrigin.BOTTOMLEFT
    assert P.same_line_flags(
        [cell(10, 742, 50, 730, bl), cell(10, 726, 50, 714, bl)]
    ) == [False]
    assert P.same_line_flags([a, cell(10, 726, 50, 714, bl)]) == [None]  # mixed origins
    assert P.same_line_flags([a]) == []


# --------------------------------------------------------------------------- #
# B. The patched functions ARE upstream's except the hyphen rule (AST)
# --------------------------------------------------------------------------- #


def _tree(fn: Any) -> ast.FunctionDef:
    node = ast.parse(textwrap.dedent(inspect.getsource(fn))).body[0]
    assert isinstance(node, ast.FunctionDef)
    node.name = "F"
    node.returns = None
    for a in node.args.args:
        a.annotation = None
    body = [n for n in node.body if not isinstance(n, ast.ImportFrom)]
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(getattr(body[0], "value", None), ast.Constant)
    ):
        body = body[1:]  # docstring
    node.body = body
    return node


def _dump(nodes: Any) -> str:
    if isinstance(nodes, list):
        return "\n".join(ast.dump(n, include_attributes=False) for n in nodes)
    return ast.dump(nodes, include_attributes=False)


def _find_if(tree: ast.AST, pred: Any) -> ast.If:
    found = [n for n in ast.walk(tree) if isinstance(n, ast.If) and pred(n)]
    assert len(found) == 1, len(found)
    return found[0]


def test_sanitize_text_is_upstream_except_the_hyphen_branch():
    ours, theirs = _tree(P._sanitize_text), _tree(P.text_upstream("sanitize_text"))

    def is_split_word(n):
        return any(
            isinstance(x, ast.Name) and x.id == "hyphen_attached_to_word"
            for x in ast.walk(n.test)
        ) and isinstance(n.test, ast.BoolOp)

    o, t = _find_if(ours, is_split_word), _find_if(theirs, is_split_word)
    assert ast.unparse(t.body[0]) == "lines[ix] = prev_line[:-1]"  # upstream drops "-"
    assert (
        len(o.body) == 2
        and ast.unparse(o.body[1]) == "if not line_break:\n    lines[ix] += ' '"
    )
    assert ast.unparse(o.body[0]) == (
        "line_break = same_line is not None and ix < len(same_line) and "
        "(same_line[ix] is False)"
    )
    o.body = t.body = [ast.Pass()]
    assert [a.arg for a in ours.args.args] == ["self", "lines", "same_line"]
    ours.args.args = ours.args.args[:2]
    ours.args.defaults = []
    assert _dump(ours) == _dump(theirs)


def test_page_assembly_is_upstream_except_the_geometry_it_passes():
    ours, theirs = _tree(P._page_assemble_call), _tree(P.text_upstream("page_assemble"))

    def text_branch(n):
        return ast.unparse(n.test) == "cluster.label in TEXT_ELEM_LABELS"

    o, t = _find_if(ours, text_branch), _find_if(theirs, text_branch)
    assert [ast.unparse(s) for s in t.body[:2]] == [
        "textlines = [cell.text.replace('\\x02', '-').strip() for cell in cluster.cells "
        "if len(cell.text.strip()) > 0]",
        "text = self.sanitize_text(textlines)",
    ]
    assert [ast.unparse(s) for s in o.body[:3]] == [
        "kept_cells = [cell for cell in cluster.cells if len(cell.text.strip()) > 0]",
        "textlines = [cell.text.replace('\\x02', '-').strip() for cell in kept_cells]",
        # sanitize_text(textlines, same_line=same_line_flags(kept_cells)), and
        # the evidence of the Standard gate export (off unless it runs)
        "text = _assembled_text(self, page, cluster, kept_cells, textlines)",
    ]
    o.body, t.body = o.body[3:], t.body[2:]
    assert _dump(ours) == _dump(theirs)


def test_merge_elements_is_upstream_except_the_hard_hyphen_branch():
    ours, theirs = _tree(P._merge_elements), _tree(P.text_upstream("merge_elements"))
    oi = [i for i, n in enumerate(ours.body) if isinstance(n, ast.If)]
    ti = [i for i, n in enumerate(theirs.body) if isinstance(n, ast.If)]
    o, t = ours.body[oi[0]], theirs.body[ti[0]]
    assert isinstance(o, ast.If) and isinstance(t, ast.If)
    # everything around the join is upstream's
    assert _dump(ours.body[: oi[0]]) == _dump(theirs.body[: ti[0]])
    assert _dump(ours.body[oi[0] + 1 :]) == _dump(theirs.body[ti[0] + 1 :])
    # upstream: if SOFT or HARD: drop the last char ... else: space join
    assert isinstance(t.test, ast.BoolOp) and isinstance(t.test.op, ast.Or)
    soft, hard = t.test.values
    assert _dump(o.test) == _dump(soft) and _dump(o.body) == _dump(t.body)
    assert len(o.orelse) == 1 and isinstance(o.orelse[0], ast.If)
    elif_ = o.orelse[0]
    assert _dump(elif_.test) == _dump(hard)
    assert _dump(elif_.orelse) == _dump(t.orelse)
    assert (
        [ast.unparse(s) for s in elif_.body]
        == [
            "_record_merge(new_item, merged_elem)",  # Standard gate evidence (off by default)
            "prov = ProvenanceItem(page_no=prov.page_no, charspan=(len(new_item.text), "
            "len(new_item.text) + len(merged_elem.text)), bbox=prov.bbox)",
            "new_item.text = new_item.text + merged_elem.text",
            "new_item.orig = new_item.orig + merged_elem.text",
        ]
    )


def test_footnote_serializers_call_upstream_and_only_append_notes():
    """Upstream's serialize runs unchanged; the wrapper adds the attached notes
    after it (never inside a nested table)."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(P._with_attached_footnotes)))
    calls = [
        ast.unparse(n)
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "upstream"
    ]
    assert calls == [
        "upstream(self, item=item, doc_serializer=doc_serializer, doc=doc, **kwargs)"
    ]
    for key in ("table_markdown", "picture_markdown"):
        current = P._text_owner(key).__dict__[P.TEXT_TARGETS[key][3]]
        assert current.__cb5400_upstream__ is P.text_upstream(key)


# --------------------------------------------------------------------------- #
# C. Guards (D-39 pattern): versions, sources, all or nothing, idempotence
# --------------------------------------------------------------------------- #


def test_apply_is_idempotent_and_fingerprints_follow_the_upstream_source(unpatched):
    assert P.apply_text_preservation() is True
    first = {k: P._text_owner(k).__dict__[t[3]] for k, t in P.TEXT_TARGETS.items()}
    assert P.apply_text_preservation() is True
    for key, target in P.TEXT_TARGETS.items():
        current = P._text_owner(key).__dict__[target[3]]
        assert current is first[key]
        assert current.__cb5400_patch__ == target[0]
        assert not hasattr(current.__cb5400_upstream__, "__cb5400_patch__")  # one layer
    assert compat.check_fingerprints(compat.DOCLING_FINGERPRINTS) == []
    for key, target in P.TEXT_TARGETS.items():
        name = f"{target[1]}:{target[2]}.{target[3]}"
        assert compat.DOCLING_FINGERPRINTS[name] == target[4]
    status = P.text_status()
    assert status["applied"] is True and status["problems"] == []
    assert (status["docling"], status["docling_core"]) == ("2.129.0", "2.96.0")


@pytest.mark.parametrize("dist", ["docling", "docling-core"])
def test_another_version_is_refused_and_nothing_is_patched(
    unpatched, monkeypatch, dist
):
    real = P._installed
    monkeypatch.setattr(P, "_installed", lambda d: "9.9.9" if d == dist else real(d))
    with pytest.raises(P.TextPreservationPatchError, match=f"{dist} 9.9.9"):
        P.apply_text_preservation(required=True)
    assert not any(
        hasattr(P._text_owner(k).__dict__[t[3]], "__cb5400_patch__")
        for k, t in P.TEXT_TARGETS.items()
    )
    assert isinstance(
        P.TextPreservationPatchError("x"), ValueError
    )  # jobs stop, no retry
    messages: list[str] = []
    from loguru import logger

    sink = logger.add(lambda m: messages.append(str(m)), level="ERROR")
    try:
        assert P.apply_text_preservation(required=False) is False
    finally:
        logger.remove(sink)
    assert any("text preservation is not available" in m for m in messages)
    assert P.text_status()["problems"]


def test_a_changed_upstream_source_is_refused_all_or_nothing(unpatched, monkeypatch):
    targets = dict(P.TEXT_TARGETS)
    pid, mod, owner, attr, _sha = targets["picture_markdown"]  # the LAST target
    targets["picture_markdown"] = (pid, mod, owner, attr, "0" * 64)
    monkeypatch.setattr(P, "TEXT_TARGETS", targets)
    with pytest.raises(P.TextPreservationPatchError, match="not the verified upstream"):
        P.apply_text_preservation()
    for key, target in targets.items():  # not even the first targets
        assert not hasattr(P._text_owner(key).__dict__[target[3]], "__cb5400_patch__")


def test_concurrent_apply_patches_once(unpatched):
    errors: list[BaseException] = []
    start = threading.Barrier(16)

    def work():
        try:
            start.wait(timeout=10)
            for _ in range(30):
                assert P.apply_text_preservation()
        except BaseException as e:  # noqa: BLE001 - reported below
            errors.append(e)

    threads = [threading.Thread(target=work) for _ in range(16)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=60)
    assert not errors
    for key, target in P.TEXT_TARGETS.items():
        current = P._text_owner(key).__dict__[target[3]]
        assert current.__cb5400_upstream__ is P.text_upstream(key)
        assert not hasattr(current.__cb5400_upstream__, "__cb5400_patch__")


def test_a_model_built_before_apply_runs_the_patched_code(unpatched):
    """The patch is on the class: a pipeline (and its PageAssembleModel)
    initialised by an earlier job, before apply, still gets it."""
    from docling.models.stages.page_assemble.page_assemble_model import (
        PageAssembleModel,
        PageAssembleOptions,
    )

    model = PageAssembleModel(options=PageAssembleOptions())
    assert model.sanitize_text(["05/2024/TT-", "BNNPTNT"]) == "05/2024/TTBNNPTNT"
    assert P.apply_text_preservation()
    assert model.sanitize_text(["05/2024/TT-", "BNNPTNT"]) == "05/2024/TT- BNNPTNT"


def test_upstream_context_restores_the_patch_and_blocks_apply_inside():
    _apply()
    with P.upstream_text_preservation():
        assert not P.text_patches_applied()
        assert P.apply_text_preservation() is False  # tests asked for upstream
        with P.upstream_text_preservation():
            assert not P.text_patches_applied()
        assert not P.text_patches_applied()
    assert P.text_patches_applied()


CHILD = """
import asyncio, json, sys, tempfile
from open_notebook.ocr import docling_patches as P
out = {"import": P.text_patches_applied()}
from content_core import ContentCoreConfig
from open_notebook.ocr import docling_extract
from open_notebook.ocr.options import OcrSettings
from docling.datamodel.pipeline_options import PdfPipelineOptions
docling_extract.build_pipeline_options = lambda *a, **k: PdfPipelineOptions()
out["after_import"] = P.text_patches_applied()
mode = sys.argv[1]
if mode == "converter":
    docling_extract.build_converter(ContentCoreConfig(), OcrSettings())
elif mode == "legal":
    from docling_core.types.doc import DoclingDocument
    from open_notebook.ocr import legal_normalizer
    legal_normalizer.normalize_document(DoclingDocument(name="x"))
elif mode == "graph":
    from open_notebook.graphs import source
    pdf = tempfile.mktemp(suffix=".pdf")
    open(pdf, "wb").write(b"%PDF-1.4\\n%%EOF\\n")
    asyncio.run(source._apply_docling_text_preservation({"file_path": pdf}, True))
out["after"] = P.text_patches_applied()
print("RESULT", json.dumps(out, sort_keys=True))
"""


@pytest.mark.parametrize("mode", ["converter", "legal", "graph"])
def test_a_fresh_worker_process_is_patched_before_its_first_conversion(mode):
    """A new interpreter (worker start / spawn): nothing at import; the first
    converter, Legal normalization or source-graph extraction applies it."""
    out = subprocess.run(
        [sys.executable, "-c", CHILD, mode],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=600,
    )
    assert out.returncode == 0, out.stderr[-3000:]
    line = [ln for ln in out.stdout.splitlines() if ln.startswith("RESULT")][-1]
    assert line == 'RESULT {"after": true, "after_import": false, "import": false}'


# --------------------------------------------------------------------------- #
# D. Where it is applied: every engine, content-core's own path, the graph
# --------------------------------------------------------------------------- #


def test_every_engine_converter_is_built_patched(unpatched, monkeypatch):
    from content_core import ContentCoreConfig
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    from open_notebook.ocr import catalog, docling_extract
    from open_notebook.ocr.options import OcrSettings

    monkeypatch.setattr(
        docling_extract, "build_pipeline_options", lambda *a, **k: PdfPipelineOptions()
    )
    engines = list(catalog.ENGINES)
    assert {"rapidocr", "easyocr", "tesseract_fast", "tesseract_best"} <= set(engines)
    for engine in engines:
        for key, target in P.TEXT_TARGETS.items():
            setattr(P._text_owner(key), target[3], P.text_upstream(key))
        docling_extract.build_converter(ContentCoreConfig(), OcrSettings(engine=engine))
        assert P.text_patches_applied(), engine


def test_a_conversion_on_an_unverified_docling_is_refused(unpatched, monkeypatch):
    from content_core import ContentCoreConfig

    from open_notebook.ocr import docling_extract
    from open_notebook.ocr.options import OcrSettings

    real = P._installed
    monkeypatch.setattr(
        P, "_installed", lambda d: "2.130.0" if d == "docling" else real(d)
    )
    with pytest.raises(P.TextPreservationPatchError):
        docling_extract.build_converter(ContentCoreConfig(), OcrSettings())


@pytest.mark.parametrize(
    "name, content, required",
    [("scan.pdf", b"%PDF-1.4\n%%EOF\n", True), ("notes.txt", b"plain text\n", False)],
)
def test_the_source_graph_requires_the_patch_for_pdfs_only(
    unpatched, monkeypatch, tmp_path, name, content, required
):
    from open_notebook.graphs import source

    path = tmp_path / name
    path.write_bytes(content)
    real = P._installed
    monkeypatch.setattr(
        P, "_installed", lambda d: "2.130.0" if d == "docling" else real(d)
    )
    run = source._apply_docling_text_preservation({"file_path": str(path)}, True)
    if required:
        with pytest.raises(P.TextPreservationPatchError):
            asyncio.run(run)
    else:
        asyncio.run(run)  # logged; a text file never reaches Docling's PDF pipeline
    assert not P.text_patches_applied()


def test_content_cores_own_docling_path_runs_patched(unpatched, monkeypatch, tmp_path):
    """content-core's default path builds its OWN DocumentConverter: the graph
    applies the patch before it runs (the patch lives on Docling's classes)."""
    from unittest.mock import AsyncMock, MagicMock

    from content_core.common import ExtractionOutput

    from open_notebook.graphs import source

    monkeypatch.setattr("open_notebook.config.UPLOADS_FOLDER", str(tmp_path))
    monkeypatch.setattr(source, "should_use_native_ocr", AsyncMock(return_value=False))
    mm = MagicMock()
    mm.get_defaults = AsyncMock(
        return_value=MagicMock(default_speech_to_text_model=None)
    )
    monkeypatch.setattr(source, "ModelManager", lambda: mm)
    seen: list[bool] = []

    async def extract_content(**_kw):
        seen.append(P.text_patches_applied())
        return ExtractionOutput(title="t", content="nội dung")

    monkeypatch.setattr(source, "extract_content", extract_content)
    pdf = tmp_path / "upload.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    state = {
        "source_id": "source:1",
        "content_state": {"file_path": str(pdf)},
        "embed": False,
        "apply_transformations": [],
    }
    asyncio.run(source.content_process(cast(Any, state)))
    assert seen == [True]


# --------------------------------------------------------------------------- #
# E. Docling's own block merge (reading order): page / column end hyphen
# --------------------------------------------------------------------------- #


def _blocks(pages: list[list[tuple[str, str, list[float]]]], sizes=None) -> Any:
    """DoclingDocument from Docling's REAL ReadingOrderModel: (label, text,
    [l, t, r, b]) per page; one cell per element."""
    from docling.datamodel.base_models import AssembledUnit, Cluster, Page, TextElement
    from docling.models.stages.reading_order.readingorder_model import (
        ReadingOrderModel,
        ReadingOrderOptions,
    )
    from docling_core.types.doc import BoundingBox, CoordOrigin, DocItemLabel, Size
    from docling_core.types.doc.page import BoundingRectangle, TextCell

    sizes = sizes or [A4] * len(pages)
    conv = _conv(sizes=sizes)
    conv.pages = [
        Page(page_no=i + 1, size=Size(width=w, height=h))
        for i, (w, h) in enumerate(sizes)
    ]
    elements, n = [], 0
    for page_no, page in enumerate(pages, start=1):
        for label, text, (left, top, r, b) in page:
            box = BoundingBox(l=left, t=top, r=r, b=b, coord_origin=CoordOrigin.TOPLEFT)
            lab = getattr(DocItemLabel, label.upper())
            cell = TextCell(
                index=0, text=text, orig=text, from_ocr=True, confidence=1.0,
                rect=BoundingRectangle.from_bounding_box(box),
            )  # fmt: skip
            cl = Cluster(id=n, label=lab, bbox=box, confidence=0.9, cells=[cell])
            elements.append(
                TextElement(label=lab, id=n, page_no=page_no, text=text, cluster=cl)
            )
            n += 1
    conv.assembled = AssembledUnit(elements=elements, body=elements, headers=[])
    return ReadingOrderModel(ReadingOrderOptions())(conv)


def _cross_page(first: str, second: str) -> Any:
    return _blocks(
        [
            [("text", first, [70, 760, 520, 774])],
            [("text", second, [70, 60, 520, 74])],
        ]
    )


@pytest.mark.parametrize(
    "first, second, joined",
    [
        (
            "hợp tác xuyên-",
            "biên giới với các tỉnh",
            "hợp tác xuyên-biên giới với các tỉnh",
        ),
        (
            "chương trình phát-",
            "triển nông thôn mới",
            "chương trình phát-triển nông thôn mới",
        ),
        ("theo mã 0001-", "a của phụ lục", "theo mã 0001-a của phụ lục"),
    ],
)
def test_a_page_end_hyphen_is_kept_and_the_char_span_is_exact(first, second, joined):
    _apply()
    doc = _cross_page(first, second)
    (item,) = doc.texts
    assert item.text == joined and item.orig == joined
    a, b = item.prov
    assert (a.page_no, b.page_no) == (1, 2)
    assert item.text[b.charspan[0] : b.charspan[1]] == second  # where page 2 starts
    assert item.text[: b.charspan[0]] == first
    assert doc.export_to_markdown() == joined


def test_control_upstream_block_merge_drops_the_page_end_hyphen():
    with P.upstream_text_preservation():
        doc = _cross_page("hợp tác xuyên-", "biên giới với các tỉnh")
    (item,) = doc.texts
    assert item.text == "hợp tác xuyênbiên giới với các tỉnh"
    # upstream's char span then points one character too far
    start = item.prov[1].charspan[0]
    assert item.text[start:] != "biên giới với các tỉnh"


def test_other_block_joins_are_upstreams():
    """An uppercase / digit continuation is joined with a space, a soft hyphen
    is removed (invisible line-break hint) - upstream rules, unchanged."""
    _apply()
    upper = _cross_page("Thông tư số 05/2024/TT-", "BNNPTNT ngày 01/02/2024")
    assert upper.texts[0].text == "Thông tư số 05/2024/TT- BNNPTNT ngày 01/02/2024"
    soft = _cross_page("hợp tác xuyên­", "biên giới")
    with P.upstream_text_preservation():
        soft_up = _cross_page("hợp tác xuyên­", "biên giới")
    assert soft.texts[0].text == soft_up.texts[0].text == "hợp tác xuyênbiên giới"
    plain = _cross_page("của pháp luật", "hiện hành.")
    assert plain.texts[0].text == "của pháp luật hiện hành."
    start, end = plain.texts[0].prov[1].charspan
    assert plain.texts[0].text[start:end] == "hiện hành."


def test_legal_splits_the_patched_page_end_join_back_into_its_pages():
    """Legal never joins across pages (E1-09): the patched concat join is
    recognised from its char span and split, every character kept."""
    from open_notebook.ocr import legal_normalizer as LN

    _apply()
    doc = _cross_page("hợp tác xuyên-", "biên giới với các tỉnh")
    res = LN.normalize_document(doc)
    lines = [ln for ln in res.content.splitlines() if ln.strip()]
    assert lines == ["hợp tác xuyên-", "biên giới với các tỉnh"]
    assert {w["code"] for w in res.warnings} >= {"upstream_merge_undone"}


# --------------------------------------------------------------------------- #
# F. A PDF text layer through docling-parse (Docling's default PDF backend)
# --------------------------------------------------------------------------- #


def _text_layer_regions(tmp_path: Path, texts: list[Any]) -> list[str]:
    import generate_overlay_fixtures as fx
    from docling.backend.docling_parse_backend import (
        ThreadedDoclingParseDocumentBackend,
    )
    from docling.datamodel.base_models import (
        Cluster,
        InputFormat,
        LayoutPrediction,
        Page,
    )
    from docling.datamodel.document import ConversionResult, InputDocument
    from docling.datamodel.pipeline_options import LayoutOptions
    from docling.models.stages.page_assemble.page_assemble_model import (
        PageAssembleModel,
        PageAssembleOptions,
    )
    from docling.utils.layout_postprocessor import LayoutPostprocessor
    from docling_core.types.doc import BoundingBox, CoordOrigin, DocItemLabel

    pdf = tmp_path / "text_layer.pdf"
    pdf.write_bytes(fx.build_pdf([fx.Page(texts=texts)]))
    in_doc = InputDocument(
        path_or_stream=pdf,
        format=InputFormat.PDF,
        backend=ThreadedDoclingParseDocumentBackend,
    )
    conv = ConversionResult(input=in_doc)
    backend = next(iter(cast(Any, in_doc._backend).iter_pages()))
    page = Page(page_no=1)
    page._backend = backend
    page.size = backend.get_size()
    page.parsed_page = backend.get_segmented_page()
    region = BoundingBox(l=60, t=60, r=540, b=800, coord_origin=CoordOrigin.TOPLEFT)
    clusters = [
        Cluster(id=0, label=DocItemLabel.TEXT, bbox=region, confidence=0.9, cells=[])
    ]
    processed = LayoutPostprocessor(page, clusters, LayoutOptions()).postprocess()
    page.predictions.layout = LayoutPrediction(clusters=processed)
    list(PageAssembleModel(options=PageAssembleOptions())(conv, [page]))
    assert page.assembled is not None
    return [e.text for e in page.assembled.elements]


def test_pdf_text_layer_keeps_every_hyphen(tmp_path):
    import generate_overlay_fixtures as fx

    texts = [
        fx.Text("Can cu Thong tu so 05/2024/TT-", 72, 700, 12),
        fx.Text("BNNPTNT ngay 01/02/2024; giai doan 2021-", 72, 685, 12),
        fx.Text("2025. Luu: VT-", 72, 670, 12),
        fx.Text("KHTC.", 160, 670, 12),  # its own line cell, same baseline
    ]
    with P.upstream_text_preservation():
        upstream = _text_layer_regions(tmp_path, texts)
    assert upstream == [
        "Can cu Thong tu so 05/2024/TTBNNPTNT ngay 01/02/2024; giai doan 20212025. "
        "Luu: VTKHTC."
    ]
    _apply()
    assert _text_layer_regions(tmp_path, texts) == [
        "Can cu Thong tu so 05/2024/TT-BNNPTNT ngay 01/02/2024; giai doan 2021-2025. "
        "Luu: VT- KHTC."
    ]


# --------------------------------------------------------------------------- #
# G. Table cells (TableFormer tokens): no hyphen lost upstream - control
# --------------------------------------------------------------------------- #


def test_control_table_cell_tokens_keep_the_hyphen_upstream():
    """A table cell's text is its word tokens joined with a space by
    docling-core (``TableCell.from_dict_format``): the hyphen is never dropped
    there (a line-broken number keeps a space: '05/2024/TT- BNNPTNT' - recorded
    limitation, no character lost). Not touched by the patch."""
    from docling_core.types.doc.document import TableCell

    cell = TableCell.model_validate(
        {
            "bbox": {"l": 0, "t": 0, "r": 10, "b": 10, "token": ""},
            "text_cell_bboxes": [{"token": "05/2024/TT-"}, {"token": "BNNPTNT"}],
            "row_span": 1,
            "col_span": 1,
            "start_row_offset_idx": 0,
            "end_row_offset_idx": 1,
            "start_col_offset_idx": 0,
            "end_col_offset_idx": 1,
        }  # fmt: skip
    )
    assert cell.text == "05/2024/TT- BNNPTNT"


# --------------------------------------------------------------------------- #
# H. End to end: rendered scan -> real Tesseract -> Docling -> Markdown ->
#    convert_file (Standard and Legal) -> save_source -> Source.full_text
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

SCAN = [
    ["Căn cứ Thông tư số 05/2024/TT-", "BNNPTNT ngày 01 tháng 02 năm 2024;"],
    ["Kế hoạch phát triển giai đoạn 2021-", "2025 và mã số 0001-", "0002."],
    ["Nơi nhận: Lưu VT- KHTC; giai đoạn 2021- 2025; khoản 1- Điều 5."],
]


def _scan_to_document(tmp_path: Path, monkeypatch) -> tuple[Any, list[str]]:
    """(ConversionResult with its DoclingDocument, raw TSV word fields of the
    OCR invocations) - every stage after the layout model is Docling's own."""
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import (
        AssembledUnit,
        BoundingBox,
        Cluster,
        ConversionStatus,
        InputFormat,
        LayoutPrediction,
        Page,
    )
    from docling.datamodel.document import ConversionResult, InputDocument
    from docling.datamodel.pipeline_options import (
        LayoutOptions,
        OcrMode,
        TesseractCliOcrOptions,
    )
    from docling.models.stages.ocr import tesseract_ocr_cli_model as upstream_mod
    from docling.models.stages.page_assemble.page_assemble_model import (
        PageAssembleModel,
        PageAssembleOptions,
    )
    from docling.models.stages.reading_order.readingorder_model import (
        ReadingOrderModel,
        ReadingOrderOptions,
    )
    from docling.utils.layout_postprocessor import LayoutPostprocessor
    from docling_core.types.doc import DocItemLabel
    from PIL import Image, ImageDraw, ImageFont

    P.apply()  # E0-07
    raw: list[str] = []
    real_run = subprocess.run

    def spy(cmd, *a, **kw):
        res = real_run(cmd, *a, **kw)
        if list(cmd[-2:]) == ["stdout", "tsv"]:
            for row in res.stdout.decode("utf-8").splitlines()[1:]:
                fields = row.split("\t")
                if len(fields) >= 12 and fields[0] == "5" and fields[11].strip():
                    raw.append(fields[11])
        return res

    monkeypatch.setattr(P.subprocess, "run", spy)
    font = ImageFont.truetype(FONT, 40)
    k = 72 / 300
    img = Image.new("L", (2480, 3508), 255)
    draw = ImageDraw.Draw(img)
    regions, y = [], 200
    for lines in SCAN:
        top, width = y, 0
        for text in lines:
            draw.text((160, y), text, font=font, fill=0)
            width = max(width, int(font.getlength(text)))
            y += 70
        regions.append(
            BoundingBox(
                l=(130) * k, t=(top - 20) * k, r=(190 + width) * k, b=(y + 10) * k
            )
        )
        y += 260
    pdf = tmp_path / "scan.pdf"
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
    processed = LayoutPostprocessor(page, clusters, LayoutOptions()).postprocess()
    page.predictions.layout = LayoutPrediction(clusters=processed)
    list(PageAssembleModel(options=PageAssembleOptions())(conv, [page]))
    assert page.assembled is not None
    conv.pages = [page]
    conv.assembled = AssembledUnit(
        elements=page.assembled.elements,
        body=page.assembled.body,
        headers=page.assembled.headers,
    )
    conv.document = ReadingOrderModel(ReadingOrderOptions())(conv)
    conv.status = ConversionStatus.SUCCESS  # every stage ran without an error
    return conv, raw


def _stored_full_text(conv: Any, tmp_path: Path, monkeypatch, legal: bool) -> str:
    """convert_file (the production export, Standard or Legal) and save_source
    (what the Source row stores) on that conversion."""
    from content_core import ContentCoreConfig
    from content_core.common import ExtractionOutput

    from open_notebook.graphs import source as graph
    from open_notebook.ocr import docling_extract, pdf_prep
    from open_notebook.ocr.options import OcrSettings

    class _Converter:
        initialized_pipelines: dict = {}

    monkeypatch.setattr(
        docling_extract,
        "convert_document",
        lambda *_a, **_k: (conv, _Converter(), pdf_prep.PdfPrep()),
    )
    ocr = OcrSettings(
        engine="tesseract_fast", text_normalization="legal" if legal else "standard"
    )
    assert ocr.legal_normalization is legal
    pdf = tmp_path / "scan.pdf"
    content, meta = docling_extract.convert_file(str(pdf), ContentCoreConfig(), ocr)
    if legal:
        assert meta["legal_normalization_status"] == "applied"

    class _Source:
        title = "Processing..."
        full_text = None
        asset = None

        async def save(self):
            return None

        async def vectorize(self):
            return "command:x"

        async def claim_review_embed(self):
            return False

    row = _Source()

    async def get(_id):
        return row

    monkeypatch.setattr(graph.Source, "get", get)
    state = {
        "source_id": "source:1",
        "content_state": {"file_path": str(pdf)},
        "extraction": ExtractionOutput(
            title="scan.pdf", content=content, metadata=meta
        ),
        "embed": False,
        "apply_transformations": [],
    }
    asyncio.run(graph.save_source(cast(Any, state)))
    assert row.full_text == content
    return cast(str, row.full_text)


@needs_tesseract
@pytest.mark.parametrize("legal", [False, True], ids=["standard", "legal"])
def test_e2e_every_hyphen_of_the_raw_tsv_reaches_source_full_text(
    tmp_path, monkeypatch, legal
):
    _apply()
    conv, raw = _scan_to_document(tmp_path, monkeypatch)
    full_text = _stored_full_text(conv, tmp_path, monkeypatch, legal)
    for token in ("05/2024/TT-", "2021-", "0001-", "VT-", "1-"):
        assert token in raw, (token, raw)  # what Tesseract read (E0-07: verbatim)
    assert full_text.count("-") == sum(w.count("-") for w in raw)
    for must in ("05/2024/TT-BNNPTNT", "2021-2025", "0001-0002.", "VT- KHTC;",
                 "2021- 2025;", "1- Điều 5."):  # fmt: skip
        assert must in full_text, must


@needs_tesseract
def test_control_e2e_upstream_loses_them_in_source_full_text(tmp_path, monkeypatch):
    with P.upstream_text_preservation():
        conv, raw = _scan_to_document(tmp_path, monkeypatch)
        full_text = _stored_full_text(conv, tmp_path, monkeypatch, legal=False)
    assert full_text.count("-") < sum(w.count("-") for w in raw)
    assert "05/2024/TTBNNPTNT" in full_text and "VTKHTC" in full_text


# --------------------------------------------------------------------------- #
# I. D8-02: footnotes attached to a table / picture, Standard and Legal
# --------------------------------------------------------------------------- #


def _doc_with(*parts: Any) -> Any:
    """A DoclingDocument assembled with docling-core's API: ("text", s),
    ("table", rows, [note texts]), ("picture", caption, [note texts]),
    ("note", s) for a footnote in the body. Footnotes are children of their
    table / picture and listed in its ``footnotes``, as Docling builds them."""
    from docling_core.types.doc import (
        BoundingBox,
        CoordOrigin,
        DocItemLabel,
        DoclingDocument,
        ProvenanceItem,
        Size,
        TableCell,
        TableData,
    )

    doc = DoclingDocument(name="d9")
    doc.add_page(page_no=1, size=Size(width=595, height=842))
    doc.add_page(page_no=2, size=Size(width=595, height=842))
    y = [50.0]

    def prov(page=1):
        y[0] += 20
        return ProvenanceItem(
            page_no=page,
            bbox=BoundingBox(
                l=70,
                t=842 - y[0],
                r=500,
                b=842 - y[0] - 12,
                coord_origin=CoordOrigin.BOTTOMLEFT,
            ),  # fmt: skip
            charspan=(0, 0),
        )

    for part in parts:
        kind = part[0]
        if kind == "text":
            doc.add_text(label=DocItemLabel.TEXT, text=part[1], prov=prov())
        elif kind == "note":
            doc.add_text(label=DocItemLabel.FOOTNOTE, text=part[1], prov=prov())
        elif kind == "table":
            rows = part[1]
            cells = [
                TableCell(
                    text=v,
                    start_row_offset_idx=r,
                    end_row_offset_idx=r + 1,
                    start_col_offset_idx=c,
                    end_col_offset_idx=c + 1,
                    column_header=r == 0,
                )  # fmt: skip
                for r, row in enumerate(rows)
                for c, v in enumerate(row)
            ]
            table = doc.add_table(
                data=TableData(
                    num_rows=len(rows), num_cols=len(rows[0]), table_cells=cells
                ),
                prov=prov(),
            )
            for note in part[2]:
                page = 2 if note.startswith("[p2]") else 1
                text = note.removeprefix("[p2]")
                kw = {} if text.startswith("[noprov]") else {"prov": prov(page)}
                text = text.removeprefix("[noprov]")
                item = doc.add_text(
                    label=DocItemLabel.FOOTNOTE, text=text, parent=table, **kw
                )
                table.footnotes.append(item.get_ref())
        elif kind == "picture":
            pic = doc.add_picture(prov=prov())
            if part[1]:
                cap = doc.add_text(
                    label=DocItemLabel.CAPTION, text=part[1], parent=pic, prov=prov()
                )
                pic.captions.append(cap.get_ref())
            for note in part[2]:
                item = doc.add_text(
                    label=DocItemLabel.FOOTNOTE, text=note, parent=pic, prov=prov()
                )
                pic.footnotes.append(item.get_ref())
    return doc


ROWS = [
    ["Chỉ tiêu", "Mức thu (đồng)"],
    ["Phí thẩm định", "1.250.000"],
    ["Lệ phí", "12,5%"],
]
NOTE = "(1) Theo Thông tư số 15/2024/TT-BNNPTNT ngày 01/02/2024, áp dụng từ 01/3/2024."


def _standard_and_legal(doc: Any) -> tuple[str, str]:
    from open_notebook.ocr import legal_normalizer as LN

    _apply()
    return doc.export_to_markdown(), LN.normalize_document(doc).content


def _upstream_standard_and_legal(doc: Any) -> tuple[str, str]:
    from open_notebook.ocr import legal_normalizer as LN

    with P.upstream_text_preservation():
        return doc.export_to_markdown(), LN.normalize_document(doc).content


def _after(md: str, table_line: str, note: str) -> bool:
    """``note`` is its own block right after the block holding ``table_line``."""
    blocks = md.split("\n\n")
    for i, block in enumerate(blocks):
        if table_line in block:
            return i + 1 < len(blocks) and blocks[i + 1] == note
    return False


def test_control_upstream_markdown_loses_the_note_of_a_table():
    doc = _doc_with(
        ("text", "Bảng 1. Mức thu"), ("table", ROWS, [NOTE]), ("text", "Điều 2. Tiếp")
    )
    with P.upstream_text_preservation():
        assert NOTE not in doc.export_to_markdown()
    assert NOTE in [t.text for t in doc.texts]  # it IS in the document


def test_one_table_one_footnote_standard_and_legal():
    doc = _doc_with(
        ("text", "Bảng 1. Mức thu"), ("table", ROWS, [NOTE]), ("text", "Điều 2. Tiếp")
    )
    upstream = _upstream_standard_and_legal(doc)
    for md, before in zip(_standard_and_legal(doc), upstream):
        assert NOTE not in before
        assert md.count(NOTE) == 1
        assert _after(md, "Phí thẩm định", NOTE)
        assert md.replace(f"\n\n{NOTE}", "") == before  # nothing else changes
        for number in (
            "1.250.000",
            "12,5%",
            "15/2024/TT-BNNPTNT",
            "01/02/2024",
            "01/3/2024",
        ):
            assert number in md


def test_many_footnotes_keep_their_order_and_markers():
    notes = ["(1) Mức 1.", "(2) Mức 2.", "(*) Ghi chú chung.", "a) điểm a."]
    doc = _doc_with(("table", ROWS, notes), ("text", "Điều 3."))
    for md in _standard_and_legal(doc):
        blocks = md.split("\n\n")
        i = next(n for n, b in enumerate(blocks) if "Phí thẩm định" in b)
        assert blocks[i + 1 : i + 5] == notes


def test_consecutive_tables_each_get_their_own_note():
    doc = _doc_with(
        ("table", ROWS, ["(1) Bảng một."]), ("table", ROWS, ["(2) Bảng hai."])
    )
    for md in _standard_and_legal(doc):
        blocks = md.split("\n\n")
        assert blocks.count("(1) Bảng một.") == blocks.count("(2) Bảng hai.") == 1
        assert blocks.index("(1) Bảng một.") < blocks.index("(2) Bảng hai.")
        tables = [n for n, b in enumerate(blocks) if b.startswith("|")]
        assert (
            tables[0]
            < blocks.index("(1) Bảng một.")
            < tables[1]
            < blocks.index("(2) Bảng hai.")
        )


def test_a_picture_note_follows_the_picture_and_its_caption_stays():
    doc = _doc_with(
        ("text", "Hình 1."),
        ("picture", "Sơ đồ vị trí khu đất", ["(*) Nguồn: Sở TN&MT, 2024."]),
        ("text", "Điều 4."),
    )
    # rendered exactly as each mode renders the same text as a paragraph
    # (Standard: docling-core escapes "&" as "&amp;" in every text, unchanged;
    # Legal keeps it, R2-02)
    paragraph = _standard_and_legal(_doc_with(("text", "(*) Nguồn: Sở TN&MT, 2024.")))
    assert paragraph == ("(*) Nguồn: Sở TN&amp;MT, 2024.", "(*) Nguồn: Sở TN&MT, 2024.")
    for md, as_paragraph in zip(_standard_and_legal(doc), paragraph):
        assert md.count(as_paragraph) == 1
        assert md.count("Sơ đồ vị trí khu đất") == 1
        assert (
            md.index("Sơ đồ vị trí khu đất")
            < md.index("(*) Nguồn")
            < md.index("Điều 4.")
        )


def test_a_note_referenced_by_two_tables_is_written_once():
    doc = _doc_with(("table", ROWS, [NOTE]), ("table", ROWS, []))
    note_ref = doc.tables[0].footnotes[0]
    doc.tables[1].footnotes.append(note_ref)
    for md in _standard_and_legal(doc):
        assert md.count(NOTE) == 1
        assert _after(md, "Phí thẩm định", NOTE)


def test_a_note_on_the_next_page_and_a_note_without_provenance():
    doc = _doc_with(
        ("table", ROWS, ["[p2](1) Trang sau.", "[noprov](2) Không vị trí."])
    )
    for md in _standard_and_legal(doc):
        assert md.count("(1) Trang sau.") == md.count("(2) Không vị trí.") == 1


def test_an_invalid_reference_is_skipped_without_error_or_loop():
    from docling_core.types.doc.document import RefItem

    doc = _doc_with(("table", ROWS, [NOTE]))
    doc.tables[0].footnotes.insert(0, RefItem(cref="#/texts/999"))
    doc.tables[0].footnotes.append(RefItem(cref="#/tables/0"))  # itself: not a text
    for md in _standard_and_legal(doc):
        assert md.count(NOTE) == 1


def test_normal_footnotes_and_documents_without_notes_are_byte_identical():
    """A body footnote (not attached) and every Legal fixture's Standard
    Markdown: the patched export equals upstream's byte for byte."""
    sys.path.insert(0, str(ROOT / "tests"))
    import legal_harness as H

    doc = _doc_with(
        ("text", "Điều 1."), ("note", "(1) Ghi chú cuối trang."), ("table", ROWS, [])
    )
    with P.upstream_text_preservation():
        upstream = doc.export_to_markdown()
    _apply()
    assert doc.export_to_markdown() == upstream
    fx = H.load_fixtures()
    for fixture in fx.FIXTURES:
        built = H.build_document(fixture)
        attached = [
            r for it in [*built.tables, *built.pictures] for r in (it.footnotes or [])
        ]
        with P.upstream_text_preservation():
            before = built.export_to_markdown()
        after = built.export_to_markdown()
        if not attached:
            assert after == before, fixture["name"]
        else:
            notes = [r.resolve(built).text for r in attached]
            for note in notes:
                assert after.count(note) >= 1, (fixture["name"], note)


def test_the_footnote_label_filter_of_the_caller_is_respected():
    from docling_core.transforms.serializer.markdown import (
        MarkdownDocSerializer,
        MarkdownParams,
    )
    from docling_core.types.doc import DocItemLabel

    doc = _doc_with(("table", ROWS, [NOTE]))
    _apply()
    labels = set(DocItemLabel) - {DocItemLabel.FOOTNOTE}
    md = (
        MarkdownDocSerializer(doc=doc, params=MarkdownParams(labels=labels))
        .serialize()
        .text
    )
    assert NOTE not in md and "Phí thẩm định" in md


def test_control_html_export_still_omits_attached_notes_and_json_keeps_them():
    """The patch is for the Markdown export (the default ``docling_output_format``,
    Standard and Legal). HTML output is NOT fixed (recorded limitation); JSON
    holds every text item, the note included."""
    doc = _doc_with(("table", ROWS, [NOTE]))
    _apply()
    assert NOTE not in doc.export_to_html()
    assert NOTE in json.dumps(doc.export_to_dict(), ensure_ascii=False)
