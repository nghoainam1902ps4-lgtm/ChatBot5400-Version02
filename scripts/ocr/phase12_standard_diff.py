#!/usr/bin/env python3
"""Standard expected-diff gate: every difference to v1.2.0 explained, or the run fails.

Phase 12D7 introduced this gate for the Docling TSV fix (E0-07); Phase 12D9
rebuilt it after the 12D8 review (D8-STD-01..05) and the Windows evidence of
Phase 12E2 (E2-03: one hunk can mix several causes).

Inputs: ``--before`` = v1.2.0 Standard outputs, ``--after`` = the candidate's,
one ``<name>.md`` per document on each side, and the EVIDENCE of the candidate's
own conversion of each document:

* ``--after/manifest.json`` + ``--after/<name>.evidence/`` written by
  ``scripts/ocr/phase12d9_standard_export.py`` (the release gate): the raw TSV
  of every Tesseract invocation of THAT conversion with its provenance
  (document, engine, model files + SHA-256, page, crop, bbox, invocation), the
  cells / texts of every layout element (all engines, PDF text layers too),
  Docling's block joins and the attached footnotes written;
* or ``--tsv <folder>``: raw TSV files, one per crop, ``<folder>/<name>/*.tsv``
  or ``<folder>/<name>_<suffix>.tsv`` (exact document name), each with its
  ``.json`` provenance sidecar.

What v1.2.0 printed is RECOMPUTED from that evidence with the real upstream
code (pandas' TSV parse of Docling 2.129.0, upstream ``sanitize_text``), what
the candidate prints with the patched code; their difference, per crop /
element, is the list of approved changes ("units"), each usable ONCE.

Classes, per hunk and per document (no whole-document exemption):

``unchanged``                       bytes identical (the ONLY way)
``expected TSV fix``                E0-07: a token pandas rewrote / dropped
``expected hyphen fix``             D8-03: a hyphen upstream removed
``expected attached footnote fix``  D8-02: a table / picture footnote added
``expected orientation fix``        only with orientation evidence
                                    (``orientation.jsonl``; not produced yet)
``not verified``                    the shape of an approved fix, no evidence
``unexpected regression``           anything else, incl. a byte / whitespace /
                                    structure change, or a change the crop's
                                    own evidence contradicts

A hunk is accepted only when approved units tile it completely (several
causes may share one hunk). Exit code: 0 = every document unchanged or fully
explained; 1 = an unexpected regression; 2 = something not verified; 3 = the
run proves nothing (no document, a document missing on one side, duplicate
ids, manifest mismatch, missing or unattested evidence).

Privacy: reads local files only. The report holds metadata (classes, causes,
positions, token counts and types) - no document text. ``--with-text`` adds
the tokens of each hunk to the JSON report for a manual review; that report is
written with owner-only permissions and nothing is printed but counts.

Usage::

  python scripts/ocr/phase12_standard_diff.py --before out/v120 --after out/cand \\
      --out out/standard-diff
"""

from __future__ import annotations

import argparse
import csv
import difflib
import functools
import hashlib
import io
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "chatbot5400-standard-diff/2"
UNCHANGED = "unchanged"
EXPECTED_TSV = "expected TSV fix"
EXPECTED_HYPHEN = "expected hyphen fix"
EXPECTED_FOOTNOTE = "expected attached footnote fix"
EXPECTED_ORIENTATION = "expected orientation fix"
NOT_VERIFIED = "not verified"
UNEXPECTED = "unexpected regression"
# kept for the 12D7 / 12D8 callers: the E0-07 class under its old name
EXPECTED = EXPECTED_TSV
EXPECTED_CLASSES = (
    EXPECTED_TSV,
    EXPECTED_HYPHEN,
    EXPECTED_FOOTNOTE,
    EXPECTED_ORIENTATION,
)
CAUSE_CLASS = {
    "tsv": EXPECTED_TSV,
    "hyphen": EXPECTED_HYPHEN,
    "merge": EXPECTED_HYPHEN,
    "footnote": EXPECTED_FOOTNOTE,
    "orientation": EXPECTED_ORIENTATION,
}
EXIT_OK, EXIT_UNEXPECTED, EXIT_NOT_VERIFIED, EXIT_INVALID = 0, 1, 2, 3
SIDECAR_REQUIRED = ("document", "page", "region", "invocation", "engine", "model_files")
FURNITURE = {"page_header", "page_footer"}
CONTEXT = 2  # tokens of context on each side that bind a change to its crop

# pandas' default NA strings (the words the old parser dropped)
NA_WORDS = {
    "",
    "#N/A",
    "#N/A N/A",
    "#NA",
    "-1.#IND",
    "-1.#QNAN",
    "-NaN",
    "-nan",
    "1.#IND",
    "1.#QNAN",
    "<NA>",
    "N/A",
    "NA",
    "NULL",
    "NaN",
    "None",
    "n/a",
    "nan",
    "null",
}

_TSV_HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
    "left\ttop\twidth\theight\tconf\ttext\n"
)
# the page / block / paragraph / line rows Tesseract writes before the words
# (their text is empty: the text column of a crop of numbers becomes float)
_TSV_PARENTS = (
    "1\t1\t0\t0\t0\t0\t0\t0\t100\t50\t-1\t\n"
    "2\t1\t1\t0\t0\t0\t5\t5\t90\t40\t-1\t\n"
    "3\t1\t1\t1\t0\t0\t5\t5\t90\t40\t-1\t\n"
    "4\t1\t1\t1\t1\t0\t5\t5\t90\t40\t-1\t\n"
)


# --------------------------------------------------------------------------- #
# The two parsers and the two text joins - the real code, not a model of it
# --------------------------------------------------------------------------- #


def _upstream_rows(raw: str) -> dict[int, str]:
    """Docling 2.129.0's TSV parse (pandas type inference) + its empty-row
    filter: row index -> the cell text v1.2.0 had."""
    import pandas as pd

    df = pd.read_csv(io.StringIO(raw), quoting=csv.QUOTE_NONE, sep="\t")
    kept = df[df["text"].notna() & (df["text"].apply(str).str.strip() != "")]
    return {int(i): str(row["text"]) for i, row in kept.iterrows()}


def _patched_rows(raw: str) -> list[tuple[int, str, tuple]]:
    """The candidate's parse (docling_patches.read_tesseract_tsv): row index,
    verbatim text, line key (block, paragraph, line)."""
    from open_notebook.ocr.docling_patches import read_tesseract_tsv

    df = read_tesseract_tsv(raw)
    kept = df[df["text"].notna() & (df["text"].apply(str).str.strip() != "")]
    out = []
    for i, row in kept.iterrows():
        key = tuple(
            str(row.get(c)) for c in ("page_num", "block_num", "par_num", "line_num")
        )
        out.append((int(i), str(row["text"]), key))
    return out


@functools.lru_cache(maxsize=4096)
def old_parser_form(token: str) -> Optional[str]:
    """What Docling 2.129.0's TSV parse made of ``token`` ALONE in its crop
    (None = dropped) - computed with real pandas (D8-STD-05)."""
    raw = _TSV_HEADER + _TSV_PARENTS + f"5\t1\t1\t1\t1\t1\t0\t0\t9\t9\t95\t{token}\n"
    try:
        rows = _upstream_rows(raw)
    except Exception:  # noqa: BLE001 - a token pandas cannot read
        return token
    return next(iter(rows.values()), None)  # the word row (the others are empty)


def _upstream_join(texts: list[str]) -> str:
    from open_notebook.ocr import docling_patches as P

    return P.text_upstream("sanitize_text")(None, list(texts))


def _patched_join(texts: list[str], same_line: list[Optional[bool]]) -> str:
    from open_notebook.ocr import docling_patches as P

    return P._sanitize_text(None, list(texts), same_line=list(same_line))


@functools.lru_cache(maxsize=1)
def _markdown_escaper() -> Any:
    from docling_core.transforms.serializer.markdown import MarkdownDocSerializer
    from docling_core.types.doc import DoclingDocument

    return MarkdownDocSerializer(doc=DoclingDocument(name="x"))


def markdown(text: str) -> str:
    """The text as Docling's Markdown export writes a paragraph."""
    try:
        return _markdown_escaper().post_process(text=text)
    except Exception:  # noqa: BLE001 - docling-core not installed: as is
        return text


# --------------------------------------------------------------------------- #
# Tokens: words AND whitespace (a whitespace / structure change is a change);
# Markdown table padding is canonical (it follows the cell widths)
# --------------------------------------------------------------------------- #

_SEP_CELL = re.compile(r"^:?-+:?$")


def canonical(text: str) -> str:
    out = []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("|") and s.endswith("|") and len(s) > 1:
            cells = [c.strip() for c in s[1:-1].split("|")]
            if cells and all(_SEP_CELL.match(c) for c in cells):
                cells = ["---"] * len(cells)
            out.append("| " + " | ".join(cells) + " |")
        else:
            out.append(line)
    return "\n".join(out)


def tokens(text: str) -> list[str]:
    return re.findall(r"\S+|\s+", text)


def _words(text: str) -> list[str]:
    return text.split()


def _kind(token: str) -> str:
    if re.fullmatch(r"[0-9]+([.,][0-9]+)*[.]?", token):
        return "number"
    if re.fullmatch(r"\w+", token):
        return "word"
    if re.fullmatch(r"[\W_]+", token):
        return "punctuation"
    return "mixed"


# --------------------------------------------------------------------------- #
# Evidence -> approved units and the crops / elements that own text
# --------------------------------------------------------------------------- #


class Unit:
    """One approved change of the evidence (usable once)."""

    def __init__(
        self,
        cause: str,
        old: str,
        new: str,
        source: str,
        page: Optional[int] = None,
        left: tuple[str, ...] = (),
        right: tuple[str, ...] = (),
    ) -> None:
        self.cause, self.old, self.new, self.source = cause, old, new, source
        self.page, self.left, self.right = page, left, right
        self.used = False
        self.must_show = False  # export mode: the output must hold this change


class Owner:
    """A crop / element: its v1.2.0 and candidate words, aligned."""

    def __init__(
        self, source: str, old: list[str], new: list[str], page: Optional[int] = None
    ) -> None:
        self.source, self.old, self.new, self.page = source, old, new, page
        self.ops = difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes()


class Evidence:
    def __init__(self) -> None:
        self.units: list[Unit] = []
        self.owners: list[Owner] = []
        self.problems: list[str] = []
        self.crops = 0
        self.elements = 0


def _diff_units(
    old_text: str,
    new_text: str,
    cause_of: Any,
    source: str,
    page: Optional[int],
    ev: Evidence,
    must_show: bool = False,
) -> None:
    """Approved units from one crop / element: its v1.2.0 text vs its candidate
    text, and the owner that binds them to their context."""
    a, b = tokens(old_text), tokens(new_text)
    ev.owners.append(
        Owner(source=source, old=_words(old_text), new=_words(new_text), page=page)
    )
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(
        a=a, b=b, autojunk=False
    ).get_opcodes():
        if op == "equal":
            continue
        seg_old, seg_new = "".join(a[i1:i2]).strip(), "".join(b[j1:j2]).strip()
        if not seg_old and not seg_new:
            continue
        before = _words("".join(b[:j1]))[-CONTEXT:]
        after = _words("".join(b[j2:]))[:CONTEXT]
        unit = Unit(
            cause=cause_of(seg_old, seg_new),
            old=seg_old,
            new=seg_new,
            source=source,
            page=page,
            left=tuple(before),
            right=tuple(after),
        )
        unit.must_show = must_show
        ev.units.append(unit)


def _tsv_cause(seg_old: str, seg_new: str) -> str:
    """Which approved fix(es) a unit is (informational: a unit is approved by
    construction - the difference of the v1.2.0 and candidate code)."""
    bare_new = seg_new.replace("-", "").replace(" ", "")
    if "-" in seg_new and bare_new == seg_old.replace(" ", ""):
        return "hyphen"
    if seg_new.count("-") > seg_old.count("-"):
        return "hyphen+tsv"
    return "tsv"


def crop_texts(raw: str) -> tuple[str, str]:
    """(v1.2.0 text, candidate text) of one Tesseract crop, as Markdown."""
    new_rows = _patched_rows(raw)
    old_rows = _upstream_rows(raw)
    new_texts = [t for _, t, _ in new_rows]
    old_texts = [old_rows[i] for i, _, _ in new_rows if i in old_rows]
    keys = [k for _, _, k in new_rows]
    flags = [a == b for a, b in zip(keys, keys[1:])]
    same_line: list[Optional[bool]] = [True if f else False for f in flags]
    return markdown(_upstream_join(old_texts)), markdown(
        _patched_join(new_texts, same_line)
    )


def _sidecar(path: Path) -> Optional[dict[str, Any]]:
    side = path.with_suffix(".json")
    if not side.is_file():
        return None
    try:
        data = json.loads(side.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _tsv_files(
    name: str, tsv_dir: Optional[Path], evidence_dir: Optional[Path]
) -> list[Path]:
    files: list[Path] = []
    if evidence_dir is not None and (evidence_dir / "tesseract").is_dir():
        files += sorted((evidence_dir / "tesseract").glob("*.tsv"))
    if tsv_dir is not None:
        if (tsv_dir / name).is_dir():
            files += sorted((tsv_dir / name).rglob("*.tsv"))
        for f in sorted(tsv_dir.glob("*.tsv")):
            if f.stem.rsplit("_", 1)[0] == name:  # exact name (D8-STD-03)
                files.append(f)
    return files


def load_evidence(
    name: str, tsv_dir: Optional[Path], evidence_dir: Optional[Path]
) -> Optional[Evidence]:
    ev = Evidence()
    files = _tsv_files(name, tsv_dir, evidence_dir)
    elements = (evidence_dir / "elements.jsonl") if evidence_dir else None
    have_elements = bool(elements and elements.is_file())
    if not files and not have_elements:
        return None
    seen: set[str] = set()
    for f in files:
        meta = _sidecar(f)
        if meta is None or any(k not in meta for k in SIDECAR_REQUIRED):
            ev.problems.append(f"{f.name}: no provenance sidecar (unattested evidence)")
            continue
        if str(meta["document"]) != name:
            ev.problems.append(f"{f.name}: evidence of another document")
            continue
        inv = str(meta["invocation"])
        if inv in seen:
            ev.problems.append(f"{f.name}: duplicate invocation id")
            continue
        seen.add(inv)
        raw = f.read_text(encoding="utf-8", errors="replace")
        try:
            old_text, new_text = crop_texts(raw)
        except Exception as e:  # noqa: BLE001 - a TSV pandas cannot read
            ev.problems.append(f"{f.name}: unreadable TSV ({type(e).__name__})")
            continue
        ev.crops += 1
        if not have_elements:
            # without element evidence the crop is the unit source and owner;
            # with it (export mode) the elements carry every unit and own the
            # text (a crop may be a whole page: no unit counted twice)
            _diff_units(
                old_text, new_text, _tsv_cause, f.name, _int(meta.get("page")), ev
            )
    if have_elements and elements is not None:
        for n, line in enumerate(elements.read_text(encoding="utf-8").splitlines()):
            try:
                rec = json.loads(line)
            except ValueError:
                ev.problems.append(f"elements.jsonl:{n + 1}: unreadable")
                continue
            ev.elements += 1
            _diff_units(
                markdown(str(rec.get("v120_text", ""))),
                markdown(str(rec.get("text", ""))),
                _tsv_cause,
                f"element {n + 1}",
                _int(rec.get("page")),
                ev,
                # page headers / footers are not in the Markdown export
                must_show=str(rec.get("label")) not in FURNITURE,
            )
    for kind, cause in (
        ("merges.jsonl", "merge"),
        ("footnotes.jsonl", "footnote"),
    ):
        path = (evidence_dir / kind) if evidence_dir else None
        if not path or not path.is_file():
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            try:
                rec = json.loads(line)
            except ValueError:
                ev.problems.append(f"{kind}:{n + 1}: unreadable")
                continue
            unit = Unit(
                cause=cause,
                old=str(rec.get("v120_text", "")).strip(),
                new=str(rec.get("text", "")).strip(),
                source=f"{kind}:{n + 1}",
                page=_int(rec.get("page")),
            )
            unit.must_show = cause != "orientation"
            ev.units.append(unit)
    if evidence_dir and (evidence_dir / "orientation.jsonl").exists():
        ev.problems.append("orientation correction has no verified producer")
    return ev


def _int(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# One hunk: tiled by approved units, contradicted by its owner, or not proven
# --------------------------------------------------------------------------- #


def _edges(text: str) -> tuple[str, str, str]:
    core = text.strip()
    if not core:
        return text, "", ""
    start = text.index(core)
    return text[:start], core, text[start + len(core) :]


def _context_ok(u: Unit, left: list[str], right: list[str]) -> bool:
    if u.left and tuple(left[-len(u.left) :]) != u.left:
        return False
    if u.right and tuple(right[: len(u.right)]) != u.right:
        return False
    return True


def _tile(old: str, new: str, units: list[Unit]) -> Optional[list[Unit]]:
    """Units (each once, in order) that turn ``old`` into ``new``; characters
    equal on both sides between them are glue."""

    @functools.lru_cache(maxsize=None)
    def go(i: int, j: int, used: frozenset) -> Optional[tuple[int, ...]]:
        if i == len(old) and j == len(new):
            return ()
        for k, u in enumerate(units):
            if k in used or not (u.old or u.new):
                continue
            if old.startswith(u.old, i) and new.startswith(u.new, j):
                rest = go(i + len(u.old), j + len(u.new), used | {k})
                if rest is not None:
                    return (k, *rest)
        if i < len(old) and j < len(new) and old[i] == new[j]:
            return go(i + 1, j + 1, used)
        return None

    found = go(0, 0, frozenset())
    return None if found is None else [units[k] for k in found]


def _owner_at(
    owners: list[Owner], left: list[str], right: list[str], new_words: list[str]
) -> Optional[tuple[Owner, list[str], list[str]]]:
    """The crop / element whose candidate words contain this hunk's context:
    (owner, v1.2.0 words it predicts there, candidate words it predicts)."""
    lc, rc = left[-CONTEXT:], right[:CONTEXT]
    if len(lc) < CONTEXT and len(rc) < CONTEXT:
        return None  # too little context to bind the hunk to one crop / element
    for ow in owners:
        words = ow.new
        for k in range(len(words) + 1):
            # a short context means the document starts / ends there: the
            # owner must start / end there too
            if len(lc) == CONTEXT:
                if k < CONTEXT or words[k - CONTEXT : k] != lc:
                    continue
            elif words[:k] != lc:
                continue
            for m in range(0, len(new_words) + 4):
                tail = words[k + m :]
                if (tail[:CONTEXT] == rc) if len(rc) == CONTEXT else (tail == rc):
                    return ow, _old_span(ow, k, k + m), words[k : k + m]
    return None


def _old_span(ow: Owner, j1: int, j2: int) -> list[str]:
    """The v1.2.0 words of an owner aligned with its candidate words j1:j2."""
    out: list[str] = []
    for op, a1, a2, b1, b2 in ow.ops:
        lo, hi = max(b1, j1), min(b2, j2)
        if op == "equal":
            if lo < hi:
                out += ow.old[a1 + (lo - b1) : a1 + (hi - b1)]
        elif b1 < j2 and b2 > j1 or (b1 == b2 and j1 <= b1 <= j2):
            out += ow.old[a1:a2]
    return out


def _shape_of_fix(old: str, new: str) -> bool:
    """The change looks like an approved fix (but nothing proves it)."""
    ow, nw = _words(old), _words(new)
    forms = [m for m in (old_parser_form(t) for t in nw) if m is not None]
    if forms == ow and ow != nw:
        return True  # E0-07 shape: pandas forms / dropped NA words
    if new.replace("-", "").replace(" ", "") == old.replace(" ", "") and "-" in new:
        return True  # D8-03 shape: only hyphens added
    return False


def classify_hunk(
    old: list[str] | str,
    new: list[str] | str,
    evidence: Any = None,
    left: Optional[list[str]] = None,
    right: Optional[list[str]] = None,
) -> str:
    """Class of one hunk (old / new: tokens or text). ``evidence``: an
    Evidence (units are consumed), anything else = no evidence."""
    return explain(old, new, evidence, left or [], right or [])[0]


def explain(
    old: list[str] | str,
    new: list[str] | str,
    evidence: Any,
    left: list[str],
    right: list[str],
) -> tuple[str, list[str], str]:
    """(class, causes, reason)."""
    old_s = old if isinstance(old, str) else " ".join(old)
    new_s = new if isinstance(new, str) else " ".join(new)
    if old_s == new_s:
        return UNCHANGED, [], ""
    lo, core_old, to = _edges(old_s)
    ln, core_new, tn = _edges(new_s)
    if not core_old and not core_new:
        return UNEXPECTED, [], "whitespace / structure changed"
    if core_old and core_new and (lo != ln or to != tn):
        return UNEXPECTED, [], "whitespace / structure changed beside a change"
    ev = evidence if isinstance(evidence, Evidence) else None
    if ev is not None:
        owner = _owner_at(ev.owners, left, right, _words(core_new))
        pool = [
            u
            for u in ev.units
            if not u.used
            and u.old in core_old
            and u.new in core_new
            and _context_ok(u, left, right)
            # the crop / element whose words hold this position decides alone
            and (owner is None or u.source == owner[0].source)
        ]
        tiles = _tile(core_old, core_new, pool)
        if tiles:
            for u in tiles:
                u.used = True
            causes = sorted({c for u in tiles for c in u.cause.split("+")})
            classes = sorted({CAUSE_CLASS[c] for c in causes})
            return classes[0] if len(classes) == 1 else "+".join(classes), causes, ""
        if owner is not None:
            ow, predicted_old, predicted_new = owner
            if predicted_old == predicted_new or predicted_new != _words(core_new):
                return UNEXPECTED, [], f"contradicted by its own evidence ({ow.source})"
    if _shape_of_fix(core_old, core_new):
        return NOT_VERIFIED, [], "shape of an approved fix, no evidence"
    return UNEXPECTED, [], "not an approved change"


def _doc_class(classes: Iterable[str]) -> str:
    cl = list(classes)
    if not cl:
        return UNCHANGED
    if any(c == UNEXPECTED for c in cl):
        return UNEXPECTED
    if any(c == NOT_VERIFIED for c in cl):
        return NOT_VERIFIED
    parts = sorted({p for c in cl for p in c.split("+")})
    return parts[0] if len(parts) == 1 else "+".join(parts)


def compare(
    before: str, after: str, evidence: Any = None, with_text: bool = False
) -> dict[str, Any]:
    if before == after:
        return {"class": UNCHANGED, "hunks": [], "byte_identical": True}
    a, b = tokens(canonical(before)), tokens(canonical(after))
    hunks = []
    ops = difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()
    for op, i1, i2, j1, j2 in ops:
        if op == "equal":
            continue
        old_s, new_s = "".join(a[i1:i2]), "".join(b[j1:j2])
        left = _words("".join(b[:j1]))[-CONTEXT:]
        right = _words("".join(b[j2:]))[:CONTEXT]
        kind, causes, reason = explain(old_s, new_s, evidence, left, right)
        h: dict[str, Any] = {
            "class": kind,
            "causes": causes,
            "at_token": i1,
            "before_count": len(_words(old_s)),
            "after_count": len(_words(new_s)),
            "before_kinds": sorted({_kind(t) for t in _words(old_s)}),
            "after_kinds": sorted({_kind(t) for t in _words(new_s)}),
        }
        if reason:
            h["reason"] = reason
        if with_text:
            h["before"] = _words(old_s)[:20]
            h["after"] = _words(new_s)[:20]
        hunks.append(h)
    if not hunks:  # bytes differ, canonical tokens equal: table padding only
        hunks.append(
            {
                "class": UNEXPECTED,
                "causes": [],
                "at_token": 0,
                "before_count": 0,
                "after_count": 0,
                "reason": "bytes differ outside the words (whitespace / table padding)",
            }
        )
    out: dict[str, Any] = {
        "class": _doc_class(h["class"] for h in hunks),
        "hunks": hunks,
        "byte_identical": False,
    }
    if isinstance(evidence, Evidence):
        out["units_unused"] = sum(1 for u in evidence.units if not u.used)
        missing = sum(1 for u in evidence.units if u.must_show and not u.used)
        if missing:
            # the conversion produced a change the output does not show (a
            # lost hyphen / footnote, an output that is not this conversion's)
            out["changes_missing_from_output"] = missing
            if out["class"] != UNEXPECTED:
                out["class"] = NOT_VERIFIED
    return out


# --------------------------------------------------------------------------- #
# The run
# --------------------------------------------------------------------------- #


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _manifest(folder: Path) -> Optional[dict[str, Any]]:
    path = folder / "manifest.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {"invalid": True}
    return data if isinstance(data, dict) else {"invalid": True}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_documents(
    folder: Path, data: dict[str, Any], problems: list[str]
) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    rows = data.get("documents")
    if data.get("invalid") or not isinstance(rows, list) or not rows:
        problems.append("manifest is missing a valid document inventory")
        return entries
    for row in rows:
        name = row.get("name") if isinstance(row, dict) else None
        if (
            not isinstance(name, str)
            or not name
            or name in {".", ".."}
            or any(c in name for c in "/\\:")
        ):
            problems.append("invalid document id in manifest")
            continue
        if name.casefold() in seen:
            problems.append("duplicate document ids in the manifest")
            continue
        seen.add(name.casefold())
        entries[name] = row
        path = folder / f"{name}.md"
        if (
            "error" in row
            or row.get("conversion_status") not in (None, "success")
            or row.get("conversion_errors")
        ):
            problems.append("a document failed to convert")
        elif not path.is_file() or path.is_symlink():
            problems.append("a manifest document has no output")
        elif row.get("output_sha256") != _sha(path):
            problems.append("an output differs from the manifest (sha256)")
    if {p.stem for p in folder.glob("*.md")} - entries.keys():
        problems.append("an output is not listed in the manifest")
    return entries


def _json_lines(path: Path, identity: dict[str, Any]) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    if any(not _same_identity(record, identity) for record in records):
        raise ValueError("evidence belongs to another document or run")
    return records


def _same_identity(record: Any, identity: dict[str, Any]) -> bool:
    return isinstance(record, dict) and all(
        record.get(k) == v for k, v in identity.items()
    )


def _bounds(bbox: Any) -> tuple[float, float, float, float]:
    left, top, right, bottom = bbox[:4]
    if not all(
        type(v) in (float, int) and math.isfinite(v) for v in (left, top, right, bottom)
    ):
        raise ValueError("invalid evidence coordinates")
    return min(left, right), min(top, bottom), max(left, right), max(top, bottom)


def _digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _bound_evidence(
    folder: Path, entry: dict[str, Any], run: dict[str, Any]
) -> tuple[dict, list, dict, list]:
    """Validate the files and row identities of one completed export."""
    expected = entry.get("evidence_files")
    actual = {
        path.relative_to(folder).as_posix(): path
        for path in folder.rglob("*")
        if path.is_file()
    }
    if (
        not isinstance(expected, dict)
        or set(expected) != set(actual)
        or any(
            path.is_symlink() or expected[name] != _sha(path)
            for name, path in actual.items()
        )
    ):
        raise ValueError("evidence inventory or hash differs")
    identity = {"document": entry["name"], "run_id": run["run_id"]}
    crops = {}
    for path in sorted(folder.glob("tesseract/*.tsv")):
        side = _sidecar(path)
        if not _same_identity(side, identity):
            raise ValueError("TSV belongs to another document or run")
        assert side is not None
        page, region, serial = (int(v) for v in path.stem.split("_"))
        invocation = f"{page:04d}-{region:03d}-{serial:06d}"
        models = side.get("model_files")
        if (
            page < 1
            or region < 1
            or serial < 1
            or side.get("page") != page
            or side.get("region") != region
            or side.get("invocation") != invocation
            or invocation in crops
            or not isinstance(models, list)
            or not models
            or any(not _digest(model["sha256"]) for model in models)
            or side.get("engine") != "+".join(model["name"] for model in models)
            or {model["name"]: model["sha256"] for model in models}
            != {
                name: sha
                for name, sha in (entry.get("ocr_model_files") or {}).items()
                if name != "osd"
            }
        ):
            raise ValueError("invalid TSV invocation, page, crop or model")
        raw = path.read_text(encoding="utf-8")
        crops[invocation] = (
            page,
            _bounds(side["bbox"]),
            {i: token for i, token, _ in _patched_rows(raw)},
            _upstream_rows(raw),
        )
    elements = {}
    for record in _json_lines(folder / "elements.jsonl", identity):
        key = (record["page"], record["cluster"])
        if key in elements or not isinstance(key[0], int) or key[0] < 1:
            raise ValueError("duplicate or invalid element identity")
        elements[key] = record
    footnotes = _json_lines(folder / "footnotes.jsonl", identity)
    return (
        elements,
        _json_lines(folder / "output_spans.jsonl", identity),
        crops,
        footnotes,
    )


class _NoGeometry:
    """A cell whose box the evidence does not record: no line-break evidence."""

    rect = None


def _recorded_geometry(cells: list[dict[str, Any]]) -> list[Any]:
    """Stand-ins carrying the boxes the export recorded for TSV-bound cells
    (top-left origin), for the candidate's own ``same_line_flags``. A cell
    without a recorded box gives no evidence (its flag is None: no close-up)."""
    from docling_core.types.doc import BoundingBox, CoordOrigin
    from docling_core.types.doc.page import BoundingRectangle

    out: list[Any] = []
    for cell in cells:
        if "invocation" not in cell or cell.get("bbox") is None:
            out.append(_NoGeometry())
            continue
        left, top, right, bottom = _bounds(cell["bbox"])
        rect = BoundingRectangle.from_bounding_box(
            BoundingBox(
                l=left, t=top, r=right, b=bottom, coord_origin=CoordOrigin.TOPLEFT
            )
        )
        out.append(type("RecordedCell", (), {"rect": rect})())
    return out


def _element_proof(
    element: dict[str, Any],
    crops: dict[str, Any],
    taken: set[tuple[str, int]],
) -> tuple[str, Optional[str], set[str], set[tuple[str, int]]]:
    """Rebuild one recorded element from its source evidence ONLY (D12-03).

    Returns (candidate text, v1.2.0 text or None when an OCR cell has no TSV
    row, the approved causes of their difference, the TSV rows used). Every
    OCR cell's candidate text must be its own TSV row as the candidate parses
    it; the candidate text must be the patched join of those cells with the
    line-break evidence of their recorded boxes; the v1.2.0 text is the
    upstream join of the same rows as pandas parsed them. Anything else -
    a token no row holds, a dropped or reordered token, a row used twice, a
    close-up without box evidence - raises ValueError (NOT VERIFIED).
    """
    from open_notebook.ocr.docling_patches import same_line_flags

    cells = element["cells"]
    if not isinstance(cells, list) or not cells:
        raise ValueError("element has no source cells")
    new_tokens: list[str] = []
    old_tokens: list[str] = []
    used: set[tuple[str, int]] = set()
    unmapped = False
    parse_changed = False
    for cell in cells:
        token = cell["text"]
        if not isinstance(token, str):
            raise ValueError("invalid cell text")
        if cell.get("unmapped_ocr"):
            if "invocation" in cell:
                raise ValueError("an unmapped OCR cell cannot name a TSV row")
            unmapped = True  # its v1.2.0 form is unknown
        elif "invocation" in cell:
            invocation, row = cell["invocation"], cell["row"]
            page, crop, rows, baseline = crops[invocation]
            left, top, right, bottom = _bounds(cell["bbox"])
            raw = rows[row].strip()
            key = (invocation, row)
            if (
                page != element["page"]
                or raw != cell["raw"]
                or token != raw.replace("\x02", "-").strip()
                or key in used
                or key in taken
                or not crop[0] <= (left + right) / 2 <= crop[2]
                or not crop[1] <= (top + bottom) / 2 <= crop[3]
            ):
                raise ValueError("cell does not belong to the recorded crop")
            used.add(key)
            previous = baseline.get(row)
            previous = previous.strip() if previous else None
            if previous != token:
                parse_changed = True
            if previous:
                old_tokens.append(previous)
        elif token:
            old_tokens.append(token)  # a text-layer cell: the same on both sides
        new_tokens.append(token)
    flags = same_line_flags(_recorded_geometry(cells))
    candidate = _patched_join(new_tokens, flags)
    if candidate != element["text"]:
        raise ValueError("candidate text does not follow its source cells")
    causes: set[str] = set()
    if parse_changed:
        causes.add("tsv")
    if _upstream_join(new_tokens) != candidate:
        causes.add("hyphen")
    baseline_text = None if unmapped else _upstream_join(old_tokens)
    return candidate, baseline_text, causes, used


def _token_forms(token: str) -> list[str]:
    """How one cell's text can appear in the Markdown output (as is, after the
    join's character normalization, after Markdown escaping)."""
    normalized = _patched_join([token], [])
    forms = [token, normalized, markdown(normalized)]
    return list(dict.fromkeys(f for f in forms if f))


def verify_bound_output(
    before: str, after: str, folder: Path, entry: dict[str, Any], run: dict[str, Any]
) -> dict:
    """Reconstruct the baseline bytes AND the candidate bytes of every span from
    its source evidence only (D12-03: nothing the candidate declares about its
    own text is trusted without the TSV rows / boxes that produced it)."""
    try:
        elements, spans, crops, footnotes = _bound_evidence(folder, entry, run)
        output = []
        cursor = 0
        refs: set[str] = set()
        hyphens: set[tuple[str, int]] = set()
        taken: set[tuple[str, int]] = set()
        used_elements: set[tuple[Any, Any]] = set()
        used_notes: set[int] = set()
        expected_hyphens = {
            (invocation, row)
            for invocation, (_, _, rows, _) in crops.items()
            for row, word in rows.items()
            if "-" in word
        }
        classes = set()
        for span in spans:
            start, end = span["start"], span["end"]
            if (
                not cursor <= start < end <= len(after)
                or after[start:end] != span["text"]
                or span["item"] in refs
            ):
                raise ValueError("source span does not match the output")
            refs.add(span["item"])
            if span.get("kind") == "footnote":
                previous = span["v120_text"]
                notes = span["notes"]
                if (
                    not notes
                    or not str(span["item"]).startswith(("#/tables/", "#/pictures/"))
                    or type(span["page"]) is not int
                    or span["page"] < 1
                    or "\n\n".join(text for text in [previous, *notes] if text)
                    != span["text"]
                ):
                    raise ValueError("unbound attached footnotes")
                for note in notes:
                    # each note: a footnote the export wrote, and the recorded
                    # element whose source cells produce exactly that text
                    n = next(
                        (
                            i
                            for i, rec in enumerate(footnotes)
                            if i not in used_notes and rec.get("text") == note
                        ),
                        None,
                    )
                    if n is None:
                        raise ValueError("attached footnote without its export record")
                    used_notes.add(n)
                    owner = [
                        key
                        for key, rec in elements.items()
                        if key not in used_elements
                        and key[0] == footnotes[n].get("page")
                        and markdown(str(rec.get("text"))) == note
                    ]
                    if len(owner) != 1:
                        raise ValueError("attached footnote without one source element")
                    _, _, _, rows_used = _element_proof(
                        elements[owner[0]], crops, taken
                    )
                    used_elements.add(owner[0])
                    taken |= rows_used
                output.extend((after[cursor:start], previous))
                cursor = end
                classes.add(EXPECTED_FOOTNOTE)
                continue
            key = (span["page"], span["cluster"])
            element = elements[key]
            if (
                key in used_elements
                or span["bbox"] != element["bbox"]
                or markdown(element["text"]) != after[start:end]
            ):
                raise ValueError("source span does not match the output")
            used_elements.add(key)
            _, baseline_text, causes, cell_ids = _element_proof(element, crops, taken)
            taken |= cell_ids
            old_text = span["v120_text"]
            changed = old_text != span["text"]
            if baseline_text is None:
                if changed:
                    raise ValueError("change includes an unmapped OCR cell")
            elif markdown(baseline_text) != old_text:
                raise ValueError("baseline span does not follow source cells")
            if changed and not causes:
                raise ValueError("difference without an approved cause")
            position = start
            mapped = iter(span["hyphens"])
            occurrence = next(mapped, None)
            cells = [cell for cell in element["cells"] if cell["text"]]
            for n, cell in enumerate(cells):
                token = cell["text"]
                while position < end and after[position].isspace():
                    position += 1
                form = next(
                    (
                        f
                        for f in _token_forms(token)
                        if position + len(f) <= end and after.startswith(f, position)
                    ),
                    None,
                )
                if form is None or (form != token and "-" in token):
                    # the whole span must be walked: a changed span, or one
                    # with hyphen rows still to place, is not proven
                    if changed or any(
                        "-" in c["text"] and "invocation" in c for c in cells[n:]
                    ):
                        raise ValueError("span does not follow its source cells")
                    position = end
                    break
                token = form
                if "-" in token and "invocation" in cell:
                    key = (cell["invocation"], cell["row"])
                    if (
                        occurrence
                        != {
                            "invocation": key[0],
                            "row": key[1],
                            "start": position,
                            "end": position + len(token),
                        }
                        or key not in cell_ids
                        or key in hyphens
                    ):
                        raise ValueError(
                            "hyphen occurrence does not match the source order"
                        )
                    hyphens.add(key)
                    occurrence = next(mapped, None)
                position += len(token)
            if occurrence is not None:
                raise ValueError("unmatched output occurrence")
            if changed and after[position:end].strip():
                raise ValueError("span holds text no source cell produced")
            if changed:
                # the causes the evidence proves, not a guess from the texts
                classes.update(CAUSE_CLASS[cause] for cause in causes)
            output.extend((after[cursor:start], old_text))
            cursor = end
        output.append(after[cursor:])
        if (
            before != "".join(output)
            or hyphens != expected_hyphens
            or (folder / "orientation.jsonl").exists()
        ):
            return {
                "class": NOT_VERIFIED,
                "hunks": [],
                "reason": "unproven difference or OCR occurrence",
            }
        return {
            "class": _doc_class(classes),
            "hunks": [],
            "byte_identical": before == after,
            "hyphen_occurrence_status": "verified" if crops else "not applicable",
        }
    except (OSError, TypeError, ValueError, KeyError, IndexError, AttributeError):
        return {
            "class": NOT_VERIFIED,
            "hunks": [],
            "reason": "invalid or unbound source evidence",
        }


def _failed_documents(folder: Path) -> list[str]:
    """Documents the export of ``folder`` could not convert (manifest ``error``)."""
    data = _manifest(folder)
    if not data or data.get("invalid"):
        return []
    return sorted(
        str(d.get("name"))
        for d in (data["documents"] if isinstance(data.get("documents"), list) else [])
        if isinstance(d, dict) and "error" in d
    )


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--before", required=True, help="v1.2.0 Standard outputs (*.md)")
    p.add_argument("--after", required=True, help="candidate Standard outputs (*.md)")
    p.add_argument(
        "--tsv", help="raw TSV per crop: <dir>/<name>/*.tsv or <dir>/<name>_*.tsv"
    )
    p.add_argument("--out", required=True)
    p.add_argument(
        "--release",
        action="store_true",
        help="require manifest-bound source spans and image identity",
    )
    p.add_argument("--candidate-commit", help="expected release candidate commit SHA")
    p.add_argument(
        "--candidate-image", help="expected release candidate Docker image ID"
    )
    p.add_argument(
        "--with-text",
        action="store_true",
        help="also write the tokens of each hunk (owner-only file; never printed)",
    )
    args = p.parse_args(argv)
    before, after = Path(args.before), Path(args.after)
    tsv_dir = Path(args.tsv) if args.tsv else None
    report: dict[str, Any] = {"schema": SCHEMA, "documents": {}, "run_problems": []}
    problems: list[str] = report["run_problems"]

    def names_of(folder: Path) -> list[str]:
        return sorted(f.stem for f in folder.glob("*.md"))

    b_names, a_names = names_of(before), names_of(after)
    for side, names in (("before", b_names), ("after", a_names)):
        lower = [n.casefold() for n in names]
        if len(set(lower)) != len(lower):
            problems.append(f"duplicate document ids on the {side} side")
    b_manifest, manifest = _manifest(before), _manifest(after)
    a_docs = (
        _manifest_documents(after, manifest, problems) if manifest is not None else {}
    )
    b_docs = (
        _manifest_documents(before, b_manifest, problems)
        if b_manifest is not None
        else {}
    )
    if not args.release and any(
        run and run.get("image_id") for run in (b_manifest, manifest)
    ):
        problems.append("image-labelled release exports require --release")
    if args.release:
        for run in (b_manifest, manifest):
            if (
                not run
                or run.get("schema") != "chatbot5400-standard-export/2"
                or not re.fullmatch(r"[a-f0-9]{32}", str(run.get("run_id", "")))
                or not re.fullmatch(r"[a-f0-9]{40}", str(run.get("commit", "")))
                or not re.fullmatch(
                    r"sha256:[a-f0-9]{64}", str(run.get("image_id", ""))
                )
            ):
                problems.append(
                    "release requires two valid run, commit and image identities"
                )
        if (
            not b_manifest
            or b_manifest.get("commit") != "f2fdf2714a7c0b5b196132f71cfc091928befc06"
        ):
            problems.append("release baseline is not the official v1.2.0 commit")
        if not (
            manifest
            and args.candidate_commit
            and args.candidate_image
            and manifest.get("commit") == args.candidate_commit
            and manifest.get("image_id") == args.candidate_image
        ):
            problems.append("candidate commit and image must match the release request")
        if not manifest or manifest.get("evidence") is not True:
            problems.append("release requires evidence from the candidate conversion")
        if tsv_dir is not None:
            problems.append("external TSV cannot attest a release run")
        for run, documents in ((manifest, a_docs), (b_manifest, b_docs)):
            if not run:
                continue
            for entry in documents.values():
                if (
                    not run.get("engine")
                    or entry.get("ocr_engine") != run["engine"]
                    or entry.get("output") != f"{entry['name']}.md"
                ):
                    problems.append("document engine or artifact differs from its run")
        for entry in (*a_docs.values(), *b_docs.values()):
            files = entry.get("ocr_model_files")
            config = entry.get("ocr_config")
            if (
                not _digest(entry.get("input_sha256"))
                or entry.get("conversion_status") != "success"
                or not isinstance(config, dict)
                or not isinstance(config.get("settings"), dict)
            ):
                problems.append("incomplete input or conversion identity")
            if (
                not isinstance(files, dict)
                or not files
                or not all(_digest(v) for v in files.values())
            ):
                problems.append("unverified OCR model identity")
    if b_manifest is not None and manifest is not None:
        if set(a_docs) != set(b_docs):
            problems.append("run document inventories differ")
        for key in ("engine", "custom_version", "ocr_config", "versions"):
            if manifest.get(key) != b_manifest.get(key):
                problems.append(f"run identity differs: {key}")
        if manifest.get("run_id") and manifest.get("run_id") == b_manifest.get(
            "run_id"
        ):
            problems.append("baseline and candidate use the same run id")
        for name in a_docs.keys() & b_docs.keys():
            for key in (
                "input_sha256",
                "ocr_engine",
                "ocr_model_version",
                "ocr_model_sha256",
                "ocr_model_files",
                "ocr_config",
            ):
                if a_docs[name].get(key) != b_docs[name].get(key):
                    problems.append(f"document identity differs: {key}")
    names = sorted(
        set(b_docs if b_manifest is not None else b_names)
        | set(a_docs if manifest is not None else a_names)
    )
    if not names:
        problems.append("no document to compare")
    for name in names:
        fa, fb = before / f"{name}.md", after / f"{name}.md"
        if not fa.is_file() or not fb.is_file():
            report["documents"][name] = {
                "class": NOT_VERIFIED,
                "reason": "missing on one side",
            }
            problems.append("a document is missing on one side")
            continue
        bytes_a, bytes_b = fa.read_bytes(), fb.read_bytes()
        if bytes_a == bytes_b and not args.release:
            report["documents"][name] = {
                "class": UNCHANGED,
                "hunks": [],
                "byte_identical": True,
            }
            continue
        try:
            text_a, text_b = bytes_a.decode("utf-8"), bytes_b.decode("utf-8")
        except UnicodeDecodeError:
            problems.append("an output is not UTF-8")
            report["documents"][name] = {
                "class": NOT_VERIFIED,
                "reason": "invalid output encoding",
            }
            continue
        evidence_dir = after / f"{name}.evidence"
        if args.release:
            if not manifest or name not in a_docs:
                report["documents"][name] = {
                    "class": NOT_VERIFIED,
                    "reason": "missing candidate manifest",
                }
            else:
                report["documents"][name] = verify_bound_output(
                    text_a, text_b, evidence_dir, a_docs[name], manifest
                )
            continue
        if manifest and isinstance(a_docs.get(name, {}).get("evidence_files"), dict):
            actual = {
                p.relative_to(evidence_dir).as_posix(): _sha(p)
                for p in evidence_dir.rglob("*")
                if p.is_file() and not p.is_symlink()
            }
            if actual != a_docs[name]["evidence_files"]:
                problems.append("evidence inventory or hash differs")
        evidence = load_evidence(
            name, tsv_dir, evidence_dir if evidence_dir.is_dir() else None
        )
        if manifest is not None and evidence is None:
            problems.append("a changed document has no evidence")
        doc = compare(text_a, text_b, evidence, with_text=args.with_text)
        if evidence is not None:
            doc["evidence"] = {
                "crops": evidence.crops,
                "elements": evidence.elements,
                "units": len(evidence.units),
                "problems": len(evidence.problems),
            }
            if evidence.problems:
                problems.append("unattested or mismatched evidence")
                if doc["class"] not in (UNEXPECTED, UNCHANGED):
                    doc["class"] = NOT_VERIFIED
        report["documents"][name] = doc
    for side, folder in (("before", before), ("after", after)):
        # a conversion that failed is never "not compared": the run proves nothing
        # for that document, and a stale output beside it must not be compared
        for name in _failed_documents(folder):
            problems.append(f"a document failed to convert on the {side} side")
            entry = report["documents"].setdefault(name, {"class": NOT_VERIFIED})
            if entry["class"] != UNEXPECTED:
                entry["class"] = NOT_VERIFIED
            entry["reason"] = "conversion failed"
    counts: dict[str, int] = {}
    for doc in report["documents"].values():
        counts[doc["class"]] = counts.get(doc["class"], 0) + 1
    report["summary"] = counts
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    body = json.dumps(report, ensure_ascii=False, indent=1)
    if args.with_text:
        _write_private(out / "standard_diff.json", body)
    else:
        (out / "standard_diff.json").write_text(body, encoding="utf-8")
    lines = [
        "# Standard expected-diff (Phase 12D9)",
        "",
        "| document | class | hunks |",
        "|---|---|---|",
    ]
    for name, doc in report["documents"].items():
        lines.append(f"| {name} | {doc['class']} | {len(doc.get('hunks', []))} |")
    lines += [
        "",
        "Summary: " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())),
    ]
    if problems:
        lines += ["", "Run problems (the gate fails):"] + [
            f"- {x}" for x in sorted(set(problems))
        ]
    (out / "standard_diff.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"summary": counts, "run_problems": len(set(problems))}, ensure_ascii=False
        )
    )
    if counts.get(UNEXPECTED):
        return EXIT_UNEXPECTED
    if problems:
        return EXIT_INVALID
    if counts.get(NOT_VERIFIED):
        return EXIT_NOT_VERIFIED
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
