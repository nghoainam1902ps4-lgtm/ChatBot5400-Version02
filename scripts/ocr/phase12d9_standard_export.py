#!/usr/bin/env python3
"""Export Standard outputs WITH the evidence of the same conversion (Phase 12D9).

The input of the Standard expected-diff gate (``phase12_standard_diff.py``,
D8-STD-03): each PDF of ``--input`` is converted ONCE with the application's
production path (``open_notebook.ocr.docling_extract.convert_file``, Standard
mode, the engine of ``--engine``), and that very conversion writes

* ``<out>/<name>.md``            the Standard content a Source would store;
* ``<out>/<name>.evidence/``     the raw TSV of every Tesseract invocation with
                                 its provenance, the v1.2.0 and candidate texts
                                 of every text region, Docling's block joins,
                                 the attached footnotes written
                                 (``docling_patches.evidence_capture``);
* ``<out>/manifest.json``        document names, input / output SHA-256,
                                 conversion status, versions, engine, commit;
                                 with evidence also two COUNTS for the D8-03
                                 gate: words with a ``-`` in the raw TSV, and how
                                 many of them the output shows verbatim.

Run it in the application environment (the container, models installed). On a
checkout without the evidence capture (v1.2.0, which has no patch module) it
exports the outputs and the manifest only - that is the ``--before`` side of
the gate. The v1.2.0 image does not ship this script: copy it to
``/app/scripts/ocr/`` of that container first (``docker compose cp``).

Privacy: the outputs and the evidence hold document text. They are written
with owner-only permissions under ``--out`` and never printed: the console
shows counts only. Do not upload or commit them.

Usage (inside the container)::

  python scripts/ocr/phase12d9_standard_export.py --input /data/pdfs \\
      --engine tesseract_best --out /data/out/candidate
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "chatbot5400-standard-export/2"


def _private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _write_private(path: Path, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _commit() -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() or None


def _versions() -> dict[str, Optional[str]]:
    from importlib.metadata import PackageNotFoundError, version

    out: dict[str, Optional[str]] = {}
    for dist in ("docling", "docling-core", "content-core"):
        try:
            out[dist] = version(dist)
        except PackageNotFoundError:
            out[dist] = None
    return out


def _model_files(engine: str, custom_version: Optional[str]) -> dict[str, str]:
    from open_notebook.ocr import catalog, paths
    from open_notebook.ocr.options import engine_langs, rapidocr_persistent

    spec = catalog.get_engine(engine)
    if spec.docling_kind == "tesseract":
        sources = {
            lang: paths.tessdata_dir() / f"{lang}.traineddata"
            for lang in engine_langs(engine, custom_version)
        }
        if (paths.tessdata_dir() / "osd.traineddata").is_file():
            sources["osd"] = paths.tessdata_dir() / "osd.traineddata"
    elif spec.docling_kind == "rapidocr":
        from open_notebook.ocr import installer

        package = installer.rapidocr_package_model_dir()
        directory = paths.rapidocr_dir() if rapidocr_persistent() else package
        files = installer.rapidocr_known_checksums()
        sources = (
            {p.name: p for p in directory.iterdir() if p.is_file() and p.name in files}
            if directory and directory.is_dir()
            else {}
        )
        if package and package.is_dir():
            sources.update({f"package/{p.name}": p for p in package.glob("*.txt")})
    else:
        sources = {
            file.rel_path: paths.models_dir() / file.rel_path for file in spec.files
        }
    try:
        return {name: _sha(path) for name, path in sources.items()}
    except OSError:
        return {}


def hyphen_words(evidence: Path, content: str) -> dict[str, int]:
    """D8-03 local gate (counts only): the words with a ``-`` Tesseract read in
    this very conversion, and how many of them the stored content shows
    verbatim. Fewer in the output = a hyphen may be lost: check that document
    locally. Never returns or prints a word."""
    words: list[str] = []
    for tsv in sorted((evidence / "tesseract").glob("*.tsv")):
        lines = tsv.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines:
            continue
        header = lines[0].split("\t")
        if "text" not in header or "level" not in header:
            continue
        col, lvl = header.index("text"), header.index("level")
        for line in lines[1:]:
            cells = line.split("\t")
            if len(cells) <= max(col, lvl) or cells[lvl] != "5":
                continue
            if "-" in cells[col]:
                words.append(cells[col])
    occupied: set[int] = set()
    found = 0
    for word in sorted(words, key=len, reverse=True):
        for match in re.finditer(re.escape(word), content):
            span = range(match.start(), match.end())
            if occupied.isdisjoint(span):
                occupied.update(span)
                found += 1
                break
    return {"tsv_hyphen_words": len(words), "tsv_hyphen_words_in_output": found}


def export(
    input_dir: Path,
    out: Path,
    engine: str,
    custom_version: Optional[str] = None,
    convert: Any = None,
    *,
    commit: Optional[str] = None,
    image_id: Optional[str] = None,
) -> dict[str, Any]:
    """Convert every PDF of ``input_dir``; returns the manifest."""
    capture: Any = None  # v1.2.0: no evidence capture
    try:
        from open_notebook.ocr import docling_patches
    except ImportError:  # v1.2.0 has no patch module at all
        pass
    else:
        capture = getattr(docling_patches, "evidence_capture", None)
    if convert is None:
        from content_core import ContentCoreConfig

        from open_notebook.ocr.docling_extract import convert_file
        from open_notebook.ocr.options import OcrSettings

        settings = OcrSettings(engine=engine, custom_version=custom_version).pinned()
        custom_version = settings.custom_version
        config = ContentCoreConfig()

        def convert(path: Path) -> tuple[str, dict[str, Any]]:
            text, metadata = convert_file(str(path), config, settings)
            metadata["settings"] = {
                "force_full_page": settings.force_full_page,
                "docling_ocr": config.docling_ocr,
                "docling_formulas": config.docling_formulas,
                "docling_vision": config.docling_vision,
                "num_threads": settings.num_threads,
                "watermark": os.environ.get("OCR_AUTO_FULL_PAGE_ON_WATERMARK", "false"),
            }
            return text, metadata

        model_files = _model_files(engine, custom_version)
    else:
        model_files = {}

    if out.exists() and any(out.iterdir()):
        # outputs of two runs must never mix: a stale <name>.md would be compared
        raise SystemExit(f"--out must be a new or empty folder: {out}")
    _private_dir(out)
    pdfs = sorted(p for p in input_dir.iterdir() if p.suffix.lower() == ".pdf")
    names = [p.stem for p in pdfs]
    if len({n.casefold() for n in names}) != len(names):
        raise SystemExit("two input files have the same name (case-insensitive)")
    run_id = uuid.uuid4().hex
    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "run_id": run_id,
        "commit": commit or _commit(),
        "image_id": image_id,
        "versions": _versions(),
        "engine": engine,
        "custom_version": custom_version,
        "evidence": capture is not None,
        "documents": [],
    }
    for pdf in pdfs:
        name = pdf.stem
        entry: dict[str, Any] = {"name": name, "input_sha256": _sha(pdf)}
        try:
            if capture is not None:
                evidence = out / f"{name}.evidence"
                _private_dir(evidence)
                with capture(evidence, name) as sink:
                    sink.run_id = run_id
                    content, meta = convert(pdf)
            else:
                content, meta = convert(pdf)
        except Exception as e:  # noqa: BLE001 - recorded, the gate then fails
            entry["error"] = type(e).__name__
            manifest["documents"].append(entry)
            continue
        target = out / f"{name}.md"
        _write_private(target, content)
        entry.update(
            output="{}.md".format(name),
            output_sha256=_sha(target),
            conversion_status=meta.get("conversion_status"),
            conversion_errors=meta.get("conversion_errors", 0),
            ocr_engine=meta.get("ocr_engine"),
            ocr_model_version=meta.get("ocr_model_version"),
            ocr_model_sha256=meta.get("ocr_model_sha256"),
            ocr_model_files=meta.get("ocr_model_files") or model_files,
            ocr_config={
                key: meta.get(key)
                for key in (
                    "settings",
                    "scan_dpi",
                    "ocr_scale",
                    "ocr_mode_configured",
                    "ocr_mode_effective",
                    "auto_full_page",
                    "auto_full_page_reason",
                    "layout_model",
                    "table_model",
                    "table_mode",
                    "docling_format",
                    "ocr_models",
                )
            },
        )
        if capture is not None:
            entry.update(hyphen_words(out / f"{name}.evidence", content))
            evidence = out / f"{name}.evidence"
            entry["evidence_files"] = {
                p.relative_to(evidence).as_posix(): _sha(p)
                for p in sorted(evidence.rglob("*"))
                if p.is_file()
            }
            entry["hyphen_occurrence_status"] = (
                "requires release gate with source spans"
            )
        manifest["documents"].append(entry)
    _write_private(
        out / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1)
    )
    return manifest


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--input", required=True, help="folder of PDFs")
    p.add_argument("--out", required=True, help="output folder (created, owner-only)")
    p.add_argument("--engine", required=True, help="OCR engine id, e.g. tesseract_best")
    p.add_argument("--custom-version", help="custom model version (Agri)")
    p.add_argument("--commit", help="exact source SHA of the running image")
    p.add_argument("--image-id", help="exact ID of the running image")
    args = p.parse_args(argv)
    manifest = export(
        Path(args.input),
        Path(args.out),
        args.engine,
        args.custom_version,
        commit=args.commit,
        image_id=args.image_id,
    )
    docs = manifest["documents"]
    failed = sum(1 for d in docs if "error" in d)
    print(
        json.dumps(
            {
                "documents": len(docs),
                "converted": len(docs) - failed,
                "failed": failed,
                "evidence": manifest["evidence"],
            }
        )
    )
    return 1 if failed or not docs else 0


if __name__ == "__main__":
    sys.exit(main())
