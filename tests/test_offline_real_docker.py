"""Phase 12D5 rehearsal of the offline update tool against a REAL Docker daemon + Compose.

Skipped unless `docker info` works AND CB5400_REAL_DOCKER=1. What it uses for real:
the Docker daemon and its image store (Docker 29 / containerd here: the image ID is
the index digest), `docker build` (BuildKit, real OCI labels), `docker save` /
`docker load` / `docker tag`, Docker Compose (`config`, `ps`, `exec`, `up` with the
operator's files, the maintenance override and the per-attempt override), published
ports, container / volume identity, `docker restart`. What is a STAND-IN: the
application image (busybox: httpd answers the health URL; /app/.venv/bin/python is a
shell script that answers the tool's probes) and the database (busybox httpd serving a
JSON file of record ids from a named volume - the app reads it over the compose
network, as the real app reads SurrealDB).

Everything is created under a unique compose project / image repository and removed
at the end (containers, network, volume, every tag of the repository).
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "offline"))

import offline_package as OP  # noqa: E402


def _docker_ok() -> bool:
    if os.environ.get("CB5400_REAL_DOCKER") != "1" or not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


pytestmark = pytest.mark.skipif(
    not _docker_ok(), reason="real Docker rehearsal: set CB5400_REAL_DOCKER=1 (needs a daemon)"
)

TABLES = ("source", "notebook", "note", "source_embedding", "source_insight")

STAND_IN_PYTHON = r"""#!/bin/sh
# Stand-in for /app/.venv/bin/python of the ChatBot5400 image (rehearsal only):
# answers the probes of scripts/offline/offline_package.py.
if [ "$1" = "/app/scripts/offline/offline_package.py" ] && [ "$2" = "inventory" ]; then
  cat /app/inventory.json; exit 0
fi
case "$*" in
  *FINGERPRINT*)
    data=$(wget -qO- http://surrealdb:8000/records.json) || exit 1
    [ -n "$data" ] || exit 1
    echo "FINGERPRINT $data"; exit 0 ;;
  *get_latest_version*) echo 33; exit 0 ;;
  *"command WHERE"*) echo 0; exit 0 ;;
  *import_rapidocr_weights*) echo '{"copied": {"det.onnx": "existing"}, "on_volume": [["det.onnx", 10]]}'; exit 0 ;;
  *ARTIFACTS*) echo 'ARTIFACTS {"ocr_models": [["tesseract/fast/vie.traineddata", 4, "a2f4"]], "huggingface_hub": []}'; exit 0 ;;
esac
exit 0
"""


def _sh(*cmd, check=True, input_text=None):
    proc = subprocess.run(list(cmd), capture_output=True, text=True, input=input_text)
    if check and proc.returncode != 0:
        raise AssertionError(f"{cmd}: {proc.stdout}{proc.stderr}")
    return proc.stdout.strip()


def _git(repo, *a):
    return _sh("git", "-C", str(repo), *a)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _image_id(ref):
    return _sh("docker", "image", "inspect", "--format", "{{.Id}}", ref)


class Lab:
    """A deployment on the real daemon: operator files, tool configuration, helpers."""

    def __init__(self, tmp: Path) -> None:
        self.id = "rh" + secrets.token_hex(4)
        self.repo_name = f"{self.id}-app"
        self.deploy_tag = f"{self.repo_name}:deploy"
        self.port = _free_port()
        self.tmp = tmp
        self.deploy = tmp / "deploy"
        self.deploy.mkdir()
        self.state = tmp / "state"
        self.backups = tmp / "backups.log"
        (self.deploy / "docker-compose.yml").write_text(
            "services:\n"
            "  open_notebook:\n"
            f"    image: {self.deploy_tag}\n"
            "    environment:\n"
            '      OCR_RAPIDOCR_PERSISTENT: "true"\n'
            '      OCR_OFFLINE: "true"\n'
            "    ports:\n"
            f'      - "{self.port}:5055"\n'
            "    depends_on: [surrealdb]\n"
            "  surrealdb:\n"
            "    image: busybox:1.36\n"
            '    command: ["httpd", "-f", "-p", "8000", "-h", "/data"]\n'
            "    volumes:\n"
            "      - dbdata:/data\n"
            "volumes:\n"
            "  dbdata: {}\n"
        )
        self.maintenance = tmp / "docker-compose.maintenance.yml"
        self.maintenance.write_text(
            "services:\n  open_notebook:\n    ports: !override\n"
            f'      - "127.0.0.1:{self.port}:5055"\n'
        )
        self.conf = tmp / "offline-update.conf"
        values = {
            "DEPLOY_DIR": self.deploy,
            "COMPOSE_PROJECT": self.id,
            "COMPOSE_FILES": "docker-compose.yml",
            "DEPLOY_IMAGE_TAG": self.deploy_tag,
            "IMAGE_REPO": self.repo_name,
            "STATE_DIR": self.state,
            "ALLOWED_SIGNERS": tmp / "no-allowed-signers",
            "MAINTENANCE_OVERRIDE": self.maintenance,
            "BACKUP_CMD": f"echo backup >> {self.backups}",
            "BACKUP_VERIFY_CMD": "true",
            "HEALTH_URL": f"http://127.0.0.1:{self.port}/health",
            "MIN_FREE_GB_EXTRA": "0",
            "JOBS_WAIT_SECONDS": "20",
        }
        self.conf.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
        self.conf.chmod(0o644)

    # --- images -------------------------------------------------------------------
    def build_image(self, version: str, revision: str) -> str:
        ctx = self.tmp / f"ctx-{version}"
        (ctx / "app" / ".venv" / "bin").mkdir(parents=True)
        (ctx / "app" / "www").mkdir()
        (ctx / "app" / "www" / "health").write_text("ok\n")
        (ctx / "app" / "VERSION").write_text(version + "\n")
        (ctx / "app" / ".venv" / "bin" / "python").write_text(STAND_IN_PYTHON)
        (ctx / "app" / "inventory.json").write_text(json.dumps({
            "app_version": version, "schema_version": 33, "python": "3.12",
            "tesseract": "tesseract 5.5.0 (stand-in)",
            "dependencies": {"docling": "stand-in"},
            "runtimes_baked": {"docling": True, "easyocr": True, "tesseract": True,
                               "tiktoken_offline": True},
            "runtime_artifacts": {"tiktoken": {"encoding": "o200k_base", "loads_offline": True}},
        }))  # fmt: skip
        (ctx / "Dockerfile").write_text(
            "FROM busybox:1.36\nCOPY app /app\nRUN chmod 755 /app/.venv/bin/python\n"
            'ENTRYPOINT ["httpd", "-f", "-p", "5055", "-h", "/app/www"]\n'
        )
        ref = f"{self.repo_name}:{version}"
        _sh("docker", "build", "-q", "--label", f"org.opencontainers.image.revision={revision}",
            "--label", f"org.opencontainers.image.version={version}", "-t", ref, str(ctx))  # fmt: skip
        return _image_id(ref)

    # --- the operator's side ------------------------------------------------------
    def compose(self, *a, check=True):
        return _sh("docker", "compose", "-p", self.id, "--project-directory", str(self.deploy),
                   "-f", str(self.deploy / "docker-compose.yml"), *a, check=check)  # fmt: skip

    def container(self, service):
        return self.compose("ps", "-q", service)

    def app_image(self):
        return _sh("docker", "inspect", "--format", "{{.Image}}", self.container("open_notebook"))

    def app_host_ips(self):
        ports = json.loads(_sh("docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}",
                               self.container("open_notebook")))  # fmt: skip
        return sorted({b["HostIp"] for bindings in ports.values() for b in (bindings or [])})

    def set_records(self, **counts):
        raw = {}
        for t in TABLES:
            ids = [f"{t}:{i}" for i in range(1, counts.get(t, 0) + 1)]
            raw[t] = {"ids": ids, "updated": None if t == "source_embedding" else ["u0"] * len(ids)}
        db = self.container("surrealdb")
        _sh("docker", "exec", "-i", db, "sh", "-c", "cat > /data/records.json",
            input_text=json.dumps(raw))  # fmt: skip

    def wait_healthy(self):
        import urllib.request

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for _ in range(100):
            try:
                with opener.open(f"http://127.0.0.1:{self.port}/health", timeout=2) as r:
                    if r.status == 200:
                        return
            except OSError:
                pass
            time.sleep(0.2)

    # --- the tool -------------------------------------------------------------------
    def tool(self, *a):
        return OP.main([a[0], "--config", str(self.conf), *a[1:]])

    def approved(self):
        return json.loads((self.state / "approved.json").read_text())

    def journal(self):
        return json.loads((self.state / "journal.json").read_text())

    def cleanup(self):
        self.compose("down", "-v", "--remove-orphans", check=False)  # the TEST's own project
        tags = _sh("docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}",
                   self.repo_name, check=False).split()  # fmt: skip
        for tag in tags:
            subprocess.run(["docker", "rmi", "-f", tag], capture_output=True)


@pytest.fixture
def lab(tmp_path, monkeypatch):
    real_sleep = time.sleep
    # the tool retries its health URL every 5 s; 0.5 s is enough for busybox httpd
    monkeypatch.setattr(OP.time, "sleep", lambda s: real_sleep(min(s, 0.5)))
    lab = Lab(tmp_path)
    monkeypatch.setenv("CB5400_OFFLINE_CONFIG", str(lab.conf))
    try:
        yield lab
    finally:
        lab.cleanup()


def _repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    (repo / "VERSION").write_text("1.2.0\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "v1.2.0")
    _git(repo, "tag", "v1.2.0")
    (repo / "VERSION").write_text("1.3.0\n")
    # every package carries the manual procedure (Phase 12D5): the real one
    docs = repo / "docs" / "deployment"
    docs.mkdir(parents=True)
    for name in ("OFFLINE_UPDATE_MANUAL_FALLBACK.md", "OFFLINE_UPDATE_INTEGRATION_CONTRACT.md"):
        shutil.copy2(ROOT / "docs" / "deployment" / name, docs / name)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "v1.3.0")
    return repo


@pytest.mark.timeout(600)
def test_real_docker_rehearsal(lab, tmp_path):
    """The whole cycle on the real daemon. Each `# real:` comment names what it proves."""
    repo = _repo(tmp_path)
    commit = _git(repo, "rev-parse", "HEAD")
    old_id = lab.build_image("1.2.0", _git(repo, "rev-parse", "v1.2.0"))
    new_id = lab.build_image("1.3.0", commit)
    _sh("docker", "tag", f"{lab.repo_name}:1.2.0", lab.deploy_tag)  # the operator's approved tag
    lab.compose("up", "-d")
    lab.wait_healthy()
    db_id = lab.container("surrealdb")
    lab.set_records(source=3, notebook=1, note=2, source_embedding=6)
    assert lab.app_image() == old_id and "0.0.0.0" in lab.app_host_ips()

    # --- build (real docker save, real labels) and verify ----------------------------
    out = tmp_path / "dist"
    assert OP.main(["build", "--version", "1.3.0", "--image", f"{lab.repo_name}:1.3.0",
                    "--image-repo", lab.repo_name, "--repo", str(repo), "--out", str(out)]) == 0  # fmt: skip
    pkg = next(out.glob("*.tar.gz"))
    manifest = json.loads(_sh("tar", "-xzOf", str(pkg), f"{pkg.name[:-7]}/manifest.json"))
    image = manifest["image"]
    assert image["id"] == new_id and image["provenance"] == "verified"
    assert image["labels"]["org.opencontainers.image.revision"] == commit
    # real: the containerd store's image ID is NOT the config digest
    store = "containerd" if image["id"] != image["config_digest"] else "classic"
    # real: the run configuration hashed from the archive == from `docker image inspect`
    assert OP.local_run_config(f"{lab.repo_name}:1.3.0") == image["run_config_sha256"]
    _sh("docker", "rmi", f"{lab.repo_name}:1.3.0")  # the server gets it only by docker load
    digest = OP.sha256_file(pkg)
    assert OP.main(["verify", str(pkg), "--extract-to", str(tmp_path / "pkgx"),
                    "--expected-sha256", digest, "--platform", "linux/amd64"]) == 0  # fmt: skip
    pkg_dir = next(p for p in (tmp_path / "pkgx").iterdir() if p.is_dir())
    assert (lab.state / "verified" / f"{digest}.json").is_file()

    # --- preflight (the contract) and update -------------------------------------------
    assert lab.tool("preflight", "--package-dir", str(pkg_dir)) == 0
    assert lab.tool("update", "--package-dir", str(pkg_dir), "--apply") == 0
    loaded_id = _image_id(manifest["image"]["tag"])
    assert lab.app_image() == loaded_id
    assert lab.app_host_ips() == ["127.0.0.1"]  # real: maintenance ports bound to loopback
    assert lab.container("surrealdb") == db_id  # real: --no-deps kept the database container
    assert lab.backups.read_text().count("backup") == 1
    assert _image_id(lab.deploy_tag) == old_id  # the update never moves the deploy tag
    assert lab.approved()["how"] == "adopted" and lab.approved()["image_id"] == old_id
    journal = lab.journal()
    assert journal["status"] == "awaiting_approval"
    identified_by = journal["steps"][0]["identified_by"]

    # real: a plain `docker compose up -d` during acceptance starts the APPROVED image
    lab.compose("up", "-d")
    lab.wait_healthy()
    assert lab.app_image() == old_id and "0.0.0.0" in lab.app_host_ips()
    assert lab.container("surrealdb") == db_id
    assert lab.tool("status") == OP.EXIT_DRIFT  # the attempt's new image is gone: reported

    # --- finish: the deploy tag moves; the operator's files alone start the new image -----
    assert lab.tool("finish", "--approve", "rehearsal") == 0
    assert _image_id(lab.deploy_tag) == loaded_id
    assert lab.app_image() == loaded_id and "0.0.0.0" in lab.app_host_ips()
    assert lab.approved()["how"] == "finish"
    app_container = lab.container("open_notebook")
    lab.compose("up", "-d")  # real: plain compose up keeps it (nothing to recreate)
    assert lab.container("open_notebook") == app_container and lab.app_image() == loaded_id
    _sh("docker", "restart", app_container)  # real: docker restart keeps the image
    lab.wait_healthy()
    assert lab.app_image() == loaded_id and lab.container("surrealdb") == db_id
    command = (lab.state / "compose-command.txt").read_text()
    subprocess.run(["bash", "-c", command], check=True, capture_output=True)  # recorded command
    lab.wait_healthy()
    assert lab.app_image() == loaded_id
    assert lab.tool("status") == 0
    assert lab.tool("health") == 0

    # --- data written after the update is not a loss ----------------------------------
    lab.set_records(source=4, notebook=1, note=2, source_embedding=8)

    # --- rollback: the deploy tag goes back; every start path follows -------------------
    assert lab.tool("rollback", "app", "--no-maintenance") == 0
    assert _image_id(lab.deploy_tag) == old_id and lab.app_image() == old_id
    assert lab.approved()["how"] == "rollback"
    lab.compose("up", "-d")
    assert lab.app_image() == old_id and lab.container("surrealdb") == db_id
    assert lab.tool("status") == 0

    # --- a refused update leaves the approved deployment untouched ----------------------
    lab.conf.write_text(lab.conf.read_text().replace(f"echo backup >> {lab.backups}", "false"))
    approved = lab.approved()
    assert lab.tool("update", "--package-dir", str(pkg_dir), "--apply") == OP.EXIT_UPDATE
    assert lab.approved() == approved and _image_id(lab.deploy_tag) == old_id
    assert lab.app_image() == old_id and lab.app_host_ips() == ["127.0.0.1"]  # quiesced
    lab.compose("up", "-d")  # the operations script: the approved image, normal mode
    lab.wait_healthy()
    assert lab.app_image() == old_id and "0.0.0.0" in lab.app_host_ips()
    assert lab.tool("status") == OP.EXIT_UNDECIDED  # the open attempt is reported
    assert lab.tool("rollback", "interrupted") == 0
    assert lab.tool("status") == 0

    # --- the second update: its own attempt, its own backup ---------------------------
    lab.conf.write_text(lab.conf.read_text().replace("BACKUP_CMD=false", f"BACKUP_CMD=echo backup >> {lab.backups}"))
    assert lab.tool("update", "--package-dir", str(pkg_dir), "--apply") == 0
    assert lab.backups.read_text().count("backup") == 2
    assert lab.tool("finish", "--approve", "rehearsal") == 0
    assert _image_id(lab.deploy_tag) == loaded_id and lab.app_image() == loaded_id
    assert lab.container("surrealdb") == db_id  # one database container all along
    assert lab.tool("status") == 0
    print(f"REAL DOCKER: {_sh('docker', 'version', '--format', '{{.Server.Version}}')} "
          f"compose {_sh('docker', 'compose', 'version', '--short')} store {store} "
          f"identified by {identified_by!r}")  # fmt: skip
