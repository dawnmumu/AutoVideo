from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

from autovideo.services.subtitles.models import TEMPLATE_ROLES
from autovideo.services.subtitles.timeline import SubtitleEvent

DEFAULT_STYLE = {
    "font_family": "Noto Sans CJK SC",
    "font_size": 54,
    "primary_color": "#FFFFFF",
    "accent_color": "#FFD54F",
    "outline_color": "#000000",
    "outline_width": 3,
    "shadow_color": "#000000",
    "shadow_depth": 2,
    "font_weight": 700,
    "italic": False,
    "letter_spacing": 0,
    "line_spacing": 1.15,
    "margin_l": 60,
    "margin_r": 60,
    "margin_v": 80,
    "max_chars_per_line": 16,
    "max_lines": 3,
    "max_width_ratio": 0.9,
    "rotate": 0,
    "skew_x_deg": 0,
    "skew_y_deg": 0,
    "fade_in_ms": 80,
    "fade_out_ms": 80,
}
STYLE_FORMAT = (
    "Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
    "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
    "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
)
EVENT_FORMAT = "Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"


@dataclass(frozen=True)
class WrappedTextLine:
    text: str
    start: int


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
    if "shadow" in style:
        merged["shadow_depth"] = style["shadow"]
    return merged


def _shadow_value(style: dict[str, Any]) -> Any:
    return style.get("shadow") if "shadow" in style else style.get("shadow_depth")


def _style_line(role: str, style: dict[str, Any]) -> str:
    font_size = _scaled_font_size(style)
    outline = _number(_non_negative_numeric(style.get("outline_width"), DEFAULT_STYLE["outline_width"]))
    shadow = _number(_non_negative_numeric(_shadow_value(style), DEFAULT_STYLE["shadow_depth"]))
    angle = _number(style.get("rotate", DEFAULT_STYLE["rotate"]))
    spacing = _number(style.get("letter_spacing", DEFAULT_STYLE["letter_spacing"]))
    margin_l = int(_non_negative_numeric(style.get("margin_l"), DEFAULT_STYLE["margin_l"]))
    margin_r = int(_non_negative_numeric(style.get("margin_r"), DEFAULT_STYLE["margin_r"]))
    margin_v = int(_non_negative_numeric(style.get("margin_v"), DEFAULT_STYLE["margin_v"]))
    is_bold = _is_bold(style.get("font_weight"))
    is_italic = _is_truthy(style.get("italic"))

    fields = [
        role,
        str(style.get("font_family") or DEFAULT_STYLE["font_family"]),
        str(font_size),
        _ass_color(style.get("primary_color"), DEFAULT_STYLE["primary_color"]),
        "&H000000FF",
        _ass_color(style.get("outline_color"), DEFAULT_STYLE["outline_color"]),
        _ass_color(style.get("shadow_color"), DEFAULT_STYLE["shadow_color"]),
        "-1" if is_bold else "0",
        "-1" if is_italic else "0",
        "0",
        "0",
        "100",
        "100",
        spacing,
        angle,
        "1",
        outline,
        shadow,
        "2",
        str(margin_l),
        str(margin_r),
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
    text = _render_text(
        event.text,
        event.spans,
        reset_tags=override_tags,
        base_font_size=event_font_size,
        style=event.style if isinstance(event.style, dict) else {},
        resolution=resolution,
    )
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

    shadow_depth = _non_negative_numeric(_shadow_value(style)) if ("shadow_depth" in style or "shadow" in style) else None
    if shadow_depth is not None:
        tags.append(f"\\shad{_format_coordinate(shadow_depth)}")

    shadow_color = style.get("shadow_color")
    if isinstance(shadow_color, str) and _is_hex_color(shadow_color.strip()):
        tags.append(f"\\4c{_inline_color(shadow_color)}")

    rotate = _optional_numeric(style.get("rotate")) if "rotate" in style else None
    if rotate:
        tags.append(f"\\frz{_format_coordinate(rotate)}")

    tags.extend(_skew_tags(style))

    if "font_weight" in style and _is_bold(style.get("font_weight")):
        tags.append("\\b1")
    if "italic" in style and _is_truthy(style.get("italic")):
        tags.append("\\i1")

    tags.extend(_motion_or_position_tags(position, event.event_animations, resolution))
    tags.extend(_fade_tags(style, event.event_animations))

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
    anchor_tag = _anchor_tag(position.get("anchor"), y) if "anchor" in position else ""
    return f"{anchor_tag}\\pos({_format_coordinate(x_value)},{_format_coordinate(y_value)})"


def _render_text(
    text: str,
    spans: list[dict[str, Any]],
    *,
    reset_tags: str = "",
    base_font_size: int = DEFAULT_STYLE["font_size"],
    style: dict[str, Any] | None = None,
    resolution: tuple[int, int] = (1080, 1920),
) -> str:
    text_style = style if isinstance(style, dict) else {}
    max_chars_per_line = _max_chars_for_style_width(text_style, resolution, base_font_size)
    max_lines = _bounded_int(text_style.get("max_lines"), DEFAULT_STYLE["max_lines"], 1, 4)
    lines = _wrap_text_line_segments(text, max_chars_per_line, max_lines)
    rendered_lines = [
        _render_text_line(line.text, line.start, spans, reset_tags=reset_tags, base_font_size=base_font_size)
        for line in lines
    ]
    if len(rendered_lines) <= 1:
        return "".join(rendered_lines)

    line_spacing = _bounded_float(text_style.get("line_spacing"), DEFAULT_STYLE["line_spacing"], 0.8, 2.0)
    if line_spacing <= 1:
        return r"\N".join(rendered_lines)

    spacer_size = max(1, int(round(base_font_size * (line_spacing - 1) * 0.35)))
    separator = r"\N{\fs" + str(spacer_size) + r"} \N{\fs" + str(base_font_size) + r"}"
    return separator.join(rendered_lines)


def _render_text_line(
    text: str,
    line_start: int,
    spans: list[dict[str, Any]],
    *,
    reset_tags: str,
    base_font_size: int,
) -> str:
    selected_ranges: list[tuple[int, int, str]] = []
    for span in spans:
        if not isinstance(span, dict):
            continue
        selector = span.get("selector")
        style = span.get("style")
        if not isinstance(selector, dict) or not isinstance(style, dict):
            continue

        span_tags = _span_override_tags(style, base_font_size)
        if not span_tags:
            continue

        if selector.get("type") == "range":
            match_range = _range_selector_for_line(selector, line_start, len(text), selected_ranges)
            if match_range is not None:
                selected_ranges.append((match_range[0], match_range[1], span_tags))
        elif selector.get("type") == "keyword":
            keyword = selector.get("value")
            if not isinstance(keyword, str) or not keyword:
                continue
            match_range = _find_first_available_range(text, keyword, selected_ranges)
            if match_range is not None:
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


def _range_selector_for_line(
    selector: dict[str, Any],
    line_start: int,
    line_length: int,
    selected_ranges: list[tuple[int, int, str]],
) -> tuple[int, int] | None:
    start = _optional_int(selector.get("start"))
    end = _optional_int(selector.get("end"))
    if start is None or end is None or end <= start:
        return None

    line_end = line_start + line_length
    local_start = max(start, line_start) - line_start
    local_end = min(end, line_end) - line_start
    if local_start >= local_end:
        return None
    if _overlaps_selected_range(local_start, local_end, selected_ranges):
        return None
    return (local_start, local_end)


def _max_chars_for_style_width(
    style: dict[str, Any],
    resolution: tuple[int, int],
    base_font_size: int,
) -> int:
    max_chars = _bounded_int(style.get("max_chars_per_line"), DEFAULT_STYLE["max_chars_per_line"], 1, 120)
    ratio_source = style.get("max_width_ratio", style.get("max_width", DEFAULT_STYLE["max_width_ratio"]))
    max_width_ratio = _bounded_float(ratio_source, DEFAULT_STYLE["max_width_ratio"], 0.3, 1)
    width = max(1, int(resolution[0]))
    estimated = int((width * max_width_ratio) / max(base_font_size, 1))
    return max(1, min(max_chars, max(1, estimated)))


def _wrap_text_line_segments(text: str, max_chars_per_line: int, max_lines: int) -> list[WrappedTextLine]:
    logical_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not logical_lines:
        return [WrappedTextLine("", 0)]

    wrapped: list[WrappedTextLine] = []
    was_truncated = False
    logical_start = 0
    for line_index, logical_line in enumerate(logical_lines):
        leading_trim = len(logical_line) - len(logical_line.lstrip())
        remaining = logical_line.strip()
        remaining_start = logical_start + leading_trim
        if not remaining:
            wrapped.append(WrappedTextLine("", logical_start))
        while remaining:
            line, line_start, remaining, remaining_start = _split_visual_line_segment(
                remaining,
                remaining_start,
                max_chars_per_line,
            )
            wrapped.append(WrappedTextLine(line, line_start))
            if len(wrapped) >= max_lines:
                if remaining or any(line.strip() for line in logical_lines[line_index + 1 :]):
                    was_truncated = True
                break
        if len(wrapped) >= max_lines:
            break
        logical_start += len(logical_line) + 1

    wrapped = wrapped[:max_lines] or [WrappedTextLine("", 0)]
    if was_truncated and wrapped:
        suffix = "..."
        limit = max(0, max_chars_per_line - len(suffix))
        last = wrapped[-1]
        wrapped[-1] = WrappedTextLine(
            last.text[:limit] + suffix if limit else suffix[:max_chars_per_line],
            last.start,
        )
    return wrapped


def _split_visual_line_segment(
    text: str,
    start: int,
    max_chars_per_line: int,
) -> tuple[str, int, str, int]:
    if len(text) <= max_chars_per_line:
        return text, start, "", start + len(text)

    candidate = text[:max_chars_per_line]
    split_at = candidate.rfind(" ")
    if split_at > 0:
        next_text = text[split_at + 1 :]
        next_remaining = next_text.lstrip()
        next_start = start + split_at + 1 + len(next_text) - len(next_remaining)
        return text[:split_at].rstrip(), start, next_remaining, next_start
    return candidate, start, text[max_chars_per_line:], start + max_chars_per_line


def _span_override_tags(style: dict[str, Any], base_font_size: int) -> str:
    tags: list[str] = []

    primary_color = style.get("primary_color")
    if isinstance(primary_color, str) and _is_hex_color(primary_color.strip()):
        tags.append(f"\\c{_inline_color(primary_color)}")

    accent_color = style.get("accent_color")
    if isinstance(accent_color, str) and _is_hex_color(accent_color.strip()):
        tags.append(f"\\2c{_inline_color(accent_color)}")

    outline_color = style.get("outline_color")
    if isinstance(outline_color, str) and _is_hex_color(outline_color.strip()):
        tags.append(f"\\3c{_inline_color(outline_color)}")

    if "font_size" in style:
        font_size = _positive_numeric(style.get("font_size"))
        if font_size is not None:
            tags.append(f"\\fs{max(1, int(font_size))}")
    elif "font_scale" in style:
        font_scale = _positive_numeric(style.get("font_scale"))
        if font_scale is not None:
            tags.append(f"\\fs{max(1, int(base_font_size * font_scale))}")

    outline_width = _non_negative_numeric(style.get("outline_width")) if "outline_width" in style else None
    if outline_width is not None:
        tags.append(f"\\bord{_format_coordinate(outline_width)}")

    shadow_depth = _non_negative_numeric(_shadow_value(style)) if ("shadow_depth" in style or "shadow" in style) else None
    if shadow_depth is not None:
        tags.append(f"\\shad{_format_coordinate(shadow_depth)}")

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


def _optional_int(value: Any) -> int | None:
    number = _optional_numeric(value)
    if number is None:
        return None
    return int(number)


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    number = _optional_int(value)
    if number is None:
        number = int(default)
    return max(minimum, min(maximum, number))


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    number = _optional_numeric(value)
    if number is None:
        number = float(default)
    return max(minimum, min(maximum, float(number)))


def _skew_tags(style: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    skew_x_source = style.get("skew_x_deg", style.get("skew"))
    skew_y_source = style.get("skew_y_deg")
    skew_x = _bounded_float(skew_x_source, 0, -30, 30)
    skew_y = _bounded_float(skew_y_source, 0, -30, 30)
    if skew_x:
        tags.append(f"\\fax{_format_coordinate(math.tan(math.radians(skew_x)))}")
    if skew_y:
        tags.append(f"\\fay{_format_coordinate(math.tan(math.radians(skew_y)))}")
    return tags


def _motion_or_position_tags(
    position: dict[str, Any],
    animations: Any,
    resolution: tuple[int, int],
) -> list[str]:
    x = _optional_numeric(position.get("x"))
    y = _optional_numeric(position.get("y"))
    if x is None or y is None:
        return []

    width, height = resolution
    x_value = x * width if 0 <= x <= 1 else x
    y_value = y * height if 0 <= y <= 1 else y
    anchor_tag = _anchor_tag(position.get("anchor"), y) if "anchor" in position else ""
    in_animation = _block_animation(animations, "in")
    animation_type = in_animation.get("type")

    if animation_type == "slide_up_fade":
        offset_y = _optional_numeric(in_animation.get("offset_y"))
        if offset_y is None:
            offset_y = 18
        duration = _non_negative_int(in_animation.get("duration_ms"), 180)
        return [
            anchor_tag,
            (
                "\\move("
                f"{_format_coordinate(x_value)},"
                f"{_format_coordinate(y_value + offset_y)},"
                f"{_format_coordinate(x_value)},"
                f"{_format_coordinate(y_value)},"
                f"0,{duration})"
            ),
        ]

    tags = [f"{anchor_tag}\\pos({_format_coordinate(x_value)},{_format_coordinate(y_value)})"]
    if animation_type == "pop_in":
        duration = _non_negative_int(in_animation.get("duration_ms"), 140)
        tags.extend(["\\fscx80", "\\fscy80", f"\\t(0,{duration},\\fscx100\\fscy100)"])
    return tags


def _fade_tags(style: dict[str, Any], animations: Any) -> list[str]:
    in_animation = _block_animation(animations, "in")
    out_animation = _block_animation(animations, "out")
    has_fade_style = "fade_in_ms" in style or "fade_out_ms" in style
    has_fade_animation = in_animation.get("type") in {"fade", "slide_up_fade"} or out_animation.get("type") in {
        "fade",
        "fade_out",
    }
    if not has_fade_style and not has_fade_animation:
        return []

    fade_in_default = DEFAULT_STYLE["fade_in_ms"] if "fade_in_ms" in style else 0
    fade_out_default = DEFAULT_STYLE["fade_out_ms"] if "fade_out_ms" in style else 0
    fade_in = _non_negative_int(style.get("fade_in_ms"), int(fade_in_default))
    fade_out = _non_negative_int(style.get("fade_out_ms"), int(fade_out_default))
    if in_animation.get("type") in {"fade", "slide_up_fade"}:
        fade_in = _non_negative_int(in_animation.get("duration_ms"), fade_in)
    if out_animation.get("type") in {"fade", "fade_out"}:
        fade_out = _non_negative_int(out_animation.get("duration_ms"), fade_out)
    if fade_in or fade_out:
        return [f"\\fad({fade_in},{fade_out})"]
    return []


def _block_animation(animations: Any, phase: str) -> dict[str, Any]:
    if not isinstance(animations, dict):
        return {"type": "none", "duration_ms": 0}
    animation = animations.get(phase)
    if not isinstance(animation, dict):
        return {"type": "none", "duration_ms": 0}
    return animation


def _non_negative_int(value: Any, default: int = 0) -> int:
    number = _optional_numeric(value)
    if number is None or number < 0:
        return max(0, int(default))
    return int(number)


def _is_bold(value: Any) -> bool:
    weight = _optional_numeric(value)
    if weight is None:
        return False
    return weight >= 700


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _anchor_tag(anchor: Any, y: int | float) -> str:
    horizontal = {"left": 1, "center": 2, "right": 3}.get(str(anchor or "center").strip(), 2)
    if 0 <= y <= 1:
        vertical = 7 if y <= 0.33 else 4 if y <= 0.66 else 1
    else:
        vertical = 7 if y <= 360 else 4 if y <= 720 else 1
    return f"\\an{vertical + horizontal - 1}"


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
