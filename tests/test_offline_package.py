"""Offline update package tooling (Phase 12F, scripts/offline/offline_package.py).

MOCK VERIFIED: ``docker`` is a recording fake on PATH (no daemon in CI / Cloud);
git, tar, SHA-256 and ssh-keygen signatures are real. What a real Docker
engine does with these commands is verified on the isolated test stack
(docs/deployment/OFFLINE_UPDATE_UBUNTU_GUIDE.md §Kiểm thử).
"""

from __future__ import annotations

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

IMAGE_ID = "sha256:" + "a" * 64
OLD_ID = "sha256:" + "b" * 64

FAKE_DOCKER = r"""#!/usr/bin/env python3
import json, os, re, sys
state_path = os.environ["FAKE_DOCKER_STATE"]
state = json.load(open(state_path))
argv = sys.argv[1:]
with open(state["log"], "a") as log:
    log.write(json.dumps(argv) + "\n")
def save():
    json.dump(state, open(state_path, "w"))
def out(x):
    sys.stdout.write(x if isinstance(x, str) else json.dumps(x)); sys.stdout.write("\n")
if argv[:2] == ["image", "inspect"]:
    if "--format" in argv:
        ref = argv[-1]
        if ref in state["images"]: out(state["images"][ref]); sys.exit(0)
        sys.exit(1)
    ref = argv[2]
    if ref not in state["images"] and not ref.startswith("sha256:"): sys.exit(1)
    out([{"Id": state["images"].get(ref, ref), "Os": "linux", "Architecture": state.get("arch", "amd64"),
          "Created": "2026-11-17T00:00:00Z", "Config": {"Labels": state.get("labels", {})}}]); sys.exit(0)
if argv[0] == "info":
    fmt = argv[-1]
    out({"{{.Architecture}}": "x86_64", "{{.DockerRootDir}}": state["root"], "{{.OSType}}": "linux"}[fmt]); sys.exit(0)
if argv[0] == "run" and "inventory" in argv:
    out(state["inventory"]); sys.exit(0)
if argv[0] == "tag":
    src, dst = argv[1], argv[2]
    state["images"][dst] = state["images"].get(src, src); save(); sys.exit(0)
if argv[0] == "save":
    path, ref = argv[2], argv[3]
    open(path, "w").write(json.dumps({"tag": ref, "id": state["images"][ref]})); sys.exit(0)
if argv[0] == "load":
    data = json.load(open(argv[2])); state["images"][data["tag"]] = data["id"]; save(); out("Loaded image: " + data["tag"]); sys.exit(0)
if argv[0] == "inspect":
    fmt, cont = argv[2], argv[3]
    c = state["containers"].get(cont)
    if not c: sys.exit(1)
    out(c["image_id"] if fmt == "{{.Image}}" else c["image"]); sys.exit(0)
if argv[0] == "compose":
    files = [argv[i + 1] for i, a in enumerate(argv) if a == "-f"]
    rest = argv[argv.index(files[-1]) + 1:] if files else argv
    def effective():
        cfg = json.loads(json.dumps(state["config"]))
        for f in files:
            text = open(f).read() if os.path.exists(f) else ""
            m = re.search(r"image: (\S+)", text)
            if "image-override" in f and m:
                cfg["services"]["open_notebook"]["image"] = m.group(1)
                cfg["services"]["open_notebook"]["pull_policy"] = "never"
            if "maintenance" in f:
                for p in cfg["services"]["open_notebook"]["ports"]: p["host_ip"] = "127.0.0.1"
            if "evil" in f:
                cfg["services"]["surrealdb"]["image"] = "surrealdb/surrealdb:v3"
        return cfg
    if rest[:1] == ["config"]: out(effective()); sys.exit(0)
    if rest[:2] == ["ps", "-q"]: out("c1" if state["containers"] else ""); sys.exit(0)
    if rest[:2] == ["exec", "-T"]:
        cmd = rest[3:]
        if cmd[:1] == ["cat"]: out(state["version"]); sys.exit(0)
        joined = " ".join(cmd)
        if "get_latest_version" in joined: out(str(state["schema"])); sys.exit(0)
        if "repo_query" in joined: out(str(state["jobs"])); sys.exit(0)
        if "import_rapidocr_weights" in joined: out("{}"); sys.exit(0)
        sys.exit(state.get("exec_rc", 0))
    if rest[:2] == ["up", "-d"]:
        img = effective()["services"]["open_notebook"]["image"]
        state["containers"]["c1"] = {"image": img, "image_id": state["images"].get(img, img)}; save(); sys.exit(0)
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
        "images": {"chatbot5400:local": OLD_ID, "chatbot5400:1.3.0-rc.1": IMAGE_ID},
        "labels": {},
        "containers": {"c1": {"image": "chatbot5400:local", "image_id": OLD_ID}},
        "version": "1.2.0",
        "schema": 33,
        "jobs": 0,
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
            "runtimes_baked": {"docling": True, "easyocr": True, "tesseract": True},
            "runtime_artifacts": {"rapidocr_weights_sha256": {}},
        },
        "config": {
            "services": {
                "open_notebook": {
                    "image": "chatbot5400:local",
                    "ports": [
                        {"target": 8502, "published": "8502", "host_ip": "0.0.0.0"}
                    ],
                },
                "surrealdb": {
                    "image": "surrealdb/surrealdb:v2",
                    "volumes": [{"source": "./surreal_data"}],
                },
            }
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

        def calls(self):
            log = Path(self.get()["log"])
            return (
                [json.loads(x) for x in log.read_text().splitlines()]
                if log.is_file()
                else []
            )

    return Fake()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()

    def git(*a):
        subprocess.run(["git", "-C", str(r), *a], check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.invalid")
    git("config", "user.name", "t")
    (r / "VERSION").write_text("1.2.0\n")
    git("add", ".")
    git("commit", "-qm", "v1.2.0")
    git("tag", "v1.2.0")
    (r / "VERSION").write_text("1.3.0\n")
    (r / "docs" / "deployment").mkdir(parents=True)
    (r / "docs" / "deployment" / "OFFLINE_UPDATE_UBUNTU_GUIDE.md").write_text(
        "# guide\n"
    )
    git("add", ".")
    git("commit", "-qm", "phase 12")
    return r


def _build(repo, tmp_path, *extra):
    out = tmp_path / "dist"
    rc = OP.main(
        [
            "build",
            "--version",
            "1.3.0-rc.1",
            "--image",
            "chatbot5400:1.3.0-rc.1",
            "--repo",
            str(repo),
            "--out",
            str(out),
            *extra,
        ]
    )
    assert rc == 0
    pkg = next(out.glob("*.tar.gz"))
    return pkg, OP.sha256_file(pkg)


@pytest.fixture
def package(fake_docker, repo, tmp_path):
    return _build(repo, tmp_path)


def _verify(pkg, dest, *extra):
    return OP.main(
        [
            "verify",
            str(pkg),
            "--extract-to",
            str(dest),
            "--platform",
            "linux/amd64",
            *extra,
        ]
    )


# --------------------------------------------------------------------------- #
# build + verify
# --------------------------------------------------------------------------- #


def test_build_uses_docker_save_and_git_bundle(package, fake_docker):
    pkg, _ = package
    calls = fake_docker.calls()
    assert any(c[0] == "save" for c in calls)
    assert not any(c[0] in ("export", "push", "pull", "login") for c in calls)
    run_call = next(c for c in calls if c[0] == "run")
    assert run_call[run_call.index("--network") + 1] == "none"
    names = tarfile.open(pkg).getnames()
    top = names[0].split("/")[0]
    for rel in (
        "manifest.json",
        "SHA256SUMS",
        "images/chatbot5400-1.3.0-rc.1.tar",
        "source/chatbot5400-1.3.0-rc.1.bundle",
        "scripts/update.sh",
        "scripts/offline_package.py",
    ):
        assert f"{top}/{rel}" in names
    manifest = json.loads(tarfile.open(pkg).extractfile(f"{top}/manifest.json").read())
    assert manifest["image"]["id"] == IMAGE_ID
    assert manifest["database"] == {
        "schema_version": 33,
        "migration_required": False,
        "compatible_schema_versions": [33],
    }
    assert manifest["readiness"]["status"] == "READY"
    assert manifest["source"]["base_ref"] == "v1.2.0"
    blob = json.dumps(manifest).lower()
    for word in ("password", "api_key", "secret=", ".env"):
        assert word not in blob


def test_verify_with_trusted_hash(package, tmp_path):
    pkg, digest = package
    assert _verify(pkg, tmp_path / "x", "--expected-sha256", digest) == 0
    report = json.loads((tmp_path / "x" / "verify-report.json").read_text())
    assert report["result"] == "VERIFIED"


def test_verify_refuses_without_authenticity(package, tmp_path):
    pkg, _ = package
    assert (
        _verify(pkg, tmp_path / "x", "--allowed-signers", str(tmp_path / "none"))
        == OP.EXIT_VERIFY
    )


def test_verify_refuses_wrong_hash(package, tmp_path):
    pkg, _ = package
    assert _verify(pkg, tmp_path / "x", "--expected-sha256", "0" * 64) == OP.EXIT_VERIFY


def test_verify_refuses_wrong_platform(package, tmp_path):
    pkg, digest = package
    rc = OP.main(
        [
            "verify",
            str(pkg),
            "--extract-to",
            str(tmp_path / "x"),
            "--expected-sha256",
            digest,
            "--platform",
            "linux/arm64",
        ]
    )
    assert rc == OP.EXIT_VERIFY


def test_verify_refuses_unsupported_source_version(package, tmp_path):
    pkg, digest = package
    assert (
        _verify(
            pkg,
            tmp_path / "x",
            "--expected-sha256",
            digest,
            "--current-version",
            "1.0.8",
        )
        == OP.EXIT_VERIFY
    )


def test_verify_refuses_newer_database(package, tmp_path):
    pkg, digest = package
    assert (
        _verify(
            pkg, tmp_path / "x", "--expected-sha256", digest, "--current-schema", "34"
        )
        == OP.EXIT_VERIFY
    )


def _repack(pkg, tmp_path, mutate):
    """Extract (trusted test helper), mutate, repack -> new package + its hash."""
    work = tmp_path / "work"
    with tarfile.open(pkg) as t:
        t.extractall(work, filter="data")
    top = next(work.iterdir())
    mutate(top)
    new = tmp_path / "mutated.tar.gz"
    with tarfile.open(new, "w:gz") as t:
        t.add(top, arcname=top.name)
    return new, OP.sha256_file(new)


def test_verify_detects_corrupted_image(package, tmp_path):
    pkg, _ = package

    def corrupt(top):
        f = top / "images" / "chatbot5400-1.3.0-rc.1.tar"
        f.write_text(f.read_text() + "x")

    new, digest = _repack(pkg, tmp_path, corrupt)
    assert _verify(new, tmp_path / "x", "--expected-sha256", digest) == OP.EXIT_VERIFY


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
    ["traversal", "absolute", "symlink", "hardlink", "two_tops", "device"],
)
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

    pkg = _evil_tar(tmp_path, build)
    dest = tmp_path / "out"
    with pytest.raises(OP.Refused):
        OP.safe_extract(pkg, dest)
    assert not (tmp_path / "etc").exists()
    assert not dest.exists() or not any(dest.rglob("*"))


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


@pytest.mark.skipif(
    shutil.which("ssh-keygen") is None, reason="ssh-keygen not installed"
)
def test_signature_valid_and_invalid(fake_docker, repo, tmp_path):
    key = tmp_path / "release_key"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "test", "-f", str(key)],
        check=True,
    )
    pub = (tmp_path / "release_key.pub").read_text().strip()
    signers = tmp_path / "allowed_signers"
    signers.write_text(f"release@chatbot5400 {pub}\n")
    pkg, _ = _build(repo, tmp_path, "--sign-key", str(key))
    assert _verify(pkg, tmp_path / "ok", "--allowed-signers", str(signers)) == 0
    report = json.loads((tmp_path / "ok" / "verify-report.json").read_text())
    assert report["authenticity"] == ["signature valid"]

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

    def tamper(top):  # manifest changed after signing
        m = json.loads((top / "manifest.json").read_text())
        m["application"]["supported_source_versions"].append("0.0.1")
        (top / "manifest.json").write_text(json.dumps(m))

    new, _ = _repack(pkg, tmp_path / "t", tamper)
    assert (
        _verify(new, tmp_path / "tampered", "--allowed-signers", str(signers))
        == OP.EXIT_VERIFY
    )


# --------------------------------------------------------------------------- #
# preflight / update / rollback against a fake deployment
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


@pytest.fixture
def deployment(tmp_path, package, health_server, monkeypatch):
    pkg, digest = package
    extract = tmp_path / "pkgx"
    assert _verify(pkg, extract, "--expected-sha256", digest) == 0
    pkg_dir = next(p for p in extract.iterdir() if p.is_dir())
    deploy = tmp_path / "deploy"
    deploy.mkdir()
    (deploy / "docker-compose.yml").write_text("services: {}\n")
    (deploy / ".env").write_text("SURREAL_PASSWORD=do-not-read\n")
    maint = tmp_path / "docker-compose.maintenance.yml"
    maint.write_text("services: {}\n")
    conf = tmp_path / "offline-update.conf"
    conf.write_text(
        "\n".join(
            [
                f"DEPLOY_DIR={deploy}",
                "COMPOSE_PROJECT=cb-test",
                "COMPOSE_FILES=docker-compose.yml",
                f"STATE_DIR={tmp_path / 'state'}",
                f"MAINTENANCE_OVERRIDE={maint}",
                f"HEALTH_URL={health_server}",
                "MIN_FREE_GB_EXTRA=0",
            ]
        )
    )
    monkeypatch.setattr(OP.time, "sleep", lambda s: None)
    return conf, pkg_dir, deploy


def _server(cmd, conf, pkg_dir, *extra):
    return OP.main([cmd, "--config", str(conf), "--package-dir", str(pkg_dir), *extra])


def test_preflight_is_read_only(deployment, fake_docker):
    conf, pkg_dir, _ = deployment
    before = len(fake_docker.calls())
    assert _server("preflight", conf, pkg_dir, "--backup-reference", "bk-1") == 0
    new = fake_docker.calls()[before:]
    mutating = {"load", "tag", "rm", "rmi", "save", "push", "pull"}
    assert not any(c[0] in mutating for c in new)
    assert not any(
        "up" in c or "down" in c or "stop" in c for c in new if c[0] == "compose"
    )
    for c in new:
        if c[0] == "compose" and "exec" in c:
            assert "-T" in c  # only read-only probes (version, schema, jobs)


def test_preflight_fails_closed(deployment, fake_docker):
    conf, pkg_dir, _ = deployment
    fake_docker.set(jobs=2)
    assert (
        _server("preflight", conf, pkg_dir, "--backup-reference", "x")
        == OP.EXIT_PREFLIGHT
    )
    fake_docker.set(jobs=0, schema=32)
    assert (
        _server("preflight", conf, pkg_dir, "--backup-reference", "x")
        == OP.EXIT_PREFLIGHT
    )
    fake_docker.set(schema=33, version="1.0.8")
    assert (
        _server("preflight", conf, pkg_dir, "--backup-reference", "x")
        == OP.EXIT_PREFLIGHT
    )


def test_preflight_needs_verified_package(deployment, tmp_path):
    conf, pkg_dir, _ = deployment
    (pkg_dir.parent / "verify-report.json").unlink()
    assert _server("preflight", conf, pkg_dir) == OP.EXIT_PREFLIGHT


def test_update_dry_run_changes_nothing(deployment, fake_docker):
    conf, pkg_dir, _ = deployment
    before = len(fake_docker.calls())
    assert _server("update", conf, pkg_dir, "--backup-reference", "bk") == 0
    assert not any(
        c[0] in ("load", "tag") or "up" in c for c in fake_docker.calls()[before:]
    )


SAFE_UP_TAIL = [
    "up",
    "-d",
    "--no-deps",
    "--no-build",
    "--pull",
    "never",
    "--force-recreate",
    "open_notebook",
]
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


def test_safe_calls_oracle_can_fail():
    """The oracle rejects each dangerous form on its own."""
    base = ["compose", "-p", "x", "-f", "docker-compose.yml"]
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
        ],  # no --no-deps
        base
        + [
            "up",
            "-d",
            "--no-deps",
            "--pull",
            "never",
            "--force-recreate",
            "open_notebook",
        ],  # no --no-build
        base
        + [
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "--force-recreate",
            "open_notebook",
        ],  # no --pull never
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
        base
        + [
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "--pull",
            "never",
            "--force-recreate",
            "surrealdb",
        ],
        base
        + [
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "--pull",
            "never",
            "--force-recreate",
            "open_notebook",
            "surrealdb",
        ],
        base
        + [
            "up",
            "-d",
            "--no-deps",
            "--no-build",
            "--pull",
            "never",
            "--force-recreate",
            "-v",
            "open_notebook",
        ],
        base + ["rm", "-f", "open_notebook"],
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


def test_update_apply_full_flow(deployment, fake_docker, tmp_path):
    conf, pkg_dir, deploy = deployment
    rc = _server(
        "update",
        conf,
        pkg_dir,
        "--apply",
        "--backup-reference",
        "bk-2026-11-17",
        "--backup-verified",
    )
    assert rc == 0
    calls = fake_docker.calls()
    _assert_safe_calls(calls)
    kinds = [c[0] for c in calls]
    assert kinds.index("load") < kinds.index("tag")
    tag_call = next(c for c in calls if c[0] == "tag")
    assert tag_call[1] == OLD_ID and tag_call[2].startswith("chatbot5400:rollback-")
    ups = [c for c in calls if c[0] == "compose" and "up" in c]
    assert len(ups) == 1 and any("maintenance" in x for x in ups[0])
    state = fake_docker.get()
    assert state["containers"]["c1"]["image_id"] == IMAGE_ID
    journal = json.loads((tmp_path / "state" / "journal.json").read_text())
    assert journal["status"] == "awaiting_approval"
    assert [s["step"] for s in journal["steps"]][:4] == [
        "G_load",
        "H_rollback_tag",
        "I_backup",
        "J_backup_verified",
    ]
    override = (tmp_path / "state" / "image-override.yml").read_text()
    assert "pull_policy: never" in override and "OCR_RAPIDOCR_PERSISTENT" in override
    assert (
        deploy / ".env"
    ).read_text() == "SURREAL_PASSWORD=do-not-read\n"  # untouched

    # finish (approval) -> normal mode, without the maintenance override
    assert OP.main(["finish", "--config", str(conf)]) == OP.EXIT_USAGE
    assert OP.main(["finish", "--config", str(conf), "--approve", "owner"]) == 0
    last_up = [c for c in fake_docker.calls() if c[0] == "compose" and "up" in c][-1]
    assert not any("maintenance" in x for x in last_up)

    # rollback to the previous image
    assert (
        OP.main(
            ["rollback", "app", "--config", str(conf), "--package-dir", str(pkg_dir)]
        )
        == 0
    )
    assert fake_docker.get()["containers"]["c1"]["image_id"] == OLD_ID
    _assert_safe_calls(fake_docker.calls())

    # and upgrade again (journal re-used for the same version, image not loaded twice)
    journal = json.loads((tmp_path / "state" / "journal.json").read_text())
    assert journal["status"] == "rolled_back"


def test_update_without_backup_refused_then_resumed(deployment, fake_docker, tmp_path):
    conf, pkg_dir, _ = deployment
    assert (
        _server(
            "update",
            conf,
            pkg_dir,
            "--apply",
            "--no-maintenance",
            "--backup-reference",
            "x",
        )
        == OP.EXIT_UPDATE
    )  # restore not verified
    journal = json.loads((tmp_path / "state" / "journal.json").read_text())
    assert journal["status"] == "in_progress"
    assert not any("up" in c for c in fake_docker.calls() if c[0] == "compose")
    loads = sum(1 for c in fake_docker.calls() if c[0] == "load")
    assert (
        _server(
            "update",
            conf,
            pkg_dir,
            "--apply",
            "--no-maintenance",
            "--backup-reference",
            "x",
            "--backup-verified",
        )
        == 0
    )
    assert (
        sum(1 for c in fake_docker.calls() if c[0] == "load") == loads
    )  # resumed, not reloaded


def test_update_lock(deployment, tmp_path):
    conf, pkg_dir, _ = deployment
    with OP.update_lock(tmp_path / "state"):
        rc = _server(
            "update",
            conf,
            pkg_dir,
            "--apply",
            "--backup-reference",
            "x",
            "--backup-verified",
        )
    assert rc == OP.EXIT_LOCK


def test_failed_health_keeps_maintenance_and_reports(deployment, fake_docker, tmp_path):
    conf, pkg_dir, _ = deployment
    fake_docker.set(exec_rc=1)  # readiness check fails in the new container
    rc = _server(
        "update",
        conf,
        pkg_dir,
        "--apply",
        "--backup-reference",
        "x",
        "--backup-verified",
    )
    assert rc == OP.EXIT_UPDATE
    journal = json.loads((tmp_path / "state" / "journal.json").read_text())
    assert journal["status"] == "failed"
    assert OP.main(["rollback", "interrupted", "--config", str(conf)]) == 0
    assert fake_docker.get()["containers"]["c1"]["image_id"] == OLD_ID


def test_config_change_to_database_refused(deployment, fake_docker, tmp_path):
    conf, _, _ = deployment
    dep = OP.Deployment(OP.load_config(str(conf)))
    before = dep.config_json()
    evil = tmp_path / "evil.yml"
    evil.write_text("x")
    after = dep.config_json([str(evil)])
    with pytest.raises(OP.Refused, match="database"):
        OP.compare_configs(dep, before, after, maintenance=False)


def test_legal_mode_rollback_via_gate(deployment, fake_docker, tmp_path):
    conf, _, _ = deployment
    assert (
        OP.main(["rollback", "legal-off", "--config", str(conf), "--no-maintenance"])
        == 0
    )
    override = (tmp_path / "state" / "image-override.yml").read_text()
    assert 'OCR_LEGAL_NORMALIZATION_ENABLED: "false"' in override
    _assert_safe_calls(fake_docker.calls())


def test_wrapper_scripts_only_delegate():
    for name in (
        "verify-package.sh",
        "preflight.sh",
        "update.sh",
        "rollback.sh",
        "healthcheck.sh",
        "finish.sh",
        "status.sh",
    ):
        text = (ROOT / "scripts" / "offline" / name).read_text()
        assert "exec python3" in text and "rm -" not in text and "down" not in text
