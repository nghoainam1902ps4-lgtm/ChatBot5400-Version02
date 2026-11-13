"""Phase 8C quality corrections (DECISIONS D-25 / D-26).

* ``tesseract_gate``: low-confidence orientation guesses become "upright".
* ``pdf_prep``: page orientation on a temporary copy, OCR scale from scan DPI.
* EasyOCR confidence threshold.

No OCR engine is needed: Tesseract is replaced by a small fake executable and
the page-orientation detector by a stub.
"""

import hashlib
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from open_notebook.ocr import options, pdf_prep, tesseract_gate

OSD = (
    "Page number: 0\n"
    "Orientation in degrees: {deg}\n"
    "Rotate: {rot}\n"
    "Orientation confidence: {conf}\n"
    "Script: Latin\n"
    "Script confidence: 3.10\n"
)


# --- tesseract_gate ----------------------------------------------------------


def test_gate_recognises_only_orientation_calls():
    assert tesseract_gate.is_osd_call(["--psm", "0", "-l", "osd", "a.png", "stdout"])
    assert not tesseract_gate.is_osd_call(["-l", "vie", "a.png", "stdout", "tsv"])
    assert not tesseract_gate.is_osd_call(["--psm", "6", "a.png", "stdout"])
    assert not tesseract_gate.is_osd_call(["--version"])


@pytest.mark.parametrize(
    "deg,conf,expected",
    [
        (180, 0.16, 0),  # the Phase 8B table crop: wrong and unsure -> upright
        (90, 0.02, 0),
        (90, 1.99, 0),
        (90, 2.0, 90),  # confident rotations are kept
        (270, 7.5, 270),
        (0, 0.1, 0),
    ],
)
def test_gate_osd_threshold(deg, conf, expected):
    out = tesseract_gate.gate_osd(
        OSD.format(deg=deg, rot=(360 - deg) % 360, conf=conf), 2.0
    )
    assert tesseract_gate.parse_osd(out) == (expected, conf)
    if expected == 0:
        assert "Rotate: 0\n" in out
    assert "Script: Latin" in out  # everything else untouched


def test_gate_leaves_unparseable_output_alone():
    assert tesseract_gate.gate_osd("Too few characters", 2.0) == "Too few characters"


def _fake_tesseract(tmp_path: Path) -> Path:
    fake = tmp_path / "fake-tesseract"
    fake.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        f"  *'--psm 0'*) printf '{OSD.format(deg=180, rot=180, conf=0.16)}' ;;\n".replace(
            "\n'", "\\n'"
        )
        + "  *fail*) echo boom >&2; exit 3 ;;\n"
        '  *) echo "ARGS:$*" ;;\n'
        "esac\n"
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    return fake


def _run_gate(fake: Path, *args: str, env: dict | None = None):
    full_env = {**os.environ, tesseract_gate.REAL_ENV: str(fake), **(env or {})}
    return subprocess.run(
        [sys.executable, tesseract_gate.__file__, *args],
        capture_output=True,
        text=True,
        env=full_env,
        timeout=30,
    )


def test_gate_process_rewrites_low_confidence_osd(tmp_path):
    fake = _fake_tesseract(tmp_path)
    proc = _run_gate(fake, "--psm", "0", "-l", "osd", "x.png", "stdout")
    assert proc.returncode == 0
    assert "Orientation in degrees: 0" in proc.stdout
    assert "Orientation confidence: 0.16" in proc.stdout
    # A threshold of 0 keeps Tesseract's answer.
    proc = _run_gate(
        fake,
        "--psm",
        "0",
        "x.png",
        "stdout",
        env={tesseract_gate.MIN_CONFIDENCE_ENV: "0"},
    )
    assert "Orientation in degrees: 180" in proc.stdout


def test_gate_process_passes_other_calls_through(tmp_path):
    fake = _fake_tesseract(tmp_path)
    proc = _run_gate(fake, "-l", "best/vie", "x.png", "stdout", "tsv")
    assert proc.stdout.strip() == "ARGS:-l best/vie x.png stdout tsv"
    proc = _run_gate(fake, "fail")
    assert proc.returncode == 3 and "boom" in proc.stderr


def test_tesseract_command_gate_on_and_off(monkeypatch):
    monkeypatch.delenv(options.TESSERACT_GATE_ENV, raising=False)
    monkeypatch.delenv(tesseract_gate.REAL_ENV, raising=False)
    cmd = options.tesseract_command("/usr/bin/tesseract")
    assert Path(cmd).name == "tesseract_gate.py" and os.access(cmd, os.X_OK)
    assert os.environ[tesseract_gate.REAL_ENV] == "/usr/bin/tesseract"
    monkeypatch.setenv(options.TESSERACT_GATE_ENV, "false")
    assert options.tesseract_command("/usr/bin/tesseract") == "/usr/bin/tesseract"


def test_gate_is_a_valid_docling_tesseract_cmd(monkeypatch):
    """Docling validates tesseract_cmd; the gate path must be accepted as is."""
    pytest.importorskip("docling")
    from docling.datamodel.pipeline_options import TesseractCliOcrOptions

    monkeypatch.delenv(options.TESSERACT_GATE_ENV, raising=False)
    cmd = options.tesseract_command("tesseract")
    assert TesseractCliOcrOptions(lang=["vie"], tesseract_cmd=cmd).tesseract_cmd == cmd


# --- EasyOCR threshold -------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, 0.2),
        ("", 0.2),
        ("0.35", 0.35),
        ("0", 0.0),
        ("1", 1.0),
        ("1.5", 0.2),
        ("-1", 0.2),
        ("x", 0.2),
    ],
)
def test_easyocr_confidence_threshold(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv(options.EASYOCR_CONFIDENCE_ENV, raising=False)
    else:
        monkeypatch.setenv(options.EASYOCR_CONFIDENCE_ENV, raw)
    assert options.easyocr_confidence_threshold() == expected


# --- pdf_prep ----------------------------------------------------------------


@pytest.mark.parametrize(
    "dpi,expected",
    [
        (None, None),
        (0, None),
        (150, 2.0833),
        (200, 2.7778),
        (216, None),
        (300, None),
        (96, 2.0),
        (72, 2.0),
    ],
)
def test_scale_for_dpi(dpi, expected):
    assert pdf_prep.scale_for_dpi(dpi) == expected


@pytest.fixture
def scan_pdf(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    pytest.importorskip("pypdfium2")
    img = Image.new("RGB", (620, 877), "white")  # A4 at 75 DPI
    path = tmp_path / "scan.pdf"
    img.save(path, save_all=True, append_images=[img.copy()], resolution=75)
    return path


@pytest.fixture
def osd_available(tmp_path, monkeypatch):
    tessdata = tmp_path / "tessdata"
    tessdata.mkdir()
    (tessdata / "osd.traineddata").write_bytes(b"x")
    monkeypatch.setattr(pdf_prep.paths, "tessdata_dir", lambda: tessdata)
    monkeypatch.delenv(pdf_prep.DISABLE_ENV, raising=False)
    monkeypatch.delenv(pdf_prep.PAGE_MIN_CONFIDENCE_ENV, raising=False)
    return tessdata


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_prepare_rotates_confident_pages_in_a_temporary_copy(
    scan_pdf, osd_available, monkeypatch
):
    import pypdfium2 as pdfium

    answers = iter([(90, 8.0), (180, 0.5)])  # page 1 confident, page 2 unsure
    monkeypatch.setattr(pdf_prep, "detect_page_rotation", lambda *a: next(answers))
    before = _sha(scan_pdf)
    prep = pdf_prep.prepare(str(scan_pdf), "tesseract")
    try:
        assert prep.rotated_pages == {0: 90}
        assert prep.path and prep.path != str(scan_pdf)
        assert Path(prep.path).name == "scan.pdf"  # Docling names the document
        assert _sha(scan_pdf) == before  # the upload is never modified
        copy = pdfium.PdfDocument(prep.path)
        assert [copy[i].get_rotation() for i in range(len(copy))] == [90, 0]
        copy.close()
        assert prep.scan_dpi == 75.0 and prep.scale == 2.0
        assert prep.as_meta()["rotated_pages"] == {"1": 90}
        tmp = Path(prep.path).parent
    finally:
        prep.cleanup()
    assert not tmp.exists() and prep.path is None


def test_prepare_upright_scan_uses_the_original_file(
    scan_pdf, osd_available, monkeypatch
):
    monkeypatch.setattr(pdf_prep, "detect_page_rotation", lambda *a: (0, 9.0))
    prep = pdf_prep.prepare(str(scan_pdf), "tesseract")
    assert prep.path is None and prep.rotated_pages == {} and prep.scale == 2.0


def test_prepare_without_osd_data_never_calls_tesseract(
    scan_pdf, osd_available, monkeypatch
):
    (osd_available / "osd.traineddata").unlink()

    def boom(*a):
        raise AssertionError("orientation detection must not run")

    monkeypatch.setattr(pdf_prep, "detect_page_rotation", boom)
    prep = pdf_prep.prepare(str(scan_pdf), "tesseract")
    assert prep.path is None and prep.scan_dpi == 75.0
    assert pdf_prep.prepare(str(scan_pdf), None).path is None


def test_prepare_ignores_text_pdfs_other_files_and_failures(
    tmp_path, scan_pdf, osd_available, monkeypatch
):
    def boom(*a):
        raise RuntimeError("tesseract exploded")

    monkeypatch.setattr(pdf_prep, "detect_page_rotation", boom)
    # A failure means "convert the document as it is", never an exception.
    prep = pdf_prep.prepare(str(scan_pdf), "tesseract")
    assert prep.path is None and prep.scale is None and prep.rotated_pages == {}
    # Not a PDF / unreadable / disabled: nothing happens.
    txt = tmp_path / "a.txt"
    txt.write_text("hello")
    assert pdf_prep.prepare(str(txt), "tesseract").as_meta()["scan_dpi"] is None
    assert pdf_prep.prepare(str(tmp_path / "missing.pdf"), "tesseract").path is None
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 not really")
    assert pdf_prep.prepare(str(broken), "tesseract").path is None
    monkeypatch.setenv(pdf_prep.DISABLE_ENV, "false")
    assert pdf_prep.prepare(str(scan_pdf), "tesseract").scan_dpi is None


def test_born_digital_pdf_is_left_alone(osd_available, monkeypatch):
    fixture = Path(__file__).parent / "fixtures" / "ocr" / "vb_text.pdf"
    if not fixture.exists():
        pytest.skip("acceptance fixtures not present")
    pytest.importorskip("pypdfium2")

    def boom(*a):
        raise AssertionError("a text-layer page must not be inspected")

    monkeypatch.setattr(pdf_prep, "detect_page_rotation", boom)
    prep = pdf_prep.prepare(str(fixture), "tesseract")
    assert prep.path is None and prep.scale is None and prep.scan_dpi is None


def test_detect_page_rotation_maps_orientation_to_clockwise_rotation(monkeypatch):
    class Proc:
        returncode = 0
        stdout = OSD.format(deg=270, rot=90, conf=6.5).encode()

    monkeypatch.setattr(pdf_prep.subprocess, "run", lambda *a, **k: Proc())
    assert pdf_prep.detect_page_rotation("p.png", "tesseract", "/td") == (90, 6.5)
    Proc.returncode = 1  # "Too few characters"
    assert pdf_prep.detect_page_rotation("p.png", "tesseract", "/td") is None


def test_convert_document_scale_only_for_tesseract(monkeypatch):
    from open_notebook.ocr import docling_extract

    seen = {}

    class Conv:
        def convert(self, path):
            seen["path"] = path
            return "result"

    def fake_build(cc, ocr, scale=None):
        seen["scale"] = scale
        return Conv()

    monkeypatch.setattr(docling_extract, "build_converter", fake_build)
    monkeypatch.setattr(
        pdf_prep,
        "prepare",
        lambda path, cmd: pdf_prep.PdfPrep(scale=2.0833, scan_dpi=150.0),
    )
    for engine, expected in (
        ("tesseract_best", 2.0833),
        ("rapidocr", None),
        ("easyocr", None),
    ):
        docling_extract.convert_document(
            "/x/a.pdf", object(), options.OcrSettings(engine=engine)
        )
        assert seen["scale"] == expected and seen["path"] == "/x/a.pdf"
    # OCR switched off: no preparation at all.
    monkeypatch.setattr(pdf_prep, "prepare", lambda *a: pytest.fail("must not run"))
    docling_extract.convert_document(
        "/x/a.pdf",
        object(),
        options.OcrSettings(engine="tesseract_best", enabled=False),
    )
    assert seen["scale"] is None


def test_tesseract_command_falls_back_when_gate_is_not_executable(monkeypatch):
    monkeypatch.delenv(options.TESSERACT_GATE_ENV, raising=False)
    import os as real_os

    monkeypatch.setattr(real_os, "access", lambda *a: False)
    monkeypatch.setattr(Path, "chmod", lambda self, mode: None)
    assert options.tesseract_command("/usr/bin/tesseract") == "/usr/bin/tesseract"
