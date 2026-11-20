"""Phase 12 shared metrics: what the reader sees, and how close it is to the truth.

Used by the tests (tests/legal_harness.py re-exports these), by the quality
benchmark and by the local diagnostic scripts, so every report measures the
same way. Standard library + markdown-it-py (already installed with the app:
a dependency of ``rich``). No network, no file access.
"""

from __future__ import annotations

import re
from typing import Any

# --------------------------------------------------------------------------- #
# What the reader sees: CommonMark rendering, incl. browser list numbers
# --------------------------------------------------------------------------- #


def display_lines(markdown: str, list_prefixes: bool = True) -> list[str]:
    """Visible text blocks, in order, as a CommonMark + GFM-table renderer shows them.

    Ordered list items get the number the browser draws (``start`` + position),
    NOT the number written in the source; bullet items get "•"; raw HTML (e.g.
    ``<!-- image -->``) is shown literally, as react-markdown does without
    rehype-raw; the lines of a fenced / indented code block are shown too (the
    frontend renders them - Phase 12D9, D8-ORC-02). ``list_prefixes=False``
    leaves out what the renderer draws (numbers / bullets) to compare the text
    itself.
    """
    return [text for text, _ in display_lines_typed(markdown, list_prefixes)]


def display_lines_typed(
    markdown: str, list_prefixes: bool = True
) -> list[tuple[str, str]]:
    """``display_lines`` with the kind of block each line is: heading,
    paragraph, list_item, quote, table_row, code, html (Phase 12D9, D8-ORC-04)."""
    from markdown_it import MarkdownIt

    md = MarkdownIt("commonmark").enable("table")
    tokens = md.parse(markdown)
    out: list[tuple[str, str]] = []
    stack: list[list[Any]] = []  # [ordered, next_number]
    prefix_pending: list[str] = []
    row: list[str] = []
    in_cell = False
    heading = quote = items = 0
    for tok in tokens:
        t = tok.type
        if t == "ordered_list_open":
            stack.append([True, int(tok.attrGet("start") or 1)])
        elif t == "bullet_list_open":
            stack.append([False, 0])
        elif t in ("ordered_list_close", "bullet_list_close"):
            stack.pop()
        elif t == "list_item_open":
            items += 1
            ordered, number = stack[-1]
            if ordered:
                prefix_pending.append(f"{number}. " if list_prefixes else "")
                stack[-1][1] = number + 1
            else:
                prefix_pending.append("• " if list_prefixes else "")
        elif t == "list_item_close":
            items -= 1
        elif t == "heading_open":
            heading += 1
        elif t == "heading_close":
            heading -= 1
        elif t == "blockquote_open":
            quote += 1
        elif t == "blockquote_close":
            quote -= 1
        elif t == "inline":
            text = "".join(
                child.content
                if child.type in ("text", "code_inline", "html_inline")
                else (" " if child.type in ("softbreak", "hardbreak") else "")
                for child in (tok.children or [])
            )
            if in_cell:
                row.append(text.strip())
                continue
            prefix = "".join(prefix_pending)
            prefix_pending.clear()
            kind = (
                "quote"
                if quote
                else "heading"
                if heading
                else "list_item"
                if items
                else "paragraph"
            )
            out.append((f"{prefix}{text}".strip(), kind))
        elif t in ("th_open", "td_open"):
            in_cell = True
        elif t in ("th_close", "td_close"):
            in_cell = False
        elif t == "tr_close":
            out.append((" | ".join(row), "table_row"))
            row = []
        elif t == "html_block":
            out.append((tok.content.strip(), "html"))
        elif t in ("fence", "code_block"):
            for line in tok.content.splitlines():
                out.append((line.strip(), "code"))
    return [(text, kind) for text, kind in out if text]


def display_text(markdown: str, list_prefixes: bool = True) -> str:
    return " ".join(display_lines(markdown, list_prefixes))


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace(" | ", " ")).strip()


def levenshtein(a: list[Any] | str, b: list[Any] | str) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb))
            )
        previous = current
    return previous[-1]


def cer(reference: str, hypothesis: str) -> float:
    ref, hyp = _norm(reference), _norm(hypothesis)
    return levenshtein(ref, hyp) / max(1, len(ref))


def wer(reference: str, hypothesis: str) -> float:
    ref, hyp = _norm(reference).split(), _norm(hypothesis).split()
    return levenshtein(ref, hyp) / max(1, len(ref))


def word_recall(reference: str, hypothesis: str) -> float:
    from collections import Counter

    ref, hyp = Counter(_norm(reference).split()), Counter(_norm(hypothesis).split())
    total = sum(ref.values())
    return sum(min(n, hyp[w]) for w, n in ref.items()) / max(1, total)


def lost_words(before: str, after: str) -> int:
    """Words present in ``before`` and missing from ``after`` (multiset)."""
    from collections import Counter

    b, a = Counter(_norm(before).split()), Counter(_norm(after).split())
    return sum(max(0, n - a[w]) for w, n in b.items())


def markers_displayed(fixture: dict[str, Any], lines: list[str]) -> tuple[int, int]:
    """(expected markers displayed at a line start, expected markers)."""
    expected = fixture.get("markers") or []
    starts = [line.split(" ", 1)[0] for line in lines]
    remaining = list(starts)
    hit = 0
    for marker in expected:
        if marker in remaining:
            remaining.remove(marker)
            hit += 1
    return hit, len(expected)


def order_accuracy(fixture: dict[str, Any], text: str) -> float | None:
    phrases = fixture.get("order") or []
    if len(phrases) < 2:
        return None
    positions = [text.find(p) for p in phrases]
    pairs = list(zip(positions, positions[1:]))
    good = sum(1 for x, y in pairs if x != -1 and y != -1 and x < y)
    return good / len(pairs)


def renumbered_list_items(markdown: str) -> tuple[int, int]:
    """(ordered items whose drawn number differs from the source number, ordered items).

    CommonMark keeps only the first number of an ordered list; a browser then
    counts 1 by 1. markdown-it records each item's own source number in
    ``token.info``, so the difference is exactly what the reader is misled by.
    """
    from markdown_it import MarkdownIt

    tokens = MarkdownIt("commonmark").parse(markdown)
    stack: list[int | None] = []
    wrong = total = 0
    for tok in tokens:
        if tok.type == "ordered_list_open":
            stack.append(int(tok.attrGet("start") or 1))
        elif tok.type == "bullet_list_open":
            stack.append(None)
        elif tok.type in ("ordered_list_close", "bullet_list_close"):
            stack.pop()
        elif tok.type == "list_item_open" and stack and stack[-1] is not None:
            drawn = stack[-1]
            stack[-1] = drawn + 1
            total += 1
            if tok.info and tok.info.isdigit() and int(tok.info) != drawn:
                wrong += 1
    return wrong, total


PLACEHOLDER = "<!-- image -->"


def placeholder_count(markdown: str) -> int:
    return markdown.count(PLACEHOLDER)


def numeric_only_lines(lines: list[str]) -> int:
    return sum(1 for line in lines if re.fullmatch(r"[\d\s/\-–—]+", line or ""))


def page_boundary_report(
    pages_text: list[str], output: str, words: int = 3
) -> list[dict[str, Any]]:
    """For each page of a direct OCR, whether its last words reach the output.

    Answers "is the last word of the page lost, and where": run it once on the
    Docling output and once on the normalized output.
    """
    flat = " ".join(_norm(output).split())
    report = []
    for n, text in enumerate(pages_text, start=1):
        tail = _norm(text).split()[-words:]
        if not tail:
            continue
        phrase = " ".join(tail)
        report.append(
            {
                "page": n,
                "last_words_found": phrase in flat,
                "missing": [w for w in tail if w not in flat.split()],
            }
        )
    return report


# --------------------------------------------------------------------------- #
# Phase 12D3 (T-01): preservation oracle from DECLARED ground truth only
# --------------------------------------------------------------------------- #

_LIST_MARKER_ORDERED = re.compile(r"^(\s{0,3})(\d{1,9})([.)])(?=\s|$)")
_LIST_MARKER_BULLET = re.compile(r"^(\s{0,3})([-+*])(?=\s|$)")
_FENCE = re.compile(r"^\s{0,3}(```|~~~)")
_HEADING = re.compile(r"^(\s{0,3}#{1,6}\s+)(.*)$")
_THEMATIC_DASHES = re.compile(r"^(\s{0,3})-(?:\s*-){2,}\s*$")
_SERIALIZER_COMMENT = re.compile(r"^\s*<!--[^<>]*-->\s*$")  # <!-- image --> & co.
_ASCII_PUNCT = frozenset("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
# Characters Markdown (CommonMark + GFM tables / strikethrough / autolinks, and
# remark-math for "$") would read as syntax inside a line.
_INLINE_SPECIAL = frozenset("`*_[]~$<|")
# Entities the Legal serializer itself writes: "&lt;" (a "<" that would open
# HTML) and "&#124;" (a "|" inside a table cell, by Docling) - shown as "<" / "|".
_KEPT_ENTITIES = ("&lt;", "&#124;")


# A bare URL: GFM turns it into a link VERBATIM (escapes inside it would be
# displayed), so it is copied as it is; "_" / "&" inside it are literal anyway.
_URL = re.compile(r"(?:https?://|www\.)[^\s<>]*", re.IGNORECASE)


def _escape_inline(text: str, table: bool = False) -> str:
    """Backslash every Markdown-significant character of printed text, once."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        url = (
            _URL.match(text, i)
            if text[i] in "hHwW" and (i == 0 or not text[i - 1].isalnum())
            else None
        )
        if url and url.end() > i:
            out.append(url.group(0))
            i = url.end()
            continue
        c = text[i]
        if c == "\\":
            if i + 1 < n and text[i + 1] in _ASCII_PUNCT:
                out.append(text[i : i + 2])  # already an escape: idempotent
                i += 2
                continue
            out.append("\\\\")
        elif c == "&":
            out.append("&" if text.startswith(_KEPT_ENTITIES, i) else "\\&")
        elif c == "|" and table:
            out.append(c)
        elif c in _INLINE_SPECIAL:
            out.append("\\" + c)
        else:
            out.append(c)
        i += 1
    return "".join(out)


def legal_display_markdown(markdown: str) -> str:
    """What the frontend does to a Legal-normalized Source before rendering it.

    Reference implementation of ``frontend/src/lib/utils/legal-display.ts``
    (both are checked against tests/fixtures/legal/display_escape_cases.json).
    A Legal source stores the PRINTED text (Phase 12D5, F-17 / R2-02): clause
    markers ("9. ...", "- ..."), "*", "_", "`", "$", "[", "]", "~", "<", "&",
    "|" and "\\" exactly as on paper. At render time every such character of a
    text line is escaped so that Markdown shows it literally instead of building
    a list, emphasis, code, a link, a formula or HTML. Table rows keep their
    "|" cell separators, headings their "#" prefix, the serializer's own
    "<!-- image -->" placeholders and fenced code are left alone. Applying it
    twice changes nothing.
    """
    out, in_fence = [], False
    for line in markdown.split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence and line.strip() and not _SERIALIZER_COMMENT.match(line):
            if line.lstrip().startswith("|"):
                line = _escape_inline(line, table=True)
            elif _HEADING.match(line):
                m = _HEADING.match(line)
                assert m is not None
                line = m.group(1) + _escape_inline(m.group(2))
            else:
                m = _LIST_MARKER_ORDERED.match(line)
                b = _LIST_MARKER_BULLET.match(line)
                t = _THEMATIC_DASHES.match(line)
                if m:
                    line = f"{m.group(1)}{m.group(2)}\\{m.group(3)}" + _escape_inline(
                        line[m.end() :]
                    )
                elif b:
                    line = f"{b.group(1)}\\{b.group(2)}" + _escape_inline(
                        line[b.end() :]
                    )
                elif t:
                    line = f"{t.group(1)}\\{line[len(t.group(1)) :]}"
                else:
                    line = _escape_inline(line)
        out.append(line)
    return "\n".join(out)


# The oracle itself (Phase 12D5, findings R2-14 / T-01 / T-03): identity-based,
# see scripts/ocr/phase12_oracle.py. Re-exported here so that the tests, the
# benchmark and the local reports keep measuring the same way.
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from phase12_oracle import expected_units, preservation  # noqa: E402

__all__ = [
    "cer",
    "display_lines",
    "display_text",
    "expected_units",
    "legal_display_markdown",
    "levenshtein",
    "lost_words",
    "markers_displayed",
    "numeric_only_lines",
    "order_accuracy",
    "page_boundary_report",
    "placeholder_count",
    "preservation",
    "renumbered_list_items",
    "wer",
    "word_recall",
]
