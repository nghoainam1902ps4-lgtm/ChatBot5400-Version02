"""LOCAL benchmark on the operator's own documents — numbers only (Phase 9A).

Runs the production OCR pipeline on a folder of PDFs chosen by the operator and
writes AGGREGATE METRICS ONLY. It is meant for real business documents, so by
design it never stores or prints:

* recognised text, ground-truth text or key-field values;
* file names or paths (documents become ``doc-001``, ``doc-002``… in sorted
  order; pass ``--keep-names`` only for non-sensitive material).

Run it on the server, in a plain shell — not inside an AI coding session, and do
not paste documents or their text anywhere. The JSON / Markdown it writes are
safe to share: they contain counts, rates and timings.

Layout of ``--dir`` (everything optional except the PDFs)::

    <dir>/<category>/<name>.pdf          category = sub-folder name, e.g. cong_van,
                                         quyet_dinh, quy_dinh, bang_scan, chat_luong_thap
    <dir>/<category>/<name>.gt.txt       the correct text, typed by a person
                                         -> CER, WER, word recall, diacritic accuracy
    <dir>/<category>/<name>.fields.txt   one value per line that MUST be read exactly
                                         (amounts, dates, document numbers)
                                         -> how many were found (the values are not stored)
    <dir>/<category>/<name>.headings.txt one bold heading per line
                                         -> found exactly / found without diacritics / lost

    uv run python scripts/ocr/local_document_benchmark.py --dir /path/to/docs \\
        --engines tesseract_best rapidocr --out bench.json --markdown bench.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

DEFAULT_ENGINES = ("tesseract_best",)


def _fold(text: str) -> str:
    out = unicodedata.normalize("NFD", text.lower())
    out = "".join(c for c in out if not unicodedata.combining(c))
    return unicodedata.normalize("NFC", out.replace("đ", "d"))


def _lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [
        ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]


def measure(
    markdown: str,
    ground_truth: str | None,
    fields: list[str],
    headings: list[str],
) -> dict[str, Any]:
    """Metrics for one document. Returns numbers only — never any text."""
    from open_notebook.ocr import metrics

    norm_md = metrics.normalize(markdown)
    out: dict[str, Any] = {"chars": len(norm_md), "words": len(norm_md.split())}
    if ground_truth is not None and ground_truth.strip():
        out.update(
            cer=round(metrics.cer(ground_truth, markdown), 4),
            wer=round(metrics.wer(ground_truth, markdown), 4),
            word_recall=round(metrics.word_recall(ground_truth, markdown), 4),
            diacritics=metrics.diacritic_accuracy(ground_truth, markdown),
        )
    if fields:
        found = sum(
            1 for f in fields if (metrics.field_recall([f], markdown) or 0) >= 1.0
        )
        out.update(fields_total=len(fields), fields_found=found)
    if headings:
        low_md, folded_md = norm_md.lower(), _fold(norm_md)
        exact = sum(1 for h in headings if metrics.normalize(h).lower() in low_md)
        folded = sum(1 for h in headings if _fold(metrics.normalize(h)) in folded_md)
        out.update(
            headings_total=len(headings),
            headings_exact=exact,
            headings_without_diacritics_only=folded - exact,
            headings_lost=len(headings) - folded,
        )
    return out


def aggregate(docs: list[dict[str, Any]]) -> dict[str, Any]:
    def mean(key: str) -> float | None:
        vals = [d[key] for d in docs if d.get(key) is not None]
        return round(statistics.mean(vals), 4) if vals else None

    def total(key: str) -> int:
        return sum(int(d.get(key) or 0) for d in docs)

    pages = total("pages")
    seconds = sum(float(d.get("seconds") or 0) for d in docs)
    return {
        "documents": len(docs),
        "failed": sum(1 for d in docs if d.get("error")),
        "pages": pages,
        "seconds_per_page": round(seconds / pages, 2) if pages else None,
        "with_ground_truth": sum(1 for d in docs if d.get("cer") is not None),
        "cer": mean("cer"),
        "wer": mean("wer"),
        "word_recall": mean("word_recall"),
        "diacritics": mean("diacritics"),
        "fields_found": total("fields_found"),
        "fields_total": total("fields_total"),
        "headings_exact": total("headings_exact"),
        "headings_without_diacritics_only": total("headings_without_diacritics_only"),
        "headings_lost": total("headings_lost"),
        "headings_total": total("headings_total"),
        "tables": total("tables"),
        "pages_orientation_corrected": total("pages_orientation_corrected"),
    }


def to_markdown(report: dict[str, Any]) -> str:
    def f(v: Any) -> str:
        return "–" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))

    lines = [
        "| Engine | Nhóm | Tài liệu | Lỗi | Trang | Giây/trang | CER | WER | Word recall | Dấu | Trường khóa | Tiêu đề đúng / mất dấu / mất | Bảng | Trang đã xoay |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for engine, data in report["engines"].items():
        for name, a in [("TẤT CẢ", data["all"])] + sorted(data["by_category"].items()):
            lines.append(
                f"| {engine} | {name} | {a['documents']} | {a['failed']} | {a['pages']} | "
                f"{f(a['seconds_per_page'])} | {f(a['cer'])} | {f(a['wer'])} | {f(a['word_recall'])} | "
                f"{f(a['diacritics'])} | {a['fields_found']}/{a['fields_total']} | "
                f"{a['headings_exact']} / {a['headings_without_diacritics_only']} / {a['headings_lost']} | "
                f"{a['tables']} | {a['pages_orientation_corrected']} |"
            )
    return "\n".join(lines) + "\n"


def silence_logs() -> None:
    """Keep application and library logs off the terminal.

    They name the file being converted ("... corrected page(s) [1] of <file>")
    and an error line could quote it. With real documents the only output is
    this tool's own lines: ``doc-NNN`` ids and numbers.
    """
    import logging
    import warnings

    from loguru import logger

    logger.remove()
    logging.disable(logging.CRITICAL)
    warnings.simplefilter("ignore")


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", required=True, type=Path)
    ap.add_argument("--engines", nargs="*", default=list(DEFAULT_ENGINES))
    ap.add_argument("--out", type=Path)
    ap.add_argument("--markdown", type=Path)
    ap.add_argument(
        "--keep-names",
        action="store_true",
        help="store file names in the report (only for non-sensitive material)",
    )
    args = ap.parse_args()
    sys.path.insert(0, str(root))

    from content_core import ContentCoreConfig

    from open_notebook.ocr.docling_extract import convert_document
    from open_notebook.ocr.options import OcrSettings

    if not args.keep_names:
        silence_logs()  # after the imports: libraries install log sinks on import
    pdfs = sorted(p for p in args.dir.rglob("*.pdf") if p.is_file())
    if not pdfs:
        print("no PDF found", file=sys.stderr)
        return 2
    cc = ContentCoreConfig(document_engine="docling", docling_ocr=True)
    report: dict[str, Any] = {
        "note": "Aggregate metrics only: no recognised text, no ground truth, no field values.",
        "documents": len(pdfs),
        "engines": {},
    }
    for engine in args.engines:
        docs: list[dict[str, Any]] = []
        for index, pdf in enumerate(pdfs, start=1):
            rel = pdf.relative_to(args.dir)
            category = rel.parts[0] if len(rel.parts) > 1 else "(không phân nhóm)"
            row: dict[str, Any] = {
                "id": str(rel) if args.keep_names else f"doc-{index:03d}",
                "category": category,
            }
            gt_path = pdf.with_suffix(".gt.txt")
            started = time.time()
            try:
                # inside the try: an unreadable file would otherwise end the run
                # with a traceback that names the document
                gt = gt_path.read_text(encoding="utf-8") if gt_path.is_file() else None
                result, _conv, prep = convert_document(
                    str(pdf), cc, OcrSettings(engine=engine)
                )
                doc = result.document
                row.update(
                    measure(
                        doc.export_to_markdown(),
                        gt,
                        _lines(pdf.with_suffix(".fields.txt")),
                        _lines(pdf.with_suffix(".headings.txt")),
                    )
                )
                row.update(
                    pages=len(result.pages),
                    tables=len(doc.tables),
                    pages_orientation_corrected=len(prep.rotated_pages),
                    page_orientation=prep.orientation,
                    scan_dpi=prep.scan_dpi,
                )
            except Exception as e:  # the type only: a message could quote the document
                row["error"] = type(e).__name__
            row["seconds"] = round(time.time() - started, 1)
            docs.append(row)
            print(
                f"{engine:15s} {row['id']:10s} {category:20s} "
                f"pages={row.get('pages', '-')} cer={row.get('cer', '-')} "
                f"fields={row.get('fields_found', '-')}/{row.get('fields_total', '-')} "
                f"{row['seconds']}s {row.get('error', '')}",
                flush=True,
            )
        categories = sorted({d["category"] for d in docs})
        report["engines"][engine] = {
            "all": aggregate(docs),
            "by_category": {
                c: aggregate([d for d in docs if d["category"] == c])
                for c in categories
            },
            "documents": docs,
        }
    if args.out:
        args.out.write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    md = to_markdown(report)
    if args.markdown:
        args.markdown.write_text(md, encoding="utf-8")
    print("\n" + md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
