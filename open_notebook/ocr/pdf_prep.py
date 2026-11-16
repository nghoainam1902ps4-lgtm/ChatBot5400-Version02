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

* Visible text boxes over a scan (D-33, opt-in). Docling drops every OCR cell
  whose box touches the axis-aligned box of a VISIBLE PDF text cell. A diagonal
  watermark line is one such cell whose box spans most of the page, so the
  text recognised under it is discarded. ``overlay_scan`` measures that
  situation per page (scan image, oblique visible text boxes, ordinary visible
  text) and ``auto_full_page`` turns it into a per-document decision to use
  Docling's official full-page OCR mode. Nothing is removed from the PDF.

The uploaded file is never modified. Anything that goes wrong here is logged
and the document is converted exactly as before.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from functools import lru_cache
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
OSD_TIMEOUT_SECONDS = 30
# Orientation costs about one second per scanned page and runs before Docling:
# keep it bounded on very long scans (the remaining pages are left as they are).
DEFAULT_OSD_MAX_PAGES = 200
OSD_MAX_PAGES_ENV = "OCR_PAGE_OSD_MAX_PAGES"
# Wall-clock budget for the whole orientation step of ONE document. Measured:
# 0.55-0.65 s per scanned page on 8 CPUs, so the 200-page cap normally needs
# about 2.5 minutes. Without a total bound, 200 pages that each hit the 30 s
# page timeout would hold a job for 100 minutes before Docling starts (the
# worker has no job timeout). When the budget is spent the remaining pages are
# converted as they are; the page being checked may finish, so the hard bound
# is the budget plus one page timeout.
DEFAULT_OSD_BUDGET_SECONDS = 600.0
MAX_OSD_BUDGET_SECONDS = float(DEFAULT_OSD_MAX_PAGES * OSD_TIMEOUT_SECONDS)
OSD_BUDGET_ENV = "OCR_PAGE_OSD_BUDGET_SECONDS"
DEFAULT_PAGE_MIN_CONFIDENCE = 2.0
PAGE_MIN_CONFIDENCE_ENV = "OCR_PAGE_OSD_MIN_CONFIDENCE"
DISABLE_ENV = "OCR_PDF_PREP"

# --- automatic full-page OCR for scans under a visible text box (D-33) --------
# Opt-in: unset / anything but true keeps the behaviour of earlier versions.
AUTO_FULL_PAGE_ENV = "OCR_AUTO_FULL_PAGE_ON_WATERMARK"
# A visible text object is a "tilted box" when its bounding box is at least
# this many times larger than the cells of its own characters. Text parallel
# to a page axis measures exactly 1.0 whatever its size; a line tilted by 2
# degrees already measures 3, a diagonal watermark 10-15.
OVERLAY_BOX_INFLATION = 1.5
# ... and its baseline is at least this far (degrees) from both page axes. A
# guard against odd fonts only: the inflation above is what really decides.
DEFAULT_OVERLAY_MIN_ANGLE_DEG = 1.0
OVERLAY_MIN_ANGLE_ENV = "OCR_AUTO_FULL_PAGE_MIN_ANGLE"
# Share of the page that tilted boxes must claim ON TOP OF an image, outside
# every visible character, before the page counts as at risk. Measured in
# Phase 10G: the share of the page text Docling discards is about twice this
# value (a 3.6% box lost 8% of the words, 14% lost 27%, 58% lost 96%).
DEFAULT_OVERLAY_MIN_COVERAGE = 0.02
OVERLAY_MIN_COVERAGE_ENV = "OCR_AUTO_FULL_PAGE_MIN_COVERAGE"
# A page with at least this many ordinary (not tilted) visible characters, and
# more of them than hidden ones, carries its content in the PDF text layer:
# Docling keeps that text, nothing is lost, and re-reading it by OCR would
# only make it worse (measured: 1-2% of the words of a digital page).
DEFAULT_OVERLAY_TEXT_PAGE_CHARS = 400
OVERLAY_TEXT_PAGE_CHARS_ENV = "OCR_AUTO_FULL_PAGE_TEXT_PAGE_CHARS"
# PDF text render modes that paint nothing (a hidden OCR layer).
_INVISIBLE_TEXT_MODES = (3, 7)
_OVERLAY_OBJECT_DEPTH = 8
# The check reads an UNTRUSTED upload before Docling does. It is bounded like the
# orientation step: past any of these limits it gives up and the document is
# converted with its configured mode (reason "check_failed").
OVERLAY_MAX_PAGES = 2000  # pages of one document
OVERLAY_MAX_PAGE_OBJECTS = 20_000  # image / text objects enumerated on one page
OVERLAY_MAX_PAGE_CHARS = 100_000  # characters read on one page
OVERLAY_BUDGET_SECONDS = 20.0  # wall clock for the whole document
_OVERLAY_PAGE_WARNINGS = 3  # unreadable pages reported one by one


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
        value = float(
            os.environ.get(PAGE_MIN_CONFIDENCE_ENV, "") or DEFAULT_PAGE_MIN_CONFIDENCE
        )
    except ValueError:
        return DEFAULT_PAGE_MIN_CONFIDENCE
    # nan / inf / negative would silently switch the check off or on
    return value if math.isfinite(value) and value >= 0 else DEFAULT_PAGE_MIN_CONFIDENCE


def osd_max_pages() -> int:
    try:
        value = int(os.environ.get(OSD_MAX_PAGES_ENV, "") or DEFAULT_OSD_MAX_PAGES)
    except ValueError:
        return DEFAULT_OSD_MAX_PAGES
    return value if value >= 0 else DEFAULT_OSD_MAX_PAGES


def osd_budget_seconds() -> float:
    try:
        value = float(os.environ.get(OSD_BUDGET_ENV, "") or DEFAULT_OSD_BUDGET_SECONDS)
    except ValueError:
        return DEFAULT_OSD_BUDGET_SECONDS
    # nan / inf / zero / negative must never remove the bound or skip every page
    if not math.isfinite(value) or value <= 0:
        return DEFAULT_OSD_BUDGET_SECONDS
    return min(value, MAX_OSD_BUDGET_SECONDS)


_now = time.monotonic


@dataclass
class PdfPrep:
    """What to convert and how. ``path`` is None when the original is used."""

    path: str | None = None
    scale: float | None = None
    scan_dpi: float | None = None
    rotated_pages: dict[int, int] = field(default_factory=dict)
    # ok | disabled | tesseract_missing | osd_data_missing | not_a_pdf | skipped
    orientation: str = "skipped"
    # Scanned pages whose orientation was really checked, and why the others
    # were not: None | "max_pages" | "time_budget".
    orientation_checked: int = 0
    orientation_limit: str | None = None
    # The OCR mode of this document (D-33); set by docling_extract.
    mode: Any = None
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
            # Whether orientation correction was able to run for this document.
            "page_orientation": self.orientation,
            "orientation_checked_pages": self.orientation_checked,
            # Set when some scanned pages were left unchecked (page cap / time budget).
            "page_orientation_limit": self.orientation_limit,
            # Configured / effective OCR mode (nothing while the feature is off).
            **(self.mode.as_meta() if self.mode is not None else {}),
        }


def orientation_status(tesseract_cmd: str | None) -> dict[str, Any]:
    """Whether page-orientation correction will really run (UI, logs, readiness).

    ``available`` is only true when everything it needs is present: it is never
    reported as working because of configuration alone, and nothing is ever
    downloaded or installed to make it work.
    """
    is_enabled = enabled()
    has_cmd = bool(tesseract_cmd)
    has_osd = (paths.tessdata_dir() / "osd.traineddata").is_file()
    if not is_enabled:
        reason = "disabled"
    elif not has_cmd:
        reason = "tesseract_missing"
    elif not has_osd:
        reason = "osd_data_missing"
    else:
        reason = "ok"
    return {
        "enabled": is_enabled,
        "available": is_enabled and has_cmd and has_osd,
        "reason": reason,
        "min_confidence": page_min_confidence(),
        "max_pages": osd_max_pages(),
        "time_budget_seconds": osd_budget_seconds(),
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


def _page_rotation(
    page: Any, index: int, workdir: str, tesseract_cmd: str, tessdata: str
) -> tuple[int, float] | None:
    image_path = os.path.join(workdir, f"page-{index}.png")
    try:
        with _pdfium_lock():
            width, height = page.get_size()
            render_scale = min(
                OSD_RENDER_SCALE, OSD_MAX_SIDE_PX / max(width, height, 1.0)
            )
            image = page.render(scale=render_scale, grayscale=True).to_pil()
        image.save(image_path)
        # The Tesseract call runs outside the lock: it does not touch pdfium.
        return detect_page_rotation(image_path, tesseract_cmd, tessdata)
    finally:
        if os.path.exists(image_path):
            os.remove(image_path)


def _pdfium_lock() -> Any:
    """Docling's own lock for pdfium, which is not thread-safe.

    The worker converts one document at a time on its event loop, but an
    engine test runs a Docling conversion in a thread of the same process:
    this module must not use pdfium while Docling does.
    """
    try:
        from docling.utils.locks import pypdfium2_lock

        return pypdfium2_lock
    except Exception:  # Docling not installed: nothing else uses pdfium
        return _FALLBACK_LOCK


_FALLBACK_LOCK = threading.Lock()


# --- visible text boxes over scanned pages (D-33) -----------------------------


def auto_full_page_enabled() -> bool:
    """Off by default; ``OCR_AUTO_FULL_PAGE_ON_WATERMARK=true`` switches it on."""
    return os.environ.get(AUTO_FULL_PAGE_ENV, "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


_ignored_env_values: set[tuple[str, str]] = set()


def _env_number(name: str, default: float, low: float, high: float) -> float:
    raw = os.environ.get(name, "")
    try:
        value = float(raw or default)
    except ValueError:
        value = math.nan
    if math.isfinite(value) and low <= value <= high:
        return value
    if (name, raw) not in _ignored_env_values:  # once, not for every page
        _ignored_env_values.add((name, raw))
        logger.warning(
            f"{name}={raw!r} is not a number between {low:g} and {high:g}; "
            f"using the default {default:g}"
        )
    return default


def overlay_min_angle() -> float:
    return _env_number(OVERLAY_MIN_ANGLE_ENV, DEFAULT_OVERLAY_MIN_ANGLE_DEG, 0.1, 45.0)


def overlay_min_coverage() -> float:
    return _env_number(
        OVERLAY_MIN_COVERAGE_ENV, DEFAULT_OVERLAY_MIN_COVERAGE, 0.001, 1.0
    )


def overlay_text_page_chars() -> int:
    return int(
        _env_number(
            OVERLAY_TEXT_PAGE_CHARS_ENV, DEFAULT_OVERLAY_TEXT_PAGE_CHARS, 1, 1_000_000
        )
    )


@dataclass
class PageOverlay:
    """Measurements of one page (geometry and counts only, never any text)."""

    page: int  # 1-based
    image_share: float = 0.0  # share of the page covered by images
    visible_objects: int = 0  # text objects that paint ink
    invisible_objects: int = 0  # hidden OCR layer objects
    # Visible text objects whose box is much larger than their own characters.
    tilted_boxes: int = 0
    tilted_chars: int = 0
    # Share of the page those boxes claim on top of an image where no visible
    # character lies: there Docling discards OCR text for nothing.
    conflict_share: float = 0.0
    # Share of the page they claim on top of an image where visible characters
    # DO lie. Boxes that are more filled than empty are lines of text.
    filled_share: float = 0.0
    max_box_share: float = 0.0  # largest single tilted box
    max_inflation: float = 0.0  # largest box / own character cells
    angles: tuple[int, ...] = ()  # distinct tilts, degrees from the nearest axis
    # Visible characters of ordinary (not tilted) text and characters of the
    # hidden layer; None = not counted (the page is not a scan and no other
    # page is at risk).
    ordinary_chars: int | None = None
    invisible_chars: int | None = None

    def is_scan(self) -> bool:
        return self.image_share >= SCAN_AREA_SHARE

    def text_chars(self) -> int:
        """Visible characters that are the page's own text.

        Tilted text counts too when its boxes are more filled with visible
        characters than empty: a visible text layer over a skewed scan is the
        text of the page, not an overlay on top of it.
        """
        dense = self.filled_share >= self.conflict_share
        return (self.ordinary_chars or 0) + (self.tilted_chars if dense else 0)

    def is_text_page(self) -> bool:
        """The page content is ordinary visible PDF text."""
        chars = self.text_chars()
        return chars >= overlay_text_page_chars() and chars > (
            self.invisible_chars or 0
        )

    def at_risk(self) -> bool:
        """A scan whose recognised text Docling would discard under a tilted box."""
        return (
            self.is_scan()
            and self.conflict_share >= overlay_min_coverage()
            and not self.is_text_page()
        )


@dataclass
class OverlayScan:
    """Per-document result of ``overlay_scan`` (safe to log: numbers only)."""

    status: str = "ok"  # ok | not_a_pdf | error
    pages: int = 0
    scan_pages: int = 0
    risk_pages: list[int] = field(default_factory=list)  # 1-based
    # Pages whose content is ordinary visible PDF text. Only looked for when a
    # page is at risk, and only until the first one is found.
    text_pages: list[int] = field(default_factory=list)
    max_conflict_share: float = 0.0
    max_box_share: float = 0.0
    max_inflation: float = 0.0
    angles: tuple[int, ...] = ()
    details: list[PageOverlay] = field(default_factory=list)

    @property
    def decision(self) -> str:
        """full_page | mixed | none."""
        if not self.risk_pages:
            return "none"
        return "mixed" if self.text_pages else "full_page"


Box = tuple[float, float, float, float]  # left, bottom, right, top (PDF points)


def _union_share(
    boxes: list[Box],
    width: float,
    height: float,
    within: list[Box] | None = None,
    without: list[Box] | None = None,
) -> float:
    """Share of the page covered by the union of ``boxes``, optionally only
    where one of ``within`` also lies and none of ``without`` does."""
    if not boxes or width <= 0 or height <= 0:
        return 0.0
    import numpy as np

    step = max(1.0, max(width, height) / 1000.0)  # at most ~1000 cells per side
    cols, rows = int(math.ceil(width / step)), int(math.ceil(height / step))

    def raster(items: list[Box]) -> Any:
        grid = np.zeros((rows, cols), dtype=bool)
        for left, bottom, right, top in items:
            x0, x1 = sorted((left, right))
            y0, y1 = sorted((bottom, top))
            c0, c1 = max(0, int(x0 / step)), min(cols, int(math.ceil(x1 / step)))
            r0, r1 = max(0, int(y0 / step)), min(rows, int(math.ceil(y1 / step)))
            if c1 > c0 and r1 > r0:
                grid[r0:r1, c0:c1] = True
        return grid

    covered = raster(boxes)
    if within is not None:
        covered &= raster(within)
    if without:
        covered &= ~raster(without)
    return round(float(covered.mean()), 4)


class _OverlayLimit(Exception):
    """A bound of the overlay check was exceeded (the message has numbers only)."""


def _check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() > deadline:
        raise _OverlayLimit(f"more than {OVERLAY_BUDGET_SECONDS:g} s")


def _page_overlay(
    page: Any, number: int, count_text: bool, deadline: float | None = None
) -> PageOverlay:
    """Measure one page. ``count_text`` also reads the characters of a page that
    is not a scan (needed only to recognise a digital text page)."""
    import ctypes

    import pypdfium2.raw as pdfium_c

    out = PageOverlay(page=number)
    # Object bounds and character boxes are in the page's own, UNROTATED user
    # space, whose visible part is the page box — it need not start at (0, 0).
    # (page.get_size() is the size after /Rotate: wrong frame for these boxes.)
    left, bottom, right, top = page.get_bbox()
    width, height = right - left, top - bottom
    if not (math.isfinite(width) and math.isfinite(height)):
        return out
    if width <= 0 or height <= 0:
        return out

    def local(box: Box) -> Box:
        return (box[0] - left, box[1] - bottom, box[2] - left, box[3] - bottom)

    images: list[Box] = []
    for seen, obj in enumerate(
        page.get_objects(
            filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE, pdfium_c.FPDF_PAGEOBJ_TEXT],
            max_depth=_OVERLAY_OBJECT_DEPTH,
        ),
        start=1,
    ):
        if seen > OVERLAY_MAX_PAGE_OBJECTS:
            raise _OverlayLimit(
                f"page {number} has more than {OVERLAY_MAX_PAGE_OBJECTS} objects"
            )
        if seen % 512 == 0:
            _check_deadline(deadline)
        if obj.type == pdfium_c.FPDF_PAGEOBJ_IMAGE:
            images.append(local(obj.get_bounds()))
        elif pdfium_c.FPDFTextObj_GetTextRenderMode(obj.raw) in _INVISIBLE_TEXT_MODES:
            out.invisible_objects += 1
        else:
            out.visible_objects += 1
    out.image_share = _union_share(images, width, height)
    if not out.visible_objects:
        out.ordinary_chars = 0
        return out  # a hidden layer alone never hides OCR text
    if not out.is_scan() and not count_text:
        return out  # geometry only matters on top of a scan

    # Character level: page coordinates, also for text drawn through a form.
    textpage = page.get_textpage()
    try:
        raw_page = textpage.raw
        # object -> [left, bottom, right, top, characters, cell area, angle]
        groups: dict[int, list[float]] = {}
        visible_by_object: dict[int, bool] = {}
        cells: list[Box] = []  # the cell of every visible character
        invisible_chars = 0
        rect = pdfium_c.FS_RECTF()
        total_chars = pdfium_c.FPDFText_CountChars(raw_page)
        if total_chars > OVERLAY_MAX_PAGE_CHARS:
            raise _OverlayLimit(
                f"page {number} has more than {OVERLAY_MAX_PAGE_CHARS} characters"
            )
        for i in range(total_chars):
            if i % 2048 == 2047:
                _check_deadline(deadline)
            obj = pdfium_c.FPDFText_GetTextObject(raw_page, i)
            if not obj:
                continue  # a separator pdfium generated, not in the file
            key = ctypes.cast(obj, ctypes.c_void_p).value or 0
            visible = visible_by_object.get(key)
            if visible is None:
                visible = visible_by_object[key] = (
                    pdfium_c.FPDFTextObj_GetTextRenderMode(obj)
                    not in _INVISIBLE_TEXT_MODES
                )
            inked = pdfium_c.FPDFText_GetUnicode(raw_page, i) > 32
            if not visible:
                invisible_chars += inked
                continue
            if not pdfium_c.FPDFText_GetLooseCharBox(raw_page, i, rect):
                continue
            cell = local((rect.left, rect.bottom, rect.right, rect.top))
            area = abs(cell[2] - cell[0]) * abs(cell[3] - cell[1])
            if area <= 0:
                continue
            cells.append(cell)
            group = groups.get(key)
            if group is None:
                angle = pdfium_c.FPDFText_GetCharAngle(raw_page, i)
                group = groups[key] = [
                    *cell,
                    0.0,
                    0.0,
                    math.degrees(angle) if angle >= 0 else 0.0,
                ]
            group[0] = min(group[0], cell[0])
            group[1] = min(group[1], cell[1])
            group[2] = max(group[2], cell[2])
            group[3] = max(group[3], cell[3])
            group[4] += inked
            group[5] += area
    finally:
        textpage.close()

    min_angle = overlay_min_angle()
    tilted: list[Box] = []
    angles: set[int] = set()
    ordinary = 0
    page_area = width * height
    for x0, y0, x1, y1, chars, cell_area, angle in groups.values():
        tilt = angle % 90.0
        tilt = min(tilt, 90.0 - tilt)  # distance from the nearest page axis
        inflation = (x1 - x0) * (y1 - y0) / cell_area if cell_area > 0 else 1.0
        if tilt < min_angle or inflation < OVERLAY_BOX_INFLATION or chars < 2:
            ordinary += int(chars)
            continue
        box = (max(0.0, x0), max(0.0, y0), min(width, x1), min(height, y1))
        if box[2] <= box[0] or box[3] <= box[1]:
            continue  # entirely off the page
        tilted.append(box)
        angles.add(int(round(tilt)))
        out.tilted_chars += int(chars)
        out.max_inflation = max(out.max_inflation, round(inflation, 2))
        out.max_box_share = max(
            out.max_box_share,
            round((box[2] - box[0]) * (box[3] - box[1]) / page_area, 4),
        )
    out.ordinary_chars = ordinary
    out.invisible_chars = invisible_chars
    out.tilted_boxes = len(tilted)
    out.angles = tuple(sorted(angles))
    out.conflict_share = _union_share(
        tilted, width, height, within=images, without=cells
    )
    if out.conflict_share > 0:
        claimed = _union_share(tilted, width, height, within=images)
        out.filled_share = round(max(0.0, claimed - out.conflict_share), 4)
    return out


def _overlay_scan(path: str) -> OverlayScan:
    """Measure the document within fixed bounds (pages, objects, characters,
    time). Past a bound the result is ``status="error"``: the caller keeps the
    configured OCR mode, exactly as when the file cannot be read."""
    import pypdfium2 as pdfium

    scan = OverlayScan()
    lock = _pdfium_lock()
    deadline = time.monotonic() + OVERLAY_BUDGET_SECONDS
    unreadable = 0
    with lock:
        pdf = pdfium.PdfDocument(path)
    try:
        with lock:
            scan.pages = len(pdf)
        if scan.pages > OVERLAY_MAX_PAGES:
            raise _OverlayLimit(f"more than {OVERLAY_MAX_PAGES} pages")

        def measure(index: int, count_text: bool) -> PageOverlay | None:
            nonlocal unreadable
            _check_deadline(deadline)
            try:
                with lock:  # per page: never held across the whole document
                    page = pdf[index]
                    try:
                        return _page_overlay(page, index + 1, count_text, deadline)
                    finally:
                        page.close()
            except _OverlayLimit:
                raise
            except Exception as e:  # one unreadable page must not undo the others
                unreadable += 1
                if unreadable <= _OVERLAY_PAGE_WARNINGS:
                    logger.warning(
                        f"OCR overlay check skipped page {index + 1}: "
                        f"{type(e).__name__}"
                    )
                return None

        pending: list[int] = []  # digital pages whose characters were not read
        for index in range(scan.pages):
            info = measure(index, count_text=False)
            if info is None:
                continue
            scan.details.append(info)
            if info.is_scan():
                scan.scan_pages += 1
            if info.at_risk():
                scan.risk_pages.append(info.page)
                scan.max_conflict_share = max(
                    scan.max_conflict_share, info.conflict_share
                )
                scan.max_box_share = max(scan.max_box_share, info.max_box_share)
                scan.max_inflation = max(scan.max_inflation, info.max_inflation)
                scan.angles = tuple(sorted(set(scan.angles) | set(info.angles)))
            elif info.ordinary_chars is None:
                pending.append(index)
            elif info.is_text_page():
                scan.text_pages.append(info.page)
        if scan.risk_pages and not scan.text_pages:
            # Is this a mixed document? Stop at the first digital text page.
            for index in pending:
                info = measure(index, count_text=True)
                if info is not None and info.is_text_page():
                    scan.text_pages.append(info.page)
                    break
    except _OverlayLimit as e:
        # Numbers only. Cached like any result, so the routing decision and the
        # conversion of one upload do not both pay for it.
        logger.warning(f"OCR overlay check stopped: {e}")
        return OverlayScan(status="error", pages=scan.pages)
    finally:
        if unreadable > _OVERLAY_PAGE_WARNINGS:
            logger.warning(
                f"OCR overlay check skipped {unreadable} unreadable pages in total"
            )
        with lock:
            pdf.close()
    return scan


@lru_cache(maxsize=16)
def _overlay_scan_cached(
    path: str, size: int, mtime_ns: int, settings: tuple[float, float, int, float]
) -> OverlayScan:
    return _overlay_scan(path)


def overlay_scan(path: str) -> OverlayScan:
    """Measure every page of ``path``; never raises.

    Cached per (file, thresholds): the routing decision and the conversion of
    one upload ask the same question a moment apart.
    """
    if not is_pdf(path):
        return OverlayScan(status="not_a_pdf")
    try:
        st = os.stat(path)
        return _overlay_scan_cached(
            path,
            st.st_size,
            st.st_mtime_ns,
            (
                overlay_min_angle(),
                overlay_min_coverage(),
                overlay_text_page_chars(),
                OVERLAY_BOX_INFLATION,
            ),
        )
    except Exception as e:  # corrupt / encrypted PDF, pdfium missing, …
        # The type only: an OSError message carries the file path.
        logger.warning(f"OCR overlay check skipped: {type(e).__name__}")
        return OverlayScan(status="error")


MODE_DEFAULT = "default"
MODE_FULL_PAGE = "full_page"
# Why a document got its OCR mode (log / metadata; never contains document text).
REASON_FLAG_OFF = "flag_off"
REASON_OCR_DISABLED = "ocr_disabled"
REASON_MANUAL = "manual_full_page"
REASON_NOT_A_PDF = "not_a_pdf"
REASON_CHECK_FAILED = "check_failed"
REASON_NO_RISK = "no_risk"
REASON_MIXED = "mixed_document"
REASON_TILTED_TEXT = "tilted_text_box_over_scan"


@dataclass(frozen=True)
class OcrModeDecision:
    """The OCR mode one document is converted with, and why (D-33)."""

    configured: str = MODE_DEFAULT  # what the administrator saved
    effective: str = MODE_DEFAULT  # what this document really gets
    triggered: bool = False  # the automatic rule switched it to full page
    reason: str = REASON_FLAG_OFF
    scan: OverlayScan | None = None  # the measurements, when the check ran

    @property
    def evaluated(self) -> bool:
        return self.scan is not None and self.scan.status == "ok"

    def as_meta(self) -> dict[str, Any]:
        """Numbers only. Empty while the feature is switched off."""
        if self.reason == REASON_FLAG_OFF:
            return {}
        meta: dict[str, Any] = {
            "ocr_mode_configured": self.configured,
            "ocr_mode_effective": self.effective,
            "auto_full_page": self.triggered,
            "auto_full_page_reason": self.reason,
        }
        if self.evaluated and self.scan is not None:
            meta.update(
                auto_full_page_pages=self.scan.pages,
                auto_full_page_scan_pages=self.scan.scan_pages,
                auto_full_page_risk_pages=len(self.scan.risk_pages),
                auto_full_page_text_pages=len(self.scan.text_pages),
                auto_full_page_max_coverage=self.scan.max_conflict_share,
                auto_full_page_max_box=self.scan.max_box_share,
                auto_full_page_max_inflation=self.scan.max_inflation,
                auto_full_page_angles=list(self.scan.angles),
            )
        return meta

    def describe(self, engine: str) -> str:
        """One log line: engine, modes, reason and the ratios behind it."""
        line = (
            f"OCR mode: engine={engine} configured={self.configured} "
            f"effective={self.effective} auto_full_page={self.triggered} "
            f"reason={self.reason}"
        )
        if self.evaluated and self.scan is not None:
            line += (
                f" pages={self.scan.pages} scan_pages={self.scan.scan_pages} "
                f"risk_pages={len(self.scan.risk_pages)} "
                f"text_pages={len(self.scan.text_pages)} "
                f"max_coverage={self.scan.max_conflict_share} "
                f"max_box={self.scan.max_box_share} "
                f"max_inflation={self.scan.max_inflation} "
                f"angles={list(self.scan.angles)} "
                f"(thresholds: scan>={SCAN_AREA_SHARE}, "
                f"coverage>={overlay_min_coverage()}, "
                f"box_inflation>={OVERLAY_BOX_INFLATION}, "
                f"angle>={overlay_min_angle()}, "
                f"text_page_chars>={overlay_text_page_chars()})"
            )
        return line


def decide_ocr_mode(
    path: str, ocr_enabled: bool, force_full_page: bool
) -> OcrModeDecision:
    """Which OCR mode ``path`` is converted with. Never raises, never writes.

    The saved Force Full Page setting always wins when it is on. When it is
    off, the opt-in rule (``OCR_AUTO_FULL_PAGE_ON_WATERMARK``) may use full-page
    OCR for THIS document only: every page at risk is a scan under tilted
    visible text boxes, and no page carries its content as ordinary PDF text.
    A document that mixes both kinds keeps its configured mode (Docling has
    one OCR mode per document) and a warning is logged by the caller.
    """
    configured = MODE_FULL_PAGE if force_full_page else MODE_DEFAULT
    if not auto_full_page_enabled():
        # Feature off: nothing is analysed, logged or added to the metadata.
        return OcrModeDecision(configured, configured, False, REASON_FLAG_OFF)
    if not ocr_enabled:
        return OcrModeDecision(configured, configured, False, REASON_OCR_DISABLED)
    if force_full_page:
        return OcrModeDecision(configured, MODE_FULL_PAGE, False, REASON_MANUAL)
    scan = overlay_scan(path)
    if scan.status == "not_a_pdf":
        return OcrModeDecision(configured, configured, False, REASON_NOT_A_PDF, scan)
    if scan.status != "ok":
        return OcrModeDecision(configured, configured, False, REASON_CHECK_FAILED, scan)
    if scan.decision == "full_page":
        return OcrModeDecision(
            configured, MODE_FULL_PAGE, True, REASON_TILTED_TEXT, scan
        )
    reason = REASON_MIXED if scan.decision == "mixed" else REASON_NO_RISK
    return OcrModeDecision(configured, configured, False, reason, scan)


def prepare(path: str, tesseract_cmd: str | None) -> PdfPrep:
    """Inspect ``path``; never raises (a failure means "convert it as it is")."""
    prep = PdfPrep()
    if not enabled():
        prep.orientation = "disabled"
        return prep
    if not is_pdf(path):
        prep.orientation = "not_a_pdf"
        return prep
    prep.orientation = orientation_status(tesseract_cmd)["reason"]
    try:
        _prepare(path, tesseract_cmd, prep)
    except Exception as e:  # corrupt / encrypted PDF, pdfium missing, …
        logger.warning(f"OCR PDF preparation skipped for {os.path.basename(path)}: {e}")
        prep.cleanup()
        return PdfPrep(orientation="skipped")
    return prep


def _prepare(path: str, tesseract_cmd: str | None, prep: PdfPrep) -> None:
    import pypdfium2 as pdfium

    tessdata = str(paths.tessdata_dir())
    threshold = page_min_confidence()
    # Orientation needs the Tesseract binary and its ``osd`` data (installed
    # with either Tesseract engine); without them pages are left as they are.
    can_detect = bool(tesseract_cmd) and (Path(tessdata) / "osd.traineddata").is_file()
    lock = _pdfium_lock()  # held per pdfium call, never across Tesseract
    workdir = tempfile.mkdtemp(prefix="ocr-prep-")
    prep._tmpdir = workdir  # removed by prepare() if anything below fails
    with lock:
        pdf = pdfium.PdfDocument(path)
    try:
        with lock:
            page_count = len(pdf)
        dpis: list[float] = []
        checked, max_pages = 0, osd_max_pages()
        deadline = _now() + osd_budget_seconds()
        for index in range(page_count):
            try:
                with lock:
                    page = pdf[index]
            except Exception as e:  # one unloadable page must not undo the others
                logger.warning(
                    f"OCR PDF preparation skipped page {index + 1} of "
                    f"{os.path.basename(path)}: {type(e).__name__}"
                )
                continue
            try:
                with lock:
                    dpi = _scan_dpi(page)
                if dpi is None:
                    continue  # born-digital page: nothing to do
                dpis.append(dpi)
                if not can_detect or not tesseract_cmd:
                    continue
                if checked >= max_pages:
                    if max_pages:  # 0 = detection switched off on purpose
                        prep.orientation_limit = prep.orientation_limit or "max_pages"
                    continue
                if _now() >= deadline:
                    prep.orientation_limit = "time_budget"
                    continue
                checked += 1
                try:
                    found = _page_rotation(
                        page, index, workdir, tesseract_cmd, tessdata
                    )
                except Exception as e:  # one bad page must not undo the others
                    logger.warning(
                        f"OCR page orientation skipped for page {index + 1} of "
                        f"{os.path.basename(path)}: {type(e).__name__}"
                    )
                    continue
                if found and found[0] != 0 and found[1] >= threshold:
                    with lock:
                        page.set_rotation((page.get_rotation() + found[0]) % 360)
                    prep.rotated_pages[index] = found[0]
            finally:
                with lock:
                    page.close()
        prep.orientation_checked = checked
        if prep.orientation_limit:
            # Not a failure: the document is converted, these pages just keep
            # the orientation they were scanned with.
            logger.warning(
                f"OCR page orientation limited by {prep.orientation_limit} for "
                f"{os.path.basename(path)}: {checked} scanned page(s) checked, "
                f"the remaining pages are converted as they are"
            )
        if dpis:
            # One scale per document (Docling has one OcrOptions): the HIGHEST scan
            # resolution, so no page is ever rendered below its own resolution or
            # below what it got before this module existed.
            prep.scan_dpi = round(max(dpis), 1)
            prep.scale = scale_for_dpi(prep.scan_dpi)
        if prep.rotated_pages:
            # Same file name in a private directory: Docling names the document
            # after the file it is given.
            target = os.path.join(workdir, Path(path).name)
            with lock:
                pdf.save(target)
            prep.path = target
            logger.info(
                f"OCR page orientation: corrected page(s) "
                f"{sorted(p + 1 for p in prep.rotated_pages)} of "
                f"{os.path.basename(path)} in a temporary copy"
            )
    finally:
        with lock:
            pdf.close()
    if prep.path is None:
        prep.cleanup()
