"""Dependency compatibility guard (docs/ocr/DECISIONS.md D-14).

Locks together: uv.lock, the versions/fingerprints in open_notebook/ocr/compat.py,
the catalog's EasyOCR pin, the Docker constraints export and the entrypoint.
"""

import os
import stat
import subprocess
import tomllib
from pathlib import Path

import pytest

from open_notebook.ocr import catalog, compat, runtime
from open_notebook.ocr.options import OcrSettings

ROOT = Path(__file__).resolve().parents[1]


def _locked() -> dict[str, set[str]]:
    data = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    out: dict[str, set[str]] = {}
    for p in data["package"]:
        out.setdefault(p["name"], set()).add(p["version"])
    return out


class TestLockMatchesVerifiedSet:
    def test_uv_lock_pins_the_verified_versions(self):
        locked = _locked()
        for dist, version in compat.VERIFIED_VERSIONS.items():
            assert locked.get(dist) == {version}, dist
        for versions in compat.VERIFIED_ENGINE_VERSIONS.values():
            for dist, version in versions.items():
                assert locked.get(dist) == {version}, dist

    def test_catalog_easyocr_pin_matches_lock_and_extra(self):
        assert (
            compat.VERIFIED_ENGINE_VERSIONS["easyocr"]["easyocr"]
            == catalog.EASYOCR_VERSION
        )
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        extra = pyproject["project"]["optional-dependencies"]["ocr-easyocr"]
        assert extra == [f"easyocr=={catalog.EASYOCR_VERSION}"]

    def test_installed_environment_is_the_verified_one(self):
        pytest.importorskip("docling")
        assert compat.check_versions(compat.VERIFIED_VERSIONS) == []

    def test_fingerprints_match_installed_sources(self):
        pytest.importorskip("docling")
        assert compat.check_fingerprints(compat.CONTENT_CORE_FINGERPRINTS) == []
        assert compat.check_fingerprints(compat.DOCLING_FINGERPRINTS) == []


class TestDriftIsNeverSilent:
    @pytest.fixture(autouse=True)
    def _drift(self, monkeypatch):
        compat.reset_cache()
        monkeypatch.delenv(compat.OVERRIDE_ENV, raising=False)
        real = compat._version
        monkeypatch.setattr(
            compat, "_version", lambda d: "9.9.9" if d == "content-core" else real(d)
        )
        yield
        compat.reset_cache()

    def test_ensure_compatible_raises(self):
        with pytest.raises(ValueError, match="content-core 9.9.9"):
            compat.ensure_compatible("tesseract_best")

    def test_override_is_explicit(self, monkeypatch):
        monkeypatch.setenv(compat.OVERRIDE_ENV, "true")
        compat.ensure_compatible("tesseract_best")

    def test_selected_engine_reported_incompatible(self, monkeypatch, tmp_path):
        from open_notebook.ocr import status, store

        monkeypatch.setenv("OCR_DATA_DIR", str(tmp_path))
        monkeypatch.setattr(
            runtime,
            "probe_runtime",
            lambda e: runtime.RuntimeStatus(kind="x", status="ready"),
        )
        monkeypatch.setattr(
            store, "model_status", lambda e: store.ModelStatus("installed", [])
        )
        s = status.engine_status("tesseract_best", "rapidocr")
        assert s["state"] == "incompatible" and s["ready"] is False
        assert "content-core 9.9.9" in s["error"]
        # The default engine stays usable (content-core path), with a warning.
        r = status.engine_status("rapidocr", "rapidocr")
        assert r["state"] == "ready" and "content-core" in (r["error"] or "")

    def test_default_path_not_pinned_on_unverified_deps(self, monkeypatch):
        from open_notebook.ocr import docling_extract

        monkeypatch.setattr(runtime, "auto_resolves_to_rapidocr", lambda: False)
        assert docling_extract.native_path_required(OcrSettings()) is False

    def test_docling_fingerprint_problem_from_probe_blocks(self, monkeypatch, tmp_path):
        from open_notebook.ocr import status, store

        compat.reset_cache()
        monkeypatch.setattr(
            compat, "_version", lambda d: compat.VERIFIED_VERSIONS.get(d, "1.7.2")
        )
        monkeypatch.setenv("OCR_DATA_DIR", str(tmp_path))
        monkeypatch.setattr(
            runtime,
            "probe_runtime",
            lambda e: runtime.RuntimeStatus(kind="x", status="ready"),
        )
        monkeypatch.setattr(
            store, "model_status", lambda e: store.ModelStatus("installed", [])
        )
        s = status.engine_status(
            "tesseract_fast", "rapidocr", ["auto_ocr_model changed"]
        )
        assert s["state"] == "incompatible"


class TestFreshBuildUsesLockedVersions:
    def test_dockerfile_exports_lock_constraints(self):
        df = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "uv export --frozen --no-dev --extra docling --extra ocr-easyocr" in df
        assert "COPY --from=backend-builder /app/runtime-constraints.txt" in df
        assert "OPEN_NOTEBOOK_RUNTIME_CONSTRAINTS=/app/runtime-constraints.txt" in df

    def test_constraints_export_contains_verified_pins(self, tmp_path):
        uv = __import__("shutil").which("uv")
        if not uv:
            pytest.skip("uv not available")
        out = tmp_path / "c.txt"
        subprocess.run(
            [
                uv,
                "export",
                "--frozen",
                "--no-dev",
                "--extra",
                "docling",
                "--extra",
                "ocr-easyocr",
                "--no-hashes",
                "--no-emit-project",
                "--no-header",
                "--no-annotate",
                "-o",
                str(out),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        lines = {line.split(";")[0].strip() for line in out.read_text().splitlines()}
        assert "docling==2.129.0" in lines and "content-core==2.0.7" in lines
        assert "rapidocr==3.9.2" in lines and "easyocr==1.7.2" in lines

    def test_entrypoint_installs_docling_with_constraints_and_keeps_cmd(self, tmp_path):
        """Run the real entrypoint with stub uv/python: -c is passed, CMD still exec'd."""
        script = (ROOT / "scripts" / "docker-entrypoint.sh").read_text(encoding="utf-8")
        fake_py = tmp_path / "python"
        fake_py.write_text(
            "#!/bin/sh\n"
            'case "$*" in *find_spec*) exit 1 ;; *metadata*) echo 2.0.7 ;; esac\n'
        )
        fake_uv = tmp_path / "uv"
        log = tmp_path / "uv.log"
        fake_uv.write_text(f'#!/bin/sh\necho "$@" >> {log}\nexit 0\n')
        for f in (fake_py, fake_uv):
            f.chmod(f.stat().st_mode | stat.S_IEXEC)
        patched = script.replace(
            'VENV_PY="/app/.venv/bin/python"', f'VENV_PY="{fake_py}"'
        )
        ep = tmp_path / "entrypoint.sh"
        ep.write_text(patched)
        constraints = tmp_path / "constraints.txt"
        constraints.write_text("docling==2.129.0\n")
        env = dict(
            os.environ,
            PATH=f"{tmp_path}:{os.environ['PATH']}",
            OPEN_NOTEBOOK_ENABLE_DOCLING="true",
            OPEN_NOTEBOOK_RUNTIME_CONSTRAINTS=str(constraints),
            UV_CACHE_DIR=str(tmp_path / "c1"),
            PLAYWRIGHT_BROWSERS_PATH=str(tmp_path / "c2"),
            HF_HOME=str(tmp_path / "c3"),
        )
        env.pop("OPEN_NOTEBOOK_ENABLE_OCR_TESSERACT", None)
        env.pop("OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR", None)
        proc = subprocess.run(
            ["sh", str(ep), "echo", "CMD-RAN", "with-args"],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        assert "CMD-RAN with-args" in proc.stdout  # exec "$@" intact
        calls = log.read_text()
        assert f"-c {constraints} content-core[docling]==2.0.7" in calls
