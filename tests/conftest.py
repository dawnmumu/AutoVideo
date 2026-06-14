from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings


LLM_ENV_VARS = (
    "AUTOVIDEO_LLM_PROVIDER",
    "AUTOVIDEO_LLM_BASE_URL",
    "AUTOVIDEO_LLM_API_KEY",
    "AUTOVIDEO_LLM_MODEL",
    "AUTOVIDEO_LLM_TIMEOUT_SECONDS",
    "AUTOVIDEO_LLM_TEMPERATURE",
)


@pytest.fixture(autouse=True)
def clean_llm_environment(monkeypatch) -> None:
    for env_var in LLM_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        ffmpeg_path="missing-autovideo-ffmpeg-binary",
        fish_speech_url=None,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
