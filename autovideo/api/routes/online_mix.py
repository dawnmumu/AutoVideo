from __future__ import annotations

from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from autovideo.api.dependencies import get_settings, get_store
from autovideo.api.errors import structured_error
from autovideo.api.routes.tasks import public_task
from autovideo.core.settings import Settings
from autovideo.services.online_downloads import (
    OnlineMaterialContentTypeNotAllowedError,
    OnlineMaterialDownloadFailedError,
    OnlineMaterialDownloadTooLargeError,
    OnlineMaterialDownloadUrlNotAllowedError,
    default_download_resolver,
)
from autovideo.services.online_materials import (
    CandidateTokenExpiredError,
    CandidateTokenInvalidError,
    CandidateTokenService,
    build_provider_registry,
    provider_status,
)
from autovideo.services.online_mix import (
    OnlineMaterialProviderNotAvailableError,
    OnlineMaterialSearchFailedError,
    OnlineMixNoMaterialMatchError,
    OnlineMixShotSelectionInvalidError,
    create_online_mix_task,
    validate_manual_shot_coverage,
    validate_shot_selection,
)
from autovideo.services.tasks import (
    MaterialNotFoundError,
    TaskMaterialLimitExceededError,
    TaskOptionsTooLargeError,
)
from autovideo.storage.database import AutoVideoStore

router = APIRouter(prefix="/api/online-mix", tags=["online-mix"])


class ShotAssetSelection(BaseModel):
    shot_index: int
    candidate_token: str


class ShotMaterialSelection(BaseModel):
    shot_index: int
    material_id: str


class CreateOnlineMixTaskRequest(BaseModel):
    title: str = Field(default="未命名线上混剪任务", min_length=1, max_length=120)
    script: dict[str, Any]
    asset_strategy: Literal["auto", "manual"] = "auto"
    provider: Literal["auto", "pexels", "pixabay"] = "auto"
    shot_assets: list[ShotAssetSelection] = Field(default_factory=list)
    shot_materials: list[ShotMaterialSelection] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


def _provider_registry(request: Request, settings: Settings) -> dict[str, Any]:
    providers = getattr(request.app.state, "online_material_providers", None)
    if providers is None:
        providers = build_provider_registry(settings)
    return dict(providers or {})


def _provider_is_enabled(provider: Any) -> bool:
    return bool(getattr(provider, "enabled", True))


def _has_enabled_provider(providers: dict[str, Any]) -> bool:
    return any(_provider_is_enabled(provider) for provider in providers.values())


def _token_service(settings: Settings, request: Request) -> CandidateTokenService | None:
    if not settings.candidate_token_secret:
        return None
    return CandidateTokenService(
        secret=settings.candidate_token_secret,
        ttl_seconds=settings.candidate_token_ttl_seconds,
        now=getattr(request.app.state, "candidate_token_now", None),
    )


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_online_mix_video_task(
    request_body: CreateOnlineMixTaskRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    store: AutoVideoStore = Depends(get_store),
) -> dict[str, Any]:
    shot_assets = [item.model_dump() for item in request_body.shot_assets]
    shot_materials = [item.model_dump() for item in request_body.shot_materials]
    try:
        validate_shot_selection(request_body.script, shot_assets, shot_materials)
    except OnlineMixShotSelectionInvalidError as exc:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "ONLINE_MIX_SHOT_SELECTION_INVALID",
        ) from exc

    for item in shot_materials:
        material_id = str(item.get("material_id", ""))
        if store.get_material(material_id) is None:
            raise structured_error(
                status.HTTP_404_NOT_FOUND,
                "MATERIAL_NOT_FOUND",
                material_id=material_id,
            )

    needs_online_assets = bool(shot_assets) or request_body.asset_strategy == "auto"
    providers = _provider_registry(request, settings)
    if needs_online_assets:
        if request_body.asset_strategy == "auto" and request_body.provider != "auto":
            provider = providers.get(request_body.provider)
            if provider is None or not _provider_is_enabled(provider):
                raise structured_error(
                    status.HTTP_400_BAD_REQUEST,
                    "ONLINE_MATERIAL_PROVIDER_NOT_AVAILABLE",
                    provider=request_body.provider,
                )
        elif not _has_enabled_provider(providers):
            raise structured_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "ONLINE_MATERIAL_PROVIDER_NOT_CONFIGURED",
            )
        if not settings.candidate_token_secret:
            raise structured_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED",
            )

    token_service = _token_service(settings, request)
    try:
        validate_manual_shot_coverage(
            request_body.script,
            shot_assets,
            shot_materials,
            request_body.asset_strategy,
        )
    except OnlineMixNoMaterialMatchError as exc:
        raise structured_error(
            status.HTTP_409_CONFLICT,
            "ONLINE_MIX_NO_MATERIAL_MATCH",
        ) from exc

    for item in shot_assets:
        try:
            assert token_service is not None
            token_service.verify(str(item["candidate_token"]))
        except CandidateTokenExpiredError as exc:
            raise structured_error(
                status.HTTP_400_BAD_REQUEST,
                "ONLINE_MATERIAL_CANDIDATE_TOKEN_EXPIRED",
            ) from exc
        except CandidateTokenInvalidError as exc:
            raise structured_error(
                status.HTTP_400_BAD_REQUEST,
                "ONLINE_MATERIAL_CANDIDATE_TOKEN_INVALID",
            ) from exc

    injected_http_client = getattr(request.app.state, "online_download_http_client", None)
    should_close_http_client = injected_http_client is None
    http_client = injected_http_client or httpx.Client(
        timeout=settings.online_material_download_timeout_seconds
    )
    resolver = getattr(
        request.app.state,
        "online_download_resolver",
        default_download_resolver,
    )

    try:
        task = create_online_mix_task(
            store,
            title=request_body.title,
            script=request_body.script,
            shot_assets=shot_assets,
            shot_materials=shot_materials,
            asset_strategy=request_body.asset_strategy,
            provider_name=request_body.provider,
            providers=providers,
            token_service=token_service,
            http_client=http_client,
            max_download_bytes=settings.online_material_max_download_bytes,
            resolver=resolver,
            timeout=settings.online_material_download_timeout_seconds,
            results_per_query=settings.online_material_results_per_query,
            options=request_body.options,
            provider_status_snapshot=provider_status(settings, providers),
        )
        return public_task(task)
    except OnlineMixShotSelectionInvalidError as exc:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "ONLINE_MIX_SHOT_SELECTION_INVALID",
        ) from exc
    except OnlineMixNoMaterialMatchError as exc:
        raise structured_error(
            status.HTTP_409_CONFLICT,
            "ONLINE_MIX_NO_MATERIAL_MATCH",
        ) from exc
    except OnlineMaterialProviderNotAvailableError as exc:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "ONLINE_MATERIAL_PROVIDER_NOT_AVAILABLE",
            provider=exc.provider,
        ) from exc
    except (
        OnlineMaterialDownloadUrlNotAllowedError,
        OnlineMaterialContentTypeNotAllowedError,
    ) as exc:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "ONLINE_MATERIAL_REDIRECT_NOT_ALLOWED",
        ) from exc
    except OnlineMaterialDownloadTooLargeError as exc:
        raise structured_error(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "ONLINE_MATERIAL_TOO_LARGE",
            max_download_bytes=exc.max_download_bytes,
        ) from exc
    except OnlineMaterialDownloadFailedError as exc:
        raise structured_error(
            status.HTTP_502_BAD_GATEWAY,
            "ONLINE_MATERIAL_DOWNLOAD_FAILED",
        ) from exc
    except OnlineMaterialSearchFailedError as exc:
        raise structured_error(
            status.HTTP_502_BAD_GATEWAY,
            "ONLINE_MATERIAL_SEARCH_FAILED",
        ) from exc
    except CandidateTokenExpiredError as exc:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "ONLINE_MATERIAL_CANDIDATE_TOKEN_EXPIRED",
        ) from exc
    except CandidateTokenInvalidError as exc:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "ONLINE_MATERIAL_CANDIDATE_TOKEN_INVALID",
        ) from exc
    except MaterialNotFoundError as exc:
        raise structured_error(
            status.HTTP_404_NOT_FOUND,
            "MATERIAL_NOT_FOUND",
            material_id=exc.material_id,
        ) from exc
    except TaskMaterialLimitExceededError as exc:
        raise structured_error(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "TASK_MATERIAL_LIMIT_EXCEEDED",
            max_task_materials=exc.max_task_materials,
            material_count=exc.material_count,
        ) from exc
    except TaskOptionsTooLargeError as exc:
        raise structured_error(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "TASK_OPTIONS_TOO_LARGE",
            max_task_options_bytes=exc.max_task_options_bytes,
            options_bytes=exc.options_bytes,
        ) from exc
    finally:
        if should_close_http_client:
            http_client.close()
