from __future__ import annotations

import copy
import math
from typing import Any

from autovideo.services.subtitles.models import (
    DEFAULT_TRACK,
    RENDERER_MODE,
    SCHEMA_VERSION,
    TEMPLATE_ROLES,
)

SUPPORTED_TOP_LEVEL_FIELDS = {
    "id",
    "name",
    "created_at",
    "updated_at",
    "is_builtin",
    "is_modified",
    "is_favorite",
    "favorite",
    "preset_id",
    "schema_version",
    "renderer_mode",
    "tracks",
    "blocks",
    "templates",
    "template_variants",
}

ADVANCED_BLOCK_FIELDS = {
    "mask",
    "filter",
    "filters",
    "blend",
    "keyframes",
    "cue_points",
    "layers",
}

SUPPORTED_STYLE_FIELDS = {
    "font_family",
    "font_size",
    "primary_color",
    "accent_color",
    "outline_color",
    "outline_width",
    "shadow_color",
    "shadow_depth",
    "shadow",
    "font_size_scale",
    "font_scale",
    "margin_v",
    "max_width",
    "rotate",
    "skew",
}

NUMERIC_STYLE_FIELDS = {
    "font_size",
    "outline_width",
    "shadow_depth",
    "shadow",
    "font_size_scale",
    "font_scale",
    "margin_v",
    "max_width",
    "rotate",
    "skew",
}

DEFAULT_TEMPLATE_STYLE = {
    "font_family": "PingFang SC",
    "font_size": 54,
    "primary_color": "#FFFFFF",
    "outline_color": "#111827",
    "outline_width": 3,
    "shadow_color": "#000000",
    "shadow_depth": 2,
}


def validate_template_set_v2(payload: Any) -> dict[str, Any]:
    warnings: list[str] = []
    if not isinstance(payload, dict):
        warnings.append("payload must be an object")
        return {"ok": False, "normalized": None, "warnings": warnings}

    normalized = normalize_template_set_v2(payload, warnings=warnings)
    return {"ok": True, "normalized": normalized, "warnings": warnings}


def normalize_template_set_v2(payload: Any, warnings: list[str] | None = None) -> dict[str, Any]:
    warning_list = warnings if warnings is not None else []
    source = payload if isinstance(payload, dict) else {}

    for field in source:
        if field not in SUPPORTED_TOP_LEVEL_FIELDS:
            warning_list.append(f"Unsupported top-level field ignored: {field}")

    normalized: dict[str, Any] = {}
    for field in (
        "id",
        "name",
        "created_at",
        "updated_at",
        "is_builtin",
        "is_modified",
        "is_favorite",
        "favorite",
        "preset_id",
    ):
        if field in source:
            normalized[field] = copy.deepcopy(source[field])

    normalized["schema_version"] = SCHEMA_VERSION
    normalized["renderer_mode"] = source.get("renderer_mode") or RENDERER_MODE
    normalized["tracks"] = _normalize_tracks(source.get("tracks"))
    normalized["blocks"] = _normalize_blocks(source.get("blocks"), warning_list)

    templates = copy.deepcopy(source.get("templates")) if isinstance(source.get("templates"), dict) else {}
    templates.update(compile_v2_blocks_to_legacy_templates(normalized["blocks"]))
    normalized["templates"] = templates

    if "template_variants" in source and isinstance(source["template_variants"], dict):
        normalized["template_variants"] = copy.deepcopy(source["template_variants"])
    elif "template_variants" in source:
        normalized["template_variants"] = {}

    return normalized


def _normalize_tracks(value: Any) -> list[dict[str, Any]]:
    tracks = value if isinstance(value, list) else []
    normalized = [copy.deepcopy(track) for track in tracks if isinstance(track, dict)]
    return normalized or [copy.deepcopy(DEFAULT_TRACK)]


def _normalize_blocks(value: Any, warnings: list[str] | None = None) -> list[dict[str, Any]]:
    warning_list = warnings if warnings is not None else []
    blocks = value if isinstance(value, list) else []
    normalized: list[dict[str, Any]] = []

    for index, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue

        role = _normalize_role(block.get("role", "bottom"))
        if role not in TEMPLATE_ROLES:
            warning_list.append(f"Block {block.get('id') or index + 1} has unsupported role: {block.get('role')!r}")
            continue

        item: dict[str, Any] = {"role": role}
        for field, field_value in block.items():
            if field == "role":
                continue
            if field == "style":
                item["style"] = _normalize_style(field_value, warning_list, context=f"block {block.get('id') or index + 1}")
            elif field == "spans":
                item["spans"] = _normalize_spans(field_value, warning_list)
            else:
                item[field] = copy.deepcopy(field_value)

        if "id" not in item:
            item["id"] = f"{item['role']}-{index + 1}"
        if "track_id" not in item:
            item["track_id"] = "main"
        if "style" not in item:
            item["style"] = {}
        if "spans" not in item:
            item["spans"] = []

        for advanced_field in ADVANCED_BLOCK_FIELDS:
            if advanced_field in block:
                warning_list.append(
                    f"Block {item['id']} uses advanced field '{advanced_field}' not supported by current renderer"
                )

        normalized.append(item)

    return normalized


def _normalize_spans(value: Any, warnings: list[str] | None = None) -> list[dict[str, Any]]:
    warning_list = warnings if warnings is not None else []
    spans = value if isinstance(value, list) else []
    normalized: list[dict[str, Any]] = []

    for index, span in enumerate(spans):
        if not isinstance(span, dict):
            continue

        item = copy.deepcopy(span)
        if "style" in item:
            item["style"] = _normalize_style(item["style"], warning_list, context=f"span {index + 1}")
        normalized.append(item)

    return normalized


def _normalize_style(value: Any, warnings: list[str] | None = None, *, context: str = "style") -> dict[str, Any]:
    warning_list = warnings if warnings is not None else []
    style = value if isinstance(value, dict) else {}
    normalized: dict[str, Any] = {}

    for field in SUPPORTED_STYLE_FIELDS:
        if field not in style:
            continue

        if field in NUMERIC_STYLE_FIELDS:
            numeric_value = _coerce_number(style[field])
            if numeric_value is None:
                warning_list.append(f"Invalid numeric style field '{field}' in {context}; ignored")
                continue
            normalized[field] = numeric_value
        else:
            normalized[field] = copy.deepcopy(style[field])

    return normalized


def _normalize_role(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _coerce_number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        if math.isfinite(value):
            return value
        return None
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            number = float(candidate)
        except ValueError:
            return None
        if not math.isfinite(number):
            return None
        return int(number) if number.is_integer() else number
    return None


def compile_v2_blocks_to_legacy_templates(blocks: Any) -> dict[str, dict[str, Any]]:
    templates: dict[str, dict[str, Any]] = {}
    source_blocks = blocks if isinstance(blocks, list) else []

    for block in source_blocks:
        if not isinstance(block, dict):
            continue

        role = block.get("role")
        if role not in TEMPLATE_ROLES:
            continue

        style = copy.deepcopy(block.get("style")) if isinstance(block.get("style"), dict) else {}
        template = {**DEFAULT_TEMPLATE_STYLE, **style}
        if "shadow_depth" not in style:
            template["shadow_depth"] = style.get("shadow", DEFAULT_TEMPLATE_STYLE["shadow_depth"])
        templates[role] = template

    return templates
