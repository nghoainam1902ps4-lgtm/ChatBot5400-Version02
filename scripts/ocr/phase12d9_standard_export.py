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
                                 conversion status, versions, engine, commit.

Run it in the application environment (the container, models installed). On a
checkout without the evidence capture (v1.2.0) it exports the outputs and the
manifest only - that is the ``--before`` side of the gate.

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
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "chatbot5400-standard-export/1"


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


def export(
    input_dir: Path,
    out: Path,
    engine: str,
    custom_version: Optional[str] = None,
    convert: Any = None,
) -> dict[str, Any]:
    """Convert every PDF of ``input_dir``; returns the manifest."""
    from open_notebook.ocr import docling_patches as P

    capture = getattr(P, "evidence_capture", None)  # absent on v1.2.0
    if convert is None:
        from content_core import ContentCoreConfig

        from open_notebook.ocr.docling_extract import convert_file
        from open_notebook.ocr.options import OcrSettings

        settings = OcrSettings(engine=engine, custom_version=custom_version)

        def convert(path: Path) -> tuple[str, dict[str, Any]]:
            return convert_file(str(path), ContentCoreConfig(), settings)

    _private_dir(out)
    pdfs = sorted(p for p in input_dir.iterdir() if p.suffix.lower() == ".pdf")
    names = [p.stem for p in pdfs]
    if len({n.casefold() for n in names}) != len(names):
        raise SystemExit("two input files have the same name (case-insensitive)")
    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "commit": _commit(),
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
                with capture(evidence, name):
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
            ocr_engine=meta.get("ocr_engine"),
            ocr_model_version=meta.get("ocr_model_version"),
            ocr_model_sha256=meta.get("ocr_model_sha256"),
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
    args = p.parse_args(argv)
    manifest = export(
        Path(args.input), Path(args.out), args.engine, args.custom_version
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
