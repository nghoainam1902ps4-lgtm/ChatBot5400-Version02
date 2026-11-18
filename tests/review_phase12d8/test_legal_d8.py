"""Phase 12D8 final review: Legal normalizer 1.3.0 - counter-examples and controls.

Review only: runtime code is not modified. ``xfail(strict=True)`` = expected
safe behaviour that fails today (finding id in the reason); ``test_verified_*``
/ ``test_control_*`` = passes, records something the review checked itself.

Documents are built by Docling's REAL ``ReadingOrderModel`` (reading order,
its own TEXT merge, captions / footnotes, furniture) from synthetic layout
elements - like tests/legal_harness.py, but with PER-PAGE sizes: the harness
(and so all 92 oracle fixtures) gives every page 595 x 842.
"""

from __future__ import annotations

import random
import tempfile
import warnings
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("docling")

from open_notebook.ocr import legal_normalizer as LN  # noqa: E402

A4 = (595, 842)


def T(text: str, left: float, top: float, right: float, bottom: float, label="text"):
    return {"label": label, "text": text, "bbox": [left, top, right, bottom]}


def build(pages: list[list[dict[str, Any]]], sizes: list[tuple[int, int]] | None = None):
    """(DoclingDocument, merge evidence) from Docling's real ReadingOrderModel."""
    import pypdfium2 as pdfium
    from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
    from docling.datamodel.base_models import (
        AssembledUnit,
        Cluster,
        FigureElement,
        InputFormat,
        Page,
        Table,
        TextElement,
    )
    from docling.datamodel.document import ConversionResult, InputDocument
    from docling.models.stages.reading_order.readingorder_model import (
        ReadingOrderModel,
        ReadingOrderOptions,
    )
    from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
    from docling_core.types.doc.document import TableCell
    from docling_core.types.doc.labels import DocItemLabel
    from docling_core.types.doc.page import BoundingRectangle, TextCell

    sizes = sizes or [A4] * len(pages)
    pdf = pdfium.PdfDocument.new()
    for w, h in sizes:
        pdf.new_page(w, h)
    path = tempfile.mktemp(prefix="d8_", suffix=".pdf")
    pdf.save(path)
    conv = ConversionResult(
        input=InputDocument(
            path_or_stream=Path(path),
            format=InputFormat.PDF,
            backend=PyPdfiumDocumentBackend,
        )
    )
    conv.pages = [
        Page(page_no=i + 1, size=Size(width=w, height=h))
        for i, (w, h) in enumerate(sizes)
    ]
    elements: list[Any] = []
    counter = [0]

    def bbox(spec):
        left, t, r, b = spec["bbox"]
        return BoundingBox(l=left, t=t, r=r, b=b, coord_origin=CoordOrigin.TOPLEFT)

    def cluster(spec, label, children=None):
        cid = counter[0]
        counter[0] += 1
        cells = []
        if spec.get("text"):
            cells = [
                TextCell(
                    index=0,
                    text=spec["text"],
                    orig=spec["text"],
                    rect=BoundingRectangle.from_bounding_box(bbox(spec)),
                    from_ocr=True,
                    confidence=1.0,
                )
            ]
        return Cluster(
            id=cid, label=label, bbox=bbox(spec), confidence=0.9, cells=cells,
            children=children or [],
        )  # fmt: skip

    for page_no, page in enumerate(pages, start=1):
        for spec in page:
            label = getattr(DocItemLabel, spec["label"].upper())
            if spec["label"] == "picture":
                kids = [
                    cluster(c, getattr(DocItemLabel, c["label"].upper()))
                    for c in spec.get("children", [])
                ]
                cl = cluster({"bbox": spec["bbox"]}, label, kids)
                elements.append(
                    FigureElement(label=label, id=cl.id, page_no=page_no, text="", cluster=cl)
                )
            elif spec["label"] == "table":
                cl = cluster({"bbox": spec["bbox"]}, label)
                rows = spec["rows"]
                cells = [
                    TableCell(
                        text=val,
                        start_row_offset_idx=r,
                        end_row_offset_idx=r + 1,
                        start_col_offset_idx=c,
                        end_col_offset_idx=c + 1,
                        column_header=(r == 0),
                    )
                    for r, row in enumerate(rows)
                    for c, val in enumerate(row)
                ]
                elements.append(
                    Table(
                        label=label, id=cl.id, page_no=page_no, cluster=cl, otsl_seq=[],
                        num_rows=len(rows), num_cols=len(rows[0]), table_cells=cells,
                    )  # fmt: skip
                )
            else:
                cl = cluster(spec, label)
                elements.append(
                    TextElement(
                        label=label, id=cl.id, page_no=page_no, text=spec["text"], cluster=cl
                    )
                )
    conv.assembled = AssembledUnit(elements=elements, body=elements, headers=[])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        doc = ReadingOrderModel(ReadingOrderOptions())(conv)
    return doc, LN.source_evidence(conv)


def legal(pages, sizes=None):
    doc, evidence = build(pages, sizes)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = LN.normalize_document(doc, evidence=evidence)
    return doc, res, [ln for ln in res.content.split("\n") if ln.strip()]


# --------------------------------------------------------------------------- #
# D8-01: a split-off part is re-inserted by geometry, with the wrong geometry
# --------------------------------------------------------------------------- #

CONT = "của pháp luật hiện hành về bảo vệ thực vật."
PAGE2 = [
    T(CONT, 70, 70, 400, 82),
    T("Điều 6. Hiệu lực thi hành", 70, 88, 300, 100),
    T("Thông tư này có hiệu lực kể từ ngày ký.", 70, 106, 500, 118),
    T("Điều 7. Trách nhiệm thi hành", 70, 400, 320, 412),
]
HEAD = "Tổ chức, cá nhân có trách nhiệm thực hiện theo quy định"
EXPECTED_ORDER = [
    HEAD,
    CONT,
    "Điều 6. Hiệu lực thi hành",
    "Thông tư này có hiệu lực kể từ ngày ký.",
    "Điều 7. Trách nhiệm thi hành",
]


def test_control_same_page_size_keeps_the_reading_order():
    """The case all 92 fixtures cover: both pages 595 x 842."""
    doc, res, lines = legal([[T(HEAD, 70, 760, 525, 790)], PAGE2])
    assert len(doc.texts[0].prov) == 2  # Docling merged the two pages
    assert lines == EXPECTED_ORDER
    assert res.counts.get("upstream_merge_undone") == 1


def test_control_docling_records_the_merged_part_with_the_first_pages_height():
    """Root cause, upstream: ``_merge_elements`` converts the bbox of the part on
    page 2 with the height of PAGE 1 (``page_height`` of the first element)."""
    doc, _ = build([[T(HEAD, 70, 740, 525, 770)], PAGE2], [(595, 820), A4])
    part2 = doc.texts[0].prov[1]
    assert part2.page_no == 2
    top_left = part2.bbox.to_top_left_origin(page_height=842)
    assert round(top_left.t) == 70 + (842 - 820)  # 22 pt lower than it is


# was: xfail(strict) D8-01 - fixed in Phase 12D9 (legal_normalizer: Docling's
# box convention for joined parts, placement by Docling's own reading order)
@pytest.mark.parametrize(
    "first_page, sizes",
    [
        (T(HEAD, 70, 740, 525, 770), [(595, 820), A4]),  # scanner auto-crop, 22 pt
        (T(HEAD, 70, 520, 780, 550), [(842, 595), A4]),  # landscape, then portrait
    ],
)
def test_d8_01_mixed_page_heights_keep_the_reading_order(first_page, sizes):
    _doc, _res, lines = legal([[first_page], PAGE2], sizes)
    assert lines == EXPECTED_ORDER


# was: xfail(strict) D8-01 - fixed in Phase 12D9 (never placed past a text)
def test_d8_01_two_columns_keep_the_reading_order():
    left = T("của pháp luật hiện hành về bảo vệ thực vật và kiểm dịch.", 60, 72, 290, 400)
    right = [
        T("Điều 6. Hiệu lực thi hành", 310, 70, 540, 82),
        T("Thông tư này có hiệu lực kể từ ngày ký.", 310, 100, 540, 112),
    ]
    doc, _res, lines = legal([[T(HEAD, 70, 760, 525, 790)], [left, *right]])
    assert len(doc.texts[0].prov) == 2 and doc.texts[1].text.startswith("Điều 6")
    assert lines == [HEAD, left["text"], right[0]["text"], right[1]["text"]]


# was: test_control_d8_01_today_the_continuation_lands_after_the_next_article
# (Legal 1.3.0 stored the continuation after "Điều 6" for the 820 -> 842 pt scan)
def test_d8_01_the_continuation_goes_back_right_after_its_head():
    """Inverted in Phase 12D9: same scan, the continuation is right after its
    head, nothing lost, one warning that names the split."""
    _doc, res, lines = legal([[T(HEAD, 70, 740, 525, 770)], PAGE2], [(595, 820), A4])
    assert lines.index(CONT) == lines.index(HEAD) + 1
    assert lines.index(CONT) < lines.index("Điều 6. Hiệu lực thi hành")
    assert lines == EXPECTED_ORDER  # nothing lost, order kept
    assert [w["code"] for w in res.warnings] == ["upstream_merge_undone"]


# --------------------------------------------------------------------------- #
# D8-02: a footnote Docling attaches to a table / picture is in no export
# --------------------------------------------------------------------------- #

NOTE = "(1) Theo Thông tư số 15/2024/TT-BNNPTNT ngày 01/02/2024."
TABLE = {
    "label": "table",
    "bbox": [70, 200, 525, 400],
    "rows": [["STT", "Mã số"], ["1", "0001"], ["2", "12.50"]],
}
PICTURE = {"label": "picture", "bbox": [70, 200, 525, 600], "children": []}


def _with_note(floating: dict[str, Any], note_top: float):
    return [
        [
            T("Điều 1. Phạm vi điều chỉnh", 70, 100, 400, 114),
            floating,
            T(NOTE, 70, note_top, 500, note_top + 12, "footnote"),
            T("Điều 2. Đối tượng áp dụng.", 70, 700, 400, 714),
        ]
    ]


@pytest.mark.parametrize("floating, top", [(TABLE, 410), (PICTURE, 610)])
def test_control_docling_attaches_the_note_and_the_standard_export_drops_it(
    floating, top
):
    """Upstream (docling-core 2.96.0 Markdown serializer), same in v1.2.0.
    Phase 12D9 patches the serializer (D8-02); the control runs UPSTREAM."""
    from open_notebook.ocr import docling_patches

    with docling_patches.upstream_text_preservation():
        doc, _ = build(_with_note(floating, top))
        holders = [*doc.tables, *doc.pictures]
        assert [len(h.footnotes) for h in holders] == [1]
        assert any(t.text == NOTE for t in doc.texts)  # the text IS in the document
        assert NOTE not in doc.export_to_markdown()


def test_control_a_footnote_that_is_not_attached_is_kept():
    _doc, _res, lines = legal(
        [[T("Điều 1. Phạm vi", 70, 100, 400, 114), T(NOTE, 70, 780, 500, 792, "footnote")]]
    )
    assert NOTE in lines


# was: xfail(strict) D8-02 - fixed in Phase 12D9 (docling_patches, D8-02 patch)
@pytest.mark.parametrize("floating, top", [(TABLE, 410), (PICTURE, 610)])
def test_d8_02_legal_keeps_a_footnote_attached_to_a_table_or_picture(floating, top):
    _doc, res, lines = legal(_with_note(floating, top))
    assert NOTE in lines or any("footnote" in w["code"] for w in res.warnings)


# --------------------------------------------------------------------------- #
# Verified: no join across pages, nothing lost, tables / markers / pictures
# --------------------------------------------------------------------------- #


def test_verified_docling_merges_into_an_article_heading_and_legal_splits_it():
    """Docling joins "... quy định" (ASCII lowercase) with a next-page TEXT that
    starts with ANY letter - here an article heading; Standard shows one
    paragraph, Legal two, in order, text unchanged."""
    pages = [
        [T("Phạm vi áp dụng theo quy định", 70, 760, 525, 790)],
        [T("Điều 5. Trách nhiệm của tổ chức", 70, 70, 400, 82)],
    ]
    doc, _res, lines = legal(pages)
    assert "quy định Điều 5." in doc.export_to_markdown()
    assert lines == [pages[0][0]["text"], pages[1][0]["text"]]


def test_verified_two_independent_documents_are_not_one_paragraph():
    pages = [
        [T("Nơi nhận: như trên, lưu vt", 70, 760, 300, 790)],
        [
            T("BỘ NÔNG NGHIỆP VÀ PHÁT TRIỂN NÔNG THÔN", 70, 60, 400, 74),
            T("Số: 0001/2024/QĐ-BNN", 70, 90, 300, 104),
        ],
    ]
    _doc, _res, lines = legal(pages)
    assert lines == [e["text"] for page in pages for e in page]


def test_control_residual_a_removed_hyphen_without_evidence_stays_joined():
    """R-D8-A (residual, reported by a warning): Docling dropped the hyphen and
    joined across the page; with no pre-merge element text the two pages stay
    ONE paragraph in Legal mode - 'no cross-page join' holds only with evidence.
    Phase 12D9: Docling no longer removes a hard hyphen (D8-03), so this happens
    only with an UPSTREAM-built document; the control builds one."""
    from open_notebook.ocr import docling_patches

    pages = [
        [T("Cơ quan kiểm dịch thực vật xuyên-", 70, 760, 525, 790)],
        [T("biên giới thực hiện kiểm tra.", 70, 70, 400, 82)],
    ]
    with docling_patches.upstream_text_preservation():
        doc, evidence = build(pages)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        without = LN.normalize_document(doc, evidence=None)
        with_ev = LN.normalize_document(doc, evidence=evidence)
    joined = [ln for ln in without.content.split("\n") if ln.strip()]
    assert joined == ["Cơ quan kiểm dịch thực vật xuyênbiên giới thực hiện kiểm tra."]
    assert [w["code"] for w in without.warnings] == ["upstream_dehyphenation"]
    apart = [ln for ln in with_ev.content.split("\n") if ln.strip()]
    assert apart == [pages[0][0]["text"], pages[1][0]["text"]]  # hyphen restored


def test_verified_table_numbers_markers_and_picture_text_are_kept():
    stamp = {
        "label": "picture",
        "bbox": [400, 600, 500, 660],
        "children": [T("BỘ NÔNG NGHIỆP", 410, 610, 490, 622), T("0001", 410, 630, 450, 642)],
    }
    pages = [
        [
            T("9.", 70, 80, 85, 94),
            T("Số: 0001/2024 ngày 01/02/2024, mức 12.50%/năm, 1.000.000 đồng", 70, 110, 525, 124),
            TABLE,
            stamp,
            T("Hình 1. Con dấu", 400, 665, 500, 677, "caption"),
        ]
    ]
    _doc, res, lines = legal(pages)
    text = "\n".join(lines)
    for token in ("9.", "0001/2024", "01/02/2024", "12.50%/năm", "1.000.000",
                  "BỘ NÔNG NGHIỆP", "Hình 1. Con dấu"):  # fmt: skip
        assert token in text, token
    assert "|     1 |    0001 |" in text and "|     2 |   12.50 |" in text
    assert res.counts.get("image_placeholder_dropped") == 1  # < 4 % of the page


WORDS = ["Điều", "5.", "khoản", "0001", "2024", "12.50", "9.", "theo", "quy", "định",
         "của", "NA", "N/A", "thuế-", "kiểm­", "a)", "đ)", "Số:", "15/2024/TT-BNN",
         "é", "—", "pháp", "luật,", "tổ-", "chức"]  # fmt: skip


def _docling_merge(parts: list[str]) -> tuple[str, list[tuple[int, int]]]:
    """Docling 2.129.0 ``_merge_elements`` arithmetic."""
    text = parts[0]
    spans = [(0, len(text))]
    for p in parts[1:]:
        spans.append((len(text) + 1, len(text) + 1 + len(p)))
        cont = p.lstrip()
        if text.endswith("­") or (text.endswith("-") and cont and cont[0].islower()):
            text = text[:-1] + p
        else:
            text += f" {p}"
    return text, spans


def _tokens(s: str) -> Counter:
    return Counter(s.replace("­", "").replace("-", " ").split())


def test_verified_fuzz_bad_char_spans_never_lose_or_add_text():
    """Missing, overlapping, out-of-range, shifted, negative, swapped spans on
    multi-provenance items: no exception, the words of every item are in the
    Legal content exactly once, the input document is untouched, and a second
    run changes nothing."""
    from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
    from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
    from docling_core.types.doc.labels import DocItemLabel

    rng = random.Random(8)
    modes = ["ok", "ok", "ok", "missing", "overlap", "beyond", "shift", "neg", "swap", "zero"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for _ in range(500):
            n_pages = rng.randint(1, 4)
            doc = DoclingDocument(name="f")
            for p in range(1, n_pages + 1):
                doc.add_page(
                    page_no=p, size=Size(width=595, height=rng.choice([842, 820, 595]))
                )
            expect: Counter = Counter()
            for _k in range(rng.randint(1, 6)):
                nparts = rng.choice([1, 1, 2, 2, 3, 4])
                parts = [
                    " ".join(rng.choice(WORDS) for _w in range(rng.randint(1, 8)))
                    for _p in range(nparts)
                ]
                text, spans = _docling_merge(parts)
                mode = rng.choice(modes) if nparts > 1 else "ok"
                if mode == "overlap":
                    spans = [(0, len(text))] * nparts
                elif mode == "beyond":
                    spans = [(s, e + rng.randint(1, 50)) for s, e in spans]
                elif mode == "shift":
                    spans = [spans[0]] + [
                        (s + rng.choice([-2, -1, 1, 2]), e + rng.choice([-2, -1, 0, 1, 2]))
                        for s, e in spans[1:]
                    ]
                elif mode == "neg":
                    spans = [(0, len(parts[0]))] + [(-5, 3)] * (nparts - 1)
                elif mode == "swap":
                    spans = spans[::-1]
                elif mode in ("zero", "missing"):
                    spans = [(0, 0)] * nparts
                provs = []
                for i, page in enumerate(sorted(rng.randint(1, n_pages) for _p in range(nparts))):
                    top = rng.uniform(40, 500)
                    left = rng.choice([60, 60, 310])
                    box = BoundingBox(
                        l=left, t=top, r=left + 200, b=top + 14, coord_origin=CoordOrigin.TOPLEFT
                    ).to_bottom_left_origin(595)
                    try:
                        provs.append(ProvenanceItem(page_no=page, bbox=box, charspan=spans[i]))
                    except Exception:  # noqa: BLE001 - pydantic refuses the span
                        provs.append(ProvenanceItem(page_no=page, bbox=box, charspan=(0, 0)))
                item = doc.add_text(label=DocItemLabel.TEXT, text=text, orig=text, prov=provs[0])
                for extra in provs[1:]:
                    item.prov.append(extra)
                expect += _tokens(text)
            before = doc.export_to_markdown()
            res = LN.normalize_document(doc)
            assert _tokens(res.content) == expect
            assert doc.export_to_markdown() == before
            assert LN.normalize_document(res.document).content == res.content


def test_verified_a_failing_normalizer_keeps_the_standard_export_and_says_so(
    monkeypatch,
):
    doc, _ = build([[T("Điều 1. Phạm vi", 70, 100, 400, 114)]])

    def boom(*_a, **_kw):
        raise RuntimeError("x")

    monkeypatch.setattr(LN, "normalize_document", boom)
    content, meta = LN.normalize_or_fallback(doc)
    assert content == doc.export_to_markdown()
    assert meta["legal_normalization_status"] == "failed"
    assert meta["legal_normalization_record"]["status"] == "failed"
    # was: == "1.3.0" (Phase 12D9 bumped the normalizer to 1.3.1 for D8-01 / D8-03)
    assert meta["legal_normalization_record"]["version"] == "1.3.1"
