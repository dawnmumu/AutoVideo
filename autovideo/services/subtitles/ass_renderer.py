from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from autovideo.services.subtitles.models import TEMPLATE_ROLES
from autovideo.services.subtitles.timeline import SubtitleEvent

DEFAULT_STYLE = {
    "font_family": "PingFang SC",
    "font_size": 54,
    "primary_color": "#FFFFFF",
    "outline_color": "#000000",
    "outline_width": 3,
    "shadow_color": "#000000",
    "shadow_depth": 2,
    "margin_v": 60,
    "rotate": 0,
}
STYLE_FORMAT = (
    "Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
    "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
    "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
)
EVENT_FORMAT = "Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"


def write_ass_file(
    path: str | Path,
    events: list[SubtitleEvent],
    template_set: dict[str, Any],
    resolution: tuple[int, int],
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_ass(events, template_set, resolution), encoding="utf-8")
    return output_path


def render_ass(
    events: list[SubtitleEvent],
    template_set: dict[str, Any],
    resolution: tuple[int, int],
) -> str:
    width, height = resolution
    dialogue_ranges = _monotonic_dialogue_ranges(events)
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {int(width)}",
        f"PlayResY: {int(height)}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        f"Format: {STYLE_FORMAT}",
    ]
    lines.extend(_style_line(role, _template_style(template_set, role)) for role in TEMPLATE_ROLES)
    lines.extend(
        [
            "",
            "[Events]",
            f"Format: {EVENT_FORMAT}",
        ]
    )
    lines.extend(_dialogue_line(event, resolution, dialogue_ranges[index]) for index, event in enumerate(events))
    return "\n".join(lines) + "\n"


def _template_style(template_set: dict[str, Any], role: str) -> dict[str, Any]:
    templates = template_set.get("templates") if isinstance(template_set, dict) else {}
    style = templates.get(role) if isinstance(templates, dict) else {}
    if not isinstance(style, dict):
        style = {}
    merged = {**DEFAULT_STYLE, **style}
    if "shadow" in style and "shadow_depth" not in style:
        merged["shadow_depth"] = style["shadow"]
    return merged


def _style_line(role: str, style: dict[str, Any]) -> str:
    font_size = _scaled_font_size(style)
    outline = _number(_non_negative_numeric(style.get("outline_width"), DEFAULT_STYLE["outline_width"]))
    shadow = _number(
        _non_negative_numeric(style.get("shadow_depth", style.get("shadow")), DEFAULT_STYLE["shadow_depth"])
    )
    angle = _number(style.get("rotate", DEFAULT_STYLE["rotate"]))
    margin_v = int(_non_negative_numeric(style.get("margin_v"), DEFAULT_STYLE["margin_v"]))

    fields = [
        role,
        str(style.get("font_family") or DEFAULT_STYLE["font_family"]),
        str(font_size),
        _ass_color(style.get("primary_color"), DEFAULT_STYLE["primary_color"]),
        "&H000000FF",
        _ass_color(style.get("outline_color"), DEFAULT_STYLE["outline_color"]),
        _ass_color(style.get("shadow_color"), DEFAULT_STYLE["shadow_color"]),
        "0",
        "0",
        "0",
        "0",
        "100",
        "100",
        "0",
        angle,
        "1",
        outline,
        shadow,
        "2",
        "60",
        "60",
        str(margin_v),
        "1",
    ]
    return "Style: " + ",".join(fields)


def _dialogue_line(
    event: SubtitleEvent,
    resolution: tuple[int, int],
    time_range: tuple[int, int],
) -> str:
    event_font_size = _event_font_size(event)
    override_tags = _event_override_tags(event, resolution, event_font_size)
    text = _render_text(event.text, event.spans, reset_tags=override_tags, base_font_size=event_font_size)
    if override_tags:
        text = f"{override_tags}{text}"
    start_text, end_text = (_format_ass_centiseconds(time_range[0]), _format_ass_centiseconds(time_range[1]))
    margin_v = _event_margin_v(event)
    return (
        f"Dialogue: 0,{start_text},{end_text},"
        f"{event.template},,0,0,{margin_v},,{text}"
    )


def _monotonic_dialogue_ranges(events: list[SubtitleEvent]) -> dict[int, tuple[int, int]]:
    ranges: dict[int, tuple[int, int]] = {}
    grouped_indexes: dict[str, list[int]] = {}
    for index, event in enumerate(events):
        grouped_indexes.setdefault(event.track_id, []).append(index)

    for indexes in grouped_indexes.values():
        previous_end_cs = 0
        for index in sorted(indexes, key=lambda item: (events[item].start_ms, events[item].index, item)):
            event = events[index]
            raw_start_cs, raw_end_cs = _raw_ass_centisecond_range(event.start_ms, event.end_ms)
            start_cs = max(raw_start_cs, previous_end_cs)
            end_cs = max(raw_end_cs, start_cs + 1)
            ranges[index] = (start_cs, end_cs)
            previous_end_cs = end_cs

    return ranges


def _event_override_tags(event: SubtitleEvent, resolution: tuple[int, int], event_font_size: int) -> str:
    tags: list[str] = []
    style = event.style if isinstance(event.style, dict) else {}
    position = event.position if isinstance(event.position, dict) else {}

    if any(key in style for key in ("font_size", "font_size_scale", "font_scale")):
        tags.append(f"\\fs{event_font_size}")

    primary_color = style.get("primary_color")
    if isinstance(primary_color, str) and _is_hex_color(primary_color.strip()):
        tags.append(f"\\c{_inline_color(primary_color)}")

    outline_width = _non_negative_numeric(style.get("outline_width")) if "outline_width" in style else None
    if outline_width is not None:
        tags.append(f"\\bord{_format_coordinate(outline_width)}")

    outline_color = style.get("outline_color")
    if isinstance(outline_color, str) and _is_hex_color(outline_color.strip()):
        tags.append(f"\\3c{_inline_color(outline_color)}")

    shadow_source = style.get("shadow_depth") if "shadow_depth" in style else style.get("shadow")
    shadow_depth = _non_negative_numeric(shadow_source) if ("shadow_depth" in style or "shadow" in style) else None
    if shadow_depth is not None:
        tags.append(f"\\shad{_format_coordinate(shadow_depth)}")

    shadow_color = style.get("shadow_color")
    if isinstance(shadow_color, str) and _is_hex_color(shadow_color.strip()):
        tags.append(f"\\4c{_inline_color(shadow_color)}")

    rotate = _optional_numeric(style.get("rotate")) if "rotate" in style else None
    if rotate is not None:
        tags.append(f"\\frz{_format_coordinate(rotate)}")

    position_tag = _position_tag(position, resolution)
    if position_tag:
        tags.append(position_tag)

    return "{" + "".join(tags) + "}" if tags else ""


def _event_margin_v(event: SubtitleEvent) -> str:
    style = event.style if isinstance(event.style, dict) else {}
    if "margin_v" not in style:
        return "0"
    margin_v = _non_negative_numeric(style.get("margin_v"))
    if margin_v is None:
        return "0"
    return str(int(margin_v))


def _position_tag(position: dict[str, Any], resolution: tuple[int, int]) -> str:
    x = _optional_numeric(position.get("x"))
    y = _optional_numeric(position.get("y"))
    if x is None or y is None:
        return ""

    width, height = resolution
    x_value = x * width if 0 <= x <= 1 else x
    y_value = y * height if 0 <= y <= 1 else y
    return f"\\pos({_format_coordinate(x_value)},{_format_coordinate(y_value)})"


def _render_text(
    text: str,
    spans: list[dict[str, Any]],
    *,
    reset_tags: str = "",
    base_font_size: int = DEFAULT_STYLE["font_size"],
) -> str:
    selected_ranges: list[tuple[int, int, str]] = []
    for span in spans:
        if not isinstance(span, dict):
            continue
        selector = span.get("selector")
        style = span.get("style")
        if not isinstance(selector, dict) or selector.get("type") != "keyword" or not isinstance(style, dict):
            continue

        keyword = selector.get("value")
        span_tags = _span_override_tags(style, base_font_size)
        if not isinstance(keyword, str) or not keyword or not span_tags:
            continue

        match_range = _find_first_available_range(text, keyword, selected_ranges)
        if match_range is None:
            continue
        selected_ranges.append((match_range[0], match_range[1], span_tags))

    if not selected_ranges:
        return _escape_ass_text(text)

    rendered_parts: list[str] = []
    cursor = 0
    for start, end, span_tags in sorted(selected_ranges, key=lambda item: item[0]):
        rendered_parts.append(_escape_ass_text(text[cursor:start]))
        rendered_parts.append(f"{{{span_tags}}}{_escape_ass_text(text[start:end])}{{\\r}}{reset_tags}")
        cursor = end

    rendered_parts.append(_escape_ass_text(text[cursor:]))
    return "".join(rendered_parts)


def _span_override_tags(style: dict[str, Any], base_font_size: int) -> str:
    tags: list[str] = []

    primary_color = style.get("primary_color")
    if isinstance(primary_color, str) and _is_hex_color(primary_color.strip()):
        tags.append(f"\\c{_inline_color(primary_color)}")

    if "font_size" in style:
        font_size = _positive_numeric(style.get("font_size"))
        if font_size is not None:
            tags.append(f"\\fs{max(1, int(font_size))}")
    elif "font_scale" in style:
        font_scale = _positive_numeric(style.get("font_scale"))
        if font_scale is not None:
            tags.append(f"\\fs{max(1, int(base_font_size * font_scale))}")

    return "".join(tags)


def _find_first_available_range(
    text: str,
    keyword: str,
    selected_ranges: list[tuple[int, int, str]],
) -> tuple[int, int] | None:
    start = text.find(keyword)
    while start != -1:
        end = start + len(keyword)
        if not _overlaps_selected_range(start, end, selected_ranges):
            return (start, end)
        start = text.find(keyword, start + 1)
    return None


def _overlaps_selected_range(start: int, end: int, selected_ranges: list[tuple[int, int, str]]) -> bool:
    return any(start < selected_end and end > selected_start for selected_start, selected_end, _color in selected_ranges)


def _scaled_font_size(style: dict[str, Any]) -> int:
    font_size = _positive_numeric(style.get("font_size"), DEFAULT_STYLE["font_size"])
    scale = style.get("font_size_scale", style.get("font_scale", 1))
    return max(1, int(font_size * _positive_numeric(scale, 1)))


def _event_font_size(event: SubtitleEvent) -> int:
    style = event.style if isinstance(event.style, dict) else {}
    return _scaled_font_size(style)


def _numeric(value: Any, default: int | float) -> int | float:
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        if not math.isfinite(value):
            return default
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return default
        try:
            number = float(candidate)
        except ValueError:
            return default
        if not math.isfinite(number):
            return default
        return int(number) if number.is_integer() else number
    return default


def _optional_numeric(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        if not math.isfinite(value):
            return None
        return value
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


def _positive_numeric(value: Any, default: int | float | None = None) -> int | float | None:
    number = _optional_numeric(value)
    if number is None or number <= 0:
        return default
    return number


def _non_negative_numeric(value: Any, default: int | float | None = None) -> int | float | None:
    number = _optional_numeric(value)
    if number is None or number < 0:
        return default
    return number


def _format_coordinate(value: int | float) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


def _number(value: Any) -> str:
    return f"{_numeric(value, 0):g}"


def _ass_color(value: Any, default: str) -> str:
    rgb = _rgb(value if isinstance(value, str) else default, default)
    return f"&H00{rgb[2]}{rgb[1]}{rgb[0]}"


def _inline_color(value: str) -> str:
    rgb = _rgb(value, "#FFFFFF")
    return f"&H{rgb[2]}{rgb[1]}{rgb[0]}&"


def _rgb(value: str, default: str) -> tuple[str, str, str]:
    candidate = value.strip()
    if not _is_hex_color(candidate):
        candidate = default
    return (candidate[1:3].upper(), candidate[3:5].upper(), candidate[5:7].upper())


def _is_hex_color(value: str) -> bool:
    return len(value) == 7 and value.startswith("#") and all(char in "0123456789abcdefABCDEF" for char in value[1:])


def _raw_ass_centisecond_range(start_ms: int, end_ms: int) -> tuple[int, int]:
    start_cs = max(0, int(math.floor(start_ms / 10)))
    end_cs = max(0, int(math.ceil(end_ms / 10)))
    if end_cs <= start_cs:
        end_cs = start_cs + 1
    return (start_cs, end_cs)


def _format_ass_centiseconds(centiseconds: int) -> str:
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"


def _escape_ass_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\r\n", "\\N")
        .replace("\n", "\\N")
        .replace("\r", "\\N")
    )
