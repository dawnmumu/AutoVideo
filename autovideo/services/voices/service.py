from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
import re
from typing import Any, Protocol

from pydantic import BaseModel, Field, field_validator

from autovideo.core.settings import Settings
from autovideo.services.voices.edge_tts import EdgeTtsProvider

PREVIEW_FILENAME_PATTERN = re.compile(r"^edge-tts-[a-f0-9]{24}\.mp3$")


class VoiceProvider(Protocol):
    async def list_voices(self) -> list[dict[str, Any]]:
        ...

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
        ...


class VoiceProviderError(RuntimeError):
    pass


class VoiceNotFoundError(RuntimeError):
    def __init__(self, voice_id: str) -> None:
        super().__init__(voice_id)
        self.voice_id = voice_id


class VoicePreviewTextTooLongError(ValueError):
    def __init__(self, max_chars: int) -> None:
        super().__init__(f"Voice preview text exceeds {max_chars} characters")
        self.max_chars = max_chars


class VoicePreviewRequest(BaseModel):
    text: str = Field(min_length=1)
    voice_id: str = Field(min_length=1)
    rate: str = "+0%"
    volume: str = "+0%"
    pitch: str = "+0Hz"

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text is required")
        return stripped

    @field_validator("rate", "volume")
    @classmethod
    def validate_percent(cls, value: str) -> str:
        if not re.fullmatch(r"[+-]\d{1,3}%", value):
            raise ValueError("prosody percent must look like +0%")
        return value

    @field_validator("pitch")
    @classmethod
    def validate_pitch(cls, value: str) -> str:
        if not re.fullmatch(r"[+-]\d{1,3}Hz", value):
            raise ValueError("pitch must look like +0Hz")
        return value


def _voice_tag_list(raw_voice: dict[str, Any], key: str) -> list[str]:
    voice_tag = raw_voice.get("VoiceTag")
    if not isinstance(voice_tag, dict):
        return []
    values = voice_tag.get(key)
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if str(value).strip()]


def normalize_edge_voice(raw_voice: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw_voice, dict):
        raise ValueError("Edge TTS voice entry must be an object")
    voice_id = str(raw_voice.get("ShortName") or "").strip()
    if not voice_id:
        raise ValueError("Edge TTS voice is missing ShortName")
    name = str(raw_voice.get("FriendlyName") or voice_id).strip()
    locale = str(raw_voice.get("Locale") or "").strip()
    gender = str(raw_voice.get("Gender") or "").strip()

    return {
        "id": voice_id,
        "name": name,
        "provider": "edge_tts",
        "locale": locale,
        "gender": gender,
        "content_categories": _voice_tag_list(raw_voice, "ContentCategories"),
        "personalities": _voice_tag_list(raw_voice, "VoicePersonalities"),
    }


class VoiceCenterService:
    def __init__(self, settings: Settings, provider: VoiceProvider | None = None) -> None:
        self.settings = settings
        self.provider = provider or EdgeTtsProvider()

    async def list_voices(
        self,
        *,
        locale: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        try:
            raw_voices = await self.provider.list_voices()
        except Exception as exc:  # pragma: no cover - provider details are external
            raise VoiceProviderError(str(exc)) from exc

        try:
            voices = [normalize_edge_voice(raw_voice) for raw_voice in raw_voices]
        except (TypeError, ValueError) as exc:
            raise VoiceProviderError(str(exc)) from exc
        if locale:
            locale_value = locale.strip().lower()
            voices = [
                voice for voice in voices if str(voice["locale"]).lower() == locale_value
            ]
        if query:
            query_value = query.strip().lower()
            voices = [
                voice
                for voice in voices
                if query_value in str(voice["id"]).lower()
                or query_value in str(voice["name"]).lower()
            ]

        return {"provider": "edge_tts", "items": voices, "total": len(voices)}

    async def create_preview(self, request: VoicePreviewRequest) -> dict[str, Any]:
        if len(request.text) > self.settings.max_voice_preview_text_chars:
            raise VoicePreviewTextTooLongError(self.settings.max_voice_preview_text_chars)

        await self._require_voice(request.voice_id)
        preview_dir = self.preview_dir()
        preview_dir.mkdir(parents=True, exist_ok=True)
        filename = self._preview_filename(request)
        output_path = preview_dir / filename

        try:
            await self.provider.synthesize_to_file(
                text=request.text,
                voice_id=request.voice_id,
                output_path=output_path,
                rate=request.rate,
                volume=request.volume,
                pitch=request.pitch,
            )
        except Exception as exc:  # pragma: no cover - provider details are external
            if output_path.exists():
                output_path.unlink()
            raise VoiceProviderError(str(exc)) from exc

        return {
            "voice_id": request.voice_id,
            "filename": filename,
            "audio_url": f"/api/voices/previews/{filename}",
            "media_type": "audio/mpeg",
            "created_at": datetime.now(UTC).isoformat(),
        }

    def preview_dir(self) -> Path:
        return self.settings.resolved_data_dir / "voices" / "previews"

    def preview_path(self, filename: str) -> Path:
        if not PREVIEW_FILENAME_PATTERN.fullmatch(filename):
            raise FileNotFoundError(filename)
        path = (self.preview_dir() / filename).resolve()
        preview_dir = self.preview_dir().resolve()
        if preview_dir not in path.parents:
            raise FileNotFoundError(filename)
        if not path.is_file():
            raise FileNotFoundError(filename)
        return path

    async def _require_voice(self, voice_id: str) -> None:
        voices = await self.list_voices()
        if not any(voice["id"] == voice_id for voice in voices["items"]):
            raise VoiceNotFoundError(voice_id)

    @staticmethod
    def _preview_filename(request: VoicePreviewRequest) -> str:
        digest = sha256(
            "\n".join(
                [
                    request.voice_id,
                    request.rate,
                    request.volume,
                    request.pitch,
                    request.text,
                ]
            ).encode("utf-8")
        ).hexdigest()
        return f"edge-tts-{digest[:24]}.mp3"
