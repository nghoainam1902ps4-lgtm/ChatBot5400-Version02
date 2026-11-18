#!/usr/bin/env python3
"""Phase 12D quality benchmark on the SYNTHETIC legal fixtures (no real data).

Two independent measurements, reported separately on purpose:

STRUCTURE  Standard export vs Legal Document normalization of the same
           DoclingDocument, each compared with the fixture's DECLARED ground
           truth (which lines must stay, which are artifacts, which may be
           joined, which values are critical). Nothing is compared with another
           output of the system (Phase 12D2 finding T-01). The document comes
           from Docling's real ReadingOrderModel fed with the fixture's layout
           (tests/legal_harness.py), so OCR and layout-model errors are
           excluded: this isolates what the serializer / normalizer does to
           correct text. --before measures a frozen copy of another normalizer
           version with the same oracle.
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

MODES = ("standard", "legal_before", "legal")


def load_normalizer(path: str | None) -> Any:
    """The current normalizer, or a frozen copy of another version (``--before``).

    A frozen copy is how the pre-remediation implementation is measured with
    the SAME oracle and fixtures, e.g.::

      git show 2ef0074:open_notebook/ocr/legal_normalizer.py > /tmp/normalizer_v100.py
    """
    if not path:
        from open_notebook.ocr import legal_normalizer

        return legal_normalizer
    import importlib.util

    name = f"legal_normalizer_frozen_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look the module up while it loads
    spec.loader.exec_module(module)
    return module


def measure(
    fx: dict[str, Any],
    markdown: str,
    legal: bool,
    document: Any = None,
    traversed: bool | None = None,
) -> dict[str, Any]:
    """One output against the fixture's DECLARED ground truth (never against
    another output of the system: docs/review/PHASE12D3_QUALITY_BENCHMARK.md).

    Phase 12D5 (R2-14): with ``document`` (what ``markdown`` was serialized
    from) every displayed line is attributed to the declared element that
    produced it by provenance (scripts/ocr/phase12_oracle.py)."""
    shown = M.legal_display_markdown(markdown) if legal else markdown
    lines = M.display_lines(shown)
    text = " ".join(lines)
    p = M.preservation(
        fx,
        lines,
        markdown,
        document=document,
        pictures_traversed=legal if traversed is None else traversed,
    )
    hit, total = M.markers_displayed(fx, lines)
    renum, ordered = M.renumbered_list_items(shown)
    return {
        "required_units": p["required_units"],
        "false_deletion_units": p["false_deletion"],
        "false_deletion_tokens": p["false_deletion_tokens"],
        "false_deleted": p["false_deletion_units"][:8],
        "false_merge": p["false_merge"],
        "false_merged": p["false_merge_lines"][:4],
        "false_insertion": p["false_insertion"],
        "false_insertion_tokens": p["false_insertion_tokens"],
        "false_inserted": p["false_insertion_lines"][:4],
        "false_reordering": p["false_reordering"],
        "altered_units": p["altered_units"],
        "altered": [a["why"] for a in p["altered"]][:4],
        "placeholders_required": p["placeholders_required"],
        "placeholders_lost": p["placeholders_lost"],
        "furniture_shown": [p["furniture_shown"], p["furniture_declared"]],
        "marker_changed": p["marker_changed"],
        "attribution": p["attribution"],
        "critical_fields": [
            sum(1 for c in p["critical_fields"] if c["ok"]),
            len(p["critical_fields"]),
        ],
        "markers": [hit, total],
        "artifacts_removed": [
            p["artifacts_declared"] - p["artifacts_left"],
            p["artifacts_declared"],
        ],
        "joins": [p["joins_made"], p["joins_allowed"]],
        "tables_ok": p["tables_ok"],
        "table_rows": p["table_rows"],
        "placeholders": p["placeholders"],
        "numeric_only_lines": M.numeric_only_lines(lines),
        "renumbered_items": [renum, ordered],
        # Secondary: edit distance to the declared truth (sensitive to list
        # prefixes and kept artifacts; the counts above are the acceptance data).
        "cer": round(M.cer(fx["ground_truth"], text), 4),
        "wer": round(M.wer(fx["ground_truth"], text), 4),
    }


def structure(fx: dict[str, Any], repeats: int, before: Any = None) -> dict[str, Any]:
    N = load_normalizer(None)
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

    out: dict[str, Any] = {"name": fx["name"], "pages": len(fx["pages"])}
    out["standard"] = measure(fx, standard, legal=False, document=doc)
    out["standard"]["ms_median"] = round(statistics.median(t_std), 3)
    out["legal"] = measure(fx, res.content, legal=True, document=res.document)
    out["legal"]["ms_median"] = round(statistics.median(t_leg), 3)
    out["legal"]["peak_kib"] = round(peak / 1024, 1)
    out["legal"]["counts"] = res.counts
    out["legal"]["warnings"] = sorted({w["code"] for w in res.warnings})
    if fx.get("table_identical"):
        out["legal"]["tables_identical"] = all(
            t.export_to_markdown(doc) in res.content for t in doc.tables
        )
    if before is not None:
        # The frozen implementation mutates its input: give it its own document.
        old_doc = H.build_document(fx)
        old = before.normalize_document(old_doc)
        # v1.0.0 stored escaped list markers and rendered the text as it was.
        out["legal_before"] = measure(
            fx,
            old.content,
            legal=False,
            document=getattr(old, "document", None) or old_doc,
            traversed=True,
        )
        out["legal_before"]["counts"] = old.counts
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
    # an entry is a value, or [value, number of occurrences]
    protected = [
        e if isinstance(e, str) else str(e[0]) for e in fx.get("protected", [])
    ]
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


SUMS = (
    "required_units",
    "false_deletion_units",
    "false_deletion_tokens",
    "false_merge",
    "false_insertion",
    "false_insertion_tokens",
    "false_reordering",
    "altered_units",
    "placeholders_required",
    "placeholders_lost",
    "marker_changed",
    "placeholders",
    "numeric_only_lines",
    "table_rows",
)
PAIRS = (
    "critical_fields",
    "markers",
    "artifacts_removed",
    "joins",
    "renumbered_items",
    "furniture_shown",
)


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    agg: dict[str, Any] = {}
    for mode in MODES:
        r = [x[mode] for x in rows if mode in x]
        if not r:
            continue
        a: dict[str, Any] = {key: sum(x[key] for x in r) for key in SUMS}
        for key in PAIRS:
            a[key] = [sum(x[key][0] for x in r), sum(x[key][1] for x in r)]
        a["documents_with_false_deletion"] = sum(
            1 for x in r if x["false_deletion_units"]
        )
        a["documents_with_false_merge"] = sum(1 for x in r if x["false_merge"])
        a["documents_with_content_loss"] = sum(
            1
            for x in r
            if x["false_deletion_units"]
            or x["false_merge"]
            or x["false_insertion"]
            or x["placeholders_lost"]
            or x["altered_units"]
            or x["false_reordering"]
            or x["marker_changed"]
        )
        a["tables_ok"] = all(x["tables_ok"] for x in r)
        a["cer_mean"] = round(statistics.mean(x["cer"] for x in r), 4)
        a["wer_mean"] = round(statistics.mean(x["wer"] for x in r), 4)
        if "ms_median" in r[0]:
            a["ms_total"] = round(sum(x["ms_median"] for x in r), 2)
        agg[mode] = a
    legal = [x["legal"] for x in rows]
    agg["legal"]["peak_kib_max"] = max(x["peak_kib"] for x in legal)
    agg["legal"]["tables_identical"] = all(
        x.get("tables_identical", True) for x in legal
    )
    warnings: dict[str, int] = {}
    for x in legal:
        for code in x["warnings"]:
            warnings[code] = warnings.get(code, 0) + 1
    agg["legal"]["documents_with_warning"] = dict(sorted(warnings.items()))
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
    p.add_argument(
        "--before",
        help="frozen copy of another normalizer version to measure with the same "
        "oracle (e.g. git show 2ef0074:open_notebook/ocr/legal_normalizer.py > file)",
    )
    args = p.parse_args(argv)
    fixtures = H.load_fixtures().FIXTURES
    before = load_normalizer(args.before) if args.before else None
    rows = []
    for fx in fixtures:
        row = structure(fx, args.repeats, before)
        if args.pdf_dir:
            row["recognition"] = recognition(
                fx, Path(args.pdf_dir), args.tesseract_lang, args.dpi
            )
        rows.append(row)
    from importlib.metadata import version

    result = {
        "schema": "chatbot5400-phase12-benchmark/3",
        "oracle": "declared ground truth of the fixtures (tests/fixtures/legal), units "
        "attributed by source identity (page + bounding box -> DocItem, "
        "scripts/ocr/phase12_oracle.py, Phase 12D5 R2-14); schema /2 matched by text "
        "only and is superseded",
        "fixtures": len(rows),
        "normalizer_version": load_normalizer(None).NORMALIZER_VERSION,
        "before_normalizer_version": getattr(before, "NORMALIZER_VERSION", None),
        "versions": {k: version(k) for k in ("docling", "docling-core")},
        "tesseract": (
            subprocess.run(
                ["tesseract", "--version"], capture_output=True, text=True, check=False
            ).stdout.splitlines()
            or [""]
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
