from autovideo.core.runtime import RuntimeCheck, check_runtime
from autovideo.core.settings import Settings


def test_runtime_marks_missing_ffmpeg_as_error() -> None:
    settings = Settings(ffmpeg_path="missing-autovideo-ffmpeg-binary")

    status = check_runtime(settings)

    assert status["ffmpeg"] == RuntimeCheck(
        name="ffmpeg",
        ok=False,
        required=True,
        message="未找到 FFmpeg，可执行文件：missing-autovideo-ffmpeg-binary",
    )


def test_runtime_marks_empty_fish_speech_as_optional() -> None:
    settings = Settings(fish_speech_url=None)

    status = check_runtime(settings)

    assert status["fish_speech"] == RuntimeCheck(
        name="fish_speech",
        ok=False,
        required=False,
        message="Fish Speech 未配置，音色复刻功能将保持禁用",
    )


def test_runtime_marks_configured_fish_speech_as_available() -> None:
    settings = Settings(fish_speech_url="http://127.0.0.1:7860")

    status = check_runtime(settings)

    assert status["fish_speech"] == RuntimeCheck(
        name="fish_speech",
        ok=True,
        required=False,
        message="Fish Speech 已配置：http://127.0.0.1:7860",
    )
