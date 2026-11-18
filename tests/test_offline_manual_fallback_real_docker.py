"""Rehearsal of the MANUAL offline update (docs/deployment/OFFLINE_UPDATE_MANUAL_FALLBACK.md)
on a REAL Docker daemon with stand-in images (Phase 12D5).

What this proves: the Docker / Compose commands of the procedure behave as the
document says - an archive authenticated by SHA-256 loads with its labels; moving
the deployment tag and recreating ONLY the application (``--no-deps``) switches
the image while the database container keeps its ID and its volume its data; the
maintenance override binds loopback only; a plain ``docker compose up -d`` and a
``docker restart`` keep the image the tag points to; rolling back is moving the
tag back. What it does NOT prove (LOCAL VERIFICATION REQUIRED): the real operations
script, boot guard, SurrealDB, application image and production Docker.

Opt-in: ``CB5400_REAL_DOCKER=1`` and a working ``docker info``. Only
``busybox:1.36`` is needed (images are made with ``docker commit``, no build, no
pull). Everything it creates carries a unique project name and is removed.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest


def _docker_ok() -> bool:
    if os.environ.get("CB5400_REAL_DOCKER") != "1" or not shutil.which("docker"):
        return False
    try:
        return (
            subprocess.run(
                ["docker", "image", "inspect", "busybox:1.36"],
                capture_output=True,
                timeout=30,
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


pytestmark = pytest.mark.skipif(
    not _docker_ok(),
    reason="real Docker rehearsal: set CB5400_REAL_DOCKER=1 (needs docker and busybox:1.36)",
)


def sh(*argv: str, check: bool = True, timeout: int = 300) -> str:
    proc = subprocess.run(
        list(argv), capture_output=True, text=True, timeout=timeout, check=False
    )
    if check and proc.returncode != 0:
        raise AssertionError(f"{argv} -> {proc.returncode}: {proc.stderr[-2000:]}")
    return proc.stdout.strip()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_image(tag: str, version: str, revision: str, work: Path) -> str:
    www = work / f"www-{version}"
    www.mkdir()
    (www / "health").write_text("ok\n")
    (www / "version").write_text(version + "\n")
    cid = sh("docker", "create", "busybox:1.36", "true")
    try:
        sh("docker", "cp", f"{www}/.", f"{cid}:/www")
        sh(
            "docker", "commit",
            "--change", f"LABEL org.opencontainers.image.revision={revision}",
            "--change", f"LABEL org.opencontainers.image.version={version}",
            "--change", 'CMD ["httpd", "-f", "-p", "8502", "-h", "/www"]',
            cid, tag,
        )  # fmt: skip
    finally:
        sh("docker", "rm", "-f", cid, check=False)
    return sh("docker", "image", "inspect", "--format", "{{.Id}}", tag)


class Lab:
    def __init__(self, work: Path):
        self.id = "fb" + secrets.token_hex(4)
        self.work = work
        self.repo = f"{self.id}-app"
        self.deploy_tag = f"{self.repo}:local"
        self.port = _free_port()
        self.dir = work / "deploy"
        self.dir.mkdir()
        (self.dir / "docker-compose.yml").write_text(
            "services:\n"
            "  app:\n"
            f"    image: {self.deploy_tag}\n"
            "    pull_policy: never\n"
            "    restart: unless-stopped\n"
            f'    ports: ["{self.port}:8502"]\n'
            "    depends_on: [db]\n"
            "  db:\n"
            "    image: busybox:1.36\n"
            '    command: ["sh", "-c", "while true; do sleep 3600; done"]\n'
            "    restart: unless-stopped\n"
            "    volumes: [dbdata:/data]\n"
            "volumes:\n"
            "  dbdata: {}\n"
        )
        (self.dir / "maintenance.yml").write_text(
            f'services:\n  app:\n    ports: !override ["127.0.0.1:{self.port}:8502"]\n'
        )

    def dc(self, *args: str, maint: bool = False) -> str:
        # ABSOLUTE file paths: compose resolves -f against the current directory,
        # not --project-directory (a relative path would pick another project).
        names = ["docker-compose.yml"] + (["maintenance.yml"] if maint else [])
        files = [x for n in names for x in ("-f", str(self.dir / n))]
        return sh(
            "docker", "compose", "--project-directory", str(self.dir), "-p", self.id,
            *files, *args, timeout=600,
        )  # fmt: skip

    def recreate_app(self, maint: bool) -> None:
        # the command of the procedure, §7.3 / §9 / §10.1
        self.dc(
            "up", "-d", "--no-deps", "--no-build", "--pull", "never",
            "--force-recreate", "app", maint=maint,
        )  # fmt: skip

    def cid(self, service: str) -> str:
        return self.dc("ps", "-q", service)

    def image_of(self, service: str) -> str:
        return sh("docker", "inspect", "--format", "{{.Image}}", self.cid(service))

    def tag_id(self) -> str:
        return sh("docker", "image", "inspect", "--format", "{{.Id}}", self.deploy_tag)

    def host_ips(self) -> list[str]:
        out = sh("docker", "port", self.cid("app"), "8502/tcp")
        return sorted({line.rsplit(":", 1)[0].strip("[]") for line in out.splitlines()})

    def health(self) -> str:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        last = None
        for _ in range(60):
            try:
                with opener.open(
                    f"http://127.0.0.1:{self.port}/version", timeout=2
                ) as r:
                    return r.read().decode().strip()
            except OSError as e:
                last = e
                time.sleep(0.5)
        raise AssertionError(f"app not answering on {self.port}: {last}")

    def db_identity(self) -> tuple:
        cid = self.cid("db")
        return (
            cid,
            sh("docker", "inspect", "--format", "{{.Image}}", cid),
            sh("docker", "inspect", "--format", "{{json .Mounts}}", cid),
        )

    def db_marker(self) -> str:
        return sh("docker", "exec", self.cid("db"), "cat", "/data/marker")

    def cleanup(self) -> None:
        ids = sh(
            "docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={self.id}",
            check=False,
        ).split()  # fmt: skip
        if ids:
            sh("docker", "rm", "-f", *ids, check=False)
        sh("docker", "volume", "rm", f"{self.id}_dbdata", check=False)
        sh("docker", "network", "rm", f"{self.id}_default", check=False)
        refs = sh(
            "docker", "image", "ls", "--format", "{{.Repository}}:{{.Tag}}", self.repo,
            check=False,
        ).split()  # fmt: skip
        if refs:
            sh("docker", "rmi", "-f", *refs, check=False)


@pytest.fixture
def lab(tmp_path):
    lab = Lab(tmp_path)
    try:
        yield lab
    finally:
        lab.cleanup()


def test_manual_procedure_update_restart_and_rollback(lab, tmp_path):
    rev_old, rev_new = "a" * 40, "b" * 40
    # --- the server runs 1.2.0 under the deployment tag ------------------------
    old_id = _make_image(f"{lab.repo}:1.2.0", "1.2.0", rev_old, tmp_path)
    sh("docker", "tag", old_id, lab.deploy_tag)
    lab.dc("up", "-d")
    sh("docker", "exec", lab.cid("db"), "sh", "-c", "echo records-1-2-3 > /data/marker")
    assert lab.health() == "1.2.0"
    db_before = lab.db_identity()

    # --- §2 build machine: docker save, package SHA-256 sent separately --------
    new_built = _make_image(f"{lab.repo}:1.3.0", "1.3.0", rev_new, tmp_path)
    archive = tmp_path / "pkg" / "images" / f"{lab.repo}-1.3.0.tar"
    archive.parent.mkdir(parents=True)
    sh("docker", "save", "-o", str(archive), f"{lab.repo}:1.3.0")
    sh("docker", "rmi", f"{lab.repo}:1.3.0")  # the server does not have it
    trusted = hashlib.sha256(archive.read_bytes()).hexdigest()

    # --- §3 authenticate BEFORE use: sha256sum -c of the trusted value --------
    check = subprocess.run(
        ["sha256sum", "-c", "-"],
        input=f"{trusted}  {archive.name}\n",
        cwd=archive.parent, capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert check.returncode == 0 and check.stdout.strip().endswith(": OK")
    tampered = archive.with_name("tampered.tar")
    data = bytearray(archive.read_bytes())
    data[len(data) // 2] ^= 1
    tampered.write_bytes(bytes(data))
    bad = subprocess.run(
        ["sha256sum", "-c", "-"],
        input=f"{trusted}  {tampered.name}\n",
        cwd=archive.parent, capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert bad.returncode != 0  # the procedure stops here, nothing is loaded

    # --- §4 record: the running app is what the tag points to -----------------
    assert lab.image_of("app") == lab.tag_id() == old_id

    # --- §5 load, labels, rollback name ---------------------------------------
    out = sh("docker", "load", "-i", str(archive))
    assert f"Loaded image: {lab.repo}:1.3.0" in out
    new_id = sh(
        "docker", "image", "inspect", "--format", "{{.Id}}", f"{lab.repo}:1.3.0"
    )
    assert new_id != old_id
    labels = sh(
        "docker", "image", "inspect", "--format",
        '{{index .Config.Labels "org.opencontainers.image.revision"}} '
        '{{index .Config.Labels "org.opencontainers.image.version"}}',
        f"{lab.repo}:1.3.0",
    )  # fmt: skip
    assert labels == f"{rev_new} 1.3.0"
    sh("docker", "tag", old_id, f"{lab.repo}:rollback-before-1.3.0")
    assert lab.image_of("app") == old_id  # nothing changed for the users yet
    del new_built

    # --- §6 maintenance on the OLD image: loopback only, DB untouched ----------
    lab.recreate_app(maint=True)
    assert lab.image_of("app") == old_id and lab.host_ips() == ["127.0.0.1"]
    assert lab.db_identity() == db_before

    # --- §7 move the deployment tag, recreate ONLY the app in maintenance -----
    sh("docker", "tag", f"{lab.repo}:1.3.0", lab.deploy_tag)
    assert lab.tag_id() == new_id
    lab.recreate_app(maint=True)
    assert lab.image_of("app") == new_id and lab.host_ips() == ["127.0.0.1"]
    assert lab.health() == "1.3.0"
    assert lab.db_identity() == db_before and lab.db_marker() == "records-1-2-3"

    # --- §9 normal mode: same image, published again --------------------------
    lab.recreate_app(maint=False)
    app_cid = lab.cid("app")
    assert lab.image_of("app") == new_id and "127.0.0.1" not in lab.host_ips()
    # every other start path keeps the image the tag points to
    lab.dc("up", "-d")  # a plain compose up (operations script, boot guard)
    assert lab.cid("app") == app_cid and lab.image_of("app") == new_id
    sh("docker", "restart", app_cid)
    assert lab.image_of("app") == new_id and lab.health() == "1.3.0"
    lab.dc("up", "-d", "--force-recreate", "--no-deps", "app")  # a recreate
    assert lab.image_of("app") == new_id
    assert lab.db_identity() == db_before and lab.db_marker() == "records-1-2-3"

    # --- §10.1 rollback = move the tag back, recreate the app -----------------
    sh("docker", "tag", f"{lab.repo}:rollback-before-1.3.0", lab.deploy_tag)
    assert lab.tag_id() == old_id
    lab.recreate_app(maint=True)
    assert lab.image_of("app") == old_id and lab.health() == "1.2.0"
    lab.recreate_app(maint=False)
    lab.dc("up", "-d")
    assert lab.image_of("app") == old_id
    assert lab.db_identity() == db_before and lab.db_marker() == "records-1-2-3"


def test_a_version_tag_in_the_compose_file_is_not_switched_by_the_tag_move(
    lab, tmp_path
):
    """Why contract C1 matters: a compose file that names a VERSION tag keeps
    running it after the deployment tag moved - the procedure does not apply."""
    old_id = _make_image(f"{lab.repo}:1.2.0", "1.2.0", "a" * 40, tmp_path)
    new_id = _make_image(f"{lab.repo}:1.3.0", "1.3.0", "b" * 40, tmp_path)
    compose = lab.dir / "docker-compose.yml"
    compose.write_text(compose.read_text().replace(lab.deploy_tag, f"{lab.repo}:1.2.0"))
    sh("docker", "tag", old_id, lab.deploy_tag)
    lab.dc("up", "-d")
    sh("docker", "tag", new_id, lab.deploy_tag)
    lab.recreate_app(maint=False)
    assert lab.image_of("app") == old_id  # C1 violated: still 1.2.0
