#!/usr/bin/env python3
"""Standard parity after E0-07: classify every difference (Phase 12D7, section 9).

The approved rule: after the Docling TSV parser fix, Standard may differ from
v1.2.0 ONLY where the old parser rewrote a token Tesseract recognised. Every
other byte must be identical. This tool compares two Standard outputs of the
same documents (``--before`` = v1.2.0, ``--after`` = the candidate, one
``<name>.md`` per document in each folder) token by token and classifies each
changed hunk:

``unchanged``              identical text
``expected parser fix``    the old text is exactly what pandas made of the new
                           tokens (``0001`` -> ``1.0``, ``12.50`` -> ``12.5``,
                           ``NA`` / ``N/A`` dropped, ``true`` -> ``True``) AND
                           every new token is in the document's raw Tesseract
                           TSV (``--tsv``: ``<name>*.tsv`` files)
``not verified``           same shape as the parser fix, but no raw TSV proves
                           the new token (no TSV given, or token absent)
``unexpected regression``  anything else - a release blocker until explained

Nothing is uploaded; reads local files only and writes a JSON + Markdown report.
Usage::

  python scripts/ocr/phase12_standard_diff.py --before out/v120 --after out/cand \\
      --tsv out/diag --out out/standard-diff
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any, Optional

UNCHANGED = "unchanged"
EXPECTED = "expected parser fix"
NOT_VERIFIED = "not verified"
UNEXPECTED = "unexpected regression"

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


def old_parser_form(token: str) -> Optional[str]:
    """What Docling 2.129.0's TSV parse made of ``token`` in a crop of numbers
    (None = the word was dropped). Unchanged tokens return themselves."""
    if token in NA_WORDS:
        return None
    if token in ("true", "True", "TRUE"):
        return "True"
    if token in ("false", "False", "FALSE"):
        return "False"
    try:
        value = float(token)
    except ValueError:
        return token
    if token.strip() != token or "_" in token:
        return token  # pandas' parser does not take these as numbers
    return str(value)


def tokens(text: str) -> list[str]:
    return text.split()


def tsv_words(paths: list[Path]) -> set[str]:
    words: set[str] = set()
    for p in paths:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) >= 12 and parts[0] == "5" and parts[-1].strip():
                words.add(parts[-1])
    return words


def classify_hunk(old: list[str], new: list[str], evidence: Optional[set[str]]) -> str:
    if old == new:
        return UNCHANGED
    mangled = [m for m in (old_parser_form(t) for t in new) if m is not None]
    if mangled != old:
        return UNEXPECTED
    changed = [t for t in new if old_parser_form(t) != t]
    if evidence is not None and changed and all(t in evidence for t in changed):
        return EXPECTED
    return NOT_VERIFIED


def compare(before: str, after: str, evidence: Optional[set[str]]) -> dict[str, Any]:
    a, b = tokens(before), tokens(after)
    hunks = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(
        a=a, b=b, autojunk=False
    ).get_opcodes():
        if op == "equal":
            continue
        kind = classify_hunk(a[i1:i2], b[j1:j2], evidence)
        hunks.append(
            {
                "class": kind,
                "before": a[i1:i2][:20],
                "after": b[j1:j2][:20],
                "at_token": i1,
            }
        )
    if not hunks:
        verdict = UNCHANGED
    elif any(h["class"] == UNEXPECTED for h in hunks):
        verdict = UNEXPECTED
    elif any(h["class"] == NOT_VERIFIED for h in hunks):
        verdict = NOT_VERIFIED
    else:
        verdict = EXPECTED
    return {"class": verdict, "hunks": hunks, "byte_identical": before == after}


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--before", required=True, help="folder of v1.2.0 Standard outputs (*.md)"
    )
    p.add_argument(
        "--after", required=True, help="folder of candidate Standard outputs (*.md)"
    )
    p.add_argument("--tsv", help="folder of raw Tesseract TSV files (<name>*.tsv)")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    before, after = Path(args.before), Path(args.after)
    tsv_dir = Path(args.tsv) if args.tsv else None
    report: dict[str, Any] = {"schema": "chatbot5400-standard-diff/1", "documents": {}}
    names = sorted(
        {f.stem for f in before.glob("*.md")} | {f.stem for f in after.glob("*.md")}
    )
    for name in names:
        fa, fb = before / f"{name}.md", after / f"{name}.md"
        if not fa.is_file() or not fb.is_file():
            report["documents"][name] = {
                "class": NOT_VERIFIED,
                "reason": "missing on one side",
            }
            continue
        evidence = None
        if tsv_dir is not None:
            files = sorted(tsv_dir.rglob(f"{name}*.tsv"))
            evidence = tsv_words(files) if files else None
        report["documents"][name] = compare(
            fa.read_text(encoding="utf-8"), fb.read_text(encoding="utf-8"), evidence
        )
    counts: dict[str, int] = {}
    for doc in report["documents"].values():
        counts[doc["class"]] = counts.get(doc["class"], 0) + 1
    report["summary"] = counts
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "standard_diff.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    lines = [
        "# Standard parity after E0-07",
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
    (out / "standard_diff.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(counts, ensure_ascii=False))
    return 1 if counts.get(UNEXPECTED) else 0


if __name__ == "__main__":
    sys.exit(main())
