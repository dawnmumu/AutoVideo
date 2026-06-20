import asyncio
from pathlib import Path
from typing import Any

import pytest

from autovideo.core.settings import Settings
from autovideo.services.voices import (
    VoiceCenterService,
    VoicePreviewRequest,
    VoicePreviewTextTooLongError,
    VoiceProviderError,
    normalize_edge_voice,
)


EDGE_VOICE_FIXTURES = [
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
        self.voices = voices or EDGE_VOICE_FIXTURES
        self.calls: list[dict[str, Any]] = []

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
        self.calls.append(
            {
                "text": text,
                "voice_id": voice_id,
                "output_path": output_path,
                "rate": rate,
                "volume": volume,
                "pitch": pitch,
            }
        )
        output_path.write_bytes(b"fake-mp3-data")


def voice_settings(tmp_path: Path, **overrides: Any) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path,
        fish_speech_url=None,
        **overrides,
    )


def test_normalize_edge_voice_exposes_public_voice_fields() -> None:
    voice = normalize_edge_voice(EDGE_VOICE_FIXTURES[0])

    assert voice == {
        "id": "zh-CN-XiaoxiaoNeural",
        "name": "Microsoft Xiaoxiao Online (Natural) - Chinese (Mainland)",
        "provider": "edge_tts",
        "locale": "zh-CN",
        "gender": "Female",
        "content_categories": ["General"],
        "personalities": ["Warm", "Friendly"],
    }


def test_voice_service_lists_edge_voices_with_locale_filter(tmp_path: Path) -> None:
    service = VoiceCenterService(
        voice_settings(tmp_path),
        provider=FakeEdgeTtsProvider(),
    )

    result = asyncio.run(service.list_voices(locale="zh-CN"))

    assert [voice["id"] for voice in result["items"]] == ["zh-CN-XiaoxiaoNeural"]
    assert result["provider"] == "edge_tts"
    assert result["total"] == 1


def test_voice_service_maps_malformed_edge_voice_to_provider_error(tmp_path: Path) -> None:
    service = VoiceCenterService(
        voice_settings(tmp_path),
        provider=FakeEdgeTtsProvider(voices=[{"FriendlyName": "Missing short name"}]),
    )

    with pytest.raises(VoiceProviderError):
        asyncio.run(service.list_voices())


def test_voice_service_writes_preview_without_exposing_local_path(tmp_path: Path) -> None:
    provider = FakeEdgeTtsProvider()
    service = VoiceCenterService(voice_settings(tmp_path), provider=provider)

    result = asyncio.run(
        service.create_preview(
            VoicePreviewRequest(
                text="你好，欢迎使用 AutoVideo。",
                voice_id="zh-CN-XiaoxiaoNeural",
                rate="+5%",
                volume="+0%",
                pitch="+0Hz",
            )
        )
    )

    assert result["voice_id"] == "zh-CN-XiaoxiaoNeural"
    assert result["audio_url"].startswith("/api/voices/previews/")
    assert result["media_type"] == "audio/mpeg"
    assert "path" not in result
    assert provider.calls == [
        {
            "text": "你好，欢迎使用 AutoVideo。",
            "voice_id": "zh-CN-XiaoxiaoNeural",
            "output_path": tmp_path / "voices" / "previews" / result["filename"],
            "rate": "+5%",
            "volume": "+0%",
            "pitch": "+0Hz",
        }
    ]
    assert (tmp_path / "voices" / "previews" / result["filename"]).read_bytes() == b"fake-mp3-data"


def test_voice_service_rejects_overlong_preview_text(tmp_path: Path) -> None:
    service = VoiceCenterService(
        voice_settings(tmp_path, max_voice_preview_text_chars=8),
        provider=FakeEdgeTtsProvider(),
    )

    with pytest.raises(VoicePreviewTextTooLongError) as exc:
        asyncio.run(
            service.create_preview(
                VoicePreviewRequest(
                    text="这是一段明显超过限制的试听文案",
                    voice_id="zh-CN-XiaoxiaoNeural",
                )
            )
        )

    assert exc.value.max_chars == 8
