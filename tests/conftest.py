from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    settings = Settings(
        data_dir=tmp_path,
        ffmpeg_path="missing-autovideo-ffmpeg-binary",
        fish_speech_url=None,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
