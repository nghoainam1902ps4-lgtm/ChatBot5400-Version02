#!/usr/bin/env python3
"""Tesseract command wrapper: ignore low-confidence orientation detection (D-25).

Docling's ``TesseractOcrCliModel`` runs ``tesseract --psm 0 -l osd`` on every
OCR crop (a table, a paragraph…) and rotates the crop by whatever orientation
comes back, even when Tesseract itself reports a confidence close to zero. On
a tight crop that turns upright tables upside down.

This file is what ``TesseractCliOcrOptions.tesseract_cmd`` (an official Docling
option) points at. It is NOT an OCR engine and holds no OCR logic:

* orientation detection call (``--psm 0``): run the real Tesseract unchanged;
  when it reports a rotation with ``Orientation confidence`` below
  ``OCR_TESSERACT_OSD_MIN_CONFIDENCE`` (default 2.0), report 0 degrees instead;
* every other call (``--version``, ``--list-langs``, recognition): ``exec`` the
  real Tesseract with the arguments untouched.

Standard library only, started once per Tesseract call. The real binary comes
from ``OCR_TESSERACT_REAL`` (set by ``open_notebook.ocr.options``).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

REAL_ENV = "OCR_TESSERACT_REAL"
MIN_CONFIDENCE_ENV = "OCR_TESSERACT_OSD_MIN_CONFIDENCE"
# Measured on 1 340 crop orientations (docs/ocr/OCR_PHASE8C_REPORT.md): every
# wrong answer had a confidence <= 1.44; 2.0 leaves a margin.
DEFAULT_MIN_CONFIDENCE = 2.0

_ORIENTATION = re.compile(r"^(Orientation in degrees:\s*)(\d+)\s*$", re.MULTILINE)
_ROTATE = re.compile(r"^(Rotate:\s*)(\d+)\s*$", re.MULTILINE)
_CONFIDENCE = re.compile(r"^Orientation confidence:\s*([0-9.]+)\s*$", re.MULTILINE)


OSD_TIMEOUT_SECONDS = 120


def _is_self(real: str) -> bool:
    import shutil

    resolved = shutil.which(real) or real
    try:
        return os.path.samefile(resolved, __file__)
    except OSError:
        return False


def min_confidence() -> float:
    try:
        value = float(os.environ.get(MIN_CONFIDENCE_ENV, "") or DEFAULT_MIN_CONFIDENCE)
    except ValueError:
        return DEFAULT_MIN_CONFIDENCE
    # nan / inf / negative would silently gate everything or nothing
    return (
        value
        if value == value and 0 <= value < float("inf")
        else DEFAULT_MIN_CONFIDENCE
    )


def is_osd_call(args: list[str]) -> bool:
    """``--psm 0`` anywhere in the arguments = orientation and script detection."""
    return any(
        a == "--psm" and i + 1 < len(args) and args[i + 1] == "0"
        for i, a in enumerate(args)
    )


def parse_osd(output: str) -> tuple[int, float] | None:
    """(orientation in degrees, orientation confidence) from Tesseract's OSD text."""
    deg = _ORIENTATION.search(output)
    conf = _CONFIDENCE.search(output)
    if not deg or not conf:
        return None
    try:
        return int(deg.group(2)), float(conf.group(1))
    except ValueError:
        return None


def gate_osd(output: str, threshold: float) -> str:
    """Report "upright" when the detected rotation is below ``threshold``."""
    parsed = parse_osd(output)
    if parsed is None:
        if _ORIENTATION.search(output) and not _CONFIDENCE.search(output):
            # A rotation without a readable confidence is not trustworthy either.
            output = _ORIENTATION.sub(lambda m: f"{m.group(1)}0", output)
            return _ROTATE.sub(lambda m: f"{m.group(1)}0", output)
        return output
    degrees, confidence = parsed
    if degrees == 0 or confidence >= threshold:
        return output
    output = _ORIENTATION.sub(lambda m: f"{m.group(1)}0", output)
    return _ROTATE.sub(lambda m: f"{m.group(1)}0", output)


def main(argv: list[str]) -> int:
    real = os.environ.get(REAL_ENV) or "tesseract"
    if _is_self(real):
        # Misconfiguration (the "real" binary points back here): refuse instead
        # of spawning ourselves forever.
        sys.stderr.write(
            "tesseract_gate: OCR_TESSERACT_REAL points to the gate itself\n"
        )
        return 126
    if not is_osd_call(argv):
        os.execvp(real, [real, *argv])  # never returns
    try:
        proc = subprocess.run(  # noqa: S603 - fixed binary, arguments from Docling
            [real, *argv],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            check=False,
            timeout=OSD_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        # Docling treats a failed orientation call as "no rotation" and goes on.
        sys.stderr.write("tesseract_gate: orientation detection timed out\n")
        return 124
    sys.stderr.buffer.write(proc.stderr)
    out = proc.stdout
    if proc.returncode == 0:
        out = gate_osd(out.decode("utf-8", "replace"), min_confidence()).encode("utf-8")
    sys.stdout.buffer.write(out)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
