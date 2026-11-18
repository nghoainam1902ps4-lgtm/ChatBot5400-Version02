"""The Standard expected-diff classifier (Phase 12D7, section 9)."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "phase12_standard_diff", ROOT / "scripts" / "ocr" / "phase12_standard_diff.py"
)
assert _spec is not None and _spec.loader is not None
D = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(D)

HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"


# Phase 12D9: the page / block / paragraph / line rows (empty text) a real
# Tesseract TSV always has - they decide how pandas types the text column
# (0001 alone in its crop -> "1.0"). was: word rows only.
PARENTS = (
    "1\t1\t0\t0\t0\t0\t0\t0\t100\t50\t-1\t\n"
    "2\t1\t1\t0\t0\t0\t5\t5\t90\t40\t-1\t\n"
    "3\t1\t1\t1\t0\t0\t5\t5\t90\t40\t-1\t\n"
    "4\t1\t1\t1\t1\t0\t5\t5\t90\t40\t-1\t\n"
)


def _tsv(*words):
    return (
        HEADER
        + PARENTS
        + "".join(
            f"5\t1\t1\t1\t1\t{i}\t0\t0\t9\t9\t95\t{w}\n"
            for i, w in enumerate(words, 1)
        )
    )


def test_old_parser_form_matches_the_e0_07_defect():
    assert D.old_parser_form("0001") == "1.0"
    assert D.old_parser_form("12.50") == "12.5"
    assert D.old_parser_form("2024") == "2024.0"
    assert D.old_parser_form("NA") is None and D.old_parser_form("N/A") is None
    assert D.old_parser_form("true") == "True"
    assert (
        D.old_parser_form("Điều") == "Điều" and D.old_parser_form("1/2024") == "1/2024"
    )


def _crops(folder, name, *crops):
    """One TSV per crop + the provenance sidecar the export tool writes."""
    for n, words in enumerate(crops, 1):
        (folder / f"{name}_c{n:03d}.tsv").write_text(_tsv(*words), encoding="utf-8")
        (folder / f"{name}_c{n:03d}.json").write_text(
            json.dumps(
                {
                    "document": name,
                    "page": 1,
                    "region": n,
                    "invocation": f"{name}-{n}",
                    "engine": "tesseract_best",
                    "model_files": [{"name": "vie.traineddata", "sha256": "0" * 64}],
                }
            ),
            encoding="utf-8",
        )


def test_each_class(tmp_path):
    """Phase 12D9 (D8-STD-02 / 03 / 04, owner decision): a parser fix is proven
    by the crop it was in - a number ALONE in its crop (pandas rewrote it) -
    and every TSV names its document. was: one mixed crop "Số: 0001 ngày 2024"
    proved "fixed" (real pandas never rewrites a mixed crop) and "na" was proven
    by a crop of other words."""
    before, after, tsv = tmp_path / "b", tmp_path / "a", tmp_path / "t"
    for d in (before, after, tsv):
        d.mkdir()
    docs = {
        "same": ("Điều 1. Lãi suất", "Điều 1. Lãi suất"),
        "fixed": ("Số: 1.0 ngày 2024.0", "Số: 0001 ngày 2024"),
        "shipped_example": ("Số: 1.0 ngày 2024.0", "Số: 0001 ngày 2024"),
        "na": ("Mã sản phẩm và", "Mã sản phẩm NA và"),
        "unproven": ("Kỳ 12.5", "Kỳ 12.50"),
        "regression": ("Điều 1. Lãi suất", "Điều 2. Lãi suất"),
    }
    for name, (b, a) in docs.items():
        (before / f"{name}.md").write_text(b, encoding="utf-8")
        (after / f"{name}.md").write_text(a, encoding="utf-8")
    _crops(tsv, "fixed", ["Số:"], ["0001"], ["ngày"], ["2024"])
    _crops(tsv, "shipped_example", ["Số:", "0001", "ngày", "2024"])  # mixed crop
    _crops(tsv, "na", ["Mã", "sản", "phẩm", "NA", "và"])  # NA dropped in any crop
    _crops(tsv, "regression", ["Điều", "2."])
    rc = D.main(
        ["--before", str(before), "--after", str(after), "--tsv", str(tsv),
         "--out", str(tmp_path / "o")]
    )  # fmt: skip
    report = json.loads(
        (tmp_path / "o" / "standard_diff.json").read_text(encoding="utf-8")
    )
    got = {k: v["class"] for k, v in report["documents"].items()}
    assert got == {
        "same": D.UNCHANGED,
        "fixed": D.EXPECTED,
        "shipped_example": D.UNEXPECTED,  # its own crop contradicts it
        "na": D.EXPECTED,
        "unproven": D.NOT_VERIFIED,  # right shape, no TSV of that document
        "regression": D.UNEXPECTED,  # a different digit is never a parser fix
    }
    assert rc == 1  # an unexpected regression fails the run
    assert (tmp_path / "o" / "standard_diff.md").is_file()
    # metadata only by default: no token text in the report
    assert "Lãi" not in (tmp_path / "o" / "standard_diff.json").read_text(
        "utf-8"
    ).split('"documents"', 1)[1].split('"summary"')[0].replace('"regression"', "")


def test_a_fully_explained_run_exits_0_and_an_unproven_one_does_not(tmp_path):
    """D8-STD-04: exit 0 only when every difference is proven.
    was: ("Số: 1.0" -> "Số: 0001") with no evidence exited 0."""
    before, after, tsv = tmp_path / "b", tmp_path / "a", tmp_path / "t"
    for d in (before, after, tsv):
        d.mkdir()
    (before / "x.md").write_text("Số: 1.0", encoding="utf-8")
    (after / "x.md").write_text("Số: 0001", encoding="utf-8")
    argv = [
        "--before",
        str(before),
        "--after",
        str(after),
        "--out",
        str(tmp_path / "o"),
    ]
    assert D.main(argv) == D.EXIT_NOT_VERIFIED
    _crops(tsv, "x", ["Số:"], ["0001"])
    assert D.main([*argv, "--tsv", str(tsv)]) == D.EXIT_OK
