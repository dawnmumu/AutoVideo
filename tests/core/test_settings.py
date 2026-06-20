from pathlib import Path

import pytest
from pydantic import ValidationError

from autovideo.core.settings import Settings

AUTOVIDEO_ENV_VARS = [
    "AUTOVIDEO_APP_NAME",
    "AUTOVIDEO_ENVIRONMENT",
    "AUTOVIDEO_HOST",
    "AUTOVIDEO_PORT",
    "AUTOVIDEO_DATA_DIR",
    "AUTOVIDEO_FFMPEG_PATH",
    "AUTOVIDEO_FISH_SPEECH_URL",
    "AUTOVIDEO_EDGE_TTS_DEFAULT_VOICE",
    "AUTOVIDEO_MAX_VOICE_PREVIEW_TEXT_CHARS",
    "AUTOVIDEO_MAX_VOICE_PREVIEW_REQUEST_BYTES",
    "AUTOVIDEO_MAX_UPLOAD_BYTES",
    "AUTOVIDEO_MAX_MULTIPART_OVERHEAD_BYTES",
    "AUTOVIDEO_MAX_TASK_MATERIALS",
    "AUTOVIDEO_MAX_TASK_OPTIONS_BYTES",
    "AUTOVIDEO_MAX_TASK_REQUEST_BYTES",
    "AUTOVIDEO_LLM_PROVIDER",
    "AUTOVIDEO_LLM_BASE_URL",
    "AUTOVIDEO_LLM_API_KEY",
    "AUTOVIDEO_LLM_MODEL",
    "AUTOVIDEO_LLM_TIMEOUT_SECONDS",
    "AUTOVIDEO_LLM_TEMPERATURE",
    "AUTOVIDEO_PEXELS_API_KEY",
    "AUTOVIDEO_PIXABAY_API_KEY",
    "AUTOVIDEO_ONLINE_MATERIAL_PROVIDER",
    "AUTOVIDEO_ONLINE_MATERIAL_RESULTS_PER_QUERY",
    "AUTOVIDEO_ONLINE_MATERIAL_DOWNLOAD_TIMEOUT_SECONDS",
    "AUTOVIDEO_ONLINE_MATERIAL_MAX_DOWNLOAD_BYTES",
    "AUTOVIDEO_MAX_ONLINE_MATERIAL_REQUEST_BYTES",
    "AUTOVIDEO_CANDIDATE_TOKEN_SECRET",
    "AUTOVIDEO_CANDIDATE_TOKEN_TTL_SECONDS",
    "AUTOVIDEO_MAX_SCRIPT_PAYLOAD_BYTES",
    "AUTOVIDEO_MAX_ONLINE_MIX_REQUEST_BYTES",
]


@pytest.fixture(autouse=True)
def clean_autovideo_environment(monkeypatch) -> None:
    for env_var in AUTOVIDEO_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)


def test_settings_have_safe_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_name == "AutoVideo"
    assert settings.environment == "development"
    assert settings.host == "0.0.0.0"
    assert settings.port == 8090
    assert settings.data_dir == Path("data")
    assert settings.ffmpeg_path == "ffmpeg"
    assert settings.fish_speech_url is None
    assert settings.edge_tts_default_voice == "zh-CN-XiaoxiaoNeural"
    assert settings.max_voice_preview_text_chars == 300
    assert settings.max_voice_preview_request_bytes == 8192


def test_settings_read_autovideo_environment(monkeypatch) -> None:
    monkeypatch.setenv("AUTOVIDEO_DATA_DIR", "/tmp/autovideo-data")
    monkeypatch.setenv("AUTOVIDEO_PORT", "9010")
    monkeypatch.setenv("AUTOVIDEO_FFMPEG_PATH", "/usr/local/bin/ffmpeg")
    monkeypatch.setenv("AUTOVIDEO_FISH_SPEECH_URL", "http://127.0.0.1:7860")
    monkeypatch.setenv("AUTOVIDEO_EDGE_TTS_DEFAULT_VOICE", "zh-CN-YunxiNeural")
    monkeypatch.setenv("AUTOVIDEO_MAX_VOICE_PREVIEW_TEXT_CHARS", "180")
    monkeypatch.setenv("AUTOVIDEO_MAX_VOICE_PREVIEW_REQUEST_BYTES", "4096")

    settings = Settings(_env_file=None)

    assert settings.data_dir == Path("/tmp/autovideo-data")
    assert settings.port == 9010
    assert settings.ffmpeg_path == "/usr/local/bin/ffmpeg"
    assert settings.fish_speech_url == "http://127.0.0.1:7860"
    assert settings.edge_tts_default_voice == "zh-CN-YunxiNeural"
    assert settings.max_voice_preview_text_chars == 180
    assert settings.max_voice_preview_request_bytes == 4096


def test_empty_optional_service_url_is_disabled(monkeypatch) -> None:
    monkeypatch.setenv("AUTOVIDEO_FISH_SPEECH_URL", "")

    settings = Settings(_env_file=None)

    assert settings.fish_speech_url is None


def test_resolved_data_dir_is_absolute(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path / "runtime", _env_file=None)

    assert settings.resolved_data_dir == tmp_path / "runtime"
    assert settings.resolved_data_dir.is_absolute()


def test_online_remix_settings_have_safe_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.llm_provider == "openai_compatible"
    assert settings.llm_base_url is None
    assert settings.llm_api_key is None
    assert settings.llm_model is None
    assert settings.llm_timeout_seconds == 45
    assert settings.llm_temperature == 0.6
    assert settings.pexels_api_key is None
    assert settings.pixabay_api_key is None
    assert settings.online_material_provider == "auto"
    assert settings.online_material_results_per_query == 8
    assert settings.online_material_download_timeout_seconds == 60
    assert settings.online_material_max_download_bytes == 524288000
    assert settings.max_online_material_request_bytes == 65536
    assert settings.candidate_token_secret is None
    assert settings.candidate_token_ttl_seconds == 1800
    assert settings.max_script_payload_bytes == 65536
    assert settings.max_online_mix_request_bytes == 2097152


def test_empty_secret_and_api_keys_are_disabled(monkeypatch) -> None:
    monkeypatch.setenv("AUTOVIDEO_LLM_BASE_URL", "")
    monkeypatch.setenv("AUTOVIDEO_LLM_API_KEY", "")
    monkeypatch.setenv("AUTOVIDEO_LLM_MODEL", "")
    monkeypatch.setenv("AUTOVIDEO_PEXELS_API_KEY", "")
    monkeypatch.setenv("AUTOVIDEO_PIXABAY_API_KEY", "")
    monkeypatch.setenv("AUTOVIDEO_CANDIDATE_TOKEN_SECRET", "")

    settings = Settings(_env_file=None)

    assert settings.llm_base_url is None
    assert settings.llm_api_key is None
    assert settings.llm_model is None
    assert settings.pexels_api_key is None
    assert settings.pixabay_api_key is None
    assert settings.candidate_token_secret is None


def test_online_remix_settings_read_environment(monkeypatch) -> None:
    monkeypatch.setenv("AUTOVIDEO_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("AUTOVIDEO_LLM_BASE_URL", "https://llm.example.test/v1")
    monkeypatch.setenv("AUTOVIDEO_LLM_API_KEY", "test-key")
    monkeypatch.setenv("AUTOVIDEO_LLM_MODEL", "test-model")
    monkeypatch.setenv("AUTOVIDEO_PEXELS_API_KEY", "pexels-key")
    monkeypatch.setenv("AUTOVIDEO_PIXABAY_API_KEY", "pixabay-key")
    monkeypatch.setenv("AUTOVIDEO_ONLINE_MATERIAL_PROVIDER", "auto")
    monkeypatch.setenv("AUTOVIDEO_CANDIDATE_TOKEN_SECRET", "candidate-secret")
    monkeypatch.setenv("AUTOVIDEO_CANDIDATE_TOKEN_TTL_SECONDS", "60")

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "openai_compatible"
    assert settings.llm_base_url == "https://llm.example.test/v1"
    assert settings.llm_api_key == "test-key"
    assert settings.llm_model == "test-model"
    assert settings.pexels_api_key == "pexels-key"
    assert settings.pixabay_api_key == "pixabay-key"
    assert settings.online_material_provider == "auto"
    assert settings.candidate_token_secret == "candidate-secret"
    assert settings.candidate_token_ttl_seconds == 60


@pytest.mark.parametrize(
    ("env_var", "value"),
    [
        ("AUTOVIDEO_LLM_PROVIDER", "anthropic"),
        ("AUTOVIDEO_ONLINE_MATERIAL_PROVIDER", "pexels"),
    ],
)
def test_provider_settings_reject_unsupported_environment_values(
    monkeypatch,
    env_var: str,
    value: str,
) -> None:
    monkeypatch.setenv(env_var, value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
