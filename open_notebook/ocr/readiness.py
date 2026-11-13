"""Online preparation and offline readiness (docs/ocr/OCR_ONLINE_PREPARATION.md).

Operating model: the server is ONLINE to install / update / prepare, then
OFFLINE for document processing. Readiness is never inferred from files on disk
alone — it comes from running the real production pipeline:

* ``online`` check     — full Docling pipeline (Heron + TableFormer + selected
                         OCR) on the built-in sample; downloads what is missing
                         (Docling HF models, RapidOCR weights) while online.
* ``local_only`` check — same pipeline in a child process whose HTTP(S) proxies
                         point to a closed local port: any download attempt
                         fails, so success proves every component is local.
* ``offline`` check    — same, run while the Internet is really unreachable
                         (detected): the strongest evidence.

``offline_ready`` = the latest local_only/offline check passed and nothing that
it depends on changed since (fingerprint). OCR-only success (engine smoke test)
is reported separately and never implies offline readiness.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from open_notebook.ocr import catalog, runtime, store

PROBE_URLS = (
    "https://huggingface.co",
    "https://pypi.org",
    "https://github.com",
    "https://www.modelscope.cn",
)
DEAD_PROXY = "http://127.0.0.1:9"
# huggingface_hub re-raises ProxyError / SSLError instead of falling back to the
# local cache (``_snapshot_download.py``: "Actually raise for those subclasses of
# ConnectionError"), so a dead proxy alone makes Heron/TableFormer fail even
# when they are fully cached. An unplugged server gets a plain ConnectionError
# (DNS / connect failure) and DOES fall back to the cache. Pointing the Hub
# endpoint at the same closed local port (exempt from the proxy via NO_PROXY)
# reproduces exactly that: connection refused -> cache, or LocalEntryNotFound
# when the model is not cached (Phase 8B, found on a real host).
DEAD_ENDPOINT = DEAD_PROXY
CHECK_TIMEOUT = int(os.environ.get("OCR_READINESS_TIMEOUT", "1800"))

# States (MASTER_PLAN Phase 8A B4)
RUNTIME_MISSING = "runtime_missing"
MODEL_MISSING = "model_missing"
MODEL_INCOMPLETE = "model_incomplete"
INCOMPATIBLE = "incompatible"
PIPELINE_NOT_VERIFIED = "pipeline_not_verified"
OFFLINE_READY = "offline_ready"
NOT_OFFLINE_READY = "not_offline_ready"


def internet_reachable(timeout: float = 5.0) -> bool:
    """True if any well-known public host answers (any HTTP status counts)."""
    for url in PROBE_URLS:
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=timeout):
                return True
        except urllib.error.HTTPError:
            return True  # an HTTP answer means the network path works
        except Exception:
            continue
    return False


# Hugging Face repos the production pipeline loads (Layout Heron, TableFormer).
DOCLING_HF_REPOS = (
    "docling-project/docling-layout-heron",
    "docling-project/docling-models",
)


def _docling_cache_signature() -> dict[str, list[list[Any]]]:
    """Files of the Docling repos in the HF cache: [snapshot/rel_path, size].

    Part of the fingerprint so that a verdict goes stale when the cache is
    cleared, pruned (snapshot symlinks left dangling: size -1) or replaced —
    presence alone never makes an engine ready. Sizes come from ``stat`` (no
    hashing), so this stays cheap enough for every status request.
    """
    try:
        from huggingface_hub import constants

        cache = Path(constants.HF_HUB_CACHE)
    except Exception:
        return {}
    out: dict[str, list[list[Any]]] = {}
    for repo in DOCLING_HF_REPOS:
        snaps = cache / f"models--{repo.replace('/', '--')}" / "snapshots"
        files: list[list[Any]] = []
        try:
            for f in snaps.rglob("*"):
                if f.is_symlink() or f.is_file():
                    try:
                        size = f.stat().st_size  # follows the snapshot symlink
                    except OSError:
                        size = -1  # dangling: blob pruned
                    files.append([f.relative_to(snaps).as_posix(), size])
        except OSError:
            pass
        out[repo] = sorted(files)
    return out


def _rapidocr_weights_signature(persistent: bool) -> list[list[Any]]:
    """RapidOCR weight files present where RapidOCR will look for them.

    Default mode keeps them inside the package (container layer: lost on
    recreate); persistent mode keeps them under the OCR data volume.
    """
    from open_notebook.ocr import installer, paths

    try:
        known = installer.rapidocr_known_checksums()
        where = (
            paths.rapidocr_dir()
            if persistent
            else installer.rapidocr_package_model_dir()
        )
        if where is None or not where.is_dir():
            return []
        return sorted(
            [f.name, f.stat().st_size]
            for f in where.iterdir()
            if f.is_file() and f.name in known
        )
    except Exception:
        return []


def fingerprint(engine_id: str) -> dict[str, Any]:
    """Everything a readiness verdict depends on; a change makes it stale."""
    from open_notebook.ocr.options import rapidocr_force_cpu, rapidocr_persistent

    spec = catalog.get_engine(engine_id)
    fp: dict[str, Any] = {
        "docling": runtime._version("docling"),
        "content_core": runtime._version("content-core"),
        "models": {f.rel_path: f.sha256 for f in spec.files},
        "docling_cache": _docling_cache_signature(),
    }
    if spec.runtime == "builtin":
        persistent = rapidocr_persistent()
        fp.update(
            rapidocr=runtime._version("rapidocr"),
            backend=runtime.rapidocr_backend(),
            persistent=persistent,
            force_cpu=rapidocr_force_cpu(),
            rapidocr_weights=_rapidocr_weights_signature(persistent),
        )
    elif spec.runtime == "tesseract":
        fp["tesseract"] = runtime.probe_tesseract().version
    else:
        fp["easyocr"] = runtime._version("easyocr")
    fp["quality"] = quality_config(engine_id)
    return fp


def quality_config(engine_id: str) -> dict[str, Any]:
    """The OCR quality settings a verdict was produced with (D-25 / D-26).

    Part of the fingerprint: changing one of them (or installing / removing
    the orientation data) makes an earlier verdict stale, so "offline ready"
    always describes the configuration that will really run.
    """
    from open_notebook.ocr import options, pdf_prep, tesseract_gate

    spec = catalog.get_engine(engine_id)
    orientation = pdf_prep.orientation_status(runtime.tesseract_cmd())
    cfg: dict[str, Any] = {
        "page_orientation": {
            k: orientation[k] for k in ("enabled", "available", "min_confidence")
        }
    }
    if spec.runtime == "tesseract":
        cfg["osd_gate"] = options.tesseract_osd_gate_enabled()
        cfg["osd_gate_min_confidence"] = tesseract_gate.min_confidence()
    elif spec.runtime == "easyocr":
        cfg["confidence_threshold"] = options.easyocr_confidence_threshold()
    return cfg


def _child_env(local_only: bool) -> dict[str, str]:
    env = dict(os.environ)
    if local_only:
        for var in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            env[var] = DEAD_PROXY
        env["NO_PROXY"] = env["no_proxy"] = "localhost,127.0.0.1,::1"
        env["HF_ENDPOINT"] = DEAD_ENDPOINT  # refused, not ProxyError (see above)
        env.pop("HF_HUB_OFFLINE", None)  # behave like an unplugged server
    return env


def run_pipeline_check(engine_id: str, mode: str) -> dict[str, Any]:
    """Run the production pipeline on the sample in a child process."""
    catalog.get_engine(engine_id)
    started = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "open_notebook.ocr.readiness", "_child", engine_id],
            # The network is blocked for every check except "online": an
            # "offline" verdict must not depend on the Internet probe being right.
            env=_child_env(mode != "online"),
            capture_output=True,
            timeout=CHECK_TIMEOUT,
            check=False,
            shell=False,
            cwd=str(Path(__file__).resolve().parents[2]),
        )
        lines = (proc.stdout or b"").decode("utf-8", "replace").strip().splitlines()
        result = json.loads(lines[-1]) if lines else {"success": False}
        if not lines:
            result["error"] = (proc.stderr or b"").decode("utf-8", "replace")[-800:]
    except subprocess.TimeoutExpired:
        result = {"success": False, "error": f"check timed out after {CHECK_TIMEOUT}s"}
    except (OSError, ValueError) as e:
        result = {"success": False, "error": f"{type(e).__name__}: {e}"}
    result.update(
        mode=mode, checked_at=time.time(), seconds=round(time.time() - started, 1)
    )
    result["pipeline_ok"] = bool(
        result.get("success")
        and result.get("layout_model") == "layout_heron"
        and result.get("table_model") == "docling_tableformer"
        and result.get("table_mode") == "accurate"
    )
    result["fingerprint"] = fingerprint(engine_id)
    return result


def record(engine_id: str, check: dict[str, Any]) -> None:
    st = store.read_state(engine_id)
    checks = dict(st.get("readiness") or {})
    checks[check["mode"]] = {k: v for k, v in check.items() if k != "text"}
    store.update_state(engine_id, readiness=checks)


def readiness_status(
    engine_id: str, rt_status: str | None = None, model_status: str | None = None
) -> dict[str, Any]:
    """Computed readiness of one engine (cheap: reads manifests + probes)."""
    spec = catalog.get_engine(engine_id)
    rt_status = rt_status or runtime.probe_runtime(engine_id).status
    model_status = model_status or store.model_status(engine_id).status
    checks: dict[str, Any] = store.read_state(engine_id).get("readiness") or {}
    current = fingerprint(engine_id)

    def fresh(c: dict[str, Any] | None) -> bool:
        return c is not None and bool(c) and c.get("fingerprint") == current

    online, local, offline = (
        checks.get("online"),
        checks.get("local_only"),
        checks.get("offline"),
    )
    # The most recent fresh no-network check decides (a newer failure wins).
    fresh_no_network = [c for c in (offline, local) if c is not None and fresh(c)]
    best = max(fresh_no_network, key=lambda c: c.get("checked_at", 0), default=None)
    info = {
        "engine": engine_id,
        "ocr_ok": any(
            bool(c and c.get("success")) for c in (online, local, offline) if fresh(c)
        ),
        "pipeline_ok": any(
            bool(c and c.get("pipeline_ok"))
            for c in (online, local, offline)
            if fresh(c)
        ),
        "local_only_verified": bool(
            fresh(local) and local and local.get("pipeline_ok")
        ),
        "offline_verified": bool(
            fresh(offline) and offline and offline.get("pipeline_ok")
        ),
        "stale": any(c and not fresh(c) for c in (online, local, offline)),
        "last_check": max(
            (c for c in (online, local, offline) if c),
            key=lambda c: c.get("checked_at", 0),
            default=None,
        ),
    }
    if rt_status in (runtime.RUNTIME_MISSING,):
        state = RUNTIME_MISSING
    elif rt_status == runtime.RUNTIME_INCOMPATIBLE:
        state = INCOMPATIBLE
    elif spec.files and model_status == "not_installed":
        state = MODEL_MISSING
    elif spec.files and model_status in ("partial", "corrupted"):
        state = MODEL_INCOMPLETE
    elif best and best.get("pipeline_ok"):
        state = OFFLINE_READY
    elif best:
        state = NOT_OFFLINE_READY
    else:
        state = PIPELINE_NOT_VERIFIED
    info["state"] = state
    return info


def prepare(engine_id: str, allow_download: bool = True, log=print) -> dict[str, Any]:
    """Online preparation of one engine, then the readiness checks.

    Never installs system/Python runtimes (that is the admin CLI / image).
    """
    from open_notebook.ocr import compat, installer
    from open_notebook.ocr.options import rapidocr_persistent

    spec = catalog.get_engine(engine_id)
    out: dict[str, Any] = {"engine": engine_id, "steps": {}}
    steps = out["steps"]
    rt = runtime.probe_runtime(engine_id)
    steps["runtime"] = rt.status
    if not rt.ready:
        out["error"] = f"runtime {rt.status}: {rt.detail or ''}".strip()
        return out
    problems = compat.problems(engine_id)
    steps["dependencies"] = "verified" if not problems else problems
    if problems and not compat.override_enabled():
        out["error"] = "dependencies differ from the verified set: " + "; ".join(
            problems
        )
        return out
    online = internet_reachable()
    steps["internet"] = online
    if spec.files and not store.model_status(engine_id).installed:
        if not (online and allow_download):
            missing = [
                f.rel_path
                for f in store.model_status(engine_id).files
                if not f.verified
            ]
            out["error"] = (
                f"model files missing ({', '.join(missing)}); connect to the Internet and run prepare again"
            )
            return out
        log(f"[{engine_id}] downloading model files")
        steps["model_install"] = installer.install_models(engine_id).get("sources")
    steps["model"] = store.model_status(engine_id).status
    if spec.runtime == "builtin" and rapidocr_persistent():
        steps["rapidocr_import"] = installer.import_rapidocr_weights()
    if online and allow_download:
        log(
            f"[{engine_id}] online pipeline check (downloads Heron/TableFormer/RapidOCR weights if missing)"
        )
        check = run_pipeline_check(engine_id, "online")
        record(engine_id, check)
        steps["online_check"] = check.get("pipeline_ok")
        if spec.runtime == "builtin" and rapidocr_persistent():
            steps["rapidocr_import_after"] = installer.import_rapidocr_weights()
    mode = "offline" if not online else "local_only"
    log(f"[{engine_id}] {mode} pipeline check (no network allowed)")
    check = run_pipeline_check(engine_id, mode)
    record(engine_id, check)
    steps[f"{mode}_check"] = check.get("pipeline_ok")
    if not check.get("pipeline_ok"):
        out["error"] = check.get("error") or "pipeline check failed"
    out["readiness"] = readiness_status(engine_id)
    return out


def check(engine_id: str) -> dict[str, Any]:
    """Readiness check only (never downloads): offline if no Internet, else local_only."""
    mode = "local_only" if internet_reachable() else "offline"
    result = run_pipeline_check(engine_id, mode)
    record(engine_id, result)
    return {
        "engine": engine_id,
        "check": {k: v for k, v in result.items() if k != "text"},
        "readiness": readiness_status(engine_id),
    }


def explain_offline_failure(exc: BaseException) -> str | None:
    """User-facing message when processing failed because a model is not local.

    Recognises model-download failures (Hugging Face, ModelScope/RapidOCR) —
    not ordinary URL fetch errors — so the job fails fast with guidance instead
    of retrying a download that cannot succeed.
    """
    seen = 0
    e: BaseException | None = exc
    while e is not None and seen < 8:
        name = type(e).__name__
        text = str(e)
        if name in (
            "LocalEntryNotFoundError",
            "OfflineModeIsEnabled",
            "DownloadFileException",
        ) or any(
            host in text for host in ("huggingface.co", "modelscope.cn", "hf.co/")
        ):
            return (
                "An OCR/Docling model needed for this document is not available locally and "
                "cannot be downloaded now (no Internet). Connect to the Internet and run "
                "'Prepare models' in Settings → OCR Engine Manager (or "
                "`python -m open_notebook.ocr.cli prepare`), then retry the source."
            )
        e = e.__cause__ or e.__context__
        seen += 1
    return None


def _child(engine_id: str) -> int:
    """Child-process entry: run the production pipeline test, print JSON."""
    from open_notebook.ocr.tester import run_engine_test

    result = run_engine_test(engine_id)
    result.pop("text", None)
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "_child":
        sys.exit(_child(sys.argv[2]))
    sys.exit(2)
