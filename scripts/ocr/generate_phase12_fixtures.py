#!/usr/bin/env python3
"""Render the Phase 12 synthetic legal fixtures as PDFs (all content FICTIONAL).

The layout specs live in ``tests/fixtures/legal/legal_fixtures.py``. This
script draws them so the FULL pipeline (Layout Heron, TableFormer, the OCR
engines, Agri) can be measured on a machine with the Docling models:

  <name>.scan.pdf         image-only pages (no text layer), 200 DPI
  <name>.watermark.pdf    scan + a tilted "BẢN SAO KIỂM SOÁT" watermark
  <name>.text.pdf         electronic PDF with a real text layer (needs reportlab)
  <name>.hidden_ocr.pdf   scan + an invisible, deliberately poor OCR text layer (reportlab)
  <name>.mixed.pdf        multi-page fixtures: odd pages text layer, even pages scan (reportlab)
  <name>.gt.txt           ground truth for scripts/ocr/phase12_compare.py

Usage::

  uv run python scripts/ocr/generate_phase12_fixtures.py --out ./phase12-fixtures
  uv run --with reportlab python scripts/ocr/generate_phase12_fixtures.py --out ./phase12-fixtures --all

Nothing is committed from the output: regenerate when needed.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import math
import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "tests" / "fixtures" / "legal" / "legal_fixtures.py"
DPI = 200
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/times.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/timesbd.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def load_specs() -> Any:
    spec = importlib.util.spec_from_file_location("legal_fixtures", SPEC)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FONT_DIR: Path | None = (
    None  # --font-dir / PHASE12_FONT_DIR (e.g. Windows fonts mounted read-only)
)
FONT_DIR_NAMES = {
    "regular": ["times.ttf", "arial.ttf", "DejaVuSerif.ttf", "DejaVuSans.ttf"],
    "bold": [
        "timesbd.ttf",
        "arialbd.ttf",
        "DejaVuSerif-Bold.ttf",
        "DejaVuSans-Bold.ttf",
    ],
}


def _font_path(candidates: list[str]) -> str | None:
    if FONT_DIR is not None:
        kind = "bold" if candidates is BOLD_CANDIDATES else "regular"
        for name in FONT_DIR_NAMES[kind]:
            for found in (
                FONT_DIR / name,
                FONT_DIR / name.upper(),
                FONT_DIR / name.capitalize(),
            ):
                if found.is_file():
                    return str(found)
    return next((c for c in candidates if Path(c).is_file()), None)


def _font(candidates: list[str], size: int) -> Any:
    path = _font_path(candidates)
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


def _px(v: float) -> int:
    return int(round(v * DPI / 72))


def _fit_size(
    draw: ImageDraw.ImageDraw, text: str, box_w: float, box_h: float, bold: bool
) -> Any:
    size = max(10, int(_px(box_h) * 0.8))
    while size > 10:
        font = _font(BOLD_CANDIDATES if bold else FONT_CANDIDATES, size)
        if draw.textlength(text, font=font) <= _px(box_w):
            return font
        size -= 1
    return _font(BOLD_CANDIDATES if bold else FONT_CANDIDATES, 10)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: Any, width_px: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= width_px or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    return lines + ([cur] if cur else [])


def draw_element(draw: ImageDraw.ImageDraw, el: dict[str, Any]) -> None:
    left, t, r, b = el["bbox"]
    label = el["label"]
    if label == "picture":
        w, h = r - left, b - t
        if el.get("children"):
            # stamp: red double circle with its text
            draw.ellipse(
                [_px(left), _px(t), _px(r), _px(b)], outline=(200, 30, 30), width=4
            )
            draw.ellipse(
                [_px(left + 6), _px(t + 6), _px(r - 6), _px(b - 6)],
                outline=(200, 30, 30),
                width=2,
            )
            for c in el["children"]:
                draw_element(draw, {**c, "color": (200, 30, 30)})
        elif w * h > 0.15 * 595 * 842:
            draw.rectangle(
                [_px(left), _px(t), _px(r), _px(b)], outline=(90, 90, 90), width=3
            )
            for k in range(3):
                x0 = _px(left + 30 + k * (w - 60) / 3)
                draw.rectangle(
                    [x0, _px(t + h / 3), x0 + _px((w - 120) / 3), _px(t + 2 * h / 3)],
                    outline=(60, 60, 160),
                    width=3,
                )
        elif h >= w * 0.8:  # stamp without text
            draw.ellipse(
                [_px(left), _px(t), _px(r), _px(b)], outline=(200, 30, 30), width=4
            )
        else:  # signature squiggle
            pts = [
                (_px(left + i * w / 40), _px(t + h / 2 + math.sin(i / 2.5) * h / 3))
                for i in range(41)
            ]
            draw.line(pts, fill=(20, 20, 120), width=3)
        return
    if label == "table":
        rows = el["rows"]
        n_r, n_c = len(rows), len(rows[0])
        rh, cw = (b - t) / n_r, (r - left) / n_c
        for i in range(n_r + 1):
            draw.line(
                [(_px(left), _px(t + i * rh)), (_px(r), _px(t + i * rh))],
                fill=0,
                width=2,
            )
        for j in range(n_c + 1):
            draw.line(
                [(_px(left + j * cw), _px(t)), (_px(left + j * cw), _px(b))],
                fill=0,
                width=2,
            )
        for i, row in enumerate(rows):
            for j, val in enumerate(row):
                font = _fit_size(
                    draw,
                    val,
                    cw - 8,
                    min(rh * 0.6, 12),
                    bold=(i == 0 and not row[0].isdigit()),
                )
                draw.text(
                    (_px(left + j * cw + 4), _px(t + i * rh + rh * 0.2)),
                    val,
                    font=font,
                    fill=0,
                )
        return
    text = el.get("text", "")
    if not text:
        return
    bold = label in ("section_header", "title")
    font = _font(
        BOLD_CANDIDATES if bold else FONT_CANDIDATES,
        max(10, int(_px(min(b - t, 14)) * 0.8)),
    )
    lines = _wrap(draw, text, font, _px(r - left))
    if len(lines) == 1:
        font = _fit_size(draw, text, r - left, min(b - t, 14), bold)
        lines = [text]
    y = _px(t)
    for line in lines:
        draw.text((_px(left), y), line, font=font, fill=el.get("color", 0))
        y += int(font.size * 1.3)


def render_page(page: list[dict[str, Any]], watermark: bool = False) -> Image.Image:
    img = Image.new("RGB", (_px(595), _px(842)), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for el in page:
        draw_element(draw, el)
    if watermark:
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        wd = ImageDraw.Draw(layer)
        font = _font(BOLD_CANDIDATES, _px(48))
        wd.text(
            (_px(90), _px(380)),
            "BẢN SAO KIỂM SOÁT",
            font=font,
            fill=(150, 150, 150, 110),
        )
        layer = layer.rotate(35, center=(img.size[0] // 2, img.size[1] // 2))
        img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
    return img


def save_scan(pages: list[Image.Image], path: Path) -> None:
    first, rest = pages[0], pages[1:]
    first.save(path, "PDF", resolution=DPI, save_all=True, append_images=rest)


def _reportlab() -> Any:
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen import canvas
    except ImportError:
        return None
    regular, bold = _font_path(FONT_CANDIDATES), _font_path(BOLD_CANDIDATES)
    if not regular:
        return None
    pdfmetrics.registerFont(TTFont("P12", regular))
    pdfmetrics.registerFont(TTFont("P12B", bold or regular))
    return canvas


def save_text_pdf(
    fx: dict[str, Any],
    path: Path,
    scan_pages: set[int] | None = None,
    hidden_bad_ocr: bool = False,
) -> None:
    canvas = _reportlab()
    assert canvas is not None
    c = canvas.Canvas(str(path), pagesize=(595, 842))
    for n, page in enumerate(fx["pages"], start=1):
        if hidden_bad_ocr or (scan_pages and n in scan_pages):
            img = render_page(page)
            buf = io.BytesIO()
            img.save(buf, "PNG")
            buf.seek(0)
            from reportlab.lib.utils import ImageReader

            c.drawImage(ImageReader(buf), 0, 0, width=595, height=842)
        if not (scan_pages and n in scan_pages):
            text_obj_mode = 3 if hidden_bad_ocr else 0  # 3 = invisible text
            for el in page:
                items = [el] + list(el.get("children", []))
                for it in items:
                    text = it.get("text")
                    if not text:
                        if it["label"] == "table":
                            left, t, r, b = it["bbox"]
                            rh, cw = (
                                (b - t) / len(it["rows"]),
                                (r - left) / len(it["rows"][0]),
                            )
                            for i, row in enumerate(it["rows"]):
                                for j, val in enumerate(row):
                                    _draw_text(
                                        c,
                                        val,
                                        left + j * cw + 4,
                                        t + i * rh + rh * 0.7,
                                        9,
                                        False,
                                        text_obj_mode,
                                        hidden_bad_ocr,
                                    )
                        continue
                    left, top, _, bottom = it["bbox"]
                    size = max(8.0, min(12.0, (bottom - top) * 0.8))
                    _draw_text(
                        c,
                        text,
                        left,
                        top + size,
                        size,
                        it["label"] in ("section_header", "title"),
                        text_obj_mode,
                        hidden_bad_ocr,
                    )
        c.showPage()
    c.save()


def _degrade(text: str) -> str:
    """A poor hidden OCR layer: Vietnamese diacritics stripped, some digits swapped."""
    import unicodedata

    out = "".join(
        ch
        for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )
    return out.replace("đ", "d").replace("Đ", "D").replace("0", "O").replace("1", "l")


def _draw_text(
    c: Any,
    text: str,
    x: float,
    y_top: float,
    size: float,
    bold: bool,
    mode: int,
    bad: bool,
) -> None:
    t = c.beginText()
    t.setTextRenderMode(mode)
    t.setFont("P12B" if bold else "P12", size)
    t.setTextOrigin(x, 842 - y_top)
    t.textLine(_degrade(text) if bad else text)
    c.drawText(t)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--out", required=True)
    p.add_argument(
        "--all",
        action="store_true",
        help="also text / hidden-OCR / mixed variants (needs reportlab)",
    )
    p.add_argument("--only", nargs="*", help="fixture names")
    p.add_argument(
        "--font-dir",
        default=os.environ.get("PHASE12_FONT_DIR"),
        help="folder with a Vietnamese-capable TTF (times.ttf / arial.ttf / DejaVu)",
    )
    args = p.parse_args(argv)
    global FONT_DIR
    FONT_DIR = Path(args.font_dir) if args.font_dir else None
    if _font_path(FONT_CANDIDATES) is None:
        raise SystemExit(
            "No Vietnamese-capable font found: pass --font-dir (e.g. the Windows Fonts folder mounted read-only)."
        )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fixtures = load_specs().FIXTURES
    if args.only:
        fixtures = [f for f in fixtures if f["name"] in set(args.only)]
    have_rl = _reportlab() is not None
    manifest = []
    for fx in fixtures:
        if not any(fx["pages"]):
            continue
        variants = []
        images = [render_page(pg) for pg in fx["pages"]]
        save_scan(images, out / f"{fx['name']}.scan.pdf")
        variants.append("scan")
        save_scan(
            [render_page(pg, watermark=True) for pg in fx["pages"]],
            out / f"{fx['name']}.watermark.pdf",
        )
        variants.append("watermark")
        if args.all and have_rl:
            save_text_pdf(fx, out / f"{fx['name']}.text.pdf")
            save_text_pdf(fx, out / f"{fx['name']}.hidden_ocr.pdf", hidden_bad_ocr=True)
            variants += ["text", "hidden_ocr"]
            if len(fx["pages"]) > 1:
                save_text_pdf(
                    fx,
                    out / f"{fx['name']}.mixed.pdf",
                    scan_pages={n for n in range(2, len(fx["pages"]) + 1, 2)},
                )
                variants.append("mixed")
        for v in variants:
            (out / f"{fx['name']}.{v}.gt.txt").write_text(
                fx["ground_truth"] + "\n", encoding="utf-8"
            )
        manifest.append(
            {
                "name": fx["name"],
                "description": fx["description"],
                "variants": variants,
                "pages": len(fx["pages"]),
            }
        )
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if args.all and not have_rl:
        print(
            "reportlab not installed: only scan / watermark variants were written (uv run --with reportlab ...)."
        )
    print(f"{len(manifest)} fixtures written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
