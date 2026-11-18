"""Synthetic Vietnamese legal-document fixtures for Phase 12 (no real data).

Every organisation, person, number and address below is FICTIONAL. Each fixture
is a *layout specification*: the elements a layout model (Docling Layout Heron)
would report for each page - label, text, bounding box (PDF points, top-left
origin) - plus the ground truth of the clean document and the checks a correct
normalization must pass.

The specs are consumed by:
- ``tests/legal_harness.py``: builds a real ``DoclingDocument`` by running
  Docling's own ReadingOrderModel (reading order, list-marker detection,
  Docling's cross-page merge, furniture layer) on these elements;
- ``scripts/ocr/generate_phase12_fixtures.py``: renders the same pages as PDF
  (scan / text layer / watermark / hidden-OCR variants) for the full pipeline
  on a machine with Docling models (Windows Local).

Element shorthand: ``E(label, text, x, y, w=..., h=...)``; pictures may carry
``children`` (OCR text Docling places inside the picture region), tables carry
``rows`` (first row = header).

GROUND TRUTH (Phase 12D3, finding T-01). The oracle must not depend on what the
normalizer does, so every element declares its own truth, written with the
fixture and before any implementation runs:

  (no ``gt`` key)   REQUIRED: the text must be in the output, as its own line,
                    as many times as it is declared, in this order.
  ``gt="artifact"`` a page number / running header: MAY be removed. Removing
                    anything else is a false deletion.
  ``gt="join"``     the continuation of the previous required element: MAY be
                    joined to it with one space. Any other merge is a false merge.
  ``gt="furniture"``labelled PAGE_HEADER / PAGE_FOOTER by the layout model
                    AND not business content (page number, running title):
                    may be absent. Business content the layout model labelled
                    header / footer (a document number, the issuer, a footnote)
                    is REQUIRED like any other text (Phase 12D5, R2-11).
  pictures          (Phase 12D5, F-06) the ``<!-- image -->`` placeholder is a
                    REQUIRED trace by default: the picture may hold content
                    nobody extracted. ``gt="decoration"`` (signature, stamp,
                    logo) may lose it. OCR text inside a picture is REQUIRED.

``expect_removed`` / ``expect_joined`` list what MUST happen where the evidence
is sufficient (so that conservative rules do not silently disable the feature).
``tests/legal_harness.py::preservation`` computes the metrics from these
declarations only.
"""

from __future__ import annotations

from typing import Any

PAGE_W, PAGE_H = 595.0, 842.0  # A4 in points
LEFT, WIDTH = 70.0, 455.0


def E(
    label: str,
    text: str = "",
    x: float = LEFT,
    y: float = 100.0,
    w: float = WIDTH,
    h: float = 14.0,
    **extra: Any,
) -> dict[str, Any]:
    return {"label": label, "text": text, "bbox": [x, y, x + w, y + h], **extra}


def page_number(n: int | str, bottom: bool = True) -> dict[str, Any]:
    """A page number the layout model mislabelled as body TEXT (the common case)."""
    return E("text", str(n), x=290, y=800 if bottom else 30, w=16, h=12, gt="artifact")


def footer(n: int | str) -> dict[str, Any]:
    """A page number correctly labelled PAGE_FOOTER (Docling puts it in furniture)."""
    return E("page_footer", str(n), x=290, y=800, w=16, h=12, gt="furniture")


def signature(y: float = 700) -> dict[str, Any]:
    """A signature image: decoration, its placeholder may be dropped (Phase 12D5)."""
    return E("picture", x=360, y=y, w=120, h=45, gt="decoration")


def stamp(y: float = 690) -> dict[str, Any]:
    """A seal / stamp image: decoration, its placeholder may be dropped (Phase 12D5)."""
    return E("picture", x=320, y=y, w=80, h=80, gt="decoration")


QD_HEADER = [
    E("text", "NGÂN HÀNG THƯƠNG MẠI MẪU", y=40, w=200),
    E("text", "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", x=300, y=40, w=225),
    E("text", "Số: 123/2024/QĐ-NHM", y=60, w=200),
    E("text", "Độc lập - Tự do - Hạnh phúc", x=320, y=60, w=185),
]


FIXTURES: list[dict[str, Any]] = [
    {
        "name": "f01_one_page_decision",
        "description": "Một trang quyết định: Điều, khoản 1./2., điểm a) b) đ), chữ ký và con dấu.",
        "pages": [
            QD_HEADER
            + [
                E("section_header", "QUYẾT ĐỊNH", x=230, y=110, w=135, h=18),
                E("section_header", "Điều 1. Phạm vi điều chỉnh", y=150),
                E(
                    "list_item",
                    "1. Quy định này áp dụng đối với các đơn vị trong hệ thống.",
                    y=175,
                ),
                E(
                    "list_item",
                    "2. Các trường hợp sau đây được miễn phí dịch vụ:",
                    y=195,
                ),
                E(
                    "list_item",
                    "a) Khách hàng cá nhân mở tài khoản lần đầu;",
                    x=90,
                    y=215,
                    w=435,
                ),
                E(
                    "list_item",
                    "b) Khách hàng là học sinh, sinh viên;",
                    x=90,
                    y=235,
                    w=435,
                ),
                E(
                    "list_item",
                    "đ) Các trường hợp khác do Tổng Giám đốc quyết định.",
                    x=90,
                    y=255,
                    w=435,
                ),
                E("text", "TỔNG GIÁM ĐỐC", x=360, y=640, w=120),
                signature(665),
                stamp(655),
                E("text", "Nguyễn Văn Mẫu", x=360, y=730, w=120),
            ]
        ],
        "ground_truth": (
            "NGÂN HÀNG THƯƠNG MẠI MẪU CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM Số: 123/2024/QĐ-NHM "
            "Độc lập - Tự do - Hạnh phúc QUYẾT ĐỊNH Điều 1. Phạm vi điều chỉnh "
            "1. Quy định này áp dụng đối với các đơn vị trong hệ thống. "
            "2. Các trường hợp sau đây được miễn phí dịch vụ: "
            "a) Khách hàng cá nhân mở tài khoản lần đầu; b) Khách hàng là học sinh, sinh viên; "
            "đ) Các trường hợp khác do Tổng Giám đốc quyết định. TỔNG GIÁM ĐỐC Nguyễn Văn Mẫu"
        ),
        "markers": ["1.", "2.", "a)", "b)", "đ)"],
        "protected": ["Số: 123/2024/QĐ-NHM"],
        "order": [
            "Điều 1.",
            "1. Quy định",
            "2. Các trường hợp",
            "a) Khách",
            "b) Khách",
            "đ) Các",
            "TỔNG GIÁM ĐỐC",
        ],
        "expect_placeholders": 0,
    },
    {
        "name": "f02_clause_across_pages",
        "description": "Ví dụ của người dùng: khoản 9 bị cắt bởi trang, có con dấu nhỏ và số trang (nhãn TEXT) chen giữa.",
        "pages": [
            [
                E("section_header", "Điều 3. Giải thích từ ngữ", y=80),
                E(
                    "list_item",
                    "8. Dịch vụ tài chính là dịch vụ làm thay đổi số dư tài khoản.",
                    y=720,
                ),
                E(
                    "list_item",
                    "9. Dịch vụ phi tài chính là dịch vụ không làm thay đổi số",
                    y=745,
                ),
                stamp(760),
                page_number(6),
            ],
            [
                E("text", "dư trên tài khoản của khách hàng.", y=60, gt="join"),
                E(
                    "list_item",
                    "10. Ngày làm việc là các ngày từ thứ Hai đến thứ Sáu.",
                    y=85,
                ),
                page_number(7),
            ],
        ],
        "page_offset": 5,
        "ground_truth": (
            "Điều 3. Giải thích từ ngữ 8. Dịch vụ tài chính là dịch vụ làm thay đổi số dư tài khoản. "
            "9. Dịch vụ phi tài chính là dịch vụ không làm thay đổi số dư trên tài khoản của khách hàng. "
            "10. Ngày làm việc là các ngày từ thứ Hai đến thứ Sáu."
        ),
        "markers": ["8.", "9.", "10."],
        # 2 trang: chưa đủ bằng chứng số trang (F-02) => số trang và phép ghép chỉ là "được phép".
        "order": ["8. Dịch vụ", "9. Dịch vụ", "10. Ngày"],
        "expect_placeholders": 0,
    },
    {
        "name": "f03_missing_word_not_invented",
        "description": "OCR mất chữ cuối trang ('số'): được nối nhưng KHÔNG được tự thêm chữ.",
        "pages": [
            [
                E(
                    "list_item",
                    "9. Dịch vụ phi tài chính là dịch vụ không làm thay đổi",
                    y=745,
                ),
                page_number(6),
            ],
            [
                E("text", "dư trên tài khoản của khách hàng.", y=60, gt="join"),
                page_number(7),
            ],
        ],
        "ground_truth": "9. Dịch vụ phi tài chính là dịch vụ không làm thay đổi số dư trên tài khoản của khách hàng.",
        "markers": ["9."],
        "forbidden": ["thay đổi số dư"],
    },
    {
        "name": "f04_new_clause_not_joined",
        "description": "Trang sau bắt đầu bằng điểm a) / khoản mới: không được nối dù trang trước chưa có dấu chấm.",
        "pages": [
            [
                E("list_item", "3. Đối tượng áp dụng gồm", y=730),
                page_number(2),
            ],
            [
                E("list_item", "a) khách hàng cá nhân;", x=90, y=60, w=435),
                E("list_item", "b) khách hàng tổ chức;", x=90, y=80, w=435),
                E("text", "Danh mục được cập nhật theo quy định", y=760),
                page_number(3),
            ],
            [
                E("list_item", "4. Hiệu lực thi hành", y=60),
                E("text", "Quy định có hiệu lực từ ngày 01/07/2024.", y=80),
                page_number(4),
            ],
        ],
        "ground_truth": (
            "3. Đối tượng áp dụng gồm a) khách hàng cá nhân; b) khách hàng tổ chức; "
            "Danh mục được cập nhật theo quy định 4. Hiệu lực thi hành Quy định có hiệu lực từ ngày 01/07/2024."
        ),
        "markers": ["3.", "a)", "b)", "4."],
        "must_not_join": [
            ["Đối tượng áp dụng gồm", "a) khách hàng"],
            ["theo quy định", "4. Hiệu lực"],
        ],
        "protected": ["01/07/2024"],
        "expect_removed": ["2", "3", "4"],
    },
    {
        "name": "f05_list_starts_at_10_not_continuous",
        "description": "Danh sách bắt đầu từ 5 và 10, số không liên tục (trích dẫn một phần điều khoản).",
        "pages": [
            [
                E("section_header", "Điều 7. Trách nhiệm của đơn vị", y=80),
                E("list_item", "5. Lập báo cáo định kỳ hằng quý.", y=110),
                E("list_item", "7. Lưu trữ hồ sơ theo quy định.", y=130),
                E("text", "Nội dung khác của Điều 7 giữ nguyên.", y=160),
                E("list_item", "10. Kiểm tra, giám sát việc thực hiện.", y=190),
                E("list_item", "11. Báo cáo kết quả cho Tổng Giám đốc.", y=210),
                E("list_item", "13. Thực hiện các nhiệm vụ khác.", y=230),
            ]
        ],
        "ground_truth": (
            "Điều 7. Trách nhiệm của đơn vị 5. Lập báo cáo định kỳ hằng quý. 7. Lưu trữ hồ sơ theo quy định. "
            "Nội dung khác của Điều 7 giữ nguyên. 10. Kiểm tra, giám sát việc thực hiện. "
            "11. Báo cáo kết quả cho Tổng Giám đốc. 13. Thực hiện các nhiệm vụ khác."
        ),
        "markers": ["5.", "7.", "10.", "11.", "13."],
    },
    {
        "name": "f06_multilevel_list",
        "description": "Danh sách nhiều cấp: 1., 1.1, 1.2, 2., 2.1, a), b), c), d), đ), a.1), gạch đầu dòng.",
        "pages": [
            [
                E("list_item", "1. Nguyên tắc chung", y=80),
                E("list_item", "1.1 Tuân thủ pháp luật;", x=90, y=100, w=435),
                E("list_item", "1.2 Bảo đảm an toàn;", x=90, y=120, w=435),
                E("list_item", "2. Điều kiện cấp tín dụng", y=140),
                E(
                    "list_item",
                    "2.1 Khách hàng có năng lực pháp luật dân sự;",
                    x=90,
                    y=160,
                    w=435,
                ),
                E(
                    "list_item",
                    "a) có phương án sử dụng vốn khả thi;",
                    x=110,
                    y=180,
                    w=415,
                ),
                E("list_item", "b) có khả năng tài chính;", x=110, y=200, w=415),
                E("list_item", "c) có tài sản bảo đảm;", x=110, y=220, w=415),
                E("list_item", "d) không có nợ xấu;", x=110, y=240, w=415),
                E("list_item", "đ) đáp ứng điều kiện khác;", x=110, y=260, w=415),
                E("list_item", "a.1) đối với khách hàng cá nhân;", x=130, y=280, w=395),
                E("list_item", "- đối với khách hàng tổ chức.", x=130, y=300, w=395),
            ]
        ],
        "ground_truth": (
            "1. Nguyên tắc chung 1.1 Tuân thủ pháp luật; 1.2 Bảo đảm an toàn; 2. Điều kiện cấp tín dụng "
            "2.1 Khách hàng có năng lực pháp luật dân sự; a) có phương án sử dụng vốn khả thi; "
            "b) có khả năng tài chính; c) có tài sản bảo đảm; d) không có nợ xấu; đ) đáp ứng điều kiện khác; "
            "a.1) đối với khách hàng cá nhân; - đối với khách hàng tổ chức."
        ),
        "markers": [
            "1.",
            "1.1",
            "1.2",
            "2.",
            "2.1",
            "a)",
            "b)",
            "c)",
            "d)",
            "đ)",
            "a.1)",
            "-",
        ],
    },
    {
        "name": "f07_parts_chapters_sections",
        "description": "PHẦN I, CHƯƠNG I, Mục 1, Điều 1. và Điều 2. qua nhiều trang.",
        "pages": [
            [
                E("section_header", "PHẦN I", x=260, y=80, w=75, h=18),
                E("section_header", "QUY ĐỊNH CHUNG", x=220, y=100, w=155, h=18),
                E("section_header", "CHƯƠNG I", x=255, y=130, w=85, h=18),
                E("section_header", "Mục 1. Phạm vi", y=160),
                E("section_header", "Điều 1. Đối tượng", y=185),
                E(
                    "text",
                    "Quy định này áp dụng cho toàn hệ thống ngân hàng mẫu.",
                    y=205,
                ),
                page_number(1),
            ],
            [
                E("section_header", "Điều 2. Giải thích", y=60),
                E(
                    "text",
                    "Trong quy định này, các từ ngữ dưới đây được hiểu như sau.",
                    y=80,
                ),
                page_number(2),
            ],
        ],
        "ground_truth": (
            "PHẦN I QUY ĐỊNH CHUNG CHƯƠNG I Mục 1. Phạm vi Điều 1. Đối tượng "
            "Quy định này áp dụng cho toàn hệ thống ngân hàng mẫu. Điều 2. Giải thích "
            "Trong quy định này, các từ ngữ dưới đây được hiểu như sau."
        ),
        "order": ["PHẦN I", "CHƯƠNG I", "Mục 1.", "Điều 1.", "Điều 2."],
    },
    {
        "name": "f08_protected_fields",
        "description": "Số hiệu, ngày, số tiền, %, lãi suất, hạn mức, thời hạn, URL, mã tài liệu; số đứng riêng giữa trang.",
        "pages": [
            [
                E(
                    "text",
                    "Căn cứ Thông tư số 39/2016/TT-NHNN ngày 30/12/2016 của Ngân hàng Nhà nước;",
                    y=80,
                ),
                E(
                    "text",
                    "Lãi suất cho vay tối đa 7,5%/năm, hạn mức 2.500.000.000 đồng, thời hạn 12 tháng.",
                    y=100,
                ),
                E(
                    "text",
                    "Phí dịch vụ: 0,05% giá trị giao dịch, tối thiểu 10.000 VND.",
                    y=120,
                ),
                E(
                    "text",
                    "Tra cứu tại https://vanban.example.vn/qd-123 (mã tài liệu QT-07/HĐQT).",
                    y=140,
                ),
                E("text", "2024", x=280, y=300, w=40),
                E("text", "15", x=290, y=320, w=20),
                E("text", "Tỷ lệ 0,5% áp dụng từ 01/01/2025.", y=340),
                page_number(1),
            ],
            [
                E("text", "Hạn mức tối đa 500 triệu đồng/khách hàng.", y=60),
                page_number(2),
            ],
        ],
        "ground_truth": (
            "Căn cứ Thông tư số 39/2016/TT-NHNN ngày 30/12/2016 của Ngân hàng Nhà nước; "
            "Lãi suất cho vay tối đa 7,5%/năm, hạn mức 2.500.000.000 đồng, thời hạn 12 tháng. "
            "Phí dịch vụ: 0,05% giá trị giao dịch, tối thiểu 10.000 VND. "
            "Tra cứu tại https://vanban.example.vn/qd-123 (mã tài liệu QT-07/HĐQT). 2024 15 "
            "Tỷ lệ 0,5% áp dụng từ 01/01/2025. Hạn mức tối đa 500 triệu đồng/khách hàng."
        ),
        "protected": [
            "39/2016/TT-NHNN",
            "30/12/2016",
            "7,5%/năm",
            "2.500.000.000 đồng",
            "12 tháng",
            "0,05%",
            "10.000 VND",
            "https://vanban.example.vn/qd-123",
            "QT-07/HĐQT",
            "0,5%",
            "01/01/2025",
            "500 triệu đồng",
        ],
        "present_lines": ["2024", "15"],
    },
    {
        "name": "f09_table",
        "description": "Bảng biểu phí có tiêu đề cột và caption.",
        "pages": [
            [
                E("text", "Biểu phí áp dụng như sau:", y=80),
                E("caption", "Bảng 1. Biểu phí dịch vụ mẫu", y=100),
                E(
                    "table",
                    y=120,
                    h=80,
                    rows=[
                        ["STT", "Dịch vụ", "Mức phí (đồng)"],
                        ["1", "Mở tài khoản", "0"],
                        ["2", "Chuyển tiền trong hệ thống", "2.200"],
                        ["3", "Rút tiền mặt", "1.100"],
                    ],
                ),
                E("text", "Mức phí trên đã bao gồm thuế giá trị gia tăng.", y=210),
            ]
        ],
        "ground_truth": (
            "Biểu phí áp dụng như sau: Bảng 1. Biểu phí dịch vụ mẫu STT Dịch vụ Mức phí (đồng) "
            "1 Mở tài khoản 0 2 Chuyển tiền trong hệ thống 2.200 3 Rút tiền mặt 1.100 "
            "Mức phí trên đã bao gồm thuế giá trị gia tăng."
        ),
        "protected": ["2.200", "1.100"],
        "table_identical": True,
    },
    {
        "name": "f10_table_across_pages",
        "description": "Bảng kéo dài hai trang: không được tự ghép bảng, không được nối với đoạn văn.",
        "pages": [
            [
                E("text", "Danh sách chi nhánh thí điểm", y=600),
                E(
                    "table",
                    y=620,
                    h=150,
                    rows=[
                        ["STT", "Chi nhánh", "Mã"],
                        ["1", "Chi nhánh A", "CN01"],
                        ["2", "Chi nhánh B", "CN02"],
                    ],
                ),
                page_number(1),
            ],
            [
                E(
                    "table",
                    y=50,
                    h=60,
                    rows=[["3", "Chi nhánh C", "CN03"], ["4", "Chi nhánh D", "CN04"]],
                ),
                E("text", "danh sách có thể được điều chỉnh", y=130),
                page_number(2),
            ],
        ],
        "ground_truth": (
            "Danh sách chi nhánh thí điểm STT Chi nhánh Mã 1 Chi nhánh A CN01 2 Chi nhánh B CN02 "
            "3 Chi nhánh C CN03 4 Chi nhánh D CN04 danh sách có thể được điều chỉnh"
        ),
        "protected": ["CN01", "CN02", "CN03", "CN04"],
        "table_identical": True,
    },
    {
        "name": "f11_blank_page",
        "description": "Trang trắng ở giữa: không được nối đoạn qua trang trắng.",
        "pages": [
            [
                E("text", "Phần này được để trống có chủ ý và tiếp tục", y=740),
                page_number(1),
            ],
            [],
            [E("text", "nội dung của phụ lục kèm theo.", y=60), page_number(3)],
        ],
        "ground_truth": "Phần này được để trống có chủ ý và tiếp tục nội dung của phụ lục kèm theo.",
        "must_not_join": [["tiếp tục", "nội dung của phụ lục"]],
    },
    {
        "name": "f12_two_columns",
        "description": "Văn bản hai cột: thứ tự đọc phải giữ nguyên như Docling xác định.",
        "pages": [
            [
                E("section_header", "THÔNG BÁO", x=250, y=60, w=95, h=18),
                E(
                    "text",
                    "Cột trái đoạn một nói về thủ tục mở tài khoản.",
                    y=100,
                    w=210,
                    h=40,
                ),
                E(
                    "text",
                    "Cột trái đoạn hai nói về hồ sơ cần chuẩn bị.",
                    y=150,
                    w=210,
                    h=40,
                ),
                E(
                    "text",
                    "Cột phải đoạn một nói về thời gian xử lý.",
                    x=315,
                    y=100,
                    w=210,
                    h=40,
                ),
                E(
                    "text",
                    "Cột phải đoạn hai nói về phí dịch vụ.",
                    x=315,
                    y=150,
                    w=210,
                    h=40,
                ),
            ]
        ],
        "ground_truth": (
            "THÔNG BÁO Cột trái đoạn một nói về thủ tục mở tài khoản. Cột trái đoạn hai nói về hồ sơ cần chuẩn bị. "
            "Cột phải đoạn một nói về thời gian xử lý. Cột phải đoạn hai nói về phí dịch vụ."
        ),
        # Phase 12D5: declared exception, see scripts/ocr/phase12_oracle.py
        "upstream_reordering": "Docling's ReadingOrderModel reads these two synthetic columns "
        "row by row (the standard export too): verify on real scans, Windows Local W-RC-10",
        "order": [
            "THÔNG BÁO",
            "Cột trái đoạn một",
            "Cột trái đoạn hai",
            "Cột phải đoạn một",
            "Cột phải đoạn hai",
        ],
    },
    {
        "name": "f13_footnotes",
        "description": "Chú thích cuối trang có nội dung nghiệp vụ phải được giữ.",
        "pages": [
            [
                E("text", "Khách hàng được hưởng ưu đãi theo chương trình(1).", y=100),
                E(
                    "footnote",
                    "(1) Chương trình áp dụng từ ngày 01/07/2024 đến 31/12/2024.",
                    y=770,
                    h=12,
                ),
                page_number(1),
            ],
            [E("text", "Các ưu đãi không được cộng dồn.", y=60), page_number(2)],
        ],
        "ground_truth": (
            "Khách hàng được hưởng ưu đãi theo chương trình(1). "
            "(1) Chương trình áp dụng từ ngày 01/07/2024 đến 31/12/2024. Các ưu đãi không được cộng dồn."
        ),
        "protected": ["01/07/2024", "31/12/2024"],
    },
    {
        "name": "f14_running_header_footer",
        "description": "Header/footer lặp trên 4 trang (nhãn TEXT) và 'Trang n/4'.",
        "pages": [
            [
                E(
                    "text",
                    "NGÂN HÀNG MẪU - QUY ĐỊNH NỘI BỘ",
                    y=25,
                    w=250,
                    h=12,
                    gt="artifact",
                ),
                E(
                    "section_header",
                    "QUY ĐỊNH VỀ DỊCH VỤ THẺ",
                    x=180,
                    y=80,
                    w=235,
                    h=18,
                ),
                E("text", f"Nội dung trang {1} của quy định.", y=120),
                E("text", "Trang 1/4", x=270, y=805, w=60, h=12, gt="artifact"),
            ]
        ]
        + [
            [
                E(
                    "text",
                    "NGÂN HÀNG MẪU - QUY ĐỊNH NỘI BỘ",
                    y=25,
                    w=250,
                    h=12,
                    gt="artifact",
                ),
                E("text", f"Nội dung trang {n} của quy định.", y=60),
                E("text", f"Trang {n}/4", x=270, y=805, w=60, h=12, gt="artifact"),
            ]
            for n in (2, 3, 4)
        ],
        "ground_truth": (
            "QUY ĐỊNH VỀ DỊCH VỤ THẺ Nội dung trang 1 của quy định. Nội dung trang 2 của quy định. "
            "Nội dung trang 3 của quy định. Nội dung trang 4 của quy định."
        ),
        "expect_removed": ["Trang 1/4", "Trang 2/4", "Trang 3/4", "Trang 4/4"],
        "present_lines": ["QUY ĐỊNH VỀ DỊCH VỤ THẺ"],
    },
    {
        "name": "f15_watermark_and_large_picture",
        "description": "Hình lớn không có chữ (sơ đồ/watermark) giữ placeholder + cảnh báo; con dấu có chữ OCR được giữ chữ.",
        "pages": [
            [
                E("text", "Sơ đồ quy trình được trình bày dưới đây.", y=80),
                E("picture", x=70, y=100, w=455, h=300),
                E("text", "Quy trình gồm ba bước như sơ đồ trên.", y=420),
                E(
                    "picture",
                    x=380,
                    y=600,
                    w=90,
                    h=90,
                    gt="decoration",  # the stamp; its OCR text below is REQUIRED
                    children=[E("text", "NGÂN HÀNG MẪU", x=390, y=640, w=70, h=10)],
                ),
            ]
        ],
        "ground_truth": "Sơ đồ quy trình được trình bày dưới đây. Quy trình gồm ba bước như sơ đồ trên. NGÂN HÀNG MẪU",
        "expect_placeholders": 1,
        "expect_warnings": ["picture_without_text"],
    },
    {
        "name": "f16_text_inside_picture",
        "description": "Trang scan bị layout bao trong một PICTURE: chữ OCR là con của ảnh (chế độ toàn trang).",
        "pages": [
            [
                E(
                    "picture",
                    x=40,
                    y=40,
                    w=515,
                    h=760,
                    children=[
                        E("text", "Điều 5. Phí dịch vụ", y=80),
                        E("text", "Phí rút tiền là 1.100 đồng mỗi giao dịch.", y=100),
                    ],
                )
            ]
        ],
        "ground_truth": "Điều 5. Phí dịch vụ Phí rút tiền là 1.100 đồng mỗi giao dịch.",
        "protected": ["1.100 đồng"],
        "expect_placeholders": 0,
    },
    {
        "name": "f17_signature_block",
        "description": "Khối chữ ký: tên, chức danh, chữ ký và con dấu (ảnh nhỏ không chữ).",
        "pages": [
            [
                E("text", "Quyết định này có hiệu lực kể từ ngày ký.", y=100),
                E("text", "Nơi nhận:", y=600, w=150),
                E("text", "- Như Điều 3;", y=615, w=150),
                E("text", "- Lưu VT.", y=630, w=150),
                E("text", "TM. HỘI ĐỒNG QUẢN TRỊ", x=340, y=600, w=180),
                E("text", "CHỦ TỊCH", x=380, y=615, w=100),
                signature(640),
                stamp(630),
                E("text", "Trần Thị Mẫu", x=380, y=720, w=100),
            ]
        ],
        "ground_truth": (
            "Quyết định này có hiệu lực kể từ ngày ký. Nơi nhận: - Như Điều 3; - Lưu VT. "
            "TM. HỘI ĐỒNG QUẢN TRỊ CHỦ TỊCH Trần Thị Mẫu"
        ),
        "expect_placeholders": 0,
        "present_lines": ["- Như Điều 3;", "- Lưu VT."],
    },
    {
        "name": "f18_literal_html_comment",
        "description": "Tài liệu kỹ thuật chứa chuỗi literal '<!-- image -->': phải giữ.",
        "pages": [
            [
                E(
                    "text",
                    "Trong mẫu HTML, ghi chú <!-- image --> đánh dấu vị trí ảnh.",
                    y=100,
                ),
                E("text", "Không được xóa chuỗi này khỏi tài liệu.", y=120),
            ]
        ],
        "ground_truth": "Trong mẫu HTML, ghi chú <!-- image --> đánh dấu vị trí ảnh. Không được xóa chuỗi này khỏi tài liệu.",
        "protected": ["&lt;!-- image --&gt;"],
        "expect_placeholders": 0,
    },
    {
        "name": "f19_hyphen_at_page_break",
        "description": "Từ có gạch nối ở cuối trang (khoản nhãn LIST_ITEM để Docling không tự bỏ gạch nối): không tự nối, có cảnh báo.",
        "pages": [
            [E("list_item", "3. Áp dụng cho tổ chức tín dụng phi-", y=740), footer(1)],
            [
                E("text", "ngân hàng và chi nhánh ngân hàng nước ngoài.", y=60),
                footer(2),
            ],
        ],
        "ground_truth": "3. Áp dụng cho tổ chức tín dụng phi- ngân hàng và chi nhánh ngân hàng nước ngoài.",
        "must_not_join": [["phi-", "ngân hàng và"]],
        "expect_warnings": ["hyphen_at_page_break_not_joined"],
    },
    {
        "name": "f20_finished_sentence_not_joined",
        "description": "Câu đã kết thúc bằng dấu chấm: trang sau bắt đầu chữ thường vẫn không nối.",
        "pages": [
            [
                E("text", "Đơn vị báo cáo trước ngày 05 hằng tháng.", y=740),
                page_number(1),
            ],
            [
                E("text", "trường hợp đặc biệt do Giám đốc quyết định.", y=60),
                page_number(2),
            ],
        ],
        "ground_truth": "Đơn vị báo cáo trước ngày 05 hằng tháng. trường hợp đặc biệt do Giám đốc quyết định.",
        "must_not_join": [["hằng tháng.", "trường hợp đặc biệt"]],
    },
    {
        "name": "f21_dash_paragraphs",
        "description": "Đoạn văn bắt đầu bằng gạch đầu dòng nhưng layout gán nhãn TEXT; đoạn bắt đầu bằng số.",
        "pages": [
            [
                E("text", "- Tiếp nhận hồ sơ của khách hàng;", y=100),
                E("text", "- Kiểm tra tính đầy đủ của hồ sơ.", y=120),
                E("text", "12. Thời hạn xử lý là 05 ngày làm việc.", y=140),
                E("text", "15. Kết quả được trả tại quầy.", y=160),
            ]
        ],
        "ground_truth": (
            "- Tiếp nhận hồ sơ của khách hàng; - Kiểm tra tính đầy đủ của hồ sơ. "
            "12. Thời hạn xử lý là 05 ngày làm việc. 15. Kết quả được trả tại quầy."
        ),
        "markers": ["-", "12.", "15."],
    },
    {
        "name": "f22_single_page_number_kept",
        "description": "Một trang duy nhất có số đứng riêng ở cuối: không đủ bằng chứng mẫu lặp, giữ nguyên.",
        "pages": [[E("text", "Văn bản một trang.", y=100), page_number(1)]],
        "ground_truth": "Văn bản một trang. 1",
        "present_lines": ["1"],
    },
    {
        "name": "f23_heading_at_page_top_not_removed",
        "description": "Tiêu đề chương ở đầu trang không bị coi là header.",
        "pages": [
            [E("text", "Nội dung chương một kết thúc tại đây.", y=740), page_number(1)],
            [
                E("section_header", "CHƯƠNG II", x=255, y=30, w=85, h=16),
                E("text", "Nội dung chương hai.", y=60),
                page_number(2),
            ],
            [
                E("section_header", "CHƯƠNG III", x=255, y=30, w=85, h=16),
                E("text", "Nội dung chương ba.", y=60),
                page_number(3),
            ],
        ],
        "ground_truth": "Nội dung chương một kết thúc tại đây. CHƯƠNG II Nội dung chương hai. CHƯƠNG III Nội dung chương ba.",
        "order": ["CHƯƠNG II", "Nội dung chương hai", "CHƯƠNG III"],
        "expect_removed": ["1", "2", "3"],
    },
    {
        "name": "f24_join_chain_and_footer_label",
        "description": "Đoạn kéo dài 3 trang; số trang được Docling gán đúng PAGE_FOOTER (đã là furniture).",
        "pages": [
            [E("text", "Đoạn văn rất dài bắt đầu ở trang một và", y=760), footer(1)],
            [
                E(
                    "text",
                    "tiếp tục suốt trang hai cho đến khi",
                    y=60,
                    h=700,
                    gt="join",
                ),
                footer(2),
            ],
            [E("text", "kết thúc ở đầu trang ba.", y=60, gt="join"), footer(3)],
        ],
        "ground_truth": "Đoạn văn rất dài bắt đầu ở trang một và tiếp tục suốt trang hai cho đến khi kết thúc ở đầu trang ba.",
        "expect_joined": [
            "Đoạn văn rất dài bắt đầu ở trang một và tiếp tục suốt trang hai cho đến khi kết thúc ở đầu trang ba."
        ],
    },
    # ------------------------------------------------------------------ #
    # Phase 12D3: counter-examples of the independent audit (PHASE12D2),
    # promoted to fixtures. Ground truth = the gt annotations above.
    # ------------------------------------------------------------------ #
    {
        "name": "f25_appendix_unit_line_every_page",
        "description": "F-01: phụ lục 3 trang, mỗi trang bắt đầu bằng 'Đơn vị tính: triệu đồng' — là nội dung, không phải header.",
        "pages": [
            [
                E("text", "Đơn vị tính: triệu đồng", x=380, y=62, w=145, h=14),
                E(
                    "text",
                    f"Chi nhánh {p} dư nợ cho vay ngắn hạn là {1500 + p}.",
                    y=120,
                    h=28,
                ),
                E(
                    "text",
                    f"Chi nhánh {p} dư nợ cho vay trung hạn là {2500 + p}.",
                    y=400,
                    h=28,
                ),
            ]
            for p in (1, 2, 3)
        ],
        "ground_truth": " ".join(
            f"Đơn vị tính: triệu đồng Chi nhánh {p} dư nợ cho vay ngắn hạn là {1500 + p}. "
            f"Chi nhánh {p} dư nợ cho vay trung hạn là {2500 + p}."
            for p in (1, 2, 3)
        ),
        "protected": [["Đơn vị tính: triệu đồng", 3], ["1501", 1], ["2503", 1]],
    },
    {
        "name": "f26_bundle_of_one_page_notices",
        "description": "F-01: bốn thông báo một trang scan chung một PDF; tên đơn vị ban hành và ghi chú ký lặp lại có chủ đích.",
        "pages": [
            [
                E("text", "NGÂN HÀNG THƯƠNG MẠI MẪU - CHI NHÁNH TỈNH", y=50, w=300),
                E(
                    "section_header",
                    f"THÔNG BÁO SỐ {p + 10}",
                    x=230,
                    y=110,
                    w=135,
                    h=18,
                ),
                E(
                    "text",
                    f"Thông báo lãi suất cho vay áp dụng từ tháng {p + 1} là {7 + p},5%/năm.",
                    y=160,
                    h=28,
                ),
                E("text", "(Ký, ghi rõ họ tên và đóng dấu)", x=330, y=770, w=190, h=12),
            ]
            for p in range(4)
        ],
        "ground_truth": " ".join(
            f"NGÂN HÀNG THƯƠNG MẠI MẪU - CHI NHÁNH TỈNH THÔNG BÁO SỐ {p + 10} "
            f"Thông báo lãi suất cho vay áp dụng từ tháng {p + 1} là {7 + p},5%/năm. (Ký, ghi rõ họ tên và đóng dấu)"
            for p in range(4)
        ),
        "protected": [
            ["NGÂN HÀNG THƯƠNG MẠI MẪU - CHI NHÁNH TỈNH", 4],
            ["(Ký, ghi rõ họ tên và đóng dấu)", 4],
            ["7,5%/năm", 1],
            ["10,5%/năm", 1],
        ],
    },
    {
        "name": "f27_years_at_page_bottom",
        "description": "F-02: ô cuối trang là số năm (cột bảng không được nhận diện) — không phải số trang.",
        "pages": [
            [
                E("text", "Kế hoạch tăng trưởng tín dụng năm:", y=120, h=28),
                E("text", "2024", x=450, y=780, w=40, h=12),
            ],
            [
                E("text", "Kế hoạch huy động vốn năm:", y=120, h=28),
                E("text", "2025", x=450, y=780, w=40, h=12),
            ],
            [
                E(
                    "text",
                    "Các nội dung khác thực hiện theo quy định hiện hành.",
                    y=120,
                    h=28,
                )
            ],
        ],
        "ground_truth": (
            "Kế hoạch tăng trưởng tín dụng năm: 2024 Kế hoạch huy động vốn năm: 2025 "
            "Các nội dung khác thực hiện theo quy định hiện hành."
        ),
        "protected": [["2024", 1], ["2025", 1]],
        "present_lines": ["2024", "2025"],
    },
    {
        "name": "f28_clause_numbers_at_page_top",
        "description": "F-02: OCR tách số khoản khỏi nội dung; số đứng đầu trang ở lề trái thân.",
        "pages": [
            [E("text", "Điều 4. Quyền của khách hàng.", y=120, h=28)],
            [
                E("text", "2", x=70, y=62, w=10, h=12),
                E(
                    "text",
                    "Khách hàng có quyền từ chối các yêu cầu trái thỏa thuận.",
                    y=100,
                    h=28,
                ),
            ],
            [
                E("text", "3", x=70, y=62, w=10, h=12),
                E(
                    "text",
                    "Khách hàng có quyền khiếu nại theo quy định của pháp luật.",
                    y=100,
                    h=28,
                ),
            ],
        ],
        "ground_truth": (
            "Điều 4. Quyền của khách hàng. 2 Khách hàng có quyền từ chối các yêu cầu trái thỏa thuận. "
            "3 Khách hàng có quyền khiếu nại theo quy định của pháp luật."
        ),
        "present_lines": ["2", "3"],
    },
    {
        "name": "f29_footnote_labelled_text",
        "description": "F-03: footnote nhãn TEXT nằm giữa đoạn bị cắt và phần nối — không được ghép footnote với trang sau.",
        "pages": [
            [
                E("text", "Điều 3. Mức cho vay.", y=120, h=28),
                E(
                    "text",
                    "Mức cho vay tối đa được xác định căn cứ vào nhu cầu vay vốn và khả năng hoàn trả nợ của",
                    y=600,
                    h=28,
                ),
                E("text", "1 Thông tư số 39/2016/TT-NHNN", y=760, h=12, w=200),
            ],
            [
                E(
                    "text",
                    "khách hàng theo quy định tại Điều 5 Quy chế này.",
                    y=100,
                    h=14,
                ),
                E("text", "Điều 4. Thời hạn cho vay.", y=200, h=28),
            ],
        ],
        "ground_truth": (
            "Điều 3. Mức cho vay. Mức cho vay tối đa được xác định căn cứ vào nhu cầu vay vốn và khả năng hoàn trả nợ của "
            "1 Thông tư số 39/2016/TT-NHNN khách hàng theo quy định tại Điều 5 Quy chế này. Điều 4. Thời hạn cho vay."
        ),
        "protected": [["39/2016/TT-NHNN", 1]],
        "must_not_join": [["39/2016/TT-NHNN", "khách hàng theo quy định"]],
    },
    {
        "name": "f30_two_page_running_footer",
        "description": "F-03: tài liệu 2 trang có footer 'Lưu hành nội bộ' (nhãn TEXT) — không được ghép footer với thân trang sau.",
        "pages": [
            [
                E("text", "Điều 3. Mức cho vay.", y=120, h=28),
                E(
                    "text",
                    "Mức cho vay tối đa được xác định căn cứ vào nhu cầu vay vốn và khả năng trả nợ.",
                    y=600,
                    h=28,
                ),
                E("text", "Lưu hành nội bộ", y=790, h=12, w=200, gt="artifact"),
            ],
            [
                E(
                    "text",
                    "trong trường hợp đặc biệt, Tổng Giám đốc quyết định mức cho vay.",
                    y=100,
                    h=14,
                ),
                E("text", "Điều 4. Thời hạn cho vay.", y=200, h=28),
                E("text", "Lưu hành nội bộ", y=790, h=12, w=200, gt="artifact"),
            ],
        ],
        "ground_truth": (
            "Điều 3. Mức cho vay. Mức cho vay tối đa được xác định căn cứ vào nhu cầu vay vốn và khả năng trả nợ. "
            "trong trường hợp đặc biệt, Tổng Giám đốc quyết định mức cho vay. Điều 4. Thời hạn cho vay."
        ),
        "must_not_join": [["Lưu hành nội bộ", "trong trường hợp"]],
    },
]

_POINT_STYLES = {
    "a_dot": ("a. Giấy đề nghị vay vốn;", "b. Phương án sử dụng vốn."),
    "a_slash": ("a/ Giấy đề nghị vay vốn;", "b/ Phương án sử dụng vốn."),
    "dd_dot": ("đ. Giấy đề nghị vay vốn;", "e. Phương án sử dụng vốn."),
    "paren": ("(a) giấy đề nghị vay vốn;", "(b) phương án sử dụng vốn."),
    "a_1": ("a.1) giấy đề nghị vay vốn;", "a.2) phương án sử dụng vốn."),
    "dd_paren": ("đ) giấy đề nghị vay vốn;", "e) phương án sử dụng vốn."),
}
for _style, (_first, _second) in _POINT_STYLES.items():
    FIXTURES.append(
        {
            "name": f"f31_lettered_points_{_style}",
            "description": f"F-03: điểm kiểu '{_first.split(' ')[0]}' ở đầu trang sau là đơn vị mới, không phải phần nối của câu dẫn.",
            "pages": [
                [
                    E("text", "Điều 6. Hồ sơ vay vốn.", y=120, h=28),
                    E("text", "2. Hồ sơ vay vốn bao gồm các giấy tờ", y=700, h=14),
                ],
                [E("text", _first, y=100, h=14), E("text", _second, y=130, h=14)],
            ],
            "ground_truth": f"Điều 6. Hồ sơ vay vốn. 2. Hồ sơ vay vốn bao gồm các giấy tờ {_first} {_second}",
            "must_not_join": [["bao gồm các giấy tờ", _first.split(" ")[0]]],
            "present_lines": [_first, _second],
        }
    )

FIXTURES += [
    {
        "name": "f32_pictures_5_12_20_percent",
        "description": "F-06: ảnh không chữ 5%, 12%, 20% diện tích trang (bảng lãi suất scan, sơ đồ) phải để lại dấu vết.",
        "pages": [
            [
                E("text", "Biểu lãi suất áp dụng:", y=60, h=14),
                E("picture", x=70, y=90, w=200, h=125),  # 5.0 %
                E("text", "Sơ đồ quy trình phê duyệt:", y=240, h=14),
                E("picture", x=70, y=270, w=300, h=200),  # 12.0 %
                E("text", "Biểu đồ dư nợ theo năm:", y=490, h=14),
                E("picture", x=70, y=520, w=400, h=250),  # 20.0 %
            ]
        ],
        "ground_truth": "Biểu lãi suất áp dụng: Sơ đồ quy trình phê duyệt: Biểu đồ dư nợ theo năm:",
        "expect_placeholders": 3,
        "expect_warnings": ["picture_without_text"],
    },
    {
        "name": "f33_five_pages_real_page_numbers_and_join",
        "description": "Đủ bằng chứng: 5 trang có số trang thật ở giữa cuối trang (nhãn TEXT) và khoản 9 bị cắt qua trang.",
        "pages": [
            [
                E("section_header", "Điều 3. Giải thích từ ngữ", y=80),
                E(
                    "text",
                    "Trong Quy định này, các từ ngữ được hiểu như sau.",
                    y=110,
                    h=28,
                ),
                page_number(5),
            ],
            [
                E(
                    "list_item",
                    "8. Dịch vụ tài chính là dịch vụ làm thay đổi số dư tài khoản.",
                    y=700,
                    h=28,
                ),
                E(
                    "list_item",
                    "9. Dịch vụ phi tài chính là dịch vụ không làm thay đổi số",
                    y=735,
                    h=28,
                ),
                page_number(6),
            ],
            [
                E("text", "dư trên tài khoản của khách hàng.", y=60, gt="join"),
                E(
                    "list_item",
                    "10. Ngày làm việc là các ngày từ thứ Hai đến thứ Sáu.",
                    y=85,
                ),
                page_number(7),
            ],
            [
                E("section_header", "Điều 4. Phạm vi áp dụng", y=60),
                E("text", "Quy định áp dụng trong toàn hệ thống.", y=90, h=28),
                page_number(8),
            ],
            [
                E("section_header", "Điều 5. Hiệu lực", y=60),
                E("text", "Quy định có hiệu lực từ ngày 01/01/2025.", y=90, h=28),
                page_number(9),
            ],
        ],
        "ground_truth": (
            "Điều 3. Giải thích từ ngữ Trong Quy định này, các từ ngữ được hiểu như sau. "
            "8. Dịch vụ tài chính là dịch vụ làm thay đổi số dư tài khoản. "
            "9. Dịch vụ phi tài chính là dịch vụ không làm thay đổi số dư trên tài khoản của khách hàng. "
            "10. Ngày làm việc là các ngày từ thứ Hai đến thứ Sáu. Điều 4. Phạm vi áp dụng "
            "Quy định áp dụng trong toàn hệ thống. Điều 5. Hiệu lực Quy định có hiệu lực từ ngày 01/01/2025."
        ),
        "markers": ["8.", "9.", "10."],
        "protected": [["01/01/2025", 1]],
        "expect_removed": ["5", "6", "7", "8", "9"],
        "expect_joined": [
            "9. Dịch vụ phi tài chính là dịch vụ không làm thay đổi số dư trên tài khoản của khách hàng."
        ],
    },
    {
        "name": "f34_five_pages_detached_clause_numbers",
        "description": "F-02: số khoản 2, 3, 4 bị OCR tách ra, đứng đầu trang 2-4 tại lề trái của thân (5 trang) — phải giữ.",
        "pages": [
            [E("text", "Điều 4. Quyền của khách hàng.", y=120, h=28)],
            [
                E("text", "2", x=70, y=62, w=10, h=12),
                E(
                    "text",
                    "Khách hàng có quyền từ chối các yêu cầu trái thỏa thuận.",
                    y=100,
                    h=28,
                ),
            ],
            [
                E("text", "3", x=70, y=62, w=10, h=12),
                E(
                    "text",
                    "Khách hàng có quyền khiếu nại theo quy định của pháp luật.",
                    y=100,
                    h=28,
                ),
            ],
            [
                E("text", "4", x=70, y=62, w=10, h=12),
                E("text", "Khách hàng có quyền được bảo mật thông tin.", y=100, h=28),
            ],
            [E("text", "Điều 5. Nghĩa vụ của khách hàng.", y=100, h=28)],
        ],
        "ground_truth": (
            "Điều 4. Quyền của khách hàng. 2 Khách hàng có quyền từ chối các yêu cầu trái thỏa thuận. "
            "3 Khách hàng có quyền khiếu nại theo quy định của pháp luật. 4 Khách hàng có quyền được bảo mật thông tin. "
            "Điều 5. Nghĩa vụ của khách hàng."
        ),
        "present_lines": ["2", "3", "4"],
    },
    {
        "name": "f35_unrecognised_table_repeated_column_headers",
        "description": "F-01/F-02: bảng không được nhận diện; tiêu đề cột lặp ở đầu mỗi trang và số liệu đứng riêng ở cuối trang.",
        "pages": [
            [
                E("text", "STT", x=70, y=60, w=30, h=12),
                E("text", "CHỈ TIÊU", x=120, y=60, w=60, h=12),
                E("text", "SỐ TIỀN", x=420, y=60, w=60, h=12),
                E("text", str(p), x=70, y=400, w=10, h=12),
                E("text", f"Dư nợ nhóm {p}", x=120, y=400, w=120, h=12),
                E("text", str(100 + p), x=420, y=790, w=30, h=12),
            ]
            for p in (1, 2, 3, 4)
        ],
        "ground_truth": " ".join(
            f"STT CHỈ TIÊU SỐ TIỀN {p} Dư nợ nhóm {p} {100 + p}" for p in (1, 2, 3, 4)
        ),
        "protected": [["STT", 4], ["SỐ TIỀN", 4], ["101", 1], ["104", 1]],
        "present_lines": ["101", "102", "103", "104"],
    },
    {
        "name": "f36_six_pages_mirrored_page_numbers",
        "description": "Đủ bằng chứng: số trang ở lề ngoài, trang lẻ bên phải / trang chẵn bên trái (6 trang).",
        "pages": [
            [
                E(
                    "text",
                    f"Nội dung chính của trang thứ {n} trong quy định mẫu.",
                    y=100,
                    h=28,
                ),
                E(
                    "text",
                    str(n),
                    x=520 if n % 2 else 60,
                    y=805,
                    w=14,
                    h=12,
                    gt="artifact",
                ),
            ]
            for n in range(1, 7)
        ],
        "ground_truth": " ".join(
            f"Nội dung chính của trang thứ {n} trong quy định mẫu." for n in range(1, 7)
        ),
        "expect_removed": ["1", "2", "3", "4", "5", "6"],
    },
    {
        "name": "f37_repeated_business_lines",
        "description": "F-01: 'Kính gửi', 'Nơi nhận', 'Căn cứ', tiêu đề phụ lục, tên các bên lặp trên mọi trang của bộ văn bản.",
        "pages": [
            [
                E("text", "Kính gửi: Các chi nhánh trong hệ thống", y=40, w=300, h=12),
                E("text", "PHỤ LỤC HỢP ĐỒNG", x=230, y=62, w=135, h=14),
                E(
                    "text",
                    f"Căn cứ Quyết định số {p}0/QĐ-NHM ngày 0{p}/01/2025;",
                    y=120,
                    h=28,
                ),
                E("text", "Bên A: Ngân hàng Thương mại Mẫu", y=760, w=300, h=12),
                E("text", "Nơi nhận: Như trên; Lưu VT", y=790, w=300, h=12),
            ]
            for p in (1, 2, 3, 4)
        ],
        "ground_truth": " ".join(
            "Kính gửi: Các chi nhánh trong hệ thống PHỤ LỤC HỢP ĐỒNG "
            f"Căn cứ Quyết định số {p}0/QĐ-NHM ngày 0{p}/01/2025; Bên A: Ngân hàng Thương mại Mẫu Nơi nhận: Như trên; Lưu VT"
            for p in (1, 2, 3, 4)
        ),
        "protected": [
            ["Kính gửi: Các chi nhánh trong hệ thống", 4],
            ["PHỤ LỤC HỢP ĐỒNG", 4],
            ["Bên A: Ngân hàng Thương mại Mẫu", 4],
            ["Nơi nhận: Như trên; Lưu VT", 4],
        ],
    },
    {
        "name": "f38_two_columns_across_pages",
        "description": "Hai cột qua hai trang: không ghép giữa hai cột khác nhau (cuối cột phải trang 1 với đầu cột trái trang 2).",
        "pages": [
            [
                E(
                    "text",
                    "Cột trái trang một nói về điều kiện vay vốn của khách hàng.",
                    x=70,
                    y=100,
                    w=210,
                    h=640,
                ),
                E(
                    "text",
                    "Cột phải trang một nói về thời hạn và lãi suất áp dụng và",
                    x=315,
                    y=100,
                    w=210,
                    h=660,
                ),
            ],
            [
                E(
                    "text",
                    "cột trái trang hai tiếp tục một nội dung khác hẳn.",
                    x=70,
                    y=100,
                    w=210,
                    h=300,
                ),
                E(
                    "text",
                    "Cột phải trang hai kết thúc văn bản.",
                    x=315,
                    y=100,
                    w=210,
                    h=300,
                ),
            ],
        ],
        "ground_truth": (
            "Cột trái trang một nói về điều kiện vay vốn của khách hàng. Cột phải trang một nói về thời hạn và lãi suất áp dụng và "
            "cột trái trang hai tiếp tục một nội dung khác hẳn. Cột phải trang hai kết thúc văn bản."
        ),
        "must_not_join": [["lãi suất áp dụng và", "cột trái trang hai"]],
    },
    {
        "name": "f39_text_then_table_across_pages",
        "description": "Đoạn chưa kết thúc ở cuối trang, trang sau bắt đầu bằng bảng rồi tới đoạn chữ thường: không ghép qua bảng.",
        "pages": [
            [
                E("text", "Biểu phí áp dụng cho các dịch vụ sau đây gồm", y=700, h=28),
                page_number(1),
            ],
            [
                E(
                    "table",
                    y=60,
                    h=60,
                    rows=[["STT", "Dịch vụ", "Phí"], ["1", "Chuyển tiền", "2.200"]],
                ),
                E("text", "phí trên đã bao gồm thuế giá trị gia tăng.", y=140, h=14),
                page_number(2),
            ],
            [E("text", "Điều 9. Tổ chức thực hiện.", y=60, h=28), page_number(3)],
        ],
        "ground_truth": (
            "Biểu phí áp dụng cho các dịch vụ sau đây gồm STT Dịch vụ Phí 1 Chuyển tiền 2.200 "
            "phí trên đã bao gồm thuế giá trị gia tăng. Điều 9. Tổ chức thực hiện."
        ),
        "protected": [["2.200", 1]],
        "table_identical": True,
        "must_not_join": [["sau đây gồm", "phí trên đã bao gồm"]],
        "expect_removed": ["1", "2", "3"],
    },
    {
        "name": "f40_caption_and_picture_text",
        "description": "F-06: ảnh có caption và ảnh có chữ OCR bên trong — caption và chữ phải còn; literal HTML comment giữ nguyên.",
        "pages": [
            [
                E(
                    "text",
                    "Mẫu biểu có ghi chú <!-- image --> trong mã nguồn.",
                    y=60,
                    h=14,
                ),
                E("caption", "Hình 1. Sơ đồ tổ chức chi nhánh", y=90, h=14),
                E("picture", x=70, y=110, w=300, h=200),
                E(
                    "picture",
                    x=70,
                    y=340,
                    w=455,
                    h=200,
                    children=[
                        E("text", "Lãi suất kỳ hạn 12 tháng: 5,2%/năm", y=380),
                        E("text", "Lãi suất kỳ hạn 24 tháng: 5,8%/năm", y=420),
                    ],
                ),
            ]
        ],
        "ground_truth": (
            "Mẫu biểu có ghi chú <!-- image --> trong mã nguồn. Hình 1. Sơ đồ tổ chức chi nhánh "
            "Lãi suất kỳ hạn 12 tháng: 5,2%/năm Lãi suất kỳ hạn 24 tháng: 5,8%/năm"
        ),
        "protected": [
            ["5,2%/năm", 1],
            ["5,8%/năm", 1],
            ["Hình 1. Sơ đồ tổ chức chi nhánh", 1],
        ],
    },
]


# --------------------------------------------------------------------------- #
# Phase 12D5 (12D5A, findings R2-14 / T-03): the counter-examples of the Phase
# 12D4 re-review, the ORIGINAL form of fixtures that Phase 12D3 had reworded so
# that Docling's own merge never triggered, and position / label / Unicode-tail
# variants of every threshold. The ground truth below was declared BEFORE the
# Phase 12D5 normalizer changes and is not adjusted to any implementation: the
# first benchmark of it ran on the unchanged 8d0c438 code
# (docs/review/phase12d5/benchmark_8d0c438.json).
# --------------------------------------------------------------------------- #

FILLER = "của trang này trình bày nội dung nghiệp vụ thông thường."


def _fill(y: float, n: int = 1, tag: str = "") -> list[dict[str, Any]]:
    """``n`` finished body paragraphs (two lines each) from ``y`` down."""
    return [
        E("text", f"Đoạn văn số {i}{tag} {FILLER}", y=y + 40 * i, h=28)
        for i in range(n)
    ]


def _truth(pages: list[list[dict[str, Any]]]) -> str:
    """The clean text: every required element, in declared order."""
    out = []
    for page in pages:
        for el in page:
            if el.get("gt") in ("artifact", "furniture", "decoration"):
                continue
            if el["label"] == "picture":
                out += [c["text"] for c in el.get("children", [])]
            elif el["label"] == "table":
                out += [" ".join(row) for row in el["rows"]]
            elif el.get("text"):
                out.append(el["text"])
    return " ".join(out)


def _d5(
    name: str, description: str, pages: list[list[dict[str, Any]]], **extra: Any
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "pages": pages,
        "ground_truth": _truth(pages),
        "d5": True,
        **extra,
    }


def _pn(
    n: int, x: float = 290, top: bool = False, label: str = "text"
) -> dict[str, Any]:
    """A real page number: TEXT-labelled -> artifact, PAGE_FOOTER/HEADER -> furniture."""
    gt = "artifact" if label == "text" else "furniture"
    return E(label, str(n), x=x, y=30 if top else 800, w=16, h=12, gt=gt)


_RIGHTS = [
    "Khách hàng có quyền từ chối các yêu cầu trái với thỏa thuận đã ký kết với ngân hàng.",
    "Khách hàng có quyền khiếu nại theo quy định của pháp luật và quy định nội bộ.",
    "Khách hàng có quyền được bảo mật thông tin theo quy định của pháp luật.",
]
_RIGHTS_TAIL = "Việc thực hiện quyền này tuân theo hợp đồng và quy định của pháp luật có liên quan."


def _clause_numbers(x: float) -> list[list[dict[str, Any]]]:
    """Clause numbers 2, 3, 4 that OCR split off their paragraph, at the top of pages 2-4."""
    pages = [[E("text", "Điều 4. Quyền của khách hàng.", y=120, h=28)]]
    for i, text in enumerate(_RIGHTS):
        pages.append(
            [
                E("text", str(i + 2), x=x, y=62, w=10, h=12),
                E("text", text, y=62, h=28),
                E("text", _RIGHTS_TAIL, y=110, h=28),
            ]
        )
    pages.append([E("text", "Điều 5. Nghĩa vụ của khách hàng.", y=100, h=28)])
    return pages


_FOOTNOTE = (
    "Mức lãi suất nêu trên áp dụng đối với khoản vay có tài sản bảo đảm theo Quyết định số "
    "123/2024/QĐ-NHM ngày 01/7/2024"
)
_CUT = "Mức cho vay tối đa được xác định căn cứ vào nhu cầu vay vốn và khả năng hoàn trả nợ của"
_CONTINUATION = "khách hàng theo quy định tại Điều 5 Quy chế này."
_POINT_B = "b) Tổ chức tín dụng phi ngân hàng được Ngân hàng Nhà nước cấp phép thành lập và hoạt động"
_LEAD = "2. Hồ sơ vay vốn bao gồm các giấy tờ"
_BODY = (
    "Khách hàng có trách nhiệm hoàn trả đầy đủ nợ gốc và lãi tiền vay theo đúng thời hạn đã "
    "thỏa thuận trong hợp đồng tín dụng đã ký"
)


def _footnote_case(mark: str) -> list[list[dict[str, Any]]]:
    return [
        _fill(100, 2)
        + [E("text", _CUT, y=600, h=28), E("text", mark + _FOOTNOTE, y=735, h=24)],
        [E("text", _CONTINUATION, y=62, h=14)] + _fill(100, 2, "b"),
    ]


def _new_unit_case(label: str, first: str, second: str) -> list[list[dict[str, Any]]]:
    return [
        _fill(100, 3) + [E(label, first, y=700, h=28)],
        [E("text", second, y=62, h=14)] + _fill(100, 2, "b"),
    ]


def _top_line_case(header: str) -> list[list[dict[str, Any]]]:
    return [
        _fill(100, 3) + [E("text", _BODY, y=700, h=42)],
        [
            E("text", header, y=30, w=250, h=12),
            E("text", "và các phụ lục kèm theo hợp đồng.", y=62, h=14),
        ]
        + _fill(100, 2, "b"),
        _fill(100, 2, "c"),
    ]


def _cut_paragraph(first_end: str, second: str) -> list[list[dict[str, Any]]]:
    """A paragraph really cut by the page break: the continuation may be joined."""
    return [
        _fill(100, 3)
        + [
            E(
                "text",
                f"Ngân hàng xem xét hồ sơ và thông báo kết quả cho {first_end}",
                y=740,
                h=14,
            )
        ],
        [E("text", second, y=62, h=14, gt="join")] + _fill(100, 2, "b"),
    ]


def _T(
    label: str,
    text: str,
    top: float,
    left: float = 70.0,
    right: float = 525.0,
    height: float = 14.0,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "label": label,
        "text": text,
        "bbox": [left, top, right, top + height],
        **extra,
    }


def _footer(n: int) -> dict[str, Any]:
    return _T("page_footer", str(n), 800, 290, 306, 12, gt="furniture")


FIXTURES += [
    # ---- F-02: numbers that are CONTENT and follow the page index --------------
    _d5(
        "d5_f02_clause_numbers_first_line_indent",
        "Số khoản 2, 3, 4 tách rời ở vị trí thụt đầu dòng (x = 98); đoạn văn ở x = 70 (12D4).",
        _clause_numbers(98),
        present_lines=["2", "3", "4"],
    ),
    _d5(
        "d5_f02_clause_numbers_hanging_indent",
        "Biến thể vị trí: số khoản ở lề treo (x = 42, ngoài lề đoạn văn 28 pt).",
        _clause_numbers(42),
        present_lines=["2", "3", "4"],
    ),
    _d5(
        "d5_f02_voucher_numbers_beside_label",
        "Bộ chứng từ một trang: 'Số:' và '0001'…'0004' là hai ô cùng dòng (12D4).",
        [
            [
                E("text", "Số:", x=400, y=40, w=30, h=12),
                E("text", f"{p:04d}", x=440, y=40, w=40, h=12),
                E("section_header", "GIẤY NỘP TIỀN", x=230, y=110, w=135, h=18),
                E(
                    "text",
                    f"Người nộp tiền: Khách hàng mẫu {p}. Số tiền: {p}5.000.000 đồng.",
                    y=160,
                    h=28,
                ),
                E("text", "(Ký, ghi rõ họ tên)", x=330, y=700, w=190, h=12),
            ]
            for p in range(1, 5)
        ],
        protected=[[f"{p:04d}", 1] for p in range(1, 5)],
        upstream_reordering="Docling's ReadingOrderModel reads this layout in another order (the standard export too): verify on real scans, Windows Local W-RC-10",
    ),
    _d5(
        "d5_f02_voucher_numbers_alone_top_right",
        "Biến thể nhãn: số chứng từ '0001'…'0005' đứng một mình ở góc phải trên (số 0 đứng đầu).",
        [
            [
                E("text", f"{p:04d}", x=480, y=30, w=40, h=12),
                E("section_header", "PHIẾU THU", x=250, y=110, w=95, h=18),
                E(
                    "text",
                    f"Thu của khách hàng mẫu số {p} khoản phí dịch vụ tháng này.",
                    y=160,
                    h=28,
                ),
            ]
            for p in range(1, 6)
        ],
        protected=[[f"{p:04d}", 1] for p in range(1, 6)],
        upstream_reordering="Docling's ReadingOrderModel reads this layout in another order (the standard export too): verify on real scans, Windows Local W-RC-10",
    ),
    _d5(
        "d5_f02_reporting_periods_beside_label",
        "'Kỳ báo cáo:' và '1/2024'…'4/2024' là hai ô cùng dòng (12D4).",
        [
            [
                E("text", "Kỳ báo cáo:", x=360, y=40, w=70, h=12),
                E("text", f"{p}/2024", x=440, y=40, w=50, h=12),
                E("section_header", "BÁO CÁO DƯ NỢ", x=230, y=110, w=135, h=18),
                E("text", f"Dư nợ cuối kỳ là {p}50 tỷ đồng.", y=160, h=28),
            ]
            for p in range(1, 5)
        ],
        protected=[[f"{p}/2024", 1] for p in range(1, 5)],
    ),
    _d5(
        "d5_f02_reporting_periods_alone_bottom_centre",
        "Biến thể vị trí: kỳ báo cáo '1/2024'…'5/2024' một mình ở giữa đáy trang (dạng n/yyyy).",
        [
            [
                E("section_header", "BÁO CÁO THÁNG", x=230, y=110, w=135, h=18),
                E(
                    "text",
                    f"Số liệu của tháng {p} năm 2024 được tổng hợp như sau.",
                    y=160,
                    h=28,
                ),
                E("text", f"{p}/2024", x=280, y=800, w=40, h=12),
            ]
            for p in range(1, 6)
        ],
        protected=[[f"{p}/2024", 1] for p in range(1, 6)],
    ),
    _d5(
        "d5_f02_numbers_inside_the_body",
        "Số liệu trong thân trang (giữa trang), tăng theo trang: không bao giờ là số trang.",
        [
            [
                E(
                    "text",
                    f"Chỉ tiêu số {p} của báo cáo được tính như sau.",
                    y=300,
                    h=14,
                ),
                E("text", str(p), x=290, y=330, w=16, h=12),
                E("text", f"Đoạn giải thích cho chỉ tiêu số {p}.", y=360, h=14),
            ]
            for p in range(1, 6)
        ],
        present_lines=["1", "2", "3", "4", "5"],
    ),
    _d5(
        "d5_f02_true_page_numbers_bottom_centre",
        "Đối chứng: số trang thật nhãn TEXT ở giữa đáy 5 trang (được phép bỏ).",
        [
            [
                E(
                    "text",
                    f"Nội dung trang {p} của quy định về dịch vụ ngân hàng điện tử.",
                    y=100,
                    h=28,
                ),
                _pn(p),
            ]
            for p in range(1, 6)
        ],
    ),
    _d5(
        "d5_f02_true_page_numbers_top_right",
        "Đối chứng: số trang thật nhãn TEXT ở góc phải trên 5 trang (được phép bỏ).",
        [
            [
                _pn(p, x=505, top=True),
                E(
                    "text",
                    f"Nội dung trang {p} của quy định về dịch vụ thẻ.",
                    y=100,
                    h=28,
                ),
            ]
            for p in range(1, 6)
        ],
    ),
    _d5(
        "d5_f02_page_number_and_clause_number_alias",
        "Số trang '2' (giữa trên) và số khoản '2' (x = 98) cùng chữ trên cùng trang (12D4, oracle R2-14).",
        [
            [_pn(1, top=True), E("text", "Điều 4. Quyền của khách hàng.", y=120, h=28)],
            [
                _pn(2, top=True),
                E("text", "2", x=98, y=62, w=10, h=12),
                E("text", "Khách hàng có quyền từ chối.", y=100, h=14),
            ],
            [
                _pn(3, top=True),
                E("text", "3", x=98, y=62, w=10, h=12),
                E("text", "Khách hàng có quyền khiếu nại.", y=100, h=14),
            ],
            [
                _pn(4, top=True),
                E("text", "4", x=98, y=62, w=10, h=12),
                E("text", "Khách hàng có quyền được bảo mật thông tin.", y=100, h=14),
            ],
        ],
        upstream_reordering="Docling's ReadingOrderModel reads this layout in another order (the standard export too): verify on real scans, Windows Local W-RC-10",
    ),
    # ---- F-03: the normalizer must not create a sentence across the break -------
    *[
        _d5(
            f"d5_f03_footnote_{slug}",
            f"Footnote nhãn TEXT rộng hết cột, ký hiệu {mark!r}, nằm dưới đoạn bị cắt (12D4).",
            _footnote_case(mark),
            must_not_join=[[(mark + _FOOTNOTE)[-20:], _CONTINUATION[:20]]],
        )
        for slug, mark in (
            ("paren_star", "(*) "),
            ("number_dot", "1. "),
            ("superscript", "¹ "),
            ("no_marker", ""),
        )
    ],
    *[
        _d5(
            f"d5_f03_{slug}",
            f"Dòng đầu trang sau mở đơn vị mới ({why}) (12D4).",
            _new_unit_case(label, first, second),
            must_not_join=[[first[-20:], second[:15]]],
        )
        for slug, label, first, second, why in (
            (
                "point_c_space_paren",
                "list_item",
                _POINT_B,
                "c ) khách hàng cá nhân là người cư trú;",
                "OCR chèn khoảng trắng 'c )'",
            ),
            (
                "point_marker_lost",
                "list_item",
                _POINT_B,
                "khách hàng cá nhân là người cư trú;",
                "mất marker",
            ),
            (
                "hollow_bullet_as_o",
                "list_item",
                _POINT_B,
                "o khách hàng cá nhân là người cư trú;",
                "bullet rỗng đọc thành 'o'",
            ),
            ("point_a_comma", "text", _LEAD, "a, giấy đề nghị vay vốn;", "marker 'a,'"),
            ("point_a_dash", "text", _LEAD, "a- giấy đề nghị vay vốn;", "marker 'a-'"),
            (
                "date_line",
                "list_item",
                "5. Hợp đồng này được lập thành 02 bản có giá trị pháp lý như nhau, mỗi bên giữ 01 bản",
                "ngày 15 tháng 7 năm 2024",
                "dòng ngày tháng",
            ),
            (
                "unit_line",
                "text",
                "Biểu tổng hợp dư nợ cho vay theo nhóm nợ của toàn hệ thống tại thời điểm 31/12/2024",
                "đvt: triệu đồng",
                "dòng đơn vị tính",
            ),
            (
                "trong_do_line",
                "text",
                "Tổng dư nợ cho vay của chi nhánh tại thời điểm báo cáo là 1.250 tỷ đồng",
                "trong đó: dư nợ ngắn hạn 700 tỷ đồng;",
                "dòng 'trong đó:'",
            ),
        )
    ],
    *[
        _d5(
            f"d5_f03_top_line_{slug}",
            f"Dòng đầu trang sau là {why}, phần tiếp theo thật nằm ngay dưới (12D4).",
            _top_line_case(header),
            must_not_join=[[_BODY[-20:], header[:15]]],
        )
        for slug, header, why in (
            (
                "running_title",
                "quy chế cho vay tiêu dùng - lưu hành nội bộ",
                "tiêu đề chạy viết thường",
            ),
            ("web_address", "www.nganhangmau.example.vn", "địa chỉ web"),
            ("page_of_pages", "trang 2/3", "'trang 2/3'"),
        )
    ],
    *[
        _d5(
            f"d5_f03_genuine_cut_{slug}",
            f"Đối chứng: đoạn văn thật bị ngắt trang, đuôi {why}; phần tiếp theo ĐƯỢC PHÉP nối.",
            _cut_paragraph(first_end, second),
        )
        for slug, first_end, second, why in (
            (
                "ascii_tail",
                "khách hàng theo",
                "quy định tại Điều 7 của Quy chế này.",
                "chữ ASCII",
            ),
            (
                "vietnamese_tail",
                "khách hàng trong thời hạn được",
                "thỏa thuận tại hợp đồng tín dụng.",
                "chữ có dấu",
            ),
            (
                "comma_tail",
                "khách hàng,",
                "đồng thời lưu hồ sơ theo quy định.",
                "dấu phẩy",
            ),
        )
    ],
    # ---- R2-01: Docling's OWN merge across a page / a column ------------------
    _d5(
        "d5_r201_two_documents_signer_then_title",
        "Hai văn bản độc lập: tên người ký cuối văn bản 1 và tiêu đề phụ lục đầu trang sau (12D4).",
        [
            [
                _T("section_header", "QUYẾT ĐỊNH", 80),
                _T(
                    "text",
                    "Điều 1. Ban hành kèm theo Quyết định này Quy định về phí dịch vụ.",
                    120,
                ),
                _T("text", "TỔNG GIÁM ĐỐC", 600, 330, 525),
                _T("text", "Nguyễn Văn An", 700, 340, 515),
                _footer(1),
            ],
            [
                _T("text", "Phụ lục 01 ban hành kèm theo Quyết định số 12/QĐ-NHM", 80),
                _T("text", "Mức phí chuyển tiền là 11.000 đồng mỗi giao dịch.", 120),
                _footer(2),
            ],
        ],
        must_not_join=[["Nguyễn Văn An", "Phụ lục 01"]],
    ),
    _d5(
        "d5_r201_clause_then_next_article",
        "Khoản cuối trang (nhãn TEXT) và 'Điều 5.' đầu trang sau (12D4).",
        [
            [
                _T("text", "Điều 4. Phạm vi áp dụng", 80),
                _T("text", "Quy định này áp dụng đối với toàn bộ khách hàng", 700),
                _footer(1),
            ],
            [
                _T("text", "Điều 5. Hiệu lực thi hành", 80),
                _T("text", "Quy định có hiệu lực từ ngày 01/01/2025.", 120),
                _footer(2),
            ],
        ],
        must_not_join=[["toàn bộ khách hàng", "Điều 5."]],
    ),
    _d5(
        "d5_r201_footnote_then_continuation",
        "Footnote nhãn TEXT và phần tiếp theo của đoạn ở trang sau (12D4).",
        [
            [
                _T(
                    "text",
                    "Khách hàng được miễn phí khi duy trì số dư tối thiểu theo quy định của",
                    660,
                ),
                _T(
                    "text",
                    "Theo Thông tư số 39/2016/TT-NHNN của Ngân hàng Nhà nước về cho vay",
                    770,
                    70,
                    525,
                    12,
                ),
                _footer(1),
            ],
            [_T("text", "ngân hàng trong từng thời kỳ.", 80), _footer(2)],
        ],
        must_not_join=[["về cho vay", "ngân hàng trong"]],
    ),
    _d5(
        "d5_r201_side_note_same_page",
        "Ghi chú bên phải một dòng thân văn bản, cùng trang (12D4).",
        [
            [
                _T(
                    "text",
                    "Lãi suất cho vay ngắn hạn tối đa theo thông báo từng",
                    300,
                    70,
                    300,
                ),
                _T("text", "Ghi chú: áp dụng từ quý I", 300, 320, 525),
                _T("text", "thời kỳ của Tổng Giám đốc.", 330, 70, 300),
            ]
        ],
        must_not_join=[["thông báo từng", "Ghi chú"]],
    ),
    _d5(
        "d5_r201_hyphen_lowercase",
        "Gạch nối cuối trang, phần sau viết thường: Docling bỏ gạch nối ('phingân hàng') (12D4).",
        [
            [_T("text", "Áp dụng cho tổ chức tín dụng phi-", 700), _footer(1)],
            [
                _T("text", "ngân hàng và chi nhánh ngân hàng nước ngoài.", 80),
                _footer(2),
            ],
        ],
        protected=[["phi-", 1]],
    ),
    _d5(
        "d5_r201_hyphen_document_number",
        "Số hiệu văn bản bị ngắt sau 'TT-': Docling chèn khoảng trắng ('TT- NHNN') (12D4).",
        [
            [_T("text", "Căn cứ Thông tư số 39/2016/TT-", 700), _footer(1)],
            [_T("text", "NHNN ngày 30/12/2016 của Thống đốc;", 80), _footer(2)],
        ],
        must_not_join=[["39/2016/TT-", "NHNN ngày"]],
    ),
    _d5(
        "d5_orig_f19_text_labels",
        "Nguyên bản f19 trước 12D3 (khôi phục): phần đầu nhãn TEXT, số trang nhãn TEXT.",
        [
            [
                E("text", "Áp dụng cho tổ chức tín dụng phi-", y=740),
                E("text", "1", x=290, y=800, w=16, h=12, gt="artifact"),
            ],
            [
                E("text", "ngân hàng và chi nhánh ngân hàng nước ngoài.", y=60),
                E("text", "2", x=290, y=800, w=16, h=12, gt="artifact"),
            ],
        ],
        protected=[["phi-", 1]],
    ),
    _d5(
        "d5_var_f38_two_columns_ascii_tail",
        "Biến thể f38: cột trái trang một kết thúc bằng chữ ASCII ('theo') thay vì 'và'.",
        [
            [
                E(
                    "text",
                    "Cột trái trang một nói về điều kiện vay vốn của khách hàng theo",
                    x=70,
                    y=100,
                    w=210,
                    h=640,
                ),
                E(
                    "text",
                    "Cột phải trang một nói về thời hạn và lãi suất áp dụng.",
                    x=315,
                    y=100,
                    w=210,
                    h=660,
                ),
            ],
            [
                E(
                    "text",
                    "cột trái trang hai tiếp tục một nội dung khác hẳn.",
                    x=70,
                    y=100,
                    w=210,
                    h=300,
                ),
                E(
                    "text",
                    "Cột phải trang hai kết thúc văn bản.",
                    x=315,
                    y=100,
                    w=210,
                    h=300,
                ),
            ],
        ],
        must_not_join=[["khách hàng theo", "Cột phải trang một"]],
    ),
    _d5(
        "d5_var_f31_lead_ascii_tail",
        "Biến thể f31: câu dẫn kết thúc 'bao gồm' (chữ ASCII), điểm a) nhãn TEXT ở trang sau.",
        [
            [
                E("text", "Điều 6. Hồ sơ vay vốn.", y=120, h=28),
                E("text", "2. Hồ sơ vay vốn của khách hàng bao gồm", y=700),
            ],
            [
                E("text", "a) giấy đề nghị vay vốn;", y=100),
                E("text", "b) phương án sử dụng vốn.", y=130),
            ],
        ],
        must_not_join=[["bao gồm", "a) giấy"]],
    ),
    _d5(
        "d5_var_f39_footer_labels",
        "Biến thể f39: số trang nhãn PAGE_FOOTER; bảng nằm giữa câu dẫn và phần sau.",
        [
            [
                E("text", "Biểu phí áp dụng cho các dịch vụ sau đây gồm", y=700, h=28),
                _pn(1, label="page_footer"),
            ],
            [
                E(
                    "table",
                    y=60,
                    h=60,
                    rows=[["Dịch vụ", "Mức phí"], ["Chuyển tiền", "2.200"]],
                ),
                E("text", "phí trên đã bao gồm thuế giá trị gia tăng.", y=140),
                _pn(2, label="page_footer"),
            ],
            [
                E("text", "Điều 9. Tổ chức thực hiện.", y=60, h=28),
                _pn(3, label="page_footer"),
            ],
        ],
        protected=[["2.200", 1]],
        must_not_join=[["sau đây gồm", "phí trên đã bao gồm"]],
    ),
    _d5(
        "d5_var_f11_footer_labels",
        "Biến thể f11: số trang nhãn PAGE_FOOTER, trang trắng ở giữa.",
        [
            [
                E("text", "Phần này được để trống có chủ ý và tiếp tục", y=740),
                _pn(1, label="page_footer"),
            ],
            [],
            [
                E("text", "nội dung của phụ lục kèm theo.", y=60),
                _pn(3, label="page_footer"),
            ],
        ],
        must_not_join=[["tiếp tục", "nội dung của phụ lục"]],
    ),
    _d5(
        "d5_var_f26_signer_name_last",
        "Biến thể f26: bộ thông báo một trang, dòng cuối là tên người ký (chữ thường cuối).",
        [
            [
                E("text", "NGÂN HÀNG THƯƠNG MẠI MẪU - CHI NHÁNH TỈNH", y=50, w=300),
                E("section_header", f"THÔNG BÁO SỐ {n}", x=230, y=110, w=135, h=18),
                E(
                    "text",
                    f"Thông báo lãi suất cho vay áp dụng từ tháng {n - 9} là {n - 3},5%/năm.",
                    y=160,
                    h=28,
                ),
                E("text", "Nguyễn Văn An", x=340, y=770, w=170, h=12),
            ]
            for n in (10, 11, 12)
        ],
        protected=[
            ["Nguyễn Văn An", 3],
            ["NGÂN HÀNG THƯƠNG MẠI MẪU - CHI NHÁNH TỈNH", 3],
        ],
        must_not_join=[["Nguyễn Văn An", "NGÂN HÀNG"]],
    ),
    _d5(
        "d5_var_f35_sentence_case_headers",
        "Biến thể f35: tiêu đề cột viết thường ('Chỉ tiêu', 'Số tiền') lặp trên 3 trang.",
        [
            [
                E("text", "Stt", x=70, y=60, w=30, h=12),
                E("text", "Chỉ tiêu", x=120, y=60, w=60, h=12),
                E("text", "Số tiền", x=420, y=60, w=60, h=12),
                E("text", f"Dư nợ nhóm {p}", x=120, y=400, w=120, h=12),
                E("text", f"10{p}", x=420, y=400, w=30, h=12),
            ]
            for p in range(1, 4)
        ],
        protected=[["Chỉ tiêu", 3], ["Số tiền", 3], ["101", 1], ["103", 1]],
    ),
    # ---- R2-11: business content the layout model put in the furniture layer ---
    _d5(
        "d5_r211_letterhead_document_number",
        "Tên đơn vị và số hiệu văn bản nhãn PAGE_HEADER, footnote nhãn PAGE_FOOTER, chỉ ở trang 1 (12D4).",
        [
            [
                _T("page_header", "NGÂN HÀNG NÔNG NGHIỆP MẪU", 30, 70, 300),
                _T("page_header", "Số: 1234/QĐ-NHM-KHCN", 50, 70, 300),
                _T("section_header", "QUYẾT ĐỊNH", 120),
                _T("text", "Điều 1. Ban hành Quy định về phí dịch vụ.", 160),
                _T(
                    "page_footer",
                    "(1) Mức phí chưa bao gồm thuế giá trị gia tăng 10%.",
                    790,
                    70,
                    525,
                ),
            ],
            [_T("text", "Điều 2. Quyết định có hiệu lực từ ngày ký.", 80)],
        ],
        protected=[["Số: 1234/QĐ-NHM-KHCN", 1]],
    ),
    _d5(
        "d5_r211_running_header_and_footer_numbers",
        "Đối chứng: tiêu đề chạy nhãn PAGE_HEADER lặp 3 trang + số trang nhãn PAGE_FOOTER (không phải nội dung).",
        [
            [
                _T(
                    "page_header",
                    "Quy chế cho vay - lưu hành nội bộ",
                    30,
                    70,
                    300,
                    gt="furniture",
                ),
                _T("text", f"Nội dung trang {p} của quy chế cho vay tiêu dùng.", 100),
                _footer(p),
            ]
            for p in range(1, 4)
        ],
    ),
    # ---- F-06: pictures must keep a trace ----------------------------------------
    _d5(
        "d5_f06_large_picture_with_caption",
        "Ảnh 36% trang có chú thích: chú thích không phải 'chữ của ảnh' (12D4).",
        [
            [
                E(
                    "text",
                    "Biểu lãi suất áp dụng từ ngày 01/7/2024 như sau:",
                    y=60,
                    h=14,
                ),
                E("caption", "Hình 1. Biểu lãi suất huy động", y=90, h=14),
                E("picture", x=70, y=110, w=455, h=400),
                E("text", "Các mức lãi suất khác giữ nguyên.", y=540, h=14),
            ]
        ],
    ),
    _d5(
        "d5_f06_large_picture_one_stray_word",
        "Ảnh 36% trang chỉ có MỘT từ OCR lạc bên trong (12D4).",
        [
            [
                E(
                    "text",
                    "Biểu lãi suất áp dụng từ ngày 01/7/2024 như sau:",
                    y=60,
                    h=14,
                ),
                E(
                    "picture",
                    x=70,
                    y=110,
                    w=455,
                    h=400,
                    children=[E("text", "Kỳ hạn", x=80, y=120, w=40, h=10)],
                ),
                E("text", "Các mức lãi suất khác giữ nguyên.", y=540, h=14),
            ]
        ],
    ),
    _d5(
        "d5_f06_small_logo_without_text",
        "Đối chứng: logo nhỏ (2% trang) không có chữ, khai báo decoration.",
        [
            [
                E("picture", x=70, y=30, w=60, h=60, gt="decoration"),
                E(
                    "text",
                    "Thông báo về việc điều chỉnh biểu phí dịch vụ.",
                    y=120,
                    h=14,
                ),
            ]
        ],
    ),
    # ---- R2-02 / F-17: characters that must survive storage, display and copy ---
    _d5(
        "d5_r202_markdown_significant_characters",
        "Dấu *, _, `, $, [ ], ~, <, &, \\ và công thức / tỷ lệ / URL / mã nghiệp vụ trong chữ OCR (12D4).",
        [
            [
                E("text", line, y=80 + 30 * i)
                for i, line in enumerate(
                    [
                        "Lãi suất = 5*3% (tối đa 15*2)",
                        "Mức phí (*) áp dụng theo biểu phí (*) hiện hành",
                        "Mã `TK01` dùng cho tài khoản thanh toán",
                        "Phí 5$ và 10$ cho mỗi giao dịch quốc tế",
                        "Tỷ lệ 1:2 và công thức a_1 + b_2 = c_3",
                        "Mã sản phẩm TK_VND_01 và file bao_cao_2024.xlsx",
                        "Email: ho_tro@agribank.com.vn; website https://agribank.com.vn/a_b?x=1&y=2",
                        "Họ tên: <Tên khách hàng> & <Số CMND>",
                        "Ký hiệu ~50 triệu đồng và [chưa xác nhận]",
                        "Đường dẫn C:\\Bieu\\phi.xlsx trên máy trạm",
                    ]
                )
            ]
        ],
        protected=[
            ["5*3%", 1],
            ["15*2", 1],
            ["(*)", 2],
            ["`TK01`", 1],
            ["5$", 1],
            ["10$", 1],
            ["a_1", 1],
            ["TK_VND_01", 1],
            ["ho_tro@agribank.com.vn", 1],
            ["x=1&y=2", 1],
            ["<Tên khách hàng>", 1],
            ["~50", 1],
            ["[chưa xác nhận]", 1],
            ["C:\\Bieu\\phi.xlsx", 1],
        ],
    ),
]


def by_name(name: str) -> dict[str, Any]:
    for fx in FIXTURES:
        if fx["name"] == name:
            return fx
    raise KeyError(name)
