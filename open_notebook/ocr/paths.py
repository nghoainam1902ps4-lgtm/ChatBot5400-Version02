"""Filesystem layout for the OCR Engine Manager.

Everything lives under the persistent data volume (``/app/data`` in Docker,
``./data`` in dev) so downloaded models survive container restarts, image
updates and recreation::

    <data>/ocr/
    ├── models/            OCR_MODELS_DIR    verified model weights only
    │   ├── tesseract/     == TESSDATA_PREFIX (see DECISIONS D-04)
    │   │   ├── osd.traineddata       shared by fast + best
    │   │   ├── fast/{vie,eng}.traineddata
    │   │   └── best/{vie,eng}.traineddata
    │   └── easyocr/{craft_mlt_25k,latin_g2}.pth
    ├── packages/          OCR_PACKAGES_DIR  offline bundles (models/, wheels/, debs/)
    ├── manifests/         OCR_MANIFESTS_DIR per-engine install state (JSON)
    ├── downloads/         staging (.part files, locks) — never read by OCR
    └── logs/

RapidOCR keeps its models where RapidOCR itself stores them (unchanged
behavior); Layout/TableFormer stay in HF_HOME. Nothing here duplicates them.
"""

from __future__ import annotations

import os
from pathlib import Path

from open_notebook.config import DATA_FOLDER


def _env_dir(name: str, default: Path) -> Path:
    raw = os.environ.get(name, "").strip()
    return Path(raw).expanduser().resolve() if raw else default.resolve()


def ocr_root() -> Path:
    return _env_dir("OCR_DATA_DIR", Path(DATA_FOLDER) / "ocr")


def models_dir() -> Path:
    return _env_dir("OCR_MODELS_DIR", ocr_root() / "models")


def packages_dir() -> Path:
    return _env_dir("OCR_PACKAGES_DIR", ocr_root() / "packages")


def manifests_dir() -> Path:
    return _env_dir("OCR_MANIFESTS_DIR", ocr_root() / "manifests")


def downloads_dir() -> Path:
    return ocr_root().joinpath("downloads").resolve()


def logs_dir() -> Path:
    return ocr_root().joinpath("logs").resolve()


def tessdata_dir() -> Path:
    """The single TESSDATA_PREFIX used for both Tesseract variants (D-04)."""
    return models_dir() / "tesseract"


def easyocr_dir() -> Path:
    return models_dir() / "easyocr"


def ensure_dirs() -> None:
    for d in (
        models_dir(),
        packages_dir(),
        manifests_dir(),
        downloads_dir(),
        logs_dir(),
    ):
        d.mkdir(parents=True, exist_ok=True)


def safe_child(base: Path, rel: str) -> Path:
    """Resolve ``rel`` under ``base`` and refuse anything that escapes it.

    ``rel`` only ever comes from the hard-coded catalog, but this guards against
    a future mistake and against symlinks planted inside the data volume.
    """
    if not rel or rel.startswith(("/", "\\")) or "\x00" in rel:
        raise ValueError(f"Invalid relative path: {rel!r}")
    base_resolved = base.resolve()
    target = (base_resolved / rel).resolve()
    if target != base_resolved and base_resolved not in target.parents:
        raise ValueError(f"Path escapes {base_resolved}: {rel!r}")
    return target


def offline_mode() -> bool:
    """OCR_OFFLINE=true forbids any network download (bundle/local files only)."""
    return os.environ.get("OCR_OFFLINE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
