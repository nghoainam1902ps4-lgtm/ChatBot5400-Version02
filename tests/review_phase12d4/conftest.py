"""Phase 12D4 re-review after remediation: counter-example and control tests.

Review branch only (review/phase12d4-fable-reaudit). Runtime code is NOT
modified by this review. Conventions, same as tests/review_phase12d2:

* a test marked ``xfail(strict=True)`` states the EXPECTED safe behaviour and
  fails today (finding R2-xx of docs/review/PHASE12D4_NEW_FINDINGS.json, or a
  Phase 12D2 finding that is only partially fixed). When a later phase fixes
  it, strict xfail turns the pass into an error and the marker must be removed;
* a test named ``test_verified_*`` / ``test_control_*`` passes and records
  something this review checked for itself.

Everything here is synthetic. No Docker daemon, no network, no real document.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTS = HERE.parent
ROOT = TESTS.parent
for p in (TESTS, ROOT / "scripts" / "offline", ROOT / "scripts" / "ocr", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
