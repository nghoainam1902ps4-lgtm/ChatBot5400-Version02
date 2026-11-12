"""Offline bundle + admin CLI tests (no network; fake catalog entries)."""

import hashlib
import json

import pytest

from open_notebook.ocr import bundle, catalog, cli, paths, store


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_DATA_DIR", str(tmp_path / "ocr"))
    for var in (
        "OCR_MODELS_DIR",
        "OCR_PACKAGES_DIR",
        "OCR_MANIFESTS_DIR",
        "OCR_OFFLINE",
    ):
        monkeypatch.delenv(var, raising=False)
    store._hash_cache.clear()
    data = b"vietnamese-weights"
    spec = catalog.EngineSpec(
        id="fake",
        display_name="Fake",
        description="",
        languages=("vie",),
        docling_kind="tesseract",
        model_name="fake",
        model_version="1",
        runtime="tesseract",
        license="Apache-2.0",
        source_url="",
        files=(
            catalog.ModelFile(
                rel_path="fake/vie.traineddata",
                url="https://raw.githubusercontent.com/x",
                sha256=hashlib.sha256(data).hexdigest(),
                size=len(data),
            ),
        ),
    )
    monkeypatch.setitem(catalog.ENGINES, "fake", spec)
    monkeypatch.setattr(
        "open_notebook.ocr.installer.smoke_check",
        lambda e: {"ok": None, "detail": "test"},
    )
    # Pre-install the model so create() copies it instead of downloading.
    p = paths.models_dir() / "fake" / "vie.traineddata"
    p.parent.mkdir(parents=True)
    p.write_bytes(data)
    return tmp_path, data


def _make(tmp_path):
    out = tmp_path / "bundle"
    bundle.create(["fake"], out, with_runtime=False)
    return out


def _rewrite_checksums(out):
    lines = []
    for p in sorted((out).rglob("*")):
        if p.is_file() and p.name not in ("checksums.sha256", "README.md"):
            lines.append(
                f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out).as_posix()}"
            )
    (out / "checksums.sha256").write_text("\n".join(lines) + "\n")


def test_create_and_verify(env):
    tmp_path, _ = env
    out = _make(tmp_path)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["engines"] == ["fake"]
    assert manifest["environment"]["python"]
    assert (out / "README.md").exists()
    r = bundle.verify(out)
    assert r["ok"], r["problems"]
    assert r["digest"] == bundle.digest(out)


def test_tampered_file_detected(env):
    tmp_path, _ = env
    out = _make(tmp_path)
    (out / "models" / "fake" / "vie.traineddata").write_bytes(b"evil")
    assert not bundle.verify(out)["ok"]


def test_consistent_but_unpinned_model_rejected(env):
    """A bundle re-checksummed after swapping weights still fails: catalog is the anchor."""
    tmp_path, _ = env
    out = _make(tmp_path)
    (out / "models" / "fake" / "vie.traineddata").write_bytes(b"evil")
    _rewrite_checksums(out)
    r = bundle.verify(out)
    assert not r["ok"]
    assert any("pinned checksum" in p for p in r["problems"])
    with pytest.raises(RuntimeError):
        bundle.install(out)


def test_unlisted_and_traversal_entries_rejected(env):
    tmp_path, _ = env
    out = _make(tmp_path)
    (out / "models" / "extra.bin").write_bytes(b"x")
    assert any("unlisted" in p for p in bundle.verify(out)["problems"])
    (out / "models" / "extra.bin").unlink()
    with open(out / "checksums.sha256", "a") as f:
        f.write("0" * 64 + "  ../../etc/passwd\n")
    assert any("unsafe path" in p for p in bundle.verify(out)["problems"])


def test_install_offline_into_fresh_volume(env, monkeypatch):
    tmp_path, data = env
    out = _make(tmp_path)
    # Fresh target volume.
    monkeypatch.setenv("OCR_DATA_DIR", str(tmp_path / "target"))

    def no_network(*a, **k):
        raise AssertionError("network used")

    monkeypatch.setattr("open_notebook.ocr.installer._download", no_network)
    r = bundle.install(out)
    assert r["models"] == {"fake": {"fake/vie.traineddata": "bundle"}}
    assert (paths.models_dir() / "fake" / "vie.traineddata").read_bytes() == data
    # No duplicate copy of the weights left in the staging area.
    assert not (paths.packages_dir() / "models").exists()


def test_pinned_easyocr_wheel_enforced(env):
    good = paths.packages_dir() / "easyocr-1.7.2-py3-none-any.whl"
    good.parent.mkdir(parents=True, exist_ok=True)
    good.write_bytes(b"not the real wheel")
    with pytest.raises(RuntimeError, match="pinned"):
        cli._check_pinned_easyocr_wheel([good])
    with pytest.raises(RuntimeError, match="pinned"):
        cli._check_pinned_easyocr_wheel([])


def test_staged_package_verification(env, monkeypatch):
    d = paths.packages_dir() / "wheels"
    d.mkdir(parents=True)
    (d / "easyocr-1.7.2-py3-none-any.whl").write_bytes(b"wheel")
    (d / "checksums.sha256").write_text(
        hashlib.sha256(b"wheel").hexdigest() + "  easyocr-1.7.2-py3-none-any.whl\n"
    )
    # Not trusted until the operator pins the digest outside the volume.
    with pytest.raises(RuntimeError, match="OCR_TRUSTED_WHEELS_SHA256"):
        cli._verify_staged(d)
    monkeypatch.setenv("OCR_TRUSTED_WHEELS_SHA256", cli.staged_digest(d))
    assert len(cli._verify_staged(d)) == 1
    (d / "easyocr-1.7.2-py3-none-any.whl").write_bytes(b"tampered")
    store._hash_cache.clear()
    with pytest.raises(RuntimeError):
        cli._verify_staged(d)


def test_runtime_ensure_noop_without_flags(env, monkeypatch):
    for v in ("OPEN_NOTEBOOK_ENABLE_OCR_TESSERACT", "OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(
        cli, "install_tesseract_runtime", lambda o: pytest.fail("should not install")
    )
    monkeypatch.setattr(
        cli, "install_easyocr_runtime", lambda o: pytest.fail("should not install")
    )
    assert cli.runtime_ensure(offline=False) == 0
    assert (
        paths.tessdata_dir() / "configs" / "tsv"
    ).read_text() == "tessedit_create_tsv 1\n"


def test_runtime_ensure_offline_uses_uv_cache_only_and_degrades(
    env, monkeypatch, tmp_path
):
    """No staged bundle offline: try the local uv cache (--offline), never the network;
    a cache miss is logged and boot continues."""
    import subprocess as sp

    monkeypatch.setenv("OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR", "true")
    monkeypatch.setattr("open_notebook.ocr.runtime.docling_available", lambda: True)
    monkeypatch.setattr("open_notebook.ocr.runtime.module_available", lambda n: False)
    constraints = tmp_path / "c.txt"
    constraints.write_text("easyocr==1.7.2\n")
    monkeypatch.setattr(
        "open_notebook.ocr.runtime.runtime_constraints", lambda: constraints
    )
    calls = []

    def fake_run(cmd, **k):
        calls.append(cmd)
        return sp.CompletedProcess(cmd, 1)  # cache miss

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli.runtime_ensure(offline=True) == 0  # never fails boot
    assert len(calls) == 1
    cmd = calls[0]
    assert "--offline" in cmd and "--find-links" not in cmd
    assert cmd[cmd.index("-c") + 1] == str(constraints)
    assert cmd[-1] == "easyocr==1.7.2"


def test_cli_remove_refuses_when_db_unknown(env, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_active_engine", lambda: None)
    assert cli.main(["remove-model", "tesseract_best"]) == 1
    assert "Refusing" in capsys.readouterr().out


def test_cli_rejects_unknown_engine():
    with pytest.raises(SystemExit):
        cli.main(["install-model", "vietocr"])
    with pytest.raises(SystemExit):
        cli.main(["install-model", "rapidocr"])  # builtin, nothing to install
