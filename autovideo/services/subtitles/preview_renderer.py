from __future__ import annotations

import base64
import copy
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from autovideo.services.subtitles.event_enrichment import position_from_style_layout
from autovideo.services.subtitles.ass_renderer import write_ass_file
from autovideo.services.subtitles.ffmpeg_paths import ass_filter
from autovideo.services.subtitles.timeline import SubtitleEvent

DEFAULT_PREVIEW_DURATION_MS = 1200
DEFAULT_PREVIEW_SAMPLE_TEXT = "这是字幕预览，支持多个位置和不同倾斜角度"
DEFAULT_PREVIEW_STILL_CAPTURE_MS = DEFAULT_PREVIEW_DURATION_MS // 2
MIN_TIMELINE_DURATION_MS = 500
MAX_TIMELINE_DURATION_MS = 5000
FFMPEG_TIMEOUT_SECONDS = 15
PREVIEW_BACKGROUND_COLOR = "0xE2E8F0"
LIVE_PREVIEW_DISPLAY_WIDTH = 280
LIVE_PREVIEW_BASE_FONT_SIZE = 16
LIVE_PREVIEW_FONT_REFERENCE = 54
LIVE_PREVIEW_FONT_SIZE_MIN_SCALE = 0.82
LIVE_PREVIEW_FONT_SIZE_MAX_SCALE = 1.35
LIVE_PREVIEW_FONT_SCALE_MIN = 0.6
LIVE_PREVIEW_FONT_SCALE_MAX = 1.8
LIVE_PREVIEW_LIBASS_FONT_SIZE_TUNING = 1.04
PREVIEW_ROLE_DEFAULT_Y = {"bottom": 78, "highlight": 52, "punch": 30}
PREVIEW_ROLE_LANE_CANDIDATES = {
    "bottom": [78, 64, 86],
    "highlight": [52, 64, 40],
    "punch": [30, 18, 42],
}


class SubtitlePreviewRendererUnavailableError(RuntimeError):
    pass


def render_preview_png(
    ffmpeg_path: str,
    template_set: dict[str, Any],
    template_type: str,
    aspect_ratio: str,
    sample_text: str,
    work_dir: str | Path,
    *,
    template_types: list[str] | None = None,
) -> dict[str, Any]:
    ffmpeg_binary = _resolve_ffmpeg(ffmpeg_path)
    resolution = _resolution_for_aspect_ratio(aspect_ratio)

    with _preview_work_dir(work_dir) as preview_dir_value:
        preview_dir = Path(preview_dir_value)
        ass_path = _write_preview_ass(
            preview_dir / "preview.ass",
            template_set,
            template_type,
            sample_text,
            DEFAULT_PREVIEW_DURATION_MS,
            resolution,
            match_live_preview_font_size=True,
            template_types=template_types,
        )
        output_path = preview_dir / "preview.png"
        duration_seconds = _duration_seconds(DEFAULT_PREVIEW_DURATION_MS)
        command = [
            ffmpeg_binary,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={PREVIEW_BACKGROUND_COLOR}:s={resolution[0]}x{resolution[1]}:d={duration_seconds}",
            "-vf",
            ass_filter(ass_path),
            "-ss",
            _duration_seconds(DEFAULT_PREVIEW_STILL_CAPTURE_MS),
            "-frames:v",
            "1",
            str(output_path),
        ]
        _run_preview_command(command, output_path)
        return {
            "mime_type": "image/png",
            "data": _base64_file(output_path),
            "resolution": _resolution_payload(resolution),
            "warnings": [],
        }


def render_preview_timeline(
    ffmpeg_path: str,
    template_set: dict[str, Any],
    template_type: str,
    aspect_ratio: str,
    sample_text: str,
    duration_ms: int | float | str | None,
    work_dir: str | Path,
    *,
    template_types: list[str] | None = None,
) -> dict[str, Any]:
    ffmpeg_binary = _resolve_ffmpeg(ffmpeg_path)
    clean_duration_ms = _clean_timeline_duration_ms(duration_ms)
    resolution = _resolution_for_aspect_ratio(aspect_ratio)

    with _preview_work_dir(work_dir) as preview_dir_value:
        preview_dir = Path(preview_dir_value)
        ass_path = _write_preview_ass(
            preview_dir / "preview.ass",
            template_set,
            template_type,
            sample_text,
            clean_duration_ms,
            resolution,
            template_types=template_types,
        )
        output_path = preview_dir / "preview.mp4"
        duration_seconds = _duration_seconds(clean_duration_ms)
        command = [
            ffmpeg_binary,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={PREVIEW_BACKGROUND_COLOR}:s={resolution[0]}x{resolution[1]}:r=30:d={duration_seconds}",
            "-vf",
            ass_filter(ass_path),
            "-t",
            duration_seconds,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        _run_preview_command(command, output_path)
        return {
            "mime_type": "video/mp4",
            "data": _base64_file(output_path),
            "duration_ms": clean_duration_ms,
            "resolution": _resolution_payload(resolution),
            "warnings": [],
        }


def _resolve_ffmpeg(ffmpeg_path: str) -> str:
    ffmpeg_binary = shutil.which(ffmpeg_path)
    if ffmpeg_binary is None:
        raise SubtitlePreviewRendererUnavailableError("FFmpeg/libass preview renderer is unavailable")
    return ffmpeg_binary


def _preview_work_dir(work_dir: str | Path) -> tempfile.TemporaryDirectory[str]:
    root = Path(work_dir)
    root.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix="subtitle-preview-", dir=root)


def _write_preview_ass(
    ass_path: Path,
    template_set: dict[str, Any],
    template_type: str,
    sample_text: str,
    duration_ms: int,
    resolution: tuple[int, int],
    *,
    match_live_preview_font_size: bool = False,
    template_types: list[str] | None = None,
) -> Path:
    preview_roles = _preview_template_types(template_type, template_types)
    use_preview_lanes = len(preview_roles) > 1
    occupied_lanes: list[float] = []
    events: list[SubtitleEvent] = []
    text = sample_text or DEFAULT_PREVIEW_SAMPLE_TEXT

    for index, role in enumerate(preview_roles, start=1):
        block = _template_block(template_set, role)
        position = _preview_block_position(
            template_set,
            role,
            block,
            resolution=resolution,
            occupied_lanes=occupied_lanes if use_preview_lanes else None,
        )
        if match_live_preview_font_size:
            style = _preview_event_style(template_set, role, block, resolution)
            spans = _preview_event_spans(block, resolution)
        else:
            style = dict(block.get("style")) if isinstance(block.get("style"), dict) else {}
            spans = _list_of_dicts(block.get("spans"))

        events.append(
            SubtitleEvent(
                index=index,
                shot_index=1,
                start_ms=0,
                end_ms=duration_ms,
                text=text,
                template=role,
                track_id=f"preview-{role}" if use_preview_lanes else str(block.get("track_id") or "main"),
                spans=spans,
                style=style,
                position=position,
                event_animations=dict(block.get("animations")) if isinstance(block.get("animations"), dict) else {},
            )
        )

    return write_ass_file(ass_path, events, template_set, resolution)


def _preview_template_types(template_type: str, template_types: list[str] | None) -> list[str]:
    roles: list[str] = []
    if isinstance(template_types, list):
        for item in template_types:
            if not isinstance(item, str):
                continue
            role = item.strip()
            if role and role not in roles:
                roles.append(role)

    fallback_role = str(template_type or "bottom").strip() or "bottom"
    return roles or [fallback_role]


def _template_block(template_set: dict[str, Any], template_type: str) -> dict[str, Any]:
    blocks = template_set.get("blocks") if isinstance(template_set, dict) else []
    if not isinstance(blocks, list):
        return {}
    for block in blocks:
        if isinstance(block, dict) and block.get("role") == template_type:
            return block
    return {}


def _preview_block_position(
    template_set: dict[str, Any],
    template_type: str,
    block: dict[str, Any],
    *,
    resolution: tuple[int, int],
    occupied_lanes: list[float] | None = None,
) -> dict[str, Any]:
    fallback_position = block.get("position") if isinstance(block.get("position"), dict) else {}
    layout_style: dict[str, Any] = {}
    templates = template_set.get("templates") if isinstance(template_set, dict) else {}
    template = templates.get(template_type) if isinstance(templates, dict) else None
    if isinstance(template, dict):
        layout_style.update(dict(template))
    if isinstance(block.get("style"), dict):
        layout_style.update(dict(block["style"]))
    position = position_from_style_layout(layout_style, fallback_position)
    clean_position = dict(position if position is not None else fallback_position)

    if occupied_lanes is not None:
        y_percent = _preview_position_y_percent(clean_position, template_type)
        lane_percent = _preview_role_lane_value(
            template_type,
            y_percent,
            occupied_lanes,
            _preview_lane_min_gap_percent(resolution),
        )
        clean_position["y"] = lane_percent / 100
        occupied_lanes.append(lane_percent)

    return clean_position


def _preview_event_style(
    template_set: dict[str, Any],
    template_type: str,
    block: dict[str, Any],
    resolution: tuple[int, int],
) -> dict[str, Any]:
    style = _merged_template_block_style(template_set, template_type, block)
    style["font_size"] = _live_preview_equivalent_font_size(style, resolution)
    style.pop("font_size_scale", None)
    style.pop("font_scale", None)
    return style


def _preview_event_spans(block: dict[str, Any], resolution: tuple[int, int]) -> list[dict[str, Any]]:
    spans = block.get("spans")
    if not isinstance(spans, list):
        return []

    preview_spans: list[dict[str, Any]] = []
    for item in spans:
        if not isinstance(item, dict):
            continue
        span = copy.deepcopy(item)
        style = span.get("style")
        if isinstance(style, dict) and "font_size" in style:
            font_size = _live_preview_equivalent_css_font_size(style.get("font_size"), resolution)
            if font_size is not None:
                style["font_size"] = font_size
        preview_spans.append(span)
    return preview_spans


def _merged_template_block_style(
    template_set: dict[str, Any],
    template_type: str,
    block: dict[str, Any],
) -> dict[str, Any]:
    style: dict[str, Any] = {}
    templates = template_set.get("templates") if isinstance(template_set, dict) else {}
    template = templates.get(template_type) if isinstance(templates, dict) else None
    if isinstance(template, dict):
        style.update(dict(template))
    if isinstance(block.get("style"), dict):
        style.update(dict(block["style"]))
    return style


def _live_preview_equivalent_font_size(style: dict[str, Any], resolution: tuple[int, int]) -> int:
    font_size = _positive_number(style.get("font_size"), LIVE_PREVIEW_FONT_REFERENCE)
    font_scale = _positive_number(
        style.get("font_size_scale", style.get("font_scale", 1)),
        1,
    )
    live_font_size = _round_preview_number(
        _clamp(font_size / LIVE_PREVIEW_FONT_REFERENCE, LIVE_PREVIEW_FONT_SIZE_MIN_SCALE, LIVE_PREVIEW_FONT_SIZE_MAX_SCALE)
        * LIVE_PREVIEW_BASE_FONT_SIZE
        * _clamp(font_scale, LIVE_PREVIEW_FONT_SCALE_MIN, LIVE_PREVIEW_FONT_SCALE_MAX),
    )
    preview_width = max(1, int(resolution[0]))
    return max(
        1,
        _round_preview_number(
            live_font_size * preview_width / LIVE_PREVIEW_DISPLAY_WIDTH * LIVE_PREVIEW_LIBASS_FONT_SIZE_TUNING
        ),
    )


def _live_preview_equivalent_css_font_size(value: Any, resolution: tuple[int, int]) -> int | None:
    font_size = _positive_number(value, 0)
    if font_size <= 0:
        return None
    preview_width = max(1, int(resolution[0]))
    return max(
        1,
        _round_preview_number(
            font_size * preview_width / LIVE_PREVIEW_DISPLAY_WIDTH * LIVE_PREVIEW_LIBASS_FONT_SIZE_TUNING
        ),
    )


def _preview_position_y_percent(position: dict[str, Any], role: str) -> float:
    fallback = PREVIEW_ROLE_DEFAULT_Y.get(role, PREVIEW_ROLE_DEFAULT_Y["bottom"])
    value = position.get("y")
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int | float) and math.isfinite(value):
        if 0 <= value <= 1:
            return _clamp(value * 100, 0, 100)
        return _clamp(value, 0, 100)
    return fallback


def _preview_role_lane_value(
    role: str,
    value: float,
    occupied_lanes: list[float],
    min_gap: float,
) -> float:
    if not any(_preview_lane_conflict(value, lane, min_gap) for lane in occupied_lanes):
        return value

    candidates = [
        *PREVIEW_ROLE_LANE_CANDIDATES.get(role, []),
        PREVIEW_ROLE_DEFAULT_Y.get(role, PREVIEW_ROLE_DEFAULT_Y["bottom"]),
        value + min_gap,
        value - min_gap,
        value + min_gap * 2,
        value - min_gap * 2,
    ]
    for candidate in candidates:
        if 8 <= candidate <= 92 and not any(
            _preview_lane_conflict(candidate, lane, min_gap) for lane in occupied_lanes
        ):
            return candidate
    return value


def _preview_lane_min_gap_percent(resolution: tuple[int, int]) -> float:
    width, height = resolution
    return 18 if width > height else 10


def _preview_lane_conflict(first: float, second: float, min_gap: float) -> bool:
    return abs(first - second) < min_gap


def _positive_number(value: Any, default: int | float) -> int | float:
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        return value if math.isfinite(value) and value > 0 else default
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return default
        try:
            number = float(candidate)
        except ValueError:
            return default
        if not math.isfinite(number) or number <= 0:
            return default
        return int(number) if number.is_integer() else number
    return default


def _clamp(value: int | float, minimum: int | float, maximum: int | float) -> int | float:
    return min(maximum, max(minimum, value))


def _round_preview_number(value: int | float) -> int:
    return int(math.floor(value + 0.5))


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _resolution_for_aspect_ratio(aspect_ratio: str) -> tuple[int, int]:
    if aspect_ratio == "16:9":
        return (1920, 1080)
    if aspect_ratio == "1:1":
        return (1080, 1080)
    return (1080, 1920)


def _clean_timeline_duration_ms(duration_ms: int | float | str | None) -> int:
    clean_duration_ms = DEFAULT_PREVIEW_DURATION_MS
    if isinstance(duration_ms, bool):
        clean_duration_ms = DEFAULT_PREVIEW_DURATION_MS
    elif isinstance(duration_ms, int):
        clean_duration_ms = duration_ms
    elif isinstance(duration_ms, float):
        clean_duration_ms = int(duration_ms) if math.isfinite(duration_ms) else DEFAULT_PREVIEW_DURATION_MS
    elif isinstance(duration_ms, str):
        try:
            parsed_duration_ms = float(duration_ms.strip())
            clean_duration_ms = int(parsed_duration_ms) if math.isfinite(parsed_duration_ms) else DEFAULT_PREVIEW_DURATION_MS
        except ValueError:
            clean_duration_ms = DEFAULT_PREVIEW_DURATION_MS

    return min(MAX_TIMELINE_DURATION_MS, max(MIN_TIMELINE_DURATION_MS, clean_duration_ms))


def _duration_seconds(duration_ms: int) -> str:
    return f"{duration_ms / 1000:.3f}"


def _run_preview_command(command: list[str], output_path: Path) -> None:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        detail = _clean_stderr(exc.stderr or exc.stdout or "")
        message = "FFmpeg/libass preview renderer timed out"
        if detail:
            message = f"{message}: {detail}"
        raise SubtitlePreviewRendererUnavailableError(message) from exc
    except OSError as exc:
        raise SubtitlePreviewRendererUnavailableError(
            f"FFmpeg/libass preview renderer could not start: {exc}"
        ) from exc

    if completed.returncode != 0:
        detail = _clean_stderr(completed.stderr or completed.stdout or "")
        message = "FFmpeg/libass preview renderer failed"
        if detail:
            message = f"{message}: {detail}"
        raise SubtitlePreviewRendererUnavailableError(message)

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise SubtitlePreviewRendererUnavailableError("FFmpeg/libass preview renderer did not generate output")


def _clean_stderr(stderr: str | bytes) -> str:
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    return " ".join(stderr.strip().split())[:500]


def _base64_file(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _resolution_payload(resolution: tuple[int, int]) -> dict[str, int]:
    return {"width": resolution[0], "height": resolution[1]}
