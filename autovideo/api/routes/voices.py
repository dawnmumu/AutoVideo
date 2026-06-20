from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import FileResponse

from autovideo.api.dependencies import get_settings
from autovideo.api.errors import structured_error
from autovideo.core.settings import Settings
from autovideo.services.voices import (
    EdgeTtsProvider,
    VoiceCenterService,
    VoiceNotFoundError,
    VoicePreviewRequest,
    VoicePreviewTextTooLongError,
    VoiceProviderError,
)

router = APIRouter(prefix="/api/voices", tags=["voices"])


def _provider(request: Request) -> Any:
    provider = getattr(request.app.state, "edge_tts_provider", None)
    if provider is None:
        provider = EdgeTtsProvider()
        request.app.state.edge_tts_provider = provider
    return provider


def _service(request: Request, settings: Settings) -> VoiceCenterService:
    return VoiceCenterService(settings, provider=_provider(request))


@router.get("/status")
def voice_status(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "edge_tts": {
            "enabled": True,
            "provider": "edge_tts",
            "requires_api_key": False,
            "default_voice": settings.edge_tts_default_voice,
            "max_preview_text_chars": settings.max_voice_preview_text_chars,
        },
        "fish_speech": {
            "configured": settings.fish_speech_url is not None,
            "enabled": settings.fish_speech_url is not None,
        },
    }


@router.get("")
async def list_voices(
    request: Request,
    locale: str | None = Query(default=None, min_length=2, max_length=16),
    q: str | None = Query(default=None, min_length=1, max_length=80),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return await _service(request, settings).list_voices(locale=locale, query=q)
    except VoiceProviderError as exc:
        raise structured_error(
            status.HTTP_502_BAD_GATEWAY,
            "VOICE_LIST_FAILED",
        ) from exc


@router.post("/preview", status_code=status.HTTP_201_CREATED)
async def create_voice_preview(
    body: VoicePreviewRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return await _service(request, settings).create_preview(body)
    except VoicePreviewTextTooLongError as exc:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "VOICE_PREVIEW_TEXT_TOO_LONG",
            max_chars=exc.max_chars,
        ) from exc
    except VoiceNotFoundError as exc:
        raise structured_error(
            status.HTTP_404_NOT_FOUND,
            "VOICE_NOT_FOUND",
            voice_id=exc.voice_id,
        ) from exc
    except VoiceProviderError as exc:
        raise structured_error(
            status.HTTP_502_BAD_GATEWAY,
            "VOICE_PREVIEW_FAILED",
        ) from exc


@router.get("/previews/{filename}")
def download_voice_preview(
    filename: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    try:
        preview_path = _service(request, settings).preview_path(filename)
    except FileNotFoundError as exc:
        raise structured_error(
            status.HTTP_404_NOT_FOUND,
            "VOICE_PREVIEW_NOT_FOUND",
            filename=filename,
        ) from exc
    return FileResponse(preview_path, media_type="audio/mpeg", filename=filename)
