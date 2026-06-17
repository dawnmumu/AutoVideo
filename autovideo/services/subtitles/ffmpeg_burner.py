from __future__ import annotations

import subprocess
from pathlib import Path


def burn_ass_subtitles(
    ffmpeg_binary: str,
    input_path: Path,
    ass_path: Path,
    output_path: Path,
    timeout_seconds: float,
) -> Path:
    command = [
        ffmpeg_binary,
        "-y",
        "-i",
        str(input_path),
        "-vf",
        f"ass={_escape_filter_path(ass_path)}",
        "-an",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise _render_error("FFmpeg 字幕烧录超时", _timeout_output(exc)) from exc

    if completed.returncode != 0:
        raise _render_error(
            "FFmpeg 字幕烧录失败",
            _clean_process_output(completed.stderr or completed.stdout or ""),
        )
    if not output_path.is_file():
        raise _render_error("FFmpeg 未生成字幕烧录输出视频", "")
    return output_path


def _escape_filter_path(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _render_error(message: str, stderr: str):
    from autovideo.services.rendering import FfmpegRenderFailedError

    return FfmpegRenderFailedError(message, stderr=stderr)


def _timeout_output(exc: subprocess.TimeoutExpired) -> str:
    output = exc.stderr or exc.stdout or ""
    if isinstance(output, bytes):
        return _clean_process_output(output.decode("utf-8", errors="replace"))
    return _clean_process_output(str(output))


def _clean_process_output(output: str) -> str:
    return output.strip()[-1200:]
