"""Admin CLI for the OCR Engine Manager (server-side; never reachable from the web).

    python -m open_notebook.ocr.cli status [--json]
    python -m open_notebook.ocr.cli install-model <engine>
    python -m open_notebook.ocr.cli remove-model <engine>
    python -m open_notebook.ocr.cli runtime install <tesseract|easyocr> [--offline]
    python -m open_notebook.ocr.cli runtime ensure [--offline]   # used by the entrypoint
    python -m open_notebook.ocr.cli bundle create --engines E [E...] --out DIR [--models-only]
    python -m open_notebook.ocr.cli bundle verify DIR
    python -m open_notebook.ocr.cli bundle install DIR

In Docker:  docker compose exec open_notebook uv run --no-sync python -m open_notebook.ocr.cli status

Runtime installs need OS privileges (apt/dpkg for Tesseract) or write access to
the venv (EasyOCR) — which is why they live here and in the container
entrypoint, not behind an HTTP endpoint (DECISIONS D-06). All subprocesses use
argument lists (no shell) with fixed, pinned package specs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from open_notebook.ocr import catalog, installer, paths, runtime, store


def _log(msg: str) -> None:
    print(f"[ocr] {msg}", flush=True)


def _is_true(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _active_engine() -> str | None:
    """Active engine from the database, or None if the DB is unreachable."""

    async def _get() -> str | None:
        from open_notebook.domain.content_settings import ContentSettings

        settings = await ContentSettings.get_instance()
        return getattr(settings, "docling_ocr_engine", None) or catalog.DEFAULT_ENGINE

    try:
        return asyncio.run(asyncio.wait_for(_get(), timeout=20))
    except Exception as e:
        _log(f"could not read the active engine from the database: {e}")
        return None


# --- runtime installs -----------------------------------------------------------


def _wheels_dir() -> Path:
    return paths.packages_dir() / "wheels"


def _debs_dir() -> Path:
    return paths.packages_dir() / "debs"


TRUSTED_DIGEST_ENV = {
    "wheels": "OCR_TRUSTED_WHEELS_SHA256",
    "debs": "OCR_TRUSTED_DEBS_SHA256",
}


def staged_digest(directory: Path) -> str:
    return store.sha256_file(directory / "checksums.sha256")


def _verify_staged(directory: Path) -> list[Path]:
    """Files staged by ``bundle install``, verified before anything is installed.

    The checksum list lives on the data volume, so on its own it only proves
    the files were not corrupted. The trust anchor is the digest of that list,
    which the operator pins in the service environment (compose file, outside
    the volume) — printed by ``bundle install``. Without a matching pin nothing
    staged is installed (a writable volume must not lead to root package installs).
    """
    sums = directory / "checksums.sha256"
    if not sums.is_file():
        raise RuntimeError(f"{sums} missing; stage packages with 'bundle install'")
    env_name = TRUSTED_DIGEST_ENV.get(directory.name)
    pinned = os.environ.get(env_name or "", "").strip().lower()
    actual = staged_digest(directory)
    if not env_name or pinned != actual:
        raise RuntimeError(
            f"Staged packages in {directory} are not trusted: set {env_name}={actual} "
            "in the service environment (value printed by 'bundle install')."
        )
    files: list[Path] = []
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest_hex, _, name = line.partition("  ")
        p = paths.safe_child(directory, name)
        if p.is_symlink() or not p.is_file() or store.sha256_file(p) != digest_hex:
            raise RuntimeError(f"staged package failed verification: {name}")
        files.append(p)
    return files


def _check_pinned_easyocr_wheel(files: list[Path]) -> None:
    """The easyocr wheel itself must match the hash pinned in the catalog (in Git)."""
    name = f"easyocr-{catalog.EASYOCR_VERSION}-py3-none-any.whl"
    match = [p for p in files if p.name == name]
    if not match or store.sha256_file(match[0]) != catalog.EASYOCR_WHEEL_SHA256:
        raise RuntimeError(f"{name} missing or not matching the pinned sha256")


def install_easyocr_runtime(offline: bool) -> bool:
    if runtime.module_available("easyocr"):
        _log("EasyOCR runtime already installed.")
        return True
    spec = f"{catalog.EASYOCR_PACKAGE}=={catalog.EASYOCR_VERSION}"
    uv = shutil.which("uv")
    wheels = _wheels_dir()
    local = wheels.is_dir() and any(wheels.glob("easyocr-*.whl"))
    if uv:
        cmd = [uv, "pip", "install", "--python", sys.executable]
    else:
        cmd = [sys.executable, "-m", "pip", "install"]
    if local:
        try:
            staged = _verify_staged(wheels)
            _check_pinned_easyocr_wheel(staged)
        except RuntimeError as e:
            _log(f"EasyOCR runtime NOT installed: {e}")
            return False
        cmd += ["--no-index", "--find-links", str(wheels)] + (
            ["--offline"] if uv else []
        )
    elif offline:
        _log(
            f"OFFLINE and no staged wheels in {wheels}: cannot install EasyOCR (missing: {spec})."
        )
        return False
    cmd.append(spec)
    _log("Installing EasyOCR runtime: " + " ".join(cmd))
    if subprocess.run(cmd, check=False, shell=False).returncode != 0:
        _log("EasyOCR runtime install FAILED.")
        return False
    runtime.write_runtime_marker("easyocr", catalog.EASYOCR_VERSION)
    _log("EasyOCR runtime installed.")
    return True


def install_tesseract_runtime(offline: bool) -> bool:
    if runtime.tesseract_cmd():
        _log("Tesseract runtime already installed.")
        return True
    if hasattr(os, "geteuid") and os.geteuid() != 0:
        _log(
            "Installing Tesseract needs root (apt/dpkg). Use the Docker build arg OCR_INSTALL_TESSERACT=true or run as root."
        )
        return False
    debs_dir = _debs_dir()
    if debs_dir.is_dir() and any(debs_dir.glob("*.deb")):
        try:
            debs = [p for p in _verify_staged(debs_dir) if p.suffix == ".deb"]
        except RuntimeError as e:
            _log(f"Tesseract runtime NOT installed: {e}")
            return False
        cmd = ["dpkg", "-i", *map(str, debs)]
    elif offline:
        _log(
            f"OFFLINE and no staged .deb packages in {debs_dir}: cannot install {catalog.TESSERACT_APT_PACKAGE}."
        )
        return False
    else:
        env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
        if (
            subprocess.run(
                ["apt-get", "update"], check=False, shell=False, env=env
            ).returncode
            != 0
        ):
            _log("apt-get update failed.")
            return False
        cmd = [
            "apt-get",
            "install",
            "-y",
            "--no-install-recommends",
            catalog.TESSERACT_APT_PACKAGE,
        ]
    _log(
        "Installing Tesseract runtime: "
        + " ".join(cmd[:4])
        + (" ..." if len(cmd) > 4 else "")
    )
    ok = (
        subprocess.run(
            cmd,
            check=False,
            shell=False,
            env=dict(os.environ, DEBIAN_FRONTEND="noninteractive"),
        ).returncode
        == 0
    )
    if not ok or not runtime.tesseract_cmd():
        _log("Tesseract runtime install FAILED.")
        return False
    runtime.write_runtime_marker("tesseract", runtime.probe_tesseract().version)
    _log("Tesseract runtime installed.")
    return True


def runtime_ensure(offline: bool) -> int:
    """Restore enabled runtimes after a container (re)create. Never fails boot."""
    offline = offline or paths.offline_mode()
    paths.ensure_dirs()
    runtime.ensure_tessdata_layout()
    if _is_true("OPEN_NOTEBOOK_ENABLE_OCR_TESSERACT"):
        install_tesseract_runtime(offline)
    if _is_true("OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR"):
        if not runtime.docling_available():
            _log("EasyOCR needs Docling (OPEN_NOTEBOOK_ENABLE_DOCLING=true); skipping.")
        else:
            install_easyocr_runtime(offline)
    return 0


# --- commands ----------------------------------------------------------------------


def cmd_status(args: argparse.Namespace) -> int:
    from open_notebook.ocr.status import engine_status

    active = _active_engine() if not args.no_db else None
    rows = [engine_status(e, active) for e in catalog.ENGINE_IDS]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        return 0
    print(
        f"models dir: {paths.models_dir()}   offline: {paths.offline_mode()}   active: {active or '?'}"
    )
    for r in rows:
        print(
            f"{r['id']:<15} state={r['state']:<16} runtime={r['runtime']['status']:<16} "
            f"model={r['model']['status']:<14} {'(active)' if r['active'] and active else ''}"
        )
        if r.get("error"):
            print(f"{'':<15} error: {r['error']}")
    return 0


def cmd_install_model(args: argparse.Namespace) -> int:
    def progress(state: dict[str, Any]) -> None:
        p = state.get("progress") or {}
        if p.get("bytes_total"):
            print(
                f"\r[ocr] {p.get('bytes_done', 0) // 1048576}/{p['bytes_total'] // 1048576} MB",
                end="",
                flush=True,
            )

    try:
        result = installer.install_models(args.engine, progress)
    except (installer.InstallError, store.LockBusy) as e:
        print()
        store.update_state(args.engine, state=store.FAILED, error=str(e))
        _log(f"FAILED: {e}")
        return 1
    print()
    _log(
        f"{args.engine}: {result['state']} sources={result.get('sources')} smoke={result.get('smoke')}"
    )
    return 0


def cmd_remove_model(args: argparse.Namespace) -> int:
    active = _active_engine()
    if active is None:
        _log(
            "Refusing to remove a model while the active engine is unknown (database unreachable)."
        )
        return 1
    try:
        removed = installer.delete_models(args.engine, active)
    except (installer.InstallError, store.LockBusy) as e:
        _log(f"Refused: {e}")
        return 1
    _log(f"removed: {removed}")
    return 0


def cmd_runtime(args: argparse.Namespace) -> int:
    if args.action == "ensure":
        return runtime_ensure(args.offline)
    if args.kind == "easyocr":
        return 0 if install_easyocr_runtime(args.offline or paths.offline_mode()) else 1
    return 0 if install_tesseract_runtime(args.offline or paths.offline_mode()) else 1


def cmd_bundle(args: argparse.Namespace) -> int:
    from open_notebook.ocr import bundle

    if args.action == "create":
        r = bundle.create(
            args.engines, Path(args.out), with_runtime=not args.models_only
        )
        _log(f"bundle written to {r['out']} ({r['files']} files)")
        _log(f"bundle digest: {r['digest']}")
        return 0
    if args.action == "verify":
        r = bundle.verify(Path(args.dir))
        for w in r.get("warnings", []):
            _log(f"warning: {w}")
        for p in r["problems"]:
            _log(f"problem: {p}")
        _log(f"digest: {r.get('digest')}  ->  {'OK' if r['ok'] else 'FAILED'}")
        return 0 if r["ok"] else 1
    r = bundle.install(Path(args.dir))
    _log(f"installed: {r['models']} staged: {r['staged']} digest: {r['digest']}")
    for kind, env_name in TRUSTED_DIGEST_ENV.items():
        d = paths.packages_dir() / kind
        if (d / "checksums.sha256").is_file():
            _log(f"Pin in the service environment: {env_name}={staged_digest(d)}")
    _log(
        "Next: 'runtime ensure --offline' (or restart the container with the OPEN_NOTEBOOK_ENABLE_OCR_* flags)."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m open_notebook.ocr.cli",
        description="OCR Engine Manager admin CLI",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("status", help="show engine status")
    s.add_argument("--json", action="store_true")
    s.add_argument(
        "--no-db",
        action="store_true",
        help="do not query the database for the active engine",
    )
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("install-model", help="download/verify an engine's model files")
    s.add_argument(
        "engine", choices=[e for e in catalog.ENGINE_IDS if catalog.ENGINES[e].files]
    )
    s.set_defaults(func=cmd_install_model)

    s = sub.add_parser(
        "remove-model", help="remove an engine's model files (refused if active)"
    )
    s.add_argument(
        "engine", choices=[e for e in catalog.ENGINE_IDS if catalog.ENGINES[e].files]
    )
    s.set_defaults(func=cmd_remove_model)

    s = sub.add_parser("runtime", help="install or restore runtimes")
    rs = s.add_subparsers(dest="action", required=True)
    ri = rs.add_parser("install")
    ri.add_argument("kind", choices=["tesseract", "easyocr"])
    ri.add_argument("--offline", action="store_true")
    re_ = rs.add_parser("ensure")
    re_.add_argument("--offline", action="store_true")
    s.set_defaults(func=cmd_runtime)

    s = sub.add_parser("bundle", help="offline bundles")
    bs = s.add_subparsers(dest="action", required=True)
    bc = bs.add_parser("create")
    bc.add_argument(
        "--engines",
        nargs="+",
        required=True,
        choices=[e for e in catalog.ENGINE_IDS if catalog.ENGINES[e].files],
    )
    bc.add_argument("--out", required=True)
    bc.add_argument(
        "--models-only", action="store_true", help="skip wheels/.deb packages"
    )
    bv = bs.add_parser("verify")
    bv.add_argument("dir")
    bi = bs.add_parser("install")
    bi.add_argument("dir")
    s.set_defaults(func=cmd_bundle)

    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
