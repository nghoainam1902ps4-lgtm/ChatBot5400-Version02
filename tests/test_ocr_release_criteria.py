"""Supplementary release criteria (scripts/ocr/release_criteria.py, D-27).

The logic is tested on synthetic recognised text; no OCR engine is needed.
The original acceptance test (tests/test_ocr_integration.py) is NOT replaced:
these tests make sure the supplementary verdict can never be more lenient than
intended.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ocr"))

import release_criteria as rc  # noqa: E402

MANIFEST = json.loads(
    (ROOT / "tests" / "fixtures" / "ocr" / "manifest.json").read_text()
)
SPEC = MANIFEST["bang_gop_scan"]
TITLE = "BẢNG KÊ CHI TIẾT KHOẢN MỤC MẪU"
ROWS = [
    ["1", "Phí dịch vụ mẫu", "2.500.000", "1.200.000", "05/01/2024"],
    ["2", "Lãi suất giả định", "18.750.000", "9.375.000", "12/02/2024"],
    ["3", "Khoản vay thử nghiệm", "350.000.000", "175.000.000", "20/03/2024"],
    ["4", "Tổng cộng", "371.250.000", "185.575.000", "31/03/2024"],
]


def _table(rows=ROWS):
    cells = [
        (0, 0, 2, 1, "STT"),
        (0, 1, 2, 1, "Nội dung"),
        (0, 2, 1, 2, "Số tiền (đồng)"),
        (0, 4, 2, 1, "Ngày"),
        (1, 2, 1, 1, "Kỳ 1"),
        (1, 3, 1, 1, "Kỳ 2"),
    ]
    for r, row in enumerate(rows, start=2):
        cells += [(r, c, 1, 1, text) for c, text in enumerate(row)]
    return [{"rows": 6, "cols": 5, "cells": cells}]


def _md(title=TITLE, rows=ROWS):
    return title + "\n\n" + "\n".join(" | ".join(r) for r in rows)


def _eval(engine="tesseract_best", **kw):
    return rc.evaluate(
        engine,
        SPEC,
        kw.get("md", _md()),
        kw.get("tables", _table()),
        kw.get("pages", 1),
    )


def test_thresholds_are_the_original_ones():
    import test_ocr_integration as original

    assert rc.MAX_CER == original.MAX_CER
    assert rc.MIN_FIELD_RECALL == original.MIN_FIELD_RECALL
    assert tuple(rc.VIETNAMESE_ENGINES) == tuple(original.VIETNAMESE_ENGINES)
    assert tuple(rc.NUMERIC_KEYS) == tuple(original.NUMERIC_KEYS)


def test_clean_result_passes_both():
    v = _eval()
    assert v["original"] == "PASS" and v["conditional"] == "PASS" and v["critical_ok"]
    assert v["known_limitations"] == []


@pytest.mark.parametrize(
    "title", ["BANG KE CHI TIẾT KHOẢN MỤC MẪU", "BANG KE CHI TIET KHOAN MUC MAU"]
)
def test_heading_without_diacritics_is_the_accepted_limitation(title):
    v = _eval(md=_md(title=title))
    assert v["original"] == "FAIL"  # the original verdict is never changed
    assert v["failed_original_checks"] == ["ordered_phrases"]
    assert v["conditional"] == "PASS_WITH_KNOWN_LIMITATION"
    assert v["known_limitations"] == ["KL-1"] and v["critical_ok"]


def test_limitation_only_for_the_accepted_engines():
    v = _eval(engine="easyocr", md=_md(title="BANG KE CHI TIẾT KHOẢN MỤC MẪU"))
    assert v["conditional"] == "FAIL"


@pytest.mark.parametrize(
    "title",
    [
        "BANG KE CHI TIẾT KHOẢN MỤC",  # a word is missing: not only diacritics
        "BẢNG KÊ CHI TIẾT KHOAN MUC MAO",  # a wrong letter
        "",  # heading lost
    ],
)
def test_other_heading_defects_are_not_waived(title):
    v = _eval(md=_md(title=title))
    assert v["conditional"] == "FAIL" and not v["critical_ok"]


def test_a_wrong_amount_is_never_waived():
    rows = [list(r) for r in ROWS]
    rows[3][2] = "371250000"  # 371.250.000 read without separators
    v = _eval(
        md=_md(title="BANG KE CHI TIẾT KHOẢN MỤC MẪU", rows=rows), tables=_table(rows)
    )
    assert v["conditional"] == "FAIL" and not v["critical_ok"]
    assert (
        "all_amounts" in v["critical_failed"]
        and "table_row_values" in v["critical_failed"]
    )


def test_a_wrong_row_label_is_outside_the_exception():
    rows = [list(r) for r in ROWS]
    rows[1][1] = "Lai suat gia dinh"
    v = _eval(
        md=_md(title="BANG KE CHI TIẾT KHOẢN MỤC MẪU", rows=rows), tables=_table(rows)
    )
    # The numbers are right (critical ok) but the defect is not the accepted one.
    assert v["critical_ok"] and v["conditional"] == "FAIL"
    assert set(v["failed_original_checks"]) == {"ordered_phrases", "table_rows"}


def test_broken_table_shape_is_critical():
    v = _eval(tables=[{"rows": 6, "cols": 4, "cells": []}])
    assert v["conditional"] == "FAIL" and "table_shape" in v["critical_failed"]


def test_limitation_never_rewrites_other_phrases():
    spec = MANIFEST["vb_scan"]
    md = spec["ground_truth"].replace("QUYẾT ĐỊNH", "QUYET DINH")
    v = rc.evaluate("tesseract_best", spec, md, [], 1)
    assert v["original"] == "FAIL" and v["conditional"] == "FAIL"


def test_markdown_and_summary():
    res = {
        "tesseract_best": {
            "bang_gop_scan": _eval(md=_md(title="BANG KE CHI TIẾT KHOẢN MỤC MẪU"))
        }
    }
    s = rc.summarize(res)["tesseract_best"]
    assert s == {
        "original_pass": 0,
        "conditional_pass": 0,
        "conditional_known_limitation": 1,
        "conditional_fail": 0,
        "critical_ok": 1,
        "total": 1,
    }
    assert "PASS_WITH_KNOWN_LIMITATION" in rc.to_markdown(res)
