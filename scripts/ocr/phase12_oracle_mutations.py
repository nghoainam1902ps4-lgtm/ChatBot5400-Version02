#!/usr/bin/env python3
"""Print / save the oracle's detection rate per injected defect class (Phase 12D5).

Runs the systematic negative controls of tests/test_phase12d5_oracle.py and
reports (found, total) for each class, e.g.::

  uv run python scripts/ocr/phase12_oracle_mutations.py --out docs/review/phase12d5/oracle_mutations.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out")
    args = p.parse_args(argv)
    import pytest

    sys.path.insert(0, str(ROOT / "tests"))
    rc = pytest.main(
        [
            str(ROOT / "tests" / "test_phase12d5_oracle.py"),
            "-q",
            "-p",
            "no:cacheprovider",
        ]
    )
    import test_phase12d5_oracle as T

    rows = {k: {"found": v[0], "total": v[1]} for k, v in sorted(T.DETECTION.items())}
    text = json.dumps(
        {"pytest_exit": int(rc), "detection": rows}, ensure_ascii=False, indent=2
    )
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
