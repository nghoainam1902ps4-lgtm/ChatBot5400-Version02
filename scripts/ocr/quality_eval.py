"""OCR quality evaluation through the PRODUCTION conversion path (Phase 8C).

Measures a directory of PDFs that has a ``manifest.json`` in the shape of
tests/fixtures/ocr/manifest.json (the acceptance fixtures, or the holdout set
written by generate_holdout_fixtures.py):

    uv run python scripts/ocr/quality_eval.py --engine tesseract_best \
        --dir tests/fixtures/ocr --out result.json

``--src`` evaluates another checkout (e.g. a git worktree of an older commit)
with the same Python environment, for before/after comparisons. ``--set
key=json`` overrides attributes of the Docling OCR options; it exists for
experiments only and is never used by the application.

The output holds metrics only plus the recognised markdown of these synthetic
documents — do not run it on real documents and keep its output out of git.
"""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True)
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--src", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=JSON")
    args = ap.parse_args()
    sys.path.insert(0, str(args.src))

    from content_core import ContentCoreConfig

    import open_notebook.ocr.docling_extract as extract
    from open_notebook.ocr import metrics
    from open_notebook.ocr import options as ocr_options

    overrides = {}
    for item in args.set:
        key, value = item.split("=", 1)
        try:
            overrides[key] = json.loads(value)
        except ValueError:
            overrides[key] = value
    if overrides:
        original = extract.build_ocr_options

        def patched(*a, **k):
            opts = original(*a, **k)
            for key, value in overrides.items():
                setattr(opts, key, value)
            return opts

        extract.build_ocr_options = patched  # experiment only

    cc = ContentCoreConfig(document_engine="docling", docling_ocr=True)
    settings = ocr_options.OcrSettings(engine=args.engine)
    manifest = json.loads((args.dir / "manifest.json").read_text())
    results: dict[str, dict] = {}
    for name in args.only or sorted(manifest):
        spec = manifest[name]
        path = str(args.dir / spec["file"])
        started = time.time()
        prep_meta: dict = {}
        if hasattr(extract, "convert_document"):
            result, _conv, prep = extract.convert_document(path, cc, settings)
            prep_meta = prep.as_meta()
        else:  # checkouts before Phase 8C
            result = extract.build_converter(cc, settings).convert(path)
        seconds = round(time.time() - started, 1)
        doc = result.document
        md = doc.export_to_markdown()
        gt, kf = spec["ground_truth"], spec["key_fields"]
        tables = []
        for tb in doc.tables:
            rows: dict[int, list[tuple[int, str]]] = {}
            for c in tb.data.table_cells:
                rows.setdefault(c.start_row_offset_idx, []).append(
                    (c.start_col_offset_idx, c.text)
                )
            tables.append(
                {
                    "rows": tb.data.num_rows,
                    "cols": tb.data.num_cols,
                    "row_text": [
                        " | ".join(t for _c, t in sorted(v))
                        for _r, v in sorted(rows.items())
                    ],
                }
            )
        rows_ok = rows_total = None
        if spec["tables"]:
            checks = spec["tables"][0]["row_checks"]
            rows_total = len(checks)
            rows_ok = sum(
                1
                for ch in checks
                if any(
                    all(cell in row for cell in ch["cells"])
                    and metrics.normalize(ch["label"]).lower()
                    in metrics.normalize(row).lower()
                    for tb in tables
                    for row in tb["row_text"]
                )
            )
        all_fields = [
            f for k in ("amounts", "dates", "doc_numbers") for f in kf.get(k, [])
        ]
        rec = {
            "cer": round(metrics.cer(gt, md), 4),
            "wer": round(metrics.wer(gt, md), 4),
            "word_recall": round(metrics.word_recall(gt, md), 4),
            "diacritics": metrics.diacritic_accuracy(gt, md),
            "amounts": metrics.field_recall(kf.get("amounts", []), md),
            "dates": metrics.field_recall(kf.get("dates", []), md),
            "doc_numbers": metrics.field_recall(kf.get("doc_numbers", []), md),
            "fields": metrics.field_recall(all_fields, md) if all_fields else None,
            "tables": [(t["rows"], t["cols"]) for t in tables],
            "rows_ok": rows_ok,
            "rows_total": rows_total,
            "seconds": seconds,
            "prep": prep_meta,
            "markdown": md,
            "table_rows": [t["row_text"] for t in tables],
        }
        results[name] = rec

        def f(v):
            return "-" if v is None else f"{v:.2f}"

        print(
            f"{name:24s} cer={rec['cer']:.3f} wer={rec['wer']:.3f} "
            f"wrec={rec['word_recall']:.2f} dia={f(rec['diacritics'])} "
            f"amt={f(rec['amounts'])} date={f(rec['dates'])} doc={f(rec['doc_numbers'])} "
            f"tabs={rec['tables']} rows={rows_ok}/{rows_total} {seconds}s "
            f"rot={prep_meta.get('rotated_pages') or ''}",
            flush=True,
        )
    peak_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
    print(f"peak RSS {peak_mb} MB")
    if args.out:
        args.out.write_text(
            json.dumps(
                {
                    "engine": args.engine,
                    "overrides": overrides,
                    "peak_rss_mb": peak_mb,
                    "results": results,
                },
                ensure_ascii=False,
                indent=1,
            )
        )


if __name__ == "__main__":
    main()
