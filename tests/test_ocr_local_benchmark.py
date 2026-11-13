"""scripts/ocr/local_document_benchmark.py: the report must hold numbers only.

The tool is meant for the operator's real documents, so nothing that was
recognised, typed as ground truth or listed as a key field may reach its output.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ocr"))

import local_document_benchmark as bench  # noqa: E402

SECRET_TEXT = (
    "Khách hàng NGUYỄN VĂN BÍ MẬT, tài khoản 9988776655, số tiền 1.234.567.890 đồng"
)
MARKDOWN = "## QUYET DINH\n\n" + SECRET_TEXT.replace("NGUYỄN", "NGUYEN")


def test_measure_returns_numbers_only():
    row = bench.measure(
        MARKDOWN,
        "QUYẾT ĐỊNH\n" + SECRET_TEXT,
        ["9988776655", "1.234.567.890", "31/12/2099"],
        ["QUYẾT ĐỊNH", "ĐIỀU KHOẢN KHÔNG CÓ"],
    )
    assert row["fields_total"] == 3 and row["fields_found"] == 2
    assert row["headings_exact"] == 0
    assert row["headings_without_diacritics_only"] == 1  # QUYET DINH
    assert row["headings_lost"] == 1
    assert 0 < row["cer"] < 0.2 and 0 < row["word_recall"] < 1
    dumped = json.dumps(row, ensure_ascii=False)
    for secret in (
        "9988776655",
        "1.234.567.890",
        "BÍ MẬT",
        "NGUYEN",
        "QUYET",
        "31/12/2099",
    ):
        assert secret not in dumped
    assert all(isinstance(v, (int, float, type(None))) for v in row.values())


def test_no_ground_truth_gives_no_accuracy_claim():
    row = bench.measure(MARKDOWN, None, [], [])
    assert set(row) == {"chars", "words"}


def test_aggregate_and_markdown_hold_no_text():
    docs = [
        {
            **bench.measure(MARKDOWN, SECRET_TEXT, ["9988776655"], []),
            "id": "doc-001",
            "category": "cong_van",
            "pages": 2,
            "seconds": 9.0,
            "tables": 1,
            "pages_orientation_corrected": 1,
        },
        {
            "id": "doc-002",
            "category": "cong_van",
            "error": "ValueError",
            "seconds": 1.0,
        },
    ]
    agg = bench.aggregate(docs)
    assert agg["documents"] == 2 and agg["failed"] == 1 and agg["pages"] == 2
    assert agg["seconds_per_page"] == 5.0 and agg["fields_found"] == 1
    report = {
        "engines": {"tesseract_best": {"all": agg, "by_category": {"cong_van": agg}}}
    }
    text = bench.to_markdown(report) + json.dumps(agg, ensure_ascii=False)
    for secret in ("9988776655", "BÍ MẬT", "NGUYEN", "1.234.567.890"):
        assert secret not in text


def test_the_script_never_writes_text_fields():
    """Static guard: no 'markdown'/'text'/'ground_truth' key is ever put in a row."""
    source = (ROOT / "scripts" / "ocr" / "local_document_benchmark.py").read_text()
    for forbidden in ('"markdown":', '"text":', '"ground_truth":', "str(e)", "repr(e)"):
        assert forbidden not in source, forbidden
