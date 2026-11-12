"""Offline bundles for air-gapped ChatBot5400 servers (MASTER_PLAN Phase 4).

Layout (one bundle may hold one or several engines)::

    ocr-offline-bundle/
    ├── manifest.json        engines, versions, python/platform/OS, licenses
    ├── models/<rel_path>    model files (verified against the CATALOG sha256)
    ├── wheels/*.whl         Python packages missing from the target image
    ├── system-packages/*.deb Debian packages for tesseract-ocr
    ├── checksums.sha256     sha256 of every file above (sha256sum format)
    └── README.md

Trust model: model files are accepted only if they match the SHA-256 pinned in
``catalog.py`` (in Git) — a bundle cannot smuggle different weights. Wheels and
.debs are verified against ``checksums.sha256``; the operator compares the
bundle digest printed by ``create`` with the one printed by ``verify`` over a
trusted channel. Nothing is uploaded or executed from the web UI.

Bundles are created INSIDE a container built from the same image (on a machine
with Internet), so the wheel/.deb sets are exactly what the target lacks.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from open_notebook.ocr import catalog, installer, paths, store

FORMAT_VERSION = 1


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _os_release() -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                data[k] = v.strip('"')
    except OSError:
        pass
    return {k: data.get(k, "") for k in ("ID", "VERSION_ID", "VERSION_CODENAME")}


def environment_fingerprint() -> dict[str, Any]:
    import importlib.metadata as md

    def ver(d: str) -> str | None:
        try:
            return md.version(d)
        except md.PackageNotFoundError:
            return None

    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "machine": platform.machine(),
        "os": _os_release(),
        "docling": ver("docling"),
        "content_core": ver("content-core"),
        "torch": ver("torch"),
    }


def _run(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, shell=False, **kw)


# --- Python wheels -------------------------------------------------------------


def easyocr_missing_requirements() -> list[str]:
    """Exact ``name==version`` set uv would add to THIS venv for easyocr."""
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv is required to compute the wheel set")
    spec = f"{catalog.EASYOCR_PACKAGE}=={catalog.EASYOCR_VERSION}"
    proc = subprocess.run(
        [uv, "pip", "install", "--python", sys.executable, "--dry-run", spec],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    out = proc.stdout + proc.stderr
    reqs = re.findall(r"^\s*\+\s+([A-Za-z0-9_.\-]+)==([^\s]+)", out, re.MULTILINE)
    if proc.returncode != 0:
        raise RuntimeError(out[-2000:])
    return [f"{n}=={v}" for n, v in reqs]


def _download_wheels(reqs: list[str], dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if not reqs:
        return
    base = [sys.executable, "-m", "pip"]
    if (
        subprocess.run(
            base + ["--version"], capture_output=True, check=False
        ).returncode
        != 0
    ):
        uvx = shutil.which("uvx")
        if not uvx:
            raise RuntimeError("Neither pip nor uvx is available to download wheels")
        base = [uvx, "pip"]
    _run(
        base + ["download", "--no-deps", "--only-binary=:all:", "-d", str(dest), *reqs]
    )


# --- Debian packages -------------------------------------------------------------


def tesseract_missing_debs() -> list[str]:
    """Packages apt would install for tesseract-ocr on THIS system."""
    proc = subprocess.run(
        [
            "apt-get",
            "install",
            "--simulate",
            "--no-install-recommends",
            catalog.TESSERACT_APT_PACKAGE,
        ],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            proc.stderr[-2000:]
            or "apt-get --simulate failed (run apt-get update first)"
        )
    return [
        f"{n}={v}"
        for n, v in re.findall(r"^Inst (\S+) \((\S+)", proc.stdout, re.MULTILINE)
    ]


def _download_debs(pkgs: list[str], dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if pkgs:
        _run(["apt-get", "download", *pkgs], cwd=dest)


# --- Create / verify / install ------------------------------------------------------


def create(engines: list[str], out: Path, with_runtime: bool = True) -> dict[str, Any]:
    for e in engines:
        catalog.get_engine(e)
    out.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    runtime_items: dict[str, list[str]] = {}

    # Model files: reuse verified local copies, else download (pinned + checked).
    for e in engines:
        for mf in catalog.get_engine(e).files:
            dest = paths.safe_child(out / "models", mf.rel_path)
            if dest.is_file() and _sha256(dest) == mf.sha256:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            local = paths.models_dir() / mf.rel_path
            if store.check_file(mf).verified:
                shutil.copyfile(local, dest)
            else:
                installer._install_file(e, mf, lambda n: None)
                shutil.copyfile(local, dest)
    if with_runtime:
        specs = {catalog.get_engine(e).runtime for e in engines}
        if "easyocr" in specs:
            reqs = easyocr_missing_requirements()
            _download_wheels(reqs, out / "wheels")
            runtime_items["wheels"] = reqs
        if "tesseract" in specs and shutil.which("apt-get"):
            debs = tesseract_missing_debs()
            _download_debs(debs, out / "system-packages")
            runtime_items["system-packages"] = debs

    for kind in ("models", "wheels", "system-packages"):
        base = out / kind
        if base.is_dir():
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    files.append(
                        {
                            "path": p.relative_to(out).as_posix(),
                            "sha256": _sha256(p),
                            "size": p.stat().st_size,
                            "kind": kind,
                        }
                    )
    manifest = {
        "format_version": FORMAT_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "engines": engines,
        "engine_details": {
            e: {
                "display_name": catalog.get_engine(e).display_name,
                "model": f"{catalog.get_engine(e).model_name} {catalog.get_engine(e).model_version}",
                "license": catalog.get_engine(e).license,
                "source": catalog.get_engine(e).source_url,
            }
            for e in engines
        },
        "runtime": runtime_items,
        "environment": environment_fingerprint(),
        "files": files,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [f"{f['sha256']}  {f['path']}" for f in files] + [
        f"{_sha256(out / 'manifest.json')}  manifest.json"
    ]
    (out / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "README.md").write_text(
        _README.format(engines=", ".join(engines), digest=digest(out)), encoding="utf-8"
    )
    return {"out": str(out), "digest": digest(out), "files": len(files)}


def digest(bundle: Path) -> str:
    return _sha256(bundle / "checksums.sha256")


def verify(bundle: Path) -> dict[str, Any]:
    """Integrity + compatibility check. Never touches the network."""
    problems: list[str] = []
    sums = bundle / "checksums.sha256"
    if not sums.is_file():
        return {"ok": False, "problems": ["checksums.sha256 missing"]}
    root = bundle.resolve()
    listed: set[str] = set()
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest_hex, _, rel = line.partition("  ")
        try:
            p = paths.safe_child(root, rel)
        except ValueError:
            problems.append(f"unsafe path in checksums: {rel!r}")
            continue
        listed.add(rel)
        if p.is_symlink() or not p.is_file():
            problems.append(f"missing or not a regular file: {rel}")
        elif _sha256(p) != digest_hex:
            problems.append(f"checksum mismatch: {rel}")
    for p in root.rglob("*"):
        if p.is_file() and p.name not in ("checksums.sha256", "README.md"):
            rel = p.relative_to(root).as_posix()
            if rel not in listed:
                problems.append(f"unlisted file: {rel}")
    manifest: dict[str, Any] = {}
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        problems.append("manifest.json unreadable")
    env = environment_fingerprint()
    want = manifest.get("environment", {})
    warnings: list[str] = []
    if manifest.get("runtime"):
        for key in ("python", "machine"):
            if want.get(key) and want.get(key) != env.get(key):
                problems.append(
                    f"incompatible {key}: bundle {want.get(key)} vs here {env.get(key)}"
                )
        if want.get("os", {}).get("VERSION_CODENAME") != env["os"].get(
            "VERSION_CODENAME"
        ):
            warnings.append(f"OS differs: bundle {want.get('os')} vs here {env['os']}")
    # Model files must match the catalog pinned in Git (trust anchor).
    for e in manifest.get("engines", []):
        try:
            spec = catalog.get_engine(e)
        except ValueError:
            problems.append(f"unknown engine in manifest: {e}")
            continue
        for mf in spec.files:
            p = root / "models" / mf.rel_path
            if not p.is_file():
                problems.append(f"{e}: model file missing: {mf.rel_path}")
            elif _sha256(p) != mf.sha256:
                problems.append(
                    f"{e}: model file does not match the pinned checksum: {mf.rel_path}"
                )
    wheel = root / "wheels" / f"easyocr-{catalog.EASYOCR_VERSION}-py3-none-any.whl"
    if wheel.is_file() and _sha256(wheel) != catalog.EASYOCR_WHEEL_SHA256:
        problems.append("wheels: easyocr wheel does not match the pinned checksum")
    return {
        "ok": not problems,
        "problems": problems,
        "warnings": warnings,
        "digest": digest(bundle) if sums.is_file() else None,
        "manifest": manifest,
    }


def install(bundle: Path, install_runtime: bool = True) -> dict[str, Any]:
    """Install models (+ stage runtime packages) from a verified bundle, offline."""
    result = verify(bundle)
    if not result["ok"]:
        raise RuntimeError(
            "Bundle verification failed: " + "; ".join(result["problems"])
        )
    manifest = result["manifest"]
    paths.ensure_dirs()
    # Stage runtime packages on the data volume: the entrypoint reinstalls from
    # here after every container recreate, without Internet.
    staged: dict[str, int] = {}
    for kind, target in (
        ("wheels", paths.packages_dir() / "wheels"),
        ("system-packages", paths.packages_dir() / "debs"),
    ):
        src = bundle / kind
        if src.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            n = 0
            for p in src.iterdir():
                if p.is_file() and not p.is_symlink():
                    shutil.copyfile(p, target / p.name)
                    n += 1
            staged[kind] = n
            sums = [
                f"{_sha256(p)}  {p.name}"
                for p in sorted(target.iterdir())
                if p.is_file() and p.name != "checksums.sha256"
            ]
            (target / "checksums.sha256").write_text(
                "\n".join(sums) + "\n", encoding="utf-8"
            )
    # Models: copy into OCR_PACKAGES_DIR/models, then the regular installer
    # verifies against the catalog and moves them in atomically.
    installed: dict[str, Any] = {}
    old = os.environ.get("OCR_OFFLINE")
    os.environ["OCR_OFFLINE"] = "true"  # CLI process only: never fall back to network
    try:
        for e in manifest.get("engines", []):
            spec = catalog.get_engine(e)
            for mf in spec.files:
                dest = paths.safe_child(paths.packages_dir() / "models", mf.rel_path)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(bundle / "models" / mf.rel_path, dest)
            installed[e] = installer.install_models(e).get("sources")
        # The verified weights now live in models/; drop the staging copies so
        # the volume never holds two copies of a model.
        staged_models = paths.packages_dir() / "models"
        if staged_models.is_dir() and not staged_models.is_symlink():
            shutil.rmtree(staged_models)
    finally:
        if old is None:
            os.environ.pop("OCR_OFFLINE", None)
        else:
            os.environ["OCR_OFFLINE"] = old
    return {"models": installed, "staged": staged, "digest": result["digest"]}


_README = """# ChatBot5400 OCR offline bundle

Engines: {engines}

Bundle digest (sha256 of checksums.sha256): `{digest}`
Compare this digest over a trusted channel before installing.

## Install on the air-gapped server

```bash
# copy this folder into the data volume, e.g. ./notebook_data/ocr-bundle
docker compose exec open_notebook uv run --no-sync python -m open_notebook.ocr.cli bundle verify /app/data/ocr-bundle
docker compose exec open_notebook uv run --no-sync python -m open_notebook.ocr.cli bundle install /app/data/ocr-bundle
docker compose exec open_notebook uv run --no-sync python -m open_notebook.ocr.cli runtime ensure --offline
docker compose restart open_notebook
```

Model files are checked against the SHA-256 values pinned in ChatBot5400's source
(open_notebook/ocr/catalog.py). Wheels / .deb packages are staged under
/app/data/ocr/packages so they are reinstalled offline after container recreation.

Licenses: tessdata_fast / tessdata_best — Apache-2.0; EasyOCR and its models —
Apache-2.0; Tesseract — Apache-2.0. See manifest.json for versions.
"""
