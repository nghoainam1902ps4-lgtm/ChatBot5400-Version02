"""Legal Document normalization of a Docling result (Phase 12, decision D-34).

Works on a COPY of the ``DoclingDocument`` Docling produced, using the structure
Docling already computed (labels, content layers, list markers, provenance
pages and bounding boxes, reading order) - never the flattened Markdown string.

RULE ZERO (Phase 12D3, tightened in Phase 12D5 after the re-review): legal
content is kept unless the evidence that something is a page artifact is
strong. Leaving a page number in the text, or a paragraph cut by a page break,
is a blemish; deleting a year, a clause or voucher number, or creating a
sentence the document does not contain, is a defect. Whenever the evidence is
missing the item stays as it is and a warning says so.

What it does (version 1.2.0, Phase 12D5):

1. PAGE NUMBERS labelled TEXT by the layout model go to the furniture layer
   (where Docling itself puts PAGE_HEADER / PAGE_FOOTER) only when ALL hold:
   a strict page-number shape (no leading zero; "n/m" and "trang n/m" only when
   m is the page count); top / bottom band and outermost on its page; ALONE on
   its line (no other item at that height - "Số:" + "0001" is a field, not a
   page number) and not under a label ending with ":"; centred, or at the
   outer (right) edge, or mirrored on odd / even pages - never on the left
   side only, where detached clause numbers sit; the same vertical place; the
   same "printed number - PDF page" offset on at least 3 pages AND at least
   60 % of the pages; a value that fits the document. One- and two-page
   documents never qualify. Anything else is kept (``page_number_kept``).
2. REPEATED LINES labelled TEXT are never removed (``repeated_line_kept``).
   Items the layout model labelled PAGE_HEADER / PAGE_FOOTER are artifacts only
   when they repeat on several pages or are page numbers that fit the page
   index; a header / footer text that appears ONCE (document number, issuer on
   page 1, a footnote labelled footer) is business content: it is kept in the
   text (``furniture_text_kept``) - the standard export drops it (R2-11).
3. PICTURES: the ``<!-- image -->`` placeholder is dropped only for a picture
   under 4 % of the page (signature, stamp, logo). Every other picture keeps it,
   whatever text was found inside (a caption or a stray word is no evidence the
   picture was read), with a located warning (``picture_without_text`` /
   ``picture_text_unverified``). OCR text Docling placed INSIDE a picture is kept
   (``traverse_pictures``); the standard export drops it.
4. A PARAGRAPH CUT BY A PAGE BREAK is joined to its continuation only when
   every rule of ``_pair_refusal`` passes - among them: the next page has ONE
   candidate first line, the page before ONE unfinished paragraph (a footnote
   under the cut paragraph is never the left part), and the first line does not
   open a new unit (clause, point - also as OCR damages it: "c )", "a,", "a-",
   "o " -, a date line, a unit line, "trong đó:", a web address, "trang n/m").
   The refusal reason of a near miss is reported (``join_not_made``). One space
   is the only character ever added.
5. DOCLING'S OWN MERGE (R2-01): Docling joins a TEXT ending in [a-z,-] with the
   next TEXT starting with a letter - across pages, across columns, over tables,
   pictures and footers - and drops the hyphen before a lowercase continuation.
   The provenance char spans show exactly where the parts were joined. A join
   the rules of point 4 would refuse is UNDONE: the item is split back into its
   parts, from their recorded spans, at their own reading position
   (``upstream_merge_undone``). A removed hyphen cannot be restored from the
   document (it was "-" or a soft hyphen): the text is kept and
   ``upstream_dehyphenation`` names the pages. Spans that do not add up are
   left alone and reported (``upstream_merge_kept``).
6. LIST ITEMS are written with their ORIGINAL marker ("9.", "a)", "đ)", "1.1",
   "-") as plain text, one paragraph each; an item without a recognised marker
   is never given a synthesised number.
7. THE STORED TEXT IS THE PRINTED TEXT (F-17): no Markdown escape of markers,
   underscores, "&" or "<" is stored - chunks, embeddings, copy and display see
   the same characters. Only two literal forms stay neutralised in storage: a
   line starting with "#" / ">" (``\\#`` / ``\\>``) and a "<" that would open an
   HTML tag or comment (``&lt;``), so that no consumer ever receives active
   markup. The Source page escapes every Markdown-significant character of a
   Legal source at render time (``frontend/src/lib/utils/legal-display.ts``).

What it never does: call an LLM or the network, touch the database or a file,
change a character of recognised text (spelling, digits, 0/O, 1/l, units), add
a word, renumber anything, reorder anything, flatten or merge tables.

Pure and deterministic; running it on its own output document changes nothing
(idempotent); the input document is never modified. Linear in the number of
items, with resource and time limits. Callers keep the standard export as the
fallback (``normalize_or_fallback``).
"""

from __future__ import annotations

import hashlib
import os
import re
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

NORMALIZER_VERSION = "1.2.0"

MODE_STANDARD = "standard"
MODE_LEGAL = "legal"
MODES = (MODE_STANDARD, MODE_LEGAL)

# Deployment gate (default OFF): without it the "legal" setting is ignored.
ENV_FLAG = "OCR_LEGAL_NORMALIZATION_ENABLED"

# Only these inputs were designed and tested (Phase 12D). Images, Office, HTML,
# Markdown, audio, web pages keep the standard behaviour.
SUPPORTED_MIME_TYPES = frozenset({"application/pdf"})

# Resource limits: beyond them the document is returned unnormalized (fallback).
MAX_ITEMS = 200_000
MAX_PAGES = 10_000
MAX_TEXT_CHARS = 50_000_000
TIME_BUDGET_SECONDS = 30.0

# Geometry (fractions of the page, top-left origin).
BAND_TOP = 0.10  # an item entirely above this line is in the top band
BAND_BOTTOM = 0.90  # an item entirely below this line is in the bottom band
JOIN_LOWER_HALF = 0.50  # first part of a join ends in the lower half of its page
JOIN_UPPER_HALF = 0.50  # second part starts in the upper half of the next page
JOIN_MIN_COLUMN_SHARE = 0.85  # first part spans the body column (a cut line does)
JOIN_MIN_COLUMN_OVERLAP = 0.50  # both parts lie in the same column
JOIN_MAX_INDENT = 0.02  # second part starts at the column edge (no first-line indent)
SILENT_PICTURE_RATIO = 0.04  # only pictures smaller than this are dropped silently

# Page numbers (finding F-02).
PAGE_NUMBER_MAX_CHARS = 20
PAGE_NUMBER_MIN_PAGES = 3
PAGE_NUMBER_MIN_SHARE = 0.60
PAGE_NUMBER_MAX_OFFSET = 50  # a file that starts at page 51 of a longer document
PAGE_NUMBER_MIN_OFFSET = -10
PAGE_NUMBER_X_TOLERANCE = 0.05  # spread of the horizontal centres (page widths)
BODY_MARGIN_TOLERANCE = 0.01  # "starts where the paragraphs start" (page widths)
PAGE_NUMBER_CENTRE = 0.08  # centred: centre within 8 % of the page width of the middle
PAGE_NUMBER_OUTER_EDGE = (
    0.70  # right side: the number starts right of 70 % of the width
)
PAGE_NUMBER_Y_TOLERANCE = 0.02  # spread of the vertical places (page heights)
LABEL_GAP_LINES = 1.5  # a label line ("Số:") this close above makes it a field

# Repeated lines (finding F-01): reported, never removed.
REPEATED_MAX_CHARS = 150
REPEATED_MIN_PAGES = 3

# What is stored for the Source (finding F-07): bounded, no text.
PERSIST_MAX_OPERATIONS = 200
PERSIST_MAX_WARNINGS = 50

# Strict page-number shapes (Phase 12D5, F-02). A leading zero is a document /
# voucher number; "n/m" and "trang n/m" count only when m is the page count
# (checked by the caller: _SLASH_TOTAL), so "3/2024" (a reporting period) never is.
_PAGE_NUMBER_RES = [
    re.compile(p)
    for p in (
        r"[1-9]\d{0,3}",
        r"[-–—]\s*[1-9]\d{0,3}\s*[-–—]",
        r"(?i:trang|page)\s+[1-9]\d{0,3}",
        r"(?i:trang)\s+[1-9]\d{0,3}\s*(?:/|(?i:trên))\s*[1-9]\d{0,3}",
        r"(?i:page)\s+[1-9]\d{0,3}\s*(?:/|(?i:of))\s*[1-9]\d{0,3}",
        r"[1-9]\d{0,3}\s*/\s*[1-9]\d{0,3}",
    )
]
_SLASH_TOTAL = re.compile(r"(?:/|(?i:trên)|(?i:of))\s*(\d{1,4})\s*$")
_FIRST_INT = re.compile(r"\d{1,4}")

# A line that opens a new legal unit: never the continuation of a paragraph.
_STRUCTURE_START = re.compile(
    r"^(?:"
    r"(?:phần|chương|mục|điều|khoản|điểm|tiểu mục|phụ lục)\s+[\divxlcdm]+"  # Điều 5
    r"|[a-zđ](?:\.\d+)*[.)/](?:\s|$)"  # a.  a)  a/  đ.  đ)  a.1)  a.1.
    r"|\([a-zđ0-9]{1,3}\)(?:\s|$)"  # (a)  (đ)  (1)
    r"|[ivxlcdm]+[.)](?:\s|$)"  # i.  ii)
    r"|\d+(?:\.\d+)*[.)]?(?:\s|$)"  # 1.  1.1  2)  1.2.3
    r"|[-+*•●○▪–](?:\s|$)"  # bullets
    # Phase 12D5 (F-03): markers as OCR damages them, and lines that are a unit
    # of their own although they start in lowercase
    r"|[a-zđ]\s+[.)\]](?:\s|$)"  # c )  c .
    r"|[a-zđ][,\-–:](?:\s|$)"  # a,  a-  a:
    r"|[oO0°]\s+\S"  # a hollow bullet read as the letter o / zero / degree
    r"|ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4}"  # date line
    r"|(?:đvt|đơn vị tính|đơn vị)\s*:"  # unit line
    r"|trong đó\s*:"
    r"|(?:www\.|https?://)"  # a web address
    r"|(?:trang|page)\s+\d{1,4}\s*(?:/|trên|of)\s*\d{1,4}"  # "trang 2/3"
    r")",
    re.IGNORECASE,
)

# A footnote the layout model labelled TEXT: "1 Thông tư…", "(1) …", "* …",
# "(*) …", "¹ …".
_FOOTNOTE_START = re.compile(
    r"^(?:\d{1,2}\s+\S|\(\d{1,2}\)\s|\[\d{1,2}\]\s|\(\*+\)|[*†‡]|[¹²³⁴⁵⁶⁷⁸⁹⁰]+)"
)

# Markdown block syntax a literal text line must not trigger. List markers are
# NOT escaped in the stored text (see the module docstring, point 7).
_MD_HEADING = re.compile(r"^(\s{0,3})(#{1,6})(?=\s|$)")
_MD_QUOTE = re.compile(r"^(\s{0,3})(>)")
# A "<" that opens raw HTML in CommonMark (tag, closing tag, comment,
# processing instruction, declaration, CDATA): neutralised in storage.
_HTML_OPEN = re.compile(r"<(?=[A-Za-z][A-Za-z0-9-]*(?:[\s/>]|$)|/[A-Za-z]|!|\?)")


class NormalizationLimitError(ValueError):
    """The document exceeds a resource limit; the caller keeps the standard export."""


def legal_normalization_available() -> bool:
    """Deployment gate: ``OCR_LEGAL_NORMALIZATION_ENABLED=true`` (default off)."""
    return os.environ.get(ENV_FLAG, "").strip().lower() in ("1", "true", "yes", "on")


def effective_mode(setting: str | None) -> str:
    """The mode a job really uses: "legal" only when chosen AND enabled."""
    if setting == MODE_LEGAL and legal_normalization_available():
        return MODE_LEGAL
    return MODE_STANDARD


def applies_to(mime: str | None) -> bool:
    return (mime or "") in SUPPORTED_MIME_TYPES


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


@dataclass
class Operation:
    """One change, with the evidence needed to verify it against the source."""

    op: str
    reason: str
    pages: list[int] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)
    bboxes: list[list[float]] = field(default_factory=list)
    chars_before: int = 0
    chars_after: int = 0
    sha256: str = ""  # of the text before the change (never the text itself)
    # Only with include_text=True (local diagnostics): never logged or stored.
    text_before: str | None = None
    text_after: str | None = None


@dataclass
class NormalizationResult:
    content: str
    operations: list[Operation]
    warnings: list[dict[str, Any]]
    counts: dict[str, int]
    elapsed_ms: float
    version: str = NORMALIZER_VERSION
    document: Any = None  # the normalized copy (diagnostics / idempotency)

    def summary(self) -> dict[str, Any]:
        """Counts only - safe to log and to keep in extraction metadata."""
        return {
            "legal_normalizer_version": self.version,
            "legal_normalization_ms": round(self.elapsed_ms, 2),
            "legal_normalization_counts": dict(sorted(self.counts.items())),
            "legal_normalization_warnings": len(self.warnings),
        }

    def report(self) -> dict[str, Any]:
        """Full provenance report (texts included only if requested)."""
        return {
            **self.summary(),
            "operations": [
                {k: v for k, v in asdict(o).items() if v is not None}
                for o in self.operations
            ],
            "warnings": self.warnings,
        }

    def persistable(self) -> dict[str, Any]:
        """What is stored with the Source (finding F-07): small, bounded, no text.

        Removed lines are identified by page and SHA-256 so that a later check
        against the original can prove what was removed without storing it twice.
        """
        ops = [
            {"op": o.op, "pages": o.pages, "sha256": o.sha256}
            for o in self.operations
            if o.op != "image_placeholder_dropped"
        ]
        return {
            "mode": MODE_LEGAL,
            "status": "applied",
            "version": self.version,
            "counts": dict(sorted(self.counts.items())),
            "warnings": self.warnings[:PERSIST_MAX_WARNINGS],
            "operations": ops[:PERSIST_MAX_OPERATIONS],
            "truncated": len(ops) > PERSIST_MAX_OPERATIONS
            or len(self.warnings) > PERSIST_MAX_WARNINGS,
        }


def skipped_record(reason: str) -> dict[str, Any]:
    """Stored when Legal was requested but this input is outside its scope."""
    return {
        "mode": MODE_LEGAL,
        "status": "skipped",
        "version": NORMALIZER_VERSION,
        "reason": reason,
    }


def failed_record(error: str) -> dict[str, Any]:
    """Stored when Legal was requested but the standard export was kept."""
    return {
        "mode": MODE_LEGAL,
        "status": "failed",
        "version": NORMALIZER_VERSION,
        "error": error,
    }


# --------------------------------------------------------------------------- #
# Geometry
# --------------------------------------------------------------------------- #

Box = tuple[float, float, float, float]  # left, top, right, bottom (top-left origin)


def _provs(item: Any) -> list[Any]:
    return list(getattr(item, "prov", None) or [])


class _Geometry:
    """Boxes of the body items, converted once; per-page extremes for O(1) checks."""

    def __init__(self, doc: Any, items: list[Any]) -> None:
        self.sizes: dict[int, tuple[float, float]] = {}
        for page_no, page in (getattr(doc, "pages", None) or {}).items():
            size = getattr(page, "size", None)
            width, height = getattr(size, "width", None), getattr(size, "height", None)
            if width and height:
                self.sizes[int(page_no)] = (float(width), float(height))
        self.n_pages = len(getattr(doc, "pages", None) or {})
        self._boxes: dict[int, Box | None] = {}  # id(prov) -> box
        # page -> the two lowest bottoms / highest tops, owned by two different items
        self._min_bottom: dict[int, list[tuple[float, int]]] = defaultdict(list)
        self._max_top: dict[int, list[tuple[float, int]]] = defaultdict(list)
        for item in items:
            for prov in _provs(item):
                box = self.box(prov)
                if box is None:
                    continue
                page = int(prov.page_no)
                self._keep(self._min_bottom[page], (box[3], id(item)), smallest=True)
                self._keep(self._max_top[page], (box[1], id(item)), smallest=False)

    @staticmethod
    def _keep(
        store: list[tuple[float, int]], entry: tuple[float, int], smallest: bool
    ) -> None:
        """Keep the two extreme values that belong to two different items."""
        store.append(entry)
        store.sort(reverse=not smallest)
        seen: set[int] = set()
        kept = []
        for value, owner in store:
            if owner in seen:
                continue
            seen.add(owner)
            kept.append((value, owner))
            if len(kept) == 2:
                break
        store[:] = kept

    def box(self, prov: Any) -> Box | None:
        key = id(prov)
        if key not in self._boxes:
            self._boxes[key] = self._convert(prov)
        return self._boxes[key]

    def _convert(self, prov: Any) -> Box | None:
        bbox = getattr(prov, "bbox", None)
        size = self.sizes.get(int(getattr(prov, "page_no", -1)))
        if bbox is None or size is None:
            return None
        try:
            tl = bbox.to_top_left_origin(page_height=size[1])
        except Exception:
            return None
        t, b = min(tl.t, tl.b), max(tl.t, tl.b)
        left, r = min(tl.l, tl.r), max(tl.l, tl.r)
        return float(left), float(t), float(r), float(b)

    def band(self, prov: Any) -> str | None:
        box = self.box(prov)
        size = self.sizes.get(int(getattr(prov, "page_no", -1)))
        if box is None or size is None:
            return None
        if box[3] <= BAND_TOP * size[1]:
            return "top"
        if box[1] >= BAND_BOTTOM * size[1]:
            return "bottom"
        return None

    def outermost(self, item: Any, band: str) -> bool:
        """Nothing else on the page lies entirely above (top) / below (bottom) it."""
        prov = _provs(item)[0]
        box = self.box(prov)
        if box is None:
            return False
        page = int(prov.page_no)
        if band == "top":
            for bottom, owner in self._min_bottom.get(page, []):
                if owner != id(item):
                    return bottom > box[1]
        else:
            for top, owner in self._max_top.get(page, []):
                if owner != id(item):
                    return top < box[3]
        return True

    def bbox_list(self, prov: Any) -> list[float]:
        box = self.box(prov)
        return [round(v, 1) for v in box] if box else []

    def area_ratio(self, item: Any) -> float | None:
        provs = _provs(item)
        if not provs:
            return None
        box = self.box(provs[0])
        size = self.sizes.get(int(getattr(provs[0], "page_no", -1)))
        if box is None or size is None:
            return None
        return (
            max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1]) / (size[0] * size[1])
        )


# --------------------------------------------------------------------------- #
# Item classification
# --------------------------------------------------------------------------- #


def _types() -> dict[str, Any]:
    from docling_core.types.doc.document import (
        ListItem,
        PictureItem,
        SectionHeaderItem,
        TableItem,
        TextItem,
        TitleItem,
    )
    from docling_core.types.doc.labels import DocItemLabel

    return {
        "ListItem": ListItem,
        "PictureItem": PictureItem,
        "SectionHeaderItem": SectionHeaderItem,
        "TableItem": TableItem,
        "TextItem": TextItem,
        "TitleItem": TitleItem,
        "DocItemLabel": DocItemLabel,
    }


def _parent(item: Any, doc: Any) -> Any:
    ref = getattr(item, "parent", None)
    if ref is None:
        return None
    try:
        return ref.resolve(doc)
    except Exception:
        return None


def _inside(item: Any, doc: Any, kinds: tuple[type, ...]) -> bool:
    """Whether an ancestor of ``item`` is one of ``kinds`` (picture / table)."""
    node = _parent(item, doc)
    seen = 0
    while node is not None and seen < 64:
        if isinstance(node, kinds):
            return True
        node = _parent(node, doc)
        seen += 1
    return False


def _is_plain_text(item: Any, T: dict[str, Any]) -> bool:
    """A body paragraph: TextItem labelled TEXT (not a list item / heading / caption)."""
    return (
        type(item) is T["TextItem"]
        and getattr(item, "label", None) == T["DocItemLabel"].TEXT
    )


def _is_paragraph(item: Any, T: dict[str, Any]) -> bool:
    return _is_plain_text(item, T) or isinstance(item, T["ListItem"])


def _edge_candidate(item: Any, doc: Any, T: dict[str, Any]) -> bool:
    """A lone text item that could be a page artifact (never inside a picture / table)."""
    label = getattr(item, "label", None)
    L = T["DocItemLabel"]
    return (
        type(item) is T["TextItem"]
        and label in (L.TEXT, L.PAGE_HEADER, L.PAGE_FOOTER)
        and len(_provs(item)) == 1
        and not _inside(item, doc, (T["PictureItem"], T["TableItem"]))
    )


def _layout_says_furniture(item: Any, T: dict[str, Any]) -> bool:
    L = T["DocItemLabel"]
    return getattr(item, "label", None) in (L.PAGE_HEADER, L.PAGE_FOOTER)


# --------------------------------------------------------------------------- #
# Markdown serialization with original markers
# --------------------------------------------------------------------------- #


def escape_literal_block_syntax(text: str) -> str:
    """Escape a leading ``#`` / ``>`` of literal text so it is not a heading / quote.

    Clause markers ("9.", "10)", "-") are deliberately NOT escaped here: the
    stored text keeps them as printed (finding F-17) and the Source page
    escapes them when rendering.
    """
    out = []
    for line in text.split("\n"):
        for rx in (_MD_HEADING, _MD_QUOTE):
            m = rx.match(line)
            if m:
                line = f"{m.group(1)}\\{line[len(m.group(1)) :]}"
                break
        out.append(line)
    return "\n".join(out)


def neutralize_html(text: str) -> str:
    """Make a "<" that would OPEN raw HTML inert ("&lt;"); nothing else changes.

    Phase 12D5 (F-17): the stored Legal text is the printed text - "<Tên khách
    hàng>", "a < b", "A&B", "TK_VND_01" are stored as printed. Only a "<"
    starting a CommonMark HTML tag, closing tag, comment, declaration or
    processing instruction ("<script>", "</b>", "<!--", "<?") is written as
    "&lt;", so that no consumer of the text ever receives active markup.
    """
    return _HTML_OPEN.sub("&lt;", text)


def _build_serializer(doc: Any, drop_picture_refs: set[str]) -> Any:
    from docling_core.transforms.serializer.base import SerializationResult
    from docling_core.transforms.serializer.common import create_ser_result
    from docling_core.transforms.serializer.markdown import (
        MarkdownDocSerializer,
        MarkdownListSerializer,
        MarkdownParams,
        MarkdownPictureSerializer,
        MarkdownTextSerializer,
        OrigListItemMarkerMode,
    )
    from docling_core.types.doc.document import (
        DEFAULT_CONTENT_LAYERS,
        DOCUMENT_TOKENS_EXPORT_LABELS,
        CodeItem,
        FormulaItem,
        ListItem,
        SectionHeaderItem,
        TitleItem,
    )
    from docling_core.types.doc.labels import DocItemLabel

    class LegalTextSerializer(MarkdownTextSerializer):
        def serialize(self, *, item: Any, **kwargs: Any) -> SerializationResult:  # type: ignore[override]
            if isinstance(item, ListItem):
                kwargs = {
                    **kwargs,
                    "orig_list_item_marker_mode": OrigListItemMarkerMode.NEVER,
                    "ensure_valid_list_item_marker": False,
                }
                res = super().serialize(item=item, **kwargs)
                marker = (item.marker or "").strip()
                body = res.text
                text = f"{marker} {body}" if marker and body else (marker or body)
                return create_ser_result(
                    text=escape_literal_block_syntax(text), span_source=item
                )
            res = super().serialize(item=item, **kwargs)
            if (
                isinstance(item, (TitleItem, SectionHeaderItem, CodeItem, FormulaItem))
                or item.label
                in (DocItemLabel.CHECKBOX_SELECTED, DocItemLabel.CHECKBOX_UNSELECTED)
                or not res.text
            ):
                return res
            return create_ser_result(
                text=escape_literal_block_syntax(res.text), span_source=item
            )

    class LegalListSerializer(MarkdownListSerializer):
        """Every item is its own paragraph: the marker is text, not list syntax."""

        def serialize(  # type: ignore[override]
            self,
            *,
            item: Any,
            doc_serializer: Any,
            doc: Any,
            list_level: int = 0,
            is_inline_scope: bool = False,
            visited: set[str] | None = None,
            **kwargs: Any,
        ) -> SerializationResult:
            parts = doc_serializer.get_parts(
                item=item,
                list_level=list_level + 1,
                is_inline_scope=is_inline_scope,
                visited=visited if visited is not None else set(),
                **kwargs,
            )
            parts = [p for p in parts if p.text]
            return create_ser_result(
                text="\n\n".join(p.text.strip(" ") for p in parts), span_source=parts
            )

    class LegalPictureSerializer(MarkdownPictureSerializer):
        def __init__(self, drop: set[str]) -> None:
            self._drop = drop

        def _serialize_image_part(  # type: ignore[override]
            self,
            item: Any,
            doc: Any,
            image_mode: Any,
            image_placeholder: str,
            **kwargs: Any,
        ) -> SerializationResult:
            if item.self_ref in self._drop:
                return create_ser_result(text="", span_source=item)
            return super()._serialize_image_part(
                item=item,
                doc=doc,
                image_mode=image_mode,
                image_placeholder=image_placeholder,
                **kwargs,
            )

    class LegalDocSerializer(MarkdownDocSerializer):
        """The stored text is the printed text (Phase 12D5, F-17 / R2-02): no
        "\\_" for underscores, no HTML entities for "&" / "<" / ">", no bold /
        italic / link markup a native PDF may carry - only a "<" that would open
        raw HTML is neutralised (``neutralize_html``)."""

        def post_process(  # type: ignore[override]
            self,
            text: str,
            *,
            escape_html: bool = True,
            escape_underscores: bool = True,
            formatting: Any = None,
            hyperlink: Any = None,
            **kwargs: Any,
        ) -> str:
            res = neutralize_html(text) if escape_html else text
            return super().post_process(
                text=res,
                escape_html=False,
                escape_underscores=False,
                formatting=None,
                hyperlink=None,
                **kwargs,
            )

    return LegalDocSerializer(
        doc=doc,
        text_serializer=LegalTextSerializer(),
        list_serializer=LegalListSerializer(),
        picture_serializer=LegalPictureSerializer(drop_picture_refs),
        params=MarkdownParams(
            labels=DOCUMENT_TOKENS_EXPORT_LABELS,
            layers=DEFAULT_CONTENT_LAYERS,
            traverse_pictures=True,
        ),
    )


# --------------------------------------------------------------------------- #
# Limits
# --------------------------------------------------------------------------- #


def _check_limits(doc: Any) -> None:
    n_items = sum(
        len(getattr(doc, name, None) or [])
        for name in (
            "texts",
            "tables",
            "pictures",
            "groups",
            "key_value_items",
            "form_items",
        )
    )
    if n_items > MAX_ITEMS:
        raise NormalizationLimitError(f"{n_items} items > {MAX_ITEMS}")
    n_pages = len(getattr(doc, "pages", None) or {})
    if n_pages > MAX_PAGES:
        raise NormalizationLimitError(f"{n_pages} pages > {MAX_PAGES}")
    chars = sum(
        len(getattr(t, "text", "") or "") for t in getattr(doc, "texts", None) or []
    )
    if chars > MAX_TEXT_CHARS:
        raise NormalizationLimitError(f"{chars} characters > {MAX_TEXT_CHARS}")


class _Budget:
    """Wall-clock limit of one normalization (finding F-10)."""

    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.limit = float(TIME_BUDGET_SECONDS)

    def check(self, stage: str) -> None:
        if time.perf_counter() - self.started > self.limit:
            raise NormalizationLimitError(
                f"time budget of {self.limit:g} s exceeded ({stage})"
            )


def _body_items(doc: Any) -> list[Any]:
    from docling_core.types.doc.document import ContentLayer

    return [
        item
        for item, _ in doc.iterate_items(
            with_groups=False,
            traverse_pictures=True,
            included_content_layers={ContentLayer.BODY},
        )
    ]


# --------------------------------------------------------------------------- #
# 1. Page numbers (findings F-02, Phase 12D5)
# --------------------------------------------------------------------------- #


def _body_left_edges(
    items: list[Any], geo: _Geometry, T: dict[str, Any]
) -> dict[int, float]:
    """page -> left edge of its paragraphs (median), from items outside the bands."""
    per_page: dict[int, list[float]] = defaultdict(list)
    for item in items:
        if not _is_paragraph(item, T):
            continue
        for prov in _provs(item):
            box = geo.box(prov)
            if box is not None and geo.band(prov) is None:
                per_page[int(prov.page_no)].append(box[0])
    return {page: statistics.median(values) for page, values in per_page.items()}


class _Lines:
    """Every located item of every page (body AND furniture), for "same line" tests."""

    def __init__(self, doc: Any, geo: _Geometry) -> None:
        from docling_core.types.doc.document import ContentLayer

        self.by_page: dict[int, list[tuple[Box, int, str]]] = defaultdict(list)
        for item, _ in doc.iterate_items(
            with_groups=False,
            traverse_pictures=True,
            included_content_layers={ContentLayer.BODY, ContentLayer.FURNITURE},
        ):
            for prov in _provs(item):
                box = geo.box(prov)
                if box is not None:
                    self.by_page[int(prov.page_no)].append(
                        (box, id(item), str(getattr(item, "text", "") or ""))
                    )

    def alone(self, item: Any, page: int, box: Box) -> bool:
        """No other item shares the vertical extent of ``box`` on its page."""
        height = max(1e-6, box[3] - box[1])
        for other, owner, _ in self.by_page.get(page, []):
            if owner == id(item):
                continue
            overlap = min(other[3], box[3]) - max(other[1], box[1])
            if overlap > 0.3 * height:
                return False
        return True

    def label_above(self, item: Any, page: int, box: Box, width: float) -> bool:
        """A label ending with ':' right above (or to the left of) ``box``."""
        height = max(1e-6, box[3] - box[1])
        for other, owner, text in self.by_page.get(page, []):
            if owner == id(item) or not text.rstrip().endswith(":"):
                continue
            gap = box[1] - other[3]
            horizontal = min(other[2], box[2]) - max(other[0], box[0])
            if 0 <= gap <= LABEL_GAP_LINES * height and horizontal > -0.05 * width:
                return True
        return False


def _page_number_value(text: str, n_pages: int) -> int | None:
    """The printed number of a STRICT page-number shape, or None."""
    t = text.strip()
    if not t or len(t) > PAGE_NUMBER_MAX_CHARS:
        return None
    if not any(rx.fullmatch(t) for rx in _PAGE_NUMBER_RES):
        return None
    total = _SLASH_TOTAL.search(t)
    if total is not None and int(total.group(1)) != n_pages:
        return None  # "3/2024" is a period; "n/m" only when m is the page count
    found = _FIRST_INT.search(t)
    return int(found.group(0)) if found else None


def _place(box: Box, width: float) -> str | None:
    centre = (box[0] + box[2]) / 2
    if abs(centre - width / 2) <= PAGE_NUMBER_CENTRE * width:
        return "centre"
    if box[0] >= PAGE_NUMBER_OUTER_EDGE * width:
        return "right"
    if box[2] <= (1 - PAGE_NUMBER_OUTER_EDGE) * width:
        return "left"
    return None


def _places_consistent(members: list[tuple[int, str]]) -> bool:
    """All centred, all at the right edge, or mirrored on odd / even pages.
    A number on the LEFT side only is where a detached clause number sits."""
    places = {place for _, place in members}
    if places in ({"centre"}, {"right"}):
        return True
    odd = {place for page, place in members if page % 2}
    even = {place for page, place in members if not page % 2}
    return len(odd) == 1 and len(even) == 1 and odd | even == {"left", "right"}


def _find_page_numbers(
    items: list[Any],
    doc: Any,
    geo: _Geometry,
    T: dict[str, Any],
    budget: _Budget,
    lines: _Lines,
) -> tuple[list[Any], list[dict[str, Any]]]:
    body_left = _body_left_edges(items, geo, T)
    doc_left = statistics.median(body_left.values()) if body_left else None
    # (offset, band) -> [(item, page, place, top as a page-height fraction)]
    groups: dict[tuple[int, str], list[tuple[Any, int, str, float]]] = defaultdict(list)
    kept: list[tuple[Any, str]] = []
    for n, item in enumerate(items):
        if n % 5000 == 0:
            budget.check("page numbers")
        if not _edge_candidate(item, doc, T) or _layout_says_furniture(item, T):
            continue
        value = _page_number_value(item.text or "", geo.n_pages)
        if value is None:
            continue  # not a strict page-number shape: never a candidate
        prov = _provs(item)[0]
        band = geo.band(prov)
        if band is None or not geo.outermost(item, band):
            continue  # inside the body: never a candidate, not even a suspect
        page = int(prov.page_no)
        box = geo.box(prov)
        assert box is not None  # band() returned a value
        width, height = geo.sizes[page]
        offset = value - page
        left_edge = body_left.get(page, doc_left)
        place = _place(box, width)
        why = None
        if not PAGE_NUMBER_MIN_OFFSET <= offset <= PAGE_NUMBER_MAX_OFFSET:
            why = "the value does not follow the page index"
        elif left_edge is not None and abs(box[0] - left_edge) <= (
            BODY_MARGIN_TOLERANCE * width
        ):
            why = "it starts at the paragraph margin (a detached clause number?)"
        elif not lines.alone(item, page, box):
            why = "it shares its line with another item (a field such as 'Số: 0001'?)"
        elif lines.label_above(item, page, box, width):
            why = "it stands under a label ending with ':'"
        elif place is None or place == "left" and page % 2:
            why = "it is neither centred nor at the outer edge of the page"
        if why is not None or place is None:
            kept.append((item, why or "no position"))
            continue
        groups[(offset, band)].append((item, page, place, box[1] / height))
    found: list[Any] = []
    for key in sorted(groups):
        members = groups[key]
        pages = Counter(page for _, page, _, _ in members)
        single = [m for m in members if pages[m[1]] == 1]  # two on one page: not sure
        tops = [m[3] for m in single]
        enough = (
            len(single) >= PAGE_NUMBER_MIN_PAGES
            and len(single) >= PAGE_NUMBER_MIN_SHARE * geo.n_pages
            and _places_consistent([(page, place) for _, page, place, _ in single])
            and max(tops) - min(tops) <= PAGE_NUMBER_Y_TOLERANCE
        )
        if enough:
            found.extend(m[0] for m in single)
            kept.extend(
                (m[0], "two candidates on one page")
                for m in members
                if pages[m[1]] != 1
            )
        else:
            kept.extend(
                (m[0], "the same offset, place and height on too few pages")
                for m in members
            )
    warnings: list[dict[str, Any]] = []
    if kept:
        warnings.append(
            {
                "code": "page_number_kept",
                "count": len(kept),
                "pages": sorted({int(_provs(i)[0].page_no) for i, _ in kept})[:50],
                "reason": "looks like a page number but the evidence is not sufficient "
                f"(needs: alone on its line, centred or at the outer edge, the same "
                f"offset on >= {PAGE_NUMBER_MIN_PAGES} pages and "
                f">= {int(PAGE_NUMBER_MIN_SHARE * 100)} % of the pages): kept",
                "why": sorted({why for _, why in kept})[:5],
            }
        )
    return found, warnings


# --------------------------------------------------------------------------- #
# 2. Repeated lines, and what the layout model called header / footer
#    (findings F-01, R2-11)
# --------------------------------------------------------------------------- #


def _repeat_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _repeated_text_warnings(
    items: list[Any], doc: Any, geo: _Geometry, T: dict[str, Any], exclude: set[int]
) -> list[dict[str, Any]]:
    """Repeated TEXT lines at the page edge: reported, never removed (F-01)."""
    groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for item in items:
        if id(item) in exclude or not _edge_candidate(item, doc, T):
            continue
        text = (item.text or "").strip()
        if (
            not text
            or _layout_says_furniture(item, T)
            or len(text) > REPEATED_MAX_CHARS
        ):
            continue
        band = geo.band(_provs(item)[0])
        if band is None:
            continue
        groups[(band, _repeat_key(text))].append(item)
    warnings: list[dict[str, Any]] = []
    for key in sorted(groups):
        members = groups[key]
        pages = sorted({int(_provs(i)[0].page_no) for i in members})
        if len(pages) >= REPEATED_MIN_PAGES:
            warnings.append(
                {
                    "code": "repeated_line_kept",
                    "band": key[0],
                    "count": len(members),
                    "pages": pages[:50],
                    "sha256": _sha256(members[0].text or ""),
                    "reason": "the same line at the page edge on several pages: it may be a "
                    "running header / footer or repeated content (unit, issuer, "
                    "addressee, signature note); kept",
                }
            )
    return warnings


def _classify_header_footer(
    doc: Any, geo: _Geometry, T: dict[str, Any]
) -> tuple[list[Any], list[Any]]:
    """(artifacts, business content) among the items the LAYOUT MODEL labelled
    PAGE_HEADER / PAGE_FOOTER, in the body or in the furniture layer.

    An artifact repeats on two or more pages (a running title) or is a page
    number that fits the page index. Text that appears once - a document
    number, the issuer on page 1, a footnote labelled footer - is content.
    """
    from docling_core.types.doc.document import ContentLayer

    labelled: list[Any] = []
    for item, _ in doc.iterate_items(
        with_groups=False,
        traverse_pictures=False,
        included_content_layers={ContentLayer.BODY, ContentLayer.FURNITURE},
    ):
        if (
            type(item) is T["TextItem"]
            and _layout_says_furniture(item, T)
            and (item.text or "").strip()
            and _provs(item)
        ):
            labelled.append(item)
    pages_of: dict[str, set[int]] = defaultdict(set)
    for item in labelled:
        pages_of[_repeat_key(item.text or "")].update(
            int(p.page_no) for p in _provs(item)
        )
    artifacts, content = [], []
    for item in labelled:
        page = int(_provs(item)[0].page_no)
        value = _page_number_value(item.text or "", geo.n_pages)
        is_number = value is not None and (
            PAGE_NUMBER_MIN_OFFSET <= value - page <= PAGE_NUMBER_MAX_OFFSET
        )
        if is_number or len(pages_of[_repeat_key(item.text or "")]) >= 2:
            artifacts.append(item)
        else:
            content.append(item)
    return artifacts, content


# --------------------------------------------------------------------------- #
# 3. Pictures (finding F-06)
# --------------------------------------------------------------------------- #


def _picture_text_count(pic: Any, doc: Any, T: dict[str, Any]) -> int:
    """OCR text Docling placed INSIDE the picture; its captions / footnotes are
    separate items and say nothing about whether the picture itself was read."""
    attached = {r.cref for r in (pic.captions or [])} | {
        r.cref for r in (getattr(pic, "footnotes", None) or [])
    }
    n = 0
    for child, _ in doc.iterate_items(
        root=pic, with_groups=False, traverse_pictures=True
    ):
        if child is pic or getattr(child, "self_ref", None) in attached:
            continue
        if isinstance(child, T["TextItem"]) and (child.text or "").strip():
            n += 1
    return n


def _classify_pictures(
    items: list[Any], doc: Any, geo: _Geometry, T: dict[str, Any]
) -> tuple[list[tuple[Any, str]], list[tuple[Any, float | None, int]]]:
    """(pictures whose placeholder is dropped + why, pictures kept + area + texts)."""
    drop: list[tuple[Any, str]] = []
    keep: list[tuple[Any, float | None, int]] = []
    for item in items:
        if not isinstance(item, T["PictureItem"]):
            continue
        if _inside(item, doc, (T["TableItem"],)):
            continue  # rich table cell: leave the table exactly as it is
        ratio = geo.area_ratio(item)
        texts = _picture_text_count(item, doc, T)
        if ratio is not None and ratio < SILENT_PICTURE_RATIO:
            drop.append((item, "small picture (signature / stamp / logo)"))
        else:
            keep.append((item, ratio, texts))  # may hold a table, a diagram, a chart
    return drop, keep


# --------------------------------------------------------------------------- #
# 4. Joins across a page break (finding F-03), for the normalizer's own joins
#    and for Docling's merges (finding R2-01)
# --------------------------------------------------------------------------- #


def _starts_lowercase(text: str) -> bool:
    stripped = text.lstrip()
    return bool(stripped) and stripped[0].isalpha() and stripped[0].islower()


def _starts_new_unit(text: str) -> bool:
    return bool(_STRUCTURE_START.match(text.lstrip()))


def _ends_open(text: str) -> tuple[bool, str | None]:
    """(paragraph is unfinished, reason it is not)."""
    stripped = text.rstrip()
    if not stripped:
        return False, "empty"
    last = stripped[-1]
    if last in "-‐‑–­":
        return False, "hyphen"
    if last.isalnum() or last == ",":
        return True, None
    return False, "terminal"


@dataclass
class _Part:
    """One located line block: an item, or one provenance part of a merged item."""

    text: str
    page: int
    box: Box | None
    kind: str  # "text" (plain TEXT), "list", "other"
    marker: str
    pid: int  # id() of the provenance
    owner: int  # id() of the item
    inside: bool  # inside a picture or a table


def _part(
    item: Any, prov: Any, text: str, geo: _Geometry, doc: Any, T: dict[str, Any]
) -> _Part:
    if _is_plain_text(item, T):
        kind = "text"
    elif isinstance(item, T["ListItem"]):
        kind = "list"
    else:
        kind = "other"
    return _Part(
        text=text,
        page=int(prov.page_no),
        box=geo.box(prov),
        kind=kind,
        marker=(getattr(item, "marker", "") or "").strip(),
        pid=id(prov),
        owner=id(item),
        inside=_inside(item, doc, (T["PictureItem"], T["TableItem"])),
    )


class _JoinContext:
    """Per-document facts the join rules need, computed once."""

    def __init__(
        self,
        items: list[Any],
        doc: Any,
        geo: _Geometry,
        T: dict[str, Any],
        removed: set[int] | None = None,
    ) -> None:
        self.doc, self.geo, self.T = doc, geo, T
        widths: dict[int, list[float]] = defaultdict(list)
        self.texts_on_page: dict[int, set[str]] = defaultdict(set)
        # every located part of the body, per page: the "is it the only candidate"
        # rules look at what else is at the end of a page / the top of the next
        self.parts_by_page: dict[int, list[_Part]] = defaultdict(list)
        for item in items:
            if removed and id(item) in removed:
                continue
            provs = _provs(item)
            texts = _part_texts(item)
            for prov, text in zip(provs, texts):
                part = _part(item, prov, text, geo, doc, T)
                if part.box is not None and not part.inside:
                    self.parts_by_page[part.page].append(part)
            if not _is_paragraph(item, T):
                continue
            for prov in provs:
                box = geo.box(prov)
                if box is not None:
                    widths[int(prov.page_no)].append(box[2] - box[0])
            for prov in provs[:1]:
                self.texts_on_page[int(prov.page_no)].add(_repeat_key(item.text or ""))
        self.column_width = {page: statistics.median(v) for page, v in widths.items()}
        every = [w for v in widths.values() for w in v]
        self.doc_column_width = statistics.median(every) if every else None
        # Items the layout model itself labelled PAGE_FOOTER (furniture layer).
        from docling_core.types.doc.document import ContentLayer

        self.footer_tops: dict[int, list[float]] = defaultdict(list)
        for item, _ in doc.iterate_items(
            with_groups=False, included_content_layers={ContentLayer.FURNITURE}
        ):
            if getattr(item, "label", None) == T["DocItemLabel"].PAGE_FOOTER:
                for prov in _provs(item):
                    box = geo.box(prov)
                    if box is not None:
                        self.footer_tops[int(prov.page_no)].append(box[1])


def _part_texts(item: Any) -> list[str]:
    """The text of each provenance part of an item (its segments when Docling's
    char spans add up, else the whole text for the first part)."""
    provs = _provs(item)
    text = getattr(item, "text", "") or ""
    if len(provs) <= 1:
        return [text] * len(provs)
    found = _segments(item)
    if found is None:
        return [text] + [""] * (len(provs) - 1)
    spans, _ = found
    return [text[s:e] for s, e in spans]


def _pair_refusal(a: _Part, b: _Part, ctx: _JoinContext) -> tuple[str | None, bool]:
    """(why parts A and B may NOT be read as one paragraph - None when they may,
    whether the refusal is a near miss worth a warning).

    Every rule can only say no; the order goes from cheap text tests to
    geometry. A near miss reads like a cut paragraph (A unfinished, B starting
    in lowercase on the next page) and is still refused.
    """
    geo = ctx.geo
    if a.kind not in ("text", "list"):
        return "the first part is not a paragraph or list item", False
    if not (
        b.kind == "text" or (b.kind == "list" and a.kind == "list" and not b.marker)
    ):
        return "the second part is not a plain paragraph", False
    if a.inside or b.inside:
        return "inside a picture or table", False
    if b.page != a.page + 1:
        return "not on consecutive pages", False
    is_open, why = _ends_open(a.text)
    lowercase = _starts_lowercase(b.text)
    if not is_open:
        return (
            f"the first part ends with a {why} character",
            why == "hyphen" and lowercase,
        )
    if _starts_new_unit(b.text):
        return (
            "the second part starts a new unit (clause, point, date, unit line)",
            False,
        )
    if not lowercase:
        return "the second part does not start with a lowercase letter", False
    # From here on the pair reads like a cut paragraph: refusals are near misses.
    if a.kind == "list" and b.text.rstrip().endswith(";"):
        # A point / clause continued by a line that ends like a point itself: the
        # line may be the NEXT point whose marker OCR lost (and the point above
        # lost its ";"). Not decidable from the text: kept apart (F-03).
        return "the next line ends like a point of its own (lost marker?)", True
    if _FOOTNOTE_START.match(a.text.lstrip()):
        return "the first part looks like a footnote", True
    box_a, box_b = a.box, b.box
    size_a, size_b = geo.sizes.get(a.page), geo.sizes.get(b.page)
    if box_a is None or box_b is None or size_a is None or size_b is None:
        return "no bounding box / page size", True
    # ONE candidate on each side of the break (Phase 12D5, F-03)
    end_of_a = [p for p in ctx.parts_by_page.get(a.page, []) if p.pid != a.pid]
    if any(p.box is not None and p.box[1] > box_a[1] + 1 for p in end_of_a):
        return "something lies below the first part on its page (a footnote?)", True
    above = [p for p in end_of_a if p.box is not None and p.box[3] <= box_a[1] + 1]
    if above:
        nearest = max(above, key=lambda p: p.box[3])  # type: ignore[index]
        if nearest.kind in ("text", "list") and _ends_open(nearest.text)[0]:
            return "the page ends with two unfinished paragraphs (a footnote?)", True
    top_of_b = [p for p in ctx.parts_by_page.get(b.page, []) if p.pid != b.pid]
    if any(p.box is not None and p.box[3] <= box_b[1] + 1 for p in top_of_b):
        return "the second part is not the first line of its page", True
    below = [p for p in top_of_b if p.box is not None and p.box[1] >= box_b[3] - 1]
    if below:
        nearest = min(below, key=lambda p: p.box[1])  # type: ignore[index]
        if (
            nearest.kind in ("text", "list")
            and _starts_lowercase(nearest.text)
            and not _starts_new_unit(nearest.text)
        ):
            return "the next page has more than one candidate first line", True
    if box_a[1] >= BAND_BOTTOM * size_a[1] and not any(
        top >= box_a[3] - 1 for top in ctx.footer_tops.get(a.page, [])
    ):
        # A single line in the footer zone, and the layout model did not mark a
        # footer below it: it may be the footer itself.
        return "the first part lies entirely in the bottom band of its page", True
    if box_a[3] < JOIN_LOWER_HALF * size_a[1]:
        return "the first part does not end in the lower half of its page", True
    if box_b[1] > JOIN_UPPER_HALF * size_b[1]:
        return "the second part does not start in the upper half of its page", True
    overlap = min(box_a[2], box_b[2]) - max(box_a[0], box_b[0])
    narrower = min(box_a[2] - box_a[0], box_b[2] - box_b[0])
    if narrower <= 0 or overlap < JOIN_MIN_COLUMN_OVERLAP * narrower:
        return "the two parts are in different columns", True
    column = ctx.column_width.get(a.page) or ctx.doc_column_width
    if column and box_a[2] - box_a[0] < JOIN_MIN_COLUMN_SHARE * column:
        return "the first part is narrower than the body column (not a cut line)", True
    if box_b[0] - box_a[0] > JOIN_MAX_INDENT * size_b[0]:
        return "the second part has a first-line indent (a new paragraph)", True
    if _repeat_key(a.text) in ctx.texts_on_page.get(b.page, set()):
        return "the first part repeats on the next page (running footer)", True
    return None, False


# --------------------------------------------------------------------------- #
# 5. Docling's own merges (finding R2-01)
# --------------------------------------------------------------------------- #


def _segments(item: Any) -> tuple[list[tuple[int, int]], list[str]] | None:
    """Where each provenance part of a merged item lies in ``item.text``, and how
    each join was made ("space" / "dehyphen"), from Docling's char spans.

    Docling records part i at ``(len(text so far) + 1, ... + len(part))`` and then
    appends " " + part, or - before a lowercase continuation - replaces a final
    "-" / soft hyphen by the part. So the span arithmetic tells which join was
    made, and where. None when the spans do not add up (nothing is undone then).
    """
    provs = _provs(item)
    text = getattr(item, "text", "") or ""
    if len(provs) < 2:
        return None
    try:
        spans = [(int(p.charspan[0]), int(p.charspan[1])) for p in provs]
    except (TypeError, ValueError, IndexError, AttributeError):
        return None
    if spans[0][0] != 0 or any(e < s for s, e in spans):
        return None
    kinds: list[str] = []
    for i in range(1, len(spans)):
        after = spans[i + 1][0] - 1 if i + 1 < len(spans) else len(text)
        if after == spans[i][1]:
            kinds.append("space")
        elif after == spans[i][1] - 2:
            kinds.append("dehyphen")
        else:
            return None
    out: list[tuple[int, int]] = []
    start = 0
    for i, (s, e) in enumerate(spans):
        end = start + (e - s)
        if i < len(kinds) and kinds[i] == "dehyphen":
            end -= 1  # its last character (the hyphen) was removed
        out.append((start, end))
        if i < len(kinds):
            if kinds[i] == "space":
                if text[end : end + 1] != " ":
                    return None
                start = end + 1
            else:
                start = end
    if out[-1][1] != len(text):
        return None
    return out, kinds


def _evidence_key(page: int, box: Box | None) -> tuple[int, tuple[float, ...]] | None:
    if box is None:
        return None
    return page, tuple(round(float(v), 1) for v in box)


def source_evidence(conv_res: Any) -> dict[tuple[int, tuple[float, ...]], str] | None:
    """The text of every layout element BEFORE Docling's merge, by page and box.

    Docling's standard PDF pipeline keeps ``conv_res.assembled.elements`` after
    the conversion (only the parsed pages are released); each element's text is
    built from its OCR / text cells. Used ONLY to confirm a part of a merged
    item character for character and to restore the hyphen Docling removed;
    never to add any other text. None when the conversion result has no
    elements (other pipelines).
    """
    elements = getattr(getattr(conv_res, "assembled", None), "elements", None) or []
    out: dict[tuple[int, tuple[float, ...]], str] = {}
    for el in elements:
        text = getattr(el, "text", None)
        cluster = getattr(el, "cluster", None)
        bbox = getattr(cluster, "bbox", None)
        if not isinstance(text, str) or not text or bbox is None:
            continue
        try:
            box = (
                min(bbox.l, bbox.r),
                min(bbox.t, bbox.b),
                max(bbox.l, bbox.r),
                max(bbox.t, bbox.b),
            )
            key = _evidence_key(int(el.page_no), box)
        except (AttributeError, TypeError, ValueError):
            continue
        if key is not None:
            out[key] = text
    return out or None


def _reading_key(prov: Any, geo: _Geometry) -> tuple[int, float]:
    box = geo.box(prov)
    return int(prov.page_no), (box[1] if box else 0.0)


def _undo_upstream_merges(
    work: Any,
    T: dict[str, Any],
    evidence: dict[tuple[int, tuple[float, ...]], str] | None,
    record: Any,
    warnings: list[dict[str, Any]],
    budget: _Budget,
) -> int:
    """Split back Docling's merges that the join rules refuse (R2-01).

    A space join is undone from the recorded spans: the parts are exactly the
    texts Docling joined. A removed hyphen is restored only when the source
    evidence (the element's own text) shows it; otherwise the item is left as
    Docling made it and ``upstream_dehyphenation`` names the pages. Returns the
    number of items created.
    """
    items = _body_items(work)
    geo = _Geometry(work, items)
    ctx = _JoinContext(items, work, geo, T)
    created = 0
    for n, item in enumerate(items):
        if n % 2000 == 0:
            budget.check("upstream merges")
        provs = _provs(item)
        if len(provs) < 2 or not _is_plain_text(item, T):
            continue
        found = _segments(item)
        pages = sorted({int(p.page_no) for p in provs})
        if found is None:
            if len(pages) > 1 or len(provs) > 1:
                warnings.append(
                    {
                        "code": "upstream_merge_kept",
                        "pages": pages[:50],
                        "reason": "Docling joined several layout blocks into one paragraph and "
                        "their char spans do not add up: left as Docling made it; verify "
                        "against the scan",
                    }
                )
            continue
        spans, kinds = found
        text = item.text or ""
        parts = [
            _part(item, p, text[s:e], geo, work, T) for p, (s, e) in zip(provs, spans)
        ]
        cuts: list[int] = []  # boundary i: between part i and part i + 1
        restore: dict[int, str] = {}  # boundary -> hyphen character to put back
        for i, kind in enumerate(kinds):
            if kind == "dehyphen":
                # The part ended with "-" / a soft hyphen that Docling removed: the
                # rules never join across a hyphen (it may belong to the text).
                reason: str | None = "the first part ended with a hyphen"
            else:
                reason, _ = _pair_refusal(parts[i], parts[i + 1], ctx)
            if reason is None:
                continue  # a join the rules would make themselves
            if kind == "space":
                cuts.append(i)
                continue
            original = None
            key = _evidence_key(parts[i].page, parts[i].box)
            if evidence is not None and key is not None:
                original = evidence.get(key)
            seg = text[spans[i][0] : spans[i][1]]
            if (
                isinstance(original, str)
                and original[-1:] in ("-", "­")
                and original[:-1] == seg
            ):
                cuts.append(i)
                restore[i] = original[-1]
            else:
                warnings.append(
                    {
                        "code": "upstream_dehyphenation",
                        "pages": sorted({parts[i].page, parts[i + 1].page}),
                        "reason": "Docling joined a line ending with a hyphen to the next one "
                        f"and removed the hyphen ({reason}); the document does not show "
                        "which character it was, so the text is left as Docling made it: "
                        "verify against the scan",
                    }
                )
        if not cuts:
            continue
        record(
            "upstream_merge_undone",
            "Docling joined unrelated blocks; split back at the recorded char spans",
            [item],
            text,
            "",
        )
        created += _split_item(work, item, provs, spans, cuts, restore, geo)
        warnings.append(
            {
                "code": "upstream_merge_undone",
                "pages": pages[:50],
                "reason": "Docling had joined these blocks into one paragraph; the join rules "
                "refuse it, so the blocks are shown apart again, each with its own text",
            }
        )
    return created


def _split_item(
    work: Any,
    item: Any,
    provs: list[Any],
    spans: list[tuple[int, int]],
    cuts: list[int],
    restore: dict[int, str],
    geo: _Geometry,
) -> int:
    """Cut ``item`` after the parts in ``cuts``; the first group stays in the item,
    each other group becomes a new TEXT item placed at its own reading position
    (after the tables / pictures / footers Docling had skipped over)."""
    from docling_core.types.doc.document import ProvenanceItem

    text = item.text or ""
    bounds = [-1] + sorted(cuts) + [len(provs) - 1]
    groups = [(bounds[k] + 1, bounds[k + 1]) for k in range(len(bounds) - 1)]

    def group_text(first: int, last: int) -> str:
        out = text[spans[first][0] : spans[last][1]]
        return out + restore.get(last, "")

    def rebased(first: int, last: int) -> list[Any]:
        # Docling's OWN span arithmetic, shifted to the group (not the final text
        # positions): a de-hyphenated join kept inside a group is then read back
        # the same way by the next run (idempotence).
        base = int(provs[first].charspan[0])
        return [
            ProvenanceItem(
                page_no=provs[i].page_no,
                bbox=provs[i].bbox,
                charspan=(
                    int(provs[i].charspan[0]) - base,
                    int(provs[i].charspan[1]) - base,
                ),
            )
            for i in range(first, last + 1)
        ]

    first_first, first_last = groups[0]
    parent = _parent(item, work)
    item.text = group_text(first_first, first_last)
    item.orig = item.text
    item.prov = rebased(first_first, first_last)
    created = 0
    after = item
    for first, last in groups[1:]:
        new_provs = rebased(first, last)
        new = work.add_text(
            label=item.label,
            text=group_text(first, last),
            orig=group_text(first, last),
            prov=new_provs[0],
            parent=parent,
        )
        for extra in new_provs[1:]:
            new.prov.append(extra)
        # reading position: after the item (or the previous new part), past the
        # siblings Docling skipped that come before this part on the page(s)
        if parent is not None:
            children = parent.children
            # add_text appended the new reference: take it off the end in O(1)
            # (list.remove would compare pydantic models one by one - F-10)
            if children and children[-1].cref == new.self_ref:
                ref = children.pop()
            else:
                k = next(k for k, c in enumerate(children) if c.cref == new.self_ref)
                ref = children.pop(k)
            index = next(
                (k for k, c in enumerate(children) if c.cref == after.self_ref),
                len(children) - 1,
            )
            own = _reading_key(new_provs[0], geo)
            while index + 1 < len(children):
                nxt = children[index + 1].resolve(work)
                nxt_provs = _provs(nxt)
                if not nxt_provs or _reading_key(nxt_provs[0], geo) >= own:
                    break
                index += 1
            children.insert(index + 1, ref)
        after = new
        created += 1
    return created


# --------------------------------------------------------------------------- #
# The normalizer
# --------------------------------------------------------------------------- #


def normalize_document(
    doc: Any,
    *,
    include_text: bool = False,
    evidence: dict[tuple[int, tuple[float, ...]], str] | None = None,
) -> NormalizationResult:
    """Normalize a COPY of ``doc``; ``doc`` itself is never modified.

    ``evidence``: the element texts before Docling's merge (``source_evidence``
    of the conversion result), used only to restore a hyphen Docling removed.
    """
    budget = _Budget()
    _check_limits(doc)
    from docling_core.types.doc.document import ContentLayer, ListGroup

    T = _types()
    work = doc.model_copy(deep=True)
    budget.check("copy")
    ops: list[Operation] = []
    warnings: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    sizes_only = _Geometry(work, [])

    def record(
        op: str, reason: str, targets: Iterable[Any], before: str = "", after: str = ""
    ) -> None:
        targets = list(targets)
        provs = [p for i in targets for p in _provs(i)]
        ops.append(
            Operation(
                op=op,
                reason=reason,
                pages=sorted({int(p.page_no) for p in provs}),
                refs=[str(getattr(i, "self_ref", "")) for i in targets],
                bboxes=[b for b in (sizes_only.bbox_list(p) for p in provs) if b],
                chars_before=len(before),
                chars_after=len(after),
                sha256=_sha256(before),
                text_before=before if include_text else None,
                text_after=after if include_text else None,
            )
        )
        counts[op] += 1

    # 0. Docling's own merges the join rules refuse are split back (R2-01).
    _undo_upstream_merges(work, T, evidence, record, warnings, budget)
    budget.check("upstream merges")

    # 1. What the layout model labelled header / footer: artifacts leave the
    #    body, text that appears once is business content and joins it (R2-11).
    hf_artifacts, hf_content = _classify_header_footer(
        work, _Geometry(work, _body_items(work)), T
    )
    brought: list[Any] = []
    for item in hf_content:
        if item.content_layer != ContentLayer.BODY:
            item.content_layer = ContentLayer.BODY
            record(
                "furniture_text_kept",
                "labelled PAGE_HEADER / PAGE_FOOTER by the layout model but it appears "
                "once: business content, kept in the text",
                [item],
                item.text,
                item.text,
            )
            brought.append(item)
    if brought:
        warnings.append(
            {
                "code": "furniture_text_kept",
                "count": len(brought),
                "pages": sorted({int(_provs(i)[0].page_no) for i in brought})[:50],
                "reason": "text the layout model labelled header / footer appears only once "
                "(a document number, the issuer, a footnote?): kept in the text; the "
                "standard export leaves it out",
            }
        )

    items = _body_items(work)
    geo = _Geometry(work, items)
    budget.check("geometry")

    # 2. Page artifacts the layout model left in the body.
    page_numbers, pn_warnings = _find_page_numbers(
        items, work, geo, T, budget, _Lines(work, geo)
    )
    warnings.extend(pn_warnings)
    labelled = [i for i in hf_artifacts if i.content_layer == ContentLayer.BODY]
    warnings.extend(
        _repeated_text_warnings(items, work, geo, T, {id(i) for i in page_numbers})
    )
    artifacts = {id(i) for i in page_numbers} | {id(i) for i in labelled}
    budget.check("artifacts")

    # 3. Pictures.
    drop_pictures, kept_pictures = _classify_pictures(items, work, geo, T)
    silent = {id(p) for p, _ in drop_pictures}
    budget.check("pictures")

    # 4. Cross-page joins (skipping only removed artifacts / dropped pictures).
    ctx = _JoinContext(items, work, geo, T, removed=artifacts | silent)
    position = {id(i): n for n, i in enumerate(items)}
    real = [i for i in items if id(i) not in artifacts and id(i) not in silent]
    joined: list[Any] = []
    joined_ids: set[int] = set()
    kept_real: list[Any] = []  # `real` without the parts joined into their predecessor
    for b in real:
        if len(kept_real) % 2000 == 0:
            budget.check("joins")
        a = kept_real[-1] if kept_real else None
        if a is None or not _provs(a) or not _provs(b):
            kept_real.append(b)
            continue
        reason, near_miss = _pair_refusal(
            _part(a, _provs(a)[-1], getattr(a, "text", "") or "", geo, work, T),
            _part(b, _provs(b)[0], getattr(b, "text", "") or "", geo, work, T),
            ctx,
        )
        if reason is None:
            between = [
                x
                for x in items[position[id(a)] + 1 : position[id(b)]]
                if id(x) not in joined_ids
            ]
            pages_ab = {int(_provs(a)[-1].page_no), int(_provs(b)[0].page_no)}
            if any(int(p.page_no) not in pages_ab for x in between for p in _provs(x)):
                reason, near_miss = (
                    "something on another page lies between the two parts",
                    True,
                )
        if reason is not None:
            if near_miss:
                code = (
                    "hyphen_at_page_break_not_joined"
                    if "hyphen" in reason
                    else "join_not_made"
                )
                warnings.append(
                    {
                        "code": code,
                        "pages": sorted(
                            {int(p.page_no) for p in _provs(a)[-1:] + _provs(b)[:1]}
                        ),
                        "reason": reason,
                    }
                )
            kept_real.append(b)
            continue
        before = f"{a.text}\n\n{b.text}"
        left = (a.text or "").rstrip()
        base = len(left) + 1
        first_b = int(_provs(b)[0].charspan[0])
        for p in _provs(b):  # Docling's span arithmetic: the next run reads it back
            p.charspan = (
                base + int(p.charspan[0]) - first_b,
                base + int(p.charspan[1]) - first_b,
            )
        a.text = f"{left} {(b.text or '').lstrip()}"
        a.orig = f"{(a.orig or '').rstrip()} {(b.orig or '').lstrip()}"
        a.prov.extend(b.prov)
        record(
            "join_across_pages",
            "unfinished paragraph continues on the next page",
            [a],
            before,
            a.text,
        )
        joined.append(b)  # a stays last: it may continue again on the following page
        joined_ids.add(id(b))

    for item in page_numbers:
        record(
            "page_number_to_furniture",
            "page-number shape, alone on its line, page edge, same offset / place on "
            "most pages",
            [item],
            item.text,
            "",
        )
        item.content_layer = ContentLayer.FURNITURE
    for item in labelled:
        record(
            "running_header_footer_to_furniture",
            "labelled PAGE_HEADER / PAGE_FOOTER by the layout model and repeated (or a "
            "page number)",
            [item],
            item.text,
            "",
        )
        item.content_layer = ContentLayer.FURNITURE
    for item in joined:
        # Its text now lives in the previous paragraph. Taking it out of the body
        # layer is O(1); DoclingDocument.delete_items is quadratic (finding F-10).
        item.content_layer = ContentLayer.INVISIBLE
    budget.check("apply")

    for pic, why in drop_pictures:
        record("image_placeholder_dropped", why, [pic])
    for pic, ratio, texts in kept_pictures:
        provs = _provs(pic)
        warnings.append(
            {
                "code": "picture_without_text"
                if not texts
                else "picture_text_unverified",
                "pages": sorted({int(p.page_no) for p in provs}),
                "bbox": geo.bbox_list(provs[0]) if provs else [],
                "area_ratio": round(ratio, 4) if ratio is not None else None,
                "reason": (
                    "picture with no OCR text: it may contain a table, a diagram or a "
                    "chart that was not extracted; the placeholder is kept"
                    if not texts
                    else f"{texts} OCR text block(s) were found inside the picture and are "
                    "kept, but nothing shows the whole picture was read: the placeholder "
                    "is kept"
                ),
            }
        )
        counts["image_placeholder_kept"] += 1
    gone = joined_ids | artifacts
    counts["picture_text_items"] = sum(
        1
        for it in items
        if id(it) not in gone
        and isinstance(it, T["TextItem"])
        and (it.text or "").strip()
        and _inside(it, work, (T["PictureItem"],))
    )

    # 5. List markers (counted here, written by the serializer).
    for item in items:
        if id(item) in gone or not isinstance(item, T["ListItem"]):
            continue
        if (item.marker or "").strip():
            counts["list_markers_preserved"] += 1
        else:
            group = _parent(item, work)
            if isinstance(group, ListGroup) and group.first_item_is_enumerated(work):
                counts["synthesized_number_avoided"] += 1
    budget.check("serialize")

    serializer = _build_serializer(work, {p.self_ref for p, _ in drop_pictures})
    content = serializer.serialize().text
    return NormalizationResult(
        content=content,
        operations=ops,
        warnings=warnings,
        counts=dict(counts),
        elapsed_ms=(time.perf_counter() - budget.started) * 1000,
        document=work,
    )


def normalize_or_fallback(
    doc: Any,
    standard: str | None = None,
    evidence: dict[tuple[int, tuple[float, ...]], str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Legal content + metadata, or the standard export when normalization fails.

    Never raises for a normalization problem: the extraction result must not be
    lost because of it. The metadata says which content was produced;
    ``legal_normalization_record`` is the small record stored with the Source.
    """
    from loguru import logger

    def failed(error: str) -> tuple[str, dict[str, Any]]:
        content = standard if standard is not None else doc.export_to_markdown()
        return content, {
            "text_normalization": MODE_LEGAL,
            "legal_normalization_status": "failed",
            "legal_normalization_error": error,
            "legal_normalizer_version": NORMALIZER_VERSION,
            "legal_normalization_record": failed_record(error),
        }

    try:
        result = normalize_document(doc, evidence=evidence)
    except Exception as e:  # noqa: BLE001 - any failure -> the standard export
        logger.warning(
            f"Legal document normalization {NORMALIZER_VERSION} failed "
            f"({type(e).__name__}); the standard Docling export is kept."
        )
        return failed(type(e).__name__)
    if not result.content.strip():
        fallback = standard if standard is not None else doc.export_to_markdown()
        if fallback.strip():
            # Defensive: never replace text by nothing.
            logger.warning(
                "Legal document normalization produced no text; the standard export is kept."
            )
            return failed("EmptyResult")
    meta = {
        "text_normalization": MODE_LEGAL,
        "legal_normalization_status": "applied",
        **result.summary(),
        "legal_normalization_record": result.persistable(),
    }
    c = result.counts
    logger.info(
        f"Legal document normalization {NORMALIZER_VERSION}: "
        f"operations={len(result.operations)} "
        f"placeholders_dropped={c.get('image_placeholder_dropped', 0)} "
        f"placeholders_kept={c.get('image_placeholder_kept', 0)} "
        f"page_numbers={c.get('page_number_to_furniture', 0)} "
        f"headers_footers={c.get('running_header_footer_to_furniture', 0)} "
        f"furniture_text_kept={c.get('furniture_text_kept', 0)} "
        f"upstream_merges_undone={c.get('upstream_merge_undone', 0)} "
        f"joins={c.get('join_across_pages', 0)} "
        f"warnings={len(result.warnings)} in {result.elapsed_ms:.1f} ms"
    )
    return result.content, meta
