"""Admin CLI for the OCR Engine Manager (server-side; never reachable from the web).

    python -m open_notebook.ocr.cli status [--json]
    python -m open_notebook.ocr.cli install-model <engine>
    python -m open_notebook.ocr.cli remove-model <engine>
    python -m open_notebook.ocr.cli runtime install <tesseract|easyocr> [--offline]
    python -m open_notebook.ocr.cli runtime ensure [--offline]   # used by the entrypoint
    python -m open_notebook.ocr.cli bundle create --engines E [E...] --out DIR [--models-only]
    python -m open_notebook.ocr.cli bundle verify DIR
    python -m open_notebook.ocr.cli bundle install DIR
    python -m open_notebook.ocr.cli custom import --file FILE --version v1 [--notes TEXT]
    python -m open_notebook.ocr.cli custom list | status [--json]
    python -m open_notebook.ocr.cli custom verify --version v1
    python -m open_notebook.ocr.cli custom activate --version v1
    python -m open_notebook.ocr.cli custom rollback
    python -m open_notebook.ocr.cli custom remove --version v1   # inactive versions only

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

from open_notebook.ocr import catalog, compat, installer, paths, runtime, store


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
        if not uv:
            _log(
                f"OFFLINE, no staged wheels in {wheels} and no uv cache: cannot install EasyOCR ({spec})."
            )
            return False
        # No staged bundle: try the persistent uv cache only (wheels downloaded
        # on an earlier online boot). Fails cleanly if they are not cached.
        cmd += ["--offline"]
        _log("OFFLINE: installing EasyOCR from the local uv cache only.")
    constraints = runtime.runtime_constraints()
    if constraints is not None:
        cmd += ["-c", str(constraints)]
    elif not compat.override_enabled():
        _log(
            "No lock-derived constraints found (OPEN_NOTEBOOK_RUNTIME_CONSTRAINTS / uv.lock): "
            "refusing to install EasyOCR with unverified dependency versions. "
            f"Set {compat.OVERRIDE_ENV}=true to override."
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


def _docling_patch_state() -> dict[str, dict[str, Any]]:
    """Whether the controlled Docling patches can run here (D8-10, Phase 12D9):
    the E0-07 TSV text patch (Tesseract engines) and the D8-03 / D8-02 text
    preservation patches (every Docling conversion). ``ready`` = they apply at
    conversion time; otherwise the conversion refuses to run (never unpatched)."""
    from open_notebook.ocr import docling_patches as P

    def one(problems: Any, installed: bool) -> dict[str, Any]:
        try:
            found = list(problems())
        except Exception as e:  # noqa: BLE001 - reported, status never fails
            found = [f"{type(e).__name__}: {e}"]
        return {
            "installed": installed,
            "ready": installed and not found,
            "problems": found,
        }

    docling = P._installed("docling") is not None
    return {
        # P.problems() verifies both Tesseract targets: the TSV parse (E0-07) and
        # the OCR loop that never drops a failed region (E2-04, Phase 12D9)
        "tsv": {
            "patch": P.PATCH_ID,
            "patches": [P.PATCH_ID, P.REGION_PATCH_ID],
            **one(P.problems, docling),
        },
        "text": {
            "patches": [P.HYPHEN_PATCH_ID, P.FOOTNOTE_PATCH_ID],
            **one(P.text_problems, P._docling_present()),
        },
    }


def _patch_line(name: str, state: dict[str, Any]) -> str:
    if not state["installed"]:
        return f"{name}: not applicable (Docling is not installed)"
    if state["ready"]:
        return f"{name}: ready (applied at conversion time)"
    return f"{name}: NOT AVAILABLE - conversions refuse to run: " + "; ".join(
        state["problems"]
    )


def cmd_status(args: argparse.Namespace) -> int:
    from open_notebook.ocr.options import tesseract_gate_state
    from open_notebook.ocr.status import engine_status

    active = _active_engine() if not args.no_db else None
    rows = [engine_status(e, active) for e in catalog.ALL_ENGINE_IDS]
    # E1-05 (Phase 12D7): whether the orientation gate really runs (D-25).
    gate = tesseract_gate_state()
    patches = _docling_patch_state()
    if args.json:
        # D8-ORI-02 / D8-10 (Phase 12D9): the same states for automation, on the
        # rows they concern (the list shape of earlier versions is kept).
        gate_state = {
            k: gate.get(k)
            for k in (
                "enabled",
                "active",
                "reason",
                "min_confidence",
                "crlf",
                "executable",
            )
        }
        for r in rows:
            r["docling_text_preservation"] = patches["text"]
            if catalog.get_engine(r["id"]).runtime == "tesseract":
                r["orientation_gate"] = gate_state
                r["docling_tsv_patch"] = patches["tsv"]
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
    print(
        _patch_line(
            "docling Tesseract patches (E0-07 TSV text, E2-04 failed OCR region)",
            patches["tsv"],
        )
    )
    print(
        _patch_line(
            "docling text preservation (D8-03 hyphens, D8-02 table / picture footnotes)",
            patches["text"],
        )
    )
    if gate["active"]:  # last line (scripts of 12D7 read it there)
        print(f"orientation gate: active (min confidence {gate['min_confidence']})")
    else:
        print(f"orientation gate: NOT ACTIVE - {gate['reason']}")
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


def cmd_prepare(args: argparse.Namespace) -> int:
    """Online preparation of the selected engines (docs/ocr/OCR_ONLINE_PREPARATION.md)."""
    from open_notebook.ocr import readiness

    failed = 0
    for engine_id in args.engines:
        spec = catalog.get_engine(engine_id)
        if args.install_runtime and spec.runtime in ("tesseract", "easyocr"):
            ok = (
                install_tesseract_runtime
                if spec.runtime == "tesseract"
                else install_easyocr_runtime
            )(False)
            if not ok:
                _log(f"[{engine_id}] runtime install failed")
        result = readiness.prepare(
            engine_id, allow_download=not args.no_download, log=_log
        )
        state = (result.get("readiness") or {}).get("state", "error")
        _log(f"[{engine_id}] {state} steps={json.dumps(result['steps'], default=str)}")
        if result.get("error"):
            _log(f"[{engine_id}] ERROR: {result['error']}")
        if state != readiness.OFFLINE_READY:
            failed += 1
    return 1 if failed else 0


def cmd_readiness(args: argparse.Namespace) -> int:
    from open_notebook.ocr import readiness

    if args.engines:
        engines = args.engines
    else:
        # A deployment that never imported a custom model must still be able to
        # get exit code 0 here: a custom engine counts once it has a version.
        from open_notebook.ocr import custom_models

        engines = [
            *catalog.ENGINE_IDS,
            *(c for c in catalog.CUSTOM_ENGINE_IDS if custom_models.active_version(c)),
        ]
    rows = []
    for engine_id in engines:
        if args.check:
            readiness.check(engine_id)
        rows.append(readiness.readiness_status(engine_id))
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    else:
        for r in rows:
            last = r.get("last_check") or {}
            print(
                f"{r['engine']:<15} {r['state']:<22} ocr={r['ocr_ok']!s:<5} pipeline={r['pipeline_ok']!s:<5} "
                f"local_only={r['local_only_verified']!s:<5} offline={r['offline_verified']!s:<5} "
                f"stale={r['stale']!s:<5} last={last.get('mode', '-')}"
            )
    return 0 if all(r["state"] == readiness.OFFLINE_READY for r in rows) else 1


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


# --- custom (fine-tuned, versioned) models ------------------------------------------


def _fmt_time(ts: Any) -> str:
    import time as _time

    try:
        return _time.strftime("%Y-%m-%d %H:%M:%S", _time.localtime(float(ts)))
    except (TypeError, ValueError):
        return "-"


def _print_versions(info: dict[str, Any]) -> None:
    if not info["versions"]:
        print("  (no version imported)")
        return
    for v in info["versions"]:
        flag = "ACTIVE" if v["active"] else ("previous" if v["previous"] else "")
        smoke = v.get("smoke") or {}
        verification = (v.get("verification") or {}).get("status", "?")
        print(
            f"  {v['version']:<12} {flag:<8} size={v['size']:>10} sha256={v['sha256']}"
        )
        print(
            f"  {'':<12} imported={_fmt_time(v['imported_at'])} "
            f"verification={verification} file={'ok' if v['file_ok'] else 'CHANGED'} "
            f"smoke={'ok' if smoke.get('ok') else 'FAILED'}"
            f"{'' if smoke.get('cer') is None else ' (CER ' + format(smoke['cer'], '.1%') + ')'} "
            f"readiness={v['readiness_state']}"
        )
        if not v["file_ok"]:
            print(f"  {'':<12} PROBLEM: {v['file_detail']}")
        if v.get("duplicate_of"):
            print(f"  {'':<12} same content as: {', '.join(v['duplicate_of'])}")
        if v.get("notes"):
            print(f"  {'':<12} notes: {v['notes']}")


def cmd_custom(args: argparse.Namespace) -> int:
    from open_notebook.ocr import custom_models as cm

    engine_id = args.engine
    spec = catalog.get_engine(engine_id)
    try:
        if args.action == "import":
            _log(f"importing {args.file} as {spec.display_name} version {args.version}")
            manifest = cm.import_model(engine_id, args.file, args.version, args.notes)
            _log(
                f"stored {manifest['rel_path']} ({manifest['size']} bytes, "
                f"sha256 {manifest['sha256']})"
            )
            params = (manifest.get("traineddata") or {}).get("config_params") or []
            _log(
                "embedded Tesseract parameters (checked against the allow-list): "
                + (", ".join(f"{p['name']}={p['value']}" for p in params) or "none")
            )
            _log(f"tesseract smoke test: {manifest['smoke']['detail']}")
            if manifest.get("duplicate_of"):
                _log(
                    "WARNING: identical content to version(s) "
                    + ", ".join(manifest["duplicate_of"])
                )
            if args.skip_readiness:
                _log("readiness check skipped (--skip-readiness)")
            elif not runtime.docling_available():
                _log("readiness check skipped: Docling is not installed here")
            else:
                from open_notebook.ocr import readiness

                _log("readiness check (full Docling pipeline, no network)...")
                r = readiness.check(engine_id, custom_version=args.version)
                state = (r.get("readiness") or {}).get("state")
                _log(f"readiness: {state}")
                if (r.get("check") or {}).get("error"):
                    _log(f"readiness error: {r['check']['error']}")
            active = cm.active_version(engine_id)
            _log(
                f"version {args.version} is imported but NOT active "
                f"(active version: {active or 'none'}). Activate it with: "
                f"custom activate --version {args.version}"
            )
            return 0
        if args.action in ("list", "status"):
            info = cm.status(engine_id)
            if args.json:
                print(json.dumps(info, ensure_ascii=False, indent=2, default=str))
                return 0
            print(f"{spec.display_name} ({engine_id})")
            if args.action == "status":
                from open_notebook.ocr.status import engine_status

                engine = None if args.no_db else _active_engine()
                st = engine_status(engine_id, engine)
                print(f"  OCR engine in use     : {engine or '? (database not read)'}")
                print(
                    f"  engine state          : {st['state']} (runtime "
                    f"{st['runtime']['status']} {st['runtime'].get('version') or ''}, "
                    f"model {st['model']['status']})"
                )
                print(f"  active version        : {info['active_version'] or 'none'}")
                print(f"  previous version      : {info['previous_version'] or 'none'}")
                print(f"  activated at          : {_fmt_time(info['activated_at'])}")
                print(f"  offline readiness     : {st['readiness'].get('state')}")
                print(
                    f"  languages             : {st['options'].get('lang')} "
                    f"({info['english_env']}={'true' if info['with_english'] else 'false'})"
                )
                print(f"  models directory      : {info['models_dir']}")
                print(f"  manifests directory   : {info['manifests_dir']}")
                if st.get("error"):
                    print(f"  error                 : {st['error']}")
                print("  versions:")
            _print_versions(info)
            return 0
        if args.action == "verify":
            versions = (
                [args.version]
                if args.version
                else [m["version"] for m in cm.list_versions(engine_id)]
            )
            if not versions:
                _log("no version imported")
                return 1
            failed = 0
            for version in versions:
                manifest = cm.verify_version(engine_id, version)
                v = manifest["verification"]
                _log(
                    f"{version}: {v['status']}"
                    + (f" — {v['detail']}" if v.get("detail") else "")
                    + f" (sha256 in manifest {manifest['sha256']})"
                )
                failed += v["status"] != cm.VERIFIED
            return 1 if failed else 0
        if args.action == "activate":
            before = cm.active_version(engine_id)
            registry = cm.activate_version(engine_id, args.version)
            _log(
                f"active version: {registry['active_version']} (was {before or 'none'}). "
                "Documents already being processed keep the version they started with."
            )
            _note_readiness(engine_id)
            return 0
        if args.action == "rollback":
            before = cm.active_version(engine_id)
            registry = cm.rollback(engine_id)
            _log(
                f"rolled back: active version {registry['active_version']} (was {before})"
            )
            _note_readiness(engine_id)
            return 0
        if args.action == "remove":
            cm.require_version(engine_id, args.version)
            if not args.force:
                running = _running_ocr_jobs()
                if running is None:
                    _log(
                        "ERROR: could not check whether documents are being processed "
                        "(database unreachable); nothing was removed. Use --force only "
                        "when the application is stopped."
                    )
                    return 1
                if running:
                    _log(
                        f"ERROR: {running} OCR job(s) are running; a running document "
                        "keeps reading the version it started with. Nothing was "
                        "removed — try again when processing has finished."
                    )
                    return 1
            registry = cm.remove_version(engine_id, args.version)
            _log(
                f"removed version {args.version} (active version: "
                f"{registry['active_version'] or 'none'}, rollback target: "
                f"{registry['previous_version'] or 'none'})"
            )
            return 0
    except (cm.CustomModelError, store.LockBusy) as e:
        _log(f"ERROR: {e}")
        return 1
    return 2


_OCR_JOB_COMMANDS = (
    "process_source",
    "ocr_test_engine",
    "ocr_prepare_engine",
    "ocr_check_readiness",
)


def _running_ocr_jobs() -> int | None:
    """Jobs that may be reading a model file right now (None: database unreachable)."""

    async def _count() -> int:
        from open_notebook.database.repository import repo_query

        rows = await repo_query(
            "SELECT count() AS n FROM command WHERE name IN $names "
            "AND status = 'running' GROUP ALL",
            {"names": list(_OCR_JOB_COMMANDS)},
        )
        return int(rows[0].get("n", 0)) if rows else 0

    try:
        return asyncio.run(asyncio.wait_for(_count(), timeout=20))
    except Exception as e:
        _log(f"could not query running jobs: {e}")
        return None


def _note_readiness(engine_id: str) -> None:
    from open_notebook.ocr import readiness

    state = readiness.readiness_status(engine_id).get("state")
    if state != readiness.OFFLINE_READY:
        _log(
            f"offline readiness of the active version: {state}. Run "
            f"'readiness --engines {engine_id} --check' (or 'Check' in Settings)."
        )
    else:
        _log("offline readiness of the active version: offline_ready")


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
        "engine",
        choices=[e for e in catalog.ALL_ENGINE_IDS if catalog.ENGINES[e].files],
    )
    s.set_defaults(func=cmd_install_model)

    s = sub.add_parser(
        "remove-model", help="remove an engine's model files (refused if active)"
    )
    s.add_argument(
        "engine", choices=[e for e in catalog.ENGINE_IDS if catalog.ENGINES[e].files]
    )
    s.set_defaults(func=cmd_remove_model)

    s = sub.add_parser(
        "prepare",
        help="ONLINE: install missing models, warm Docling/RapidOCR weights, verify offline readiness",
    )
    s.add_argument(
        "--engines", nargs="+", required=True, choices=list(catalog.ALL_ENGINE_IDS)
    )
    s.add_argument(
        "--install-runtime",
        action="store_true",
        help="also install a missing Tesseract/EasyOCR runtime (root / venv access)",
    )
    s.add_argument(
        "--no-download", action="store_true", help="never download; only verify"
    )
    s.set_defaults(func=cmd_prepare)

    s = sub.add_parser(
        "readiness",
        help="offline readiness status (add --check to run the local-only check)",
    )
    s.add_argument("--engines", nargs="*", choices=list(catalog.ALL_ENGINE_IDS))
    s.add_argument("--check", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_readiness)

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

    s = sub.add_parser(
        "custom",
        help="custom fine-tuned Tesseract model versions (import, verify, switch)",
        description=(
            "Manage the versions of a custom fine-tuned Tesseract model "
            "(Tesseract Vietnamese Agri). Files are only ever read from a local "
            "path; nothing is downloaded. Importing never activates a version."
        ),
    )
    cs = s.add_subparsers(dest="action", required=True)

    def _engine_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--engine",
            default=catalog.CUSTOM_ENGINE_IDS[0],
            choices=list(catalog.CUSTOM_ENGINE_IDS),
            help="custom engine (default: %(default)s)",
        )

    ci = cs.add_parser(
        "import",
        help="check a .traineddata file and store it as a new, inactive version",
        description=(
            "Stage the file, compute its SHA-256, load it with the real Tesseract, "
            "run a smoke OCR, store it as a new version and run the offline "
            "readiness check. The active version is not changed."
        ),
    )
    ci.add_argument("--file", required=True, help="local path of the .traineddata file")
    ci.add_argument(
        "--version",
        required=True,
        help="new version id, e.g. v2 (letters, digits, - _)",
    )
    ci.add_argument("--notes", default="", help="free text stored in the manifest")
    ci.add_argument(
        "--skip-readiness",
        action="store_true",
        help="do not run the Docling pipeline readiness check after the import",
    )
    _engine_arg(ci)
    for name, text in (
        ("list", "list imported versions"),
        ("status", "engine state, active / previous version and all versions"),
    ):
        cl = cs.add_parser(name, help=text, description=text.capitalize() + ".")
        cl.add_argument("--json", action="store_true")
        if name == "status":
            cl.add_argument(
                "--no-db",
                action="store_true",
                help="do not query the database for the OCR engine in use",
            )
        _engine_arg(cl)
    cv = cs.add_parser(
        "verify",
        help="re-check a version against its manifest (full SHA-256 + Tesseract load)",
        description=(
            "Re-read the model file, compare size and SHA-256 with the import "
            "manifest and load it with Tesseract. Without --version: every version."
        ),
    )
    cv.add_argument("--version")
    _engine_arg(cv)
    ca = cs.add_parser(
        "activate",
        help="make a verified version the one new documents use",
        description=(
            "Verify the version, then make it active. Documents already being "
            "processed keep the version they started with. The previous active "
            "version becomes the rollback target."
        ),
    )
    ca.add_argument("--version", required=True)
    _engine_arg(ca)
    cr = cs.add_parser(
        "rollback",
        help="return to the version that was active before the last switch",
        description="Verify the previous version and make it active again.",
    )
    _engine_arg(cr)
    cx = cs.add_parser(
        "remove",
        help="delete an inactive version (its model file and manifest)",
        description=(
            "Delete a version that is not active. Refused while documents are "
            "being processed. Official models are never touched."
        ),
    )
    cx.add_argument("--version", required=True)
    cx.add_argument(
        "--force",
        action="store_true",
        help="skip the running-document check (only when the application is stopped)",
    )
    _engine_arg(cx)
    s.set_defaults(func=cmd_custom)

    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
