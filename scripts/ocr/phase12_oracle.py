"""Phase 12D5 preservation oracle: declared ground truth, matched by SOURCE IDENTITY.

Findings R2-14, T-01 and T-03 of the Phase 12D4 re-review: the Phase 12D3 oracle
matched what the reader sees against the declared truth by TEXT only, so a page
number "2" that stayed in the output stood in for a clause number "2" that the
normalizer deleted; lines moved across artifacts or placeholders changed no
counter; ``<!-- image -->`` lines and ``gt="furniture"`` content were never
measured; order was only asserted "Legal <= Standard".

GROUND TRUTH is what a fixture declares for each element, written with the
fixture and before any implementation runs (tests/fixtures/legal/):

  (no ``gt``) / ``"keep"``  REQUIRED: shown, exactly this text, once per declared
                          element, in the declared order
  ``"artifact"``          page number / running header the layout model
                          labelled TEXT: may be removed; if kept, it must stay
                          where it was (it takes part in the order check)
  ``"join"``              continuation of the previous required element: may be
                          joined to it with ONE space, or kept apart
  ``"furniture"``         labelled PAGE_HEADER / PAGE_FOOTER and NOT business
                          content (a page number, a running title): may be absent
  pictures                REQUIRED trace by default: the ``<!-- image -->``
                          placeholder must be shown (the picture may hold a table,
                          a chart, a scanned paragraph nobody extracted);
                          ``gt="decoration"`` (signature, stamp, logo) may lose it
  table rows, OCR text Docling placed inside a picture: REQUIRED

Business content the layout model put in the furniture layer (a document
number, the issuer on page 1, a footnote labelled footer) is declared REQUIRED:
if it is missing that is a deletion, whoever caused it (finding R2-11).

ATTRIBUTION. With ``document`` (the DoclingDocument the output was serialized
from) every declared element is located by its provenance - page and bounding
box, which the fixture declared and Docling copied - so each displayed line is
attributed to the element that produced it; the displayed lines are then
reconciled with the body items (occurrence by occurrence, in order) so that a
serializer cannot hide an item the document still claims. Without ``document``
(lines only) a line whose text is shared by a required unit and an optional
unit (artifact / furniture / decoration) is attributed to the OPTIONAL unit
first: an aliased deletion is never reported as 0 (``attribution="text"``,
worst case; false alarms are possible, misses are not).

Nothing the normalizer reports about itself (operations, counts, warnings) is
used for a verdict. Standard library + docling-core types only (no network,
no file access).
"""

from __future__ import annotations

import bisect
import re
from collections import Counter, defaultdict
from typing import Any, Iterable

PLACEHOLDER = "<!-- image -->"
REQUIRED_GT = ("keep", "join")
OPTIONAL_GT = ("artifact", "furniture", "decoration")
_DRAWN_PREFIX = re.compile(r"^(?:• |\d{1,9}\. )")
# A marker printed in the source text ("- ", "+ ", "9. ", "10) ") that a
# Markdown renderer may draw differently (bullet, renumbered list).
_SOURCE_MARKER = re.compile(r"^(?:[-+*•]|\d{1,9}[.)])\s+")
_HYPHENS = ("-", "­")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


# --------------------------------------------------------------------------- #
# The declared truth
# --------------------------------------------------------------------------- #


def expected_units(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    """Every declared unit, in declared reading order (never from an output).

    ``{"id", "index", "page", "element", "kind", "label", "text", "gt", "bbox"}``
    with kind text / table_row / picture / picture_text. A picture is one unit
    whose text is the placeholder; each table row is one unit "a | b | c" (how
    a rendered table row reads).
    """
    units: list[dict[str, Any]] = []
    for page_no, page in enumerate(fixture["pages"], start=1):
        for k, el in enumerate(page):
            base = {"page": page_no, "element": k, "label": el["label"]}
            if el["label"] == "picture":
                units.append(
                    {
                        **base,
                        "id": f"p{page_no}e{k}",
                        "kind": "picture",
                        "text": PLACEHOLDER,
                        "gt": el.get("gt") or "keep",
                        "bbox": list(el["bbox"]),
                    }
                )
                for c, child in enumerate(el.get("children", [])):
                    units.append(
                        {
                            **base,
                            "id": f"p{page_no}e{k}c{c}",
                            "kind": "picture_text",
                            "label": child["label"],
                            "text": child["text"],
                            "gt": child.get("gt") or "keep",
                            "bbox": list(child["bbox"]),
                        }
                    )
            elif el["label"] == "table":
                for r, row in enumerate(el["rows"]):
                    units.append(
                        {
                            **base,
                            "id": f"p{page_no}e{k}r{r}",
                            "kind": "table_row",
                            "text": " | ".join(row),
                            "gt": "keep",
                            "bbox": list(el["bbox"]),
                            "row": r,
                        }
                    )
            elif el.get("text"):
                units.append(
                    {
                        **base,
                        "id": f"p{page_no}e{k}",
                        "kind": "text",
                        "text": el["text"],
                        "gt": el.get("gt") or "keep",
                        "bbox": list(el["bbox"]),
                    }
                )
    for i, u in enumerate(units):
        u["index"] = i
    return units


def _required(u: dict[str, Any]) -> bool:
    return u["gt"] in REQUIRED_GT


def _predecessors(units: list[dict[str, Any]]) -> dict[str, str]:
    """join unit id -> id of the unit it may be joined to (the previous text unit
    that is required, skipping artifacts / furniture / pictures in between)."""
    out: dict[str, str] = {}
    last: str | None = None
    for u in units:
        if u["kind"] != "text":
            continue
        if u["gt"] == "join" and last is not None:
            out[u["id"]] = last
        if _required(u):
            last = u["id"]
    return out


def _lis_length(seq: list[int]) -> int:
    tails: list[int] = []
    for x in seq:
        i = bisect.bisect_left(tails, x)
        if i == len(tails):
            tails.append(x)
        else:
            tails[i] = x
    return len(tails)


def _joined_forms(texts: list[str], dehyphenate: bool = True) -> set[str]:
    """How Docling or the normalizer may render consecutive parts in ONE item:
    one space between them; the parts closed up with the hyphen KEPT (the
    Phase 12D9 Docling patch, D8-03: "phi-" + "ngân" -> "phi-ngân"); or, with
    ``dehyphenate``, upstream Docling's de-hyphenation (trailing '-' / soft
    hyphen removed before a lowercase continuation). Returned normalized."""
    forms = {texts[0]}
    for t in texts[1:]:
        nxt: set[str] = set()
        for f in forms:
            nxt.add(f.rstrip() + " " + t.lstrip())
            stripped = t.lstrip()
            if f.endswith("-") and stripped[:1].islower():
                nxt.add(f + stripped)  # hyphen kept: no character lost
            if dehyphenate and f.endswith(_HYPHENS) and stripped[:1].islower():
                nxt.add(f[:-1] + stripped)
        forms = nxt
    return {_norm(f) for f in forms}


def _space_joined(texts: list[str]) -> str:
    return _norm(" ".join(t.strip() for t in texts))


# --------------------------------------------------------------------------- #
# Identity: where each declared unit is in the output document
# --------------------------------------------------------------------------- #


def _box_key(page: int, box: Iterable[float]) -> tuple[int, tuple[float, ...]]:
    return page, tuple(round(float(v), 1) for v in box)


class _DocView:
    """The output DoclingDocument seen through provenance (page + top-left box)."""

    def __init__(self, document: Any, pictures_traversed: bool) -> None:
        from docling_core.types.doc.document import (
            ContentLayer,
            ListItem,
            PictureItem,
            TableItem,
            TextItem,
        )

        self.T = {
            "ListItem": ListItem,
            "PictureItem": PictureItem,
            "TableItem": TableItem,
            "TextItem": TextItem,
        }
        self.BODY = ContentLayer.BODY
        self.doc = document
        self.heights = {
            int(k): float(p.size.height) for k, p in (document.pages or {}).items()
        }
        self.by_box: dict[tuple[int, tuple[float, ...]], list[tuple[Any, int]]] = (
            defaultdict(list)
        )
        for item, _ in document.iterate_items(
            with_groups=False,
            traverse_pictures=True,
            included_content_layers=set(ContentLayer),
        ):
            for i, prov in enumerate(getattr(item, "prov", None) or []):
                h = self.heights.get(int(prov.page_no))
                if h is None:
                    continue
                b = prov.bbox.to_top_left_origin(page_height=h)
                box = (min(b.l, b.r), min(b.t, b.b), max(b.l, b.r), max(b.t, b.b))
                self.by_box[_box_key(int(prov.page_no), box)].append((item, i))
        # what the serializer can show: body items, in document order
        self.entries: list[dict[str, Any]] = []
        for item, _ in document.iterate_items(
            with_groups=False,
            traverse_pictures=pictures_traversed,
            included_content_layers={ContentLayer.BODY},
        ):
            if isinstance(item, PictureItem):
                if not pictures_traversed:
                    # the picture serializer prints the captions of a picture
                    for ref in item.captions or []:
                        cap = ref.resolve(document)
                        if getattr(cap, "text", "").strip():
                            self._text_entry(cap)
                self.entries.append(
                    {"item": item, "row": None, "keys": [PLACEHOLDER], "plain": None}
                )
            elif isinstance(item, TableItem):
                for r, row in enumerate(item.data.grid if item.data else []):
                    self.entries.append(
                        {
                            "item": item,
                            "row": r,
                            "keys": [_norm(" | ".join(c.text for c in row))],
                            "plain": None,
                        }
                    )
            elif isinstance(item, TextItem):
                if (item.text or "").strip():
                    self._text_entry(item)

    def _text_entry(self, item: Any) -> None:
        text = _norm(item.text)
        marker = _norm(getattr(item, "marker", "") or "")
        full = _norm(f"{marker} {text}") if marker else text
        self.entries.append(
            {
                "item": item,
                "row": None,
                "keys": [full],
                "plain": text if marker else None,
            }
        )

    def full_text(self, item: Any) -> str:
        marker = _norm(getattr(item, "marker", "") or "")
        text = _norm(getattr(item, "text", "") or "")
        return _norm(f"{marker} {text}") if marker else text

    def holders(self, unit: dict[str, Any]) -> list[tuple[Any, int]]:
        found = self.by_box.get(_box_key(unit["page"], unit["bbox"]), [])
        kind = self.T["PictureItem"] if unit["kind"] == "picture" else None
        if unit["kind"] == "table_row":
            kind = self.T["TableItem"]
        if kind is not None:
            return [(i, n) for i, n in found if isinstance(i, kind)]
        return [
            (i, n)
            for i, n in found
            if isinstance(i, self.T["TextItem"])
            and not isinstance(i, (self.T["PictureItem"], self.T["TableItem"]))
        ]


# --------------------------------------------------------------------------- #
# The oracle
# --------------------------------------------------------------------------- #


def preservation(
    fixture: dict[str, Any],
    lines: list[str],
    markdown: str = "",
    *,
    document: Any = None,
    pictures_traversed: bool = True,
) -> dict[str, Any]:
    """Compare what the reader sees (``lines``) with the fixture's declared truth.

    ``document``: the DoclingDocument ``lines`` were rendered from (the Legal
    result document, or the input document for the Standard export) - enables
    identity attribution. ``pictures_traversed``: whether the output serialized
    the OCR text inside pictures (Legal: yes; Docling's standard export: no).
    """
    units = expected_units(fixture)
    if document is not None:
        verdict = _identity_verdict(units, lines, document, pictures_traversed)
    else:
        verdict = _text_verdict(units, lines)
    return _metrics(fixture, units, lines, markdown, verdict)


def _identity_verdict(
    units: list[dict[str, Any]],
    lines: list[str],
    document: Any,
    pictures_traversed: bool,
) -> dict[str, Any]:
    view = _DocView(document, pictures_traversed)
    preds = _predecessors(units)
    # 1. where is every unit in the document?
    carrier: dict[str, Any] = {}  # unit id -> body item holding it
    located: dict[str, bool] = {}
    for u in units:
        holders = view.holders(u)
        located[u["id"]] = bool(holders)
        body = [
            (i, n) for i, n in holders if getattr(i, "content_layer", None) == view.BODY
        ]
        if body:
            carrier[u["id"]] = body[0][0]
    by_item: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for u in units:
        item = carrier.get(u["id"])
        if item is not None:
            by_item[id(item)].append(u)

    # 2. which body entries does the reader actually see? (occurrence by occurrence)
    line_keys = [_norm(x) for x in lines]
    used_line = [False] * len(lines)
    entry_line: dict[int, int] = {}  # entry index -> line index

    def required_first(e: dict[str, Any]) -> int:
        holders = by_item.get(id(e["item"]), [])
        return 0 if any(_required(u) for u in holders) else 1

    # Matching passes, strictest first: the line as shown; without the list
    # number / bullet the renderer drew; then forms where only the MARKER differs
    # (a list item shown without its marker, a literal "- " / "9. " the renderer
    # turned into a drawn bullet / number): those count as a changed marker.
    def drawn(ln: str) -> str:
        return _DRAWN_PREFIX.sub("", ln, count=1)

    def unmarked(text: str | None) -> str | None:
        if not text:
            return None
        out = _SOURCE_MARKER.sub("", text, count=1)
        return out if out != text else None

    passes = [
        (lambda e: e["keys"][0], lambda ln: ln, False),
        (lambda e: e["keys"][0], drawn, False),
        (lambda e: e["plain"], lambda ln: ln, True),
        (lambda e: e["plain"], drawn, True),
        (lambda e: unmarked(e["keys"][0]), drawn, True),
    ]
    marker_lost: list[str] = []
    for entry_key, line_shape, changes_marker in passes:
        want: dict[str, list[int]] = defaultdict(list)
        for ei, e in enumerate(view.entries):
            if ei in entry_line:
                continue
            key = entry_key(e)
            if key:
                want[key].append(ei)
        for li, ln in enumerate(line_keys):
            if used_line[li]:
                continue
            cands = want.get(line_shape(ln))
            if cands:
                ei = cands.pop(0)
                entry_line[ei] = li
                used_line[li] = True
                if changes_marker:
                    marker_lost.append(lines[li])
    # When several body entries share a text and fewer lines show it (the
    # serializer showed only some of them - e.g. identical picture placeholders),
    # each such line is attributed WITHIN the window of its nearest lines of
    # other texts: the serializer emits body items in document order, so a line
    # between the lines of entries i and j comes from an entry between i and j.
    # Inside a window that still holds several candidates, the OPTIONAL entries
    # (artifact, furniture, decoration) take the lines first: the required
    # entries left without a line are the deleted ones (worst case).
    by_key: dict[str, list[int]] = defaultdict(list)
    for ei, e in enumerate(view.entries):
        by_key[e["keys"][0]].append(ei)
    ambiguous_keys = {
        key
        for key, eis in by_key.items()
        if 0 < sum(1 for ei in eis if ei in entry_line) < len(eis)
    }
    if ambiguous_keys:
        fixed = {
            li: ei
            for ei, li in entry_line.items()
            if view.entries[ei]["keys"][0] not in ambiguous_keys
        }
        fixed_lines = sorted(fixed)
        for key in sorted(ambiguous_keys):
            eis = by_key[key]
            lines_for_key = sorted(entry_line[ei] for ei in eis if ei in entry_line)
            for ei in eis:
                entry_line.pop(ei, None)
            taken: set[int] = set()
            for li in lines_for_key:
                k = bisect.bisect_left(fixed_lines, li)
                lo = fixed[fixed_lines[k - 1]] if k > 0 else -1
                hi = (
                    fixed[fixed_lines[k]] if k < len(fixed_lines) else len(view.entries)
                )
                window = [ei for ei in eis if lo < ei < hi and ei not in taken]
                pool = window or [ei for ei in eis if ei not in taken]
                if not pool:
                    continue
                pick = sorted(
                    pool, key=lambda ei: (required_first(view.entries[ei]) == 0, ei)
                )[0]
                taken.add(pick)
                entry_line[pick] = li
    shown_entries = set(entry_line)

    # 3. units shown, in display order
    sequence: list[tuple[int, dict[str, Any]]] = []  # (line index, unit)
    shown: set[str] = set()
    for ei, li in entry_line.items():
        entry = view.entries[ei]
        item_units: list[dict[str, Any]] = by_item.get(id(entry["item"]), [])
        if entry["row"] is not None:
            item_units = [x for x in item_units if x.get("row") == entry["row"]]
        elif isinstance(entry["item"], view.T["PictureItem"]):
            item_units = [x for x in item_units if x["kind"] == "picture"]
        # several units of ONE item (a join / a merge) appear in provenance order
        rank_item = entry["item"]
        for unit in sorted(item_units, key=lambda x: _prov_rank(view, x, rank_item)):
            sequence.append((li, unit))
            shown.add(unit["id"])
    sequence.sort(key=lambda x: (x[0], x[1]["index"]))

    # 4. merges and changed text inside one item
    false_merges: list[str] = []
    altered: list[dict[str, Any]] = []
    joined_pairs: set[tuple[str, str]] = set()
    for item_id, group in by_item.items():
        texts_units = [u for u in group if u["kind"] in ("text", "picture_text")]
        if len(texts_units) < 1:
            continue
        item = carrier[texts_units[0]["id"]]
        ordered = sorted(texts_units, key=lambda u: _prov_rank(view, u, item))
        full = view.full_text(item)
        if len(ordered) >= 2:
            bad = False
            for a, b in zip(ordered, ordered[1:]):
                if preds.get(b["id"]) == a["id"]:
                    joined_pairs.add((a["id"], b["id"]))
                else:
                    bad = True
            if bad:
                false_merges.append(full)
        forms = _joined_forms([u["text"] for u in ordered])
        if full not in forms:
            altered.append(
                {
                    "units": [u["id"] for u in ordered],
                    "pages": sorted({u["page"] for u in ordered}),
                    "expected": _space_joined([u["text"] for u in ordered]),
                    "found": full,
                    "why": "text changed inside the item",
                }
            )
        elif len(ordered) >= 2 and full not in _joined_forms(
            [u["text"] for u in ordered], dehyphenate=False
        ):
            altered.append(
                {
                    "units": [u["id"] for u in ordered],
                    "pages": sorted({u["page"] for u in ordered}),
                    "expected": _space_joined([u["text"] for u in ordered]),
                    "found": full,
                    "why": "de-hyphenated (a hyphen was removed at the break)",
                }
            )

    # 5. lines nobody accounts for: a line made of two or more declared texts is a
    # merge (whatever their length - "2" + "Khách hàng ..." too), anything else is
    # an insertion
    texts = {_norm(u["text"]) for u in units}
    inserted: list[str] = []
    merged_lines: list[str] = []
    matched_lines = set(entry_line.values())
    for li, ln in enumerate(lines):
        if li in matched_lines:
            continue
        if _parts(_norm(ln), texts) >= 2:
            merged_lines.append(ln)
        else:
            inserted.append(ln)
    hidden_body = [
        view.entries[ei] for ei in range(len(view.entries)) if ei not in shown_entries
    ]
    return {
        "attribution": "identity",
        "shown": shown,
        "sequence": [u for _, u in sequence],
        "joined_pairs": joined_pairs,
        "false_merges": false_merges + merged_lines,
        "inserted": inserted,
        "altered": altered,
        "marker_lost": marker_lost,
        "not_located": [u["id"] for u in units if not located[u["id"]]],
        "hidden_body_items": len(hidden_body),
        "ambiguous": [],
    }


def _parts(line: str, texts: set[str]) -> int:
    """Largest number of declared texts the line is made of, joined by one space
    or by Docling's de-hyphenation (0 when it is not made of declared texts)."""
    from functools import lru_cache

    by_first: dict[str, list[str]] = defaultdict(list)
    for t in texts:
        if t:
            by_first[t[0]].append(t)

    @lru_cache(maxsize=None)
    def best(i: int) -> int:
        if i == len(line):
            return 0
        out = -1
        for t in by_first.get(line[i], []):
            if not line.startswith(t, i):
                continue
            j = i + len(t)
            if j == len(line):
                out = max(out, 1)
            elif line[j] == " ":
                rest = best(j + 1)
                if rest > 0:
                    out = max(out, 1 + rest)
            elif t.endswith("-") and line[j].islower():
                # the Phase 12D9 Docling join: hyphen kept, the parts close up
                rest = best(j)
                if rest > 0:
                    out = max(out, 1 + rest)
        # Docling's de-hyphenation: "...phi" + "ngân" written as "phingân"
        for t in by_first.get(line[i], []):
            if t.endswith(_HYPHENS) and line.startswith(t[:-1], i):
                rest = best(i + len(t) - 1)
                if rest > 0:
                    out = max(out, 1 + rest)
        return out

    found = best(0)
    return found if found > 0 else 0


def _prov_rank(view: _DocView, unit: dict[str, Any], item: Any) -> int:
    """Position of the unit's provenance inside ``item`` (order of the parts)."""
    for holder, n in view.holders(unit):
        if holder is item:
            return n
    return 10**6


def _text_verdict(units: list[dict[str, Any]], lines: list[str]) -> dict[str, Any]:
    """Lines only: worst-case attribution of aliased lines (see module docstring).

    WHICH units are shown is decided pessimistically: when fewer lines show a
    text than units declare it, the optional units (artifact, furniture,
    decoration) take those lines first and the required ones are missing. WHERE
    a shown unit is, is then decided in declared order (the k-th shown unit with
    a text takes the k-th line with that text), so identical texts never create
    a reordering by themselves.
    """
    preds = _predecessors(units)
    positions: dict[str, list[int]] = defaultdict(list)
    for i, ln in enumerate(lines):
        positions[_norm(ln)].append(i)
    avail = {t: len(v) for t, v in positions.items()}
    optional = [u for u in units if u["gt"] in OPTIONAL_GT]
    required_texts = Counter(_norm(u["text"]) for u in units if _required(u))
    ambiguous = sorted({_norm(u["text"]) for u in optional} & set(required_texts))
    shown_optional: set[str] = set()
    for u in optional:  # declared order; worst case: they take the lines first
        t = _norm(u["text"])
        if avail.get(t, 0) > 0:
            avail[t] -= 1
            shown_optional.add(u["id"])
    runs: list[list[dict[str, Any]]] = []
    for u in units:
        if not _required(u):
            continue
        if u["gt"] == "join" and runs and preds.get(u["id"]) == runs[-1][-1]["id"]:
            runs[-1].append(u)
        else:
            runs.append([u])
    # (form text, units shown in it) for every required group that is shown
    groups_shown: list[tuple[str, list[dict[str, Any]]]] = []
    joined_pairs: set[tuple[str, str]] = set()
    for run in runs:
        texts = [u["text"] for u in run]
        placed = False
        for groups in _partitions(list(range(len(run)))):
            forms = [_space_joined([texts[i] for i in g]) for g in groups]
            need = Counter(forms)
            if all(avail.get(f, 0) >= c for f, c in need.items()):
                for g, f in zip(groups, forms):
                    avail[f] -= 1
                    groups_shown.append((f, [run[i] for i in g]))
                    for a, b in zip(g, g[1:]):
                        joined_pairs.add((run[a]["id"], run[b]["id"]))
                placed = True
                break
        if not placed:
            for u in run:
                t = _norm(u["text"])
                if avail.get(t, 0) > 0:
                    avail[t] -= 1
                    groups_shown.append((t, [u]))
    # positions, in declared order per text
    by_text: dict[str, list[tuple[int, list[dict[str, Any]]]]] = defaultdict(list)
    for f, members in groups_shown:
        by_text[f].append((members[0]["index"], members))
    for u in optional:
        if u["id"] in shown_optional:
            by_text[_norm(u["text"])].append((u["index"], [u]))
    placed_units: list[tuple[int, int, dict[str, Any]]] = []
    used: set[int] = set()
    for f, entries in by_text.items():
        for (_, members), li in zip(
            sorted(entries, key=lambda x: x[0]), positions.get(f, [])
        ):
            used.add(li)
            for u in members:
                placed_units.append((li, u["index"], u))
    texts_all = {_norm(u["text"]) for u in units}
    inserted, merged_lines = [], []
    for i, ln in enumerate(lines):
        if i in used:
            continue
        t = _norm(ln)
        if _parts(t, texts_all) >= 2:
            merged_lines.append(t)
        else:
            inserted.append(t)
    placed_units.sort(key=lambda x: (x[0], x[1]))
    return {
        "attribution": "text",
        "shown": {u["id"] for _, _, u in placed_units},
        "sequence": [u for _, _, u in placed_units],
        "joined_pairs": joined_pairs,
        "false_merges": merged_lines,
        "inserted": inserted,
        "altered": [],
        "marker_lost": [],
        "not_located": [],
        "hidden_body_items": 0,
        "ambiguous": ambiguous,
    }


def _partitions(idx: list[int]) -> list[list[list[int]]]:
    """Every way to keep a run [keep, join, join...] together or apart, most
    joined first (runs are short: a paragraph and its continuations)."""
    n = len(idx)
    out = []
    for mask in range(1 << max(0, n - 1)):
        groups, cur = [], [idx[0]]
        for i in range(n - 1):
            if mask >> i & 1:
                groups.append(cur)
                cur = [idx[i + 1]]
            else:
                cur.append(idx[i + 1])
        groups.append(cur)
        out.append(groups)
    return sorted(out, key=len)


def _metrics(
    fixture: dict[str, Any],
    units: list[dict[str, Any]],
    lines: list[str],
    markdown: str,
    v: dict[str, Any],
) -> dict[str, Any]:
    shown = v["shown"]
    required = [u for u in units if _required(u) and u["kind"] != "picture"]
    missing = [u for u in required if u["id"] not in shown]
    pictures = [u for u in units if u["kind"] == "picture"]
    trace_required = [u for u in pictures if u["gt"] != "decoration"]
    lost_traces = [u for u in trace_required if u["id"] not in shown]
    artifacts = [u for u in units if u["gt"] == "artifact"]
    furniture = [u for u in units if u["gt"] == "furniture"]
    joins = [u for u in units if u["gt"] == "join"]
    preds = _predecessors(units)
    joins_made = sum(
        1 for u in joins if (preds.get(u["id"]), u["id"]) in v["joined_pairs"]
    )
    # decoration (signature / stamp / logo) has no reading position of its own
    order = [u["index"] for u in v["sequence"] if u["gt"] != "decoration"]
    required_tokens: Counter[str] = Counter()
    for u in required:
        required_tokens.update(u["text"].replace(" | ", " ").split())
    optional_tokens: Counter[str] = Counter()
    for u in units:
        if not _required(u) and u["kind"] != "picture":
            optional_tokens.update(u["text"].split())
    shown_tokens: Counter[str] = Counter()
    for ln in lines:
        if _norm(ln) != PLACEHOLDER:
            shown_tokens.update(ln.replace(" | ", " ").split())
    text = " ".join(lines)
    critical = []
    for entry in fixture.get("protected", []):
        value, count = (
            (entry, 1) if isinstance(entry, str) else (entry[0], int(entry[1]))
        )
        found = max(text.count(value), markdown.count(value))
        critical.append(
            {"value": value, "expected": count, "found": found, "ok": found >= count}
        )
    table_units = [u for u in units if u["kind"] == "table_row"]
    return {
        "attribution": v["attribution"],
        "required_units": len(required),
        "false_deletion": len(missing),
        "false_deletion_units": [u["text"] for u in missing],
        "false_deletion_ids": [u["id"] for u in missing],
        "false_deletion_tokens": sum((required_tokens - shown_tokens).values()),
        "false_merge": len(v["false_merges"]),
        "false_merge_lines": v["false_merges"],
        "false_insertion": len(v["inserted"]),
        "false_insertion_lines": v["inserted"],
        "false_insertion_tokens": sum(
            ((shown_tokens - required_tokens) - optional_tokens).values()
        ),
        "false_reordering": len(order) - _lis_length(order),
        "altered": v["altered"],
        "altered_units": len(v["altered"]),
        # a list marker shown differently from the source (lost, renumbered by the
        # renderer, changed): the reader sees another clause number - an error
        "marker_lost": v["marker_lost"],
        "marker_changed": len(v["marker_lost"]),
        "not_located": v["not_located"],
        "hidden_body_items": v["hidden_body_items"],
        "ambiguous": v["ambiguous"],
        "artifacts_declared": len(artifacts),
        "artifacts_left": sum(1 for u in artifacts if u["id"] in shown),
        "furniture_declared": len(furniture),
        "furniture_shown": sum(1 for u in furniture if u["id"] in shown),
        "pictures_declared": len(pictures),
        "placeholders_required": len(trace_required),
        "placeholders_lost": len(lost_traces),
        "placeholders_lost_ids": [u["id"] for u in lost_traces],
        "placeholders": sum(1 for ln in lines if _norm(ln) == PLACEHOLDER),
        "joins_allowed": len(joins),
        "joins_made": joins_made,
        "joins_missed": len(joins) - joins_made,
        "critical_fields": critical,
        "critical_ok": all(c["ok"] for c in critical),
        "table_rows": len(table_units),
        "tables_ok": all(u["id"] in shown for u in table_units),
    }


def faithful_lines(document: Any, pictures_traversed: bool = True) -> list[str]:
    """What a serializer that shows exactly the document's body would display
    (one line per text item / table row / picture placeholder, document order).

    For the oracle's own tests only: a clean base on which damage is injected
    (tests/test_phase12d5_oracle.py). Never used for a verdict.
    """
    return [e["keys"][0] for e in _DocView(document, pictures_traversed).entries]
