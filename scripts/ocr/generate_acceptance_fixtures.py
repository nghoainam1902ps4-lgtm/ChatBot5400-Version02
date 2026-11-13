#!/usr/bin/env python3
"""Generate the synthetic acceptance fixtures used by tests/test_ocr_integration.py.

All content is FICTIONAL (no real organisation, person or banking data). Output
is committed under tests/fixtures/ocr/ so the acceptance run on a deployment
machine needs no font or reportlab. Regenerate with:

    uv run --with reportlab python scripts/ocr/generate_acceptance_fixtures.py --out tests/fixtures/ocr

Each fixture has structured ground truth in manifest.json:
  text_layer      per page: True = PDF text layer, False = image only (OCR needed)
  ordered_phrases must appear in this order in the Markdown (reading order)
  key_fields      amounts / dates / document numbers that must be exact
  ground_truth    full text, for CER/WER
  tables          expected table shape, row contents and the merged header cell
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from generate_samples import (
    BOLD_CANDIDATES,
    CONG_VAN_LINES,
    FONT_CANDIDATES,
    KEY_FIELDS,
    _font,
)
from PIL import Image, ImageDraw

DPI = 150
PAGE_W, PAGE_H = int(8.27 * DPI), int(11.69 * DPI)  # A4

TABLE_TITLE = "BẢNG KÊ CHI TIẾT KHOẢN MỤC MẪU"
# Two-level header: STT / Nội dung / Ngày span 2 rows; "Số tiền (đồng)" spans 2 columns.
TABLE_ROWS = [
    ["1", "Phí dịch vụ mẫu", "2.500.000", "1.200.000", "05/01/2024"],
    ["2", "Lãi suất giả định", "18.750.000", "9.375.000", "12/02/2024"],
    ["3", "Khoản vay thử nghiệm", "350.000.000", "175.000.000", "20/03/2024"],
    ["4", "Tổng cộng", "371.250.000", "185.575.000", "31/03/2024"],
]
TABLE_EXPECT = {
    "cols": 5,
    "rows_min": 5,  # 4 data rows + >= 1 header row
    "rows_max": 6,  # 4 data rows + 2 header rows
    "merged_header": "Số tiền (đồng)",
    "sub_headers": ["Kỳ 1", "Kỳ 2"],
    "row_checks": [{"label": r[1], "cells": r[2:]} for r in TABLE_ROWS],
}
TABLE_FIELDS = {
    "amounts": [c for r in TABLE_ROWS for c in r[2:4]],
    "dates": [r[4] for r in TABLE_ROWS],
    "doc_numbers": [],
}
TABLE_TEXT = "\n".join(
    [TABLE_TITLE, "STT Nội dung Số tiền (đồng) Ngày", "Kỳ 1 Kỳ 2"]
    + [" ".join(r) for r in TABLE_ROWS]
)
CV_TEXT = "\n".join(CONG_VAN_LINES)
CV_ORDER = [
    "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
    "QUYẾT ĐỊNH",
    "Điều 1.",
    "Điều 2.",
    "Điều 3.",
]


def render_cong_van() -> Image.Image:
    font, bold = _font(FONT_CANDIDATES, 22), _font(BOLD_CANDIDATES, 22)
    img = Image.new("L", (PAGE_W, PAGE_H), 255)
    d = ImageDraw.Draw(img)
    y = 90
    for i, line in enumerate(CONG_VAN_LINES):
        d.text((80, y), line, font=bold if i in (0, 4) else font, fill=0)
        y += 44
    return img


def render_merged_table() -> Image.Image:
    font, bold = _font(FONT_CANDIDATES, 20), _font(BOLD_CANDIDATES, 20)
    img = Image.new("L", (PAGE_W, PAGE_H), 255)
    d = ImageDraw.Draw(img)
    d.text((80, 80), TABLE_TITLE, font=bold, fill=0)
    x = [70, 140, 470, 690, 910, 1130]  # 5 columns
    top, h = 150, 56
    rows = 6
    y = [top + i * h for i in range(rows + 1)]

    def line(x0, y0, x1, y1):
        d.line([(x0, y0), (x1, y1)], fill=0, width=2)

    # outer box + horizontal lines (header row 0/1 boundary only under "Số tiền")
    line(x[0], y[0], x[5], y[0])
    line(x[2], y[1], x[4], y[1])
    for r in range(2, rows + 1):
        line(x[0], y[r], x[5], y[r])
    # vertical lines; the line between Kỳ 1/Kỳ 2 starts at the second header row
    for c in (0, 1, 2, 4, 5):
        line(x[c], y[0], x[c], y[rows])
    line(x[3], y[1], x[3], y[rows])

    def cell(c0, c1, r0, r1, text, f):
        w = d.textlength(text, font=f)
        d.text(
            ((x[c0] + x[c1]) / 2 - w / 2, (y[r0] + y[r1]) / 2 - 12),
            text,
            font=f,
            fill=0,
        )

    cell(0, 1, 0, 2, "STT", bold)
    cell(1, 2, 0, 2, "Nội dung", bold)
    cell(2, 4, 0, 1, "Số tiền (đồng)", bold)
    cell(2, 3, 1, 2, "Kỳ 1", bold)
    cell(3, 4, 1, 2, "Kỳ 2", bold)
    cell(4, 5, 0, 2, "Ngày", bold)
    for i, row in enumerate(TABLE_ROWS):
        for c, text in enumerate(row):
            cell(c, c + 1, 2 + i, 3 + i, text, font)
    return img


def save_scan(images: list[Image.Image], path: Path) -> None:
    rgb = [im.convert("RGB") for im in images]
    rgb[0].save(path, save_all=True, append_images=rgb[1:], resolution=DPI)


def _rl() -> dict:
    """reportlab objects (optional dependency, only needed to regenerate fixtures)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    reg = next(p for p in FONT_CANDIDATES if Path(p).exists())
    bold = next(p for p in BOLD_CANDIDATES if Path(p).exists())
    pdfmetrics.registerFont(TTFont("VN", reg))
    pdfmetrics.registerFont(TTFont("VNB", bold))
    return {
        "colors": colors,
        "A4": A4,
        "ParagraphStyle": ParagraphStyle,
        "ImageReader": ImageReader,
        "Paragraph": Paragraph,
        "SimpleDocTemplate": SimpleDocTemplate,
        "Spacer": Spacer,
        "Table": Table,
        "TableStyle": TableStyle,
    }


def text_cong_van(path: Path) -> None:
    rl = _rl()
    st = rl["ParagraphStyle"]("n", fontName="VN", fontSize=11, leading=16)
    hb = rl["ParagraphStyle"]("h", fontName="VNB", fontSize=13, leading=18)
    story = [
        rl["Paragraph"](line, hb if i in (0, 4) else st)
        for i, line in enumerate(CONG_VAN_LINES)
    ]
    rl["SimpleDocTemplate"](str(path), pagesize=rl["A4"]).build(story)


def _rl_table(rl):
    data = [
        ["STT", "Nội dung", "Số tiền (đồng)", "", "Ngày"],
        ["", "", "Kỳ 1", "Kỳ 2", ""],
    ] + TABLE_ROWS
    t = rl["Table"](data, colWidths=[35, 160, 90, 90, 80])
    t.setStyle(
        rl["TableStyle"](
            [
                ("FONTNAME", (0, 0), (-1, -1), "VN"),
                ("FONTNAME", (0, 0), (-1, 1), "VNB"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.8, rl["colors"].black),
                ("SPAN", (0, 0), (0, 1)),
                ("SPAN", (1, 0), (1, 1)),
                ("SPAN", (2, 0), (3, 0)),
                ("SPAN", (4, 0), (4, 1)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, 1), "CENTER"),
            ]
        )
    )
    return t


def text_table(path: Path) -> None:
    rl = _rl()
    hb = rl["ParagraphStyle"]("h", fontName="VNB", fontSize=13, leading=18)
    rl["SimpleDocTemplate"](str(path), pagesize=rl["A4"]).build(
        [rl["Paragraph"](TABLE_TITLE, hb), rl["Spacer"](1, 12), _rl_table(rl)]
    )


def mixed(path: Path, scan: Image.Image) -> None:
    """Page 1: text layer (first 6 lines of the công văn); page 2: image-only table."""
    rl = _rl()
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=rl["A4"])
    c.setFont("VN", 12)
    y = rl["A4"][1] - 60
    for line in CONG_VAN_LINES[:6]:
        c.drawString(50, y, line)
        y -= 22
    c.showPage()
    w, h = rl["A4"]
    c.drawImage(rl["ImageReader"](scan.convert("RGB")), 0, 0, width=w, height=h)
    c.showPage()
    c.save()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    out = ap.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    cv, table = render_cong_van(), render_merged_table()
    m: dict[str, dict] = {}

    def add(name, kind, text_layer, phrases, fields, gt, tables=(), rotated=False):
        m[name] = {
            "file": f"{name}.pdf",
            "kind": kind,
            "pages": len(text_layer),
            "text_layer": text_layer,
            "ordered_phrases": phrases,
            "key_fields": fields,
            "ground_truth": gt,
            "tables": list(tables),
            "rotated": rotated,
        }

    save_scan([cv], out / "vb_scan.pdf")
    add("vb_scan", "scanned_text", [False], CV_ORDER, KEY_FIELDS, CV_TEXT)
    save_scan([table], out / "bang_gop_scan.pdf")
    add(
        "bang_gop_scan",
        "scanned_table_merged",
        [False],
        [TABLE_TITLE],
        TABLE_FIELDS,
        TABLE_TEXT,
        [TABLE_EXPECT],
    )
    save_scan([cv, table], out / "nhieu_trang_scan.pdf")
    merged = {k: KEY_FIELDS[k] + TABLE_FIELDS[k] for k in KEY_FIELDS}
    add(
        "nhieu_trang_scan",
        "scanned_multipage",
        [False, False],
        CV_ORDER + [TABLE_TITLE],
        merged,
        CV_TEXT + "\n" + TABLE_TEXT,
        [TABLE_EXPECT],
    )
    save_scan([cv.rotate(90, expand=True, fillcolor=255)], out / "vb_xoay_scan.pdf")
    add(
        "vb_xoay_scan",
        "scanned_rotated",
        [False],
        CV_ORDER,
        KEY_FIELDS,
        CV_TEXT,
        rotated=True,
    )
    text_cong_van(out / "vb_text.pdf")
    add("vb_text", "text_layer", [True], CV_ORDER, KEY_FIELDS, CV_TEXT)
    text_table(out / "bang_gop_text.pdf")
    add(
        "bang_gop_text",
        "text_layer_table_merged",
        [True],
        [TABLE_TITLE],
        TABLE_FIELDS,
        TABLE_TEXT,
        [TABLE_EXPECT],
    )
    mixed(out / "hon_hop.pdf", table)
    mixed_fields = {
        "doc_numbers": ["1234/2024/QĐ-MẪU"],
        "dates": ["15 tháng 03 năm 2024"] + TABLE_FIELDS["dates"],
        "amounts": TABLE_FIELDS["amounts"],
    }
    add(
        "hon_hop",
        "mixed_text_and_scan",
        [True, False],
        CV_ORDER[:2] + [TABLE_TITLE],
        mixed_fields,
        "\n".join(CONG_VAN_LINES[:6]) + "\n" + TABLE_TEXT,
        [TABLE_EXPECT],
    )
    (out / "manifest.json").write_text(
        json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {len(m)} fixtures to {out}")


if __name__ == "__main__":
    main()
