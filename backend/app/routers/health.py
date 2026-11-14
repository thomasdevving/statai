from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app import ai
from app.config import Settings, get_settings
from app.media.ffmpeg import ffmpeg_available

CONTRACT_VERSION = "2.0"

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str | bool]:
    return {
        "status": "ok",
        "contract_version": CONTRACT_VERSION,
        "ai_mode": ai.ai_mode(),
        "storage": settings.storage,
        "ffmpeg": ffmpeg_available(),
    }
