"""Custom Tesseract model manager (Phase 10): versions, manifests, activation.

Unit tests use a tiny synthetic ``.traineddata`` and a stubbed Tesseract, so
they run anywhere. ``TestRealTesseract`` exercises the real executable and a
real LSTM model when one is available (``OCR_TEST_REAL_TRAINEDDATA``).
"""

import hashlib
import json
import os
import shutil
import struct
import time
from pathlib import Path

import pytest

from open_notebook.ocr import (
    catalog,
    custom_models,
    installer,
    options,
    paths,
    readiness,
    runtime,
    store,
)
from open_notebook.ocr.options import OcrSettings
from open_notebook.ocr.status import assert_engine_ready, engine_status

ENGINE = "tesseract_agri"

# SHA-256 of the OFFICIAL model files (tessdata 4.1.0 / EasyOCR releases) as
# shipped in v1.1.0-rc.1. Adding a custom engine must never change them.
OFFICIAL_SHA256 = {
    "tesseract/osd.traineddata": "9cf5d576fcc47564f11265841e5ca839001e7e6f38ff7f7aacf46d15a96b00ff",
    "tesseract/fast/vie.traineddata": "79df64caf7bcfb2a27df5042ecb6121e196eada34da774956995747636d5bfa1",
    "tesseract/fast/eng.traineddata": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
    "tesseract/best/vie.traineddata": "b6b49293d95d0b6dbd8780174627e82c75be957b6f4ed9862155540d6b00bb45",
    "tesseract/best/eng.traineddata": "8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba",
    "easyocr/craft_mlt_25k.pth": "4a5efbfb48b4081100544e75e1e2b57f8de3d84f213004b14b85fd4b3748db17",
    "easyocr/latin_g2.pth": "aaa95be1c4a9cb3496879bed7c520886ce1164f89e026f0c54488394e74e8c55",
}


# The parameter file of the official Vietnamese model (tessdata_best 4.1.0).
OFFICIAL_CONFIG = b"language_model_ngram_on\t1\nclassify_misfit_junk_penalty 0.125\n"


def fake_traineddata(
    seed: bytes = b"a", lstm: bool = True, config: bytes | None = OFFICIAL_CONFIG
) -> bytes:
    """A structurally valid traineddata file (component table + payloads).

    ``config`` is the embedded parameter file (component 0); None = absent.
    """
    parts: dict[int, bytes] = {}
    if config is not None:
        parts[0] = b"# test model " + seed + b"\n" + config
    if lstm:
        parts.update(
            {
                17: (b"LSTM" + seed) * 1500,
                21: b"unicharset " + seed,
                22: b"recoder " + seed,
            }
        )
    else:
        parts[1] = (b"legacy-unicharset" + seed) * 400
    parts[23] = b"4.00.00alpha:vie:test"
    count = 24
    offsets = [-1] * count
    body = b""
    pos = 4 + 8 * count
    for index in sorted(parts):
        offsets[index] = pos
        body += parts[index]
        pos += len(parts[index])
    return struct.pack("<i", count) + struct.pack(f"<{count}q", *offsets) + body


@pytest.fixture
def ocr_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_DATA_DIR", str(tmp_path / "ocr"))
    for var in (
        "OCR_MODELS_DIR",
        "OCR_PACKAGES_DIR",
        "OCR_MANIFESTS_DIR",
        "OCR_OFFLINE",
        "OCR_AGRI_WITH_ENGLISH",
        "TESSDATA_PREFIX",
    ):
        monkeypatch.delenv(var, raising=False)
    store._hash_cache.clear()
    return tmp_path / "ocr"


@pytest.fixture
def fake_tesseract(monkeypatch):
    """Tesseract present; the smoke test accepts every file unless told otherwise."""
    state = {"ok": True, "calls": []}

    def smoke(tessdata, lang, extra_langs=None):
        state["calls"].append((str(tessdata), lang))
        return {
            "ok": state["ok"],
            "langs": [lang, *(extra_langs or [])],
            "checked_at": time.time(),
            "tesseract_version": "5.5.0",
            "cer": 0.01 if state["ok"] else 0.9,
            "chars": 190,
            "detail": "stub ok" if state["ok"] else "stub: model misreads the sample",
        }

    monkeypatch.setattr(runtime, "tesseract_cmd", lambda: "/usr/bin/tesseract")
    monkeypatch.setattr(custom_models, "tesseract_smoke", smoke)
    monkeypatch.setattr(
        runtime,
        "probe_tesseract",
        lambda: runtime.RuntimeStatus(
            kind="tesseract", status=runtime.RUNTIME_READY, version="5.5.0"
        ),
    )
    monkeypatch.setattr(
        runtime,
        "probe_runtime",
        lambda e: runtime.RuntimeStatus(
            kind="tesseract", status=runtime.RUNTIME_READY, version="5.5.0"
        ),
    )
    return state


def _source(tmp_path, seed: bytes = b"a", name: str = "vie_agri.traineddata") -> Path:
    src = tmp_path / f"src-{seed.decode()}" / name
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(fake_traineddata(seed))
    return src


def _install_osd(monkeypatch, data: bytes = b"osd-bytes"):
    """Make the official prerequisite (osd) verify without downloading it."""
    target = paths.models_dir() / "tesseract" / "osd.traineddata"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    spec = catalog.get_engine(ENGINE)
    osd = catalog.ModelFile(
        rel_path="tesseract/osd.traineddata",
        url="https://raw.githubusercontent.com/x/y/osd",
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
        shared=True,
    )
    import dataclasses

    monkeypatch.setitem(
        catalog.ENGINES, ENGINE, dataclasses.replace(spec, files=(osd,))
    )


# --- Catalog ----------------------------------------------------------------------


class TestCatalog:
    def test_four_official_choices_unchanged_plus_one_custom(self):
        assert catalog.ENGINE_IDS == (
            "rapidocr",
            "tesseract_fast",
            "tesseract_best",
            "easyocr",
        )
        assert catalog.CUSTOM_ENGINE_IDS == (ENGINE,)
        assert catalog.ALL_ENGINE_IDS == catalog.ENGINE_IDS + (ENGINE,)
        assert set(catalog.ENGINES) == set(catalog.ALL_ENGINE_IDS)
        assert catalog.DEFAULT_ENGINE == "rapidocr"

    def test_official_checksums_unchanged(self):
        pinned = {
            f.rel_path: f.sha256
            for e in catalog.ENGINE_IDS
            for f in catalog.get_engine(e).files
        }
        assert pinned == OFFICIAL_SHA256

    def test_agri_spec(self):
        spec = catalog.get_engine(ENGINE)
        assert spec.display_name == "Tesseract Vietnamese Agri"
        assert spec.docling_kind == "tesseract" and spec.runtime == "tesseract"
        assert spec.quality == "experimental"
        assert spec.custom is not None
        assert spec.custom.filename == "vie_agri.traineddata"
        # Only the shared, official orientation data is pinned for this engine.
        assert [f.rel_path for f in spec.files] == ["tesseract/osd.traineddata"]
        assert all(f.shared for f in spec.files)

    def test_no_custom_checksum_or_url_in_source(self):
        """The custom model's hash is never hard-coded and it has no download URL."""
        spec = catalog.get_engine(ENGINE)
        assert not any("agri" in f.rel_path or "agri" in f.url for f in spec.files)
        assert ENGINE not in catalog.DOCLING_LANGS
        for other in catalog.ENGINE_IDS:
            assert catalog.get_engine(other).custom is None
        src = Path(custom_models.__file__).read_text(encoding="utf-8")
        assert "http://" not in src and "https://" not in src
        assert "httpx" not in src and "urllib" not in src and "requests" not in src

    def test_official_languages_unchanged(self):
        assert options.engine_langs("tesseract_fast") == ["fast/vie", "fast/eng"]
        assert options.engine_langs("tesseract_best") == ["best/vie", "best/eng"]
        assert options.engine_langs("easyocr") == ["vi", "en"]
        assert options.engine_langs("rapidocr") == []

    def test_content_settings_accepts_the_engine(self):
        from open_notebook.domain.content_settings import ContentSettings

        field = ContentSettings.model_fields["docling_ocr_engine"]
        assert ENGINE in str(field.annotation)
        assert field.default == "rapidocr"


# --- Version ids and paths ------------------------------------------------------------


class TestNames:
    @pytest.mark.parametrize(
        "bad",
        [
            "",
            ".",
            "..",
            "../v1",
            "v1/../v2",
            "v1/x",
            "/etc",
            "v 1",
            "v1.0",
            "v1+eng",
            "-v1",
            "_v1",
            "v1\x00",
            "v1\n",
            "a" * 33,
            None,
            1,
        ],
    )
    def test_invalid_version_ids(self, bad, ocr_dir):
        with pytest.raises(custom_models.CustomModelError):
            custom_models.validate_version(bad)
        with pytest.raises(custom_models.CustomModelError):
            custom_models.model_path(ENGINE, bad)

    @pytest.mark.parametrize("good", ["v1", "v2", "2026-11-16", "agri_v3", "V10a"])
    def test_valid_version_ids(self, good, ocr_dir):
        assert custom_models.validate_version(good) == good
        path = custom_models.model_path(ENGINE, good)
        assert path == (
            paths.models_dir()
            / "tesseract"
            / "custom"
            / "agri"
            / good
            / "vie_agri.traineddata"
        )
        assert custom_models.lang_code(ENGINE, good) == f"custom/agri/{good}/vie_agri"

    def test_language_is_accepted_by_docling_sanitiser(self, ocr_dir):
        import re

        # docling 2.129 tesseract_ocr_cli_model._VALID_LANG_RE
        valid = re.compile(r"^[a-zA-Z0-9_/][a-zA-Z0-9_/+-]*$")
        for version in ("v1", "2026-11-16", "agri_v3"):
            assert valid.match(custom_models.lang_code(ENGINE, version))

    def test_not_a_custom_engine(self, ocr_dir):
        with pytest.raises(custom_models.CustomModelError):
            custom_models.spec_for("tesseract_best")
        with pytest.raises(ValueError):
            custom_models.spec_for("vietocr")
        assert custom_models.active_version("tesseract_best") is None


# --- traineddata structure ---------------------------------------------------------------


class TestInspect:
    def test_valid(self, tmp_path):
        p = tmp_path / "m.traineddata"
        p.write_bytes(fake_traineddata())
        info = custom_models.inspect_traineddata(p)
        assert {c["name"] for c in info["components"]} >= {
            "lstm",
            "lstm-unicharset",
            "lstm-recoder",
        }
        assert info["version_string"] == "4.00.00alpha:vie:test"
        assert sum(c["size"] for c in info["components"]) == p.stat().st_size - 196

    @pytest.mark.parametrize(
        "data",
        [
            b"hello world, this is not a model",
            os.urandom(8192),
            fake_traineddata()[:150],
            fake_traineddata()[:400],
            fake_traineddata(lstm=False),
            struct.pack("<i", 24) + struct.pack("<24q", *([-1] * 24)) + b"x" * 500,
        ],
    )
    def test_rejected(self, tmp_path, data):
        p = tmp_path / "m.traineddata"
        p.write_bytes(data)
        with pytest.raises(custom_models.CustomModelError):
            custom_models.inspect_traineddata(p)


# --- Import -----------------------------------------------------------------------------


class TestImport:
    def test_import_stores_an_inactive_verified_version(
        self, ocr_dir, tmp_path, fake_tesseract
    ):
        src = _source(tmp_path)
        before = (src.read_bytes(), src.stat().st_mtime_ns)
        manifest = custom_models.import_model(ENGINE, src, "v1", notes=" first  run ")
        stored = custom_models.model_path(ENGINE, "v1")
        assert stored.read_bytes() == before[0]
        assert manifest["sha256"] == hashlib.sha256(before[0]).hexdigest()
        assert manifest["size"] == len(before[0])
        assert manifest["version"] == "v1" and manifest["notes"] == "first run"
        assert manifest["verification"]["status"] == "verified"
        assert manifest["smoke"]["ok"] is True
        assert manifest["imported_at_iso"].endswith("Z")
        assert manifest["rel_path"] == "tesseract/custom/agri/v1/vie_agri.traineddata"
        # Never activated by an import; the source file is untouched.
        assert custom_models.active_version(ENGINE) is None
        assert (src.read_bytes(), src.stat().st_mtime_ns) == before
        # Stored read-only; staging removed; manifest on disk.
        assert stored.stat().st_mode & 0o222 == 0
        assert not any((paths.downloads_dir() / "custom-staging").iterdir())
        on_disk = json.loads(
            (
                paths.manifests_dir() / "custom" / "agri" / "versions" / "v1.json"
            ).read_text()
        )
        assert on_disk["sha256"] == manifest["sha256"]

    def test_smoke_runs_in_staging_outside_tessdata(
        self, ocr_dir, tmp_path, fake_tesseract
    ):
        custom_models.import_model(ENGINE, _source(tmp_path), "v1")
        tessdata, lang = fake_tesseract["calls"][0]
        assert lang == "vie_agri"
        assert str(paths.tessdata_dir()) not in tessdata
        assert tessdata.startswith(str(paths.downloads_dir()))

    def test_versions_are_immutable(self, ocr_dir, tmp_path, fake_tesseract):
        custom_models.import_model(ENGINE, _source(tmp_path, b"a"), "v1")
        first = custom_models.model_path(ENGINE, "v1").read_bytes()
        with pytest.raises(custom_models.CustomModelError, match="already exists"):
            custom_models.import_model(ENGINE, _source(tmp_path, b"b"), "v1")
        assert custom_models.model_path(ENGINE, "v1").read_bytes() == first

    def test_rejected_file_leaves_everything_untouched(
        self, ocr_dir, tmp_path, fake_tesseract
    ):
        custom_models.import_model(ENGINE, _source(tmp_path, b"a"), "v1")
        custom_models.activate_version(ENGINE, "v1")
        v1 = custom_models.model_path(ENGINE, "v1").read_bytes()
        registry = custom_models.read_registry(ENGINE)

        bad = tmp_path / "bad" / "vie_agri.traineddata"
        bad.parent.mkdir()
        bad.write_bytes(os.urandom(9000))
        with pytest.raises(custom_models.CustomModelError):
            custom_models.import_model(ENGINE, bad, "v2")
        # A structurally valid file that Tesseract refuses / misreads.
        fake_tesseract["ok"] = False
        with pytest.raises(custom_models.CustomModelError, match="rejected"):
            custom_models.import_model(ENGINE, _source(tmp_path, b"c"), "v3")

        assert [m["version"] for m in custom_models.list_versions(ENGINE)] == ["v1"]
        assert custom_models.model_path(ENGINE, "v1").read_bytes() == v1
        assert custom_models.read_registry(ENGINE) == registry
        root = paths.tessdata_dir() / "custom" / "agri"
        assert sorted(p.name for p in root.iterdir()) == ["v1"]
        assert not any((paths.downloads_dir() / "custom-staging").iterdir())

    @pytest.mark.parametrize(
        "make",
        ["symlink", "wrong_ext", "tiny", "directory", "missing", "url"],
    )
    def test_source_checks(self, ocr_dir, tmp_path, fake_tesseract, make):
        real = _source(tmp_path)
        if make == "symlink":
            src = tmp_path / "link.traineddata"
            src.symlink_to(real)
        elif make == "wrong_ext":
            src = tmp_path / "model.bin"
            shutil.copyfile(real, src)
        elif make == "tiny":
            src = tmp_path / "tiny.traineddata"
            src.write_bytes(b"x" * 10)
        elif make == "directory":
            src = tmp_path / "dir.traineddata"
            src.mkdir()
        elif make == "missing":
            src = tmp_path / "nope.traineddata"
        else:
            src = "https://example.com/vie_agri.traineddata"
        with pytest.raises(custom_models.CustomModelError):
            custom_models.import_model(ENGINE, src, "v1")
        assert custom_models.list_versions(ENGINE) == []
        assert not (paths.tessdata_dir() / "custom" / "agri" / "v1").exists()

    def test_too_large(self, ocr_dir, tmp_path, fake_tesseract, monkeypatch):
        import dataclasses

        spec = catalog.get_engine(ENGINE)
        small = dataclasses.replace(spec.custom, max_size=5000)
        monkeypatch.setitem(
            catalog.ENGINES, ENGINE, dataclasses.replace(spec, custom=small)
        )
        with pytest.raises(custom_models.CustomModelError, match="larger"):
            custom_models.import_model(ENGINE, _source(tmp_path), "v1")

    def test_requires_tesseract(self, ocr_dir, tmp_path, monkeypatch):
        monkeypatch.setattr(runtime, "tesseract_cmd", lambda: None)
        with pytest.raises(custom_models.CustomModelError, match="Tesseract runtime"):
            custom_models.import_model(ENGINE, _source(tmp_path), "v1")
        assert custom_models.list_versions(ENGINE) == []

    def test_never_writes_outside_its_own_directory(
        self, ocr_dir, tmp_path, fake_tesseract
    ):
        best = paths.tessdata_dir() / "best" / "vie.traineddata"
        best.parent.mkdir(parents=True)
        best.write_bytes(b"official-best")
        custom_models.import_model(ENGINE, _source(tmp_path), "v1")
        custom_models.activate_version(ENGINE, "v1")
        assert best.read_bytes() == b"official-best"
        files = sorted(
            p.relative_to(paths.tessdata_dir()).as_posix()
            for p in paths.tessdata_dir().rglob("*")
            if p.is_file() and p.suffix == ".traineddata"
        )
        assert files == ["best/vie.traineddata", "custom/agri/v1/vie_agri.traineddata"]

    def test_symlinked_version_directory_is_refused(
        self, ocr_dir, tmp_path, fake_tesseract
    ):
        outside = tmp_path / "outside"
        outside.mkdir()
        root = paths.tessdata_dir() / "custom" / "agri"
        root.mkdir(parents=True)
        (root / "v1").symlink_to(outside)
        with pytest.raises(custom_models.CustomModelError):
            custom_models.import_model(ENGINE, _source(tmp_path), "v1")
        assert list(outside.iterdir()) == []

    def test_leftover_directory_of_an_interrupted_import_is_reused(
        self, ocr_dir, tmp_path, fake_tesseract
    ):
        vdir = paths.tessdata_dir() / "custom" / "agri" / "v1"
        vdir.mkdir(parents=True)
        (vdir / "vie_agri.traineddata").write_bytes(b"half written")
        manifest = custom_models.import_model(ENGINE, _source(tmp_path), "v1")
        assert custom_models.check_version(ENGINE, "v1", deep=True).verified
        assert manifest["size"] > 1000

    def test_duplicate_content_is_flagged(self, ocr_dir, tmp_path, fake_tesseract):
        custom_models.import_model(ENGINE, _source(tmp_path, b"a"), "v1")
        manifest = custom_models.import_model(ENGINE, _source(tmp_path, b"a"), "v2")
        assert manifest["duplicate_of"] == ["v1"]


# --- Activation, rollback, verification ----------------------------------------------------


@pytest.fixture
def two_versions(ocr_dir, tmp_path, fake_tesseract, monkeypatch):
    _install_osd(monkeypatch)
    custom_models.import_model(ENGINE, _source(tmp_path, b"a"), "v1")
    custom_models.import_model(ENGINE, _source(tmp_path, b"b"), "v2")
    return fake_tesseract


class TestActivation:
    def test_activate_then_rollback(self, two_versions):
        assert custom_models.active_version(ENGINE) is None
        custom_models.activate_version(ENGINE, "v1")
        assert custom_models.active_version(ENGINE) == "v1"
        registry = custom_models.activate_version(ENGINE, "v2", actor="admin:alice")
        assert registry["active_version"] == "v2"
        assert registry["previous_version"] == "v1"
        assert registry["history"][-1]["by"] == "admin:alice"
        assert registry["history"][-1]["action"] == "activate"
        back = custom_models.rollback(ENGINE)
        assert back["active_version"] == "v1" and back["previous_version"] == "v2"
        assert back["history"][-1]["action"] == "rollback"
        # Rolling back again returns to v2 (the version we just left).
        assert custom_models.rollback(ENGINE)["active_version"] == "v2"

    def test_reactivating_the_active_version_changes_nothing(self, two_versions):
        custom_models.activate_version(ENGINE, "v1")
        custom_models.activate_version(ENGINE, "v2")
        before = custom_models.read_registry(ENGINE)
        assert custom_models.activate_version(ENGINE, "v2") == before

    def test_unknown_version(self, two_versions):
        with pytest.raises(custom_models.CustomModelError, match="Unknown version"):
            custom_models.activate_version(ENGINE, "v9")

    def test_rollback_without_history(self, two_versions):
        with pytest.raises(custom_models.CustomModelError, match="no earlier"):
            custom_models.rollback(ENGINE)
        custom_models.activate_version(ENGINE, "v1")
        with pytest.raises(custom_models.CustomModelError, match="no earlier"):
            custom_models.rollback(ENGINE)

    def test_modified_file_cannot_be_activated(self, two_versions):
        custom_models.activate_version(ENGINE, "v1")
        target = custom_models.model_path(ENGINE, "v2")
        os.chmod(target, 0o644)
        data = bytearray(target.read_bytes())
        data[300] ^= 0xFF  # same size, different content
        target.write_bytes(bytes(data))
        with pytest.raises(custom_models.CustomModelError, match="verification"):
            custom_models.activate_version(ENGINE, "v2")
        assert custom_models.active_version(ENGINE) == "v1"
        assert (
            custom_models.read_version(ENGINE, "v2")["verification"]["status"]
            == "corrupted"
        )

    def test_rollback_target_must_still_verify(self, two_versions):
        custom_models.activate_version(ENGINE, "v1")
        custom_models.activate_version(ENGINE, "v2")
        custom_models.model_path(ENGINE, "v1").unlink()
        with pytest.raises(custom_models.CustomModelError):
            custom_models.rollback(ENGINE)
        assert custom_models.active_version(ENGINE) == "v2"

    def test_history_is_bounded(self, two_versions):
        for i in range(custom_models.HISTORY_LIMIT + 6):
            custom_models.activate_version(ENGINE, "v1" if i % 2 == 0 else "v2")
        assert (
            len(custom_models.read_registry(ENGINE)["history"])
            == custom_models.HISTORY_LIMIT
        )


class TestRemove:
    def test_inactive_version_is_removed_with_its_manifest(self, two_versions):
        custom_models.activate_version(ENGINE, "v1")
        custom_models.activate_version(ENGINE, "v2")
        registry = custom_models.remove_version(ENGINE, "v1")
        assert registry["active_version"] == "v2"
        assert registry["previous_version"] is None  # it was the rollback target
        assert registry["history"][-1]["action"] == "remove"
        assert [m["version"] for m in custom_models.list_versions(ENGINE)] == ["v2"]
        assert not (paths.tessdata_dir() / "custom" / "agri" / "v1").exists()
        assert custom_models.check_version(ENGINE, "v2", deep=True).verified
        with pytest.raises(custom_models.CustomModelError, match="no earlier"):
            custom_models.rollback(ENGINE)
        # The id is free again.
        assert custom_models.read_version(ENGINE, "v1") is None

    def test_active_version_cannot_be_removed(self, two_versions):
        custom_models.activate_version(ENGINE, "v1")
        with pytest.raises(custom_models.CustomModelError, match="is active"):
            custom_models.remove_version(ENGINE, "v1")
        assert custom_models.model_path(ENGINE, "v1").is_file()

    def test_unknown_version(self, two_versions):
        with pytest.raises(custom_models.CustomModelError, match="Unknown version"):
            custom_models.remove_version(ENGINE, "v9")

    def test_symlinked_directory_is_unlinked_not_followed(self, two_versions, tmp_path):
        custom_models.activate_version(ENGINE, "v1")
        vdir = custom_models.model_path(ENGINE, "v2").parent
        outside = tmp_path / "outside"
        shutil.copytree(vdir, outside)
        shutil.rmtree(vdir)
        vdir.symlink_to(outside)
        custom_models.remove_version(ENGINE, "v2")
        assert not vdir.exists() and not vdir.is_symlink()
        assert (outside / "vie_agri.traineddata").is_file()

    def test_cli_refuses_while_jobs_run_or_db_is_unknown(
        self, two_versions, capsys, monkeypatch
    ):
        from open_notebook.ocr import cli

        custom_models.activate_version(ENGINE, "v1")
        for running in (2, None):
            monkeypatch.setattr(cli, "_running_ocr_jobs", lambda r=running: r)
            assert cli.main(["custom", "remove", "--version", "v2"]) == 1
            assert "ERROR:" in capsys.readouterr().out
            assert custom_models.read_version(ENGINE, "v2") is not None
        monkeypatch.setattr(cli, "_running_ocr_jobs", lambda: 0)
        assert cli.main(["custom", "remove", "--version", "v1"]) == 1  # active
        assert cli.main(["custom", "remove", "--version", "v2"]) == 0
        assert custom_models.read_version(ENGINE, "v2") is None


class TestTamperDetection:
    def test_engine_ready_then_failed_when_the_active_file_changes(self, two_versions):
        custom_models.activate_version(ENGINE, "v1")
        assert store.model_status(ENGINE).status == "installed"
        assert engine_status(ENGINE)["state"] == store.READY
        assert_engine_ready_no_compat(ENGINE, "v1")

        target = custom_models.model_path(ENGINE, "v1")
        os.chmod(target, 0o644)
        target.write_bytes(target.read_bytes() + b"appended")
        ms = store.model_status(ENGINE)
        assert ms.status == "corrupted"
        st = engine_status(ENGINE)
        assert st["state"] == store.FAILED and not st["ready"]
        assert "roll back" in st["error"]
        with pytest.raises(ValueError, match="corrupted"):
            assert_engine_ready_no_compat(ENGINE, "v1")
        # v2 was not touched and can still be activated.
        custom_models.activate_version(ENGINE, "v2")
        assert engine_status(ENGINE)["state"] == store.READY

    def test_same_size_same_mtime_edit_is_caught_by_verify(self, two_versions):
        custom_models.activate_version(ENGINE, "v1")
        target = custom_models.model_path(ENGINE, "v1")
        assert store.model_status(ENGINE).status == "installed"  # fills the cache
        st = target.stat()
        os.chmod(target, 0o644)
        data = bytearray(target.read_bytes())
        data[500] ^= 0x01
        target.write_bytes(bytes(data))
        os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns))
        manifest = custom_models.verify_version(ENGINE, "v1")
        assert manifest["verification"]["status"] == "corrupted"
        assert "sha256" in manifest["verification"]["detail"]

    def test_same_size_same_mtime_edit_stops_the_next_document(self, two_versions):
        """Every job re-reads the whole file: the hash cache cannot hide an edit."""
        custom_models.activate_version(ENGINE, "v1")
        target = custom_models.model_path(ENGINE, "v1")
        assert_engine_ready_no_compat(ENGINE, "v1")  # fills the cache
        st = target.stat()
        os.chmod(target, 0o644)
        data = bytearray(target.read_bytes())
        data[700] ^= 0x01
        target.write_bytes(bytes(data))
        os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns))
        assert store.model_status(ENGINE).status == "installed"  # cached verdict
        with pytest.raises(ValueError, match="corrupted"):
            assert_engine_ready_no_compat(ENGINE, "v1")

    def test_missing_file(self, two_versions):
        custom_models.activate_version(ENGINE, "v1")
        custom_models.model_path(ENGINE, "v1").unlink()
        assert store.model_status(ENGINE).status in ("not_installed", "partial")
        assert engine_status(ENGINE)["state"] != store.READY
        assert (
            custom_models.verify_version(ENGINE, "v1")["verification"]["status"]
            == "missing"
        )

    def test_version_directory_swapped_for_a_symlink(self, two_versions, tmp_path):
        custom_models.activate_version(ENGINE, "v1")
        vdir = custom_models.model_path(ENGINE, "v1").parent
        elsewhere = tmp_path / "elsewhere"
        shutil.copytree(vdir, elsewhere)
        shutil.rmtree(vdir)
        vdir.symlink_to(elsewhere)
        check = custom_models.check_version(ENGINE, "v1")
        assert not check.verified
        assert store.model_status(ENGINE).status == "corrupted"

    def test_no_active_version_is_not_installed(self, two_versions):
        assert store.model_status(ENGINE).status == "not_installed"
        assert engine_status(ENGINE)["state"] == store.NOT_INSTALLED
        assert readiness.readiness_status(ENGINE)["state"] == readiness.MODEL_MISSING

    def test_verify_restores_verified_status(self, two_versions):
        manifest = custom_models.verify_version(ENGINE, "v1")
        assert manifest["verification"]["status"] == "verified"
        assert two_versions["calls"][-1] == (
            str(paths.tessdata_dir()),
            "custom/agri/v1/vie_agri",
        )


def assert_engine_ready_no_compat(engine_id, version):
    """assert_engine_ready without the Docling dependency fingerprint check."""
    from unittest.mock import patch

    from open_notebook.ocr import compat

    with patch.object(compat, "ensure_compatible", lambda e: None):
        assert_engine_ready(engine_id, version)


# --- OCR options: one version per job ---------------------------------------------------------


class TestOptions:
    def test_languages_follow_the_active_version(self, two_versions):
        assert options.engine_langs(ENGINE) == []
        custom_models.activate_version(ENGINE, "v1")
        assert options.engine_langs(ENGINE) == ["custom/agri/v1/vie_agri"]
        assert options.engine_langs(ENGINE, "v2") == ["custom/agri/v2/vie_agri"]
        info = options.describe(ENGINE)
        assert info["docling_class"] == "TesseractCliOcrOptions"
        assert info["custom_model"]["version"] == "v1"
        assert (
            info["custom_model"]["sha256"]
            == custom_models.read_version(ENGINE, "v1")["sha256"]
        )

    def test_english_companion_is_opt_in(self, two_versions, monkeypatch):
        custom_models.activate_version(ENGINE, "v1")
        assert custom_models.with_english(ENGINE) is False
        monkeypatch.setenv("OCR_AGRI_WITH_ENGLISH", "true")
        assert options.engine_langs(ENGINE) == ["custom/agri/v1/vie_agri", "best/eng"]
        # ... and then the official English model must be installed.
        assert store.model_status(ENGINE).status == "partial"
        assert custom_models.status(ENGINE)["english_ok"] is False

    def test_settings_freeze_the_version_at_job_start(self, two_versions):
        class Settings:
            docling_ocr = True
            docling_ocr_engine = ENGINE
            docling_ocr_num_threads = None
            docling_ocr_force_full_page = False

        custom_models.activate_version(ENGINE, "v1")
        job = OcrSettings.from_content_settings(Settings())
        assert job.custom_version == "v1"
        # The admin switches the version while the document is being processed.
        custom_models.activate_version(ENGINE, "v2")
        assert job.pinned().custom_version == "v1"
        assert options.engine_langs(job.engine, job.custom_version) == [
            "custom/agri/v1/vie_agri"
        ]
        # A document that starts now uses the new version.
        assert OcrSettings.from_content_settings(Settings()).custom_version == "v2"

    def test_official_engines_carry_no_version(self, two_versions):
        custom_models.activate_version(ENGINE, "v1")
        for engine in catalog.ENGINE_IDS:
            assert OcrSettings(engine=engine).pinned().custom_version is None
            assert "custom_model" not in options.describe(engine)
            assert "custom_model" not in readiness.fingerprint(engine)

    def test_build_options_pins_the_version(self, two_versions, monkeypatch):
        pytest.importorskip("docling")
        monkeypatch.setattr(options, "tesseract_command", lambda cmd: cmd)
        custom_models.activate_version(ENGINE, "v1")
        built = options.build_ocr_options(ENGINE, custom_version="v2")
        assert type(built).__name__ == "TesseractCliOcrOptions"
        assert list(built.lang) == ["custom/agri/v2/vie_agri"]
        assert built.path == str(paths.tessdata_dir())
        assert list(options.build_ocr_options(ENGINE).lang) == [
            "custom/agri/v1/vie_agri"
        ]

    def test_build_options_without_a_version_fails_loudly(
        self, two_versions, monkeypatch
    ):
        pytest.importorskip("docling")
        with pytest.raises(ValueError, match="no active model version"):
            options.build_ocr_options(ENGINE)


# --- Readiness belongs to one version -------------------------------------------------------


def _passing_check(mode="local_only", version=None):
    return {
        "mode": mode,
        "success": True,
        "pipeline_ok": True,
        "checked_at": time.time(),
        "custom_version": version,
        "layout_model": "layout_heron",
        "table_model": "docling_tableformer",
        "table_mode": "accurate",
        "fingerprint": readiness.fingerprint(ENGINE, version),
    }


class TestReadiness:
    def test_fingerprint_carries_version_and_sha(self, two_versions):
        custom_models.activate_version(ENGINE, "v1")
        fp1 = readiness.fingerprint(ENGINE)
        assert fp1["custom_model"]["version"] == "v1"
        assert (
            fp1["custom_model"]["sha256"]
            == custom_models.read_version(ENGINE, "v1")["sha256"]
        )
        assert fp1["custom_model"]["langs"] == ["custom/agri/v1/vie_agri"]
        custom_models.activate_version(ENGINE, "v2")
        fp2 = readiness.fingerprint(ENGINE)
        assert fp2["custom_model"] != fp1["custom_model"]
        assert readiness.fingerprint(ENGINE, "v1") == fp1

    def test_verdict_does_not_carry_over_to_another_version(self, two_versions):
        custom_models.activate_version(ENGINE, "v1")
        readiness.record(ENGINE, _passing_check(version="v1"))
        assert readiness.readiness_status(ENGINE)["state"] == readiness.OFFLINE_READY
        assert engine_status(ENGINE)["readiness"]["state"] == readiness.OFFLINE_READY

        custom_models.activate_version(ENGINE, "v2")  # the model changed
        now = readiness.readiness_status(ENGINE)
        assert now["state"] == readiness.PIPELINE_NOT_VERIFIED
        assert now["custom_version"] == "v2" and not now["pipeline_ok"]

        custom_models.rollback(ENGINE)  # v1's own verdict is still about v1
        assert readiness.readiness_status(ENGINE)["state"] == readiness.OFFLINE_READY

    def test_verdict_goes_stale_when_the_recorded_sha_changes(self, two_versions):
        custom_models.activate_version(ENGINE, "v1")
        readiness.record(ENGINE, _passing_check(version="v1"))
        path = paths.manifests_dir() / "custom" / "agri" / "versions" / "v1.json"
        manifest = json.loads(path.read_text())
        manifest["sha256"] = "0" * 64  # someone edits the manifest to fit a new file
        path.write_text(json.dumps(manifest))
        status = readiness.readiness_status(ENGINE)
        assert status["state"] != readiness.OFFLINE_READY
        assert status["stale"] is True

    def test_english_switch_makes_the_verdict_stale(self, two_versions, monkeypatch):
        custom_models.activate_version(ENGINE, "v1")
        readiness.record(ENGINE, _passing_check(version="v1"))
        monkeypatch.setenv("OCR_AGRI_WITH_ENGLISH", "true")
        assert readiness.readiness_status(ENGINE)["state"] != readiness.OFFLINE_READY

    def test_check_is_recorded_on_the_version_it_ran(self, two_versions, monkeypatch):
        custom_models.activate_version(ENGINE, "v1")
        seen = {}

        def fake_run(cmd, **kw):
            seen["cmd"] = cmd

            class P:
                stdout = json.dumps(
                    {
                        "success": True,
                        "layout_model": "layout_heron",
                        "table_model": "docling_tableformer",
                        "table_mode": "accurate",
                        "custom_model": {"version": "v2", "sha256": "x"},
                    }
                ).encode()
                stderr = b""

            return P()

        monkeypatch.setattr(readiness.subprocess, "run", fake_run)
        monkeypatch.setattr(readiness, "internet_reachable", lambda: False)
        out = readiness.check(ENGINE, custom_version="v2")
        assert seen["cmd"][-2:] == [ENGINE, "v2"]
        assert out["check"]["custom_version"] == "v2"
        assert out["readiness"]["state"] == readiness.OFFLINE_READY
        # The inactive version got the verdict; the active one did not.
        assert readiness.readiness_status(ENGINE)["state"] == (
            readiness.PIPELINE_NOT_VERIFIED
        )
        per_version = {
            v["version"]: v["readiness_state"]
            for v in custom_models.status(ENGINE)["versions"]
        }
        assert per_version == {
            "v1": readiness.PIPELINE_NOT_VERIFIED,
            "v2": readiness.OFFLINE_READY,
        }

    def test_check_that_ran_another_version_is_not_credited(
        self, two_versions, monkeypatch
    ):
        custom_models.activate_version(ENGINE, "v1")

        def fake_run(cmd, **kw):
            class P:
                stdout = json.dumps(
                    {
                        "success": True,
                        "layout_model": "layout_heron",
                        "table_model": "docling_tableformer",
                        "table_mode": "accurate",
                        "custom_model": {"version": "v2", "sha256": "x"},
                    }
                ).encode()
                stderr = b""

            return P()

        monkeypatch.setattr(readiness.subprocess, "run", fake_run)
        result = readiness.run_pipeline_check(ENGINE, "local_only")
        assert result["custom_version"] == "v1"
        assert result["success"] is False and result["pipeline_ok"] is False

    def test_check_without_a_version(self, ocr_dir, fake_tesseract):
        result = readiness.run_pipeline_check(ENGINE, "local_only")
        assert result["pipeline_ok"] is False
        assert "no model version" in result["error"]

    def test_official_engine_readiness_storage_unchanged(self, two_versions):
        check = {
            "mode": "local_only",
            "success": True,
            "pipeline_ok": True,
            "checked_at": time.time(),
            "fingerprint": readiness.fingerprint("rapidocr"),
        }
        readiness.record("rapidocr", check)
        assert store.read_state("rapidocr")["readiness"]["local_only"]["success"]
        assert not (paths.manifests_dir() / "custom" / "rapidocr").exists()


# --- Installer guards ------------------------------------------------------------------------


class TestInstaller:
    def test_custom_versions_are_not_removed_by_delete(self, two_versions):
        custom_models.activate_version(ENGINE, "v1")
        with pytest.raises(installer.InstallError, match="admin CLI"):
            installer.delete_models(ENGINE, "rapidocr")
        assert custom_models.model_path(ENGINE, "v1").is_file()

    def test_shared_osd_is_kept_while_agri_has_an_active_version(
        self, two_versions, monkeypatch
    ):
        """Removing Fast/Best must not take the orientation data Agri uses."""
        custom_models.activate_version(ENGINE, "v1")
        osd = catalog.get_engine(ENGINE).files[0]
        fake = catalog.EngineSpec(
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
            files=(osd,),
        )
        monkeypatch.setitem(catalog.ENGINES, "fake", fake)
        installer.delete_models("fake", "rapidocr")
        assert (paths.models_dir() / osd.rel_path).is_file()

    def test_smoke_check_without_a_version(self, two_versions):
        assert installer.smoke_check(ENGINE)["ok"] is None

    def _best_like(self, monkeypatch):
        """An official engine that owns the English model Agri may read."""
        english = catalog.get_engine(ENGINE).custom.english_rel_path
        target = paths.models_dir() / english
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"official english")
        owner = catalog.EngineSpec(
            id="bestlike",
            display_name="Best-like",
            description="",
            languages=("vie", "eng"),
            docling_kind="tesseract",
            model_name="bestlike",
            model_version="1",
            runtime="tesseract",
            license="MIT",
            source_url="",
            files=(
                catalog.ModelFile(
                    rel_path=english,
                    url="https://raw.githubusercontent.com/x/y/eng",
                    sha256=hashlib.sha256(b"official english").hexdigest(),
                    size=len(b"official english"),
                ),
            ),
        )
        monkeypatch.setitem(catalog.ENGINES, "bestlike", owner)
        return target

    def test_the_english_companion_is_not_removed_while_agri_reads_it(
        self, two_versions, monkeypatch
    ):
        """Review finding: removing Best must not break an Agri that uses eng."""
        target = self._best_like(monkeypatch)
        custom_models.activate_version(ENGINE, "v1")
        monkeypatch.setenv("OCR_AGRI_WITH_ENGLISH", "true")
        with pytest.raises(installer.InstallError, match="second language"):
            installer.delete_models("bestlike", "rapidocr")
        assert target.read_bytes() == b"official english"

    def test_the_english_model_is_removable_when_agri_does_not_read_it(
        self, two_versions, monkeypatch
    ):
        target = self._best_like(monkeypatch)
        custom_models.activate_version(ENGINE, "v1")  # switch off: Vietnamese only
        assert installer.delete_models("bestlike", "rapidocr") == [
            catalog.get_engine(ENGINE).custom.english_rel_path
        ]
        assert not target.exists()

    def test_the_english_model_is_removable_when_agri_has_no_active_version(
        self, two_versions, monkeypatch
    ):
        target = self._best_like(monkeypatch)
        monkeypatch.setenv("OCR_AGRI_WITH_ENGLISH", "true")
        installer.delete_models("bestlike", "rapidocr")
        assert not target.exists()


# --- Status payload ----------------------------------------------------------------------------


class TestStatus:
    def test_status_lists_versions(self, two_versions):
        custom_models.activate_version(ENGINE, "v1")
        custom_models.activate_version(ENGINE, "v2")
        info = custom_models.status(ENGINE)
        assert info["active_version"] == "v2" and info["previous_version"] == "v1"
        assert [v["version"] for v in info["versions"]] == ["v1", "v2"]
        assert [v["active"] for v in info["versions"]] == [False, True]
        assert [v["previous"] for v in info["versions"]] == [True, False]
        assert all(v["file_ok"] and len(v["sha256"]) == 64 for v in info["versions"])
        assert info["prerequisites_ok"] is True
        assert "custom import" in info["import_cli"]
        assert all(v["file_present"] is True for v in info["versions"])
        st = engine_status(ENGINE, ENGINE)
        assert st["custom"]["active_version"] == "v2" and st["active"] is True
        assert st["quality"] == "experimental"

    def test_official_engines_have_no_custom_block(self, two_versions):
        for engine in catalog.ENGINE_IDS:
            assert engine_status(engine)["custom"] is None


# --- CLI -----------------------------------------------------------------------------------------


class TestCli:
    def _run(self, argv, capsys):
        from open_notebook.ocr import cli

        code = cli.main(argv)
        return code, capsys.readouterr().out

    @pytest.mark.parametrize(
        "argv",
        [
            ["custom", "--help"],
            ["custom", "import", "--help"],
            ["custom", "list", "--help"],
            ["custom", "verify", "--help"],
            ["custom", "activate", "--help"],
            ["custom", "rollback", "--help"],
            ["custom", "status", "--help"],
            ["custom", "remove", "--help"],
        ],
    )
    def test_help(self, argv, capsys):
        from open_notebook.ocr import cli

        with pytest.raises(SystemExit) as e:
            cli.main(argv)
        assert e.value.code == 0
        assert "usage:" in capsys.readouterr().out

    def test_a_model_with_a_forbidden_parameter_is_refused_with_exit_code_1(
        self, ocr_dir, tmp_path, fake_tesseract, capsys
    ):
        bad = _source_with(tmp_path, b"debug_file /app/data/x\n")
        code, out = self._run(
            ["custom", "import", "--file", str(bad), "--version", "v1"], capsys
        )
        assert code == 1 and "debug_file" in out and "ERROR" in out
        assert custom_models.list_versions(ENGINE) == []

    def test_bare_readiness_ignores_a_custom_engine_without_a_model(
        self, ocr_dir, fake_tesseract, capsys, monkeypatch
    ):
        """Review finding: a deployment that never imported Agri must still be
        able to get exit code 0 from `readiness` (documented offline procedure)."""
        from open_notebook.ocr import cli

        asked = []

        def fake_status(engine_id, **kwargs):
            asked.append(engine_id)
            return {
                "engine": engine_id,
                "state": readiness.OFFLINE_READY,
                "ocr_ok": True,
                "pipeline_ok": True,
                "local_only_verified": True,
                "offline_verified": True,
                "stale": False,
                "last_check": {"mode": "offline"},
            }

        monkeypatch.setattr(readiness, "readiness_status", fake_status)
        assert cli.main(["readiness"]) == 0
        assert asked == list(catalog.ENGINE_IDS)
        capsys.readouterr()

    def test_bare_readiness_includes_a_custom_engine_that_has_a_model(
        self, two_versions, capsys, monkeypatch
    ):
        from open_notebook.ocr import cli

        asked = []

        def fake_status(engine_id, **kwargs):
            asked.append(engine_id)
            ready = engine_id != ENGINE
            return {
                "engine": engine_id,
                "state": readiness.OFFLINE_READY if ready else "pipeline_not_verified",
                "ocr_ok": ready,
                "pipeline_ok": ready,
                "local_only_verified": ready,
                "offline_verified": ready,
                "stale": False,
                "last_check": {},
            }

        monkeypatch.setattr(readiness, "readiness_status", fake_status)
        custom_models.activate_version(ENGINE, "v1")
        assert cli.main(["readiness"]) == 1  # Agri now counts, and is not ready
        assert asked == [*catalog.ENGINE_IDS, ENGINE]
        asked.clear()
        assert cli.main(["readiness", "--engines", "rapidocr"]) == 0
        assert asked == ["rapidocr"]
        capsys.readouterr()

    def test_full_cycle(self, ocr_dir, tmp_path, fake_tesseract, capsys, monkeypatch):
        _install_osd(monkeypatch)
        a, b = _source(tmp_path, b"a"), _source(tmp_path, b"b")
        code, out = self._run(
            [
                "custom",
                "import",
                "--file",
                str(a),
                "--version",
                "v1",
                "--skip-readiness",
            ],
            capsys,
        )
        assert code == 0 and "NOT active" in out and "sha256" in out
        assert (
            "language_model_ngram_on=1, classify_misfit_junk_penalty=0.125" in out
        )  # what the model itself tells Tesseract, shown to the operator
        code, out = self._run(["custom", "activate", "--version", "v1"], capsys)
        assert code == 0 and "active version: v1" in out
        code, _ = self._run(
            [
                "custom",
                "import",
                "--file",
                str(b),
                "--version",
                "v2",
                "--skip-readiness",
            ],
            capsys,
        )
        assert code == 0 and custom_models.active_version(ENGINE) == "v1"
        code, out = self._run(["custom", "activate", "--version", "v2"], capsys)
        assert code == 0 and "was v1" in out
        code, out = self._run(["custom", "rollback"], capsys)
        assert code == 0 and "active version v1" in out
        code, out = self._run(["custom", "list"], capsys)
        assert code == 0 and "ACTIVE" in out and "previous" in out
        code, out = self._run(["custom", "verify"], capsys)
        assert code == 0 and out.count("verified") == 2
        code, out = self._run(["custom", "status", "--no-db"], capsys)
        assert code == 0 and "active version        : v1" in out
        code, out = self._run(["custom", "list", "--json"], capsys)
        assert json.loads(out)["active_version"] == "v1"

    def test_errors_are_reported_with_exit_code_1(
        self, ocr_dir, tmp_path, fake_tesseract, capsys
    ):
        bad = tmp_path / "bad.traineddata"
        bad.write_bytes(os.urandom(9000))
        for argv in (
            ["custom", "import", "--file", str(bad), "--version", "v1"],
            ["custom", "import", "--file", str(bad), "--version", "../x"],
            ["custom", "activate", "--version", "v7"],
            ["custom", "rollback"],
            ["custom", "verify", "--version", "v7"],
        ):
            code, out = self._run(argv, capsys)
            assert code == 1 and "ERROR:" in out, argv
        assert custom_models.list_versions(ENGINE) == []

    def test_only_custom_engines_are_accepted(self, capsys):
        from open_notebook.ocr import cli

        with pytest.raises(SystemExit) as e:
            cli.main(["custom", "list", "--engine", "tesseract_best"])
        assert e.value.code == 2

    def test_bundles_and_removal_exclude_custom_engines(self, capsys):
        from open_notebook.ocr import cli

        for argv in (
            ["remove-model", ENGINE],
            ["bundle", "create", "--engines", ENGINE, "--out", "/tmp/x"],
        ):
            with pytest.raises(SystemExit) as e:
                cli.main(argv)
            assert e.value.code == 2


# --- API ------------------------------------------------------------------------------------------


class TestApi:
    @pytest.fixture
    def client(self, two_versions, monkeypatch):
        from fastapi.testclient import TestClient

        from api.main import app
        from open_notebook.domain.content_settings import ContentSettings

        ContentSettings.clear_instance()

        class FakeSettings:
            docling_ocr = True
            docling_ocr_engine = "rapidocr"
            docling_ocr_num_threads = None
            docling_ocr_force_full_page = False

            async def update(self):
                pass

        fake = FakeSettings()

        async def get_settings():
            return fake

        async def no_running_jobs():
            return 0

        monkeypatch.setattr("api.ocr_service._settings", get_settings)
        monkeypatch.setattr("api.ocr_service._running_source_jobs", no_running_jobs)
        monkeypatch.setattr(
            runtime,
            "docling_info",
            lambda force=False: {"available": True, "version": "2.129.0"},
        )
        return TestClient(app), fake

    def test_list_includes_the_custom_engine_last(self, client):
        c, _ = client
        body = c.get("/api/ocr/engines").json()
        assert [e["id"] for e in body["engines"]] == list(catalog.ALL_ENGINE_IDS)
        agri = body["engines"][-1]
        assert agri["display_name"] == "Tesseract Vietnamese Agri"
        assert agri["state"] == "not_installed"
        assert [v["version"] for v in agri["custom"]["versions"]] == ["v1", "v2"]
        assert all(e["custom"] is None for e in body["engines"][:-1])

    def test_activate_version_then_engine_then_rollback(self, client):
        c, fake = client
        base = f"/api/ocr/engines/{ENGINE}"
        # The engine cannot be selected before a version is active.
        assert c.post(f"{base}/activate").status_code == 400
        r = c.post(f"{base}/custom/activate", json={"version": "v1"})
        assert r.status_code == 200 and r.json()["custom"]["active_version"] == "v1"
        assert r.json()["state"] == "ready"
        r = c.post(f"{base}/activate")
        assert r.status_code == 200 and fake.docling_ocr_engine == ENGINE
        r = c.post(f"{base}/custom/activate", json={"version": "v2"})
        assert r.json()["custom"]["active_version"] == "v2"
        assert r.json()["custom"]["previous_version"] == "v1"
        r = c.post(f"{base}/custom/rollback")
        assert r.status_code == 200 and r.json()["custom"]["active_version"] == "v1"
        # Switching back to an official engine still works.
        assert c.post("/api/ocr/engines/rapidocr/activate").status_code == 200
        assert fake.docling_ocr_engine == "rapidocr"

    def test_verify_endpoint(self, client):
        c, _ = client
        r = c.post(f"/api/ocr/engines/{ENGINE}/custom/verify", json={"version": "v2"})
        assert r.status_code == 200
        v2 = [v for v in r.json()["custom"]["versions"] if v["version"] == "v2"][0]
        assert v2["verification"]["status"] == "verified"

    def test_errors(self, client):
        c, _ = client
        base = f"/api/ocr/engines/{ENGINE}/custom"
        assert c.post(f"{base}/activate", json={"version": "v9"}).status_code == 404
        assert c.post(f"{base}/verify", json={"version": "v9"}).status_code == 404
        for bad in ("../v1", "v1/..", "", "v1.0", "a" * 40):
            assert (
                c.post(f"{base}/activate", json={"version": bad}).status_code == 422
            ), bad
        assert c.post(f"{base}/activate", json={}).status_code == 422
        assert c.post(f"{base}/rollback").status_code == 400  # nothing to roll back
        for engine in ("tesseract_best", "rapidocr"):
            r = c.post(
                f"/api/ocr/engines/{engine}/custom/activate", json={"version": "v1"}
            )
            assert r.status_code == 400
        assert (
            c.post(
                "/api/ocr/engines/vietocr/custom/activate", json={"version": "v1"}
            ).status_code
            == 404
        )
        assert c.delete(f"/api/ocr/engines/{ENGINE}/model").status_code == 400

    def test_corrupted_version_cannot_be_activated(self, client):
        c, _ = client
        base = f"/api/ocr/engines/{ENGINE}/custom"
        c.post(f"{base}/activate", json={"version": "v1"})
        target = custom_models.model_path(ENGINE, "v2")
        os.chmod(target, 0o644)
        target.write_bytes(b"x" * target.stat().st_size)
        r = c.post(f"{base}/activate", json={"version": "v2"})
        assert r.status_code == 400 and "verification" in r.json()["detail"]
        assert custom_models.active_version(ENGINE) == "v1"

    def test_no_http_upload_route(self):
        """Model files are imported by the CLI only: no OCR route takes a body file."""
        from api.main import app

        ocr_routes = {
            (tuple(sorted(r.methods)), r.path)
            for r in app.routes
            if getattr(r, "path", "").startswith("/api/ocr")
        }
        assert ocr_routes == {
            (("GET",), "/api/ocr/engines"),
            (("GET",), "/api/ocr/engines/{engine_id}"),
            (("POST",), "/api/ocr/engines/{engine_id}/install"),
            (("POST",), "/api/ocr/engines/{engine_id}/activate"),
            (("POST",), "/api/ocr/engines/{engine_id}/test"),
            (("POST",), "/api/ocr/engines/{engine_id}/prepare"),
            (("POST",), "/api/ocr/engines/{engine_id}/readiness-check"),
            (("DELETE",), "/api/ocr/engines/{engine_id}/model"),
            (("POST",), "/api/ocr/engines/{engine_id}/custom/activate"),
            (("POST",), "/api/ocr/engines/{engine_id}/custom/rollback"),
            (("POST",), "/api/ocr/engines/{engine_id}/custom/verify"),
            (("GET",), "/api/ocr/jobs/{job_id}"),
            (("GET",), "/api/ocr/config"),
            (("PUT",), "/api/ocr/config"),
        }
        src = Path("api/routers/ocr.py").read_text(encoding="utf-8")
        assert "UploadFile" not in src and "File(" not in src


class TestApiRequiresAdmin:
    @pytest.fixture(autouse=True)
    def _auth(self, monkeypatch):
        monkeypatch.setenv("OPEN_NOTEBOOK_JWT_SECRET", "test-secret-key")
        monkeypatch.delenv("OPEN_NOTEBOOK_DISABLE_AUTH", raising=False)

    @pytest.mark.parametrize(
        "path,body",
        [
            (f"/api/ocr/engines/{ENGINE}/custom/activate", {"version": "v1"}),
            (f"/api/ocr/engines/{ENGINE}/custom/rollback", None),
            (f"/api/ocr/engines/{ENGINE}/custom/verify", {"version": "v1"}),
            (f"/api/ocr/engines/{ENGINE}/activate", None),
            (f"/api/ocr/engines/{ENGINE}/test", None),
            (f"/api/ocr/engines/{ENGINE}/install", None),
            (f"/api/ocr/engines/{ENGINE}/readiness-check", None),
        ],
    )
    @pytest.mark.parametrize("role", ["user", "contributor", "approver"])
    def test_non_admin_forbidden(self, path, body, role, ocr_dir):
        from fastapi.testclient import TestClient

        from api.auth import create_access_token
        from api.main import app

        c = TestClient(app)
        kwargs = {"json": body} if body is not None else {}
        assert c.post(path, **kwargs).status_code == 401
        token = create_access_token(f"user:{role}", role, role)
        r = c.post(path, headers={"Authorization": f"Bearer {token}"}, **kwargs)
        assert r.status_code == 403
        assert custom_models.active_version(ENGINE) is None


# --- Real Tesseract (skipped when unavailable) ---------------------------------------------------


REAL_MODEL = os.environ.get("OCR_TEST_REAL_TRAINEDDATA", "")


# --- Hardening from the Phase 10H security review -------------------------------------------


def _source_with(tmp_path, config: bytes | None, seed: bytes = b"z") -> Path:
    src = tmp_path / f"cfg-{seed.decode()}" / "vie_agri.traineddata"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(fake_traineddata(seed, config=config))
    return src


class TestEmbeddedParameters:
    """A model may only carry harmless recognition-tuning parameters (M1)."""

    def test_the_official_parameter_file_is_accepted_and_recorded(
        self, ocr_dir, tmp_path, fake_tesseract
    ):
        manifest = custom_models.import_model(ENGINE, _source(tmp_path), "v1")
        assert manifest["traineddata"]["config_params"] == [
            {"name": "language_model_ngram_on", "value": "1"},
            {"name": "classify_misfit_junk_penalty", "value": "0.125"},
        ]

    def test_a_model_without_parameter_file_is_accepted(
        self, ocr_dir, tmp_path, fake_tesseract
    ):
        manifest = custom_models.import_model(
            ENGINE, _source_with(tmp_path, None), "v1"
        )
        assert manifest["traineddata"]["config_params"] == []

    @pytest.mark.parametrize(
        "config",
        [
            b"debug_file /app/data/victim\n",
            b"tessedit_load_sublangs ../../../../x\n",
            b"user_words_file /etc/passwd\n",
            b"tessedit_write_images 1\n",
            b"language_model_ngram_on 1\ndebug_file /tmp/x\n",
            # an accepted name with something that is not a number / boolean
            b"language_model_ngram_on /etc/passwd\n",
            b"classify_misfit_junk_penalty 0.1 debug_file /x\n",
            # Tesseract would read the tail of an over-long line as a new line
            b"#" + b"x" * 5000 + b"debug_file /tmp/x\n",
            b" debug_file /tmp/x\n",  # leading blank: not a comment for Tesseract
            b"language_model_ngram_on\t1\rdebug_file /tmp/x\n",
            b"language_model_ngram_on 1\x00\n",
            b"# only comments\n" * 2000,  # larger than the accepted size
        ],
    )
    def test_anything_else_rejects_the_import_before_tesseract_loads_it(
        self, ocr_dir, tmp_path, fake_tesseract, config
    ):
        with pytest.raises(custom_models.CustomModelError, match="parameter"):
            custom_models.import_model(ENGINE, _source_with(tmp_path, config), "v1")
        assert fake_tesseract["calls"] == []  # the file was never given to Tesseract
        assert custom_models.list_versions(ENGINE) == []
        assert not (
            paths.models_dir() / "tesseract" / "custom" / "agri" / "v1"
        ).exists()

    def test_every_accepted_parameter_is_a_plain_tuning_switch(self):
        risky = ("file", "path", "dir", "write", "debug", "output", "sublang", "user_")
        for name in custom_models.ALLOWED_CONFIG_PARAMS:
            assert not any(word in name for word in risky), name
        for value in ("1", "0", "0.125", "-2.5e-3", "T", "f", "true", "No"):
            assert custom_models.parse_model_config(
                f"chop_enable {value}\n".encode()
            ) == [{"name": "chop_enable", "value": value}]

    def test_a_version_stored_by_an_older_release_is_checked_too(
        self, two_versions, tmp_path
    ):
        """v1 is active; pretend its file (and manifest) predate the check."""
        custom_models.activate_version(ENGINE, "v1")
        bad = fake_traineddata(b"old", config=b"debug_file /app/data/victim\n")
        target = custom_models.model_path(ENGINE, "v1")
        os.chmod(target, 0o644)
        target.write_bytes(bad)
        manifest_file = paths.manifests_dir() / "custom/agri/versions/v1.json"
        manifest = json.loads(manifest_file.read_text())
        manifest.update(sha256=hashlib.sha256(bad).hexdigest(), size=len(bad))
        manifest["traineddata"].pop("config_params", None)
        manifest_file.write_text(json.dumps(manifest))
        store._hash_cache.clear()

        check = custom_models.check_version(ENGINE, "v1")
        assert check.present and not check.verified and "debug_file" in check.detail
        assert engine_status(ENGINE)["state"] == store.FAILED
        with pytest.raises(ValueError):
            assert_engine_ready_no_compat(ENGINE, "v1")
        assert custom_models.verify_version(ENGINE, "v1")["verification"]["status"] == (
            "corrupted"
        )
        custom_models.activate_version(ENGINE, "v2")
        with pytest.raises(custom_models.CustomModelError, match="failed verification"):
            custom_models.rollback(ENGINE)


class TestFilesystemHardening:
    def test_import_refuses_a_version_directory_that_is_a_link(
        self, ocr_dir, tmp_path, fake_tesseract
    ):
        """L1: custom/agri/v2 -> ../../best must not delete the official models."""
        best = paths.models_dir() / "tesseract" / "best"
        best.mkdir(parents=True)
        (best / "vie.traineddata").write_bytes(b"official vie")
        (best / "eng.traineddata").write_bytes(b"official eng")
        family = paths.models_dir() / "tesseract" / "custom" / "agri"
        family.mkdir(parents=True)
        (family / "v2").symlink_to("../../best")
        with pytest.raises(custom_models.CustomModelError, match="symbolic link"):
            custom_models.import_model(ENGINE, _source(tmp_path), "v2")
        assert sorted(p.name for p in best.iterdir()) == [
            "eng.traineddata",
            "vie.traineddata",
        ]
        assert (best / "vie.traineddata").read_bytes() == b"official vie"
        assert custom_models.list_versions(ENGINE) == []

    def test_import_refuses_a_linked_family_directory(
        self, ocr_dir, tmp_path, fake_tesseract
    ):
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        custom = paths.models_dir() / "tesseract" / "custom"
        custom.mkdir(parents=True)
        (custom / "agri").symlink_to(elsewhere)
        with pytest.raises(custom_models.CustomModelError, match="symbolic link"):
            custom_models.import_model(ENGINE, _source(tmp_path), "v1")
        assert list(elsewhere.iterdir()) == []

    def test_a_link_to_another_version_is_never_followed(self, two_versions, tmp_path):
        custom_models.activate_version(ENGINE, "v1")
        family = paths.models_dir() / "tesseract" / "custom" / "agri"
        (family / "v3").symlink_to("v1")
        before = custom_models.model_path(ENGINE, "v1").read_bytes()
        with pytest.raises(custom_models.CustomModelError, match="symbolic link"):
            custom_models.import_model(ENGINE, _source(tmp_path, b"c"), "v3")
        assert custom_models.model_path(ENGINE, "v1").read_bytes() == before
        assert custom_models.check_version(ENGINE, "v1", deep=True).verified

    def test_remove_refuses_a_linked_family_directory(self, two_versions, tmp_path):
        family = paths.models_dir() / "tesseract" / "custom" / "agri"
        moved = tmp_path / "moved-agri"
        family.rename(moved)
        family.symlink_to(moved)
        with pytest.raises(custom_models.CustomModelError, match="symbolic link"):
            custom_models.remove_version(ENGINE, "v2")
        assert (moved / "v2" / "vie_agri.traineddata").is_file()

    def test_reimporting_the_active_id_after_its_manifest_is_lost_is_refused(
        self, two_versions, tmp_path
    ):
        """L2: the file documents are read with is never replaced in place."""
        custom_models.activate_version(ENGINE, "v1")
        custom_models.activate_version(ENGINE, "v2")  # v1 = rollback target
        before = {
            v: custom_models.model_path(ENGINE, v).read_bytes() for v in ("v1", "v2")
        }
        for version in ("v1", "v2"):
            (paths.manifests_dir() / f"custom/agri/versions/{version}.json").unlink()
            with pytest.raises(custom_models.CustomModelError, match="manifest"):
                custom_models.import_model(ENGINE, _source(tmp_path, b"other"), version)
            assert (
                custom_models.model_path(ENGINE, version).read_bytes()
                == (before[version])
            )
        registry = custom_models.read_registry(ENGINE)
        assert (registry["active_version"], registry["previous_version"]) == (
            "v2",
            "v1",
        )

    def test_a_leftover_directory_of_an_interrupted_import_is_still_replaced(
        self, ocr_dir, tmp_path, fake_tesseract
    ):
        leftover = paths.models_dir() / "tesseract" / "custom" / "agri" / "v1"
        leftover.mkdir(parents=True)
        (leftover / "vie_agri.traineddata").write_bytes(b"half a file")
        manifest = custom_models.import_model(ENGINE, _source(tmp_path), "v1")
        assert custom_models.check_version(ENGINE, "v1", deep=True).verified
        assert manifest["size"] == len(fake_traineddata(b"a"))

    def test_the_copy_is_bounded_and_takes_its_facts_from_the_open_file(self, tmp_path):
        """L5: nothing is trusted from the earlier lstat of the path."""
        big = tmp_path / "big.traineddata"
        big.write_bytes(b"x" * 20_000)
        with pytest.raises(custom_models.CustomModelError, match="changed|larger"):
            custom_models._copy_no_follow(big, tmp_path / "out1", max_size=10_000)
        fifo = tmp_path / "pipe.traineddata"
        os.mkfifo(fifo)
        started = time.monotonic()
        with pytest.raises(custom_models.CustomModelError, match="regular file"):
            custom_models._copy_no_follow(fifo, tmp_path / "out2", max_size=10_000)
        assert time.monotonic() - started < 5  # opening a FIFO must not block
        link = tmp_path / "link.traineddata"
        link.symlink_to(big)
        with pytest.raises(custom_models.CustomModelError, match="Cannot open"):
            custom_models._copy_no_follow(link, tmp_path / "out3", max_size=10**9)

    def test_staging_left_by_a_killed_import_is_removed_by_the_next_one(
        self, ocr_dir, tmp_path, fake_tesseract
    ):
        paths.ensure_dirs()
        stale = paths.downloads_dir() / "custom-staging" / "agri-v0-1-1"
        stale.mkdir(parents=True)
        (stale / "vie_agri.traineddata").write_bytes(b"x" * 1000)
        other = paths.downloads_dir() / "custom-staging" / "otherfamily-v0-1-1"
        other.mkdir(parents=True)
        custom_models.import_model(ENGINE, _source(tmp_path), "v1")
        assert not stale.exists() and other.exists()


class TestDamagedManifests:
    """L3: hand-edited or damaged JSON never becomes an exception elsewhere."""

    def _registry(self):
        return paths.manifests_dir() / "custom/agri/registry.json"

    def _manifest(self, version):
        return paths.manifests_dir() / f"custom/agri/versions/{version}.json"

    def _edit(self, path, **changes):
        data = json.loads(path.read_text())
        data.update(changes)
        path.write_text(json.dumps(data))

    @pytest.mark.parametrize(
        "changes",
        [
            {"history": 5},
            {"history": "x"},
            {"history": [1, "a", None]},
            {"previous_version": {"a": 1}},
            {"previous_version": "../v1"},
            {"activated_at": "now"},
            {"active_version": ["v1"]},
        ],
    )
    def test_registry(self, two_versions, changes):
        custom_models.activate_version(ENGINE, "v1")
        custom_models.activate_version(ENGINE, "v2")
        self._edit(self._registry(), **changes)
        registry = custom_models.read_registry(ENGINE)
        assert isinstance(registry["history"], list)
        assert all(isinstance(h, dict) for h in registry["history"])
        for key in ("active_version", "previous_version"):
            assert registry[key] is None or custom_models.VERSION_RE.match(
                registry[key]
            )
        info = custom_models.status(ENGINE)  # the settings page still renders
        assert info["previous_version"] is None or isinstance(
            info["previous_version"], str
        )
        engine_status(ENGINE)
        OcrSettings(engine=ENGINE).pinned()
        # and the family can still be operated
        custom_models.activate_version(ENGINE, "v1")
        assert custom_models.active_version(ENGINE) == "v1"

    @pytest.mark.parametrize(
        "changes",
        [
            {"imported_at": "yesterday"},
            {"smoke": "yes"},
            {"verification": ["verified"]},
            {"notes": {"a": 1}},
            {"duplicate_of": "v1"},
            {"readiness": 3},
            {"traineddata": None},
            {"size": "12"},
            {"sha256": 7},
        ],
    )
    def test_version_manifest(self, two_versions, tmp_path, changes):
        custom_models.activate_version(ENGINE, "v1")
        self._edit(self._manifest("v2"), **changes)
        versions = custom_models.list_versions(ENGINE)
        assert [v["version"] for v in versions] == ["v1", "v2"] or [
            v["version"] for v in versions
        ] == ["v2", "v1"]
        info = custom_models.status(ENGINE)
        v2 = next(v for v in info["versions"] if v["version"] == "v2")
        assert isinstance(v2["notes"], str) and isinstance(v2["duplicate_of"], list)
        engine_status(ENGINE)
        # v2 can never be activated on the strength of a damaged manifest ...
        usable = not (set(changes) & {"smoke", "verification", "size", "sha256"})
        if usable:
            custom_models.activate_version(ENGINE, "v2")
        else:
            with pytest.raises(custom_models.CustomModelError):
                custom_models.activate_version(ENGINE, "v2")
            assert custom_models.active_version(ENGINE) == "v1"
        # ... and the next import still works.
        custom_models.import_model(ENGINE, _source(tmp_path, b"c"), "v3")

    def test_a_manifest_filed_under_another_id_is_not_a_version(self, two_versions):
        self._edit(self._manifest("v2"), version="v1")
        assert custom_models.read_version(ENGINE, "v2") is None
        assert [v["version"] for v in custom_models.list_versions(ENGINE)] == ["v1"]
        with pytest.raises(custom_models.CustomModelError, match="Unknown version"):
            custom_models.activate_version(ENGINE, "v2")


class TestReadinessRecord:
    def test_the_verdict_is_written_under_the_family_lock(
        self, two_versions, monkeypatch
    ):
        """L4: the worker must not undo what verify / activate just wrote."""
        import contextlib

        held = []
        real = store.file_lock

        @contextlib.contextmanager
        def spy(name, timeout=0.0):
            held.append(name)
            with real(name, timeout):
                yield

        monkeypatch.setattr(store, "file_lock", spy)
        custom_models.record_readiness(
            ENGINE, "v1", {"mode": "offline", "ok": True, "text": "not stored"}
        )
        assert held == ["custom-agri"]
        stored = custom_models.readiness_checks(ENGINE, "v1")["offline"]
        assert stored == {"mode": "offline", "ok": True}

    def test_a_busy_lock_is_reported_not_raised(self, two_versions, monkeypatch):
        import contextlib

        from loguru import logger

        @contextlib.contextmanager
        def busy(name, timeout=0.0):
            raise store.LockBusy(f"{name} is busy")
            yield  # pragma: no cover

        monkeypatch.setattr(store, "file_lock", busy)
        messages = []
        sink = logger.add(
            lambda m: messages.append(m.record["message"]), level="WARNING"
        )
        try:
            custom_models.record_readiness(
                ENGINE, "v1", {"mode": "offline", "ok": True}
            )
        finally:
            logger.remove(sink)
        assert any("was not recorded" in m for m in messages)
        assert custom_models.readiness_checks(ENGINE, "v1") == {}


@pytest.mark.skipif(
    not (shutil.which("tesseract") and REAL_MODEL and Path(REAL_MODEL).is_file()),
    reason="needs the tesseract executable and OCR_TEST_REAL_TRAINEDDATA=<lstm model>",
)
class TestRealTesseract:
    def test_import_verify_and_reject_with_the_real_executable(self, ocr_dir, tmp_path):
        src = tmp_path / "vie_agri.traineddata"
        shutil.copyfile(REAL_MODEL, src)
        manifest = custom_models.import_model(ENGINE, src, "v1")
        assert manifest["smoke"]["ok"] and manifest["smoke"]["cer"] < 0.3
        assert manifest["sha256"] == hashlib.sha256(src.read_bytes()).hexdigest()
        assert (
            custom_models.verify_version(ENGINE, "v1")["verification"]["status"]
            == "verified"
        )
        # Structure intact, weights destroyed: only the real load can tell.
        data = bytearray(src.read_bytes())
        middle = len(data) // 2
        data[middle : middle + len(data) // 4] = bytes(len(data) // 4)
        broken = tmp_path / "broken" / "vie_agri.traineddata"
        broken.parent.mkdir()
        broken.write_bytes(bytes(data))
        with pytest.raises(custom_models.CustomModelError):
            custom_models.import_model(ENGINE, broken, "v2")
        assert [m["version"] for m in custom_models.list_versions(ENGINE)] == ["v1"]
