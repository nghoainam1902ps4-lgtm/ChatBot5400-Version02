"""Phase 12D4 re-review: counter-examples against Legal normalizer v1.1.0 itself.

Found by a fresh-context sub-reviewer of this session (it was given the code,
not the Phase 12D3 conclusions) and re-run by the main reviewer. In every case
the Standard export keeps the content / keeps the two lines apart, so Docling
is NOT the cause: the loss or the merged sentence is produced by
``open_notebook/ocr/legal_normalizer.py``.

Each ``xfail(strict=True)`` test states the EXPECTED behaviour.
"""

from __future__ import annotations

import pytest

pytest.importorskip("docling")

import legal_harness as H  # noqa: E402

from open_notebook.ocr import legal_normalizer as N  # noqa: E402

E = H.load_fixtures().E


def run(pages):
    doc = H.build_document({"name": "d4", "pages": pages, "ground_truth": ""})
    standard = H.display_lines(doc.export_to_markdown())
    result = N.normalize_document(doc)
    return standard, H.legal_lines(result.content), result


def fill(y, n=1, suffix=""):
    return [
        E("text", f"Đoạn văn số {i}{suffix} của trang này trình bày nội dung nghiệp vụ thông thường.", y=y + 40 * i, h=28)
        for i in range(n)
    ]  # fmt: skip


# --------------------------------------------------------------------------- #
# F-02 PARTIALLY FIXED: content numbers that track the page index are still deleted
# --------------------------------------------------------------------------- #


def _detached_clause_numbers():
    """Clause numbers 2, 3, 4 split off by OCR, printed at the first-line indent
    (x=98) while the wrapped paragraph box starts at the margin (x=70). The
    Phase 12D3 fixture f34 puts the same numbers exactly AT the margin."""
    texts = [
        "Khách hàng có quyền từ chối các yêu cầu trái với thỏa thuận đã ký kết với ngân hàng.",
        "Khách hàng có quyền khiếu nại theo quy định của pháp luật và quy định nội bộ.",
        "Khách hàng có quyền được bảo mật thông tin theo quy định của pháp luật.",
    ]
    pages = [[E("text", "Điều 4. Quyền của khách hàng.", y=120, h=28)]]
    for i, text in enumerate(texts):
        pages.append(
            [
                E("text", str(i + 2), x=98, y=62, w=10, h=12),
                E("text", text, y=62, h=28),
                E("text", "Việc thực hiện quyền này tuân theo hợp đồng và quy định của pháp luật có liên quan.", y=110, h=28),
            ]
        )  # fmt: skip
    pages.append([E("text", "Điều 5. Nghĩa vụ của khách hàng.", y=100, h=28)])
    return pages, ["2", "3", "4"]


def _voucher_numbers():
    pages = [
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
    ]
    return pages, ["0001", "0002", "0003", "0004"]


def _reporting_periods():
    pages = [
        [
            E("text", "Kỳ báo cáo:", x=360, y=40, w=70, h=12),
            E("text", f"{p}/2024", x=440, y=40, w=50, h=12),
            E("section_header", "BÁO CÁO DƯ NỢ", x=230, y=110, w=135, h=18),
            E("text", f"Dư nợ cuối kỳ là {p}50 tỷ đồng.", y=160, h=28),
        ]
        for p in range(1, 5)
    ]
    return pages, ["1/2024", "2/2024", "3/2024", "4/2024"]


CONTENT_NUMBERS = {
    "clause numbers at the first-line indent": _detached_clause_numbers,
    "voucher numbers beside 'Số:'": _voucher_numbers,
    "reporting periods beside 'Kỳ báo cáo:'": _reporting_periods,
}


@pytest.mark.parametrize("case", sorted(CONTENT_NUMBERS))
def test_control_f02_standard_keeps_these_numbers_and_legal_gives_no_warning(case):
    pages, numbers = CONTENT_NUMBERS[case]()
    standard, legal, result = run(pages)
    assert all(n in standard for n in numbers)
    assert not any(n in legal for n in numbers)  # all of them are gone
    assert result.counts.get("page_number_to_furniture") == len(numbers)
    assert not [
        w for w in result.warnings if str(w.get("code", "")).startswith("page_number")
    ]


@pytest.mark.xfail(
    strict=True,
    reason="PHASE12D2 F-02 PARTIALLY FIXED (data loss remains): a bare number in the top/bottom band that follows the page "
    "index on >= 3 pages and is not flush with the paragraph margin is removed as a page number, "
    "although it is a clause number, a voucher number or a reporting period",
)
@pytest.mark.parametrize("case", sorted(CONTENT_NUMBERS))
def test_f02_content_numbers_that_track_the_page_index_are_kept(case):
    pages, numbers = CONTENT_NUMBERS[case]()
    _, legal, _ = run(pages)
    assert all(n in legal for n in numbers)


# --------------------------------------------------------------------------- #
# F-03 PARTIALLY FIXED: the normalizer's own cross-page join still creates sentences
# --------------------------------------------------------------------------- #

A_POINT = "b) Tổ chức tín dụng phi ngân hàng được Ngân hàng Nhà nước cấp phép thành lập và hoạt động"
A_LEAD = "2. Hồ sơ vay vốn bao gồm các giấy tờ"
A_BODY = (
    "Khách hàng có trách nhiệm hoàn trả đầy đủ nợ gốc và lãi tiền vay theo đúng thời hạn đã "
    "thỏa thuận trong hợp đồng tín dụng đã ký"
)
FOOTNOTE = (
    "Mức lãi suất nêu trên áp dụng đối với khoản vay có tài sản bảo đảm theo Quyết định số "
    "123/2024/QĐ-NHM ngày 01/7/2024"
)
CONTINUATION = "khách hàng theo quy định tại Điều 5 Quy chế này."


def _footnote(mark):
    foot = mark + FOOTNOTE
    pages = [
        fill(100, 2)
        + [
            E("text", "Mức cho vay tối đa được xác định căn cứ vào nhu cầu vay vốn và khả năng hoàn trả nợ của", y=600, h=28),
            E("text", foot, y=735, h=24),
        ],
        [E("text", CONTINUATION, y=62, h=14)] + fill(100, 2, "b"),
    ]  # fmt: skip
    return pages, foot, CONTINUATION


def _new_unit(label, first, second):
    pages = [
        fill(100, 3) + [E(label, first, y=700, h=28)],
        [E("text", second, y=62, h=14)] + fill(100, 2, "b"),
    ]
    shown_first = first if label == "text" else first.split(" ", 1)[1]
    return pages, shown_first, second


def _top_line(header):
    pages = [
        fill(100, 3) + [E("text", A_BODY, y=700, h=42)],
        [
            E("text", header, y=30, w=250, h=12),
            E("text", "và các phụ lục kèm theo hợp đồng.", y=62, h=14),
        ]
        + fill(100, 2, "b"),
        fill(100, 2, "c"),
    ]
    return pages, A_BODY, header


FALSE_JOINS = {
    "footnote marked (*)": lambda: _footnote("(*) "),
    "footnote marked 1.": lambda: _footnote("1. "),
    "footnote marked with a superscript": lambda: _footnote("¹ "),
    "footnote without a marker": lambda: _footnote(""),
    "next point read as 'c )'": lambda: _new_unit("list_item", A_POINT, "c ) khách hàng cá nhân là người cư trú;"),
    "next point lost its marker": lambda: _new_unit("list_item", A_POINT, "khách hàng cá nhân là người cư trú;"),
    "hollow bullet read as the letter o": lambda: _new_unit("list_item", A_POINT, "o khách hàng cá nhân là người cư trú;"),
    "next point marked 'a,'": lambda: _new_unit("text", A_LEAD, "a, giấy đề nghị vay vốn;"),
    "next point marked 'a-'": lambda: _new_unit("text", A_LEAD, "a- giấy đề nghị vay vốn;"),
    "date line after the last clause": lambda: _new_unit(
        "list_item",
        "5. Hợp đồng này được lập thành 02 bản có giá trị pháp lý như nhau, mỗi bên giữ 01 bản",
        "ngày 15 tháng 7 năm 2024",
    ),
    "unit line after a table title": lambda: _new_unit(
        "text",
        "Biểu tổng hợp dư nợ cho vay theo nhóm nợ của toàn hệ thống tại thời điểm 31/12/2024",
        "đvt: triệu đồng",
    ),
    "running title at the top of the next page": lambda: _top_line("quy chế cho vay tiêu dùng - lưu hành nội bộ"),
    "web address at the top of the next page": lambda: _top_line("www.nganhangmau.example.vn"),
    "'trang 2/3' at the top of the next page": lambda: _top_line("trang 2/3"),
}  # fmt: skip


@pytest.mark.parametrize("case", sorted(FALSE_JOINS))
def test_control_f03_standard_keeps_the_two_lines_apart(case):
    """The merge is made by the normalizer (counts.join_across_pages == 1), not by Docling."""
    pages, first, second = FALSE_JOINS[case]()
    standard, legal, result = run(pages)
    assert not any(first in line and second in line for line in standard)
    assert any(first in line for line in standard) and any(
        second in line for line in standard
    )
    assert any(first in line and second in line for line in legal)
    assert result.counts.get("join_across_pages") == 1


@pytest.mark.xfail(
    strict=True,
    reason="PHASE12D2 F-03 PARTIALLY FIXED (wrong sentences remain): the normalizer still joins a footnote, a new point whose "
    "marker OCR damaged, a date / unit line or a running title to the previous page's text",
)
@pytest.mark.parametrize("case", sorted(FALSE_JOINS))
def test_f03_no_sentence_is_created_across_the_page_break(case):
    pages, first, second = FALSE_JOINS[case]()
    _, legal, _ = run(pages)
    assert not any(first in line and second in line for line in legal)


# --------------------------------------------------------------------------- #
# F-06 PARTIALLY FIXED: a large picture loses its only trace
# --------------------------------------------------------------------------- #

PICTURES = {
    "36 % picture with a caption": [
        [
            E("text", "Biểu lãi suất áp dụng từ ngày 01/7/2024 như sau:", y=60, h=14),
            E("caption", "Hình 1. Biểu lãi suất huy động", y=90, h=14),
            E("picture", x=70, y=110, w=455, h=400),
            E("text", "Các mức lãi suất khác giữ nguyên.", y=540, h=14),
        ]
    ],
    "36 % picture with one stray OCR word inside": [
        [
            E("text", "Biểu lãi suất áp dụng từ ngày 01/7/2024 như sau:", y=60, h=14),
            E("picture", x=70, y=110, w=455, h=400, children=[E("text", "Kỳ hạn", x=80, y=120, w=40, h=10)]),
            E("text", "Các mức lãi suất khác giữ nguyên.", y=540, h=14),
        ]
    ],
}  # fmt: skip


@pytest.mark.xfail(
    strict=True,
    reason="PHASE12D2 F-06 PARTIALLY FIXED: a caption or a single OCR word counts as 'the text of "
    "the picture', so a page-sized scanned table / chart loses its placeholder with no warning",
)
@pytest.mark.parametrize("case", sorted(PICTURES))
def test_f06_large_picture_keeps_a_trace(case):
    standard, legal, result = run(PICTURES[case])
    assert "<!-- image -->" in standard
    reported = any(w.get("code") == "picture_without_text" for w in result.warnings)
    assert "<!-- image -->" in legal or reported


# --------------------------------------------------------------------------- #
# Oracle (T-01): blind spots of preservation()
# --------------------------------------------------------------------------- #

ALIAS = {
    "pages": [
        [E("text", "1", x=290, y=30, w=16, h=12, gt="artifact"), E("text", "Điều 4. Quyền của khách hàng.", y=120)],
        [E("text", "2", x=290, y=30, w=16, h=12, gt="artifact"), E("text", "2", x=98, y=62, w=10, h=12), E("text", "Khách hàng có quyền từ chối.", y=100)],
        [E("text", "3", x=290, y=30, w=16, h=12, gt="artifact"), E("text", "3", x=98, y=62, w=10, h=12), E("text", "Khách hàng có quyền khiếu nại.", y=100)],
    ]
}  # fmt: skip


def test_control_oracle_sees_ordinary_damage():
    truth = [u["text"] for u in H.expected_units(ALIAS)]
    assert H.preservation(ALIAS, truth)["false_deletion"] == 0
    assert (
        H.preservation(ALIAS, [x for x in truth if "khiếu nại" not in x])[
            "false_deletion"
        ]
        == 1
    )
    assert (
        H.preservation(ALIAS, truth + ["Câu không có trong văn bản."])[
            "false_insertion"
        ]
        == 1
    )


# Phase 12D5: R2-14 fixed (scripts/ocr/phase12_oracle.py, worst-case attribution of
# aliased lines without a document, identity attribution with one); xfail removed.
def test_r2_14_oracle_sees_a_required_number_deleted_while_its_twin_artifact_stays():
    damaged = [
        "1", "Điều 4. Quyền của khách hàng.",
        "2", "Khách hàng có quyền từ chối.",  # the clause number "2" is gone, the page number stays
        "3", "Khách hàng có quyền khiếu nại.",
    ]  # fmt: skip
    assert H.preservation(ALIAS, damaged)["false_deletion"] == 2


# Phase 12D5: R2-14 fixed (artifacts take part in the order check); xfail removed.
def test_r2_14_oracle_sees_an_artifact_reinserted_in_the_middle_of_a_page():
    moved = [
        "Điều 4. Quyền của khách hàng.",
        "2", "2", "Khách hàng có quyền từ chối.",
        "1",  # the page number of page 1, now in the middle of page 3
        "3", "3", "Khách hàng có quyền khiếu nại.",
    ]  # fmt: skip
    p = H.preservation(ALIAS, moved)
    assert p["false_reordering"] + p["false_insertion"] > 0
