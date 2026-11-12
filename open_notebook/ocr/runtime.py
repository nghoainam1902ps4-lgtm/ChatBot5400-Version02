"""Runtime probes for the OCR engines (executables, Python packages, Docling API).

These answer "can this process actually run engine X?" — distinct from "are
its model weights on disk?" (see ``models.py``). The UI must never call an
engine ready when only one of the two is true (MASTER_PLAN Phase 2.3).

Probes are cheap and side-effect free, except ``docling_info()``, which runs
ONE short-lived subprocess (importing Docling costs ~9 s and pulls torch, which
the API process must not keep resident) and caches the answer per Docling
version.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from open_notebook.ocr import catalog, paths

# Process start; a runtime installed after this needs a restart (requires_restart).
PROCESS_STARTED_AT = time.time()

RUNTIME_READY = "ready"
RUNTIME_MISSING = "missing"
RUNTIME_INCOMPATIBLE = "incompatible"
RUNTIME_REQUIRES_RESTART = "requires_restart"


@dataclass
class RuntimeStatus:
    kind: str
    status: str  # ready | missing | incompatible | requires_restart
    version: str | None = None
    detail: str | None = None
    # How an operator installs it (never executed by the web app).
    install_env_var: str | None = None
    install_cli: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.status == RUNTIME_READY

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _version(dist: str) -> str | None:
    try:
        return importlib.metadata.version(dist)
    except importlib.metadata.PackageNotFoundError:
        return None


def module_available(name: str) -> bool:
    importlib.invalidate_caches()
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def docling_available() -> bool:
    from open_notebook.utils.runtime_capabilities import docling_available as _probe

    return _probe()


# --- Runtime-install markers (written by the admin CLI / entrypoint) --------


def _marker_path(kind: str) -> Path:
    return paths.manifests_dir() / f"runtime-{kind}.json"


def write_runtime_marker(kind: str, version: str | None) -> None:
    paths.ensure_dirs()
    data = {"kind": kind, "version": version, "installed_at": time.time()}
    tmp = _marker_path(kind).with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, _marker_path(kind))


def _installed_after_start(kind: str) -> bool:
    try:
        data = json.loads(_marker_path(kind).read_text(encoding="utf-8"))
        return float(data.get("installed_at", 0)) > PROCESS_STARTED_AT
    except (OSError, ValueError, TypeError):
        return False


# --- Tesseract ----------------------------------------------------------------

_TESS_VERSION_RE = re.compile(r"tesseract\s+v?(\d+)\.(\d+)(?:\.(\d+))?", re.IGNORECASE)


def tesseract_cmd() -> str | None:
    return shutil.which(os.environ.get("OCR_TESSERACT_CMD", "tesseract"))


def ensure_tessdata_prefix() -> tuple[bool, str]:
    """Pin TESSDATA_PREFIX to our tessdata dir for this process (DECISIONS D-04).

    The value is identical for every job, so setting it is race-free. An
    operator-provided different value is respected and reported, not overridden.
    """
    ours = str(paths.tessdata_dir())
    current = os.environ.get("TESSDATA_PREFIX")
    if not current:
        os.environ["TESSDATA_PREFIX"] = ours
        return True, ours
    try:
        same = Path(current).resolve() == Path(ours).resolve()
    except OSError:
        same = False
    if same:
        return True, current
    return False, (
        f"TESSDATA_PREFIX={current} differs from the OCR models directory {ours}. "
        f"Unset it or set it to {ours}."
    )


# Tesseract resolves output configs (``tesseract img stdout tsv``, which Docling
# uses) from ``$TESSDATA_PREFIX/configs/``. Our dedicated tessdata directory
# therefore needs the standard one-line ``tsv`` config shipped by Tesseract.
_TSV_CONFIG = "tessedit_create_tsv 1\n"


def ensure_tessdata_layout() -> Path:
    cfg = paths.tessdata_dir() / "configs" / "tsv"
    if not cfg.is_file() or cfg.read_text(encoding="utf-8") != _TSV_CONFIG:
        cfg.parent.mkdir(parents=True, exist_ok=True)
        tmp = cfg.with_suffix(".tmp")
        tmp.write_text(_TSV_CONFIG, encoding="utf-8")
        os.replace(tmp, cfg)
    return cfg


def tesseract_env() -> dict[str, str]:
    """Environment for subprocesses we launch ourselves (never mutates os.environ)."""
    env = dict(os.environ)
    env["TESSDATA_PREFIX"] = str(paths.tessdata_dir())
    return env


def probe_tesseract() -> RuntimeStatus:
    st = RuntimeStatus(
        kind="tesseract",
        status=RUNTIME_MISSING,
        install_env_var="OPEN_NOTEBOOK_ENABLE_OCR_TESSERACT",
        install_cli="python -m open_notebook.ocr.cli runtime install tesseract",
    )
    cmd = tesseract_cmd()
    if not cmd:
        st.detail = (
            "Tesseract executable not found. Build the image with "
            "OCR_INSTALL_TESSERACT=true or set OPEN_NOTEBOOK_ENABLE_OCR_TESSERACT=true "
            "and restart the container."
        )
        return st
    try:
        proc = subprocess.run(
            [cmd, "--version"],
            capture_output=True,
            timeout=15,
            check=False,
            shell=False,
        )
        out = (proc.stdout or b"").decode("utf-8", "replace") + (
            proc.stderr or b""
        ).decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError) as e:
        st.status = RUNTIME_INCOMPATIBLE
        st.detail = f"Could not run tesseract --version: {e}"
        return st
    m = _TESS_VERSION_RE.search(out)
    if not m:
        st.status = RUNTIME_INCOMPATIBLE
        st.detail = "Unrecognised tesseract --version output."
        return st
    st.version = ".".join(g for g in m.groups() if g)
    if int(m.group(1)) < catalog.TESSERACT_MIN_MAJOR:
        st.status = RUNTIME_INCOMPATIBLE
        st.detail = f"Tesseract {st.version} is too old; LSTM models need >= 4."
        return st
    ok, detail = ensure_tessdata_prefix()
    if not ok:
        st.status = RUNTIME_INCOMPATIBLE
        st.detail = detail
        return st
    st.extra["executable"] = cmd
    st.extra["tessdata_prefix"] = str(paths.tessdata_dir())
    st.status = (
        RUNTIME_REQUIRES_RESTART
        if _installed_after_start("tesseract")
        else RUNTIME_READY
    )
    if st.status == RUNTIME_REQUIRES_RESTART:
        st.detail = (
            "Tesseract was installed after this process started; restart the worker."
        )
    return st


# --- EasyOCR --------------------------------------------------------------------


def probe_easyocr() -> RuntimeStatus:
    st = RuntimeStatus(
        kind="easyocr",
        status=RUNTIME_MISSING,
        install_env_var="OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR",
        install_cli="python -m open_notebook.ocr.cli runtime install easyocr",
    )
    if not module_available("easyocr"):
        st.detail = (
            f"Python package easyocr=={catalog.EASYOCR_VERSION} is not installed. Set "
            "OPEN_NOTEBOOK_ENABLE_OCR_EASYOCR=true and restart the container, or run the "
            "admin CLI."
        )
        return st
    st.version = _version("easyocr")
    if not st.version or not st.version.startswith("1.7."):
        st.status = RUNTIME_INCOMPATIBLE
        st.detail = (
            f"easyocr {st.version} is not the tested 1.7.x line "
            f"(pinned {catalog.EASYOCR_VERSION})."
        )
        return st
    st.status = (
        RUNTIME_REQUIRES_RESTART if _installed_after_start("easyocr") else RUNTIME_READY
    )
    if st.status == RUNTIME_REQUIRES_RESTART:
        st.detail = (
            "EasyOCR was installed after this process started; restart the worker."
        )
    return st


def probe_rapidocr() -> RuntimeStatus:
    st = RuntimeStatus(kind="builtin", status=RUNTIME_MISSING)
    if not docling_available():
        st.detail = "Docling is not installed (set OPEN_NOTEBOOK_ENABLE_DOCLING=true)."
        st.install_env_var = "OPEN_NOTEBOOK_ENABLE_DOCLING"
        return st
    if not module_available("rapidocr"):
        st.detail = "rapidocr package is missing from the Docling install."
        return st
    st.version = _version("rapidocr")
    st.extra["backend"] = rapidocr_backend()
    st.status = RUNTIME_READY
    return st


def probe_runtime(engine_id: str) -> RuntimeStatus:
    spec = catalog.get_engine(engine_id)
    if spec.runtime == "builtin":
        return probe_rapidocr()
    if not docling_available():
        return RuntimeStatus(
            kind=spec.runtime,
            status=RUNTIME_MISSING,
            detail="Docling is not installed (set OPEN_NOTEBOOK_ENABLE_DOCLING=true).",
            install_env_var="OPEN_NOTEBOOK_ENABLE_DOCLING",
        )
    if spec.runtime == "tesseract":
        return probe_tesseract()
    return probe_easyocr()


# --- RapidOCR / Docling Auto equivalence (DECISIONS D-03) ------------------------


def rapidocr_backend() -> str:
    """The RapidOCR backend Docling's Auto mode selects in this environment."""
    return "onnxruntime" if module_available("onnxruntime") else "torch"


def auto_resolves_to_rapidocr() -> bool:
    """True when Docling's OcrAutoOptions would pick RapidOCR here.

    Mirrors docling/models/stages/ocr/auto_ocr_model.py (2.129): ocrmac on macOS,
    nemotron on Linux, then RapidOCR+onnxruntime, then EasyOCR, then RapidOCR+torch.
    """
    if sys.platform == "darwin" and module_available("ocrmac"):
        return False
    if sys.platform.startswith("linux") and module_available("nemotron_ocr"):
        return False
    if module_available("onnxruntime"):
        return True
    return not module_available("easyocr")


# --- Lock-derived constraints for runtime installs (DECISIONS D-14) ---------------


def runtime_constraints() -> Path | None:
    """Constraints file pinning runtime installs to the versions in uv.lock.

    Docker: exported at image build (OPEN_NOTEBOOK_RUNTIME_CONSTRAINTS).
    Dev checkout: exported on demand from the repository's uv.lock.
    None when neither is available (callers must not install unpinned).
    """
    env = os.environ.get("OPEN_NOTEBOOK_RUNTIME_CONSTRAINTS", "").strip()
    if env and Path(env).is_file():
        return Path(env)
    lock = Path(_PROJECT_ROOT) / "uv.lock"
    uv = shutil.which("uv")
    if not lock.is_file() or not uv:
        return None
    out = paths.downloads_dir() / "runtime-constraints.txt"
    try:
        if out.is_file() and out.stat().st_mtime >= lock.stat().st_mtime:
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [
                uv,
                "export",
                "--frozen",
                "--no-dev",
                "--extra",
                "docling",
                "--extra",
                "ocr-easyocr",
                "--no-hashes",
                "--no-emit-project",
                "--no-header",
                "--no-annotate",
                "-o",
                str(out),
            ],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            timeout=120,
            check=False,
            shell=False,
        )
        return out if proc.returncode == 0 and out.is_file() else None
    except (OSError, subprocess.SubprocessError):
        return None


# --- Docling details (subprocess, cached) ---------------------------------------

_DOCLING_PROBE = r"""
import json, sys
out = {"ok": True, "missing": []}
try:
    import docling.datamodel.pipeline_options as po
except Exception as e:
    print(json.dumps({"ok": False, "error": repr(e)})); sys.exit(0)
need = {
    "RapidOcrOptions": ["backend", "lang", "mode"],
    "TesseractCliOcrOptions": ["lang", "path", "tesseract_cmd", "mode"],
    "EasyOcrOptions": ["lang", "use_gpu", "model_storage_directory", "download_enabled", "mode"],
    "PdfPipelineOptions": ["ocr_options", "accelerator_options", "do_ocr", "layout_options", "table_structure_options"],
}
for cls, fields in need.items():
    c = getattr(po, cls, None)
    if c is None:
        out["missing"].append(cls); continue
    for f in fields:
        if f not in c.model_fields:
            out["missing"].append(f"{cls}.{f}")
if not hasattr(po, "OcrMode"):
    out["missing"].append("OcrMode")
try:
    from docling.datamodel.accelerator_options import AcceleratorOptions  # noqa
except Exception:
    out["missing"].append("AcceleratorOptions")
try:
    lo = po.PdfPipelineOptions().layout_options
    spec = getattr(lo, "model_spec", None)
    out["layout_model"] = getattr(spec, "name", None) or type(lo).__name__
except Exception as e:
    out["layout_model"] = None
try:
    to = po.PdfPipelineOptions().table_structure_options
    mode = getattr(to, "mode", None)
    out["table_model"] = f"{getattr(to, 'kind', type(to).__name__)}" + (f" ({getattr(mode, 'value', mode)})" if mode is not None else "")
except Exception:
    out["table_model"] = None
# Docling internals the OCR layer relies on (open_notebook/ocr/compat.py).
try:
    sys.path.insert(0, sys.argv[1])
    from open_notebook.ocr import compat
    out["fingerprint_problems"] = compat.check_fingerprints(compat.DOCLING_FINGERPRINTS)
except Exception as e:
    out["fingerprint_problems"] = ["fingerprint probe failed: " + repr(e)]
out["ok"] = not out["missing"]
print(json.dumps(out))
"""

_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])


def _compat_key() -> str:
    """Invalidate the cached probe when the verified fingerprints change."""
    import hashlib

    from open_notebook.ocr import compat

    blob = json.dumps(compat.DOCLING_FINGERPRINTS, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def docling_info(force: bool = False) -> dict[str, Any]:
    """Docling version, API compatibility and default Layout/Table model names."""
    version = _version("docling")
    info: dict[str, Any] = {
        "available": docling_available(),
        "version": version,
        "api_compatible": None,
        "missing": [],
        "layout_model": None,
        "table_model": None,
        "fingerprint_problems": [],
    }
    if not info["available"] or not version:
        return info
    cache = paths.manifests_dir() / "docling-info.json"
    if not force:
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            if (
                cached.get("version") == version
                and cached.get("compat_key") == _compat_key()
            ):
                return cached
        except (OSError, ValueError):
            pass
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _DOCLING_PROBE, _PROJECT_ROOT],
            capture_output=True,
            timeout=180,
            check=False,
            shell=False,
        )
        lines = (proc.stdout or b"").decode("utf-8", "replace").strip().splitlines()
        data = json.loads(lines[-1]) if lines else {"ok": False}
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        logger.warning(f"Docling probe failed: {e}")
        return info
    info["api_compatible"] = bool(data.get("ok"))
    info["missing"] = data.get("missing", [])
    info["layout_model"] = data.get("layout_model")
    info["table_model"] = data.get("table_model")
    info["fingerprint_problems"] = data.get("fingerprint_problems", [])
    info["compat_key"] = _compat_key()
    try:
        paths.ensure_dirs()
        tmp = cache.with_suffix(".tmp")
        tmp.write_text(json.dumps(info), encoding="utf-8")
        os.replace(tmp, cache)
    except OSError:
        pass
    return info
