from __future__ import annotations

import copy
from typing import Any

from autovideo.services.subtitles.timeline import SubtitleEvent


def enrich_subtitle_events(
    events: list[SubtitleEvent],
    template_set: dict[str, Any],
    resolution: tuple[int, int],
) -> list[SubtitleEvent]:
    del resolution

    enriched = copy.deepcopy(events)
    for event in enriched:
        block = _resolve_block(template_set, event)
        if block is None:
            continue

        track_id = block.get("track_id")
        if isinstance(track_id, str) and track_id.strip() and event.track_id == "main":
            event.track_id = track_id.strip()

        event.style = _merge_defaults(block.get("style"), event.style)
        event.position = _merge_defaults(block.get("position"), event.position)
        event.event_animations = _merge_defaults(block.get("animations"), event.event_animations)
        event.spans = _merge_spans(block.get("spans"), event.spans)

    return enriched


def _resolve_block(template_set: dict[str, Any], event: SubtitleEvent) -> dict[str, Any] | None:
    variant_block = _variant_block(template_set, event.template, event.template_variant)
    if variant_block is not None:
        return variant_block
    return _base_block(template_set, event.template)


def _base_block(template_set: dict[str, Any], role: str) -> dict[str, Any] | None:
    blocks = template_set.get("blocks") if isinstance(template_set, dict) else []
    if not isinstance(blocks, list):
        return None

    for block in blocks:
        if isinstance(block, dict) and block.get("role") == role:
            return block
    return None


def _variant_block(template_set: dict[str, Any], role: str, variant_id: str | None) -> dict[str, Any] | None:
    if not variant_id:
        return None

    variant = _find_variant(template_set, role, variant_id)
    if not isinstance(variant, dict):
        return None

    blocks = variant.get("blocks")
    if not isinstance(blocks, list):
        return None

    fallback: dict[str, Any] | None = None
    for block in blocks:
        if not isinstance(block, dict):
            continue
        fallback = fallback or block
        if block.get("role") == role:
            return block
    return fallback


def _find_variant(template_set: dict[str, Any], role: str, variant_id: str) -> dict[str, Any] | None:
    variants = template_set.get("template_variants") if isinstance(template_set, dict) else {}
    if not isinstance(variants, dict):
        return None

    role_variants = variants.get(role)
    if isinstance(role_variants, list):
        for variant in role_variants:
            if isinstance(variant, dict) and _variant_matches(variant, variant_id):
                return variant
        return None

    if isinstance(role_variants, dict):
        for key, variant in role_variants.items():
            if not isinstance(variant, dict):
                continue
            if str(key) == variant_id or _variant_matches(variant, variant_id):
                return variant

    return None


def _variant_matches(variant: dict[str, Any], variant_id: str) -> bool:
    for key in ("id", "key", "name"):
        value = variant.get(key)
        if isinstance(value, str) and value.strip() == variant_id:
            return True
    return False


def _merge_defaults(defaults: Any, current: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(defaults) if isinstance(defaults, dict) else {}
    merged.update(copy.deepcopy(current) if isinstance(current, dict) else {})
    return merged


def _merge_spans(default_spans: Any, current_spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    selector_indexes: dict[tuple[str, str], int] = {}

    for source_index, source in enumerate((default_spans, current_spans)):
        if not isinstance(source, list):
            continue
        for span in source:
            if not isinstance(span, dict):
                continue
            candidate = copy.deepcopy(span)
            selector_key = _span_selector_key(candidate)
            if selector_key is None:
                if candidate not in merged:
                    merged.append(candidate)
                continue

            if selector_key in selector_indexes:
                if source_index == 1:
                    merged[selector_indexes[selector_key]] = candidate
                continue

            selector_indexes[selector_key] = len(merged)
            merged.append(candidate)
    return merged


def _span_selector_key(span: dict[str, Any]) -> tuple[str, str] | None:
    selector = span.get("selector")
    if not isinstance(selector, dict):
        return None

    selector_type = selector.get("type")
    selector_value = selector.get("value")
    if not isinstance(selector_type, str) or not isinstance(selector_value, str):
        return None
    return (selector_type, selector_value)
