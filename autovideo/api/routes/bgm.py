from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from autovideo.api.dependencies import get_settings
from autovideo.api.errors import structured_error
from autovideo.core.settings import Settings
from autovideo.services.bgm import (
    BgmCategoryDuplicateError,
    BgmCategoryEmptyError,
    BgmCategoryNameRequiredError,
    BgmCategoryNotFoundError,
    BgmFileEmptyError,
    BgmFileTooLargeError,
    BgmFileUnsupportedError,
    BgmLibraryCorruptError,
    BgmLibraryService,
    BgmTrackFileDeleteError,
    BgmTrackNameRequiredError,
    BgmTrackNotFoundError,
)
from autovideo.services.bgm.models import SUPPORTED_BGM_EXTENSIONS

router = APIRouter(prefix="/api/bgm", tags=["bgm"])


class BgmCategoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class BgmTrackUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    category_id: str | None = None


def _service(request: Request, settings: Settings) -> BgmLibraryService:
    return BgmLibraryService(
        settings,
        audio_probe=getattr(request.app.state, "bgm_audio_probe", None),
    )


def _public_library(library: dict[str, Any]) -> dict[str, Any]:
    items = library.get("items")
    categories = library.get("categories")
    public_items = items if isinstance(items, list) else []
    public_categories = categories if isinstance(categories, list) else []
    return {
        "items": public_items,
        "categories": public_categories,
        "total_tracks": int(library.get("total_tracks") or len(public_items)),
        "storage_status": "ready",
        "supported_extensions": sorted(SUPPORTED_BGM_EXTENSIONS),
    }


def _raise_bgm_error(exc: Exception) -> NoReturn:
    if isinstance(exc, BgmFileUnsupportedError):
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "BGM_FILE_UNSUPPORTED",
            allowed=sorted(SUPPORTED_BGM_EXTENSIONS),
        ) from exc
    if isinstance(exc, BgmFileEmptyError):
        raise structured_error(status.HTTP_400_BAD_REQUEST, "BGM_FILE_EMPTY") from exc
    if isinstance(exc, BgmFileTooLargeError):
        raise structured_error(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "BGM_FILE_TOO_LARGE",
            max_upload_bytes=exc.max_upload_bytes,
        ) from exc
    if isinstance(exc, BgmTrackNotFoundError):
        raise structured_error(status.HTTP_404_NOT_FOUND, "BGM_TRACK_NOT_FOUND") from exc
    if isinstance(exc, BgmCategoryNotFoundError):
        raise structured_error(status.HTTP_404_NOT_FOUND, "BGM_CATEGORY_NOT_FOUND") from exc
    if isinstance(exc, BgmCategoryDuplicateError):
        raise structured_error(status.HTTP_400_BAD_REQUEST, "BGM_CATEGORY_DUPLICATE") from exc
    if isinstance(exc, BgmCategoryNameRequiredError):
        raise structured_error(status.HTTP_400_BAD_REQUEST, "BGM_CATEGORY_NAME_REQUIRED") from exc
    if isinstance(exc, BgmTrackNameRequiredError):
        raise structured_error(status.HTTP_400_BAD_REQUEST, "BGM_TRACK_NAME_REQUIRED") from exc
    if isinstance(exc, BgmCategoryEmptyError):
        raise structured_error(status.HTTP_400_BAD_REQUEST, "BGM_CATEGORY_EMPTY") from exc
    if isinstance(exc, BgmLibraryCorruptError):
        raise structured_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "BGM_LIBRARY_CORRUPT") from exc
    if isinstance(exc, BgmTrackFileDeleteError):
        raise structured_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "BGM_TRACK_FILE_DELETE_FAILED",
        ) from exc
    raise exc


@router.get("")
def list_bgm(request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    try:
        return _public_library(_service(request, settings).library())
    except Exception as exc:
        _raise_bgm_error(exc)


@router.post("/tracks", status_code=status.HTTP_201_CREATED)
async def upload_bgm_track(
    request: Request,
    file: UploadFile = File(...),
    category_id: str | None = Form(default=None),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return _service(request, settings).store_track(
            content=await file.read(),
            original_filename=file.filename or "bgm",
            category_id=category_id or None,
        )
    except Exception as exc:
        _raise_bgm_error(exc)


@router.put("/tracks/{track_id}")
def update_bgm_track(
    track_id: str,
    body: BgmTrackUpdateRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return _service(request, settings).update_track(
            track_id,
            display_name=body.display_name,
            category_id=body.category_id,
        )
    except Exception as exc:
        _raise_bgm_error(exc)


@router.delete("/tracks/{track_id}")
def delete_bgm_track(
    track_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return _service(request, settings).delete_track(track_id)
    except Exception as exc:
        _raise_bgm_error(exc)


@router.get("/tracks/{track_id}/file")
def download_bgm_track(
    track_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    try:
        path, media_type, filename = _service(request, settings).track_file(track_id)
    except Exception as exc:
        _raise_bgm_error(exc)
    response = FileResponse(path, media_type=media_type, filename=filename)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@router.post("/categories", status_code=status.HTTP_201_CREATED)
def create_bgm_category(
    body: BgmCategoryRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return _service(request, settings).create_category(body.name)
    except Exception as exc:
        _raise_bgm_error(exc)


@router.put("/categories/{category_id}")
def update_bgm_category(
    category_id: str,
    body: BgmCategoryRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return _service(request, settings).update_category(category_id, body.name)
    except Exception as exc:
        _raise_bgm_error(exc)


@router.delete("/categories/{category_id}")
def delete_bgm_category(
    category_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return _service(request, settings).delete_category(category_id)
    except Exception as exc:
        _raise_bgm_error(exc)
