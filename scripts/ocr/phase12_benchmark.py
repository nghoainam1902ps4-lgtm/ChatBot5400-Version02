#!/usr/bin/env python3
"""Phase 12D quality benchmark on the SYNTHETIC legal fixtures (no real data).

Two independent measurements, reported separately on purpose:

STRUCTURE  Standard export vs Legal Document normalization of the same
           DoclingDocument. The document comes from Docling's real
           ReadingOrderModel fed with the fixture's layout (tests/legal_harness.py),
           so OCR and layout-model errors are excluded: this isolates what the
           serializer / normalizer does to correct text.
RECOGNITION Direct Tesseract on the rendered scan PDFs (generate_phase12_fixtures.py),
           i.e. how well the OCR engine reads the page - something normalization
           cannot and must not change.

The full pipeline (Layout Heron + TableFormer + the engines, incl. Agri) is NOT
measured here: run scripts/ocr/phase12_compare.py on Windows Local for that.

  uv run python scripts/ocr/phase12_benchmark.py --out docs/ocr/phase12_benchmark.json
  uv run python scripts/ocr/phase12_benchmark.py --pdf-dir ./phase12-fixtures --tesseract-lang vie ...
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import legal_harness as H  # noqa: E402
import phase12_metrics as M  # noqa: E402


def structure(fx: dict[str, Any], repeats: int) -> dict[str, Any]:
    from open_notebook.ocr import legal_normalizer as N

    doc = H.build_document(fx)
    t_std, t_leg = [], []
    for _ in range(repeats):
        t0 = time.perf_counter()
        standard = doc.export_to_markdown()
        t_std.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        res = N.normalize_document(doc)
        t_leg.append((time.perf_counter() - t0) * 1000)
    tracemalloc.start()
    N.normalize_document(doc)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    detail = N.normalize_document(doc, include_text=True)
    removed = " ".join(
        o.text_before or "" for o in detail.operations if o.op.endswith("_to_furniture")
    )

    gt = fx["ground_truth"]
    out: dict[str, Any] = {"name": fx["name"], "pages": len(fx["pages"])}
    for mode, md in (("standard", standard), ("legal", res.content)):
        lines = M.display_lines(md)
        text = " ".join(lines)
        hit, total = M.markers_displayed(fx, lines)
        protected = fx.get("protected", [])
        renum, ordered = M.renumbered_list_items(md)
        out[mode] = {
            "cer": round(M.cer(gt, text), 4),
            "wer": round(M.wer(gt, text), 4),
            "recall": round(M.word_recall(gt, text), 4),
            "protected_exact": [
                sum(1 for p in protected if p in md or p in text),
                len(protected),
            ],
            "markers": [hit, total],
            "order": M.order_accuracy(fx, text),
            "placeholders": M.placeholder_count(md),
            "numeric_only_lines": M.numeric_only_lines(lines),
            "renumbered_items": [renum, ordered],
            "must_join": [
                sum(1 for p in fx.get("must_join", []) if any(p in ln for ln in lines)),
                len(fx.get("must_join", [])),
            ],
            "false_merges": sum(
                1
                for a, b in fx.get("must_not_join", [])
                if any(a in ln and b in ln for ln in lines)
            ),
            "absent_ok": [
                sum(1 for a in fx.get("absent_lines", []) if a not in lines),
                len(fx.get("absent_lines", [])),
            ],
            "ms_median": round(
                statistics.median(t_std if mode == "standard" else t_leg), 3
            ),
        }
    out["legal"]["false_deleted_words"] = max(
        0,
        M.lost_words(
            M.display_text(standard, list_prefixes=False),
            M.display_text(res.content) + " " + removed,
        )
        - 3 * res.counts.get("image_placeholder_dropped", 0),
    )
    out["legal"]["peak_kib"] = round(peak / 1024, 1)
    out["legal"]["joins"] = res.counts.get("join_across_pages", 0)
    out["legal"]["counts"] = res.counts
    out["legal"]["warnings"] = [w["code"] for w in res.warnings]
    if fx.get("table_identical"):
        out["legal"]["tables_identical"] = all(
            t.export_to_markdown(doc) in res.content for t in doc.tables
        )
    return out


def recognition(
    fx: dict[str, Any], pdf_dir: Path, lang: str, dpi: int
) -> dict[str, Any] | None:
    import pypdfium2 as pdfium

    tess = shutil.which("tesseract")
    pdf = pdf_dir / f"{fx['name']}.scan.pdf"
    if not tess or not pdf.is_file():
        return None
    texts = []
    doc = pdfium.PdfDocument(str(pdf))
    t0 = time.perf_counter()
    try:
        for i in range(len(doc)):
            png = pdf_dir / f".bench_{fx['name']}_{i}.png"
            doc[i].render(scale=dpi / 72).to_pil().convert("L").save(png)
            r = subprocess.run(
                [tess, str(png), "stdout", "-l", lang, "--psm", "3"],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )  # noqa: S603
            png.unlink(missing_ok=True)
            texts.append(r.stdout)
    finally:
        doc.close()
    text = " ".join(texts)
    gt = fx["ground_truth"]
    protected = fx.get("protected", [])
    return {
        "cer": round(M.cer(gt, text), 4),
        "wer": round(M.wer(gt, text), 4),
        "recall": round(M.word_recall(gt, text), 4),
        "protected_exact": [
            sum(
                1
                for p in protected
                if p.replace("&lt;", "<").replace("&gt;", ">") in text
            ),
            len(protected),
        ],
        "seconds": round(time.perf_counter() - t0, 2),
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    agg: dict[str, Any] = {}
    for mode in ("standard", "legal"):
        r = [x[mode] for x in rows]
        agg[mode] = {
            "cer_mean": round(statistics.mean(x["cer"] for x in r), 4),
            "wer_mean": round(statistics.mean(x["wer"] for x in r), 4),
            "recall_mean": round(statistics.mean(x["recall"] for x in r), 4),
            "protected_exact": [
                sum(x["protected_exact"][0] for x in r),
                sum(x["protected_exact"][1] for x in r),
            ],
            "markers": [
                sum(x["markers"][0] for x in r),
                sum(x["markers"][1] for x in r),
            ],
            "order_mean": round(
                statistics.mean(x["order"] for x in r if x["order"] is not None), 4
            ),
            "placeholders": sum(x["placeholders"] for x in r),
            "numeric_only_lines": sum(x["numeric_only_lines"] for x in r),
            "renumbered_items": [
                sum(x["renumbered_items"][0] for x in r),
                sum(x["renumbered_items"][1] for x in r),
            ],
            "must_join": [
                sum(x["must_join"][0] for x in r),
                sum(x["must_join"][1] for x in r),
            ],
            "false_merges": sum(x["false_merges"] for x in r),
            "absent_ok": [
                sum(x["absent_ok"][0] for x in r),
                sum(x["absent_ok"][1] for x in r),
            ],
            "ms_total": round(sum(x["ms_median"] for x in r), 2),
        }
    legal = [x["legal"] for x in rows]
    joins = sum(x["joins"] for x in legal)
    agg["legal"]["joins"] = joins
    agg["legal"]["join_precision"] = (
        round((joins - agg["legal"]["false_merges"]) / joins, 4) if joins else None
    )
    agg["legal"]["false_deleted_words"] = sum(x["false_deleted_words"] for x in legal)
    agg["legal"]["peak_kib_max"] = max(x["peak_kib"] for x in legal)
    agg["legal"]["tables_identical"] = all(
        x.get("tables_identical", True) for x in legal
    )
    rec = [x["recognition"] for x in rows if x.get("recognition")]
    if rec:
        agg["direct_tesseract"] = {
            "documents": len(rec),
            "cer_mean": round(statistics.mean(x["cer"] for x in rec), 4),
            "wer_mean": round(statistics.mean(x["wer"] for x in rec), 4),
            "recall_mean": round(statistics.mean(x["recall"] for x in rec), 4),
            "protected_exact": [
                sum(x["protected_exact"][0] for x in rec),
                sum(x["protected_exact"][1] for x in rec),
            ],
        }
    return agg


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--out", required=True, help="JSON result file")
    p.add_argument(
        "--pdf-dir", help="folder written by generate_phase12_fixtures.py (direct OCR)"
    )
    p.add_argument("--tesseract-lang", default="vie")
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--repeats", type=int, default=5)
    args = p.parse_args(argv)
    fixtures = H.load_fixtures().FIXTURES
    rows = []
    for fx in fixtures:
        row = structure(fx, args.repeats)
        if args.pdf_dir:
            row["recognition"] = recognition(
                fx, Path(args.pdf_dir), args.tesseract_lang, args.dpi
            )
        rows.append(row)
    from importlib.metadata import version

    result = {
        "schema": "chatbot5400-phase12-benchmark/1",
        "fixtures": len(rows),
        "versions": {k: version(k) for k in ("docling", "docling-core")},
        "tesseract": (
            subprocess.run(
                ["tesseract", "--version"], capture_output=True, text=True, check=False
            ).stdout.splitlines()
            or [None]
        )[0]
        if shutil.which("tesseract")
        else None,  # noqa: S607
        "aggregate": aggregate(rows),
        "rows": rows,
    }
    Path(args.out).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result["aggregate"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
