"""The Standard expected-diff classifier (Phase 12D7, section 9)."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "phase12_standard_diff", ROOT / "scripts" / "ocr" / "phase12_standard_diff.py"
)
D = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(D)  # type: ignore[union-attr]

HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"


def _tsv(*words):
    return HEADER + "".join(
        f"5\t1\t1\t1\t1\t{i}\t0\t0\t9\t9\t95\t{w}\n" for i, w in enumerate(words, 1)
    )


def test_old_parser_form_matches_the_e0_07_defect():
    assert D.old_parser_form("0001") == "1.0"
    assert D.old_parser_form("12.50") == "12.5"
    assert D.old_parser_form("2024") == "2024.0"
    assert D.old_parser_form("NA") is None and D.old_parser_form("N/A") is None
    assert D.old_parser_form("true") == "True"
    assert D.old_parser_form("Điều") == "Điều" and D.old_parser_form("1/2024") == "1/2024"


def test_each_class(tmp_path):
    before, after, tsv = tmp_path / "b", tmp_path / "a", tmp_path / "t"
    for d in (before, after, tsv):
        d.mkdir()
    docs = {
        "same": ("Điều 1. Lãi suất", "Điều 1. Lãi suất"),
        "fixed": ("Số: 1.0 ngày 2024.0", "Số: 0001 ngày 2024"),
        "na": ("Mã sản phẩm và", "Mã sản phẩm NA và"),
        "unproven": ("Kỳ 12.5", "Kỳ 12.50"),
        "regression": ("Điều 1. Lãi suất", "Điều 2. Lãi suất"),
    }
    for name, (b, a) in docs.items():
        (before / f"{name}.md").write_text(b, encoding="utf-8")
        (after / f"{name}.md").write_text(a, encoding="utf-8")
    (tsv / "fixed_p001.tsv").write_text(_tsv("Số:", "0001", "ngày", "2024"), encoding="utf-8")
    (tsv / "na_p001.tsv").write_text(_tsv("Mã", "NA"), encoding="utf-8")
    (tsv / "regression_p001.tsv").write_text(_tsv("Điều", "2."), encoding="utf-8")
    rc = D.main(["--before", str(before), "--after", str(after), "--tsv", str(tsv), "--out", str(tmp_path / "o")])
    report = json.loads((tmp_path / "o" / "standard_diff.json").read_text(encoding="utf-8"))
    got = {k: v["class"] for k, v in report["documents"].items()}
    assert got == {
        "same": D.UNCHANGED,
        "fixed": D.EXPECTED,
        "na": D.EXPECTED,
        "unproven": D.NOT_VERIFIED,  # right shape, no TSV of that document
        "regression": D.UNEXPECTED,  # a different digit is never a parser fix
    }
    assert rc == 1  # an unexpected regression fails the run
    assert (tmp_path / "o" / "standard_diff.md").is_file()


def test_no_unexpected_difference_exits_0(tmp_path):
    before, after = tmp_path / "b", tmp_path / "a"
    before.mkdir()
    after.mkdir()
    (before / "x.md").write_text("Số: 1.0", encoding="utf-8")
    (after / "x.md").write_text("Số: 0001", encoding="utf-8")
    assert D.main(["--before", str(before), "--after", str(after), "--out", str(tmp_path / "o")]) == 0
