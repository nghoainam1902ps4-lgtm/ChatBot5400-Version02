"""OCR Engine Manager API (admin only).

Every endpoint requires an admin (existing ``require_admin``; no new auth).
Long work (model download, engine test) is queued to the surreal-commands
worker; requests return immediately with a job id.

- GET    /ocr/engines                     engines + general info + config
- GET    /ocr/engines/{engine_id}         one engine
- POST   /ocr/engines/{engine_id}/install queue model download (pinned, checksummed)
- POST   /ocr/engines/{engine_id}/activate make it the active OCR engine (must be ready)
- POST   /ocr/engines/{engine_id}/test    queue a test on the built-in sample
- DELETE /ocr/engines/{engine_id}/model   remove its model (refused while active)
- GET    /ocr/jobs/{job_id}               status of an OCR job
- GET/PUT /ocr/config                     enable OCR, threads, full-page
"""

from fastapi import APIRouter, Depends

from api import ocr_service
from api.auth import require_admin
from api.models import (
    OcrConfig,
    OcrConfigUpdate,
    OcrDeleteResponse,
    OcrEnginesResponse,
    OcrEngineStatus,
    OcrJobResponse,
    OcrJobStatusResponse,
)

router = APIRouter(prefix="/ocr", tags=["ocr"], dependencies=[Depends(require_admin)])


@router.get("/engines", response_model=OcrEnginesResponse)
async def list_engines():
    return await ocr_service.list_engines()


@router.get("/engines/{engine_id}", response_model=OcrEngineStatus)
async def get_engine(engine_id: str):
    return await ocr_service.get_engine(engine_id)


@router.post(
    "/engines/{engine_id}/install", response_model=OcrJobResponse, status_code=202
)
async def install_engine(engine_id: str):
    return await ocr_service.install(engine_id)


@router.post("/engines/{engine_id}/activate", response_model=OcrEngineStatus)
async def activate_engine(engine_id: str):
    return await ocr_service.activate(engine_id)


@router.post(
    "/engines/{engine_id}/test", response_model=OcrJobResponse, status_code=202
)
async def test_engine(engine_id: str):
    return await ocr_service.test(engine_id)


@router.post(
    "/engines/{engine_id}/prepare", response_model=OcrJobResponse, status_code=202
)
async def prepare_engine(engine_id: str):
    """Online preparation; needs Internet for anything missing (never installs runtimes)."""
    return await ocr_service.prepare(engine_id)


@router.post(
    "/engines/{engine_id}/readiness-check",
    response_model=OcrJobResponse,
    status_code=202,
)
async def readiness_check(engine_id: str):
    """Offline-readiness check with network access disabled for the check itself."""
    return await ocr_service.readiness_check(engine_id)


@router.delete("/engines/{engine_id}/model", response_model=OcrDeleteResponse)
async def delete_engine_model(engine_id: str):
    removed = await ocr_service.delete_model(engine_id)
    return OcrDeleteResponse(engine_id=engine_id, removed=removed)


@router.get("/jobs/{job_id}", response_model=OcrJobStatusResponse)
async def get_job(job_id: str):
    return await ocr_service.job_status(job_id)


@router.get("/config", response_model=OcrConfig)
async def get_config():
    return await ocr_service.get_config()


@router.put("/config", response_model=OcrConfig)
async def update_config(update: OcrConfigUpdate):
    return await ocr_service.update_config(update)
