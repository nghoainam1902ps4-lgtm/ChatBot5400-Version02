"""Dependency compatibility guard for the OCR Engine Manager (DECISIONS D-14).

The OCR layer (docling_extract.py) mirrors a few INTERNAL pieces of content-core
(Docling option building, MIME routing, URL download) and relies on specific
Docling behaviours (Auto OCR selection order, Tesseract CLI language probing).
Those are not public APIs, so a dependency upgrade could silently change them.

Two independent checks, both must pass for the native OCR path:

1. Versions — the exact versions verified by this release (also enforced at
   install time through constraints exported from uv.lock).
2. Source fingerprints — SHA-256 of the source of every mirrored/relied-upon
   function. Any change means "re-verify before use", even for a same-version
   rebuild or a patched wheel.

On mismatch the selected non-default engine reports ``incompatible`` (never a
silent fallback) and the default RapidOCR path keeps using content-core as-is.
An operator who has re-verified can set OCR_ALLOW_UNVERIFIED_DEPENDENCIES=true.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import inspect
import os
from functools import lru_cache
from typing import Any

VERIFIED_VERSIONS: dict[str, str] = {
    "content-core": "2.0.7",
    "docling": "2.129.0",
}
# Engine-specific runtime versions (only relevant when that engine is used).
VERIFIED_ENGINE_VERSIONS: dict[str, dict[str, str]] = {
    "rapidocr": {"rapidocr": "3.9.2"},
    "easyocr": {"easyocr": "1.7.2"},
}

CONTENT_CORE_FINGERPRINTS: dict[str, str] = {
    "content_core.extraction:_download_remote_file": "824804c9837a47b9d50a816bf0d588bab3446bbe13f01fc29a3e7ae1b5ced423",
    "content_core.extraction:_extract_file": "4214ea6f55ffc6607c7e4c283e684315c7d285c9e0860fa292a368e23f81b1fb",
    "content_core.extraction:_extract_url": "db8926c807ca7ab575af41a6ffc8eef8cc79ddfaf9623a5c3f73113a160c7511",
    "content_core.extraction:_fetch_remote_file": "057053654d7de2f915a3806c27b4cc3958be4dbc3127ce8587af60f4d0b00d4c",
    "content_core.extraction:_route_for_mime": "d0cececc5a7f52af9e4709b003018cd136f645211c67df7574249e7cf2aa2e79",
    "content_core.processors.document.docling:extract_docling": "62a0daf9b0f616f2138a7d5e1a01dc97de19a28f97e9990d136d02b686279528",
    "content_core.processors.url:detect_remote_mime": "b7105c15e0e0fb11f8109d060fadf4f80cd1c2ea45954b132b7ddf963b2a7aab",
}
DOCLING_FINGERPRINTS: dict[str, str] = {
    "docling.models.stages.ocr.auto_ocr_model:OcrAutoModel.__init__": "1e905edb7f52504381e3e5737ac511fc48190927d79bf1e0c7e9d4cc994cf990",
    "docling.models.stages.ocr.tesseract_ocr_cli_model:TesseractOcrCliModel._run_tesseract": "e0623aa9536128c833896869f39e27e52c10f66aa0ac51cb76418e3d61de233c",
    "docling.models.stages.ocr.tesseract_ocr_cli_model:TesseractOcrCliModel._set_languages": "0490147bdbe9dac9ecfc7b11af8030c0e4cddbf94e8e80814ec041929f0cef84",
}

OVERRIDE_ENV = "OCR_ALLOW_UNVERIFIED_DEPENDENCIES"


def override_enabled() -> bool:
    return os.environ.get(OVERRIDE_ENV, "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _version(dist: str) -> str | None:
    try:
        return importlib.metadata.version(dist)
    except importlib.metadata.PackageNotFoundError:
        return None


def source_fingerprint(target: str) -> str | None:
    """sha256 of ``inspect.getsource`` for ``module:Qualified.name``; None if absent."""
    mod_name, _, attr = target.partition(":")
    try:
        obj: Any = importlib.import_module(mod_name)
        for part in attr.split("."):
            obj = getattr(obj, part)
        return hashlib.sha256(inspect.getsource(obj).encode("utf-8")).hexdigest()
    except Exception:
        return None


def check_fingerprints(expected: dict[str, str]) -> list[str]:
    problems = []
    for target, digest in expected.items():
        actual = source_fingerprint(target)
        if actual is None:
            problems.append(f"{target} is missing")
        elif actual != digest:
            problems.append(f"{target} changed since it was verified")
    return problems


def check_versions(expected: dict[str, str]) -> list[str]:
    problems = []
    for dist, version in expected.items():
        actual = _version(dist)
        if actual != version:
            problems.append(f"{dist} {actual or 'not installed'} (verified: {version})")
    return problems


@lru_cache(maxsize=1)
def _content_core_report() -> tuple[str, ...]:
    return tuple(
        check_versions(VERIFIED_VERSIONS)
        + check_fingerprints(CONTENT_CORE_FINGERPRINTS)
    )


@lru_cache(maxsize=1)
def _docling_report() -> tuple[str, ...]:
    return tuple(check_fingerprints(DOCLING_FINGERPRINTS))


def problems(
    engine_id: str | None = None, include_docling_sources: bool = True
) -> list[str]:
    """All compatibility problems relevant to the native OCR path for ``engine_id``.

    ``include_docling_sources`` imports Docling OCR modules (torch): use it only
    where Docling is loaded anyway (worker, probe subprocess).
    """
    found = list(_content_core_report())
    if include_docling_sources:
        found += list(_docling_report())
    if engine_id:
        found += check_versions(VERIFIED_ENGINE_VERSIONS.get(engine_id, {}))
    return found


def ensure_compatible(engine_id: str) -> None:
    """Raise ValueError (clear, permanent) unless dependencies are verified."""
    found = problems(engine_id)
    if found and not override_enabled():
        raise ValueError(
            "OCR engine selection is disabled because dependencies differ from the "
            "verified set: "
            + "; ".join(found)
            + f". Re-verify, then set {OVERRIDE_ENV}=true."
        )


def reset_cache() -> None:
    _content_core_report.cache_clear()
    _docling_report.cache_clear()
