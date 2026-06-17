from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from autovideo.api.dependencies import get_settings
from autovideo.api.errors import structured_error
from autovideo.core.settings import Settings
from autovideo.services.subtitles import dsl_v2
from autovideo.services.subtitles.preview_renderer import (
    SubtitlePreviewRendererUnavailableError,
    render_preview_png,
    render_preview_timeline,
)
from autovideo.services.subtitles.template_store import SubtitleTemplateStore, SubtitleTemplateStoreError

router = APIRouter(prefix="/api/subtitle-template-sets", tags=["subtitle-template-sets"])


class CreateTemplateSetRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    preset_id: str | None = None
    source_id: str | None = None


class PreviewRequest(BaseModel):
    template_set: dict[str, Any]
    template_type: str = "bottom"
    aspect_ratio: str = "9:16"
    sample_text: str = "AI 提升效率"
    duration_ms: Any = 1200


def _store(settings: Settings) -> SubtitleTemplateStore:
    return SubtitleTemplateStore(settings)


@router.get("")
def list_template_sets(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    store = _store(settings)
    return {"items": store.list_template_sets(), "presets": store.list_presets()}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_template_set(
    body: CreateTemplateSetRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return _store(settings).create_template_set(
            body.name,
            preset_id=body.preset_id,
            source_id=body.source_id,
        )
    except (KeyError, ValueError, SubtitleTemplateStoreError) as exc:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "SUBTITLE_TEMPLATE_INVALID",
            message=str(exc),
        ) from exc


@router.put("/presets/{preset_id}")
def update_preset(
    preset_id: str,
    patch: dict[str, Any],
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return _store(settings).update_preset(preset_id, patch)
    except KeyError as exc:
        raise structured_error(
            status.HTTP_404_NOT_FOUND,
            "SUBTITLE_TEMPLATE_NOT_FOUND",
            message=str(exc),
        ) from exc
    except (ValueError, SubtitleTemplateStoreError) as exc:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "SUBTITLE_TEMPLATE_INVALID",
            message=str(exc),
        ) from exc


@router.delete("/presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
def reset_preset(
    preset_id: str,
    settings: Settings = Depends(get_settings),
) -> Response:
    try:
        _store(settings).reset_preset(preset_id)
    except KeyError as exc:
        raise structured_error(
            status.HTTP_404_NOT_FOUND,
            "SUBTITLE_TEMPLATE_NOT_FOUND",
            message=str(exc),
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/validate")
def validate_template_set(payload: dict[str, Any]) -> dict[str, Any]:
    return dsl_v2.validate_template_set_v2(payload)


@router.post("/preview")
def preview_template_set(
    body: PreviewRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return render_preview_png(
            settings.ffmpeg_path,
            body.template_set,
            body.template_type,
            body.aspect_ratio,
            body.sample_text,
            settings.resolved_data_dir / "subtitle_previews",
        )
    except SubtitlePreviewRendererUnavailableError as exc:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "SUBTITLE_PREVIEW_RENDERER_UNAVAILABLE",
            message=str(exc),
        ) from exc


@router.post("/preview-timeline")
def preview_template_set_timeline(
    body: PreviewRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return render_preview_timeline(
            settings.ffmpeg_path,
            body.template_set,
            body.template_type,
            body.aspect_ratio,
            body.sample_text,
            body.duration_ms,
            settings.resolved_data_dir / "subtitle_previews",
        )
    except SubtitlePreviewRendererUnavailableError as exc:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "SUBTITLE_PREVIEW_RENDERER_UNAVAILABLE",
            message=str(exc),
        ) from exc


@router.put("/{template_set_id}")
def update_template_set(
    template_set_id: str,
    patch: dict[str, Any],
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return _store(settings).update_template_set(template_set_id, patch)
    except KeyError as exc:
        raise structured_error(
            status.HTTP_404_NOT_FOUND,
            "SUBTITLE_TEMPLATE_NOT_FOUND",
            message=str(exc),
        ) from exc
    except (ValueError, SubtitleTemplateStoreError) as exc:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "SUBTITLE_TEMPLATE_INVALID",
            message=str(exc),
        ) from exc


@router.delete("/{template_set_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template_set(
    template_set_id: str,
    settings: Settings = Depends(get_settings),
) -> Response:
    try:
        _store(settings).delete_template_set(template_set_id)
    except KeyError as exc:
        raise structured_error(
            status.HTTP_404_NOT_FOUND,
            "SUBTITLE_TEMPLATE_NOT_FOUND",
            message=str(exc),
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
