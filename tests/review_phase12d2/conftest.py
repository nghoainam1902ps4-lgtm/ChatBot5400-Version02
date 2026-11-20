"""Phase 12D2 independent review: counter-example tests (review branch only).

These tests document findings of docs/review/PHASE12D2_FINDINGS.json. A test
marked ``xfail(strict=True)`` states the EXPECTED safe behaviour and fails
today; when Phase 12D3 fixes the finding the test starts passing, strict xfail
turns that into an error, and the marker must then be removed (the test becomes
the regression test). Runtime code is not modified by this review.
"""

from __future__ import annotations

import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parents[1]
ROOT = TESTS.parent
for p in (TESTS, ROOT / "scripts" / "offline"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
