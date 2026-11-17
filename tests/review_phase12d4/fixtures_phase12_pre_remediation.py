# Phase 12D4 review fixture: verbatim copy of tests/fixtures/legal/legal_fixtures.py at 2ef0074
# (the 24 synthetic fixtures BEFORE the Phase 12D3 remediation changed their expectations).
# ruff: noqa
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
    return E("text", str(n), x=290, y=800 if bottom else 30, w=16, h=12)


def footer(n: int | str) -> dict[str, Any]:
    """A page number correctly labelled PAGE_FOOTER (Docling puts it in furniture)."""
    return E("page_footer", str(n), x=290, y=800, w=16, h=12)


def signature(y: float = 700) -> dict[str, Any]:
    return E("picture", x=360, y=y, w=120, h=45)


def stamp(y: float = 690) -> dict[str, Any]:
    return E("picture", x=320, y=y, w=80, h=80)


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
                E("text", "dư trên tài khoản của khách hàng.", y=60),
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
        "must_join": ["không làm thay đổi số dư trên tài khoản của khách hàng."],
        "absent_lines": ["6", "7"],
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
            [E("text", "dư trên tài khoản của khách hàng.", y=60), page_number(7)],
        ],
        "ground_truth": "9. Dịch vụ phi tài chính là dịch vụ không làm thay đổi số dư trên tài khoản của khách hàng.",
        "markers": ["9."],
        "must_join": ["không làm thay đổi dư trên tài khoản"],
        "forbidden": ["thay đổi số dư"],
        "absent_lines": ["6", "7"],
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
        "absent_lines": ["2", "3", "4"],
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
        "absent_lines": ["1", "2"],
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
        "absent_lines": ["1", "2"],
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
        "absent_lines": ["1", "2"],
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
        "absent_lines": ["1", "3"],
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
        "absent_lines": ["1", "2"],
    },
    {
        "name": "f14_running_header_footer",
        "description": "Header/footer lặp trên 4 trang (nhãn TEXT) và 'Trang n/4'.",
        "pages": [
            [
                E("text", "NGÂN HÀNG MẪU - QUY ĐỊNH NỘI BỘ", y=25, w=250, h=12),
                E(
                    "section_header",
                    "QUY ĐỊNH VỀ DỊCH VỤ THẺ",
                    x=180,
                    y=80,
                    w=235,
                    h=18,
                ),
                E("text", f"Nội dung trang {1} của quy định.", y=120),
                E("text", "Trang 1/4", x=270, y=805, w=60, h=12),
            ]
        ]
        + [
            [
                E("text", "NGÂN HÀNG MẪU - QUY ĐỊNH NỘI BỘ", y=25, w=250, h=12),
                E("text", f"Nội dung trang {n} của quy định.", y=60),
                E("text", f"Trang {n}/4", x=270, y=805, w=60, h=12),
            ]
            for n in (2, 3, 4)
        ],
        "ground_truth": (
            "QUY ĐỊNH VỀ DỊCH VỤ THẺ Nội dung trang 1 của quy định. Nội dung trang 2 của quy định. "
            "Nội dung trang 3 của quy định. Nội dung trang 4 của quy định."
        ),
        "absent_lines": ["NGÂN HÀNG MẪU - QUY ĐỊNH NỘI BỘ", "Trang 1/4", "Trang 4/4"],
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
        "present_lines": ["\\- Như Điều 3;"],
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
        "description": "Từ có gạch nối ở cuối trang: không tự nối (mơ hồ), có cảnh báo.",
        "pages": [
            [E("text", "Áp dụng cho tổ chức tín dụng phi-", y=740), page_number(1)],
            [
                E("text", "ngân hàng và chi nhánh ngân hàng nước ngoài.", y=60),
                page_number(2),
            ],
        ],
        "ground_truth": "Áp dụng cho tổ chức tín dụng phi- ngân hàng và chi nhánh ngân hàng nước ngoài.",
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
        "absent_lines": ["1", "2", "3"],
    },
    {
        "name": "f24_join_chain_and_footer_label",
        "description": "Đoạn kéo dài 3 trang; số trang được Docling gán đúng PAGE_FOOTER (đã là furniture).",
        "pages": [
            [E("text", "Đoạn văn rất dài bắt đầu ở trang một và", y=760), footer(1)],
            [E("text", "tiếp tục suốt trang hai cho đến khi", y=60, h=700), footer(2)],
            [E("text", "kết thúc ở đầu trang ba.", y=60), footer(3)],
        ],
        "ground_truth": "Đoạn văn rất dài bắt đầu ở trang một và tiếp tục suốt trang hai cho đến khi kết thúc ở đầu trang ba.",
        "must_join": [
            "trang một và tiếp tục suốt trang hai cho đến khi kết thúc ở đầu trang ba."
        ],
    },
]


def by_name(name: str) -> dict[str, Any]:
    for fx in FIXTURES:
        if fx["name"] == name:
            return fx
    raise KeyError(name)
