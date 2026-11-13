"""Unit tests for the OCR Engine Manager (open_notebook/ocr, api/routers/ocr.py).

No network and no OCR engines are needed here; real-engine tests live in
tests/test_ocr_integration.py.
"""

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from open_notebook.ocr import catalog, installer, paths, runtime, store
from open_notebook.ocr.options import OcrSettings


@pytest.fixture(autouse=True)
def _url_ingestion_enabled(monkeypatch):
    """This module covers behaviour WITH URL ingestion switched on (URL policy,
    engine routing). The deployment default is OFF (D-29); the switched-off
    behaviour is covered by tests/test_url_ingestion_switch.py."""
    monkeypatch.setenv("OPEN_NOTEBOOK_ENABLE_URL_INGESTION", "true")


@pytest.fixture
def ocr_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_DATA_DIR", str(tmp_path / "ocr"))
    for var in (
        "OCR_MODELS_DIR",
        "OCR_PACKAGES_DIR",
        "OCR_MANIFESTS_DIR",
        "OCR_OFFLINE",
    ):
        monkeypatch.delenv(var, raising=False)
    store._hash_cache.clear()
    return tmp_path / "ocr"


def _fake_engine(monkeypatch, files):
    """Register a tiny fake engine in the catalog (test-only)."""
    spec = catalog.EngineSpec(
        id="fake",
        display_name="Fake",
        description="",
        languages=("vie",),
        docling_kind="tesseract",
        model_name="fake",
        model_version="1",
        runtime="tesseract",
        license="MIT",
        source_url="",
        files=tuple(files),
    )
    monkeypatch.setitem(catalog.ENGINES, "fake", spec)
    return spec


def _mf(rel, data: bytes, **kw):
    return catalog.ModelFile(
        rel_path=rel,
        url="https://raw.githubusercontent.com/x/y/z",
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
        **kw,
    )


# --- Catalog -----------------------------------------------------------------


class TestCatalog:
    def test_exactly_three_engines_four_choices(self):
        assert catalog.ENGINE_IDS == (
            "rapidocr",
            "tesseract_fast",
            "tesseract_best",
            "easyocr",
        )
        assert {e.runtime for e in catalog.ENGINES.values()} == {
            "builtin",
            "tesseract",
            "easyocr",
        }
        assert catalog.DEFAULT_ENGINE == "rapidocr"

    def test_vietnamese_languages(self):
        assert catalog.DOCLING_LANGS["tesseract_fast"] == ["fast/vie", "fast/eng"]
        assert catalog.DOCLING_LANGS["tesseract_best"] == ["best/vie", "best/eng"]
        assert catalog.DOCLING_LANGS["easyocr"] == ["vi", "en"]
        # RapidOCR keeps exactly what Docling's Auto passes today.
        assert catalog.DOCLING_LANGS["rapidocr"] == []

    def test_fast_and_best_are_independent_dirs_sharing_only_osd(self):
        fast = {f.rel_path for f in catalog.ENGINES["tesseract_fast"].files}
        best = {f.rel_path for f in catalog.ENGINES["tesseract_best"].files}
        assert fast & best == {"tesseract/osd.traineddata"}
        assert all(p.startswith("tesseract/fast/") for p in fast - best)
        assert all(p.startswith("tesseract/best/") for p in best - fast)

    def test_every_artifact_is_pinned_https_allowlisted(self):
        for spec in catalog.ENGINES.values():
            for f in spec.files:
                assert f.url.startswith("https://")
                assert f.url.split("/")[2] in catalog.ALLOWED_DOWNLOAD_HOSTS
                assert len(f.sha256) == 64 and int(f.sha256, 16) >= 0
                assert f.size > 0
                if f.archive_member:
                    assert f.archive_sha256 and f.archive_size

    def test_rapidocr_is_builtin_without_downloads(self):
        assert catalog.ENGINES["rapidocr"].files == ()

    def test_unknown_engine_rejected(self):
        with pytest.raises(ValueError):
            catalog.get_engine("vietocr")
        with pytest.raises(ValueError):
            catalog.get_engine("../../etc")


# --- Paths ---------------------------------------------------------------------


class TestPaths:
    def test_layout_under_data_volume(self, ocr_dir):
        assert paths.models_dir() == (ocr_dir / "models").resolve()
        assert paths.tessdata_dir() == (ocr_dir / "models" / "tesseract").resolve()

    def test_env_overrides(self, ocr_dir, monkeypatch, tmp_path):
        monkeypatch.setenv("OCR_MODELS_DIR", str(tmp_path / "m"))
        assert paths.models_dir() == (tmp_path / "m").resolve()

    @pytest.mark.parametrize("rel", ["../x", "/etc/passwd", "a/../../x", "", "a\x00b"])
    def test_safe_child_blocks_traversal(self, ocr_dir, rel):
        with pytest.raises(ValueError):
            paths.safe_child(ocr_dir, rel)

    def test_safe_child_blocks_symlink_escape(self, ocr_dir, tmp_path):
        ocr_dir.mkdir(parents=True)
        (ocr_dir / "link").symlink_to(tmp_path)
        with pytest.raises(ValueError):
            paths.safe_child(ocr_dir, "link/outside")


# --- Settings / options ----------------------------------------------------------


class TestSettings:
    def test_content_settings_defaults_preserve_behaviour(self):
        from open_notebook.domain.content_settings import ContentSettings

        fields = ContentSettings.model_fields
        assert fields["docling_ocr_engine"].default == "rapidocr"
        assert fields["docling_ocr_device"].default == "cpu"
        assert fields["docling_ocr_num_threads"].default is None
        assert fields["docling_ocr_force_full_page"].default is False
        assert fields["docling_ocr"].default is True  # unchanged

    def test_from_settings_tolerates_legacy_records(self):
        class Legacy:  # a DB record from before this feature
            docling_ocr = True

        s = OcrSettings.from_content_settings(Legacy())
        assert s == OcrSettings(
            enabled=True, engine="rapidocr", num_threads=None, force_full_page=False
        )

    def test_from_settings_rejects_unknown_engine(self):
        class Bad:
            docling_ocr_engine = "deepseek"

        assert OcrSettings.from_content_settings(Bad()).engine == "rapidocr"


class TestNativePathDecision:
    def test_default_config_keeps_content_core_path(self, monkeypatch):
        from open_notebook.ocr import docling_extract

        monkeypatch.setattr(runtime, "auto_resolves_to_rapidocr", lambda: True)
        assert docling_extract.native_path_required(OcrSettings()) is False

    def test_rapidocr_pinned_when_auto_would_switch(self, monkeypatch):
        from open_notebook.ocr import docling_extract

        # e.g. EasyOCR got installed: Auto would silently switch engines.
        monkeypatch.setattr(runtime, "auto_resolves_to_rapidocr", lambda: False)
        assert docling_extract.native_path_required(OcrSettings()) is True

    @pytest.mark.parametrize("engine", ["tesseract_fast", "tesseract_best", "easyocr"])
    def test_other_engines_use_native_path(self, engine):
        from open_notebook.ocr import docling_extract

        assert docling_extract.native_path_required(OcrSettings(engine=engine)) is True

    def test_tuning_requires_native_path(self, monkeypatch):
        from open_notebook.ocr import docling_extract

        monkeypatch.setattr(runtime, "auto_resolves_to_rapidocr", lambda: True)
        assert docling_extract.native_path_required(OcrSettings(num_threads=2)) is True
        assert (
            docling_extract.native_path_required(OcrSettings(force_full_page=True))
            is True
        )

    def test_ocr_disabled_never_native(self):
        from open_notebook.ocr import docling_extract

        assert (
            docling_extract.native_path_required(
                OcrSettings(enabled=False, engine="easyocr")
            )
            is False
        )

    def test_auto_resolution_mirrors_docling_order(self, monkeypatch):
        avail = {
            "onnxruntime": False,
            "easyocr": False,
            "nemotron_ocr": False,
            "ocrmac": False,
        }
        monkeypatch.setattr(runtime, "module_available", lambda n: avail.get(n, False))
        monkeypatch.setattr(runtime.sys, "platform", "linux")
        assert runtime.auto_resolves_to_rapidocr() is True  # rapidocr + torch
        assert runtime.rapidocr_backend() == "torch"
        avail["easyocr"] = True
        assert runtime.auto_resolves_to_rapidocr() is False  # Auto -> EasyOCR
        avail["onnxruntime"] = True
        assert runtime.auto_resolves_to_rapidocr() is True  # onnx precedes easyocr
        assert runtime.rapidocr_backend() == "onnxruntime"
        avail["nemotron_ocr"] = True
        assert runtime.auto_resolves_to_rapidocr() is False

    @pytest.mark.asyncio
    async def test_only_pdf_and_images_routed_to_docling(self, monkeypatch):
        from open_notebook.ocr import docling_extract

        async def fake_type(path):
            return {
                "a.pdf": "application/pdf",
                "a.png": "image/png",
                "a.docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }[path]

        monkeypatch.setattr(
            "content_core.content.identification.get_file_type", fake_type
        )
        monkeypatch.setattr(
            docling_extract, "_docling_routes", lambda mime, eng: eng == "docling"
        )
        ocr = OcrSettings(engine="tesseract_best")
        assert (
            await docling_extract.should_use_native_ocr("a.pdf", "docling", ocr) is True
        )
        assert (
            await docling_extract.should_use_native_ocr("a.png", "docling", ocr) is True
        )
        assert (
            await docling_extract.should_use_native_ocr("a.docx", "docling", ocr)
            is False
        )
        assert (
            await docling_extract.should_use_native_ocr("a.pdf", "simple", ocr) is False
        )


# --- Store / installer -------------------------------------------------------------


class TestModelStatus:
    def test_lifecycle_of_files(self, ocr_dir, monkeypatch):
        a, b = b"model-a", b"model-b"
        _fake_engine(monkeypatch, [_mf("fake/a.bin", a), _mf("fake/b.bin", b)])
        assert store.model_status("fake").status == "not_installed"
        target = paths.models_dir() / "fake"
        target.mkdir(parents=True)
        (target / "a.bin").write_bytes(a)
        assert store.model_status("fake").status == "partial"
        (target / "b.bin").write_bytes(b"tampered")
        assert store.model_status("fake").status == "corrupted"
        (target / "b.bin").write_bytes(b)
        ms = store.model_status("fake")
        assert ms.status == "installed" and ms.installed_bytes == len(a) + len(b)

    def test_symlinked_model_rejected(self, ocr_dir, monkeypatch, tmp_path):
        data = b"x"
        _fake_engine(monkeypatch, [_mf("fake/a.bin", data)])
        real = tmp_path / "real.bin"
        real.write_bytes(data)
        (paths.models_dir() / "fake").mkdir(parents=True)
        (paths.models_dir() / "fake" / "a.bin").symlink_to(real)
        assert store.model_status("fake").status == "corrupted"

    def test_state_roundtrip_and_stale_detection(self, ocr_dir):
        store.write_state("easyocr", {"state": store.DOWNLOADING})
        st = store.read_state("easyocr")
        assert store.job_is_active(st)
        assert not store.job_is_active(
            st, now=st["updated_at"] + store.STALE_AFTER_SECONDS + 1
        )

    def test_state_file_name_cannot_be_injected(self, ocr_dir):
        assert store.read_state("../../x") == {}
        with pytest.raises(ValueError):
            store.write_state("../../x", {"state": "ready"})
        assert not any(ocr_dir.parent.glob("*.json"))


class TestInstaller:
    def test_offline_bundle_install_without_network(self, ocr_dir, monkeypatch):
        data = b"vie-weights"
        _fake_engine(monkeypatch, [_mf("fake/vie.traineddata", data)])
        monkeypatch.setenv("OCR_OFFLINE", "true")
        bundle = paths.packages_dir() / "models" / "fake"
        bundle.mkdir(parents=True)
        (bundle / "vie.traineddata").write_bytes(data)

        def no_network(*a, **k):
            raise AssertionError("network used in offline mode")

        monkeypatch.setattr(installer, "_download", no_network)
        monkeypatch.setattr(
            installer, "smoke_check", lambda e: {"ok": True, "detail": "stub"}
        )
        result = installer.install_models("fake")
        assert result["state"] == store.INSTALLED
        assert result["sources"] == {"fake/vie.traineddata": "bundle"}
        assert store.model_status("fake").installed

    def test_offline_missing_file_fails_clearly(self, ocr_dir, monkeypatch):
        _fake_engine(monkeypatch, [_mf("fake/vie.traineddata", b"x")])
        monkeypatch.setenv("OCR_OFFLINE", "true")
        with pytest.raises(installer.InstallError, match="OCR_OFFLINE"):
            installer.install_models("fake")
        assert not store.model_status("fake").installed

    def test_tampered_bundle_never_becomes_visible(self, ocr_dir, monkeypatch):
        _fake_engine(monkeypatch, [_mf("fake/vie.traineddata", b"good")])
        bundle = paths.packages_dir() / "models" / "fake"
        bundle.mkdir(parents=True)
        (bundle / "vie.traineddata").write_bytes(b"evil")
        with pytest.raises(installer.InstallError, match="Checksum"):
            installer.install_models("fake")
        assert not (paths.models_dir() / "fake" / "vie.traineddata").exists()

    def test_download_resume_and_checksum(self, ocr_dir, monkeypatch):
        data = b"0123456789" * 10
        _fake_engine(monkeypatch, [_mf("fake/vie.traineddata", data)])
        calls = []

        def fake_download(url, part, expected, progress):
            calls.append(part.stat().st_size if part.exists() else 0)
            if len(calls) == 1:
                part.write_bytes(data[:40])  # interrupted transfer
                raise IOError("connection reset")
            with open(part, "ab") as fh:
                fh.write(data[part.stat().st_size :])

        monkeypatch.setattr(installer, "_download", fake_download)
        monkeypatch.setattr(installer.time, "sleep", lambda s: None)
        monkeypatch.setattr(
            installer, "smoke_check", lambda e: {"ok": None, "detail": "no runtime"}
        )
        installer.install_models("fake")
        assert calls == [0, 40]  # second attempt resumed from the staged bytes
        assert store.model_status("fake").installed

    def test_idempotent_no_redownload(self, ocr_dir, monkeypatch):
        data = b"weights"
        _fake_engine(monkeypatch, [_mf("fake/a.bin", data)])
        (paths.models_dir() / "fake").mkdir(parents=True)
        (paths.models_dir() / "fake" / "a.bin").write_bytes(data)
        monkeypatch.setattr(
            installer, "_download", lambda *a: pytest.fail("re-downloaded")
        )
        monkeypatch.setattr(
            installer, "smoke_check", lambda e: {"ok": True, "detail": ""}
        )
        assert installer.install_models("fake")["sources"] == {"fake/a.bin": "existing"}

    def test_smoke_failure_not_marked_ready(self, ocr_dir, monkeypatch):
        data = b"weights"
        _fake_engine(monkeypatch, [_mf("fake/a.bin", data)])
        (paths.models_dir() / "fake").mkdir(parents=True)
        (paths.models_dir() / "fake" / "a.bin").write_bytes(data)
        monkeypatch.setattr(
            installer, "smoke_check", lambda e: {"ok": False, "detail": "boom"}
        )
        with pytest.raises(installer.InstallError, match="Smoke"):
            installer.install_models("fake")
        assert store.read_state("fake").get("state") != store.INSTALLED

    def test_insufficient_disk_space(self, ocr_dir, monkeypatch):
        _fake_engine(monkeypatch, [_mf("fake/a.bin", b"x" * 10)])
        monkeypatch.setattr(
            installer.shutil, "disk_usage", lambda p: type("U", (), {"free": 1})()
        )
        with pytest.raises(installer.InstallError, match="disk space"):
            installer.install_models("fake")

    def test_duplicate_concurrent_install_blocked(self, ocr_dir, monkeypatch):
        _fake_engine(monkeypatch, [_mf("fake/a.bin", b"x")])
        with store.file_lock("install-fake"):
            with pytest.raises(store.LockBusy):
                installer.install_models("fake")

    @pytest.mark.parametrize(
        "url",
        [
            "http://raw.githubusercontent.com/a",
            "https://evil.example.com/a",
            "https://169.254.169.254/latest",
            "file:///etc/passwd",
        ],
    )
    def test_host_allowlist(self, url):
        with pytest.raises(installer.InstallError):
            installer._check_host(url)

    def test_zip_extraction_only_expected_member(self, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../evil.pth", b"x" * 4)
            zf.writestr("model.pth", b"y" * 4)
        archive = tmp_path / "a.zip"
        archive.write_bytes(buf.getvalue())
        out = tmp_path / "out.bin"
        installer._extract_member(archive, "model.pth", out, 4)
        assert out.read_bytes() == b"yyyy"
        with pytest.raises(installer.InstallError):
            installer._extract_member(archive, "../evil.pth", out, 4)
        with pytest.raises(installer.InstallError):
            installer._extract_member(archive, "model.pth", out, 3)  # size mismatch
        with pytest.raises(installer.InstallError):
            installer._extract_member(archive, "missing.pth", out, 4)


class TestDelete:
    def _install(self, engine_id):
        for f in catalog.ENGINES[engine_id].files:
            p = paths.safe_child(paths.models_dir(), f.rel_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"placeholder")

    def test_active_engine_cannot_be_removed(self, ocr_dir):
        with pytest.raises(installer.InstallError, match="in use"):
            installer.delete_models("tesseract_fast", active_engine="tesseract_fast")

    def test_builtin_cannot_be_removed(self, ocr_dir):
        with pytest.raises(installer.InstallError):
            installer.delete_models("rapidocr", active_engine="tesseract_best")

    def test_shared_osd_kept_while_other_variant_installed(self, ocr_dir, monkeypatch):
        # Real files with matching checksums are not needed: "partial" counts
        # as still installed for the sharing rule.
        monkeypatch.setattr(
            store, "model_status", lambda e: store.ModelStatus("partial", [])
        )
        self._install("tesseract_fast")
        self._install("tesseract_best")
        removed = installer.delete_models("tesseract_fast", active_engine="rapidocr")
        assert "tesseract/osd.traineddata" not in removed
        assert (paths.models_dir() / "tesseract" / "osd.traineddata").exists()
        assert (paths.models_dir() / "tesseract" / "best" / "vie.traineddata").exists()
        assert not (
            paths.models_dir() / "tesseract" / "fast" / "vie.traineddata"
        ).exists()

    def test_last_user_removes_shared_osd(self, ocr_dir, monkeypatch):
        monkeypatch.setattr(
            store, "model_status", lambda e: store.ModelStatus("not_installed", [])
        )
        self._install("tesseract_best")
        removed = installer.delete_models("tesseract_best", active_engine="rapidocr")
        assert "tesseract/osd.traineddata" in removed

    def test_delete_refused_during_install(self, ocr_dir):
        store.write_state("easyocr", {"state": store.DOWNLOADING})
        with pytest.raises(installer.InstallError, match="in progress"):
            installer.delete_models("easyocr", active_engine="rapidocr")


# --- Lifecycle status ---------------------------------------------------------------


class TestLifecycle:
    def _status(self, monkeypatch, rt_status, model_status, state=None):
        from open_notebook.ocr import status as status_mod

        monkeypatch.setattr(
            runtime,
            "probe_runtime",
            lambda e: runtime.RuntimeStatus(kind="tesseract", status=rt_status),
        )
        monkeypatch.setattr(
            store, "model_status", lambda e: store.ModelStatus(model_status, [])
        )
        if state:
            store.write_state("tesseract_best", state)
        return status_mod.engine_status("tesseract_best", "rapidocr")

    def test_ready_needs_runtime_and_model(self, ocr_dir, monkeypatch):
        assert self._status(monkeypatch, "ready", "installed")["state"] == "ready"
        assert (
            self._status(monkeypatch, "missing", "installed")["state"]
            == "not_installed"
        )
        assert (
            self._status(monkeypatch, "ready", "not_installed")["state"]
            == "not_installed"
        )

    def test_requires_restart(self, ocr_dir, monkeypatch):
        s = self._status(monkeypatch, "requires_restart", "installed")
        assert s["state"] == "requires_restart" and s["ready"] is False

    def test_incompatible(self, ocr_dir, monkeypatch):
        assert (
            self._status(monkeypatch, "incompatible", "installed")["state"]
            == "incompatible"
        )

    def test_corrupted_is_failed_with_message(self, ocr_dir, monkeypatch):
        s = self._status(monkeypatch, "ready", "corrupted")
        assert s["state"] == "failed" and s["ready"] is False

    def test_active_job_wins(self, ocr_dir, monkeypatch):
        s = self._status(
            monkeypatch, "ready", "not_installed", {"state": "downloading"}
        )
        assert s["state"] == "downloading"

    def test_dead_job_becomes_retryable_failure(self, ocr_dir, monkeypatch):
        store.write_state("tesseract_best", {"state": "downloading"})
        data = json.loads((paths.manifests_dir() / "tesseract_best.json").read_text())
        data["updated_at"] = 0
        (paths.manifests_dir() / "tesseract_best.json").write_text(json.dumps(data))
        monkeypatch.setattr(store, "write_state", lambda *a, **k: None)
        s = self._status(monkeypatch, "ready", "not_installed")
        assert s["state"] == "failed"

    def test_assert_ready_raises_value_error(self, ocr_dir, monkeypatch):
        from open_notebook.ocr.status import assert_engine_ready

        monkeypatch.setattr(
            runtime,
            "probe_runtime",
            lambda e: runtime.RuntimeStatus(
                kind="easyocr", status="missing", detail="pip"
            ),
        )
        with pytest.raises(ValueError, match="runtime is missing"):
            assert_engine_ready("easyocr")


class TestRuntimeProbes:
    def test_tessdata_prefix_set_once_and_respected(self, ocr_dir, monkeypatch):
        monkeypatch.setenv("TESSDATA_PREFIX", "")  # restored by monkeypatch afterwards
        monkeypatch.delenv("TESSDATA_PREFIX")
        ok, value = runtime.ensure_tessdata_prefix()
        assert ok and value == str(paths.tessdata_dir())
        monkeypatch.setenv("TESSDATA_PREFIX", "/somewhere/else")
        ok, detail = runtime.ensure_tessdata_prefix()
        assert not ok and "/somewhere/else" in detail

    def test_tesseract_env_does_not_mutate_process_env(self, ocr_dir, monkeypatch):
        monkeypatch.setenv("TESSDATA_PREFIX", "/x")
        env = runtime.tesseract_env()
        assert env["TESSDATA_PREFIX"] == str(paths.tessdata_dir())
        import os

        assert os.environ["TESSDATA_PREFIX"] == "/x"

    def test_missing_tesseract(self, monkeypatch):
        monkeypatch.setattr(runtime, "tesseract_cmd", lambda: None)
        st = runtime.probe_tesseract()
        assert (
            st.status == "missing"
            and st.install_env_var == "OPEN_NOTEBOOK_ENABLE_OCR_TESSERACT"
        )

    def test_old_tesseract_incompatible(self, monkeypatch):
        import subprocess

        monkeypatch.setattr(runtime, "tesseract_cmd", lambda: "/usr/bin/tesseract")
        monkeypatch.setattr(
            runtime.subprocess,
            "run",
            lambda *a, **k: subprocess.CompletedProcess(
                a, 0, b"tesseract 3.05.02\n", b""
            ),
        )
        assert runtime.probe_tesseract().status == "incompatible"

    def test_runtime_installed_after_start_requires_restart(self, ocr_dir, monkeypatch):
        monkeypatch.setattr(runtime, "module_available", lambda n: True)
        monkeypatch.setattr(runtime, "_version", lambda d: "1.7.2")
        assert runtime.probe_easyocr().status == "ready"
        runtime.write_runtime_marker("easyocr", "1.7.2")
        assert runtime.probe_easyocr().status == "requires_restart"

    def test_unsupported_easyocr_version_incompatible(self, monkeypatch):
        monkeypatch.setattr(runtime, "module_available", lambda n: True)
        monkeypatch.setattr(runtime, "_version", lambda d: "2.0.0")
        assert runtime.probe_easyocr().status == "incompatible"


# --- Worker command authorisation -------------------------------------------------------


class TestCommandNonce:
    @pytest.mark.asyncio
    async def test_install_without_matching_nonce_is_rejected(
        self, ocr_dir, monkeypatch
    ):
        from commands import ocr_commands

        monkeypatch.setattr(
            installer, "install_models", lambda e: pytest.fail("must not run")
        )
        out = await ocr_commands.ocr_install_model_command(
            ocr_commands.OcrJobInput(engine_id="tesseract_best", nonce="guess")
        )
        assert out.success is False and out.error_message == "Unauthorised job"
        store.write_state("tesseract_best", {"state": "pending", "nonce": "secret"})
        out = await ocr_commands.ocr_install_model_command(
            ocr_commands.OcrJobInput(engine_id="tesseract_best", nonce="other")
        )
        assert out.error_message == "Unauthorised job"

    @pytest.mark.asyncio
    async def test_install_with_nonce_runs_and_records_failure(
        self, ocr_dir, monkeypatch
    ):
        from commands import ocr_commands

        def boom(engine_id):
            raise installer.InstallError("Download failed after 3 attempts: offline")

        monkeypatch.setattr(installer, "install_models", boom)
        store.write_state("tesseract_best", {"state": "pending", "nonce": "secret"})
        out = await ocr_commands.ocr_install_model_command(
            ocr_commands.OcrJobInput(engine_id="tesseract_best", nonce="secret")
        )
        assert out.success is False
        st = store.read_state("tesseract_best")
        assert (
            st["state"] == "failed" and "offline" in st["error"] and st["nonce"] is None
        )

    @pytest.mark.asyncio
    async def test_test_command_requires_test_nonce(self, ocr_dir):
        from commands import ocr_commands

        out = await ocr_commands.ocr_test_engine_command(
            ocr_commands.OcrJobInput(engine_id="rapidocr", nonce="x")
        )
        assert out.error_message == "Unauthorised job"


# --- API --------------------------------------------------------------------------------


class TestOcrApi:
    @pytest.fixture
    def client(self, ocr_dir, monkeypatch):
        from fastapi.testclient import TestClient

        from api.main import app
        from open_notebook.domain.content_settings import ContentSettings

        ContentSettings.clear_instance()

        class FakeSettings:
            docling_ocr = True
            docling_ocr_engine = "rapidocr"
            docling_ocr_num_threads = None
            docling_ocr_force_full_page = False
            saved = 0

            async def update(self):
                FakeSettings.saved += 1

        fake = FakeSettings()

        async def get_settings():
            return fake

        monkeypatch.setattr("api.ocr_service._settings", get_settings)

        async def no_running_jobs():
            return 0

        monkeypatch.setattr("api.ocr_service._running_source_jobs", no_running_jobs)
        monkeypatch.setattr(
            runtime,
            "docling_info",
            lambda force=False: {
                "available": True,
                "version": "2.129.0",
                "api_compatible": True,
                "missing": [],
                "layout_model": "layout_heron",
                "table_model": "docling_tableformer (accurate)",
            },
        )
        return TestClient(app), fake

    def _rt(self, monkeypatch, status="ready"):
        monkeypatch.setattr(
            runtime,
            "probe_runtime",
            lambda e: runtime.RuntimeStatus(kind="x", status=status),
        )

    def test_list_engines_shape(self, client, monkeypatch):
        c, _ = client
        self._rt(monkeypatch)
        body = c.get("/api/ocr/engines").json()
        assert [e["id"] for e in body["engines"]] == list(catalog.ENGINE_IDS)
        assert body["general"]["layout_model"] == "layout_heron"
        assert body["general"]["ocr_device"] == "cpu"
        assert body["config"]["docling_ocr_engine"] == "rapidocr"
        assert [e["active"] for e in body["engines"]] == [True, False, False, False]

    def test_activate_refuses_not_ready_engine_and_keeps_current(
        self, client, monkeypatch
    ):
        c, fake = client
        self._rt(monkeypatch)
        r = c.post("/api/ocr/engines/tesseract_best/activate")
        assert r.status_code == 400
        assert fake.docling_ocr_engine == "rapidocr" and fake.saved == 0

    def test_activate_ready_engine(self, client, monkeypatch):
        c, fake = client
        self._rt(monkeypatch)
        monkeypatch.setattr(
            store, "model_status", lambda e: store.ModelStatus("installed", [])
        )
        r = c.post("/api/ocr/engines/tesseract_best/activate")
        assert r.status_code == 200, r.text
        assert fake.docling_ocr_engine == "tesseract_best" and fake.saved == 1

    def test_unknown_engine_404(self, client):
        c, _ = client
        assert c.get("/api/ocr/engines/vietocr").status_code == 404
        assert c.post("/api/ocr/engines/vietocr/install").status_code == 404

    def test_builtin_install_and_delete_refused(self, client):
        c, _ = client
        assert c.post("/api/ocr/engines/rapidocr/install").status_code == 400
        assert c.delete("/api/ocr/engines/rapidocr/model").status_code == 400

    def test_delete_active_model_refused(self, client, monkeypatch):
        c, fake = client
        fake.docling_ocr_engine = "easyocr"
        r = c.delete("/api/ocr/engines/easyocr/model")
        assert r.status_code == 400 and "in use" in r.json()["detail"]

    @pytest.mark.parametrize(
        "running,expected", [(2, "being processed"), (None, "Could not verify")]
    )
    def test_delete_refused_while_documents_processing(
        self, client, monkeypatch, running, expected
    ):
        c, _ = client

        async def jobs():
            return running

        monkeypatch.setattr("api.ocr_service._running_source_jobs", jobs)
        monkeypatch.setattr(
            installer, "delete_models", lambda *a: pytest.fail("must not delete")
        )
        r = c.delete("/api/ocr/engines/tesseract_best/model")
        assert r.status_code == 400 and expected in r.json()["detail"]

    def test_delete_refused_while_engine_test_pending(self, client, monkeypatch):
        c, _ = client
        store.write_state("tesseract_best", {"state": "installed", "test_nonce": "x"})
        monkeypatch.setattr(
            installer, "delete_models", lambda *a: pytest.fail("must not delete")
        )
        r = c.delete("/api/ocr/engines/tesseract_best/model")
        assert r.status_code == 400 and "test" in r.json()["detail"]

    def test_install_queues_job_with_nonce(self, client, monkeypatch):
        c, _ = client
        self._rt(monkeypatch, "missing")  # model download allowed before runtime
        submitted = {}

        async def fake_submit(command, engine_id, nonce):
            submitted.update(command=command, engine_id=engine_id, nonce=nonce)
            return "command:123"

        monkeypatch.setattr("api.ocr_service._submit", fake_submit)
        r = c.post("/api/ocr/engines/easyocr/install")
        assert r.status_code == 202 and r.json()["job_id"] == "command:123"
        st = store.read_state("easyocr")
        assert (
            st["state"] == "pending"
            and st["nonce"] == submitted["nonce"]
            and len(st["nonce"]) > 20
        )
        # Duplicate request while pending is refused (no double download).
        assert c.post("/api/ocr/engines/easyocr/install").status_code == 400

    def test_install_refused_when_runtime_incompatible(self, client, monkeypatch):
        c, _ = client
        self._rt(monkeypatch, "incompatible")
        assert c.post("/api/ocr/engines/easyocr/install").status_code == 400

    def test_job_status_only_for_ocr_jobs(self, client):
        c, _ = client
        assert c.get("/api/ocr/jobs/command:unknown").status_code == 404

    def test_config_update_validates_threads(self, client):
        c, fake = client
        assert (
            c.put("/api/ocr/config", json={"docling_ocr_num_threads": 999}).status_code
            == 422
        )
        r = c.put(
            "/api/ocr/config",
            json={"docling_ocr_num_threads": 2, "docling_ocr_force_full_page": True},
        )
        assert r.status_code == 200
        assert (
            fake.docling_ocr_num_threads == 2
            and fake.docling_ocr_force_full_page is True
        )
        r = c.put("/api/ocr/config", json={"docling_ocr_num_threads": 0})
        assert r.json()["docling_ocr_num_threads"] is None

    def test_settings_put_cannot_bypass_activation(self):
        from api.models import SettingsUpdate

        assert "docling_ocr_engine" not in SettingsUpdate.model_fields


class TestOcrApiRequiresAdmin:
    @pytest.fixture(autouse=True)
    def _auth(self, monkeypatch):
        monkeypatch.setenv("OPEN_NOTEBOOK_JWT_SECRET", "test-secret-key")
        monkeypatch.delenv("OPEN_NOTEBOOK_DISABLE_AUTH", raising=False)

    @pytest.mark.parametrize(
        "method,path",
        [
            ("get", "/api/ocr/engines"),
            ("post", "/api/ocr/engines/easyocr/install"),
            ("post", "/api/ocr/engines/easyocr/activate"),
            ("post", "/api/ocr/engines/easyocr/test"),
            ("delete", "/api/ocr/engines/easyocr/model"),
            ("put", "/api/ocr/config"),
        ],
    )
    def test_non_admin_forbidden(self, method, path):
        from fastapi.testclient import TestClient

        from api.auth import create_access_token
        from api.main import app

        c = TestClient(app)
        assert getattr(c, method)(path).status_code == 401
        token = create_access_token("user:u", "user", "user")
        r = getattr(c, method)(
            path,
            headers={"Authorization": f"Bearer {token}"},
            **({"json": {}} if method == "put" else {}),
        )
        assert r.status_code == 403


def test_docling_probe_script_is_static():
    """The subprocess probe runs a fixed script with no user input."""
    assert "{" not in runtime._DOCLING_PROBE.split("import json")[0]
    assert Path(runtime.__file__).read_text(encoding="utf-8").count("shell=True") == 0


# --- Regression tests for the independent review findings -------------------------


class TestReviewFixes:
    def _rt_ready(self, monkeypatch):
        monkeypatch.setattr(
            runtime,
            "probe_runtime",
            lambda e: runtime.RuntimeStatus(kind="tesseract", status="ready"),
        )

    def test_failed_smoke_with_verified_files_is_not_ready(self, ocr_dir, monkeypatch):
        from open_notebook.ocr import status as status_mod

        self._rt_ready(monkeypatch)
        monkeypatch.setattr(
            store, "model_status", lambda e: store.ModelStatus("installed", [])
        )
        store.write_state(
            "tesseract_best", {"state": store.FAILED, "error": "Smoke check failed"}
        )
        s = status_mod.engine_status("tesseract_best", "rapidocr")
        assert s["state"] == "failed" and s["ready"] is False

    def test_stale_job_with_files_from_other_engine_is_not_ready(
        self, ocr_dir, monkeypatch
    ):
        from open_notebook.ocr import status as status_mod

        self._rt_ready(monkeypatch)
        monkeypatch.setattr(
            store, "model_status", lambda e: store.ModelStatus("installed", [])
        )
        store.write_state("tesseract_best", {"state": store.DOWNLOADING})
        p = paths.manifests_dir() / "tesseract_best.json"
        data = json.loads(p.read_text())
        data["updated_at"] = 0
        p.write_text(json.dumps(data))
        assert (
            status_mod.engine_status("tesseract_best", "rapidocr")["state"] == "failed"
        )

    @pytest.mark.asyncio
    async def test_lock_busy_job_records_retryable_failure(self, ocr_dir, monkeypatch):
        from commands import ocr_commands

        def busy(engine_id):
            raise store.LockBusy("busy")

        monkeypatch.setattr(installer, "install_models", busy)
        store.write_state("tesseract_fast", {"state": "pending", "nonce": "n"})
        out = await ocr_commands.ocr_install_model_command(
            ocr_commands.OcrJobInput(engine_id="tesseract_fast", nonce="n")
        )
        st = store.read_state("tesseract_fast")
        assert out.success is False and st["state"] == "failed" and st["nonce"] is None

    def test_shared_lock_waits_instead_of_failing(self, ocr_dir):
        import threading
        import time

        acquired = []

        def holder():
            with store.file_lock("shared-x"):
                time.sleep(1.0)

        t = threading.Thread(target=holder)
        t.start()
        time.sleep(0.2)
        with store.file_lock("shared-x", timeout=10):
            acquired.append(True)
        t.join()
        assert acquired == [True]
        with store.file_lock("solo"):
            with pytest.raises(store.LockBusy):
                with store.file_lock("solo", timeout=0.6):
                    pass

    @pytest.mark.parametrize("other_status", ["corrupted", "partial", "installed"])
    def test_osd_kept_while_other_variant_has_any_files(
        self, ocr_dir, monkeypatch, other_status
    ):
        real = store.model_status
        monkeypatch.setattr(
            store,
            "model_status",
            lambda e: store.ModelStatus(other_status, [])
            if e == "tesseract_best"
            else real(e),
        )
        for f in catalog.ENGINES["tesseract_fast"].files:
            p = paths.safe_child(paths.models_dir(), f.rel_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x")
        removed = installer.delete_models("tesseract_fast", active_engine="rapidocr")
        assert "tesseract/osd.traineddata" not in removed

    def test_osd_kept_while_other_variant_installing(self, ocr_dir):
        for f in catalog.ENGINES["tesseract_fast"].files:
            p = paths.safe_child(paths.models_dir(), f.rel_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"x")
        store.write_state("tesseract_best", {"state": store.DOWNLOADING})
        removed = installer.delete_models("tesseract_fast", active_engine="rapidocr")
        assert "tesseract/osd.traineddata" not in removed

    @pytest.mark.asyncio
    async def test_url_scans_follow_selected_engine(self, monkeypatch):
        from open_notebook.ocr import docling_extract

        async def mime(url):
            return {"https://x/a.pdf": "application/pdf", "https://x/page": "article"}[
                url
            ]

        monkeypatch.setattr("content_core.processors.url.detect_remote_mime", mime)
        monkeypatch.setattr(docling_extract, "_docling_routes", lambda m, e: True)
        ocr = OcrSettings(engine="tesseract_best")
        assert await docling_extract.should_use_native_ocr_for_url(
            "https://x/a.pdf", "auto", ocr
        )
        assert not await docling_extract.should_use_native_ocr_for_url(
            "https://x/page", "auto", ocr
        )
        monkeypatch.setattr(runtime, "auto_resolves_to_rapidocr", lambda: True)
        # Default configuration: no HEAD request, content-core handles the URL.
        monkeypatch.setattr(
            "content_core.processors.url.detect_remote_mime",
            lambda u: pytest.fail("HEAD"),
        )
        assert not await docling_extract.should_use_native_ocr_for_url(
            "https://x/a.pdf", "auto", OcrSettings()
        )

    @pytest.mark.asyncio
    async def test_lost_job_is_reconciled_to_failed(self, ocr_dir, monkeypatch):
        from api import ocr_service

        store.write_state(
            "easyocr", {"state": store.PENDING, "job_id": "command:1", "nonce": "n"}
        )

        async def status(job_id):
            return {"status": "failed"}

        monkeypatch.setattr(ocr_service.CommandService, "get_command_status", status)
        await ocr_service._reconcile_job("easyocr")
        st = store.read_state("easyocr")
        assert st["state"] == "failed" and st["nonce"] is None

    @pytest.mark.asyncio
    async def test_running_job_not_reconciled(self, ocr_dir, monkeypatch):
        from api import ocr_service

        store.write_state(
            "easyocr", {"state": store.DOWNLOADING, "job_id": "command:1"}
        )

        async def status(job_id):
            return {"status": "running"}

        monkeypatch.setattr(ocr_service.CommandService, "get_command_status", status)
        await ocr_service._reconcile_job("easyocr")
        assert store.read_state("easyocr")["state"] == store.DOWNLOADING


class TestCpuMode:
    def test_rapidocr_default_keeps_previous_device_behaviour(self, monkeypatch):
        from open_notebook.ocr.options import build_ocr_options, describe

        monkeypatch.delenv("OCR_RAPIDOCR_FORCE_CPU", raising=False)
        pytest.importorskip("docling")
        assert build_ocr_options("rapidocr").rapidocr_params == {}
        assert describe("rapidocr")["device"].startswith("docling-auto")

    def test_rapidocr_force_cpu_is_opt_in_and_ocr_only(self, monkeypatch, ocr_dir):
        from open_notebook.ocr import docling_extract
        from open_notebook.ocr.options import (
            RAPIDOCR_CPU_PARAMS,
            build_ocr_options,
            describe,
        )

        pytest.importorskip("docling")
        monkeypatch.setenv("OCR_RAPIDOCR_FORCE_CPU", "true")
        monkeypatch.setattr(runtime, "auto_resolves_to_rapidocr", lambda: True)
        opts = build_ocr_options("rapidocr")
        assert opts.rapidocr_params == RAPIDOCR_CPU_PARAMS
        assert opts.rapidocr_params["EngineConfig.torch.use_cuda"] is False
        assert describe("rapidocr")["device"] == "cpu"
        # Needs explicit ocr_options -> the Docling layer, not content-core Auto.
        assert docling_extract.native_path_required(OcrSettings()) is True
        # Layout / TableFormer device untouched: no accelerator_options forced.
        from content_core import ContentCoreConfig

        po = docling_extract.build_pipeline_options(ContentCoreConfig(), OcrSettings())
        assert str(po.accelerator_options.device).lower().endswith("auto")

    def test_tesseract_and_easyocr_are_cpu(self):
        from open_notebook.ocr.options import describe

        for e in ("tesseract_fast", "tesseract_best", "easyocr"):
            assert describe(e)["device"] == "cpu"
