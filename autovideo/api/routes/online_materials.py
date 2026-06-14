from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from autovideo.api.dependencies import get_settings
from autovideo.api.errors import structured_error
from autovideo.core.settings import Settings
from autovideo.services.online_materials import (
    CandidateTokenService,
    OnlineMaterialCandidate,
    OnlineMaterialPublicUrlInvalidError,
    provider_status,
    public_candidate,
    rank_candidates,
)

router = APIRouter(prefix="/api/online-materials", tags=["online-materials"])


class OnlineMaterialSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    aspect_ratio: str = "9:16"
    min_duration_seconds: int = Field(default=4, ge=1)
    provider: str = "auto"


def _provider_registry(request: Request) -> dict[str, Any]:
    return dict(getattr(request.app.state, "online_material_providers", {}) or {})


def _provider_is_enabled(provider: Any) -> bool:
    return bool(getattr(provider, "enabled", True))


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
