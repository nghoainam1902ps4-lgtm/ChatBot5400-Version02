"""Supplementary RELEASE criteria for the OCR engines (Phase 8D, DECISIONS D-27).

This does NOT replace tests/test_ocr_integration.py and never changes its
verdict. For every engine x acceptance fixture it re-evaluates EVERY assertion
of the original full-pipeline test (the original stops at the first failure,
so it cannot tell whether a second defect hides behind the first), then sorts
the checks into three classes:

* critical  - amounts, dates, document numbers, table shape and the numeric
              cells of every table row. Nothing here is ever waived.
* general   - character accuracy, Vietnamese diacritics, headings / reading
              order, row labels.
* known limitation - a general check that failed ONLY because of a limitation
              the project owner accepted (ACCEPTED_LIMITATIONS below).

Verdicts per engine x fixture:

* original     PASS / FAIL  - exactly what the original test decides.
* conditional  PASS                      - original PASS
               PASS_WITH_KNOWN_LIMITATION - every critical check passes and
                   every failed check is fully explained by an accepted limitation
               FAIL                      - anything else.

An accepted limitation is a statement about ONE phrase and ONE defect (missing
diacritics): the phrase must still be there, in the right place, when both
sides are compared without diacritics. It never edits the OCR output and it is
not a dictionary of corrections; any other difference keeps the check failed.

    uv run python scripts/ocr/release_criteria.py --out release.json --markdown release.md
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

ENGINES = ("rapidocr", "tesseract_fast", "tesseract_best", "easyocr")

# Same values as tests/test_ocr_integration.py (a unit test keeps them equal).
VIETNAMESE_ENGINES = ("tesseract_fast", "tesseract_best", "easyocr")
MAX_CER = {"tesseract_best": 0.08, "tesseract_fast": 0.10, "easyocr": 0.15}
MIN_FIELD_RECALL = {
    "tesseract_best": 1.0,
    "tesseract_fast": 0.9,
    "easyocr": 0.9,
    "rapidocr": 0.8,
}
NUMERIC_KEYS = ("amounts", "dates")
ROTATED_MIN_WORD_RECALL = 0.85

# Limitations accepted by the project owner (RELEASE_CANDIDATE.md section 8).
ACCEPTED_LIMITATIONS = (
    {
        "id": "KL-1",
        "engines": ("tesseract_best", "tesseract_fast"),
        "phrase": "BẢNG KÊ CHI TIẾT KHOẢN MỤC MẪU",
        "defect": "missing_diacritics",
        "description": (
            "Tesseract drops diacritics in this bold upper-case table heading "
            "(read as 'BANG KE ...'); verified on the source image with "
            "Tesseract alone (OCR_FAILURE_ANALYSIS.md 5.3)."
        ),
    },
)

CRITICAL, GENERAL = "critical", "general"


def norm(text: str) -> str:
    from open_notebook.ocr import metrics

    return metrics.normalize(text).lower()


def fold(text: str) -> str:
    """Lower-case, diacritics removed (đ -> d). Used ONLY to recognise KL-1."""
    out = unicodedata.normalize("NFD", norm(text))
    out = "".join(c for c in out if not unicodedata.combining(c))
    return unicodedata.normalize("NFC", out.replace("đ", "d"))


def limitation_for(engine: str, phrase: str) -> dict[str, Any] | None:
    for lim in ACCEPTED_LIMITATIONS:
        if engine in lim["engines"] and norm(str(lim["phrase"])) == norm(phrase):
            return dict(lim)
    return None


def _check(name: str, cls: str, ok: bool, detail: str = "", **extra: Any) -> dict:
    return {"name": name, "class": cls, "ok": bool(ok), "detail": detail, **extra}


def evaluate(
    engine: str,
    spec: dict[str, Any],
    markdown: str,
    tables: list[dict[str, Any]],
    pages: int,
    ocr_class_ok: bool = True,
) -> dict[str, Any]:
    """All checks for one engine x fixture. ``tables``: rows, cols, cells
    [(row, col, row_span, col_span, text)] as in the original test."""
    from open_notebook.ocr import metrics

    nmd = norm(markdown)
    needs_ocr = not all(spec["text_layer"])
    vietnamese_ok = engine in VIETNAMESE_ENGINES or not needs_ocr
    kf = spec["key_fields"]
    original: list[dict] = []  # the original test's assertions, all of them
    critical: list[dict] = []  # release-critical view (stricter where it matters)

    # 1. engine and page count
    original.append(_check("selected_engine_ran", CRITICAL, ocr_class_ok))
    original.append(
        _check(
            "page_count", CRITICAL, pages == spec["pages"], f"{pages}/{spec['pages']}"
        )
    )

    # 2. key fields (original: one pooled recall against the engine threshold)
    keys = list(NUMERIC_KEYS) + (["doc_numbers"] if vietnamese_ok else [])
    fields = [f for k in keys for f in kf.get(k, [])]
    if not vietnamese_ok:
        fields = [f for f in fields if f.isascii()]
    recall = metrics.field_recall(fields, markdown) if fields else None
    if recall is not None:
        need = 1.0 if not needs_ocr else MIN_FIELD_RECALL[engine]
        original.append(
            _check(
                "key_field_recall", CRITICAL, recall >= need, f"{recall:.2f} >= {need}"
            )
        )
    # Release view: every amount, date and document number, no pooling, no
    # engine-specific allowance (document numbers only where the engine is
    # expected to read Vietnamese).
    for key in keys:
        values = [f for f in kf.get(key, []) if vietnamese_ok or f.isascii()]
        if not values:
            continue
        missing = [
            v for v in values if (metrics.field_recall([v], markdown) or 0) < 1.0
        ]
        critical.append(
            _check(
                f"all_{key}",
                CRITICAL,
                not missing,
                f"{len(values) - len(missing)}/{len(values)}",
                missing=missing,
            )
        )

    # 3. headings / reading order
    known: list[dict] = []
    if vietnamese_ok and not spec["rotated"]:
        positions, missing_phrases, unexplained = [], [], []
        for phrase in spec["ordered_phrases"]:
            pos = nmd.find(norm(phrase))
            if pos < 0:
                missing_phrases.append(phrase)
                lim = limitation_for(engine, phrase)
                folded_pos = fold(markdown).find(fold(phrase))
                if lim and folded_pos >= 0:
                    known.append({**lim, "fixture_phrase": phrase})
                    # same text position scale is not guaranteed after folding;
                    # order is re-checked on the folded text below
                else:
                    unexplained.append(phrase)
            positions.append(pos)
        present = all(p >= 0 for p in positions)
        in_order = present and positions == sorted(positions)
        original.append(
            _check(
                "ordered_phrases",
                GENERAL,
                in_order,
                "missing: " + "; ".join(missing_phrases) if missing_phrases else "",
                missing=missing_phrases,
                unexplained=unexplained,
            )
        )
        # Diacritic-insensitive presence and order: is the CONTENT there and in
        # the right place? (This is what tells KL-1 from a real loss.)
        folded_md = fold(markdown)
        fpos = [folded_md.find(fold(p)) for p in spec["ordered_phrases"]]
        critical.append(
            _check(
                "headings_present_in_order_ignoring_diacritics",
                CRITICAL,
                all(p >= 0 for p in fpos) and fpos == sorted(fpos),
                str(fpos),
            )
        )
    if spec["rotated"] and engine.startswith("tesseract"):
        wr = metrics.word_recall(spec["ground_truth"], markdown)
        original.append(
            _check(
                "rotated_word_recall",
                GENERAL,
                wr >= ROTATED_MIN_WORD_RECALL,
                f"{wr:.2f} >= {ROTATED_MIN_WORD_RECALL}",
            )
        )

    # 4. character accuracy
    if needs_ocr and engine in MAX_CER and not spec["rotated"] and not spec["tables"]:
        cer = metrics.cer(spec["ground_truth"], markdown)
        original.append(
            _check(
                "cer",
                GENERAL,
                cer <= MAX_CER[engine],
                f"{cer:.3f} <= {MAX_CER[engine]}",
            )
        )

    # 5. tables
    for expect in spec["tables"]:
        cands = [t for t in tables if t["cols"] == expect["cols"]]
        shape_ok = bool(cands) and (
            expect["rows_min"] <= cands[0]["rows"] <= expect["rows_max"]
        )
        got = [(t["rows"], t["cols"]) for t in tables]
        original.append(_check("table_shape", CRITICAL, shape_ok, str(got)))
        critical.append(_check("table_shape", CRITICAL, shape_ok, str(got)))
        if not cands:
            original.append(_check("table_rows", CRITICAL, False, "no table"))
            critical.append(_check("table_row_values", CRITICAL, False, "no table"))
            continue
        t = cands[0]
        by_row: dict[int, list[tuple[int, str]]] = {}
        for r, c, _rs, _cs, text in t["cells"]:
            by_row.setdefault(r, []).append((c, text))
        rows = [
            " | ".join(x for _c, x in sorted(v)) for _r, v in sorted(by_row.items())
        ]
        bad_rows, bad_values, bad_labels = [], [], []
        for check in expect["row_checks"]:
            label_ok = vietnamese_ok or check["label"].isascii()
            with_values = [r for r in rows if all(c in r for c in check["cells"])]
            if not with_values:
                bad_values.append(check["label"])
            full = [
                r
                for r in with_values
                if not label_ok or norm(check["label"]) in norm(r)
            ]
            if not full:
                bad_rows.append(check["label"])
                if with_values:
                    bad_labels.append(check["label"])
        original.append(
            _check(
                "table_rows",
                CRITICAL if bad_values else GENERAL,
                not bad_rows,
                f"{len(expect['row_checks']) - len(bad_rows)}/{len(expect['row_checks'])}",
                rows_without_values=bad_values,
                rows_with_wrong_label_only=bad_labels,
            )
        )
        # Release view: the NUMBERS of every row, in one row, whatever the label.
        critical.append(
            _check(
                "table_row_values",
                CRITICAL,
                not bad_values,
                f"{len(expect['row_checks']) - len(bad_values)}/{len(expect['row_checks'])}",
                missing=bad_values,
            )
        )
        if vietnamese_ok and expect.get("merged_header"):
            merged = [
                c for c in t["cells"] if norm(expect["merged_header"]) in norm(c[4])
            ]
            ok = bool(merged) and max(c[3] for c in merged) >= 2
            original.append(_check("merged_header", CRITICAL, ok))
            critical.append(_check("merged_header", CRITICAL, ok))
    if len(tables) < len(spec["tables"]):
        original.append(_check("table_count", CRITICAL, False, str(len(tables))))
        critical.append(_check("table_count", CRITICAL, False, str(len(tables))))

    failed = [c for c in original if not c["ok"]]
    critical_failed = [c for c in critical if not c["ok"]] + [
        c for c in failed if c["class"] == CRITICAL
    ]
    original_verdict = "PASS" if not failed else "FAIL"
    explained = (
        bool(failed)
        and not critical_failed
        and all(
            c["name"] == "ordered_phrases" and not c.get("unexplained") and known
            for c in failed
        )
    )
    if original_verdict == "PASS":
        conditional = "PASS"
    elif explained:
        conditional = "PASS_WITH_KNOWN_LIMITATION"
    else:
        conditional = "FAIL"
    general = {
        "cer": round(metrics.cer(spec["ground_truth"], markdown), 4),
        "wer": round(metrics.wer(spec["ground_truth"], markdown), 4),
        "word_recall": round(metrics.word_recall(spec["ground_truth"], markdown), 4),
        "diacritics": metrics.diacritic_accuracy(spec["ground_truth"], markdown),
    }
    return {
        "original": original_verdict,
        "conditional": conditional,
        "failed_original_checks": [c["name"] for c in failed],
        "critical_ok": not critical_failed,
        "critical_failed": sorted({c["name"] for c in critical_failed}),
        "known_limitations": sorted({k["id"] for k in known}) if explained else [],
        "general": general,
        "checks": {"original": original, "critical": critical},
    }


def _tables(doc: Any) -> list[dict[str, Any]]:
    out = []
    for t in doc.tables:
        cells = [
            (
                c.start_row_offset_idx,
                c.start_col_offset_idx,
                c.row_span,
                c.col_span,
                c.text,
            )
            for c in t.data.table_cells
        ]
        out.append({"rows": t.data.num_rows, "cols": t.data.num_cols, "cells": cells})
    return out


def summarize(results: dict[str, dict[str, dict]]) -> dict[str, Any]:
    per_engine = {}
    for engine, docs in results.items():
        vals = list(docs.values())
        per_engine[engine] = {
            "original_pass": sum(v["original"] == "PASS" for v in vals),
            "conditional_pass": sum(v["conditional"] == "PASS" for v in vals),
            "conditional_known_limitation": sum(
                v["conditional"] == "PASS_WITH_KNOWN_LIMITATION" for v in vals
            ),
            "conditional_fail": sum(v["conditional"] == "FAIL" for v in vals),
            "critical_ok": sum(v["critical_ok"] for v in vals),
            "total": len(vals),
        }
    return per_engine


def to_markdown(results: dict[str, dict[str, dict]]) -> str:
    lines = [
        "| Engine | Fixture | Gốc | Có điều kiện | Critical | Assertion gốc thất bại | Giới hạn áp dụng | CER | Dấu |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for engine, docs in results.items():
        for name, v in docs.items():
            g = v["general"]
            dia = "–" if g["diacritics"] is None else f"{g['diacritics']:.2f}"
            crit = (
                "đạt"
                if v["critical_ok"]
                else "KHÔNG: " + ", ".join(v["critical_failed"])
            )
            lines.append(
                f"| {engine} | {name} | {v['original']} | {v['conditional']} | {crit} | "
                f"{', '.join(v['failed_original_checks']) or '–'} | "
                f"{', '.join(v['known_limitations']) or '–'} | {g['cer']:.3f} | {dia} |"
            )
    lines += [
        "",
        "| Engine | Gốc PASS | Có điều kiện: PASS | PASS kèm giới hạn đã chấp nhận | FAIL | Critical đạt |",
        "|---|---|---|---|---|---|",
    ]
    for engine, s in summarize(results).items():
        lines.append(
            f"| {engine} | {s['original_pass']}/{s['total']} | {s['conditional_pass']} | "
            f"{s['conditional_known_limitation']} | {s['conditional_fail']} | {s['critical_ok']}/{s['total']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=root / "tests" / "fixtures" / "ocr")
    ap.add_argument("--engines", nargs="*", default=list(ENGINES))
    ap.add_argument("--out", type=Path)
    ap.add_argument("--markdown", type=Path)
    args = ap.parse_args()
    sys.path.insert(0, str(root))

    from content_core import ContentCoreConfig

    from open_notebook.ocr import catalog
    from open_notebook.ocr.docling_extract import actual_ocr_models, convert_document
    from open_notebook.ocr.options import OcrSettings

    expected_class = {
        "rapidocr": "RapidOcrModel",
        "tesseract": "TesseractOcrCliModel",
        "easyocr": "EasyOcrModel",
    }
    manifest = json.loads((args.dir / "manifest.json").read_text(encoding="utf-8"))
    cc = ContentCoreConfig(document_engine="docling", docling_ocr=True)
    results: dict[str, dict[str, dict]] = {}
    for engine in args.engines:
        results[engine] = {}
        kind = catalog.get_engine(engine).docling_kind
        for name in sorted(manifest):
            spec = manifest[name]
            result, conv, prep = convert_document(
                str(args.dir / spec["file"]), cc, OcrSettings(engine=engine)
            )
            doc = result.document
            verdict = evaluate(
                engine,
                spec,
                doc.export_to_markdown(),
                _tables(doc),
                len(result.pages),
                expected_class[kind] in actual_ocr_models(conv),
            )
            verdict["prep"] = prep.as_meta()
            results[engine][name] = verdict
            print(
                f"{engine:15s} {name:18s} original={verdict['original']:4s} "
                f"conditional={verdict['conditional']:26s} critical_ok={verdict['critical_ok']} "
                f"failed={verdict['failed_original_checks']}",
                flush=True,
            )
    summary = summarize(results)
    print(json.dumps(summary, indent=1))
    if args.out:
        args.out.write_text(
            json.dumps(
                {
                    "accepted_limitations": ACCEPTED_LIMITATIONS,
                    "summary": summary,
                    "results": results,
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
    if args.markdown:
        args.markdown.write_text(to_markdown(results), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
