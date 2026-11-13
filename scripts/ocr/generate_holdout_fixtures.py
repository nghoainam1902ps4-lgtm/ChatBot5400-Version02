"""Synthetic HOLDOUT set for OCR quality evaluation (Phase 8C).

Independent of tests/fixtures/ocr (the set used for tuning): other wording,
serif fonts, another table shape, other amounts / dates / numbers, other page
sizes, other rotations and a degraded scan. Entirely fictional — no real
bank document. It is used ONCE to evaluate an already chosen configuration,
never to tune one.

    uv run python scripts/ocr/generate_holdout_fixtures.py --out <dir>

The manifest has the same shape as tests/fixtures/ocr/manifest.json.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SERIF = [
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
]
SERIF_BOLD = [
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
]
NOTO = ["/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf", *SERIF]
NOTO_BOLD = ["/usr/share/fonts/truetype/noto/NotoSerif-Bold.ttf", *SERIF_BOLD]

LETTER_LINES = [
    "ỦY BAN NHÂN DÂN XÃ THỬ NGHIỆM",
    "Số: 57/TB-UBND",
    "Thử Nghiệm, ngày 09 tháng 11 năm 2025",
    "THÔNG BÁO",
    "Về việc tổ chức buổi tập huấn nghiệp vụ lưu trữ hồ sơ",
    "Kính gửi: Các phòng, ban chuyên môn trực thuộc",
    "Căn cứ Kế hoạch số 842/KH-VP ngày 21/10/2025 của Văn phòng;",
    "Ủy ban thông báo lịch tập huấn như sau:",
    "1. Thời gian: 08 giờ 30 phút, ngày 24/11/2025.",
    "2. Địa điểm: Hội trường tầng 2, trụ sở Ủy ban.",
    "3. Kinh phí dự kiến: 46.800.000 đồng, trích từ nguồn đào tạo.",
    "4. Mỗi đơn vị cử 03 cán bộ tham dự đầy đủ, đúng giờ.",
    "Đề nghị thủ trưởng các đơn vị nghiêm túc triển khai thực hiện.",
    "Nơi nhận: Như trên; Lưu: VT.",
    "TM. ỦY BAN NHÂN DÂN",
]
LETTER_BOLD = (0, 3, 14)
LETTER_FIELDS = {
    "amounts": ["46.800.000"],
    "dates": ["09 tháng 11 năm 2025", "21/10/2025", "24/11/2025"],
    "doc_numbers": ["57/TB-UBND", "842/KH-VP"],
}
LETTER_ORDER = [
    "ỦY BAN NHÂN DÂN XÃ THỬ NGHIỆM",
    "THÔNG BÁO",
    "1. Thời gian",
    "2. Địa điểm",
    "3. Kinh phí",
]

TABLE_TITLE = "BÁO CÁO THU CHI QUỸ THÁNG 10"
TABLE_HEADER = ["Mã", "Diễn giải", "Thu (đồng)", "Chi (đồng)"]
TABLE_ROWS = [
    ["A01", "Học phí lớp buổi tối", "64.300.000", "0"],
    ["A02", "Thuê hội trường", "0", "7.450.000"],
    ["B07", "Mua văn phòng phẩm", "0", "3.286.500"],
    ["B11", "Tài trợ giả định", "120.000.000", "0"],
    ["C03", "Bồi dưỡng giảng viên", "0", "28.900.000"],
    ["D20", "Lãi tiền gửi", "815.700", "0"],
    ["", "Cộng phát sinh", "185.115.700", "39.636.500"],
]
TABLE_FIELDS = {
    "amounts": sorted(
        {c for r in TABLE_ROWS for c in r[2:] if c != "0"}, key=lambda s: (len(s), s)
    ),
    "dates": [],
    "doc_numbers": [],
}
TABLE_EXPECT = {
    "cols": 4,
    "rows_min": 8,
    "rows_max": 8,
    "merged_header": None,
    "sub_headers": [],
    "row_checks": [{"label": r[1], "cells": r[2:]} for r in TABLE_ROWS],
}
LETTER_TEXT = "\n".join(LETTER_LINES)
TABLE_TEXT = "\n".join(
    [TABLE_TITLE, " ".join(TABLE_HEADER)]
    + [" ".join(c for c in r if c) for r in TABLE_ROWS]
)


def _font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise SystemExit("No serif TrueType font found (install fonts-liberation).")


def render_letter(
    dpi: int, page_in: tuple[float, float], pt: float, fonts
) -> Image.Image:
    w, h = int(page_in[0] * dpi), int(page_in[1] * dpi)
    size = round(pt * dpi / 72)
    font, bold = _font(fonts[0], size), _font(fonts[1], size)
    img = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(img)
    y = int(0.7 * dpi)
    for i, line in enumerate(LETTER_LINES):
        d.text(
            (int(0.6 * dpi), y), line, font=bold if i in LETTER_BOLD else font, fill=0
        )
        y += int(size * 1.75)
    return img


def render_table(
    dpi: int, page_in: tuple[float, float], pt: float, fonts
) -> Image.Image:
    w, h = int(page_in[0] * dpi), int(page_in[1] * dpi)
    size = round(pt * dpi / 72)
    font, bold = _font(fonts[0], size), _font(fonts[1], size)
    img = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(img)
    left = int(0.6 * dpi)
    d.text((left, int(0.6 * dpi)), TABLE_TITLE, font=bold, fill=0)
    usable = w - 2 * left
    shares = [0.10, 0.44, 0.23, 0.23]
    xs = [left]
    for s in shares:
        xs.append(xs[-1] + int(usable * s))
    top, row_h = int(1.1 * dpi), int(size * 2.4)
    rows = [TABLE_HEADER] + TABLE_ROWS
    lw = max(1, round(dpi / 100))
    for r in range(len(rows) + 1):
        d.line([(xs[0], top + r * row_h), (xs[-1], top + r * row_h)], fill=0, width=lw)
    for x in xs:
        d.line([(x, top), (x, top + len(rows) * row_h)], fill=0, width=lw)
    for r, row in enumerate(rows):
        f = bold if r in (0, len(rows) - 1) else font
        for c, text in enumerate(row):
            tw = d.textlength(text, font=f)
            ty = top + r * row_h + (row_h - size) // 2 - size // 8
            if c >= 2 and r > 0:  # amounts right-aligned
                tx = xs[c + 1] - tw - int(0.08 * dpi)
            elif c == 1 and r > 0:
                tx = xs[c] + int(0.08 * dpi)
            else:
                tx = (xs[c] + xs[c + 1]) / 2 - tw / 2
            d.text((tx, ty), text, font=f, fill=0)
    return img


def degrade(img: Image.Image, seed: int = 7) -> Image.Image:
    """A poor photocopy: slight skew, blur, grey background, speckle."""
    rnd = random.Random(seed)
    out = img.rotate(0.6, resample=Image.Resampling.BICUBIC, fillcolor=255)
    out = out.filter(ImageFilter.GaussianBlur(0.8))
    out = out.point(lambda v: int(40 + v * 0.78))
    px = out.load()
    assert px is not None
    for _ in range(out.width * out.height // 250):
        x, y = rnd.randrange(out.width), rnd.randrange(out.height)
        px[x, y] = rnd.choice((30, 60, 235))
    return out


def save_scan(
    images: list[Image.Image], path: Path, dpi: int, quality: int = 75
) -> None:
    rgb = [im.convert("RGB") for im in images]
    rgb[0].save(
        path, save_all=True, append_images=rgb[1:], resolution=dpi, quality=quality
    )


def entry(file, kind, pages, order, fields, text, tables, rotated):
    return {
        "file": file,
        "kind": kind,
        "pages": pages,
        "text_layer": [False] * pages,
        "ordered_phrases": order,
        "key_fields": fields,
        "ground_truth": text,
        "tables": tables,
        "rotated": rotated,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    out = ap.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    a4, a5, letter_l = (8.27, 11.69), (5.83, 8.27), (11.0, 8.5)
    serif, noto = (SERIF, SERIF_BOLD), (NOTO, NOTO_BOLD)
    manifest: dict[str, dict] = {}

    def add(name, images, dpi, kind, order, fields, text, tables, rotated, quality=75):
        save_scan(images, out / f"{name}.pdf", dpi, quality)
        manifest[name] = entry(
            f"{name}.pdf", kind, len(images), order, fields, text, tables, rotated
        )

    both = {k: LETTER_FIELDS[k] + TABLE_FIELDS[k] for k in LETTER_FIELDS}
    letter200 = render_letter(200, a4, 12, serif)
    table200 = render_table(200, a4, 11, serif)
    add(
        "ho_letter_200",
        [letter200],
        200,
        "letter",
        LETTER_ORDER,
        LETTER_FIELDS,
        LETTER_TEXT,
        [],
        False,
    )
    add(
        "ho_table_200",
        [table200],
        200,
        "table",
        [TABLE_TITLE],
        TABLE_FIELDS,
        TABLE_TEXT,
        [TABLE_EXPECT],
        False,
    )
    add(
        "ho_letter_150",
        [render_letter(150, a4, 12, noto)],
        150,
        "letter",
        LETTER_ORDER,
        LETTER_FIELDS,
        LETTER_TEXT,
        [],
        False,
    )
    add(
        "ho_table_150",
        [render_table(150, a4, 11, noto)],
        150,
        "table",
        [TABLE_TITLE],
        TABLE_FIELDS,
        TABLE_TEXT,
        [TABLE_EXPECT],
        False,
    )
    add(
        "ho_letter_a5_300",
        [render_letter(300, a5, 9, serif)],
        300,
        "letter_a5",
        LETTER_ORDER,
        LETTER_FIELDS,
        LETTER_TEXT,
        [],
        False,
    )
    add(
        "ho_table_landscape_200",
        [render_table(200, letter_l, 12, noto)],
        200,
        "table_landscape_page",
        [TABLE_TITLE],
        TABLE_FIELDS,
        TABLE_TEXT,
        [TABLE_EXPECT],
        False,
    )
    add(
        "ho_letter_lowq_150",
        [degrade(render_letter(150, a4, 12, serif))],
        150,
        "letter_low_quality",
        LETTER_ORDER,
        LETTER_FIELDS,
        LETTER_TEXT,
        [],
        False,
        quality=40,
    )
    for angle in (90, 180, 270):
        add(
            f"ho_letter_rot{angle}_200",
            [letter200.rotate(angle, expand=True, fillcolor=255)],
            200,
            "letter_rotated",
            LETTER_ORDER,
            LETTER_FIELDS,
            LETTER_TEXT,
            [],
            True,
        )
    add(
        "ho_table_rot180_200",
        [table200.rotate(180, expand=True, fillcolor=255)],
        200,
        "table_rotated",
        [TABLE_TITLE],
        TABLE_FIELDS,
        TABLE_TEXT,
        [TABLE_EXPECT],
        True,
    )
    add(
        "ho_table_rot270_200",
        [table200.rotate(270, expand=True, fillcolor=255)],
        200,
        "table_rotated",
        [TABLE_TITLE],
        TABLE_FIELDS,
        TABLE_TEXT,
        [TABLE_EXPECT],
        True,
    )
    add(
        "ho_mixed_rot_200",
        [
            letter200,
            table200.rotate(90, expand=True, fillcolor=255),
            letter200.rotate(180, expand=True, fillcolor=255),
        ],
        200,
        "multi_page_mixed_orientation",
        LETTER_ORDER,
        both,
        LETTER_TEXT + "\n" + TABLE_TEXT + "\n" + LETTER_TEXT,
        [TABLE_EXPECT],
        True,
    )
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1)
    )
    print(f"wrote {len(manifest)} holdout documents to {out}")


if __name__ == "__main__":
    main()
