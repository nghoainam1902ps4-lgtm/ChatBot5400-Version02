"""Service layer of the OCR Engine Manager API (routers stay thin)."""

from __future__ import annotations

import asyncio
import secrets
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
from open_notebook.ocr import catalog, installer, paths, runtime, store
from open_notebook.ocr.status import engine_status

_OCR_COMMANDS = ("ocr_install_model", "ocr_test_engine")
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


async def _status(engine_id: str, active: str) -> OcrEngineStatus:
    # Filesystem hashing + subprocess probes: off the event loop.
    data = await asyncio.to_thread(engine_status, engine_id, active)
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


async def delete_model(engine_id: str) -> list[str]:
    spec = _require_engine(engine_id)
    if spec.runtime == "builtin":
        raise InvalidInputError("The built-in RapidOCR model cannot be removed.")
    async with _lock:
        settings = await _settings()
        active = _config(settings).docling_ocr_engine
        try:
            return await asyncio.to_thread(installer.delete_models, engine_id, active)
        except installer.InstallError as e:
            raise InvalidInputError(str(e)) from e
        except store.LockBusy as e:
            raise InvalidInputError(str(e)) from e


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
        if k in ("job_id", "test_job_id") and v
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
