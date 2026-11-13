#!/usr/bin/env python3
"""Generate synthetic, NON-SENSITIVE Vietnamese OCR samples with ground truth.

All text below is fictional (made-up organisation, numbers, people). It is used
by the OCR integration tests and the benchmark (docs/ocr/OCR_BENCHMARK.md) so
results are reproducible without ever touching real banking documents.

Usage (dev machine / CI, needs a font with Vietnamese glyphs, e.g. DejaVu Sans):

    uv run --with reportlab python scripts/ocr/generate_samples.py --out ./data/ocr-samples

reportlab is only needed for the text-native PDF sample; without it that sample
is skipped. Nothing here is a runtime dependency of the application.

Outputs per sample: <name>.(png|pdf) + <name>.gt.txt (full ground truth), and a
manifest.json listing key fields (amounts, dates, document numbers) to score.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

# --- Fictional content -------------------------------------------------------

CONG_VAN_LINES = [
    "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM",
    "Độc lập - Tự do - Hạnh phúc",
    "Số: 1234/2024/QĐ-MẪU",
    "Hà Nội, ngày 15 tháng 03 năm 2024",
    "QUYẾT ĐỊNH",
    "Về việc ban hành quy định mẫu phục vụ kiểm thử nhận dạng ký tự",
    "Căn cứ Thông tư số 39/2016/TT-MẪU ngày 30/12/2016;",
    "Xét đề nghị của Trưởng phòng Kiểm thử Dữ liệu Giả lập,",
    "Điều 1. Ban hành kèm theo Quyết định này Quy định mẫu.",
    "Điều 2. Hạn mức thử nghiệm là 1.250.000.000 đồng.",
    "Điều 3. Quyết định có hiệu lực kể từ ngày 01/04/2024.",
    "Nơi nhận: Như Điều 3; Lưu: VT, KTDL.",
]

TABLE_HEADER = ["STT", "Nội dung", "Số tiền (đồng)", "Ngày"]
TABLE_ROWS = [
    ["1", "Phí dịch vụ mẫu", "2.500.000", "05/01/2024"],
    ["2", "Lãi suất giả định", "18.750.000", "12/02/2024"],
    ["3", "Khoản vay thử nghiệm", "350.000.000", "20/03/2024"],
    ["4", "Tổng cộng", "371.250.000", "31/03/2024"],
]

KEY_FIELDS = {
    "doc_numbers": ["1234/2024/QĐ-MẪU", "39/2016/TT-MẪU"],
    "dates": ["15 tháng 03 năm 2024", "30/12/2016", "01/04/2024"],
    "amounts": ["1.250.000.000"],
}
TABLE_KEY_FIELDS = {
    "amounts": ["2.500.000", "18.750.000", "350.000.000", "371.250.000"],
    "dates": ["05/01/2024", "12/02/2024", "20/03/2024", "31/03/2024"],
    "doc_numbers": [],
}


def _font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise SystemExit(
        "No TrueType font with Vietnamese glyphs found (install fonts-dejavu-core)."
    )


def render_lines(lines: list[str], width: int = 1654, size: int = 34) -> Image.Image:
    """Render text lines on an A4-ish page at ~200 DPI (1654 px wide)."""
    font = _font(FONT_CANDIDATES, size)
    bold = _font(BOLD_CANDIDATES, size)
    line_h = int(size * 1.9)
    height = max(2339, 160 + line_h * len(lines))
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)
    y = 120
    for i, line in enumerate(lines):
        f = bold if i in (0, 4) else font
        draw.text((120, y), line, font=f, fill=0)
        y += line_h
    return img


def render_table() -> Image.Image:
    font = _font(FONT_CANDIDATES, 32)
    bold = _font(BOLD_CANDIDATES, 32)
    width, height = 1654, 1100
    img = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(img)
    draw.text((120, 100), "BẢNG KÊ CHI TIẾT KHOẢN MỤC MẪU", font=bold, fill=0)
    cols = [120, 260, 900, 1260, 1540]
    top, row_h = 220, 90
    rows = [TABLE_HEADER] + TABLE_ROWS
    for r, row in enumerate(rows):
        y0 = top + r * row_h
        for c, cell in enumerate(row):
            draw.text(
                (cols[c] + 15, y0 + 25), cell, font=bold if r == 0 else font, fill=0
            )
    for r in range(len(rows) + 1):
        y = top + r * row_h
        draw.line([(cols[0], y), (cols[-1], y)], fill=0, width=3)
    for x in cols:
        draw.line([(x, top), (x, top + row_h * len(rows))], fill=0, width=3)
    return img


def degrade(img: Image.Image, seed: int = 7) -> Image.Image:
    """Simulate a low-quality scan: downsample, blur, speckle noise."""
    rnd = random.Random(seed)
    small = img.resize((img.width // 2, img.height // 2), Image.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(0.9))
    px = small.load()
    for _ in range(small.width * small.height // 60):
        x, y = rnd.randrange(small.width), rnd.randrange(small.height)
        px[x, y] = rnd.choice((0, 90, 200))
    return small.resize(img.size, Image.BILINEAR)


def save_pdf(images: list[Image.Image], path: Path, dpi: int = 200) -> None:
    rgb = [im.convert("RGB") for im in images]
    rgb[0].save(path, save_all=True, append_images=rgb[1:], resolution=dpi)


def text_native_pdf(path: Path, lines: list[str]) -> bool:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen import canvas
    except ImportError:
        return False
    font_path = next((p for p in FONT_CANDIDATES if Path(p).exists()), None)
    if not font_path:
        return False
    pdfmetrics.registerFont(TTFont("VNSans", font_path))
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("VNSans", 12)
    y = A4[1] - 60
    for line in lines:
        c.drawString(50, y, line)
        y -= 22
    c.showPage()
    c.save()
    return True


def mixed_pdf(path: Path, lines: list[str], scan: Image.Image) -> bool:
    """Page 1: native text; page 2: an embedded scan image (no text layer)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen import canvas
    except ImportError:
        return False
    font_path = next((p for p in FONT_CANDIDATES if Path(p).exists()), None)
    if not font_path:
        return False
    pdfmetrics.registerFont(TTFont("VNSans", font_path))
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont("VNSans", 12)
    y = A4[1] - 60
    for line in lines[:6]:
        c.drawString(50, y, line)
        y -= 22
    c.showPage()
    w, h = A4
    c.drawImage(ImageReader(scan.convert("RGB")), 0, 0, width=w, height=h)
    c.showPage()
    c.save()
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument(
        "--asset-only",
        action="store_true",
        help="Only (re)generate the small built-in test image used by the OCR Engine Manager.",
    )
    args = ap.parse_args()
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)

    if args.asset_only:
        lines = CONG_VAN_LINES[:6]
        img = render_lines(lines, width=1400, size=36)
        img = img.crop((0, 0, img.width, 120 + int(36 * 1.9) * len(lines) + 60))
        img.save(out / "sample_vi.png", optimize=True)
        (out / "sample_vi.gt.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"wrote {out / 'sample_vi.png'}")
        return

    manifest: dict[str, dict] = {}
    gt_cv = "\n".join(CONG_VAN_LINES)
    gt_tab = "\n".join(
        ["BẢNG KÊ CHI TIẾT KHOẢN MỤC MẪU"]
        + [" ".join(r) for r in [TABLE_HEADER] + TABLE_ROWS]
    )

    def add(
        name: str, fname: str, gt: str, fields: dict, kind: str, pages: int
    ) -> None:
        (out / f"{name}.gt.txt").write_text(gt + "\n", encoding="utf-8")
        manifest[name] = {
            "file": fname,
            "kind": kind,
            "pages": pages,
            "key_fields": fields,
        }

    page = render_lines(CONG_VAN_LINES)
    table = render_table()

    page.save(out / "scan_cong_van.png")
    add("scan_cong_van", "scan_cong_van.png", gt_cv, KEY_FIELDS, "image", 1)

    save_pdf([page], out / "scan_cong_van.pdf")
    add("scan_cong_van_pdf", "scan_cong_van.pdf", gt_cv, KEY_FIELDS, "scanned_pdf", 1)

    save_pdf([table], out / "scan_bang_bieu.pdf")
    add(
        "scan_bang_bieu",
        "scan_bang_bieu.pdf",
        gt_tab,
        TABLE_KEY_FIELDS,
        "scanned_pdf_table",
        1,
    )

    save_pdf([page, table], out / "scan_nhieu_trang.pdf")
    merged_fields = {k: KEY_FIELDS[k] + TABLE_KEY_FIELDS[k] for k in KEY_FIELDS}
    add(
        "scan_nhieu_trang",
        "scan_nhieu_trang.pdf",
        gt_cv + "\n" + gt_tab,
        merged_fields,
        "scanned_pdf_multipage",
        2,
    )

    save_pdf([degrade(page)], out / "scan_chat_luong_thap.pdf")
    add(
        "scan_chat_luong_thap",
        "scan_chat_luong_thap.pdf",
        gt_cv,
        KEY_FIELDS,
        "scanned_pdf_low_quality",
        1,
    )

    save_pdf([page.rotate(90, expand=True, fillcolor=255)], out / "scan_xoay.pdf")
    add("scan_xoay", "scan_xoay.pdf", gt_cv, KEY_FIELDS, "scanned_pdf_rotated", 1)

    if text_native_pdf(out / "text_native.pdf", CONG_VAN_LINES):
        add("text_native", "text_native.pdf", gt_cv, KEY_FIELDS, "text_pdf", 1)
    if mixed_pdf(out / "hon_hop.pdf", CONG_VAN_LINES, table):
        gt_mixed = "\n".join(CONG_VAN_LINES[:6]) + "\n" + gt_tab
        mixed_fields = {
            "doc_numbers": ["1234/2024/QĐ-MẪU"],
            "dates": ["15 tháng 03 năm 2024"] + TABLE_KEY_FIELDS["dates"],
            "amounts": TABLE_KEY_FIELDS["amounts"],
        }
        add("hon_hop", "hon_hop.pdf", gt_mixed, mixed_fields, "mixed_pdf", 2)

    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {len(manifest)} samples to {out}")


if __name__ == "__main__":
    main()
