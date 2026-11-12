#!/usr/bin/env python3
"""Syntax-check every ```bash block in the OCR docs with `bash -n`.

    python scripts/ocr/check_doc_commands.py [docs/ocr/*.md ...]

Exit 1 and print the offending block when bash cannot parse it. (Syntax only:
it does not execute anything.)
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BLOCK = re.compile(r"```bash\n(.*?)```", re.S)


def check(path: Path) -> list[str]:
    errors = []
    for i, block in enumerate(BLOCK.findall(path.read_text(encoding="utf-8")), 1):
        proc = subprocess.run(
            ["bash", "-n"], input=block, text=True, capture_output=True
        )
        if proc.returncode != 0:
            errors.append(
                f"{path.relative_to(ROOT)} block {i}: {proc.stderr.strip()}\n{block}"
            )
    return errors


def main(argv: list[str]) -> int:
    files = [Path(a).resolve() for a in argv] or sorted(
        (ROOT / "docs" / "ocr").glob("*.md")
    )
    errors = [e for f in files for e in check(f)]
    for e in errors:
        print(e, file=sys.stderr)
    blocks = sum(len(BLOCK.findall(f.read_text(encoding="utf-8"))) for f in files)
    print(
        f"checked {blocks} bash blocks in {len(files)} files: {'OK' if not errors else f'{len(errors)} error(s)'}"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
