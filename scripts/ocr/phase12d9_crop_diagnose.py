#!/usr/bin/env python3
"""OCR crop diagnostics for E2-01 (short text) and E2-02 (noisy crops) - Phase 12D9.

LOCAL USE ONLY, nothing is uploaded, nothing changes the ingestion: the default
PSM, the engines, the models, the orientation gate and Layout Heron stay as
they are. Default output is METADATA ONLY (counts, sizes, statistics, states);
``--with-text`` adds the recognised words to the JSON report, written with
owner-only permissions. The console prints counts only.

``benchmark`` (E2-01): synthetic crops of the short tokens Windows saw lost
when they are ALONE in a layout region (a single digit, ``9.``, ``4.``,
``123.``, ``a).``, ``đ).``, short document numbers, a Vietnamese word) and
crops that must stay EMPTY (blank, noise at the page edge, a stamp, a
signature, a picture, a table rule) or hold several lines. Each is read with
the configured Tesseract model at PSM 3 (Tesseract's default, what Docling
runs), 6 and 7, and with the PROPOSED short-text fallback - PSM 7 once, only
when PSM 3 succeeded with no text, the crop is one line high and has ink. It
measures accuracy, empty results, false recognition (a wrong token) and false
insertion (text on a crop that has none) - not just how many crops gave text.
The fallback is NOT implemented in the pipeline (Phase 12D9 decision): this is
the evidence for deciding it.

``crops DIR`` (E2-02): for crop images saved locally (e.g. with
``phase12_orientation_diagnose.py --with-text``): size, ink share, contrast,
blur, ink touching the edge (clipped text), and per PSM the word count and
confidence statistics. A pointer for a human reviewer, not a verdict.

Examples (inside the container)::

  python scripts/ocr/phase12d9_crop_diagnose.py benchmark --lang vie --out /app/data/diag/e2-01
  python scripts/ocr/phase12d9_crop_diagnose.py crops /app/data/diag/crops --lang vie \\
      --out /app/data/diag/e2-02
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA = "chatbot5400-crop-diagnose/1"
PSMS = (3, 6, 7)
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
)

# (category, expected text or "" for a crop that holds no text, kind)
CASES: list[tuple[str, str, str]] = [
    ("single digit", "4", "short"),
    ("single digit", "9", "short"),
    ("clause number", "9.", "short"),
    ("clause number", "4.", "short"),
    ("clause number", "123.", "short"),
    ("point marker", "a).", "short"),
    ("point marker", "đ).", "short"),
    ("short document number", "0004", "short"),
    ("short document number", "05/2024", "short"),
    ("Vietnamese word", "Điều", "short"),
    ("Vietnamese word", "Khoản", "short"),
    ("blank crop", "", "empty"),
    ("noise at the page edge", "", "empty"),
    ("stamp", "", "empty"),
    ("signature", "", "empty"),
    ("picture", "", "empty"),
    ("table rule", "", "empty"),
    ("several lines", "Điều 5. Hiệu lực\nKhoản 1. Thi hành", "multi"),
]


def _font(size: int) -> Any:
    from PIL import ImageFont

    for path in FONT_CANDIDATES:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise SystemExit("no TrueType font found (DejaVu / Arial)")


def render_case(category: str, text: str, dest: Path) -> Path:
    """A crop as Docling hands it to Tesseract (white page, black ink, ~216 dpi)."""
    from PIL import Image, ImageDraw

    font = _font(44)
    if category == "several lines":
        lines = text.split("\n")
        w = max(int(font.getlength(x)) for x in lines) + 40
        img = Image.new("L", (w, 70 * len(lines) + 30), 255)
        d = ImageDraw.Draw(img)
        for i, line in enumerate(lines):
            d.text((20, 15 + 70 * i), line, font=font, fill=0)
    elif text:
        w = int(font.getlength(text)) + 40
        img = Image.new("L", (max(w, 60), 80), 255)
        ImageDraw.Draw(img).text((20, 12), text, font=font, fill=0)
    else:
        img = Image.new("L", (260, 90), 255)
        d = ImageDraw.Draw(img)
        if category == "noise at the page edge":
            for x in range(0, 260, 7):
                d.point((x, 1), fill=0)
                d.point((x + 3, 88), fill=60)
            d.line((0, 0, 0, 89), fill=0, width=3)
        elif category == "stamp":
            d.ellipse((60, 5, 200, 85), outline=40, width=5)
            d.ellipse((80, 20, 180, 70), outline=40, width=2)
        elif category == "signature":
            d.line(
                (20, 60, 60, 20, 100, 70, 140, 25, 180, 65, 230, 30), fill=10, width=4
            )
        elif category == "picture":
            for y in range(90):
                d.line((0, y, 259, y), fill=120 + (y % 40))
            d.rectangle((40, 20, 120, 70), fill=30)
        elif category == "table rule":
            d.line((0, 45, 259, 45), fill=0, width=3)
            d.line((130, 0, 130, 89), fill=0, width=3)
    img.save(dest, dpi=(216, 216))
    return dest


def run_tesseract(
    real: str, image: Path, langs: list[str], tessdata: Optional[str], psm: int
) -> dict[str, Any]:
    """One recognition, the command Docling builds plus --psm; the TSV text
    read verbatim (E0-07). Returns words + confidences, never logs them."""
    from open_notebook.ocr import docling_patches

    cmd = [real]
    if langs:
        cmd += ["-l", "+".join(langs)]
    if tessdata:
        cmd += ["--tessdata-dir", tessdata]
    cmd += ["--psm", str(int(psm)), str(image), "stdout", "tsv"]
    out = subprocess.run(  # noqa: S603 - the configured Tesseract binary
        cmd, capture_output=True, stdin=subprocess.DEVNULL, timeout=300
    )
    if out.returncode != 0:
        return {"rc": out.returncode, "words": [], "conf": []}
    df = docling_patches.read_tesseract_tsv_plain(out.stdout.decode("utf-8", "replace"))
    df = df[df["text"].notna() & (df["text"].apply(str).str.strip() != "")]
    return {
        "rc": 0,
        "words": [str(t) for t in df["text"]],
        "conf": [float(c) for c in df["conf"] if float(c) >= 0],
    }


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", " ".join(text.split()))


def outcome(expected: str, words: list[str]) -> str:
    got = _norm(" ".join(words))
    if not expected:
        return "correct empty" if not got else "false insertion"
    if not got:
        return "empty"
    return "correct" if got == _norm(expected) else "false recognition"


def _pixels(img: Any) -> list[int]:
    get = getattr(img, "get_flattened_data", None) or img.getdata
    return list(get())


def image_stats(path: Path) -> dict[str, Any]:
    """Size, ink share, contrast, blur and ink at the edge of one crop."""
    from PIL import Image, ImageFilter

    with Image.open(path) as im:
        g = im.convert("L")
        w, h = g.size
        px = _pixels(g)
        ink = [p < 128 for p in px]
        edges = _pixels(g.filter(ImageFilter.FIND_EDGES))
        border = [
            px[i]
            for i in range(len(px))
            if i < w or i >= w * (h - 1) or i % w in (0, w - 1)
        ]
        dpi = im.info.get("dpi")
    return {
        "width": w,
        "height": h,
        "dpi": [round(float(x), 1) for x in dpi] if dpi else None,
        "ink_share": round(sum(ink) / max(len(ink), 1), 4),
        "contrast": round(statistics.pstdev(px), 1) if px else 0.0,
        "edge_energy": round(statistics.fmean(edges), 2) if edges else 0.0,
        "ink_touches_edge": any(p < 128 for p in border),
    }


def one_line_high(stats: dict[str, Any]) -> bool:
    """The geometry of ONE text line: short and wider than high (no layout label
    is available for a saved crop; the pipeline would also need a text label)."""
    return 20 <= int(stats["height"]) <= 140 and int(stats["width"]) >= int(
        stats["height"]
    )


def fallback(
    stats: dict[str, Any], psm3: dict[str, Any], psm7: dict[str, Any]
) -> dict[str, Any]:
    """The PROPOSED policy (not implemented): PSM 7 once, only when PSM 3 ran
    without error and returned no text, the crop is one line high and has ink.
    A non-empty PSM 3 result is never replaced."""
    if psm3["rc"] != 0 or psm3["words"]:
        return psm3
    if not one_line_high(stats) or float(stats["ink_share"]) <= 0.0:
        return psm3
    return psm7


def _summary(rows: list[dict[str, Any]], keys: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in keys:
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["outcomes"][key]] = counts.get(r["outcomes"][key], 0) + 1
        out[key] = counts
    return out


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)


def _real_tesseract() -> str:
    real = os.environ.get("OCR_TESSERACT_REAL") or shutil.which("tesseract")
    if not real:
        raise SystemExit("tesseract not found")
    return real


def cmd_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    real = _real_tesseract()
    langs = args.lang
    rows = []
    with tempfile.TemporaryDirectory(prefix="cb5400-e201-") as tmp:
        for n, (category, expected, kind) in enumerate(CASES, 1):
            img = render_case(category, expected, Path(tmp) / f"case_{n:02d}.png")
            stats = image_stats(img)
            reads = {
                psm: run_tesseract(real, img, langs, args.tessdata, psm) for psm in PSMS
            }
            fb = fallback(stats, reads[3], reads[7])
            outcomes = {f"psm{p}": outcome(expected, reads[p]["words"]) for p in PSMS}
            outcomes["fallback"] = outcome(expected, fb["words"])
            row: dict[str, Any] = {
                "case": n,
                "category": category,
                "kind": kind,
                "stats": stats,
                "outcomes": outcomes,
                "mean_conf": {
                    f"psm{p}": round(statistics.fmean(reads[p]["conf"]), 1)
                    if reads[p]["conf"]
                    else None
                    for p in PSMS
                },
                "fallback_used": fb is reads[7] and fb is not reads[3],
            }
            if args.with_text:
                row["expected"] = expected
                row["words"] = {f"psm{p}": reads[p]["words"] for p in PSMS}
            rows.append(row)
    keys = [f"psm{p}" for p in PSMS] + ["fallback"]
    return {
        "schema": SCHEMA,
        "mode": "benchmark",
        "langs": langs,
        "tesseract": real,
        "summary": _summary(rows, keys),
        "summary_by_kind": {
            kind: _summary([r for r in rows if r["kind"] == kind], keys)
            for kind in ("short", "empty", "multi")
        },
        "rows": rows,
    }


def cmd_crops(args: argparse.Namespace) -> dict[str, Any]:
    real = _real_tesseract()
    folder = Path(args.dir)
    images = sorted(
        p
        for p in folder.iterdir()
        if p.suffix.lower() in (".png", ".jpg", ".tif", ".tiff")
    )
    rows = []
    for n, img in enumerate(images, 1):
        stats = image_stats(img)
        reads = {
            psm: run_tesseract(real, img, args.lang, args.tessdata, psm) for psm in PSMS
        }
        row: dict[str, Any] = {
            "crop": n,
            "file": img.name if args.with_text else None,
            "stats": stats,
            "one_line_high": one_line_high(stats),
            "psm": {
                f"psm{p}": {
                    "rc": reads[p]["rc"],
                    "words": len(reads[p]["words"]),
                    "mean_conf": round(statistics.fmean(reads[p]["conf"]), 1)
                    if reads[p]["conf"]
                    else None,
                    "min_conf": round(min(reads[p]["conf"]), 1)
                    if reads[p]["conf"]
                    else None,
                    "digits": sum(bool(re.search(r"\d", w)) for w in reads[p]["words"]),
                }
                for p in PSMS
            },
        }
        if args.with_text:
            row["words"] = {f"psm{p}": reads[p]["words"] for p in PSMS}
        rows.append(row)
    return {
        "schema": SCHEMA,
        "mode": "crops",
        "langs": args.lang,
        "crops": len(rows),
        "rows": rows,
    }


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("benchmark", "crops"):
        s = sub.add_parser(name)
        if name == "crops":
            s.add_argument("dir", help="folder of crop images (local)")
        s.add_argument(
            "--lang", nargs="+", default=["vie"], help="Tesseract languages / model"
        )
        s.add_argument("--tessdata", help="tessdata folder (default: Tesseract's own)")
        s.add_argument("--out", required=True, help="report folder (owner-only)")
        s.add_argument(
            "--with-text",
            action="store_true",
            help="add the words to the report (owner-only)",
        )
    args = p.parse_args(argv)
    report = cmd_benchmark(args) if args.cmd == "benchmark" else cmd_crops(args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(out, 0o700)
    except OSError:
        pass
    _write_private(
        out / f"crop_diagnose_{args.cmd}.json",
        json.dumps(report, ensure_ascii=False, indent=1),
    )
    brief = (
        report.get("summary") if args.cmd == "benchmark" else {"crops": report["crops"]}
    )
    print(json.dumps(brief, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
