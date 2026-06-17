from __future__ import annotations

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
    lines.extend(_dialogue_line(event, resolution) for event in events)
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
    outline = _number(style.get("outline_width", DEFAULT_STYLE["outline_width"]))
    shadow = _number(style.get("shadow_depth", style.get("shadow", DEFAULT_STYLE["shadow_depth"])))
    angle = _number(style.get("rotate", DEFAULT_STYLE["rotate"]))
    margin_v = int(_numeric(style.get("margin_v", DEFAULT_STYLE["margin_v"]), DEFAULT_STYLE["margin_v"]))

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


def _dialogue_line(event: SubtitleEvent, resolution: tuple[int, int]) -> str:
    text = _render_text(event.text, event.spans)
    override_tags = _event_override_tags(event, resolution)
    if override_tags:
        text = f"{override_tags}{text}"
    return (
        f"Dialogue: 0,{_format_ass_time(event.start_ms)},{_format_ass_time(event.end_ms)},"
        f"{event.template},,0,0,0,,{text}"
    )


def _event_override_tags(event: SubtitleEvent, resolution: tuple[int, int]) -> str:
    tags: list[str] = []
    style = event.style if isinstance(event.style, dict) else {}
    position = event.position if isinstance(event.position, dict) else {}

    if "font_size" in style:
        tags.append(f"\\fs{_scaled_font_size(style)}")

    primary_color = style.get("primary_color")
    if isinstance(primary_color, str) and _is_hex_color(primary_color.strip()):
        tags.append(f"\\c{_inline_color(primary_color)}")

    position_tag = _position_tag(position, resolution)
    if position_tag:
        tags.append(position_tag)

    return "{" + "".join(tags) + "}" if tags else ""


def _position_tag(position: dict[str, Any], resolution: tuple[int, int]) -> str:
    x = _optional_numeric(position.get("x"))
    y = _optional_numeric(position.get("y"))
    if x is None or y is None:
        return ""

    width, height = resolution
    x_value = x * width if 0 <= x <= 1 else x
    y_value = y * height if 0 <= y <= 1 else y
    return f"\\pos({_format_coordinate(x_value)},{_format_coordinate(y_value)})"


def _render_text(text: str, spans: list[dict[str, Any]]) -> str:
    rendered = _escape_ass_text(text)
    for span in spans:
        if not isinstance(span, dict):
            continue
        selector = span.get("selector")
        style = span.get("style")
        if not isinstance(selector, dict) or selector.get("type") != "keyword" or not isinstance(style, dict):
            continue

        keyword = selector.get("value")
        color = style.get("primary_color")
        if not isinstance(keyword, str) or not keyword or not isinstance(color, str):
            continue

        escaped_keyword = _escape_ass_text(keyword)
        if escaped_keyword not in rendered:
            continue
        replacement = f"{{\\c{_inline_color(color)}}}{escaped_keyword}{{\\r}}"
        rendered = rendered.replace(escaped_keyword, replacement, 1)
    return rendered


def _scaled_font_size(style: dict[str, Any]) -> int:
    font_size = _numeric(style.get("font_size", DEFAULT_STYLE["font_size"]), DEFAULT_STYLE["font_size"])
    scale = style.get("font_size_scale", style.get("font_scale", 1))
    return int(font_size * _numeric(scale, 1))


def _numeric(value: Any, default: int | float) -> int | float:
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return default
        try:
            number = float(candidate)
        except ValueError:
            return default
        return int(number) if number.is_integer() else number
    return default


def _optional_numeric(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            number = float(candidate)
        except ValueError:
            return None
        return int(number) if number.is_integer() else number
    return None


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


def _format_ass_time(value_ms: int) -> str:
    centiseconds = max(0, int(round(value_ms / 10)))
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
