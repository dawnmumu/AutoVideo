from __future__ import annotations

import copy
import math
import re
from typing import Any, Literal

import httpx

from autovideo.services.bgm import (
    BgmCategoryEmptyError,
    BgmCategoryNotFoundError,
    BgmLibraryService,
    BgmTrackNotFoundError,
)
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
from autovideo.services.rendering import (
    FfmpegRenderFailedError,
    build_render_timeline,
    render_mix_video,
    sanitize_render_timeline,
    write_timeline_artifacts,
)
from autovideo.services.subtitles import dsl_v2
from autovideo.services.subtitles.source_masks import build_source_subtitle_masks
from autovideo.services.subtitles.template_store import SubtitleTemplateStore, SubtitleTemplateStoreError
from autovideo.services.tasks import (
    MaterialNotFoundError,
    create_task,
    sanitize_manifest_payload,
)
from autovideo.storage.database import AutoVideoStore

AssetStrategy = Literal["auto", "manual"]
ProviderSelection = Literal["auto", "pexels", "pixabay"]
EMPTY_SUBTITLE_OPTION_KEYS = frozenset(
    {
        "subtitle_template_set_id",
        "subtitle_template_set_name",
        "subtitle_template_snapshot",
        "subtitle_font_family",
    }
)
RENDER_ERROR_SENSITIVE_FRAGMENT_RE = re.compile(
    r"(?<![\w-])"
    r"("
    r"access[-_]?token|refresh[-_]?token|(?:x[\s_-]*)?api[\s_-]*key|"
    r"client[-_]?secret|token|secret|password"
    r")"
    r"(?![\w-])\s*(=|:|\s)\s*\S+",
    re.IGNORECASE,
)


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


class SubtitleTemplateInvalidError(ValueError):
    pass


class VoiceProviderInvalidError(ValueError):
    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(provider)


class BgmOptionInvalidError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


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


def validate_manual_shot_coverage(
    script: dict[str, Any],
    shot_assets: list[dict[str, Any]],
    shot_materials: list[dict[str, Any]],
    asset_strategy: AssetStrategy,
) -> None:
    if asset_strategy != "manual":
        return
    selected_indexes = set(
        _selection_indexes(shot_assets) + _selection_indexes(shot_materials)
    )
    if selected_indexes != _shot_indexes(script):
        raise OnlineMixNoMaterialMatchError()


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
    if not isinstance(sanitized, dict):
        return {}
    return {
        key: value
        for key, value in sanitized.items()
        if not (key in EMPTY_SUBTITLE_OPTION_KEYS and value is None)
    }


def normalize_subtitle_options(
    store: AutoVideoStore,
    options: dict[str, Any],
) -> dict[str, Any]:
    subtitle_enabled = bool(options.get("subtitle_enabled", True))
    if not subtitle_enabled:
        return {
            "subtitle_enabled": False,
            "subtitle_template_set_id": None,
            "subtitle_template_set_name": None,
            "subtitle_template_snapshot": None,
            "subtitle_font_family": None,
        }

    template_store = SubtitleTemplateStore(store.settings)
    requested_template_id = _optional_text(options.get("subtitle_template_set_id"))
    snapshot = options.get("subtitle_template_snapshot")
    template_set: dict[str, Any]

    if snapshot is not None:
        if not isinstance(snapshot, dict):
            raise SubtitleTemplateInvalidError("字幕模板快照必须是对象")
        snapshot_id = _required_template_text(snapshot, "id")
        _required_template_text(snapshot, "name")
        if requested_template_id and requested_template_id != snapshot_id:
            raise SubtitleTemplateInvalidError("字幕模板快照 ID 与请求模板 ID 不一致")
        template_set = copy.deepcopy(snapshot)
    elif requested_template_id:
        try:
            template_set = template_store.get_template_set(requested_template_id)
        except KeyError as exc:
            raise SubtitleTemplateInvalidError("字幕模板不存在") from exc
    else:
        try:
            template_set = template_store.select_auto_template_set()
        except KeyError as exc:
            raise SubtitleTemplateInvalidError("没有可用的字幕模板") from exc

    try:
        template_set = template_store.with_template_variants(template_set)
    except SubtitleTemplateStoreError as exc:
        raise SubtitleTemplateInvalidError("字幕模板无效") from exc

    result = dsl_v2.validate_template_set_v2(template_set)
    normalized = result.get("normalized")
    if not result.get("ok") or not isinstance(normalized, dict):
        warnings = "; ".join(str(item) for item in result.get("warnings") or [])
        message = f"字幕模板无效: {warnings}" if warnings else "字幕模板无效"
        raise SubtitleTemplateInvalidError(message)

    template_id = _required_template_text(normalized, "id")
    template_name = _required_template_text(normalized, "name")
    normalized.setdefault("template_variants", {})
    font_family = _optional_text(options.get("subtitle_font_family"))
    snapshot_with_font = _override_subtitle_template_font_family(
        normalized,
        font_family,
    )

    return {
        "subtitle_enabled": True,
        "subtitle_template_set_id": template_id,
        "subtitle_template_set_name": template_name,
        "subtitle_template_snapshot": snapshot_with_font,
        "subtitle_font_family": font_family,
    }


def normalize_voice_options(options: dict[str, Any]) -> dict[str, Any]:
    provider = _optional_text(options.get("voice_provider"))
    if provider and provider != "edge_tts":
        raise VoiceProviderInvalidError(provider)

    voice_id = _optional_text(options.get("voice_id"))
    if not voice_id:
        return {
            "voice_id": None,
            "voice_name": None,
            "voice_provider": None,
            "voice_locale": None,
            "voice_gender": None,
        }

    return {
        "voice_id": voice_id,
        "voice_name": _optional_text(options.get("voice_name")),
        "voice_provider": provider or "edge_tts",
        "voice_locale": _optional_text(options.get("voice_locale")),
        "voice_gender": _optional_text(options.get("voice_gender")),
    }


def normalize_bgm_options(
    store: AutoVideoStore,
    options: dict[str, Any],
) -> dict[str, Any]:
    if not bool(options.get("bgm_enabled")):
        return _disabled_bgm_options()

    track_id = _optional_text(options.get("bgm_track_id"))
    category_id = _optional_text(options.get("bgm_category_id"))
    if not track_id and not category_id:
        return _disabled_bgm_options()

    service = BgmLibraryService(store.settings)
    try:
        track = (
            service.get_track(track_id)
            if track_id
            else service.select_track_for_category(category_id)
        )
        snapshot = service.track_snapshot(str(track["id"]))
    except BgmTrackNotFoundError as exc:
        raise BgmOptionInvalidError("BGM_TRACK_NOT_FOUND") from exc
    except BgmCategoryNotFoundError as exc:
        raise BgmOptionInvalidError("BGM_CATEGORY_NOT_FOUND") from exc
    except BgmCategoryEmptyError as exc:
        raise BgmOptionInvalidError("BGM_CATEGORY_EMPTY") from exc

    volume = _optional_float(options.get("bgm_volume"))
    if volume is None:
        volume = 0.12
    volume = min(1.0, max(0.0, volume))

    return {
        "bgm_enabled": True,
        "bgm_track_id": str(track["id"]),
        "bgm_display_name": track.get("display_name"),
        "bgm_category_id": track.get("category_id"),
        "bgm_category_name": track.get("category_name"),
        "bgm_volume": volume,
        "bgm_snapshot": snapshot,
        "bgm_mix_status": "selected_not_mixed",
    }


def _disabled_bgm_options() -> dict[str, Any]:
    return {
        "bgm_enabled": False,
        "bgm_track_id": None,
        "bgm_display_name": None,
        "bgm_category_id": None,
        "bgm_category_name": None,
        "bgm_volume": None,
        "bgm_snapshot": None,
        "bgm_mix_status": "not_requested",
    }


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _required_template_text(template_set: dict[str, Any], field: str) -> str:
    value = template_set.get(field)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise SubtitleTemplateInvalidError(f"字幕模板缺少 {field}")


def _override_subtitle_template_font_family(
    template_set: dict[str, Any],
    font_family: str | None,
) -> dict[str, Any]:
    normalized = copy.deepcopy(template_set)
    if not font_family:
        return normalized

    templates = normalized.get("templates")
    if isinstance(templates, dict):
        for template in templates.values():
            if isinstance(template, dict):
                template["font_family"] = font_family

    _override_subtitle_blocks_font_family(normalized.get("blocks"), font_family)
    _override_subtitle_variants_font_family(
        normalized.get("template_variants"),
        font_family,
    )
    return normalized


def _override_subtitle_blocks_font_family(blocks: Any, font_family: str) -> None:
    if not isinstance(blocks, list):
        return
    for block in blocks:
        if not isinstance(block, dict):
            continue
        style = block.get("style")
        if not isinstance(style, dict):
            style = {}
            block["style"] = style
        style["font_family"] = font_family


def _override_subtitle_variants_font_family(value: Any, font_family: str) -> None:
    if isinstance(value, list):
        for item in value:
            _override_subtitle_variants_font_family(item, font_family)
        return

    if not isinstance(value, dict):
        return

    template = value.get("template")
    if isinstance(template, dict):
        template["font_family"] = font_family
    _override_subtitle_blocks_font_family(value.get("blocks"), font_family)

    for item in value.values():
        if item is template:
            continue
        _override_subtitle_variants_font_family(item, font_family)


def _material_source_for_manifest_shots(manifest_shots: list[dict[str, Any]]) -> str:
    has_online = any(bool(item.get("provider")) for item in manifest_shots)
    has_local = any(not item.get("provider") for item in manifest_shots)
    if has_online and has_local:
        return "hybrid"
    if has_online:
        return "online"
    return "local"


def _material_paths_for_manifest_shots(
    manifest_shots: list[dict[str, Any]],
    materials_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    paths: list[str] = []
    for item in manifest_shots:
        material_id = item.get("material_id")
        material = (
            materials_by_id.get(str(material_id))
            if material_id is not None
            else None
        )
        path = material.get("storage_path") if isinstance(material, dict) else None
        paths.append(str(path) if path is not None else "")
    return paths


def _render_plan_from_result(
    render_result: Any,
    source_subtitle_masks: list[bool],
) -> dict[str, Any]:
    return {
        "status": render_result.status,
        "renderer": render_result.renderer,
        "output": (
            render_result.output_path.name
            if render_result.output_path is not None
            else None
        ),
        "base_output": render_result.base_output_path,
        "timeline": render_result.timeline_path,
        "subtitles": render_result.subtitles_path,
        "subtitles_ass": render_result.subtitles_ass_path,
        "base_video_skipped": render_result.base_video_skipped,
        "subtitle_burn_skipped": render_result.subtitle_burn_skipped,
        "error_summary": _sanitize_render_error_summary(
            render_result.error_summary
        ),
        "source_subtitle_masked": any(source_subtitle_masks),
        "source_subtitle_mask_count": sum(
            1 for item in source_subtitle_masks if item
        ),
        "source_subtitle_masks": source_subtitle_masks,
    }


def _sanitize_render_error_summary(error_summary: str | None) -> str | None:
    if not error_summary:
        return error_summary
    if RENDER_ERROR_SENSITIVE_FRAGMENT_RE.search(error_summary):
        return "[redacted]"
    sanitized = sanitize_manifest_payload(error_summary)
    return sanitized if isinstance(sanitized, str) else ""


def _render_online_mix_output_builder(
    *,
    store: AutoVideoStore,
    title: str,
    script: dict[str, Any],
    manifest_shots: list[dict[str, Any]],
    materials_by_id: dict[str, dict[str, Any]],
    options: dict[str, Any],
    subtitle_options: dict[str, Any],
):
    def build(output_payload: dict[str, Any], output_dir: Any):
        timeline = build_render_timeline(
            title=title,
            script=script,
            shot_materials=manifest_shots,
        )
        safe_timeline = sanitize_render_timeline(timeline)
        output_payload["timeline"] = safe_timeline
        write_timeline_artifacts(output_dir, safe_timeline)
        subtitle_enabled = bool(subtitle_options.get("subtitle_enabled"))
        material_paths = _material_paths_for_manifest_shots(
            manifest_shots,
            materials_by_id,
        )
        source_subtitle_masks = build_source_subtitle_masks(
            _material_source_for_manifest_shots(manifest_shots),
            material_paths,
            subtitle_enabled=subtitle_enabled,
        )
        render_result = render_mix_video(
            settings=store.settings,
            output_dir=output_dir,
            timeline=safe_timeline,
            materials_by_id=materials_by_id,
            aspect_ratio=str(
                options.get("aspect_ratio") or script.get("aspect_ratio") or "9:16"
            ),
            subtitle_enabled=subtitle_enabled,
            subtitle_template_set=subtitle_options.get("subtitle_template_snapshot"),
            source_subtitle_masks=source_subtitle_masks,
        )
        output_payload["render_plan"] = _render_plan_from_result(
            render_result,
            source_subtitle_masks,
        )
        return render_result.output_path

    return build


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

    user_materials: dict[str, dict[str, Any]] = {}
    for item in shot_materials:
        material_id = str(item.get("material_id", ""))
        material = store.get_material(material_id)
        if material is None:
            raise MaterialNotFoundError(material_id)
        user_materials[material_id] = material

    used_online_assets: set[tuple[str, str]] = set()
    for material in user_materials.values():
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

    validate_manual_shot_coverage(
        script,
        shot_assets,
        shot_materials,
        asset_strategy,
    )
    subtitle_options = normalize_subtitle_options(store, options)
    voice_options = normalize_voice_options(options)
    bgm_options = normalize_bgm_options(store, options)

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
    materials_by_id: dict[str, dict[str, Any]] = {}
    source_attribution_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for selection in sorted(resolved_materials, key=lambda value: int(value["shot_index"])):
        material_id = str(selection["material_id"])
        material = store.get_material(material_id)
        if material is None:
            raise MaterialNotFoundError(material_id)
        material_ids.append(material_id)
        materials_by_id[material_id] = material
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

    sanitized_options = sanitized_online_mix_options(
        {**options, **subtitle_options, **voice_options, **bgm_options}
    )

    return create_task(
        store,
        title=title,
        material_ids=material_ids,
        options=sanitized_options,
        manifest_payload={
            "script": script,
            "shot_materials": manifest_shots,
            "source_attribution": list(source_attribution_by_key.values()),
            "render_plan": {
                "status": "manifest_only",
                "renderer": "not_enabled",
            },
            "subtitle_enabled": subtitle_options["subtitle_enabled"],
            "subtitle_template_set_id": subtitle_options["subtitle_template_set_id"],
            "subtitle_template_set_name": subtitle_options["subtitle_template_set_name"],
            "subtitle_template_snapshot": subtitle_options["subtitle_template_snapshot"],
            "subtitle_font_family": subtitle_options["subtitle_font_family"],
            "voice_id": voice_options["voice_id"],
            "voice_name": voice_options["voice_name"],
            "voice_provider": voice_options["voice_provider"],
            "voice_locale": voice_options["voice_locale"],
            "voice_gender": voice_options["voice_gender"],
            "bgm_enabled": bgm_options["bgm_enabled"],
            "bgm_track_id": bgm_options["bgm_track_id"],
            "bgm_display_name": bgm_options["bgm_display_name"],
            "bgm_category_id": bgm_options["bgm_category_id"],
            "bgm_category_name": bgm_options["bgm_category_name"],
            "bgm_volume": bgm_options["bgm_volume"],
            "bgm_snapshot": bgm_options["bgm_snapshot"],
            "bgm_mix_status": bgm_options["bgm_mix_status"],
            "provider_status_snapshot": provider_status_snapshot,
        },
        output_builder=_render_online_mix_output_builder(
            store=store,
            title=title,
            script=script,
            manifest_shots=manifest_shots,
            materials_by_id=materials_by_id,
            options=options,
            subtitle_options=subtitle_options,
        ),
    )
