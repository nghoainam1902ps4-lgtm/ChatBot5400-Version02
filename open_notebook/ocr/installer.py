"""Model installer for the OCR Engine Manager (runs in the worker or admin CLI).

Guarantees (MASTER_PLAN Phase 2.4):
- only catalog URLs, only allow-listed hosts on every redirect hop;
- disk-space check before downloading;
- download into ``downloads/`` staging with HTTP Range resume, then SHA-256
  check, then atomic ``os.replace`` into ``models/`` — a half-written or
  tampered file is never visible to OCR;
- per-engine lock (no duplicate concurrent installs) and bounded retries;
- offline: files are taken from ``OCR_PACKAGES_DIR/models`` (offline bundle)
  first; with ``OCR_OFFLINE=true`` the network is never touched;
- the engine is never marked ready before checksum + smoke check succeed.

Nothing here installs Python packages or system packages: those are runtime
installs done by the entrypoint / admin CLI (DECISIONS D-06).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

from loguru import logger

from open_notebook.ocr import catalog, paths, runtime, store

ProgressCb = Callable[[dict[str, Any]], None]

_MAX_REDIRECTS = 5
_ATTEMPTS = 3
_DISK_MARGIN = 64 * 1024 * 1024


class InstallError(Exception):
    """A permanent, user-explainable installation failure."""


def _check_host(url: str) -> None:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in catalog.ALLOWED_DOWNLOAD_HOSTS
    ):
        raise InstallError(f"Refusing to download from non-allow-listed URL: {url}")


def _download(
    url: str, part: Path, expected_size: int, progress: Callable[[int], None]
) -> None:
    """Stream ``url`` into ``part``, resuming an interrupted transfer."""
    import httpx

    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        _check_host(current)
        offset = part.stat().st_size if part.exists() else 0
        if offset > expected_size:
            part.unlink()
            offset = 0
        if offset == expected_size:
            return
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        with httpx.Client(
            timeout=httpx.Timeout(60.0, connect=20.0), follow_redirects=False
        ) as client:
            with client.stream("GET", current, headers=headers) as resp:
                if resp.status_code in (301, 302, 303, 307, 308):
                    location = resp.headers.get("location")
                    if not location:
                        raise InstallError("Redirect without location")
                    current = urljoin(current, location)
                    continue
                if resp.status_code == 416:  # range not satisfiable -> restart
                    part.unlink(missing_ok=True)
                    continue
                if resp.status_code not in (200, 206):
                    raise IOError(f"HTTP {resp.status_code} for {current}")
                mode = "ab" if resp.status_code == 206 and offset else "wb"
                written = offset if mode == "ab" else 0
                with open(part, mode) as fh:
                    for chunk in resp.iter_bytes(1024 * 256):
                        fh.write(chunk)
                        written += len(chunk)
                        if written > expected_size:
                            raise InstallError(
                                f"{current} is larger than the pinned size"
                            )
                        progress(written)
                return
    raise InstallError("Too many redirects")


def _extract_member(archive: Path, member: str, dest: Path, max_size: int) -> None:
    """Extract exactly one expected member, by name, with a size cap (no traversal)."""
    with zipfile.ZipFile(archive) as zf:
        try:
            info = zf.getinfo(member)
        except KeyError as e:
            raise InstallError(f"{archive.name} does not contain {member}") from e
        if info.file_size != max_size or "/" in info.filename or "\\" in info.filename:
            raise InstallError(
                f"Unexpected archive member {info.filename} ({info.file_size} bytes)"
            )
        with zf.open(info) as src, open(dest, "wb") as out:
            copied = 0
            for chunk in iter(lambda: src.read(1024 * 1024), b""):
                copied += len(chunk)
                if copied > max_size:
                    raise InstallError("Archive member exceeds pinned size")
                out.write(chunk)


def _bundle_source(mf: catalog.ModelFile) -> Path | None:
    """An offline-bundle copy of this file, if present (already extracted form)."""
    try:
        candidate = paths.safe_child(paths.packages_dir() / "models", mf.rel_path)
    except ValueError:
        return None
    return candidate if candidate.is_file() and not candidate.is_symlink() else None


def required_free_bytes(spec: catalog.EngineSpec) -> int:
    need = 0
    for mf in spec.files:
        if store.check_file(mf).verified:
            continue
        need += mf.size + (mf.archive_size or 0)
    return need + _DISK_MARGIN if need else 0


def _ensure_space(spec: catalog.EngineSpec) -> None:
    need = required_free_bytes(spec)
    if not need:
        return
    paths.ensure_dirs()
    free = shutil.disk_usage(paths.models_dir()).free
    if free < need:
        raise InstallError(
            f"Not enough disk space: need {need // (1024 * 1024)} MB, "
            f"have {free // (1024 * 1024)} MB free on {paths.models_dir()}"
        )


def _install_file(
    engine_id: str, mf: catalog.ModelFile, report: Callable[[int], None]
) -> str:
    """Make ``mf`` present and verified. Returns where it came from."""
    if store.check_file(mf).verified:
        return "existing"
    target = paths.safe_child(paths.models_dir(), mf.rel_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = paths.downloads_dir()
    staging.mkdir(parents=True, exist_ok=True)
    stem = mf.rel_path.replace("/", "__")
    final_tmp = staging / f"{stem}.{engine_id}.verified.tmp"

    bundled = _bundle_source(mf)
    if bundled is not None:
        shutil.copyfile(bundled, final_tmp)
        source = "bundle"
    elif paths.offline_mode():
        raise InstallError(
            f"OCR_OFFLINE is set and {mf.rel_path} is not in the offline bundle "
            f"({paths.packages_dir() / 'models'})."
        )
    else:
        part = staging / f"{stem}.{'zip' if mf.archive_member else 'bin'}.part"
        expected = mf.archive_size or mf.size
        expected_sha = mf.archive_sha256 or mf.sha256
        last_err: Exception | None = None
        for attempt in range(1, _ATTEMPTS + 1):
            try:
                _download(mf.url, part, expected, report)
                if (
                    part.stat().st_size != expected
                    or store.sha256_file(part) != expected_sha
                ):
                    part.unlink(missing_ok=True)
                    raise IOError(f"Checksum mismatch for {mf.url}")
                last_err = None
                break
            except InstallError:
                raise
            except Exception as e:  # network / IO: retry with backoff, resume
                last_err = e
                logger.warning(
                    f"OCR download attempt {attempt}/{_ATTEMPTS} failed: {e}"
                )
                time.sleep(min(2**attempt, 10))
        if last_err is not None:
            raise InstallError(
                f"Download failed after {_ATTEMPTS} attempts: {last_err}"
            )
        if mf.archive_member:
            _extract_member(part, mf.archive_member, final_tmp, mf.size)
            part.unlink(missing_ok=True)
        else:
            os.replace(part, final_tmp)
        source = "download"

    if final_tmp.stat().st_size != mf.size or store.sha256_file(final_tmp) != mf.sha256:
        final_tmp.unlink(missing_ok=True)
        raise InstallError(f"Checksum verification failed for {mf.rel_path}")
    os.replace(final_tmp, target)
    return source


def smoke_check(engine_id: str) -> dict[str, Any]:
    """Prove the installed model loads with the real runtime (no Docling needed).

    Returns {"ok": bool|None, "detail": str}; ok=None when the runtime is not
    installed yet (model files are still verified by checksum).
    """
    spec = catalog.get_engine(engine_id)
    rt = runtime.probe_runtime(engine_id)
    if rt.status in (runtime.RUNTIME_MISSING, runtime.RUNTIME_INCOMPATIBLE):
        return {"ok": None, "detail": f"runtime {rt.status}: {rt.detail}"}
    sample = Path(__file__).parent / "assets" / "sample_vi.png"
    if spec.runtime == "tesseract":
        cmd = runtime.tesseract_cmd()
        langs = catalog.DOCLING_LANGS[engine_id]
        assert cmd
        runtime.ensure_tessdata_layout()
        listed = subprocess.run(
            [cmd, "--list-langs"],
            capture_output=True,
            timeout=30,
            env=runtime.tesseract_env(),
            check=False,
        )
        available = (listed.stdout or b"").decode("utf-8", "replace").split()
        missing = [lang for lang in langs + ["osd"] if lang not in available]
        if missing:
            return {
                "ok": False,
                "detail": f"tesseract --list-langs is missing {missing}",
            }
        proc = subprocess.run(
            [cmd, str(sample), "stdout", "-l", "+".join(langs)],
            capture_output=True,
            timeout=120,
            env=runtime.tesseract_env(),
            check=False,
        )
        text = (proc.stdout or b"").decode("utf-8", "replace").strip()
        if proc.returncode != 0 or not text:
            return {
                "ok": False,
                "detail": (proc.stderr or b"").decode("utf-8", "replace")[-400:],
            }
        return {
            "ok": True,
            "detail": f"recognised {len(text)} characters from the built-in sample",
        }
    if spec.runtime == "easyocr":
        import easyocr  # type: ignore[import-not-found]

        reader = easyocr.Reader(
            ["vi", "en"],
            gpu=False,
            model_storage_directory=str(paths.easyocr_dir()),
            download_enabled=False,
            verbose=False,
        )
        lines = reader.readtext(str(sample), detail=0)
        text = " ".join(lines).strip()
        if not text:
            return {
                "ok": False,
                "detail": "EasyOCR returned no text for the built-in sample",
            }
        return {
            "ok": True,
            "detail": f"recognised {len(text)} characters from the built-in sample",
        }
    return {"ok": True, "detail": "builtin"}


def install_models(
    engine_id: str, progress: ProgressCb | None = None
) -> dict[str, Any]:
    """Install (or repair) the model files of ``engine_id``. Idempotent."""
    spec = catalog.get_engine(engine_id)
    if not spec.files:
        raise InstallError(
            f"{spec.display_name} uses the project's built-in model; nothing to install."
        )
    paths.ensure_dirs()
    sources: dict[str, str] = {}
    total = spec.download_size
    done_before = 0

    def emit(**kw: Any) -> None:
        state = store.update_state(engine_id, **kw)
        if progress:
            progress(state)

    with store.file_lock(f"install-{engine_id}"):
        emit(
            state=store.DOWNLOADING,
            error=None,
            progress={"bytes_done": 0, "bytes_total": total},
        )
        _ensure_space(spec)
        last_emit = 0.0
        for mf in spec.files:
            base = done_before

            def report(written: int, _base: int = base) -> None:
                nonlocal last_emit
                now = time.time()
                if now - last_emit >= 1.0:
                    last_emit = now
                    emit(
                        progress={
                            "bytes_done": _base + written,
                            "bytes_total": total,
                            "file": mf.rel_path,
                        }
                    )

            # Shared files (osd) get their own lock so fast/best never write it at once.
            if mf.shared:
                with store.file_lock(
                    f"shared-{mf.rel_path.replace('/', '__')}", timeout=1800
                ):
                    sources[mf.rel_path] = _install_file(engine_id, mf, report)
            else:
                sources[mf.rel_path] = _install_file(engine_id, mf, report)
            done_before += mf.download_size
            emit(progress={"bytes_done": done_before, "bytes_total": total})

        emit(state=store.INSTALLING)
        ms = store.model_status(engine_id)
        if not ms.installed:
            raise InstallError(f"Model verification failed: {ms.to_dict()}")
        smoke = smoke_check(engine_id)
        if smoke["ok"] is False:
            raise InstallError(f"Smoke check failed: {smoke['detail']}")
        final = store.update_state(
            engine_id,
            # "installed" = model verified; READY is computed live together with
            # the runtime probe (status.py), so it can never go stale.
            state=store.INSTALLED,
            installed_at=time.time(),
            sources=sources,
            smoke=smoke,
            error=None,
            nonce=None,
        )
        logger.info(
            f"OCR model install finished for {engine_id}: sources={sources} smoke={smoke}"
        )
        return final


def delete_models(engine_id: str, active_engine: str | None) -> list[str]:
    """Remove the engine's own model files. Never the shared/builtin ones in use."""
    spec = catalog.get_engine(engine_id)
    if not spec.files:
        raise InstallError("The built-in RapidOCR model cannot be removed.")
    if active_engine == engine_id:
        raise InstallError("This engine is in use. Activate another engine first.")
    if store.job_is_active(store.read_state(engine_id)):
        raise InstallError("An installation of this engine is in progress.")
    removed: list[str] = []
    with store.file_lock(f"install-{engine_id}"):
        for mf in spec.files:
            if mf.shared:
                others = [
                    e for e in catalog.engines_sharing(mf.rel_path) if e != engine_id
                ]
                # Kept while ANY other engine has its own files on disk (even
                # corrupted ones) or an install in flight (e.g. osd for fast/best).
                if any(
                    store.model_status(o).status != "not_installed"
                    or store.job_is_active(store.read_state(o))
                    for o in others
                ):
                    continue
                with store.file_lock(
                    f"shared-{mf.rel_path.replace('/', '__')}", timeout=60
                ):
                    target = paths.safe_child(paths.models_dir(), mf.rel_path)
                    if target.is_file() or target.is_symlink():
                        target.unlink()
                        removed.append(mf.rel_path)
                continue
            target = paths.safe_child(paths.models_dir(), mf.rel_path)
            if target.is_file() or target.is_symlink():
                target.unlink()
                removed.append(mf.rel_path)
        store.write_state(
            engine_id, {"state": store.NOT_INSTALLED, "removed_at": time.time()}
        )
    return removed


def rapidocr_package_model_dir() -> Path | None:
    """Where RapidOCR stores weights by default (inside the installed package)."""
    import importlib.util

    spec = importlib.util.find_spec("rapidocr")
    if spec is None or not spec.origin:
        return None
    return Path(spec.origin).parent / "models"


def rapidocr_known_checksums() -> dict[str, str]:
    """file name -> SHA-256 from RapidOCR's own default_models.yaml (trust anchor)."""
    import yaml  # type: ignore[import-untyped]  # PyYAML ships with the Docling stack

    pkg = rapidocr_package_model_dir()
    if pkg is None:
        return {}
    data = yaml.safe_load(
        (pkg.parent / "default_models.yaml").read_text(encoding="utf-8")
    )
    out: dict[str, str] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            url, sha = node.get("model_dir"), node.get("SHA256")
            if isinstance(url, str) and isinstance(sha, str):
                out[url.rstrip("/").rsplit("/", 1)[-1]] = sha.lower()
            for v in node.values():
                walk(v)

    walk(data)
    return out


def import_rapidocr_weights() -> dict[str, str]:
    """Copy already-downloaded RapidOCR weights from the venv into the persistent dir.

    Only files whose SHA-256 matches RapidOCR's own list are copied (atomic
    replace); nothing is downloaded here. RapidOCR re-checks the same hashes
    when it loads them.
    """
    src = rapidocr_package_model_dir()
    if src is None or not src.is_dir():
        return {}
    known = rapidocr_known_checksums()
    dest = paths.rapidocr_dir()
    dest.mkdir(parents=True, exist_ok=True)
    result: dict[str, str] = {}
    for f in sorted(src.iterdir()):
        if not f.is_file() or f.is_symlink() or f.name not in known:
            continue
        target = dest / f.name
        if target.is_file() and store.sha256_file(target) == known[f.name]:
            result[f.name] = "existing"
            continue
        if store.sha256_file(f) != known[f.name]:
            result[f.name] = "skipped (checksum mismatch)"
            continue
        tmp = dest / f".{f.name}.import.tmp"
        shutil.copyfile(f, tmp)
        os.replace(tmp, target)
        result[f.name] = "imported"
    return result
