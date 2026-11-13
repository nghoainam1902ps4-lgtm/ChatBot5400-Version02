"""Online preparation / offline readiness (docs/ocr/OCR_ONLINE_PREPARATION.md)."""

import hashlib
import importlib.util
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from open_notebook.ocr import catalog, installer, paths, readiness, runtime, store


@pytest.fixture
def ocr_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_DATA_DIR", str(tmp_path / "ocr"))
    for var in (
        "OCR_MODELS_DIR",
        "OCR_PACKAGES_DIR",
        "OCR_MANIFESTS_DIR",
        "OCR_RAPIDOCR_PERSISTENT",
        "OCR_RAPIDOCR_FORCE_CPU",
    ):
        monkeypatch.delenv(var, raising=False)
    store._hash_cache.clear()
    return tmp_path / "ocr"


def _check(engine, mode, ok, fp=None):
    return {
        "mode": mode,
        "success": ok,
        "pipeline_ok": ok,
        "checked_at": time.time(),
        "fingerprint": fp if fp is not None else readiness.fingerprint(engine),
    }


class TestReadinessStates:
    @pytest.fixture(autouse=True)
    def _ready_runtime(self, monkeypatch):
        monkeypatch.setattr(
            runtime,
            "probe_tesseract",
            lambda: runtime.RuntimeStatus(
                kind="tesseract", status="ready", version="5.3.4"
            ),
        )

    def s(self, engine="tesseract_best", rt="ready", model="installed"):
        return readiness.readiness_status(engine, rt, model)

    def test_runtime_missing(self, ocr_dir):
        assert self.s(rt="missing")["state"] == readiness.RUNTIME_MISSING

    def test_incompatible(self, ocr_dir):
        assert self.s(rt="incompatible")["state"] == readiness.INCOMPATIBLE

    def test_model_missing_and_incomplete(self, ocr_dir):
        assert self.s(model="not_installed")["state"] == readiness.MODEL_MISSING
        assert self.s(model="partial")["state"] == readiness.MODEL_INCOMPLETE
        assert self.s(model="corrupted")["state"] == readiness.MODEL_INCOMPLETE

    def test_files_present_are_not_enough(self, ocr_dir):
        """Never offline-ready from checksums / files alone."""
        r = self.s()
        assert r["state"] == readiness.PIPELINE_NOT_VERIFIED and not r["pipeline_ok"]

    def test_online_check_alone_is_not_offline_ready(self, ocr_dir):
        readiness.record("tesseract_best", _check("tesseract_best", "online", True))
        r = self.s()
        assert (
            r["pipeline_ok"] is True and r["state"] == readiness.PIPELINE_NOT_VERIFIED
        )

    def test_local_only_pass_is_offline_ready_but_not_offline_verified(self, ocr_dir):
        readiness.record("tesseract_best", _check("tesseract_best", "local_only", True))
        r = self.s()
        assert r["state"] == readiness.OFFLINE_READY
        assert r["local_only_verified"] and not r["offline_verified"]

    def test_real_offline_pass_is_offline_verified(self, ocr_dir):
        readiness.record("tesseract_best", _check("tesseract_best", "offline", True))
        r = self.s()
        assert r["state"] == readiness.OFFLINE_READY and r["offline_verified"]

    def test_failed_local_check_is_not_offline_ready(self, ocr_dir):
        readiness.record(
            "tesseract_best", _check("tesseract_best", "local_only", False)
        )
        assert self.s()["state"] == readiness.NOT_OFFLINE_READY

    def test_changed_dependencies_make_verdict_stale(self, ocr_dir):
        fp = dict(readiness.fingerprint("tesseract_best"), docling="0.0.1")
        readiness.record(
            "tesseract_best", _check("tesseract_best", "local_only", True, fp)
        )
        r = self.s()
        assert r["stale"] and r["state"] == readiness.PIPELINE_NOT_VERIFIED

    def test_cleared_docling_cache_makes_verdict_stale(
        self, ocr_dir, monkeypatch, tmp_path
    ):
        from huggingface_hub import constants

        cache = tmp_path / "hub"
        snap = cache / "models--docling-project--docling-layout-heron" / "snapshots"
        (snap / "abc123").mkdir(parents=True)
        (snap / "abc123" / "model.safetensors").write_bytes(b"w")
        monkeypatch.setattr(constants, "HF_HUB_CACHE", str(cache))
        readiness.record("tesseract_best", _check("tesseract_best", "local_only", True))
        assert self.s()["state"] == readiness.OFFLINE_READY
        (snap / "abc123" / "model.safetensors").unlink()  # cache cleared
        r = self.s()
        assert r["stale"] and r["state"] == readiness.PIPELINE_NOT_VERIFIED

    def test_lost_rapidocr_weights_make_verdict_stale(
        self, ocr_dir, monkeypatch, tmp_path
    ):
        """Default RapidOCR weights live in the container layer: a recreate loses them."""
        pkg = tmp_path / "rapidocr_pkg" / "models"
        pkg.mkdir(parents=True)
        (pkg / "PP-OCRv6_det_small.pth").write_bytes(b"w")
        monkeypatch.setattr(installer, "rapidocr_package_model_dir", lambda: pkg)
        monkeypatch.setattr(
            installer,
            "rapidocr_known_checksums",
            lambda: {"PP-OCRv6_det_small.pth": "x"},
        )
        monkeypatch.setattr(runtime, "rapidocr_backend", lambda: "torch")
        readiness.record("rapidocr", _check("rapidocr", "local_only", True))
        assert self.s("rapidocr")["state"] == readiness.OFFLINE_READY
        (pkg / "PP-OCRv6_det_small.pth").unlink()  # container recreated
        r = self.s("rapidocr")
        assert r["stale"] and r["state"] == readiness.PIPELINE_NOT_VERIFIED

    def test_newer_failed_check_wins_over_older_offline_pass(self, ocr_dir):
        old_pass = dict(_check("tesseract_best", "offline", True), checked_at=100.0)
        new_fail = dict(_check("tesseract_best", "local_only", False), checked_at=200.0)
        readiness.record("tesseract_best", old_pass)
        readiness.record("tesseract_best", new_fail)
        r = self.s()
        assert r["state"] == readiness.NOT_OFFLINE_READY

    def test_pruned_docling_blobs_make_verdict_stale(
        self, ocr_dir, monkeypatch, tmp_path
    ):
        """HF snapshots are symlinks to blobs: pruning blobs leaves them dangling."""
        from huggingface_hub import constants

        cache = tmp_path / "hub"
        repo = cache / "models--docling-project--docling-models"
        blob = repo / "blobs" / "b1"
        blob.parent.mkdir(parents=True)
        blob.write_bytes(b"weights")
        snap = repo / "snapshots" / "abc"
        snap.mkdir(parents=True)
        (snap / "model.pt").symlink_to(blob)
        monkeypatch.setattr(constants, "HF_HUB_CACHE", str(cache))
        readiness.record("tesseract_best", _check("tesseract_best", "local_only", True))
        assert self.s()["state"] == readiness.OFFLINE_READY
        blob.unlink()  # cache pruned, dangling snapshot link remains
        assert self.s()["state"] == readiness.PIPELINE_NOT_VERIFIED

    def test_engine_status_exposes_readiness(self, ocr_dir, monkeypatch):
        from open_notebook.ocr import status

        monkeypatch.setattr(
            runtime,
            "probe_runtime",
            lambda e: runtime.RuntimeStatus(kind="tesseract", status="ready"),
        )
        monkeypatch.setattr(
            store, "model_status", lambda e: store.ModelStatus("installed", [])
        )
        assert (
            status.engine_status("tesseract_best", "rapidocr")["readiness"]["state"]
            == readiness.PIPELINE_NOT_VERIFIED
        )


class TestChecks:
    def test_local_only_child_env_blocks_network(self, monkeypatch):
        monkeypatch.setenv("HF_HUB_OFFLINE", "1")
        env = readiness._child_env(local_only=True)
        for var in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "http_proxy",
            "https_proxy",
            "ALL_PROXY",
        ):
            assert env[var] == readiness.DEAD_PROXY
        assert "HF_HUB_OFFLINE" not in env  # behaves like an unplugged server
        # The online child keeps the operator's proxy untouched (independent of
        # whatever proxy the test harness itself exports).
        monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
        monkeypatch.setenv("https_proxy", "http://proxy.example:3128")
        online_env = readiness._child_env(local_only=False)
        assert online_env["HTTPS_PROXY"] == "http://proxy.example:3128"
        assert online_env["https_proxy"] == "http://proxy.example:3128"

    @pytest.mark.parametrize(
        "mode,blocked", [("online", False), ("local_only", True), ("offline", True)]
    )
    def test_network_blocked_for_every_no_download_check(
        self, monkeypatch, ocr_dir, mode, blocked
    ):
        """An "offline" verdict must not rely on the Internet probe being right."""
        seen = {}

        def fake_run(cmd, env=None, **kw):
            seen["proxy"] = env.get("HTTPS_PROXY")
            return SimpleNamespace(stdout=b'{"success": false}', stderr=b"")

        monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
        monkeypatch.setattr(readiness.subprocess, "run", fake_run)
        monkeypatch.setattr(
            runtime,
            "probe_tesseract",
            lambda: runtime.RuntimeStatus(kind="tesseract", status="ready"),
        )
        readiness.run_pipeline_check("tesseract_best", mode)
        assert (seen["proxy"] == readiness.DEAD_PROXY) is blocked

    def test_pipeline_ok_requires_heron_and_tableformer_accurate(
        self, monkeypatch, ocr_dir
    ):
        def fake_run(cmd, **kw):
            return SimpleNamespace(
                stdout=b'{"success": true, "layout_model": "layout_heron", "table_model": "docling_tableformer", "table_mode": "fast"}',
                stderr=b"",
            )

        monkeypatch.setattr(readiness.subprocess, "run", fake_run)
        monkeypatch.setattr(
            runtime,
            "probe_tesseract",
            lambda: runtime.RuntimeStatus(kind="tesseract", status="ready"),
        )
        assert (
            readiness.run_pipeline_check("tesseract_best", "local_only")["pipeline_ok"]
            is False
        )

    @pytest.mark.skipif(
        importlib.util.find_spec("docling") is None, reason="needs Docling"
    )
    def test_real_local_only_child_process(self, ocr_dir):
        """Real subprocess run: without local Docling models it must NOT pass."""
        r = readiness.run_pipeline_check("rapidocr", "local_only")
        assert r["mode"] == "local_only" and "fingerprint" in r
        if not r["pipeline_ok"]:
            assert r.get("error"), r  # explained, not silent

    def test_prepare_offline_with_missing_model_fails_fast(self, ocr_dir, monkeypatch):
        monkeypatch.setattr(
            runtime,
            "probe_runtime",
            lambda e: runtime.RuntimeStatus(kind="tesseract", status="ready"),
        )
        monkeypatch.setattr("open_notebook.ocr.compat.problems", lambda *a, **k: [])
        monkeypatch.setattr(readiness, "internet_reachable", lambda timeout=5.0: False)
        monkeypatch.setattr(
            installer,
            "install_models",
            lambda e: pytest.fail("must not download offline"),
        )
        monkeypatch.setattr(
            readiness,
            "run_pipeline_check",
            lambda *a: pytest.fail("no check without models"),
        )
        out = readiness.prepare("tesseract_best")
        assert "connect to the Internet" in out["error"] and "best/vie" in out["error"]

    def test_prepare_never_installs_runtime(self, ocr_dir, monkeypatch):
        monkeypatch.setattr(
            runtime,
            "probe_runtime",
            lambda e: runtime.RuntimeStatus(
                kind="easyocr", status="missing", detail="pip"
            ),
        )
        out = readiness.prepare("easyocr")
        assert out["error"].startswith("runtime missing") and out["steps"] == {
            "runtime": "missing"
        }

    def test_prepare_online_runs_online_then_local_only(self, ocr_dir, monkeypatch):
        modes = []
        monkeypatch.setattr(
            runtime,
            "probe_runtime",
            lambda e: runtime.RuntimeStatus(kind="tesseract", status="ready"),
        )
        monkeypatch.setattr(
            runtime,
            "probe_tesseract",
            lambda: runtime.RuntimeStatus(kind="tesseract", status="ready"),
        )
        monkeypatch.setattr("open_notebook.ocr.compat.problems", lambda *a, **k: [])
        monkeypatch.setattr(readiness, "internet_reachable", lambda timeout=5.0: True)
        monkeypatch.setattr(
            store, "model_status", lambda e: store.ModelStatus("installed", [])
        )

        def fake_check(engine, mode):
            modes.append(mode)
            return _check(engine, mode, True)

        monkeypatch.setattr(readiness, "run_pipeline_check", fake_check)
        out = readiness.prepare("tesseract_best")
        assert modes == ["online", "local_only"]
        assert out["readiness"]["state"] == readiness.OFFLINE_READY

    def test_check_uses_offline_mode_when_internet_down(self, ocr_dir, monkeypatch):
        monkeypatch.setattr(readiness, "internet_reachable", lambda timeout=5.0: False)
        monkeypatch.setattr(
            readiness, "run_pipeline_check", lambda e, mode: _check(e, mode, True)
        )
        monkeypatch.setattr(
            runtime,
            "probe_tesseract",
            lambda: runtime.RuntimeStatus(kind="tesseract", status="ready"),
        )
        out = readiness.check("tesseract_fast")
        assert out["check"]["mode"] == "offline"


class TestOfflineFailureMessages:
    def test_model_download_failures_explained(self):
        class LocalEntryNotFoundError(Exception):
            pass

        class DownloadFileException(Exception):
            pass

        wrapped = RuntimeError("init failed")
        wrapped.__cause__ = ConnectionError(
            "HTTPSConnectionPool(host='huggingface.co', port=443)"
        )
        for exc in (
            LocalEntryNotFoundError("x"),
            DownloadFileException("modelscope"),
            wrapped,
        ):
            assert "Prepare models" in (readiness.explain_offline_failure(exc) or "")

    def test_ordinary_url_errors_untouched(self):
        assert (
            readiness.explain_offline_failure(
                ConnectionError("Cannot connect to host example.org")
            )
            is None
        )

    @pytest.mark.asyncio
    async def test_content_process_fails_fast_without_retry(
        self, monkeypatch, tmp_path
    ):
        from open_notebook.graphs import source as g

        class S:
            youtube_preferred_languages = None
            default_content_processing_engine_url = None
            default_content_processing_engine_doc = "docling"
            docling_ocr = True
            docling_formulas = False
            docling_vision = False

        async def gi():
            return S()

        monkeypatch.setattr(g.ContentSettings, "get_instance", gi)
        monkeypatch.setattr(
            g.ContentSettings, "clear_instance", classmethod(lambda c: None)
        )
        monkeypatch.setattr(g, "_usable_engine", lambda e, k: e)

        class MM:
            async def get_defaults(self):
                return SimpleNamespace(default_speech_to_text_model=None)

        monkeypatch.setattr(g, "ModelManager", MM)

        async def never(*a):
            return False

        monkeypatch.setattr(g, "should_use_native_ocr_for_url", never)
        boom = RuntimeError("x")
        boom.__cause__ = ConnectionError("huggingface.co unreachable")
        monkeypatch.setattr(g, "extract_content", AsyncMock(side_effect=boom))
        with pytest.raises(
            ValueError, match="Prepare models"
        ):  # ValueError => no retry
            await g.content_process({"content_state": {"content": "plain text"}})  # type: ignore[typeddict-item]


class TestRapidOcrPersistence:
    def test_default_unchanged(self, ocr_dir, monkeypatch):
        pytest.importorskip("docling")
        from open_notebook.ocr import docling_extract
        from open_notebook.ocr.options import OcrSettings, build_ocr_options

        monkeypatch.setattr(runtime, "auto_resolves_to_rapidocr", lambda: True)
        assert (
            "Global.model_root_dir" not in build_ocr_options("rapidocr").rapidocr_params
        )
        assert docling_extract.native_path_required(OcrSettings()) is False

    def test_opt_in_uses_official_model_root_dir(self, ocr_dir, monkeypatch):
        pytest.importorskip("docling")
        from open_notebook.ocr import docling_extract
        from open_notebook.ocr.options import OcrSettings, build_ocr_options

        monkeypatch.setenv("OCR_RAPIDOCR_PERSISTENT", "true")
        monkeypatch.setattr(runtime, "auto_resolves_to_rapidocr", lambda: True)
        opts = build_ocr_options("rapidocr")
        assert opts.rapidocr_params == {
            "Global.model_root_dir": str(paths.rapidocr_dir())
        }
        assert (
            opts.lang == [] and opts.backend == runtime.rapidocr_backend()
        )  # same model choice
        assert docling_extract.native_path_required(OcrSettings()) is True

    def test_import_copies_only_checksum_valid_weights(
        self, ocr_dir, monkeypatch, tmp_path
    ):
        pkg = tmp_path / "rapidocr_pkg" / "models"
        pkg.mkdir(parents=True)
        good, bad = b"good-weights", b"tampered"
        (pkg / "PP-OCRv6_det_small.pth").write_bytes(good)
        (pkg / "PP-OCRv6_rec_small.pth").write_bytes(bad)
        (pkg / "unrelated.bin").write_bytes(b"x")
        known = {
            "PP-OCRv6_det_small.pth": hashlib.sha256(good).hexdigest(),
            "PP-OCRv6_rec_small.pth": hashlib.sha256(b"expected").hexdigest(),
        }
        monkeypatch.setattr(installer, "rapidocr_package_model_dir", lambda: pkg)
        monkeypatch.setattr(installer, "rapidocr_known_checksums", lambda: known)
        out = installer.import_rapidocr_weights()
        assert out == {
            "PP-OCRv6_det_small.pth": "imported",
            "PP-OCRv6_rec_small.pth": "skipped (checksum mismatch)",
        }
        assert (paths.rapidocr_dir() / "PP-OCRv6_det_small.pth").read_bytes() == good
        assert not (paths.rapidocr_dir() / "PP-OCRv6_rec_small.pth").exists()
        assert (
            installer.import_rapidocr_weights()["PP-OCRv6_det_small.pth"] == "existing"
        )

    def test_rapidocr_checksum_list_is_rapidocrs_own(self):
        pytest.importorskip("rapidocr")
        known = installer.rapidocr_known_checksums()
        assert (
            known.get("PP-OCRv6_det_small.pth")
            == "fbdc74c97ea7b770ab22cbdc1bba01a52bdf1975efcf3442057356d622b05d54"
        )


class TestReadinessApi:
    @pytest.fixture
    def client(self, ocr_dir):
        from fastapi.testclient import TestClient

        from api.main import app

        return TestClient(app)

    @pytest.mark.parametrize(
        "action,command,prefix",
        [
            ("prepare", "ocr_prepare_engine", "prepare"),
            ("readiness-check", "ocr_check_readiness", "readiness"),
        ],
    )
    def test_queue_with_nonce_and_no_duplicates(
        self, client, monkeypatch, action, command, prefix
    ):
        seen: dict[str, str] = {}

        async def fake_submit(cmd, engine_id, nonce):
            seen.update(cmd=cmd, nonce=nonce)
            return "command:1"

        monkeypatch.setattr("api.ocr_service._submit", fake_submit)
        r = client.post(f"/api/ocr/engines/tesseract_best/{action}")
        assert r.status_code == 202 and seen["cmd"] == command
        assert store.read_state("tesseract_best")[f"{prefix}_nonce"] == seen["nonce"]
        assert (
            client.post(f"/api/ocr/engines/tesseract_best/{action}").status_code == 400
        )

    @pytest.mark.asyncio
    async def test_dead_marker_is_cleared_after_timeout(self, ocr_dir, monkeypatch):
        """Worker killed mid-check: the queue keeps saying "running" forever."""
        from api import ocr_service

        monkeypatch.setattr(
            ocr_service.CommandService,
            "get_command_status",
            AsyncMock(return_value={"status": "running"}),
        )
        store.write_state(
            "tesseract_best",
            {
                "prepare_nonce": "n",
                "prepare_job_id": "command:1",
                "prepare_queued_at": time.time(),
            },
        )
        await ocr_service._reconcile_readiness_jobs("tesseract_best")
        assert store.read_state("tesseract_best")["prepare_nonce"] == "n"  # alive
        store.update_state(
            "tesseract_best",
            prepare_queued_at=time.time()
            - ocr_service.READINESS_MARKER_STALE_SECONDS
            - 1,
        )
        await ocr_service._reconcile_readiness_jobs("tesseract_best")
        assert store.read_state("tesseract_best")["prepare_nonce"] is None

    @pytest.mark.asyncio
    async def test_prepare_download_not_failed_by_install_reconcile(
        self, ocr_dir, monkeypatch
    ):
        """prepare downloads with the previous install's job_id still recorded."""
        from api import ocr_service

        monkeypatch.setattr(
            ocr_service.CommandService,
            "get_command_status",
            AsyncMock(return_value={"status": "completed"}),
        )
        store.write_state(
            "tesseract_best",
            {
                "state": store.DOWNLOADING,
                "job_id": "command:old-install",
                "prepare_nonce": "n",
            },
        )
        await ocr_service._reconcile_job("tesseract_best")
        assert store.read_state("tesseract_best")["state"] == store.DOWNLOADING
        store.update_state("tesseract_best", prepare_nonce=None)
        await ocr_service._reconcile_job("tesseract_best")  # no prepare: crash path
        assert store.read_state("tesseract_best")["state"] == store.FAILED

    @pytest.mark.parametrize("action", ["prepare", "readiness-check"])
    def test_non_admin_forbidden(self, client, monkeypatch, action):
        from api.auth import create_access_token

        monkeypatch.setenv(
            "OPEN_NOTEBOOK_JWT_SECRET", "test-secret-key-for-readiness-tests"
        )
        monkeypatch.delenv("OPEN_NOTEBOOK_DISABLE_AUTH", raising=False)
        token = create_access_token("user:u", "u", "user")
        r = client.post(
            f"/api/ocr/engines/easyocr/{action}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_commands_require_their_own_nonce(self, ocr_dir):
        from commands import ocr_commands

        store.write_state(
            "easyocr", {"nonce": "install-nonce", "test_nonce": "test-nonce"}
        )
        for fn in (
            ocr_commands.ocr_prepare_engine_command,
            ocr_commands.ocr_check_readiness_command,
        ):
            with (
                patch.object(readiness, "prepare", side_effect=AssertionError),
                patch.object(readiness, "check", side_effect=AssertionError),
            ):
                out = await fn(
                    ocr_commands.OcrJobInput(engine_id="easyocr", nonce="install-nonce")
                )
            assert out.error_message == "Unauthorised job"

    def test_catalog_unchanged(self):
        assert catalog.ENGINE_IDS == (
            "rapidocr",
            "tesseract_fast",
            "tesseract_best",
            "easyocr",
        )
