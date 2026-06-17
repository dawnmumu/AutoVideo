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

ALLOWED_BLOCK_FIELDS = {
    "id",
    "role",
    "track_id",
    "position",
    "style",
    "spans",
    "animations",
}

SUPPORTED_STYLE_FIELDS = {
    "template_type",
    "font_family",
    "font_size",
    "primary_color",
    "accent_color",
    "outline_color",
    "outline_width",
    "shadow_color",
    "shadow_depth",
    "shadow",
    "position",
    "alignment",
    "x_percent",
    "y_percent",
    "angle",
    "font_size_scale",
    "font_scale",
    "font_weight",
    "italic",
    "letter_spacing",
    "line_spacing",
    "margin_l",
    "margin_r",
    "margin_v",
    "max_width",
    "max_width_ratio",
    "max_chars_per_line",
    "max_lines",
    "rotate",
    "skew",
    "skew_x_deg",
    "skew_y_deg",
    "bottom_safe_area_ratio",
    "fade_in_ms",
    "fade_out_ms",
    "decoration_shape",
}

NUMERIC_STYLE_FIELDS = {
    "font_size",
    "outline_width",
    "shadow_depth",
    "shadow",
    "x_percent",
    "y_percent",
    "angle",
    "font_size_scale",
    "font_scale",
    "font_weight",
    "letter_spacing",
    "line_spacing",
    "margin_l",
    "margin_r",
    "margin_v",
    "max_width",
    "max_width_ratio",
    "max_chars_per_line",
    "max_lines",
    "rotate",
    "skew",
    "skew_x_deg",
    "skew_y_deg",
    "bottom_safe_area_ratio",
    "fade_in_ms",
    "fade_out_ms",
}

DEFAULT_TEMPLATE_STYLE = {
    "template_type": "bottom",
    "font_family": "Noto Sans CJK SC",
    "font_size": 54,
    "font_weight": 700,
    "font_scale": 1.0,
    "italic": False,
    "letter_spacing": 0,
    "line_spacing": 1.15,
    "primary_color": "#FFFFFF",
    "accent_color": "#FFD54F",
    "outline_color": "#111111",
    "outline_width": 3,
    "shadow_color": "#000000",
    "shadow_depth": 2,
    "position": "bottom",
    "alignment": "center",
    "margin_l": 60,
    "margin_r": 60,
    "margin_v": 80,
    "x_percent": 50,
    "y_percent": 78,
    "angle": 0,
    "bottom_safe_area_ratio": 0.22,
    "max_chars_per_line": 16,
    "max_lines": 3,
    "max_width_ratio": 0.9,
    "fade_in_ms": 80,
    "fade_out_ms": 80,
    "decoration_shape": "none",
}


def validate_template_set_v2(payload: Any) -> dict[str, Any]:
    warnings: list[str] = []
    if not isinstance(payload, dict):
        warnings.append("payload must be an object")
        return {"ok": False, "normalized": None, "warnings": warnings}

    if not _top_level_metadata_is_valid(payload, warnings):
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
    normalized["renderer_mode"] = _normalize_renderer_mode(source, warning_list)
    normalized["tracks"] = _normalize_tracks(source.get("tracks"))
    normalized["blocks"] = _normalize_blocks(source.get("blocks"), warning_list)

    templates = _normalize_legacy_templates(source.get("templates"), warning_list) if "templates" in source else {}
    templates.update(compile_v2_blocks_to_legacy_templates(normalized["blocks"]))
    normalized["templates"] = templates

    if "template_variants" in source and isinstance(source["template_variants"], dict):
        normalized["template_variants"] = copy.deepcopy(source["template_variants"])
    elif "template_variants" in source:
        normalized["template_variants"] = {}

    return normalized


def _top_level_metadata_is_valid(source: dict[str, Any], warnings: list[str]) -> bool:
    is_valid = True

    for field in ("id", "name", "created_at", "updated_at", "preset_id"):
        if field not in source:
            continue
        value = source[field]
        if not isinstance(value, str):
            warnings.append(f"Invalid top-level field '{field}'; expected string")
            is_valid = False
            continue
        if field in {"id", "name", "preset_id"} and not value.strip():
            warnings.append(f"Invalid top-level field '{field}'; expected non-empty string")
            is_valid = False

    for field in ("is_builtin", "is_modified", "is_favorite", "favorite"):
        if field in source and not isinstance(source[field], bool):
            warnings.append(f"Invalid top-level field '{field}'; expected boolean")
            is_valid = False

    return is_valid


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
            if field in ADVANCED_BLOCK_FIELDS:
                warning_list.append(
                    f"Block {block.get('id') or index + 1} uses advanced field '{field}' not supported by current renderer"
                )
                continue
            if field not in ALLOWED_BLOCK_FIELDS:
                warning_list.append(f"Block {block.get('id') or index + 1} has unknown block field '{field}' ignored")
                continue
            if field == "style":
                item["style"] = _normalize_style(field_value, warning_list, context=f"block {block.get('id') or index + 1}")
            elif field == "spans":
                item["spans"] = _normalize_spans(field_value, warning_list)
            elif field in {"position", "animations"}:
                item[field] = _normalize_block_dict_field(
                    field_value,
                    warning_list,
                    field=field,
                    context=f"block {block.get('id') or index + 1}",
                )
            elif field in {"id", "track_id"}:
                item[field] = _normalize_string_field(
                    field_value,
                    warning_list,
                    field=field,
                    default="",
                    context=f"block {block.get('id') or index + 1}",
                )
            else:
                item[field] = copy.deepcopy(field_value)

        if not item.get("id"):
            item["id"] = f"{item['role']}-{index + 1}"
        if not item.get("track_id"):
            item["track_id"] = "main"
        if "style" not in item:
            item["style"] = {}
        if "spans" not in item:
            item["spans"] = []

        normalized.append(item)

    return normalized


def _normalize_block_dict_field(
    value: Any,
    warnings: list[str],
    *,
    field: str,
    context: str,
) -> dict[str, Any]:
    if isinstance(value, dict):
        return copy.deepcopy(value)

    warnings.append(f"Invalid block field '{field}' in {context}; expected object")
    return {}


def _normalize_string_field(
    value: Any,
    warnings: list[str],
    *,
    field: str,
    default: str,
    context: str,
) -> str:
    if isinstance(value, str):
        return value.strip()

    warnings.append(f"Invalid string field '{field}' in {context}; using default")
    return default


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


def _normalize_renderer_mode(source: dict[str, Any], warnings: list[str]) -> str:
    if "renderer_mode" not in source:
        return RENDERER_MODE

    value = source.get("renderer_mode")
    if isinstance(value, str) and value.strip():
        return value.strip()

    warnings.append("Invalid renderer_mode; using default renderer mode")
    return RENDERER_MODE


def _normalize_legacy_templates(value: Any, warnings: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        warnings.append("Invalid templates field; expected object")
        return {}

    templates: dict[str, dict[str, Any]] = {}
    for raw_role, raw_template in value.items():
        role = _normalize_role(raw_role)
        if role not in TEMPLATE_ROLES:
            warnings.append(f"Legacy template has unsupported role: {raw_role!r}")
            continue
        if not isinstance(raw_template, dict):
            warnings.append(f"Legacy template for role '{role}' must be an object; ignored")
            continue
        templates[role] = _normalize_style(raw_template, warnings, context=f"legacy template {role}")

    return templates


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
        template = {**DEFAULT_TEMPLATE_STYLE, "template_type": role, **style}
        if "shadow_depth" not in style:
            template["shadow_depth"] = style.get("shadow", DEFAULT_TEMPLATE_STYLE["shadow_depth"])
        if "max_width_ratio" not in style and "max_width" in style:
            template["max_width_ratio"] = style["max_width"]
        if "skew_x_deg" not in style and "skew" in style:
            template["skew_x_deg"] = style["skew"]
        if "font_scale" in style and "font_size_scale" not in style:
            template["font_size_scale"] = style["font_scale"]
        if "angle" not in style and "rotate" in style:
            template["angle"] = style["rotate"]
        _apply_position_to_template(template, block.get("position"), style_keys=set(style))
        templates[role] = template

    return templates


def _apply_position_to_template(template: dict[str, Any], position: Any, *, style_keys: set[str]) -> None:
    if not isinstance(position, dict):
        return

    x = _coerce_number(position.get("x"))
    y = _coerce_number(position.get("y"))
    if x is not None and "x_percent" not in style_keys:
        template["x_percent"] = _ratio_or_percent_to_percent(x)
    if y is not None and "y_percent" not in style_keys:
        template["y_percent"] = _ratio_or_percent_to_percent(y)

    anchor = position.get("anchor")
    if "alignment" not in style_keys and isinstance(anchor, str) and anchor.strip() in {"left", "center", "right"}:
        template["alignment"] = anchor.strip()
    if "position" not in style_keys:
        template["position"] = _position_from_y_percent(template.get("y_percent"))


def _ratio_or_percent_to_percent(value: int | float) -> int | float:
    percent = value * 100 if 0 <= value <= 1 else value
    bounded = max(0, min(100, percent))
    return int(bounded) if float(bounded).is_integer() else bounded


def _position_from_y_percent(value: Any) -> str:
    y_percent = _coerce_number(value)
    if y_percent is None:
        return str(DEFAULT_TEMPLATE_STYLE["position"])
    if y_percent <= 33:
        return "upper"
    if y_percent <= 66:
        return "center"
    return "bottom"
