"""Measure what Docling keeps of a scan that has visible text boxes over it (D-33).

For every PDF of ``generate_overlay_fixtures.py`` this runs the PRODUCTION
conversion (``docling_extract.convert_document``) in up to three ways:

    default     Force Full Page off, automatic rule off  (behaviour before D-33)
    auto        Force Full Page off, automatic rule on
    full_page   Force Full Page on (the manual setting)

and records, next to the page measurements of ``pdf_prep.overlay_scan``:
OCR cells produced / kept by Docling's merge, how much of the ground truth is
in the result (word recall, CER), and the time taken. The numbers are the
basis of the thresholds in ``pdf_prep`` and of docs/ocr/OCR_PHASE10G_REPORT.md.

    uv run python scripts/ocr/overlay_calibration.py run --dir FIXTURES --out result.json \
        [--engine tesseract_best] [--modes default auto full_page]
    uv run python scripts/ocr/overlay_calibration.py report result.json

Synthetic input only. The cell counters are attached in this process; nothing
in Docling or the application is modified.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from open_notebook.ocr import metrics, pdf_prep  # noqa: E402

MODES = ("default", "auto", "full_page")


def words(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text or "").lower()
    text = re.sub(r"<!--.*?-->", " ", text)
    return [w for w in re.split(r"[^0-9a-zà-ỹđ]+", text) if w]


def recall(reference: list[str], hypothesis: list[str]) -> float | None:
    if not reference:
        return None
    ref, hyp = collections.Counter(reference), collections.Counter(hypothesis)
    return round(sum(min(n, hyp[w]) for w, n in ref.items()) / sum(ref.values()), 4)


def scan_summary(path: Path) -> dict[str, Any]:
    scan = pdf_prep.overlay_scan(str(path))
    return {
        "decision": scan.decision,
        "pages": scan.pages,
        "scan_pages": scan.scan_pages,
        "risk_pages": len(scan.risk_pages),
        "text_pages": len(scan.text_pages),
        "max_conflict_share": max(
            (p.conflict_share for p in scan.details), default=0.0
        ),
        "max_box_share": max((p.max_box_share for p in scan.details), default=0.0),
        "max_inflation": max((p.max_inflation for p in scan.details), default=0.0),
        "angles": sorted({a for p in scan.details for a in p.angles}),
        "ordinary_chars_max": max(
            (p.ordinary_chars or 0 for p in scan.details), default=0
        ),
        "invisible_chars_max": max(
            (p.invisible_chars or 0 for p in scan.details), default=0
        ),
    }


def convert(path: Path, engine: str, mode: str) -> dict[str, Any]:
    """One production conversion; returns counts and the Markdown."""
    from content_core import ContentCoreConfig
    from docling.models import base_ocr_model as bom

    from open_notebook.ocr.docling_extract import convert_document
    from open_notebook.ocr.options import OcrSettings

    counts = {"produced": 0, "kept": 0}
    original = bom.BaseOcrModel.post_process_cells

    def counting(self, ocr_cells, page, conv_res, priority=None):
        produced = list(ocr_cells)
        original(self, ocr_cells, page, conv_res, priority)
        final = {id(c) for c in page.parsed_page.textline_cells}
        counts["produced"] += len(produced)
        counts["kept"] += sum(1 for c in produced if id(c) in final)

    os.environ[pdf_prep.AUTO_FULL_PAGE_ENV] = "true" if mode == "auto" else "false"
    bom.BaseOcrModel.post_process_cells = counting
    started = time.time()
    try:
        ocr = OcrSettings(
            enabled=True, engine=engine, force_full_page=mode == "full_page"
        ).pinned()
        result, converter, prep = convert_document(
            str(path),
            ContentCoreConfig(document_engine="docling", docling_ocr=True),
            ocr,
        )
    finally:
        bom.BaseOcrModel.post_process_cells = original
    markdown = result.document.export_to_markdown()
    effective = None
    for pipeline in getattr(converter, "initialized_pipelines", {}).values():
        effective = str(pipeline.pipeline_options.ocr_options.mode.value)
        break
    return {
        "seconds": round(time.time() - started, 2),
        "ocr_cells_produced": counts["produced"],
        "ocr_cells_kept": counts["kept"],
        "effective_mode": effective,
        "markdown": markdown,
        "status": str(getattr(result.status, "value", result.status)),
    }


def cmd_run(args: argparse.Namespace) -> int:
    manifest = json.loads((args.dir / "manifest.json").read_text(encoding="utf-8"))
    rows = []
    for entry in manifest["files"]:
        if args.only and not any(o in entry["file"] for o in args.only):
            continue
        path = args.dir / entry["file"]
        truths = [t for t in entry["ground_truth"] if t]
        truth = "\n".join(truths)
        row: dict[str, Any] = {
            "file": entry["file"],
            "group": entry["group"],
            "expect": entry["expect"],
            "why": entry["why"],
            "scan": scan_summary(path),
            "engine": args.engine,
            "runs": {},
        }
        for mode in args.modes:
            try:
                out = convert(path, args.engine, mode)
            except Exception as e:  # a failed conversion is a result, not a crash
                row["runs"][mode] = {"error": f"{type(e).__name__}: {e}"[:300]}
                continue
            md = out.pop("markdown")
            out.update(
                markdown_chars=len(md),
                markdown_words=len(words(md)),
                markdown_sha16=hashlib.sha256(md.encode()).hexdigest()[:16],
                image_placeholders=md.count("<!-- image -->"),
                kept_share=round(out["ocr_cells_kept"] / out["ocr_cells_produced"], 4)
                if out["ocr_cells_produced"]
                else None,
            )
            if truth:
                out["word_recall"] = recall(words(truth), words(md))
                if len(truths) == len(entry["ground_truth"]):
                    out["cer"] = round(metrics.cer(truth, md), 4)
            row["runs"][mode] = out
        rows.append(row)
        print(
            f"{entry['file']:40s} {row['scan']['decision']:9s} "
            + "  ".join(
                f"{m}: kept={r.get('kept_share')} recall={r.get('word_recall')} "
                f"{r.get('seconds')}s"
                for m, r in row["runs"].items()
            ),
            flush=True,
        )
    args.out.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


def _pct(v: Any) -> str:
    return "—" if v is None else f"{100 * v:.1f}%"


def cmd_report(args: argparse.Namespace) -> int:
    rows = json.loads(Path(args.file).read_text(encoding="utf-8"))
    modes = [m for m in MODES if any(m in r["runs"] for r in rows)]
    head = (
        "| PDF | Nhóm | Góc | Phủ trên ảnh | Hộp lớn nhất | Ký tự thường | Quyết định |"
    )
    for m in modes:
        head += f" {m}: ô OCR giữ | {m}: recall | {m}: CER | {m}: giây |"
    print(head)
    print("|" + "---|" * (head.count("|") - 1))
    for r in rows:
        s = r["scan"]
        line = (
            f"| {r['file'][:-4]} | {r['group']} | {','.join(map(str, s['angles'])) or '—'} | "
            f"{_pct(s['max_conflict_share'])} | {_pct(s['max_box_share'])} | "
            f"{s['ordinary_chars_max']} | {s['decision']} |"
        )
        for m in modes:
            run = r["runs"].get(m, {})
            kept = (
                f"{run.get('ocr_cells_kept')}/{run.get('ocr_cells_produced')}"
                if "ocr_cells_produced" in run
                else run.get("error", "—")[:30]
            )
            line += (
                f" {kept} | {_pct(run.get('word_recall'))} | {_pct(run.get('cer'))} | "
                f"{run.get('seconds', '—')} |"
            )
        print(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--dir", required=True, type=Path)
    r.add_argument("--out", required=True, type=Path)
    r.add_argument("--engine", default="tesseract_best")
    r.add_argument(
        "--modes", nargs="+", default=["default", "full_page"], choices=MODES
    )
    r.add_argument("--only", nargs="*")
    r.set_defaults(func=cmd_run)
    p = sub.add_parser("report")
    p.add_argument("file")
    p.set_defaults(func=cmd_report)
    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
