#!/usr/bin/env python3
"""Phase 12E: compare Direct OCR / Standard / Legal Document in ONE command.

LOCAL USE ONLY (Windows Local test stack, inside the container). For every PDF
given (a file or a folder of PDFs), one Docling conversion is run with the
selected engine; the Standard export and the Legal Document normalization are
produced from the SAME DoclingDocument, and Tesseract is run directly on the
same pages for reference. Each document gets a full diagnostic folder
(``phase12_diagnose.py``), and the run writes:

  compare.md     a table per document: words, placeholders, page-number lines,
                 renumbered list items, joins, removed artifacts, warnings,
                 CER / WER when a ground truth file ``<name>.gt.txt`` exists
  compare.json   the same numbers (no document text)

Nothing is uploaded. The folder holds document text: keep it on this machine.

Example::

  python scripts/ocr/phase12_compare.py /import/legal-pdfs --engine tesseract_agri \
      --out /app/data/phase12-diagnostics/run-01
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import phase12_diagnose as D  # noqa: E402


def _pdfs(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(
        p for p in target.iterdir() if p.suffix.lower() == ".pdf" and p.is_file()
    )


def _row(name: str, s: dict[str, Any]) -> dict[str, Any]:
    gt = s.get("ground_truth") or {}
    counts = s["legal"].get("counts") or {}
    return {
        "document": name,
        "words_direct": s["words_per_layer"].get("direct_tesseract"),
        "words_standard": s["words_per_layer"]["markdown_standard_display"],
        "words_legal": s["words_per_layer"]["markdown_legal_display"],
        "placeholders_standard": s["standard"]["placeholders"],
        "placeholders_legal": s["legal"]["placeholders"],
        "numeric_lines_standard": s["standard"]["numeric_only_lines"],
        "numeric_lines_legal": s["legal"]["numeric_only_lines"],
        "renumbered_standard": s["standard"]["ordered_items_renumbered_by_renderer"],
        "renumbered_legal": s["legal"]["ordered_items_renumbered_by_renderer"],
        "joins": counts.get("join_across_pages", 0),
        "page_numbers_removed": counts.get("page_number_to_furniture", 0),
        "headers_footers_removed": counts.get("running_header_footer_to_furniture", 0),
        "picture_text_recovered": s.get(
            "text_items_under_pictures_dropped_by_standard_export", 0
        ),
        "warnings": ",".join(s["legal"].get("warnings") or []) or "-",
        "legal_ms": s["legal"].get("ms"),
        "docling_s": (s.get("environment") or {}).get("docling_seconds"),
        "cer_direct": (gt.get("direct_tesseract") or {}).get("cer"),
        "cer_standard": (gt.get("standard") or {}).get("cer"),
        "cer_legal": (gt.get("legal") or {}).get("cer"),
        "wer_standard": (gt.get("standard") or {}).get("wer"),
        "wer_legal": (gt.get("legal") or {}).get("wer"),
        "page_end_words_lost_standard": sum(
            1
            for p in s.get("page_end_words_in_standard", [])
            if not p["last_words_found"]
        ),
        "page_end_words_lost_legal": sum(
            1 for p in s.get("page_end_words_in_legal", []) if not p["last_words_found"]
        ),
    }


def _markdown(rows: list[dict[str, Any]], engine: str) -> str:
    lines = [
        f"# Phase 12 — so sánh Direct OCR / Standard / Legal (engine `{engine}`)",
        "",
    ]
    if not rows:
        return "\n".join(lines + ["(không có tài liệu)"])
    keys = list(rows[0])
    lines.append("| " + " | ".join(keys) + " |")
    lines.append("|" + "---|" * len(keys))
    for r in rows:
        lines.append(
            "| " + " | ".join("" if r[k] is None else str(r[k]) for k in keys) + " |"
        )
    lines += [
        "",
        "Đọc bảng: `renumbered_*` = số mục danh sách mà trình duyệt vẽ khác số gốc; `numeric_lines_*` = dòng chỉ có",
        "chữ số (thường là số trang lọt vào nội dung); `page_end_words_lost_*` = số trang mà các từ cuối trang của",
        "OCR trực tiếp không còn trong kết quả. Chi tiết từng tầng: thư mục con của từng tài liệu.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = D.build_parser()
    p.description = __doc__
    p.formatter_class = argparse.RawDescriptionHelpFormatter
    args = p.parse_args(argv)
    target = Path(args.pdf).resolve()
    out = Path(args.out).resolve()
    D._prepare_out(out, args.overwrite)
    rows = []
    for pdf in _pdfs(target):
        sub = argparse.Namespace(**vars(args))
        sub.pdf = str(pdf)
        sub.out = str(out / pdf.stem)
        gt = pdf.with_suffix(".gt.txt")
        if not args.ground_truth and gt.is_file():
            sub.ground_truth = str(gt)
        print(f"[phase12] {pdf.name} …", flush=True)
        try:
            rows.append(_row(pdf.name, D.run(sub)))
        except Exception as e:  # noqa: BLE001 - one bad file must not stop the batch
            rows.append({"document": pdf.name, "error": type(e).__name__})
            print(f"[phase12] {pdf.name}: {type(e).__name__}: {e}", file=sys.stderr)
    good = [r for r in rows if "error" not in r]
    (out / "compare.json").write_text(
        json.dumps({"engine": args.engine, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out / "compare.md").write_text(_markdown(good, args.engine), encoding="utf-8")
    for f in ("compare.json", "compare.md"):
        os.chmod(out / f, 0o600)
    print(_markdown(good, args.engine))
    print(f"Kết quả: {out} (chứa nội dung tài liệu — chỉ lưu trên máy này).")
    return 0 if len(good) == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
