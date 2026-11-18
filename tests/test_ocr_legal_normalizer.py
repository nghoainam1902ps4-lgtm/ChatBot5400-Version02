"""Legal Document normalization (Phase 12, docs/ocr D-34) - unit tests.

The documents are built by Docling's REAL ReadingOrderModel from synthetic
layout elements (tests/legal_harness.py); checks run on what a CommonMark
renderer displays, the way the frontend shows the source to the reader.

Phase 12D3 (findings T-01, T-03 of the independent audit): the oracle is the
ground truth DECLARED in the fixtures (``gt`` annotations of every element),
never something the normalizer reports about itself; parametrized tests run
only on the fixtures that carry the data they assert on.
"""

from __future__ import annotations

import random
import socket
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("docling")

sys.path.insert(0, str(Path(__file__).parent))

import legal_harness as H  # noqa: E402

from open_notebook.ocr import legal_normalizer as N  # noqa: E402

FX = H.load_fixtures()
NAMES = [f["name"] for f in FX.FIXTURES]


def _with(*keys: str) -> list[str]:
    """Fixtures that declare at least one of ``keys`` (T-03: no empty cases)."""
    names = [f["name"] for f in FX.FIXTURES if any(f.get(k) for k in keys)]
    assert names, keys
    return names


# Phase 12D5: the (test, fixture) pairs that were RED on the unchanged 8d0c438
# normalizer are listed in docs/review/phase12d5/red_8d0c438_normalizer_tests.txt;
# they are all green with normalizer 1.2.0 (no xfail left in this module).


@pytest.fixture(scope="module")
def built():
    """name -> (fixture, document, standard markdown, legal result)."""
    out = {}
    for fx in FX.FIXTURES:
        doc = H.build_document(fx)
        standard = doc.export_to_markdown()
        # as in production (open_notebook/ocr/docling_extract.py): with the
        # element texts Docling had before its own merge (R2-01 evidence)
        res = N.normalize_document(doc, evidence=H.evidence(doc))
        out[fx["name"]] = (fx, doc, standard, res)
    return out


# --------------------------------------------------------------------------- #
# The oracle itself must be able to fail (T-01)
# --------------------------------------------------------------------------- #


def _truth_lines(fx):
    """Everything the fixture declares, in declared order (optional units too)."""
    return [u["text"] for u in H.expected_units(fx)]


def test_oracle_accepts_the_declared_truth():
    for fx in FX.FIXTURES:
        p = H.preservation(fx, _truth_lines(fx))
        assert (
            p["false_deletion"],
            p["false_merge"],
            p["false_insertion"],
            p["false_reordering"],
            p["placeholders_lost"],
        ) == (0, 0, 0, 0, 0), fx["name"]


def test_oracle_sees_a_repeated_line_deleted_once():
    fx = FX.by_name("f25_appendix_unit_line_every_page")
    lines = _truth_lines(fx)
    lines.remove("Đơn vị tính: triệu đồng")  # 2 of 3 occurrences left
    p = H.preservation(fx, lines)
    assert p["false_deletion"] == 1 and p["false_deletion_tokens"] == 5
    assert not p["critical_ok"]  # declared 3 times, shown twice


def test_oracle_sees_deletion_merge_insertion_and_reordering():
    fx = FX.by_name("f29_footnote_labelled_text")
    truth = _truth_lines(fx)
    assert H.preservation(fx, truth[:-1])["false_deletion"] == 1
    merged = truth[:2] + [f"{truth[2]} {truth[3]}"] + truth[4:]
    p = H.preservation(fx, merged)
    assert p["false_merge"] == 1 and p["false_deletion"] == 2
    assert (
        H.preservation(fx, truth + ["Câu này không có trong văn bản."])[
            "false_insertion"
        ]
        == 1
    )
    swapped = [truth[1], truth[0]] + truth[2:]
    assert H.preservation(fx, swapped)["false_reordering"] == 1


def test_oracle_does_not_use_the_normalizer_report():
    """The verdict is a function of the declared truth and of the OUTPUT only:
    nothing the normalizer reports about itself is read (T-01)."""
    import ast
    import inspect

    import phase12_oracle as O

    tree = ast.parse(inspect.getsource(O))
    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    imports = {
        a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names
    } | {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    for forbidden in ("operations", "warnings", "counts", "text_before", "persistable"):
        assert forbidden not in names, forbidden
    assert not any("legal_normalizer" in i for i in imports)


def test_declared_truth_matches_the_ground_truth_string():
    """Two independent statements of the truth agree (except documented OCR loss)."""
    differs = set()
    for fx in FX.FIXTURES:
        units = " ".join(
            u["text"].replace(" | ", " ")
            for u in H.expected_units(fx)
            if u["gt"] in ("keep", "join") and u["kind"] != "picture"
        )
        if " ".join(units.split()) != " ".join(fx["ground_truth"].split()):
            differs.add(fx["name"])
    # f03: the OCR lost a word that the ground truth has; f22: the lone "1" is
    # kept in the ground truth string although it may be removed.
    assert differs == {"f03_missing_word_not_invented", "f22_single_page_number_kept"}


# --------------------------------------------------------------------------- #
# Preservation: every fixture, measured against the declared truth
# --------------------------------------------------------------------------- #


def _measure(fx, doc, standard, res):
    legal = H.preservation(
        fx, H.legal_lines(res.content), res.content, document=res.document
    )
    std = H.preservation(
        fx,
        H.display_lines(standard),
        standard,
        document=doc,
        pictures_traversed=False,
    )
    return legal, std


@pytest.mark.parametrize("name", NAMES)
def test_no_false_deletion_merge_or_insertion(built, name):
    """Identity attribution (Phase 12D5, R2-14): every declared element is found
    by its provenance, so an artifact with the same text never stands in for a
    deleted required unit."""
    fx, doc, standard, res = built[name]
    legal, std = _measure(fx, doc, standard, res)
    assert legal["attribution"] == "identity"
    assert legal["not_located"] == [], legal["not_located"]
    assert legal["false_deletion"] == 0, legal["false_deletion_units"]
    assert legal["false_deletion_tokens"] == 0, legal["false_deletion_units"]
    assert legal["false_merge"] == 0, legal["false_merge_lines"]
    assert legal["false_insertion"] == 0, legal["false_insertion_lines"]
    assert legal["false_insertion_tokens"] == 0
    assert legal["placeholders_lost"] == 0, legal["placeholders_lost_ids"]
    assert legal["tables_ok"]
    # A changed character inside an item is allowed only when Docling made the
    # change upstream, it cannot be undone from the evidence, and the Legal
    # result says so with a located warning (R2-01).
    reported = {
        p
        for w in res.warnings
        if w.get("code") in ("upstream_dehyphenation", "upstream_merge_kept")
        for p in w.get("pages") or []
    }
    for a in legal["altered"]:
        assert set(a["pages"]) <= reported, a
    # Reading order: Docling's. Zero unless the fixture documents that Docling
    # itself reorders that layout, and then never worse than the standard export.
    if fx.get("upstream_reordering"):
        assert legal["false_reordering"] <= std["false_reordering"]
    else:
        assert legal["false_reordering"] == 0


@pytest.mark.parametrize("name", _with("protected"))
def test_critical_fields_exact_count(built, name):
    fx, _, _, res = built[name]
    p = H.preservation(
        fx, H.legal_lines(res.content), res.content, document=res.document
    )
    assert p["critical_ok"], [c for c in p["critical_fields"] if not c["ok"]]


@pytest.mark.parametrize("name", _with("markers"))
def test_markers_displayed_as_in_original(built, name):
    fx, _, _, res = built[name]
    hit, total = H.markers_displayed(fx, H.legal_lines(res.content))
    assert total > 0 and hit == total


@pytest.mark.parametrize("name", _with("present_lines"))
def test_lines_that_must_stay(built, name):
    fx, _, _, res = built[name]
    lines = H.legal_lines(res.content)
    for line in fx["present_lines"]:
        assert line in lines, line


@pytest.mark.parametrize("name", _with("expect_removed"))
def test_artifacts_removed_when_the_evidence_is_sufficient(built, name):
    fx, _, standard, res = built[name]
    lines = H.legal_lines(res.content)
    for line in fx["expect_removed"]:
        assert line in H.display_lines(standard)  # it was there
        assert line not in lines, line


# Phase 12D7 (owner decision after Windows finding E1-09): Legal never joins
# across pages. was: test_joins_made_when_the_evidence_is_sufficient. The
# fixtures still DECLARE which joins the old rules made (ground truth unchanged);
# none is made now and no content is lost (test_no_false_deletion_merge_or_insertion).
@pytest.mark.parametrize("name", _with("expect_joined"))
def test_no_cross_page_join_even_where_the_old_rules_joined(built, name):
    fx, _, _, res = built[name]
    lines = H.legal_lines(res.content)
    assert res.counts.get("join_across_pages", 0) == 0
    for line in fx["expect_joined"]:
        assert line not in lines, line  # never one paragraph across the page break


@pytest.mark.parametrize("name", _with("must_not_join", "forbidden"))
def test_no_forbidden_join(built, name):
    fx, _, _, res = built[name]
    lines = H.legal_lines(res.content)
    for left, right in fx.get("must_not_join", []):
        assert not any(left in line and right in line for line in lines), (left, right)
    for phrase in fx.get("forbidden", []):
        assert not any(phrase in line for line in lines), phrase


@pytest.mark.parametrize("name", _with("expect_placeholders", "expect_warnings"))
def test_placeholders_and_warnings(built, name):
    fx, _, _, res = built[name]
    if "expect_placeholders" in fx:
        assert res.content.count("<!-- image -->") == fx["expect_placeholders"]
    codes = {w["code"] for w in res.warnings}
    for code in fx.get("expect_warnings", []):
        assert code in codes


@pytest.mark.parametrize("name", _with("table_identical"))
def test_tables_identical(built, name):
    _, doc, _, res = built[name]
    assert doc.tables
    for table in doc.tables:
        assert table.export_to_markdown(doc) in res.content


@pytest.mark.parametrize("name", NAMES)
def test_reading_order_not_changed(built, name):
    """Legal mode never reorders: the lines it shares with Standard come in the same order.

    Where Legal undid a merge Docling made (R2-01), the Standard export is no
    reference for the order (its merged line is not in the source); there the
    order is held against the DECLARED order by the identity oracle instead."""
    fx, doc, standard, res = built[name]
    if any(w.get("code") == "upstream_merge_undone" for w in res.warnings):
        legal, _ = _measure(fx, doc, standard, res)
        assert legal["false_reordering"] == 0
        return
    std, leg = H.display_lines(standard), H.legal_lines(res.content)
    shared = [x for x in leg if x in set(std)]
    cursor = 0
    for (
        line
    ) in shared:  # `shared` must be a subsequence of `std` (repeated lines included)
        while cursor < len(std) and std[cursor] != line:
            cursor += 1
        assert cursor < len(std), line
        cursor += 1


@pytest.mark.parametrize("name", NAMES)
def test_idempotent_and_deterministic(built, name):
    _, doc, _, res = built[name]
    again = N.normalize_document(res.document)
    assert again.content == res.content
    assert not any(
        o.op in ("join_across_pages", "upstream_merge_undone") for o in again.operations
    )
    assert N.normalize_document(doc, evidence=H.evidence(doc)).content == res.content


@pytest.mark.parametrize("name", NAMES)
def test_source_document_untouched(built, name):
    _, doc, standard, _ = built[name]
    N.normalize_document(doc)
    assert doc.export_to_markdown() == standard


@pytest.mark.parametrize("name", NAMES)
def test_stored_text_is_the_displayed_text(built, name):
    """F-17: no Markdown escape of clause markers is stored (RAG = display = copy)."""
    _, _, _, res = built[name]
    for line in res.content.split("\n"):
        assert not line.lstrip().startswith(("\\-", "\\+", "\\*")), line
        head = line.lstrip()[:12]
        assert "\\." not in head and "\\)" not in head, line


def _built_by_upstream_docling(name):
    """The fixture as UPSTREAM Docling 2.129.0 builds it: its ``_merge_elements``
    removes the hyphen (Phase 12D9 patches that, D8-03); Legal must still read
    such a document safely (a soft hyphen is still removed upstream-style)."""
    from open_notebook.ocr import docling_patches

    with docling_patches.upstream_text_preservation():
        doc = H.build_document(FX.by_name(name))
    return doc, H.evidence(doc)


def test_upstream_dehyphenation_without_evidence_is_kept_and_reported():
    """R2-01 safe default: without the element texts the removed hyphen cannot be
    known ('-' or a soft hyphen), so Docling's text is kept and the pages named;
    with them (production) the two blocks are restored exactly."""
    doc, evidence = _built_by_upstream_docling("d5_r201_hyphen_lowercase")
    with_evidence = N.normalize_document(doc, evidence=evidence)
    blind = N.normalize_document(doc)
    assert "phingân hàng" in blind.content
    codes = {w["code"]: w for w in blind.warnings}
    assert codes["upstream_dehyphenation"]["pages"] == [1, 2]
    assert H.legal_lines(with_evidence.content)[:2] == [
        "Áp dụng cho tổ chức tín dụng phi-",
        "ngân hàng và chi nhánh ngân hàng nước ngoài.",
    ]
    assert "upstream_merge_undone" in {w["code"] for w in with_evidence.warnings}


def test_evidence_that_does_not_match_the_document_is_not_used():
    """Evidence only confirms a part character for character; a mismatching text
    (another document, a stale conversion) is ignored."""
    doc, real = _built_by_upstream_docling("d5_r201_hyphen_lowercase")
    evidence = {k: v.replace("phi-", "phí-") for k, v in real.items()}
    res = N.normalize_document(doc, evidence=evidence)
    assert "phingân hàng" in res.content and "phí-" not in res.content
    assert "upstream_dehyphenation" in {w["code"] for w in res.warnings}


def test_d8_03_patched_docling_keeps_the_hyphen_and_legal_splits_without_evidence(
    built,
):
    """Phase 12D9 (D8-03): Docling keeps the hyphen when it joins the blocks of
    two pages and records where the continuation starts; Standard keeps every
    character, Legal shows the two blocks apart - no evidence needed, nothing
    restored by guess."""
    fx, doc, standard, _ = built["d5_r201_hyphen_lowercase"]
    assert "phi-ngân hàng" in standard and "phingân" not in standard
    res = N.normalize_document(doc)
    assert H.legal_lines(res.content)[:2] == [
        "Áp dụng cho tổ chức tín dụng phi-",
        "ngân hàng và chi nhánh ngân hàng nước ngoài.",
    ]
    codes = {w["code"] for w in res.warnings}
    assert "upstream_merge_undone" in codes and "upstream_dehyphenation" not in codes
    again = N.normalize_document(res.document)
    assert again.content == res.content  # idempotent


def test_upstream_space_merge_is_split_back_exactly_without_evidence():
    """A space join is undone from the char spans alone: every part keeps exactly
    the text Docling joined (here two independent documents)."""
    fx = FX.by_name("d5_r201_two_documents_signer_then_title")
    doc = H.build_document(fx)
    res = N.normalize_document(doc)
    lines = H.legal_lines(res.content)
    assert "Nguyễn Văn An" in lines
    assert "Phụ lục 01 ban hành kèm theo Quyết định số 12/QĐ-NHM" in lines
    assert res.counts.get("upstream_merge_undone") == 1


# --------------------------------------------------------------------------- #
# The reported case and the audit's counter-examples, spelled out
# --------------------------------------------------------------------------- #


def test_reported_case_khoan_9_with_sufficient_evidence(built):
    _, _, standard, res = built["f33_five_pages_real_page_numbers_and_join"]
    assert "\n\n6\n\n" in standard
    lines = H.legal_lines(res.content)
    # was: the two halves joined into one sentence (Phase 12D7: no cross-page join)
    assert (
        "9. Dịch vụ phi tài chính là dịch vụ không làm thay đổi số dư trên tài khoản của khách hàng."
        not in lines
    )
    assert "9. Dịch vụ phi tài chính là dịch vụ không làm thay đổi số" in lines
    assert "dư trên tài khoản của khách hàng." in lines
    assert res.counts.get("join_across_pages", 0) == 0
    assert res.counts["page_number_to_furniture"] == 5


def test_two_page_excerpt_keeps_suspected_page_numbers_and_reports_why(built):
    """F-02: two pages are no pattern; the number stays, so the clause is not joined."""
    _, _, _, res = built["f02_clause_across_pages"]
    lines = H.legal_lines(res.content)
    assert "6" in lines and "7" in lines
    assert "join_across_pages" not in res.counts
    assert any(w["code"] == "page_number_kept" for w in res.warnings)
    assert "<!-- image -->" not in res.content


def test_missing_word_is_never_invented(built):
    _, _, _, res = built["f03_missing_word_not_invented"]
    assert "thay đổi số" not in res.content


def test_standard_renumbers_but_legal_does_not(built):
    _, _, standard, res = built["f05_list_starts_at_10_not_continuous"]
    # the browser draws 6 and 12 where the source says 7 and 13
    assert "6. Lưu trữ hồ sơ theo quy định." in H.display_lines(standard)
    assert "12. Thực hiện các nhiệm vụ khác." in H.display_lines(standard)
    assert "7. Lưu trữ hồ sơ theo quy định." in H.legal_lines(res.content)
    assert "13. Thực hiện các nhiệm vụ khác." in H.legal_lines(res.content)


def test_synthesized_number_avoided(built):
    _, _, standard, res = built["f01_one_page_decision"]
    assert "5. đ)" in standard
    assert "5. đ)" not in res.content and "đ) Các trường hợp" in res.content
    assert res.counts["synthesized_number_avoided"] == 1


def test_text_inside_picture_recovered(built):
    _, _, standard, res = built["f16_text_inside_picture"]
    assert "Phí rút tiền" not in standard
    assert "Phí rút tiền là 1.100 đồng mỗi giao dịch." in res.content


def test_repeated_text_lines_are_reported_never_removed(built):
    """F-01: a repeated TEXT line is content unless the layout model says otherwise."""
    for name in (
        "f14_running_header_footer",
        "f25_appendix_unit_line_every_page",
        "f26_bundle_of_one_page_notices",
        "f37_repeated_business_lines",
    ):
        _, _, _, res = built[name]
        assert "running_header_footer_to_furniture" not in res.counts, name
    _, _, _, res = built["f14_running_header_footer"]
    assert res.content.count("NGÂN HÀNG MẪU - QUY ĐỊNH NỘI BỘ") == 4
    warning = next(w for w in res.warnings if w["code"] == "repeated_line_kept")
    assert warning["pages"] == [1, 2, 3, 4] and "NGÂN HÀNG" not in repr(warning)


def test_layout_labelled_header_in_body_goes_to_furniture():
    """The only running header removed: one the layout model itself labelled."""
    from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
    from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
    from docling_core.types.doc.labels import DocItemLabel

    doc = DoclingDocument(name="hdr")
    for page in (1, 2, 3):
        doc.add_page(page_no=page, size=Size(width=595, height=842))
        top = BoundingBox(l=70, t=25, r=320, b=37, coord_origin=CoordOrigin.TOPLEFT)
        doc.add_text(
            label=DocItemLabel.PAGE_HEADER,
            text="QUY ĐỊNH NỘI BỘ",
            prov=ProvenanceItem(page_no=page, bbox=top, charspan=(0, 1)),
        )
        body = BoundingBox(l=70, t=100, r=525, b=128, coord_origin=CoordOrigin.TOPLEFT)
        doc.add_text(
            label=DocItemLabel.TEXT,
            text=f"Nội dung trang {page}.",
            prov=ProvenanceItem(page_no=page, bbox=body, charspan=(0, 1)),
        )
    res = N.normalize_document(doc)
    assert "QUY ĐỊNH NỘI BỘ" not in res.content
    assert res.counts["running_header_footer_to_furniture"] == 3
    assert all(f"Nội dung trang {p}." in res.content for p in (1, 2, 3))


def test_medium_and_large_pictures_leave_a_trace(built):
    """F-06: 5 %, 12 % and 20 % pictures without text keep the placeholder + a located warning."""
    _, _, _, res = built["f32_pictures_5_12_20_percent"]
    located = [w for w in res.warnings if w["code"] == "picture_without_text"]
    assert len(located) == 3
    assert all(
        w["pages"] == [1] and len(w["bbox"]) == 4 and w["area_ratio"] >= 0.04
        for w in located
    )


def test_small_picture_drop_is_recorded_with_page_and_bbox(built):
    _, _, _, res = built["f17_signature_block"]
    drops = [o for o in res.operations if o.op == "image_placeholder_dropped"]
    assert len(drops) == 2 and all(o.pages == [1] and o.bboxes for o in drops)


# --------------------------------------------------------------------------- #
# Page numbers: evidence thresholds (F-02)
# --------------------------------------------------------------------------- #


def _doc(pages):
    return H.build_document({"pages": pages})


def _numbered(
    n_pages, value=lambda p: p, x=lambda p: 290, y=800, body=True, label="text"
):
    E = FX.E
    pages = []
    for p in range(1, n_pages + 1):
        page = (
            [E("text", f"Nội dung trang {p} của tài liệu thử nghiệm.", y=100, h=28)]
            if body
            else []
        )
        if value(p) is not None:
            page.append(E(label, str(value(p)), x=x(p), y=y, w=16, h=12))
        pages.append(page)
    return pages


@pytest.mark.parametrize("n_pages,removed", [(1, 0), (2, 0), (3, 3), (5, 5), (40, 40)])
def test_page_numbers_need_three_pages(n_pages, removed):
    res = N.normalize_document(_doc(_numbered(n_pages)))
    assert res.counts.get("page_number_to_furniture", 0) == removed


def test_page_numbers_need_sixty_percent_of_the_pages():
    few = N.normalize_document(
        _doc(_numbered(10, value=lambda p: p if p <= 5 else None))
    )
    assert "page_number_to_furniture" not in few.counts  # 5 of 10 pages
    enough = N.normalize_document(
        _doc(_numbered(10, value=lambda p: p if p <= 6 else None))
    )
    assert enough.counts["page_number_to_furniture"] == 6


def test_page_number_values_must_fit_the_document():
    years = N.normalize_document(_doc(_numbered(5, value=lambda p: 2020 + p)))
    assert "page_number_to_furniture" not in years.counts
    for y in range(2021, 2026):
        assert str(y) in years.content
    offset = N.normalize_document(
        _doc(_numbered(5, value=lambda p: 40 + p))
    )  # pages 41..45 of a long file
    assert offset.counts["page_number_to_furniture"] == 5


def test_page_numbers_need_a_consistent_horizontal_position():
    scattered = N.normalize_document(_doc(_numbered(5, x=lambda p: 80 + 90 * p)))
    assert "page_number_to_furniture" not in scattered.counts
    mirrored = N.normalize_document(
        _doc(_numbered(6, x=lambda p: 520 if p % 2 else 60))
    )
    assert mirrored.counts["page_number_to_furniture"] == 6


def test_numbers_at_the_body_margin_are_kept():
    """Detached clause numbers start where the paragraphs start."""
    res = N.normalize_document(_doc(_numbered(6, x=lambda p: 70, y=62)))
    assert "page_number_to_furniture" not in res.counts


def test_numbers_inside_the_body_are_never_candidates():
    res = N.normalize_document(_doc(_numbered(6, y=400)))
    assert "page_number_to_furniture" not in res.counts
    for p in range(1, 7):
        assert f"\n\n{p}\n\n" in f"\n\n{res.content}\n\n"


def test_hundred_pages_with_stray_figures_at_the_bottom():
    """A long report whose last cell of every page is a figure: nothing is removed."""
    rng = random.Random(12)
    values = {
        p: rng.choice([3, 7, 12, 25, 40, 55, 68, 80, 95, 120, 150])
        for p in range(1, 101)
    }
    res = N.normalize_document(
        _doc(_numbered(100, value=lambda p: values[p], x=lambda p: 450))
    )
    assert "page_number_to_furniture" not in res.counts
    assert res.content.count("Nội dung trang") == 100


def test_legal_numeric_fields_at_page_edges_survive():
    E = FX.E
    edge = ["2024", "2025", "2026", "15", "500", "12", "3"]
    pages = [
        [
            E("text", f"Chỉ tiêu của trang {i + 1}:", y=100, h=28),
            E("text", v, x=450, y=790, w=40, h=12),
        ]
        for i, v in enumerate(edge)
    ]
    res = N.normalize_document(_doc(pages))
    lines = H.legal_lines(res.content)
    for v in edge:
        assert v in lines


# --------------------------------------------------------------------------- #
# Cross-page joins: every rule can say no (F-03)
# --------------------------------------------------------------------------- #


def _a(text="Khách hàng được hưởng các quyền lợi theo thỏa thuận đã ký và", **kw):
    kw.setdefault("y", 700)
    kw.setdefault("h", 28)
    return FX.E("text", text, **kw)


def _b(text="các quy định khác của ngân hàng.", **kw):
    kw.setdefault("y", 60)
    return FX.E("text", text, **kw)


def test_join_baseline_is_not_made():
    """was: test_join_baseline_is_made. Phase 12D7: the cut paragraph stays as two
    paragraphs, in reading order; nothing is joined, nothing hidden."""
    a, b = _a(), _b()
    res = N.normalize_document(_join_case(a, b))
    assert res.counts.get("join_across_pages", 0) == 0
    lines = H.legal_lines(res.content)
    assert a["text"] in lines and b["text"] in lines
    assert lines.index(a["text"]) < lines.index(b["text"])


@pytest.mark.parametrize(
    "start",
    ["a. điểm mới", "a/ điểm mới", "a) điểm mới", "đ. điểm mới", "đ) điểm mới", "(a) điểm mới", "(1) điểm mới", "a.1) điểm mới",
     "a.1. điểm mới", "1.2.3 điểm mới", "i. điểm mới", "ii) điểm mới", "- gạch đầu dòng", "+ dấu cộng", "điều 5 quy định", "khoản 2 quy định"],
)  # fmt: skip
def test_join_refused_when_the_next_page_starts_a_new_unit(start):
    res = N.normalize_document(_join_case(_a(), _b(start)))
    assert "join_across_pages" not in res.counts, start
    assert start in H.legal_lines(res.content)


def _join_case(a, b, extra_p1=(), extra_p2=(), pages_before=3, footers=True):
    E = FX.E

    def foot(n):
        return [FX.footer(n)] if footers else []

    filler = [
        [E("text", f"Trang đệm {i}.", y=100, h=28), *foot(i)]
        for i in range(1, pages_before + 1)
    ]
    return _doc(
        filler
        + [
            [E("text", "Điều 9. Nội dung.", y=100, h=28), a, *extra_p1, *foot(4)],
            [b, *extra_p2, *foot(5)],
        ]
    )


def test_doclings_cross_page_merge_is_split_back_even_when_the_rules_accept_it():
    """Phase 12D7 (E1-09), join type B: Docling itself joined the paragraph across
    the page break (its rule: ASCII lowercase end + letter start). The provenance
    char spans prove the two parts, so Legal shows them apart as printed; the old
    rules accepted this continuation and kept Docling's join. Standard keeps it
    (v1.2.0 behaviour)."""
    a = _a("Khách hàng thực hiện theo quy định của pháp luật hiện hành")
    b = _b("và các văn bản hướng dẫn của ngân hàng.")
    doc = _join_case(a, b)
    merged = f"{a['text']} {b['text']}"
    assert merged in doc.export_to_markdown()  # Docling's own merge
    res = N.normalize_document(doc)
    lines = H.legal_lines(res.content)
    assert a["text"] in lines and b["text"] in lines
    assert merged not in res.content
    assert res.counts.get("upstream_merge_undone", 0) >= 1
    assert res.counts.get("join_across_pages", 0) == 0


E1_09 = {
    # the three shapes the old rules joined on real scans (Windows, Phase 12E1)
    "point whose marker OCR lost": (
        "a) giấy đề nghị vay vốn theo mẫu của ngân hàng",
        "phương án sử dụng vốn khả thi;",
    ),
    "unit line damaged by OCR": (
        "Bảng 2. Dư nợ cho vay theo kỳ hạn của chi nhánh",
        "đvt- triệu đồng",
    ),
    "running title in lowercase at the top of the page": (
        "Điều 4. Chi nhánh thực hiện báo cáo định kỳ theo",
        "quy định cho vay đối với khách hàng cá nhân",
    ),
}


@pytest.mark.parametrize("case", sorted(E1_09))
def test_e1_09_real_scan_shapes_are_never_one_paragraph(case):
    first, second = E1_09[case]
    res = N.normalize_document(_join_case(_a(first), _b(second)))
    lines = H.legal_lines(res.content)
    assert first in lines and second in lines, case
    assert not any(first in line and second in line for line in lines), case
    assert res.counts.get("join_across_pages", 0) == 0


@pytest.mark.parametrize(
    "case,a,b,reason",
    [
        ("narrow first part", _a(w=200), _b(), "narrower"),
        (
            "footnote number",
            _a("1 Thông tư số 39/2016/TT-NHNN của Ngân hàng Nhà nước và", y=760, h=12),
            _b(),
            "footnote",
        ),
        ("footnote star", _a("* Áp dụng với khách hàng cá nhân và"), _b(), "footnote"),
        (
            "footnote paren",
            _a("(1) Áp dụng với khách hàng cá nhân và"),
            _b(),
            "footnote",
        ),
        (
            "single line in the footer band, no footer marked by the layout model",
            _a(y=780, h=14),
            _b(),
            "bottom band",
        ),
        ("indented continuation", _a(), _b(x=110, w=415), "indent"),
        ("continuation not at the top", _a(), _b(y=500), "upper"),
        ("other column", _a(x=70, w=210), _b(x=315, w=210), "column"),
        # not near misses: refused by the text itself, no warning needed
        (
            "sentence finished",
            _a("Khách hàng được hưởng các quyền lợi theo thỏa thuận đã ký."),
            _b(),
            None,
        ),
        ("colon", _a("Hồ sơ gồm:"), _b(), None),
        ("uppercase start", _a(), _b("Các quy định khác của ngân hàng."), None),
    ],
)
def test_join_refused_and_reason_reported(case, a, b, reason):
    """Phase 12D7: no join is attempted any more, so no refusal reason either
    (was: the near-miss reason in a join_not_made warning)."""
    footers = "no footer marked" not in case
    res = N.normalize_document(_join_case(a, b, footers=footers), include_text=True)
    assert "join_across_pages" not in res.counts, case
    lines = H.legal_lines(res.content)
    assert a["text"] in lines and b["text"] in lines, case
    assert not [w for w in res.warnings if w["code"] == "join_not_made"], case


def test_single_line_at_the_page_bottom_is_not_joined_either():
    """f24's situation (the layout model separated the footer from the last body
    line). was: ..._is_joined_when_the_layout_marks_the_footer_below_it."""
    res = N.normalize_document(_join_case(_a(y=765, h=14), _b(), footers=True))
    assert res.counts.get("join_across_pages", 0) == 0


def test_join_refused_across_a_table_a_picture_and_a_blank_page():
    E = FX.E
    table = E("table", y=40, h=15, rows=[["A", "B"], ["1", "2"]])
    assert (
        "join_across_pages"
        not in N.normalize_document(_join_case(_a(), _b(y=70), extra_p2=[table])).counts
    )
    big = E("picture", x=70, y=730, w=455, h=60)
    assert (
        "join_across_pages"
        not in N.normalize_document(_join_case(_a(y=690), _b(), extra_p1=[big])).counts
    )
    blank = _doc(
        [
            [_a(), FX.footer(1)],
            [],
            [_b(), FX.footer(3)],
            [E("text", "Hết.", y=100)],
            [E("text", "Hết.", y=100)],
        ]
    )
    assert "join_across_pages" not in N.normalize_document(blank).counts


def test_join_refused_when_the_first_part_repeats_on_the_next_page():
    """A running footer of a short document is never the start of a sentence."""
    E = FX.E
    foot = "Tài liệu lưu hành nội bộ của ngân hàng thương mại mẫu và các công ty con"
    pages = [
        [E("text", "Điều 1. Phạm vi.", y=100, h=28), E("text", foot, y=700, h=28)],
        [
            E("text", "các nội dung khác thực hiện theo quy định.", y=60),
            E("text", foot, y=700, h=28),
        ],
    ]
    res = N.normalize_document(_doc(pages))
    assert "join_across_pages" not in res.counts


# --------------------------------------------------------------------------- #
# Property: text outside the page edges is never lost (seeded, no new dependency)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("seed", range(12))
def test_property_body_tokens_always_survive(seed):
    rng = random.Random(seed)
    E = FX.E
    words = [
        "khoản",
        "vay",
        "lãi",
        "suất",
        "2024",
        "15",
        "7,5%",
        "đồng",
        "a)",
        "đ)",
        "1.",
        "Điều",
        "số",
        "và",
        "theo",
        "quy",
        "định",
        "-",
        "(1)",
        "3",
    ]
    pages, expected = [], []
    for p in range(rng.randint(1, 9)):
        page, y = [], 90.0
        for _ in range(rng.randint(0, 9)):
            text = " ".join(rng.choice(words) for _ in range(rng.randint(1, 9)))
            label = rng.choice(["text", "text", "text", "list_item", "section_header"])
            h = rng.choice([12, 14, 28, 42])
            if y + h > 750:
                break
            page.append(
                E(
                    label,
                    text,
                    x=rng.choice([70, 70, 90, 315]),
                    y=y,
                    w=rng.choice([455, 300, 210, 60]),
                    h=h,
                )
            )
            expected.append(text)
            y += h + rng.choice([6, 12, 30, 200])
        if rng.random() < 0.6:
            page.append(
                E(
                    "text",
                    str(rng.choice([p + 1, p + 1, 2024, 7])),
                    x=rng.choice([290, 70, 450]),
                    y=800,
                    w=16,
                    h=12,
                )
            )
        if rng.random() < 0.3:
            page.append(E("picture", x=70, y=760, w=rng.choice([40, 200]), h=30))
        pages.append(page)
    doc = _doc(pages)
    standard = doc.export_to_markdown()
    res = N.normalize_document(doc)
    from collections import Counter

    shown = Counter(H.display_text(H.legal_display_markdown(res.content)).split())
    need = Counter(" ".join(expected).split())
    assert not (need - shown), (seed, need - shown)
    assert doc.export_to_markdown() == standard
    assert N.normalize_document(res.document).content == res.content


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


def _plain_doc():
    from docling_core.types.doc.document import DoclingDocument
    from docling_core.types.doc.labels import DocItemLabel, GroupLabel

    doc = DoclingDocument(name="noprov")
    doc.add_text(
        label=DocItemLabel.TEXT, text="Đoạn không có provenance và chưa kết thúc"
    )
    doc.add_picture()
    doc.add_text(label=DocItemLabel.TEXT, text="6")
    doc.add_text(label=DocItemLabel.TEXT, text="tiếp tục ở đây.")
    group = doc.add_group(label=GroupLabel.LIST, name="list")
    doc.add_list_item(text="Mục không có marker", enumerated=True, parent=group)
    return doc


def test_document_without_provenance_keeps_everything():
    doc = _plain_doc()
    res = N.normalize_document(doc)
    lines = H.legal_lines(res.content)
    for line in (
        "Đoạn không có provenance và chưa kết thúc",
        "6",
        "tiếp tục ở đây.",
        "Mục không có marker",
    ):
        assert line in lines
    assert "join_across_pages" not in res.counts
    assert "page_number_to_furniture" not in res.counts
    assert "<!-- image -->" in res.content  # no evidence about the picture: kept


def test_empty_document():
    from docling_core.types.doc.document import DoclingDocument

    res = N.normalize_document(DoclingDocument(name="empty"))
    assert res.content == ""


def test_fallback_on_failure_keeps_standard(monkeypatch):
    doc = _plain_doc()
    standard = doc.export_to_markdown()

    def boom(*a, **k):
        raise RuntimeError("malformed")

    monkeypatch.setattr(N, "normalize_document", boom)
    content, meta = N.normalize_or_fallback(doc)
    assert content == standard
    assert meta["legal_normalization_status"] == "failed"
    assert meta["legal_normalization_error"] == "RuntimeError"


def test_limits_fall_back(monkeypatch):
    doc = _plain_doc()
    monkeypatch.setattr(N, "MAX_ITEMS", 2)
    with pytest.raises(N.NormalizationLimitError):
        N.normalize_document(doc)
    content, meta = N.normalize_or_fallback(doc)
    assert content == doc.export_to_markdown()
    assert meta["legal_normalization_status"] == "failed"


def test_time_budget_falls_back(monkeypatch):
    """F-10: a document that takes too long is returned unnormalized, with a status."""
    doc = _doc(_numbered(30))
    monkeypatch.setattr(N, "TIME_BUDGET_SECONDS", 0.0)
    with pytest.raises(N.NormalizationLimitError, match="time budget"):
        N.normalize_document(doc)
    content, meta = N.normalize_or_fallback(doc)
    assert content == doc.export_to_markdown()
    assert meta["legal_normalization_error"] == "NormalizationLimitError"


def test_malformed_object_falls_back_without_raising():
    class Broken:
        texts = None

        def model_copy(self, **k):
            raise TypeError("not a DoclingDocument")

        def export_to_markdown(self):
            return "x"

    content, meta = N.normalize_or_fallback(Broken())
    assert content == "x" and meta["legal_normalization_status"] == "failed"


def test_no_network_calls(built, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    for fx, doc, _, _ in built.values():
        N.normalize_document(doc)


def test_html_and_markdown_injection_not_introduced():
    from docling_core.types.doc.document import DoclingDocument
    from docling_core.types.doc.labels import DocItemLabel

    doc = DoclingDocument(name="inj")
    doc.add_text(
        label=DocItemLabel.TEXT,
        text="<script>alert(1)</script> [x](javascript:alert(1))",
    )
    doc.add_text(label=DocItemLabel.TEXT, text="# không phải tiêu đề")
    doc.add_text(label=DocItemLabel.TEXT, text="> không phải trích dẫn")
    res = N.normalize_document(doc)
    # Phase 12D5 (F-17): the printed text is stored; only the "<" that would OPEN
    # raw HTML is neutralised - no consumer ever receives active markup
    assert "<script>" not in res.content and "&lt;script>" in res.content
    assert "[x](javascript:alert(1))" in res.content  # printed text, not a link
    lines = H.legal_lines(res.content)
    assert "<script>alert(1)</script> [x](javascript:alert(1))" in lines
    assert "# không phải tiêu đề" in lines and "> không phải trích dẫn" in lines


# --------------------------------------------------------------------------- #
# Performance: relative, with joins, headers, tables and pictures (F-10)
# --------------------------------------------------------------------------- #


def _big(
    n_pages, joins=True, pictures=False, tables=False, short_items=0, header=False
):
    from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
    from docling_core.types.doc.document import (
        DoclingDocument,
        ProvenanceItem,
        TableCell,
        TableData,
    )
    from docling_core.types.doc.labels import DocItemLabel

    def prov(page, left, t, r, b):
        return ProvenanceItem(
            page_no=page,
            bbox=BoundingBox(l=left, t=t, r=r, b=b, coord_origin=CoordOrigin.TOPLEFT),
            charspan=(0, 1),
        )

    doc = DoclingDocument(name="big")
    for page in range(1, n_pages + 1):
        doc.add_page(page_no=page, size=Size(width=595, height=842))
        if header:
            doc.add_text(
                label=DocItemLabel.TEXT,
                text="NGÂN HÀNG MẪU - QUY ĐỊNH NỘI BỘ",
                prov=prov(page, 70, 20, 320, 32),
            )
        doc.add_text(
            label=DocItemLabel.TEXT,
            text="phần tiếp theo của đoạn văn trang trước.",
            prov=prov(page, 70, 60, 525, 74),
        )
        for k in range(12):
            doc.add_text(
                label=DocItemLabel.TEXT,
                text=f"Đoạn {k} của trang {page}.",
                prov=prov(page, 70, 90 + 40 * k, 525, 118 + 40 * k),
            )
        for k in range(short_items):
            doc.add_text(
                label=DocItemLabel.TEXT,
                text=f"m{k}",
                prov=prov(
                    page,
                    70 + (k % 40) * 10,
                    2 + (k // 40),
                    78 + (k % 40) * 10,
                    4 + (k // 40),
                ),
            )
        if tables:
            cells = [
                TableCell(
                    text=f"{r}{c}",
                    start_row_offset_idx=r,
                    end_row_offset_idx=r + 1,
                    start_col_offset_idx=c,
                    end_col_offset_idx=c + 1,
                )
                for r in range(3)
                for c in range(3)
            ]
            doc.add_table(
                data=TableData(num_rows=3, num_cols=3, table_cells=cells),
                prov=prov(page, 70, 580, 525, 640),
            )
        if pictures:
            doc.add_picture(prov=prov(page, 400, 650, 480, 690))
        end = "chưa kết thúc và" if joins else "đã kết thúc."
        doc.add_text(
            label=DocItemLabel.TEXT,
            text=f"Đoạn cuối trang {page} {end}",
            prov=prov(page, 70, 700, 525, 728),
        )
        doc.add_text(
            label=DocItemLabel.TEXT, text=str(page), prov=prov(page, 290, 800, 306, 812)
        )
    return doc


def _time(doc):
    import time

    best = None
    for _ in range(2):
        t0 = time.perf_counter()
        res = N.normalize_document(doc)
        took = time.perf_counter() - t0
        best = took if best is None else min(best, took)
    return best, res


def test_many_cut_paragraphs_scale_linearly():
    """F-10: 300 pages with a paragraph cut on every page (was: a join on every
    page - none since Phase 12D7); doubling the pages must not triple the time."""
    half, res_half = _time(_big(150))
    full, res_full = _time(_big(300))
    assert res_full.counts.get("join_across_pages", 0) == 0
    assert res_full.counts["page_number_to_furniture"] == 300
    assert full <= 2.6 * half + 0.5, (half, full)
    assert full < 20


def _merged_everywhere(n_pages):
    """Docling merges the signer line of every page with the title of the next."""
    E = FX.E
    pages = [
        [
            E("text", "Phụ lục ban hành kèm theo quyết định", y=40, h=14),
            E("text", f"Đoạn mở đầu trang {p} trình bày nội dung.", y=100, h=28),
            E("text", f"Người ký số {p} Nguyễn Văn An", x=340, y=700, w=170, h=12),
            E("page_footer", str(p), x=290, y=800, w=16, h=12),
        ]
        for p in range(1, n_pages + 1)
    ]
    return H.build_document({"name": "merged", "pages": pages, "ground_truth": ""})


def test_undoing_upstream_merges_scales_linearly():
    """F-10 with Phase 12D5: splitting back a Docling merge on every page break
    (R2-01) must stay linear - doubling the pages must not triple the time."""
    small, big = _merged_everywhere(150), _merged_everywhere(300)
    t0 = time.perf_counter()
    r_small = N.normalize_document(small, evidence=H.evidence(small))
    half = time.perf_counter() - t0
    t0 = time.perf_counter()
    r_big = N.normalize_document(big, evidence=H.evidence(big))
    full = time.perf_counter() - t0
    assert r_small.counts["upstream_merge_undone"] == 149
    assert r_big.counts["upstream_merge_undone"] == 299
    assert full <= 2.6 * half + 0.5, (half, full)
    assert full < 20


def test_large_document_with_tables_pictures_and_cut_paragraphs():
    took, res = _time(_big(300, pictures=True, tables=True))
    assert res.counts.get("join_across_pages", 0) == 0  # Phase 12D7
    assert res.counts["image_placeholder_dropped"] == 300
    assert res.content.count("|------|------|------|") == 300  # every table still there
    assert took < 30


def test_text_labelled_running_header_is_kept_and_blocks_the_joins():
    """The price of never deleting a repeated TEXT line: it stays between the two parts."""
    took, res = _time(_big(300, header=True))
    assert res.content.count("NGÂN HÀNG MẪU - QUY ĐỊNH NỘI BỘ") == 300
    assert "join_across_pages" not in res.counts
    assert res.counts["page_number_to_furniture"] == 300
    assert any(
        w["code"] == "repeated_line_kept" and w["count"] == 300 for w in res.warnings
    )
    assert took < 30


def test_many_short_items_in_the_page_band_scale_linearly():
    small, _ = _time(_big(3, joins=False, short_items=1000))
    large, _ = _time(_big(3, joins=False, short_items=3000))
    assert large <= 4.0 * small + 0.5, (small, large)


def test_very_long_text_item():
    from docling_core.types.doc.document import DoclingDocument
    from docling_core.types.doc.labels import DocItemLabel

    doc = DoclingDocument(name="long")
    doc.add_text(label=DocItemLabel.TEXT, text="chữ " * 200_000)
    res = N.normalize_document(doc)
    assert res.content.count("chữ") == 200_000


# --------------------------------------------------------------------------- #
# Stored text, display escape, gate, metadata
# --------------------------------------------------------------------------- #


def test_display_escape_matches_the_shared_cases():
    """The frontend port (legal-display.ts) is tested against the same file."""
    import json

    cases = json.loads(
        (
            Path(__file__).parent / "fixtures" / "legal" / "display_escape_cases.json"
        ).read_text(encoding="utf-8")
    )
    assert len(cases) >= 20
    for case in cases:
        assert H.legal_display_markdown(case["input"]) == case["display"], case
        assert H.legal_display_markdown(case["display"]) == case["display"], (
            case
        )  # idempotent


def test_literal_block_syntax_is_escaped_in_the_stored_text():
    assert N.escape_literal_block_syntax("# tiêu đề giả") == "\\# tiêu đề giả"
    assert N.escape_literal_block_syntax("> trích dẫn giả") == "\\> trích dẫn giả"
    for plain in (
        "9. Dịch vụ",
        "10) Điểm",
        "- gạch",
        "a) điểm",
        "1.1 Nội dung",
        "2024",
        "Điều 5. Phạm vi",
    ):
        assert N.escape_literal_block_syntax(plain) == plain


def test_deployment_gate(monkeypatch):
    monkeypatch.delenv(N.ENV_FLAG, raising=False)
    assert N.effective_mode("legal") == "standard"
    monkeypatch.setenv(N.ENV_FLAG, "true")
    assert N.effective_mode("legal") == "legal"
    assert N.effective_mode("standard") == "standard"
    assert N.effective_mode(None) == "standard"
    monkeypatch.setenv(N.ENV_FLAG, "maybe")
    assert N.effective_mode("legal") == "standard"


def test_only_pdf_is_supported():
    assert N.applies_to("application/pdf")
    for mime in (
        "image/png",
        "text/html",
        "text/markdown",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "audio/mpeg",
        None,
    ):
        assert not N.applies_to(mime)


def test_summary_and_persisted_metadata_contain_no_text(built):
    _, _, _, res = built["f33_five_pages_real_page_numbers_and_join"]
    for blob in (repr(res.summary()), repr(res.persistable())):
        assert "Dịch vụ" not in blob and "khách hàng" not in blob
    report = res.report()
    assert all("text_before" not in op for op in report["operations"])
    meta = res.persistable()
    assert meta["version"] == N.NORMALIZER_VERSION and meta["status"] == "applied"
    removed = [o for o in meta["operations"] if o["op"] == "page_number_to_furniture"]
    assert len(removed) == 5 and all(
        len(o["sha256"]) == 64 and o["pages"] for o in removed
    )


# --------------------------------------------------------------------------- #
# Layouts the Phase 12D2 review listed as having no fixture (TEST_GAPS §5):
# mixed page sizes / landscape pages, partly missing provenance, items with
# several provenances, a table inside a picture.
# --------------------------------------------------------------------------- #


def _edge_tools():
    from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
    from docling_core.types.doc.document import (
        DoclingDocument,
        ProvenanceItem,
        TableCell,
        TableData,
    )
    from docling_core.types.doc.labels import DocItemLabel

    def prov(page, left, t, r, b):
        return ProvenanceItem(
            page_no=page,
            bbox=BoundingBox(l=left, t=t, r=r, b=b, coord_origin=CoordOrigin.TOPLEFT),
            charspan=(0, 1),
        )

    return DoclingDocument, DocItemLabel, Size, TableCell, TableData, prov


def _kept(doc, expected):
    """Every expected line is displayed, in order, exactly once; nothing merged."""
    res = N.normalize_document(doc)
    lines = H.legal_lines(res.content)
    assert [ln for ln in lines if ln in expected] == expected
    return res, lines


def test_mixed_page_sizes_and_landscape_pages():
    """A4, A3 landscape, A4, A4 landscape, A4: positions are compared relative to
    each page, so real page numbers are still found and no body line is touched."""
    DoclingDocument, L, Size, _, _, prov = _edge_tools()
    sizes = [(595, 842), (1191, 842), (595, 842), (842, 595), (595, 842)]
    doc = DoclingDocument(name="mixed")
    body = []
    for p, (w, h) in enumerate(sizes, 1):
        doc.add_page(page_no=p, size=Size(width=w, height=h))
        text = f"Nội dung trang {p} của quy định chưa kết thúc ở cuối trang nên còn"
        body.append(text)
        doc.add_text(
            label=L.TEXT, text=text, prov=prov(p, w * 0.12, h * 0.1, w * 0.88, h * 0.85)
        )
        doc.add_text(
            label=L.TEXT,
            text=str(p),
            prov=prov(p, w * 0.49, h * 0.95, w * 0.51, h * 0.965),
        )
    res, lines = _kept(doc, body)
    assert lines == body  # page numbers gone, each page still its own paragraph
    assert res.counts["page_number_to_furniture"] == 5
    assert res.counts.get("join_across_pages", 0) == 0


def test_items_without_provenance_between_located_items():
    """An item the layout gave no position is never a candidate for anything."""
    DoclingDocument, L, Size, _, _, prov = _edge_tools()
    doc = DoclingDocument(name="partial")
    expected = []
    for p in range(1, 6):
        doc.add_page(page_no=p, size=Size(width=595, height=842))
        located = f"Điều {p}. Đoạn có vị trí trên trang {p}."
        floating = f"Đoạn thứ {p} không có vị trí và chưa kết thúc ở"
        expected += [located, floating]
        doc.add_text(label=L.TEXT, text=located, prov=prov(p, 70, 80, 525, 110))
        doc.add_text(label=L.TEXT, text=floating)
        doc.add_text(label=L.TEXT, text=str(p), prov=prov(p, 290, 800, 306, 812))
    res, lines = _kept(doc, expected)
    assert lines == expected
    assert res.counts.get("join_across_pages", 0) == 0
    # a bare number without a position is content, not a page number
    doc.add_text(label=L.TEXT, text="2024")
    assert "2024" in H.legal_lines(N.normalize_document(doc).content)


def test_items_with_several_provenances_are_left_whole():
    """Docling can already give one item two page fragments: it is neither
    joined again nor split, and its text is unchanged."""
    DoclingDocument, L, Size, _, _, prov = _edge_tools()
    doc = DoclingDocument(name="multi")
    for p in range(1, 6):
        doc.add_page(page_no=p, size=Size(width=595, height=842))
    expected = []
    for p in range(1, 6):
        head = f"Điều {p}. Mở đầu trang {p}."
        expected.append(head)
        doc.add_text(label=L.TEXT, text=head, prov=prov(p, 70, 80, 525, 110))
        if p < 5:
            spanning = f"Đoạn {p} bắt đầu ở trang {p} và kết thúc ở trang {p + 1}."
            expected.append(spanning)
            item = doc.add_text(
                label=L.TEXT, text=spanning, prov=prov(p, 70, 700, 525, 780)
            )
            item.prov.append(prov(p + 1, 70, 40, 525, 70))
        doc.add_text(label=L.TEXT, text=str(p), prov=prov(p, 290, 800, 306, 812))
    res, lines = _kept(doc, expected)
    assert lines == expected
    assert res.counts.get("join_across_pages", 0) == 0


def test_table_inside_a_picture_is_kept_and_the_picture_leaves_a_trace():
    """The Standard export drops a table the layout nested in a picture region
    (a scanned annex photographed as one image). Legal keeps its rows."""
    DoclingDocument, L, Size, TableCell, TableData, prov = _edge_tools()
    doc = DoclingDocument(name="tabpic")
    doc.add_page(page_no=1, size=Size(width=595, height=842))
    doc.add_text(
        label=L.TEXT,
        text="Phụ lục 01. Biểu phí dịch vụ.",
        prov=prov(1, 70, 80, 525, 110),
    )
    picture = doc.add_picture(prov=prov(1, 70, 150, 525, 600))
    rows = [["Chỉ tiêu", "Mức phí"], ["Phí chuyển tiền", "11.000 đồng"]]
    cells = [
        TableCell(
            text=text,
            start_row_offset_idx=r,
            end_row_offset_idx=r + 1,
            start_col_offset_idx=c,
            end_col_offset_idx=c + 1,
            column_header=(r == 0),
        )
        for r, row in enumerate(rows)
        for c, text in enumerate(row)
    ]
    doc.add_table(
        data=TableData(table_cells=cells, num_rows=2, num_cols=2),
        prov=prov(1, 90, 200, 500, 400),
        parent=picture,
    )
    doc.add_text(
        label=L.TEXT,
        text="Mức phí trên chưa bao gồm thuế.",
        prov=prov(1, 70, 650, 525, 680),
    )
    standard = H.display_lines(doc.export_to_markdown())
    assert "Phí chuyển tiền | 11.000 đồng" not in standard  # the upstream loss
    lines = H.legal_lines(N.normalize_document(doc).content)
    assert lines == [
        "Phụ lục 01. Biểu phí dịch vụ.",
        "<!-- image -->",
        "Chỉ tiêu | Mức phí",
        "Phí chuyển tiền | 11.000 đồng",
        "Mức phí trên chưa bao gồm thuế.",
    ]
