"""Background jobs of the OCR Engine Manager (model install, engine test).

Both commands authorise themselves with a one-time nonce that only the
admin-only OCR API writes into the engine manifest (DECISIONS D-08):
``POST /api/commands/jobs`` lets any authenticated user submit any registered
command, so the command must not trust its caller.

Long work happens here (worker), never inside an HTTP request.
"""

import asyncio
import hmac
import time
from typing import Any, Dict, Optional

from loguru import logger
from surreal_commands import CommandInput, CommandOutput, command

from open_notebook.ocr import catalog, installer, store


class OcrJobInput(CommandInput):
    engine_id: str
    nonce: str


class OcrJobOutput(CommandOutput):
    success: bool
    engine_id: str
    state: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


def _authorised(engine_id: str, nonce: str, field: str) -> bool:
    expected = store.read_state(engine_id).get(field)
    return bool(expected) and hmac.compare_digest(str(expected), str(nonce))


@command("ocr_install_model", app="open_notebook", retry={"max_attempts": 1})
async def ocr_install_model_command(input_data: OcrJobInput) -> OcrJobOutput:
    engine_id = input_data.engine_id
    if engine_id not in catalog.ENGINES:
        return OcrJobOutput(
            success=False, engine_id=engine_id, error_message="Unknown engine"
        )
    if not _authorised(engine_id, input_data.nonce, "nonce"):
        logger.warning(f"Rejected unauthorised OCR install job for {engine_id}")
        return OcrJobOutput(
            success=False, engine_id=engine_id, error_message="Unauthorised job"
        )
    try:
        # Blocking I/O + hashing: keep the worker's event loop responsive.
        state = await asyncio.to_thread(installer.install_models, engine_id)
        return OcrJobOutput(success=True, engine_id=engine_id, state=state.get("state"))
    except store.LockBusy as e:
        return OcrJobOutput(success=False, engine_id=engine_id, error_message=str(e))
    except Exception as e:
        message = (
            str(e)
            if isinstance(e, installer.InstallError)
            else f"{type(e).__name__}: {e}"
        )
        logger.error(f"OCR model install failed for {engine_id}: {message}")
        store.update_state(
            engine_id, state=store.FAILED, error=message[:1000], nonce=None
        )
        return OcrJobOutput(
            success=False,
            engine_id=engine_id,
            state=store.FAILED,
            error_message=message,
        )


@command("ocr_test_engine", app="open_notebook", retry={"max_attempts": 1})
async def ocr_test_engine_command(input_data: OcrJobInput) -> OcrJobOutput:
    engine_id = input_data.engine_id
    if engine_id not in catalog.ENGINES:
        return OcrJobOutput(
            success=False, engine_id=engine_id, error_message="Unknown engine"
        )
    if not _authorised(engine_id, input_data.nonce, "test_nonce"):
        logger.warning(f"Rejected unauthorised OCR test job for {engine_id}")
        return OcrJobOutput(
            success=False, engine_id=engine_id, error_message="Unauthorised job"
        )
    from open_notebook.domain.content_settings import ContentSettings
    from open_notebook.ocr.options import OcrSettings
    from open_notebook.ocr.tester import run_engine_test

    ContentSettings.clear_instance()
    settings = await ContentSettings.get_instance()
    base = OcrSettings.from_content_settings(settings)
    result = await asyncio.to_thread(run_engine_test, engine_id, base)
    store.update_state(
        engine_id, last_test=result, test_nonce=None, test_finished_at=time.time()
    )
    return OcrJobOutput(
        success=bool(result.get("success")),
        engine_id=engine_id,
        result=result,
        error_message=result.get("error"),
    )
