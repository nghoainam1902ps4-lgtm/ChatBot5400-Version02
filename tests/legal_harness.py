"""Phase 12 test harness: synthetic layout -> REAL Docling post-layout pipeline.

Docling's Layout Heron / TableFormer weights come from Hugging Face, which a
sandbox may not reach. Everything Docling does AFTER the layout model is pure
Python, so this harness feeds the elements of a fixture spec
(``tests/fixtures/legal/legal_fixtures.py``) to Docling's own
``ReadingOrderModel`` - reading order, list-marker detection, Docling's
cross-page merge, captions/footnotes, furniture layer - and gets the
``DoclingDocument`` the production pipeline would build from that layout.

What this does NOT cover (and the reports say so): OCR recognition, the layout
model's own decisions, table structure recognition. Those need the real models
(Windows Local guide, docs/ocr/PHASE12E_WINDOWS_LOCAL_TEST_GUIDE.md).

Also here: ``display_lines`` renders Markdown the way a CommonMark renderer
(react-markdown + remark-gfm in the frontend) shows it, including the list
numbers a browser draws, so checks measure what the user actually reads; and
the metrics used by the quality benchmark.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Any

_FIXTURES_PATH = Path(__file__).parent / "fixtures" / "legal" / "legal_fixtures.py"


def load_fixtures() -> Any:
    spec = importlib.util.spec_from_file_location("legal_fixtures", _FIXTURES_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_LABELS = {
    "text": "TEXT",
    "list_item": "LIST_ITEM",
    "section_header": "SECTION_HEADER",
    "title": "TITLE",
    "caption": "CAPTION",
    "footnote": "FOOTNOTE",
    "page_header": "PAGE_HEADER",
    "page_footer": "PAGE_FOOTER",
    "picture": "PICTURE",
    "table": "TABLE",
}

_EMPTY_PDF: dict[int, str] = {}


def _empty_pdf(n_pages: int) -> str:
    """A blank PDF with ``n_pages`` pages (ConversionResult needs an input file)."""
    if n_pages not in _EMPTY_PDF:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument.new()
        for _ in range(max(1, n_pages)):
            pdf.new_page(595, 842)
        path = tempfile.mktemp(prefix="phase12_", suffix=".pdf")
        pdf.save(path)
        _EMPTY_PDF[n_pages] = path
    return _EMPTY_PDF[n_pages]


def build_document(fixture: dict[str, Any]) -> Any:
    """Run Docling's ReadingOrderModel on the fixture's layout elements."""
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

    pages = fixture["pages"]
    path = _empty_pdf(len(pages))
    input_doc = InputDocument(
        path_or_stream=Path(path),
        format=InputFormat.PDF,
        backend=PyPdfiumDocumentBackend,
    )
    conv = ConversionResult(input=input_doc)
    conv.pages = [
        Page(page_no=i + 1, size=Size(width=595, height=842)) for i in range(len(pages))
    ]
    elements: list[Any] = []
    counter = [0]

    def bbox(spec: dict[str, Any]) -> Any:
        left, t, r, b = spec["bbox"]
        return BoundingBox(l=left, t=t, r=r, b=b, coord_origin=CoordOrigin.TOPLEFT)

    def cluster(
        spec: dict[str, Any], label: Any, children: list[Any] | None = None
    ) -> Any:
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
            id=cid,
            label=label,
            bbox=bbox(spec),
            confidence=0.9,
            cells=cells,
            children=children or [],
        )

    for page_no, page in enumerate(pages, start=1):
        for spec in page:
            label = getattr(DocItemLabel, _LABELS[spec["label"]])
            if spec["label"] == "picture":
                kids = [
                    cluster(c, getattr(DocItemLabel, _LABELS[c["label"]]))
                    for c in spec.get("children", [])
                ]
                cl = cluster({"bbox": spec["bbox"]}, label, kids)
                elements.append(
                    FigureElement(
                        label=label, id=cl.id, page_no=page_no, text="", cluster=cl
                    )
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
                        column_header=(
                            r == 0 and spec.get("header", not rows[0][0].isdigit())
                        ),
                    )
                    for r, row in enumerate(rows)
                    for c, val in enumerate(row)
                ]
                elements.append(
                    Table(
                        label=label,
                        id=cl.id,
                        page_no=page_no,
                        cluster=cl,
                        otsl_seq=[],
                        num_rows=len(rows),
                        num_cols=len(rows[0]),
                        table_cells=cells,
                    )
                )
            else:
                cl = cluster(spec, label)
                elements.append(
                    TextElement(
                        label=label,
                        id=cl.id,
                        page_no=page_no,
                        text=spec["text"],
                        cluster=cl,
                    )
                )
    conv.assembled = AssembledUnit(elements=elements, body=elements, headers=[])
    return ReadingOrderModel(ReadingOrderOptions())(conv)


# Display rendering and metrics live with the diagnostic scripts so that the
# tests, the benchmark and the local reports measure the same way.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "ocr"))

from phase12_metrics import (  # noqa: E402,F401
    cer,
    display_lines,
    display_text,
    expected_units,
    legal_display_markdown,
    levenshtein,
    lost_words,
    markers_displayed,
    order_accuracy,
    preservation,
    wer,
    word_recall,
)


def legal_lines(markdown: str) -> list[str]:
    """Lines the reader sees for a Legal-normalized Source (frontend escape + CommonMark)."""
    return display_lines(legal_display_markdown(markdown))
