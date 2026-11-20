"""Offline rollback integration controls. Docker deployments are represented by probes."""

import hashlib
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.offline import offline_package as package
from scripts.offline import rb1_setup as setup
from scripts.offline.rb1 import runtime_gate

ASSETS = Path(setup.__file__).with_name("rb1")
IMAGE = "sha256:" + "a" * 64
APP = "b" * 64


def test_package_allowlist_checks_all_approved_bytes(tmp_path):
    package.rb1_artifacts(ASSETS)
    for name in package.RB1_FILES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ASSETS / name).read_bytes())
    dictionary = tmp_path / "assets/rapidocr/ppocrv6_dict.txt"
    raw = dictionary.read_bytes()
    dictionary.unlink()
    with pytest.raises(package.Refused, match="missing"):
        package.rb1_artifacts(tmp_path)
    dictionary.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
    with pytest.raises(package.Refused, match="approved bytes"):
        package.rb1_artifacts(tmp_path)


@pytest.mark.skipif(os.name != "posix", reason="atomic POSIX dictionary installation")
def test_runtime_gate_verifies_models_and_restores_exact_dictionary(
    tmp_path, monkeypatch
):
    from open_notebook.ocr import paths

    implementation = runpy.run_path(str(ASSETS / "restore_rapidocr_assets.py"))
    manifest = implementation["load_manifest"](ASSETS / "manifest.json")
    (tmp_path / "VERSION").write_text("1.2.0\n")
    weights = tmp_path / "data" / "ocr" / "rapidocr"
    weights.mkdir(parents=True)
    model = manifest["recognition_model"]
    for item in (model, *manifest["related_models_verified_only"]):
        file = weights / item["file"]
        file.write_bytes(b"synthetic weights")
        item.update(
            size=file.stat().st_size,
            sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
        )
    recognizer = tmp_path / "package" / "ch_ppocr_rec" / "main.py"
    recognizer.parent.mkdir(parents=True)
    recognizer.write_text("# synthetic recognizer\n")
    manifest["runtime"]["recognizer_source_sha256"] = hashlib.sha256(
        recognizer.read_bytes()
    ).hexdigest()
    asset = manifest["assets"]["dictionary"]
    target = tmp_path / "package" / asset["file"]
    monkeypatch.setenv("OCR_RAPIDOCR_PERSISTENT", "true")
    monkeypatch.setenv("OCR_OFFLINE", "true")
    monkeypatch.setattr(paths, "rapidocr_dir", lambda: weights)
    monkeypatch.setattr(
        runtime_gate, "Path", lambda path: tmp_path / path.removeprefix("/app/")
    )
    monkeypatch.setattr(runtime_gate, "version", lambda _: "2.14.0+cpu")
    implementation.update(
        check_runtime=lambda _: {
            "pkg": recognizer.parents[1],
            "yaml": tmp_path / "unused",
        },
        check_model=lambda *_: {
            "weights": weights / model["file"],
            "dict_url": asset["source_url"],
        },
        resolve_target=lambda *_: target,
    )
    assert runtime_gate.check(implementation, manifest) == "missing - would restore"
    assert not target.exists()
    assert runtime_gate.verdict(implementation, manifest, tmp_path / "missing") == 5
    assert runtime_gate.check(implementation, manifest, ASSETS) == "restored"
    assert target.read_bytes() == (ASSETS / asset["source_relative_path"]).read_bytes()
    assert runtime_gate.check(implementation, manifest, ASSETS) == "already valid"
    target.write_bytes(b"unknown dictionary")
    assert runtime_gate.verdict(implementation, manifest, ASSETS) == 6
    assert target.read_bytes() == b"unknown dictionary"
    (weights / model["file"]).write_bytes(b"wrong size")
    assert runtime_gate.verdict(implementation, manifest, ASSETS) == 4
    monkeypatch.setattr(runtime_gate, "version", lambda _: "2.14.0+other")
    assert runtime_gate.verdict(implementation, manifest, ASSETS) == 3


@pytest.mark.skipif(os.name != "posix", reason="Linux target staging")
def test_signed_payload_stage_is_external_and_compose_mount_is_readonly(tmp_path):
    dest = tmp_path / "permanent"
    setup.stage_assets(ASSETS, dest, "app", IMAGE, "chatbot5400:local")
    config = json.loads((dest / "compose.json").read_text())["services"]["app"]
    assert config["entrypoint"] == setup.ENTRYPOINT
    assert config["command"] == []
    assert config["pull_policy"] == "never"
    assert config["volumes"][0]["source"] == str(dest)
    assert config["volumes"][0]["read_only"]
    package.rb1_artifacts(dest)
    fake = tmp_path / "docker"
    fake.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_IMAGE"\n')
    fake.chmod(0o755)
    select = ["/bin/sh", str(dest / "select-compose.sh")]
    environment = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ["PATH"])
    assert subprocess.check_output(
        select, env=dict(environment, TEST_IMAGE=IMAGE), text=True
    ).strip() == str(dest / "compose.json")
    assert not subprocess.check_output(
        select, env=dict(environment, TEST_IMAGE="sha256:" + "c" * 64)
    )
    assert subprocess.run(select, env=dict(environment, TEST_IMAGE="")).returncode != 0
    with pytest.raises(package.Refused, match="new absolute"):
        setup.stage_assets(ASSETS, dest, "app", IMAGE, "chatbot5400:local")


@pytest.mark.parametrize(
    ("live", "fresh", "verdict"),
    [
        ("already valid", "missing - would restore", "A-valid"),
        ("missing - would restore", "missing - would restore", "B-recoverable"),
        ("already valid", "REFUSED", None),
        ("REFUSED", None, None),
    ],
)
def test_preflight_requires_runtime_and_fresh_offline_cache(
    monkeypatch, live, fresh, verdict
):
    model = {
        "Image": IMAGE,
        "State": {"Running": True},
        "Config": {
            "Env": [
                "OCR_OFFLINE=true",
                "OCR_RAPIDOCR_PERSISTENT=true",
                "OPEN_NOTEBOOK_ENABLE_DOCLING=true",
                "UNRELATED_SECRET=synthetic-never-forwarded",
            ]
        },
        "Mounts": [{"Destination": "/app/data", "Type": "volume", "Name": "lab_data"}],
    }
    monkeypatch.setattr(
        package,
        "docker_inspect_image",
        lambda ref: {"Id": IMAGE, "Config": {"Entrypoint": [setup.STOCK]}},
    )
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[1] == "inspect":
            return SimpleNamespace(stdout=json.dumps([model]))
        assert kwargs["input_text"].startswith("import hashlib, json")
        result = live if args[1] == "exec" else fresh
        return SimpleNamespace(
            returncode=3 if result == "REFUSED" else 0,
            stdout="RB1 " + json.dumps({"result": result}),
        )

    monkeypatch.setattr(package, "run", run)
    if verdict is None:
        with pytest.raises(package.Refused, match="could not be verified"):
            setup.preflight(ASSETS, APP, IMAGE, "chatbot5400:local")
    else:
        assert setup.preflight(ASSETS, APP, IMAGE, "chatbot5400:local") == verdict
    if live != "REFUSED":
        assert ["--pull", "never", "--network", "none"] == calls[-1][3:7]
        assert "type=volume,source=lab_data,target=/app/data,readonly" in calls[-1]
        assert all("UNRELATED_SECRET" not in arg for arg in calls[-1])


@pytest.mark.skipif(os.name != "posix", reason="POSIX startup contract")
def test_startup_runs_after_stock_entrypoint_and_fail_closed(tmp_path):
    trace = tmp_path / "trace"
    stock = tmp_path / "entrypoint.sh"
    stock.write_text('#!/bin/sh\necho runtime >> "$TRACE"\nexec "$@"\n')
    stock.chmod(0o755)
    supervisor = tmp_path / "supervisord"
    supervisor.write_text('#!/bin/sh\necho supervisor >> "$TRACE"\n')
    supervisor.chmod(0o755)
    gate = tmp_path / "runtime_gate.py"
    gate.write_text(
        'import os, sys\nassert sys.argv[1:] == ["--apply"]\nwith open(os.environ["TRACE"], "a") as f:\n    f.write("helper\\n")\nraise SystemExit(int(os.environ.get("FAIL_HELPER", "0")))\n'
    )
    startup = tmp_path / "startup.sh"
    startup.write_text(
        (ASSETS / "startup.sh")
        .read_text()
        .replace(setup.MOUNT, str(tmp_path))
        .replace(setup.STOCK_SHA, hashlib.sha256(stock.read_bytes()).hexdigest())
        .replace(setup.STOCK, str(stock))
        .replace(setup.PYTHON, sys.executable)
        .replace("/usr/bin/supervisord", str(supervisor))
    )
    env = dict(
        os.environ,
        TRACE=str(trace),
        OCR_OFFLINE="true",
        OCR_RAPIDOCR_PERSISTENT="true",
        OPEN_NOTEBOOK_ENABLE_DOCLING="true",
        OPEN_NOTEBOOK_ENABLE_CRAWL4AI="false",
    )
    for _ in range(3):
        subprocess.run(["/bin/sh", str(startup)], env=env, check=True)
    assert trace.read_text().splitlines() == ["runtime", "helper", "supervisor"] * 3
    trace.unlink()
    assert (
        subprocess.run(
            ["/bin/sh", str(startup)], env=dict(env, FAIL_HELPER="5")
        ).returncode
        == 5
    )
    assert trace.read_text().splitlines() == ["runtime", "helper"]
    trace.unlink()
    assert (
        subprocess.run(
            ["/bin/sh", str(startup)], env=dict(env, OCR_OFFLINE="false")
        ).returncode
        == 3
    )
    assert not trace.exists()
