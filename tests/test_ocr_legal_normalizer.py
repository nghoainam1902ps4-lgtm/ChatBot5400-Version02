"""Legal Document normalization (Phase 12, docs/ocr D-34) - unit tests.

The documents are built by Docling's REAL ReadingOrderModel from synthetic
layout elements (tests/legal_harness.py); checks run on what a CommonMark
renderer displays, the way the frontend shows the source to the reader.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

pytest.importorskip("docling")

sys.path.insert(0, str(Path(__file__).parent))

import legal_harness as H  # noqa: E402

from open_notebook.ocr import legal_normalizer as N  # noqa: E402

FX = H.load_fixtures()
NAMES = [f["name"] for f in FX.FIXTURES]


@pytest.fixture(scope="module")
def built():
    """name -> (fixture, document, standard markdown, legal result)."""
    out = {}
    for fx in FX.FIXTURES:
        doc = H.build_document(fx)
        standard = doc.export_to_markdown()
        out[fx["name"]] = (fx, doc, standard, N.normalize_document(doc))
    return out


# --------------------------------------------------------------------------- #
# Per-fixture acceptance checks
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", NAMES)
def test_protected_fields_exact(built, name):
    fx, _, _, res = built[name]
    for value in fx.get("protected", []):
        assert value in res.content, value


@pytest.mark.parametrize("name", NAMES)
def test_markers_displayed_as_in_original(built, name):
    fx, _, _, res = built[name]
    hit, total = H.markers_displayed(fx, H.display_lines(res.content))
    assert hit == total


@pytest.mark.parametrize("name", NAMES)
def test_artifact_lines_absent_and_kept_lines_present(built, name):
    fx, _, _, res = built[name]
    lines = H.display_lines(res.content)
    for line in fx.get("absent_lines", []):
        assert line not in lines, line
    for line in fx.get("present_lines", []):
        assert line.replace("\\", "") in lines, line


@pytest.mark.parametrize("name", NAMES)
def test_joins_and_non_joins(built, name):
    fx, _, _, res = built[name]
    lines = H.display_lines(res.content)
    for phrase in fx.get("must_join", []):
        assert any(phrase in line for line in lines), phrase
    for left, right in fx.get("must_not_join", []):
        assert not any(left in line and right in line for line in lines), (left, right)
    for phrase in fx.get("forbidden", []):
        assert not any(phrase in line for line in lines), phrase


@pytest.mark.parametrize("name", NAMES)
def test_placeholders_and_warnings(built, name):
    fx, _, _, res = built[name]
    if "expect_placeholders" in fx:
        assert res.content.count("<!-- image -->") == fx["expect_placeholders"]
    codes = {w["code"] for w in res.warnings}
    for code in fx.get("expect_warnings", []):
        assert code in codes


@pytest.mark.parametrize("name", NAMES)
def test_no_valid_content_lost(built, name):
    """Every word the standard export shows is still shown, except removed artifacts."""
    fx, doc, standard, res = built[name]
    removed = " ".join(
        o.text_before or ""
        for o in N.normalize_document(doc, include_text=True).operations
        if o.op.endswith("_to_furniture")
    )
    lost = H.lost_words(
        H.display_text(standard, list_prefixes=False),
        H.display_text(res.content) + " " + removed,
    )
    # The bare "<!--", "image", "-->" tokens of a dropped placeholder are the
    # only other words allowed to disappear.
    placeholder_tokens = 3 * res.counts.get("image_placeholder_dropped", 0)
    assert lost <= placeholder_tokens


@pytest.mark.parametrize("name", NAMES)
def test_reading_order_not_changed(built, name):
    """Legal mode never reorders: shared lines keep the standard order."""
    _, _, standard, res = built[name]
    std, leg = H.display_lines(standard), H.display_lines(res.content)
    common = [x for x in leg if x in std]
    positions = [std.index(x) for x in common]
    assert positions == sorted(positions)


@pytest.mark.parametrize("name", NAMES)
def test_tables_identical(built, name):
    fx, doc, _, res = built[name]
    if not fx.get("table_identical"):
        return
    for table in doc.tables:
        assert table.export_to_markdown(doc) in res.content


@pytest.mark.parametrize("name", NAMES)
def test_idempotent_and_deterministic(built, name):
    _, doc, _, res = built[name]
    again = N.normalize_document(res.document)
    assert again.content == res.content
    assert not any(o.op in ("join_across_pages",) for o in again.operations)
    assert N.normalize_document(doc).content == res.content


@pytest.mark.parametrize("name", NAMES)
def test_source_document_untouched(built, name):
    _, doc, standard, _ = built[name]
    N.normalize_document(doc)
    assert doc.export_to_markdown() == standard


# --------------------------------------------------------------------------- #
# The user's reported case, spelled out
# --------------------------------------------------------------------------- #


def test_reported_case_khoan_9(built):
    _, _, standard, res = built["f02_clause_across_pages"]
    assert "<!-- image -->" in standard and "\n\n6\n\n" in standard
    lines = H.display_lines(res.content)
    assert (
        "9. Dịch vụ phi tài chính là dịch vụ không làm thay đổi số dư trên tài khoản của khách hàng."
        in lines
    )
    assert "<!-- image -->" not in res.content
    assert res.counts["join_across_pages"] == 1
    assert res.counts["page_number_to_furniture"] == 2


def test_missing_word_is_never_invented(built):
    _, _, _, res = built["f03_missing_word_not_invented"]
    assert "thay đổi số" not in res.content
    assert "thay đổi dư trên" in res.content


def test_standard_renumbers_but_legal_does_not(built):
    _, _, standard, res = built["f05_list_starts_at_10_not_continuous"]
    # the browser draws 6 and 12 where the source says 7 and 13
    assert "6. Lưu trữ hồ sơ theo quy định." in H.display_lines(standard)
    assert "12. Thực hiện các nhiệm vụ khác." in H.display_lines(standard)
    assert "7. Lưu trữ hồ sơ theo quy định." in H.display_lines(res.content)
    assert "13. Thực hiện các nhiệm vụ khác." in H.display_lines(res.content)


def test_synthesized_number_avoided(built):
    _, _, standard, res = built["f01_one_page_decision"]
    assert "5. đ)" in standard
    assert "5. đ)" not in res.content and "đ) Các trường hợp" in res.content
    assert res.counts["synthesized_number_avoided"] == 1


def test_text_inside_picture_recovered(built):
    _, _, standard, res = built["f16_text_inside_picture"]
    assert "Phí rút tiền" not in standard
    assert "Phí rút tiền là 1.100 đồng mỗi giao dịch." in res.content


def test_running_header_only_when_repeated_exactly(built):
    _, _, _, res = built["f14_running_header_footer"]
    for n in (1, 2, 3, 4):
        assert f"Nội dung trang {n} của quy định." in res.content
    assert "NGÂN HÀNG MẪU - QUY ĐỊNH NỘI BỘ" not in res.content


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
    std_words = H.display_text(doc.export_to_markdown()).split()
    for word in ("Đoạn", "6", "tiếp", "Mục"):
        assert word in res.content
    assert "join_across_pages" not in res.counts
    assert "page_number_to_furniture" not in res.counts
    assert "<!-- image -->" in res.content  # no evidence about the picture: kept
    assert (
        len(H.display_text(res.content).split()) >= len(std_words) - 1
    )  # only "1." differs


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
    assert "<script>" not in res.content and "&lt;script&gt;" in res.content
    lines = H.display_lines(res.content)
    assert "# không phải tiêu đề" in lines and "> không phải trích dẫn" in lines


def test_large_document_is_fast():
    from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
    from docling_core.types.doc.document import DoclingDocument, ProvenanceItem
    from docling_core.types.doc.labels import DocItemLabel

    doc = DoclingDocument(name="big")
    for page in range(1, 301):
        doc.add_page(page_no=page, size=Size(width=595, height=842))
        for k in range(15):
            box = BoundingBox(
                l=70,
                t=60 + 40 * k,
                r=525,
                b=74 + 40 * k,
                coord_origin=CoordOrigin.TOPLEFT,
            )
            doc.add_text(
                label=DocItemLabel.TEXT,
                text=f"Đoạn {k} của trang {page} chưa kết thúc"
                if k == 14
                else f"Đoạn {k}.",
                prov=ProvenanceItem(page_no=page, bbox=box, charspan=(0, 1)),
            )
        box = BoundingBox(l=290, t=800, r=306, b=812, coord_origin=CoordOrigin.TOPLEFT)
        doc.add_text(
            label=DocItemLabel.TEXT,
            text=str(page),
            prov=ProvenanceItem(page_no=page, bbox=box, charspan=(0, 1)),
        )
    res = N.normalize_document(doc)
    assert res.counts["page_number_to_furniture"] == 300
    assert res.elapsed_ms < 10_000  # linear: ~1 s for 300 pages on a laptop CPU


def test_very_long_text_item():
    from docling_core.types.doc.document import DoclingDocument
    from docling_core.types.doc.labels import DocItemLabel

    doc = DoclingDocument(name="long")
    doc.add_text(label=DocItemLabel.TEXT, text="chữ " * 200_000)
    res = N.normalize_document(doc)
    assert res.content.count("chữ") == 200_000


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("9. Dịch vụ", "9\\. Dịch vụ"),
        ("10) Điểm", "10\\) Điểm"),
        ("- gạch", "\\- gạch"),
        ("* sao", "\\* sao"),
        ("# tiêu đề", "\\# tiêu đề"),
        ("> trích", "\\> trích"),
        ("a) điểm", "a) điểm"),
        ("1.1 Nội dung", "1.1 Nội dung"),
        ("2024", "2024"),
        ("Điều 5. Phạm vi", "Điều 5. Phạm vi"),
        ("dòng một  \n- dòng hai", "dòng một  \n\\- dòng hai"),
    ],
)
def test_escape_block_start(raw, expected):
    assert N.escape_block_start(raw) == expected
    assert N.escape_block_start(expected) == expected or expected == raw


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


def test_summary_contains_no_text(built):
    _, _, _, res = built["f02_clause_across_pages"]
    blob = repr(res.summary())
    assert "Dịch vụ" not in blob and "khách hàng" not in blob
    report = res.report()
    assert all("text_before" not in op for op in report["operations"])
