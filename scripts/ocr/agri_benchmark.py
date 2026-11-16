"""Benchmark of the custom Tesseract Agri model against Tesseract Best (Phase 10E).

Compares, on the synthetic legal fixtures of
``generate_agri_benchmark_fixtures.py``:

    A  best  = best/vie + best/eng         (engine tesseract_best, unchanged)
    B  agri  = <agri version>              (engine tesseract_agri, Vietnamese only)
    C  agri_eng = <agri version> + best/eng

Two stages, the same metrics:

    direct    the Tesseract executable on the page images (isolates the model)
    pipeline  the production path (docling_extract.convert_file: Docling + Layout
              Heron + TableFormer + Tesseract through the OSD gate), with
              Force Full Page OCR off and on

    uv run python scripts/ocr/agri_benchmark.py direct   --dir FIXTURES --out direct.json
    uv run python scripts/ocr/agri_benchmark.py pipeline --dir FIXTURES --out pipeline.json
    uv run python scripts/ocr/agri_benchmark.py report   direct.json pipeline.json

Metrics (lower is better unless noted): CER, WER, diacritic accuracy (higher),
heading accuracy (higher), Điều / Khoản / Điểm anchor recall (higher),
legal-meaning errors (changed or dropped negation / obligation / exception
words and numbers), omission rate, seconds, CPU seconds, peak RSS.

Read-only with respect to the application: nothing is installed or activated.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from open_notebook.ocr import metrics  # noqa: E402

# Words whose loss or change alters what a legal sentence means.
NEGATION = {"không", "chưa", "chẳng", "cấm", "nghiêm"}
OBLIGATION = {"phải", "buộc", "bắt", "nghĩa", "vụ", "trách", "nhiệm"}
EXCEPTION = {"trừ", "ngoại", "chỉ", "ngoài"}
PERMISSION = {"được", "quyền"}
LIMIT = {"tối", "đa", "thiểu", "quá", "vượt", "ít", "nhất", "chậm"}
CRITICAL = NEGATION | OBLIGATION | EXCEPTION | PERMISSION | LIMIT

_EDGE_PUNCT = ".,;:()[]\"'“”‘’!?"


def _core(token: str) -> str:
    """A token as its meaning: lower case, no surrounding punctuation."""
    return token.strip(_EDGE_PUNCT).lower()


def _is_critical(token: str) -> bool:
    core = _core(token)
    return core in CRITICAL or any(ch.isdigit() for ch in core)


def align(ref: list[str], hyp: list[str]) -> list[tuple[str, str | None, str | None]]:
    """Word alignment: ("ok" | "sub" | "del" | "ins", ref word, hyp word)."""
    n, m = len(ref), len(hyp)
    dist = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dist[i][0] = i
    for j in range(m + 1):
        dist[0][j] = j
    for i in range(1, n + 1):
        ri, row, prev = ref[i - 1], dist[i], dist[i - 1]
        for j in range(1, m + 1):
            row[j] = min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + (ri != hyp[j - 1]))
    ops: list[tuple[str, str | None, str | None]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if (
            i > 0
            and j > 0
            and dist[i][j] == dist[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1])
        ):
            ops.append(
                ("ok" if ref[i - 1] == hyp[j - 1] else "sub", ref[i - 1], hyp[j - 1])
            )
            i, j = i - 1, j - 1
        elif i > 0 and dist[i][j] == dist[i - 1][j] + 1:
            ops.append(("del", ref[i - 1], None))
            i -= 1
        else:
            ops.append(("ins", None, hyp[j - 1]))
            j -= 1
    ops.reverse()
    return ops


def _window_cer(needle: str, hyp_words: list[str]) -> float:
    """Smallest CER of ``needle`` against any hypothesis window of similar length."""
    k = len(needle.split())
    best = 1.0
    for size in {max(1, k - 1), k, k + 1}:
        for start in range(0, max(1, len(hyp_words) - size + 1)):
            window = " ".join(hyp_words[start : start + size])
            best = min(best, metrics.cer(needle, window))
            if best == 0.0:
                return 0.0
    return best


def legal_metrics(entry: dict[str, Any], hypothesis: str) -> dict[str, Any]:
    ref_text = entry["ground_truth"]
    ref_n, hyp_n = metrics.normalize(ref_text), metrics.normalize(hypothesis)
    ref_w, hyp_w = ref_n.split(), hyp_n.split()
    ops = align(ref_w, hyp_w)
    deletions = sum(1 for op, _, _ in ops if op == "del")
    legal: list[str] = []
    for op, r, h in ops:
        if op in ("sub", "del") and r is not None and _is_critical(r):
            if op == "del" or _core(r) != _core(h or ""):
                legal.append(f"{r} -> {h if h is not None else '∅'}")
        elif op == "ins" and h is not None and _core(h) in NEGATION:
            legal.append(f"∅ -> {h}")
    anchors = entry.get("anchors") or {}
    out: dict[str, Any] = {
        "ref_words": len(ref_w),
        "cer": round(metrics.cer(ref_text, hypothesis), 4),
        "wer": round(metrics.wer(ref_text, hypothesis), 4),
        "diacritic_accuracy": metrics.diacritic_accuracy(ref_text, hypothesis),
        "word_recall": round(metrics.word_recall(ref_text, hypothesis), 4),
        "omission_rate": round(deletions / max(1, len(ref_w)), 4),
        "legal_errors": len(legal),
        "legal_error_examples": legal[:12],
    }
    for kind in ("heading", "dieu", "khoan", "diem"):
        items = [metrics.normalize(a) for a in anchors.get(kind, [])]
        if not items:
            out[f"{kind}_exact"] = None
            continue
        out[f"{kind}_total"] = len(items)
        out[f"{kind}_hits"] = sum(1 for a in items if a in hyp_n)
        out[f"{kind}_exact"] = round(out[f"{kind}_hits"] / len(items), 4)
        if kind == "heading":
            out["heading_cer"] = round(
                sum(_window_cer(a, hyp_w) for a in items) / len(items), 4
            )
    fields = entry.get("key_fields") or {}
    for name in ("doc_numbers", "dates"):
        out[f"{name}_recall"] = metrics.field_recall(fields.get(name) or [], hypothesis)
    return out


# --- direct Tesseract ------------------------------------------------------------


def _run_child(cmd: list[str], env: dict[str, str]) -> tuple[str, float, float, int]:
    """Run ``cmd``; return (stdout, wall seconds, CPU seconds, peak RSS in KiB)."""
    started = time.time()
    proc = subprocess.Popen(  # noqa: S603 - fixed argument list, no shell
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env
    )
    assert proc.stdout is not None
    out = proc.stdout.read()
    _, status, usage = os.wait4(proc.pid, 0)
    proc.returncode = os.waitstatus_to_exitcode(status)
    if proc.returncode != 0:
        raise RuntimeError(f"{cmd[0]} exited with {proc.returncode}")
    return (
        out.decode("utf-8", "replace"),
        time.time() - started,
        usage.ru_utime + usage.ru_stime,
        usage.ru_maxrss,
    )


def configs(agri_version: str) -> dict[str, list[str]]:
    agri = f"custom/agri/{agri_version}/vie_agri"
    return {
        "best": ["best/vie", "best/eng"],
        "agri": [agri],
        "agri_eng": [agri, "best/eng"],
    }


def cmd_direct(args: argparse.Namespace) -> int:
    manifest = json.loads((args.dir / "manifest.json").read_text(encoding="utf-8"))
    env = dict(os.environ, TESSDATA_PREFIX=str(args.tessdata))
    rows = []
    for name, langs in configs(args.agri_version).items():
        for entry in manifest["files"]:
            if entry["text_layer"]:
                continue
            text, wall, cpu, rss = "", 0.0, 0.0, 0
            for page in entry["page_images"]:
                t, w, c, r = _run_child(
                    [
                        args.tesseract,
                        str(args.dir / page),
                        "stdout",
                        "-l",
                        "+".join(langs),
                        "--dpi",
                        str(entry["dpi"]),
                    ],
                    env,
                )
                text += t + "\n"
                wall, cpu, rss = wall + w, cpu + c, max(rss, r)
            row = {
                "stage": "direct",
                "config": name,
                "langs": langs,
                "file": entry["file"],
                "doc": entry["doc"],
                "variant": entry["variant"],
                "seconds": round(wall, 2),
                "cpu_seconds": round(cpu, 2),
                "peak_rss_mb": round(rss / 1024, 1),
                **legal_metrics(entry, text),
            }
            if args.keep_text:
                row["text"] = text
            rows.append(row)
            print(
                f"direct {name:<9} {entry['file']:<32} cer={row['cer']:.4f} "
                f"wer={row['wer']:.4f} legal={row['legal_errors']}",
                flush=True,
            )
    args.out.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


# --- production pipeline ------------------------------------------------------------


def _pipeline_child(args: argparse.Namespace) -> int:
    """One (engine, agri language set, full page) combination, in its own process."""
    from content_core import ContentCoreConfig

    from open_notebook.ocr.docling_extract import convert_file
    from open_notebook.ocr.options import OcrSettings, describe

    manifest = json.loads((args.dir / "manifest.json").read_text(encoding="utf-8"))
    engine = "tesseract_best" if args.config == "best" else "tesseract_agri"
    ocr = OcrSettings(
        enabled=True,
        engine=engine,
        force_full_page=args.full_page,
        # The version named on the command line, like the "direct" stage — not
        # whatever happens to be active.
        custom_version=args.agri_version if engine == "tesseract_agri" else None,
    ).pinned()
    info = describe(engine, ocr.custom_version)
    rows = []
    for entry in manifest["files"]:
        if args.only and entry["file"] not in args.only:
            continue
        self0 = resource.getrusage(resource.RUSAGE_SELF)
        kids0 = resource.getrusage(resource.RUSAGE_CHILDREN)
        started = time.time()
        error = None
        text = ""
        meta: dict[str, Any] = {}
        try:
            text, meta = convert_file(
                str(args.dir / entry["file"]),
                ContentCoreConfig(document_engine="docling", docling_ocr=True),
                ocr,
            )
        except Exception as e:  # a failed file is a result, not a crash
            error = f"{type(e).__name__}: {e}"[:400]
        wall = time.time() - started
        self1 = resource.getrusage(resource.RUSAGE_SELF)
        kids1 = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu = (
            self1.ru_utime
            + self1.ru_stime
            + kids1.ru_utime
            + kids1.ru_stime
            - self0.ru_utime
            - self0.ru_stime
            - kids0.ru_utime
            - kids0.ru_stime
        )
        row = {
            "stage": "pipeline",
            "config": args.config,
            "langs": info.get("lang"),
            "model": info.get("model"),
            "full_page": bool(args.full_page),
            "file": entry["file"],
            "doc": entry["doc"],
            "variant": entry["variant"],
            "text_layer": entry["text_layer"],
            "seconds": round(wall, 2),
            "cpu_seconds": round(cpu, 2),
            # Process high-water mark: includes the Docling models, loaded once.
            "peak_rss_mb": round(max(self1.ru_maxrss, kids1.ru_maxrss) / 1024, 1),
            "ocr_models": meta.get("ocr_models"),
            "layout_model": meta.get("layout_model"),
            "table_model": meta.get("table_model"),
            "table_mode": meta.get("table_mode"),
            "ocr_scale": meta.get("ocr_scale"),
            "error": error,
            "agri_version": ocr.custom_version,
            **legal_metrics(entry, text),
        }
        if args.keep_text:
            row["text"] = text
        rows.append(row)
        print(
            f"pipeline {args.config:<9} full_page={int(bool(args.full_page))} "
            f"{entry['file']:<32} cer={row['cer']:.4f} wer={row['wer']:.4f} "
            f"legal={row['legal_errors']} {row['seconds']}s"
            + (f" ERROR {error}" if error else ""),
            flush=True,
        )
    print("JSON:" + json.dumps(rows, ensure_ascii=False))
    return 1 if any(r["error"] for r in rows) else 0


def cmd_pipeline(args: argparse.Namespace) -> int:
    if args.child:
        return _pipeline_child(args)
    rows: list[dict[str, Any]] = []
    failed = 0
    for config in args.configs:
        for full_page in (False, True):
            env = dict(os.environ)
            # The Agri language set is a deployment setting (options.py).
            env["OCR_AGRI_WITH_ENGLISH"] = "true" if config == "agri_eng" else "false"
            cmd = [
                sys.executable,
                str(Path(__file__).resolve()),
                "pipeline",
                "--child",
                "--config",
                config,
                "--dir",
                str(args.dir),
                "--out",
                str(args.out),
            ]
            cmd += ["--agri-version", args.agri_version]
            if full_page:
                cmd.append("--full-page")
            if args.keep_text:
                cmd.append("--keep-text")
            if args.only:
                cmd += ["--only", *args.only]
            proc = subprocess.run(  # noqa: S603 - our own script, fixed arguments
                cmd, env=env, stdout=subprocess.PIPE, text=True, check=False
            )
            for line in proc.stdout.splitlines():
                if line.startswith("JSON:"):
                    rows.extend(json.loads(line[5:]))
                else:
                    print(line, flush=True)
            if proc.returncode != 0:
                failed += 1
                print(f"child for {config} full_page={full_page} failed", flush=True)
    args.out.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    errors = sum(1 for r in rows if r.get("error"))
    if failed or errors:
        print(f"{failed} run(s) failed, {errors} file(s) with an error", flush=True)
    return 1 if failed or errors else 0


# --- report -------------------------------------------------------------------------

_MEAN_KEYS = (
    "cer",
    "wer",
    "diacritic_accuracy",
    "heading_exact",
    "heading_cer",
    "dieu_exact",
    "khoan_exact",
    "diem_exact",
    "doc_numbers_recall",
    "dates_recall",
    "omission_rate",
)


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"files": len(rows)}
    for key in _MEAN_KEYS:
        vals = [r[key] for r in rows if r.get(key) is not None]
        out[key] = round(sum(vals) / len(vals), 4) if vals else None
    words = sum(r["ref_words"] for r in rows)
    out["legal_errors"] = sum(r["legal_errors"] for r in rows)
    out["legal_errors_per_1000_words"] = (
        round(1000 * out["legal_errors"] / words, 2) if words else None
    )
    out["seconds"] = round(sum(r["seconds"] for r in rows), 1)
    out["cpu_seconds"] = round(sum(r["cpu_seconds"] for r in rows), 1)
    out["peak_rss_mb"] = max((r["peak_rss_mb"] for r in rows), default=None)
    out["errors"] = sum(1 for r in rows if r.get("error"))
    return out


def _fmt(v: Any, pct: bool = False) -> str:
    if v is None:
        return "—"
    return f"{100 * v:.2f}%" if pct else str(v)


def cmd_report(args: argparse.Namespace) -> int:
    rows: list[dict[str, Any]] = []
    for f in args.files:
        rows.extend(json.loads(Path(f).read_text(encoding="utf-8")))
    scans = [r for r in rows if not r.get("text_layer")]
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for r in scans:
        groups.setdefault((r["stage"], r.get("full_page"), r["config"]), []).append(r)
    by_variant: dict[tuple, list[dict[str, Any]]] = {}
    for r in scans:
        by_variant.setdefault(
            (r["stage"], r.get("full_page"), r["variant"], r["config"]), []
        ).append(r)
    summary = {
        "overall": {
            f"{s}|full_page={fp}|{c}": summarise(g) for (s, fp, c), g in groups.items()
        },
        "by_variant": {
            f"{s}|full_page={fp}|{v}|{c}": summarise(g)
            for (s, fp, v, c), g in by_variant.items()
        },
    }
    if args.json:
        Path(args.json).write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    cols = (
        "| Giai đoạn | Full Page | Cấu hình | CER | WER | Dấu TV | Tiêu đề đúng | "
        "CER tiêu đề | Điều | Khoản | Điểm | Số hiệu | Ngày | Lỗi pháp lý | Bỏ sót | "
        "Giây | CPU-giây | RSS MB |"
    )
    print(cols)
    print("|" + "---|" * (cols.count("|") - 1))
    for (stage, fp, config), g in sorted(groups.items(), key=lambda kv: str(kv[0])):
        s = summarise(g)
        print(
            f"| {stage} | {'—' if fp is None else ('ON' if fp else 'OFF')} | {config} | "
            f"{_fmt(s['cer'], True)} | {_fmt(s['wer'], True)} | "
            f"{_fmt(s['diacritic_accuracy'], True)} | {_fmt(s['heading_exact'], True)} | "
            f"{_fmt(s['heading_cer'], True)} | {_fmt(s['dieu_exact'], True)} | "
            f"{_fmt(s['khoan_exact'], True)} | {_fmt(s['diem_exact'], True)} | "
            f"{_fmt(s['doc_numbers_recall'], True)} | {_fmt(s['dates_recall'], True)} | "
            f"{s['legal_errors']} ({s['legal_errors_per_1000_words']}/1000 từ) | "
            f"{_fmt(s['omission_rate'], True)} | {s['seconds']} | {s['cpu_seconds']} | "
            f"{s['peak_rss_mb']} |"
        )
    print()
    print(
        "| Giai đoạn | Full Page | Chất lượng scan | Cấu hình | CER | WER | Dấu TV | "
        "Tiêu đề đúng | Lỗi pháp lý | Bỏ sót |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|")
    for (stage, fp, variant, config), g in sorted(
        by_variant.items(), key=lambda kv: str(kv[0])
    ):
        s = summarise(g)
        print(
            f"| {stage} | {'—' if fp is None else ('ON' if fp else 'OFF')} | {variant} | "
            f"{config} | {_fmt(s['cer'], True)} | {_fmt(s['wer'], True)} | "
            f"{_fmt(s['diacritic_accuracy'], True)} | {_fmt(s['heading_exact'], True)} | "
            f"{s['legal_errors']} | {_fmt(s['omission_rate'], True)} |"
        )
    text_layer = [r for r in rows if r.get("text_layer")]
    if text_layer:
        print()
        print("| PDF có lớp văn bản | Full Page | Cấu hình | CER | WER | Giây |")
        print("|---|---|---|---|---|---|")
        for r in text_layer:
            print(
                f"| {r['file']} | {'ON' if r.get('full_page') else 'OFF'} | "
                f"{r['config']} | {_fmt(r['cer'], True)} | {_fmt(r['wer'], True)} | "
                f"{r['seconds']} |"
            )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("direct", help="Tesseract executable on the page images")
    d.add_argument("--dir", required=True, type=Path)
    d.add_argument("--out", required=True, type=Path)
    d.add_argument("--tessdata", required=True, type=Path, help="TESSDATA_PREFIX")
    d.add_argument("--tesseract", default="tesseract")
    d.add_argument("--agri-version", default="v1")
    d.add_argument("--keep-text", action="store_true")
    d.set_defaults(func=cmd_direct)

    p = sub.add_parser("pipeline", help="production Docling pipeline")
    p.add_argument("--dir", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument(
        "--configs",
        nargs="+",
        default=["best", "agri", "agri_eng"],
        choices=["best", "agri", "agri_eng"],
    )
    p.add_argument("--only", nargs="*")
    p.add_argument("--agri-version", default="v1")
    p.add_argument("--keep-text", action="store_true")
    p.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--config", help=argparse.SUPPRESS)
    p.add_argument("--full-page", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_pipeline)

    r = sub.add_parser("report", help="Markdown tables from result files")
    r.add_argument("files", nargs="+")
    r.add_argument("--json", help="also write the aggregated numbers here")
    r.set_defaults(func=cmd_report)

    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
