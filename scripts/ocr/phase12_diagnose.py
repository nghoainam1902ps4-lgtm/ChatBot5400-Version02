#!/usr/bin/env python3
"""Phase 12A diagnostic harness: follow ONE PDF through every layer of the pipeline.

LOCAL USE ONLY. Run it inside the ChatBot5400 container (or a checkout with the
``docling`` extra) on the machine that holds the document. It never uploads
anything, never writes to the database and is not part of ingestion: nothing
runs unless an operator starts this script.

For one PDF, one engine, one render configuration it writes, in ``--out``:

  00_environment.json          versions, engine options, render scale (no text)
  01_tesseract_pXXX.txt/.tsv   direct Tesseract OCR of each page (Tesseract engines)
  02_ocr_cells.json            OCR / PDF text cells Docling kept per page (if exposed)
  03_layout_clusters.json      layout clusters (label, confidence, bbox, cells)
  04_assembled_elements.json   elements after cell merge / page assembly
  05_docling_document.json     the DoclingDocument (export_to_dict)
  06_items.json                reading order: label, layer, marker, enumerated, prov
  07_markdown_standard.md      what v1.2.0 stores (standard export)
  08_markdown_legal.md         Legal Document normalization of the SAME document
  09_legal_report.json         every normalization operation, with before / after
  10_display_standard.txt      what the frontend shows for 07 (CommonMark)
  10_display_legal.txt         what the frontend shows for 08
  11_source_full_text.md       (optional) the Source text stored by a local API
  12_summary.json              per-layer counts and the layer where words disappear

The output contains the document's text: keep it on the local machine, delete
it when done. The directory is created with owner-only permissions.

Examples (inside the test container)::

  python scripts/ocr/phase12_diagnose.py /import/qd.pdf --engine tesseract_agri \
      --out /app/data/phase12-diagnostics/qd
  python scripts/ocr/phase12_diagnose.py /import/qd.pdf --engine rapidocr --out ... \
      --ground-truth /import/qd.gt.txt
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import phase12_metrics as M  # noqa: E402

SCHEMA = "chatbot5400-phase12-diagnostic/1"


def _write(path: Path, data: Any) -> None:
    if isinstance(data, (dict, list)):
        text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    else:
        text = str(data)
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)


def _bbox(b: Any) -> list[float] | None:
    if b is None:
        return None
    try:
        return [
            round(float(b.l), 1),
            round(float(b.t), 1),
            round(float(b.r), 1),
            round(float(b.b), 1),
            str(getattr(b.coord_origin, "value", b.coord_origin)),
        ]
    except Exception:
        return None


def _prepare_out(out: Path, overwrite: bool) -> None:
    if out.exists() and any(out.iterdir()):
        if not overwrite:
            raise SystemExit(
                f"{out} is not empty (use --overwrite to replace its files)"
            )
    out.mkdir(parents=True, exist_ok=True)
    os.chmod(out, 0o700)


def _versions() -> dict[str, Any]:
    from importlib.metadata import PackageNotFoundError, version

    info: dict[str, Any] = {}
    for pkg in (
        "docling",
        "docling-core",
        "docling-ibm-models",
        "content-core",
        "pypdfium2",
        "rapidocr",
        "easyocr",
        "open-notebook",
    ):
        try:
            info[pkg] = version(pkg)
        except PackageNotFoundError:
            info[pkg] = None
    tess = shutil.which("tesseract")
    if tess:
        try:
            out = subprocess.run(
                [tess, "--version"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )  # noqa: S603
            info["tesseract"] = (out.stdout or out.stderr).splitlines()[0]
        except (OSError, subprocess.SubprocessError):
            info["tesseract"] = "unknown"
    return info


# --------------------------------------------------------------------------- #
# Layer 1: direct Tesseract
# --------------------------------------------------------------------------- #


def direct_tesseract(
    pdf: Path, out: Path, langs: list[str], tessdata: str | None, dpi: int, psm: int
) -> list[str]:
    import pypdfium2 as pdfium

    tess = shutil.which("tesseract")
    if not tess or not langs:
        return []
    texts: list[str] = []
    doc = pdfium.PdfDocument(str(pdf))
    try:
        for i in range(len(doc)):
            image = doc[i].render(scale=dpi / 72).to_pil().convert("L")
            png = out / f".page_{i + 1:03d}.png"
            image.save(png)
            base = [
                tess,
                str(png),
                "stdout",
                "-l",
                "+".join(langs),
                "--psm",
                str(psm),
                "--dpi",
                str(dpi),
            ]
            if tessdata:
                base[3:3] = ["--tessdata-dir", tessdata]
            txt = subprocess.run(
                base, capture_output=True, text=True, timeout=600, check=False
            )  # noqa: S603
            tsv = subprocess.run(
                base + ["tsv"], capture_output=True, text=True, timeout=600, check=False
            )  # noqa: S603
            png.unlink(missing_ok=True)
            _write(out / f"01_tesseract_p{i + 1:03d}.txt", txt.stdout)
            _write(out / f"01_tesseract_p{i + 1:03d}.tsv", tsv.stdout)
            texts.append(txt.stdout)
    finally:
        doc.close()
    return texts


# --------------------------------------------------------------------------- #
# Layers 2-6: Docling, with the production conversion
# --------------------------------------------------------------------------- #


def docling_layers(result: Any) -> dict[str, Any]:
    cells, clusters = [], []
    for page in getattr(result, "pages", []) or []:
        page_no = getattr(page, "page_no", None)
        parsed = getattr(page, "parsed_page", None)
        page_cells = []
        for attr in ("textline_cells", "word_cells"):
            for c in getattr(parsed, attr, None) or []:
                page_cells.append(
                    {
                        "kind": attr,
                        "text": getattr(c, "text", ""),
                        "from_ocr": getattr(c, "from_ocr", None),
                        "confidence": getattr(c, "confidence", None),
                        "bbox": _bbox(
                            getattr(
                                getattr(c, "rect", None),
                                "to_bounding_box",
                                lambda: None,
                            )()
                        ),
                    }
                )
        cells.append(
            {"page": page_no, "available": parsed is not None, "cells": page_cells}
        )
        layout = getattr(getattr(page, "predictions", None), "layout", None)
        for cl in getattr(layout, "clusters", None) or []:
            clusters.append(
                {
                    "page": page_no,
                    "id": cl.id,
                    "label": str(getattr(cl.label, "value", cl.label)),
                    "confidence": round(float(cl.confidence), 3),
                    "bbox": _bbox(cl.bbox),
                    "cells": len(cl.cells),
                    "text": " ".join(c.text for c in cl.cells),
                    "children": len(getattr(cl, "children", []) or []),
                }
            )
    assembled = []
    for el in getattr(getattr(result, "assembled", None), "elements", None) or []:
        assembled.append(
            {
                "page": el.page_no,
                "id": el.id,
                "type": type(el).__name__,
                "label": str(getattr(el.label, "value", el.label)),
                "text": getattr(el, "text", None),
                "bbox": _bbox(el.cluster.bbox),
            }
        )
    return {"cells": cells, "clusters": clusters, "assembled": assembled}


def item_rows(doc: Any) -> list[dict[str, Any]]:
    from docling_core.types.doc.document import ContentLayer

    rows = []
    for n, (item, level) in enumerate(
        doc.iterate_items(
            with_groups=True,
            traverse_pictures=True,
            included_content_layers=set(ContentLayer),
        )
    ):
        parent = getattr(item, "parent", None)
        rows.append(
            {
                "index": n,
                "level": level,
                "ref": str(getattr(item, "self_ref", "")),
                "parent": getattr(parent, "cref", None),
                "type": type(item).__name__,
                "label": str(
                    getattr(
                        getattr(item, "label", None),
                        "value",
                        getattr(item, "label", ""),
                    )
                ),
                "layer": str(
                    getattr(getattr(item, "content_layer", None), "value", "")
                ),
                "marker": getattr(item, "marker", None),
                "enumerated": getattr(item, "enumerated", None),
                "text": getattr(item, "text", None),
                "prov": [
                    {"page": p.page_no, "bbox": _bbox(p.bbox)}
                    for p in getattr(item, "prov", None) or []
                ],
            }
        )
    return rows


def _words(text: str) -> int:
    return len(M._norm(text).split())


def summarize(
    direct: list[str],
    layers: dict[str, Any],
    rows: list[dict[str, Any]],
    standard: str,
    legal: str,
    legal_report: dict[str, Any],
    gt: str | None,
    source_text: str | None,
) -> dict[str, Any]:
    body_text = " ".join(r["text"] or "" for r in rows if r["layer"] == "body")
    under_pictures = [
        r for r in rows if r["parent"] and r["parent"].startswith("#/pictures/")
    ]
    std_lines, leg_lines = M.display_lines(standard), M.display_lines(legal)
    std_renum, std_ordered = M.renumbered_list_items(standard)
    layer_words = {
        "direct_tesseract": _words(" ".join(direct)) if direct else None,
        "ocr_cells": _words(
            " ".join(c["text"] for p in layers["cells"] for c in p["cells"])
        )
        or None,
        "layout_clusters": _words(" ".join(c["text"] for c in layers["clusters"]))
        or None,
        "assembled_elements": _words(
            " ".join(e["text"] or "" for e in layers["assembled"])
        )
        or None,
        "docling_body_items": _words(body_text),
        "markdown_standard_display": _words(" ".join(std_lines)),
        "markdown_legal_display": _words(" ".join(leg_lines)),
    }
    summary: dict[str, Any] = {
        "schema": SCHEMA,
        "words_per_layer": layer_words,
        "items_by_label": _count(r["label"] for r in rows if r["type"] != "GroupItem"),
        "furniture_items": sum(1 for r in rows if r["layer"] == "furniture"),
        "text_items_under_pictures": len(under_pictures),
        "text_items_under_pictures_dropped_by_standard_export": sum(
            1 for r in under_pictures if (r["text"] or "").strip()
        ),
        "list_items_without_marker": sum(
            1
            for r in rows
            if r["type"] == "ListItem" and not (r["marker"] or "").strip()
        ),
        "standard": {
            "placeholders": M.placeholder_count(standard),
            "numeric_only_lines": M.numeric_only_lines(std_lines),
            "ordered_items_renumbered_by_renderer": std_renum,
            "ordered_items": std_ordered,
        },
        "legal": {
            "placeholders": M.placeholder_count(legal),
            "numeric_only_lines": M.numeric_only_lines(leg_lines),
            "ordered_items_renumbered_by_renderer": M.renumbered_list_items(legal)[0],
            "counts": legal_report.get("legal_normalization_counts"),
            "warnings": [w.get("code") for w in legal_report.get("warnings", [])],
            "ms": legal_report.get("legal_normalization_ms"),
        },
    }
    if direct:
        summary["page_end_words_in_standard"] = M.page_boundary_report(
            direct, " ".join(std_lines)
        )
        summary["page_end_words_in_legal"] = M.page_boundary_report(
            direct, " ".join(leg_lines)
        )
        summary["words_lost_direct_to_standard"] = M.lost_words(
            " ".join(direct), " ".join(std_lines)
        )
    if gt is not None:
        summary["ground_truth"] = {
            name: {
                "cer": round(M.cer(gt, text), 4),
                "wer": round(M.wer(gt, text), 4),
                "recall": round(M.word_recall(gt, text), 4),
            }
            for name, text in (
                ("direct_tesseract", " ".join(direct)),
                ("standard", " ".join(M.display_lines(standard, list_prefixes=False))),
                ("legal", " ".join(leg_lines)),
            )
            if text
        }
    if source_text is not None:
        summary["stored_source_equals"] = (
            "legal"
            if source_text.strip() == legal.strip()
            else "standard"
            if source_text.strip() == standard.strip()
            else "neither"
        )
    return summary


def _count(values: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))


def fetch_source(
    api_url: str, source_id: str, token_env: str | None, allow_remote: bool
) -> str:
    import urllib.parse
    import urllib.request

    parsed = urllib.parse.urlparse(api_url)
    if parsed.scheme not in ("http", "https"):
        raise SystemExit("the API URL must be http(s)")
    host = parsed.hostname or ""
    if not allow_remote and host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit(
            "refusing a non-loopback API URL (use --allow-remote-api for a test stack you own)"
        )
    req = urllib.request.Request(
        f"{api_url.rstrip('/')}/api/sources/{urllib.parse.quote(source_id, safe=':')}"
    )
    token = os.environ.get(token_env or "", "")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - loopback test API
        return json.loads(resp.read().decode("utf-8")).get("full_text") or ""


def run(args: argparse.Namespace) -> dict[str, Any]:
    from content_core import ContentCoreConfig

    from open_notebook.ocr import catalog, docling_extract, legal_normalizer, paths
    from open_notebook.ocr.options import OcrSettings, describe, engine_langs

    pdf = Path(args.pdf).resolve()
    if not pdf.is_file():
        raise SystemExit(f"not a file: {pdf}")
    out = Path(args.out).resolve()
    _prepare_out(out, args.overwrite)
    ocr = OcrSettings(
        enabled=not args.no_ocr,
        engine=args.engine,
        force_full_page=args.full_page,
        custom_version=args.version,
    ).pinned()
    cfg = ContentCoreConfig(document_engine="docling", docling_ocr=not args.no_ocr)
    spec = catalog.get_engine(ocr.engine)
    env = {
        "schema": SCHEMA,
        "file_name": pdf.name,
        "file_bytes": pdf.stat().st_size,
        "engine": describe(ocr.engine, ocr.custom_version),
        "force_full_page": ocr.force_full_page,
        "versions": _versions(),
        "legal_normalizer_version": legal_normalizer.NORMALIZER_VERSION,
    }

    started = time.perf_counter()
    result, converter, prep = docling_extract.convert_document(str(pdf), cfg, ocr)
    env["docling_seconds"] = round(time.perf_counter() - started, 2)
    env.update(prep.as_meta())
    env.update(docling_extract.pipeline_identity(converter))
    env.update(docling_extract.conversion_outcome(result, str(pdf)))
    env["ocr_models"] = docling_extract.actual_ocr_models(converter)

    direct: list[str] = []
    if not args.no_direct:
        langs = (
            engine_langs(ocr.engine, ocr.custom_version)
            if spec.docling_kind == "tesseract"
            else (args.direct_lang.split("+") if args.direct_lang else [])
        )
        scale = env.get("ocr_scale") or (args.dpi / 72)
        dpi = (
            int(round(float(scale) * 72))
            if spec.docling_kind == "tesseract"
            else args.dpi
        )
        env["direct_ocr"] = {"langs": langs, "dpi": dpi, "psm": args.psm}
        direct = direct_tesseract(
            pdf,
            out,
            langs,
            str(paths.tessdata_dir()) if spec.docling_kind == "tesseract" else None,
            dpi,
            args.psm,
        )

    doc = result.document
    layers = docling_layers(result)
    _write(out / "02_ocr_cells.json", layers["cells"])
    _write(out / "03_layout_clusters.json", layers["clusters"])
    _write(out / "04_assembled_elements.json", layers["assembled"])
    _write(out / "05_docling_document.json", doc.export_to_dict())
    rows = item_rows(doc)
    _write(out / "06_items.json", rows)
    t0 = time.perf_counter()
    standard = doc.export_to_markdown()
    env["standard_export_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    norm = legal_normalizer.normalize_document(doc, include_text=True)
    report = norm.report()
    _write(out / "07_markdown_standard.md", standard)
    _write(out / "08_markdown_legal.md", norm.content)
    _write(out / "09_legal_report.json", report)
    _write(out / "10_display_standard.txt", "\n".join(M.display_lines(standard)))
    _write(out / "10_display_legal.txt", "\n".join(M.display_lines(norm.content)))
    source_text = None
    if args.source_id:
        source_text = fetch_source(
            args.api_url, args.source_id, args.token_env, args.allow_remote_api
        )
        _write(out / "11_source_full_text.md", source_text)
    gt = (
        Path(args.ground_truth).read_text(encoding="utf-8")
        if args.ground_truth
        else None
    )
    summary = summarize(
        direct, layers, rows, standard, norm.content, report, gt, source_text
    )
    summary["environment"] = {
        k: env[k] for k in ("docling_seconds", "standard_export_ms") if k in env
    }
    _write(out / "00_environment.json", env)
    _write(out / "12_summary.json", summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("pdf")
    p.add_argument(
        "--out", required=True, help="new or empty local directory for the results"
    )
    p.add_argument(
        "--engine",
        default="rapidocr",
        help="rapidocr | tesseract_fast | tesseract_best | easyocr | tesseract_agri",
    )
    p.add_argument(
        "--version",
        default=None,
        help="custom engine version (default: the active one)",
    )
    p.add_argument(
        "--full-page", action="store_true", help="Docling full-page OCR mode"
    )
    p.add_argument(
        "--no-ocr", action="store_true", help="Docling without OCR (text-layer PDFs)"
    )
    p.add_argument(
        "--no-direct", action="store_true", help="skip the direct Tesseract run"
    )
    p.add_argument(
        "--direct-lang",
        default="vie",
        help="Tesseract languages for the direct run of non-Tesseract engines",
    )
    p.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="direct OCR DPI when the engine sets no scale",
    )
    p.add_argument(
        "--psm",
        type=int,
        default=3,
        help="Tesseract page segmentation mode for the direct run",
    )
    p.add_argument(
        "--ground-truth", help="UTF-8 text file with the exact text of the document"
    )
    p.add_argument(
        "--source-id", help="Source id to fetch from a LOCAL test API (stored text)"
    )
    p.add_argument("--api-url", default="http://127.0.0.1:5057")
    p.add_argument(
        "--token-env",
        default="PHASE12_API_TOKEN",
        help="env var holding a bearer token (never printed)",
    )
    p.add_argument("--allow-remote-api", action="store_true")
    p.add_argument("--overwrite", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run(args)
    print(
        json.dumps(
            {k: summary[k] for k in ("words_per_layer", "standard", "legal")},
            ensure_ascii=False,
            indent=2,
        )
    )
    print(
        f"Diagnostic written to {Path(args.out).resolve()} (contains document text: keep it local)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
