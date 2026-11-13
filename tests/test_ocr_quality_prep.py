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


@pytest.fixture
def clean_gate_env(monkeypatch):
    """tesseract_command() writes os.environ directly: make sure it is undone."""
    monkeypatch.setenv(tesseract_gate.REAL_ENV, "placeholder")
    monkeypatch.delenv(options.TESSERACT_GATE_ENV, raising=False)
    monkeypatch.setattr(options, "_GATE_OK", {})


def test_tesseract_command_gate_on_and_off(tmp_path, monkeypatch, clean_gate_env):
    fake = str(_fake_tesseract(tmp_path))
    cmd = options.tesseract_command(fake)
    assert Path(cmd).name == "tesseract_gate.py" and os.access(cmd, os.X_OK)
    assert os.environ[tesseract_gate.REAL_ENV] == fake
    monkeypatch.setenv(options.TESSERACT_GATE_ENV, "false")
    assert options.tesseract_command(fake) == fake


def test_gate_is_a_valid_docling_tesseract_cmd(tmp_path, clean_gate_env):
    """Docling validates tesseract_cmd; the gate path must be accepted as is."""
    pytest.importorskip("docling")
    from docling.datamodel.pipeline_options import TesseractCliOcrOptions

    cmd = options.tesseract_command(str(_fake_tesseract(tmp_path)))
    assert Path(cmd).name == "tesseract_gate.py"
    assert TesseractCliOcrOptions(lang=["vie"], tesseract_cmd=cmd).tesseract_cmd == cmd


def test_tesseract_command_falls_back_when_gate_cannot_run(
    tmp_path, monkeypatch, clean_gate_env
):
    """No python3 on PATH / no exec bit: OCR must keep working without the gate."""
    fake = str(_fake_tesseract(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))  # shebang cannot find python3
    assert options.tesseract_command(fake) == fake
    # A real binary that does not exist is not hidden behind the gate either.
    monkeypatch.undo()
    monkeypatch.setattr(options, "_GATE_OK", {})
    monkeypatch.setenv(tesseract_gate.REAL_ENV, "placeholder")
    missing = str(tmp_path / "no-such-tesseract")
    assert options.tesseract_command(missing) == missing


@pytest.mark.parametrize("raw", ["nan", "inf", "-1", "x"])
def test_confidence_envs_reject_nonsense(monkeypatch, raw):
    monkeypatch.setenv(tesseract_gate.MIN_CONFIDENCE_ENV, raw)
    monkeypatch.setenv(pdf_prep.PAGE_MIN_CONFIDENCE_ENV, raw)
    assert tesseract_gate.min_confidence() == tesseract_gate.DEFAULT_MIN_CONFIDENCE
    assert pdf_prep.page_min_confidence() == pdf_prep.DEFAULT_PAGE_MIN_CONFIDENCE


def test_gate_rotation_without_confidence_becomes_upright():
    out = tesseract_gate.gate_osd(
        "Orientation in degrees: 180\nRotate: 180\nOrientation confidence: nan\n", 2.0
    )
    assert "Orientation in degrees: 0" in out and "Rotate: 0" in out


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
    # A failing page is left as it is; never an exception, never a rotation.
    prep = pdf_prep.prepare(str(scan_pdf), "tesseract")
    assert prep.path is None and prep.rotated_pages == {} and prep.scale == 2.0
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


def test_one_bad_page_does_not_undo_the_others(scan_pdf, osd_available, monkeypatch):
    calls = []

    def flaky(image, cmd, tessdata):
        calls.append(image)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired("tesseract", 30)
        return (180, 9.0)

    monkeypatch.setattr(pdf_prep, "detect_page_rotation", flaky)
    prep = pdf_prep.prepare(str(scan_pdf), "tesseract")
    try:
        assert prep.rotated_pages == {1: 180} and prep.scale == 2.0
    finally:
        prep.cleanup()


def test_orientation_page_budget(scan_pdf, osd_available, monkeypatch):
    calls = []

    def upright(*a):
        calls.append(1)
        return (0, 9.0)

    monkeypatch.setattr(pdf_prep, "detect_page_rotation", upright)
    monkeypatch.setenv(pdf_prep.OSD_MAX_PAGES_ENV, "1")
    prep = pdf_prep.prepare(str(scan_pdf), "tesseract")
    assert len(calls) == 1 and prep.scan_dpi == 75.0  # resolution still measured


def test_document_scale_uses_the_highest_scan_resolution(
    tmp_path, osd_available, monkeypatch
):
    Image = pytest.importorskip("PIL.Image")
    pytest.importorskip("pypdfium2")
    import pypdfium2 as pdfium

    lo, hi = tmp_path / "lo.pdf", tmp_path / "hi.pdf"
    Image.new("RGB", (1240, 1754), "white").save(lo, resolution=150)
    Image.new("RGB", (2480, 3508), "white").save(hi, resolution=300)
    merged = pdfium.PdfDocument.new()
    for src in (lo, lo, hi):
        doc = pdfium.PdfDocument(str(src))
        merged.import_pages(doc)
        doc.close()
    mixed = tmp_path / "mixed.pdf"
    merged.save(str(mixed))
    merged.close()
    monkeypatch.setattr(pdf_prep, "detect_page_rotation", lambda *a: (0, 9.0))
    prep = pdf_prep.prepare(str(mixed), "tesseract")
    assert prep.scan_dpi == 300.0 and prep.scale is None  # 300 DPI pages keep scale 3


def test_convert_document_uses_and_removes_the_temporary_copy(
    scan_pdf, osd_available, monkeypatch
):
    from open_notebook.ocr import docling_extract

    monkeypatch.setattr(pdf_prep, "detect_page_rotation", lambda *a: (90, 9.0))
    monkeypatch.setattr(
        docling_extract.runtime, "tesseract_cmd", lambda: "tesseract", raising=False
    )
    seen = {}

    class Conv:
        def __init__(self, fail):
            self.fail = fail

        def convert(self, path):
            seen["path"], seen["existed"] = path, Path(path).is_file()
            if self.fail:
                raise RuntimeError("docling failed")
            return "result"

    for fail in (False, True):
        monkeypatch.setattr(
            docling_extract,
            "build_converter",
            lambda cc, ocr, scale=None, f=fail: Conv(f),
        )
        settings = options.OcrSettings(engine="rapidocr")
        if fail:
            with pytest.raises(RuntimeError):
                docling_extract.convert_document(str(scan_pdf), object(), settings)
        else:
            _res, _conv, prep = docling_extract.convert_document(
                str(scan_pdf), object(), settings
            )
            assert prep.as_meta()["rotated_pages"] == {"1": 90, "2": 90}
        assert seen["path"] != str(scan_pdf) and seen["existed"]
        assert not Path(seen["path"]).parent.exists()  # removed, also on failure


# --- Phase 8D: release validation ---------------------------------------------


def test_gate_refuses_to_call_itself(tmp_path):
    proc = _run_gate(Path(tesseract_gate.__file__), "--version")
    assert proc.returncode == 126 and "points to the gate itself" in proc.stderr
    link = tmp_path / "tesseract"
    link.symlink_to(tesseract_gate.__file__)
    assert _run_gate(link, "--psm", "0", "x.png", "stdout").returncode == 126


def test_gate_orientation_timeout_is_a_failed_osd_not_a_hang(tmp_path, monkeypatch):
    def slow(*a, **k):
        raise subprocess.TimeoutExpired("tesseract", 1)

    monkeypatch.setattr(tesseract_gate.subprocess, "run", slow)
    monkeypatch.setenv(tesseract_gate.REAL_ENV, str(_fake_tesseract(tmp_path)))
    assert tesseract_gate.main(["--psm", "0", "x.png", "stdout"]) == 124


def test_gate_holds_no_text_or_fixture_knowledge():
    """The gate may only look at the orientation lines of Tesseract's OSD output."""
    source = Path(tesseract_gate.__file__).read_text(encoding="utf-8")
    for forbidden in ("BẢNG", "BANG KE", "fixture", "replace(", "tsv", "hocr"):
        assert forbidden not in source, forbidden
    recognised = "level\tpage_num\ttext\n5\t1\tBANG KE 1.250.000.000\n"
    assert tesseract_gate.gate_osd(recognised, 2.0) == recognised


def test_tesseract_cmd_never_comes_from_a_request():
    """The command is deployment configuration: no API model carries one."""
    import api.models as models

    for name in ("OcrConfigUpdate", "OcrConfig"):
        fields = getattr(models, name).model_fields
        assert not [f for f in fields if "cmd" in f or "command" in f or "path" in f]


@pytest.mark.parametrize(
    "disable,cmd,osd,reason,available",
    [
        (None, "tesseract", True, "ok", True),
        ("false", "tesseract", True, "disabled", False),
        (None, None, True, "tesseract_missing", False),
        (None, "tesseract", False, "osd_data_missing", False),
    ],
)
def test_orientation_status(
    osd_available, monkeypatch, disable, cmd, osd, reason, available
):
    if disable:
        monkeypatch.setenv(pdf_prep.DISABLE_ENV, disable)
    if not osd:
        (osd_available / "osd.traineddata").unlink()
    status = pdf_prep.orientation_status(cmd)
    assert status["reason"] == reason and status["available"] is available
    assert status["enabled"] is (disable is None)


def test_prep_records_why_orientation_did_or_did_not_run(
    scan_pdf, osd_available, monkeypatch
):
    monkeypatch.setattr(pdf_prep, "detect_page_rotation", lambda *a: (0, 9.0))
    assert (
        pdf_prep.prepare(str(scan_pdf), "tesseract").as_meta()["page_orientation"]
        == "ok"
    )
    assert pdf_prep.prepare(str(scan_pdf), None).orientation == "tesseract_missing"
    (osd_available / "osd.traineddata").unlink()
    assert (
        pdf_prep.prepare(str(scan_pdf), "tesseract").orientation == "osd_data_missing"
    )
    monkeypatch.setenv(pdf_prep.DISABLE_ENV, "false")
    assert pdf_prep.prepare(str(scan_pdf), "tesseract").orientation == "disabled"


def test_readiness_fingerprint_follows_the_quality_configuration(
    osd_available, monkeypatch
):
    from open_notebook.ocr import readiness

    monkeypatch.setattr(readiness.runtime, "tesseract_cmd", lambda: "tesseract")
    monkeypatch.delenv(options.TESSERACT_GATE_ENV, raising=False)
    monkeypatch.delenv(options.EASYOCR_CONFIDENCE_ENV, raising=False)
    base = {
        e: readiness.quality_config(e)
        for e in ("rapidocr", "tesseract_best", "easyocr")
    }
    assert base["tesseract_best"]["osd_gate"] is True
    assert base["easyocr"]["confidence_threshold"] == 0.2
    assert base["rapidocr"]["page_orientation"]["available"] is True
    # Every quality switch changes the fingerprint of the engines it affects.
    monkeypatch.setenv(options.TESSERACT_GATE_ENV, "false")
    assert readiness.quality_config("tesseract_best") != base["tesseract_best"]
    assert readiness.quality_config("rapidocr") == base["rapidocr"]
    monkeypatch.delenv(options.TESSERACT_GATE_ENV)
    monkeypatch.setenv(options.EASYOCR_CONFIDENCE_ENV, "0.4")
    assert readiness.quality_config("easyocr") != base["easyocr"]
    monkeypatch.delenv(options.EASYOCR_CONFIDENCE_ENV)
    # Orientation data removed: stale for EVERY engine (it is used by all of them),
    # and orientation is never reported as available.
    (osd_available / "osd.traineddata").unlink()
    for engine in base:
        cfg = readiness.quality_config(engine)
        assert cfg != base[engine] and cfg["page_orientation"]["available"] is False
    assert "quality" in readiness.fingerprint("rapidocr")


def test_quality_tiers():
    from open_notebook.ocr import catalog

    tiers = {e: catalog.get_engine(e).quality for e in catalog.ENGINE_IDS}
    assert tiers == {
        "rapidocr": "compatibility",
        "tesseract_fast": "speed",
        "tesseract_best": "recommended",
        "easyocr": "experimental",
    }
    assert set(tiers.values()) <= set(catalog.QUALITY_TIERS)
    # An experimental engine is never the default (nor an automatic fallback).
    assert catalog.get_engine(catalog.DEFAULT_ENGINE).quality != "experimental"


FIXTURES = Path(__file__).parent / "fixtures" / "ocr"


@pytest.mark.parametrize("angle", [90, 180, 270])
def test_rotated_copy_keeps_text_layer_images_and_metadata(
    osd_available, monkeypatch, angle
):
    """hon_hop.pdf: a born-digital page with a text layer + a scanned page."""
    pdfium = pytest.importorskip("pypdfium2")
    import pypdfium2.raw as raw

    src = FIXTURES / "hon_hop.pdf"
    if not src.exists():
        pytest.skip("acceptance fixtures not present")
    monkeypatch.setattr(pdf_prep, "detect_page_rotation", lambda *a: (angle, 9.0))
    before = _sha(src)
    prep = pdf_prep.prepare(str(src), "tesseract")
    try:
        assert prep.path and _sha(src) == before

        def describe(path):
            doc = pdfium.PdfDocument(path)
            pages = []
            for index in range(len(doc)):
                page = doc[index]
                pages.append(
                    {
                        "text": page.get_textpage().get_text_range(),
                        "images": [
                            o.get_px_size()
                            for o in page.get_objects(
                                filter=[raw.FPDF_PAGEOBJ_IMAGE], max_depth=3
                            )
                        ],
                        "box": page.get_mediabox(),
                        "rotation": page.get_rotation(),
                    }
                )
            meta = doc.get_metadata_dict()
            doc.close()
            return pages, meta

        before_pages, before_meta = describe(str(src))
        after_pages, after_meta = describe(prep.path)
        assert len(after_pages) == len(before_pages) == 2
        assert after_meta == before_meta
        assert before_pages[0]["text"].strip()  # page 1 has a real text layer
        for a, b in zip(before_pages, after_pages):
            assert b["text"] == a["text"]  # text layer intact, nothing rasterised
            assert b["images"] == a["images"]  # same embedded scan, same pixels
            assert b["box"] == a["box"]
        # The ONLY difference: /Rotate of the scanned page; the text page is untouched.
        assert after_pages[0]["rotation"] == before_pages[0]["rotation"]
        assert after_pages[1]["rotation"] == (before_pages[1]["rotation"] + angle) % 360
        assert prep.rotated_pages == {1: angle}
    finally:
        prep.cleanup()


def test_gate_does_not_change_recognition_output(tmp_path):
    """Real Tesseract, when installed: recognition through the gate == direct."""
    import shutil

    real = shutil.which(os.environ.get("OCR_TESSERACT_CMD", "tesseract"))
    tessdata = os.environ.get("OCR_TEST_DATA_DIR") or os.environ.get("OCR_DATA_DIR")
    lang_dir = Path(tessdata or "/nonexistent") / "models" / "tesseract"
    if not real or not (lang_dir / "fast" / "vie.traineddata").is_file():
        pytest.skip("Tesseract runtime / Vietnamese model not installed")
    pdfium = pytest.importorskip("pypdfium2")
    image = tmp_path / "page.png"
    doc = pdfium.PdfDocument(str(FIXTURES / "vb_scan.pdf"))
    doc[0].render(scale=2.0, grayscale=True).to_pil().save(image)
    doc.close()
    args = [
        "-l",
        "fast/vie",
        "--tessdata-dir",
        str(lang_dir),
        str(image),
        "stdout",
        "tsv",
    ]
    direct = subprocess.run([real, *args], capture_output=True, timeout=300)
    gated = _run_gate(Path(real), *args)
    assert direct.returncode == 0 and gated.returncode == 0
    assert gated.stdout.encode() == direct.stdout and len(direct.stdout) > 500
    for extra in (["--version"], ["--list-langs", "--tessdata-dir", str(lang_dir)]):
        a = subprocess.run([real, *extra], capture_output=True, timeout=60)
        b = _run_gate(Path(real), *extra)
        assert (b.returncode, b.stdout.encode()) == (a.returncode, a.stdout)


def test_pdf_prep_uses_doclings_pdfium_lock_and_never_across_tesseract(
    scan_pdf, osd_available, monkeypatch
):
    """pdfium is not thread-safe: synchronous API requests run in threads, so the
    preparation must share Docling's lock — and release it for the slow part."""
    pytest.importorskip("docling")
    from docling.utils.locks import pypdfium2_lock

    assert pdf_prep._pdfium_lock() is pypdfium2_lock
    held_during_tesseract = []

    def detect(*a):
        held_during_tesseract.append(pypdfium2_lock.locked())
        return (90, 9.0)

    monkeypatch.setattr(pdf_prep, "detect_page_rotation", detect)
    prep = pdf_prep.prepare(str(scan_pdf), "tesseract")
    try:
        assert prep.rotated_pages == {0: 90, 1: 90}
        assert held_during_tesseract == [False, False]
        assert not pypdfium2_lock.locked()  # released on every path
    finally:
        prep.cleanup()


def test_hub_timeout_install_never_fails_a_document(monkeypatch):
    from open_notebook.ocr import hub_http

    def broken():
        raise AttributeError("huggingface_hub moved its internals")

    monkeypatch.setattr(hub_http, "_install", broken)
    assert hub_http.bound_hub_timeouts() is False


# ---------------------------------------------------------------------------
# Phase 9B: total time budget of the orientation step, pdfium lock coverage
# ---------------------------------------------------------------------------
def test_orientation_time_budget_limits_the_step_not_the_document(
    scan_pdf, osd_available, monkeypatch
):
    """A slow orientation step stops checking pages; it never fails or drops the
    document, keeps what it already corrected and says that it was limited."""
    clock = [1000.0]
    calls = []

    def slow(*a):
        calls.append(1)
        clock[0] += 400.0  # each page "takes" 400 s
        return (90, 9.0)

    monkeypatch.setattr(pdf_prep, "_now", lambda: clock[0])
    monkeypatch.setattr(pdf_prep, "detect_page_rotation", slow)
    monkeypatch.setenv(pdf_prep.OSD_BUDGET_ENV, "300")
    before = _sha(scan_pdf)
    prep = pdf_prep.prepare(str(scan_pdf), "tesseract")
    try:
        assert len(calls) == 1  # page 2 was not checked: budget spent
        assert prep.rotated_pages == {0: 90}  # the finished page is kept
        assert prep.path and Path(prep.path).is_file()
        assert prep.orientation == "ok" and prep.scan_dpi == 75.0
        meta = prep.as_meta()
        assert meta["page_orientation_limit"] == "time_budget"
        assert meta["orientation_checked_pages"] == 1
        assert _sha(scan_pdf) == before  # the upload is never modified
    finally:
        prep.cleanup()
    assert prep.path is None


def test_orientation_within_budget_reports_no_limit(
    scan_pdf, osd_available, monkeypatch
):
    monkeypatch.delenv(pdf_prep.OSD_BUDGET_ENV, raising=False)
    monkeypatch.delenv(pdf_prep.OSD_MAX_PAGES_ENV, raising=False)
    monkeypatch.setattr(pdf_prep, "detect_page_rotation", lambda *a: (0, 9.0))
    meta = pdf_prep.prepare(str(scan_pdf), "tesseract").as_meta()
    assert meta["page_orientation_limit"] is None
    assert meta["orientation_checked_pages"] == 2


def test_orientation_page_cap_is_reported(scan_pdf, osd_available, monkeypatch):
    monkeypatch.setattr(pdf_prep, "detect_page_rotation", lambda *a: (0, 9.0))
    monkeypatch.setenv(pdf_prep.OSD_MAX_PAGES_ENV, "1")
    meta = pdf_prep.prepare(str(scan_pdf), "tesseract").as_meta()
    assert meta["page_orientation_limit"] == "max_pages"
    assert meta["orientation_checked_pages"] == 1


def test_orientation_switched_off_by_page_cap_zero_is_not_a_limit(
    scan_pdf, osd_available, monkeypatch
):
    """OCR_PAGE_OSD_MAX_PAGES=0 is a deliberate "do not check": no limit is
    reported and no warning is logged for every document."""
    calls: list[int] = []
    warned: list[str] = []
    monkeypatch.setattr(pdf_prep, "detect_page_rotation", lambda *a: calls.append(1))
    monkeypatch.setattr(pdf_prep.logger, "warning", warned.append)
    monkeypatch.setenv(pdf_prep.OSD_MAX_PAGES_ENV, "0")
    prep = pdf_prep.prepare(str(scan_pdf), "tesseract")
    meta = prep.as_meta()
    assert calls == [] and warned == []
    assert meta["page_orientation_limit"] is None
    assert meta["orientation_checked_pages"] == 0 and prep.scan_dpi == 75.0


@pytest.mark.parametrize("raw", ["nan", "inf", "-inf", "0", "-5", "x", "", "1e400"])
def test_orientation_budget_env_rejects_nonsense(monkeypatch, raw):
    monkeypatch.setenv(pdf_prep.OSD_BUDGET_ENV, raw)
    assert pdf_prep.osd_budget_seconds() == pdf_prep.DEFAULT_OSD_BUDGET_SECONDS


def test_orientation_budget_env_is_capped(monkeypatch):
    monkeypatch.setenv(pdf_prep.OSD_BUDGET_ENV, "45")
    assert pdf_prep.osd_budget_seconds() == 45.0
    monkeypatch.setenv(pdf_prep.OSD_BUDGET_ENV, "1e9")
    assert pdf_prep.osd_budget_seconds() == pdf_prep.MAX_OSD_BUDGET_SECONDS
    assert pdf_prep.orientation_status("tesseract")["time_budget_seconds"] == (
        pdf_prep.MAX_OSD_BUDGET_SECONDS
    )


def test_orientation_budget_does_not_change_the_readiness_fingerprint(
    osd_available, monkeypatch
):
    """The budget bounds time, not results: an earlier verdict stays valid."""
    from open_notebook.ocr import readiness

    monkeypatch.delenv(pdf_prep.OSD_BUDGET_ENV, raising=False)
    base = readiness.quality_config("tesseract_best")
    monkeypatch.setenv(pdf_prep.OSD_BUDGET_ENV, "30")
    assert readiness.quality_config("tesseract_best") == base


def test_every_pdfium_call_of_pdf_prep_holds_doclings_lock(
    scan_pdf, osd_available, monkeypatch
):
    """get_size / render / rotation / close / save included (pdfium is not
    thread-safe and synchronous API requests convert in threads)."""
    pytest.importorskip("docling")
    import pypdfium2 as pdfium
    from docling.utils.locks import pypdfium2_lock

    unlocked: list[str] = []

    def spy(cls, name):
        original = getattr(cls, name)

        def wrapper(self, *a, **k):
            if not pypdfium2_lock.locked():
                unlocked.append(f"{cls.__name__}.{name}")
            return original(self, *a, **k)

        monkeypatch.setattr(cls, name, wrapper)

    for name in (
        "get_size",
        "render",
        "get_rotation",
        "set_rotation",
        "get_objects",
        "close",
    ):
        spy(pdfium.PdfPage, name)
    for name in ("__init__", "__len__", "__getitem__", "save", "close"):
        spy(pdfium.PdfDocument, name)
    monkeypatch.setattr(pdf_prep, "detect_page_rotation", lambda *a: (90, 9.0))
    prep = pdf_prep.prepare(str(scan_pdf), "tesseract")
    try:
        assert prep.rotated_pages == {0: 90, 1: 90}  # the whole path really ran
        assert unlocked == []
        assert not pypdfium2_lock.locked()
    finally:
        prep.cleanup()


def test_one_unloadable_page_does_not_undo_the_others(
    scan_pdf, osd_available, monkeypatch
):
    """Phase 9B (A11): a page pdfium cannot load is skipped, not the document."""
    import pypdfium2 as pdfium

    original = pdfium.PdfDocument.__getitem__

    def flaky(self, index):
        if index == 0:
            raise RuntimeError("Failed to load page.")
        return original(self, index)

    monkeypatch.setattr(pdfium.PdfDocument, "__getitem__", flaky)
    monkeypatch.setattr(pdf_prep, "detect_page_rotation", lambda *a: (180, 9.0))
    prep = pdf_prep.prepare(str(scan_pdf), "tesseract")
    try:
        assert prep.orientation == "ok"  # not "skipped": the rest was prepared
        assert prep.rotated_pages == {1: 180} and prep.scale == 2.0
    finally:
        prep.cleanup()
