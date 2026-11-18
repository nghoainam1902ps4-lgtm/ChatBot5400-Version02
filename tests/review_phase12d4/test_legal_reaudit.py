"""Phase 12D4 re-review: Legal normalizer v1.1.0, oracle and text handling.

Documents are built by Docling's real ReadingOrderModel from declared layouts
(tests/legal_harness.py), exactly like the Phase 12D3 fixtures. Nothing here
uses the normalizer's own report as ground truth: every expectation is written
from the source layout.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

pytest.importorskip("docling")

import legal_harness as H  # noqa: E402

from open_notebook.ocr import legal_normalizer as N  # noqa: E402

HERE = Path(__file__).resolve().parent


def T(label, text, top, left=70.0, right=525.0, height=14.0):
    return {"label": label, "text": text, "bbox": [left, top, right, top + height]}


def foot(n):
    """A page number the layout model labelled correctly (PAGE_FOOTER)."""
    return T("page_footer", str(n), 800, 290, 306)


def outputs(pages):
    doc = H.build_document({"name": "d4", "pages": pages, "ground_truth": ""})
    standard = H.display_lines(doc.export_to_markdown())
    result = N.normalize_document(doc)
    return standard, H.legal_lines(result.content), result


# --------------------------------------------------------------------------- #
# R2-01: Docling's own cross-page / cross-column merge reaches the Legal output
# unchanged and unreported. The Phase 12D3 fixtures f19, f35, f38 were reworded
# so that this merge does not trigger, hence "0 false merge" does not cover it.
# --------------------------------------------------------------------------- #

UPSTREAM = {
    "two independent documents (signer name + next title)": (
        [
            [
                T("section_header", "QUYẾT ĐỊNH", 80),
                T("text", "Điều 1. Ban hành kèm theo Quyết định này Quy định về phí dịch vụ.", 120),
                T("text", "TỔNG GIÁM ĐỐC", 600, 330, 525),
                T("text", "Nguyễn Văn An", 700, 340, 515),
                foot(1),
            ],
            [
                T("text", "Phụ lục 01 ban hành kèm theo Quyết định số 12/QĐ-NHM", 80),
                T("text", "Mức phí chuyển tiền là 11.000 đồng mỗi giao dịch.", 120),
                foot(2),
            ],
        ],
        ("Nguyễn Văn An", "Phụ lục 01 ban hành kèm theo Quyết định số 12/QĐ-NHM"),
    ),
    "a clause and the next Article labelled as text": (
        [
            [
                T("text", "Điều 4. Phạm vi áp dụng", 80),
                T("text", "Quy định này áp dụng đối với toàn bộ khách hàng", 700),
                foot(1),
            ],
            [
                T("text", "Điều 5. Hiệu lực thi hành", 80),
                T("text", "Quy định có hiệu lực từ ngày 01/01/2025.", 120),
                foot(2),
            ],
        ],
        ("Quy định này áp dụng đối với toàn bộ khách hàng", "Điều 5. Hiệu lực thi hành"),
    ),
    "a footnote labelled as text and the body continuation": (
        [
            [
                T("text", "Khách hàng được miễn phí khi duy trì số dư tối thiểu theo quy định của", 660),
                T("text", "Theo Thông tư số 39/2016/TT-NHNN của Ngân hàng Nhà nước về cho vay", 770, 70, 525, 12),
                foot(1),
            ],
            [T("text", "ngân hàng trong từng thời kỳ.", 80), foot(2)],
        ],
        ("Theo Thông tư số 39/2016/TT-NHNN của Ngân hàng Nhà nước về cho vay", "ngân hàng trong từng thời kỳ."),
    ),
    "a side note to the right of a body line (same page)": (
        [
            [
                T("text", "Lãi suất cho vay ngắn hạn tối đa theo thông báo từng", 300, 70, 300),
                T("text", "Ghi chú: áp dụng từ quý I", 300, 320, 525),
                T("text", "thời kỳ của Tổng Giám đốc.", 330, 70, 300),
            ]
        ],
        ("Lãi suất cho vay ngắn hạn tối đa theo thông báo từng", "Ghi chú: áp dụng từ quý I"),
    ),
}  # fmt: skip


# was: test_control_upstream_merge_exists_in_standard_and_legal (PHASE12D4 evidence:
# it asserted that Legal inherited the merge silently). Phase 12D5 regression test:
# the merge is still Docling's (Standard / v1.2.0 unchanged); Legal splits it back at
# the recorded char spans and says so.
@pytest.mark.parametrize("case", sorted(UPSTREAM))
def test_regression_upstream_merge_is_undone_in_legal(case):
    pages, (first, second) = UPSTREAM[case]
    standard, legal, result = outputs(pages)
    merged = f"{first} {second}"
    assert any(merged in line for line in standard)  # upstream, also in v1.2.0
    assert not any(merged in line for line in legal)
    assert first in legal and second in legal  # each part exactly as Docling had it
    assert "upstream_merge_undone" in {w["code"] for w in result.warnings}


# Phase 12D5: R2-01 fixed for space joins (char spans) and, with the element texts
# as evidence, for removed hyphens; xfail removed.
@pytest.mark.parametrize("case", sorted(UPSTREAM))
def test_r2_01_upstream_merge_of_unrelated_items_is_undone_or_reported(case):
    """EXPECTED: a sentence that exists nowhere in the source is either split back
    (the split point is recoverable from the item's provenance char spans) or
    reported as a warning that names the pages."""
    pages, (first, second) = UPSTREAM[case]
    _, legal, result = outputs(pages)
    merged = any(f"{first} {second}" in line for line in legal)
    reported = any("merge" in str(w.get("code", "")) for w in result.warnings)
    assert (not merged) or reported


# Phase 12D5: R2-01 - without evidence the change is reported (upstream_dehyphenation /
# upstream_merge_undone); xfail removed.
@pytest.mark.parametrize(
    "first, second, exact",
    [
        ("Áp dụng cho tổ chức tín dụng phi-", "ngân hàng và chi nhánh ngân hàng nước ngoài.", "phi-"),
        ("Căn cứ Thông tư số 39/2016/TT-", "NHNN ngày 30/12/2016 của Thống đốc;", "39/2016/TT-NHNN"),
    ],
)  # fmt: skip
def test_r2_01_text_changed_at_a_page_break_is_reported(first, second, exact):
    """'phi-' + 'ngân hàng' becomes 'phingân hàng'; '39/2016/TT-' + 'NHNN' becomes
    '39/2016/TT- NHNN'. EXPECTED: the original spelling survives, or a warning."""
    _, legal, result = outputs(
        [[T("text", first, 700), foot(1)], [T("text", second, 80), foot(2)]]
    )
    text = " ".join(legal)
    reported = any(
        "hyphen" in str(w.get("code", "")) or "merge" in str(w.get("code", ""))
        for w in result.warnings
    )
    assert exact in text or reported


def test_control_text_page_numbers_block_the_upstream_merge():
    """The same layout with page numbers labelled TEXT is NOT merged by Docling:
    which behaviour a real scan gets depends on Layout Heron's labels (local gate)."""
    pages, (first, second) = UPSTREAM["a clause and the next Article labelled as text"]
    pages = [
        [e if e["label"] != "page_footer" else dict(e, label="text") for e in page]
        for page in pages
    ]
    standard, legal, _ = outputs(pages)
    assert not any(f"{first} {second}" in line for line in standard + legal)


# --------------------------------------------------------------------------- #
# The 24 fixtures as they were BEFORE the remediation changed their expectations
# --------------------------------------------------------------------------- #


def _old_fixtures():
    spec = importlib.util.spec_from_file_location(
        "d4_old_fixtures", HERE / "fixtures_phase12_pre_remediation.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["d4_old_fixtures"] = module
    spec.loader.exec_module(module)
    return module.FIXTURES


OLD = _old_fixtures()
ARTIFACT = re.compile(r"[\d\s/\-–—]+|Trang \d+/\d+")
MARKER = re.compile(r"^(\d+[.)]|[a-zđ][.)]|-)\s+")


@pytest.mark.parametrize("fixture", OLD, ids=[f["name"] for f in OLD])
def test_verified_original_fixtures_lose_no_body_text_under_v110(fixture):
    """Independent of the new oracle: every body element of the ORIGINAL fixtures
    is still visible in the v1.1.0 output (substring of the displayed text)."""
    doc = H.build_document(fixture)
    shown = " ".join(H.legal_lines(N.normalize_document(doc).content))
    for page in fixture["pages"]:
        for element in page:
            text = element.get("text")
            if not text or element.get("label") in ("page_header", "page_footer"):
                continue
            if ARTIFACT.fullmatch(text):
                continue
            assert text in shown or MARKER.sub("", text) in shown, text


def test_verified_what_the_remediation_gave_up_on_the_original_fixtures():
    """The original expectations that v1.1.0 no longer meets are all in the safe
    direction: 2 joins not made, 15 page numbers / 1 running header kept."""
    joins_not_made, artifacts_kept = [], []
    for fixture in OLD:
        doc = H.build_document(fixture)
        legal = H.legal_lines(N.normalize_document(doc).content)
        joins_not_made += [
            (fixture["name"], j)
            for j in fixture.get("must_join") or []
            if not any(j in line for line in legal)
        ]
        artifacts_kept += [
            (fixture["name"], a)
            for a in fixture.get("absent_lines") or []
            if a in legal
        ]
    assert sorted({n for n, _ in joins_not_made}) == [
        "f02_clause_across_pages",
        "f03_missing_word_not_invented",
    ]
    assert len(artifacts_kept) == 15
    assert {n for n, _ in artifacts_kept} == {
        "f02_clause_across_pages", "f03_missing_word_not_invented", "f07_parts_chapters_sections",
        "f08_protected_fields", "f10_table_across_pages", "f11_blank_page", "f13_footnotes",
        "f14_running_header_footer",
    }  # fmt: skip


# --------------------------------------------------------------------------- #
# F-17 (partially fixed): the stored text is still not the printed text
# --------------------------------------------------------------------------- #

SENSITIVE = [
    "Mã sản phẩm TK_VND_01 và file bao_cao_2024.xlsx",
    "Email: ho_tro@agribank.com.vn; website https://agribank.com.vn/a_b?x=1&y=2",
    "Họ tên: <Tên khách hàng> & <Số CMND>",
]


def _stored(lines):
    doc = H.build_document(
        {
            "name": "esc",
            "ground_truth": "",
            "pages": [[T("text", s, 80 + 30 * i) for i, s in enumerate(lines)]],
        }
    )
    standard = doc.export_to_markdown()
    legal = N.normalize_document(doc).content
    return standard, legal


def test_control_list_marker_escapes_are_gone_from_the_stored_text():
    """What F-17 did fix: no backslash before '9.', '-', '+', '1)'."""
    _, legal = _stored(
        ["9. Khoản chín", "- Gạch đầu dòng", "+ Trường hợp cộng", "1) Điều kiện"]
    )
    assert [x for x in legal.split("\n") if x.strip()] == [
        "9. Khoản chín", "- Gạch đầu dòng", "+ Trường hợp cộng", "1) Điều kiện",
    ]  # fmt: skip


# Phase 12D5: F-17 fixed (the Legal serializer stores the printed text); xfail removed.
def test_f17_stored_legal_text_equals_the_printed_text():
    _, legal = _stored(SENSITIVE)
    assert [x for x in legal.split("\n") if x.strip()] == SENSITIVE


def test_control_display_of_those_lines_is_correct():
    """The Source page shows them correctly; only the stored / RAG text differs."""
    _, legal = _stored(SENSITIVE)
    assert H.legal_lines(legal) == SENSITIVE


def test_verified_html_in_ocr_text_is_inert():
    """No rehype-raw in the frontend and Docling escapes '<': a script tag in OCR
    text is stored as entities and displayed as literal text."""
    _, legal = _stored(["<script>alert(1)</script>", "<img src=x onerror=alert(1)>"])
    assert "<script" not in legal and "<img" not in legal
    assert H.legal_lines(legal) == [
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
    ]
    package = (HERE.parents[1] / "frontend" / "package.json").read_text(
        encoding="utf-8"
    )
    assert "rehype-raw" not in package


# --------------------------------------------------------------------------- #
# R2-02: Markdown emphasis changes numbers on the Source page (both modes)
# --------------------------------------------------------------------------- #


# Phase 12D5: R2-02 fixed (legal-display escapes every Markdown-significant character
# at render time); xfail removed.
@pytest.mark.parametrize(
    "line",
    [
        "Lãi suất = 5*3% (tối đa 15*2)",
        "Mức phí (*) áp dụng theo biểu phí (*) hiện hành",
        "Mã `TK01` dùng cho tài khoản thanh toán",
    ],
)
def test_r2_02_display_keeps_asterisks_and_backticks(line):
    _, legal = _stored([line])
    assert H.legal_lines(legal) == [line]


def test_control_r2_02_same_in_standard():
    standard, _ = _stored(["Lãi suất = 5*3% (tối đa 15*2)"])
    assert H.display_lines(standard) == ["Lãi suất = 53% (tối đa 152)"]


# --------------------------------------------------------------------------- #
# F-07: the record on the Source
# --------------------------------------------------------------------------- #


def test_verified_v120_asset_model_ignores_the_new_key():
    """Rollback: the v1.2.0 Asset model (BaseModel, two optional fields, default
    extra='ignore') reads a Source whose asset carries `extraction`."""
    from pydantic import BaseModel

    class AssetV120(
        BaseModel
    ):  # verbatim shape of f2fdf27:open_notebook/domain/notebook.py
        file_path: str | None = None
        url: str | None = None

    row = {
        "file_path": "/app/data/uploads/a.pdf",
        "extraction": {"mode": "legal", "status": "applied"},
    }
    assert AssetV120(**row).model_dump() == {
        "file_path": "/app/data/uploads/a.pdf",
        "url": None,
    }


def test_verified_standard_asset_is_stored_without_the_key_and_reprocessing_replaces_it():
    from open_notebook.domain.notebook import Asset

    assert "extraction" not in Asset(file_path="/x.pdf").model_dump()
    legal = Asset(file_path="/x.pdf", extraction={"mode": "legal", "status": "applied"})
    assert legal.model_dump()["extraction"]["status"] == "applied"
    # save_source assigns a NEW Asset each time: a later Standard run drops the record
    assert (
        "extraction" not in Asset(file_path=legal.file_path, url=legal.url).model_dump()
    )


# Phase 12D5: R2-03 fixed (field_validator on Asset.extraction); xfail removed.
def test_r2_03_domain_asset_tolerates_a_non_mapping_record():
    from open_notebook.domain.notebook import Asset

    assert Asset(file_path="/x.pdf", extraction="legacy-string").file_path == "/x.pdf"
    assert Asset(file_path="/x.pdf", extraction=["x"]).extraction is None
    assert "extraction" not in Asset(file_path="/x.pdf", extraction=7).model_dump()
    kept = Asset(file_path="/x.pdf", extraction={"mode": "legal", "status": "applied"})
    assert kept.extraction == {"mode": "legal", "status": "applied"}


# --------------------------------------------------------------------------- #
# R2-11: real content the layout model labelled PAGE_HEADER / PAGE_FOOTER
# --------------------------------------------------------------------------- #

LETTERHEAD = [
    [
        T("page_header", "NGÂN HÀNG NÔNG NGHIỆP MẪU", 30, 70, 300),
        T("page_header", "Số: 1234/QĐ-NHM-KHCN", 50, 70, 300),
        T("section_header", "QUYẾT ĐỊNH", 120),
        T("text", "Điều 1. Ban hành Quy định về phí dịch vụ.", 160),
        T(
            "page_footer",
            "(1) Mức phí chưa bao gồm thuế giá trị gia tăng 10%.",
            790,
            70,
            525,
        ),
    ],
    [T("text", "Điều 2. Quyết định có hiệu lực từ ngày ký.", 80)],
]


# was: test_control_r2_11_furniture_labelled_content_is_absent_in_both_modes (PHASE12D4
# evidence: it asserted the content was missing from Legal too, silently). Phase 12D5
# regression test: Standard (v1.2.0) still leaves it out; Legal keeps it and says so.
def test_regression_r2_11_furniture_labelled_content_is_kept_in_legal():
    standard, legal, result = outputs(LETTERHEAD)
    for text in (
        "Số: 1234/QĐ-NHM-KHCN",
        "NGÂN HÀNG NÔNG NGHIỆP MẪU",
        "(1) Mức phí chưa bao gồm thuế giá trị gia tăng 10%.",
    ):
        assert text not in standard and text in legal
    assert "furniture_text_kept" in {w["code"] for w in result.warnings}


# Phase 12D5: R2-11 fixed (header / footer text that appears once is kept); xfail removed.
def test_r2_11_unique_furniture_text_is_kept_or_reported():
    """EXPECTED: non-repeating furniture text is kept, or at least a warning names
    the page, so that an operator can see the document number never reached RAG."""
    _, legal, result = outputs(LETTERHEAD)
    kept = "Số: 1234/QĐ-NHM-KHCN" in legal
    reported = any(1 in (w.get("pages") or []) for w in result.warnings)
    assert kept or reported
