from __future__ import annotations

import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from autovideo.core.paths import build_data_paths
from autovideo.core.settings import Settings
from autovideo.services.tasks import sanitize_manifest_payload
from autovideo.services.voices import EdgeTtsProvider, VoiceCenterService
from autovideo.services.voices.service import VoiceProvider

AUDIO_MIX_TIMEOUT_PADDING_SECONDS = 30.0
MIN_AUDIO_MIX_TIMEOUT_SECONDS = 30.0


class AudioMixFailedError(RuntimeError):
    def __init__(self, message: str, stderr: str = "") -> None:
        self.stderr = stderr
        super().__init__(message)


def build_audio_mix_status(
    *,
    mixed: bool,
    voiceover_requested: bool,
    voiceover_clip_count: int,
    bgm_requested: bool,
    bgm_volume: float | None,
    output: str | None,
    voiceover_requested_not_mixed: bool = False,
) -> dict[str, Any]:
    return {
        "status": "mixed" if mixed else "skipped",
        "voiceover_status": (
            "mixed"
            if mixed and voiceover_clip_count > 0
            else "not_requested"
            if not voiceover_requested
            else "requested_not_mixed"
            if voiceover_requested_not_mixed
            else "empty"
        ),
        "voiceover_clip_count": voiceover_clip_count,
        "bgm_status": (
            "mixed"
            if mixed and bgm_requested
            else "requested_not_mixed" if bgm_requested else "not_requested"
        ),
        "bgm_volume": bgm_volume,
        "output": output,
    }


def resolve_bgm_audio(settings: Settings, bgm_options: dict[str, Any]) -> Path | None:
    if not bool(bgm_options.get("bgm_enabled")):
        return None
    snapshot = bgm_options.get("bgm_snapshot")
    if not isinstance(snapshot, dict):
        raise AudioMixFailedError("BGM 快照缺失")
    filename = snapshot.get("filename")
    if not isinstance(filename, str) or not filename.strip():
        raise AudioMixFailedError("BGM 文件名缺失")
    if Path(filename).name != filename or "/" in filename or "\\" in filename:
        raise AudioMixFailedError("BGM 文件名不安全")

    tracks_dir = _safe_bgm_tracks_dir(settings)
    path = (tracks_dir / filename).resolve()
    try:
        path.relative_to(tracks_dir)
    except ValueError as exc:
        raise AudioMixFailedError("BGM 文件路径不安全") from exc
    if not path.is_file():
        raise AudioMixFailedError("BGM 文件不存在")
    return path


def apply_audio_mix(
    *,
    settings: Settings,
    output_dir: Path,
    video_path: Path | None,
    timeline: dict[str, Any],
    voice_options: dict[str, Any],
    bgm_options: dict[str, Any],
    provider: VoiceProvider | None = None,
) -> dict[str, Any]:
    voiceover_requested = _optional_text(voice_options.get("voice_id")) is not None
    bgm_path = resolve_bgm_audio(settings, bgm_options)
    bgm_requested = bgm_path is not None
    if video_path is None or not video_path.is_file():
        return build_audio_mix_status(
            mixed=False,
            voiceover_requested=voiceover_requested,
            voiceover_clip_count=0,
            voiceover_requested_not_mixed=voiceover_requested,
            bgm_requested=bgm_requested,
            bgm_volume=_optional_float(bgm_options.get("bgm_volume")),
            output=None,
        )
    if not voiceover_requested and not bgm_requested:
        return build_audio_mix_status(
            mixed=False,
            voiceover_requested=False,
            voiceover_clip_count=0,
            bgm_requested=False,
            bgm_volume=None,
            output=None,
        )

    narration_clips = _run_async(
        prepare_narration_clips(
            settings=settings,
            output_dir=output_dir,
            timeline=timeline,
            voice_options=voice_options,
            provider=provider,
        )
    )
    if not narration_clips and not bgm_requested:
        return build_audio_mix_status(
            mixed=False,
            voiceover_requested=voiceover_requested,
            voiceover_clip_count=0,
            bgm_requested=False,
            bgm_volume=None,
            output=None,
        )

    ffmpeg_binary = shutil.which(settings.ffmpeg_path)
    if ffmpeg_binary is None:
        raise AudioMixFailedError("FFmpeg 不可用，无法合成音频")

    bgm_volume = _optional_float(bgm_options.get("bgm_volume"))
    mix_audio_into_video(
        ffmpeg_binary=ffmpeg_binary,
        video_path=video_path,
        total_duration=_timeline_total_duration(timeline),
        narration_clips=narration_clips,
        bgm_path=bgm_path,
        bgm_volume=bgm_volume,
    )
    return build_audio_mix_status(
        mixed=True,
        voiceover_requested=voiceover_requested,
        voiceover_clip_count=len(narration_clips),
        bgm_requested=bgm_requested,
        bgm_volume=bgm_volume,
        output=video_path.name,
    )


async def prepare_narration_clips(
    *,
    settings: Settings,
    output_dir: Path,
    timeline: dict[str, Any],
    voice_options: dict[str, Any],
    provider: VoiceProvider | None = None,
) -> list[dict[str, Any]]:
    voice_id = _optional_text(voice_options.get("voice_id"))
    if not voice_id:
        return []
    if _optional_text(voice_options.get("voice_provider")) not in {None, "edge_tts"}:
        raise AudioMixFailedError("暂不支持当前旁白音色 provider")

    narration_dir = output_dir / "narration"
    narration_dir.mkdir(parents=True, exist_ok=True)
    voice_service = VoiceCenterService(
        settings,
        provider=provider or EdgeTtsProvider(),
    )
    clips: list[dict[str, Any]] = []
    for index, item in enumerate(timeline.get("items", []), start=1):
        if not isinstance(item, dict):
            continue
        text = _optional_text(item.get("narration"))
        if not text:
            continue
        shot_index = _optional_int(item.get("shot_index")) or index
        start_time = _optional_float(item.get("start_time")) or 0.0
        duration = _optional_float(item.get("duration")) or 1.0
        filename = f"narration-{shot_index}.mp3"
        output_path = narration_dir / filename
        try:
            await voice_service.provider.synthesize_to_file(
                text=text,
                voice_id=voice_id,
                output_path=output_path,
                rate="+0%",
                volume="+0%",
                pitch="+0Hz",
            )
        except Exception as exc:
            raise AudioMixFailedError("旁白音频生成失败") from exc
        clips.append(
            {
                "shot_index": shot_index,
                "filename": filename,
                "path": output_path,
                "start_time": round(start_time, 3),
                "duration": round(max(duration, 0.1), 3),
            }
        )
    return clips


def mix_audio_into_video(
    *,
    ffmpeg_binary: str,
    video_path: Path,
    total_duration: float,
    narration_clips: list[dict[str, Any]],
    bgm_path: Path | None,
    bgm_volume: float | None,
) -> Path:
    if not narration_clips and bgm_path is None:
        return video_path
    temp_output = video_path.with_name(f"{video_path.stem}.audio-mix.tmp{video_path.suffix}")
    command = _build_audio_mix_command(
        ffmpeg_binary=ffmpeg_binary,
        video_path=video_path,
        output_path=temp_output,
        total_duration=total_duration,
        narration_clips=narration_clips,
        bgm_path=bgm_path,
        bgm_volume=bgm_volume,
    )
    try:
        _run_audio_mix_command(command, total_duration)
        if not temp_output.is_file():
            raise AudioMixFailedError("FFmpeg 未生成音频混合输出")
        os.replace(temp_output, video_path)
    finally:
        if temp_output.exists():
            temp_output.unlink()
    return video_path


def _build_audio_mix_command(
    *,
    ffmpeg_binary: str,
    video_path: Path,
    output_path: Path,
    total_duration: float,
    narration_clips: list[dict[str, Any]],
    bgm_path: Path | None,
    bgm_volume: float | None,
) -> list[str]:
    command = [ffmpeg_binary, "-y", "-i", str(video_path)]
    for clip in narration_clips:
        command.extend(["-i", str(clip["path"])])
    if bgm_path is not None:
        command.extend(["-stream_loop", "-1", "-i", str(bgm_path)])

    filters: list[str] = []
    labels: list[str] = []
    for index, clip in enumerate(narration_clips):
        input_index = index + 1
        label = f"narration{index}"
        delay_ms = max(0, round(float(clip.get("start_time") or 0) * 1000))
        duration = _ffmpeg_number(float(clip.get("duration") or total_duration))
        filters.append(
            f"[{input_index}:a]atrim=0:{duration},asetpts=PTS-STARTPTS,"
            f"adelay={delay_ms}|{delay_ms}[{label}]"
        )
        labels.append(f"[{label}]")

    if bgm_path is not None:
        bgm_input_index = 1 + len(narration_clips)
        volume = _ffmpeg_number(bgm_volume if bgm_volume is not None else 0.12)
        duration = _ffmpeg_number(total_duration)
        filters.append(
            f"[{bgm_input_index}:a]atrim=0:{duration},asetpts=PTS-STARTPTS,"
            f"volume={volume}[bgm]"
        )
        labels.append("[bgm]")

    duration = _ffmpeg_number(total_duration)
    if len(labels) == 1:
        filters.append(f"{labels[0]}apad,atrim=0:{duration},asetpts=PTS-STARTPTS[aout]")
    else:
        mix_inputs = "".join(labels)
        filters.append(
            f"{mix_inputs}amix=inputs={len(labels)}:duration=longest:dropout_transition=0,"
            f"apad,atrim=0:{duration},asetpts=PTS-STARTPTS[aout]"
        )
    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "0:v:0",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    return command


def _run_audio_mix_command(command: list[str], total_duration: float) -> None:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=_audio_mix_timeout_seconds(total_duration),
        )
    except subprocess.TimeoutExpired as exc:
        raise AudioMixFailedError(
            "FFmpeg 音频合成超时",
            stderr=_timeout_output(exc),
        ) from exc
    if completed.returncode != 0:
        raise AudioMixFailedError(
            "FFmpeg 音频合成失败",
            stderr=_sanitize_audio_error_summary(completed.stderr or completed.stdout or ""),
        )


def _run_async(coro: Any) -> Any:
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    close = getattr(coro, "close", None)
    if callable(close):
        close()
    raise AudioMixFailedError("当前运行环境不支持同步等待旁白生成")


def _timeline_total_duration(timeline: dict[str, Any]) -> float:
    parsed = _optional_float(timeline.get("total_duration"))
    if parsed is not None and parsed > 0:
        return parsed
    end_times = [
        value
        for item in timeline.get("items", [])
        if isinstance(item, dict)
        for value in [_optional_float(item.get("end_time"))]
        if value is not None
    ]
    if end_times:
        return max(end_times)
    durations = [
        value
        for item in timeline.get("items", [])
        if isinstance(item, dict)
        for value in [_optional_float(item.get("duration"))]
        if value is not None
    ]
    return sum(durations) if durations else 1.0


def _safe_bgm_tracks_dir(settings: Settings) -> Path:
    return (build_data_paths(settings).bgm / "tracks").resolve()


def _sanitize_audio_error_summary(error_summary: str | None) -> str:
    if not error_summary:
        return ""
    sanitized = sanitize_manifest_payload(error_summary.strip()[-1200:])
    return sanitized if isinstance(sanitized, str) else ""


def _audio_mix_timeout_seconds(total_duration: float) -> float:
    return max(
        MIN_AUDIO_MIX_TIMEOUT_SECONDS,
        max(0.0, min(total_duration, 300.0)) + AUDIO_MIX_TIMEOUT_PADDING_SECONDS,
    )


def _timeout_output(exc: subprocess.TimeoutExpired) -> str:
    output = exc.stderr or exc.stdout or ""
    if isinstance(output, bytes):
        return _sanitize_audio_error_summary(output.decode("utf-8", errors="replace"))
    return _sanitize_audio_error_summary(str(output))


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _ffmpeg_number(value: float) -> str:
    if not math.isfinite(value):
        value = 0.0
    return f"{value:.3f}".rstrip("0").rstrip(".")
