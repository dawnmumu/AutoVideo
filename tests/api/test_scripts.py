import httpx
import pytest
from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings


def test_generate_script_heuristic_returns_structured_shots(tmp_path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "精油睡眠放松",
                "provider": "heuristic",
                "duration_seconds": 30,
                "aspect_ratio": "9:16",
                "tone": "自然可信",
                "target_audience": "睡眠质量差的年轻人",
                "selling_points": ["舒缓", "睡前仪式感"],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"]
    assert payload["topic"] == "精油睡眠放松"
    assert payload["aspect_ratio"] == "9:16"
    assert payload["duration_seconds"] == 30
    assert payload["provider"] == "heuristic"
    assert len(payload["shots"]) >= 3
    assert payload["shots"][0]["index"] == 1
    assert payload["shots"][0]["duration"] > 0
    assert payload["shots"][0]["keywords"]


def test_generate_script_auto_falls_back_without_llm(client) -> None:
    assert client.app.state.settings.llm_base_url is None
    assert client.app.state.settings.llm_api_key is None
    assert client.app.state.settings.llm_model is None

    response = client.post(
        "/api/scripts/generate",
        json={"topic": "咖啡店早高峰", "provider": "auto", "duration_seconds": 20},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "heuristic"


def test_generate_script_llm_only_requires_config(client) -> None:
    response = client.post(
        "/api/scripts/generate",
        json={"topic": "咖啡店早高峰", "provider": "llm_only"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "LLM_NOT_CONFIGURED"


def test_generate_script_auto_uses_configured_llm_client(tmp_path) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "LLM 生成脚本",
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "LLM 旁白",
                    "subtitle": "LLM 字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee shop", "morning"],
                }
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={"topic": "咖啡店早高峰", "provider": "auto", "duration_seconds": 20},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "llm"
    assert payload["title"] == "LLM 生成脚本"
    assert payload["shots"][0]["keywords"] == ["coffee shop", "morning"]


def test_generate_script_llm_only_parses_fake_structured_response(tmp_path) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "结构化脚本",
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "oil bottle close up",
                    "keywords": ["oil bottle"],
                }
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "精油睡眠放松",
                "provider": "llm_only",
                "duration_seconds": 15,
            },
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "llm"


def test_generate_script_auto_falls_back_when_llm_http_or_parse_fails(
    tmp_path,
) -> None:
    from autovideo.services.scripts import LlmResponseInvalidError

    class FailingLlmClient:
        def generate(self, payload, settings):
            raise LlmResponseInvalidError()

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FailingLlmClient()

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={"topic": "咖啡店早高峰", "provider": "auto", "duration_seconds": 20},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "heuristic"
    assert payload["topic"] == "咖啡店早高峰"


@pytest.mark.parametrize(
    "llm_payload",
    [
        {"shots": ["bad"]},
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "keywords": ["coffee"],
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": "coffee",
                }
            ]
        },
    ],
)
def test_generate_script_auto_falls_back_when_llm_shot_shape_is_invalid(
    tmp_path,
    llm_payload,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="secret-key-should-not-leak",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(llm_payload)

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={"topic": "咖啡店早高峰", "provider": "auto", "duration_seconds": 20},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "heuristic"
    assert payload["topic"] == "咖啡店早高峰"
    assert "secret-key-should-not-leak" not in response.text


@pytest.mark.parametrize(
    "llm_payload",
    [
        {"shots": ["bad"]},
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                }
            ]
        },
        {
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": "coffee",
                }
            ]
        },
    ],
)
def test_generate_script_llm_only_rejects_invalid_llm_shot_shape(
    tmp_path,
    llm_payload,
) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="secret-key-should-not-leak",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(llm_payload)

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={"topic": "咖啡店早高峰", "provider": "llm_only"},
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"
    assert "secret-key-should-not-leak" not in response.text


@pytest.mark.parametrize(
    "response_payload",
    [
        {"choices": []},
        {"choices": ["not-a-dict"]},
        ["not-a-dict"],
    ],
)
def test_openai_llm_client_wraps_invalid_response_shape(response_payload) -> None:
    from autovideo.services.scripts import (
        LlmResponseInvalidError,
        OpenAICompatibleLlmClient,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_payload)

    settings = Settings(
        _env_file=None,
        llm_base_url="https://llm.example.test/v1",
        llm_api_key="test-key",
        llm_model="test-model",
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        llm_client = OpenAICompatibleLlmClient(http_client=http_client)

        with pytest.raises(LlmResponseInvalidError):
            llm_client.generate({"topic": "咖啡店早高峰"}, settings)


def test_openai_llm_client_uses_context_manager_for_default_http_client(
    monkeypatch,
) -> None:
    from autovideo.services import scripts
    from autovideo.services.scripts import OpenAICompatibleLlmClient

    created_clients = []

    class ContextHttpClient:
        def __init__(self) -> None:
            self.entered = False
            self.exited = False
            created_clients.append(self)

        def __enter__(self):
            self.entered = True
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            self.exited = True

        def post(self, *args, **kwargs) -> httpx.Response:
            assert self.entered
            return httpx.Response(
                200,
                request=httpx.Request("POST", str(args[0])),
                json={
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"title":"结构化脚本","shots":[{"index":1,'
                                    '"duration":5,"narration":"旁白",'
                                    '"subtitle":"字幕",'
                                    '"visual_description":"coffee shop morning",'
                                    '"keywords":["coffee"]}]}'
                                )
                            }
                        }
                    ]
                },
            )

    monkeypatch.setattr(scripts.httpx, "Client", ContextHttpClient)
    settings = Settings(
        _env_file=None,
        llm_base_url="https://llm.example.test/v1",
        llm_api_key="test-key",
        llm_model="test-model",
    )

    llm_client = OpenAICompatibleLlmClient()
    payload = llm_client.generate({"topic": "咖啡店早高峰"}, settings)

    assert payload["title"] == "结构化脚本"
    assert len(created_clients) == 1
    assert created_clients[0].entered is True
    assert created_clients[0].exited is True


def test_generate_script_llm_only_returns_structured_error_on_llm_failure(
    tmp_path,
) -> None:
    from autovideo.services.scripts import LlmResponseInvalidError

    class FailingLlmClient:
        def generate(self, payload, settings):
            raise LlmResponseInvalidError("secret-key-should-not-leak")

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="secret-key-should-not-leak",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FailingLlmClient()

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={"topic": "咖啡店早高峰", "provider": "llm_only"},
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "LLM_GENERATION_FAILED"
    assert "secret-key-should-not-leak" not in response.text


def test_generate_script_rejects_content_length_with_script_payload_limit(
    tmp_path,
) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            fish_speech_url=None,
            max_script_payload_bytes=8,
        )
    )

    with TestClient(app) as limited_client:
        response = limited_client.post(
            "/api/scripts/generate",
            content=b'{"topic":"too large"}',
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 413
    payload = response.json()
    assert payload["detail"]["code"] == "SCRIPT_PAYLOAD_TOO_LARGE"
    assert payload["detail"]["max_script_payload_bytes"] == 8


def test_generate_script_validates_topic_and_payload(client) -> None:
    blank_response = client.post(
        "/api/scripts/generate",
        json={"topic": "   ", "provider": "heuristic"},
    )
    assert blank_response.status_code == 400
    assert blank_response.json()["detail"]["code"] == "SCRIPT_TOPIC_REQUIRED"

    client.app.state.settings.max_script_payload_bytes = 64
    large_response = client.post(
        "/api/scripts/generate",
        json={"topic": "x"},
    )
    assert large_response.status_code == 413
    payload = large_response.json()
    assert payload["detail"]["code"] == "SCRIPT_PAYLOAD_TOO_LARGE"
    assert payload["detail"]["max_script_payload_bytes"] == 64
    assert payload["detail"]["payload_bytes"] > 64
