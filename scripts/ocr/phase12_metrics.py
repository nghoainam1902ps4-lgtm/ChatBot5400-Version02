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
    rehype-raw. ``list_prefixes=False`` leaves out what the renderer draws
    (numbers / bullets) to compare the text itself.
    """
    from markdown_it import MarkdownIt

    md = MarkdownIt("commonmark").enable("table")
    tokens = md.parse(markdown)
    lines: list[str] = []
    stack: list[list[Any]] = []  # [ordered, next_number]
    prefix_pending: list[str] = []
    row: list[str] = []
    in_cell = False
    for tok in tokens:
        t = tok.type
        if t == "ordered_list_open":
            stack.append([True, int(tok.attrGet("start") or 1)])
        elif t == "bullet_list_open":
            stack.append([False, 0])
        elif t in ("ordered_list_close", "bullet_list_close"):
            stack.pop()
        elif t == "list_item_open":
            ordered, number = stack[-1]
            if ordered:
                prefix_pending.append(f"{number}. " if list_prefixes else "")
                stack[-1][1] = number + 1
            else:
                prefix_pending.append("• " if list_prefixes else "")
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
            lines.append(f"{prefix}{text}".strip())
        elif t in ("th_open", "td_open"):
            in_cell = True
        elif t in ("th_close", "td_close"):
            in_cell = False
        elif t == "tr_close":
            lines.append(" | ".join(row))
            row = []
        elif t == "html_block":
            lines.append(tok.content.strip())
    return [line for line in lines if line]


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


def legal_display_markdown(markdown: str) -> str:
    """What the frontend does to a Legal-normalized Source before rendering it.

    Reference implementation of ``frontend/src/lib/utils/legal-display.ts``
    (both are checked against tests/fixtures/legal/display_escape_cases.json).
    A Legal source stores its clause markers as plain text ("9. ...", "- ...");
    at render time the leading marker of a line is escaped so that Markdown
    shows it literally instead of building a list (and renumbering it).
    Fenced code is left alone; applying it twice changes nothing.
    """
    out, in_fence = [], False
    for line in markdown.split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            m = _LIST_MARKER_ORDERED.match(line)
            if m:
                line = f"{m.group(1)}{m.group(2)}\\{m.group(3)}{line[m.end() :]}"
            else:
                m = _LIST_MARKER_BULLET.match(line)
                if m:
                    line = f"{m.group(1)}\\{line[len(m.group(1)) :]}"
        out.append(line)
    return "\n".join(out)


def expected_units(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    """The declared truth of a fixture, in reading order (never from an output).

    One unit per element: ``{"text", "gt", "page"}`` with gt in keep / artifact /
    join. Table rows are "a | b | c" (how a rendered table row reads); the OCR
    text inside a picture is required content; furniture is not expected.
    """
    units: list[dict[str, Any]] = []
    for page_no, page in enumerate(fixture["pages"], start=1):
        for el in page:
            gt = el.get("gt", "keep")
            if gt == "furniture":
                continue
            if el["label"] == "picture":
                for child in el.get("children", []):
                    units.append({"text": child["text"], "gt": "keep", "page": page_no})
            elif el["label"] == "table":
                for row in el["rows"]:
                    units.append(
                        {"text": " | ".join(row), "gt": "keep", "page": page_no}
                    )
            elif el.get("text"):
                units.append({"text": el["text"], "gt": gt, "page": page_no})
    return units


def _partitions(texts: list[str]) -> list[list[str]]:
    """Every way to render [keep, join, join...]: most joined first."""
    n = len(texts)
    out = []
    for mask in range(1 << (n - 1)):  # bit i set = break between i and i+1
        groups, cur = [], [texts[0]]
        for i in range(n - 1):
            if mask >> i & 1:
                groups.append(" ".join(cur))
                cur = [texts[i + 1]]
            else:
                cur.append(texts[i + 1])
        groups.append(" ".join(cur))
        out.append(groups)
    return sorted(out, key=len)


def _lis_length(seq: list[int]) -> int:
    import bisect

    tails: list[int] = []
    for x in seq:
        i = bisect.bisect_left(tails, x)
        if i == len(tails):
            tails.append(x)
        else:
            tails[i] = x
    return len(tails)


def preservation(
    fixture: dict[str, Any], lines: list[str], markdown: str = ""
) -> dict[str, Any]:
    """Compare what the reader sees (``lines``) with the fixture's declared truth.

    Nothing the normalizer reports is used. Counted separately:
      false_deletion      required units not shown as often as declared
      false_merge         a line made of two units that may not be joined
      false_insertion     lines that are neither declared content nor a declared artifact
      false_reordering    required units shown out of the declared order
    plus token counts of the same (multisets, so a repeated line removed twice
    counts twice), allowed outcomes (artifacts left / removed, joins made / not
    made) and exact-count checks of the critical fields.
    """
    from collections import Counter

    units = expected_units(fixture)
    content_lines = [(i, ln) for i, ln in enumerate(lines) if ln != PLACEHOLDER]
    free: dict[str, list[int]] = {}
    for i, ln in content_lines:
        free.setdefault(ln, []).append(i)

    def take(text: str) -> int | None:
        idx = free.get(text)
        return idx.pop(0) if idx else None

    runs: list[list[dict[str, Any]]] = []
    for u in units:
        if u["gt"] == "join" and runs and runs[-1][0]["gt"] == "keep":
            runs[-1].append(u)
        elif u["gt"] in ("keep", "join"):
            runs.append([u])
    missing: list[str] = []
    order: list[int] = []
    joins_made = joins_missed = 0
    for run in runs:
        texts = [u["text"] for u in run]
        done = False
        for forms in _partitions(texts):
            need = Counter(forms)
            if all(len(free.get(f, [])) >= c for f, c in need.items()):
                order.extend(i for i in (take(f) for f in forms) if i is not None)
                joins_made += len(texts) - len(forms)
                joins_missed += len(forms) - 1
                done = True
                break
        if not done:
            for t in texts:
                i = take(t)
                if i is None:
                    missing.append(t)
                else:
                    order.append(i)
    artifacts = Counter(u["text"] for u in units if u["gt"] == "artifact")
    artifacts_left = 0
    false_merges: list[str] = []
    false_insertions: list[str] = []
    unit_texts = {u["text"] for u in units if len(u["text"]) >= 3}
    for text, idxs in free.items():
        for _ in idxs:
            if artifacts[text] > 0:
                artifacts[text] -= 1
                artifacts_left += 1
            elif sum(1 for t in unit_texts if t != text and t in text) >= 2:
                false_merges.append(text)
            else:
                false_insertions.append(text)
    required_tokens: Counter[str] = Counter()
    for u in units:
        if u["gt"] != "artifact":
            required_tokens.update(u["text"].replace(" | ", " ").split())
    artifact_tokens: Counter[str] = Counter()
    for u in units:
        if u["gt"] == "artifact":
            artifact_tokens.update(u["text"].split())
    shown: Counter[str] = Counter()
    for _, ln in content_lines:
        shown.update(ln.replace(" | ", " ").split())
    deleted_tokens = sum((required_tokens - shown).values())
    inserted_tokens = sum(((shown - required_tokens) - artifact_tokens).values())
    text = " ".join(ln for _, ln in content_lines)
    critical = []
    for entry in fixture.get("protected", []):
        value, count = (
            (entry, 1) if isinstance(entry, str) else (entry[0], int(entry[1]))
        )
        found = max(text.count(value), markdown.count(value))
        critical.append(
            {"value": value, "expected": count, "found": found, "ok": found >= count}
        )
    table_units = [u["text"] for u in units if " | " in u["text"]]
    table_ok = all(t in lines for t in table_units)
    return {
        "required_units": len([u for u in units if u["gt"] != "artifact"]),
        "false_deletion": len(missing),
        "false_deletion_units": missing,
        "false_deletion_tokens": deleted_tokens,
        "false_merge": len(false_merges),
        "false_merge_lines": false_merges,
        "false_insertion": len(false_insertions),
        "false_insertion_lines": false_insertions,
        "false_insertion_tokens": inserted_tokens,
        "false_reordering": len(order) - _lis_length(order),
        "artifacts_declared": sum(1 for u in units if u["gt"] == "artifact"),
        "artifacts_left": artifacts_left,
        "joins_allowed": sum(1 for u in units if u["gt"] == "join"),
        "joins_made": joins_made,
        "joins_missed": joins_missed,
        "critical_fields": critical,
        "critical_ok": all(c["ok"] for c in critical),
        "table_rows": len(table_units),
        "tables_ok": table_ok,
        "placeholders": sum(1 for ln in lines if ln == PLACEHOLDER),
    }
