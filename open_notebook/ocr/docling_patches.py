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
upstream code, unchanged (a test compares the AST with upstream). Nothing in
pandas is patched; nothing else in Docling is touched. RapidOCR / EasyOCR do
not use this code. The recognised text is never modified: what Tesseract
wrote in the TSV is what the OCR cell holds.

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
import importlib.metadata
import inspect
import io
import subprocess
import threading
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
        cmd, stdout=PIPE, stderr=DEVNULL, stdin=DEVNULL, check=True, shell=False
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
    return found


def is_applied() -> bool:
    try:
        current = _upstream_class().__dict__.get("_run_tesseract")
    except Exception:  # noqa: BLE001 - docling not importable
        return False
    return getattr(current, "__cb5400_patch__", None) == PATCH_ID


def apply() -> None:
    """Apply the patch (idempotent). Raise TsvPatchError when it cannot be applied."""
    with _lock:
        if is_applied():
            return
        found = problems()
        if found:
            raise TsvPatchError(
                "Tesseract OCR is disabled: "
                + "; ".join(found)
                + ". Without the patch numbers recognised by Tesseract change in the text "
                "(0001 -> 1.0). Use the verified Docling version or update the patch."
            )
        cls = _upstream_class()
        original = cls.__dict__["_run_tesseract"]

        def patched(self: Any, ifilename: str, osd: Optional[Any]):
            return _run_tesseract(self, ifilename, osd)

        patched.__cb5400_patch__ = PATCH_ID  # type: ignore[attr-defined]
        patched.__cb5400_upstream__ = original  # type: ignore[attr-defined]
        patched.__doc__ = original.__doc__
        patched.__name__ = original.__name__
        patched.__qualname__ = original.__qualname__
        cls._run_tesseract = patched


def status() -> dict[str, Any]:
    """For diagnostics / status output."""
    return {
        "patch": PATCH_ID,
        "docling": _installed_docling(),
        "applied": is_applied(),
        "problems": problems() if not is_applied() else [],
    }
