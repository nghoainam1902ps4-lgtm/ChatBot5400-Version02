"""Synthetic PDFs for the "visible text box over a scan" problem (Phase 10G, D-33).

Docling 2.129 drops every OCR cell whose bounding box touches the axis-aligned
box of a VISIBLE PDF text cell. One diagonal watermark line therefore claims
most of a scanned page and the recognised text under it is discarded. These
fixtures reproduce that structure — and the look-alikes that must NOT be
treated the same way — without any real document:

    scan image (several resolutions, grey JPEG or 1-bit)
    + hidden OCR text layer (text render mode 3)
    + visible overlays: diagonal / tiled / small watermark, header, footer,
      signature block, vertical margin text, a visible text layer
    born-digital text pages, with and without a watermark or a background image
    mixed and multi-page documents

Everything is fictional (the page text comes from
``generate_agri_benchmark_fixtures.py``); watermark strings are neutral
placeholders. The PDF is written by hand (no reportlab), so the same builder
serves the unit tests.

    uv run python scripts/ocr/generate_overlay_fixtures.py --out <dir>

Output: <dir>/<case>.pdf and <dir>/manifest.json (ground truth per page, the
expected decision of the automatic full-page rule and what each case is for).
"""

from __future__ import annotations

import argparse
import io
import json
import math
import sys
import unicodedata
import zlib
from dataclasses import dataclass, field, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

A4 = (595.28, 841.89)
WATERMARK = "MAU WATERMARK 0123"


# --- a minimal PDF writer --------------------------------------------------------


@dataclass
class Text:
    """One text object. ``angle`` is counter-clockwise degrees about (x, y)."""

    text: str
    x: float
    y: float
    size: float = 12.0
    angle: float = 0.0
    invisible: bool = False  # text render mode 3 (a hidden OCR layer)
    gray: float = 0.0
    alpha: float = 1.0
    in_form: bool = False  # draw through a Form XObject (rotation in its /Matrix)


@dataclass
class Page:
    size: tuple[float, float] = A4
    image: bytes | None = None  # encoded sample data
    image_filter: str = "DCTDecode"  # or FlateDecode (1-bit)
    image_px: tuple[int, int] = (0, 0)
    image_bits: int = 8
    # where the image is placed, PDF points (left, bottom, right, top)
    image_rect: tuple[float, float, float, float] | None = None
    texts: list[Text] = field(default_factory=list)


def _esc(text: str) -> bytes:
    raw = text.encode("latin-1", "replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _num(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".")


def _text_ops(t: Text, rotate: bool = True) -> bytes:
    a = math.radians(t.angle if rotate else 0.0)
    c, s = math.cos(a), math.sin(a)
    x, y = (t.x, t.y) if rotate else (0.0, 0.0)
    parts = ["q"]
    if t.alpha < 1.0:
        parts.append(f"/GS{int(round(t.alpha * 100))} gs")
    parts.append(f"{_num(t.gray)} g")
    parts.append(
        f"BT /F1 {_num(t.size)} Tf {3 if t.invisible else 0} Tr "
        f"{_num(c)} {_num(s)} {_num(-s)} {_num(c)} {_num(x)} {_num(y)} Tm "
    )
    return " ".join(parts).encode() + b"(" + _esc(t.text) + b") Tj ET Q\n"


def build_pdf(pages: list[Page]) -> bytes:
    """Serialise ``pages`` into a small, valid PDF 1.4 file."""
    objs: list[bytes] = []

    def add(body: bytes) -> int:
        objs.append(body)
        return len(objs)

    def stream(entries: str, data: bytes) -> bytes:
        return (
            f"<< {entries} /Length {len(data)} >>\nstream\n".encode()
            + data
            + b"\nendstream"
        )

    catalog = add(b"")
    pages_obj = add(b"")
    font = add(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        b"/Encoding /WinAnsiEncoding >>"
    )
    kids: list[int] = []
    for page in pages:
        w, h = page.size
        alphas = sorted({int(round(t.alpha * 100)) for t in page.texts if t.alpha < 1})
        gstates = " ".join(
            f"/GS{a} << /Type /ExtGState /ca {a / 100} >>" for a in alphas
        )
        content = b""
        xobjects: list[str] = []
        if page.image is not None:
            pw, ph = page.image_px
            colour = "/DeviceGray"
            img = add(
                stream(
                    f"/Type /XObject /Subtype /Image /Width {pw} /Height {ph} "
                    f"/ColorSpace {colour} /BitsPerComponent {page.image_bits} "
                    f"/Filter /{page.image_filter}",
                    page.image,
                )
            )
            xobjects.append(f"/Im0 {img} 0 R")
            left, bottom, right, top = page.image_rect or (0.0, 0.0, w, h)
            content += (
                f"q {_num(right - left)} 0 0 {_num(top - bottom)} "
                f"{_num(left)} {_num(bottom)} cm /Im0 Do Q\n"
            ).encode()
        for i, t in enumerate(page.texts):
            if not t.in_form:
                content += _text_ops(t)
                continue
            a = math.radians(t.angle)
            c, s = math.cos(a), math.sin(a)
            res = f"/Font << /F1 {font} 0 R >>"
            if t.alpha < 1.0:
                ga = int(round(t.alpha * 100))
                res += (
                    f" /ExtGState << /GS{ga} << /Type /ExtGState /ca {ga / 100} >> >>"
                )
            form = add(
                stream(
                    f"/Type /XObject /Subtype /Form /BBox [0 -200 2000 200] "
                    f"/Matrix [{_num(c)} {_num(s)} {_num(-s)} {_num(c)} "
                    f"{_num(t.x)} {_num(t.y)}] /Resources << {res} >>",
                    _text_ops(t, rotate=False),
                )
            )
            xobjects.append(f"/Fm{i} {form} 0 R")
            content += f"/Fm{i} Do\n".encode()
        contents = add(stream("/Filter /FlateDecode", zlib.compress(content)))
        resources = f"/Font << /F1 {font} 0 R >>"
        if xobjects:
            resources += f" /XObject << {' '.join(xobjects)} >>"
        if gstates:
            resources += f" /ExtGState << {gstates} >>"
        kids.append(
            add(
                (
                    f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 {_num(w)} "
                    f"{_num(h)}] /Resources << {resources} >> /Contents {contents} 0 R >>"
                ).encode()
            )
        )
    objs[catalog - 1] = f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode()
    objs[pages_obj - 1] = (
        f"<< /Type /Pages /Count {len(kids)} /Kids "
        f"[{' '.join(f'{k} 0 R' for k in kids)}] >>"
    ).encode()

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, body in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{n} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objs) + 1} /Root {catalog} 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


# --- building blocks -----------------------------------------------------------


def ascii_fold(text: str) -> str:
    """What a poor embedded OCR layer looks like: Vietnamese without its marks."""
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def text_width(text: str, size: float) -> float:
    """Rough Helvetica width (enough to place overlays; not used for metrics)."""
    return 0.5 * size * len(text)


def jpeg(image, quality: int = 70) -> bytes:
    buf = io.BytesIO()
    image.convert("L").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def scan_page(image, bilevel: bool = False, size=A4, rect=None) -> Page:
    """A page whose content is one image (grey JPEG, or 1-bit like a fax scan)."""
    if bilevel:
        one = image.convert("L").point(lambda v: 255 if v > 150 else 0).convert("1")
        return Page(
            size=size,
            image=zlib.compress(one.tobytes()),
            image_filter="FlateDecode",
            image_px=one.size,
            image_bits=1,
            image_rect=rect,
        )
    return Page(size=size, image=jpeg(image), image_px=image.size, image_rect=rect)


def wrap(text: str, chars: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > chars:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines


def text_lines(
    text: str,
    size: float = 11.0,
    invisible: bool = False,
    top: float = 780.0,
    left: float = 72.0,
    chars: int = 86,
    max_lines: int = 48,
) -> list[Text]:
    """A column of horizontal lines (a hidden OCR layer, or born-digital text)."""
    out = []
    for i, line in enumerate(wrap(ascii_fold(text), chars)[:max_lines]):
        out.append(
            Text(line, left, top - i * size * 1.35, size=size, invisible=invisible)
        )
    return out


def watermark(
    angle: float = 55.0,
    size: float = 16.0,
    repeat: int = 6,
    centre: tuple[float, float] = (A4[0] / 2, A4[1] / 2),
    in_form: bool = False,
    text: str | None = None,
) -> Text:
    """One grey, half-transparent line through ``centre`` at ``angle``."""
    line = text if text is not None else "   ".join([WATERMARK] * repeat)
    half = text_width(line, size) / 2
    a = math.radians(angle)
    x = centre[0] - half * math.cos(a)
    y = centre[1] - half * math.sin(a)
    return Text(
        line, x, y, size=size, angle=angle, gray=0.5, alpha=0.5, in_form=in_form
    )


def tiled_watermark(
    angle: float = 45.0, size: float = 12.0, step: float = 130.0
) -> list[Text]:
    out = []
    y = 60.0
    while y < A4[1] - 40:
        x = 40.0
        while x < A4[0] - 60:
            out.append(
                Text(WATERMARK[:13], x, y, size=size, angle=angle, gray=0.5, alpha=0.5)
            )
            x += step
        y += step
    return out


def paragraph_watermark(
    angle: float = 30.0, size: float = 13.0, lines: int = 9, gap: float = 85.0
) -> list[Text]:
    """Several long, widely spaced tilted lines: a watermark with many characters."""
    out = []
    for i in range(lines):
        centre = (A4[0] / 2, A4[1] / 2 + (i - (lines - 1) / 2) * gap)
        text = "   ".join([f"{WATERMARK} {i:02d}"] * 3)
        out.append(watermark(angle, size=size, centre=centre, text=text))
    return out


def tilted(texts: list[Text], angle: float) -> list[Text]:
    """The same lines, each turned by ``angle`` (the text layer of a skewed scan)."""
    return [replace(t, angle=angle) for t in texts]


def header_footer(page_no: int = 1) -> list[Text]:
    return [
        Text("Van ban mau - luu hanh thu nghiem", 72, 815, size=8),
        Text(f"Trang {page_no}", 285, 22, size=9),
    ]


def signature_block() -> list[Text]:
    lines = [
        "Ky boi: He thong mau",
        "Ngay ky: 01/01/2026 08:00:00",
        "Ma xac thuc: 0000-1111-2222",
    ]
    return [Text(t, 380, 70 - 11 * i, size=8) for i, t in enumerate(lines)]


# --- the corpus ------------------------------------------------------------------


def corpus() -> list[dict]:
    """Every case: pages, the ground truth of each page and the expected verdict."""
    import generate_agri_benchmark_fixtures as legal

    rendered: dict[tuple[str, int], list] = {}

    def scan_images(doc: str, dpi: int):
        key = (doc, dpi)
        if key not in rendered:
            variant = legal.VARIANTS["scan_200"]
            # same degradation as the Phase 10E "scan_200" level, at ``dpi``
            pages = legal.render(legal.DOCS[doc], dpi)
            rendered[key] = [
                legal.degrade(p, (dpi, *variant[1:]), seed=500 + i)
                for i, p in enumerate(pages)
            ]
        return rendered[key]

    def gt(doc: str) -> str:
        return "\n".join(legal.plain_text(k, t) for k, t in legal.DOCS[doc]["blocks"])

    doc = "nghia_vu"  # fits on ONE page: the ground truth is exact
    truth = gt(doc)

    def scan(dpi=200, bilevel=False) -> Page:
        return scan_page(scan_images(doc, dpi)[0], bilevel=bilevel)

    def hidden() -> list[Text]:
        return text_lines(truth, size=11, invisible=True)

    cases: list[dict] = []

    def case(name, pages, truths, expect, why, group):
        cases.append(
            {
                "name": name,
                "pages": pages,
                "ground_truth": truths,
                "expect": expect,  # full_page | none | mixed
                "why": why,
                "group": group,
            }
        )

    def with_texts(page: Page, *groups) -> Page:
        for g in groups:
            page.texts.extend(g if isinstance(g, list) else [g])
        return page

    # --- the failing structure, at several resolutions ---------------------------
    for dpi in (150, 200, 300):
        case(
            f"scan{dpi}_hidden_wm55",
            [with_texts(scan(dpi), hidden(), watermark(55))],
            [truth],
            "full_page",
            f"scan {dpi} DPI + hidden OCR layer + 55 degree watermark",
            "positive",
        )
    case(
        "scan300_1bit_hidden_wm55",
        [with_texts(scan(300, bilevel=True), hidden(), watermark(55))],
        [truth],
        "full_page",
        "1-bit 300 DPI scan + hidden OCR layer + 55 degree watermark (the reported structure)",
        "positive",
    )
    case(
        "scan200_wm55",
        [with_texts(scan(), watermark(55))],
        [truth],
        "full_page",
        "scan + watermark, no hidden layer",
        "positive",
    )
    case(
        "scan200_hidden_wm55_form",
        [with_texts(scan(), hidden(), watermark(55, in_form=True))],
        [truth],
        "full_page",
        "watermark drawn through a Form XObject (rotation in the form matrix)",
        "positive",
    )
    case(
        "scan200_hidden_wm55_header_footer",
        [
            with_texts(
                scan(), hidden(), watermark(55), header_footer(), signature_block()
            )
        ],
        [truth],
        "full_page",
        "watermark plus ordinary header, footer and signature text",
        "positive",
    )
    case(
        "scan200_hidden_tiled45",
        [with_texts(scan(), hidden(), tiled_watermark(45))],
        [truth],
        "full_page",
        "many small 45 degree watermarks tiled over the page",
        "positive",
    )
    case(
        "scan200_hidden_wm30_paragraph",
        [with_texts(scan(), hidden(), paragraph_watermark(30))],
        [truth],
        "full_page",
        "watermark of nine long, widely spaced 30 degree lines (many characters)",
        "positive",
    )
    case(
        "scan200_wm30_paragraph",
        [with_texts(scan(), paragraph_watermark(30))],
        [truth],
        "full_page",
        "the same watermark on a scan without a hidden layer",
        "positive",
    )
    # --- angle sweep --------------------------------------------------------------
    for angle in (2, 5, 10, 15, 30, 45, 75, 85):
        case(
            f"scan200_hidden_wm{angle:02d}",
            [with_texts(scan(), hidden(), watermark(angle))],
            [truth],
            "measure",
            f"long watermark line at {angle} degrees",
            "angle",
        )
    case(
        "scan200_hidden_wm90",
        [with_texts(scan(), hidden(), watermark(90, repeat=4, centre=(40, A4[1] / 2)))],
        [truth],
        "none",
        "vertical (90 degree) margin text: its box is tight",
        "negative",
    )
    # --- coverage sweep: one 55 degree line of growing length ------------------------
    for repeat, size in ((1, 10), (1, 16), (2, 16), (3, 16), (4, 16), (8, 16)):
        case(
            f"scan200_hidden_wm55_len{repeat}x{size}",
            [with_texts(scan(), hidden(), watermark(55, size=size, repeat=repeat))],
            [truth],
            "measure",
            f"55 degree watermark, {repeat} repeat(s) at {size} pt",
            "coverage",
        )
    case(
        "scan200_hidden_small_corner_wm",
        [
            with_texts(
                scan(),
                hidden(),
                watermark(45, size=9, repeat=1, centre=(520, 60), text="BAN SAO"),
            )
        ],
        [truth],
        "none",
        "small diagonal stamp in a corner",
        "negative",
    )
    # --- horizontal large watermark (a different mechanism: tight box) ----------------
    case(
        "scan200_hidden_wm00_big",
        [
            with_texts(
                scan(), hidden(), watermark(0, size=60, repeat=1, text="MAU NOI BO")
            )
        ],
        [truth],
        "none",
        "large horizontal watermark: tight box, limited loss, NOT covered by the rule",
        "limitation",
    )
    # --- look-alikes that must stay as they are ---------------------------------------
    for dpi in (150, 200, 300):
        case(f"scan{dpi}_only", [scan(dpi)], [truth], "none", "plain scan", "negative")
    case(
        "scan200_hidden",
        [with_texts(scan(), hidden())],
        [truth],
        "none",
        "scan + hidden OCR layer, no watermark",
        "negative",
    )
    case(
        "scan200_hidden_header_footer",
        [with_texts(scan(), hidden(), header_footer(), signature_block())],
        [truth],
        "none",
        "scan + hidden layer + ordinary header / footer / signature text",
        "negative",
    )
    digital = text_lines(truth, size=11)
    digital_truth = "\n".join(t.text for t in digital)
    case(
        "text_only",
        [Page(texts=list(digital))],
        [digital_truth],
        "none",
        "born-digital text page",
        "negative",
    )
    case(
        "text_wm55",
        [Page(texts=[*digital, watermark(55)])],
        [digital_truth],
        "none",
        "born-digital text + diagonal watermark (no scan underneath)",
        "negative",
    )
    from PIL import Image

    background = Image.new("L", (827, 1169), 244)
    case(
        "text_background_wm55",
        [with_texts(scan_page(background), list(digital), watermark(55))],
        [digital_truth],
        "none",
        "digital text over a full-page background image + watermark (slide / letterhead)",
        "negative",
    )
    case(
        "scan200_visible_layer_wm55",
        [with_texts(scan(), text_lines(truth, size=11), watermark(55))],
        [truth],
        "none",
        "scan whose text layer is VISIBLE ordinary text + watermark: the PDF text is kept",
        "negative",
    )
    # A VISIBLE text layer that follows a skewed scan: every line is tilted, yet
    # the boxes are full of characters. It is the text of the page, not an
    # overlay, and Docling keeps it; full-page OCR would read the scan through it.
    for tilt in (2, 5):
        skewed = tilted(text_lines(truth, size=11), tilt)
        case(
            f"scan200_visible_layer_tilt{tilt:02d}",
            [with_texts(scan(), skewed)],
            ["\n".join(t.text for t in skewed)],
            "none",
            f"scan under a VISIBLE text layer whose lines are tilted {tilt} degrees",
            "negative",
        )
    half = scan_images(doc, 200)[0]
    half = half.crop((0, 0, half.width, int(half.height * 0.55)))
    case(
        "text_with_half_page_figure_wm55",
        [
            with_texts(
                scan_page(half, rect=(0, A4[1] * 0.45, A4[0], A4[1])),
                text_lines(truth, size=11, top=350, max_lines=22),
                watermark(55),
            )
        ],
        ["\n".join(t.text for t in text_lines(truth, size=11, top=350, max_lines=22))],
        "none",
        "digital text + an image over half of the page + watermark",
        "negative",
    )
    # --- documents ------------------------------------------------------------------
    other = "thong_tu"
    other_pages = scan_images(other, 200)
    case(
        "doc_5_pages_scan_wm55",
        [
            with_texts(
                scan_page(other_pages[i % len(other_pages)]),
                watermark(55),
                header_footer(i + 1),
            )
            for i in range(5)
        ],
        [None] * 5,
        "full_page",
        "five scanned pages, each with the watermark",
        "document",
    )
    case(
        "doc_scan_only_one_page_wm",
        [
            scan_page(other_pages[0]),
            with_texts(scan_page(other_pages[1]), watermark(55)),
            scan_page(other_pages[0]),
        ],
        [None] * 3,
        "full_page",
        "three scanned pages, the watermark on page 2 only (no digital page)",
        "document",
    )
    case(
        "doc_mixed_digital_and_scan_wm",
        [
            Page(texts=list(digital)),
            with_texts(scan(), hidden(), watermark(55)),
            with_texts(scan(), hidden(), watermark(55)),
        ],
        [digital_truth, truth, truth],
        "mixed",
        "one good digital page + two watermarked scans: left as it is, with a warning",
        "document",
    )
    return cases


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, type=Path)
    out = ap.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    entries = []
    for c in corpus():
        (out / f"{c['name']}.pdf").write_bytes(build_pdf(c["pages"]))
        entries.append(
            {
                "file": f"{c['name']}.pdf",
                "pages": len(c["pages"]),
                "ground_truth": c["ground_truth"],
                "expect": c["expect"],
                "why": c["why"],
                "group": c["group"],
            }
        )
    (out / "manifest.json").write_text(
        json.dumps(
            {
                "note": "Synthetic, fictional pages (Phase 10G). No real document, "
                "no real watermark text.",
                "files": entries,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote {len(entries)} files to {out}")


if __name__ == "__main__":
    main()
