from __future__ import annotations

from typing import Any, Literal

import httpx

from autovideo.services.online_downloads import (
    DownloadResolver,
    stream_provider_download_to_material,
)
from autovideo.services.online_materials import (
    CandidateTokenInvalidError,
    CandidateTokenService,
    OnlineMaterialPublicUrlInvalidError,
    public_candidate,
    rank_candidates,
)
from autovideo.services.tasks import (
    MaterialNotFoundError,
    create_task,
    sanitize_manifest_payload,
)
from autovideo.storage.database import AutoVideoStore

AssetStrategy = Literal["auto", "manual"]
ProviderSelection = Literal["auto", "pexels", "pixabay"]


class OnlineMixShotSelectionInvalidError(Exception):
    """Raised when a shot-to-asset/material mapping is invalid."""


class OnlineMixNoMaterialMatchError(Exception):
    """Raised when every script shot cannot be matched to a material."""


class OnlineMaterialSearchFailedError(RuntimeError):
    """Raised when an online material provider search fails."""


class OnlineMaterialProviderNotAvailableError(Exception):
    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(provider)


def _shot_indexes(script: dict[str, Any]) -> set[int]:
    try:
        shots = script.get("shots", [])
        if not isinstance(shots, list):
            return set()
        indexes = [int(shot["index"]) for shot in shots]
    except (KeyError, TypeError, ValueError):
        return set()
    if len(indexes) != len(set(indexes)):
        return set()
    return set(indexes)


def _selection_indexes(selections: list[dict[str, Any]]) -> list[int]:
    try:
        return [int(item["shot_index"]) for item in selections]
    except (KeyError, TypeError, ValueError):
        raise OnlineMixShotSelectionInvalidError() from None


def validate_shot_selection(
    script: dict[str, Any],
    shot_assets: list[dict[str, Any]],
    shot_materials: list[dict[str, Any]],
) -> None:
    valid_indexes = _shot_indexes(script)
    if not valid_indexes:
        raise OnlineMixShotSelectionInvalidError()

    asset_indexes = _selection_indexes(shot_assets)
    material_indexes = _selection_indexes(shot_materials)
    if len(asset_indexes) != len(set(asset_indexes)):
        raise OnlineMixShotSelectionInvalidError()
    if len(material_indexes) != len(set(material_indexes)):
        raise OnlineMixShotSelectionInvalidError()
    if set(asset_indexes) & set(material_indexes):
        raise OnlineMixShotSelectionInvalidError()
    if not set(asset_indexes + material_indexes).issubset(valid_indexes):
        raise OnlineMixShotSelectionInvalidError()


def _provider_is_enabled(provider: Any) -> bool:
    return bool(getattr(provider, "enabled", True))


def _token_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise CandidateTokenInvalidError(
            f"candidate token field {field!r} is invalid"
        )
    return value


def _license_note(provider_name: str) -> str:
    return f"{provider_name} source metadata retained"


def _shot_query(script: dict[str, Any], shot: dict[str, Any]) -> str:
    keywords = shot.get("keywords")
    if isinstance(keywords, list):
        for keyword in keywords:
            if isinstance(keyword, str) and keyword.strip():
                return keyword.strip()

    visual_description = shot.get("visual_description")
    if isinstance(visual_description, str) and visual_description.strip():
        return visual_description.strip()

    topic = script.get("topic")
    if isinstance(topic, str) and topic.strip():
        return topic.strip()

    return str(shot.get("index") or "video")


def _script_aspect_ratio(script: dict[str, Any]) -> str:
    aspect_ratio = script.get("aspect_ratio")
    return aspect_ratio if isinstance(aspect_ratio, str) and aspect_ratio else "9:16"


def _shot_duration(shot: dict[str, Any]) -> int:
    try:
        return max(1, int(float(shot.get("duration") or 1)))
    except (TypeError, ValueError):
        return 1


def _download_candidate_payload(
    store: AutoVideoStore,
    *,
    provider: Any,
    payload: dict[str, Any],
    http_client: httpx.Client,
    max_download_bytes: int,
    resolver: DownloadResolver,
    timeout: float | None,
) -> dict[str, Any]:
    provider_name = _token_text(payload, "provider")
    return stream_provider_download_to_material(
        store=store,
        provider=provider,
        asset_id=_token_text(payload, "asset_id"),
        file_variant=_token_text(payload, "file_variant"),
        source_url=_token_text(payload, "source_url"),
        license_note=_license_note(provider_name),
        query=_token_text(payload, "query"),
        http_client=http_client,
        max_download_bytes=max_download_bytes,
        resolver=resolver,
        timeout=timeout,
    )


def _material_manifest_item(
    material: dict[str, Any],
    selection: dict[str, Any],
) -> dict[str, Any]:
    mode = str(selection.get("selection_mode") or "user_material")
    reasons = {
        "user_material": "用户选择已有本地素材",
        "user_candidate": "用户选择线上候选并由服务端下载",
        "auto": "系统按分镜关键词自动搜索并下载",
    }
    item: dict[str, Any] = {
        "shot_index": int(selection["shot_index"]),
        "material_id": str(selection["material_id"]),
        "selection_mode": mode,
        "selection_reason": selection.get("selection_reason")
        or reasons.get(mode, "用户选择已有本地素材"),
    }
    if material.get("source_provider") and material.get("source_url"):
        item.update(
            {
                "provider": material.get("source_provider"),
                "source_asset_id": material.get("source_asset_id"),
                "source_url": material.get("source_url"),
                "license_note": material.get("license_note"),
                "query": material.get("query"),
            }
        )
    return item


def _source_attribution(material: dict[str, Any]) -> dict[str, Any] | None:
    if not material.get("source_provider") or not material.get("source_url"):
        return None
    return {
        "provider": material.get("source_provider"),
        "source_asset_id": material.get("source_asset_id"),
        "source_url": material.get("source_url"),
        "license_note": material.get("license_note"),
        "query": material.get("query"),
    }


def sanitized_online_mix_options(options: dict[str, Any]) -> dict[str, Any]:
    sanitized = sanitize_manifest_payload(options)
    return sanitized if isinstance(sanitized, dict) else {}


def _online_asset_key_from_payload(payload: dict[str, Any]) -> tuple[str, str]:
    return (_token_text(payload, "provider"), _token_text(payload, "asset_id"))


def _online_asset_key_from_material(
    material: dict[str, Any] | None,
) -> tuple[str, str] | None:
    if material is None:
        return None
    provider = material.get("source_provider")
    asset_id = material.get("source_asset_id")
    if not isinstance(provider, str) or not provider:
        return None
    if not isinstance(asset_id, str) or not asset_id:
        return None
    return (provider, asset_id)


def _online_asset_key_from_candidate(candidate: Any) -> tuple[str, str]:
    return (str(candidate.provider), str(candidate.asset_id))


def create_online_mix_task(
    store: AutoVideoStore,
    *,
    title: str,
    script: dict[str, Any],
    shot_assets: list[dict[str, Any]],
    shot_materials: list[dict[str, Any]],
    asset_strategy: AssetStrategy,
    provider_name: ProviderSelection,
    providers: dict[str, Any],
    token_service: CandidateTokenService | None,
    http_client: httpx.Client,
    max_download_bytes: int,
    resolver: DownloadResolver,
    timeout: float | None,
    results_per_query: int,
    options: dict[str, Any],
    provider_status_snapshot: dict[str, Any],
) -> dict[str, Any]:
    validate_shot_selection(script, shot_assets, shot_materials)
    if (shot_assets or asset_strategy == "auto") and token_service is None:
        raise RuntimeError("candidate token service is required for online assets")

    used_online_assets: set[tuple[str, str]] = set()
    for item in shot_materials:
        material = store.get_material(str(item.get("material_id", "")))
        material_key = _online_asset_key_from_material(material)
        if material_key is not None:
            used_online_assets.add(material_key)
    resolved_materials = [
        {
            "shot_index": int(item["shot_index"]),
            "material_id": str(item["material_id"]),
            "selection_mode": "user_material",
        }
        for item in shot_materials
    ]

    for item in shot_assets:
        assert token_service is not None
        payload = token_service.verify(str(item["candidate_token"]))
        used_online_assets.add(_online_asset_key_from_payload(payload))
        token_provider = _token_text(payload, "provider")
        provider = providers.get(token_provider)
        if provider is None or not _provider_is_enabled(provider):
            raise OnlineMaterialProviderNotAvailableError(token_provider)
        material = _download_candidate_payload(
            store,
            provider=provider,
            payload=payload,
            http_client=http_client,
            max_download_bytes=max_download_bytes,
            resolver=resolver,
            timeout=timeout,
        )
        resolved_materials.append(
            {
                "shot_index": int(item["shot_index"]),
                "material_id": material["id"],
                "selection_mode": "user_candidate",
            }
        )

    if asset_strategy == "auto":
        assert token_service is not None
        if provider_name == "auto":
            selected_providers = [
                provider
                for provider in providers.values()
                if _provider_is_enabled(provider)
            ]
        else:
            provider = providers.get(provider_name)
            selected_providers = (
                [provider] if provider is not None and _provider_is_enabled(provider) else []
            )
        if not selected_providers:
            raise OnlineMaterialProviderNotAvailableError(provider_name)

        selected_indexes = {int(item["shot_index"]) for item in resolved_materials}
        for shot in script.get("shots", []):
            shot_index = int(shot["index"])
            if shot_index in selected_indexes:
                continue

            query = _shot_query(script, shot)
            aspect_ratio = _script_aspect_ratio(script)
            min_duration_seconds = _shot_duration(shot)
            try:
                candidates = rank_candidates(
                    [
                        candidate
                        for provider in selected_providers
                        for candidate in provider.search(
                            query,
                            aspect_ratio,
                            min_duration_seconds,
                            results_per_query,
                        )
                    ],
                    aspect_ratio=aspect_ratio,
                    min_duration_seconds=min_duration_seconds,
                )
            except Exception as exc:
                raise OnlineMaterialSearchFailedError(query) from exc
            if not candidates:
                raise OnlineMixNoMaterialMatchError()

            candidate = next(
                (
                    candidate
                    for candidate in candidates
                    if _online_asset_key_from_candidate(candidate)
                    not in used_online_assets
                ),
                candidates[0],
            )
            candidate_key = _online_asset_key_from_candidate(candidate)
            reused_online_asset = candidate_key in used_online_assets
            try:
                candidate_token = token_service.sign(
                    {
                        "provider": candidate.provider,
                        "asset_id": candidate.asset_id,
                        "query": candidate.query,
                        "file_variant": candidate.file_variant,
                        "source_url": candidate.source_url,
                    }
                )
                public_payload = public_candidate(candidate, candidate_token)
            except OnlineMaterialPublicUrlInvalidError as exc:
                raise OnlineMaterialSearchFailedError(query) from exc

            provider = providers.get(candidate.provider)
            if provider is None or not _provider_is_enabled(provider):
                raise OnlineMaterialProviderNotAvailableError(candidate.provider)
            payload = token_service.verify(str(public_payload["candidate_token"]))
            material = _download_candidate_payload(
                store,
                provider=provider,
                payload=payload,
                http_client=http_client,
                max_download_bytes=max_download_bytes,
                resolver=resolver,
                timeout=timeout,
            )
            resolved_materials.append(
                {
                    "shot_index": shot_index,
                    "material_id": material["id"],
                    "selection_mode": "auto",
                    "selection_reason": (
                        "候选不足，复用已下载的线上素材"
                        if reused_online_asset
                        else "系统按分镜关键词自动搜索并下载"
                    ),
                }
            )
            used_online_assets.add(candidate_key)
            selected_indexes.add(shot_index)

    material_ids: list[str] = []
    manifest_shots: list[dict[str, Any]] = []
    source_attribution_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for selection in sorted(resolved_materials, key=lambda value: int(value["shot_index"])):
        material_id = str(selection["material_id"])
        material = store.get_material(material_id)
        if material is None:
            raise MaterialNotFoundError(material_id)
        material_ids.append(material_id)
        manifest_shots.append(_material_manifest_item(material, selection))
        attribution = _source_attribution(material)
        if attribution is not None:
            source_key = (
                str(attribution["provider"]),
                str(attribution["source_url"]),
            )
            source_attribution_by_key[source_key] = attribution

    if {item["shot_index"] for item in manifest_shots} != _shot_indexes(script):
        raise OnlineMixNoMaterialMatchError()

    return create_task(
        store,
        title=title,
        material_ids=material_ids,
        options=sanitized_online_mix_options(options),
        manifest_payload={
            "script": script,
            "shot_materials": manifest_shots,
            "source_attribution": list(source_attribution_by_key.values()),
            "render_plan": {
                "status": "manifest_only",
                "renderer": "not_enabled",
            },
            "provider_status_snapshot": provider_status_snapshot,
        },
    )
