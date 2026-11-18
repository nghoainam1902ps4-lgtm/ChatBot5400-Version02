"""Phase 12D8 audit - the Standard expected-diff classifier (D8-STD-xx).

``scripts/ocr/phase12_standard_diff.py`` is the release gate for "Standard is
byte-identical to v1.2.0 except where the approved TSV parser fix (E0-07)
changed a token". These tests look for regressions it labels ``unchanged`` or
``expected parser fix`` / lets through with exit code 0, and compare its model
of the old parser (``old_parser_form``) with REAL pandas (the upstream
``pd.read_csv(io.StringIO(tsv), quoting=csv.QUOTE_NONE, sep="\\t")``).

xfail(strict) = the expected safe behaviour, failing today.
test_control_* / test_verified_* = checked and correct today.
"""

from __future__ import annotations

import ast
import csv
import importlib.util
import io
import json
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "phase12_standard_diff_d8", ROOT / "scripts" / "ocr" / "phase12_standard_diff.py"
)
assert _spec is not None and _spec.loader is not None
D = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(D)

HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\t"
    "left\ttop\twidth\theight\tconf\ttext\n"
)
# the page / block / paragraph / line rows Tesseract always writes (empty text)
PARENTS = [
    "1\t1\t0\t0\t0\t0\t0\t0\t100\t50\t-1\t",
    "2\t1\t1\t0\t0\t0\t5\t5\t90\t40\t-1\t",
    "3\t1\t1\t1\t0\t0\t5\t5\t90\t40\t-1\t",
    "4\t1\t1\t1\t1\t0\t5\t5\t90\t40\t-1\t",
]


def _tsv(*words: str) -> str:
    """One Tesseract TSV (= one OCR crop / one invocation) holding ``words``."""
    rows = PARENTS + [
        f"5\t1\t1\t1\t1\t{i}\t{5 + i}\t5\t9\t9\t95.5\t{w}"
        for i, w in enumerate(words, 1)
    ]
    return HEADER + "\n".join(rows) + "\n"


def _upstream_cells(*words: str) -> list[str]:
    """What Docling 2.129.0 made of one crop: upstream read_csv, the empty-row
    filter of ``_run_tesseract`` and ``str(row["text"])``."""
    pd = pytest.importorskip("pandas")
    df = pd.read_csv(io.StringIO(_tsv(*words)), quoting=csv.QUOTE_NONE, sep="\t")
    kept = df[df["text"].notna() & (df["text"].apply(str).str.strip() != "")]
    return [str(row["text"]) for _, row in kept.iterrows()]


def _model(*words: str) -> list[str]:
    return [m for m in (D.old_parser_form(w) for w in words) if m is not None]


def _run(tmp_path, docs, tsv=None, layout=None):
    """docs: name -> (before, after) (None = file absent on that side);
    tsv: file name (relative to the TSV folder) -> list of words."""
    before, after, out = tmp_path / "b", tmp_path / "a", tmp_path / "o"
    before.mkdir()
    after.mkdir()
    for name, (b, a) in docs.items():
        if b is not None:
            (before / f"{name}.md").write_text(b, encoding="utf-8")
        if a is not None:
            (after / f"{name}.md").write_text(a, encoding="utf-8")
    argv = ["--before", str(before), "--after", str(after), "--out", str(out)]
    if tsv is not None:
        folder = tmp_path / "t"
        folder.mkdir()
        for rel, words in tsv.items():
            target = folder / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_tsv(*words), encoding="utf-8")
        argv += ["--tsv", str(folder)]
    rc = D.main(argv)
    report = json.loads((out / "standard_diff.json").read_text(encoding="utf-8"))
    return rc, report


def _cls(report, name="doc"):
    return report["documents"][name]["class"]


# --------------------------------------------------------------------------- #
# Controls: what the classifier gets right
# --------------------------------------------------------------------------- #


def test_control_documented_rewrites_match_real_pandas():
    """The E0-07 forms the docs name, each ALONE in its crop, real pandas 3.x."""
    for token, old in (
        ("0001", "1.0"),
        ("000123", "123.0"),
        ("2024", "2024.0"),
        ("9.", "9.0"),
        ("12.50", "12.5"),
        ("1e5", "100000.0"),
        ("+1", "1.0"),
        (".5", "0.5"),
        ("9007199254740993", "9007199254740992.0"),  # > 2**53: precision lost
        ("123456789012345678", "1.2345678901234568e+17"),
        ("true", "True"),
        ("TRUE", "True"),
        ("false", "False"),
        ("inf", "inf"),
        ("Infinity", "inf"),
    ):
        assert _upstream_cells(token) == [old], token
        assert D.old_parser_form(token) == old, token
    for token in ("0x1", "1_000", "1,000", "1.000.000", "1/2024", "05%", "12,5", "1e"):
        assert _upstream_cells(token) == [token] == _model(token), token
    for na in sorted(D.NA_WORDS - {"", "#N/A N/A"}):
        assert _upstream_cells(na) == [] == _model(na), na
        assert _upstream_cells("Mã", na, "và") == ["Mã", "và"], na  # in ANY crop
    # the NA list is pandas' own
    from pandas._libs.parsers import STR_NA_VALUES

    assert set(STR_NA_VALUES) == D.NA_WORDS


def test_control_mixed_crops_are_not_rewritten_by_the_old_parser():
    """pandas infers the type of the WHOLE text column of one crop: a number
    beside a word, a boolean beside a number, a number beside a lone
    punctuation mark all stay text. Only NA words vanish in any crop."""
    assert _upstream_cells("Số:", "0001", "ngày", "2024") == [
        "Số:",
        "0001",
        "ngày",
        "2024",
    ]
    assert _upstream_cells("true", "1") == ["true", "1"]
    assert _upstream_cells("0001", "true") == ["0001", "true"]
    assert _upstream_cells("0001", "-") == ["0001", "-"]
    assert _upstream_cells("0001", "NA") == ["1.0"]  # NA does not break the crop
    assert _upstream_cells("1", "2", "3") == ["1.0", "2.0", "3.0"]


def test_control_unrelated_change_beside_a_parser_fix_is_a_regression(tmp_path):
    rc, report = _run(
        tmp_path,
        {
            "doc": ("1.0 Điều 5 có hiệu lực", "0001 Điều 6 có hiệu lực"),
            "glued": ("1.0 5", "0001 6"),
            "digit": ("Điều 12. Lãi suất", "Điều 13. Lãi suất"),
            "zero": ("Số 0001", "Số 1"),
            "dot": ("9. Dịch vụ", "9 Dịch vụ"),
        },
        tsv={
            "doc_p001.tsv": ["0001", "Điều", "6"],
            "glued_p001.tsv": ["0001", "6"],
            "digit_p001.tsv": ["Điều", "13."],
            "zero_p001.tsv": ["Số", "1"],
            "dot_p001.tsv": ["9", "Dịch"],
        },
    )
    assert rc == 1
    assert {v["class"] for v in report["documents"].values()} == {D.UNEXPECTED}
    kinds = [h["class"] for h in report["documents"]["doc"]["hunks"]]
    assert kinds == [D.EXPECTED, D.UNEXPECTED]  # per hunk, never per document


def test_control_deletion_reordering_and_empty_output_are_regressions(tmp_path):
    rc, report = _run(
        tmp_path,
        {
            "deleted_beside_na": ("Mã sản phẩm và tên", "Mã sản phẩm NA tên"),
            "reordered": ("Điều 1. A Điều 2. B", "Điều 2. B Điều 1. A"),
            "empty": ("Điều 1. Lãi suất", ""),
            "duplicated": ("Điều 1. Lãi suất", "Điều 1. Lãi suất Điều 1. Lãi suất"),
            "nfd": ("Điều 1", unicodedata.normalize("NFD", "Điều 1")),
            "rotated": ("Điều 1. Lãi suất tối đa", "ờưl .1 uềiĐ"),  # cause (B)
            "long": (" ".join(f"t{i}" for i in range(60)), "x"),
        },
        tsv={"deleted_beside_na_p001.tsv": ["NA"]},
    )
    assert rc == 1
    assert {v["class"] for v in report["documents"].values()} == {D.UNEXPECTED}
    # the report truncates the tokens it prints, not what it classifies
    assert len(report["documents"]["long"]["hunks"][0]["before"]) == 20


def test_verified_orientation_differences_have_no_accepting_category():
    """Cause (B), the orientation-gate fix, is never auto-accepted: the only
    non-failing classes are unchanged / expected parser fix / not verified, and
    a hunk reaches the last two only through the pandas forms."""
    assert D.classify_hunk(["Điều", "1."], ["uềiĐ", ".1"], {"uềiĐ", ".1"}) == (
        D.UNEXPECTED
    )
    assert D.classify_hunk([], ["Điều"], {"Điều"}) == D.UNEXPECTED
    assert D.classify_hunk(["Điều"], [], set()) == D.UNEXPECTED


def test_verified_tsv_patch_is_applied_in_the_tesseract_branch_only():
    """RapidOCR / EasyOCR option building is untouched by the E0-07 patch:
    ``docling_patches.apply()`` is called once, inside the
    ``docling_kind == "tesseract"`` branch of ``build_ocr_options``."""
    source = (ROOT / "open_notebook" / "ocr" / "options.py").read_text("utf-8")
    tree = ast.parse(source)
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "build_ocr_options"
    )
    branches = {}
    for node in fn.body:
        if isinstance(node, ast.If):
            kind = ast.unparse(node.test)
            branches[kind] = "docling_patches" in ast.unparse(node)
    assert branches == {
        "spec.custom is not None and (not lang)": False,
        "spec.docling_kind == 'rapidocr'": False,
        "spec.docling_kind == 'tesseract'": True,
        "spec.docling_kind == 'easyocr'": False,
    }
    assert source.count("docling_patches.apply()") == 1
    # and the patched method belongs to the Tesseract CLI model only
    patches = (ROOT / "open_notebook" / "ocr" / "docling_patches.py").read_text("utf-8")
    assert 'UPSTREAM_MODULE = "docling.models.stages.ocr.tesseract_ocr_cli_model"' in (
        patches
    )


# --------------------------------------------------------------------------- #
# D8-STD-01: "unchanged" although the bytes differ
# --------------------------------------------------------------------------- #

_STRUCTURE = {
    "paragraphs_merged": (
        "Điều 1. Phạm vi\n\nĐiều 2. Đối tượng\n",
        "Điều 1. Phạm vi Điều 2. Đối tượng\n",
    ),
    "heading_swallows_its_paragraph": (
        "## Điều 1\n\nNgân hàng áp dụng lãi suất.\n",
        "## Điều 1 Ngân hàng áp dụng lãi suất.\n",
    ),
    "table_rows_collapsed": (
        "| STT | Phí |\n|---|---|\n| 1 | 5.000 |\n| 2 | 7.000 |\n",
        "| STT | Phí | |---|---| | 1 | 5.000 | | 2 | 7.000 |\n",
    ),
    "list_items_joined": ("- a) Cá nhân;\n- b) Tổ chức;\n", "- a) Cá nhân; - b) Tổ chức;\n"),
    "space_became_nbsp": ("Số: 0001/QĐ", "Số:" + chr(0xA0) + "0001/QĐ"),
}


@pytest.mark.xfail(
    strict=True,
    reason="D8-STD-01: compare() tokenizes with str.split(); a Standard output "
    "whose BYTES differ but whose whitespace-separated tokens are the same "
    "(paragraphs merged, heading/table/list structure lost) is 'unchanged', exit 0",
)
@pytest.mark.parametrize("case", sorted(_STRUCTURE))
def test_a_byte_difference_is_never_unchanged(tmp_path, case):
    before, after = _STRUCTURE[case]
    assert before != after
    rc, report = _run(tmp_path, {"doc": (before, after)})
    assert report["documents"]["doc"]["byte_identical"] is False  # it does know
    assert _cls(report) != D.UNCHANGED
    assert rc != 0


# --------------------------------------------------------------------------- #
# D8-STD-02: the TSV evidence is a bag of words of the whole document
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason="D8-STD-02: evidence = set of every level-5 word of every TSV of the "
    "document; no crop, no position, no count. A candidate that prints the WRONG "
    "token (leading zeros still lost: 0001 -> 1) is 'expected parser fix' as soon "
    "as that token occurs anywhere else (the page number 1)",
)
def test_wrong_new_token_is_not_proven_by_another_word_of_the_document(tmp_path):
    # Raw TSV of the page: the voucher number is 0001 (alone in its crop);
    # the footer holds the page number 1.
    assert _upstream_cells("0001") == ["1.0"]  # what v1.2.0 printed
    rc, report = _run(
        tmp_path,
        # the candidate prints "1": the voucher number is still NOT verbatim
        {"doc": ("Số chứng từ:\n\n1.0\n\nTrang\n\n1.0", "Số chứng từ:\n\n1\n\nTrang\n\n1")},
        tsv={
            "doc_c001.tsv": ["Số", "chứng", "từ:"],
            "doc_c002.tsv": ["0001"],
            "doc_c003.tsv": ["Trang"],
            "doc_c004.tsv": ["1"],
        },
    )
    hunks = report["documents"]["doc"]["hunks"]
    assert len(hunks) == 2
    # one "1" in the evidence cannot prove two "1" in the output
    assert [h["class"] for h in hunks].count(D.EXPECTED) <= 1
    assert _cls(report) != D.EXPECTED


@pytest.mark.xfail(
    strict=True,
    reason="D8-STD-02: the old parser rewrote a number only when EVERY word of "
    "its crop was numeric; the classifier is context-free. A real decimal that "
    "v1.2.0 printed correctly from a mixed crop and the candidate changes "
    "(2.0 -> 2) is 'expected parser fix' because '2' is the page number",
)
def test_change_in_a_mixed_crop_is_not_a_parser_fix(tmp_path):
    crop = ["Phiên", "bản", "2.0", "ngày", "ban", "hành"]
    assert _upstream_cells(*crop) == crop  # v1.2.0 printed this crop verbatim
    rc, report = _run(
        tmp_path,
        {"doc": ("Phiên bản 2.0 ngày ban hành\n\n2.0", "Phiên bản 2 ngày ban hành\n\n2")},
        tsv={"doc_c001.tsv": crop, "doc_c002.tsv": ["2"]},
    )
    first = report["documents"]["doc"]["hunks"][0]
    assert first["before"] == ["2.0"] and first["after"] == ["2"]
    assert first["class"] == D.UNEXPECTED
    assert rc == 1


@pytest.mark.xfail(
    strict=True,
    reason="D8-STD-02: the 'fixed' example of tests/test_phase12d7_standard_diff.py "
    "is certified 'expected parser fix' with a TSV (one mixed crop 'Số: 0001 "
    "ngày 2024') from which real pandas could never produce the old text "
    "'Số: 1.0 ngày 2024.0'",
)
def test_the_shipped_example_is_not_explained_by_its_own_evidence(tmp_path):
    crop = ["Số:", "0001", "ngày", "2024"]
    assert _upstream_cells(*crop) == crop  # real pandas: nothing rewritten
    rc, report = _run(
        tmp_path,
        {"fixed": ("Số: 1.0 ngày 2024.0", "Số: 0001 ngày 2024")},
        tsv={"fixed_p001.tsv": crop},
    )
    assert _cls(report, "fixed") != D.EXPECTED


@pytest.mark.xfail(
    strict=True,
    reason="D8-STD-02: an NA word in the evidence proves any number of inserted "
    "NA words (set membership, no count)",
)
def test_one_na_in_the_tsv_does_not_prove_three_inserted_na(tmp_path):
    rc, report = _run(
        tmp_path,
        {"doc": ("Mã A và mã B và mã C", "Mã NA A và mã NA B và mã NA C")},
        tsv={"doc_p001.tsv": ["Mã", "NA", "A", "và", "mã", "B", "và", "mã", "C"]},
    )
    assert len(report["documents"]["doc"]["hunks"]) == 3
    assert _cls(report) != D.EXPECTED


@pytest.mark.xfail(
    strict=True,
    reason="D8-STD-03: evidence files are found with rglob('<name>*.tsv'): the "
    "TSV of ANOTHER document whose name starts with this one's (qd1 / qd10) is "
    "accepted as proof",
)
def test_evidence_of_another_document_is_not_used(tmp_path):
    rc, report = _run(
        tmp_path,
        {"qd1": ("Số: 1.0", "Số: 0001"), "qd10": ("Số: 0001", "Số: 0001")},
        tsv={"qd10_p001.tsv": ["Số:", "0001"]},  # no TSV at all for qd1
    )
    assert _cls(report, "qd1") == D.NOT_VERIFIED


@pytest.mark.xfail(
    strict=True,
    reason="D8-STD-03: the checklist (W-12D7-02e) says '--tsv <diagnose folder>'; "
    "phase12_diagnose.py writes <out>/<document>/01_tesseract_pNNN.tsv, which "
    "rglob('<name>*.tsv') never matches: every real parser fix stays 'not verified'",
)
def test_the_documented_diagnose_layout_provides_evidence(tmp_path):
    rc, report = _run(
        tmp_path,
        {"qd_123": ("0001", "0001"), "qd_124": ("1.0", "0001")},
        tsv={"qd_124/01_tesseract_p001.tsv": ["0001"]},
    )
    assert _cls(report, "qd_124") == D.EXPECTED


# --------------------------------------------------------------------------- #
# D8-STD-04: exit code 0 for results that prove nothing
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason="D8-STD-04: a document the candidate did not produce at all is "
    "'not verified' and the run exits 0",
)
def test_a_document_missing_from_the_candidate_fails_the_run(tmp_path):
    rc, report = _run(
        tmp_path, {"kept": ("Điều 1", "Điều 1"), "lost": ("Điều 1. Lãi suất", None)}
    )
    assert report["documents"]["lost"]["reason"] == "missing on one side"
    assert rc != 0


@pytest.mark.xfail(
    strict=True,
    reason="D8-STD-04: no *.md on either side (wrong folder, crashed export) "
    "prints {} and exits 0",
)
def test_comparing_nothing_fails_the_run(tmp_path):
    rc, report = _run(tmp_path, {})
    assert report["documents"] == {} and report["summary"] == {}
    assert rc != 0


@pytest.mark.xfail(
    strict=True,
    reason="D8-STD-04: 'not verified' exits 0. Words a stringification bug "
    "typically prints (nan, None, null, <NA>) are pandas NA words, so inserting "
    "them anywhere has 'the shape of the parser fix' and is never a regression, "
    "even when the raw TSV of the document does not contain them",
)
@pytest.mark.parametrize("word", ["nan", "None", "null", "<NA>"])
def test_inserted_stringified_null_fails_the_run(tmp_path, word):
    rc, report = _run(
        tmp_path,
        {"doc": ("| 1 | Phí |  |\n| 2 | Lãi |  |", f"| 1 | Phí | {word} |\n| 2 | Lãi | {word} |")},
        tsv={"doc_p001.tsv": ["1", "Phí", "2", "Lãi"]},  # the word is NOT in the TSV
    )
    assert _cls(report) == D.NOT_VERIFIED  # today: right shape, token absent
    assert rc != 0


# --------------------------------------------------------------------------- #
# D8-STD-05: old_parser_form is not what pandas does
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason="D8-STD-05: old_parser_form uses Python float(); real pandas differs: "
    "Unicode digits and integers >= 2**63 are NOT converted, NAN / Nan / +nan are "
    "neither NA nor numbers (unsafe direction: a rewrite pandas never made has "
    "'the shape of the parser fix')",
)
@pytest.mark.parametrize(
    "token",
    ["٣", "１２", "9223372036854775808", "12345678901234567890", "NAN", "Nan", "+nan"],
)
def test_old_parser_form_does_not_invent_rewrites(token):
    assert _upstream_cells(token) == [token]  # real pandas keeps it verbatim
    assert D.old_parser_form(token) == token


@pytest.mark.xfail(
    strict=True,
    reason="D8-STD-05: real rewrites the model gets wrong (conservative direction: "
    "a genuine parser fix is reported as 'unexpected regression'): integers go "
    "through int64 (-0 -> 0.0), pandas' float parser is not correctly rounded "
    "(0.30000000000000004 -> 0.3), booleans are case-insensitive (tRue -> True)",
)
@pytest.mark.parametrize(
    "token",
    ["-0", "0.30000000000000004", "63170669074391.50008063608", "tRue"],
)
def test_old_parser_form_matches_real_pandas(token):
    real = _upstream_cells(token)
    assert real != [token]  # pandas did rewrite it
    assert [D.old_parser_form(token)] == real


@pytest.mark.xfail(
    strict=True,
    reason="D8-STD-05: a parser fix inside a Markdown table changes the column "
    "width: Docling's padded separator row gets a different token, which is an "
    "'unexpected regression' (false alarm in the normal path for vouchers / tables)",
)
def test_a_parser_fix_inside_a_table_is_not_a_regression(tmp_path):
    pytest.importorskip("docling_core")
    from docling_core.types.doc.document import DoclingDocument, TableCell, TableData

    def table(value: str) -> str:
        doc = DoclingDocument(name="t")
        rows = [["Số", "Năm"], [value, "x"]]
        cells = [
            TableCell(
                text=v,
                start_row_offset_idx=r,
                end_row_offset_idx=r + 1,
                start_col_offset_idx=c,
                end_col_offset_idx=c + 1,
                column_header=r == 0,
            )
            for r, row in enumerate(rows)
            for c, v in enumerate(row)
        ]
        doc.add_table(data=TableData(num_rows=2, num_cols=2, table_cells=cells))
        return doc.export_to_markdown()

    before, after = table("123456.0"), table("000123456")
    rc, report = _run(
        tmp_path, {"doc": (before, after)}, tsv={"doc_c001.tsv": ["000123456"]}
    )
    assert _upstream_cells("000123456") == ["123456.0"]
    assert _cls(report) == D.EXPECTED and rc == 0
