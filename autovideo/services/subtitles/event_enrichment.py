from __future__ import annotations

import copy
import math
from typing import Any

from autovideo.services.subtitles.timeline import SubtitleEvent

LAYOUT_STYLE_FIELDS = {"alignment", "position", "x_percent", "y_percent"}


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

        layout_style = _merge_defaults(_template_block_style(template_set, block, event.template), event.style)
        position_defaults = position_from_style_layout(layout_style, block.get("position"))
        event.style = _merge_defaults(block.get("style"), event.style)
        event.position = _merge_defaults(
            position_defaults if position_defaults is not None else block.get("position"),
            event.position,
        )
        event.event_animations = _merge_defaults(block.get("animations"), event.event_animations)
        event.spans = _merge_spans(block.get("spans"), event.spans)

    return enriched


def position_from_style_layout(style: Any, fallback_position: Any = None) -> dict[str, Any] | None:
    if not isinstance(style, dict) or not any(field in style for field in LAYOUT_STYLE_FIELDS):
        return None

    fallback = copy.deepcopy(fallback_position) if isinstance(fallback_position, dict) else {}
    position = fallback if isinstance(fallback, dict) else {}

    x = _percent_to_ratio(style.get("x_percent"))
    if x is not None:
        position["x"] = x
    elif "x" not in position:
        position["x"] = 0.5

    y = _percent_to_ratio(style.get("y_percent"))
    if y is not None:
        position["y"] = y
    elif "y" not in position:
        position["y"] = _fallback_y_for_position(style.get("position"))

    anchor = _anchor_from_alignment(style.get("alignment"))
    if anchor is not None:
        position["anchor"] = anchor
    elif "anchor" not in position:
        position["anchor"] = "center"

    return position


def _resolve_block(template_set: dict[str, Any], event: SubtitleEvent) -> dict[str, Any] | None:
    base_block = _base_block(template_set, event.template)
    variant_block = _variant_block(template_set, event.template, event.template_variant)
    return _merge_blocks(base_block, variant_block)


def _base_block(template_set: dict[str, Any], role: str) -> dict[str, Any] | None:
    blocks = template_set.get("blocks") if isinstance(template_set, dict) else []
    if not isinstance(blocks, list):
        return None

    for block in blocks:
        if isinstance(block, dict) and block.get("role") == role:
            return block
    return None


def _template_block_style(template_set: dict[str, Any], block: dict[str, Any], role: str) -> dict[str, Any]:
    style: dict[str, Any] = {}
    templates = template_set.get("templates") if isinstance(template_set, dict) else {}
    template = templates.get(block.get("role") or role) if isinstance(templates, dict) else None
    if isinstance(template, dict):
        style.update(copy.deepcopy(template))
    block_style = block.get("style")
    if isinstance(block_style, dict):
        style.update(copy.deepcopy(block_style))
    return style


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


def _merge_blocks(base_block: dict[str, Any] | None, variant_block: dict[str, Any] | None) -> dict[str, Any] | None:
    if base_block is None and variant_block is None:
        return None
    if base_block is None:
        return copy.deepcopy(variant_block)
    if variant_block is None:
        return copy.deepcopy(base_block)

    merged = copy.deepcopy(base_block)
    variant = copy.deepcopy(variant_block)
    for key, value in variant.items():
        if key in {"style", "position", "animations", "spans"}:
            continue
        merged[key] = value

    merged["style"] = _merge_defaults(base_block.get("style"), variant_block.get("style"))
    merged["position"] = _merge_defaults(base_block.get("position"), variant_block.get("position"))
    merged["animations"] = _merge_defaults(base_block.get("animations"), variant_block.get("animations"))
    merged["spans"] = _merge_spans(base_block.get("spans"), variant_block.get("spans"))
    return merged


def _merge_defaults(defaults: Any, current: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(defaults) if isinstance(defaults, dict) else {}
    if not isinstance(current, dict):
        return merged

    for key, value in current.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _merge_defaults(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _merge_spans(default_spans: Any, current_spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    selector_indexes: dict[tuple[str, str], int] = {}

    for source_index, source in enumerate((current_spans, default_spans)):
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
                if source_index == 0:
                    merged[selector_indexes[selector_key]] = candidate
                else:
                    index = selector_indexes[selector_key]
                    merged[index] = _merge_span_animation_default(candidate, merged[index])
                continue

            selector_indexes[selector_key] = len(merged)
            merged.append(candidate)
    return merged


def _merge_span_animation_default(default_span: dict[str, Any], current_span: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(current_span)
    default_animation = default_span.get("animation")
    if not isinstance(default_animation, dict):
        return merged

    current_animation = merged.get("animation")
    if isinstance(current_animation, dict):
        merged["animation"] = _merge_defaults(default_animation, current_animation)
    else:
        merged["animation"] = copy.deepcopy(default_animation)
    return merged


def _span_selector_key(span: dict[str, Any]) -> tuple[str, str] | None:
    selector = span.get("selector")
    if not isinstance(selector, dict):
        return None

    selector_type = selector.get("type")
    if not isinstance(selector_type, str):
        return None
    if selector_type == "range":
        start = _span_range_int(selector.get("start"))
        end = _span_range_int(selector.get("end"))
        if start is not None and end is not None:
            return (selector_type, f"{start}:{end}")
        return None

    selector_value = selector.get("value")
    if not isinstance(selector_value, str):
        return None
    return (selector_type, selector_value)


def _span_range_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            return None
        return int(value)
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
        if not math.isfinite(number):
            return None
        return int(number)
    return None


def _percent_to_ratio(value: Any) -> float | None:
    number = _finite_number(value)
    if number is None:
        return None
    return max(0, min(1, number / 100))


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            number = float(candidate)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _fallback_y_for_position(value: Any) -> float:
    position = str(value or "").strip()
    if position == "upper":
        return 0.25
    if position == "center":
        return 0.5
    return 0.78


def _anchor_from_alignment(value: Any) -> str | None:
    candidate = str(value or "").strip()
    return candidate if candidate in {"left", "center", "right"} else None
