from pathlib import Path

from autovideo.core.settings import Settings

AUTOVIDEO_ENV_VARS = [
    "AUTOVIDEO_APP_NAME",
    "AUTOVIDEO_ENVIRONMENT",
    "AUTOVIDEO_HOST",
    "AUTOVIDEO_PORT",
    "AUTOVIDEO_DATA_DIR",
    "AUTOVIDEO_FFMPEG_PATH",
    "AUTOVIDEO_FISH_SPEECH_URL",
]


def test_settings_have_safe_defaults(monkeypatch) -> None:
    for env_var in AUTOVIDEO_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)

    settings = Settings(_env_file=None)

    assert settings.app_name == "AutoVideo"
    assert settings.environment == "development"
    assert settings.host == "0.0.0.0"
    assert settings.port == 8090
    assert settings.data_dir == Path("data")
    assert settings.ffmpeg_path == "ffmpeg"
    assert settings.fish_speech_url is None


def test_settings_read_autovideo_environment(monkeypatch) -> None:
    monkeypatch.setenv("AUTOVIDEO_DATA_DIR", "/tmp/autovideo-data")
    monkeypatch.setenv("AUTOVIDEO_PORT", "9010")
    monkeypatch.setenv("AUTOVIDEO_FFMPEG_PATH", "/usr/local/bin/ffmpeg")
    monkeypatch.setenv("AUTOVIDEO_FISH_SPEECH_URL", "http://127.0.0.1:7860")

    settings = Settings(_env_file=None)

    assert settings.data_dir == Path("/tmp/autovideo-data")
    assert settings.port == 9010
    assert settings.ffmpeg_path == "/usr/local/bin/ffmpeg"
    assert settings.fish_speech_url == "http://127.0.0.1:7860"


def test_empty_optional_service_url_is_disabled(monkeypatch) -> None:
    monkeypatch.setenv("AUTOVIDEO_FISH_SPEECH_URL", "")

    settings = Settings(_env_file=None)

    assert settings.fish_speech_url is None


def test_resolved_data_dir_is_absolute(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path / "runtime", _env_file=None)

    assert settings.resolved_data_dir == tmp_path / "runtime"
    assert settings.resolved_data_dir.is_absolute()
