"""Synthetic Vietnamese LEGAL-document scans for the Agri model benchmark (Phase 10E).

Entirely fictional text written for this benchmark ("Ngân hàng Thương mại Mẫu"):
no customer data, no internal document, nothing taken from the fine-tuning
corpus. It mimics what the custom Tesseract model was fine-tuned for — bank
legal documents: bold upper-case headings, Vietnamese diacritics, Điều / Khoản
/ Điểm structure, banking terms, document numbers, dates and the words that
carry legal meaning (negation, obligation, exception).

Every document is rendered at four scan qualities (clean 300 DPI ... blurred
150 DPI). Rendering is deterministic (fixed seeds), so the set can be
regenerated anywhere; only this generator is kept in Git.

    uv run python scripts/ocr/generate_agri_benchmark_fixtures.py --out <dir>

Output: <dir>/<doc>__<variant>.pdf (image-only PDF), <dir>/pages/*.png (the
same pages, for direct Tesseract runs), <dir>/vb_text_layer.pdf (a PDF WITH a
text layer, to prove such files are unaffected) and <dir>/manifest.json.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS = {
    "serif": {
        "regular": "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        "bold": "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
        "italic": "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
    },
    "sans": {
        "regular": "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "bold": "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "italic": "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
    },
}

# Block kinds:
#   title   centred, bold (upper-case headings)          -> "heading" metric
#   cbold   centred, bold        cital  centred, italic   center  centred
#   ital    justified-left italic paragraph (căn cứ ...)
#   dieu    "Điều N. Tên điều" in bold, the rest regular  -> "dieu" anchor
#   khoan   "1. ..." indented                              -> "khoan" anchor
#   diem    "a) ..." indented further                      -> "diem" anchor
#   para    plain paragraph
Block = tuple[str, str]

QUYET_DINH: list[Block] = [
    ("cbold", "NGÂN HÀNG THƯƠNG MẠI MẪU"),
    ("cbold", "HỘI ĐỒNG THÀNH VIÊN"),
    ("center", "Số: 468/QĐ-HĐTV-TD"),
    ("cbold", "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM"),
    ("cbold", "Độc lập - Tự do - Hạnh phúc"),
    ("cital", "Hà Nội, ngày 17 tháng 6 năm 2025"),
    ("title", "QUYẾT ĐỊNH"),
    (
        "cbold",
        "Ban hành Quy định về cho vay phục vụ phát triển nông nghiệp, nông thôn",
    ),
    ("title", "HỘI ĐỒNG THÀNH VIÊN NGÂN HÀNG THƯƠNG MẠI MẪU"),
    ("ital", "Căn cứ Luật Các tổ chức tín dụng ngày 18 tháng 01 năm 2024;"),
    (
        "ital",
        "Căn cứ Thông tư số 39/2016/TT-NHNN ngày 30 tháng 12 năm 2016 của Thống đốc "
        "Ngân hàng Nhà nước Việt Nam quy định về hoạt động cho vay của tổ chức tín "
        "dụng, chi nhánh ngân hàng nước ngoài đối với khách hàng;",
    ),
    (
        "ital",
        "Căn cứ Điều lệ tổ chức và hoạt động của Ngân hàng Thương mại Mẫu ban hành "
        "kèm theo Nghị quyết số 115/NQ-HĐTV ngày 22 tháng 4 năm 2023;",
    ),
    (
        "ital",
        "Theo đề nghị của Tổng Giám đốc tại Tờ trình số 1532/TTr-TGĐ ngày 02 tháng "
        "6 năm 2025,",
    ),
    ("title", "QUYẾT ĐỊNH:"),
    (
        "dieu",
        "Điều 1.| Ban hành kèm theo Quyết định này Quy định về cho vay phục vụ phát "
        "triển nông nghiệp, nông thôn trong hệ thống Ngân hàng Thương mại Mẫu.",
    ),
    (
        "dieu",
        "Điều 2.| Quyết định này có hiệu lực thi hành kể từ ngày 01 tháng 7 năm 2025 "
        "và thay thế Quyết định số 226/QĐ-HĐTV-TD ngày 09 tháng 3 năm 2019. Các "
        "khoản vay đã ký hợp đồng trước ngày Quyết định này có hiệu lực được tiếp "
        "tục thực hiện theo thỏa thuận đã ký, trừ trường hợp các bên có thỏa thuận "
        "sửa đổi, bổ sung phù hợp với Quy định mới.",
    ),
    (
        "dieu",
        "Điều 3.| Tổng Giám đốc, Trưởng Ban kiểm soát, Giám đốc chi nhánh loại I, "
        "loại II và Thủ trưởng các đơn vị có liên quan chịu trách nhiệm thi hành "
        "Quyết định này. Nghiêm cấm việc ban hành văn bản hướng dẫn trái với Quy "
        "định kèm theo; đơn vị không được tự ý nới lỏng điều kiện cho vay.",
    ),
    ("para", "Nơi nhận: Như Điều 3; Ban kiểm soát; Lưu: VT, HĐTV, TD."),
    ("cbold", "TM. HỘI ĐỒNG THÀNH VIÊN"),
    ("cbold", "CHỦ TỊCH"),
]

QUY_DINH: list[Block] = [
    ("title", "QUY ĐỊNH"),
    ("cbold", "Về cho vay phục vụ phát triển nông nghiệp, nông thôn"),
    (
        "cital",
        "(Ban hành kèm theo Quyết định số 468/QĐ-HĐTV-TD ngày 17 tháng 6 năm 2025)",
    ),
    ("title", "Chương I"),
    ("title", "QUY ĐỊNH CHUNG"),
    ("dieu", "Điều 1. Phạm vi điều chỉnh và đối tượng áp dụng|"),
    (
        "khoan",
        "1. Quy định này quy định về điều kiện, hạn mức, lãi suất, thời hạn và bảo "
        "đảm tiền vay đối với khách hàng vay vốn phục vụ sản xuất nông nghiệp.",
    ),
    (
        "khoan",
        "2. Quy định này không áp dụng đối với khoản vay hợp vốn và khoản cấp tín "
        "dụng bằng ngoại tệ, trừ trường hợp Tổng Giám đốc có văn bản chấp thuận.",
    ),
    ("dieu", "Điều 2. Giải thích từ ngữ|"),
    (
        "khoan",
        "1. Tài sản bảo đảm là tài sản mà bên bảo đảm dùng để bảo đảm thực hiện "
        "nghĩa vụ trả nợ, bao gồm quyền sử dụng đất và tài sản gắn liền với đất.",
    ),
    (
        "khoan",
        "2. Cơ cấu lại thời hạn trả nợ là việc điều chỉnh kỳ hạn trả nợ hoặc gia "
        "hạn nợ khi khách hàng chưa có khả năng trả nợ đúng kỳ hạn đã thỏa thuận.",
    ),
    ("dieu", "Điều 3. Điều kiện vay vốn|"),
    ("para", "Khách hàng được xem xét cho vay khi có đủ các điều kiện sau đây:"),
    (
        "diem",
        "a) Có năng lực pháp luật dân sự, năng lực hành vi dân sự đầy đủ theo quy "
        "định của pháp luật;",
    ),
    (
        "diem",
        "b) Có phương án sử dụng vốn khả thi và không thuộc đối tượng bị hạn chế "
        "cấp tín dụng;",
    ),
    (
        "diem",
        "c) Không có nợ xấu tại thời điểm đề nghị vay vốn, trừ khoản nợ đã được xử "
        "lý bằng dự phòng rủi ro;",
    ),
    (
        "diem",
        "d) Có tài sản bảo đảm hợp pháp; trường hợp cho vay không có bảo đảm thì "
        "mức cho vay tối đa không quá 300.000.000 đồng.",
    ),
    ("dieu", "Điều 4. Lãi suất và thời hạn cho vay|"),
    (
        "khoan",
        "1. Lãi suất cho vay ngắn hạn tối đa là 4,5%/năm; lãi suất quá hạn không "
        "vượt quá 150% lãi suất trong hạn.",
    ),
    (
        "khoan",
        "2. Thời hạn cho vay trung hạn không quá 60 tháng; thời gian ân hạn tối đa "
        "12 tháng và chỉ được áp dụng một lần đối với mỗi khoản vay.",
    ),
    ("dieu", "Điều 5. Thẩm quyền phê duyệt|"),
    (
        "khoan",
        "1. Giám đốc chi nhánh loại I được quyết định khoản vay đến 5.000.000.000 "
        "đồng; khoản vay vượt mức này phải trình Tổng Giám đốc phê duyệt.",
    ),
    (
        "khoan",
        "2. Người thẩm định không được đồng thời là người quyết định cho vay đối "
        "với cùng một khoản vay.",
    ),
]

THONG_TU: list[Block] = [
    ("cbold", "CƠ QUAN QUẢN LÝ MẪU"),
    ("center", "Số: 27/2025/TT-CQM"),
    ("cital", "Hà Nội, ngày 05 tháng 9 năm 2025"),
    ("title", "THÔNG TƯ"),
    (
        "cbold",
        "Quy định về phân loại nợ và trích lập dự phòng rủi ro trong hoạt động cho vay",
    ),
    (
        "ital",
        "Căn cứ Nghị định số 146/2023/NĐ-CP ngày 14 tháng 11 năm 2023 của Chính phủ;",
    ),
    ("ital", "Theo đề nghị của Vụ trưởng Vụ Chính sách an toàn;"),
    ("title", "Chương II"),
    ("title", "PHÂN LOẠI NỢ VÀ TRÍCH LẬP DỰ PHÒNG"),
    ("dieu", "Điều 6. Nguyên tắc phân loại nợ|"),
    (
        "khoan",
        "1. Toàn bộ dư nợ của một khách hàng phải được phân loại vào cùng một nhóm "
        "nợ có mức độ rủi ro cao nhất.",
    ),
    (
        "khoan",
        "2. Tổ chức tín dụng không được cơ cấu lại thời hạn trả nợ nhằm che giấu nợ "
        "xấu hoặc để giữ nguyên nhóm nợ.",
    ),
    (
        "khoan",
        "3. Việc phân loại nợ được thực hiện ít nhất mỗi quý một lần, chậm nhất vào "
        "ngày 07 của tháng đầu tiên quý tiếp theo.",
    ),
    ("dieu", "Điều 7. Mức trích lập dự phòng cụ thể|"),
    ("para", "Tỷ lệ trích lập dự phòng cụ thể đối với từng nhóm nợ như sau:"),
    ("diem", "a) Nhóm 1 (Nợ đủ tiêu chuẩn): 0%;"),
    ("diem", "b) Nhóm 2 (Nợ cần chú ý): 5%;"),
    ("diem", "c) Nhóm 3 (Nợ dưới tiêu chuẩn): 20%;"),
    ("diem", "d) Nhóm 4 (Nợ nghi ngờ): 50%;"),
    ("diem", "đ) Nhóm 5 (Nợ có khả năng mất vốn): 100%."),
    ("dieu", "Điều 8. Sử dụng dự phòng để xử lý rủi ro|"),
    (
        "khoan",
        "1. Tổ chức tín dụng chỉ được sử dụng dự phòng để xử lý rủi ro đối với khoản "
        "nợ thuộc Nhóm 5 hoặc khi khách hàng là tổ chức bị giải thể, phá sản.",
    ),
    (
        "khoan",
        "2. Việc sử dụng dự phòng không làm chấm dứt nghĩa vụ trả nợ của khách hàng; "
        "tổ chức tín dụng vẫn phải theo dõi và thu hồi nợ đầy đủ.",
    ),
    ("dieu", "Điều 9. Hiệu lực thi hành|"),
    (
        "khoan",
        "1. Thông tư này có hiệu lực thi hành kể từ ngày 20 tháng 10 năm 2025.",
    ),
    (
        "khoan",
        "2. Bãi bỏ Thông tư số 11/2021/TT-CQM ngày 30 tháng 7 năm 2021, trừ quy định "
        "tại khoản 3 Điều 12 tiếp tục có hiệu lực đến hết ngày 31/12/2025.",
    ),
]

NGHIA_VU: list[Block] = [
    ("title", "Chương III"),
    ("title", "QUYỀN, NGHĨA VỤ VÀ CÁC HÀNH VI BỊ NGHIÊM CẤM"),
    ("dieu", "Điều 10. Quyền của khách hàng vay vốn|"),
    (
        "khoan",
        "1. Khách hàng có quyền từ chối các yêu cầu không đúng với thỏa thuận trong "
        "hợp đồng tín dụng.",
    ),
    (
        "khoan",
        "2. Khách hàng được trả nợ trước hạn; ngân hàng không được thu phí trả nợ "
        "trước hạn nếu hợp đồng không có thỏa thuận.",
    ),
    ("dieu", "Điều 11. Nghĩa vụ của khách hàng vay vốn|"),
    (
        "khoan",
        "1. Khách hàng phải sử dụng vốn vay đúng mục đích và có trách nhiệm cung cấp "
        "đầy đủ, trung thực hồ sơ, tài liệu liên quan.",
    ),
    (
        "khoan",
        "2. Khách hàng bắt buộc phải mua bảo hiểm tài sản bảo đảm trong suốt thời "
        "hạn vay, ngoại trừ tài sản là quyền sử dụng đất.",
    ),
    (
        "khoan",
        "3. Khách hàng không được chuyển nhượng, tặng cho hoặc thế chấp lại tài sản "
        "bảo đảm khi chưa có văn bản đồng ý của ngân hàng.",
    ),
    ("dieu", "Điều 12. Các hành vi bị nghiêm cấm|"),
    ("para", "Nghiêm cấm cán bộ, người lao động thực hiện các hành vi sau đây:"),
    (
        "diem",
        "a) Nhận tiền, quà tặng hoặc lợi ích khác của khách hàng dưới mọi hình thức;",
    ),
    (
        "diem",
        "b) Cho vay đối với khách hàng không đủ điều kiện hoặc cho vay vượt hạn mức "
        "được phê duyệt;",
    ),
    (
        "diem",
        "c) Giải ngân khi hồ sơ chưa được phê duyệt hoặc chưa hoàn thành thủ tục bảo "
        "đảm tiền vay;",
    ),
    (
        "diem",
        "d) Tiết lộ thông tin khách hàng, trừ trường hợp có yêu cầu bằng văn bản của "
        "cơ quan nhà nước có thẩm quyền.",
    ),
    ("dieu", "Điều 13. Xử lý vi phạm|"),
    (
        "khoan",
        "1. Cá nhân vi phạm Quy định này, tùy theo tính chất và mức độ, sẽ bị xử lý "
        "kỷ luật và phải bồi thường thiệt hại theo quy định.",
    ),
    (
        "khoan",
        "2. Không áp dụng hình thức kỷ luật đối với trường hợp vi phạm do sự kiện "
        "bất khả kháng đã được Hội đồng xử lý rủi ro xác nhận.",
    ),
    (
        "khoan",
        "3. Trong thời hạn 15 ngày làm việc kể từ ngày phát hiện vi phạm, đơn vị "
        "phải báo cáo Trụ sở chính; quá thời hạn này mà chưa báo cáo thì Thủ trưởng "
        "đơn vị phải chịu trách nhiệm.",
    ),
]

DOCS: dict[str, dict] = {
    "quyet_dinh": {"blocks": QUYET_DINH, "font": "serif", "pt": 13.5},
    "quy_dinh": {"blocks": QUY_DINH, "font": "serif", "pt": 13.5},
    "thong_tu": {"blocks": THONG_TU, "font": "serif", "pt": 14},
    "nghia_vu": {"blocks": NGHIA_VU, "font": "sans", "pt": 12.5},
}

FIELDS: dict[str, dict[str, list[str]]] = {
    "quyet_dinh": {
        "doc_numbers": [
            "468/QĐ-HĐTV-TD",
            "39/2016/TT-NHNN",
            "115/NQ-HĐTV",
            "1532/TTr-TGĐ",
            "226/QĐ-HĐTV-TD",
        ],
        "dates": [
            "ngày 17 tháng 6 năm 2025",
            "ngày 18 tháng 01 năm 2024",
            "ngày 30 tháng 12 năm 2016",
            "ngày 22 tháng 4 năm 2023",
            "ngày 02 tháng 6 năm 2025",
            "ngày 01 tháng 7 năm 2025",
            "ngày 09 tháng 3 năm 2019",
        ],
    },
    "quy_dinh": {
        "doc_numbers": ["468/QĐ-HĐTV-TD"],
        "dates": ["ngày 17 tháng 6 năm 2025"],
    },
    "thong_tu": {
        "doc_numbers": ["27/2025/TT-CQM", "146/2023/NĐ-CP", "11/2021/TT-CQM"],
        "dates": [
            "ngày 05 tháng 9 năm 2025",
            "ngày 14 tháng 11 năm 2023",
            "ngày 20 tháng 10 năm 2025",
            "ngày 30 tháng 7 năm 2021",
            "31/12/2025",
        ],
    },
    "nghia_vu": {"doc_numbers": [], "dates": []},
}

# name -> (dpi, blur radius, ink grey level, background, speckle 1/N px,
#          rotation degrees, JPEG quality, binarise threshold or None)
VARIANTS: dict[str, tuple] = {
    "sach_300": (300, 0.0, 0, 255, 0, 0.0, 90, None),
    "scan_200": (200, 0.6, 25, 245, 900, -0.4, 60, None),
    "mo_150": (150, 1.0, 70, 232, 300, 0.7, 35, None),
    "photocopy_200": (200, 0.9, 0, 255, 500, 0.5, 70, 150),
}

PAGE_IN = (8.27, 11.69)  # A4
MARGIN_IN = (1.1, 0.9, 0.8, 0.8)  # left, top, right, bottom


def _font(path: str, px: int) -> ImageFont.FreeTypeFont:
    if not Path(path).is_file():
        raise SystemExit(f"Font missing: {path} (install fonts-liberation)")
    return ImageFont.truetype(path, px)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def plain_text(kind: str, text: str) -> str:
    return text.replace("|", "") if kind == "dieu" else text


def render(doc: dict, dpi: int) -> list[Image.Image]:
    """Render the blocks onto as many A4 pages as needed (pure black on white)."""
    px = int(doc["pt"] * dpi / 72)
    fam = FONTS[doc["font"]]
    regular, bold, italic = (_font(fam[k], px) for k in ("regular", "bold", "italic"))
    w, h = int(PAGE_IN[0] * dpi), int(PAGE_IN[1] * dpi)
    left, top = int(MARGIN_IN[0] * dpi), int(MARGIN_IN[1] * dpi)
    right, bottom = w - int(MARGIN_IN[2] * dpi), h - int(MARGIN_IN[3] * dpi)
    line_h = int(px * 1.42)
    pages: list[Image.Image] = []
    img = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(img)
    y = top

    def new_page() -> None:
        nonlocal img, d, y
        pages.append(img)
        img = Image.new("L", (w, h), 255)
        d = ImageDraw.Draw(img)
        y = top

    for kind, raw in doc["blocks"]:
        centred = kind in ("title", "cbold", "cital", "center")
        indent = {"khoan": 0.35, "diem": 0.6, "para": 0.35, "ital": 0.35, "dieu": 0.35}
        x0 = left + int(indent.get(kind, 0) * dpi) if not centred else left
        font = (
            bold
            if kind in ("title", "cbold")
            else italic
            if kind in ("ital", "cital")
            else regular
        )
        if kind == "dieu":
            head, _, rest = raw.partition("|")
            head_w = int(d.textlength(head + " ", font=bold)) if rest.strip() else 0
            words = _wrap(d, rest.strip(), regular, right - left)
            # First line: bold head + as much of the body as fits behind it.
            first: list[str] = []
            if rest.strip():
                body_first = _wrap(d, rest.strip(), regular, right - x0 - head_w)
                first = body_first[:1]
                remaining = rest.strip()[len(first[0]) :].strip() if first else ""
                words = _wrap(d, remaining, regular, right - left) if remaining else []
            needed = (1 + len(words)) * line_h
            if y + needed > bottom:
                new_page()
            d.text((x0, y), head, font=bold, fill=0)
            if first:
                d.text((x0 + head_w, y), first[0], font=regular, fill=0)
            y += line_h
            for ln in words:
                d.text((left, y), ln, font=regular, fill=0)
                y += line_h
        else:
            lines = _wrap(d, raw, font, right - x0 if not centred else right - left)
            if y + len(lines) * line_h > bottom:
                new_page()
            for i, ln in enumerate(lines):
                if centred:
                    tw = d.textlength(ln, font=font)
                    d.text((left + (right - left - tw) / 2, y), ln, font=font, fill=0)
                else:
                    d.text((x0 if i == 0 else left, y), ln, font=font, fill=0)
                y += line_h
        y += int(line_h * (0.55 if kind in ("title", "cbold") else 0.25))
    pages.append(img)
    return pages


def degrade(img: Image.Image, variant: tuple, seed: int) -> Image.Image:
    _dpi, blur, ink, paper, speckle, rot, _q, binarise = variant
    rnd = random.Random(seed)
    out = img
    if rot:
        out = out.rotate(rot, resample=Image.Resampling.BICUBIC, fillcolor=255)
    if blur:
        out = out.filter(ImageFilter.GaussianBlur(blur))
    if binarise is not None:
        # A photocopy: hard threshold after blur thickens / breaks strokes.
        out = out.point(lambda v: 0 if v < binarise else 255)
    scale = (paper - ink) / 255.0
    out = out.point(lambda v: int(ink + v * scale))
    if speckle:
        px = out.load()
        assert px is not None
        for _ in range(out.width * out.height // speckle):
            x, y = rnd.randrange(out.width), rnd.randrange(out.height)
            px[x, y] = rnd.choice((20, 70, 120, 215))
    return out


def save_scan(images: list[Image.Image], path: Path, dpi: int, quality: int) -> None:
    rgb = [im.convert("RGB") for im in images]
    rgb[0].save(
        path, save_all=True, append_images=rgb[1:], resolution=dpi, quality=quality
    )


def text_layer_pdf(path: Path, doc: dict) -> bool:
    """A born-digital PDF (real text layer) of one document; needs reportlab."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen import canvas
    except ImportError:
        return False
    fam = FONTS[doc["font"]]
    pdfmetrics.registerFont(TTFont("AgriR", fam["regular"]))
    pdfmetrics.registerFont(TTFont("AgriB", fam["bold"]))
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 60
    for kind, raw in doc["blocks"]:
        text = plain_text(kind, raw)
        font = "AgriB" if kind in ("title", "cbold", "dieu") else "AgriR"
        c.setFont(font, 12)
        line = ""
        for word in text.split():
            trial = f"{line} {word}".strip()
            if pdfmetrics.stringWidth(trial, font, 12) > width - 120 and line:
                c.drawString(60, y, line)
                y -= 17
                line = word
            else:
                line = trial
            if y < 60:
                c.showPage()
                c.setFont(font, 12)
                y = height - 60
        if line:
            c.drawString(60, y, line)
            y -= 21
        if y < 60:
            c.showPage()
            y = height - 60
    c.save()
    return True


def anchors(blocks: list[Block]) -> dict[str, list[str]]:
    """Structure markers that must survive OCR: headings, Điều, Khoản, Điểm."""
    out: dict[str, list[str]] = {"heading": [], "dieu": [], "khoan": [], "diem": []}
    for kind, raw in blocks:
        text = plain_text(kind, raw)
        if kind == "title":
            out["heading"].append(text)
        elif kind == "dieu":
            head = raw.partition("|")[0].strip()
            # "Điều 3. Điều kiện vay vốn" (titled) or "Điều 1." + first words.
            words = text.split()
            out["dieu"].append(head if len(head.split()) > 2 else " ".join(words[:5]))
        elif kind in ("khoan", "diem"):
            out[kind].append(" ".join(text.split()[:5]))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, type=Path)
    out = ap.parse_args().out
    (out / "pages").mkdir(parents=True, exist_ok=True)
    entries = []
    for di, (name, doc) in enumerate(DOCS.items()):
        gt = "\n".join(plain_text(k, t) for k, t in doc["blocks"])
        for vi, (vname, variant) in enumerate(VARIANTS.items()):
            dpi, quality = variant[0], variant[6]
            pages = [
                degrade(p, variant, seed=1000 + 37 * di + 11 * vi + pi)
                for pi, p in enumerate(render(doc, dpi))
            ]
            stem = f"{name}__{vname}"
            save_scan(pages, out / f"{stem}.pdf", dpi, quality)
            page_files = []
            for pi, p in enumerate(pages):
                pf = f"pages/{stem}__p{pi + 1}.png"
                # Same pixels the PDF holds: go through the same JPEG compression.
                tmp = out / f"pages/{stem}__p{pi + 1}.jpg"
                p.convert("RGB").save(tmp, quality=quality, dpi=(dpi, dpi))
                Image.open(tmp).save(out / pf, dpi=(dpi, dpi))
                tmp.unlink()
                page_files.append(pf)
            entries.append(
                {
                    "file": f"{stem}.pdf",
                    "doc": name,
                    "variant": vname,
                    "dpi": dpi,
                    "pages": len(pages),
                    "page_images": page_files,
                    "text_layer": False,
                    "ground_truth": gt,
                    "anchors": anchors(doc["blocks"]),
                    "key_fields": FIELDS[name],
                }
            )
    if text_layer_pdf(out / "vb_text_layer.pdf", DOCS["quy_dinh"]):
        entries.append(
            {
                "file": "vb_text_layer.pdf",
                "doc": "quy_dinh",
                "variant": "text_layer",
                "dpi": None,
                "pages": None,
                "page_images": [],
                "text_layer": True,
                "ground_truth": "\n".join(
                    plain_text(k, t) for k, t in DOCS["quy_dinh"]["blocks"]
                ),
                "anchors": anchors(DOCS["quy_dinh"]["blocks"]),
                "key_fields": FIELDS["quy_dinh"],
            }
        )
    (out / "manifest.json").write_text(
        json.dumps(
            {
                "note": "Synthetic, fictional legal documents (Phase 10E). No customer "
                "data; independent of any fine-tuning corpus by construction of the "
                "TEXT. Fonts / scan style may still resemble training material.",
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
