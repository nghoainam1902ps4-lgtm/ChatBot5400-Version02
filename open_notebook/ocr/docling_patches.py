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
import importlib
import importlib.metadata
import inspect
import io
import re
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
                        text = self.sanitize_text(
                            textlines, same_line=same_line_flags(kept_cells)
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
        out.append(
            create_ser_result(
                text=doc_serializer.post_process(text=note.text), span_source=note
            )
        )
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
