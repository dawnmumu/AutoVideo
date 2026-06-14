from dataclasses import dataclass
from shutil import which

from autovideo.core.settings import Settings


@dataclass(frozen=True)
class RuntimeCheck:
    name: str
    ok: bool
    required: bool
    message: str


def check_ffmpeg(settings: Settings) -> RuntimeCheck:
    binary = settings.ffmpeg_path
    if which(binary) is None:
        return RuntimeCheck(
            name="ffmpeg",
            ok=False,
            required=True,
            message=f"未找到 FFmpeg，可执行文件：{binary}",
        )
    return RuntimeCheck(
        name="ffmpeg",
        ok=True,
        required=True,
        message=f"FFmpeg 可用：{binary}",
    )


def check_fish_speech(settings: Settings) -> RuntimeCheck:
    if not settings.fish_speech_url:
        return RuntimeCheck(
            name="fish_speech",
            ok=False,
            required=False,
            message="Fish Speech 未配置，音色复刻功能将保持禁用",
        )
    return RuntimeCheck(
        name="fish_speech",
        ok=True,
        required=False,
        message=f"Fish Speech 已配置：{settings.fish_speech_url}",
    )


def check_runtime(settings: Settings) -> dict[str, RuntimeCheck]:
    return {
        "ffmpeg": check_ffmpeg(settings),
        "fish_speech": check_fish_speech(settings),
    }
