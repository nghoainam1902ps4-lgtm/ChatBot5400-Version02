"""Service layer of the OCR Engine Manager API (routers stay thin)."""

from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any

from loguru import logger

from api.command_service import CommandService
from api.models import (
    OcrConfig,
    OcrConfigUpdate,
    OcrEnginesResponse,
    OcrEngineStatus,
    OcrGeneralInfo,
)
from open_notebook.domain.content_settings import ContentSettings
from open_notebook.exceptions import InvalidInputError, NotFoundError
from open_notebook.ocr import (
    catalog,
    compat,
    installer,
    paths,
    readiness,
    runtime,
    store,
)
from open_notebook.ocr.status import engine_status

_OCR_COMMANDS = (
    "ocr_install_model",
    "ocr_test_engine",
    "ocr_prepare_engine",
    "ocr_check_readiness",
)
# Serialises state transitions inside this API process (install/test/delete).
_lock = asyncio.Lock()


def _require_engine(engine_id: str) -> catalog.EngineSpec:
    try:
        return catalog.get_engine(engine_id)
    except ValueError as e:
        raise NotFoundError(f"Unknown OCR engine: {engine_id}") from e


async def _settings() -> ContentSettings:
    ContentSettings.clear_instance()  # always the persisted truth
    return await ContentSettings.get_instance()  # type: ignore[return-value]


def _config(settings: ContentSettings) -> OcrConfig:
    engine = settings.docling_ocr_engine or catalog.DEFAULT_ENGINE
    return OcrConfig(
        docling_ocr=True
        if settings.docling_ocr is None
        else bool(settings.docling_ocr),
        docling_ocr_engine=engine,
        docling_ocr_device="cpu",
        docling_ocr_num_threads=settings.docling_ocr_num_threads,
        docling_ocr_force_full_page=bool(settings.docling_ocr_force_full_page),
    )


_FINISHED_JOB_STATES = {"completed", "failed", "canceled", "cancelled"}


async def _reconcile_job(engine_id: str) -> None:
    """Fail an install whose background job ended (or vanished) without finishing.

    The worker normally records the outcome itself; this covers a worker crash,
    a job lost from the queue or a cancelled job, so the UI never stays stuck in
    pending/downloading and Retry becomes available immediately.
    """
    st = store.read_state(engine_id)
    if st.get("state") not in store.ACTIVE_JOB_STATES or not st.get("job_id"):
        return
    if st.get("prepare_nonce"):
        # A running prepare downloads models itself (job_id is the previous
        # install's): its outcome is recorded by the prepare job; a crashed one
        # is covered by the stale timeout in store.job_is_active.
        return
    try:
        data = await CommandService.get_command_status(st["job_id"])
        job_state = str(data.get("status") or "unknown").lower()
    except Exception:
        return  # cannot tell; the stale timeout in store.job_is_active applies
    if job_state in _FINISHED_JOB_STATES:
        latest = store.read_state(engine_id)
        if latest.get("state") in store.ACTIVE_JOB_STATES:
            store.update_state(
                engine_id,
                state=store.FAILED,
                error=f"The installation job ended ({job_state}) before completing. Retry.",
                nonce=None,
            )


# A prepare/check may wait behind long source-processing jobs, then run up to
# two pipeline checks (+ downloads). Past this age the marker is considered
# dead even if the queue still says "running" (worker killed mid-job).
READINESS_MARKER_STALE_SECONDS = (
    store.PENDING_STALE_AFTER_SECONDS
    + 2 * readiness.CHECK_TIMEOUT
    + store.STALE_AFTER_SECONDS
)


async def _reconcile_readiness_jobs(engine_id: str) -> None:
    """Clear a prepare/check marker whose job ended without clearing it (worker crash)."""
    st = store.read_state(engine_id)
    for prefix in ("prepare", "readiness"):
        job_id = st.get(f"{prefix}_job_id")
        if not st.get(f"{prefix}_nonce"):
            continue
        queued_at = st.get(f"{prefix}_queued_at")
        if (
            queued_at
            and time.time() - float(queued_at) > READINESS_MARKER_STALE_SECONDS
        ):
            store.update_state(engine_id, **{f"{prefix}_nonce": None})
            continue
        if not job_id:
            continue
        try:
            data = await CommandService.get_command_status(job_id)
            job_state = str(data.get("status") or "unknown").lower()
        except Exception:
            continue
        if job_state in _FINISHED_JOB_STATES:
            store.update_state(engine_id, **{f"{prefix}_nonce": None})


async def _status(engine_id: str, active: str) -> OcrEngineStatus:
    await _reconcile_job(engine_id)
    await _reconcile_readiness_jobs(engine_id)
    # Filesystem hashing + subprocess probes: off the event loop.
    info = await asyncio.to_thread(runtime.docling_info)
    data = await asyncio.to_thread(
        engine_status, engine_id, active, info.get("fingerprint_problems") or []
    )
    return OcrEngineStatus(**data)


async def list_engines() -> OcrEnginesResponse:
    settings = await _settings()
    config = _config(settings)
    info = await asyncio.to_thread(runtime.docling_info)
    general = OcrGeneralInfo(
        docling_available=bool(info.get("available")),
        docling_version=info.get("version"),
        docling_api_compatible=info.get("api_compatible"),
        docling_missing_api=info.get("missing") or [],
        layout_model=info.get("layout_model"),
        table_model=info.get("table_model"),
        models_dir=str(paths.models_dir()),
        offline_mode=paths.offline_mode(),
        dependency_problems=await asyncio.to_thread(
            lambda: compat.problems(None, include_docling_sources=False)
            + list(info.get("fingerprint_problems") or [])
        ),
        dependency_override=compat.override_enabled(),
    )
    engines = [await _status(e, config.docling_ocr_engine) for e in catalog.ENGINE_IDS]
    return OcrEnginesResponse(general=general, config=config, engines=engines)


async def get_engine(engine_id: str) -> OcrEngineStatus:
    _require_engine(engine_id)
    settings = await _settings()
    return await _status(engine_id, _config(settings).docling_ocr_engine)


async def _submit(command: str, engine_id: str, nonce: str) -> str:
    import commands.ocr_commands  # noqa: F401  (registers the commands locally)

    assert command in _OCR_COMMANDS
    return await CommandService.submit_command_job(
        module_name="open_notebook",
        command_name=command,
        command_args={"engine_id": engine_id, "nonce": nonce},
    )


async def install(engine_id: str) -> dict[str, Any]:
    spec = _require_engine(engine_id)
    if spec.runtime == "builtin":
        raise InvalidInputError(
            f"{spec.display_name} uses the project's built-in model; nothing to install."
        )
    async with _lock:
        await _reconcile_job(engine_id)
        state = store.read_state(engine_id)
        if store.job_is_active(state):
            raise InvalidInputError(
                "An installation of this engine is already in progress."
            )
        rt = await asyncio.to_thread(runtime.probe_runtime, engine_id)
        if rt.status == runtime.RUNTIME_INCOMPATIBLE:
            raise InvalidInputError(f"Runtime incompatible: {rt.detail}")
        nonce = secrets.token_urlsafe(32)
        store.write_state(
            engine_id,
            {
                **state,
                "state": store.PENDING,
                "nonce": nonce,
                "error": None,
                "progress": None,
            },
        )
        try:
            job_id = await _submit("ocr_install_model", engine_id, nonce)
        except Exception as e:
            store.update_state(
                engine_id,
                state=store.FAILED,
                error="Could not queue the job",
                nonce=None,
            )
            logger.error(f"Failed to queue OCR install for {engine_id}: {e}")
            raise
        store.update_state(engine_id, job_id=job_id)
    return {"job_id": job_id, "engine_id": engine_id, "state": store.PENDING}


async def activate(engine_id: str) -> OcrEngineStatus:
    _require_engine(engine_id)
    async with _lock:
        status = await _status(engine_id, "")
        if engine_id == catalog.DEFAULT_ENGINE:
            if not status.runtime.get("status") == runtime.RUNTIME_READY:
                raise InvalidInputError(
                    f"RapidOCR is not available: {status.runtime.get('detail')}"
                )
        elif not status.ready:
            # The active engine stays unchanged (MASTER_PLAN 1.5).
            raise InvalidInputError(
                f"{status.display_name} is not ready (state: {status.state}). "
                f"{status.error or status.runtime.get('detail') or ''}".strip()
            )
        settings = await _settings()
        settings.docling_ocr_engine = engine_id  # type: ignore[assignment]
        await settings.update()
        logger.info(f"OCR engine activated: {engine_id}")
    return await get_engine(engine_id)


async def test(engine_id: str) -> dict[str, Any]:
    spec = _require_engine(engine_id)
    async with _lock:
        status = await _status(engine_id, "")
        runnable = status.runtime.get("status") == runtime.RUNTIME_READY and (
            spec.runtime == "builtin" or status.ready
        )
        if not runnable:
            raise InvalidInputError(
                f"{spec.display_name} is not ready to be tested (state: {status.state})."
            )
        nonce = secrets.token_urlsafe(32)
        store.update_state(engine_id, test_nonce=nonce)
        job_id = await _submit("ocr_test_engine", engine_id, nonce)
        store.update_state(engine_id, test_job_id=job_id)
    return {"job_id": job_id, "engine_id": engine_id, "state": store.PENDING}


async def _queue_readiness_job(
    engine_id: str, command: str, prefix: str
) -> dict[str, Any]:
    _require_engine(engine_id)
    async with _lock:
        await _reconcile_readiness_jobs(engine_id)
        st = store.read_state(engine_id)
        if st.get(f"{prefix}_nonce"):
            raise InvalidInputError(
                "This action is already queued or running for this engine."
            )
        nonce = secrets.token_urlsafe(32)
        store.update_state(
            engine_id, **{f"{prefix}_nonce": nonce, f"{prefix}_queued_at": time.time()}
        )
        try:
            job_id = await _submit(command, engine_id, nonce)
        except Exception:
            store.update_state(engine_id, **{f"{prefix}_nonce": None})
            raise
        store.update_state(engine_id, **{f"{prefix}_job_id": job_id})
    return {"job_id": job_id, "engine_id": engine_id, "state": store.PENDING}


async def prepare(engine_id: str) -> dict[str, Any]:
    """Queue online preparation (models + Docling/RapidOCR weights + checks)."""
    return await _queue_readiness_job(engine_id, "ocr_prepare_engine", "prepare")


async def readiness_check(engine_id: str) -> dict[str, Any]:
    """Queue an offline-readiness check (never downloads)."""
    return await _queue_readiness_job(engine_id, "ocr_check_readiness", "readiness")


async def delete_model(engine_id: str) -> list[str]:
    spec = _require_engine(engine_id)
    if spec.runtime == "builtin":
        raise InvalidInputError("The built-in RapidOCR model cannot be removed.")
    async with _lock:
        await _reconcile_job(engine_id)
        if store.read_state(engine_id).get("test_nonce"):
            raise InvalidInputError(
                "A test of this engine is queued or running; try again when it finishes."
            )
        running = await _running_source_jobs()
        if running is None:
            raise InvalidInputError(
                "Could not verify that no document is being processed; model not removed."
            )
        if running:
            # A job that started before an engine switch may still read these
            # files (Tesseract loads traineddata for every page).
            raise InvalidInputError(
                f"{running} document(s) are being processed right now; remove the model "
                "when processing has finished."
            )
        settings = await _settings()
        active = _config(settings).docling_ocr_engine
        try:
            return await asyncio.to_thread(installer.delete_models, engine_id, active)
        except installer.InstallError as e:
            raise InvalidInputError(str(e)) from e
        except store.LockBusy as e:
            raise InvalidInputError(str(e)) from e


async def _running_source_jobs() -> int | None:
    """Number of source-processing jobs currently RUNNING (None if unknown).

    Queued ("new") jobs are safe: they read the OCR settings when they start,
    so they use whichever engine is active then.
    """
    from open_notebook.database.repository import repo_query

    try:
        rows = await repo_query(
            "SELECT count() AS n FROM command WHERE name = 'process_source' "
            "AND status = 'running' GROUP ALL"
        )
    except Exception as e:
        logger.warning(f"Could not count running source jobs: {e}")
        return None
    if not rows:
        return 0
    try:
        return int(rows[0].get("n", 0))
    except (AttributeError, TypeError, ValueError):
        return None


async def update_config(update: OcrConfigUpdate) -> OcrConfig:
    settings = await _settings()
    if update.docling_ocr is not None:
        settings.docling_ocr = update.docling_ocr
    if update.docling_ocr_num_threads is not None:
        settings.docling_ocr_num_threads = update.docling_ocr_num_threads or None
    if update.docling_ocr_force_full_page is not None:
        settings.docling_ocr_force_full_page = update.docling_ocr_force_full_page
    await settings.update()
    return _config(settings)


async def get_config() -> OcrConfig:
    return _config(await _settings())


async def job_status(job_id: str) -> dict[str, Any]:
    # Only OCR jobs are reported here (the generic commands API covers the rest).
    known = {
        v
        for e in catalog.ENGINE_IDS
        for k, v in store.read_state(e).items()
        if k in ("job_id", "test_job_id", "prepare_job_id", "readiness_job_id") and v
    }
    if job_id not in known:
        raise NotFoundError("Unknown OCR job")
    data = await CommandService.get_command_status(job_id)
    return {
        "job_id": job_id,
        "status": data.get("status") or "unknown",
        "result": data.get("result"),
        "error_message": data.get("error_message"),
    }
