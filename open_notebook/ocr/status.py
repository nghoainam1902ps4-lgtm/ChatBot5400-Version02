"""Compose the truthful lifecycle status of each OCR engine.

``ready`` requires BOTH a working runtime (executable / Python package /
Docling) AND checksum-verified model files. Lifecycle precedence:

    active job (pending/downloading/installing) > incompatible >
    failed > requires_restart > ready > not_installed
"""

from __future__ import annotations

from typing import Any

from open_notebook.ocr import catalog, compat, runtime, store


def dependency_problems(
    engine_id: str, docling_fingerprint_problems: list[str] | None = None
) -> list[str]:
    """Version/fingerprint problems for the native OCR path (compat.py).

    Docling source fingerprints come from the probe subprocess (the API process
    must not import Docling's OCR modules); content-core is checked in-process.
    """
    found = compat.problems(engine_id, include_docling_sources=False)
    return found + list(docling_fingerprint_problems or [])


def engine_status(
    engine_id: str,
    active_engine: str | None = None,
    docling_fingerprint_problems: list[str] | None = None,
) -> dict[str, Any]:
    spec = catalog.get_engine(engine_id)
    rt = runtime.probe_runtime(engine_id)
    deps = (
        dependency_problems(engine_id, docling_fingerprint_problems)
        if rt.status != runtime.RUNTIME_MISSING or spec.runtime == "builtin"
        else []
    )
    deps_blocking = bool(deps) and not compat.override_enabled()
    ms = store.model_status(engine_id)
    st = store.read_state(engine_id)

    job_active = store.job_is_active(st)
    if job_active:
        lifecycle = st["state"]
    elif rt.status == runtime.RUNTIME_INCOMPATIBLE:
        lifecycle = store.INCOMPATIBLE
    elif deps_blocking and spec.runtime != "builtin":
        # Unverified content-core/Docling/engine versions: never "ready".
        lifecycle = store.INCOMPATIBLE
    elif ms.status == "corrupted":
        lifecycle = store.FAILED
    elif st.get("state") == store.FAILED:
        # Even when the files verify: a failed smoke check must never be
        # reported (or activated) as ready. Retry re-runs the checks.
        lifecycle = store.FAILED
    elif st.get("state") in store.ACTIVE_JOB_STATES:
        # Stale job (worker died / job lost): never verified end to end.
        lifecycle = store.FAILED
    elif ms.installed and rt.status == runtime.RUNTIME_REQUIRES_RESTART:
        lifecycle = store.REQUIRES_RESTART
    elif ms.installed and rt.ready:
        lifecycle = store.READY
    else:
        lifecycle = store.NOT_INSTALLED

    error = st.get("error")
    if ms.status == "corrupted":
        bad = [f.rel_path for f in ms.files if f.present and not f.verified]
        error = (
            f"Model files failed verification: {', '.join(bad)}. Reinstall to repair."
        )
    elif lifecycle == store.FAILED and not error:
        error = (
            "The previous installation stopped unexpectedly. Retry the installation."
        )

    if deps_blocking and spec.runtime != "builtin" and not job_active:
        error = (
            "Dependencies differ from the verified set: "
            + "; ".join(deps)
            + f". Re-verify, then set {compat.OVERRIDE_ENV}=true."
        )
    elif deps and spec.runtime == "builtin":
        error = (
            "Dependencies differ from the verified set ("
            + "; ".join(deps)
            + "): the default path still uses content-core unchanged, but RapidOCR "
            "can no longer be pinned against Docling Auto."
        )
    return {
        "id": spec.id,
        "display_name": spec.display_name,
        "description": spec.description,
        "languages": list(spec.languages),
        "model_name": spec.model_name,
        "model_version": spec.model_version,
        "license": spec.license,
        "source_url": spec.source_url,
        "builtin": spec.runtime == "builtin",
        "quality": spec.quality,
        "download_size_bytes": spec.download_size,
        "size_bytes": spec.total_size,
        "installed_size_bytes": ms.installed_bytes,
        "runtime": rt.to_dict(),
        "model": ms.to_dict(),
        "state": lifecycle,
        "ready": lifecycle == store.READY,
        "active": engine_id == (active_engine or catalog.DEFAULT_ENGINE),
        "job": {
            "job_id": st.get("job_id"),
            "state": st.get("state"),
            "progress": st.get("progress"),
            "updated_at": st.get("updated_at"),
        }
        if st
        else None,
        "error": error,
        "smoke": st.get("smoke"),
        "last_test": st.get("last_test"),
        "options": _safe_describe(engine_id),
        "dependency_problems": deps,
        "readiness": _safe_readiness(engine_id, rt.status, ms.status),
        # A prepare / readiness-check job is queued or running for this engine.
        "readiness_job": "prepare"
        if st.get("prepare_nonce")
        else ("check" if st.get("readiness_nonce") else None),
    }


def _safe_readiness(
    engine_id: str, rt_status: str, model_status: str
) -> dict[str, Any]:
    from open_notebook.ocr.readiness import readiness_status

    try:
        return readiness_status(engine_id, rt_status, model_status)
    except Exception as e:  # pragma: no cover - status must always render
        return {"state": "unknown", "error": str(e)}


def _safe_describe(engine_id: str) -> dict[str, Any]:
    from open_notebook.ocr.options import describe

    try:
        return describe(engine_id)
    except Exception as e:  # pragma: no cover - describe is pure
        return {"error": str(e)}


def assert_engine_ready(engine_id: str) -> None:
    """Raise ValueError (permanent, user-readable) unless the engine can run now."""
    spec = catalog.get_engine(engine_id)
    compat.ensure_compatible(engine_id)  # worker: includes Docling fingerprints
    rt = runtime.probe_runtime(engine_id)
    if not rt.ready:
        raise ValueError(
            f"OCR engine '{spec.display_name}' is selected but its runtime is "
            f"{rt.status}: {rt.detail or ''} Open Settings → OCR Engine Manager."
        )
    ms = store.model_status(engine_id)
    if not ms.installed:
        raise ValueError(
            f"OCR engine '{spec.display_name}' is selected but its model is "
            f"{ms.status}. Reinstall it in Settings → OCR Engine Manager."
        )
