#!/usr/bin/env python3
"""ChatBot5400 offline update package: build, verify, preflight, update, finish, rollback.

Phase 12F, hardened in Phase 12D3 and Phase 12D5 after the independent audits
(docs/deployment/OFFLINE_UPDATE_PACKAGE.md, docs/review/PHASE12D4_OFFLINE_UPDATE_REAUDIT.md).
Standard library only, Python >= 3.8, so the same file runs on the build
machine, inside the image (``inventory``) and on an air-gapped Ubuntu server.

Principles: fail closed; read-only unless ``--apply``; one update at a time
(lock); never ``docker compose down``, never ``-v``, never ``pull``, never
``build`` on the server; the database container is never recreated and never
restored by this tool; no network access (the only URL used is the local
health URL on loopback, never through a proxy); secrets are never read or
printed (``.env`` files are not opened); nothing from a package is used
before the package is authenticated.

Deployment contract (Phase 12D5)::

  1. DEPLOY_IMAGE_TAG (e.g. chatbot5400:local) is the image reference the
     deployment's OWN compose files (COMPOSE_FILES: the file list the
     operations script uses) give the application service. It is the ONLY
     pointer to the approved image. The tool moves it only after a verified
     `finish` (to the new image) or `rollback` (back to the previous approved
     image); a refused, failed or interrupted attempt never moves it. Every
     start path - operations script (normal / maintenance), boot guard,
     reboot, `docker restart`, a plain `docker compose up -d` - therefore
     starts the approved image without any file of this tool.
  2. The environment the new version needs (REQUIRED_APP_ENV) and the Legal
     gate (OCR_LEGAL_NORMALIZATION_ENABLED) live in the operator's own files
     (local override / .env). The tool never injects environment and never
     edits operator files; preflight refuses when a required variable is
     missing from the effective configuration or from the running container.
  3. STATE_DIR/approved.json is the last approved deployment (adopted from
     the running state at the first attempt, then written after a verified
     finish / rollback). status and health always compare the running
     container with it - or with the image an undecided attempt deployed.
  4. The only compose file of the tool is a per-attempt image override
     (STATE_DIR/attempts/<attempt>/override-update.yml, image + pull_policy,
     no environment), used solely for the maintenance recreate of `update`,
     so that the new image can be accepted before it is approved.

Data preservation: every attempt records an immutable baseline (database
container identity, schema, a fingerprint of the records: count and SHA-256
of the record ids per table). Every later check compares with it: a record of
the baseline that is missing, another database container or volume, or data
that cannot be read is a FAIL - never "nothing to compare". Such a finding is
sticky: finish / rollback refuse until the operator has looked at it and
passes --acknowledge-data-change. Nothing is ever restored automatically.

Commands::

  build      (build machine)  git bundle + docker save + manifest + SHA256SUMS (+ signature)
  inventory  (inside the image, --network none)  versions, runtime artifacts, schema version
  verify     (server)  authenticity FIRST, then archive safety, integrity, platform, compatibility
  preflight  (server)  read-only checks of the running deployment, the contract and the package
  update     (server)  dry-run by default; --apply: load, quiesce, backup, recreate in maintenance
  finish     (server)  approve: move DEPLOY_IMAGE_TAG, recreate in normal mode, health-checked
  rollback   (server)  app | interrupted | agri   (legal-on / legal-off: refused, see contract 2)
  pin        (server)  report DEPLOY_IMAGE_TAG / approved.json / container; --apply repairs the tag
  health     (server)  functional + offline readiness + drift checks of the running app
  status     (server)  journal, approved deployment and drift against the running container
  snapshot   (server)  read-only record of database / images / model files; --compare an earlier one

Exit codes::

  0  OK                          5  update / check failed (or snapshot: something lost / changed)
  2  usage or configuration      6  another update / rollback holds the lock
  3  verification failed         7  DRIFT: the running state differs from the approved / expected one
  4  preflight failed            8  UNDECIDED: no drift, but an attempt is undecided or a
                                    transition was interrupted (status / health)
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
import stat
import subprocess
import sys
import tarfile
import time
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterator, List, Optional, Tuple

FORMAT_VERSION = 3  # 3: image.run_config_sha256 + image.provenance are required (12D5)
SIG_NAMESPACE = "chatbot5400-offline"
MANIFEST = "manifest.json"
SIGNATURE = "manifest.json.sig"
SUMS = "SHA256SUMS"
BUNDLE_REF_PREFIX = "refs/cb5400-offline/build/"
# Files of the Phase 12D3 design that no longer exist: only reported / cleaned up.
PIN_FILE = "docker-compose.offline-pin.yml"
LEGACY_OVERRIDE = "image-override.yml"
APPROVED = "approved.json"
BACKUP_REFERENCES = "backup-references.json"
COMPOSE_COMMAND = "compose-command.txt"

# Archive safety limits (overridable for tests / very large images).
MAX_MEMBERS = 5000
MAX_TOTAL_BYTES = int(os.environ.get("CB5400_OFFLINE_MAX_BYTES", str(64 * 1024**3)))
MAX_RATIO = 200.0  # uncompressed / compressed
MAX_METADATA_BYTES = 5 * 1024 * 1024  # manifest / signature read before extraction
MAX_EXT_HEADER = 64 * 1024  # GNU long name / link, pax headers (R2-19)
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
VOLUME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,254}$")
REFERENCE_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,200}$")
LOOPBACK = ("127.0.0.1", "::1", "localhost")

EXIT_OK, EXIT_USAGE, EXIT_VERIFY, EXIT_PREFLIGHT, EXIT_UPDATE, EXIT_LOCK, EXIT_DRIFT = (
    0,
    2,
    3,
    4,
    5,
    6,
    7,
)
EXIT_UNDECIDED = 8

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
# Journal steps that record a completed recreate of the application (with its image).
RECREATE_DONE = ("QUIESCED", "N_recreated", "Q_normal_mode", "ROLLBACK_app", "NORMAL_restored")

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
    """Run a command (list form, never a shell). A timeout is a refusal, not a traceback."""
    try:
        proc = subprocess.run(  # noqa: S603 - fixed binaries, list arguments
            cmd,
            capture_output=capture,
            text=True,
            timeout=timeout,
            check=False,
            input=input_text,
        )
    except subprocess.TimeoutExpired:
        raise Refused(
            f"command timed out after {timeout} s: {' '.join(cmd[:4])} …", EXIT_UPDATE
        ) from None
    except OSError as e:
        raise Refused(f"cannot run {cmd[0]}: {e.strerror or e}", EXIT_UPDATE) from None
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


def normalize_ref(ref: Any) -> str:
    """`chatbot5400` == `chatbot5400:latest` == `docker.io/library/chatbot5400:latest`."""
    r = str(ref or "").strip()
    for prefix in ("docker.io/library/", "index.docker.io/library/", "docker.io/", "index.docker.io/"):
        if r.startswith(prefix):
            r = r[len(prefix) :]
            break
    if r.startswith("library/"):
        r = r[len("library/") :]
    if not r or "@" in r:
        return r
    return r if ":" in r.rsplit("/", 1)[-1] else r + ":latest"


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
    "DEPLOY_IMAGE_TAG": "",
    "STATE_DIR": "/var/lib/chatbot5400-offline",
    "ALLOWED_SIGNERS": "/etc/chatbot5400/allowed_signers",
    "SIGNER_IDENTITY": "release@chatbot5400",
    "SIGNATURE_POLICY": "",
    "MAINTENANCE_OVERRIDE": "",
    "BACKUP_CMD": "",
    "BACKUP_VERIFY_CMD": "",
    "JOBS_WAIT_SECONDS": "1800",
    "HEALTH_URL": "http://127.0.0.1:5055/health",
    "MIN_FREE_GB_EXTRA": "5",
    "REQUIRED_APP_ENV": "OCR_RAPIDOCR_PERSISTENT=true OCR_OFFLINE=true",
    # Obsolete / deprecated keys: still accepted so that an old file keeps working.
    "APP_ENV_OVERRIDES": "",  # deprecated alias of REQUIRED_APP_ENV
    "BACKUP_MAX_AGE_MINUTES": "",  # obsolete (12D5: every update run takes its own backup)
}


def _check_trusted_file(path: Path, what: str) -> None:
    """A file (or folder) that decides what runs as root must not be writable by others (F-26c)."""
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
    present = set()
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
                present.add(key)
    elif path:
        raise Refused(f"configuration file not found: {candidate}", EXIT_USAGE)
    if "REQUIRED_APP_ENV" not in present and "APP_ENV_OVERRIDES" in present:
        cfg["REQUIRED_APP_ENV"] = cfg["APP_ENV_OVERRIDES"]
        log(
            "note: APP_ENV_OVERRIDES is deprecated - rename it REQUIRED_APP_ENV. The tool no "
            "longer injects these variables: they must be in your own compose files (contract step 2)"
        )
    if "BACKUP_MAX_AGE_MINUTES" in present:
        log(
            "note: BACKUP_MAX_AGE_MINUTES is obsolete and ignored: every update run that has "
            "not recreated the application takes its own backup"
        )
    return cfg


def require(cfg: Dict[str, str], *keys: str) -> None:
    missing = [k for k in keys if not cfg.get(k)]
    if missing:
        raise Refused(
            f"configuration missing: {', '.join(missing)} "
            "(see docs/deployment/OFFLINE_UPDATE_UBUNTU_GUIDE.md)",
            EXIT_USAGE,
        )


def config_int(cfg: Dict[str, str], key: str) -> int:
    try:
        value = int(str(cfg.get(key, "")).strip())
    except ValueError:
        raise Refused(f"{key} must be a whole number of seconds", EXIT_USAGE) from None
    if value < 0:
        raise Refused(f"{key} must not be negative", EXIT_USAGE)
    return value


def signature_policy(cfg: Dict[str, str], allowed_signers: str) -> str:
    """`required` (default when a trusted key file is installed) or `optional` (R2-07)."""
    policy = str(cfg.get("SIGNATURE_POLICY", "")).strip().lower()
    if policy in ("required", "optional"):
        return policy
    if policy:
        raise Refused("SIGNATURE_POLICY must be `required` or `optional`", EXIT_USAGE)
    return "required" if allowed_signers and Path(allowed_signers).is_file() else "optional"


@contextlib.contextmanager
def update_lock(state_dir: Path) -> Iterator[None]:
    """One update at a time (flock); released automatically if the process dies."""
    import fcntl

    ensure_state_dir(state_dir)
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


def private_dir(path: Path) -> Path:
    """A folder only the user who runs the tool (root) can read or write."""
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    with contextlib.suppress(OSError):
        if path.stat().st_mode & 0o077:
            os.chmod(path, 0o700)
    return path


def ensure_state_dir(path: Path) -> None:
    """STATE_DIR is private to the user who runs the tool (root): the journal
    holds hashes of the effective compose configuration and record ids."""
    private_dir(path)


def atomic_write(path: Path, text: str, private: bool = False) -> None:
    """Write + fsync a temporary file, then rename it over ``path`` (F-13)."""
    tmp = path.with_name(path.name + ".tmp")
    if private:
        with contextlib.suppress(OSError):
            tmp.unlink()
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    _fsync_dir(path.parent)


def write_json_private(path: Path, data: Any) -> None:
    atomic_write(path, json.dumps(data, indent=2, sort_keys=True), private=True)


def open_intents(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Intent steps without their completion step: an interrupted transition (R2-13).

    Every ``*_intent`` step names the step(s) that complete it (``done_by``). A
    later successful close of the transaction (finish / rollback checks passed,
    or an attempt closed without a recreate) resolves everything before it.
    """
    out = []
    for i, s in enumerate(steps):
        name = str(s.get("step", ""))
        done_by = s.get("done_by")
        if not name.endswith("_intent") or not isinstance(done_by, list):
            continue
        later = steps[i + 1 :]
        if any(t.get("step") in done_by for t in later):
            continue
        if any(
            t.get("step") == "ROLLBACK_nothing_recreated"
            or (t.get("step") in ("Q_checks", "ROLLBACK_done") and t.get("ok") is True)
            for t in later
        ):
            continue
        out.append(s)
    return out


class Journal:
    """Progress of ONE update attempt, crash-safe (F-13), never reset blindly.

    ``journal.json`` is written atomically; the previous good copy is kept as
    ``journal.json.bak``. A damaged journal is reported with recovery
    instructions - it is never replaced by an empty one. A new attempt never
    deletes the previous journal: its history copy is written first, then
    journal.json is atomically REPLACED (R2-13), so a crash at any point leaves
    either the old or the new journal readable.
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
            "`rollback.sh app --to-image <rollback tag or previous image>` (it must be the "
            "approved image of approved.json, or pass --force-image; the database is not touched)."
        )
        raise Refused(hint, EXIT_UPDATE)

    def save(self) -> None:
        ensure_state_dir(self.dir)
        text = json.dumps(self.data, indent=2, sort_keys=True)
        atomic_write(self.path, text, private=True)
        # Second copy, written after the first is safely on disk: whichever of
        # the two a crash or a bad block damages, the other is a complete state.
        atomic_write(self.backup, text, private=True)

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

    def open_intents(self) -> List[Dict[str, Any]]:
        return open_intents(self.data.get("steps") or [])

    def start_new(self, fresh: Dict[str, Any]) -> Optional[Path]:
        """Keep the finished attempt for audit and make ``fresh`` the journal (F-08, R2-13).

        Order: history copy, then journal.json is REPLACED (os.replace), then its
        .bak copy. journal.json / .bak are never deleted.
        """
        archived = None
        if self.data:
            history = private_dir(self.dir / "journals")
            name = str(
                self.data.get("attempt_id")
                or _dt.datetime.now().strftime("%Y%m%d%H%M%S")
            )
            if not re.match(r"^[A-Za-z0-9._\-]{1,80}$", name):
                name = "unnamed-" + _dt.datetime.now().strftime("%Y%m%d%H%M%S")
            archived = history / f"journal-{name}.json"
            write_json_private(archived, self.data)
        self.data = fresh
        self.save()
        return archived


def new_attempt_id() -> str:
    return _dt.datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(3)


# --------------------------------------------------------------------------- #
# Archive safety (F-14, R2-19) - nothing is written before the archive is authenticated
# --------------------------------------------------------------------------- #

ZERO_BLOCK = b"\0" * 512
EXT_HEADER_TYPES = (b"L", b"K", b"x", b"g")  # GNU long name / link, pax


def _read_exactly(stream: Any, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = stream.read(min(n - len(data), 1024 * 1024))
        if not chunk:
            break
        data += chunk
    return data


def _skip(stream: Any, n: int) -> None:
    """Skip ``n`` bytes of member data in bounded chunks (never read whole)."""
    left = n
    while left > 0:
        chunk = stream.read(min(left, 1024 * 1024))
        if not chunk:
            raise Refused("unreadable package archive: truncated member data")
        left -= len(chunk)


def _tar_number(field: bytes) -> int:
    if field and field[0] & 0x80:  # GNU base-256 (sizes >= 8 GiB)
        if field[0] == 0xFF:
            raise Refused("unreadable package archive: negative size in a tar header")
        value = field[0] & 0x7F
        for b in field[1:]:
            value = (value << 8) | b
        return value
    text = field.split(b"\0", 1)[0].strip(b" \0")
    try:
        return int(text or b"0", 8)
    except ValueError:
        raise Refused("unreadable package archive: invalid number in a tar header") from None


def _tar_checksum_ok(header: bytes) -> bool:
    try:
        stored = _tar_number(header[148:156])
    except Refused:
        return False
    unsigned = sum(header[:148]) + 8 * 32 + sum(header[156:])
    signed = sum(b - 256 if b > 127 else b for b in header[:148] + header[156:]) + 8 * 32
    return stored in (unsigned, signed)


def _pax_size(data: bytes) -> Optional[int]:
    """The `size` record of a pax header (members >= 8 GiB carry their size there)."""
    pos, size = 0, None
    while pos < len(data):
        m = re.match(rb"(\d{1,20}) ", data[pos : pos + 24])
        if not m:
            break
        length = int(m.group(1))
        if length <= len(m.group(0)):
            break
        key, _, value = data[pos + m.end() : pos + length].rstrip(b"\n").partition(b"=")
        if key == b"size":
            try:
                size = int(value)
            except ValueError:
                raise Refused("unreadable package archive: invalid pax size") from None
        pos += length
    return size


def _decompressed(raw: Any) -> Any:
    import bz2
    import gzip
    import lzma

    magic = raw.read(6)
    raw.seek(0)
    if magic[:2] == b"\x1f\x8b":
        return gzip.GzipFile(fileobj=raw, mode="rb")
    if magic[:3] == b"BZh":
        return bz2.BZ2File(raw)
    if magic == b"\xfd7zXZ\x00":
        return lzma.LZMAFile(raw)
    return raw


def prescan_archive(package: Path) -> None:
    """Every tar header, BEFORE tarfile touches the archive (R2-19).

    The decompressed stream is read in 512-byte header blocks; member data is
    skipped in bounded chunks. Extended headers (GNU long name / link, pax)
    larger than 64 KiB are refused - tarfile would read them into memory whole,
    before anything is authenticated. MAX_MEMBERS, MAX_TOTAL_BYTES and the
    compression ratio are enforced on the way, so a bomb stops at its header.
    """
    import lzma
    import zlib

    compressed = max(1, package.stat().st_size)
    members = total = 0
    pending: Optional[int] = None
    try:
        with open(package, "rb") as raw:
            stream = _decompressed(raw)
            while True:
                header = _read_exactly(stream, 512)
                if not header or header == ZERO_BLOCK:
                    break
                if len(header) < 512:
                    raise Refused("unreadable package archive: truncated tar header")
                if not _tar_checksum_ok(header):
                    raise Refused("unreadable package archive: invalid tar header checksum")
                size = _tar_number(header[124:136])
                kind = header[156:157]
                if kind in EXT_HEADER_TYPES:
                    if size > MAX_EXT_HEADER:
                        raise Refused(
                            f"oversized extended tar header ({kind.decode()!r}, {size} bytes > "
                            f"{MAX_EXT_HEADER}): refused before authentication"
                        )
                    data = _read_exactly(stream, -(-size // 512) * 512)
                    if len(data) < size:
                        raise Refused("unreadable package archive: truncated extended header")
                    if kind == b"x":
                        pending = _pax_size(data[:size])
                    continue
                if pending is not None:
                    size, pending = pending, None
                members += 1
                total += size
                if members > MAX_MEMBERS:
                    raise Refused(f"too many archive entries (> {MAX_MEMBERS})")
                if total > MAX_TOTAL_BYTES:
                    raise Refused(f"package expands beyond {MAX_TOTAL_BYTES} bytes")
                if total / compressed > MAX_RATIO:
                    raise Refused(
                        f"abnormal compression ratio ({total / compressed:.0f}x): refused"
                    )
                _skip(stream, -(-size // 512) * 512)
    except (OSError, EOFError, ValueError, zlib.error, lzma.LZMAError) as e:
        raise Refused(f"unreadable package archive: {type(e).__name__}") from None


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
    prescan_archive(package)  # bounded: tarfile only sees small headers
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
    package: Path,
    dest: Path,
    expected: Optional[Dict[str, Dict[str, Any]]] = None,
    members: Optional[List[tarfile.TarInfo]] = None,
) -> Path:
    """Extract into a staging folder, renamed to ``dest`` only when complete.

    With ``expected`` (the ``files`` of an authenticated manifest) every file is
    hashed while it is written and anything not listed is refused. A failure
    leaves no partial tree behind. Folders are 0755 and files 0644 / 0755
    whatever the umask, so that the tree passes the ownership / permission
    check the server commands make (R2-07).
    """
    if dest.exists() and any(dest.iterdir()):
        raise Refused(f"{dest} must be a new or empty directory")
    members = members if members is not None else inspect_archive(package)
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
        for dirpath, _dirs, _files in os.walk(root):
            os.chmod(dirpath, 0o755)
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
# Docker image identity (F-20, F-25, R2-06)
# --------------------------------------------------------------------------- #

# The part of an image config that decides how a container of the image RUNS.
RUN_CONFIG_KEYS = (
    "Entrypoint", "Cmd", "User", "Env", "WorkingDir", "Labels", "ExposedPorts", "Volumes",
    "StopSignal", "Healthcheck", "Shell", "OnBuild",
)  # fmt: skip


def run_config_sha256(config: Any, os_name: Any, architecture: Any) -> str:
    """SHA-256 of a canonical JSON of the run configuration + platform (R2-06).

    The same value comes from the config blob of an image archive
    (``config`` / ``os`` / ``architecture``) and from ``docker image inspect``
    of the loaded image (``Config`` / ``Os`` / ``Architecture``). Empty values
    are dropped (``docker image inspect`` reports some keys as null / "").
    """
    cfg = config if isinstance(config, dict) else {}
    run_cfg: Dict[str, Any] = {
        k: cfg[k] for k in RUN_CONFIG_KEYS if cfg.get(k) not in (None, "", [], {})
    }
    run_cfg["platform"] = normalize_platform(f"{os_name or ''}/{architecture or ''}")
    return sha256_bytes(
        json.dumps(run_cfg, sort_keys=True, separators=(",", ":")).encode()
    )


def _blob_path(digest: Any) -> str:
    if not isinstance(digest, str) or not IMAGE_ID_RE.match(digest):
        raise Refused("image archive: invalid blob digest")
    return "blobs/" + digest.replace(":", "/")


def _is_attestation(desc: Dict[str, Any]) -> bool:
    """buildkit lists a provenance attestation next to the image in its index."""
    ann = desc.get("annotations") or {}
    plat = desc.get("platform") or {}
    return ann.get("vnd.docker.reference.type") == "attestation-manifest" or (
        plat.get("os") == "unknown" and plat.get("architecture") == "unknown"
    )


def _oci_tags(desc: Dict[str, Any]) -> List[str]:
    ann = desc.get("annotations") or {}
    name = ann.get("io.containerd.image.name")
    if name:
        return [normalize_ref(name)]
    ref = ann.get("org.opencontainers.image.ref.name")
    return [str(ref)] if ref else []


def image_archive_identity(archive: Path) -> Dict[str, Any]:
    """What a ``docker save`` archive really contains, read without loading it.

    ``repo_tags``          every tag ``docker load`` would create or MOVE
    ``config_digest``      sha256 of the image config = the image ID of the classic store
    ``diff_ids``           uncompressed layer digests = ``RootFS.Layers`` in any store
    ``run_config_sha256``  the run configuration + platform (R2-06)

    The image ID reported by ``docker image inspect`` differs between the
    classic and the containerd image store (Docker 29 with the containerd
    store reports the digest of the image INDEX, which also lists a buildkit
    attestation manifest). The docker-archive ``manifest.json`` is preferred
    (Docker 29 writes it next to ``index.json``); an OCI-only layout is read
    from ``index.json``, skipping attestation manifests.
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
                manifests = [
                    m for m in (index.get("manifests") or []) if not _is_attestation(m)
                ]
                if len(manifests) != 1:
                    raise Refused("image archive must contain exactly one image")
                desc = manifests[0]
                tags = _oci_tags(desc)
                blob = json.loads(load(_blob_path(desc.get("digest"))))
                if blob.get("manifests"):  # an image index: one platform expected
                    inner = [m for m in blob["manifests"] if not _is_attestation(m)]
                    if len(inner) != 1:
                        raise Refused("image archive holds several platforms")
                    blob = json.loads(load(_blob_path(inner[0].get("digest"))))
                config = load(_blob_path((blob.get("config") or {}).get("digest")))
                layout = "oci"
            else:
                raise Refused(
                    "not a docker image archive (no manifest.json / index.json)"
                )
    except (tarfile.TarError, ValueError, KeyError, TypeError, OSError) as e:
        raise Refused(f"unreadable docker image archive: {type(e).__name__}") from None
    try:
        parsed = json.loads(config)
        diff_ids = list(parsed["rootfs"]["diff_ids"])
    except (ValueError, KeyError, TypeError):
        raise Refused("image archive: image config has no rootfs.diff_ids") from None
    return {
        "layout": layout,
        "repo_tags": sorted(str(t) for t in tags),
        "config_digest": "sha256:" + sha256_bytes(config),
        "diff_ids": [str(d) for d in diff_ids],
        "run_config_sha256": run_config_sha256(
            parsed.get("config"), parsed.get("os"), parsed.get("architecture")
        ),
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
    if (
        image.get("run_config_sha256")
        and ident["run_config_sha256"] != image["run_config_sha256"]
    ):
        raise Refused("image archive run configuration differs from the manifest")
    return ident


def same_image(
    inspect_id: str,
    layers: List[str],
    image: Dict[str, Any],
    run_config: Optional[str] = None,
) -> Optional[str]:
    """How a local image is recognised as the packaged one (None = it is not).

    Same image ID, or same config digest (classic store), or - another image
    store - the same layers AND the same run configuration + platform (R2-06):
    layers alone are not an identity (entrypoint, user, environment differ).
    """
    if inspect_id == image.get("id"):
        return "image id"
    if inspect_id == image.get("config_digest"):
        return "config digest (classic image store)"
    if (
        layers
        and image.get("diff_ids")
        and layers == image["diff_ids"]
        and run_config
        and image.get("run_config_sha256")
        and run_config == image["run_config_sha256"]
    ):
        return "layers + run configuration + platform (other image store)"
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


def local_run_config(ref: str) -> Optional[str]:
    """run_config_sha256 of a local image, from `docker image inspect` (R2-06)."""
    proc = run(["docker", "image", "inspect", ref], check=False)
    if proc.returncode != 0:
        return None
    try:
        info = json.loads(proc.stdout)[0]
    except (ValueError, IndexError, KeyError, TypeError):
        return None
    return run_config_sha256(info.get("Config"), info.get("Os"), info.get("Architecture"))


def identify_image(ref: str, image: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """(local image ID or None, how it was recognised as the packaged image or None)."""
    found = inspect_image(ref)
    if found is None:
        return None, None
    how = same_image(found[0], found[1], image)
    if how is None and found[1] and found[1] == image.get("diff_ids"):
        how = same_image(found[0], found[1], image, local_run_config(ref))
    return found[0], how


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


def validate_manifest(manifest: Any, allow_unverified: bool = False) -> None:
    if not isinstance(manifest, dict):
        raise Refused("manifest is not a JSON object")
    for key, typ in MANIFEST_REQUIRED.items():
        if not isinstance(manifest.get(key), typ):
            raise Refused(f"manifest field missing or invalid: {key}")
    if manifest["package_format_version"] != FORMAT_VERSION:
        raise Refused(
            f"unsupported package format {manifest['package_format_version']} (this tool "
            f"reads format {FORMAT_VERSION}): rebuild the package with the current "
            "build-package script"
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
    for key in ("tag", "id", "archive", "archive_sha256", "config_digest", "run_config_sha256"):
        if not isinstance(img.get(key), str) or not img[key]:
            raise Refused(f"manifest image.{key} missing")
    if not TAGGED_REF_RE.match(img["tag"]):
        raise Refused("manifest image.tag is not a repository:tag reference")
    for key in ("id", "config_digest"):
        if not IMAGE_ID_RE.match(img[key]):
            raise Refused(f"manifest image.{key} is not a sha256 digest")
    for key in ("archive_sha256", "run_config_sha256"):
        if not SHA_RE.match(img[key]):
            raise Refused(f"manifest image.{key} invalid")
    if img.get("provenance") not in ("verified", "unverified"):
        raise Refused("manifest image.provenance missing")
    if img["provenance"] != "verified" and not allow_unverified:
        raise Refused(
            "the image of this package has UNVERIFIED provenance (a test build made with "
            "--allow-unlabelled-image: nothing proves which commit built it): refused on the server"
        )
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
    if img["archive"] not in manifest["files"]:
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


# --------------------------------------------------------------------------- #
# Trusted verification records (R2-07): STATE_DIR/verified/<package sha256>.json
# --------------------------------------------------------------------------- #


def _check_package_tree(root: Path) -> None:
    """The package folder must be something only root (or the tool's user) can change (R2-07).

    The folder and every ancestor up to ``/``: owned by root or the euid, not
    writable by group / others (a sticky ancestor such as /tmp is allowed).
    Every folder and file inside: same owner rule, not writable by group / others.
    """
    allowed = (0, os.geteuid())
    p = root
    while True:
        try:
            st = os.stat(p)
        except OSError as e:
            raise Refused(f"package folder unreadable: {p} ({e.strerror})", EXIT_PREFLIGHT) from None
        sticky_ancestor = p != root and bool(st.st_mode & stat.S_ISVTX)
        if st.st_uid not in allowed:
            raise Refused(
                f"package folder {p} is owned by another user (uid {st.st_uid}): refused "
                "(unpack packages as root into a root-owned folder)",
                EXIT_PREFLIGHT,
            )
        if st.st_mode & 0o022 and not sticky_ancestor:
            raise Refused(
                f"package folder {p} is writable by group / others: refused (anybody could "
                "replace the package after verification)",
                EXIT_PREFLIGHT,
            )
        if p.parent == p:
            break
        p = p.parent
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            item = Path(dirpath) / name
            st = os.lstat(item)
            if stat.S_ISLNK(st.st_mode):
                raise Refused(f"symlink in package: {item.relative_to(root)}", EXIT_PREFLIGHT)
            if st.st_uid not in allowed or st.st_mode & 0o022:
                raise Refused(
                    f"{item} in the package is owned by another user or writable by group / "
                    "others: refused",
                    EXIT_PREFLIGHT,
                )


def verified_dir(state: Path) -> Path:
    return state / "verified"


def find_trusted_report(
    state: Path, root: Path, manifest_sha256: str
) -> Optional[Dict[str, Any]]:
    """The verify record of THIS folder with THIS manifest, from STATE_DIR (never the package)."""
    vdir = verified_dir(state)
    if not vdir.is_dir():
        return None
    _check_trusted_file(vdir, "trusted verify records folder")
    best: Optional[Dict[str, Any]] = None
    for path in sorted(vdir.glob("*.json")):
        if not SHA_RE.match(path.stem):
            continue
        _check_trusted_file(path, "trusted verify record")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        if (
            isinstance(data, dict)
            and data.get("result") == "VERIFIED"
            and data.get("package_sha256") == path.stem
            and data.get("package_dir") == str(root)
            and data.get("manifest_sha256") == manifest_sha256
        ):
            if best is None or str(data.get("verified_at")) > str(best.get("verified_at")):
                best = data
    return best


def cmd_verify(args: argparse.Namespace) -> int:
    """Authenticate first; only then unpack (F-14); record the result in STATE_DIR (R2-07)."""
    cfg = load_config(args.config)
    allowed_signers = args.allowed_signers or cfg["ALLOWED_SIGNERS"]
    identity = args.identity or cfg["SIGNER_IDENTITY"]
    policy = signature_policy(cfg, allowed_signers)
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
    if policy == "required":
        if signature is None:
            raise Refused(
                "SIGNATURE REQUIRED: a trusted release key is installed (or SIGNATURE_POLICY="
                "required) and this package is not signed. A trusted-channel SHA-256 does not "
                "replace the signature under this policy. Nothing was unpacked."
            )
        signed = verify_signature_bytes(manifest_bytes, signature, allowed_signers, identity)
    elif signature is not None and authenticity and not Path(allowed_signers).is_file():
        # Authentic through the trusted-channel hash; the signature cannot add to it.
        log(
            "note: the package is signed but no trusted key is installed: signature NOT checked"
        )
        signed = "unchecked"
    else:
        signed = verify_signature_bytes(
            manifest_bytes, signature, allowed_signers, identity
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
    root = safe_extract(
        package, dest, expected=files if signed == "valid" else None, members=members
    )
    try:
        if (root / MANIFEST).read_bytes() != manifest_bytes:
            raise Refused("manifest changed between authentication and extraction")
        manifest = verify_tree(
            root, args.platform, args.current_version, args.current_schema
        )
        report = {
            "result": "VERIFIED",
            "package_sha256": digest,
            "manifest_sha256": sha256_bytes(manifest_bytes),
            "authenticity": authenticity,
            "signed": signed == "valid",
            "signature_policy": policy,
            "version": manifest["application"]["version"],
            "platform": manifest["platform"],
            "image": manifest["image"]["tag"],
            "readiness": manifest.get("readiness", {}).get("status"),
            "package_dir": str(root),
            "verified_at": now_iso(),
        }
        state = Path(cfg["STATE_DIR"])
        ensure_state_dir(state)
        write_json_private(private_dir(verified_dir(state)) / f"{digest}.json", report)
    except BaseException:
        shutil.rmtree(dest, ignore_errors=True)  # no half-verified tree is left behind
        raise
    human = dict(
        report,
        trusted=False,
        note="INFORMATIONAL COPY for people, NOT trusted by the tool: the server trusts only "
        f"{verified_dir(state) / (digest + '.json')}",
    )
    atomic_write(root.parent / "verify-report.json", json.dumps(human, indent=2))
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


# The token encoding the application chunks with (open_notebook/utils/token_utils.py
# holds the same three values; tests/test_offline_package.py keeps them equal).
TIKTOKEN_ENCODING = "o200k_base"
TIKTOKEN_BLOB_URL = (
    "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken"
)
TIKTOKEN_BLOB_SHA256 = (
    "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
)


def _probe_tiktoken(app_root: Path) -> Dict[str, Any]:
    """Can tokens be counted with NO network? (inventory runs with --network none)."""
    info: Dict[str, Any] = {"encoding": TIKTOKEN_ENCODING, "loads_offline": False}
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
    # tiktoken names its cache file after the SHA-1 of the blob URL.
    expected_name = hashlib.sha1(TIKTOKEN_BLOB_URL.encode()).hexdigest()  # noqa: S324
    info["expected_file"] = expected_name
    info["expected_sha256"] = TIKTOKEN_BLOB_SHA256
    info["checksum_ok"] = any(
        f["name"] == expected_name and f["sha256"] == TIKTOKEN_BLOB_SHA256
        for f in files
    )
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
        # usable offline = it loads with the network disabled AND the cache file
        # in the image is the expected encoding, byte for byte
        "tiktoken_offline": bool(
            artifacts["tiktoken"].get("loads_offline")
            and artifacts["tiktoken"].get("checksum_ok")
        ),
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




REVISION_LABEL = "org.opencontainers.image.revision"
VERSION_LABEL = "org.opencontainers.image.version"


@contextlib.contextmanager
def build_lock(out_root: Path, name: str) -> Iterator[None]:
    """One build of a given package name at a time in --out (R2-18)."""
    import fcntl

    fh = open(out_root / f".{name}.lock", "w")
    try:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Refused(
                f"another build of {name} is running in {out_root} (lock held)", EXIT_LOCK
            ) from None
        yield
    finally:
        fh.close()


def check_image_provenance(
    labels: Dict[str, Any], inv: Dict[str, Any], commit: str, version: str, allow_unlabelled: bool
) -> str:
    """Bind the image to the packaged commit and version (R2-08): 'verified' / 'unverified'."""
    revision = labels.get(REVISION_LABEL)
    if revision and revision != commit:
        raise Refused(
            "image label revision differs from the commit being packaged", EXIT_USAGE
        )
    label_version = labels.get(VERSION_LABEL)
    if label_version and not version_matches(str(label_version), version):
        raise Refused(
            f"image label version {label_version} does not match --version {version}",
            EXIT_USAGE,
        )
    if not inv.get("app_version"):
        raise Refused(
            "the image has no /app/VERSION (inventory app_version missing): nothing proves "
            "which version it is",
            EXIT_USAGE,
        )
    if not version_matches(str(inv["app_version"]), version):
        raise Refused(
            f"image VERSION {inv['app_version']} does not match --version {version}",
            EXIT_USAGE,
        )
    if revision:
        return "verified"
    if not allow_unlabelled:
        raise Refused(
            f"the image has no {REVISION_LABEL} label: nothing proves it was built from "
            f"{commit[:12]}. Build it with build-package.sh / .ps1 (they add the label), or "
            "pass --allow-unlabelled-image for a TEST package (marked unverified, refused by "
            "every server)",
            EXIT_USAGE,
        )
    log("WARNING: image without a revision label: package marked provenance UNVERIFIED (test only)")
    return "unverified"


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
    package = out_root / f"{name}.tar.gz"
    sha_file = out_root / f"{name}.tar.gz.sha256"
    # --- git first: cheap, and nothing is written when it cannot succeed ---------
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
    out_root.mkdir(parents=True, exist_ok=True)
    with build_lock(out_root, name):
        # R2-18: the stage is CLAIMED atomically; a second builder gets a clean refusal.
        try:
            stage.mkdir()
        except FileExistsError:
            raise Refused(
                f"{stage} exists: remove it or choose another --out", EXIT_USAGE
            ) from None
        tmp_package = out_root / f".{name}.tar.gz.partial-{os.getpid()}"
        try:
            manifest = _build_stage(
                args, repo, stage, name, commit, base_commit, version, release_tag, tag
            )
            with tarfile.open(tmp_package, "w:gz", compresslevel=6) as tar:
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
            digest = sha256_file(tmp_package)
            # A previous package of the same name is replaced only now, by rename; its
            # .sha256 is removed first so that a package and a stale hash never pair up.
            with contextlib.suppress(FileNotFoundError):
                sha_file.unlink()
            os.replace(tmp_package, package)
            atomic_write(sha_file, f"{digest}  {package.name}\n")
        except BaseException:
            # Only what THIS run created is removed (F-04, R2-18).
            shutil.rmtree(stage, ignore_errors=True)
            with contextlib.suppress(OSError):
                tmp_package.unlink()
            raise
    log(f"package: {package}")
    log(
        f"SHA-256: {digest}  <- send this value to the server operator over a SEPARATE trusted channel"
    )
    log(
        f"readiness: {manifest['readiness']['status']} {manifest['readiness']['problems']}"
    )
    return EXIT_OK


def _build_stage(
    args: argparse.Namespace,
    repo: Path,
    stage: Path,
    name: str,
    commit: str,
    base_commit: str,
    version: str,
    release_tag: str,
    tag: str,
) -> Dict[str, Any]:
    image_repo = args.image_repo
    for d in ("images", "source", "scripts", "docs"):
        (stage / d).mkdir(parents=True)
    bundle_rel = f"source/chatbot5400-{version}.bundle"
    log(f"git bundle {args.base_ref}..{commit[:12]} (named ref {BUNDLE_REF_PREFIX}{version})")
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
    # --- Docker -------------------------------------------------------------------
    image = docker_inspect_image(args.image)
    img_platform = normalize_platform(f"{image.get('Os')}/{image.get('Architecture')}")
    if img_platform != normalize_platform(args.platform):
        raise Refused(
            f"image platform {img_platform} != --platform {args.platform}", EXIT_USAGE
        )
    labels = (image.get("Config") or {}).get("Labels") or {}
    if labels.get(REVISION_LABEL) and labels[REVISION_LABEL] != commit:
        raise Refused(
            "image label revision differs from the commit being packaged", EXIT_USAGE
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
    provenance = check_image_provenance(
        labels, inv, commit, version, args.allow_unlabelled_image
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
        "healthcheck.sh", "finish.sh", "status.sh", "pin.sh", "snapshot.sh",
        "offline-update.conf.example",
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
            "image, or its cache file is not the expected one (TIKTOKEN_CACHE_DIR, "
            "SHA-256): chunking would hang or degrade offline"
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
            "run_config_sha256": ident["run_config_sha256"],
            "repo_tags": ident["repo_tags"],
            "archive_layout": ident["layout"],
            "archive": archive_rel,
            "archive_sha256": sha256_file(stage / archive_rel),
            "created": image.get("Created"),
            "provenance": provenance,
            "app_version": inv.get("app_version"),
            "labels": {
                k: v for k, v in labels.items() if k.startswith("org.opencontainers")
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
    validate_manifest(manifest, allow_unverified=bool(args.allow_unlabelled_image))
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
    return manifest


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
        self.deploy_tag = str(cfg.get("DEPLOY_IMAGE_TAG", "")).strip()

    def need_deploy_tag(self) -> str:
        if not self.deploy_tag:
            raise Refused(
                "configuration missing: DEPLOY_IMAGE_TAG - the image reference your OWN compose "
                "files give the application (e.g. chatbot5400:local): contract step 1",
                EXIT_USAGE,
            )
        if not IMAGE_REF_RE.match(self.deploy_tag):
            raise Refused(f"invalid DEPLOY_IMAGE_TAG: {self.deploy_tag[:80]!r}", EXIT_USAGE)
        return self.deploy_tag

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
        out = run(self.compose(extra_files) + ["config", "--format", "json"]).stdout
        try:
            data = json.loads(out)
        except ValueError:
            raise Refused("`docker compose config` printed no JSON", EXIT_UPDATE) from None
        if not isinstance(data, dict) or not isinstance(data.get("services"), dict):
            raise Refused("`docker compose config` has no services", EXIT_UPDATE)
        return data

    def app_config(self, extra_files: Optional[List[str]] = None) -> Dict[str, Any]:
        service = self.config_json(extra_files)["services"].get(self.app)
        if not isinstance(service, dict):
            raise Refused(f"the compose files define no service {self.app}", EXIT_PREFLIGHT)
        return service

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

    def attempt_dir(self, attempt_id: str) -> Path:
        if not re.match(r"^[A-Za-z0-9._\-]{1,80}$", str(attempt_id)):
            raise Refused(f"invalid attempt id {str(attempt_id)[:40]!r}", EXIT_UPDATE)
        ensure_state_dir(self.state)
        return private_dir(private_dir(self.state / "attempts") / attempt_id)

    def up_command(self, extra_files: List[str]) -> List[str]:
        """The ONLY way this tool (re)creates anything: the application, alone."""
        return self.compose(extra_files) + SAFE_UP + [self.app]


def render_override(app: str, image: str, extra_env: Optional[Dict[str, str]] = None) -> str:
    """Per-attempt compose override: image + no pulls. Never any environment (contract step 2)."""
    check_image_ref(image)
    if not SERVICE_RE.match(app):
        raise Refused(f"invalid service name {app!r}", EXIT_USAGE)
    if extra_env:
        raise Refused(
            "the offline tool never injects environment: it belongs to your own compose files "
            "(contract step 2)",
            EXIT_USAGE,
        )
    return "\n".join(
        ["services:", f"  {app}:", f'    image: "{image}"', "    pull_policy: never"]
    ) + "\n"


def write_image_override(
    dep: Deployment,
    image: str,
    extra_env: Optional[Dict[str, str]] = None,
    attempt_id: Optional[str] = None,
) -> Path:
    """The image override of ONE attempt (R2-12): STATE_DIR/attempts/<id>/override-update.yml.

    Used only for the maintenance recreate of `update`. No other start path
    refers to it, so a refused or abandoned attempt cannot change what the
    deployment starts.
    """
    text = render_override(dep.app, image, extra_env)  # every value checked first
    if not attempt_id:
        raise Refused("an image override belongs to an update attempt", EXIT_USAGE)
    path = dep.attempt_dir(attempt_id) / "override-update.yml"
    atomic_write(path, text, private=True)
    return path


LEGACY_OVERRIDE_RE = re.compile(
    r'^services:\n  [A-Za-z0-9][A-Za-z0-9_.\-]*:\n    image: "[^"\n]+"\n    pull_policy: never\n'
    r'(?:    environment:\n(?:      [A-Z][A-Z0-9_]*: "[A-Za-z0-9_.:/\-]*"\n)+)?$'
)


def cleanup_legacy_override(dep: Deployment) -> None:
    """The shared STATE_DIR/image-override.yml of Phase 12D3 is gone (R2-12)."""
    path = dep.state / LEGACY_OVERRIDE
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    if LEGACY_OVERRIDE_RE.match(text):
        path.unlink()
        log(f"removed {path}: the shared override of the 12D3 tool is no longer used")
    else:
        log(f"WARNING: {path} is not a file this tool wrote: left in place, never used")


def parse_env_list(text: str) -> Dict[str, str]:
    out = {}
    for item in str(text or "").split():
        k, sep, v = item.partition("=")
        if not sep or not ENV_KEY_RE.match(k) or not ENV_VALUE_RE.match(v):
            raise Refused(f"REQUIRED_APP_ENV entry {item[:60]!r} is not KEY=value", EXIT_USAGE)
        out[k] = v
    return out


def required_env(cfg: Dict[str, str]) -> Dict[str, str]:
    return parse_env_list(cfg.get("REQUIRED_APP_ENV", ""))


def env_missing(want: Dict[str, str], have: Dict[str, str]) -> List[str]:
    return [f"{k}={v}" for k, v in sorted(want.items()) if have.get(k) != v]


def _env_map(env: Any) -> Dict[str, str]:
    if isinstance(env, dict):
        return {str(k): "" if v is None else str(v) for k, v in env.items()}
    out = {}
    for item in env or []:
        k, _, v = str(item).partition("=")
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


# --------------------------------------------------------------------------- #
# Data fingerprint (R2-05): which records exist, not only how many
# --------------------------------------------------------------------------- #

RECORD_TABLES = ("source", "notebook", "note", "source_embedding", "source_insight")

FINGERPRINT_PROBE = (
    "import asyncio, json\n"
    "from open_notebook.database.repository import repo_query\n"
    f"TABLES = {list(RECORD_TABLES)!r}\n"
    "async def m():\n"
    "    out = {}\n"
    "    for t in TABLES:\n"
    "        rows = await repo_query(f'SELECT id, updated FROM {t}')\n"
    "        ids = [str(r.get('id')) for r in rows]\n"
    "        upd = [r.get('updated') for r in rows]\n"
    "        out[t] = {'ids': ids, 'updated': [None if u is None else str(u) for u in upd]\n"
    "                  if any(u is not None for u in upd) else None}\n"
    "    print('FINGERPRINT ' + json.dumps(out))\n"
    "asyncio.run(m())\n"
)


def make_fingerprint(raw: Any) -> Optional[Dict[str, Any]]:
    """Canonical fingerprint of the raw probe output (one place for the hashing).

    Per table: the number of records, the SHA-256 of the sorted record ids and,
    when the table has ``updated``, the SHA-256 of the sorted (id, updated)
    pairs. ``ids`` (the sorted lists) never leave STATE_DIR. None = unreadable.
    """
    if not isinstance(raw, dict):
        return None
    tables: Dict[str, Any] = {}
    ids_by: Dict[str, List[str]] = {}
    for t in RECORD_TABLES:
        entry = raw.get(t)
        if not isinstance(entry, dict) or not isinstance(entry.get("ids"), list):
            return None
        ids = [str(x) for x in entry["ids"]]
        updated = entry.get("updated")
        if updated is not None and (
            not isinstance(updated, list) or len(updated) != len(ids)
        ):
            return None
        ordered = sorted(ids)
        pairs = (
            None
            if updated is None
            else sorted(
                ([i, None if u is None else str(u)] for i, u in zip(ids, updated)),
                key=lambda p: (p[0], p[1] or ""),
            )
        )
        tables[t] = {
            "count": len(ids),
            "ids_sha256": sha256_bytes("\n".join(ordered).encode()),
            "updated_sha256": None
            if pairs is None
            else sha256_bytes(json.dumps(pairs).encode()),
        }
        ids_by[t] = ordered
    summary = {
        "tables": tables,
        "sha256": sha256_bytes(json.dumps(tables, sort_keys=True).encode()),
    }
    return {"summary": summary, "ids": ids_by}


def fingerprint(dep: Deployment) -> Optional[Dict[str, Any]]:
    """The data fingerprint read through the running application (None = unreadable)."""
    proc = dep.exec_app(
        "/app/.venv/bin/python", "-c", FINGERPRINT_PROBE, check=False, timeout=1800
    )
    if proc.returncode != 0:
        return None
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith("FINGERPRINT "):
            try:
                return make_fingerprint(json.loads(line[len("FINGERPRINT ") :]))
            except ValueError:
                return None
    return None


def fp_counts(fp: Optional[Dict[str, Any]]) -> Optional[Dict[str, int]]:
    if fp is None:
        return None
    return {t: v["count"] for t, v in fp["summary"]["tables"].items()}


def data_verdict(
    reference_ids: Optional[Dict[str, List[str]]],
    now: Optional[Dict[str, Any]],
    exact: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """THE verdict of every data check (R2-05).

    ``reference_ids``  table -> record ids that must all still exist (the attempt
                       baseline, or an acknowledged state); {} = nothing recorded
    ``now``            the fingerprint just read (None = unreadable -> FAIL)
    ``exact``          a fingerprint summary the data must equal exactly
                       (one recreate in maintenance, F1 / F2 / F3)
    Additions are allowed (acceptance uploads); a missing record never is.
    """
    if now is None:
        return False, (
            "the data could not be read (fingerprint unreadable): FAIL - unverified data is "
            "never treated as unchanged"
        )
    if reference_ids is None:
        return False, "the reference record list is missing or unreadable: FAIL"
    problems: List[str] = []
    added: Dict[str, int] = {}
    for t, ids in sorted(reference_ids.items()):
        have = set(now["ids"].get(t) or [])
        missing = [i for i in ids if i not in have]
        if missing:
            problems.append(
                f"{t}: {len(missing)} of {len(ids)} records missing (e.g. {missing[:3]})"
            )
        if len(have) > len(ids):
            added[t] = len(have) - len(ids)
    if exact is not None and now["summary"]["tables"] != exact.get("tables"):
        changed = [
            t
            for t in RECORD_TABLES
            if now["summary"]["tables"].get(t) != (exact.get("tables") or {}).get(t)
        ]
        problems.append(
            f"records changed although nothing may write (maintenance / backup): {changed}"
        )
    if problems:
        return False, (
            "DATA CHANGED: " + "; ".join(problems) + ". Stop and verify; nothing is restored."
        )
    extra = f"; added since the reference: {json.dumps(added, sort_keys=True)}" if added else ""
    return True, f"data preserved: every reference record present ({fp_counts(now)}){extra}"


def write_records(dep: Deployment, attempt_id: str, label: str, fp: Dict[str, Any]) -> Path:
    """The full sorted id lists (ids only, never content), private to STATE_DIR."""
    path = dep.attempt_dir(attempt_id) / f"records-{label}.json"
    write_json_private(
        path, {"taken_at": now_iso(), "sha256": fp["summary"]["sha256"], "tables": fp["ids"]}
    )
    return path


def read_records(dep: Deployment, attempt_id: Optional[str], label: str) -> Optional[Dict[str, List[str]]]:
    if not attempt_id:
        return None
    try:
        path = dep.state / "attempts" / str(attempt_id) / f"records-{label}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    tables = data.get("tables") if isinstance(data, dict) else None
    if not isinstance(tables, dict):
        return None
    return {str(t): [str(i) for i in ids] for t, ids in tables.items() if isinstance(ids, list)}


# --------------------------------------------------------------------------- #
# Model files (F-22, R2-10): name, size AND content
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# The REAL database container (F-21, R2-05)
# --------------------------------------------------------------------------- #


def volume_created(name: str) -> Optional[str]:
    """Creation time of a named volume: a volume re-created under the same name differs."""
    if not VOLUME_RE.match(name):
        return None
    proc = run(
        ["docker", "inspect", "--type", "volume", "--format", "{{.CreatedAt}}", name],
        check=False,
    )
    return (proc.stdout.strip() or None) if proc.returncode == 0 else None


def host_inode(source: str) -> Optional[List[int]]:
    """(st_dev, st_ino) of a bind-mounted host folder, when the tool can see it."""
    try:
        st = os.stat(source)
    except OSError:
        return None
    return [st.st_dev, st.st_ino]


def db_identity(dep: Deployment) -> Dict[str, Any]:
    """The REAL database container (docker inspect), not its Compose definition."""
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
    mounts, volumes, binds = [], {}, {}
    for m in info.get("Mounts") or []:
        kind, name, source = str(m.get("Type")), m.get("Name"), m.get("Source")
        mounts.append([kind, str(name or source), str(m.get("Destination"))])
        if kind == "volume" and name:
            volumes[str(name)] = volume_created(str(name))
        elif kind == "bind" and source:
            binds[str(source)] = host_inode(str(source))
    state = info.get("State") or {}
    return {
        "container_id": info.get("Id"),
        "image_id": info.get("Image"),
        "mounts": sorted(mounts),
        "volumes": volumes,
        "binds": binds,
        "started_at": state.get("StartedAt"),
        "running": bool(state.get("Running", state.get("Status") == "running")),
    }


IDENTITY_KEYS = ("container_id", "image_id", "mounts", "volumes", "binds")


def db_identity_changes(
    reference: Dict[str, Any], now: Dict[str, Any], within_recreate: bool
) -> List[str]:
    """What differs. StartedAt counts only within ONE recreate: a restart between two
    commands (reboot) is reported by the caller, not a change of the database."""
    keys = IDENTITY_KEYS + (("started_at",) if within_recreate else ())
    changed = [k for k in keys if k in reference and now.get(k) != reference.get(k)]
    if not now.get("running"):
        changed.append("not running")
    return changed


def published_host_ips(ports: Any) -> List[str]:
    """Host addresses of the published ports of a compose service definition.

    Every `ports` entry publishes (no `published` = a random host port);
    no host_ip = every interface."""
    out = []
    for p in ports or []:
        if isinstance(p, dict):
            out.append(str(p.get("host_ip") or "0.0.0.0"))
        else:
            parts = str(p).split(":")
            out.append(parts[0] if len(parts) >= 3 else "0.0.0.0")
    return out


def app_ports_loopback_only(dep: Deployment, container: str) -> Optional[bool]:
    """True when every published port of the running app is bound to loopback."""
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
    return all(h in LOOPBACK for h in hosts)


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


# --------------------------------------------------------------------------- #
# The package on the server (R2-07)
# --------------------------------------------------------------------------- #


def load_package(
    package_dir: Optional[str], cfg: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """The verified package, re-checked every time (F-26a, R2-07).

    Trust comes from STATE_DIR/verified (written by `verify`), never from a
    file next to the package; the folder must be root's; with a signature
    policy of `required` (or a record that says signed) the signature is
    checked again now.
    """
    if not package_dir:
        raise Refused(
            "--package-dir is required (the folder verify-package.sh extracted)",
            EXIT_USAGE,
        )
    cfg = cfg if cfg is not None else load_config(None)
    root = Path(package_dir).resolve()
    _check_package_tree(root)
    try:
        manifest_bytes = (root / MANIFEST).read_bytes()
    except OSError:
        raise Refused("manifest.json missing", EXIT_PREFLIGHT) from None
    manifest_sha = sha256_bytes(manifest_bytes)
    report = find_trusted_report(Path(cfg["STATE_DIR"]), root, manifest_sha)
    if report is None:
        raise Refused(
            "package not verified on this server: no trusted verify record in "
            f"{verified_dir(Path(cfg['STATE_DIR']))} for {root} with this manifest (not verified, "
            "or changed after verification): run verify-package.sh first. A verify-report.json "
            "next to the package is informational and never trusted.",
            EXIT_PREFLIGHT,
        )
    policy = signature_policy(cfg, cfg["ALLOWED_SIGNERS"])
    if policy == "required" or report.get("signed"):
        sig = root / SIGNATURE
        if not sig.is_file():
            raise Refused(
                "the signature of the package is missing (signature policy "
                f"{policy}): verify it again",
                EXIT_PREFLIGHT,
            )
        verify_signature_bytes(
            manifest_bytes, sig.read_bytes(), cfg["ALLOWED_SIGNERS"], cfg["SIGNER_IDENTITY"]
        )
    manifest = verify_tree(root, None, None, None)
    manifest["_package_sha256"] = report.get("package_sha256")
    manifest["_manifest_sha256"] = manifest_sha
    return manifest


def free_gb(path: str) -> float:
    return shutil.disk_usage(path).free / 1024**3


# --------------------------------------------------------------------------- #
# The approved deployment (contract step 3): STATE_DIR/approved.json
# --------------------------------------------------------------------------- #


def read_approved(state: Path) -> Optional[Dict[str, Any]]:
    path, bak = state / APPROVED, state / (APPROVED + ".bak")
    if not path.exists() and not bak.exists():
        return None
    for candidate in (path, bak):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and IMAGE_ID_RE.match(str(data.get("image_id", ""))):
            return data
    raise Refused(
        f"{path} and its .bak are damaged: nothing was changed. Compare `docker image inspect "
        "<DEPLOY_IMAGE_TAG>` with the journal and restore the record by hand.",
        EXIT_UPDATE,
    )


def _shell_quote(value: str) -> str:
    return (
        value
        if re.match(r"^[A-Za-z0-9_./:=@+\-]+$", value)
        else "'" + value.replace("'", "'\\''") + "'"
    )


def compose_command_text(dep: Deployment, approved: Dict[str, Any]) -> str:
    cmd = dep.up_command([])
    return (
        "# Recreates ONLY the ChatBot5400 application from the deployment's OWN compose files\n"
        "# (the file list of the operations script). Its image is DEPLOY_IMAGE_TAG, which the\n"
        "# offline tool moves only after a verified finish / rollback: no file of the tool is used,\n"
        "# and a plain `docker compose up -d` / the operations script start the same image.\n"
        f"# approved image {approved['image_id']} = {approved.get('deploy_tag')} "
        f"({approved.get('how')} {approved.get('approved_at')}, attempt {approved.get('attempt_id')})\n"
        + " ".join(_shell_quote(c) for c in cmd)
        + "\n"
    )


def source_head(dep: Deployment) -> Optional[str]:
    if not (dep.dir / ".git").exists():
        return None
    head = _git(dep.dir, "rev-parse", "HEAD", check=False)
    return head if COMMIT_RE.match(head) else None


def write_approved(
    dep: Deployment,
    how: str,
    image_id: str,
    journal: Optional["Journal"],
    version: Optional[str] = None,
) -> Dict[str, Any]:
    """Record the approved deployment, durably, THEN regenerate compose-command.txt from it."""
    data = {
        "schema": 1,
        "image_id": image_id,
        "deploy_tag": dep.deploy_tag,
        "approved_at": now_iso(),
        "how": how,
        "attempt_id": (journal.data.get("attempt_id") if journal is not None else None),
        "version": version,
        "source_commit": source_head(dep),
    }
    ensure_state_dir(dep.state)
    text = json.dumps(data, indent=2, sort_keys=True)
    atomic_write(dep.state / APPROVED, text, private=True)
    atomic_write(dep.state / (APPROVED + ".bak"), text, private=True)
    atomic_write(dep.state / COMPOSE_COMMAND, compose_command_text(dep, data))
    log(f"approved deployment recorded: {image_id[:19]} ({how})")
    return data


# --------------------------------------------------------------------------- #
# Backups (R2-04): one per run, bound to the attempt and the data
# --------------------------------------------------------------------------- #


def _backup_registry(state: Path) -> List[Dict[str, Any]]:
    path = state / BACKUP_REFERENCES
    if not path.exists():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        raise Refused(
            f"{path} is unreadable: no backup reference can be checked for re-use", EXIT_UPDATE
        ) from None
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def used_backup_reference(state: Path, reference: str) -> Optional[Dict[str, Any]]:
    for entry in _backup_registry(state):
        if entry.get("reference") == reference:
            return entry
    return None


def register_backup_reference(
    state: Path, reference: str, attempt_id: str, fingerprint_sha256: str
) -> None:
    """Append-only registry: a reference proves ONE backup, of ONE data state."""
    entries = _backup_registry(state)
    entries.append(
        {
            "reference": reference,
            "attempt_id": attempt_id,
            "fingerprint_sha256": fingerprint_sha256,
            "at": now_iso(),
        }
    )
    write_json_private(state / BACKUP_REFERENCES, entries)


# --------------------------------------------------------------------------- #
# Compose configuration and the recreate primitives
# --------------------------------------------------------------------------- #

ALLOWED_APP_DIFF = {"image", "pull_policy", "ports"}


def compare_configs(
    dep: Deployment,
    before: Dict[str, Any],
    after: Dict[str, Any],
    maintenance: bool,
) -> None:
    """Effective Compose config before / after the files of a recreate (F-12, F-21).

    The database service and every other service must be identical; the
    application may differ ONLY in image, pull_policy and - in maintenance -
    ports bound to loopback. Environment differences are refused: environment
    belongs to the operator's files (contract step 2).
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
            what = "the environment" if key == "environment" else f"'{key}'"
            raise Refused(
                f"the effective compose config would change {what} of the application: "
                "refused (the tool changes only the image; environment belongs to your own "
                "files - contract step 2)",
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


def check_contract_config(dep: Deployment, cfg: Dict[str, str], app: Dict[str, Any], when: str) -> List[str]:
    """Contract steps 1 and 2 in an effective application config: problems (empty = OK)."""
    problems = []
    if normalize_ref(app.get("image")) != normalize_ref(dep.deploy_tag):
        problems.append(
            f"{when}: the application image is {app.get('image') or '(none: build only)'}, not "
            f"DEPLOY_IMAGE_TAG {dep.deploy_tag} - set `image: {dep.deploy_tag}` for the service "
            f"{dep.app} in your own compose files (contract step 1)"
        )
    missing = env_missing(required_env(cfg), _env_map(app.get("environment")))
    if missing:
        problems.append(
            f"{when}: the effective configuration lacks {missing} - add them to the "
            f"environment of {dep.app} in your local override / .env (contract step 2)"
        )
    return problems


def recreate(
    dep: Deployment,
    journal: "Journal",
    files: List[str],
    purpose: str,
    done: str,
    ref: str,
    image_id: str,
    maintenance: bool,
    pre: Optional[Dict[str, Any]] = None,
) -> None:
    """Recreate ONLY the application; prove the database container is the same one.

    ``ref`` is the image reference the effective configuration resolves for
    the application; it is checked to point to ``image_id`` right before `up`
    (R2-06). The database container is inspected right before and right after
    `up` (StartedAt included: this IS one recreate). UP_intent before the
    command, ``done`` after it (R2-13).
    """
    found = inspect_image(ref)
    if found is None or found[0] != image_id:
        raise Refused(
            f"{ref} does not point to {image_id[:19]} (it is "
            f"{found[0][:19] if found else 'missing'}): nothing was recreated",
            EXIT_UPDATE,
        )
    reference = db_identity(dep)
    journal.data["reference"] = {
        "purpose": purpose,
        "taken_at": now_iso(),
        "db": reference,
        "counts": fp_counts(pre),
        "fingerprint_sha256": pre["summary"]["sha256"] if pre else None,
        "maintenance": maintenance,
    }
    cmd = dep.up_command(files)
    journal.data["compose_command"] = cmd
    journal.step(
        "UP_intent", purpose=purpose, image_id=image_id, maintenance=maintenance, done_by=[done]
    )
    run(cmd, capture=False, timeout=1800)
    container = dep.app_container()
    journal.data["app_container"] = container
    journal.data["maintenance"] = maintenance
    journal.step(done, image_id=image_id, maintenance=maintenance, container=container)
    changed = db_identity_changes(reference, db_identity(dep), within_recreate=True)
    if changed:
        journal.data["db_changed"] = True
        journal.data.setdefault("db_change_reports", []).append(
            {"at": now_iso(), "during": purpose, "changed": changed}
        )
        journal.save()
        raise Refused(
            f"DATABASE CONTAINER CHANGED during the {purpose} recreate: {changed}. The update "
            "tool never touches it: stop and verify before anything else (nothing is restored).",
            EXIT_UPDATE,
        )


def move_deploy_tag(
    dep: Deployment, journal: Optional["Journal"], to_id: str, why: str, done: str = "TAG_done"
) -> Optional[str]:
    """Point DEPLOY_IMAGE_TAG at ``to_id`` (intent first); returns the previous image ID."""
    tag = dep.need_deploy_tag()
    found = inspect_image(tag)
    before = found[0] if found else None
    if before == to_id:
        return before
    if journal is not None:
        journal.step("TAG_intent", tag=tag, from_id=before, to_id=to_id, why=why, done_by=[done])
    run(["docker", "tag", to_id, tag])
    after = inspect_image(tag)
    if after is None or after[0] != to_id:
        raise Refused(f"{tag} did not move to {to_id[:19]}", EXIT_UPDATE)
    if journal is not None:
        journal.step(done, tag=tag, image_id=to_id, previous=before)
    log(f"{tag}: {str(before)[:19]} -> {to_id[:19]} ({why})")
    return before


def sync_source(
    dep: Deployment,
    root: Path,
    manifest: Dict[str, Any],
    journal: Optional[Journal] = None,
) -> None:
    """Fast-forward the deployment's git checkout from the bundle; never reset, never force.

    Only the one ref recorded in the manifest is fetched (no wildcard), into our
    own namespace; local commits or conflicting local edits stop the step with
    the checkout unchanged. K_intent (the commit to return to) is recorded ONCE,
    before git fetch / merge (R2-15); an existing release tag that names
    another commit is refused before anything moves (R2-09).
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
    tag = manifest["application"]["release_tag"]
    existing = _git(
        repo, "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}", check=False
    )
    if existing and existing != commit:
        raise Refused(
            f"the release tag {tag} already exists on this server and names {existing[:12]}, "
            f"not the release commit {commit[:12]}: nothing was changed (check the tag by hand)",
            EXIT_UPDATE,
        )
    local = f"refs/cb5400-offline/incoming/{version}"
    previous = _git(repo, "rev-parse", "HEAD")
    branch = _git(repo, "symbolic-ref", "-q", "--short", "HEAD", check=False)
    if journal is not None:
        if not journal.data.get("source"):  # recorded once, never overwritten
            journal.data["source"] = {
                "previous_commit": previous,
                "previous_branch": branch,
                "target_commit": commit,
            }
        if not journal.done("K_intent"):
            recorded = journal.data["source"]
            journal.step(
                "K_intent",
                previous_commit=recorded["previous_commit"],
                previous_branch=recorded["previous_branch"],
                target=commit,
                done_by=["K_source"],
            )
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
    if not existing:
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
    """After an app rollback: put the checkout back where it was, only when that is safe (F-24b).

    The commit comes from K_intent (recorded before git moved anything), so it
    is right even when the run was killed between `git merge` and K_source.
    """
    src = journal.data.get("source") or {}
    intent = journal.last("K_intent") or {}
    previous = intent.get("previous_commit") or src.get("previous_commit")
    target = intent.get("target") or src.get("target_commit")
    repo = dep.dir
    if not previous or not (repo / ".git").exists():
        return "no source change recorded"
    if not COMMIT_RE.match(str(previous)):
        return "recorded commit is not a commit id: source left as it is"
    head = _git(repo, "rev-parse", "HEAD", check=False)
    if head == previous:
        return "source already at the previous commit"
    if head != target:
        return f"source is at {head[:12]}, not at the release commit: left as it is (check manually)"
    if _git(repo, "status", "--porcelain", "--untracked-files=no", check=False):
        return (
            "the working tree has local changes: source NOT moved. When ready: "
            f"git -C {repo} checkout --detach {previous}"
        )
    proc = run(["git", "-C", str(repo), "checkout", "--detach", previous], check=False)
    if proc.returncode != 0:
        return f"git refused to check out {str(previous)[:12]}: source left as it is"
    journal.step("ROLLBACK_source", commit=previous)
    return f"source back at {str(previous)[:12]} (detached; branch {src.get('previous_branch') or intent.get('previous_branch') or '-'} not moved)"


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


# --------------------------------------------------------------------------- #
# preflight (read-only)
# --------------------------------------------------------------------------- #


def writes_stop_reason(app_cfg: Dict[str, Any], no_maintenance: bool) -> str:
    """Why loopback ports cannot prove that users are locked out ("" = they can) (R2-20a)."""
    if no_maintenance:
        return "--no-maintenance: nothing closes the application during the backup"
    public = [ip for ip in published_host_ips(app_cfg.get("ports")) if ip not in LOOPBACK]
    if not public:
        return (
            "the application publishes no public port (reverse proxy / shared network?): "
            "loopback-only ports cannot prove that users are locked out"
        )
    return ""


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

    journal = Journal(dep.state) if dep.state.exists() else None
    status = journal.data.get("status") if journal else None
    same_package = bool(
        journal and journal.data.get("manifest_sha256") == manifest["_manifest_sha256"]
    )
    # The application of an unfinished attempt of THIS package is checked by the resume logic.
    unfinished_here = same_package and status in (IN_PROGRESS, FAILED)

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
    app_cfg = (base.get("services") or {}).get(dep.app) or {}
    container = dep.app_container()
    check("application container running", bool(container), container or "not found")
    current_image = dep.container_image_id(container) if container else ""

    # --- the deployment contract (Phase 12D5) -------------------------------------
    tag_id = None
    try:
        dep.need_deploy_tag()
        found = inspect_image(dep.deploy_tag)
        tag_id = found[0] if found else None
        check(
            "DEPLOY_IMAGE_TAG exists (contract step 1)",
            tag_id is not None,
            f"{dep.deploy_tag} -> {tag_id[:19] if tag_id else 'no such image'}",
        )
    except Refused as e:
        check("DEPLOY_IMAGE_TAG configured (contract step 1)", False, str(e))
    if app_cfg and dep.deploy_tag:
        check(
            "the compose files give the application DEPLOY_IMAGE_TAG (contract step 1)",
            normalize_ref(app_cfg.get("image")) == normalize_ref(dep.deploy_tag),
            f"image {app_cfg.get('image') or '(none: build only)'}; set `image: {dep.deploy_tag}` "
            f"for {dep.app} in your own compose files",
        )
        try:
            missing_cfg = env_missing(required_env(cfg), _env_map(app_cfg.get("environment")))
            check(
                "REQUIRED_APP_ENV in the effective configuration (contract step 2)",
                not missing_cfg,
                f"missing {missing_cfg}: add them to the environment of {dep.app} in your "
                "local override / .env" if missing_cfg else cfg["REQUIRED_APP_ENV"],
            )
        except Refused as e:
            check("REQUIRED_APP_ENV valid", False, str(e))
    if container and tag_id:
        drifted = current_image != tag_id
        check(
            "the application runs the image of DEPLOY_IMAGE_TAG (no pre-existing drift)",
            not drifted,
            f"running {current_image[:19]}, {dep.deploy_tag} -> {tag_id[:19]}"
            + (" (unfinished attempt of this package: checked when it is resumed)" if drifted and unfinished_here else ""),
            fatal=not unfinished_here,
        )
    try:
        approved = read_approved(dep.state)
    except Refused as e:
        check("approved deployment record readable", False, str(e))
        approved = None
    if approved:
        check(
            "DEPLOY_IMAGE_TAG is the approved image (approved.json)",
            tag_id == approved["image_id"],
            f"approved {approved['image_id'][:19]} ({approved.get('how')}), tag {str(tag_id)[:19]}",
        )
        if container:
            check(
                "the application runs the approved image",
                current_image == approved["image_id"],
                f"running {current_image[:19]}",
                fatal=not unfinished_here,
            )
    if container:
        try:
            missing_env = env_missing(required_env(cfg), container_env(container))
        except Refused:
            missing_env = ["(REQUIRED_APP_ENV invalid)"]
        check(
            "REQUIRED_APP_ENV in the running application (contract step 2)",
            not missing_env,
            f"missing {missing_env}: add them to your own compose files and recreate the "
            "application with your operations script BEFORE the update (v1.2.0 understands them)"
            if missing_env
            else "present",
        )
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
        fp = fingerprint(dep)
        check(
            "database readable (data fingerprint)",
            fp is not None,
            json.dumps(fp_counts(fp))
            if fp
            else "UNREADABLE: nothing could prove later that no record was lost",
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
        db = db_identity(dep)
        check(
            "database container inspected",
            bool(db.get("container_id")) and db["running"],
            str(db.get("container_id"))[:12],
        )
    except Refused as e:
        check("database container inspected", False, str(e))
    loaded_id, how = identify_image(manifest["image"]["tag"], manifest["image"])
    if loaded_id is not None:
        check(
            "image tag free or already this image",
            how is not None,
            f"{manifest['image']['tag']} exists as {loaded_id[:19]} ({how or 'a DIFFERENT image'})",
        )
    check(
        "not already on the target image",
        current_image != (loaded_id or manifest["image"]["id"]),
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
    reason = writes_stop_reason(app_cfg, args.no_maintenance)
    check(
        "writes can be stopped before the backup",
        not reason or args.writes_stopped_confirmed,
        (
            f"{reason}: stop all writes yourself and pass --writes-stopped-confirmed (the data "
            "fingerprint is still compared before / after the backup)"
            if reason
            else "maintenance override (ports bound to loopback) + identical data fingerprint "
            "before and after the backup"
        ),
    )
    check(
        "backup procedure configured",
        bool(cfg["BACKUP_CMD"]) or bool(args.backup_reference),
        "BACKUP_CMD set" if cfg["BACKUP_CMD"] else (args.backup_reference or "none"),
    )
    if args.backup_reference and not cfg["BACKUP_CMD"]:
        try:
            used = (
                used_backup_reference(dep.state, args.backup_reference)
                if REFERENCE_RE.match(args.backup_reference)
                else {"attempt_id": "(invalid reference)"}
            )
            check(
                "backup reference not used before",
                used is None,
                f"already used by attempt {used.get('attempt_id')} at {used.get('at')}: every "
                "update run needs its own backup"
                if used
                else args.backup_reference,
            )
        except Refused as e:
            check("backup reference not used before", False, str(e))
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


# --------------------------------------------------------------------------- #
# update
# --------------------------------------------------------------------------- #


def describe_intents(intents: List[Dict[str, Any]]) -> str:
    return "; ".join(
        f"{s.get('step')}"
        + (f"({s.get('purpose') or s.get('why')})" if s.get("purpose") or s.get("why") else "")
        + f" at {s.get('at')} without {'/'.join(s.get('done_by') or [])}"
        for s in intents
    )


def take_baseline(dep: Deployment) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """What is REALLY deployed right now, before anything changes (F-08, F-21, R2-05)."""
    container = dep.app_container()
    if not container:
        raise Refused("application container not found", EXIT_PREFLIGHT)
    image_id = dep.container_image_id(container)
    image_ref = run(
        ["docker", "inspect", "--format", "{{.Config.Image}}", container], check=False
    ).stdout.strip()
    config = dep.config_json()
    schema = current_schema(dep)
    fp = fingerprint(dep)
    if schema is None or fp is None:
        raise Refused(
            "DATABASE UNREADABLE: FAIL - the schema / data fingerprint of the running deployment "
            "cannot be read, so nothing could prove later that no record was lost. Nothing was "
            "changed.",
            EXIT_UPDATE,
        )
    baseline: Dict[str, Any] = {
        "taken_at": now_iso(),
        "image_id": image_id,
        "image_ref": image_ref,
        "app_version": dep.exec_app("cat", "/app/VERSION", check=False).stdout.strip(),
        "db": db_identity(dep),
        "config_sha256": sha256_bytes(json.dumps(config, sort_keys=True).encode()),
        "schema": schema,
        "counts": fp_counts(fp),
        "fingerprint": fp["summary"]["tables"],
        "fingerprint_sha256": fp["summary"]["sha256"],
        "maintenance": app_ports_loopback_only(dep, container),
        "container": container,
    }
    if (dep.dir / ".git").exists():
        baseline["source_commit"] = _git(dep.dir, "rev-parse", "HEAD", check=False)
        baseline["source_branch"] = _git(
            dep.dir, "symbolic-ref", "-q", "--short", "HEAD", check=False
        )
    return baseline, fp


def start_attempt(dep: Deployment, journal: Journal, manifest: Dict[str, Any]) -> None:
    """Decide: resume the same transaction, start a new one, or refuse (F-08, F-24c, R2-15)."""
    status = journal.data.get("status")
    same = journal.data.get("manifest_sha256") == manifest["_manifest_sha256"]
    if status in UNDECIDED_STATES:
        raise Refused(
            f"an update is deployed and waiting for a decision (status {status}): "
            "finish it (finish.sh --approve) or roll it back (rollback.sh app) first",
            EXIT_UPDATE,
        )
    pending = journal.open_intents()
    if pending:
        raise Refused(
            f"an interrupted transition is recorded ({describe_intents(pending)}): nothing was "
            "changed. Run status.sh, then close it with `rollback.sh interrupted` (or "
            "`rollback.sh app`) before a new update",
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
        if journal.done("K_intent"):
            # The configuration read now may be the release's, not the baseline's:
            # the database / volume comparison of F-21 would be made against the wrong side.
            raise Refused(
                "this attempt began synchronising the source before it stopped: close it "
                "with `rollback.sh interrupted` (the application goes back to normal mode on "
                "the approved image, the source goes back to the recorded commit), then start "
                "the update again",
                EXIT_UPDATE,
            )
        if journal.data.get("db_changed") or journal.data.get("data_changed"):
            raise Refused(
                "DATABASE / DATA CHANGED was reported during this attempt: stop and verify. "
                "Close the attempt with `rollback.sh interrupted --acknowledge-data-change` "
                "after the investigation (nothing is restored), then start again",
                EXIT_UPDATE,
            )
        if status == IN_PROGRESS and not journal.done("N_recreated"):
            log(
                f"resuming attempt {journal.data.get('attempt_id')} (nothing was recreated with "
                "the new image; its baseline is kept, a new backup is taken)"
            )
            return
        # failed, or interrupted after the recreate, but the baseline image runs
        # again: that transaction is over. A new one starts, with its own backup.
    attempt_id = new_attempt_id()
    # Everything that can still refuse happens BEFORE the previous journal is put away.
    baseline, fp = take_baseline(dep)
    approved = read_approved(dep.state)
    write_records(dep, attempt_id, "baseline", fp)
    fresh = {
        "schema": 3,
        "attempt_id": attempt_id,
        "version": manifest["application"]["version"],
        "package_sha256": manifest["_package_sha256"],
        "manifest_sha256": manifest["_manifest_sha256"],
        "target_image_tag": manifest["image"]["tag"],
        "deploy_tag": dep.deploy_tag,
        "status": IN_PROGRESS,
        "started": now_iso(),
        "steps": [],
        # Taken BEFORE anything changes (and before any source sync); never replaced.
        "baseline": baseline,
    }
    archived = journal.start_new(fresh)
    if archived:
        log(f"previous attempt archived: {archived}")
    if approved is None:
        # The first attempt adopts the verified running state as the approved deployment.
        approved = write_approved(
            dep, "adopted", baseline["image_id"], journal, version=baseline.get("app_version")
        )
    journal.data["approved_before"] = approved["image_id"]
    journal.save()
    log(
        f"attempt {attempt_id} started; baseline image {baseline['image_id'][:19]}, "
        f"records {baseline['counts']}"
    )


def wait_for_jobs(dep: Deployment, cfg: Dict[str, str], args: argparse.Namespace) -> None:
    """In maintenance nobody starts new work: wait for the running background jobs."""
    if args.ignore_jobs:
        log(
            "--ignore-jobs: background jobs are not awaited; the fingerprints before / after "
            "the backup must still be identical"
        )
        return
    limit = config_int(cfg, "JOBS_WAIT_SECONDS")
    waited = 0
    while True:
        n = running_jobs(dep)
        if n == 0:
            return
        if waited >= limit:
            raise Refused(
                f"background jobs still running / queued after {waited} s ({n}): the "
                "application STAYS in maintenance (nobody can start new work). Run update again "
                "when they are done (JOBS_WAIT_SECONDS), or close the attempt with "
                "rollback.sh interrupted",
                EXIT_UPDATE,
            )
        time.sleep(10)
        waited += 10


def quiesce(
    dep: Deployment,
    cfg: Dict[str, str],
    journal: Journal,
    args: argparse.Namespace,
    approved_id: str,
    maintenance: List[str],
) -> None:
    """Stop the writes before the backup (R2-04): the APPROVED image in maintenance mode."""
    app_cfg = dep.app_config()
    reason = writes_stop_reason(app_cfg, args.no_maintenance)
    if reason and not args.writes_stopped_confirmed:
        raise Refused(f"{reason}: pass --writes-stopped-confirmed", EXIT_UPDATE)
    if maintenance:
        container = dep.app_container()
        if container and container == journal.data.get("quiesced_container"):
            log("the application is still in maintenance from this attempt (same container)")
        else:
            after = dep.config_json(maintenance)
            compare_configs(dep, dep.config_json(), after, maintenance=True)
            problems = check_contract_config(
                dep, cfg, after["services"][dep.app], "COMPOSE_FILES + MAINTENANCE_OVERRIDE"
            )
            if problems:
                raise Refused("; ".join(problems), EXIT_UPDATE)
            journal.step(
                "MAINT_intent", image_id=approved_id, files=maintenance, done_by=["QUIESCED"]
            )
            recreate(
                dep, journal, maintenance, "quiesce", "QUIESCED", dep.deploy_tag,
                approved_id, maintenance=True,
            )  # fmt: skip
            journal.data["quiesced_container"] = journal.data.get("app_container")
            journal.save()
            log("Q: the APPROVED image runs in maintenance mode (loopback ports) for the backup")
    journal.data["quiesce"] = {
        "proven_by": (
            "operator attestation (--writes-stopped-confirmed): " + reason
            if reason
            else "maintenance override: published ports bound to loopback"
        )
        + "; data fingerprint compared before / after the backup and before the recreate",
        "at": now_iso(),
    }
    journal.save()
    wait_for_jobs(dep, cfg, args)
    journal.step("JOBS_idle", ignored=bool(args.ignore_jobs))


def take_backup(
    dep: Deployment,
    cfg: Dict[str, str],
    journal: Journal,
    args: argparse.Namespace,
    f1: Dict[str, Any],
) -> None:
    """I + J, in THIS run, bound to the attempt and to F1 (R2-04). Never reused."""
    attempt_id = journal.data["attempt_id"]
    sha = f1["summary"]["sha256"]
    if cfg["BACKUP_CMD"]:
        log("I: running BACKUP_CMD (writes are stopped)")
        run(["/bin/sh", "-c", cfg["BACKUP_CMD"]], capture=False, timeout=6 * 3600)
        journal.step("I_backup", method="BACKUP_CMD", fingerprint_sha256=sha)
    elif args.backup_reference:
        reference = args.backup_reference
        if not REFERENCE_RE.match(reference):
            raise Refused("invalid --backup-reference", EXIT_USAGE)
        used = used_backup_reference(dep.state, reference)
        if used:
            raise Refused(
                f"the backup reference {reference!r} was already used by attempt "
                f"{used.get('attempt_id')} at {used.get('at')}: every update run needs its own "
                "backup of the data as it is now",
                EXIT_UPDATE,
            )
        register_backup_reference(dep.state, reference, attempt_id, sha)
        journal.step(
            "I_backup", method="operator", reference=reference, fingerprint_sha256=sha
        )
    else:
        raise Refused(
            "no backup: set BACKUP_CMD, or take the approved backup NOW (the application is in "
            "maintenance) and run update again with --backup-reference <id> --backup-verified",
            EXIT_UPDATE,
        )
    if cfg["BACKUP_VERIFY_CMD"]:
        run(
            ["/bin/sh", "-c", cfg["BACKUP_VERIFY_CMD"]],
            capture=False,
            timeout=6 * 3600,
        )
        journal.step("J_backup_verified", method="BACKUP_VERIFY_CMD", fingerprint_sha256=sha)
    elif args.backup_verified:
        journal.step("J_backup_verified", method="operator attestation", fingerprint_sha256=sha)
    else:
        raise Refused(
            "backup restore not verified: set BACKUP_VERIFY_CMD or pass --backup-verified",
            EXIT_UPDATE,
        )


def cmd_update(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    dep = Deployment(cfg)
    dep.need_deploy_tag()
    manifest = load_package(args.package_dir, cfg)
    root = Path(args.package_dir).resolve()
    target = manifest["image"]["tag"]
    maintenance = [] if args.no_maintenance else [cfg["MAINTENANCE_OVERRIDE"]]
    plan = [
        "   authenticate the package again (trusted record in STATE_DIR/verified, signature)",
        "   contract: DEPLOY_IMAGE_TAG, effective configuration, REQUIRED_APP_ENV, approved.json",
        "   start a NEW attempt (own id, immutable baseline with a data fingerprint) or resume it",
        "G  check the image archive (only the approved tag), docker load, identify the image",
        "H  tag the CURRENT application image as rollback image (verified by image ID)",
        "Q  quiesce: the APPROVED image with COMPOSE_FILES + MAINTENANCE_OVERRIDE; wait for jobs",
        "F1 data fingerprint; I backup (BACKUP_CMD / single-use reference); J restore check; F2 == F1",
        "K  synchronise the source from the git bundle (only with --sync-source; fast-forward only)",
        "L  per-attempt image override (image + pull_policy never, no environment); compare configs",
        "-- move RapidOCR weights onto the data volume in the OLD container and CHECK the result",
        "M+N F3 == F1, then recreate ONLY the application with the new image, in maintenance",
        "O  health, offline readiness, schema, token encoding, model files, data vs the baseline",
        "P  approval: finish.sh --approve <name> moves DEPLOY_IMAGE_TAG, recreates in normal mode",
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
        cleanup_legacy_override(dep)
        args.quiet = True
        cmd_preflight(args, cfg)
        start_attempt(dep, journal, manifest)
        attempt_id = journal.data["attempt_id"]
        baseline = journal.data["baseline"]
        before_config = dep.config_json()  # before any source sync (F-21)

        if not journal.done("G_load"):
            log("G: docker load")
            check_image_archive(root / manifest["image"]["archive"], manifest["image"])
            run(
                ["docker", "load", "-i", str(root / manifest["image"]["archive"])],
                timeout=7200,
            )
            loaded_id, how = identify_image(target, manifest["image"])
            if loaded_id is None or how is None:
                raise Refused(
                    f"the loaded image {loaded_id or '?'} is not the packaged one (id, config "
                    "digest and layers + run configuration all differ)",
                    EXIT_UPDATE,
                )
            journal.data["expected_image_id"] = loaded_id
            journal.step("G_load", image_id=loaded_id, identified_by=how)
        else:
            loaded_id, how = identify_image(target, manifest["image"])
            if loaded_id != journal.data.get("expected_image_id") or how is None:
                raise Refused(
                    f"the tag {target} no longer points to the loaded image",
                    EXIT_UPDATE,
                )
        expected_id = journal.data["expected_image_id"]

        tag = str(journal.data.get("rollback_tag") or "")
        tagged = inspect_image(tag) if tag else None
        if tagged is None or tagged[0] != baseline["image_id"]:
            tag = f"{cfg['IMAGE_REPO']}:rollback-{attempt_id.lower()}"
            check_image_ref(tag)
            run(["docker", "tag", baseline["image_id"], tag])
            journal.data["rollback_tag"] = tag
            journal.step("H_rollback_tag", tag=tag, image_id=baseline["image_id"])
            log(f"H: rollback image {tag} -> {baseline['image_id'][:19]}")

        approved = read_approved(dep.state)
        approved_id = approved["image_id"] if approved else baseline["image_id"]
        quiesce(dep, cfg, journal, args, approved_id, maintenance)

        f1 = fingerprint(dep)
        good, detail = data_verdict(read_records(dep, attempt_id, "baseline"), f1)
        if not good:
            if f1 is not None:
                journal.data["data_changed"] = True
                journal.save()
            raise Refused(
                f"F1 (writes stopped) vs the attempt baseline: {detail} Records present at the "
                "start of the attempt are gone. Close the attempt with `rollback.sh interrupted` "
                "(--acknowledge-data-change after the investigation) and start again.",
                EXIT_UPDATE,
            )
        journal.step("F1_fingerprint", sha256=f1["summary"]["sha256"], counts=fp_counts(f1))
        take_backup(dep, cfg, journal, args, f1)
        f2 = fingerprint(dep)
        good, detail = data_verdict({}, f2, exact=f1["summary"])
        if not good:
            raise Refused(
                f"F2 after the backup differs from F1: {detail} Something wrote while the backup "
                "was taken / verified, so the backup does not hold the data that would be "
                "updated. Nothing was recreated; stop the writes and run update again.",
                EXIT_UPDATE,
            )
        journal.data["backup"] = {
            "attempt_id": attempt_id,
            "fingerprint_sha256": f1["summary"]["sha256"],
            "step": journal.last("I_backup"),
            "verified": journal.last("J_backup_verified"),
        }
        journal.step("F2_fingerprint", sha256=f2["summary"]["sha256"])

        if args.sync_source and not journal.done("K_source"):
            sync_source(dep, root, manifest, journal)
            journal.step("K_source", commit=manifest["source"]["commit"])
        override = write_image_override(dep, target, attempt_id=attempt_id)
        files = [str(override)] + maintenance
        after = dep.config_json(files)
        app_after = after["services"][dep.app]
        if normalize_ref(app_after.get("image")) != normalize_ref(target):
            raise Refused(
                "the effective configuration does not use the new image", EXIT_UPDATE
            )
        if app_after.get("pull_policy") != "never":
            raise Refused("application pull_policy must be 'never'", EXIT_UPDATE)
        compare_configs(dep, before_config, after, maintenance=bool(maintenance))
        missing = env_missing(required_env(cfg), _env_map(app_after.get("environment")))
        if missing:
            raise Refused(
                f"the configuration of the new version lacks {missing}: add them to your own "
                "compose files (contract step 2)",
                EXIT_UPDATE,
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
        write_json_private(dep.attempt_dir(attempt_id) / "artifacts.json", artifacts)
        journal.step(
            "ARTIFACTS_snapshot",
            files={k: len(v) for k, v in artifacts.items()},
            sha256=sha256_bytes(json.dumps(artifacts, sort_keys=True).encode()),
        )
        f3 = fingerprint(dep)
        good, detail = data_verdict({}, f3, exact=f1["summary"])
        if not good:
            raise Refused(
                f"F3 right before the recreate differs from F1: {detail} Something wrote "
                "after the backup. Nothing was recreated; run update again.",
                EXIT_UPDATE,
            )
        now_db = db_identity(dep)
        changed = db_identity_changes(baseline["db"], now_db, within_recreate=False)
        if changed:
            journal.data["db_changed"] = True
            journal.save()
            raise Refused(
                f"DATABASE CONTAINER CHANGED since the start of the attempt: {changed}. Stop "
                "and verify; nothing was recreated, nothing is restored.",
                EXIT_UPDATE,
            )
        if now_db.get("started_at") != baseline["db"].get("started_at"):
            log("note: the database container was restarted since the attempt started (reboot?)")
        journal.step("F3_fingerprint", sha256=f3["summary"]["sha256"])

        log("M+N: recreating ONLY the application container with the new image")
        recreate(
            dep, journal, files, "update", "N_recreated", target, expected_id,
            maintenance=bool(maintenance), pre=f3,
        )  # fmt: skip
        journal.data["status"] = PENDING_CHECKS
        journal.save()
        ok = health_checks(
            dep, cfg, expect_image=expected_id, journal=journal, manifest=manifest
        )
        ok_data, _ = check_data(
            dep, journal, "after the update recreate",
            exact=f3["summary"] if maintenance else None,
        )  # fmt: skip
        ok = ok and ok_data
        journal.step("O_P_checks", ok=ok)
        journal.data["status"] = AWAITING if ok else FAILED
        journal.save()
        if not ok:
            log(
                "CHECKS FAILED: the application stays in maintenance mode. Roll back with: rollback.sh app"
            )
            return EXIT_UPDATE
        proven = str((journal.data.get("quiesce") or {}).get("proven_by", ""))
        log(
            "update deployed in maintenance mode"
            if maintenance and not proven.startswith("operator attestation")
            else "update deployed; writes are stopped by the operator's attestation "
            "(--writes-stopped-confirmed): ports cannot prove a maintenance mode here"
        )
        log(
            f"{dep.deploy_tag} still names the approved image: a restart now returns to it. "
            "After acceptance: finish.sh --approve <name>"
        )
        return EXIT_OK


# --------------------------------------------------------------------------- #
# Checks of the running application
# --------------------------------------------------------------------------- #


def health_checks(
    dep: Deployment,
    cfg: Dict[str, str],
    expect_image: Optional[str],
    prove_offline: bool = False,
    journal: Optional[Journal] = None,
    manifest: Optional[Dict[str, Any]] = None,
) -> bool:
    """Functional checks of the running application (data: check_data)."""
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
    want_schema = (
        manifest["database"]["schema_version"]
        if manifest is not None
        else ((journal.data.get("baseline") or {}).get("schema") if journal else None)
    )
    if want_schema is not None:
        got = current_schema(dep)
        good = got == want_schema
        log(
            f"{'OK  ' if good else 'FAIL'} database schema after start: {got} (expected {want_schema})"
        )
        ok &= good
    snapshot = (
        dep.state / "attempts" / str(journal.data.get("attempt_id")) / "artifacts.json"
        if journal is not None and journal.data.get("attempt_id")
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


def check_data(
    dep: Deployment,
    journal: Journal,
    when: str,
    exact: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Database identity and records vs the IMMUTABLE attempt baseline (R2-05).

    (Or vs the state the operator acknowledged with --acknowledge-data-change.)
    A finding sets the sticky db_changed / data_changed flags; unreadable data
    fails the check without being called a change.
    """
    attempt_id = journal.data.get("attempt_id")
    ack = journal.data.get("acknowledged")
    if ack:
        label, ref_db = f"the state acknowledged at {ack.get('at')}", ack.get("db")
        ref_ids = read_records(dep, attempt_id, "acknowledged")
    elif journal.data.get("baseline"):
        label = "the attempt baseline"
        ref_db = journal.data["baseline"].get("db")
        ref_ids = read_records(dep, attempt_id, "baseline")
    else:  # no attempt recorded (journal moved aside): readability + exactness only
        label, ref_db, ref_ids = "nothing recorded", None, {}
    ok = True
    now_db = db_identity(dep)
    if ref_db:
        changed = db_identity_changes(ref_db, now_db, within_recreate=False)
        if changed:
            ok = False
            journal.data["db_changed"] = True
            journal.data.setdefault("db_change_reports", []).append(
                {"at": now_iso(), "during": when, "changed": changed}
            )
            log(
                f"FAIL DATABASE CHANGED {when} (vs {label}): {changed}. Stop and verify; "
                "nothing is restored."
            )
        elif ref_db.get("started_at") != now_db.get("started_at"):
            log(f"note: the database container was restarted since {label} (reboot?): reported")
    fp = fingerprint(dep)
    good, detail = data_verdict(ref_ids, fp, exact)
    log(f"{'OK  ' if good else 'FAIL'} data {when} vs {label}: {detail}")
    if not good:
        ok = False
        if fp is not None and attempt_id:
            journal.data["data_changed"] = True
            journal.data.setdefault("data_change_reports", []).append(
                {"at": now_iso(), "during": when, "detail": detail[:500]}
            )
            label_file = re.sub(r"[^a-z0-9]+", "-", when.lower()).strip("-")[:40]
            write_records(dep, attempt_id, f"seen-{label_file}", fp)
    journal.save()
    return ok, fp


def acknowledge(dep: Deployment, journal: Journal, who: str) -> None:
    """--acknowledge-data-change: the operator investigated; NOTHING is restored.

    From now on this attempt is compared with the database as it is NOW (the
    baseline itself stays in the journal, unchanged).
    """
    flags = {k: bool(journal.data.get(k)) for k in ("db_changed", "data_changed")}
    fp = fingerprint(dep)
    if fp is None:
        raise Refused(
            "the data cannot be read: there is nothing to acknowledge (fingerprint unreadable)",
            EXIT_UPDATE,
        )
    if not journal.data.get("attempt_id"):
        raise Refused("no attempt is recorded: nothing to acknowledge", EXIT_UPDATE)
    write_records(dep, journal.data["attempt_id"], "acknowledged", fp)
    journal.data["acknowledged"] = {
        "by": who,
        "at": now_iso(),
        "flags": flags,
        "db": db_identity(dep),
        "counts": fp_counts(fp),
        "fingerprint_sha256": fp["summary"]["sha256"],
    }
    journal.data["db_changed"] = False
    journal.data["data_changed"] = False
    journal.step("ACKNOWLEDGED_data_change", by=who, flags=flags)
    log(
        f"DATA / DATABASE CHANGE ACKNOWLEDGED by {who}: this attempt is compared with the "
        "database as it is now. Nothing was restored."
    )


def sticky_flags(journal: Journal) -> List[str]:
    return [k for k in ("db_changed", "data_changed") if journal.data.get(k)]


def operator_name() -> str:
    return os.environ.get("SUDO_USER") or os.environ.get("USER") or f"uid {os.geteuid()}"


def expected_image(journal: Journal) -> str:
    """The image ID this attempt deployed; a journal of the Phase 12 tool has none."""
    value = journal.data.get("expected_image_id")
    if not isinstance(value, str) or not IMAGE_ID_RE.match(value):
        raise Refused(
            "this journal was written by an older version of the tool (no image ID "
            "recorded): roll back with `rollback.sh app --to-image <previous tag> "
            "--force-image` or run the update again with this version",
            EXIT_UPDATE,
        )
    return value


def expected_images(
    journal: Journal, approved: Optional[Dict[str, Any]]
) -> Tuple[Optional[str], List[str], str]:
    """(image expected NOW, images an interrupted transition may have left, why)."""
    status = journal.data.get("status")
    primary = approved["image_id"] if approved else None
    why = "approved.json" if approved else ""
    if journal.data and status not in CLOSED_STATES:
        steps = journal.data.get("steps") or []
        last = next(
            (s for s in reversed(steps) if s.get("step") in RECREATE_DONE and s.get("image_id")),
            None,
        )
        if last is not None:
            primary, why = last["image_id"], f"the last recreate of attempt {journal.data.get('attempt_id')} ({last['step']})"
        elif primary is None and (journal.data.get("baseline") or {}).get("image_id"):
            primary, why = journal.data["baseline"]["image_id"], "the attempt baseline"
    alternatives = []
    for s in journal.open_intents():
        for key in ("image_id", "to_id"):
            if IMAGE_ID_RE.match(str(s.get(key) or "")) and s[key] not in alternatives:
                alternatives.append(s[key])
    return primary, alternatives, why


def assess(
    dep: Deployment, cfg: Dict[str, str], journal: Journal, approved: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Compare the running container with what is expected NOW, in EVERY journal state (R2-13)."""
    drift: List[str] = []
    undecided: List[str] = []
    notes: List[str] = []
    status = journal.data.get("status")
    pending = journal.open_intents()
    container = dep.app_container()
    running = dep.container_image_id(container) if container else None
    primary, alternatives, why = expected_images(journal, approved)
    if not container:
        drift.append("the application container is not running")
    elif primary is None and not alternatives:
        notes.append(
            "no approved deployment recorded (approved.json): the running image is not compared"
        )
    elif running != primary:
        if running in alternatives:
            undecided.append(
                f"INTERRUPTED TRANSITION: the application runs {running[:19]}, which an "
                "interrupted transition was moving to"
            )
        else:
            drift.append(
                f"IMAGE DRIFT: the container runs {running[:19]} but {str(primary)[:19]} is "
                f"expected ({why})"
            )
    tag_id = None
    if dep.deploy_tag:
        found = inspect_image(dep.deploy_tag)
        tag_id = found[0] if found else None
        if approved and tag_id != approved["image_id"]:
            if tag_id and any(s.get("to_id") == tag_id for s in pending):
                undecided.append(
                    f"INTERRUPTED TRANSITION: {dep.deploy_tag} was moved to {tag_id[:19]} by an "
                    "interrupted finish / rollback"
                )
            else:
                drift.append(
                    f"DEPLOY TAG DRIFT: {dep.deploy_tag} points to {str(tag_id)[:19]} but the "
                    f"approved image is {approved['image_id'][:19]}: every restart now starts "
                    "another image. Repair with pin.sh --apply"
                )
    else:
        notes.append("DEPLOY_IMAGE_TAG is not configured (contract step 1)")
    if container:
        missing = env_missing(required_env(cfg), container_env(container))
        if missing:
            drift.append(
                f"ENVIRONMENT DRIFT: the running application lacks {missing} (REQUIRED_APP_ENV): "
                "add them to your own compose files (contract step 2) and recreate it"
            )
    for flag in sticky_flags(journal):
        drift.append(
            f"{'DATABASE' if flag == 'db_changed' else 'DATA'} CHANGED during attempt "
            f"{journal.data.get('attempt_id')} (not acknowledged): stop and verify; finish / "
            "rollback refuse until --acknowledge-data-change"
        )
    if journal.data and status not in CLOSED_STATES:
        undecided.append(
            f"attempt {journal.data.get('attempt_id')} is undecided (status {status})"
        )
        if (
            journal.data.get("maintenance")
            and container
            and container == journal.data.get("app_container")
        ):
            undecided.append(
                "the application is in maintenance mode, left there by this attempt"
            )
    for s in pending:
        undecided.append(f"INTERRUPTED TRANSITION: {describe_intents([s])}")
    if (dep.state / LEGACY_OVERRIDE).exists():
        notes.append(f"leftover of the 12D3 tool, no longer used: {dep.state / LEGACY_OVERRIDE}")
    if (dep.dir / PIN_FILE).exists():
        notes.append(
            f"leftover of the 12D3 tool: {dep.dir / PIN_FILE} - remove it from COMPOSE_FILE / "
            "your scripts; DEPLOY_IMAGE_TAG replaces it"
        )
    return {
        "drift": drift,
        "undecided": undecided,
        "notes": notes,
        "running_image_id": running,
        "expected_image_id": primary,
        "deploy_tag_image_id": tag_id,
    }


def assess_exit(report: Dict[str, Any]) -> int:
    if report["drift"]:
        return EXIT_DRIFT
    if report["undecided"]:
        return EXIT_UNDECIDED
    return EXIT_OK


# --------------------------------------------------------------------------- #
# finish / pin / rollback
# --------------------------------------------------------------------------- #


def cmd_finish(args: argparse.Namespace) -> int:
    if not args.approve:
        raise Refused(
            "finish needs --approve (acceptance done, approval recorded)", EXIT_USAGE
        )
    cfg = load_config(args.config)
    dep = Deployment(cfg)
    dep.need_deploy_tag()
    with update_lock(dep.state):
        journal = Journal(dep.state)
        if journal.data.get("status") not in (AWAITING, FINISH_FAILED):
            raise Refused(
                f"nothing to finish (status {journal.data.get('status')})", EXIT_UPDATE
            )
        expected = expected_image(journal)
        foreign = [
            s
            for s in journal.open_intents()
            if not (
                s.get("step") in ("Q_intent", "TAG_intent")
                or (s.get("step") == "UP_intent" and s.get("purpose") == "finish")
            )
        ]
        if foreign:
            raise Refused(
                f"an interrupted transition is recorded ({describe_intents(foreign)}): run "
                "rollback.sh app",
                EXIT_UPDATE,
            )
        approved = read_approved(dep.state)
        if approved is None:
            raise Refused("no approved deployment is recorded (approved.json)", EXIT_UPDATE)
        flags = sticky_flags(journal)
        if flags and not args.acknowledge_data_change:
            raise Refused(
                f"{' and '.join(f.replace('_', ' ').upper() for f in flags)} reported during this "
                "attempt: finish refused, nothing changed. Stop and verify the database; roll "
                "back with rollback.sh app, or - after the investigation - run finish again with "
                "--acknowledge-data-change (nothing is restored).",
                EXIT_UPDATE,
            )
        cleanup_legacy_override(dep)
        problems = check_contract_config(dep, cfg, dep.app_config(), "COMPOSE_FILES")
        if problems:
            raise Refused("; ".join(problems), EXIT_UPDATE)
        if inspect_image(expected) is None:
            raise Refused(f"the image {expected[:19]} of this update is gone", EXIT_UPDATE)
        if flags:
            acknowledge(dep, journal, args.approve)
        ok, pre = check_data(dep, journal, "before finish")
        if not ok:
            raise Refused(
                "the database / data differ from the attempt baseline: finish refused, nothing "
                "changed. Stop and verify; rollback.sh app, or finish --acknowledge-data-change "
                "after the investigation.",
                EXIT_UPDATE,
            )
        journal.step(
            "Q_intent",
            from_id=approved["image_id"],
            to_id=expected,
            approved_by=args.approve,
            done_by=["Q_checks"],
        )
        move_deploy_tag(dep, journal, expected, why="finish")
        try:
            recreate(
                dep, journal, [], "finish", "Q_normal_mode", dep.deploy_tag, expected,
                maintenance=False, pre=pre,
            )  # fmt: skip
            ok = health_checks(dep, cfg, expect_image=expected, journal=journal)
            ok_data, _ = check_data(dep, journal, "after the finish recreate")
            ok = ok and ok_data
        except Refused as e:
            log(f"FAIL {e}")
            ok = False
        if ok:
            write_approved(dep, "finish", expected, journal, version=journal.data.get("version"))
            journal.data["status"] = COMPLETED
            journal.data["completed"] = now_iso()
            journal.step("Q_checks", ok=True)
            log("normal mode restored and checked; the new image is the approved deployment")
            log(
                f"{dep.deploy_tag} -> {expected[:19]}: the operations script, a reboot and a plain "
                "`docker compose up -d` start it. compose-command.txt holds the same command."
            )
            return EXIT_OK
        move_deploy_tag(
            dep, journal, approved["image_id"], why="finish failed", done="TAG_reverted"
        )
        journal.data["status"] = FINISH_FAILED
        journal.step("Q_checks", ok=False)
        log(
            "FINISH FAILED: the application does not pass its checks in normal mode. It is NOT "
            f"marked completed; {dep.deploy_tag} is back on the approved image "
            f"{approved['image_id'][:19]} (a restart returns to it). Fix the cause and run "
            "finish.sh again, or roll back with: rollback.sh app"
        )
        return EXIT_UPDATE


def cmd_pin(args: argparse.Namespace) -> int:
    """DEPLOY_IMAGE_TAG vs approved.json vs the running container; --apply repairs the tag.

    The optional pin of Phase 12D3 is gone: the deploy tag IS the pin, moved only
    by a verified finish / rollback. `pin` is a read-only report; `pin --apply`
    re-points the tag to the approved image (idempotent, refused during an
    undecided attempt, recorded in the journal).
    """
    if args.undo:
        raise Refused(
            "pin --undo no longer exists: an approval is undone with `rollback.sh app`, which "
            "is checked",
            EXIT_USAGE,
        )
    cfg = load_config(args.config)
    dep = Deployment(cfg)
    tag = dep.need_deploy_tag()

    def report(journal: Journal) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
        approved = read_approved(dep.state)
        found = inspect_image(tag)
        tag_id = found[0] if found else None
        container = dep.app_container()
        running = dep.container_image_id(container) if container else None
        print(
            json.dumps(
                {
                    "deploy_tag": tag,
                    "deploy_tag_image_id": tag_id,
                    "approved": approved,
                    "running_image_id": running,
                    "journal_status": journal.data.get("status"),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return approved, tag_id, running

    if not args.apply:
        approved, tag_id, running = report(Journal(dep.state))
        if approved is None:
            log("no approved deployment recorded (approved.json): nothing to compare")
            return EXIT_OK
        if tag_id == approved["image_id"] == running:
            log("DEPLOY_IMAGE_TAG, approved.json and the running container agree")
            return EXIT_OK
        log("NOT consistent: pin.sh --apply re-points the tag to the approved image")
        return EXIT_DRIFT
    with update_lock(dep.state):
        journal = Journal(dep.state)
        approved, tag_id, running = report(journal)
        if approved is None:
            raise Refused("no approved deployment recorded (approved.json): nothing to repair", EXIT_UPDATE)
        status = journal.data.get("status")
        pending = journal.open_intents()
        repairs = [s for s in pending if s.get("step") == "TAG_intent" and s.get("why") == "pin repair"]
        if journal.data and (status not in CLOSED_STATES or len(repairs) != len(pending)):
            raise Refused(
                f"an attempt is undecided or interrupted (status {status}): finish it or roll "
                "it back; pin --apply does not decide",
                EXIT_UPDATE,
            )
        if tag_id == approved["image_id"]:
            for s in repairs:  # an interrupted repair that had already moved the tag
                journal.step("TAG_done", tag=tag, image_id=tag_id, previous=s.get("from_id"))
            log(f"{tag} already points to the approved image: nothing to repair")
        else:
            move_deploy_tag(
                dep, journal if journal.data else None, approved["image_id"], why="pin repair"
            )
        if running != approved["image_id"]:
            log(
                "the running container is another image: recreate it with your operations "
                f"script or {dep.state / COMPOSE_COMMAND}"
            )
        return EXIT_OK


LEGAL_GATE_PROCEDURE = (
    "rollback {what} no longer writes any override (Phase 12D5, contract step 2): the Legal "
    "Document gate is part of YOUR configuration. Procedure: 1) set "
    "OCR_LEGAL_NORMALIZATION_ENABLED={value} in the environment of the application in your local "
    "compose override / .env; 2) recreate the application with your operations script (or the "
    "command in STATE_DIR/compose-command.txt); 3) run healthcheck.sh. Nothing was changed."
)


def cmd_rollback(args: argparse.Namespace) -> int:
    if args.what in ("legal-off", "legal-on"):
        raise Refused(
            LEGAL_GATE_PROCEDURE.format(
                what=args.what, value="false" if args.what == "legal-off" else "true"
            ),
            EXIT_USAGE,
        )
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
    dep.need_deploy_tag()
    with update_lock(dep.state):
        journal = Journal(dep.state)
        approved = read_approved(dep.state)
        cleanup_legacy_override(dep)
        container = dep.app_container()
        running = dep.container_image_id(container) if container else ""
        baseline = journal.data.get("baseline") or {}
        if (
            args.what == "interrupted"
            and journal.data.get("status") == IN_PROGRESS
            and not journal.done("N_recreated")
            and baseline.get("image_id")
            and running == baseline["image_id"]
        ):
            return close_interrupted(dep, cfg, journal, approved, args)
        return rollback_app(dep, cfg, journal, approved, args, container, running)


def close_interrupted(
    dep: Deployment,
    cfg: Dict[str, str],
    journal: Journal,
    approved: Optional[Dict[str, Any]],
    args: argparse.Namespace,
) -> int:
    """The update stopped before the new image ran: close the attempt (never touches the tag).

    The source goes back to the commit recorded in K_intent; an application the
    attempt put into maintenance (quiesce) is recreated in normal mode on the
    approved image.
    """
    baseline_id = journal.data["baseline"]["image_id"]
    approved_id = approved["image_id"] if approved else baseline_id
    flags = sticky_flags(journal)
    if flags and not args.acknowledge_data_change:
        raise Refused(
            f"{' and '.join(f.replace('_', ' ').upper() for f in flags)} reported during this "
            "attempt: stop and verify the database first; then close the attempt with "
            "--acknowledge-data-change (nothing is restored). Nothing was changed.",
            EXIT_UPDATE,
        )
    if flags:
        acknowledge(dep, journal, operator_name())
    note = restore_source(dep, journal)
    log(f"source: {note}")
    if journal.done("MAINT_intent"):
        problems = check_contract_config(dep, cfg, dep.app_config(), "COMPOSE_FILES")
        if problems:
            raise Refused("; ".join(problems), EXIT_UPDATE)
        recreate(
            dep, journal, [], "normal", "NORMAL_restored", dep.deploy_tag, approved_id,
            maintenance=False,
        )  # fmt: skip
        ok = health_checks(dep, cfg, expect_image=approved_id, journal=journal)
        ok_data, _ = check_data(dep, journal, "after leaving maintenance")
        if not (ok and ok_data):
            journal.data["status"] = ROLLBACK_FAILED
            journal.step("NORMAL_checks", ok=False)
            log(
                "the approved image is back in normal mode but does NOT pass its checks: "
                "status rollback_failed; investigate, then run rollback.sh app"
            )
            return EXIT_UPDATE
        log("the application left maintenance mode (approved image, normal mode)")
    else:
        log("the update had not recreated the application: it is left running, untouched")
    journal.data["status"] = ROLLED_BACK
    journal.step("ROLLBACK_nothing_recreated", image_id=approved_id, source=note)
    log("the next update is a new attempt with its own backup")
    return EXIT_OK


def rollback_app(
    dep: Deployment,
    cfg: Dict[str, str],
    journal: Journal,
    approved: Optional[Dict[str, Any]],
    args: argparse.Namespace,
    container: Optional[str],
    running: str,
) -> int:
    """Back to the approved image of before the attempt, by VERIFIED IMAGE ID (F-24a, R2-20b)."""
    baseline = journal.data.get("baseline") or {}
    reference = baseline.get("image_id") or (approved or {}).get("image_id")
    if args.to_image:
        check_image_ref(args.to_image, "--to-image")
        found = inspect_image(args.to_image)
        if found is None:
            raise Refused(
                f"--to-image {args.to_image} does not exist locally", EXIT_UPDATE
            )
        target_id = found[0]
        if not reference and not args.force_image:
            raise Refused(
                "no attempt baseline and no approved deployment are recorded: nothing proves "
                f"that {args.to_image} is the previous version. Pass --force-image to vouch for it.",
                EXIT_UPDATE,
            )
        if reference and target_id != reference and not args.force_image:
            raise Refused(
                f"--to-image points to {target_id[:19]}, the recorded previous image is "
                f"{reference[:19]}: pass --force-image to use it anyway",
                EXIT_UPDATE,
            )
    else:
        if not reference:
            raise Refused(
                "no baseline image recorded: pass --to-image <tag of the previous version> "
                "--force-image",
                EXIT_UPDATE,
            )
        target_id = str(reference)
    flags = sticky_flags(journal)
    if flags and not args.acknowledge_data_change:
        raise Refused(
            f"{' and '.join(f.replace('_', ' ').upper() for f in flags)} reported during this "
            "attempt: stop and verify the database first; then roll back with "
            "--acknowledge-data-change (nothing is restored). Nothing was changed.",
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
    # Everything that can refuse with NOTHING changed comes first (R2-12).
    maintenance = (
        []
        if args.no_maintenance or not cfg["MAINTENANCE_OVERRIDE"]
        else [cfg["MAINTENANCE_OVERRIDE"]]
    )
    before = dep.config_json()
    after = dep.config_json(maintenance) if maintenance else before
    compare_configs(dep, before, after, maintenance=bool(maintenance))
    problems = check_contract_config(dep, cfg, after["services"][dep.app], "COMPOSE_FILES")
    if [p for p in problems if "contract step 1" in p]:
        raise Refused("; ".join(problems), EXIT_UPDATE)
    for p in problems:
        log(f"WARNING {p}")
    if flags:
        acknowledge(dep, journal, operator_name())
    # A tag can be moved; the ID cannot. Use the recorded tag only when it still
    # points to the target, otherwise bind a fresh tag to the verified ID.
    tag = str(journal.data.get("rollback_tag") or "")
    tagged = inspect_image(tag) if IMAGE_REF_RE.match(tag) else None
    if tagged is None or tagged[0] != target_id:
        tag = f"{cfg['IMAGE_REPO']}:rollback-verified-{_dt.datetime.now().strftime('%Y%m%d%H%M%S')}"
        check_image_ref(tag)
        run(["docker", "tag", target_id, tag])
        journal.data["rollback_tag"] = tag
        log(f"rollback tag {tag} bound to {target_id[:19]}")
    quiet_before = bool(
        journal.data.get("maintenance")
        and container
        and container == journal.data.get("app_container")
    )
    pre = fingerprint(dep)  # may be unreadable: a broken version is the usual reason
    journal.data.setdefault("steps", [])
    journal.step(
        "ROLLBACK_intent",
        from_id=running,
        to_id=target_id,
        approved_before=(approved or {}).get("image_id"),
        done_by=["ROLLBACK_done"],
    )
    ok = False
    try:
        move_deploy_tag(dep, journal, target_id, why="rollback")
        # Source first: the previous image must be recreated from the definition it
        # was deployed with, not from the release's compose files (F-24b).
        note = restore_source(dep, journal)
        log(f"source: {note}")
        if note.startswith("source back at"):
            after = dep.config_json(maintenance) if maintenance else dep.config_json()
            compare_configs(dep, dep.config_json(), after, maintenance=bool(maintenance))
        recorded = baseline.get("config_sha256")
        if recorded and recorded != sha256_bytes(
            json.dumps(dep.config_json(), sort_keys=True).encode()
        ):
            log(
                "WARNING: the effective compose configuration differs from the one recorded "
                "before the update (changed compose files or .env?): the previous image is "
                "started with the CURRENT definition"
            )
        recreate(
            dep, journal, maintenance, "rollback", "ROLLBACK_app", dep.deploy_tag, target_id,
            maintenance=bool(maintenance), pre=pre,
        )  # fmt: skip
        ok = health_checks(dep, cfg, expect_image=target_id, journal=journal)
        ok_data, _ = check_data(
            dep, journal, "after the rollback recreate",
            exact=pre["summary"] if (pre and maintenance and quiet_before) else None,
        )  # fmt: skip
        ok = ok and ok_data
    except Refused as e:
        log(f"FAIL {e}")
        ok = False
    if not ok:
        journal.data["status"] = ROLLBACK_FAILED
        journal.step("ROLLBACK_done", ok=False, image_id=target_id)
        log(
            "ROLLBACK NOT CONFIRMED: status rollback_failed. DEPLOY_IMAGE_TAG stays on the "
            f"rollback target {target_id[:19]} (the previously approved image); nothing else is "
            "changed or restored. Investigate, then run rollback.sh app again."
        )
        return EXIT_UPDATE
    write_approved(dep, "rollback", target_id, journal, version=baseline.get("app_version"))
    journal.data["status"] = ROLLED_BACK
    journal.data["rolled_back"] = now_iso()
    journal.step("ROLLBACK_done", ok=True, image_id=target_id, tag=tag)
    log(
        f"application rolled back to {tag} ({target_id[:19]}) and checked; database not restored"
    )
    if maintenance:
        log("after approval, leave maintenance with: rollback.sh app --no-maintenance")
    return EXIT_OK


# --------------------------------------------------------------------------- #
# health / status / snapshot
# --------------------------------------------------------------------------- #


def cmd_health(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    dep = Deployment(cfg)
    journal = Journal(Path(cfg["STATE_DIR"]))
    approved = read_approved(Path(cfg["STATE_DIR"]))
    ok = health_checks(dep, cfg, expect_image=None, prove_offline=args.prove_offline)
    report = assess(dep, cfg, journal, approved)
    for line in report["drift"]:
        log("FAIL " + line)
    for line in report["undecided"]:
        log("WARN " + line)
    for line in report["notes"]:
        log("note " + line)
    if report["drift"]:
        return EXIT_DRIFT
    if not ok:
        return EXIT_UPDATE
    return assess_exit(report)


def cmd_status(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    state = Path(cfg["STATE_DIR"])
    journal = Journal(state)
    approved = read_approved(state)
    report: Dict[str, Any] = dict(journal.data) if journal.data else {"status": "no update recorded"}
    report["approved"] = approved
    assessed: Dict[str, Any] = {"drift": [], "undecided": [], "notes": []}
    if cfg.get("DEPLOY_DIR") and cfg.get("COMPOSE_PROJECT"):
        try:
            assessed = assess(Deployment(cfg), cfg, journal, approved)
        except Refused as e:
            assessed["drift"] = [f"could not inspect the deployment: {e}"]
    else:
        assessed["notes"] = ["DEPLOY_DIR / COMPOSE_PROJECT not configured: nothing compared"]
    report.update(assessed)
    print(json.dumps(report, indent=2, sort_keys=True))
    for line in assessed["drift"]:
        log("DRIFT " + line)
    for line in assessed["undecided"]:
        log("UNDECIDED " + line)
    for line in assessed["notes"]:
        log("note " + line)
    return assess_exit(assessed)


def take_snapshot(dep: Deployment, cfg: Dict[str, str]) -> Dict[str, Any]:
    """Read-only: database container, records, images, model files (no lock, no journal)."""
    unreadable: List[str] = []
    try:
        db: Optional[Dict[str, Any]] = db_identity(dep)
    except Refused as e:
        db = None
        unreadable.append(f"database container: {e}")
    container = dep.app_container()
    app = None
    if container:
        env = container_env(container)
        app = {
            "container": container,
            "image_id": dep.container_image_id(container),
            "env_keys": sorted(env),  # names only, never values
            "required_env_missing": env_missing(required_env(cfg), env),
        }
    else:
        unreadable.append("application container not running")
    tag = None
    if dep.deploy_tag and IMAGE_REF_RE.match(dep.deploy_tag):
        found = inspect_image(dep.deploy_tag)
        tag = {"ref": dep.deploy_tag, "image_id": found[0] if found else None}
    fp = fingerprint(dep) if container else None
    if fp is None:
        unreadable.append("data fingerprint")
    artifacts = artifact_snapshot(dep) if container else None
    if artifacts is None:
        unreadable.append("model files")
    return {
        "schema": 1,
        "kind": "chatbot5400-offline-snapshot",
        "taken_at": now_iso(),
        "db": db,
        "app": app,
        "deploy_tag": tag,
        "data": fp["summary"] if fp else None,
        "counts": fp_counts(fp),
        "records": fp["ids"] if fp else None,
        "artifacts": artifacts,
        "unreadable": unreadable,
    }


def compare_snapshots(earlier: Any, now: Dict[str, Any]) -> Tuple[int, List[str]]:
    """0: nothing lost (additions reported); 5: a record / file / identity lost or changed;
    3: something cannot be read."""
    if not isinstance(earlier, dict) or earlier.get("kind") != "chatbot5400-offline-snapshot":
        return EXIT_VERIFY, ["the earlier file is not a snapshot of this tool"]
    if earlier.get("records") is None or earlier.get("db") is None:
        return EXIT_VERIFY, ["the earlier snapshot has no readable records / database identity"]
    if now.get("records") is None or now.get("db") is None:
        return EXIT_VERIFY, [f"cannot read now: {now.get('unreadable')}"]
    lost: List[str] = []
    info: List[str] = []
    for t, ids in sorted(earlier["records"].items()):
        have = set(now["records"].get(t) or [])
        missing = [i for i in ids if i not in have]
        if missing:
            lost.append(f"LOST {t}: {len(missing)} of {len(ids)} records (e.g. {missing[:3]})")
        added = len(have - set(ids))
        if added:
            info.append(f"added {t}: {added} records")
    changed = db_identity_changes(earlier["db"], now["db"], within_recreate=False)
    if changed:
        lost.append(f"CHANGED the database container / volume: {changed}")
    elif earlier["db"].get("started_at") != now["db"].get("started_at"):
        info.append("the database container was restarted in between")
    if earlier.get("artifacts") is not None:
        if now.get("artifacts") is None:
            return EXIT_VERIFY, ["the model files cannot be listed now"]
        lost += [f"LOST / CHANGED model file {x}" for x in artifact_losses(earlier["artifacts"], now["artifacts"])]
    for key, label in (("deploy_tag", "deploy tag"), ("app", "application image")):
        before_id = (earlier.get(key) or {}).get("image_id")
        after_id = (now.get(key) or {}).get("image_id")
        if before_id != after_id:
            info.append(f"{label}: {str(before_id)[:19]} -> {str(after_id)[:19]}")
    lines = lost + info + ([] if lost else ["nothing was lost"])
    return (EXIT_UPDATE if lost else EXIT_OK), lines


def cmd_snapshot(args: argparse.Namespace) -> int:
    """Read-only helper of the manual fallback procedure (no lock, no journal)."""
    cfg = load_config(args.config)
    dep = Deployment(cfg)
    snap = take_snapshot(dep, cfg)
    if args.out:
        write_json_private(Path(args.out), snap)  # holds record ids: private
        log(f"snapshot written to {args.out} (record ids only, no content)")
    print(json.dumps({k: v for k, v in snap.items() if k != "records"}, indent=2, sort_keys=True))
    if not args.compare:
        return EXIT_VERIFY if snap["unreadable"] else EXIT_OK
    try:
        earlier = json.loads(Path(args.compare).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        log(f"the earlier snapshot {args.compare} is unreadable")
        return EXIT_VERIFY
    rc, lines = compare_snapshots(earlier, snap)
    for line in lines:
        log(line)
    return rc


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
    b.add_argument(
        "--allow-unlabelled-image",
        action="store_true",
        help="TEST builds only: accept an image without the org.opencontainers.image.revision "
        "label; the package is marked provenance 'unverified' and every server refuses it",
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

    v = sub.add_parser(
        "verify",
        help="authenticate, then verify and unpack a package; the trusted result is recorded "
        "in STATE_DIR/verified/<package sha256>.json",
    )
    v.add_argument("package")
    v.add_argument("--extract-to", required=True)
    v.add_argument("--config", help="server configuration (STATE_DIR, ALLOWED_SIGNERS, SIGNATURE_POLICY)")
    v.add_argument(
        "--expected-sha256", help="value received over a SEPARATE trusted channel"
    )
    v.add_argument("--allowed-signers", default=None, help="default: ALLOWED_SIGNERS of the configuration")
    v.add_argument("--identity", default=None, help="default: SIGNER_IDENTITY of the configuration")
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
        sp.add_argument(
            "--ignore-jobs",
            action="store_true",
            help="do not wait for background jobs (the data fingerprints are still compared)",
        )
        sp.add_argument(
            "--no-maintenance",
            action="store_true",
            help="no maintenance recreate; needs --writes-stopped-confirmed",
        )
        sp.add_argument(
            "--writes-stopped-confirmed",
            action="store_true",
            help="operator attests that nobody writes (no public port to close, or "
            "--no-maintenance); the data fingerprint is still compared",
        )
        sp.add_argument(
            "--backup-reference",
            help="id of an approved backup taken NOW, for this run (single use)",
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

    ack_help = (
        "the reported database / data change was investigated: compare with the database as "
        "it is now (recorded with who and when; nothing is restored)"
    )
    f = sub.add_parser("finish", help="approve: move DEPLOY_IMAGE_TAG, normal mode (checked)")
    f.add_argument("--config")
    f.add_argument("--approve", help="who approved (recorded in the journal)")
    f.add_argument("--acknowledge-data-change", action="store_true", help=ack_help)
    f.set_defaults(func=cmd_finish)

    pn = sub.add_parser(
        "pin",
        help="report DEPLOY_IMAGE_TAG vs approved.json vs the container; --apply repairs the tag",
    )
    pn.add_argument("--config")
    pn.add_argument("--apply", action="store_true", help="re-point DEPLOY_IMAGE_TAG to the approved image")
    pn.add_argument("--undo", action="store_true", help="obsolete: refused (use rollback.sh app)")
    pn.set_defaults(func=cmd_pin)

    r = sub.add_parser(
        "rollback",
        help="app | interrupted | agri (legal-off / legal-on: refused, the gate is your configuration)",
    )
    r.add_argument(
        "what", choices=["app", "legal-off", "legal-on", "agri", "interrupted"]
    )
    r.add_argument("--config")
    r.add_argument("--to-image")
    r.add_argument(
        "--force-image",
        action="store_true",
        help="accept a --to-image that is not the recorded previous (approved) image",
    )
    r.add_argument("--package-dir")
    r.add_argument(
        "--acknowledge-data-change",
        "--acknowledge-db-change",
        dest="acknowledge_data_change",
        action="store_true",
        help=ack_help,
    )
    r.add_argument("--maintenance", action="store_true", help="obsolete (legal gate)")
    r.add_argument(
        "--no-maintenance", action="store_true", help="recreate in normal mode"
    )
    r.set_defaults(func=cmd_rollback)

    h = sub.add_parser("health", help="functional + offline readiness + drift checks")
    h.add_argument("--config")
    h.add_argument("--prove-offline", action="store_true")
    h.set_defaults(func=cmd_health)

    s = sub.add_parser("status", help="journal, approved deployment and drift (exit 0 / 7 / 8)")
    s.add_argument("--config")
    s.set_defaults(func=cmd_status)

    sn = sub.add_parser(
        "snapshot",
        help="read-only record of the database / images / model files; --compare an earlier one "
        "(exit 0 nothing lost, 5 lost or changed, 3 unreadable)",
    )
    sn.add_argument("--config")
    sn.add_argument("--out", help="write the snapshot (with record ids, mode 0600) to this file")
    sn.add_argument("--compare", help="an earlier snapshot file to compare with")
    sn.set_defaults(func=cmd_snapshot)
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
