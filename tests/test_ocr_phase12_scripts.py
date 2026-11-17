"""Phase 12 diagnostic / comparison scripts (scripts/ocr/phase12_*.py).

The Docling conversion is replaced by a document from Docling's real
ReadingOrderModel (the layout weights are not available everywhere); the
direct Tesseract layer is real when Tesseract with Vietnamese is installed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("docling")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "ocr"))
sys.path.insert(0, str(ROOT / "tests"))

import generate_phase12_fixtures as G  # noqa: E402
import legal_harness as H  # noqa: E402
import phase12_compare as C  # noqa: E402
import phase12_diagnose as D  # noqa: E402
import phase12_metrics as M  # noqa: E402

from open_notebook.ocr import docling_extract  # noqa: E402
from open_notebook.ocr import pdf_prep as pdf_prep_mod  # noqa: E402


@pytest.fixture
def stub_conversion(monkeypatch):
    fixture = H.load_fixtures().by_name("f02_clause_across_pages")
    doc = H.build_document(fixture)

    def fake(path, cfg, ocr):
        result = SimpleNamespace(
            document=doc,
            status=SimpleNamespace(value="success"),
            errors=[],
            pages=[],
            assembled=None,
        )
        return result, SimpleNamespace(initialized_pipelines={}), pdf_prep_mod.PdfPrep()

    monkeypatch.setattr(docling_extract, "convert_document", fake)
    return fixture


@pytest.fixture
def fixture_pdfs(tmp_path):
    G.main(["--out", str(tmp_path / "fx"), "--only", "f02_clause_across_pages"])
    return tmp_path / "fx"


def test_generator_writes_scan_and_ground_truth(fixture_pdfs):
    pdf = fixture_pdfs / "f02_clause_across_pages.scan.pdf"
    assert pdf.read_bytes().startswith(b"%PDF")
    gt = (fixture_pdfs / "f02_clause_across_pages.scan.gt.txt").read_text(
        encoding="utf-8"
    )
    assert "9. Dịch vụ phi tài chính" in gt
    manifest = json.loads((fixture_pdfs / "manifest.json").read_text(encoding="utf-8"))
    assert manifest[0]["pages"] == 2


def test_diagnose_writes_every_layer(stub_conversion, fixture_pdfs, tmp_path):
    out = tmp_path / "diag"
    pdf = fixture_pdfs / "f02_clause_across_pages.scan.pdf"
    D.main(
        [
            str(pdf),
            "--out",
            str(out),
            "--engine",
            "rapidocr",
            "--no-direct",
            "--ground-truth",
            str(fixture_pdfs / "f02_clause_across_pages.scan.gt.txt"),
        ]
    )
    for name in (
        "00_environment.json",
        "05_docling_document.json",
        "06_items.json",
        "07_markdown_standard.md",
        "08_markdown_legal.md",
        "09_legal_report.json",
        "10_display_standard.txt",
        "10_display_legal.txt",
        "12_summary.json",
    ):
        assert (out / name).is_file(), name
    summary = json.loads((out / "12_summary.json").read_text(encoding="utf-8"))
    assert (
        summary["standard"]["placeholders"] == 1
        and summary["legal"]["placeholders"] == 0
    )
    assert (
        summary["standard"]["numeric_only_lines"] == 2
        and summary["legal"]["numeric_only_lines"] == 0
    )
    assert summary["ground_truth"]["legal"]["cer"] == 0.0
    report = json.loads((out / "09_legal_report.json").read_text(encoding="utf-8"))
    assert any(
        op["op"] == "join_across_pages" and op["text_before"]
        for op in report["operations"]
    )
    assert (out.stat().st_mode & 0o077) == 0  # owner-only folder
    env = json.loads((out / "00_environment.json").read_text(encoding="utf-8"))
    assert "Dịch vụ" not in json.dumps(
        env, ensure_ascii=False
    )  # environment holds no text


def test_diagnose_refuses_non_empty_output(stub_conversion, fixture_pdfs, tmp_path):
    out = tmp_path / "diag"
    out.mkdir()
    (out / "keep.txt").write_text("x")
    with pytest.raises(SystemExit):
        D.main(
            [
                str(fixture_pdfs / "f02_clause_across_pages.scan.pdf"),
                "--out",
                str(out),
                "--no-direct",
            ]
        )
    assert (out / "keep.txt").read_text() == "x"


def test_diagnose_refuses_remote_api():
    with pytest.raises(SystemExit):
        D.fetch_source("https://example.com", "source:1", None, allow_remote=False)
    with pytest.raises(SystemExit):
        D.fetch_source(
            "file://localhost/etc/passwd", "source:1", None, allow_remote=False
        )


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract not installed")
def test_direct_tesseract_layer_is_real(stub_conversion, fixture_pdfs, tmp_path):
    langs = subprocess.run(
        ["tesseract", "--list-langs"], capture_output=True, text=True, check=False
    ).stdout
    if "vie" not in langs.split():
        pytest.skip("Vietnamese Tesseract data not installed")
    out = tmp_path / "diag"
    D.main(
        [
            str(fixture_pdfs / "f02_clause_across_pages.scan.pdf"),
            "--out",
            str(out),
            "--direct-lang",
            "vie",
            "--dpi",
            "200",
        ]
    )
    page1 = (out / "01_tesseract_p001.txt").read_text(encoding="utf-8")
    assert "Dịch vụ" in page1
    assert (
        (out / "01_tesseract_p001.tsv").read_text(encoding="utf-8").startswith("level")
    )
    summary = json.loads((out / "12_summary.json").read_text(encoding="utf-8"))
    assert summary["page_end_words_in_legal"]


def test_compare_one_command(stub_conversion, fixture_pdfs, tmp_path):
    out = tmp_path / "cmp"
    C.main([str(fixture_pdfs), "--out", str(out), "--no-direct"])
    data = json.loads((out / "compare.json").read_text(encoding="utf-8"))
    names = {r["document"] for r in data["rows"]}
    assert "f02_clause_across_pages.scan.pdf" in names
    row = next(
        r for r in data["rows"] if r["document"] == "f02_clause_across_pages.scan.pdf"
    )
    assert (
        row["placeholders_standard"] == 1
        and row["placeholders_legal"] == 0
        and row["joins"] == 1
    )
    assert row["cer_legal"] == 0.0  # <name>.gt.txt picked up automatically
    assert "Dịch vụ" not in (out / "compare.json").read_text(encoding="utf-8")


def test_metrics_renumbering():
    assert M.renumbered_list_items("5. a\n7. b\n13. c") == (2, 3)
    assert M.renumbered_list_items("5\\. a\n\n7\\. b") == (0, 0)
