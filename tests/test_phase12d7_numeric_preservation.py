"""E1-03 (Phase 12D7): Legal and the numbers Tesseract recognised.

On the Windows runs (12E1) Legal content showed page and voucher numbers as
``1.0``, ``2.0``, ``2024.0``. Legal did not create those values: the OCR cells
were already rewritten by Docling's TSV parse (E0-07), so a page number read
as ``2`` arrived as ``2.0``, which is not a page-number shape, and stayed in
the content. After the E0-07 patch the cells hold what Tesseract read.

Legal must not try to undo the old damage either: no regex guesses that
``1.0`` was ``0001``, no numeric line is deleted to hide a wrong number, and
clause / voucher / document numbers and reporting periods stay verbatim.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("docling")

sys.path.insert(0, str(Path(__file__).parent))

import legal_harness as H  # noqa: E402

from open_notebook.ocr import docling_patches  # noqa: E402
from open_notebook.ocr import legal_normalizer as N  # noqa: E402

FX = H.load_fixtures()
E = FX.E

# tokens of the E0-07 list as they appear in legal / banking documents
BODY_TOKENS = [
    "Số: 0001/2024/QĐ-NHNo",
    "0001",
    "000123",
    "2024",
    "9.",
    "12.50",
    "1/2024",
    "001/2024",
    "05%",
    "Kỳ báo cáo: Quý 1/2024",
    "Chứng từ số 000000000000000123",
    "1.0",
    "2024.0",
    "NA",
    "N/A",
]


def _doc(pages):
    return H.build_document({"pages": pages})


def _pages_with_bottom_value(n_pages, value):
    pages = []
    for p in range(1, n_pages + 1):
        pages.append(
            [
                E("text", f"Nội dung trang {p} của tài liệu thử nghiệm.", y=100, h=28),
                E("text", value(p), x=290, y=800, w=16, h=12),
            ]
        )
    return pages


def _lines(content: str) -> list[str]:
    return [line.strip() for line in content.split("\n\n") if line.strip()]


def test_page_numbers_as_the_old_parser_wrote_them_are_kept_verbatim():
    """What 12E1 saw: 2.0 is not a page number, Legal keeps it - and never
    guesses what it was."""
    res = N.normalize_document(_doc(_pages_with_bottom_value(5, lambda p: f"{p}.0")))
    assert "page_number_to_furniture" not in res.counts
    for p in range(1, 6):
        assert f"{p}.0" in _lines(res.content)
    assert "0001" not in res.content and "\n\n1\n\n" not in f"\n\n{res.content}\n\n"


def test_the_same_page_numbers_as_tesseract_read_them_are_recognised():
    """After E0-07 the cell holds "2": the page-number rules apply as designed."""
    res = N.normalize_document(_doc(_pages_with_bottom_value(5, lambda p: str(p))))
    assert res.counts["page_number_to_furniture"] == 5


@pytest.mark.parametrize(
    "value",
    [
        lambda p: f"000{p}",  # a voucher / document number: leading zero
        lambda p: f"{p}/2024",  # a reporting period, not "n of m"
        lambda p: f"{2020 + p}",  # years
    ],
    ids=["leading_zero", "period", "years"],
)
def test_numbers_at_the_page_number_place_that_are_not_page_numbers_stay(value):
    res = N.normalize_document(_doc(_pages_with_bottom_value(5, value)))
    assert "page_number_to_furniture" not in res.counts
    for p in range(1, 6):
        assert value(p) in _lines(res.content)


def test_numbers_and_codes_in_the_body_are_kept_verbatim():
    page = [E("text", t, y=80 + 40 * i, h=20) for i, t in enumerate(BODY_TOKENS)]
    res = N.normalize_document(_doc([page]))
    lines = _lines(res.content)
    for token in BODY_TOKENS:
        assert token in lines, token
    assert len(lines) == len(BODY_TOKENS)  # nothing deleted, nothing merged


# --------------------------------------------------------------------------- #
# The chain: raw TSV -> Docling's OCR cell text -> Legal content
# --------------------------------------------------------------------------- #

HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
STRUCTURE = [
    "1\t1\t0\t0\t0\t0\t0\t0\t600\t80\t-1\t",
    "2\t1\t1\t0\t0\t0\t10\t10\t580\t60\t-1\t",
    "3\t1\t1\t1\t0\t0\t10\t10\t580\t60\t-1\t",
    "4\t1\t1\t1\t1\t0\t10\t10\t580\t60\t-1\t",
]
FAKE = textwrap.dedent(
    """\
    #!{python}
    import os, sys
    a = sys.argv[1:]
    if a[:1] == ["--version"]:
        print("tesseract 5.3.4"); sys.exit(0)
    if a[:1] == ["--list-langs"]:
        print('List of available languages in "x" (2):'); print("osd"); print("vie"); sys.exit(0)
    with open(os.environ["FAKE_TSV"], "rb") as fh:
        sys.stdout.buffer.write(fh.read())
    """
)


def _crop_text(tmp_path, monkeypatch, words, patched):
    """The text Docling makes of one OCR crop whose raw TSV holds ``words``."""
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.pipeline_options import TesseractCliOcrOptions
    from docling.models.stages.ocr import tesseract_ocr_cli_model as tm

    exe = tmp_path / "tesseract"
    exe.write_text(FAKE.format(python=sys.executable))
    exe.chmod(0o755)
    rows = [HEADER, *STRUCTURE] + [
        f"5\t1\t1\t1\t1\t{i}\t{10 + 60 * i}\t12\t50\t40\t96.25\t{w}"
        for i, w in enumerate(words, 1)
    ]
    data = tmp_path / "raw.tsv"
    data.write_text("\n".join(rows) + "\n", encoding="utf-8")
    monkeypatch.setenv("FAKE_TSV", str(data))
    model = tm.TesseractOcrCliModel(
        enabled=True,
        artifacts_path=None,
        options=TesseractCliOcrOptions(lang=["vie"], tesseract_cmd=str(exe)),
        accelerator_options=AcceleratorOptions(),
    )
    image = tmp_path / "crop.png"
    image.write_bytes(b"")
    fn = (
        docling_patches._run_tesseract
        if patched
        else docling_patches.upstream_function()
    )
    # Docling builds each OCR cell with str(row["text"]) (TesseractOcrCliModel.__call__)
    return " ".join(str(t) for t in fn(model, str(image), None)["text"])


@pytest.mark.parametrize(
    "words, old",
    [
        (["0001"], "1.0"),
        (["2024"], "2024.0"),
        (["000123"], "123.0"),
        (["9."], "9.0"),
        (["12.50"], "12.5"),
    ],
)
def test_from_the_raw_tsv_to_legal_content(tmp_path, monkeypatch, words, old):
    before = _crop_text(tmp_path, monkeypatch, words, patched=False)
    after = _crop_text(tmp_path, monkeypatch, words, patched=True)
    assert before == old  # E0-07: what reached Legal on Windows (E1-03)
    assert after == " ".join(words)
    for text, expected in ((before, old), (after, " ".join(words))):
        page = [
            E("text", "Điều 1. Nội dung quyết định.", y=100, h=20),
            E("text", text, y=140, h=20),
        ]
        res = N.normalize_document(_doc([page]))
        assert expected in _lines(res.content)  # Legal is transparent: no guess
