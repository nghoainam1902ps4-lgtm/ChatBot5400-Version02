"""Controlled patch of Docling 2.129.0: Tesseract's TSV ``text`` stays text (E0-07).

Phase 12D7, approved by the project owner. Upstream
``TesseractOcrCliModel._run_tesseract`` (``docling/models/stages/ocr/
tesseract_ocr_cli_model.py`` at v2.129.0) reads Tesseract's TSV output with
``pd.read_csv(io.StringIO(decoded_data), quoting=csv.QUOTE_NONE, sep="\\t")``
and later builds every OCR cell with ``str(row["text"])``. pandas INFERS the
type of the ``text`` column, per OCR crop:

* when every word of a crop is a number the column becomes ``float64`` (the
  rows of the page / block / paragraph / line levels have no text, i.e. NaN):
  ``0001`` -> ``1.0``, ``000123`` -> ``123.0``, ``2024`` -> ``2024.0``,
  ``9.`` -> ``9.0``, ``12.50`` -> ``12.5``;
* pandas' default NA strings (``NA``, ``N/A``, ``NULL``, ``NaN``, ``None``,
  ``nan``, ...) become NaN in ANY crop and the row is then filtered out: the
  word disappears;
* a crop whose words are all ``true`` / ``false`` becomes boolean: ``True``.

Measured on 22 real PDFs (Phase 12E0 / 12E1, Windows) through v1.2.0 and the
12D5 candidate alike: voucher numbers, years and clause numbers changed in
``full_text``.

THE PATCH reads the ``text`` column as plain strings with no NA conversion
(``dtype={"text": str}``, ``keep_default_na=False``); every OTHER column keeps
pandas' default NA strings (``na_values`` per column), so their types and
values are exactly the upstream ones - including malformed numeric fields.
The empty-row filter, the command line, logging and everything else are the
upstream code, unchanged (a test compares the AST with upstream) - except, since
Phase 12D9 (E2-04, see below), stderr kept for classification and a timeout.
Nothing in pandas is patched. RapidOCR / EasyOCR do not use this code. The
recognised text is never modified: what Tesseract wrote in the TSV is what the
OCR cell holds.

GUARDS: applied only when ``docling`` is exactly :data:`DOCLING_VERSION` and
the upstream function's source has exactly :data:`UPSTREAM_SHA256` (the source
``compat.py`` already verifies). Anything else raises :class:`TsvPatchError`
(a ``ValueError``: the Tesseract engines refuse to run - they never run
unpatched, never with a patch written for other code). Idempotent; the
upstream function stays reachable as ``__cb5400_upstream__`` so the
fingerprint check of ``compat.py`` keeps checking the real upstream source.

Applied by :func:`open_notebook.ocr.options.build_ocr_options` for every
Tesseract engine (Fast, Best, custom/Agri), Standard and Legal alike: the
single place that creates ``TesseractCliOcrOptions``.

The patched method is a modified copy of Docling code:
SPDX-FileCopyrightText: The Docling Contributors
SPDX-License-Identifier: MIT
Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions: The above copyright notice and this
permission notice shall be included in all copies or substantial portions of
the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO
EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

from __future__ import annotations

import csv
import hashlib
import importlib
import importlib.metadata
import inspect
import io
import json
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from subprocess import DEVNULL, PIPE
from typing import Any, Optional

PATCH_ID = "E0-07/tesseract-tsv-text/1"
DOCLING_VERSION = "2.129.0"
UPSTREAM_MODULE = "docling.models.stages.ocr.tesseract_ocr_cli_model"
UPSTREAM_TARGET = f"{UPSTREAM_MODULE}:TesseractOcrCliModel._run_tesseract"
# sha256(inspect.getsource(TesseractOcrCliModel._run_tesseract)) at v2.129.0 -
# the same value compat.DOCLING_FINGERPRINTS verifies.
UPSTREAM_SHA256 = "e0623aa9536128c833896869f39e27e52c10f66aa0ac51cb76418e3d61de233c"

TEXT_COLUMN = "text"
# pandas' default NA strings (read_csv documentation; equal to
# pandas._libs.parsers.STR_NA_VALUES in pandas 3.0 - a test checks it). They
# stay in force for every column EXCEPT text.
PANDAS_DEFAULT_NA = (
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
)

_lock = threading.Lock()


class TsvPatchError(ValueError):
    """The installed Docling is not the code this patch was written for."""


def read_tesseract_tsv(decoded_data: str) -> Any:
    """Tesseract's TSV as a DataFrame: ``text`` verbatim, other columns as upstream."""
    import pandas as pd

    raw = getattr(_capture, "raw", None)
    if raw is not None:  # evidence capture (the Standard gate's export only)
        raw.append(decoded_data)
    header = decoded_data.split("\n", 1)[0].rstrip("\r").split("\t")
    others = [c for c in header if c != TEXT_COLUMN]
    return pd.read_csv(
        io.StringIO(decoded_data),
        quoting=csv.QUOTE_NONE,
        sep="\t",
        dtype={TEXT_COLUMN: str},
        keep_default_na=False,
        na_values={c: list(PANDAS_DEFAULT_NA) for c in others},
    )


def _run_tesseract(self: Any, ifilename: str, osd: Optional[Any]):
    r"""
    Run tesseract CLI
    """
    # Upstream docling 2.129.0 code, except the TSV parse (read_tesseract_tsv).
    from docling.models.stages.ocr.tesseract_ocr_cli_model import _log

    cmd = [self._safe_tesseract_cmd]
    if self._auto_script and osd is not None:
        lang = self._parse_language(osd)
        if lang is not None:
            cmd.append("-l")
            cmd.append(self._sanitize_lang(lang))
    elif self._native_codes:
        cmd.append("-l")
        cmd.append("+".join(self._native_codes))

    if self._safe_tessdata_path is not None:
        cmd.append("--tessdata-dir")
        cmd.append(self._safe_tessdata_path)

    # Add PSM option if specified in the configuration; cast to int to
    # reject any non-numeric value and prevent argument injection.
    if self.options.psm is not None:
        cmd.extend(["--psm", str(int(self.options.psm))])

    cmd.append(self._sanitize_filename(ifilename))
    cmd.extend(["stdout", "tsv"])
    _log.info("command: {}".format(" ".join(cmd)))

    output = subprocess.run(
        cmd,
        stdout=PIPE,
        stderr=PIPE,  # E2-04: read (bounded) only to classify a failure, never logged
        stdin=DEVNULL,
        check=True,
        shell=False,
        timeout=RECOGNITION_TIMEOUT_SECONDS,  # E2-04: a hung run fails and is retried
    )

    # _log.info(output)

    # Decode the byte string to a regular string
    decoded_data = output.stdout.decode("utf-8")
    # _log.info(decoded_data)

    # Read the TSV file generated by Tesseract
    df_result = read_tesseract_tsv(decoded_data)

    # Display the dataframe (optional)
    # _log.info("df: ", df.head())

    # Filter rows that contain actual text (ignore header or empty rows)
    df_filtered = df_result[
        df_result["text"].notna() & (df_result["text"].apply(str).str.strip() != "")
    ]

    return df_filtered


_run_tesseract.__cb5400_patch__ = PATCH_ID  # type: ignore[attr-defined]


def _installed_docling() -> Optional[str]:
    try:
        return importlib.metadata.version("docling")
    except importlib.metadata.PackageNotFoundError:
        return None


def _upstream_class() -> Any:
    from docling.models.stages.ocr.tesseract_ocr_cli_model import TesseractOcrCliModel

    return TesseractOcrCliModel


def upstream_function() -> Any:
    """The original upstream method, whether or not the patch is applied."""
    current = _upstream_class().__dict__.get("_run_tesseract")
    return getattr(current, "__cb5400_upstream__", current)


def problems() -> list[str]:
    """Why the patch cannot be applied here ([] = it can, or already is)."""
    found = []
    version = _installed_docling()
    if version != DOCLING_VERSION:
        found.append(
            f"docling {version or 'not installed'}: the Tesseract TSV text patch (E0-07) "
            f"is written for docling {DOCLING_VERSION} only"
        )
        return found
    try:
        source = inspect.getsource(upstream_function())
    except Exception as e:  # noqa: BLE001 - reported
        return [f"{UPSTREAM_TARGET} cannot be read ({type(e).__name__})"]
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if digest != UPSTREAM_SHA256:
        found.append(
            f"{UPSTREAM_TARGET} is not the verified docling {DOCLING_VERSION} source "
            f"(sha256 {digest[:16]}..., expected {UPSTREAM_SHA256[:16]}...): the TSV text "
            "patch (E0-07) must be re-verified for it"
        )
    try:
        call_source = inspect.getsource(call_upstream())
    except Exception as e:  # noqa: BLE001 - reported
        return [*found, f"{CALL_TARGET} cannot be read ({type(e).__name__})"]
    digest = hashlib.sha256(call_source.encode("utf-8")).hexdigest()
    if digest != CALL_SHA256:
        found.append(
            f"{CALL_TARGET} is not the verified docling {DOCLING_VERSION} source "
            f"(sha256 {digest[:16]}..., expected {CALL_SHA256[:16]}...): the OCR region "
            "failure patch (E2-04) must be re-verified for it"
        )
    return found


def call_upstream() -> Any:
    """The original upstream ``TesseractOcrCliModel.__call__``, patched or not."""
    current = _upstream_class().__dict__.get("__call__")
    return getattr(current, "__cb5400_upstream__", current)


def is_applied() -> bool:
    try:
        cls = _upstream_class()
    except Exception:  # noqa: BLE001 - docling not importable
        return False
    run = cls.__dict__.get("_run_tesseract")
    call = cls.__dict__.get("__call__")
    return (
        getattr(run, "__cb5400_patch__", None) == PATCH_ID
        and getattr(call, "__cb5400_patch__", None) == REGION_PATCH_ID
    )


def apply() -> None:
    """Apply the Tesseract patches - E0-07 (TSV text) and E2-04 (a failed OCR
    region is never dropped) - all or nothing, idempotent. Raise TsvPatchError
    when they cannot be applied."""
    with _lock:
        if is_applied():
            return
        found = problems()
        if found:
            raise TsvPatchError(
                "Tesseract OCR is disabled: "
                + "; ".join(found)
                + ". Without the patches numbers recognised by Tesseract change in the "
                "text (0001 -> 1.0) and a failed OCR region is dropped without an error. "
                "Use the verified Docling version or update the patch."
            )
        cls = _upstream_class()
        if (
            getattr(cls.__dict__["_run_tesseract"], "__cb5400_patch__", None)
            != PATCH_ID
        ):
            original = cls.__dict__["_run_tesseract"]

            def patched(self: Any, ifilename: str, osd: Optional[Any]):
                return _run_tesseract(self, ifilename, osd)

            patched.__cb5400_patch__ = PATCH_ID  # type: ignore[attr-defined]
            patched.__cb5400_upstream__ = original  # type: ignore[attr-defined]
            patched.__doc__ = original.__doc__
            patched.__name__ = original.__name__
            patched.__qualname__ = original.__qualname__
            cls._run_tesseract = patched
        if (
            getattr(cls.__dict__["__call__"], "__cb5400_patch__", None)
            != REGION_PATCH_ID
        ):
            original_call = cls.__dict__["__call__"]

            def patched_call(self: Any, conv_res: Any, page_batch: Any) -> Any:
                return _tesseract_call(self, conv_res, page_batch)

            patched_call.__cb5400_patch__ = REGION_PATCH_ID  # type: ignore[attr-defined]
            patched_call.__cb5400_upstream__ = original_call  # type: ignore[attr-defined]
            patched_call.__doc__ = original_call.__doc__
            patched_call.__name__ = original_call.__name__
            patched_call.__qualname__ = original_call.__qualname__
            cls.__call__ = patched_call


def status() -> dict[str, Any]:
    """For diagnostics / status output."""
    return {
        "patch": PATCH_ID,
        "patches": [PATCH_ID, REGION_PATCH_ID],
        "docling": _installed_docling(),
        "applied": is_applied(),
        "problems": problems() if not is_applied() else [],
    }


# =========================================================================== #
# Phase 12D9, E2-04: a failed Tesseract recognition never drops a region
# =========================================================================== #
#
# Upstream ``TesseractOcrCliModel.__call__`` catches the CalledProcessError of a
# failed RECOGNITION run, logs it and continues: the words of that region are
# not in the page, and the page and the conversion report SUCCESS, errors=0
# (Windows, Phase 12E2: 13 of 49 tokens lost with Best, 63 of 100 with Agri v2,
# 445 of 1220 on a real document; the cause was not visible because the run's
# stderr goes to DEVNULL). A failed OSD run is a different case: with an explicit
# language list (every engine of the application) recognition still runs and
# nothing is lost; only without one (auto script) upstream skips the region.
#
# THE PATCH (owner decision, Phase 12D9), same guards as E0-07:
# * ``_run_tesseract`` keeps stderr - only its last STDERR_TAIL_BYTES are read,
#   to classify a failure; it is never logged or shown - and gets a timeout;
# * ``__call__`` is upstream's except two places (a test compares the AST): the
#   OSD failure is logged without the raw stderr (and, in auto-script mode, the
#   region fails instead of being skipped), and recognition goes through
#   ``_recognize_region``. A failure that can be transient is retried at most
#   RECOGNITION_RETRIES times after a short pause, on the SAME crop image,
#   command, language and model files (the model version pinned for the job is
#   never changed); a missing executable or model file is not retried. When it
#   still fails, OcrRegionError is raised instead of skipping the region:
#   Docling records the page as failed (ConversionResult.errors, status
#   PARTIAL_SUCCESS / FAILURE) and the application refuses the result
#   (``docling_extract.reject_incomplete``): no Source content, no embedding.
# Logged: page, region, language / model, category, exit code, attempts and the
# outcome - never OCR text, stderr, images or document content.

REGION_PATCH_ID = "E2-04/tesseract-region-failure/1"
CALL_TARGET = f"{UPSTREAM_MODULE}:TesseractOcrCliModel.__call__"
# sha256(inspect.getsource(TesseractOcrCliModel.__call__)) at docling 2.129.0
CALL_SHA256 = "98ecbc9142a99b163a2d5f42326f44dfb43f0eef000e19fee75899c3be006482"
RECOGNITION_RETRIES = 2  # after the first attempt: at most 3 runs per region
RETRY_BACKOFF_SECONDS = (0.5, 1.5)
RECOGNITION_TIMEOUT_SECONDS = 600.0  # one region; far above any real run
STDERR_TAIL_BYTES = 4096
OCR_REGION_FAILED = "OCR_REGION_FAILED"  # leads every OcrRegionError message

_DATA_FILE_MARKERS = (
    "error opening data file",
    "failed loading language",
    "couldn't load any languages",
    "could not initialize tesseract",
    "tessdata_prefix",
)
_MEMORY_MARKERS = ("out of memory", "bad_alloc", "cannot allocate")
_IMAGE_MARKERS = (
    "cannot open input file",
    "error in pixread",
    "pixreadstream",
    "leptonica error",
    "image file format",
)


class OcrRegionError(RuntimeError):
    """A Tesseract OCR region could not be recognised, after the bounded
    retries. NOT a CalledProcessError: upstream would skip the region again.
    The message holds metadata only (it becomes Docling's ErrorItem)."""

    def __init__(
        self,
        *,
        page_no: Any,
        region: int,
        engine: str,
        category: str,
        exit_code: Optional[int],
        attempts: int,
    ) -> None:
        self.page_no, self.region, self.engine = page_no, region, engine
        self.category, self.exit_code, self.attempts = category, exit_code, attempts
        super().__init__(
            f"{OCR_REGION_FAILED}: page {page_no}, region {region}, engine Tesseract "
            f"({engine}), category {category}, exit code {exit_code}, attempts {attempts}"
        )


@dataclass(frozen=True)
class RecognitionFailure:
    category: str
    exit_code: Optional[int]
    retryable: bool


def _stderr_tail(stderr: Any) -> str:
    if not stderr:
        return ""
    if isinstance(stderr, str):
        stderr = stderr.encode("utf-8", "replace")
    return bytes(stderr[-STDERR_TAIL_BYTES:]).decode("utf-8", "replace")


def _arg(cmd: Any, flag: str) -> Optional[str]:
    try:
        args = [str(a) for a in cmd]
        return args[args.index(flag) + 1]
    except (TypeError, ValueError, IndexError):
        return None


def _model_files_present(cmd: Any) -> Optional[bool]:
    """Whether every ``-l`` model file of ``cmd`` is a readable file now
    (None: the command does not say where they are)."""
    langs = _arg(cmd, "-l")
    folder = _arg(cmd, "--tessdata-dir") or os.environ.get("TESSDATA_PREFIX")
    if not langs or not folder:
        return None
    for lang in langs.split("+"):
        f = Path(folder) / f"{lang}.traineddata"
        if not (f.is_file() and os.access(f, os.R_OK)):
            return False
    return True


def stderr_category(stderr: Any) -> str:
    """A category for a Tesseract stderr - the text itself is never kept."""
    tail = _stderr_tail(stderr).lower()
    if any(m in tail for m in _DATA_FILE_MARKERS):
        return "data_file_unreadable"
    if any(m in tail for m in _MEMORY_MARKERS):
        return "out_of_memory"
    if any(m in tail for m in _IMAGE_MARKERS):
        return "image_unreadable"
    return "other" if tail.strip() else "no_stderr"


def classify_recognition_failure(exc: BaseException) -> RecognitionFailure:
    """Category, exit code and whether a retry can help (E2-04)."""
    if isinstance(exc, subprocess.TimeoutExpired):
        return RecognitionFailure("timeout", None, True)
    if isinstance(exc, FileNotFoundError):
        return RecognitionFailure("executable_missing", None, False)
    if isinstance(exc, PermissionError):
        return RecognitionFailure("executable_not_permitted", None, False)
    if isinstance(exc, subprocess.CalledProcessError):
        code = exc.returncode
        category = stderr_category(exc.stderr)
        if category == "data_file_unreadable":
            # the file is missing (configuration: a retry cannot help) or it is
            # there and could not be read this time (I/O: retried)
            if _model_files_present(exc.cmd) is False:
                return RecognitionFailure("model_missing", code, False)
            return RecognitionFailure(category, code, True)
        if category in ("out_of_memory", "image_unreadable"):
            return RecognitionFailure(category, code, True)
        if code is not None and code < 0:
            return RecognitionFailure("killed_by_signal", code, True)
        return RecognitionFailure("exit_nonzero", code, True)
    if isinstance(exc, OSError):
        return RecognitionFailure("os_error", getattr(exc, "errno", None), True)
    return RecognitionFailure("unknown", None, False)


def _engine_label(model: Any) -> str:
    return "+".join(getattr(model, "_native_codes", None) or []) or "auto-script"


def _recognize_region(
    model: Any, fname: str, df_osd: Any, *, page: Any, region: int, rect: Any = None
) -> Any:
    """``model._run_tesseract`` with the bounded retry of E2-04; raises
    OcrRegionError when the region cannot be recognised."""
    from docling.models.stages.ocr.tesseract_ocr_cli_model import _log

    attempt = 0
    while True:
        attempt += 1
        try:
            sink = _evidence
            if sink is None:
                return model._run_tesseract(fname, df_osd)
            _capture.raw = []
            try:
                result = model._run_tesseract(fname, df_osd)
                raws = list(_capture.raw)
            finally:
                _capture.raw = None
            sink.tesseract(model, page, region, rect, attempt, raws)
            return result
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            OSError,
        ) as exc:
            failure = classify_recognition_failure(exc)
            if failure.retryable and attempt <= RECOGNITION_RETRIES:
                _log.warning(
                    "Tesseract recognition failed (page %s, region %s, lang %s, attempt "
                    "%s of %s, category %s, exit code %s): retrying the same crop",
                    page.page_no,
                    region + 1,
                    _engine_label(model),
                    attempt,
                    RECOGNITION_RETRIES + 1,
                    failure.category,
                    failure.exit_code,
                )
                time.sleep(
                    RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS)) - 1]
                )
                continue
            _log.error(
                "Tesseract recognition failed (page %s, region %s, lang %s, %s "
                "attempt(s), category %s, exit code %s): the region is not dropped, "
                "the page fails",
                page.page_no,
                region + 1,
                _engine_label(model),
                attempt,
                failure.category,
                failure.exit_code,
            )
            raise OcrRegionError(
                page_no=page.page_no,
                region=region + 1,
                engine=_engine_label(model),
                category=failure.category,
                exit_code=failure.exit_code,
                attempts=attempt,
            ) from None


def _osd_region_error(
    model: Any, page: Any, region: int, stderr: Any
) -> OcrRegionError:
    return OcrRegionError(
        page_no=page.page_no,
        region=region + 1,
        engine=_engine_label(model),
        category="osd_failed_auto_script_" + stderr_category(stderr),
        exit_code=None,
        attempts=1,
    )


def _withheld(stderr: Any) -> str:
    return f"[stderr withheld: {len(stderr or b'')} bytes, {stderr_category(stderr)}]"


def _tesseract_call(self: Any, conv_res: Any, page_batch: Any) -> Any:
    """Upstream docling 2.129.0 ``TesseractOcrCliModel.__call__`` except (E2-04):
    the OSD failure log carries no raw stderr (and fails the region in
    auto-script mode), and recognition retries / fails the region
    (``_recognize_region``) instead of skipping it."""
    import pandas as pd
    from docling.models.stages.ocr.tesseract_ocr_cli_model import (
        BoundingBox,
        CoordOrigin,
        TextCell,
        TimeRecorder,
        _log,
        _parse_orientation,
        settings,
        tempfile,
        tesseract_box_to_bounding_rectangle,
    )

    if not self.enabled:
        yield from page_batch
        return

    for page_i, page in enumerate(page_batch):
        assert page._backend is not None
        if not page._backend.is_valid():
            yield page
        else:
            with TimeRecorder(conv_res, "ocr"):
                ocr_rects = self.get_ocr_rects(page)

                all_ocr_cells = []
                for ocr_rect_i, ocr_rect in enumerate(ocr_rects):
                    # Skip zero area boxes
                    if ocr_rect.area() == 0:
                        continue
                    high_res_image = page._backend.get_page_image(
                        scale=self.scale, cropbox=ocr_rect
                    )
                    try:
                        with tempfile.NamedTemporaryFile(
                            suffix=".png", mode="w+b", delete=False
                        ) as image_file:
                            fname = image_file.name
                            high_res_image.save(image_file)
                        doc_orientation = 0
                        df_osd: Optional[pd.DataFrame] = None
                        try:
                            df_osd = self._perform_osd(fname)
                            doc_orientation = _parse_orientation(df_osd)
                        except subprocess.CalledProcessError as exc:
                            _log.error(
                                "OSD failed (doc %s, page: %s, "
                                "OCR rectangle: %s, processed image file %s):\n %s",
                                conv_res.input.file,
                                page_i,
                                ocr_rect_i,
                                image_file,
                                _withheld(exc.stderr),
                            )
                            # Skipping if OSD fail when in auto mode, otherwise proceed
                            # to OCR in the hope OCR will succeed while OSD failed
                            if self._auto_script:
                                raise _osd_region_error(
                                    self, page, ocr_rect_i, exc.stderr
                                ) from None
                        if doc_orientation != 0:
                            high_res_image = high_res_image.rotate(
                                -doc_orientation, expand=True
                            )
                            high_res_image.save(fname)
                        df_result = _recognize_region(
                            self,
                            fname,
                            df_osd,
                            page=page,
                            region=ocr_rect_i,
                            rect=ocr_rect,
                        )
                    finally:
                        if os.path.exists(fname):
                            os.remove(fname)

                    # _log.info(df_result)

                    # Print relevant columns (bounding box and text)
                    for ix, row in df_result.iterrows():
                        text = row["text"]
                        conf = row["conf"]

                        left, top = float(row["left"]), float(row["top"])
                        right = left + float(row["width"])
                        bottom = top + row["height"]
                        bbox = BoundingBox(
                            l=left,
                            t=top,
                            r=right,
                            b=bottom,
                            coord_origin=CoordOrigin.TOPLEFT,
                        )
                        rect = tesseract_box_to_bounding_rectangle(
                            bbox,
                            original_offset=ocr_rect,
                            scale=self.scale,
                            orientation=doc_orientation,
                            im_size=high_res_image.size,
                        )
                        cell = TextCell(
                            index=ix,
                            text=str(text),
                            orig=str(text),
                            from_ocr=True,
                            confidence=conf / 100.0,
                            rect=rect,
                        )
                        all_ocr_cells.append(cell)

                # Post-process the cells
                self.post_process_cells(all_ocr_cells, page, conv_res)

            # DEBUG code:
            if settings.debug.visualize_ocr:
                self.draw_ocr_rects_and_cells(conv_res, page, ocr_rects)

            yield page


# =========================================================================== #
# Phase 12D9: text preservation in Docling's PDF text assembly and Markdown
# export - D8-03 (hyphens) and D8-02 (footnotes attached to tables / pictures)
# =========================================================================== #
#
# Approved by the project owner (Phase 12D9), same guards as the TSV patch:
# exact distribution version + SHA-256 of every upstream function; anything
# else refuses (TextPreservationPatchError, a ValueError). The modified
# functions below are copies of Docling / docling-core code (MIT, notice
# above); a test compares each with its upstream AST.
#
# D8-03 - Docling 2.129.0 removes a hyphen the document has:
#   * PageAssembleModel.sanitize_text joins the cell texts of a layout region
#     and drops a "-" that ends a cell before an alphanumeric word
#     ("05/2024/TT-" + "BNNPTNT" -> "05/2024/TTBNNPTNT"), for every OCR
#     engine and PDF text layers; Tesseract cells are WORDS, so the rule also
#     fires inside a printed line ("VT- KHTC" -> "VTKHTC").
#   * ReadingOrderModel._merge_elements drops a "-" that ends a block before a
#     lowercase continuation when Docling joins two blocks (across a page or a
#     column): "xuyên-" + "biên giới" -> "xuyênbiên giới".
#   The patch never removes a "-". The parts close up only across a line
#   break the cells' OWN boxes show (the next cell starts a lower line:
#   "05/2024/TT-" / "BNNPTNT" -> "05/2024/TT-BNNPTNT"); two cells side by side
#   in one printed line, or cells whose boxes do not tell, keep the cell
#   boundary as a space ("VT- KHTC", "1- Điều 5"): two cells are never assumed
#   to be one word. Joined blocks keep the hyphen and record where the
#   continuation really starts (charspan). A soft hyphen (U+00AD, an invisible line-break hint)
#   and every other rule of upstream (quotes, bullets, ligatures, spaces) are
#   unchanged.
# D8-02 - docling-core 2.96.0's Markdown serializer writes the captions of a
#   table / picture but never its footnotes, while the footnote is skipped at
#   its own place ("handled by the floating item holding them"): the note is
#   in no Markdown output. The patch writes every attached footnote right
#   after its table / picture, once, skipping references that do not resolve.
#   Markdown only (HTML / JSON exports are not changed by this patch).
#
# Applied by ``apply_text_preservation`` before every Docling conversion of
# the application (``docling_extract.build_converter``, the source graph
# before content-core's own path) and by the Legal normalizer.

HYPHEN_PATCH_ID = "D8-03/hyphen-preservation/1"
FOOTNOTE_PATCH_ID = "D8-02/attached-footnotes/1"
DOCLING_CORE_VERSION = "2.96.0"
PAGE_ASSEMBLE_MODULE = "docling.models.stages.page_assemble.page_assemble_model"
READING_ORDER_MODULE = "docling.models.stages.reading_order.readingorder_model"
MARKDOWN_MODULE = "docling_core.transforms.serializer.markdown"

# key -> (patch id, module, class, attribute, sha256(inspect.getsource(upstream)))
TEXT_TARGETS: dict[str, tuple[str, str, str, str, str]] = {
    "sanitize_text": (
        HYPHEN_PATCH_ID,
        PAGE_ASSEMBLE_MODULE,
        "PageAssembleModel",
        "sanitize_text",
        "7c6242f7b90cdfe9bb7f6023018280c9bc122bb29e1b3b76f5715564fa41b03e",
    ),
    "page_assemble": (
        HYPHEN_PATCH_ID,
        PAGE_ASSEMBLE_MODULE,
        "PageAssembleModel",
        "__call__",
        "b20525771b0b21e7f9d0421f42e4ce0f43b6fef8ef02fd57006321e741cec37e",
    ),
    "merge_elements": (
        HYPHEN_PATCH_ID,
        READING_ORDER_MODULE,
        "ReadingOrderModel",
        "_merge_elements",
        "297d40a4942c3d4f84d8fc03b213162b202566b5c80264fa5677e6ca2bc892da",
    ),
    "table_markdown": (
        FOOTNOTE_PATCH_ID,
        MARKDOWN_MODULE,
        "MarkdownTableSerializer",
        "serialize",
        "5eb2124b2206369ed288153bb521fee5318b478b610aa258b7255b66ffb181db",
    ),
    "picture_markdown": (
        FOOTNOTE_PATCH_ID,
        MARKDOWN_MODULE,
        "MarkdownPictureSerializer",
        "serialize",
        "ec9a00398d819e4a437523ffdc66a5034a496e928b67a29ac24f4e831609564b",
    ),
}
TEXT_PATCH_VERSIONS: dict[str, tuple[str, str]] = {
    HYPHEN_PATCH_ID: ("docling", DOCLING_VERSION),
    FOOTNOTE_PATCH_ID: ("docling-core", DOCLING_CORE_VERSION),
}
# Two cells are side by side in ONE printed line when their vertical extents
# overlap by at least this share of the smaller one (and the second starts to
# the right of the first); the second starts a LOWER line when they overlap by
# less and its middle is below the middle of the first.
SAME_LINE_MIN_OVERLAP = 0.5
_FOOTNOTE_DONE = "#cb5400-footnote-written:"  # visited-set key prefix (no ref clash)
_upstream_mode = 0  # > 0 while upstream_text_preservation() is active (tests)


class TextPreservationPatchError(ValueError):
    """The installed Docling / docling-core is not the code these patches fit."""


def _installed(dist: str) -> Optional[str]:
    try:
        return importlib.metadata.version(dist)
    except importlib.metadata.PackageNotFoundError:
        return None


def _text_owner(key: str) -> Any:
    _pid, module, owner, _attr, _sha = TEXT_TARGETS[key]
    return getattr(importlib.import_module(module), owner)


def text_upstream(key: str) -> Any:
    """The original upstream function of a target, patched or not."""
    attr = TEXT_TARGETS[key][3]
    current = _text_owner(key).__dict__.get(attr)
    return getattr(current, "__cb5400_upstream__", current)


def text_problems() -> list[str]:
    """Why the text-preservation patches cannot be applied ([] = they can / are)."""
    found: list[str] = []
    for patch_id, (dist, wanted) in TEXT_PATCH_VERSIONS.items():
        version = _installed(dist)
        if version != wanted:
            found.append(
                f"{dist} {version or 'not installed'}: the {patch_id} patch is written "
                f"for {dist} {wanted} only"
            )
    if found:
        return found
    for key, (patch_id, module, owner, attr, sha) in TEXT_TARGETS.items():
        try:
            source = inspect.getsource(text_upstream(key))
        except Exception as e:  # noqa: BLE001 - reported
            found.append(f"{module}:{owner}.{attr} cannot be read ({type(e).__name__})")
            continue
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if digest != sha:
            found.append(
                f"{module}:{owner}.{attr} is not the verified upstream source (sha256 "
                f"{digest[:16]}..., expected {sha[:16]}...): the {patch_id} patch must be "
                "re-verified for it"
            )
    return found


def text_patches_applied() -> bool:
    try:
        for key, (patch_id, _m, _o, attr, _s) in TEXT_TARGETS.items():
            current = _text_owner(key).__dict__.get(attr)
            if getattr(current, "__cb5400_patch__", None) != patch_id:
                return False
    except Exception:  # noqa: BLE001 - docling / docling-core not importable
        return False
    return True


def _docling_present() -> bool:
    return _installed("docling") is not None and _installed("docling-core") is not None


def apply_text_preservation(required: bool = True) -> bool:
    """Apply the D8-03 and D8-02 patches (idempotent, all or nothing).

    Returns True when they are in force. Without Docling there is no PDF
    pipeline to patch: False. When they cannot be applied: raise
    TextPreservationPatchError if ``required`` (a conversion must not run
    unpatched), else log an error and return False.
    """
    with _lock:
        if _upstream_mode:
            return False  # tests / diagnostics asked for upstream behaviour
        if text_patches_applied():
            return True
        if not _docling_present():
            return False
        found = text_problems()
        if found:
            message = (
                "Docling text preservation is not available: "
                + "; ".join(found)
                + ". Without it hyphens of document numbers and footnotes of tables / "
                "pictures are lost (05/2024/TT-BNNPTNT -> 05/2024/TTBNNPTNT). Use the "
                "verified Docling / docling-core versions or update the patch."
            )
            if required:
                raise TextPreservationPatchError(message)
            from loguru import logger

            logger.error(message)
            return False
        upstream = {key: text_upstream(key) for key in TEXT_TARGETS}
        replacements = {
            "sanitize_text": _sanitize_text,
            "page_assemble": _page_assemble_call,
            "merge_elements": _merge_elements,
            "table_markdown": _with_attached_footnotes(upstream["table_markdown"]),
            "picture_markdown": _with_attached_footnotes(upstream["picture_markdown"]),
        }
        # order matters: sanitize_text accepts ``same_line`` before the page
        # assembly that passes it is in place (no TypeError for a concurrent job)
        for key, new in replacements.items():
            patch_id, _m, _o, attr, _s = TEXT_TARGETS[key]
            original = upstream[key]

            def bound(*a: Any, __new: Any = new, **kw: Any) -> Any:
                return __new(*a, **kw)

            bound.__cb5400_patch__ = patch_id  # type: ignore[attr-defined]
            bound.__cb5400_upstream__ = original  # type: ignore[attr-defined]
            bound.__doc__ = original.__doc__
            bound.__name__ = original.__name__
            bound.__qualname__ = original.__qualname__
            setattr(_text_owner(key), attr, bound)
        return True


def text_status() -> dict[str, Any]:
    """For diagnostics / status output."""
    applied = text_patches_applied()
    return {
        "patches": [HYPHEN_PATCH_ID, FOOTNOTE_PATCH_ID],
        "docling": _installed("docling"),
        "docling_core": _installed("docling-core"),
        "applied": applied,
        "problems": [] if applied or not _docling_present() else text_problems(),
    }


class upstream_text_preservation:  # noqa: N801 - used like a function
    """``with upstream_text_preservation():`` - run upstream Docling text
    assembly / Markdown export, then put the patches back. Tests and
    diagnostics only (process-wide while the block runs)."""

    def __enter__(self) -> "upstream_text_preservation":
        global _upstream_mode
        with _lock:
            self._saved: dict[str, Any] = {}
            # reverse order: the page assembly that passes ``same_line`` goes
            # back to upstream before sanitize_text does
            for key in reversed(list(TEXT_TARGETS)):
                attr = TEXT_TARGETS[key][3]
                cls = _text_owner(key)
                self._saved[key] = cls.__dict__.get(attr)
                setattr(cls, attr, text_upstream(key))
            _upstream_mode += 1
        return self

    def __exit__(self, *exc: Any) -> None:
        global _upstream_mode
        with _lock:
            for key in TEXT_TARGETS:
                saved = self._saved[key]
                if saved is not None:
                    setattr(_text_owner(key), TEXT_TARGETS[key][3], saved)
            _upstream_mode -= 1


# --------------------------------------------------------------------------- #
# D8-03: page assembly (copies of docling 2.129.0 code, see the AST test)
# --------------------------------------------------------------------------- #


def same_line_flags(cells: list[Any]) -> list[Optional[bool]]:
    """For each pair of consecutive cells, from their own boxes: True = side by
    side in one printed line, False = the second starts a LOWER line (a line
    break), None = the boxes show neither (no evidence)."""
    from docling_core.types.doc.base import CoordOrigin

    flags: list[Optional[bool]] = []
    for a, b in zip(cells, cells[1:]):
        try:
            ba, bb = a.rect.to_bounding_box(), b.rect.to_bounding_box()
            if ba.coord_origin != bb.coord_origin:
                flags.append(None)
                continue
            a_lo, a_hi = min(ba.t, ba.b), max(ba.t, ba.b)
            b_lo, b_hi = min(bb.t, bb.b), max(bb.t, bb.b)
            a_left, b_left = min(ba.l, ba.r), min(bb.l, bb.r)
            down = 1.0 if ba.coord_origin == CoordOrigin.TOPLEFT else -1.0
        except Exception:  # noqa: BLE001 - a cell without a usable box
            flags.append(None)
            continue
        height = min(a_hi - a_lo, b_hi - b_lo)
        if not height > 0:
            flags.append(None)
            continue
        overlap = min(a_hi, b_hi) - max(a_lo, b_lo)
        if overlap >= SAME_LINE_MIN_OVERLAP * height:
            flags.append(True if b_left > a_left else None)
        elif down * ((b_lo + b_hi) - (a_lo + a_hi)) > 0:
            flags.append(False)
        else:
            flags.append(None)  # the next cell is ABOVE: not a line break
    return flags


def _sanitize_text(self: Any, lines: list[str], same_line: Any = None) -> str:
    """Join the text lines of a cluster into a single normalized string.

    Upstream docling 2.129.0 ``PageAssembleModel.sanitize_text`` except one
    branch (D8-03): a hyphen that ends a cell before an alphanumeric word is
    KEPT. The parts close up only when ``same_line`` (from the cells' own
    boxes) shows a line break between them ("05/2024/TT-" / "BNNPTNT" ->
    "05/2024/TT-BNNPTNT"); side by side in one printed line, or without that
    evidence (no ``same_line``: upstream's own signature), the cell boundary
    stays as a space ("VT- KHTC").
    """
    from docling.models.stages.page_assemble.page_assemble_model import (
        _LIGATURE_MAP,
        _LIGATURE_RE,
    )

    if len(lines) == 0:
        return ""

    for ix, line in enumerate(lines[1:]):
        prev_line = lines[ix]

        if prev_line.endswith("-"):
            prev_words = re.findall(r"\b[\w]+\b", prev_line)
            line_words = re.findall(r"\b[\w]+\b", line)

            hyphen_attached_to_word = len(prev_line) > 1 and prev_line[-2].isalnum()

            if (
                hyphen_attached_to_word
                and len(prev_words)
                and len(line_words)
                and prev_words[-1].isalnum()
                and line_words[0].isalnum()
            ):
                # D8-03: upstream removed the hyphen here. It is kept; the
                # parts close up only across a line break the boxes show.
                line_break = (
                    same_line is not None
                    and ix < len(same_line)
                    and same_line[ix] is False
                )
                if not line_break:
                    lines[ix] += " "
            elif not hyphen_attached_to_word:
                lines[ix] += " "
        else:
            lines[ix] += " "

    sanitized_text = "".join(lines)

    # Text normalization
    sanitized_text = sanitized_text.replace("⁄", "/")  # noqa: RUF001
    sanitized_text = sanitized_text.replace("’", "'")  # noqa: RUF001
    sanitized_text = sanitized_text.replace("‘", "'")  # noqa: RUF001
    sanitized_text = sanitized_text.replace("“", '"')
    sanitized_text = sanitized_text.replace("”", '"')
    sanitized_text = sanitized_text.replace("•", "·")
    # Ligature expansion: replace ligature characters with their ASCII equivalents.
    # For the traditional fb00-fb06 ligatures (e.g. ﬁ, ﬂ), any spurious space
    # inserted by the PDF parser between the glyph and the rest of the word is
    # absorbed (e.g. "ﬁ eld" → "field").
    # For U+0132/U+0133 (Dutch IJ/ij) and U+F0A0 (PUA discard glyph), any
    # captured trailing space is re-emitted so that real word boundaries are
    # preserved (e.g. "Ĳ is" → "IJ is", "hello world" → "hello world").
    sanitized_text = _LIGATURE_RE.sub(
        lambda m: (
            _LIGATURE_MAP[m.group(1)]
            + ("" if "ﬀ" <= m.group(1) <= "ﬆ" else (m.group(2) or ""))
        ),
        sanitized_text,
    )

    return sanitized_text.strip()  # Strip any leading or trailing whitespace


def _assembled_text(
    model: Any, page: Any, cluster: Any, kept_cells: list[Any], textlines: list[str]
) -> str:
    """The text of one region: the patched join, given the cells' geometry."""
    text = model.sanitize_text(textlines, same_line=same_line_flags(kept_cells))
    sink = _evidence
    if sink is not None:
        sink.element(model, page, cluster, kept_cells, text)
    return text


def _page_assemble_call(self: Any, conv_res: Any, page_batch: Any) -> Any:
    """Upstream docling 2.129.0 ``PageAssembleModel.__call__`` except that the
    text join of a region is given the geometry of its cells (D8-03)."""
    from docling.models.stages.page_assemble.page_assemble_model import (
        CONTAINER_LABELS,
        FIGURE_LABEL,
        PAGE_HEADER_LABELS,
        TABLE_LABELS,
        TEXT_ELEM_LABELS,
        AssembledUnit,
        ContainerElement,
        FigureElement,
        List,
        PageElement,
        Table,
        TextElement,
        TimeRecorder,
    )

    for page in page_batch:
        assert page._backend is not None
        if not page._backend.is_valid():
            yield page
        else:
            with TimeRecorder(conv_res, "page_assemble"):
                assert page.predictions.layout is not None

                # assembles some JSON output page by page.

                elements: List[PageElement] = []
                headers: List[PageElement] = []
                body: List[PageElement] = []

                for cluster in page.predictions.layout.clusters:
                    # _log.info("Cluster label seen:", cluster.label)
                    if cluster.label in TEXT_ELEM_LABELS:
                        kept_cells = [
                            cell for cell in cluster.cells if len(cell.text.strip()) > 0
                        ]
                        textlines = [
                            cell.text.replace("\x02", "-").strip()
                            for cell in kept_cells
                        ]
                        text = _assembled_text(
                            self, page, cluster, kept_cells, textlines
                        )
                        hyperlink = self._match_hyperlink(cluster.bbox, page)
                        text_el = TextElement(
                            label=cluster.label,
                            id=cluster.id,
                            text=text,
                            hyperlink=hyperlink,
                            page_no=page.page_no,
                            cluster=cluster,
                        )
                        elements.append(text_el)

                        if cluster.label in PAGE_HEADER_LABELS:
                            headers.append(text_el)
                        else:
                            body.append(text_el)
                    elif cluster.label in TABLE_LABELS:
                        tbl = None
                        if page.predictions.tablestructure:
                            tbl = page.predictions.tablestructure.table_map.get(
                                cluster.id, None
                            )
                        if (
                            not tbl
                        ):  # fallback: add table without structure, if it isn't present
                            tbl = Table(
                                label=cluster.label,
                                id=cluster.id,
                                text="",
                                otsl_seq=[],
                                table_cells=[],
                                cluster=cluster,
                                page_no=page.page_no,
                            )

                        elements.append(tbl)
                        body.append(tbl)
                    elif cluster.label == FIGURE_LABEL:
                        fig = None
                        if page.predictions.figures_classification:
                            fig = (
                                page.predictions.figures_classification.figure_map.get(
                                    cluster.id, None
                                )
                            )
                        if not fig:  # fallback: add figure without classification, if it isn't present
                            fig = FigureElement(
                                label=cluster.label,
                                id=cluster.id,
                                text="",
                                data=None,
                                cluster=cluster,
                                page_no=page.page_no,
                            )
                        elements.append(fig)
                        body.append(fig)
                    elif cluster.label in CONTAINER_LABELS:
                        container_el = ContainerElement(
                            label=cluster.label,
                            id=cluster.id,
                            page_no=page.page_no,
                            cluster=cluster,
                        )
                        elements.append(container_el)
                        body.append(container_el)

                page.assembled = AssembledUnit(
                    elements=elements, headers=headers, body=body
                )

            yield page


def _merge_elements(
    self: Any, element: Any, merged_elem: Any, new_item: Any, page_height: Any
) -> None:
    """Upstream docling 2.129.0 ``ReadingOrderModel._merge_elements`` except the
    hard hyphen before a lowercase continuation (D8-03): it is kept, the parts
    close up, and the char span says where the continuation starts. The soft
    hyphen branch (U+00AD) is upstream's."""
    from docling.models.stages.reading_order.readingorder_model import ProvenanceItem

    assert isinstance(merged_elem, type(element)), (
        "Merged element must be of same type as element."
    )
    assert merged_elem.label == new_item.label, "Labels of merged elements must match."
    prov = ProvenanceItem(
        page_no=merged_elem.page_no,
        charspan=(
            len(new_item.text) + 1,
            len(new_item.text) + 1 + len(merged_elem.text),
        ),
        bbox=merged_elem.cluster.bbox.to_bottom_left_origin(page_height),
    )
    continuation_text = merged_elem.text.lstrip()
    if new_item.text.endswith("­"):
        # A soft hyphen or hard-hyphenated lowercase continuation is a split word.
        new_item.text = new_item.text[:-1] + merged_elem.text
        new_item.orig = (
            new_item.orig[:-1] + merged_elem.text
        )  # TODO: This is incomplete, we don't have the `orig` field of the merged element.
    elif (
        new_item.text.endswith("-")
        and continuation_text
        and continuation_text[0].islower()
    ):
        # D8-03: upstream removed this hyphen. It is kept; no separator.
        _record_merge(new_item, merged_elem)
        prov = ProvenanceItem(
            page_no=prov.page_no,
            charspan=(len(new_item.text), len(new_item.text) + len(merged_elem.text)),
            bbox=prov.bbox,
        )
        new_item.text = new_item.text + merged_elem.text
        new_item.orig = new_item.orig + merged_elem.text
    else:
        new_item.text += f" {merged_elem.text}"
        new_item.orig += f" {merged_elem.text}"  # TODO: This is incomplete, we don't have the `orig` field of the merged element.
    new_item.prov.append(prov)

    if new_item.hyperlink != merged_elem.hyperlink:
        new_item.hyperlink = None


# --------------------------------------------------------------------------- #
# D8-02: footnotes attached to a table / picture in the Markdown export
# --------------------------------------------------------------------------- #


def attached_footnotes(
    item: Any, doc_serializer: Any, doc: Any, **kwargs: Any
) -> list[Any]:
    """The serialized footnotes Docling attached to ``item`` (a table / picture):
    each once per export (a note several items refer to is written after the
    first), references that do not resolve and empty notes skipped."""
    from docling_core.transforms.serializer.common import create_ser_result
    from docling_core.types.doc.document import TextItem
    from docling_core.types.doc.labels import DocItemLabel

    refs = list(getattr(item, "footnotes", None) or [])
    if not refs:
        return []
    params = doc_serializer.params.merge_with_patch(patch=kwargs)
    if DocItemLabel.FOOTNOTE not in params.labels:
        return []
    excluded = doc_serializer.get_excluded_refs(**kwargs)
    visited = kwargs.get("visited")
    out = []
    for ref in refs:
        cref = getattr(ref, "cref", None)
        if not isinstance(cref, str) or cref in excluded:
            continue
        done = _FOOTNOTE_DONE + cref
        if isinstance(visited, set) and done in visited:
            continue
        try:
            note = ref.resolve(doc)
        except Exception:  # noqa: BLE001 - a broken reference: skipped, no loop
            continue
        if not isinstance(note, TextItem) or not (note.text or "").strip():
            continue
        if isinstance(visited, set):
            visited.add(done)
        written = doc_serializer.post_process(text=note.text)
        sink = _evidence
        if sink is not None:
            sink.footnote(note, written)
        out.append(create_ser_result(text=written, span_source=note))
    return out


def _with_attached_footnotes(upstream: Any) -> Any:
    def serialize(
        self: Any, *, item: Any, doc_serializer: Any, doc: Any, **kwargs: Any
    ) -> Any:
        from docling_core.transforms.serializer.common import create_ser_result

        res = upstream(
            self, item=item, doc_serializer=doc_serializer, doc=doc, **kwargs
        )
        if kwargs.get("_nested_in_table"):
            return res  # a table inside a table cell: upstream's subtree text
        notes = attached_footnotes(item, doc_serializer, doc, **kwargs)
        if not notes:
            return res
        parts = [r for r in (res, *notes) if r.text]
        return create_ser_result(
            text="\n\n".join(r.text for r in parts), span_source=parts
        )

    return serialize


# --------------------------------------------------------------------------- #
# Phase 12D9 (D8-STD-03): the evidence of ONE conversion, for the Standard gate
# --------------------------------------------------------------------------- #
#
# Only ``scripts/ocr/phase12d9_standard_export.py`` turns this on (no setting,
# no environment variable: production never records anything). Inside
# ``with evidence_capture(folder, name):`` every Docling conversion of the
# process writes, for the Standard expected-diff gate:
#   tesseract/<page>_<region>_<n>.tsv + .json  the raw TSV of each Tesseract
#       invocation (the same bytes Docling parsed) and its provenance -
#       document, page, region, bbox, invocation, attempt, language, model
#       files with their SHA-256;
#   elements.jsonl  per text region (every engine, PDF text layers too): page,
#       label, bbox, the text the candidate assembled and the text v1.2.0's code
#       made of the same cells (Docling 2.129.0's pandas parse of the crop, its
#       sanitize_text);
#   merges.jsonl    Docling's block joins whose hyphen the patch keeps;
#   footnotes.jsonl the table / picture footnotes the patch writes.
# The files hold document text: owner-only permissions (0700 / 0600), local;
# nothing is logged, uploaded or committed.

_evidence: Optional["EvidenceSink"] = None
_capture = threading.local()


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


class EvidenceSink:
    def __init__(self, folder: Path, document: str) -> None:
        self.folder, self.document = Path(folder), document
        self.lock = threading.Lock()
        self.count = 0
        self.crops: dict[int, list[tuple[Any, dict[str, Optional[str]]]]] = {}
        self.model_sha: dict[str, str] = {}
        _private_dir(self.folder)

    def _write(self, rel: str, text: str, append: bool = False) -> None:
        path = self.folder / rel
        _private_dir(path.parent)
        flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if append else os.O_TRUNC)
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "a" if append else "w", encoding="utf-8") as fh:
            fh.write(text)

    def _line(self, rel: str, record: dict[str, Any]) -> None:
        self._write(rel, json.dumps(record, ensure_ascii=False) + "\n", append=True)

    def _models(self, model: Any) -> list[dict[str, Any]]:
        folder = getattr(model, "_safe_tessdata_path", None) or os.environ.get(
            "TESSDATA_PREFIX"
        )
        out = []
        for lang in getattr(model, "_native_codes", None) or []:
            path = Path(str(folder or "")) / f"{lang}.traineddata"
            key = str(path)
            if key not in self.model_sha:
                try:
                    self.model_sha[key] = hashlib.sha256(path.read_bytes()).hexdigest()
                except OSError:
                    self.model_sha[key] = "unreadable"
            out.append({"name": lang, "sha256": self.model_sha[key]})
        return out

    def tesseract(
        self,
        model: Any,
        page: Any,
        region: int,
        rect: Any,
        attempt: int,
        raws: list[str],
    ) -> None:
        bbox = None
        if rect is not None:
            bbox = [
                rect.l,
                rect.t,
                rect.r,
                rect.b,
                str(getattr(rect, "coord_origin", "")),
            ]
        for raw in raws:
            with self.lock:
                self.count += 1
                n = self.count
                models = self._models(model)
            stem = f"tesseract/{int(page.page_no):04d}_{region + 1:03d}_{n:06d}"
            self._write(stem + ".tsv", raw)
            self._write(
                stem + ".json",
                json.dumps(
                    {
                        "schema": "chatbot5400-ocr-evidence/1",
                        "document": self.document,
                        "page": int(page.page_no),
                        "region": region + 1,
                        "bbox": bbox,
                        "invocation": f"{int(page.page_no):04d}-{region + 1:03d}-{n:06d}",
                        "attempt": attempt,
                        "engine": _engine_label(model),
                        "model_files": models,
                    },
                    ensure_ascii=False,
                ),
            )
            if rect is not None:
                with self.lock:
                    self.crops.setdefault(int(page.page_no), []).append(
                        (rect, _old_forms(raw))
                    )

    def element(
        self, model: Any, page: Any, cluster: Any, cells: list[Any], text: str
    ) -> None:
        with self.lock:
            crops = list(self.crops.get(int(page.page_no), []))
        old: list[str] = []
        for cell in cells:
            value: Optional[str] = cell.text.replace("\x02", "-").strip()
            if getattr(cell, "from_ocr", False):
                forms = _crop_of(cell, crops)
                if forms is not None and value in forms:
                    value = forms[value]
            if value:
                old.append(value)
        v120 = text_upstream("sanitize_text")(model, old)
        box = cluster.bbox
        self._line(
            "elements.jsonl",
            {
                "page": int(page.page_no),
                "cluster": int(cluster.id),
                "label": str(getattr(cluster.label, "value", cluster.label)),
                "bbox": [box.l, box.t, box.r, box.b],
                "text": text,
                "v120_text": v120,
            },
        )

    def merge(self, record: dict[str, Any]) -> None:
        self._line("merges.jsonl", record)

    def footnote(self, note: Any, written: str) -> None:
        prov = (getattr(note, "prov", None) or [None])[0]
        self._line(
            "footnotes.jsonl",
            {"page": getattr(prov, "page_no", None), "text": written, "v120_text": ""},
        )


def _old_forms(raw: str) -> dict[str, Optional[str]]:
    """raw cell text -> what Docling 2.129.0's pandas parse made of it in THIS
    crop (None: dropped)."""
    import pandas as pd

    df = pd.read_csv(io.StringIO(raw), quoting=csv.QUOTE_NONE, sep="\t")
    upstream = df[df["text"].notna() & (df["text"].apply(str).str.strip() != "")]
    ours = read_tesseract_tsv_plain(raw)
    forms: dict[str, Optional[str]] = {}
    for i, row in ours.iterrows():
        text = str(row["text"])
        if not text.strip():
            continue
        forms[text.strip()] = (
            str(upstream.loc[i, "text"]).strip() if i in upstream.index else None
        )
    return forms


def read_tesseract_tsv_plain(decoded_data: str) -> Any:
    """read_tesseract_tsv without the evidence capture."""
    saved = getattr(_capture, "raw", None)
    _capture.raw = None
    try:
        return read_tesseract_tsv(decoded_data)
    finally:
        _capture.raw = saved


def _crop_of(cell: Any, crops: list[tuple[Any, dict[str, Optional[str]]]]) -> Any:
    try:
        box = cell.rect.to_bounding_box().to_top_left_origin(10**9)
    except Exception:  # noqa: BLE001
        return None
    cx, cy = (box.l + box.r) / 2, (box.t + box.b) / 2
    for rect, forms in crops:
        if rect.l <= cx <= rect.r and rect.t <= cy <= rect.b:
            return forms
    return None


def _record_merge(new_item: Any, merged_elem: Any) -> None:
    sink = _evidence
    if sink is None:
        return
    head = new_item.text.split()
    cont = merged_elem.text.split()
    if not head or not cont:
        return
    sink.merge(
        {
            "page": getattr(merged_elem, "page_no", None),
            "text": head[-1] + cont[0],
            "v120_text": head[-1][:-1] + cont[0],
        }
    )


class evidence_capture:  # noqa: N801 - used like a function
    """``with evidence_capture(folder, document):`` - record the evidence of
    the conversion(s) run in the block (Standard gate export only)."""

    def __init__(self, folder: Path, document: str) -> None:
        self.sink = EvidenceSink(Path(folder), document)

    def __enter__(self) -> EvidenceSink:
        global _evidence
        with _lock:
            if _evidence is not None:
                raise RuntimeError("an evidence capture is already running")
            _evidence = self.sink
        return self.sink

    def __exit__(self, *exc: Any) -> None:
        global _evidence
        with _lock:
            _evidence = None
