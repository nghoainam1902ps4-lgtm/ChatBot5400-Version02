#!/usr/bin/env python3
"""ChatBot5400 offline update package: build, verify, preflight, update, rollback.

Phase 12F, hardened in Phase 12D3 after the independent audit
(docs/deployment/OFFLINE_UPDATE_PACKAGE.md, docs/review/PHASE12D3_OFFLINE_SAFETY_REPORT.md).
Standard library only, Python >= 3.8, so the same file runs on the build
machine, inside the image (``inventory``) and on an air-gapped Ubuntu server.

Principles: fail closed; read-only unless ``--apply``; one update at a time
(lock); never ``docker compose down``, never ``-v``, never ``pull``, never
``build`` on the server; the database container is never recreated and is
checked by ``docker inspect`` before and after every recreate; no network
access (the only URL used is the local health URL on loopback, never through a
proxy); secrets are never read or printed (``.env`` files are not opened);
nothing from a package is extracted or used before the package is
authenticated.

Commands::

  build      (build machine)  git bundle + docker save + manifest + SHA256SUMS (+ signature)
  inventory  (inside the image, --network none)  versions, runtime artifacts, schema version
  verify     (server)  authenticity FIRST, then archive safety, integrity, platform, compatibility
  preflight  (server)  read-only checks of the running deployment against the package
  update     (server)  dry-run by default; --apply performs steps G..P of the guide
  finish     (server)  leave maintenance mode after approval (health-checked)
  pin        (server)  make the new image survive a plain `docker compose up -d` (operator consent)
  rollback   (server)  app image / Legal gate / Agri model / interrupted update
  health     (server)  functional + offline readiness + drift checks of the running app
  status     (server)  the update journal and drift between it and the running container
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import hashlib
import json
import os
import platform as _platform
import re
import secrets
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterator, List, Optional, Tuple

FORMAT_VERSION = 2
SIG_NAMESPACE = "chatbot5400-offline"
MANIFEST = "manifest.json"
SIGNATURE = "manifest.json.sig"
SUMS = "SHA256SUMS"
PIN_FILE = "docker-compose.offline-pin.yml"
BUNDLE_REF_PREFIX = "refs/cb5400-offline/build/"

# Archive safety limits (overridable for tests / very large images).
MAX_MEMBERS = 5000
MAX_TOTAL_BYTES = int(os.environ.get("CB5400_OFFLINE_MAX_BYTES", str(64 * 1024**3)))
MAX_RATIO = 200.0  # uncompressed / compressed
MAX_METADATA_BYTES = 5 * 1024 * 1024  # manifest / signature read before extraction
SAFE_NAME = re.compile(r"^[A-Za-z0-9._+\-/]+$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.\-]+)?$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
# Shapes of everything that ends up in a YAML file or in a git / docker argv (F-12).
_REPO = r"[a-z0-9]+(?:[._-]+[a-z0-9]+)*(?::\d{1,5})?(?:/[a-z0-9]+(?:[._-]+[a-z0-9]+)*)*"
_TAG = r"[A-Za-z0-9_][A-Za-z0-9_.\-]{0,127}"
IMAGE_REF_RE = re.compile(rf"^{_REPO}(?::{_TAG})?$")  # what a container may report
TAGGED_REF_RE = re.compile(rf"^{_REPO}:{_TAG}$")  # what a package must declare
IMAGE_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
RELEASE_TAG_RE = re.compile(r"^v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?$")
BUNDLE_REF_RE = re.compile(
    r"^refs/cb5400-offline/build/\d+\.\d+\.\d+(?:-[0-9A-Za-z.\-]+)?$"
)
ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
ENV_VALUE_RE = re.compile(r"^[A-Za-z0-9_.:/\-]{0,200}$")
SERVICE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,62}$")

EXIT_OK, EXIT_USAGE, EXIT_VERIFY, EXIT_PREFLIGHT, EXIT_UPDATE, EXIT_LOCK, EXIT_DRIFT = (
    0,
    2,
    3,
    4,
    5,
    6,
    7,
)

# Journal states.
IN_PROGRESS = "in_progress"
PENDING_CHECKS = "deployed_pending_checks"
AWAITING = "awaiting_approval"
FAILED = "failed"
COMPLETED = "completed"
ROLLED_BACK = "rolled_back"
ROLLBACK_FAILED = "rollback_failed"
FINISH_FAILED = "finish_failed"
# A finished transaction: the next `update --apply` is a NEW attempt (fresh backup).
CLOSED_STATES = (COMPLETED, ROLLED_BACK)
# The application runs (or may run) the new image and nobody decided yet.
UNDECIDED_STATES = (PENDING_CHECKS, AWAITING, ROLLBACK_FAILED, FINISH_FAILED)

SAFE_UP = ["up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate"]


class Refused(Exception):
    """A check failed: stop, change nothing more."""

    def __init__(self, message: str, code: int = EXIT_VERIFY) -> None:
        super().__init__(message)
        self.code = code


def log(msg: str) -> None:
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    print(f"[cb5400-offline {stamp}] {msg}", flush=True)


def now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(
    cmd: List[str],
    check: bool = True,
    capture: bool = True,
    timeout: Optional[int] = None,
    input_text: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """Run a command (list form, never a shell)."""
    proc = subprocess.run(  # noqa: S603 - fixed binaries, list arguments
        cmd,
        capture_output=capture,
        text=True,
        timeout=timeout,
        check=False,
        input=input_text,
    )
    if check and proc.returncode != 0:
        detail = (
            (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
            if capture
            else []
        )
        raise Refused(
            f"command failed ({proc.returncode}): {' '.join(cmd[:4])} … {' | '.join(detail)}",
            EXIT_UPDATE,
        )
    return proc


def normalize_platform(value: str) -> str:
    v = (value or "").strip().lower()
    aliases = {
        "x86_64": "linux/amd64",
        "amd64": "linux/amd64",
        "aarch64": "linux/arm64",
        "arm64": "linux/arm64",
    }
    if v in aliases:
        return aliases[v]
    if v.startswith("linux/"):
        arch = v.split("/", 1)[1]
        return "linux/" + {"x86_64": "amd64", "aarch64": "arm64"}.get(arch, arch)
    return v


# --------------------------------------------------------------------------- #
# Format checks (F-12): nothing unvalidated reaches YAML, git or docker
# --------------------------------------------------------------------------- #


def check_image_ref(value: Any, what: str = "image reference") -> str:
    if not isinstance(value, str) or not (
        IMAGE_REF_RE.match(value) or IMAGE_ID_RE.match(value)
    ):
        raise Refused(f"invalid {what}: {str(value)[:80]!r}", EXIT_USAGE)
    return value


def check_commit(value: Any) -> str:
    if not isinstance(value, str) or not COMMIT_RE.match(value):
        raise Refused(f"invalid git commit: {str(value)[:80]!r}")
    return value


# --------------------------------------------------------------------------- #
# Configuration (server side)
# --------------------------------------------------------------------------- #

DEFAULT_CONFIG = {
    "DEPLOY_DIR": "",
    "COMPOSE_PROJECT": "",
    "COMPOSE_FILES": "docker-compose.yml",
    "APP_SERVICE": "open_notebook",
    "DB_SERVICE": "surrealdb",
    "IMAGE_REPO": "chatbot5400",
    "STATE_DIR": "/var/lib/chatbot5400-offline",
    "ALLOWED_SIGNERS": "/etc/chatbot5400/allowed_signers",
    "SIGNER_IDENTITY": "release@chatbot5400",
    "MAINTENANCE_OVERRIDE": "",
    "BACKUP_CMD": "",
    "BACKUP_VERIFY_CMD": "",
    "BACKUP_MAX_AGE_MINUTES": "120",
    "HEALTH_URL": "http://127.0.0.1:5055/health",
    "MIN_FREE_GB_EXTRA": "5",
    "APP_ENV_OVERRIDES": "OCR_RAPIDOCR_PERSISTENT=true OCR_OFFLINE=true",
}


def _check_trusted_file(path: Path, what: str) -> None:
    """A file that decides what runs as root must not be writable by others (F-26c)."""
    try:
        st = path.stat()
    except OSError as e:
        raise Refused(f"{what} unreadable: {path} ({e.strerror})", EXIT_USAGE) from None
    if st.st_uid not in (0, os.geteuid()):
        raise Refused(
            f"{what} {path} is owned by another user (uid {st.st_uid})", EXIT_USAGE
        )
    if st.st_mode & 0o022:
        raise Refused(
            f"{what} {path} is writable by group / others (chmod go-w it): refused",
            EXIT_USAGE,
        )


def load_config(path: Optional[str]) -> Dict[str, str]:
    """KEY=VALUE file (no shell evaluation), owner-only writable.

    The only environment variable honoured is CB5400_OFFLINE_CONFIG (the path of
    the file): individual keys such as BACKUP_CMD can no longer be replaced
    through the environment of whoever runs the tool (F-26c).
    """
    cfg = dict(DEFAULT_CONFIG)
    candidate = Path(
        path
        or os.environ.get(
            "CB5400_OFFLINE_CONFIG", "/etc/chatbot5400/offline-update.conf"
        )
    )
    if candidate.is_file():
        _check_trusted_file(candidate, "configuration file")
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key in cfg:
                cfg[key] = value.strip().strip('"').strip("'")
    elif path:
        raise Refused(f"configuration file not found: {candidate}", EXIT_USAGE)
    return cfg


def require(cfg: Dict[str, str], *keys: str) -> None:
    missing = [k for k in keys if not cfg.get(k)]
    if missing:
        raise Refused(
            f"configuration missing: {', '.join(missing)} "
            "(see docs/deployment/OFFLINE_UPDATE_UBUNTU_GUIDE.md)",
            EXIT_USAGE,
        )


@contextlib.contextmanager
def update_lock(state_dir: Path) -> Iterator[None]:
    """One update at a time (flock); released automatically if the process dies."""
    import fcntl

    state_dir.mkdir(parents=True, exist_ok=True)
    fh = open(state_dir / "update.lock", "w")
    try:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Refused(
                "another update / rollback is running (lock held)", EXIT_LOCK
            ) from None
        fh.write(str(os.getpid()))
        fh.flush()
        yield
    finally:
        fh.close()


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write(path: Path, text: str) -> None:
    """Write + fsync a temporary file, then rename it over ``path`` (F-13)."""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    _fsync_dir(path.parent)


class Journal:
    """Progress of ONE update attempt, crash-safe (F-13), never reset blindly.

    ``journal.json`` is written atomically; the previous good copy is kept as
    ``journal.json.bak``. A damaged journal is reported with recovery
    instructions - it is never replaced by an empty one, because it is the only
    record of which image to roll back to. Finished attempts are archived under
    ``journals/`` (F-08).
    """

    def __init__(self, state_dir: Path) -> None:
        self.dir = state_dir
        self.path = state_dir / "journal.json"
        self.backup = state_dir / "journal.json.bak"
        self.data: Dict[str, Any] = self._load()

    def _read(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists() and not self.backup.exists():
            return {}
        data = self._read(self.path) if self.path.exists() else None
        if data is not None:
            return data
        previous = self._read(self.backup) if self.backup.exists() else None
        hint = (
            f"the update journal {self.path} is damaged (interrupted write?). Nothing was "
            "changed. Recovery: 1) keep both files; 2) check what runs with "
            "`docker inspect <app container> --format '{{.Image}}'`; "
        )
        if previous is not None:
            hint += (
                f"3) the previous good copy {self.backup} is from step "
                f"{(previous.get('steps') or [{}])[-1].get('step', '?')} "
                f"(status {previous.get('status')}): if it matches the running state, copy it "
                f"over {self.path.name} and run status again."
            )
        else:
            hint += (
                "3) no readable backup copy exists: move the damaged file aside by hand "
                "(journal.damaged-<date>.json) only after noting the running image and the "
                "rollback image tag (docker image ls 'chatbot5400:rollback-*')."
            )
        hint += (
            " To roll back without a journal: move BOTH files aside, then run "
            "`rollback.sh app --to-image <rollback tag or previous image>` (the image "
            "is checked, the database is not touched)."
        )
        raise Refused(hint, EXIT_UPDATE)

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        text = json.dumps(self.data, indent=2, sort_keys=True)
        atomic_write(self.path, text)
        # Second copy, written after the first is safely on disk: whichever of
        # the two a crash or a bad block damages, the other is a complete state.
        atomic_write(self.backup, text)

    def step(self, name: str, **info: Any) -> None:
        self.data.setdefault("steps", []).append(
            {"step": name, "at": now_iso(), **info}
        )
        self.save()

    def last(self, name: str) -> Optional[Dict[str, Any]]:
        for s in reversed(self.data.get("steps", [])):
            if s.get("step") == name:
                return s
        return None

    def done(self, name: str) -> bool:
        return self.last(name) is not None

    def archive(self) -> Optional[Path]:
        """Keep the finished attempt for audit and start with an empty journal."""
        if not self.data:
            return None
        history = self.dir / "journals"
        history.mkdir(parents=True, exist_ok=True)
        name = self.data.get("attempt_id") or _dt.datetime.now().strftime(
            "%Y%m%d%H%M%S"
        )
        target = history / f"journal-{name}.json"
        atomic_write(target, json.dumps(self.data, indent=2, sort_keys=True))
        self.data = {}
        for p in (self.path, self.backup):
            if p.exists():
                p.unlink()
        _fsync_dir(self.dir)
        return target


def new_attempt_id() -> str:
    return _dt.datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(3)


# --------------------------------------------------------------------------- #
# Archive safety (F-14) - nothing is written before the archive is authenticated
# --------------------------------------------------------------------------- #


def _check_member(m: tarfile.TarInfo, top: Optional[str]) -> str:
    name = m.name
    if name.startswith("/") or "\\" in name or not SAFE_NAME.match(name):
        raise Refused(f"unsafe archive entry name: {name!r}")
    raw = (name[:-1] if name.endswith("/") else name).split("/")
    if any(p in ("", ".", "..") for p in raw):
        raise Refused(f"path traversal in archive entry: {name!r}")
    parts = PurePosixPath(name).parts
    if m.issym() or m.islnk():
        raise Refused(f"link in archive (symlink / hardlink refused): {name!r}")
    if not (m.isfile() or m.isdir()):
        raise Refused(f"special file in archive refused: {name!r}")
    if top is not None and parts[0] != top:
        raise Refused(f"archive entry outside the package folder: {name!r}")
    return parts[0]


def inspect_archive(package: Path) -> List[tarfile.TarInfo]:
    """Validate every entry BEFORE anything is written to disk."""
    compressed = package.stat().st_size
    members: List[tarfile.TarInfo] = []
    seen: set = set()
    total = 0
    top: Optional[str] = None
    try:
        with tarfile.open(package, "r:*") as tar:
            for m in tar:
                if len(members) >= MAX_MEMBERS:
                    raise Refused(f"too many archive entries (> {MAX_MEMBERS})")
                top = _check_member(m, top)
                key = str(PurePosixPath(m.name))
                if key in seen:
                    raise Refused(f"duplicate archive entry: {m.name!r}")
                seen.add(key)
                total += max(0, m.size)
                if total > MAX_TOTAL_BYTES:
                    raise Refused(f"package expands beyond {MAX_TOTAL_BYTES} bytes")
                members.append(m)
    except (tarfile.TarError, EOFError, OSError) as e:
        raise Refused(f"unreadable package archive: {type(e).__name__}") from None
    if not members:
        raise Refused("empty package")
    if compressed and total / compressed > MAX_RATIO:
        raise Refused(
            f"abnormal compression ratio ({total / compressed:.0f}x): refused"
        )
    return members


def read_metadata(
    package: Path, members: List[tarfile.TarInfo]
) -> Tuple[bytes, Optional[bytes]]:
    """manifest.json and its signature, read in memory from the validated archive."""
    top = PurePosixPath(members[0].name).parts[0]
    wanted: Dict[str, Optional[bytes]] = {
        f"{top}/{MANIFEST}": None,
        f"{top}/{SIGNATURE}": None,
    }
    with tarfile.open(package, "r:*") as tar:
        for m in members:
            if m.name in wanted and m.isfile():
                if m.size > MAX_METADATA_BYTES:
                    raise Refused(f"{m.name} is too large")
                fh = tar.extractfile(m)
                wanted[m.name] = fh.read() if fh is not None else None
    manifest = wanted[f"{top}/{MANIFEST}"]
    if manifest is None:
        raise Refused("manifest.json missing")
    return manifest, wanted[f"{top}/{SIGNATURE}"]


def safe_extract(
    package: Path, dest: Path, expected: Optional[Dict[str, Dict[str, Any]]] = None
) -> Path:
    """Extract into a staging folder, renamed to ``dest`` only when complete.

    With ``expected`` (the ``files`` of an authenticated manifest) every file is
    hashed while it is written and anything not listed is refused. A failure
    leaves no partial tree behind.
    """
    if dest.exists() and any(dest.iterdir()):
        raise Refused(f"{dest} must be a new or empty directory")
    members = inspect_archive(package)
    total = sum(max(0, m.size) for m in members)
    dest.parent.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(str(dest.parent)).free
    if free < total + 64 * 1024 * 1024:
        raise Refused(
            f"not enough free space to unpack: need {total // 1024**2} MiB, "
            f"free {free // 1024**2} MiB in {dest.parent}"
        )
    top = PurePosixPath(members[0].name).parts[0]
    staging = dest.with_name(dest.name + f".partial-{os.getpid()}")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    root = staging.resolve()
    try:
        with tarfile.open(package, "r:*") as tar:
            for m in members:
                target = (root / m.name).resolve()
                if root not in target.parents and target != root:
                    raise Refused(f"entry escapes the extraction folder: {m.name!r}")
                if m.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                rel = str(PurePosixPath(m.name).relative_to(top))
                meta = None
                if expected is not None and rel not in (MANIFEST, SIGNATURE, SUMS):
                    meta = expected.get(rel)
                    if meta is None:
                        raise Refused(f"file not in the manifest: {rel}")
                    if m.size != meta["size"]:
                        raise Refused(f"size mismatch: {rel}")
                target.parent.mkdir(parents=True, exist_ok=True)
                src = tar.extractfile(m)
                if src is None:
                    raise Refused(f"unreadable archive entry: {m.name!r}")
                digest = hashlib.sha256()
                with open(target, "wb") as out:
                    for chunk in iter(lambda: src.read(4 * 1024 * 1024), b""):
                        digest.update(chunk)
                        out.write(chunk)
                if meta is not None and digest.hexdigest() != meta["sha256"]:
                    raise Refused(f"checksum mismatch: {rel}")
                os.chmod(target, 0o755 if m.mode & 0o111 else 0o644)
        if dest.exists():
            dest.rmdir()
        os.replace(staging, dest)
    except BaseException as e:
        shutil.rmtree(staging, ignore_errors=True)
        if isinstance(e, OSError):
            raise Refused(f"could not unpack the package: {e.strerror or e}") from None
        raise
    return dest.resolve() / top


# --------------------------------------------------------------------------- #
# Docker image archive identity (F-20, F-25)
# --------------------------------------------------------------------------- #


def image_archive_identity(archive: Path) -> Dict[str, Any]:
    """What a ``docker save`` archive really contains, read without loading it.

    ``repo_tags``      every tag ``docker load`` would create or MOVE
    ``config_digest``  sha256 of the image config = the image ID of the classic store
    ``diff_ids``       uncompressed layer digests = ``RootFS.Layers`` in any store

    The image ID reported by ``docker image inspect`` differs between the
    classic and the containerd image store; the layer list does not. Both the
    docker-archive ``manifest.json`` and the OCI ``index.json`` layouts are read.
    """
    try:
        with tarfile.open(archive, "r:*") as tar:
            names = {m.name: m for m in tar.getmembers() if m.isfile()}

            def load(name: str) -> bytes:
                member = names.get(name)
                if member is None or member.size > 64 * 1024 * 1024:
                    raise Refused(f"image archive: {name} missing or too large")
                fh = tar.extractfile(member)
                if fh is None:
                    raise Refused(f"image archive: {name} unreadable")
                return fh.read()

            if "manifest.json" in names:
                entries = json.loads(load("manifest.json"))
                if not isinstance(entries, list) or len(entries) != 1:
                    raise Refused("image archive must contain exactly one image")
                entry = entries[0]
                config = load(str(entry.get("Config", "")))
                tags = list(entry.get("RepoTags") or [])
                layout = "docker-archive"
            elif "index.json" in names:
                index = json.loads(load("index.json"))
                manifests = index.get("manifests") or []
                if len(manifests) != 1:
                    raise Refused("image archive must contain exactly one image")
                desc = manifests[0]
                tags = [
                    v
                    for k, v in (desc.get("annotations") or {}).items()
                    if k
                    in ("io.containerd.image.name", "org.opencontainers.image.ref.name")
                ]
                blob = json.loads(load("blobs/" + desc["digest"].replace(":", "/")))
                if blob.get("manifests"):  # an image index: one platform expected
                    if len(blob["manifests"]) != 1:
                        raise Refused("image archive holds several platforms")
                    blob = json.loads(
                        load(
                            "blobs/" + blob["manifests"][0]["digest"].replace(":", "/")
                        )
                    )
                config = load("blobs/" + blob["config"]["digest"].replace(":", "/"))
                layout = "oci"
            else:
                raise Refused(
                    "not a docker image archive (no manifest.json / index.json)"
                )
    except (tarfile.TarError, ValueError, KeyError, TypeError, OSError) as e:
        raise Refused(f"unreadable docker image archive: {type(e).__name__}") from None
    try:
        diff_ids = list(json.loads(config)["rootfs"]["diff_ids"])
    except (ValueError, KeyError, TypeError):
        raise Refused("image archive: image config has no rootfs.diff_ids") from None
    return {
        "layout": layout,
        "repo_tags": sorted(str(t) for t in tags),
        "config_digest": "sha256:" + sha256_bytes(config),
        "diff_ids": [str(d) for d in diff_ids],
    }


def check_image_archive(archive: Path, image: Dict[str, Any]) -> Dict[str, Any]:
    """The archive loads exactly one image under exactly the approved tag (F-25)."""
    ident = image_archive_identity(archive)
    if ident["repo_tags"] != [image["tag"]]:
        raise Refused(
            f"the image archive would create / move the tags {ident['repo_tags']}; "
            f"only [{image['tag']!r}] is approved by the manifest"
        )
    if image.get("config_digest") and ident["config_digest"] != image["config_digest"]:
        raise Refused("image archive config digest differs from the manifest")
    if image.get("diff_ids") and ident["diff_ids"] != image["diff_ids"]:
        raise Refused("image archive layers differ from the manifest")
    return ident


def same_image(
    inspect_id: str, layers: List[str], image: Dict[str, Any]
) -> Optional[str]:
    """How a loaded image is recognised as the packaged one (None = it is not)."""
    if inspect_id == image.get("id"):
        return "image id"
    if inspect_id == image.get("config_digest"):
        return "config digest (classic image store)"
    if layers and image.get("diff_ids") and layers == image["diff_ids"]:
        return "layer digests (other image store)"
    return None


def inspect_image(ref: str) -> Optional[Tuple[str, List[str]]]:
    """(.Id, RootFS.Layers) of a local image, or None when it does not exist."""
    proc = run(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            "{{.Id}} {{json .RootFS.Layers}}",
            ref,
        ],
        check=False,
    )
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    image_id, _, rest = out.partition(" ")
    try:
        layers = json.loads(rest) if rest else []
    except ValueError:
        layers = []
    return image_id, [str(x) for x in (layers or [])]


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #

MANIFEST_REQUIRED = {
    "package_format_version": int,
    "application": dict,
    "platform": str,
    "image": dict,
    "source": dict,
    "database": dict,
    "dependencies": dict,
    "runtime_artifacts": dict,
    "rollback": dict,
    "files": dict,
    "build": dict,
}


def validate_manifest(manifest: Any) -> None:
    if not isinstance(manifest, dict):
        raise Refused("manifest is not a JSON object")
    for key, typ in MANIFEST_REQUIRED.items():
        if not isinstance(manifest.get(key), typ):
            raise Refused(f"manifest field missing or invalid: {key}")
    if manifest["package_format_version"] != FORMAT_VERSION:
        raise Refused(
            f"unsupported package format {manifest['package_format_version']}"
        )
    app = manifest["application"]
    if not VERSION_RE.match(str(app.get("version", ""))):
        raise Refused("manifest application.version is not a version number")
    if not RELEASE_TAG_RE.match(str(app.get("release_tag", ""))):
        raise Refused("manifest application.release_tag is not a release tag")
    supported = app.get("supported_source_versions")
    if not isinstance(supported, list) or not supported:
        raise Refused("manifest application.supported_source_versions missing")
    if not all(isinstance(v, str) and VERSION_RE.match(v) for v in supported):
        raise Refused("manifest application.supported_source_versions invalid")
    img = manifest["image"]
    for key in ("tag", "id", "archive", "archive_sha256", "config_digest"):
        if not isinstance(img.get(key), str) or not img[key]:
            raise Refused(f"manifest image.{key} missing")
    if not TAGGED_REF_RE.match(img["tag"]):
        raise Refused("manifest image.tag is not a repository:tag reference")
    for key in ("id", "config_digest"):
        if not IMAGE_ID_RE.match(img[key]):
            raise Refused(f"manifest image.{key} is not a sha256 digest")
    if not SHA_RE.match(img["archive_sha256"]):
        raise Refused("manifest image.archive_sha256 invalid")
    layers = img.get("diff_ids")
    if not isinstance(layers, list) or not all(
        isinstance(x, str) and IMAGE_ID_RE.match(x) for x in layers
    ):
        raise Refused("manifest image.diff_ids invalid")
    if img.get("repo_tags") != [img["tag"]]:
        raise Refused("manifest image.repo_tags must be exactly [image.tag]")
    src = manifest["source"]
    for key in ("commit", "base_commit"):
        if not COMMIT_RE.match(str(src.get(key, ""))):
            raise Refused(f"manifest source.{key} is not a commit id")
    if not BUNDLE_REF_RE.match(str(src.get("bundle_ref", ""))):
        raise Refused("manifest source.bundle_ref invalid")
    db = manifest["database"]
    if not isinstance(db.get("schema_version"), int) or not isinstance(
        db.get("migration_required"), bool
    ):
        raise Refused("manifest database.schema_version / migration_required invalid")
    for rel, meta in manifest["files"].items():
        if (
            not isinstance(meta, dict)
            or not SHA_RE.match(str(meta.get("sha256", "")))
            or not isinstance(meta.get("size"), int)
        ):
            raise Refused(f"manifest files entry invalid: {rel}")
        parts = PurePosixPath(rel).parts
        if rel.startswith("/") or ".." in parts or not SAFE_NAME.match(rel):
            raise Refused(f"manifest files entry unsafe: {rel}")
    for key in ("archive",):
        if img[key] not in manifest["files"]:
            raise Refused("manifest image.archive is not one of the packaged files")
    for key in ("git_bundle", "archive"):
        if src.get(key) not in manifest["files"]:
            raise Refused(f"manifest source.{key} is not one of the packaged files")
    secrets_like = re.compile(
        r"(password|secret|api[_-]?key|token)\s*[=:]", re.IGNORECASE
    )
    if secrets_like.search(json.dumps(manifest)):
        raise Refused("manifest looks like it contains a secret: refused")


def verify_signature_bytes(
    manifest: bytes, signature: Optional[bytes], allowed_signers: str, identity: str
) -> str:
    """'valid' / 'absent'; raises for a bad signature or an unusable key file."""
    if signature is None:
        return "absent"
    if not allowed_signers or not Path(allowed_signers).is_file():
        raise Refused(
            f"package is signed but no trusted key file is installed ({allowed_signers})"
        )
    _check_trusted_file(Path(allowed_signers), "trusted signers file")
    keygen = shutil.which("ssh-keygen")
    if not keygen:
        raise Refused("ssh-keygen is required to check the signature")
    import tempfile

    with tempfile.TemporaryDirectory(prefix="cb5400-sig-") as tmp:
        sig_path = Path(tmp) / "manifest.json.sig"
        sig_path.write_bytes(signature)
        proc = subprocess.run(  # noqa: S603
            [
                keygen,
                "-Y",
                "verify",
                "-f",
                allowed_signers,
                "-I",
                identity,
                "-n",
                SIG_NAMESPACE,
                "-s",
                str(sig_path),
            ],  # fmt: skip
            input=manifest,
            capture_output=True,
            check=False,
        )
    if proc.returncode != 0:
        raise Refused(
            "INVALID signature: the package is not from the trusted release key"
        )
    return "valid"


def render_sums(files: Dict[str, Dict[str, Any]]) -> str:
    return "".join(f"{meta['sha256']}  {rel}\n" for rel, meta in sorted(files.items()))


def verify_tree(
    root: Path,
    platform_expected: Optional[str],
    current_version: Optional[str],
    current_schema: Optional[int],
) -> Dict[str, Any]:
    manifest_path = root / MANIFEST
    if not manifest_path.is_file():
        raise Refused("manifest.json missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise Refused(f"manifest.json unreadable: {e}") from None
    validate_manifest(manifest)
    # Every file listed, nothing more, nothing less (manifest + sums + signature aside).
    present = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() or p.is_symlink()
    } - {MANIFEST, SIGNATURE, SUMS}
    for p in root.rglob("*"):
        if p.is_symlink():
            raise Refused(f"symlink in package: {p.relative_to(root)}")
    listed = set(manifest["files"])
    if present - listed:
        raise Refused(f"files not in the manifest: {sorted(present - listed)[:5]}")
    if listed - present:
        raise Refused(f"files missing from the package: {sorted(listed - present)[:5]}")
    for rel, meta in sorted(manifest["files"].items()):
        f = root / rel
        if f.stat().st_size != meta["size"] or sha256_file(f) != meta["sha256"]:
            raise Refused(f"checksum mismatch: {rel}")
    sums = root / SUMS
    if not sums.is_file():
        raise Refused("SHA256SUMS missing")
    if sums.read_text(encoding="utf-8") != render_sums(manifest["files"]):
        raise Refused("SHA256SUMS does not match the manifest")
    image = manifest["image"]
    if manifest["files"][image["archive"]]["sha256"] != image["archive_sha256"]:
        raise Refused(
            "image archive checksum differs from manifest image.archive_sha256"
        )
    check_image_archive(root / image["archive"], image)
    if platform_expected and normalize_platform(
        manifest["platform"]
    ) != normalize_platform(platform_expected):
        raise Refused(
            f"wrong platform: package {manifest['platform']}, server {platform_expected}"
        )
    if (
        current_version
        and current_version not in manifest["application"]["supported_source_versions"]
    ):
        raise Refused(
            f"cannot update from {current_version}: supported "
            f"{manifest['application']['supported_source_versions']}"
        )
    if current_schema is not None:
        db = manifest["database"]
        if current_schema > db["schema_version"]:
            raise Refused(
                f"database schema {current_schema} is newer than the package "
                f"({db['schema_version']})"
            )
        if current_schema < db["schema_version"] and not db.get("migration_required"):
            raise Refused(
                "manifest inconsistent: schema differs but migration_required is false"
            )
    if manifest["database"]["migration_required"]:
        raise Refused(
            "this package needs a database migration: offline tooling refuses it "
            "(separate approved procedure)"
        )
    return manifest


def cmd_verify(args: argparse.Namespace) -> int:
    """Authenticate first; only then unpack (F-14)."""
    package = Path(args.package)
    if not package.is_file():
        raise Refused(f"no such package: {package}", EXIT_USAGE)
    digest = sha256_file(package)
    log(f"package sha256 {digest}")
    authenticity: List[str] = []
    if args.expected_sha256:
        if digest != args.expected_sha256.strip().lower():
            raise Refused(
                "package SHA-256 differs from the value received over the trusted channel"
            )
        authenticity.append("sha256 matched the trusted-channel value")
    members = inspect_archive(package)  # nothing written yet
    manifest_bytes, signature = read_metadata(package, members)
    if (
        signature is not None
        and authenticity
        and not Path(args.allowed_signers).is_file()
    ):
        # Authentic through the trusted-channel hash; the signature cannot add to it.
        log(
            "note: the package is signed but no trusted key is installed: signature NOT checked"
        )
        signed = "unchecked"
    else:
        signed = verify_signature_bytes(
            manifest_bytes, signature, args.allowed_signers, args.identity
        )
    if signed == "valid":
        authenticity.append("signature valid")
    if not authenticity:
        raise Refused(
            "AUTHENTICITY NOT VERIFIED: the package is unsigned (or no key is installed) and no "
            "--expected-sha256 from a trusted channel was given. Nothing was unpacked. A "
            ".sha256 file that travelled with the package is NOT a trusted channel."
        )
    try:
        files = json.loads(manifest_bytes.decode("utf-8")).get("files")
    except (ValueError, UnicodeDecodeError, AttributeError):
        raise Refused("manifest.json unreadable") from None
    if not isinstance(files, dict):
        raise Refused("manifest field missing or invalid: files")
    dest = Path(args.extract_to)
    root = safe_extract(package, dest, expected=files if signed == "valid" else None)
    try:
        if (root / MANIFEST).read_bytes() != manifest_bytes:
            raise Refused("manifest changed between authentication and extraction")
        manifest = verify_tree(
            root, args.platform, args.current_version, args.current_schema
        )
    except Refused:
        shutil.rmtree(dest, ignore_errors=True)  # no half-verified tree is left behind
        raise
    report = {
        "result": "VERIFIED",
        "package_sha256": digest,
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "authenticity": authenticity,
        "signed": signed == "valid",
        "version": manifest["application"]["version"],
        "platform": manifest["platform"],
        "image": manifest["image"]["tag"],
        "readiness": manifest.get("readiness", {}).get("status"),
        "package_dir": str(root),
        "verified_at": now_iso(),
    }
    atomic_write(root.parent / "verify-report.json", json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return EXIT_OK


# --------------------------------------------------------------------------- #
# Build (machine with Internet; Windows via build-package.ps1, Linux/WSL via .sh)
# --------------------------------------------------------------------------- #


def docker_inspect_image(ref: str) -> Dict[str, Any]:
    out = run(["docker", "image", "inspect", ref]).stdout
    data = json.loads(out)
    if not data:
        raise Refused(f"image not found: {ref}", EXIT_USAGE)
    return data[0]


def _probe_tiktoken(app_root: Path) -> Dict[str, Any]:
    """Can tokens be counted with NO network? (inventory runs with --network none)."""
    info: Dict[str, Any] = {"encoding": "o200k_base", "loads_offline": False}
    cache = os.environ.get("TIKTOKEN_CACHE_DIR", "")
    info["cache_dir"] = cache
    files = []
    if cache and Path(cache).is_dir():
        for f in sorted(Path(cache).iterdir()):
            if f.is_file():
                files.append(
                    {"name": f.name, "size": f.stat().st_size, "sha256": sha256_file(f)}
                )
    info["files"] = files
    import threading

    result: Dict[str, Any] = {}

    def work() -> None:
        try:
            import tiktoken

            result["tokens"] = len(
                tiktoken.get_encoding("o200k_base").encode("kiểm tra offline")
            )
        except Exception as e:  # noqa: BLE001 - reported
            result["error"] = type(e).__name__

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(20)
    if t.is_alive():
        info["error"] = "timeout (tiktoken tried to download)"
    elif "tokens" in result:
        info["loads_offline"] = True
    else:
        info["error"] = result.get("error", "unknown")
    return info


def cmd_inventory(args: argparse.Namespace) -> int:
    """Runs INSIDE the image (docker run --network none): what this image contains."""
    from importlib.metadata import PackageNotFoundError, version

    app_root = Path(args.app_root)
    info: Dict[str, Any] = {
        "python": _platform.python_version(),
        "machine": _platform.machine(),
    }
    deps: Dict[str, Optional[str]] = {}
    for pkg in (
        "open-notebook", "content-core", "docling", "docling-core", "docling-ibm-models",
        "torch", "rapidocr", "onnxruntime", "easyocr", "surrealdb", "langchain-core", "tiktoken",
    ):  # fmt: skip
        try:
            deps[pkg] = version(pkg)
        except PackageNotFoundError:
            deps[pkg] = None
    info["dependencies"] = deps
    tess = shutil.which("tesseract")
    info["tesseract"] = (
        run([tess, "--version"], check=False).stdout.splitlines()[0] if tess else None
    )
    migrations = sorted(
        int(p.stem)
        for p in (app_root / "open_notebook/database/migrations").glob("*.surrealql")
        if p.stem.isdigit()
    )
    info["schema_version"] = max(migrations) if migrations else 0
    version_file = app_root / "VERSION"
    info["app_version"] = (
        version_file.read_text().strip() if version_file.is_file() else None
    )
    artifacts: Dict[str, Any] = {}
    try:
        sys.path.insert(0, str(app_root))
        from open_notebook.ocr import catalog, installer

        artifacts["rapidocr_weights_sha256"] = installer.rapidocr_known_checksums()
        engines = {}
        for eid, spec in catalog.ENGINES.items():
            engines[eid] = {
                "display_name": getattr(spec, "display_name", eid),
                "runtime": getattr(spec, "runtime", None),
                "model": (
                    f"{getattr(spec, 'model_name', '')} {getattr(spec, 'model_version', '')}"
                ).strip(),
                "custom": spec.custom is not None,
            }
        artifacts["engines"] = engines
    except Exception as e:  # noqa: BLE001 - reported, not fatal
        artifacts["error"] = type(e).__name__
    artifacts["docling_models"] = {
        "location": "HF_HOME on the data volume (/app/data/.cache/huggingface): "
        "reused, never shipped",
        "layout": "docling-project/docling-layout-heron",
        "tableformer": "docling-project/docling-models (TableFormer accurate)",
    }
    artifacts["persistent_volume_artifacts"] = [
        "/app/data/.cache/huggingface (Layout Heron, TableFormer)",
        "/app/data/ocr/models/tesseract (fast / best / osd.traineddata, custom/agri/<version>)",
        "/app/data/ocr/models/rapidocr (with OCR_RAPIDOCR_PERSISTENT=true)",
        "/app/data/ocr/models/easyocr",
        "/app/data/ocr (manifests, readiness state, custom model versions)",
    ]
    artifacts["tiktoken"] = _probe_tiktoken(app_root)
    info["runtime_artifacts"] = artifacts
    info["runtimes_baked"] = {
        "docling": deps.get("docling") is not None,
        "easyocr": deps.get("easyocr") is not None,
        "tesseract": tess is not None,
        "tiktoken_offline": bool(artifacts["tiktoken"].get("loads_offline")),
    }
    print(json.dumps(info, indent=2, sort_keys=True))
    return EXIT_OK


def _git(repo: Path, *a: str, check: bool = True) -> str:
    return run(["git", "-C", str(repo), *a], check=check).stdout.strip()


def version_matches(checkout_version: str, requested: str) -> bool:
    """`1.2.0` builds `1.2.0` or `1.2.0-<suffix>`; never another release number."""
    return bool(checkout_version) and (
        requested == checkout_version or requested.split("-")[0] == checkout_version
    )


def check_build_version(repo: Path, commit: str, requested: str) -> str:
    """VERSION of the commit being packaged vs --version, BEFORE any Docker work (F-27)."""
    if not VERSION_RE.match(requested):
        raise Refused("--version must look like 1.3.0 or 1.3.0-rc.1", EXIT_USAGE)
    found = _git(repo, "show", f"{commit}:VERSION", check=False).strip()
    if not version_matches(found, requested):
        raise Refused(
            f"VERSION of the checkout is {found or '?'}: it cannot be packaged as {requested}. "
            f"Use --version {found}-<suffix> for a test package (e.g. {found}-phase12.1); a "
            "release number changes only in the release commit that updates VERSION.",
            EXIT_USAGE,
        )
    return found


def bundle_heads(repo: Path, bundle: Path) -> Dict[str, str]:
    heads = {}
    for line in _git(repo, "bundle", "list-heads", str(bundle)).splitlines():
        sha, _, ref = line.strip().partition(" ")
        if sha and ref:
            heads[ref] = sha
    return heads


def create_bundle(
    repo: Path,
    base_ref: str,
    commit: str,
    version: str,
    out: Path,
    extra_refs: List[str],
) -> str:
    """A bundle with a NAMED ref for the release commit (F-04, F-05).

    ``git bundle create base..<sha>`` is refused by git ("empty bundle"): a
    bundle carries refs, not bare commits. A temporary ref in our own namespace
    is created, bundled and always deleted again.
    """
    ref = BUNDLE_REF_PREFIX + version
    if run(["git", "-C", str(repo), "merge-base", "--is-ancestor", base_ref, commit], check=False).returncode != 0:  # fmt: skip
        raise Refused(
            f"--base-ref {base_ref} is not an ancestor of the commit to package: wrong base",
            EXIT_USAGE,
        )
    previous = _git(repo, "rev-parse", "-q", "--verify", ref, check=False)
    run(["git", "-C", str(repo), "update-ref", ref, commit])
    try:
        run(
            ["git", "-C", str(repo), "bundle", "create", str(out), f"{base_ref}..{ref}"]
            + [r for r in extra_refs if r]
        )
        run(["git", "-C", str(repo), "bundle", "verify", str(out)])
        if bundle_heads(repo, out).get(ref) != commit:
            raise Refused(
                "the bundle does not carry the release commit under its ref", EXIT_USAGE
            )
    finally:
        if previous:
            run(["git", "-C", str(repo), "update-ref", ref, previous], check=False)
        else:
            run(["git", "-C", str(repo), "update-ref", "-d", ref], check=False)
    return ref


def cmd_check_version(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    commit = check_commit(_git(repo, "rev-parse", args.git_ref + "^{commit}"))
    found = check_build_version(repo, commit, args.version)
    log(f"VERSION {found} can be packaged as {args.version}")
    return EXIT_OK


def cmd_build(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    version = args.version
    if not VERSION_RE.match(version):
        raise Refused("--version must look like 1.3.0 or 1.3.0-rc.1", EXIT_USAGE)
    release_tag = args.release_tag or f"v{version}"
    if not RELEASE_TAG_RE.match(release_tag):
        raise Refused("--release-tag must look like v1.3.0-rc.1", EXIT_USAGE)
    image_repo = args.image_repo
    tag = f"{image_repo}:{version}"
    if not TAGGED_REF_RE.match(tag):
        raise Refused(f"invalid image tag: {tag[:80]!r}", EXIT_USAGE)
    check_image_ref(args.image, "--image")
    out_root = Path(args.out).resolve()
    name = f"ChatBot5400-{version}-{normalize_platform(args.platform).replace('/', '-')}-offline"
    stage = out_root / name
    if stage.exists():
        raise Refused(f"{stage} exists: remove it or choose another --out", EXIT_USAGE)
    # --- git first: cheap, and nothing Docker runs when it cannot succeed -------
    proc = run(
        ["git", "-C", str(repo), "rev-parse", args.git_ref + "^{commit}"], check=False
    )
    if proc.returncode != 0:
        raise Refused(f"--git-ref {args.git_ref} is not a commit of {repo}", EXIT_USAGE)
    commit = check_commit(proc.stdout.strip())
    check_build_version(repo, commit, version)
    if _git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise Refused("the build checkout has uncommitted changes", EXIT_USAGE)
    base_commit = _git(
        repo, "rev-parse", "-q", "--verify", args.base_ref + "^{commit}", check=False
    )
    if not COMMIT_RE.match(base_commit):
        raise Refused(
            f"--base-ref {args.base_ref} does not exist in {repo}", EXIT_USAGE
        )
    try:
        for d in ("images", "source", "scripts", "docs"):
            (stage / d).mkdir(parents=True)
        bundle_rel = f"source/chatbot5400-{version}.bundle"
        log(
            f"git bundle {args.base_ref}..{commit[:12]} (named ref {BUNDLE_REF_PREFIX}{version})"
        )
        bundle_ref = create_bundle(
            repo,
            args.base_ref,
            commit,
            version,
            stage / bundle_rel,
            args.bundle_refs or [],
        )
        archive_src = f"source/chatbot5400-{version}-src.tar.gz"
        run(
            [
                "git",
                "-C",
                str(repo),
                "archive",
                "--format=tar.gz",
                f"--prefix=chatbot5400-{version}/",
                "-o",
                str(stage / archive_src),
                commit,
            ]  # fmt: skip
        )
        # --- Docker ---------------------------------------------------------------
        image = docker_inspect_image(args.image)
        img_platform = normalize_platform(
            f"{image.get('Os')}/{image.get('Architecture')}"
        )
        if img_platform != normalize_platform(args.platform):
            raise Refused(
                f"image platform {img_platform} != --platform {args.platform}",
                EXIT_USAGE,
            )
        labels = (image.get("Config") or {}).get("Labels") or {}
        revision = labels.get("org.opencontainers.image.revision")
        if revision and revision != commit:
            raise Refused(
                "image label revision differs from the commit being packaged",
                EXIT_USAGE,
            )
        log("inventory from the image (network disabled)")
        inv = json.loads(
            run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--entrypoint",
                    "/app/.venv/bin/python",
                    args.image,
                    "/app/scripts/offline/offline_package.py",
                    "inventory",
                ],  # fmt: skip
                timeout=900,
            ).stdout
        )
        if inv.get("app_version") and not version_matches(
            str(inv["app_version"]), version
        ):
            raise Refused(
                f"image VERSION {inv['app_version']} does not match --version {version}",
                EXIT_USAGE,
            )
        if args.image != tag:
            run(["docker", "tag", args.image, tag])
        archive_rel = f"images/{image_repo}-{version}.tar"
        log(f"docker save {tag} (keeps image metadata; docker export is never used)")
        run(["docker", "save", "-o", str(stage / archive_rel), tag], timeout=7200)
        ident = image_archive_identity(stage / archive_rel)
        if ident["repo_tags"] != [tag]:
            raise Refused(
                f"docker save produced the tags {ident['repo_tags']}, expected only [{tag!r}]",
                EXIT_USAGE,
            )

        here = Path(__file__).resolve().parent
        for f in (
            "offline_package.py", "verify-package.sh", "preflight.sh", "update.sh", "rollback.sh",
            "healthcheck.sh", "finish.sh", "status.sh", "pin.sh", "offline-update.conf.example",
        ):  # fmt: skip
            shutil.copy2(here / f, stage / "scripts" / f)
        docs = repo / "docs" / "deployment"
        for f in (
            "OFFLINE_UPDATE_PACKAGE.md", "OFFLINE_UPDATE_UBUNTU_GUIDE.md",
            "OFFLINE_UPDATE_ROLLBACK.md", "OFFLINE_UPDATE_SECURITY.md",
        ):  # fmt: skip
            if (docs / f).is_file():
                shutil.copy2(docs / f, stage / "docs" / f)
        if args.release_notes and Path(args.release_notes).is_file():
            shutil.copy2(args.release_notes, stage / "docs" / "RELEASE_NOTES.md")

        baked = inv.get("runtimes_baked", {})
        readiness_problems = []
        if not baked.get("docling"):
            readiness_problems.append(
                "Docling is not baked into the image (build with OCR_PREINSTALL_RUNTIMES=true)"
            )
        if not inv.get("tesseract"):
            readiness_problems.append(
                "Tesseract binary not in the image (build with OCR_INSTALL_TESSERACT=true)"
            )
        if not baked.get("tiktoken_offline"):
            readiness_problems.append(
                "the tiktoken encoding o200k_base does not load without network inside the "
                "image: chunking would hang or degrade offline"
            )
        manifest = {
            "package_format_version": FORMAT_VERSION,
            "application": {
                "name": "ChatBot5400",
                "version": version,
                "release_tag": release_tag,
                "supported_source_versions": args.supported_from,
            },
            "platform": normalize_platform(args.platform),
            "image": {
                "tag": tag,
                "id": image["Id"],
                "config_digest": ident["config_digest"],
                "diff_ids": ident["diff_ids"],
                "repo_tags": ident["repo_tags"],
                "archive_layout": ident["layout"],
                "archive": archive_rel,
                "archive_sha256": sha256_file(stage / archive_rel),
                "created": image.get("Created"),
                "labels": {
                    k: v
                    for k, v in labels.items()
                    if k.startswith("org.opencontainers")
                },
            },
            "source": {
                "commit": commit,
                "base_ref": args.base_ref,
                "base_commit": base_commit,
                "bundle_ref": bundle_ref,
                "git_bundle": bundle_rel,
                "archive": archive_src,
            },
            "database": {
                "schema_version": int(inv.get("schema_version") or 0),
                "migration_required": bool(args.migration_required),
                "compatible_schema_versions": [int(inv.get("schema_version") or 0)],
            },
            "dependencies": {
                **inv.get("dependencies", {}),
                "tesseract": inv.get("tesseract"),
                "python": inv.get("python"),
            },
            "runtime_artifacts": inv.get("runtime_artifacts", {}),
            "readiness": {
                "status": "READY" if not readiness_problems else "NOT_READY",
                "problems": readiness_problems,
            },
            "rollback": {
                "app_rollback_without_restore": not args.migration_required,
                "previous_versions": args.supported_from,
                "notes": "database untouched; previous image kept as a rollback tag",
            },
            "build": {
                "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "builder": "offline_package.py",
            },
            "files": {},
        }
        for p in sorted(stage.rglob("*")):
            if p.is_file():
                rel = p.relative_to(stage).as_posix()
                manifest["files"][rel] = {
                    "sha256": sha256_file(p),
                    "size": p.stat().st_size,
                }
        validate_manifest(manifest)
        (stage / MANIFEST).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (stage / SUMS).write_text(render_sums(manifest["files"]), encoding="utf-8")
        if args.sign_key:
            log("signing manifest.json with ssh-keygen -Y sign")
            run(
                [
                    "ssh-keygen",
                    "-Y",
                    "sign",
                    "-f",
                    args.sign_key,
                    "-n",
                    SIG_NAMESPACE,
                    str(stage / MANIFEST),
                ],  # fmt: skip
                capture=False,
            )
        else:
            log(
                "WARNING: package NOT signed: authenticity must be established by comparing "
                "its SHA-256 over a trusted channel"
            )
        package = out_root / f"{name}.tar.gz"
        with tarfile.open(package, "w:gz", compresslevel=6) as tar:
            for p in sorted(stage.rglob("*")):
                info = tar.gettarinfo(
                    str(p), arcname=f"{name}/{p.relative_to(stage).as_posix()}"
                )
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                info.mode = (
                    0o755 if (p.is_dir() or p.suffix in (".sh", ".py")) else 0o644
                )
                if p.is_file():
                    with open(p, "rb") as fh:
                        tar.addfile(info, fh)
                else:
                    tar.addfile(info)
    except BaseException:
        # No half-built stage is left behind to block the next run (F-04).
        shutil.rmtree(stage, ignore_errors=True)
        with contextlib.suppress(OSError):
            (out_root / f"{name}.tar.gz").unlink()
        raise
    digest = sha256_file(package)
    (out_root / f"{name}.tar.gz.sha256").write_text(f"{digest}  {package.name}\n")
    log(f"package: {package}")
    log(
        f"SHA-256: {digest}  <- send this value to the server operator over a SEPARATE trusted channel"
    )
    log(
        f"readiness: {manifest['readiness']['status']} {manifest['readiness']['problems']}"
    )
    return EXIT_OK


# --------------------------------------------------------------------------- #
# Server side helpers
# --------------------------------------------------------------------------- #


class Deployment:
    def __init__(self, cfg: Dict[str, str]) -> None:
        require(cfg, "DEPLOY_DIR", "COMPOSE_PROJECT")
        self.cfg = cfg
        self.dir = Path(cfg["DEPLOY_DIR"])
        self.project = cfg["COMPOSE_PROJECT"]
        self.files = [f for f in re.split(r"[\s:]+", cfg["COMPOSE_FILES"]) if f]
        self.app = cfg["APP_SERVICE"]
        self.db = cfg["DB_SERVICE"]
        for name in (self.app, self.db, self.project):
            if not SERVICE_RE.match(name):
                raise Refused(f"invalid service / project name: {name!r}", EXIT_USAGE)
        self.state = Path(cfg["STATE_DIR"])

    def compose(self, extra_files: Optional[List[str]] = None) -> List[str]:
        cmd = [
            "docker",
            "compose",
            "-p",
            self.project,
            "--project-directory",
            str(self.dir),
        ]
        for f in self.files + (extra_files or []):
            cmd += ["-f", f if os.path.isabs(f) else str(self.dir / f)]
        return cmd

    def config_json(self, extra_files: Optional[List[str]] = None) -> Dict[str, Any]:
        return json.loads(
            run(self.compose(extra_files) + ["config", "--format", "json"]).stdout
        )

    def container(self, service: str) -> Optional[str]:
        out = run(self.compose() + ["ps", "-q", service], check=False).stdout.strip()
        return out.splitlines()[0] if out else None

    def app_container(self) -> Optional[str]:
        return self.container(self.app)

    def container_image_id(self, container: str) -> str:
        return run(
            ["docker", "inspect", "--format", "{{.Image}}", container]
        ).stdout.strip()

    def exec_app(
        self, *cmd: str, check: bool = True, timeout: int = 600
    ) -> subprocess.CompletedProcess:
        return run(
            self.compose() + ["exec", "-T", self.app, *cmd],
            check=check,
            timeout=timeout,
        )

    def override_path(self, name: str = "image-override.yml") -> Path:
        return self.state / name

    def up_command(self, extra_files: List[str]) -> List[str]:
        """The ONLY way this tool (re)creates anything: the application, alone."""
        return self.compose(extra_files) + SAFE_UP + [self.app]


def render_override(app: str, image: str, extra_env: Dict[str, str]) -> str:
    """Compose override: image + no pulls + environment. Every value is checked and quoted."""
    check_image_ref(image)
    if not SERVICE_RE.match(app):
        raise Refused(f"invalid service name {app!r}", EXIT_USAGE)
    lines = [
        "services:",
        f"  {app}:",
        f'    image: "{image}"',
        "    pull_policy: never",
    ]
    if extra_env:
        lines.append("    environment:")
        for k, v in sorted(extra_env.items()):
            if not ENV_KEY_RE.match(k) or not ENV_VALUE_RE.match(v):
                raise Refused(f"unsafe environment override {k}", EXIT_USAGE)
            lines.append(f'      {k}: "{v}"')
    return "\n".join(lines) + "\n"


def write_image_override(
    dep: Deployment, image: str, extra_env: Dict[str, str]
) -> Path:
    """Our own override file (outside the deployment folder): image + no pulls."""
    text = render_override(dep.app, image, extra_env)
    dep.state.mkdir(parents=True, exist_ok=True)
    path = dep.override_path()
    atomic_write(path, text)
    return path


def parse_env_overrides(text: str) -> Dict[str, str]:
    out = {}
    for item in text.split():
        if "=" in item:
            k, v = item.split("=", 1)
            out[k] = v
    return out


def server_platform() -> str:
    try:
        arch = run(["docker", "info", "--format", "{{.Architecture}}"]).stdout.strip()
    except Refused:
        arch = _platform.machine()
    return normalize_platform(arch)


def _exec_int(dep: Deployment, code: str) -> Optional[int]:
    proc = dep.exec_app("/app/.venv/bin/python", "-c", code, check=False, timeout=120)
    try:
        return int(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


def current_schema(dep: Deployment) -> Optional[int]:
    return _exec_int(
        dep,
        "import asyncio\n"
        "from open_notebook.database.async_migrate import get_latest_version\n"
        "print(asyncio.run(get_latest_version()))\n",
    )


def running_jobs(dep: Deployment) -> Optional[int]:
    return _exec_int(
        dep,
        "import asyncio\n"
        "from open_notebook.database.repository import repo_query\n"
        "async def m():\n"
        '    r = await repo_query("SELECT count() AS n FROM command WHERE status IN '
        "['running','queued','new'] GROUP ALL\")\n"
        "    print(r[0]['n'] if r else 0)\n"
        "asyncio.run(m())\n",
    )


RECORD_TABLES = ("source", "notebook", "note", "source_embedding", "source_insight")


def record_counts(dep: Deployment) -> Optional[Dict[str, int]]:
    """Read-only row counts, to show that the data is the same before and after (F-21)."""
    code = (
        "import asyncio, json\n"
        "from open_notebook.database.repository import repo_query\n"
        f"TABLES = {list(RECORD_TABLES)!r}\n"
        "async def m():\n"
        "    out = {}\n"
        "    for t in TABLES:\n"
        "        r = await repo_query(f'SELECT count() AS n FROM {t} GROUP ALL')\n"
        "        out[t] = r[0]['n'] if r else 0\n"
        "    print(json.dumps(out))\n"
        "asyncio.run(m())\n"
    )
    proc = dep.exec_app("/app/.venv/bin/python", "-c", code, check=False, timeout=180)
    try:
        data = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None
    return {str(k): int(v) for k, v in data.items()} if isinstance(data, dict) else None


ARTIFACT_PROBE = r"""
import json, os
from pathlib import Path
roots = {}
try:
    from open_notebook.ocr import paths
    roots["ocr_models"] = str(paths.models_dir())
except Exception:
    roots["ocr_models"] = "/app/data/ocr/models"
hf = os.environ.get("HF_HOME", "/app/data/.cache/huggingface")
roots["huggingface_hub"] = os.path.join(hf, "hub")
out = {}
for name, root in roots.items():
    files = []
    if os.path.isdir(root):
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if d not in (".locks", "downloads", "logs")]
            for f in fn:
                p = os.path.join(dp, f)
                if f.endswith((".tmp", ".lock", ".incomplete")):
                    continue
                try:
                    size = os.stat(p).st_size  # follows the hub's links to its blobs
                except OSError:
                    size = -1  # a dangling link: the blob is gone
                files.append([os.path.relpath(p, root), size])
                if len(files) >= 20000:
                    break
    out[name] = sorted(files)
print("ARTIFACTS " + json.dumps(out))
"""


def artifact_snapshot(dep: Deployment) -> Optional[Dict[str, List[List[Any]]]]:
    """Model files on the data volume as the application container sees them (F-22).

    Layout Heron and TableFormer (Hugging Face hub cache), Tesseract traineddata
    (fast / best / OSD, the Agri versions), RapidOCR and EasyOCR weights. Names
    and sizes only: nothing is read, copied or sent anywhere.
    """
    proc = dep.exec_app(
        "/app/.venv/bin/python", "-c", ARTIFACT_PROBE, check=False, timeout=600
    )
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith("ARTIFACTS "):
            try:
                data = json.loads(line[len("ARTIFACTS ") :])
            except ValueError:
                return None
            return data if isinstance(data, dict) else None
    return None


def artifact_losses(
    before: Dict[str, List[List[Any]]], after: Optional[Dict[str, List[List[Any]]]]
) -> List[str]:
    """Files the old container had that the new one lacks or sees with another size."""
    if after is None:
        return ["the model files could not be listed in the new container"]
    lost = []
    for root, files in sorted(before.items()):
        now = {str(f[0]): f[1] for f in after.get(root) or []}
        for name, size in files:
            if str(name) not in now:
                lost.append(f"{root}/{name} (missing)")
            elif now[str(name)] != size:
                lost.append(f"{root}/{name} (size {size} -> {now[str(name)]})")
    return lost


def db_snapshot(dep: Deployment) -> Dict[str, Any]:
    """The REAL database container (docker inspect), not its Compose definition (F-21)."""
    container = dep.container(dep.db)
    if not container:
        raise Refused("database container not found", EXIT_PREFLIGHT)
    raw = run(["docker", "inspect", container]).stdout
    try:
        info = json.loads(raw)[0]
    except (ValueError, IndexError, KeyError):
        raise Refused(
            "docker inspect of the database container is unreadable", EXIT_PREFLIGHT
        ) from None
    mounts = sorted(
        [
            str(m.get("Type")),
            str(m.get("Name") or m.get("Source")),
            str(m.get("Destination")),
        ]
        for m in info.get("Mounts") or []
    )
    state = info.get("State") or {}
    return {
        "container_id": info.get("Id"),
        "image_id": info.get("Image"),
        "mounts": mounts,
        "started_at": state.get("StartedAt"),
        "running": bool(state.get("Running", state.get("Status") == "running")),
    }


def assert_db_untouched(dep: Deployment, baseline: Dict[str, Any], when: str) -> None:
    now = db_snapshot(dep)
    changed = [
        k
        for k in ("container_id", "image_id", "mounts", "started_at")
        if now.get(k) != baseline.get(k)
    ]
    if changed or not now.get("running"):
        raise Refused(
            f"DATABASE CONTAINER CHANGED {when}: {changed or ['not running']}. The update tool "
            "never touches it; stop and investigate before anything else (do not restore over "
            "new data without the approved procedure).",
            EXIT_UPDATE,
        )


def app_ports_loopback_only(dep: Deployment, container: str) -> Optional[bool]:
    """True when every published port of the running app is bound to loopback (maintenance)."""
    proc = run(
        ["docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", container],
        check=False,
    )
    try:
        ports = json.loads(proc.stdout.strip() or "null")
    except ValueError:
        return None
    if not isinstance(ports, dict):
        return None
    hosts = [b.get("HostIp") for bindings in ports.values() for b in (bindings or [])]
    if not hosts:
        return None
    return all(h in ("127.0.0.1", "::1") for h in hosts)


def container_env(container: str) -> Dict[str, str]:
    proc = run(
        ["docker", "inspect", "--format", "{{json .Config.Env}}", container],
        check=False,
    )
    try:
        items = json.loads(proc.stdout.strip() or "[]") or []
    except ValueError:
        return {}
    env = {}
    for item in items:
        if isinstance(item, str) and "=" in item:
            k, v = item.split("=", 1)
            env[k] = v
    return env


def load_package(
    package_dir: Optional[str], cfg: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """The verified package: bound to its verify report by hash, re-checked every time (F-26a)."""
    if not package_dir:
        raise Refused(
            "--package-dir is required (the folder verify-package.sh extracted)",
            EXIT_USAGE,
        )
    root = Path(package_dir).resolve()
    report_path = root.parent / "verify-report.json"
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Refused(
            "package not verified: run verify-package.sh first", EXIT_PREFLIGHT
        ) from None
    if report.get("result") != "VERIFIED" or report.get("package_dir") != str(root):
        raise Refused(
            "package not verified: run verify-package.sh first", EXIT_PREFLIGHT
        )
    try:
        manifest_bytes = (root / MANIFEST).read_bytes()
    except OSError:
        raise Refused("manifest.json missing", EXIT_PREFLIGHT) from None
    if sha256_bytes(manifest_bytes) != report.get("manifest_sha256"):
        raise Refused(
            "the package changed after it was verified (manifest hash differs): verify it again",
            EXIT_PREFLIGHT,
        )
    if report.get("signed") and cfg is not None:
        sig = root / SIGNATURE
        verify_signature_bytes(
            manifest_bytes,
            sig.read_bytes() if sig.is_file() else None,
            cfg["ALLOWED_SIGNERS"],
            cfg["SIGNER_IDENTITY"],
        )
        if not sig.is_file():
            raise Refused(
                "the signature of a signed package is gone: verify it again",
                EXIT_PREFLIGHT,
            )
    manifest = verify_tree(root, None, None, None)
    manifest["_package_sha256"] = report.get("package_sha256")
    manifest["_manifest_sha256"] = report.get("manifest_sha256")
    return manifest


def free_gb(path: str) -> float:
    return shutil.disk_usage(path).free / 1024**3


def current_baseline(dep: Deployment) -> Dict[str, Any]:
    """What is REALLY deployed right now: the starting point of an attempt (F-08, F-21)."""
    container = dep.app_container()
    if not container:
        raise Refused("application container not found", EXIT_PREFLIGHT)
    image_id = dep.container_image_id(container)
    image_ref = run(
        ["docker", "inspect", "--format", "{{.Config.Image}}", container], check=False
    ).stdout.strip()
    config = dep.config_json()
    baseline: Dict[str, Any] = {
        "taken_at": now_iso(),
        "image_id": image_id,
        "image_ref": image_ref,
        "app_version": dep.exec_app("cat", "/app/VERSION", check=False).stdout.strip(),
        "db": db_snapshot(dep),
        "config_sha256": sha256_bytes(json.dumps(config, sort_keys=True).encode()),
        "schema": current_schema(dep),
        "counts": record_counts(dep),
        "maintenance": app_ports_loopback_only(dep, container),
    }
    if (dep.dir / ".git").exists():
        baseline["source_commit"] = _git(dep.dir, "rev-parse", "HEAD", check=False)
        baseline["source_branch"] = _git(
            dep.dir, "symbolic-ref", "-q", "--short", "HEAD", check=False
        )
    return baseline


def cmd_preflight(
    args: argparse.Namespace, cfg: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    cfg = cfg or load_config(args.config)
    dep = Deployment(cfg)
    manifest = load_package(args.package_dir, cfg)
    checks: List[Dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str = "", fatal: bool = True) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail, "fatal": fatal})
        log(
            f"{'OK  ' if ok else ('FAIL' if fatal else 'WARN')} {name}{': ' + detail if detail else ''}"
        )

    plat = server_platform()
    check(
        "platform",
        plat == normalize_platform(manifest["platform"]),
        f"server {plat}, package {manifest['platform']}",
    )
    check(
        "readiness of the package",
        manifest.get("readiness", {}).get("status") == "READY" or args.accept_not_ready,
        json.dumps(manifest.get("readiness")),
    )
    try:
        base = dep.config_json()
        check(
            "compose config",
            dep.app in base.get("services", {}) and dep.db in base.get("services", {}),
            f"services {sorted(base.get('services', {}))}",
        )
    except Refused as e:
        check("compose config", False, str(e))
        base = {}
    container = dep.app_container()
    check("application container running", bool(container), container or "not found")
    current_image = dep.container_image_id(container) if container else ""
    if container:
        version_out = dep.exec_app("cat", "/app/VERSION", check=False).stdout.strip()
        supported = manifest["application"]["supported_source_versions"]
        check(
            "current version supported",
            version_out in supported or args.allow_version_mismatch,
            f"current {version_out or '?'}, supported {supported}",
        )
        schema = current_schema(dep)
        check(
            "database schema compatible",
            schema is not None and schema == manifest["database"]["schema_version"],
            f"database {schema}, package {manifest['database']['schema_version']}",
        )
        jobs = running_jobs(dep)
        check(
            "no background job running",
            jobs == 0 or args.ignore_jobs,
            f"running/queued jobs: {jobs}",
        )
        # F-22: the artifacts the OCR needs (Layout Heron, TableFormer, the engines'
        # models, Agri) must already be recorded as usable offline by the CURRENT
        # container. Stored state only: preflight writes nothing. The full
        # local-only check runs in the new container (health step O).
        ready = dep.exec_app(
            "/app/.venv/bin/python", "-m", "open_notebook.ocr.cli", "readiness",
            check=False, timeout=600,
        )  # fmt: skip
        check(
            "offline OCR artifacts recorded OFFLINE_READY in the current container",
            ready.returncode == 0 or args.accept_missing_artifacts,
            f"exit {ready.returncode}",
        )
    try:
        db = db_snapshot(dep)
        check(
            "database container inspected",
            bool(db.get("container_id")) and db["running"],
            str(db.get("container_id"))[:12],
        )
    except Refused as e:
        check("database container inspected", False, str(e))
    loaded = inspect_image(manifest["image"]["tag"])
    if loaded is not None:
        how = same_image(loaded[0], loaded[1], manifest["image"])
        check(
            "image tag free or already this image",
            how is not None,
            f"{manifest['image']['tag']} exists as {loaded[0][:19]} ({how or 'a DIFFERENT image'})",
        )
    check(
        "not already on the target image",
        current_image != (loaded[0] if loaded else manifest["image"]["id"]),
        current_image[:19],
        fatal=False,
    )
    root_dir = (
        run(
            ["docker", "info", "--format", "{{.DockerRootDir}}"], check=False
        ).stdout.strip()
        or "/var/lib/docker"
    )
    need = manifest["files"][manifest["image"]["archive"]][
        "size"
    ] * 2.5 / 1024**3 + float(cfg["MIN_FREE_GB_EXTRA"])
    have = free_gb(root_dir) if Path(root_dir).exists() else free_gb("/")
    check(
        "disk space for docker load",
        have >= need,
        f"free {have:.1f} GB, need {need:.1f} GB in {root_dir}",
    )
    state_free = free_gb(
        str(dep.state.parent if dep.state.parent.exists() else Path("/"))
    )
    check(
        "disk space for state / backup notes", state_free >= 1, f"{state_free:.1f} GB"
    )
    try:
        match = re.search(r"MemAvailable:\s+(\d+)", Path("/proc/meminfo").read_text())
        mem_kb = int(match.group(1)) if match else 0
        check(
            "available RAM",
            mem_kb / 1024**2 >= 2,
            f"{mem_kb / 1024**2:.1f} GB",
            fatal=False,
        )
    except OSError:
        check("available RAM", False, "unknown", fatal=False)
    check(
        "maintenance override configured",
        (
            bool(cfg["MAINTENANCE_OVERRIDE"])
            and Path(cfg["MAINTENANCE_OVERRIDE"]).is_file()
        )
        or args.no_maintenance,
        cfg["MAINTENANCE_OVERRIDE"] or "none",
    )
    check(
        "backup procedure configured",
        bool(cfg["BACKUP_CMD"]) or bool(args.backup_reference),
        "BACKUP_CMD set" if cfg["BACKUP_CMD"] else (args.backup_reference or "none"),
    )
    journal = Journal(dep.state) if dep.state.exists() else None
    status = journal.data.get("status") if journal else None
    same_package = bool(
        journal and journal.data.get("manifest_sha256") == manifest["_manifest_sha256"]
    )
    check(
        "no undecided update",
        status not in UNDECIDED_STATES
        and not (status in (IN_PROGRESS, FAILED) and not same_package),
        f"journal status {status or 'none'}",
    )
    fatal = [c for c in checks if not c["ok"] and c["fatal"]]
    result = {
        "result": "PASS" if not fatal else "FAIL",
        "checks": checks,
        "current_image": current_image,
    }
    if not getattr(args, "quiet", False):
        print(
            json.dumps(
                {"result": result["result"], "failed": [c["check"] for c in fatal]},
                indent=2,
            )
        )
    if fatal:
        raise Refused(
            f"preflight failed: {[c['check'] for c in fatal]}", EXIT_PREFLIGHT
        )
    return result


ALLOWED_APP_DIFF = {"image", "pull_policy", "environment", "ports"}


def compare_configs(
    dep: Deployment,
    before: Dict[str, Any],
    after: Dict[str, Any],
    maintenance: bool,
    allowed_env: Optional[Dict[str, str]] = None,
) -> None:
    """Effective Compose config before / after our override (F-12, F-21).

    The database service and every other service must be identical; the
    application may differ ONLY in image, pull_policy, the environment keys the
    override sets, and - in maintenance - ports bound to loopback.
    """
    if set(before.get("services", {})) != set(after.get("services", {})):
        raise Refused(
            "the effective compose config would add/remove services: refused",
            EXIT_UPDATE,
        )
    for name in before["services"]:
        if name != dep.app and before["services"][name] != after["services"][name]:
            what = "the database service" if name == dep.db else f"the service {name}"
            raise Refused(
                f"the effective compose config would change {what}: refused",
                EXIT_UPDATE,
            )
    for name in ("volumes", "networks", "secrets", "configs"):
        if before.get(name) != after.get(name):
            raise Refused(
                f"the effective compose config would change top-level {name}: refused",
                EXIT_UPDATE,
            )
    b_app, a_app = before["services"][dep.app], after["services"][dep.app]
    for key in sorted(set(b_app) | set(a_app)):
        if key not in ALLOWED_APP_DIFF and b_app.get(key) != a_app.get(key):
            raise Refused(
                f"the effective compose config would change '{key}' of the application: refused",
                EXIT_UPDATE,
            )
    b_env, a_env = (
        _env_map(b_app.get("environment")),
        _env_map(a_app.get("environment")),
    )
    for key in sorted(set(b_env) | set(a_env)):
        if b_env.get(key) != a_env.get(key) and key not in (allowed_env or {}):
            raise Refused(
                f"the effective compose config would change the variable {key}: refused",
                EXIT_UPDATE,
            )
    b_ports, a_ports = b_app.get("ports", []), a_app.get("ports", [])
    if not maintenance and b_ports != a_ports:
        raise Refused(
            "the effective compose config would change published ports: refused",
            EXIT_UPDATE,
        )
    if maintenance:
        if len(a_ports) != len(b_ports):
            raise Refused(
                "maintenance override must keep the same ports (loopback only)",
                EXIT_UPDATE,
            )
        for p in a_ports:
            ip = p.get("host_ip") if isinstance(p, dict) else None
            if ip not in ("127.0.0.1", "::1"):
                raise Refused(
                    "maintenance override must publish on loopback only", EXIT_UPDATE
                )
    if a_app.get("pull_policy") != "never":
        raise Refused("application pull_policy must be 'never'", EXIT_UPDATE)


def _env_map(env: Any) -> Dict[str, str]:
    if isinstance(env, dict):
        return {str(k): "" if v is None else str(v) for k, v in env.items()}
    out = {}
    for item in env or []:
        k, _, v = str(item).partition("=")
        out[k] = v
    return out


def recreate_app(
    dep: Deployment, journal: Journal, extra_files: List[str], step: str, **info: Any
) -> None:
    """Recreate ONLY the application, then prove the database container is the same one."""
    journal.data["compose_command"] = dep.up_command(extra_files)
    journal.save()
    run(dep.up_command(extra_files), capture=False, timeout=1800)
    journal.step(step, **info)
    baseline_db = (journal.data.get("baseline") or {}).get("db")
    if baseline_db:
        try:
            assert_db_untouched(dep, baseline_db, f"after {step}")
        except Refused:
            journal.data["db_changed"] = True
            journal.save()
            raise


def sync_source(
    dep: Deployment,
    root: Path,
    manifest: Dict[str, Any],
    journal: Optional[Journal] = None,
) -> None:
    """Fast-forward the deployment's git checkout from the bundle; never reset, never force.

    Only the one ref recorded in the manifest is fetched (no wildcard), into our
    own namespace; local commits or conflicting local edits stop the step with
    the checkout unchanged.
    """
    repo = dep.dir
    if not (repo / ".git").exists():
        raise Refused(
            "DEPLOY_DIR is not a git checkout: use the source archive manually",
            EXIT_UPDATE,
        )
    src = manifest["source"]
    commit, ref, version = (
        check_commit(src["commit"]),
        src["bundle_ref"],
        manifest["application"]["version"],
    )
    if not BUNDLE_REF_RE.match(ref):
        raise Refused("manifest source.bundle_ref invalid", EXIT_UPDATE)
    bundle = root / src["git_bundle"]
    run(["git", "-C", str(repo), "bundle", "verify", str(bundle)])
    if bundle_heads(repo, bundle).get(ref) != commit:
        raise Refused(
            "the bundle does not carry the release commit under the manifest's ref",
            EXIT_UPDATE,
        )
    local = f"refs/cb5400-offline/incoming/{version}"
    previous = _git(repo, "rev-parse", "HEAD")
    branch = _git(repo, "symbolic-ref", "-q", "--short", "HEAD", check=False)
    if journal is not None:
        journal.data["source"] = {
            "previous_commit": previous,
            "previous_branch": branch,
            "target_commit": commit,
        }
        journal.save()
    run(["git", "-C", str(repo), "fetch", "--no-tags", str(bundle), f"{ref}:{local}"])
    if _git(repo, "rev-parse", local) != commit:
        raise Refused("the fetched ref is not the release commit", EXIT_UPDATE)
    if (
        run(
            ["git", "-C", str(repo), "merge-base", "--is-ancestor", "HEAD", commit],
            check=False,
        ).returncode
        != 0
    ):
        raise Refused(
            "local history diverges from the release (local commits?): nothing changed, merge manually",
            EXIT_UPDATE,
        )
    tag = manifest["application"]["release_tag"]
    if (
        run(
            ["git", "-C", str(repo), "rev-parse", "-q", "--verify", f"refs/tags/{tag}"],
            check=False,
        ).returncode
        != 0
    ):
        run(["git", "-C", str(repo), "tag", tag, commit])
    if branch:
        run(
            ["git", "-C", str(repo), "merge", "--ff-only", commit]
        )  # refuses conflicting local edits
    else:
        run(
            ["git", "-C", str(repo), "checkout", "--detach", commit]
        )  # refuses conflicting local edits
    log(f"K: source now at {commit[:12]} (.env and untracked files untouched)")


def restore_source(dep: Deployment, journal: Journal) -> str:
    """After an app rollback: put the checkout back where it was, only when that is safe (F-24b)."""
    src = journal.data.get("source") or {}
    previous = src.get("previous_commit")
    repo = dep.dir
    if not previous or not (repo / ".git").exists():
        return "no source change recorded"
    if not COMMIT_RE.match(previous):
        return "recorded commit is not a commit id: source left as it is"
    head = _git(repo, "rev-parse", "HEAD", check=False)
    if head == previous:
        return "source already at the previous commit"
    if head != src.get("target_commit"):
        return f"source is at {head[:12]}, not at the release commit: left as it is (check manually)"
    if _git(repo, "status", "--porcelain", "--untracked-files=no", check=False):
        return (
            "the working tree has local changes: source NOT moved. When ready: "
            f"git -C {repo} checkout --detach {previous}"
        )
    proc = run(["git", "-C", str(repo), "checkout", "--detach", previous], check=False)
    if proc.returncode != 0:
        return f"git refused to check out {previous[:12]}: source left as it is"
    journal.step("ROLLBACK_source", commit=previous)
    return f"source back at {previous[:12]} (detached; branch {src.get('previous_branch') or '-'} not moved)"


def rapidocr_to_volume(dep: Deployment, journal: Journal, accept_missing: bool) -> None:
    """Move the RapidOCR weights of the OLD container onto the data volume, and check it worked.

    The weights live inside the container (lost on recreate) unless they are on
    the volume. The copy is SHA-256 checked by the application; here its result
    is no longer ignored (F-22): a failed or partial copy stops the update
    before the point of no return, unless the operator accepts that RapidOCR
    will not work offline (--accept-missing-rapidocr, e.g. a server that only
    uses Tesseract / Agri).
    """
    code = (
        "import json\n"
        "from open_notebook.ocr import installer, readiness\n"
        "copied = installer.import_rapidocr_weights()\n"
        "print(json.dumps({'copied': copied, 'on_volume': readiness._rapidocr_weights_signature(True)}))\n"
    )
    res = dep.exec_app("/app/.venv/bin/python", "-c", code, check=False, timeout=900)
    summary: Dict[str, Any] = {"rc": res.returncode}
    try:
        data = json.loads((res.stdout.strip().splitlines() or ["{}"])[-1])
    except ValueError:
        data = {}
    copied = data.get("copied") if isinstance(data, dict) else None
    on_volume = data.get("on_volume") if isinstance(data, dict) else None
    bad = [
        k
        for k, v in (copied or {}).items()
        if "mismatch" in str(v) or "fail" in str(v).lower()
    ]
    summary.update(
        copied=len(copied or {}),
        on_volume=len(on_volume or []),
        problems=bad[:10],
    )
    ok = (
        res.returncode == 0 and isinstance(copied, dict) and not bad and bool(on_volume)
    )
    journal.step("RAPIDOCR_weights", ok=ok, **summary)
    if not ok and not accept_missing:
        raise Refused(
            "RapidOCR weights are not on the data volume (copy failed, was partial, or the "
            f"current container never had them): {summary}. The new container could not OCR "
            "with RapidOCR offline. Prepare RapidOCR in the current container first, or pass "
            "--accept-missing-rapidocr if this server does not use RapidOCR.",
            EXIT_UPDATE,
        )


def start_attempt(dep: Deployment, journal: Journal, manifest: Dict[str, Any]) -> None:
    """Decide: resume the same transaction, start a new one, or refuse (F-08, F-24c)."""
    status = journal.data.get("status")
    same = journal.data.get("manifest_sha256") == manifest["_manifest_sha256"]
    if status in UNDECIDED_STATES:
        raise Refused(
            f"an update is deployed and waiting for a decision (status {status}): "
            "finish it (finish.sh --approve) or roll it back (rollback.sh app) first",
            EXIT_UPDATE,
        )
    container = dep.app_container()
    running = dep.container_image_id(container) if container else ""
    if status in (IN_PROGRESS, FAILED):
        baseline_image = (journal.data.get("baseline") or {}).get("image_id")
        if not same:
            raise Refused(
                "another update is unfinished: roll it back first (rollback.sh interrupted)",
                EXIT_UPDATE,
            )
        if running and running != baseline_image:
            raise Refused(
                f"the unfinished update (status {status}) left the application on another "
                "image than its baseline: roll it back first (rollback.sh interrupted)",
                EXIT_UPDATE,
            )
        if status == IN_PROGRESS and not journal.done("N_recreated"):
            log(
                f"resuming attempt {journal.data.get('attempt_id')} (nothing was recreated yet)"
            )
            return
        # failed, or interrupted after the recreate, but the baseline image runs
        # again: that transaction is over. A new one starts, with its own backup.
    carried: Dict[str, str] = {}
    if status == COMPLETED:
        previous_env = journal.data.get("override_env") or {}
        carried = {k: previous_env[k] for k in CARRIED_ENV if k in previous_env}
    if journal.data:
        archived = journal.archive()
        log(f"previous attempt archived: {archived}")
    journal.data = {
        "schema": 2,
        "attempt_id": new_attempt_id(),
        "version": manifest["application"]["version"],
        "package_sha256": manifest["_package_sha256"],
        "manifest_sha256": manifest["_manifest_sha256"],
        "target_image_tag": manifest["image"]["tag"],
        "status": IN_PROGRESS,
        "started": now_iso(),
        "steps": [],
        "carried_env": carried,
        # Taken BEFORE anything changes (and before any source sync): F-21.
        "baseline": current_baseline(dep),
    }
    journal.save()
    log(
        f"attempt {journal.data['attempt_id']} started; baseline image {journal.data['baseline']['image_id'][:19]}"
    )


CARRIED_ENV = ("OCR_LEGAL_NORMALIZATION_ENABLED",)


def attempt_env(cfg: Dict[str, str], journal: Journal) -> Dict[str, str]:
    """Environment of the generated override: the configured offline variables plus
    the operator's Legal gate decision carried over from the previous update."""
    env = parse_env_overrides(cfg["APP_ENV_OVERRIDES"])
    env.update(journal.data.get("carried_env") or {})
    return env


def backup_is_fresh(journal: Journal, cfg: Dict[str, str]) -> bool:
    """A backup belongs to THIS attempt and is recent enough to reuse on a resume."""
    step = journal.last("J_backup_verified")
    if not journal.done("I_backup") or step is None:
        return False
    try:
        age = _dt.datetime.now() - _dt.datetime.fromisoformat(step["at"])
        limit = _dt.timedelta(minutes=float(cfg["BACKUP_MAX_AGE_MINUTES"]))
    except (ValueError, KeyError):
        return False
    return age <= limit


def cmd_update(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    dep = Deployment(cfg)
    manifest = load_package(args.package_dir, cfg)
    root = Path(args.package_dir).resolve()
    target = manifest["image"]["tag"]
    maintenance = [] if args.no_maintenance else [cfg["MAINTENANCE_OVERRIDE"]]
    env = parse_env_overrides(cfg["APP_ENV_OVERRIDES"])
    plan = [
        "   authenticate the package again (hash of the manifest, signature)",
        "   start a NEW attempt (own id, own backup) unless the same attempt is resumed",
        "   snapshot the REAL database container and the effective configuration",
        "G  check the image archive (only the approved tag), docker load, identify the image",
        "H  tag the CURRENT application image as rollback image (verified by image ID)",
        "I  run the approved backup command (BACKUP_CMD) / record the operator's backup reference",
        "J  run BACKUP_VERIFY_CMD (restore check) when configured",
        "K  synchronise the source from the git bundle (only with --sync-source; fast-forward only)",
        "L  keep .env / compose files untouched; write our own image override (pull_policy never)",
        "-- move RapidOCR weights onto the data volume in the OLD container and CHECK the result",
        "M+N recreate ONLY the application: up -d --no-deps --no-build --pull never (maintenance)",
        "   prove the database container is the same (id, image, mounts, start time)",
        "O  health, offline readiness, schema, row counts, token counting offline",
        "P  normal mode only after approval: finish.sh --approve (health-checked)",
        "   optional: pin.sh --apply so that a plain `docker compose up -d` keeps the new image",
    ]
    if not args.apply:
        log("DRY RUN (nothing changes). Plan:")
        for p in plan:
            log("  " + p)
        args.quiet = True
        cmd_preflight(args, cfg)
        log(
            "dry run complete: preflight PASS. Re-run with --apply to perform the update."
        )
        return EXIT_OK

    with update_lock(dep.state):
        journal = Journal(dep.state)
        args.quiet = True
        cmd_preflight(args, cfg)
        start_attempt(dep, journal, manifest)
        env = attempt_env(cfg, journal)
        baseline = journal.data["baseline"]
        before_config = dep.config_json()  # before any source sync (F-21)

        if not journal.done("G_load"):
            log("G: docker load")
            check_image_archive(root / manifest["image"]["archive"], manifest["image"])
            run(
                ["docker", "load", "-i", str(root / manifest["image"]["archive"])],
                timeout=7200,
            )
            loaded = inspect_image(target)
            how = (
                same_image(loaded[0], loaded[1], manifest["image"]) if loaded else None
            )
            if loaded is None or how is None:
                raise Refused(
                    f"the loaded image {loaded[0] if loaded else '?'} is not the packaged one "
                    "(id, config digest and layers all differ)",
                    EXIT_UPDATE,
                )
            journal.data["expected_image_id"] = loaded[0]
            journal.step("G_load", image_id=loaded[0], identified_by=how)
        else:
            loaded = inspect_image(target)
            if loaded is None or loaded[0] != journal.data.get("expected_image_id"):
                raise Refused(
                    f"the tag {target} no longer points to the loaded image",
                    EXIT_UPDATE,
                )
        expected_image = journal.data["expected_image_id"]

        tagged = (
            inspect_image(journal.data.get("rollback_tag", ""))
            if journal.data.get("rollback_tag")
            else None
        )
        if tagged is None or tagged[0] != baseline["image_id"]:
            rollback_tag = (
                f"{cfg['IMAGE_REPO']}:rollback-{journal.data['attempt_id'].lower()}"
            )
            check_image_ref(rollback_tag)
            run(["docker", "tag", baseline["image_id"], rollback_tag])
            journal.data["rollback_tag"] = rollback_tag
            journal.step(
                "H_rollback_tag", tag=rollback_tag, image_id=baseline["image_id"]
            )
            log(f"H: rollback image {rollback_tag} -> {baseline['image_id'][:19]}")

        if not backup_is_fresh(journal, cfg):
            if cfg["BACKUP_CMD"]:
                log("I: running BACKUP_CMD")
                run(
                    ["/bin/sh", "-c", cfg["BACKUP_CMD"]],
                    capture=False,
                    timeout=6 * 3600,
                )
                journal.step("I_backup", method="BACKUP_CMD")
            elif args.backup_reference:
                journal.step(
                    "I_backup", method="operator", reference=args.backup_reference
                )
            else:
                raise Refused(
                    "no backup: set BACKUP_CMD or pass --backup-reference after an approved backup",
                    EXIT_UPDATE,
                )
            if cfg["BACKUP_VERIFY_CMD"]:
                run(
                    ["/bin/sh", "-c", cfg["BACKUP_VERIFY_CMD"]],
                    capture=False,
                    timeout=6 * 3600,
                )
                journal.step("J_backup_verified", method="BACKUP_VERIFY_CMD")
            elif args.backup_verified:
                journal.step("J_backup_verified", method="operator attestation")
            else:
                raise Refused(
                    "backup restore not verified: set BACKUP_VERIFY_CMD or pass --backup-verified",
                    EXIT_UPDATE,
                )
        if args.sync_source and not journal.done("K_source"):
            sync_source(dep, root, manifest, journal)
            journal.step("K_source", commit=manifest["source"]["commit"])
        override = write_image_override(dep, target, env)
        after = dep.config_json([str(override)] + maintenance)
        if after["services"][dep.app].get("image") != target:
            raise Refused(
                "the effective configuration does not use the new image", EXIT_UPDATE
            )
        compare_configs(
            dep, before_config, after, maintenance=bool(maintenance), allowed_env=env
        )
        rapidocr_to_volume(dep, journal, args.accept_missing_rapidocr)
        # What the OLD container can see on the data volume, after the RapidOCR
        # copy and before the recreate; compared in the NEW container (step O).
        artifacts = artifact_snapshot(dep)
        if artifacts is None:
            raise Refused(
                "the model files on the data volume could not be listed in the current "
                "container: stop before the recreate",
                EXIT_UPDATE,
            )
        atomic_write(
            dep.state / f"artifacts-{journal.data['attempt_id']}.json",
            json.dumps(artifacts, sort_keys=True),
        )
        journal.step(
            "ARTIFACTS_snapshot",
            files={k: len(v) for k, v in artifacts.items()},
            sha256=sha256_bytes(json.dumps(artifacts, sort_keys=True).encode()),
        )
        assert_db_untouched(dep, baseline["db"], "before the recreate")
        log("M+N: recreating ONLY the application container")
        journal.data["maintenance"] = bool(maintenance)
        recreate_app(
            dep,
            journal,
            [str(override)] + maintenance,
            "N_recreated",
            maintenance=bool(maintenance),
        )
        journal.data["status"] = PENDING_CHECKS
        journal.save()
        ok = health_checks(
            dep, cfg, expect_image=expected_image, journal=journal, manifest=manifest
        )
        journal.step("O_P_checks", ok=ok)
        journal.data["status"] = AWAITING if ok else FAILED
        journal.save()
        if not ok:
            log(
                "CHECKS FAILED: the application stays in maintenance mode. Roll back with: rollback.sh app"
            )
            return EXIT_UPDATE
        log(
            "update deployed in maintenance mode. After acceptance: finish.sh --approve <name>"
        )
        return EXIT_OK


def health_checks(
    dep: Deployment,
    cfg: Dict[str, str],
    expect_image: Optional[str],
    prove_offline: bool = False,
    journal: Optional[Journal] = None,
    manifest: Optional[Dict[str, Any]] = None,
) -> bool:
    import urllib.request

    ok = True
    container = None
    for _ in range(60):
        container = dep.app_container()
        if container:
            break
        time.sleep(2)
    if not container:
        log("FAIL application container not running")
        return False
    running = dep.container_image_id(container)
    if expect_image and running != expect_image:
        log(
            f"FAIL DRIFT: the container runs {running[:19]}, expected {expect_image[:19]}"
        )
        ok = False
    url = cfg["HEALTH_URL"]
    if not re.match(r"^http://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?/", url):
        log("FAIL HEALTH_URL must be a loopback http URL")
        return False
    # Never through a proxy: http_proxy in root's shell must not break (or leak) a
    # request to 127.0.0.1 (F-26d).
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    healthy = False
    for _ in range(90):
        try:
            with opener.open(url, timeout=5) as r:  # noqa: S310 - loopback only (checked above)
                healthy = r.status == 200
        except Exception:  # noqa: BLE001
            healthy = False
        if healthy:
            break
        time.sleep(5)
    log(f"{'OK  ' if healthy else 'FAIL'} API health {url}")
    ok &= healthy
    py = "/app/.venv/bin/python"
    token_probe = (
        "import threading, sys\n"
        "from open_notebook.utils.chunking import chunk_text\n"
        "r = {}\n"
        "def w():\n"
        "    r['n'] = len(chunk_text('Điều 1. Kiểm tra tách đoạn khi không có mạng. ' * 40))\n"
        "t = threading.Thread(target=w, daemon=True); t.start(); t.join(60)\n"
        "sys.exit(0 if r.get('n') else 1)\n"
    )
    checks = [
        ("Docling importable", [py, "-c", "import docling"]),
        ("OCR engine status", [py, "-m", "open_notebook.ocr.cli", "status"]),
        (
            "offline readiness (local-only check)",
            [py, "-m", "open_notebook.ocr.cli", "readiness", "--check"],
        ),
        (
            "custom model (Agri) status",
            [py, "-m", "open_notebook.ocr.cli", "custom", "status", "--no-db"],
        ),
        ("chunking / token counting without network", [py, "-c", token_probe]),
    ]
    for name, cmd in checks:
        res = dep.exec_app(*cmd, check=False, timeout=1800)
        good = res.returncode == 0
        log(f"{'OK  ' if good else 'FAIL'} {name}")
        ok &= good
    baseline = (journal.data.get("baseline") if journal else None) or {}
    if manifest is not None or baseline.get("schema") is not None:
        want = (
            manifest["database"]["schema_version"]
            if manifest
            else baseline.get("schema")
        )
        got = current_schema(dep)
        good = got == want
        log(
            f"{'OK  ' if good else 'FAIL'} database schema after start: {got} (expected {want})"
        )
        ok &= good
    if baseline.get("counts"):
        got_counts = record_counts(dep)
        good = got_counts == baseline["counts"]
        log(f"{'OK  ' if good else 'FAIL'} row counts unchanged: {got_counts}")
        ok &= good
    snapshot = (
        dep.state / f"artifacts-{journal.data.get('attempt_id')}.json"
        if journal is not None
        else None
    )
    if snapshot is not None and snapshot.is_file():
        try:
            before_files = json.loads(snapshot.read_text(encoding="utf-8"))
        except ValueError:
            before_files = None
        lost = (
            ["the snapshot of the model files is unreadable"]
            if not isinstance(before_files, dict)
            else artifact_losses(before_files, artifact_snapshot(dep))
        )
        good = not lost
        detail = "" if good else f": {lost[:10]}{' ...' if len(lost) > 10 else ''}"
        log(
            f"{'OK  ' if good else 'FAIL'} model files on the data volume unchanged "
            f"(Heron, TableFormer, Tesseract/OSD/Agri, RapidOCR, EasyOCR){detail}"
        )
        ok &= good
    if baseline.get("db"):
        try:
            assert_db_untouched(dep, baseline["db"], "at the health check")
            log("OK   database container unchanged (id, image, mounts, start time)")
        except Refused as e:
            log(f"FAIL {e}")
            ok = False
    if prove_offline:
        probe = (
            "import socket\ntry:\n    socket.create_connection(('huggingface.co', 443), 5)\n"
            "    print('REACHABLE')\nexcept OSError:\n    print('BLOCKED')\n"
        )
        res = dep.exec_app(py, "-c", probe, check=False, timeout=60)
        blocked = res.stdout.strip().endswith("BLOCKED")
        log(
            f"{'OK  ' if blocked else 'FAIL'} outbound network blocked from the container"
        )
        ok &= blocked
    return bool(ok)


def drift_report(dep: Deployment, journal: Journal, cfg: Dict[str, str]) -> List[str]:
    """Differences between what the journal says is deployed and what runs (F-11)."""
    status = journal.data.get("status")
    if status in (COMPLETED, AWAITING, PENDING_CHECKS, FINISH_FAILED):
        expected = journal.data.get("expected_image_id")
    elif status == ROLLED_BACK:
        expected = (journal.data.get("baseline") or {}).get("image_id")
    else:
        return []
    problems: List[str] = []
    container = dep.app_container()
    if not container:
        return ["the application container is not running"]
    running = dep.container_image_id(container)
    if expected and running != expected:
        problems.append(
            f"IMAGE DRIFT: the container runs {running[:19]} but the journal ({status}) expects "
            f"{expected[:19]} - was `docker compose up` run without the override?"
        )
    if status != ROLLED_BACK:
        env = container_env(container)
        want = journal.data.get("override_env") or parse_env_overrides(
            cfg["APP_ENV_OVERRIDES"]
        )
        for key, value in sorted(want.items()):
            if env.get(key) != value:
                problems.append(
                    f"ENVIRONMENT DRIFT: {key} is {env.get(key)!r}, expected {value!r}"
                )
    return problems


def expected_image(journal: Journal) -> str:
    """The image ID this attempt deployed; a journal of the Phase 12 tool has none."""
    value = journal.data.get("expected_image_id")
    if not isinstance(value, str) or not IMAGE_ID_RE.match(value):
        raise Refused(
            "this journal was written by an older version of the tool (no image ID "
            "recorded): roll back with `rollback.sh app --to-image <previous tag>` or "
            "run the update again with this version",
            EXIT_UPDATE,
        )
    return value


def compose_command_text(
    dep: Deployment, journal: Journal, extra_files: List[str]
) -> str:
    cmd = dep.up_command(extra_files)
    return (
        "# The ONLY command that may (re)create the ChatBot5400 application after this update.\n"
        "# A plain `docker compose up -d` in the deployment folder uses the OLD definition\n"
        "# (no image override, no offline variables) unless the update was pinned (pin.sh).\n"
        f"# attempt {journal.data.get('attempt_id')}  image {journal.data.get('expected_image_id')}\n"
        + " ".join(_shell_quote(c) for c in cmd)
        + "\n"
    )


def _shell_quote(value: str) -> str:
    return (
        value
        if re.match(r"^[A-Za-z0-9_./:=@+\-]+$", value)
        else "'" + value.replace("'", "'\\''") + "'"
    )


def cmd_finish(args: argparse.Namespace) -> int:
    if not args.approve:
        raise Refused(
            "finish needs --approve (acceptance done, approval recorded)", EXIT_USAGE
        )
    cfg = load_config(args.config)
    dep = Deployment(cfg)
    with update_lock(dep.state):
        journal = Journal(dep.state)
        if journal.data.get("status") not in (AWAITING, FINISH_FAILED):
            raise Refused(
                f"nothing to finish (status {journal.data.get('status')})", EXIT_UPDATE
            )
        expected = expected_image(journal)
        override = dep.override_path()
        if not override.is_file():
            raise Refused(
                "the image override of this update is missing from STATE_DIR",
                EXIT_UPDATE,
            )
        before = dep.config_json()
        after = dep.config_json([str(override)])
        env = attempt_env(cfg, journal)
        compare_configs(dep, before, after, maintenance=False, allowed_env=env)
        if after["services"][dep.app].get("image") != journal.data["target_image_tag"]:
            raise Refused(
                "the override no longer points to the image of this update", EXIT_UPDATE
            )
        recreate_app(
            dep, journal, [str(override)], "Q_normal_mode", approved_by=args.approve
        )
        ok = health_checks(dep, cfg, expect_image=expected, journal=journal)
        journal.data["override_env"] = env
        journal.data["maintenance"] = False
        atomic_write(
            dep.state / "compose-command.txt",
            compose_command_text(dep, journal, [str(override)]),
        )
        if not ok:
            journal.step("Q_checks", ok=False)
            journal.data["status"] = FINISH_FAILED
            journal.save()
            log(
                "FINISH FAILED: the application does not pass its checks in normal mode. It is "
                "NOT marked completed. Fix the cause and run finish.sh again, or roll back "
                "with: rollback.sh app"
            )
            return EXIT_UPDATE
        journal.step("Q_checks", ok=True)
        journal.data["status"] = COMPLETED
        journal.data["completed"] = now_iso()
        journal.save()
        log("normal mode restored and checked")
        log(
            f"use ONLY this command to recreate the application: {dep.state / 'compose-command.txt'}"
        )
        log(
            "a plain `docker compose up -d` would return to the old definition; to make the new"
        )
        log("image survive it, run: pin.sh (dry run) then pin.sh --apply")
    return EXIT_OK


# --------------------------------------------------------------------------- #
# Persistent pin (F-11): explicit operator consent, dry-run, backup, rollback
# --------------------------------------------------------------------------- #


def deploy_image_ref(dep: Deployment, journal: Journal) -> str:
    """The image NAME the deployment's own compose files resolve to for the application.

    A service with ``build:`` and no ``image:`` is named ``<project>-<service>``
    by Compose v2. The name is only retargeted when it is provably the one in
    use: it must be the reference the container replaced by this update was
    created from. Anything else is refused - a wrong guess would tag an image
    nothing uses and leave the drift in place.
    """
    service = dep.config_json()["services"][dep.app]
    declared = service.get("image") or f"{dep.project}-{dep.app}"
    used = str((journal.data.get("baseline") or {}).get("image_ref") or "")

    def named(ref: str) -> str:
        return ref if ":" in ref.rsplit("/", 1)[-1] else ref + ":latest"

    if not used or IMAGE_ID_RE.match(used) or named(used) != named(declared):
        raise Refused(
            f"cannot pin automatically: the compose files of the deployment name the image "
            f"{declared!r}, but the container this update replaced was created from "
            f"{used or '?'!r}. Keep using the command in compose-command.txt, or point the "
            "deployment's image name to the new image by hand (docker tag) after checking it.",
            EXIT_UPDATE,
        )
    return check_image_ref(named(declared), "image reference of the deployment")


def pin_plan(dep: Deployment, journal: Journal, cfg: Dict[str, str]) -> Dict[str, Any]:
    if journal.data.get("status") != COMPLETED:
        raise Refused(
            f"pin needs a completed update (status {journal.data.get('status')})",
            EXIT_UPDATE,
        )
    expected = expected_image(journal)
    ref = deploy_image_ref(dep, journal)
    current = inspect_image(ref)
    env = journal.data.get("override_env") or parse_env_overrides(
        cfg["APP_ENV_OVERRIDES"]
    )
    return {
        "deploy_image_ref": ref,
        "currently_points_to": current[0] if current else None,
        "will_point_to": expected,
        "pin_file": str(dep.dir / PIN_FILE),
        "pin_file_content": render_override(dep.app, ref, env),
        "compose_file_line": "COMPOSE_FILE=" + ":".join(dep.files + [PIN_FILE]),
    }


def cmd_pin(args: argparse.Namespace) -> int:
    """Make the definition in DEPLOY_DIR resolve to the NEW image (operator's decision).

    1. the image name the deployment's own compose files use is re-tagged to the
       new image ID: a plain `docker compose up -d` can no longer fall back to
       the old image (the old one stays reachable through the rollback tag);
    2. a new file docker-compose.offline-pin.yml is written into DEPLOY_DIR
       (never .env, never an existing compose file) with the offline variables;
       it takes effect only when the OPERATOR adds it to COMPOSE_FILE - the tool
       prints the line and does not edit .env.
    Both are recorded in the journal and undone by `pin --undo` / rollback.
    """
    cfg = load_config(args.config)
    dep = Deployment(cfg)
    with update_lock(dep.state):
        journal = Journal(dep.state)
        if args.undo:
            return _unpin(dep, journal, to_image=None)
        plan = pin_plan(dep, journal, cfg)
        print(
            json.dumps(
                {k: v for k, v in plan.items() if k != "pin_file_content"}, indent=2
            )
        )
        print("--- " + PIN_FILE + " ---\n" + plan["pin_file_content"], end="")
        if not args.apply:
            log("DRY RUN: nothing changed. Re-run with --apply to pin.")
            return EXIT_OK
        pin_file = Path(plan["pin_file"])
        backup = None
        if pin_file.exists():
            backups = dep.state / "config-backups" / str(journal.data.get("attempt_id"))
            backups.mkdir(parents=True, exist_ok=True)
            backup = backups / PIN_FILE
            shutil.copy2(pin_file, backup)
        journal.data["pin"] = {
            "applied": False,
            "deploy_image_ref": plan["deploy_image_ref"],
            "previous_target": plan["currently_points_to"],
            "pin_file": str(pin_file),
            "pin_file_backup": str(backup) if backup else None,
        }
        journal.save()
        run(["docker", "tag", plan["will_point_to"], plan["deploy_image_ref"]])
        atomic_write(pin_file, plan["pin_file_content"])
        journal.data["pin"]["applied"] = True
        journal.step("PIN", deploy_image_ref=plan["deploy_image_ref"])
        log(f"{plan['deploy_image_ref']} now points to the new image")
        log(
            f"to keep the offline variables too, add this line to {dep.dir / '.env'} yourself:"
        )
        log("  " + plan["compose_file_line"])
    return EXIT_OK


def _unpin(
    dep: Deployment, journal: Journal, to_image: Optional[str], remove_file: bool = True
) -> int:
    """Point the deployment's image name back; restore / remove our pin file.

    After a rollback the pin file is kept (``remove_file=False``): it names the
    deployment's own image reference, which now points to the previous image
    again, so a COMPOSE_FILE line that lists it keeps working.
    """
    pin = journal.data.get("pin") or {}
    if not pin.get("applied"):
        log("no pin recorded: nothing to undo")
        return EXIT_OK
    target = (
        to_image
        or pin.get("previous_target")
        or (journal.data.get("baseline") or {}).get("image_id")
    )
    if target and IMAGE_ID_RE.match(str(target)):
        run(["docker", "tag", target, check_image_ref(pin["deploy_image_ref"])])
        log(f"{pin['deploy_image_ref']} points to {target[:19]} again")
    pin_file = Path(pin.get("pin_file") or "")
    if remove_file:
        if pin.get("pin_file_backup") and Path(pin["pin_file_backup"]).is_file():
            shutil.copy2(pin["pin_file_backup"], pin_file)
        elif pin_file.name == PIN_FILE and pin_file.is_file():
            pin_file.unlink()
            log(f"if {PIN_FILE} was added to COMPOSE_FILE in .env, remove it there")
    pin["applied"] = False
    journal.step("UNPIN", image=target, pin_file_kept=not remove_file)
    return EXIT_OK


def cmd_rollback(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    dep = Deployment(cfg)
    if args.what == "agri":
        res = dep.exec_app(
            "/app/.venv/bin/python",
            "-m",
            "open_notebook.ocr.cli",
            "custom",
            "rollback",
            check=False,
        )
        print(res.stdout)
        return EXIT_OK if res.returncode == 0 else EXIT_UPDATE
    with update_lock(dep.state):
        journal = Journal(dep.state)
        container = dep.app_container()
        if args.what in ("legal-off", "legal-on"):
            if not container:
                raise Refused("application container not found", EXIT_UPDATE)
            # Keep the network mode the application is in (F-23): a gate change on a
            # running system must not silently put it into maintenance.
            if args.maintenance and args.no_maintenance:
                raise Refused(
                    "--maintenance and --no-maintenance exclude each other", EXIT_USAGE
                )
            if args.maintenance:
                in_maintenance = True
            elif args.no_maintenance:
                in_maintenance = False
            else:
                base_ports = dep.config_json()["services"][dep.app].get("ports", [])
                base_loopback = bool(base_ports) and all(
                    isinstance(p, dict) and p.get("host_ip") in ("127.0.0.1", "::1")
                    for p in base_ports
                )
                in_maintenance = (
                    bool(app_ports_loopback_only(dep, container)) and not base_loopback
                )
            if in_maintenance and not cfg["MAINTENANCE_OVERRIDE"]:
                raise Refused(
                    "maintenance requested but MAINTENANCE_OVERRIDE is not configured",
                    EXIT_USAGE,
                )
            maintenance = [cfg["MAINTENANCE_OVERRIDE"]] if in_maintenance else []
            current = run(
                ["docker", "inspect", "--format", "{{.Config.Image}}", container]
            ).stdout.strip()
            running_id = dep.container_image_id(container)
            env = dict(journal.data.get("override_env") or attempt_env(cfg, journal))
            env["OCR_LEGAL_NORMALIZATION_ENABLED"] = (
                "false" if args.what == "legal-off" else "true"
            )
            db_before = db_snapshot(dep)
            before = dep.config_json()
            override = write_image_override(dep, check_image_ref(current), env)
            after = dep.config_json([str(override)] + maintenance)
            compare_configs(
                dep, before, after, maintenance=bool(maintenance), allowed_env=env
            )
            run(
                dep.up_command([str(override)] + maintenance),
                capture=False,
                timeout=1800,
            )
            assert_db_untouched(dep, db_before, "after the gate change")
            ok = health_checks(dep, cfg, expect_image=running_id)
            if journal.data.get("status"):
                journal.data["override_env"] = env
                journal.step(
                    "LEGAL_GATE",
                    value=env["OCR_LEGAL_NORMALIZATION_ENABLED"],
                    maintenance=bool(maintenance),
                    ok=ok,
                )
            state = "OFF (Standard everywhere)" if args.what == "legal-off" else "ON"
            mode = "maintenance" if maintenance else "normal"
            log(
                f"Legal Document gate {state}; network mode kept: {mode}; database untouched"
            )
            return EXIT_OK if ok else EXIT_UPDATE

        # app / interrupted: back to the baseline image, by VERIFIED IMAGE ID (F-24a).
        baseline = journal.data.get("baseline") or {}
        maintenance = (
            []
            if args.no_maintenance or not cfg["MAINTENANCE_OVERRIDE"]
            else [cfg["MAINTENANCE_OVERRIDE"]]
        )
        if args.to_image:
            check_image_ref(args.to_image, "--to-image")
            found = inspect_image(args.to_image)
            if found is None:
                raise Refused(
                    f"--to-image {args.to_image} does not exist locally", EXIT_UPDATE
                )
            target_id = found[0]
            if (
                baseline.get("image_id")
                and target_id != baseline["image_id"]
                and not args.force_image
            ):
                raise Refused(
                    f"--to-image points to {target_id[:19]}, the journal's baseline is "
                    f"{baseline['image_id'][:19]}: pass --force-image to use it anyway",
                    EXIT_UPDATE,
                )
        else:
            target_id = str(baseline.get("image_id") or "")
            if not target_id:
                raise Refused(
                    "no baseline image recorded: pass --to-image <tag of the previous version>",
                    EXIT_UPDATE,
                )
        if args.package_dir:
            if load_package(args.package_dir, cfg)["database"].get(
                "migration_required"
            ):
                raise Refused(
                    "the update changed the database schema: application rollback needs the "
                    "approved restore procedure",
                    EXIT_UPDATE,
                )
        if inspect_image(target_id) is None:
            raise Refused(
                f"the baseline image {target_id[:19]} no longer exists on this host",
                EXIT_UPDATE,
            )
        # A tag can be moved; the ID cannot. Use the recorded tag only when it still
        # points to the baseline, otherwise bind a fresh tag to the verified ID.
        tag = str(journal.data.get("rollback_tag") or "")
        tagged = inspect_image(tag) if IMAGE_REF_RE.match(tag) else None
        if tagged is None or tagged[0] != target_id:
            tag = f"{cfg['IMAGE_REPO']}:rollback-verified-{_dt.datetime.now().strftime('%Y%m%d%H%M%S')}"
            check_image_ref(tag)
            run(["docker", "tag", target_id, tag])
            journal.data["rollback_tag"] = tag
            log(
                f"the rollback tag did not point to the baseline any more: new tag {tag} bound to {target_id[:19]}"
            )
        # Source first: the previous image must be recreated from the definition it
        # was deployed with, not from the release's compose files (F-24b).
        note = restore_source(dep, journal)
        log(f"source: {note}")
        recorded = baseline.get("config_sha256")
        if recorded and recorded != sha256_bytes(
            json.dumps(dep.config_json(), sort_keys=True).encode()
        ):
            log(
                "WARNING: the effective compose configuration differs from the one "
                "recorded before the update (changed compose files or .env?): the "
                "previous image is started with the CURRENT definition"
            )
        # The baseline's own environment: the offline variables plus the Legal gate
        # decision that was in force before this attempt (empty for v1.2.0).
        env = attempt_env(cfg, journal)
        if args.acknowledge_db_change:
            # The operator investigated a reported database-container change and
            # accepts the container as it is now: compare against the present.
            db_before = db_snapshot(dep)
            journal.data["db_change_acknowledged"] = now_iso()
        else:
            db_before = baseline.get("db") or db_snapshot(dep)
        before = dep.config_json()
        override = write_image_override(dep, tag, env)
        after = dep.config_json([str(override)] + maintenance)
        compare_configs(
            dep, before, after, maintenance=bool(maintenance), allowed_env=env
        )
        journal.data.setdefault("steps", [])
        journal.data["status"] = ROLLBACK_FAILED  # until proven otherwise
        journal.save()
        run(dep.up_command([str(override)] + maintenance), capture=False, timeout=1800)
        journal.step(
            "ROLLBACK_app", to=tag, image_id=target_id, maintenance=bool(maintenance)
        )
        assert_db_untouched(dep, db_before, "after the rollback")
        ok = health_checks(dep, cfg, expect_image=target_id)
        if not ok:
            log(
                "ROLLBACK NOT CONFIRMED: the previous image was started but does not pass its "
                "checks. Status rollback_failed; nothing else was changed."
            )
            return EXIT_UPDATE
        if (journal.data.get("pin") or {}).get("applied"):
            _unpin(dep, journal, to_image=target_id, remove_file=False)
        journal.data["status"] = ROLLED_BACK
        journal.data["maintenance"] = bool(maintenance)
        journal.data["override_env"] = env
        journal.save()
        atomic_write(
            dep.state / "compose-command.txt",
            compose_command_text(dep, journal, [str(override)]),
        )
        log(
            f"application rolled back to {tag} ({target_id[:19]}) and checked; database not restored"
        )
        if maintenance:
            log(
                f"after approval, leave maintenance with: rollback.sh app --to-image {tag} --no-maintenance"
            )
    return EXIT_OK


def cmd_health(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    dep = Deployment(cfg)
    journal = Journal(Path(cfg["STATE_DIR"]))
    ok = health_checks(dep, cfg, expect_image=None, prove_offline=args.prove_offline)
    drift = drift_report(dep, journal, cfg) if journal.data else []
    for line in drift:
        log("FAIL " + line)
    if drift:
        return EXIT_DRIFT
    return EXIT_OK if ok else EXIT_UPDATE


def cmd_status(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    journal = Journal(Path(cfg["STATE_DIR"]))
    if not journal.data:
        print(json.dumps({"status": "no update recorded"}, indent=2))
        return EXIT_OK
    report = dict(journal.data)
    drift: List[str] = []
    if cfg.get("DEPLOY_DIR") and cfg.get("COMPOSE_PROJECT"):
        try:
            dep = Deployment(cfg)
            drift = drift_report(dep, journal, cfg)
            container = dep.app_container()
            report["running_image_id"] = (
                dep.container_image_id(container) if container else None
            )
        except Refused as e:
            drift = [f"could not inspect the deployment: {e}"]
    report["drift"] = drift
    print(json.dumps(report, indent=2, sort_keys=True))
    for line in drift:
        log("DRIFT " + line)
    return EXIT_DRIFT if drift else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="create the package (machine with Internet)")
    b.add_argument("--version", required=True)
    b.add_argument("--image", required=True, help="local image built from --git-ref")
    b.add_argument("--image-repo", default="chatbot5400")
    b.add_argument("--platform", default="linux/amd64")
    b.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    b.add_argument(
        "--git-ref", default="HEAD", help="commit to package: a ref name or a full SHA"
    )
    b.add_argument("--base-ref", default="v1.2.0")
    b.add_argument(
        "--bundle-refs",
        nargs="*",
        help="extra refs to put in the bundle (e.g. the release tag)",
    )
    b.add_argument("--release-tag")
    b.add_argument("--supported-from", nargs="+", default=["1.2.0"])
    b.add_argument("--migration-required", action="store_true")
    b.add_argument("--release-notes")
    b.add_argument(
        "--sign-key",
        help="private ssh key for ssh-keygen -Y sign (never stored in the package)",
    )
    b.add_argument("--out", default="dist/offline")
    b.set_defaults(func=cmd_build)

    cv = sub.add_parser(
        "check-version", help="VERSION of the checkout vs the requested package version"
    )
    cv.add_argument("--version", required=True)
    cv.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    cv.add_argument("--git-ref", default="HEAD")
    cv.set_defaults(func=cmd_check_version)

    i = sub.add_parser("inventory", help="(inside the image) describe it")
    i.add_argument("--app-root", default="/app")
    i.set_defaults(func=cmd_inventory)

    v = sub.add_parser("verify", help="authenticate, then verify and unpack a package")
    v.add_argument("package")
    v.add_argument("--extract-to", required=True)
    v.add_argument(
        "--expected-sha256", help="value received over a SEPARATE trusted channel"
    )
    v.add_argument("--allowed-signers", default=DEFAULT_CONFIG["ALLOWED_SIGNERS"])
    v.add_argument("--identity", default=DEFAULT_CONFIG["SIGNER_IDENTITY"])
    v.add_argument(
        "--platform", default=None, help="expected platform (default: this machine)"
    )
    v.add_argument("--current-version")
    v.add_argument("--current-schema", type=int)
    v.set_defaults(func=cmd_verify)

    def server(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--config")
        sp.add_argument("--package-dir")
        sp.add_argument(
            "--accept-not-ready",
            action="store_true",
            help="accept a package whose readiness is NOT_READY",
        )
        sp.add_argument(
            "--accept-missing-artifacts",
            action="store_true",
            help="continue although the current container fails the offline readiness check",
        )
        sp.add_argument(
            "--accept-missing-rapidocr",
            action="store_true",
            help="continue although RapidOCR weights are not on the data volume",
        )
        sp.add_argument("--allow-version-mismatch", action="store_true")
        sp.add_argument("--ignore-jobs", action="store_true")
        sp.add_argument("--no-maintenance", action="store_true")
        sp.add_argument(
            "--backup-reference",
            help="id of an approved backup taken by the operator FOR THIS ATTEMPT",
        )
        sp.add_argument(
            "--backup-verified",
            action="store_true",
            help="operator attests the restore test of that backup passed",
        )

    pf = sub.add_parser("preflight", help="read-only checks")
    server(pf)
    pf.set_defaults(func=lambda a: (cmd_preflight(a), EXIT_OK)[1])

    u = sub.add_parser("update", help="dry run unless --apply")
    server(u)
    u.add_argument("--apply", action="store_true")
    u.add_argument("--sync-source", action="store_true")
    u.set_defaults(func=cmd_update)

    f = sub.add_parser("finish", help="leave maintenance mode (health-checked)")
    f.add_argument("--config")
    f.add_argument("--approve", help="who approved (recorded in the journal)")
    f.set_defaults(func=cmd_finish)

    pn = sub.add_parser(
        "pin", help="make the new image survive a plain `docker compose up -d`"
    )
    pn.add_argument("--config")
    pn.add_argument("--apply", action="store_true")
    pn.add_argument("--undo", action="store_true")
    pn.set_defaults(func=cmd_pin)

    r = sub.add_parser(
        "rollback", help="app | legal-off | legal-on | agri | interrupted"
    )
    r.add_argument(
        "what", choices=["app", "legal-off", "legal-on", "agri", "interrupted"]
    )
    r.add_argument("--config")
    r.add_argument("--to-image")
    r.add_argument(
        "--force-image",
        action="store_true",
        help="accept a --to-image that is not the journal's baseline",
    )
    r.add_argument("--package-dir")
    r.add_argument(
        "--acknowledge-db-change",
        action="store_true",
        help="app/interrupted: the reported database-container change was investigated; "
        "compare against the container as it is now",
    )
    r.add_argument(
        "--maintenance",
        action="store_true",
        help="legal-on/off: recreate in maintenance mode",
    )
    r.add_argument(
        "--no-maintenance", action="store_true", help="recreate in normal mode"
    )
    r.set_defaults(func=cmd_rollback)

    h = sub.add_parser("health", help="functional + offline readiness + drift checks")
    h.add_argument("--config")
    h.add_argument("--prove-offline", action="store_true")
    h.set_defaults(func=cmd_health)

    s = sub.add_parser("status", help="update journal and drift")
    s.add_argument("--config")
    s.set_defaults(func=cmd_status)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "verify" and args.platform is None:
        args.platform = normalize_platform(_platform.machine())
    try:
        return int(args.func(args) or 0)
    except Refused as e:
        log(f"REFUSED: {e}")
        return e.code


if __name__ == "__main__":
    raise SystemExit(main())
