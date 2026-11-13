"""Minimal, lossless PDF preparation before Docling converts a scanned PDF (D-25).

Two things Docling 2.129 cannot be configured to do, both measured in
docs/ocr/OCR_PHASE8C_REPORT.md:

* Page orientation. Docling detects orientation per OCR crop, where Tesseract's
  detector is unreliable. Here it runs once per scanned page on the WHOLE page
  (reliable: correct answers had confidence >= 4.77, wrong ones <= 0.66) and a
  page that is confidently sideways / upside down gets its ``/Rotate`` entry
  corrected in a TEMPORARY copy. Nothing is re-rendered or re-compressed: the
  page content, images and text layer are byte-for-byte the same objects.
* OCR render scale. Docling renders OCR crops at 72 DPI x ``scale`` (default 3
  = 216 DPI). Up-sampling a 150 DPI JPEG scan costs Vietnamese diacritics, so
  the official ``OcrOptions.scale`` is lowered to the scan's own resolution
  (never raised above Docling's default).

The uploaded file is never modified. Anything that goes wrong here is logged
and the document is converted exactly as before.
"""

from __future__ import annotations

import os
import shutil
import statistics
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from open_notebook.ocr import paths
from open_notebook.ocr.tesseract_gate import parse_osd

DOCLING_DEFAULT_SCALE = 3.0
# Below 144 DPI the glyphs get too small for Tesseract: never go under 2.0.
MIN_SCALE = 2.0
# A page counts as a scan when one image covers at least this share of it.
SCAN_AREA_SHARE = 0.5
OSD_RENDER_SCALE = 3.0
OSD_MAX_SIDE_PX = 4000
OSD_TIMEOUT_SECONDS = 120
DEFAULT_PAGE_MIN_CONFIDENCE = 2.0
PAGE_MIN_CONFIDENCE_ENV = "OCR_PAGE_OSD_MIN_CONFIDENCE"
DISABLE_ENV = "OCR_PDF_PREP"


def enabled() -> bool:
    """On by default; ``OCR_PDF_PREP=false`` restores the previous behaviour."""
    return os.environ.get(DISABLE_ENV, "").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def page_min_confidence() -> float:
    try:
        return float(
            os.environ.get(PAGE_MIN_CONFIDENCE_ENV, "") or DEFAULT_PAGE_MIN_CONFIDENCE
        )
    except ValueError:
        return DEFAULT_PAGE_MIN_CONFIDENCE


@dataclass
class PdfPrep:
    """What to convert and how. ``path`` is None when the original is used."""

    path: str | None = None
    scale: float | None = None
    scan_dpi: float | None = None
    rotated_pages: dict[int, int] = field(default_factory=dict)
    _tmpdir: str | None = None

    def cleanup(self) -> None:
        if self._tmpdir:
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            self._tmpdir = None
            self.path = None

    def as_meta(self) -> dict[str, Any]:
        return {
            "ocr_scale": self.scale or DOCLING_DEFAULT_SCALE,
            "scan_dpi": self.scan_dpi,
            # 1-based page number -> clockwise degrees added to /Rotate
            "rotated_pages": {str(p + 1): r for p, r in self.rotated_pages.items()},
        }


def is_pdf(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            return b"%PDF-" in fh.read(1024)
    except OSError:
        return False


def scale_for_dpi(dpi: float | None) -> float | None:
    """``OcrOptions.scale`` for a scan resolution; None = keep Docling's default."""
    if not dpi or dpi <= 0:
        return None
    scale = max(MIN_SCALE, dpi / 72.0)
    if scale >= DOCLING_DEFAULT_SCALE:
        return None
    return round(scale, 4)


def _scan_dpi(page: Any) -> float | None:
    """Resolution of the image that makes this page a scan, else None."""
    import pypdfium2.raw as pdfium_c

    width, height = page.get_size()
    page_area = width * height
    if page_area <= 0:
        return None
    best: tuple[float, float] | None = None
    for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=3):
        left, bottom, right, top = obj.get_bounds()
        w_pt, h_pt = abs(right - left), abs(top - bottom)
        if w_pt <= 0 or h_pt <= 0:
            continue
        share = (w_pt * h_pt) / page_area
        if share < SCAN_AREA_SHARE:
            continue
        px_w, px_h = obj.get_px_size()
        # A rotated placement swaps the image axes; the larger pair is the truth.
        dpi = max(px_w, px_h) / (max(w_pt, h_pt) / 72.0)
        if best is None or share > best[0]:
            best = (share, dpi)
    return best[1] if best else None


def detect_page_rotation(
    image_path: str, tesseract_cmd: str, tessdata: str
) -> tuple[int, float] | None:
    """(clockwise degrees needed to make the page upright, confidence) or None."""
    proc = subprocess.run(  # noqa: S603 - fixed arguments, our own temp file
        [
            tesseract_cmd,
            "--tessdata-dir",
            tessdata,
            "--psm",
            "0",
            "-l",
            "osd",
            image_path,
            "stdout",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        check=False,
        timeout=OSD_TIMEOUT_SECONDS,
    )
    if proc.returncode != 0:
        return None  # e.g. "Too few characters": leave the page alone
    parsed = parse_osd(proc.stdout.decode("utf-8", "replace"))
    if parsed is None:
        return None
    orientation, confidence = parsed
    if orientation not in (0, 90, 180, 270):
        return None
    # Tesseract: "Orientation in degrees" o  <=>  "Rotate" (360 - o) clockwise.
    return (360 - orientation) % 360, confidence


def prepare(path: str, tesseract_cmd: str | None) -> PdfPrep:
    """Inspect ``path``; never raises (a failure means "convert it as it is")."""
    prep = PdfPrep()
    if not enabled() or not is_pdf(path):
        return prep
    try:
        _prepare(path, tesseract_cmd, prep)
    except Exception as e:  # corrupt / encrypted PDF, pdfium missing, …
        logger.warning(f"OCR PDF preparation skipped for {os.path.basename(path)}: {e}")
        prep.cleanup()
        return PdfPrep()
    return prep


def _prepare(path: str, tesseract_cmd: str | None, prep: PdfPrep) -> None:
    import pypdfium2 as pdfium

    tessdata = str(paths.tessdata_dir())
    threshold = page_min_confidence()
    # Orientation needs the Tesseract binary and its ``osd`` data (installed
    # with either Tesseract engine); without them pages are left as they are.
    can_detect = bool(tesseract_cmd) and (Path(tessdata) / "osd.traineddata").is_file()
    pdf = pdfium.PdfDocument(path)
    workdir = tempfile.mkdtemp(prefix="ocr-prep-")
    prep._tmpdir = workdir
    try:
        dpis: list[float] = []
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                dpi = _scan_dpi(page)
                if dpi is None:
                    continue  # born-digital page: nothing to do
                dpis.append(dpi)
                if not can_detect or not tesseract_cmd:
                    continue
                width, height = page.get_size()
                render_scale = min(
                    OSD_RENDER_SCALE, OSD_MAX_SIDE_PX / max(width, height, 1.0)
                )
                image_path = os.path.join(workdir, f"page-{index}.png")
                page.render(scale=render_scale, grayscale=True).to_pil().save(
                    image_path
                )
                found = detect_page_rotation(image_path, tesseract_cmd, tessdata)
                os.remove(image_path)
                if found and found[0] != 0 and found[1] >= threshold:
                    page.set_rotation((page.get_rotation() + found[0]) % 360)
                    prep.rotated_pages[index] = found[0]
            finally:
                page.close()
        if dpis:
            prep.scan_dpi = round(statistics.median(dpis), 1)
            prep.scale = scale_for_dpi(prep.scan_dpi)
        if prep.rotated_pages:
            # Same file name in a private directory: Docling names the document
            # after the file it is given.
            target = os.path.join(workdir, Path(path).name)
            pdf.save(target)
            prep.path = target
            logger.info(
                f"OCR page orientation: corrected page(s) "
                f"{sorted(p + 1 for p in prep.rotated_pages)} of "
                f"{os.path.basename(path)} in a temporary copy"
            )
    finally:
        pdf.close()
    if prep.path is None:
        prep.cleanup()
