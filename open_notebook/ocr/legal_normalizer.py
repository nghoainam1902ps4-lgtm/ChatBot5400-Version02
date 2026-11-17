"""Legal Document normalization of a Docling result (Phase 12, decision D-34).

WHAT IT DOES - on a COPY of the ``DoclingDocument`` Docling produced, using the
structure Docling already computed (labels, list markers, provenance pages and
bounding boxes, reading order), never the flattened Markdown string:

1. Page numbers that the layout model labelled as body TEXT are moved to the
   furniture layer (where Docling itself puts PAGE_HEADER / PAGE_FOOTER) when
   the evidence agrees: strict page-number shape, top/bottom band of the page,
   and the same "printed number - page number" offset on at least two pages.
2. Short lines repeated in the same top/bottom band on most pages (running
   headers / footers labelled as TEXT) are moved to the furniture layer.
3. The ``<!-- image -->`` placeholder is dropped for pictures that carry no
   information as text: small pictures (signatures, stamps, logos), and
   pictures whose caption or OCR text is kept anyway. Large pictures without any
   text keep the placeholder and raise a warning (they may hold information
   nobody extracted). OCR text Docling placed INSIDE a picture region is kept
   (``traverse_pictures``): the standard export silently drops it.
4. A paragraph cut by a page break is joined to its continuation only when every
   rule in ``_join_allowed`` holds (consecutive pages, nothing but removed
   artifacts in between, the first part does not end a sentence, the second
   starts with a lowercase letter and is not a new Điều / Khoản / điểm, both
   parts lie at the page bottom / top). No character is added except one space.
5. List items are written with their ORIGINAL marker ("9.", "a)", "đ)", "1.1",
   "-") as literal text, escaped so that no Markdown renderer can renumber
   them, and an item without a recognised marker is never given a synthesised
   number (Docling's serializer writes its position in the list instead).

WHAT IT NEVER DOES: call an LLM or the network, touch the database or a file,
change a character of recognised text (spelling, digits, 0/O, 1/l, units),
add a word, renumber anything, flatten or merge tables. When the evidence is
missing (no provenance, no page size) the content is kept as it is.

Pure and deterministic: same document in, same Markdown out; running it on its
own output document changes nothing (idempotent). Callers keep the standard
export as the fallback (``normalize_or_fallback``).
"""

from __future__ import annotations

import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

NORMALIZER_VERSION = "1.0.0"

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

# Geometry (fractions of the page height, top-left origin).
BAND_TOP = 0.10  # an item entirely above this line is in the top band
BAND_BOTTOM = 0.90  # an item entirely below this line is in the bottom band
JOIN_LOWER_HALF = 0.50  # first part of a join ends in the lower half of its page
JOIN_UPPER_HALF = 0.50  # second part starts in the upper half of the next page
LARGE_PICTURE_RATIO = 0.15  # pictures at least this share of the page are "large"

PAGE_NUMBER_MAX_CHARS = 20
REPEATED_MAX_CHARS = 150
REPEATED_MIN_PAGES = 3
REPEATED_MIN_SHARE = 0.5

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
    r"(?:phần|chương|mục|điều|khoản|điểm|tiểu mục)\s+[\divxlcdm]+"  # Phần I, Điều 5
    r"|[a-zđ](?:\.\d+)*\)"  # a)  đ)  a.1)
    r"|[ivxlcdm]+[.)]\s"  # i.  ii)
    r"|\d+(?:\.\d+)*[.)]?\s"  # 1.  1.1  2)
    r"|[-+*•●○▪–]\s"  # bullets
    r")",
    re.IGNORECASE,
)
_STRUCTURE_WORDS = re.compile(r"^(?:phần|chương|mục|điều)\b", re.IGNORECASE)

# Markdown block syntax at the start of a line that would turn literal text into
# a list / heading / quote (and let the renderer renumber "9." as "1.").
_MD_ORDERED = re.compile(r"^(\s{0,3})(\d{1,9})([.)])(?=\s|$)")
_MD_BULLET = re.compile(r"^(\s{0,3})([-+*])(?=\s|$)")
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
    # Only with include_text=True (local diagnostics): never logged.
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


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #


def _provs(item: Any) -> list[Any]:
    return list(getattr(item, "prov", None) or [])


def _page_height(doc: Any, page_no: int) -> float | None:
    page = (getattr(doc, "pages", None) or {}).get(page_no)
    size = getattr(page, "size", None)
    height = getattr(size, "height", None)
    return float(height) if height else None


def _page_width(doc: Any, page_no: int) -> float | None:
    page = (getattr(doc, "pages", None) or {}).get(page_no)
    size = getattr(page, "size", None)
    width = getattr(size, "width", None)
    return float(width) if width else None


def _top_left(prov: Any, doc: Any) -> tuple[float, float, float, float] | None:
    """(l, t, r, b) with a top-left origin, or None without page size / bbox."""
    bbox = getattr(prov, "bbox", None)
    height = _page_height(doc, getattr(prov, "page_no", -1))
    if bbox is None or not height:
        return None
    try:
        tl = bbox.to_top_left_origin(page_height=height)
    except Exception:
        return None
    t, b = min(tl.t, tl.b), max(tl.t, tl.b)
    return float(tl.l), float(t), float(tl.r), float(b)


def _bbox_list(prov: Any, doc: Any) -> list[float]:
    box = _top_left(prov, doc)
    return [round(v, 1) for v in box] if box else []


def _band(prov: Any, doc: Any) -> str | None:
    box = _top_left(prov, doc)
    height = _page_height(doc, getattr(prov, "page_no", -1))
    if box is None or not height:
        return None
    _, t, _, b = box
    if b <= BAND_TOP * height:
        return "top"
    if t >= BAND_BOTTOM * height:
        return "bottom"
    return None


def _page_boxes(
    items: list[Any], doc: Any
) -> dict[int, list[tuple[int, tuple[float, float, float, float]]]]:
    """page -> [(id(item), top-left box)] for every provenance of the body items (built once)."""
    out: dict[int, list[tuple[int, tuple[float, float, float, float]]]] = defaultdict(
        list
    )
    for item in items:
        for prov in _provs(item):
            box = _top_left(prov, doc)
            if box is not None:
                out[int(prov.page_no)].append((id(item), box))
    return out


def _outermost(
    item: Any,
    band: str,
    boxes: dict[int, list[tuple[int, tuple[float, float, float, float]]]],
    doc: Any,
) -> bool:
    """Nothing else on the page lies entirely above (top band) / below (bottom band) it.

    A running header is the first thing on its page, a page number the last;
    an item with body text beyond it is not one (e.g. a line under the header).
    """
    prov = _provs(item)[0]
    box = _top_left(prov, doc)
    if box is None:
        return False
    _, t, _, b = box
    for other_id, ob in boxes.get(int(prov.page_no), []):
        if other_id == id(item):
            continue
        if band == "top" and ob[3] <= t:
            return False
        if band == "bottom" and ob[1] >= b:
            return False
    return True


def _area_ratio(item: Any, doc: Any) -> float | None:
    provs = _provs(item)
    if not provs:
        return None
    box = _top_left(provs[0], doc)
    page_no = getattr(provs[0], "page_no", -1)
    height, width = _page_height(doc, page_no), _page_width(doc, page_no)
    if box is None or not height or not width:
        return None
    left, t, r, b = box
    return max(0.0, (r - left)) * max(0.0, (b - t)) / (width * height)


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


def _artifact_candidate(item: Any, doc: Any, T: dict[str, Any]) -> bool:
    label = getattr(item, "label", None)
    L = T["DocItemLabel"]
    return (
        type(item) is T["TextItem"]
        and label in (L.TEXT, L.PAGE_HEADER, L.PAGE_FOOTER)
        and len(_provs(item)) == 1
        and not _inside(item, doc, (T["PictureItem"], T["TableItem"]))
    )


# --------------------------------------------------------------------------- #
# Markdown serialization with original markers
# --------------------------------------------------------------------------- #


def escape_block_start(text: str) -> str:
    """Escape Markdown block syntax at the start of each line, nothing else.

    "9. Dịch vụ" -> "9\\. Dịch vụ": rendered exactly as "9. Dịch vụ" but as a
    paragraph, so no renderer turns it into an ordered list and renumbers it.
    """
    lines = text.split("\n")
    out = []
    for line in lines:
        m = _MD_ORDERED.match(line)
        if m:
            line = f"{m.group(1)}{m.group(2)}\\{m.group(3)}{line[m.end() :]}"
        else:
            for rx in (_MD_BULLET, _MD_HEADING, _MD_QUOTE):
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
                    text=escape_block_start(text), span_source=item
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
                text=escape_block_start(res.text), span_source=item
            )

    class LegalListSerializer(MarkdownListSerializer):
        """Every item is its own paragraph: the marker is text, not list syntax."""

        def serialize(
            self,
            *,
            item: Any,
            doc_serializer: Any,
            doc: Any,
            list_level: int = 0,
            is_inline_scope: bool = False,
            visited: set[str] | None = None,
            **kwargs: Any,
        ) -> SerializationResult:  # type: ignore[override]  # noqa: E501
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

        def _serialize_image_part(
            self,
            item: Any,
            doc: Any,
            image_mode: Any,
            image_placeholder: str,
            **kwargs: Any,
        ) -> SerializationResult:  # type: ignore[override]  # noqa: E501
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
# The normalizer
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


def _find_page_numbers(
    items: list[Any], doc: Any, T: dict[str, Any]
) -> tuple[list[Any], list[dict]]:
    candidates: list[tuple[Any, int, int]] = []  # item, page, offset
    boxes = _page_boxes(items, doc)
    for item in items:
        if not _artifact_candidate(item, doc, T):
            continue
        text = (item.text or "").strip()
        if not text or len(text) > PAGE_NUMBER_MAX_CHARS:
            continue
        if not any(rx.fullmatch(text) for rx in _PAGE_NUMBER_RES):
            continue
        prov = _provs(item)[0]
        band = _band(prov, doc)
        if band is None or not _outermost(item, band, boxes, doc):
            continue
        value = int(_FIRST_INT.search(text).group(0))  # type: ignore[union-attr]
        candidates.append((item, int(prov.page_no), value - int(prov.page_no)))
    by_offset: dict[int, list[tuple[Any, int, int]]] = defaultdict(list)
    for c in candidates:
        by_offset[c[2]].append(c)
    found: list[Any] = []
    warnings: list[dict] = []
    for offset in sorted(by_offset):
        group = by_offset[offset]
        pages = Counter(page for _, page, _ in group)
        if len(pages) < 2:
            continue  # one page is no pattern
        for item, page, _ in group:
            if pages[page] == 1:  # two "page numbers" on one page: not sure, keep
                found.append(item)
    leftover = {id(c[0]) for c in candidates} - {id(i) for i in found}
    if leftover:
        warnings.append(
            {
                "code": "page_number_kept",
                "count": len(leftover),
                "reason": "looks like a page number but no repeated page pattern confirms it",
            }
        )
    return found, warnings


def _repeat_key(text: str) -> str:
    """Exact text up to whitespace and case: digits must repeat too (no masking)."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _find_repeated(
    items: list[Any], doc: Any, T: dict[str, Any], exclude: set[int]
) -> list[Any]:
    n_pages = len(getattr(doc, "pages", None) or {})
    if n_pages < REPEATED_MIN_PAGES:
        return []
    groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
    boxes = _page_boxes(items, doc)
    for item in items:
        if id(item) in exclude or not _artifact_candidate(item, doc, T):
            continue
        text = (item.text or "").strip()
        if not text or len(text) > REPEATED_MAX_CHARS or _STRUCTURE_WORDS.match(text):
            continue
        band = _band(_provs(item)[0], doc)
        if band is None or not _outermost(item, band, boxes, doc):
            continue
        groups[(band, _repeat_key(text))].append(item)
    found: list[Any] = []
    for key in sorted(groups):
        members = groups[key]
        pages = Counter(int(_provs(i)[0].page_no) for i in members)
        if (
            len(pages) >= REPEATED_MIN_PAGES
            and len(pages) >= REPEATED_MIN_SHARE * n_pages
        ):
            found.extend(i for i in members if pages[int(_provs(i)[0].page_no)] == 1)
    return found


def _picture_has_text(pic: Any, doc: Any, T: dict[str, Any]) -> bool:
    for child, _ in doc.iterate_items(
        root=pic, with_groups=False, traverse_pictures=True
    ):
        if child is pic:
            continue
        if isinstance(child, T["TextItem"]) and (child.text or "").strip():
            return True
    return False


def _pure_placeholders(
    items: list[Any], doc: Any, T: dict[str, Any]
) -> tuple[list[Any], list[Any]]:
    """(pictures whose placeholder is dropped, large pictures kept with a warning)."""
    drop, keep = [], []
    for item in items:
        if not isinstance(item, T["PictureItem"]):
            continue
        if _inside(item, doc, (T["TableItem"],)):
            continue  # rich table cell: leave the table exactly as it is
        if getattr(item, "captions", None) or _picture_has_text(item, doc, T):
            drop.append(item)  # its caption / text says more than the placeholder
            continue
        ratio = _area_ratio(item, doc)
        if ratio is not None and ratio < LARGE_PICTURE_RATIO:
            drop.append(item)  # signature, stamp, logo, decoration
        else:
            keep.append(item)
    return drop, keep


def _starts_continuation(text: str) -> bool:
    stripped = text.lstrip()
    if not stripped:
        return False
    first = stripped[0]
    if not (first.isalpha() and first.islower()):
        return False
    return not _STRUCTURE_START.match(stripped)


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


def _join_allowed(
    a: Any, b: Any, between: list[Any], doc: Any, T: dict[str, Any]
) -> tuple[bool, str]:
    if not (_is_plain_text(a, T) or isinstance(a, T["ListItem"])):
        return False, "first part is not a paragraph or list item"
    b_ok = _is_plain_text(b, T) or (
        isinstance(b, T["ListItem"])
        and isinstance(a, T["ListItem"])
        and not (b.marker or "").strip()
    )
    if not b_ok:
        return False, "second part is not a plain paragraph"
    kinds = (T["PictureItem"], T["TableItem"])
    if _inside(a, doc, kinds) or _inside(b, doc, kinds):
        return False, "inside a picture or table"
    pa, pb = _provs(a), _provs(b)
    if not pa or not pb:
        return False, "no provenance"
    last_a, first_b = pa[-1], pb[0]
    if int(first_b.page_no) != int(last_a.page_no) + 1:
        return False, "not on consecutive pages"
    pages = {int(last_a.page_no), int(first_b.page_no)}
    for x in between:
        if any(int(p.page_no) not in pages for p in _provs(x)):
            return False, "artifact outside the two pages"
    box_a, box_b = _top_left(last_a, doc), _top_left(first_b, doc)
    ha, hb = (
        _page_height(doc, int(last_a.page_no)),
        _page_height(doc, int(first_b.page_no)),
    )
    if box_a is None or box_b is None or not ha or not hb:
        return False, "no bounding box / page size"
    if box_a[3] < JOIN_LOWER_HALF * ha:
        return False, "first part does not end in the lower half of its page"
    if box_b[1] > JOIN_UPPER_HALF * hb:
        return False, "second part does not start in the upper half of its page"
    is_open, why = _ends_open(a.text or "")
    if not is_open:
        return False, f"first part ends with a {why} character"
    if not _starts_continuation(b.text or ""):
        return False, "second part does not start a lowercase continuation"
    return True, "unfinished paragraph continues on the next page"


def normalize_document(doc: Any, *, include_text: bool = False) -> NormalizationResult:
    """Normalize a COPY of ``doc``; ``doc`` itself is never modified."""
    started = time.perf_counter()
    _check_limits(doc)
    from docling_core.types.doc.document import ContentLayer, ListGroup

    T = _types()
    work = doc.model_copy(deep=True)
    ops: list[Operation] = []
    warnings: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    def record(
        op: str, reason: str, items: Iterable[Any], before: str = "", after: str = ""
    ) -> None:
        items = list(items)
        provs = [p for i in items for p in _provs(i)]
        ops.append(
            Operation(
                op=op,
                reason=reason,
                pages=sorted({int(p.page_no) for p in provs}),
                refs=[str(getattr(i, "self_ref", "")) for i in items],
                bboxes=[b for b in (_bbox_list(p, work) for p in provs) if b],
                chars_before=len(before),
                chars_after=len(after),
                text_before=before if include_text else None,
                text_after=after if include_text else None,
            )
        )
        counts[op] += 1

    items = _body_items(work)

    # 1-2. Page artifacts the layout model left in the body.
    page_numbers, pn_warnings = _find_page_numbers(items, work, T)
    warnings.extend(pn_warnings)
    repeated = _find_repeated(items, work, T, {id(i) for i in page_numbers})
    artifacts = {id(i) for i in page_numbers} | {id(i) for i in repeated}

    # 3. Pictures.
    drop_pictures, kept_pictures = _pure_placeholders(items, work, T)
    silent = {
        id(p)
        for p in drop_pictures
        if not p.captions and not _picture_has_text(p, work, T)
    }

    # 4. Cross-page joins (skipping only removed artifacts / silent pictures).
    real = [i for i in items if id(i) not in artifacts and id(i) not in silent]
    position = {id(i): n for n, i in enumerate(items)}
    to_delete: list[Any] = []
    idx = 0
    while idx < len(real) - 1:
        a, b = real[idx], real[idx + 1]
        between = items[position[id(a)] + 1 : position[id(b)]]
        ok, reason = _join_allowed(a, b, between, work, T)
        if not ok:
            if reason.endswith("hyphen character") and _starts_continuation(
                b.text or ""
            ):
                warnings.append(
                    {
                        "code": "hyphen_at_page_break_not_joined",
                        "pages": sorted(
                            {int(p.page_no) for p in _provs(a)[-1:] + _provs(b)[:1]}
                        ),
                    }
                )
            idx += 1
            continue
        before = f"{a.text}\n\n{b.text}"
        a.text = f"{(a.text or '').rstrip()} {(b.text or '').lstrip()}"
        a.orig = f"{(a.orig or '').rstrip()} {(b.orig or '').lstrip()}"
        a.prov.extend(b.prov)
        record("join_across_pages", reason, [a], before, a.text)
        to_delete.append(b)
        real.pop(idx + 1)  # a may continue again on the following page

    for item in page_numbers:
        record(
            "page_number_to_furniture",
            "page-number shape, page band, repeated page offset",
            [item],
            item.text,
            "",
        )
        item.content_layer = ContentLayer.FURNITURE
    for item in repeated:
        record(
            "running_header_footer_to_furniture",
            "same short line in the same page band on most pages",
            [item],
            item.text,
            "",
        )
        item.content_layer = ContentLayer.FURNITURE
    if to_delete:
        work.delete_items(node_items=to_delete)

    # Pictures, after deletions (refs are renumbered by delete_items).
    for pic in drop_pictures:
        reason = (
            "caption kept"
            if pic.captions
            else "OCR text kept"
            if _picture_has_text(pic, work, T)
            else "small picture without text (signature / stamp / logo)"
        )
        record("image_placeholder_dropped", reason, [pic])
    for pic in kept_pictures:
        warnings.append(
            {
                "code": "picture_without_text",
                "pages": sorted({int(p.page_no) for p in _provs(pic)}),
                "reason": "large picture with no caption and no OCR text: it may contain information that was not extracted",
            }
        )
        counts["image_placeholder_kept"] += 1
    counts["picture_text_items"] = sum(
        1
        for it in _body_items(work)
        if isinstance(it, T["TextItem"])
        and _inside(it, work, (T["PictureItem"],))
        and (it.text or "").strip()
    )

    # 5. List markers (counted here, written by the serializer).
    for item in _body_items(work):
        if not isinstance(item, T["ListItem"]):
            continue
        if (item.marker or "").strip():
            counts["list_markers_preserved"] += 1
        else:
            group = _parent(item, work)
            if isinstance(group, ListGroup) and group.first_item_is_enumerated(work):
                counts["synthesized_number_avoided"] += 1

    serializer = _build_serializer(work, {p.self_ref for p in drop_pictures})
    content = serializer.serialize().text
    return NormalizationResult(
        content=content,
        operations=ops,
        warnings=warnings,
        counts=dict(counts),
        elapsed_ms=(time.perf_counter() - started) * 1000,
        document=work,
    )


def normalize_or_fallback(
    doc: Any, standard: str | None = None
) -> tuple[str, dict[str, Any]]:
    """Legal content + metadata, or the standard export when normalization fails.

    Never raises for a normalization problem: the extraction result must not be
    lost because of it. The metadata says which content was produced.
    """
    from loguru import logger

    try:
        result = normalize_document(doc)
    except Exception as e:  # noqa: BLE001 - any failure -> the standard export
        content = standard if standard is not None else doc.export_to_markdown()
        logger.warning(
            f"Legal document normalization {NORMALIZER_VERSION} failed "
            f"({type(e).__name__}); the standard Docling export is kept."
        )
        return content, {
            "text_normalization": MODE_LEGAL,
            "legal_normalization_status": "failed",
            "legal_normalization_error": type(e).__name__,
            "legal_normalizer_version": NORMALIZER_VERSION,
        }
    if not result.content.strip() and (standard or "").strip():
        # Defensive: never replace text by nothing.
        logger.warning(
            "Legal document normalization produced no text; the standard export is kept."
        )
        return standard or "", {
            "text_normalization": MODE_LEGAL,
            "legal_normalization_status": "failed",
            "legal_normalization_error": "EmptyResult",
            "legal_normalizer_version": NORMALIZER_VERSION,
        }
    meta = {
        "text_normalization": MODE_LEGAL,
        "legal_normalization_status": "applied",
        **result.summary(),
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
