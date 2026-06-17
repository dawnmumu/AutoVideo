from __future__ import annotations

import base64
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from autovideo.services.subtitles.ass_renderer import write_ass_file
from autovideo.services.subtitles.ffmpeg_paths import ass_filter
from autovideo.services.subtitles.timeline import SubtitleEvent

DEFAULT_PREVIEW_DURATION_MS = 1200
MIN_TIMELINE_DURATION_MS = 500
MAX_TIMELINE_DURATION_MS = 5000
FFMPEG_TIMEOUT_SECONDS = 15


class SubtitlePreviewRendererUnavailableError(RuntimeError):
    pass


def render_preview_png(
    ffmpeg_path: str,
    template_set: dict[str, Any],
    template_type: str,
    aspect_ratio: str,
    sample_text: str,
    work_dir: str | Path,
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
        )
        output_path = preview_dir / "preview.png"
        duration_seconds = _duration_seconds(DEFAULT_PREVIEW_DURATION_MS)
        command = [
            ffmpeg_binary,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={resolution[0]}x{resolution[1]}:d={duration_seconds}",
            "-vf",
            ass_filter(ass_path),
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
        )
        output_path = preview_dir / "preview.mp4"
        duration_seconds = _duration_seconds(clean_duration_ms)
        command = [
            ffmpeg_binary,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={resolution[0]}x{resolution[1]}:r=30:d={duration_seconds}",
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
) -> Path:
    block = _template_block(template_set, template_type)
    event = SubtitleEvent(
        index=1,
        shot_index=1,
        start_ms=0,
        end_ms=duration_ms,
        text=sample_text or "AI 提升效率",
        template=template_type or "bottom",
        track_id=str(block.get("track_id") or "main"),
        spans=_list_of_dicts(block.get("spans")),
        style=dict(block.get("style")) if isinstance(block.get("style"), dict) else {},
        position=dict(block.get("position")) if isinstance(block.get("position"), dict) else {},
    )
    return write_ass_file(ass_path, [event], template_set, resolution)


def _template_block(template_set: dict[str, Any], template_type: str) -> dict[str, Any]:
    blocks = template_set.get("blocks") if isinstance(template_set, dict) else []
    if not isinstance(blocks, list):
        return {}
    for block in blocks:
        if isinstance(block, dict) and block.get("role") == template_type:
            return block
    return {}


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
    elif isinstance(duration_ms, int | float):
        clean_duration_ms = int(duration_ms)
    elif isinstance(duration_ms, str):
        try:
            clean_duration_ms = int(float(duration_ms.strip()))
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
