"""Counter-examples for open_notebook/ocr/legal_normalizer.py (Phase 12D2 review).

Documents are built exactly like the Phase 12 fixtures: synthetic layout fed to
Docling's real ReadingOrderModel (tests/legal_harness.py). All text is fictional.
"""

from __future__ import annotations

import threading

import pytest

pytest.importorskip("docling")

import legal_harness as H  # noqa: E402

from open_notebook.ocr import legal_normalizer as N  # noqa: E402

E = H.load_fixtures().E


def body(y: float, text: str) -> dict:
    return E("text", text, y=y, h=28)


def build(pages):
    doc = H.build_document({"pages": pages})
    return doc, doc.export_to_markdown(), N.normalize_document(doc, include_text=True)


# --------------------------------------------------------------------------- #
# Fixtures of the counter-examples
# --------------------------------------------------------------------------- #


def unit_line_pages():
    """Appendix: the unit of the amounts is printed at the top of every page."""
    return [
        [
            E("text", "Đơn vị tính: triệu đồng", x=380, y=62, w=145, h=14),
            body(120, f"Chi nhánh {p} dư nợ cho vay ngắn hạn là {1500 + p}."),
            body(400, f"Chi nhánh {p} dư nợ cho vay trung hạn là {2500 + p}."),
        ]
        for p in (1, 2, 3)
    ]


def bundle_pages():
    """Four one-page notices scanned into one PDF: same issuer line, same signature note."""
    return [
        [
            E("text", "NGÂN HÀNG THƯƠNG MẠI MẪU - CHI NHÁNH TỈNH", y=50, w=300),
            E("section_header", f"THÔNG BÁO SỐ {p + 10}", x=230, y=110, w=135, h=18),
            body(
                160,
                f"Thông báo lãi suất cho vay áp dụng từ tháng {p + 1} là {7 + p},5%/năm.",
            ),
            E("text", "(Ký, ghi rõ họ tên và đóng dấu)", x=330, y=770, w=190, h=12),
        ]
        for p in range(4)
    ]


def year_pages():
    """The last text of two consecutive pages is a year (a column the layout model did not see as a table)."""
    return [
        [
            body(120, "Kế hoạch tăng trưởng tín dụng năm:"),
            E("text", "2024", x=450, y=780, w=40, h=12),
        ],
        [
            body(120, "Kế hoạch huy động vốn năm:"),
            E("text", "2025", x=450, y=780, w=40, h=12),
        ],
        [body(120, "Các nội dung khác thực hiện theo quy định hiện hành.")],
    ]


def clause_number_pages():
    """OCR split the clause number from its text; the number is the first thing on the page."""
    return [
        [body(120, "Điều 4. Quyền của khách hàng.")],
        [
            E("text", "2", x=70, y=62, w=10, h=12),
            body(100, "Khách hàng có quyền từ chối các yêu cầu trái thỏa thuận."),
        ],
        [
            E("text", "3", x=70, y=62, w=10, h=12),
            body(100, "Khách hàng có quyền khiếu nại theo quy định của pháp luật."),
        ],
    ]


def footnote_pages():
    """A footnote the layout model labelled TEXT sits between a cut paragraph and its continuation."""
    return [
        [
            body(120, "Điều 3. Mức cho vay."),
            E(
                "text",
                "Mức cho vay tối đa được xác định căn cứ vào nhu cầu vay vốn và khả năng hoàn trả nợ của",
                y=600,
                h=28,
            ),
            E("text", "1 Thông tư số 39/2016/TT-NHNN", y=760, h=12, w=200),
        ],
        [
            E("text", "khách hàng theo quy định tại Điều 5 Quy chế này.", y=100, h=14),
            body(200, "Điều 4. Thời hạn cho vay."),
        ],
    ]


def two_page_footer_pages():
    """Two-page document with a running footer: below the 3-page threshold of the repeat detector."""
    return [
        [
            body(120, "Điều 3. Mức cho vay."),
            E(
                "text",
                "Mức cho vay tối đa được xác định căn cứ vào nhu cầu vay vốn và khả năng trả nợ.",
                y=600,
                h=28,
            ),
            E("text", "Lưu hành nội bộ", y=790, h=12, w=200),
        ],
        [
            E(
                "text",
                "trong trường hợp đặc biệt, Tổng Giám đốc quyết định mức cho vay.",
                y=100,
                h=14,
            ),
            body(200, "Điều 4. Thời hạn cho vay."),
            E("text", "Lưu hành nội bộ", y=790, h=12, w=200),
        ],
    ]


def lettered_points_pages(first: str, second: str):
    return [
        [
            body(120, "Điều 6. Hồ sơ vay vốn."),
            E("text", "2. Hồ sơ vay vốn bao gồm các giấy tờ", y=700, h=14),
        ],
        [E("text", first, y=100, h=14), E("text", second, y=130, h=14)],
    ]


ALL_CASES = {
    "unit_line": unit_line_pages,
    "bundle": bundle_pages,
    "years": year_pages,
    "clause_numbers": clause_number_pages,
    "footnote": footnote_pages,
    "two_page_footer": two_page_footer_pages,
    "a_dot": lambda: lettered_points_pages(
        "a. Giấy đề nghị vay vốn;", "b. Phương án sử dụng vốn."
    ),
}


# --------------------------------------------------------------------------- #
# F-01 / F-02: valid content removed as "running header / footer" or "page number"
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True, reason="PHASE12D2 F-01: unit of the amounts removed from every page"
)
def test_f01_repeated_unit_line_is_content_not_a_running_header():
    _, standard, res = build(unit_line_pages())
    assert standard.count("Đơn vị tính: triệu đồng") == 3
    assert "Đơn vị tính: triệu đồng" in res.content


@pytest.mark.xfail(
    strict=True,
    reason="PHASE12D2 F-01: issuer line and signature note of every notice removed",
)
def test_f01_bundle_of_one_page_documents_keeps_issuer_and_signature_note():
    _, _, res = build(bundle_pages())
    assert "NGÂN HÀNG THƯƠNG MẠI MẪU - CHI NHÁNH TỈNH" in res.content
    assert "(Ký, ghi rõ họ tên và đóng dấu)" in res.content


@pytest.mark.xfail(
    strict=True,
    reason="PHASE12D2 F-02: years removed as page numbers (same offset on two pages)",
)
def test_f02_years_at_page_bottom_are_not_page_numbers():
    _, standard, res = build(year_pages())
    assert "2024" in standard and "2025" in standard
    assert "2024" in res.content and "2025" in res.content


@pytest.mark.xfail(
    strict=True, reason="PHASE12D2 F-02: clause numbers removed as page numbers"
)
def test_f02_clause_numbers_at_page_top_are_not_page_numbers():
    _, _, res = build(clause_number_pages())
    lines = H.display_lines(res.content)
    assert "2" in lines and "3" in lines


def test_f01_f02_existing_oracle_cannot_see_these_deletions():
    """PHASE12D2 T-01: the oracle of tests/test_ocr_legal_normalizer.py::test_no_valid_content_lost.

    It adds back whatever the normalizer itself moved to furniture, so a wrong
    removal counts as "0 words lost". Reproduced here on the counter-examples:
    the words ARE gone from the content, the oracle still reports 0.
    """
    for pages, gone in ((unit_line_pages(), "triệu"), (year_pages(), "2024")):
        doc, standard, res = build(pages)
        removed = " ".join(
            o.text_before or ""
            for o in res.operations
            if o.op.endswith("_to_furniture")
        )
        lost_by_existing_oracle = H.lost_words(
            H.display_text(standard, list_prefixes=False),
            H.display_text(res.content) + " " + removed,
        )
        assert lost_by_existing_oracle == 0  # what Phase 12D reports
        assert gone not in res.content  # what really happened
        assert (
            H.lost_words(
                H.display_text(standard, list_prefixes=False),
                H.display_text(res.content),
            )
            > 0
        )


# --------------------------------------------------------------------------- #
# F-03: false cross-page joins (text that was never one sentence)
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason="PHASE12D2 F-03: footnote joined to the next page's continuation",
)
def test_f03_footnote_is_not_joined_to_next_page_text():
    _, standard, res = build(footnote_pages())
    fused = "39/2016/TT-NHNN khách hàng"
    assert fused not in standard  # Docling does not do this
    assert fused not in res.content


@pytest.mark.xfail(
    strict=True,
    reason="PHASE12D2 F-03: running footer of a 2-page document joined to body text",
)
def test_f03_footer_of_two_page_document_is_not_joined_to_body_text():
    _, standard, res = build(two_page_footer_pages())
    fused = "Lưu hành nội bộ trong trường hợp"
    assert fused not in standard
    assert fused not in res.content


@pytest.mark.xfail(
    strict=True,
    reason="PHASE12D2 F-03: point 'a.' / 'a/' joined into the lead-in of its clause",
)
@pytest.mark.parametrize(
    "first,second",
    [
        ("a. Giấy đề nghị vay vốn;", "b. Phương án sử dụng vốn."),
        ("a/ Giấy đề nghị vay vốn;", "b/ Phương án sử dụng vốn."),
    ],
)
def test_f03_lettered_point_is_a_new_unit_not_a_continuation(first, second):
    _, standard, res = build(lettered_points_pages(first, second))
    lines = H.display_lines(res.content)
    assert first in H.display_lines(standard)
    assert first in lines  # the point is still a line of its own


# --------------------------------------------------------------------------- #
# F-06: a picture's placeholder disappears without any trace
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason="PHASE12D2 F-06: 12%-of-page picture dropped silently (no placeholder, no warning)",
)
def test_f06_medium_picture_without_text_leaves_a_trace():
    pages = [
        [
            body(120, "Biểu lãi suất áp dụng:"),
            E(
                "picture", x=70, y=200, w=300, h=200
            ),  # 12% of an A4 page: a scanned rate table, for example
            body(500, "Các mức lãi suất khác theo thông báo."),
        ]
    ]
    _, standard, res = build(pages)
    assert "<!-- image -->" in standard
    assert "<!-- image -->" in res.content or any(
        w["code"] == "picture_without_text" for w in res.warnings
    )


# --------------------------------------------------------------------------- #
# Properties that DO hold (verified by this review)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("case", sorted(ALL_CASES))
def test_verified_idempotent_deterministic_and_source_untouched(case):
    doc, standard, res = build(ALL_CASES[case]())
    assert doc.export_to_markdown() == standard  # the source document is not mutated
    assert N.normalize_document(doc).content == res.content  # deterministic
    assert N.normalize_document(res.document).content == res.content  # idempotent


def test_verified_thread_safety_same_output_from_concurrent_runs():
    docs = {
        name: H.build_document({"pages": make()}) for name, make in ALL_CASES.items()
    }
    expected = {name: N.normalize_document(doc).content for name, doc in docs.items()}
    results: list[tuple[str, str]] = []
    errors: list[BaseException] = []

    def work(name: str) -> None:
        try:
            for _ in range(3):
                results.append((name, N.normalize_document(docs[name]).content))
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=work, args=(n,)) for n in docs for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(results) == len(threads) * 3
    assert all(content == expected[name] for name, content in results)


def test_verified_protected_values_survive_in_counterexamples():
    """Amounts, rates and document numbers inside paragraphs are not altered (only whole items move)."""
    _, _, res = build(bundle_pages())
    for value in ("7,5%/năm", "8,5%/năm", "9,5%/năm", "10,5%/năm"):
        assert value in res.content
    _, _, res = build(footnote_pages())
    assert "39/2016/TT-NHNN" in res.content
