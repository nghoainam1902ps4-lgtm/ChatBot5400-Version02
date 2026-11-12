"""Install-state manifests, file locks and model verification.

One JSON manifest per engine (``<manifests>/<engine>.json``) records the
install lifecycle so the API (a different process from the worker that does
the download) can show truthful progress. Writes are atomic (tmp + rename).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from open_notebook.ocr import catalog, paths

# Lifecycle states (MASTER_PLAN Phase 2.4).
NOT_INSTALLED = "not_installed"
PENDING = "pending"
DOWNLOADING = "downloading"
INSTALLING = "installing"
REQUIRES_RESTART = "requires_restart"
READY = "ready"
FAILED = "failed"
INCOMPATIBLE = "incompatible"
# Internal manifest value: model files verified by the last install job.
INSTALLED = "installed"
ACTIVE_JOB_STATES = (PENDING, DOWNLOADING, INSTALLING)
# The worker refreshes ``updated_at`` at least every few seconds while it works;
# a job silent for this long is considered dead (worker crash) and retryable.
STALE_AFTER_SECONDS = 15 * 60
# A queued job may legitimately wait behind long source-processing jobs.
PENDING_STALE_AFTER_SECONDS = 6 * 60 * 60


def _manifest_path(engine_id: str) -> Path:
    catalog.get_engine(engine_id)  # validates the id: no path injection via name
    return paths.manifests_dir() / f"{engine_id}.json"


def read_state(engine_id: str) -> dict[str, Any]:
    try:
        data = json.loads(_manifest_path(engine_id).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(engine_id: str, data: dict[str, Any]) -> dict[str, Any]:
    paths.ensure_dirs()
    data = dict(data)
    data["engine_id"] = engine_id
    data["updated_at"] = time.time()
    target = _manifest_path(engine_id)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)
    return data


def update_state(engine_id: str, **changes: Any) -> dict[str, Any]:
    data = read_state(engine_id)
    data.update(changes)
    return write_state(engine_id, data)


def job_is_active(state: dict[str, Any], now: float | None = None) -> bool:
    if state.get("state") not in ACTIVE_JOB_STATES:
        return False
    now = now or time.time()
    age = now - float(state.get("updated_at") or 0)
    limit = (
        PENDING_STALE_AFTER_SECONDS
        if state.get("state") == PENDING
        else STALE_AFTER_SECONDS
    )
    return age < limit


# --- Locks --------------------------------------------------------------------


class LockBusy(RuntimeError):
    pass


@contextlib.contextmanager
def file_lock(name: str) -> Iterator[None]:
    """Non-blocking exclusive lock (prevents duplicate concurrent installs)."""
    paths.ensure_dirs()
    lock_path = paths.downloads_dir() / f"{name}.lock"
    fh = open(lock_path, "a+")
    try:
        try:
            import fcntl

            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as e:
                raise LockBusy(f"{name} is already being installed") from e
        except ImportError:  # pragma: no cover - Windows dev fallback
            import msvcrt

            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
            except OSError as e:
                raise LockBusy(f"{name} is already being installed") from e
        yield
    finally:
        fh.close()


# --- Verification ---------------------------------------------------------------

# (path, size, mtime_ns) -> sha256; hashing 80 MB on every status poll is wasteful.
_hash_cache: dict[tuple[str, int, int], str] = {}


def sha256_file(path: Path) -> str:
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime_ns)
    cached = _hash_cache.get(key)
    if cached:
        return cached
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    digest = h.hexdigest()
    _hash_cache[key] = digest
    return digest


@dataclass
class FileCheck:
    rel_path: str
    present: bool
    verified: bool
    size: int
    detail: str | None = None


def check_file(mf: catalog.ModelFile) -> FileCheck:
    raw = paths.models_dir() / mf.rel_path
    if raw.is_symlink():
        return FileCheck(mf.rel_path, True, False, 0, "symlinks are not accepted")
    try:
        target = paths.safe_child(paths.models_dir(), mf.rel_path)
    except ValueError as e:  # a symlinked parent directory escaping the volume
        return FileCheck(mf.rel_path, True, False, 0, str(e))
    if target.is_symlink():
        return FileCheck(mf.rel_path, True, False, 0, "symlinks are not accepted")
    if not target.is_file():
        return FileCheck(mf.rel_path, False, False, 0)
    size = target.stat().st_size
    if size != mf.size:
        return FileCheck(
            mf.rel_path, True, False, size, f"size {size} != expected {mf.size}"
        )
    if sha256_file(target) != mf.sha256:
        return FileCheck(mf.rel_path, True, False, size, "sha256 mismatch")
    return FileCheck(mf.rel_path, True, True, size)


@dataclass
class ModelStatus:
    status: str  # builtin | not_installed | partial | corrupted | installed
    files: list[FileCheck]

    @property
    def installed(self) -> bool:
        return self.status in ("installed", "builtin")

    @property
    def installed_bytes(self) -> int:
        return sum(f.size for f in self.files if f.verified)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "installed_bytes": self.installed_bytes,
            "files": [f.__dict__ for f in self.files],
        }


def model_status(engine_id: str) -> ModelStatus:
    spec = catalog.get_engine(engine_id)
    if not spec.files:
        return ModelStatus("builtin", [])
    checks = [check_file(f) for f in spec.files]
    if all(c.verified for c in checks):
        return ModelStatus("installed", checks)
    if any(c.present and not c.verified for c in checks):
        return ModelStatus("corrupted", checks)
    if any(c.verified for c in checks if not _is_shared(spec, c.rel_path)):
        return ModelStatus("partial", checks)
    return ModelStatus("not_installed", checks)


def _is_shared(spec: catalog.EngineSpec, rel_path: str) -> bool:
    return any(f.shared and f.rel_path == rel_path for f in spec.files)
