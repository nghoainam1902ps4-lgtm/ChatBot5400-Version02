"""Legal Document normalization of a Docling result (Phase 12, decision D-34).

Works on a COPY of the ``DoclingDocument`` Docling produced, using the structure
Docling already computed (labels, content layers, list markers, provenance
pages and bounding boxes, reading order) - never the flattened Markdown string.

RULE ZERO (Phase 12D3, after the independent audit): legal content is kept
unless the evidence that something is a page artifact is strong. Leaving a page
number in the text is a blemish; deleting a year, a clause number or a unit of
account is a defect. Whenever the evidence is missing the item stays and a
warning says so.

What it does:

1. PAGE NUMBERS labelled TEXT by the layout model go to the furniture layer
   (where Docling itself puts PAGE_HEADER / PAGE_FOOTER) only when ALL hold:
   strict page-number shape; top / bottom band and outermost on its page;
   the same "printed number - PDF page" offset on at least 3 pages AND at least
   60 % of the pages; the same band; a consistent horizontal position (one
   place, or mirrored on odd / even pages); a value that fits the document;
   not aligned with the left edge of the paragraphs (a detached clause number
   starts where the paragraphs start). One- and two-page documents never
   qualify.
2. REPEATED LINES labelled TEXT are never removed: "Đơn vị tính: triệu đồng",
   an issuer line, "Kính gửi", "Nơi nhận", a signature note, a column header of
   an unrecognised table look exactly like a running header. They are reported
   (``repeated_line_kept``). Only an item the layout model itself labelled
   PAGE_HEADER / PAGE_FOOTER and that is still in the body is moved.
3. PICTURES: the ``<!-- image -->`` placeholder is dropped only for a picture
   under 4 % of the page with no text (signature, stamp, logo) and for a picture
   whose OCR text is kept anyway. Every other picture keeps the placeholder and
   raises a located warning: it may hold a table, a diagram or a chart that
   nobody extracted. OCR text Docling placed INSIDE a picture is kept
   (``traverse_pictures``); the standard export drops it.
4. A PARAGRAPH CUT BY A PAGE BREAK is joined to its continuation only when
   every rule of ``_join_refusal`` passes (see there). The refusal reason of a
   near miss is reported (``join_not_made``). One space is the only character
   ever added.
5. LIST ITEMS are written with their ORIGINAL marker ("9.", "a)", "đ)", "1.1",
   "-") as plain text, one paragraph each; an item without a recognised marker
   is never given a synthesised number. The stored text IS the visible text:
   no Markdown escape of markers is stored (chunks, embeddings, copy and display
   see the same characters). The Source page escapes a leading marker at render
   time so that no list is built and nothing is renumbered
   (``frontend/src/lib/utils/legal-display.ts``).

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

NORMALIZER_VERSION = "1.1.0"

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

# Repeated lines (finding F-01): reported, never removed.
REPEATED_MAX_CHARS = 150
REPEATED_MIN_PAGES = 3

# What is stored for the Source (finding F-07): bounded, no text.
PERSIST_MAX_OPERATIONS = 200
PERSIST_MAX_WARNINGS = 50

_PAGE_NUMBER_RES = [
    re.compile(p)
    for p in (
        r"\d{1,4}",
        r"[-–—]\s*\d{1,4}\s*[-–—]",
        r"(?i:trang)\s+\d{1,4}(?:\s*(?:/|(?i:trên))\s*\d{1,4})?",
        r"(?i:page)\s+\d{1,4}(?:\s*(?:/|(?i:of))\s*\d{1,4})?",
        r"\d{1,4}\s*/\s*\d{1,4}",
    )
]
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
    r")",
    re.IGNORECASE,
)

# A footnote the layout model labelled TEXT: "1 Thông tư…", "(1) …", "* …".
_FOOTNOTE_START = re.compile(r"^(?:\d{1,2}\s+\S|\(\d{1,2}\)\s|\[\d{1,2}\]\s|[*†‡])")

# Markdown block syntax a literal text line must not trigger. List markers are
# NOT escaped in the stored text (see the module docstring, point 5).
_MD_HEADING = re.compile(r"^(\s{0,3})(#{1,6})(?=\s|$)")
_MD_QUOTE = re.compile(r"^(\s{0,3})(>)")


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

    return MarkdownDocSerializer(
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
# 1. Page numbers (finding F-02)
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


def _x_consistent(members: list[tuple[int, float]]) -> bool:
    """One horizontal place, or one for odd pages and one for even pages."""

    def tight(values: list[float]) -> bool:
        return not values or max(values) - min(values) <= PAGE_NUMBER_X_TOLERANCE

    if tight([x for _, x in members]):
        return True
    odd = [x for page, x in members if page % 2]
    even = [x for page, x in members if not page % 2]
    return bool(odd) and bool(even) and tight(odd) and tight(even)


def _find_page_numbers(
    items: list[Any], doc: Any, geo: _Geometry, T: dict[str, Any], budget: _Budget
) -> tuple[list[Any], list[dict[str, Any]]]:
    body_left = _body_left_edges(items, geo, T)
    doc_left = statistics.median(body_left.values()) if body_left else None
    labelled: list[Any] = []
    # (offset, band) -> [(item, page, x_centre)]
    groups: dict[tuple[int, str], list[tuple[Any, int, float]]] = defaultdict(list)
    kept: list[Any] = []
    for n, item in enumerate(items):
        if n % 5000 == 0:
            budget.check("page numbers")
        if not _edge_candidate(item, doc, T):
            continue
        text = (item.text or "").strip()
        if not text or len(text) > PAGE_NUMBER_MAX_CHARS:
            continue
        if not any(rx.fullmatch(text) for rx in _PAGE_NUMBER_RES):
            continue
        prov = _provs(item)[0]
        band = geo.band(prov)
        if band is None or not geo.outermost(item, band):
            continue  # inside the body: never a candidate, not even a suspect
        if _layout_says_furniture(item, T):
            labelled.append(item)  # the layout model's own verdict
            continue
        page = int(prov.page_no)
        box = geo.box(prov)
        assert box is not None  # band() returned a value
        width = geo.sizes[page][0]
        found_int = _FIRST_INT.search(text)
        value = int(found_int.group(0)) if found_int else 0
        offset = value - page
        left_edge = body_left.get(page, doc_left)
        at_body_margin = (
            left_edge is not None
            and abs(box[0] - left_edge) <= BODY_MARGIN_TOLERANCE * width
        )
        if (
            value < 1
            or not PAGE_NUMBER_MIN_OFFSET <= offset <= PAGE_NUMBER_MAX_OFFSET
            or at_body_margin
        ):
            kept.append(item)
            continue
        groups[(offset, band)].append((item, page, (box[0] + box[2]) / 2 / width))
    found: list[Any] = list(labelled)
    for key in sorted(groups):
        members = groups[key]
        pages = Counter(page for _, page, _ in members)
        single = [m for m in members if pages[m[1]] == 1]  # two on one page: not sure
        enough = (
            len(single) >= PAGE_NUMBER_MIN_PAGES
            and len(single) >= PAGE_NUMBER_MIN_SHARE * geo.n_pages
            and _x_consistent([(page, x) for _, page, x in single])
        )
        if enough:
            found.extend(item for item, _, _ in single)
            kept.extend(m[0] for m in members if pages[m[1]] != 1)
        else:
            kept.extend(item for item, _, _ in members)
    warnings: list[dict[str, Any]] = []
    if kept:
        warnings.append(
            {
                "code": "page_number_kept",
                "count": len(kept),
                "pages": sorted({int(_provs(i)[0].page_no) for i in kept})[:50],
                "reason": "looks like a page number but the evidence is not sufficient "
                f"(needs the same offset on >= {PAGE_NUMBER_MIN_PAGES} pages and "
                f">= {int(PAGE_NUMBER_MIN_SHARE * 100)} % of the pages, one position, "
                "outside the paragraph margin): kept",
            }
        )
    return found, warnings


# --------------------------------------------------------------------------- #
# 2. Repeated lines (finding F-01): reported, never removed
# --------------------------------------------------------------------------- #


def _repeat_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _find_repeated(
    items: list[Any], doc: Any, geo: _Geometry, T: dict[str, Any], exclude: set[int]
) -> tuple[list[Any], list[dict[str, Any]]]:
    """(items the LAYOUT MODEL labelled header / footer, warnings for repeated TEXT lines)."""
    labelled: list[Any] = []
    groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for item in items:
        if id(item) in exclude or not _edge_candidate(item, doc, T):
            continue
        text = (item.text or "").strip()
        if not text:
            continue
        if _layout_says_furniture(item, T):
            labelled.append(item)
            continue
        if len(text) > REPEATED_MAX_CHARS:
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
    return labelled, warnings


# --------------------------------------------------------------------------- #
# 3. Pictures (finding F-06)
# --------------------------------------------------------------------------- #


def _picture_has_text(pic: Any, doc: Any, T: dict[str, Any]) -> bool:
    for child, _ in doc.iterate_items(
        root=pic, with_groups=False, traverse_pictures=True
    ):
        if child is pic:
            continue
        if isinstance(child, T["TextItem"]) and (child.text or "").strip():
            return True
    return False


def _classify_pictures(
    items: list[Any], doc: Any, geo: _Geometry, T: dict[str, Any]
) -> tuple[list[tuple[Any, str]], list[tuple[Any, float | None]]]:
    """(pictures whose placeholder is dropped + why, pictures kept + area ratio)."""
    drop: list[tuple[Any, str]] = []
    keep: list[tuple[Any, float | None]] = []
    for item in items:
        if not isinstance(item, T["PictureItem"]):
            continue
        if _inside(item, doc, (T["TableItem"],)):
            continue  # rich table cell: leave the table exactly as it is
        if _picture_has_text(item, doc, T):
            drop.append((item, "OCR text inside the picture is kept"))
            continue
        ratio = geo.area_ratio(item)
        if ratio is not None and ratio < SILENT_PICTURE_RATIO:
            drop.append((item, "small picture without text (signature / stamp / logo)"))
        else:
            keep.append((item, ratio))  # may hold a table, a diagram, a chart
    return drop, keep


# --------------------------------------------------------------------------- #
# 4. Cross-page joins (finding F-03)
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


class _JoinContext:
    """Per-document facts the join rules need, computed once."""

    def __init__(
        self, items: list[Any], doc: Any, geo: _Geometry, T: dict[str, Any]
    ) -> None:
        self.doc, self.geo, self.T = doc, geo, T
        widths: dict[int, list[float]] = defaultdict(list)
        self.texts_on_page: dict[int, set[str]] = defaultdict(set)
        for item in items:
            if not _is_paragraph(item, T):
                continue
            for prov in _provs(item):
                box = geo.box(prov)
                if box is not None:
                    widths[int(prov.page_no)].append(box[2] - box[0])
            for prov in _provs(item)[:1]:
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


def _join_refusal(
    a: Any, b: Any, between: list[Any], ctx: _JoinContext
) -> tuple[str | None, bool]:
    """(why A and B are NOT joined - None when they are, whether it was a near miss).

    A near miss is a pair that reads like a cut paragraph (A unfinished, B starts
    in lowercase on the next page) and is still refused: worth a warning.
    Every rule can only say no; the order goes from cheap text tests to geometry.
    """
    T, geo, doc = ctx.T, ctx.geo, ctx.doc
    if not _is_paragraph(a, T):
        return "the first part is not a paragraph or list item", False
    b_ok = _is_plain_text(b, T) or (
        isinstance(b, T["ListItem"])
        and isinstance(a, T["ListItem"])
        and not (b.marker or "").strip()
    )
    if not b_ok:
        return "the second part is not a plain paragraph", False
    kinds = (T["PictureItem"], T["TableItem"])
    if _inside(a, doc, kinds) or _inside(b, doc, kinds):
        return "inside a picture or table", False
    pa, pb = _provs(a), _provs(b)
    if not pa or not pb:
        return "no provenance", False
    last_a, first_b = pa[-1], pb[0]
    page_a, page_b = int(last_a.page_no), int(first_b.page_no)
    if page_b != page_a + 1:
        return "not on consecutive pages", False
    is_open, why = _ends_open(a.text or "")
    lowercase = _starts_lowercase(b.text or "")
    if not is_open:
        return (
            f"the first part ends with a {why} character",
            why == "hyphen" and lowercase,
        )
    if _starts_new_unit(b.text or ""):
        return "the second part starts a new unit (clause, point, bullet)", False
    if not lowercase:
        return "the second part does not start with a lowercase letter", False
    # From here on the pair reads like a cut paragraph: refusals are near misses.
    if between:
        if any(
            int(p.page_no) not in (page_a, page_b) for x in between for p in _provs(x)
        ):
            return "something on another page lies between the two parts", True
    if _FOOTNOTE_START.match((a.text or "").lstrip()):
        return "the first part looks like a footnote", True
    box_a, box_b = geo.box(last_a), geo.box(first_b)
    size_a, size_b = geo.sizes.get(page_a), geo.sizes.get(page_b)
    if box_a is None or box_b is None or size_a is None or size_b is None:
        return "no bounding box / page size", True
    if box_a[1] >= BAND_BOTTOM * size_a[1] and not any(
        top >= box_a[3] - 1 for top in ctx.footer_tops.get(page_a, [])
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
    column = ctx.column_width.get(page_a) or ctx.doc_column_width
    if column and box_a[2] - box_a[0] < JOIN_MIN_COLUMN_SHARE * column:
        return "the first part is narrower than the body column (not a cut line)", True
    if box_b[0] - box_a[0] > JOIN_MAX_INDENT * size_b[0]:
        return "the second part has a first-line indent (a new paragraph)", True
    if _repeat_key(a.text or "") in ctx.texts_on_page.get(page_b, set()):
        return "the first part repeats on the next page (running footer)", True
    return None, False


# --------------------------------------------------------------------------- #
# The normalizer
# --------------------------------------------------------------------------- #


def normalize_document(doc: Any, *, include_text: bool = False) -> NormalizationResult:
    """Normalize a COPY of ``doc``; ``doc`` itself is never modified."""
    budget = _Budget()
    _check_limits(doc)
    from docling_core.types.doc.document import ContentLayer, ListGroup

    T = _types()
    work = doc.model_copy(deep=True)
    budget.check("copy")
    ops: list[Operation] = []
    warnings: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    items = _body_items(work)
    geo = _Geometry(work, items)
    budget.check("geometry")

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
                bboxes=[b for b in (geo.bbox_list(p) for p in provs) if b],
                chars_before=len(before),
                chars_after=len(after),
                sha256=_sha256(before),
                text_before=before if include_text else None,
                text_after=after if include_text else None,
            )
        )
        counts[op] += 1

    # 1-2. Page artifacts the layout model left in the body.
    page_numbers, pn_warnings = _find_page_numbers(items, work, geo, T, budget)
    warnings.extend(pn_warnings)
    labelled, repeat_warnings = _find_repeated(
        items, work, geo, T, {id(i) for i in page_numbers}
    )
    warnings.extend(repeat_warnings)
    artifacts = {id(i) for i in page_numbers} | {id(i) for i in labelled}
    budget.check("artifacts")

    # 3. Pictures.
    drop_pictures, kept_pictures = _classify_pictures(items, work, geo, T)
    silent = {id(p) for p, why in drop_pictures if why.startswith("small")}
    budget.check("pictures")

    # 4. Cross-page joins (skipping only removed artifacts / silently dropped pictures).
    ctx = _JoinContext(items, work, geo, T)
    position = {id(i): n for n, i in enumerate(items)}
    real = [i for i in items if id(i) not in artifacts and id(i) not in silent]
    joined: list[Any] = []
    joined_ids: set[int] = set()
    kept_real: list[Any] = []  # `real` without the parts joined into their predecessor
    for b in real:
        if len(kept_real) % 2000 == 0:
            budget.check("joins")
        a = kept_real[-1] if kept_real else None
        if a is None:
            kept_real.append(b)
            continue
        between = [
            x
            for x in items[position[id(a)] + 1 : position[id(b)]]
            if id(x) not in joined_ids
        ]
        reason, near_miss = _join_refusal(a, b, between, ctx)
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
        a.text = f"{(a.text or '').rstrip()} {(b.text or '').lstrip()}"
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
        why = (
            "labelled PAGE_HEADER / PAGE_FOOTER by the layout model"
            if _layout_says_furniture(item, T)
            else "page-number shape, page edge, same offset on most pages, one position"
        )
        record("page_number_to_furniture", why, [item], item.text, "")
        item.content_layer = ContentLayer.FURNITURE
    for item in labelled:
        record(
            "running_header_footer_to_furniture",
            "labelled PAGE_HEADER / PAGE_FOOTER by the layout model",
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
    for pic, ratio in kept_pictures:
        provs = _provs(pic)
        warnings.append(
            {
                "code": "picture_without_text",
                "pages": sorted({int(p.page_no) for p in provs}),
                "bbox": geo.bbox_list(provs[0]) if provs else [],
                "area_ratio": round(ratio, 4) if ratio is not None else None,
                "reason": "picture with no OCR text: it may contain a table, a diagram or a "
                "chart that was not extracted; the placeholder is kept",
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
    doc: Any, standard: str | None = None
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
        result = normalize_document(doc)
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
        f"joins={c.get('join_across_pages', 0)} "
        f"warnings={len(result.warnings)} in {result.elapsed_ms:.1f} ms"
    )
    return result.content, meta
