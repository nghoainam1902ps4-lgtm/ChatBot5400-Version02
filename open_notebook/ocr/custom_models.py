"""Versioned custom Tesseract models (docs/ocr/OCR_CUSTOM_MODEL_MANAGER.md).

A custom engine (today only ``tesseract_agri``) runs a locally fine-tuned
``.traineddata`` file that an administrator imports with the admin CLI. Nothing
here ever touches the network, and no checksum of a custom model is hard-coded:
the trust anchor of a version is the manifest written when it was imported.

Layout on the persistent data volume::

    <models>/tesseract/custom/<family>/<version>/<filename>   the model (read-only)
    <manifests>/custom/<family>/versions/<version>.json       one manifest per version
    <manifests>/custom/<family>/registry.json                 active / previous / history

Rules this module enforces:

* a version is immutable: importing never overwrites a version, the official
  models or the active model;
* a file is staged outside TESSDATA_PREFIX, checked (structure, real Tesseract
  load, smoke OCR) and only then moved into place — a rejected file never
  becomes visible to OCR and never affects an earlier version;
* importing never activates; activation and rollback are explicit and verify
  the file against its manifest first;
* each version is its own Tesseract language, so a document that started with
  one version keeps reading that version's file until it finishes, whatever is
  activated meanwhile (the version is frozen in ``OcrSettings`` at job start).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import stat
import struct
import subprocess
import time
from pathlib import Path
from typing import Any

from loguru import logger

from open_notebook.ocr import catalog, metrics, paths, runtime, store

SCHEMA = 1
# Also a valid Tesseract language path segment for Docling (letters, digits,
# "_" and "-" only: no dots, slashes or "+").
# \Z, not $: "$" would also accept a trailing newline.
VERSION_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z")
MIN_SIZE = 4096
# Sanity bound for the import smoke test on the built-in sample: a model that
# loads but cannot read Vietnamese at all is rejected. Not a quality gate.
SMOKE_MAX_CER = 0.30
HISTORY_LIMIT = 50
NOTES_LIMIT = 500

VERIFIED = "verified"
CORRUPTED = "corrupted"
MISSING = "missing"

_SAMPLE = Path(__file__).parent / "assets" / "sample_vi.png"
_SAMPLE_GT = Path(__file__).parent / "assets" / "sample_vi.gt.txt"

# TessdataType (tesseract/src/ccutil/tessdatamanager.h)
_COMPONENTS = (
    "config",
    "unicharset",
    "unicharambigs",
    "inttemp",
    "pffmtable",
    "normproto",
    "punc-dawg",
    "word-dawg",
    "number-dawg",
    "freq-dawg",
    "fixed-length-dawgs",
    "cube-unicharset",
    "cube-word-dawg",
    "shapetable",
    "bigram-dawg",
    "unambig-dawg",
    "params-model",
    "lstm",
    "lstm-punc-dawg",
    "lstm-word-dawg",
    "lstm-number-dawg",
    "lstm-unicharset",
    "lstm-recoder",
    "version",
)
_REQUIRED_LSTM = ("lstm", "lstm-unicharset", "lstm-recoder")

# The "config" component of a traineddata file is a parameter file Tesseract
# applies, unrestricted, every time it loads the model: it can name files to
# write (debug_file) or further models to load (tessedit_load_sublangs). A
# custom model may therefore only carry recognition-tuning switches from this
# list, each with a plain number or boolean as its value. The official
# Vietnamese model sets the first two; the others are the numeric / boolean
# language settings found in official tessdata configs. Nothing here takes a
# path or produces a file.
ALLOWED_CONFIG_PARAMS = frozenset(
    {
        "language_model_ngram_on",
        "classify_misfit_junk_penalty",
        "language_model_ngram_order",
        "language_model_ngram_nonmatch_score",
        "language_model_ngram_scale_factor",
        "language_model_ngram_small_prob",
        "language_model_penalty_non_dict_word",
        "language_model_penalty_non_freq_dict_word",
        "language_model_penalty_punc",
        "language_model_penalty_case",
        "language_model_penalty_script",
        "language_model_penalty_chartype",
        "language_model_penalty_font",
        "language_model_penalty_spacing",
        "language_model_penalty_increment",
        "classify_enable_learning",
        "classify_enable_adaptive_matcher",
        "preserve_interword_spaces",
        "textord_force_make_prop_words",
        "textord_noise_sizelimit",
        "textord_noise_normratio",
        "edges_max_children_per_outline",
        "edges_children_count_limit",
        "chop_enable",
        "use_new_state_cost",
        "segment_segcost_rating",
        "enable_new_segsearch",
        "paragraph_text_based",
        "segment_penalty_dict_nonword",
        "segment_penalty_garbage",
        "stopper_nondict_certainty_base",
        "load_system_dawg",
        "load_freq_dawg",
        "load_punc_dawg",
        "load_number_dawg",
        "load_unambig_dawg",
        "load_bigram_dawg",
        "wordrec_enable_assoc",
        "tosp_table_xht_sp_ratio",
        "tosp_min_sane_kn_sp",
        "lstm_use_matrix",
    }
)
CONFIG_MAX_BYTES = 16 * 1024
# Tesseract reads the parameter file in 4096-byte pieces: the tail of a longer
# line would be read as a line of its own, behind a harmless-looking start.
CONFIG_MAX_LINE = 512
_CONFIG_VALUE_RE = re.compile(
    r"\A(?:[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|[TtFfYyNn]|true|false|yes|no)\Z",
    re.IGNORECASE,
)


class CustomModelError(Exception):
    """A permanent, user-explainable problem with a custom model operation."""


# --- Names and paths ------------------------------------------------------------


def is_custom(engine_id: str) -> bool:
    spec = catalog.ENGINES.get(engine_id)
    return spec is not None and spec.custom is not None


def spec_for(engine_id: str) -> catalog.CustomModelSpec:
    spec = catalog.get_engine(engine_id)
    if spec.custom is None:
        raise CustomModelError(
            f"{spec.display_name} is not a custom engine: it has no model versions."
        )
    return spec.custom


def validate_version(version: Any) -> str:
    if not isinstance(version, str) or not VERSION_RE.match(version):
        raise CustomModelError(
            f"Invalid version id {version!r}: use 1-32 letters, digits, '-' or '_' "
            "(starting with a letter or digit), e.g. v2."
        )
    return version


def rel_path(engine_id: str, version: str) -> str:
    """Path of the model file relative to OCR_MODELS_DIR."""
    spec = spec_for(engine_id)
    return f"tesseract/custom/{spec.family}/{validate_version(version)}/{spec.filename}"


def model_path(engine_id: str, version: str) -> Path:
    """Resolved model path; refuses anything that escapes the models directory."""
    try:
        return paths.safe_child(paths.models_dir(), rel_path(engine_id, version))
    except ValueError as e:
        raise CustomModelError(str(e)) from e


def lang_code(engine_id: str, version: str) -> str:
    """The Tesseract language of one version (relative to TESSDATA_PREFIX)."""
    spec = spec_for(engine_id)
    return f"custom/{spec.family}/{validate_version(version)}/{spec.lang_stem}"


def with_english(engine_id: str) -> bool:
    """Deployment switch: add the official English model as a second language.

    Off by default — measured in Phase 10E (docs/ocr/OCR_AGRI_BENCHMARK.md):
    Vietnamese-only was better on every criterion except percentage values.
    """
    raw = os.environ.get(spec_for(engine_id).english_env, "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def langs(engine_id: str, version: str) -> list[str]:
    out = [lang_code(engine_id, version)]
    if with_english(engine_id):
        out.append(spec_for(engine_id).english_lang)
    return out


def _manifest_root(engine_id: str) -> Path:
    return paths.manifests_dir() / "custom" / spec_for(engine_id).family


def _version_manifest(engine_id: str, version: str) -> Path:
    return _manifest_root(engine_id) / "versions" / f"{validate_version(version)}.json"


def _registry_path(engine_id: str) -> Path:
    return _manifest_root(engine_id) / "registry.json"


def _lock_name(engine_id: str) -> str:
    return f"custom-{spec_for(engine_id).family}"


def _write_json(target: Path, data: dict[str, Any]) -> None:
    """Atomic and durable: a power loss leaves the old file or the new one."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, indent=2))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)


def _read_json(target: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# --- Manifests --------------------------------------------------------------------
#
# Manifests and the registry are plain files on the data volume: they may be
# damaged or edited by hand. Everything read from them is normalised here, so a
# wrong type becomes "unknown" (and the version fails closed) instead of an
# exception in the settings page, the worker or the next import.


def _as_version(value: Any) -> str | None:
    return value if isinstance(value, str) and VERSION_RE.match(value) else None


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def _clean_manifest(data: dict[str, Any]) -> dict[str, Any]:
    out = dict(data)
    for key in ("smoke", "verification"):
        if not isinstance(out.get(key), dict):
            out[key] = None
    for key in ("readiness", "traineddata"):
        if not isinstance(out.get(key), dict):
            out[key] = {}
    for key in ("sha256", "lang", "source_name", "rel_path", "filename"):
        if not isinstance(out.get(key), str):
            out[key] = None
    size = out.get("size")
    out["size"] = size if isinstance(size, int) and not isinstance(size, bool) else None
    out["imported_at"] = _as_number(out.get("imported_at"))
    out["notes"] = out["notes"] if isinstance(out.get("notes"), str) else ""
    duplicates = out.get("duplicate_of")
    out["duplicate_of"] = (
        [d for d in duplicates if _as_version(d)]
        if isinstance(duplicates, list)
        else []
    )
    return out


def _load_manifest(target: Path, version: str) -> dict[str, Any] | None:
    data = _read_json(target)
    if not data or data.get("version") != version:
        return None
    return _clean_manifest(data)


def read_version(engine_id: str, version: str) -> dict[str, Any] | None:
    return _load_manifest(_version_manifest(engine_id, version), version)


def require_version(engine_id: str, version: str) -> dict[str, Any]:
    manifest = read_version(engine_id, version)
    if manifest is None:
        known = ", ".join(v["version"] for v in list_versions(engine_id)) or "none"
        raise CustomModelError(
            f"Unknown version {version!r} (imported versions: {known})."
        )
    return manifest


def list_versions(engine_id: str) -> list[dict[str, Any]]:
    """Every imported version, oldest first."""
    root = _manifest_root(engine_id) / "versions"
    out: list[dict[str, Any]] = []
    try:
        files = sorted(root.glob("*.json"))
    except OSError:
        files = []
    for f in files:
        if not VERSION_RE.match(f.stem):
            continue
        data = _load_manifest(f, f.stem)
        if data is not None:
            out.append(data)
    return sorted(out, key=lambda m: (m.get("imported_at") or 0, m["version"]))


def read_registry(engine_id: str) -> dict[str, Any]:
    data = _read_json(_registry_path(engine_id)) or {}
    history = data.get("history")
    return {
        "active_version": _as_version(data.get("active_version")),
        "previous_version": _as_version(data.get("previous_version")),
        "activated_at": _as_number(data.get("activated_at")),
        "history": [h for h in history if isinstance(h, dict)]
        if isinstance(history, list)
        else [],
    }


def active_version(engine_id: str) -> str | None:
    """The version new documents will use, or None when none is activated."""
    if not is_custom(engine_id):
        return None
    version = read_registry(engine_id)["active_version"]
    if isinstance(version, str) and VERSION_RE.match(version):
        return version
    return None


def _update_version(engine_id: str, version: str, **changes: Any) -> dict[str, Any]:
    manifest = require_version(engine_id, version)
    manifest.update(changes)
    _write_json(_version_manifest(engine_id, version), manifest)
    return manifest


# --- File inspection ---------------------------------------------------------------


def _sha256(path: Path) -> str:
    """Always a full read: verification must not trust a (size, mtime) cache."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_model_config(data: bytes) -> list[dict[str, str]]:
    """The parameters of a traineddata "config" component, or CustomModelError.

    Read the way Tesseract reads it (``#`` comment lines, ``name value``), but
    strictly: an unknown parameter, a value that is not a number or a boolean,
    an over-long line or binary content rejects the model.
    """
    if len(data) > CONFIG_MAX_BYTES:
        raise CustomModelError(
            f"The model's embedded parameter file is {len(data)} bytes; at most "
            f"{CONFIG_MAX_BYTES} are accepted."
        )
    if b"\x00" in data:
        raise CustomModelError("The model's embedded parameter file is not text.")
    params: list[dict[str, str]] = []
    for raw in data.split(b"\n"):
        if len(raw) > CONFIG_MAX_LINE:
            raise CustomModelError(
                "The model's embedded parameter file has a line longer than "
                f"{CONFIG_MAX_LINE} bytes."
            )
        line = raw.decode("latin-1").rstrip("\r")
        if not line.strip() or line[0] == "#":
            continue
        match = re.match(r"([^ \t]*)[ \t]*(.*)\Z", line, re.DOTALL)
        name = match.group(1) if match else ""
        value = (match.group(2) if match else "").strip()
        if name not in ALLOWED_CONFIG_PARAMS:
            shown = (
                name[:60] if re.fullmatch(r"[A-Za-z0-9_]+", name) else "<not a name>"
            )
            raise CustomModelError(
                f"The model sets the Tesseract parameter '{shown}' in its embedded "
                "parameter file. Only recognition-tuning parameters are accepted "
                "(open_notebook/ocr/custom_models.py, ALLOWED_CONFIG_PARAMS); a "
                "model must not control files, output or other models. Re-export "
                "the model with the standard parameter file of its base language."
            )
        if not _CONFIG_VALUE_RE.match(value):
            raise CustomModelError(
                f"The model gives the Tesseract parameter '{name}' a value that is "
                "not a number or a boolean."
            )
        params.append({"name": name, "value": value})
    return params


def inspect_traineddata(path: Path) -> dict[str, Any]:
    """Parse the traineddata directory; raise unless it holds an LSTM model
    whose embedded parameter file is harmless (``parse_model_config``)."""
    size = path.stat().st_size
    with open(path, "rb") as f:
        head = f.read(4 + 8 * 64)
        if len(head) < 12:
            raise CustomModelError("Not a Tesseract traineddata file (too short).")
        (count,) = struct.unpack("<i", head[:4])
        if not 0 < count <= 64 or len(head) < 4 + 8 * count:
            raise CustomModelError(
                "Not a Tesseract traineddata file (unreadable component table)."
            )
        offsets = struct.unpack(f"<{count}q", head[4 : 4 + 8 * count])
        header = 4 + 8 * count
        present = [(i, off) for i, off in enumerate(offsets) if off >= 0]
        if not present:
            raise CustomModelError("The traineddata file contains no component.")
        last = header
        for _i, off in present:
            if off < last or off >= size:
                raise CustomModelError(
                    "The traineddata component table is inconsistent (truncated or "
                    "damaged file)."
                )
            last = off
        components: list[dict[str, Any]] = []
        for n, (i, off) in enumerate(present):
            end = present[n + 1][1] if n + 1 < len(present) else size
            name = _COMPONENTS[i] if i < len(_COMPONENTS) else f"type-{i}"
            components.append({"name": name, "size": end - off})
        names = {c["name"] for c in components}
        missing = [c for c in _REQUIRED_LSTM if c not in names]
        if missing:
            raise CustomModelError(
                "The file has no LSTM model (missing " + ", ".join(missing) + "): a "
                "Tesseract 4+/5 LSTM traineddata file is required."
            )
        version_string = None
        config_params: list[dict[str, str]] = []
        for n, (i, off) in enumerate(present):
            if i < len(_COMPONENTS) and _COMPONENTS[i] == "version":
                f.seek(off)
                version_string = f.read(min(200, size - off)).decode("utf-8", "replace")
            elif i == 0:  # "config": applied by Tesseract on every load
                end = present[n + 1][1] if n + 1 < len(present) else size
                f.seek(off)
                config_params = parse_model_config(
                    f.read(min(end - off, CONFIG_MAX_BYTES + 1))
                )
    return {
        "components": components,
        "version_string": (version_string or "").strip() or None,
        "legacy_engine": "inttemp" in names,
        "config_params": config_params,
    }


def _refuse_symlinks(rel: str) -> None:
    """No directory or file of ``rel`` below the models directory may be a link.

    ``paths.safe_child`` keeps a path inside the models directory; it does not
    stop ``custom/agri/v2 -> ../../best``, which would make an import or a
    removal act on another model's directory.
    """
    node = paths.models_dir()
    for part in Path(rel).parts:
        node = node / part
        if node.is_symlink():
            raise CustomModelError(
                f"{node} is a symbolic link; refusing to use it. Remove the link "
                "and repeat the command."
            )


def _check_source(source: Path, spec: catalog.CustomModelSpec) -> os.stat_result:
    """Step 1 of an import: a plain, plausible, local .traineddata file."""
    try:
        st = os.lstat(source)
    except OSError as e:
        raise CustomModelError(f"Cannot read {source}: {e.strerror or e}") from e
    if stat.S_ISLNK(st.st_mode):
        raise CustomModelError(
            f"{source} is a symbolic link; give the path of the real file."
        )
    if not stat.S_ISREG(st.st_mode):
        raise CustomModelError(f"{source} is not a regular file.")
    if source.suffix != ".traineddata":
        raise CustomModelError(
            f"{source.name} is not a .traineddata file (expected {spec.filename})."
        )
    if st.st_size < MIN_SIZE:
        raise CustomModelError(
            f"{source.name} is only {st.st_size} bytes: not a model file."
        )
    if st.st_size > spec.max_size:
        raise CustomModelError(
            f"{source.name} is larger than the {spec.max_size // (1024 * 1024)} MB limit."
        )
    return st


def _copy_no_follow(source: Path, dest: Path, max_size: int) -> str:
    """Copy ``source`` to ``dest`` without following a symlink; return the SHA-256.

    The file is opened ONCE; type and size are taken from that descriptor and
    the copy stops at ``max_size``, so swapping the path after ``_check_source``
    (for a bigger file, a FIFO, a device) cannot fill the volume or block.
    """
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(source, flags)
    except OSError as e:
        raise CustomModelError(f"Cannot open {source}: {e.strerror or e}") from e
    h = hashlib.sha256()
    copied = 0
    with os.fdopen(fd, "rb") as src, open(dest, "wb") as out:
        st = os.fstat(src.fileno())
        if not stat.S_ISREG(st.st_mode):
            raise CustomModelError(f"{source} is not a regular file.")
        if not MIN_SIZE <= st.st_size <= max_size:
            raise CustomModelError(f"{source.name} changed while it was being read.")
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            copied += len(chunk)
            if copied > max_size:
                raise CustomModelError(
                    f"{source.name} is larger than the "
                    f"{max_size // (1024 * 1024)} MB limit."
                )
            h.update(chunk)
            out.write(chunk)
        out.flush()
        os.fsync(out.fileno())
    return h.hexdigest()


def tesseract_smoke(
    tessdata: Path, lang: str, extra_langs: list[str] | None = None
) -> dict[str, Any]:
    """Load ``lang`` from ``tessdata`` with the real executable and OCR the sample."""
    cmd = runtime.tesseract_cmd()
    if not cmd:
        raise CustomModelError(
            "The Tesseract runtime is not installed, so the model cannot be checked. "
            "Enable OPEN_NOTEBOOK_ENABLE_OCR_TESSERACT (or bake Tesseract into the "
            "image) and run the command inside the application container."
        )
    env = dict(os.environ, TESSDATA_PREFIX=str(tessdata))
    all_langs = [lang, *(extra_langs or [])]
    result: dict[str, Any] = {
        "ok": False,
        "langs": all_langs,
        "checked_at": time.time(),
        "tesseract_version": runtime.probe_tesseract().version,
    }
    try:
        listed = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            [cmd, "--tessdata-dir", str(tessdata), "--list-langs"],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=60,
            env=env,
            check=False,
        )
        available = (listed.stdout or b"").decode("utf-8", "replace").split()
        missing = [name for name in all_langs if name not in available]
        if missing:
            result["detail"] = f"Tesseract does not list {missing} in {tessdata}"
            return result
        proc = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            [
                cmd,
                str(_SAMPLE),
                "stdout",
                "--tessdata-dir",
                str(tessdata),
                "-l",
                "+".join(all_langs),
            ],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=180,
            env=env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as e:
        result["detail"] = f"Could not run Tesseract: {type(e).__name__}: {e}"
        return result
    text = (proc.stdout or b"").decode("utf-8", "replace").strip()
    if proc.returncode != 0 or not text:
        err = (proc.stderr or b"").decode("utf-8", "replace").strip()
        result["detail"] = (
            f"Tesseract could not load the model or read the sample "
            f"(exit {proc.returncode}): {err[-400:] or 'no text recognised'}"
        )
        return result
    cer = round(metrics.cer(_SAMPLE_GT.read_text(encoding="utf-8"), text), 4)
    result.update(chars=len(text), cer=cer)
    if cer > SMOKE_MAX_CER:
        result["detail"] = (
            f"The model loads but misreads the built-in Vietnamese sample "
            f"(CER {cer:.0%}, limit {SMOKE_MAX_CER:.0%})."
        )
        return result
    result["ok"] = True
    result["detail"] = (
        f"recognised {len(text)} characters from the built-in sample (CER {cer:.1%})"
    )
    return result


# --- Verification -------------------------------------------------------------------


def check_version(engine_id: str, version: str, deep: bool = False) -> store.FileCheck:
    """Compare a version's file with its manifest.

    ``deep=False`` may reuse the (path, size, mtime) hash cache — cheap enough
    for status polls. ``deep=True`` always re-reads the whole file.
    """
    rel = rel_path(engine_id, version)
    manifest = read_version(engine_id, version)
    if manifest is None:
        return store.FileCheck(
            rel, False, False, 0, f"version {version} has no manifest"
        )
    try:
        _refuse_symlinks(rel)
    except CustomModelError:
        return store.FileCheck(rel, True, False, 0, "symlinks are not accepted")
    try:
        target = paths.safe_child(paths.models_dir(), rel)
    except ValueError as e:
        return store.FileCheck(rel, True, False, 0, str(e))
    if not target.is_file():
        return store.FileCheck(rel, False, False, 0, "model file is missing")
    size = target.stat().st_size
    if size != manifest.get("size"):
        return store.FileCheck(
            rel, True, False, size, f"size {size} != manifest {manifest.get('size')}"
        )
    digest = _sha256(target) if deep else store.sha256_file(target)
    if digest != manifest.get("sha256"):
        return store.FileCheck(
            rel, True, False, size, "sha256 differs from the import manifest"
        )
    # Also for a version imported by a release that did not look at it yet: the
    # embedded parameter file (a few hundred bytes) must be harmless.
    try:
        inspect_traineddata(target)
    except (CustomModelError, OSError) as e:
        return store.FileCheck(rel, True, False, size, str(e))
    return store.FileCheck(rel, True, True, size)


def english_check(engine_id: str) -> store.FileCheck | None:
    """The official English companion, only when the deployment switched it on."""
    if not with_english(engine_id):
        return None
    spec = spec_for(engine_id)
    pinned = catalog.pinned_file(spec.english_rel_path)
    if pinned is None:  # pragma: no cover - guarded by a unit test on the catalog
        return store.FileCheck(spec.english_rel_path, False, False, 0, "not pinned")
    check = store.check_file(pinned)
    if not check.verified and not check.detail:
        check.detail = (
            f"{spec.english_env}=true needs {spec.english_rel_path}: install "
            "Tesseract Vietnamese Best."
        )
    return check


def file_checks(engine_id: str, version: str | None = None) -> list[store.FileCheck]:
    """The custom part of an engine's model status (active version by default)."""
    spec = spec_for(engine_id)
    version = version or active_version(engine_id)
    if version is None:
        placeholder = f"tesseract/custom/{spec.family}/<no active version>"
        checks = [
            store.FileCheck(placeholder, False, False, 0, "no version is activated")
        ]
    else:
        checks = [check_version(engine_id, version)]
    companion = english_check(engine_id)
    if companion is not None:
        checks.append(companion)
    return checks


def verify_version(engine_id: str, version: str, smoke: bool = True) -> dict[str, Any]:
    """Full re-check of one version (checksum, structure, real Tesseract load)."""
    require_version(engine_id, version)
    with store.file_lock(_lock_name(engine_id), timeout=30):
        check = check_version(engine_id, version, deep=True)
        verification: dict[str, Any] = {
            "status": VERIFIED
            if check.verified
            else (CORRUPTED if check.present else MISSING),
            "checked_at": time.time(),
            "detail": check.detail,
        }
        changes: dict[str, Any] = {"verification": verification}
        if check.verified:
            target = model_path(engine_id, version)
            try:
                inspect_traineddata(target)
            except CustomModelError as e:  # cannot happen for an unchanged file
                verification.update(status=CORRUPTED, detail=str(e))
            else:
                if smoke and runtime.tesseract_cmd():
                    result = tesseract_smoke(
                        paths.tessdata_dir(), lang_code(engine_id, version)
                    )
                    changes["smoke"] = result
                    if not result["ok"]:
                        verification.update(status=CORRUPTED, detail=result["detail"])
        return _update_version(engine_id, version, **changes)


# --- Import ------------------------------------------------------------------------


def import_model(
    engine_id: str, source: Path | str, version: str, notes: str = ""
) -> dict[str, Any]:
    """Import ``source`` as a new, inactive version. Never overwrites anything."""
    spec = spec_for(engine_id)
    validate_version(version)
    if "://" in str(source) or "\x00" in str(source):
        raise CustomModelError(
            "Only a local file path is accepted (custom models are never downloaded)."
        )
    source = Path(source).expanduser()
    if not source.is_absolute():
        source = Path.cwd() / source
    notes = " ".join(str(notes or "").split())[:NOTES_LIMIT]
    _check_source(source, spec)  # 1. the file itself
    if not runtime.tesseract_cmd():
        raise CustomModelError(
            "The Tesseract runtime is not installed, so the model cannot be checked. "
            "Run the import inside the application container."
        )
    paths.ensure_dirs()
    runtime.ensure_tessdata_layout()
    staging_root = paths.downloads_dir() / "custom-staging"
    staging = staging_root / f"{spec.family}-{version}-{os.getpid()}-{int(time.time())}"
    with store.file_lock(_lock_name(engine_id), timeout=30):
        if read_version(engine_id, version) is not None:
            raise CustomModelError(
                f"Version {version} already exists. Versions are immutable: import "
                "the new file under a new version id."
            )
        registry = read_registry(engine_id)
        if version in (registry["active_version"], registry["previous_version"]):
            # Its manifest is missing or unreadable, yet documents (or a
            # rollback) use this version: never replace its file in place.
            raise CustomModelError(
                f"Version {version} is the active or the rollback version but its "
                "manifest cannot be read. Restore the manifest from a backup, or "
                "activate another version first; then import under a new version id."
            )
        rel = rel_path(engine_id, version)
        _refuse_symlinks(rel)
        # Under the family lock no other import of this family is running:
        # whatever is left in the staging area belongs to a killed import.
        for stale in staging_root.glob(f"{spec.family}-*"):
            shutil.rmtree(stale, ignore_errors=True)
        try:
            # 2. staging — outside TESSDATA_PREFIX, never read by OCR
            staging.mkdir(parents=True, exist_ok=False)
            staged = staging / spec.filename
            sha_in = _copy_no_follow(source, staged, spec.max_size)
            # 3. checksum of what was actually staged
            sha = _sha256(staged)
            size = staged.stat().st_size
            if sha != sha_in:
                raise CustomModelError("The file changed while it was being copied.")
            # 4. structure + real Tesseract load, 5. smoke OCR
            info = inspect_traineddata(staged)
            smoke = tesseract_smoke(staging, spec.lang_stem)
            if not smoke["ok"]:
                raise CustomModelError(
                    f"Tesseract rejected the model: {smoke['detail']}"
                )
            duplicates = [
                m["version"] for m in list_versions(engine_id) if m.get("sha256") == sha
            ]
            # 6. store the valid version in its own (new) directory
            _refuse_symlinks(rel)  # again: the checks above took a while
            final = model_path(engine_id, version)
            vdir = final.parent
            if vdir.exists():
                # No manifest and not referenced by the registry (both checked
                # above): leftover of an interrupted import that was never
                # visible as a version. Safe to clear.
                shutil.rmtree(vdir)
            vdir.mkdir(parents=True, exist_ok=False)
            os.chmod(staged, 0o444)
            try:
                os.replace(staged, final)
            except OSError:  # models dir on another filesystem
                part = final.with_suffix(".part")
                shutil.copyfile(staged, part)
                os.chmod(part, 0o444)
                os.replace(part, final)
            if _sha256(final) != sha:
                shutil.rmtree(vdir, ignore_errors=True)
                raise CustomModelError(
                    "The stored file does not match the staged file."
                )
            # 7. manifest (the version exists from this point on)
            now = time.time()
            manifest: dict[str, Any] = {
                "schema": SCHEMA,
                "engine_id": engine_id,
                "family": spec.family,
                "version": version,
                "filename": spec.filename,
                "rel_path": rel,
                "lang": lang_code(engine_id, version),
                "sha256": sha,
                "size": size,
                "imported_at": now,
                "imported_at_iso": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)
                ),
                "source_name": source.name,
                "notes": notes,
                "duplicate_of": duplicates,
                "traineddata": info,
                "smoke": smoke,
                "verification": {"status": VERIFIED, "checked_at": now, "detail": None},
                "readiness": {},
            }
            _write_json(_version_manifest(engine_id, version), manifest)
            return manifest
        finally:
            shutil.rmtree(staging, ignore_errors=True)


# --- Activation / rollback ------------------------------------------------------------


def _switch(engine_id: str, version: str, action: str, actor: str) -> dict[str, Any]:
    check = check_version(engine_id, version, deep=True)
    if not check.verified:
        _update_version(
            engine_id,
            version,
            verification={
                "status": CORRUPTED if check.present else MISSING,
                "checked_at": time.time(),
                "detail": check.detail,
            },
        )
        raise CustomModelError(
            f"Version {version} failed verification ({check.detail}); the active "
            "version was not changed."
        )
    manifest = require_version(engine_id, version)
    if (manifest.get("verification") or {}).get("status") != VERIFIED or not (
        manifest.get("smoke") or {}
    ).get("ok"):
        raise CustomModelError(
            f"Version {version} is not verified; run 'custom verify --version "
            f"{version}' first. The active version was not changed."
        )
    registry = read_registry(engine_id)
    current = registry["active_version"]
    now = time.time()
    if current == version:
        return registry
    history = registry["history"]
    history.append(
        {
            "at": now,
            "action": action,
            "from": current,
            "to": version,
            "sha256": manifest.get("sha256"),
            "by": actor,
        }
    )
    registry.update(
        active_version=version,
        previous_version=current,
        activated_at=now,
        history=history[-HISTORY_LIMIT:],
    )
    _write_json(_registry_path(engine_id), registry)
    return registry


def activate_version(
    engine_id: str, version: str, actor: str = "cli"
) -> dict[str, Any]:
    """Make ``version`` the one NEW documents use. Running documents keep theirs."""
    require_version(engine_id, version)
    with store.file_lock(_lock_name(engine_id), timeout=30):
        return _switch(engine_id, version, "activate", actor)


def rollback(engine_id: str, actor: str = "cli") -> dict[str, Any]:
    """Return to the version that was active before the last switch."""
    spec_for(engine_id)
    with store.file_lock(_lock_name(engine_id), timeout=30):
        previous = read_registry(engine_id)["previous_version"]
        if not previous:
            raise CustomModelError("There is no earlier version to roll back to.")
        if read_version(engine_id, previous) is None:
            raise CustomModelError(
                f"The previous version {previous} no longer exists; activate another "
                "version explicitly."
            )
        return _switch(engine_id, previous, "rollback", actor)


def remove_version(engine_id: str, version: str, actor: str = "cli") -> dict[str, Any]:
    """Delete an INACTIVE version (its file and manifest). Never the active one.

    The caller must make sure no document is being processed with this version
    (the CLI checks the job queue): a running job keeps reading its version's
    file until it finishes.
    """
    manifest = require_version(engine_id, version)
    with store.file_lock(_lock_name(engine_id), timeout=30):
        registry = read_registry(engine_id)
        if registry["active_version"] == version:
            raise CustomModelError(
                f"Version {version} is active. Activate another version (or roll "
                "back) before removing it."
            )
        rel = rel_path(engine_id, version)
        raw_dir = (paths.models_dir() / rel).parent
        _refuse_symlinks(str(Path(rel).parent.parent))  # custom/<family> and above
        if raw_dir.is_symlink():
            raw_dir.unlink()  # never follow a planted link
        else:
            vdir = model_path(engine_id, version).parent
            if vdir.is_dir():
                shutil.rmtree(vdir)
        _version_manifest(engine_id, version).unlink(missing_ok=True)
        if registry["previous_version"] == version:
            registry["previous_version"] = None
        history = registry["history"]
        history.append(
            {
                "at": time.time(),
                "action": "remove",
                "from": version,
                "to": None,
                "sha256": manifest.get("sha256"),
                "by": actor,
            }
        )
        registry["history"] = history[-HISTORY_LIMIT:]
        _write_json(_registry_path(engine_id), registry)
        return registry


# --- Readiness records (written by readiness.record) ----------------------------------


def record_readiness(engine_id: str, version: str, check: dict[str, Any]) -> None:
    """Store a readiness verdict in the version's manifest.

    Under the family lock: the worker, the API and the CLI are separate
    processes, and an unlocked read-modify-write here could undo a verdict
    another of them has just written (e.g. ``corrupted`` from ``verify``).
    """
    try:
        with store.file_lock(_lock_name(engine_id), timeout=30):
            manifest = read_version(engine_id, version)
            if manifest is None:
                return
            checks = dict(manifest.get("readiness") or {})
            checks[check["mode"]] = {k: v for k, v in check.items() if k != "text"}
            _update_version(engine_id, version, readiness=checks)
    except store.LockBusy:
        logger.warning(
            f"OCR custom model: readiness of {engine_id} version {version} was not "
            "recorded (another model operation is running); run the check again."
        )


def readiness_checks(engine_id: str, version: str | None) -> dict[str, Any]:
    if version is None:
        return {}
    manifest = read_version(engine_id, version)
    return dict((manifest or {}).get("readiness") or {})


def fingerprint_part(engine_id: str, version: str | None) -> dict[str, Any]:
    """What a readiness verdict of a custom engine depends on, model-wise."""
    manifest = read_version(engine_id, version) if version else None
    return {
        "version": version,
        "sha256": (manifest or {}).get("sha256"),
        "size": (manifest or {}).get("size"),
        "langs": langs(engine_id, version) if version else [],
    }


# --- Status ------------------------------------------------------------------------


def status(engine_id: str) -> dict[str, Any]:
    """Everything the UI / CLI shows about a custom engine and its versions."""
    from open_notebook.ocr import readiness

    spec = spec_for(engine_id)
    registry = read_registry(engine_id)
    active = active_version(engine_id)
    versions = []
    manifests = list_versions(engine_id)
    rt_status = base = None
    if manifests:
        rt_status = runtime.probe_runtime(engine_id).status
        base = readiness.fingerprint(engine_id)
    for manifest in manifests:
        version = manifest["version"]
        live = check_version(engine_id, version)
        try:
            ready = readiness.readiness_status(
                engine_id,
                rt_status=rt_status,
                custom_version=version,
                base_fingerprint=base,
            )
        except Exception as e:  # pragma: no cover - status must always render
            ready = {"state": "unknown", "error": str(e)}
        versions.append(
            {
                "version": version,
                "active": version == active,
                "previous": version == registry["previous_version"],
                "sha256": manifest.get("sha256"),
                "size": manifest.get("size"),
                "imported_at": manifest.get("imported_at"),
                "notes": manifest.get("notes") or "",
                "source_name": manifest.get("source_name"),
                "duplicate_of": manifest.get("duplicate_of") or [],
                "lang": manifest.get("lang"),
                "traineddata_version": (manifest.get("traineddata") or {}).get(
                    "version_string"
                ),
                "smoke": manifest.get("smoke"),
                "verification": manifest.get("verification"),
                # Live comparison with the manifest (detects edits after import).
                "file_ok": live.verified,
                "file_present": live.present,
                "file_detail": live.detail,
                "readiness_state": ready.get("state"),
                "readiness": ready,
            }
        )
    english = english_check(engine_id)
    prerequisites = [store.check_file(f) for f in catalog.get_engine(engine_id).files]
    return {
        "family": spec.family,
        "filename": spec.filename,
        "active_version": active,
        "previous_version": registry["previous_version"],
        "activated_at": registry["activated_at"],
        "history": registry["history"][-10:],
        "versions": versions,
        "with_english": with_english(engine_id),
        "english_ok": None if english is None else english.verified,
        "english_env": spec.english_env,
        "prerequisites_ok": all(c.verified for c in prerequisites),
        "models_dir": str(paths.tessdata_dir() / "custom" / spec.family),
        "manifests_dir": str(_manifest_root(engine_id)),
        # /app/data exists in every deployment (./notebook_data on the host); a
        # stack may also mount a read-only drop folder (docs: OCR_AGRI_MODEL_GUIDE).
        "import_cli": (
            "python -m open_notebook.ocr.cli custom import "
            f"--file /app/data/ocr-import/{spec.filename} --version <id>"
        ),
    }
