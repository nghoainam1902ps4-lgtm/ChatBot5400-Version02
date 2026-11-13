"""Fixes from the Phase 9B independent review (docs/ocr/OCR_PHASE9B_REPORT.md)."""

import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from open_notebook.ocr import docling_extract, readiness

ROOT = Path(__file__).resolve().parents[1]


# --- L4 / N6: a mistyped OCR_READINESS_TIMEOUT must not stop the application --
@pytest.mark.parametrize("raw", ["30m", "", "0", "-5", "1.5", "nan"])
def test_readiness_timeout_env_falls_back(monkeypatch, raw):
    monkeypatch.setenv("OCR_READINESS_TIMEOUT", raw)
    assert readiness._check_timeout() == readiness.DEFAULT_CHECK_TIMEOUT


def test_readiness_timeout_env_is_used(monkeypatch):
    monkeypatch.setenv("OCR_READINESS_TIMEOUT", "600")
    assert readiness._check_timeout() == 600


def test_readiness_module_imports_with_a_bad_timeout(monkeypatch):
    """The source graph imports this module: before the fix a typo raised at
    import and neither the API nor the worker could process a source."""
    monkeypatch.setenv("OCR_READINESS_TIMEOUT", "30m")
    try:
        assert importlib.reload(readiness).CHECK_TIMEOUT == 1800
    finally:
        monkeypatch.delenv("OCR_READINESS_TIMEOUT")
        importlib.reload(readiness)


# --- M1: RapidOCR's dictionary lives in the container layer -------------------
def test_lost_rapidocr_dictionary_makes_a_persistent_verdict_stale(
    tmp_path, monkeypatch
):
    """Persistent mode keeps the weights on the data volume, but RapidOCR's
    torch backend keeps its recognition dictionary in the package directory.
    After a container recreate that file is gone: the fingerprint must change
    so "offline ready" is not reported for a pipeline that needs a download."""
    from open_notebook.ocr import installer, paths

    persistent, package = tmp_path / "persistent", tmp_path / "package"
    persistent.mkdir()
    package.mkdir()
    (persistent / "rec.pth").write_bytes(b"w" * 10)
    (package / "ppocrv6_dict.txt").write_text("a\nb\n")
    monkeypatch.setattr(installer, "rapidocr_known_checksums", lambda: {"rec.pth": "x"})
    monkeypatch.setattr(installer, "rapidocr_package_model_dir", lambda: package)
    monkeypatch.setattr(paths, "rapidocr_dir", lambda: persistent)

    prepared = readiness._rapidocr_weights_signature(persistent=True)
    assert ["rec.pth", 10] in prepared
    assert ["package/ppocrv6_dict.txt", 4] in prepared

    (package / "ppocrv6_dict.txt").unlink()  # container recreated
    recreated = readiness._rapidocr_weights_signature(persistent=True)
    assert ["rec.pth", 10] in recreated  # the weights did survive
    assert recreated != prepared  # ... but the verdict is stale


# --- A2: a partial Docling conversion is no longer silent ---------------------
def _messages(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(docling_extract.logger, "warning", seen.append)
    return seen


def test_successful_conversion_reports_status_without_warning(monkeypatch):
    seen = _messages(monkeypatch)
    result = SimpleNamespace(status=SimpleNamespace(value="success"), errors=[])
    assert docling_extract.conversion_outcome(result, "/x/a.pdf") == {
        "conversion_status": "success",
        "conversion_errors": 0,
    }
    assert seen == []


def test_partial_conversion_is_logged_and_recorded(monkeypatch):
    seen = _messages(monkeypatch)
    result = SimpleNamespace(
        status=SimpleNamespace(value="partial_success"), errors=[object(), object()]
    )
    meta = docling_extract.conversion_outcome(result, "/uploads/scan.pdf")
    assert meta == {"conversion_status": "partial_success", "conversion_errors": 2}
    assert len(seen) == 1 and "partial_success" in seen[0] and "scan.pdf" in seen[0]
    assert "/uploads" not in seen[0]  # base name only


def test_conversion_outcome_tolerates_results_without_status(monkeypatch):
    seen = _messages(monkeypatch)
    assert docling_extract.conversion_outcome(SimpleNamespace(), "a.pdf") == {
        "conversion_status": None,
        "conversion_errors": 0,
    }
    assert seen == []


def test_conversion_status_matches_doclings_enum():
    pytest.importorskip("docling")
    from docling.datamodel.base_models import ConversionStatus

    assert ConversionStatus.SUCCESS.value == "success"
    assert ConversionStatus.PARTIAL_SUCCESS.value == "partial_success"


# --- M2: the Tesseract build argument survives `docker compose up --build` ----
@pytest.mark.parametrize(
    "compose", ["docker-compose.yml", "deploy/docker-compose.prod.yml"]
)
def test_compose_passes_the_tesseract_build_argument(compose):
    yaml = pytest.importorskip("yaml")
    service = yaml.safe_load((ROOT / compose).read_text())["services"]["open_notebook"]
    args = service["build"]["args"]
    assert args["OCR_INSTALL_TESSERACT"] == "${OCR_INSTALL_TESSERACT:-false}"
    assert "ARG OCR_INSTALL_TESSERACT=false" in (ROOT / "Dockerfile").read_text()
