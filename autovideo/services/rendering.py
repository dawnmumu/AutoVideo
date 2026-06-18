from __future__ import annotations

import json
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autovideo.core.settings import Settings
from autovideo.services.subtitles import (
    ass_renderer,
    event_enrichment,
    keyword_spans,
    template_assignment,
)
from autovideo.services.subtitles.ffmpeg_paths import ass_filter
from autovideo.services.subtitles.source_masks import drawbox_filter
from autovideo.services.subtitles.timeline import events_from_render_timeline
from autovideo.services.tasks import sanitize_manifest_payload

VIDEO_MEDIA_TYPE = "video/mp4"
JSON_MEDIA_TYPE = "application/json"

IMAGE_CONTENT_PREFIX = "image/"
IMAGE_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".webp"}
MAX_RENDER_DURATION_SECONDS = 300.0
FFMPEG_RENDER_TIMEOUT_PADDING_SECONDS = 30.0
MIN_FFMPEG_RENDER_TIMEOUT_SECONDS = 30.0


class FfmpegRenderFailedError(RuntimeError):
    def __init__(self, message: str, stderr: str = "") -> None:
        self.stderr = stderr
        super().__init__(message)


@dataclass(frozen=True)
class RenderResult:
    output_path: Path | None
    status: str
    renderer: str
    timeline_path: str = "timeline.json"
    subtitles_path: str = "subtitles.srt"
    subtitles_ass_path: str | None = None
    base_output_path: str | None = None
    base_video_skipped: bool = False
    subtitle_burn_skipped: bool = False
    error_summary: str = ""


def media_type_for_output(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".mp4":
        return VIDEO_MEDIA_TYPE
    return JSON_MEDIA_TYPE


def build_render_timeline(
    *,
    title: str,
    script: dict[str, Any],
    shot_materials: list[dict[str, Any]],
) -> dict[str, Any]:
    _validate_script_duration_fields(script)
    material_by_shot = {
        int(item["shot_index"]): item
        for item in shot_materials
        if "shot_index" in item and "material_id" in item
    }
    items: list[dict[str, Any]] = []
    start_time = 0.0

    for shot in script.get("shots", []):
        if not isinstance(shot, dict):
            continue
        shot_index = int(shot["index"])
        duration = _shot_duration(shot)
        end_time = round(start_time + duration, 1)
        _validate_duration_within_limit(end_time, "timeline total_duration")
        material = material_by_shot.get(shot_index, {})
        narration = str(shot.get("narration") or "").strip()
        subtitle = str(shot.get("subtitle") or narration).strip()
        items.append(
            {
                "shot_index": shot_index,
                "start_time": round(start_time, 1),
                "end_time": end_time,
                "duration": duration,
                "narration": narration,
                "subtitle": subtitle,
                "visual_description": str(shot.get("visual_description") or "").strip(),
                "material_id": material.get("material_id"),
                "selection_mode": material.get("selection_mode"),
                "selection_reason": material.get("selection_reason"),
            }
        )
        start_time = end_time

    return {
        "title": title,
        "total_duration": round(start_time, 1),
        "items": items,
    }


def render_mix_video(
    *,
    settings: Settings,
    output_dir: Path,
    timeline: dict[str, Any],
    materials_by_id: dict[str, dict[str, Any]],
    aspect_ratio: str,
    subtitle_enabled: bool = False,
    subtitle_template_set: dict[str, Any] | None = None,
    source_subtitle_masks: list[bool] | None = None,
) -> RenderResult:
    _validate_render_timeline(timeline)
    safe_timeline = sanitize_render_timeline(timeline)
    output_dir.mkdir(parents=True, exist_ok=True)
    timeline_path = output_dir / "timeline.json"
    subtitles_path = output_dir / "subtitles.srt"
    output_path = output_dir / "output.mp4"
    timeline_path.write_text(
        json.dumps(safe_timeline, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    subtitles_path.write_text(_format_srt(safe_timeline), encoding="utf-8")

    resolution = _resolution_for_aspect_ratio(aspect_ratio)
    ass_path = _write_subtitle_ass_artifact(
        output_dir=output_dir,
        timeline=safe_timeline,
        template_set=subtitle_template_set,
        resolution=resolution,
    ) if subtitle_enabled and subtitle_template_set else None

    render_items = _timeline_items_with_materials(safe_timeline, materials_by_id)
    if not render_items:
        raise FfmpegRenderFailedError("没有可用于渲染的镜头素材")

    ffmpeg_binary = shutil.which(settings.ffmpeg_path)
    if ffmpeg_binary is None:
        return RenderResult(
            output_path=None,
            status="manifest_only",
            renderer="ffmpeg_unavailable",
            subtitles_ass_path=ass_path.name if ass_path else None,
            base_video_skipped=True,
            subtitle_burn_skipped=ass_path is not None,
        )

    base_output_path = output_dir / "output.base.mp4" if ass_path else output_path
    command = _build_ffmpeg_command(
        ffmpeg_binary=ffmpeg_binary,
        render_items=render_items,
        output_path=base_output_path,
        aspect_ratio=aspect_ratio,
        source_subtitle_masks=source_subtitle_masks,
        ass_path=None,
    )
    try:
        _run_ffmpeg_command(command, safe_timeline)
        if not base_output_path.is_file():
            raise FfmpegRenderFailedError("FFmpeg 未生成输出视频")
    except FfmpegRenderFailedError as exc:
        if ass_path is None:
            raise
        return RenderResult(
            output_path=None,
            status="base_video_failed",
            renderer="ffmpeg",
            subtitles_ass_path=ass_path.name,
            error_summary=_clean_ffmpeg_stderr(exc.stderr) or str(exc),
        )

    if ass_path is None:
        return RenderResult(
            output_path=output_path,
            status="video_rendered",
            renderer="ffmpeg",
        )

    from autovideo.services.subtitles import ffmpeg_burner

    try:
        ffmpeg_burner.burn_ass_subtitles(
            ffmpeg_binary,
            base_output_path,
            ass_path,
            output_path,
            _ffmpeg_timeout_seconds(safe_timeline),
        )
    except FfmpegRenderFailedError as exc:
        return RenderResult(
            output_path=base_output_path,
            status="subtitle_burn_failed",
            renderer="ffmpeg",
            subtitles_ass_path=ass_path.name,
            base_output_path=base_output_path.name,
            error_summary=_clean_ffmpeg_stderr(exc.stderr) or str(exc),
        )

    return RenderResult(
        output_path=output_path,
        status="subtitle_burned",
        renderer="ffmpeg",
        subtitles_ass_path=ass_path.name,
        base_output_path=base_output_path.name,
    )


def write_timeline_artifacts(output_dir: Path, timeline: dict[str, Any]) -> None:
    _validate_render_timeline(timeline)
    safe_timeline = sanitize_render_timeline(timeline)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "timeline.json").write_text(
        json.dumps(safe_timeline, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "subtitles.srt").write_text(
        _format_srt(safe_timeline),
        encoding="utf-8",
    )


def sanitize_render_timeline(timeline: dict[str, Any]) -> dict[str, Any]:
    sanitized = sanitize_manifest_payload(timeline)
    return sanitized if isinstance(sanitized, dict) else {}


def _shot_duration(shot: dict[str, Any]) -> float:
    try:
        duration = float(shot.get("duration") or 1)
    except (TypeError, ValueError):
        duration = 1.0
    if not math.isfinite(duration):
        raise FfmpegRenderFailedError("镜头 duration 必须是有限秒数")
    duration = round(max(duration, 1.0), 1)
    _validate_duration_within_limit(duration, "镜头 duration")
    return duration


def _validate_script_duration_fields(script: dict[str, Any]) -> None:
    for field in ("duration_seconds", "total_duration"):
        value = script.get(field)
        if value is None or value == "":
            continue
        duration = _coerce_duration(value, f"script {field}")
        _validate_duration_within_limit(duration, f"script {field}")


def _validate_render_timeline(timeline: dict[str, Any]) -> None:
    total_duration = timeline.get("total_duration")
    if total_duration is not None and total_duration != "":
        _validate_duration_within_limit(
            _coerce_duration(total_duration, "timeline total_duration"),
            "timeline total_duration",
        )

    computed_total = 0.0
    max_end_time = 0.0
    for index, item in enumerate(timeline.get("items", []), start=1):
        if not isinstance(item, dict):
            continue
        duration = _coerce_duration(
            item.get("duration"),
            f"timeline item {index} duration",
        )
        if duration <= 0:
            raise FfmpegRenderFailedError("timeline item duration 必须大于 0")
        _validate_duration_within_limit(
            duration,
            f"timeline item {index} duration",
        )
        computed_total = round(computed_total + duration, 1)
        _validate_duration_within_limit(computed_total, "timeline total_duration")

        for field in ("start_time", "end_time"):
            if field not in item:
                continue
            value = _coerce_duration(item[field], f"timeline item {index} {field}")
            _validate_duration_within_limit(value, f"timeline item {index} {field}")
            if field == "end_time":
                max_end_time = max(max_end_time, value)

    _validate_duration_within_limit(max_end_time, "timeline total_duration")


def _coerce_duration(value: Any, field_name: str) -> float:
    try:
        duration = float(value)
    except (TypeError, ValueError) as exc:
        raise FfmpegRenderFailedError(f"{field_name} 必须是有限秒数") from exc
    if not math.isfinite(duration):
        raise FfmpegRenderFailedError(f"{field_name} 必须是有限秒数")
    return duration


def _validate_duration_within_limit(duration: float, field_name: str) -> None:
    if not math.isfinite(duration):
        raise FfmpegRenderFailedError(f"{field_name} 必须是有限秒数")
    if duration > MAX_RENDER_DURATION_SECONDS:
        raise FfmpegRenderFailedError(
            f"{field_name} 不能超过 {int(MAX_RENDER_DURATION_SECONDS)} 秒"
        )


def _ffmpeg_timeout_seconds(timeline: dict[str, Any]) -> float:
    try:
        duration = float(timeline.get("total_duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return max(
        MIN_FFMPEG_RENDER_TIMEOUT_SECONDS,
        min(duration, MAX_RENDER_DURATION_SECONDS)
        + FFMPEG_RENDER_TIMEOUT_PADDING_SECONDS,
    )


def _timeout_output(exc: subprocess.TimeoutExpired) -> str:
    output = exc.stderr or exc.stdout or ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace").strip()
    return str(output).strip()


def _run_ffmpeg_command(command: list[str], timeline: dict[str, Any]) -> None:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=_ffmpeg_timeout_seconds(timeline),
        )
    except subprocess.TimeoutExpired as exc:
        raise FfmpegRenderFailedError(
            "FFmpeg 渲染超时",
            stderr=_timeout_output(exc),
        ) from exc
    if completed.returncode != 0:
        raise FfmpegRenderFailedError(
            "FFmpeg 渲染失败",
            stderr=_clean_ffmpeg_stderr(completed.stderr or completed.stdout or ""),
        )


def _clean_ffmpeg_stderr(stderr: str) -> str:
    return (stderr or "").strip()[-1200:]


def _timeline_items_with_materials(
    timeline: dict[str, Any],
    materials_by_id: dict[str, dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    items: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item in timeline.get("items", []):
        if not isinstance(item, dict):
            continue
        material_id = item.get("material_id")
        if not isinstance(material_id, str):
            continue
        material = materials_by_id.get(material_id)
        if material is not None:
            items.append((item, material))
    return items


def _build_ffmpeg_command(
    *,
    ffmpeg_binary: str,
    render_items: list[tuple[dict[str, Any], dict[str, Any]]],
    output_path: Path,
    aspect_ratio: str,
    source_subtitle_masks: list[bool] | None = None,
    ass_path: Path | None = None,
) -> list[str]:
    width, height = _resolution_for_aspect_ratio(aspect_ratio)
    command = [ffmpeg_binary, "-y"]

    for item, material in render_items:
        duration = str(item["duration"])
        storage_path = str(Path(material["storage_path"]))
        if _is_image_material(material):
            command.extend(["-loop", "1", "-t", duration, "-i", storage_path])
        else:
            command.extend(["-stream_loop", "-1", "-t", duration, "-i", storage_path])

    filters = []
    video_labels = []
    for index, _ in enumerate(render_items):
        label = f"v{index}"
        input_filters = [
            f"scale={width}:{height}:force_original_aspect_ratio=increase",
            f"crop={width}:{height}",
            "setsar=1",
            "fps=30",
            "format=yuv420p",
        ]
        if (
            source_subtitle_masks is not None
            and index < len(source_subtitle_masks)
            and source_subtitle_masks[index]
        ):
            input_filters.append(drawbox_filter(width, height))
        filters.append(
            f"[{index}:v]{','.join(input_filters)}[{label}]"
        )
        video_labels.append(f"[{label}]")

    concat_filter = (
        f"{''.join(video_labels)}concat=n={len(video_labels)}:v=1:a=0,"
        f"format=yuv420p"
    )
    if ass_path is not None:
        concat_filter = f"{concat_filter},{ass_filter(ass_path)}"
    filters.append(f"{concat_filter}[v]")
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[v]",
        ]
    )
    command.extend(
        [
            "-an",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return command


def _write_subtitle_ass_artifact(
    *,
    output_dir: Path,
    timeline: dict[str, Any],
    template_set: dict[str, Any],
    resolution: tuple[int, int],
) -> Path:
    events = events_from_render_timeline(timeline)
    assigned = template_assignment.assign_template_roles(
        events,
        template_set,
    )
    keyworded = keyword_spans.apply_keyword_spans(
        assigned,
        template_set,
    )
    enriched = event_enrichment.enrich_subtitle_events(
        keyworded,
        template_set,
        resolution,
    )
    return ass_renderer.write_ass_file(
        output_dir / "subtitles.ass",
        enriched,
        template_set,
        resolution,
    )

def _resolution_for_aspect_ratio(aspect_ratio: str) -> tuple[int, int]:
    if aspect_ratio == "16:9":
        return 1920, 1080
    if aspect_ratio == "1:1":
        return 1080, 1080
    return 1080, 1920


def _is_image_material(material: dict[str, Any]) -> bool:
    content_type = str(material.get("content_type") or "").lower()
    suffix = Path(str(material.get("storage_path") or "")).suffix.lower()
    return content_type.startswith(IMAGE_CONTENT_PREFIX) or suffix in IMAGE_EXTENSIONS


def _format_srt(timeline: dict[str, Any]) -> str:
    blocks: list[str] = []
    for index, item in enumerate(timeline.get("items", []), start=1):
        if not isinstance(item, dict):
            continue
        subtitle = str(item.get("subtitle") or item.get("narration") or "").strip()
        if not subtitle:
            continue
        blocks.append(
            "\n".join(
                [
                    str(index),
                    (
                        f"{_format_srt_timestamp(float(item['start_time']))} --> "
                        f"{_format_srt_timestamp(float(item['end_time']))}"
                    ),
                    subtitle,
                ]
            )
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _format_srt_timestamp(seconds: float) -> str:
    milliseconds = max(round(seconds * 1000), 0)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02},{milliseconds:03}"
