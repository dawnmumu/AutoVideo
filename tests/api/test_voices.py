from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings


VOICE_FIXTURES = [
    {
        "ShortName": "zh-CN-XiaoxiaoNeural",
        "FriendlyName": "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
        "Locale": "zh-CN",
        "Gender": "Female",
        "VoiceTag": {
            "ContentCategories": ["General"],
            "VoicePersonalities": ["Warm", "Friendly"],
        },
    },
    {
        "ShortName": "en-US-JennyNeural",
        "FriendlyName": "Microsoft Jenny Online (Natural) - English (United States)",
        "Locale": "en-US",
        "Gender": "Female",
        "VoiceTag": {
            "ContentCategories": ["General"],
            "VoicePersonalities": ["Friendly"],
        },
    },
]


class FakeEdgeTtsProvider:
    def __init__(self, voices: list[dict[str, Any]] | None = None) -> None:
        self.voices = voices or VOICE_FIXTURES

    async def list_voices(self) -> list[dict[str, Any]]:
        return self.voices

    async def synthesize_to_file(
        self,
        *,
        text: str,
        voice_id: str,
        output_path: Path,
        rate: str,
        volume: str,
        pitch: str,
    ) -> None:
        output_path.write_bytes(
            f"{voice_id}|{rate}|{volume}|{pitch}|{text}".encode("utf-8")
        )


class FailingPreviewProvider(FakeEdgeTtsProvider):
    async def synthesize_to_file(
        self,
        *,
        text: str,
        voice_id: str,
        output_path: Path,
        rate: str,
        volume: str,
        pitch: str,
    ) -> None:
        raise OSError(f"cannot write {output_path}")


def voice_client(
    tmp_path: Path,
    *,
    provider: FakeEdgeTtsProvider | None = None,
    **overrides: Any,
) -> TestClient:
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        fish_speech_url=None,
        **overrides,
    )
    app = create_app(settings)
    app.state.edge_tts_provider = provider or FakeEdgeTtsProvider()
    return TestClient(app)


def test_voice_status_reports_edge_tts_and_preview_limits(tmp_path: Path) -> None:
    with voice_client(tmp_path, max_voice_preview_text_chars=180) as client:
        response = client.get("/api/voices/status")

    assert response.status_code == 200
    assert response.json()["edge_tts"] == {
        "enabled": True,
        "provider": "edge_tts",
        "requires_api_key": False,
        "default_voice": "zh-CN-XiaoxiaoNeural",
        "max_preview_text_chars": 180,
    }
    assert response.json()["fish_speech"] == {
        "configured": False,
        "enabled": False,
    }


def test_list_edge_tts_voices_filters_by_locale(tmp_path: Path) -> None:
    with voice_client(tmp_path) as client:
        response = client.get("/api/voices", params={"locale": "zh-CN"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "edge_tts"
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == "zh-CN-XiaoxiaoNeural"
    assert payload["items"][0]["personalities"] == ["Warm", "Friendly"]


def test_list_edge_tts_voices_returns_structured_error_for_malformed_provider_payload(
    tmp_path: Path,
) -> None:
    provider = FakeEdgeTtsProvider(voices=[{"FriendlyName": "Missing short name"}])

    with voice_client(tmp_path, provider=provider) as client:
        response = client.get("/api/voices")

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "VOICE_LIST_FAILED"


def test_list_edge_tts_voices_returns_structured_error_for_non_object_voice(
    tmp_path: Path,
) -> None:
    provider = FakeEdgeTtsProvider(voices=["not-a-voice-object"])

    with voice_client(tmp_path, provider=provider) as client:
        response = client.get("/api/voices")

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "VOICE_LIST_FAILED"


def test_create_voice_preview_and_download_audio(tmp_path: Path) -> None:
    with voice_client(tmp_path) as client:
        response = client.post(
            "/api/voices/preview",
            json={
                "text": "你好，欢迎使用 AutoVideo。",
                "voice_id": "zh-CN-XiaoxiaoNeural",
                "rate": "+5%",
            },
        )
        audio_response = client.get(response.json()["audio_url"])

    assert response.status_code == 201
    payload = response.json()
    assert payload["voice_id"] == "zh-CN-XiaoxiaoNeural"
    assert payload["audio_url"].startswith("/api/voices/previews/")
    assert payload["media_type"] == "audio/mpeg"
    assert "path" not in payload
    assert audio_response.status_code == 200
    assert audio_response.headers["content-type"].startswith("audio/mpeg")
    assert b"zh-CN-XiaoxiaoNeural|+5%" in audio_response.content


def test_create_voice_preview_rejects_unknown_voice(tmp_path: Path) -> None:
    with voice_client(tmp_path) as client:
        response = client.post(
            "/api/voices/preview",
            json={
                "text": "你好",
                "voice_id": "zh-CN-UnknownNeural",
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "VOICE_NOT_FOUND",
        "voice_id": "zh-CN-UnknownNeural",
    }


def test_create_voice_preview_rejects_overlong_text(tmp_path: Path) -> None:
    with voice_client(tmp_path, max_voice_preview_text_chars=6) as client:
        response = client.post(
            "/api/voices/preview",
            json={
                "text": "这是一段太长的试听文本",
                "voice_id": "zh-CN-XiaoxiaoNeural",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "VOICE_PREVIEW_TEXT_TOO_LONG",
        "max_chars": 6,
    }


def test_create_voice_preview_hides_provider_failure_details(tmp_path: Path) -> None:
    with voice_client(tmp_path, provider=FailingPreviewProvider()) as client:
        response = client.post(
            "/api/voices/preview",
            json={
                "text": "你好",
                "voice_id": "zh-CN-XiaoxiaoNeural",
            },
        )

    payload = response.json()
    response_text = response.text
    assert response.status_code == 502
    assert payload["detail"] == {"code": "VOICE_PREVIEW_FAILED"}
    assert str(tmp_path) not in response_text
    assert "voices/previews" not in response_text


def test_create_voice_preview_rejects_oversized_request(tmp_path: Path) -> None:
    with voice_client(tmp_path, max_voice_preview_request_bytes=2) as client:
        response = client.post(
            "/api/voices/preview",
            json={"text": "你好", "voice_id": "zh-CN-XiaoxiaoNeural"},
        )

    assert response.status_code == 413
    assert response.json()["detail"] == {
        "code": "REQUEST_TOO_LARGE",
        "max_request_bytes": 2,
    }


def test_download_voice_preview_rejects_unrecognized_filename(tmp_path: Path) -> None:
    with voice_client(tmp_path) as client:
        response = client.get("/api/voices/previews/not-an-edge-preview.mp3")

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "VOICE_PREVIEW_NOT_FOUND",
        "filename": "not-an-edge-preview.mp3",
    }
