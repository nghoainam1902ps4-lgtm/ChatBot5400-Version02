"""Phase 12D13 / D12-L1 - the candidate restores RapidOCR's dictionary offline.

Unit controls with the real Windows-verified helper (scripts/offline/rb1) and a
synthetic package folder; the runtime / model identity checks are replaced by
probes (the real pinned stack is exercised on Docker Desktop, see
docs/review/PHASE12D13_RB1_HARDENING_REPORT.md). No network, no model.
"""

import os
import runpy
from pathlib import Path

import pytest

from open_notebook.ocr import rapidocr_dictionary as rd

posix = pytest.mark.skipif(os.name != "posix", reason="atomic POSIX installation")


@pytest.fixture
def rig(tmp_path, monkeypatch):
    helper = runpy.run_path(str(rd.HELPER))
    manifest = helper["load_manifest"](rd.MANIFEST)
    asset = manifest["assets"]["dictionary"]
    package = tmp_path / "site" / "rapidocr"
    (package / "models").mkdir(parents=True)
    target = package / "models" / asset["file"]
    weights = tmp_path / "weights.pth"
    weights.write_bytes(b"synthetic")
    state = {"refuse": None}

    def check_runtime(_m):
        if state["refuse"]:
            raise helper["Refuse"](*state["refuse"])
        return {"pkg": package, "yaml": package / "default_models.yaml"}

    helper.update(
        check_runtime=check_runtime,
        check_model=lambda *_: {"dict_url": asset["source_url"], "weights": weights},
        resolve_target=lambda *_: target,
    )
    monkeypatch.setattr(rd, "_helper", helper)
    monkeypatch.setattr(rd, "_verified", None)
    return helper, asset, target, state


@posix
def test_recreated_container_gets_the_approved_dictionary_back(rig, monkeypatch):
    _helper, asset, target, _state = rig
    monkeypatch.setenv("OCR_OFFLINE", "true")
    source = (rd.RB1 / asset["source_relative_path"]).read_bytes()
    assert not target.exists()
    assert rd.ensure_dictionary() == "restored"
    assert target.read_bytes() == source
    assert oct(target.stat().st_mode & 0o777) == oct(int(asset["mode"], 8))
    assert rd.ensure_dictionary() == "cached"
    target.unlink()  # a recreate: the container layer is new
    assert rd.ensure_dictionary() == "restored"
    assert target.read_bytes() == source


@posix
def test_offline_refusal_stops_the_conversion_and_downloads_nothing(rig, monkeypatch):
    _helper, _asset, target, state = rig
    monkeypatch.setenv("OCR_OFFLINE", "true")
    target.write_bytes(b"dictionary of unknown origin")
    with pytest.raises(ValueError, match="OCR_OFFLINE=true"):
        rd.ensure_dictionary()
    assert target.read_bytes() == b"dictionary of unknown origin"  # not overwritten
    target.unlink()
    state["refuse"] = (3, "rapidocr 3.9.3 != manifest 3.9.2")
    with pytest.raises(ValueError, match="helper code 3"):
        rd.ensure_dictionary()
    assert not target.exists()


@posix
def test_online_refusal_keeps_upstream_behaviour(rig, monkeypatch):
    _helper, _asset, target, state = rig
    monkeypatch.delenv("OCR_OFFLINE", raising=False)
    state["refuse"] = (4, "weights not prepared yet")
    assert rd.ensure_dictionary() == "not applicable"
    assert not target.exists()


@posix
def test_concurrent_install_by_another_process_is_accepted(rig, monkeypatch):
    helper, asset, target, _state = rig
    monkeypatch.setenv("OCR_OFFLINE", "true")
    real = helper["restore"]

    def racing(src, dst, a, apply):
        if apply and not dst.exists():
            real(src, dst, a, True)  # the worker installed it first
            raise helper["Refuse"](6, "appeared during the restore")
        return real(src, dst, a, apply)

    helper["restore"] = racing
    assert rd.ensure_dictionary() == "already valid"
    assert target.read_bytes() == (rd.RB1 / asset["source_relative_path"]).read_bytes()


def test_rapidocr_options_restore_the_dictionary_before_rapidocr_starts(monkeypatch):
    pytest.importorskip("docling")
    from open_notebook.ocr import options

    calls = []
    monkeypatch.setattr(rd, "ensure_dictionary", lambda: calls.append("dictionary"))
    built = options.build_ocr_options("rapidocr")
    assert calls == ["dictionary"]
    assert type(built).__name__ == "RapidOcrOptions"
    monkeypatch.setattr(
        rd, "ensure_dictionary", lambda: (_ for _ in ()).throw(ValueError("refused"))
    )
    with pytest.raises(ValueError, match="refused"):
        options.build_ocr_options("rapidocr")


def test_the_candidate_uses_the_same_approved_artifact_as_the_rollback():
    from scripts.offline import offline_package as package

    for name in (
        "restore_rapidocr_assets.py",
        "manifest.json",
        "assets/rapidocr/ppocrv6_dict.txt",
    ):
        size, sha = package.RB1_PINNED[name]
        path = rd.RB1 / name
        assert path.stat().st_size == size
        assert package.sha256_file(path) == sha
    entry = (
        Path(rd.__file__).resolve().parents[2] / "scripts" / "docker-entrypoint.sh"
    ).read_text()
    restore = entry.index("open_notebook.ocr.rapidocr_dictionary")
    assert entry.index("Installing Docling") < restore < entry.index('exec "$@"')
