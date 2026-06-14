from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from autovideo.api.dependencies import get_settings
from autovideo.api.dependencies import get_store
from autovideo.api.errors import structured_error
from autovideo.core.settings import Settings
from autovideo.services.materials import public_material
from autovideo.services.online_downloads import (
    OnlineMaterialContentTypeNotAllowedError,
    OnlineMaterialDownloadFailedError,
    OnlineMaterialDownloadTooLargeError,
    OnlineMaterialDownloadUrlNotAllowedError,
    default_download_resolver,
    stream_provider_download_to_material,
)
from autovideo.services.online_materials import (
    CandidateTokenExpiredError,
    CandidateTokenInvalidError,
    CandidateTokenService,
    OnlineMaterialCandidate,
    OnlineMaterialPublicUrlInvalidError,
    provider_status,
    public_candidate,
    rank_candidates,
)
from autovideo.storage.database import AutoVideoStore

router = APIRouter(prefix="/api/online-materials", tags=["online-materials"])


class OnlineMaterialSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    aspect_ratio: str = "9:16"
    min_duration_seconds: int = Field(default=4, ge=1)
    provider: str = "auto"


class OnlineMaterialDownloadRequest(BaseModel):
    candidate_token: Any = None


def _provider_registry(request: Request) -> dict[str, Any]:
    return dict(getattr(request.app.state, "online_material_providers", {}) or {})


def _provider_is_enabled(provider: Any) -> bool:
    return bool(getattr(provider, "enabled", True))


def _token_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise CandidateTokenInvalidError("candidate token payload is invalid")
    return value


def _default_license_note(provider_name: str) -> str:
    if provider_name == "pexels":
        return "Pexels source metadata retained"
    if provider_name == "pixabay":
        return "Pixabay source metadata retained"
    return "Online source metadata retained"


@router.get("/status")
def online_material_status(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    return provider_status(settings, _provider_registry(request))


@router.post("/search")
def search_online_materials(
    payload: OnlineMaterialSearchRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    providers = _provider_registry(request)

    if payload.provider == "auto":
        selected_providers = [
            provider for provider in providers.values() if _provider_is_enabled(provider)
        ]
        if not selected_providers:
            raise structured_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "ONLINE_MATERIAL_PROVIDER_NOT_CONFIGURED",
            )
    else:
        provider = providers.get(payload.provider)
        if provider is None or not _provider_is_enabled(provider):
            raise structured_error(
                status.HTTP_400_BAD_REQUEST,
                "ONLINE_MATERIAL_PROVIDER_NOT_AVAILABLE",
                provider=payload.provider,
            )
        selected_providers = [provider]

    if not settings.candidate_token_secret:
        raise structured_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED",
        )

    candidates: list[OnlineMaterialCandidate] = []
    try:
        for provider in selected_providers:
            candidates.extend(
                provider.search(
                    payload.query,
                    payload.aspect_ratio,
                    payload.min_duration_seconds,
                    settings.online_material_results_per_query,
                )
            )
    except Exception as exc:
        raise structured_error(
            status.HTTP_502_BAD_GATEWAY,
            "ONLINE_MATERIAL_SEARCH_FAILED",
        ) from exc

    ranked_candidates = rank_candidates(
        candidates,
        aspect_ratio=payload.aspect_ratio,
        min_duration_seconds=payload.min_duration_seconds,
    )[: settings.online_material_results_per_query]
    token_service = CandidateTokenService(
        secret=settings.candidate_token_secret,
        ttl_seconds=settings.candidate_token_ttl_seconds,
    )

    public_candidates: list[dict[str, Any]] = []
    try:
        for candidate in ranked_candidates:
            token = token_service.sign(
                {
                    "provider": candidate.provider,
                    "asset_id": candidate.asset_id,
                    "query": candidate.query,
                    "file_variant": candidate.file_variant,
                    "source_url": candidate.source_url,
                }
            )
            public_candidates.append(public_candidate(candidate, token))
    except OnlineMaterialPublicUrlInvalidError as exc:
        raise structured_error(
            status.HTTP_502_BAD_GATEWAY,
            "ONLINE_MATERIAL_SEARCH_FAILED",
        ) from exc

    return public_candidates


@router.post("/download", status_code=status.HTTP_201_CREATED)
def download_online_material(
    payload: OnlineMaterialDownloadRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    store: AutoVideoStore = Depends(get_store),
) -> dict[str, Any]:
    providers = _provider_registry(request)
    if not any(_provider_is_enabled(provider) for provider in providers.values()):
        raise structured_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "ONLINE_MATERIAL_PROVIDER_NOT_CONFIGURED",
        )

    if not settings.candidate_token_secret:
        raise structured_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED",
        )

    candidate_token = payload.candidate_token
    if not isinstance(candidate_token, str) or not candidate_token:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "ONLINE_MATERIAL_CANDIDATE_TOKEN_INVALID",
        )

    token_service = CandidateTokenService(
        secret=settings.candidate_token_secret,
        ttl_seconds=settings.candidate_token_ttl_seconds,
    )
    try:
        token_payload = token_service.verify(candidate_token)
        provider_name = _token_text(token_payload, "provider")
        asset_id = _token_text(token_payload, "asset_id")
        file_variant = _token_text(token_payload, "file_variant")
        source_url = _token_text(token_payload, "source_url")
        query = _token_text(token_payload, "query")
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

    provider = providers.get(provider_name)
    if provider is None or not _provider_is_enabled(provider):
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "ONLINE_MATERIAL_PROVIDER_NOT_AVAILABLE",
            provider=provider_name,
        )

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
        material = stream_provider_download_to_material(
            store=store,
            provider=provider,
            asset_id=asset_id,
            file_variant=file_variant,
            source_url=source_url,
            license_note=_default_license_note(provider_name),
            query=query,
            http_client=http_client,
            max_download_bytes=settings.online_material_max_download_bytes,
            resolver=resolver,
            timeout=settings.online_material_download_timeout_seconds,
        )
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
    finally:
        if should_close_http_client:
            http_client.close()

    return public_material(material)
