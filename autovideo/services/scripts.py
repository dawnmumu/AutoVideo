from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import httpx

from autovideo.core.settings import Settings
from autovideo.services.tasks import encoded_json_size

ScriptProvider = Literal["auto", "llm_only", "heuristic"]
LLM_SHOT_REQUIRED_FIELDS = frozenset(
    {
        "index",
        "duration",
        "narration",
        "subtitle",
        "visual_description",
        "keywords",
    }
)


class ScriptTopicRequiredError(Exception):
    pass


class ScriptPayloadTooLargeError(Exception):
    def __init__(self, payload_bytes: int, max_bytes: int) -> None:
        self.payload_bytes = payload_bytes
        self.max_bytes = max_bytes
        super().__init__(str(payload_bytes))


class LlmNotConfiguredError(Exception):
    pass


class LlmResponseInvalidError(Exception):
    pass


class LlmClient(Protocol):
    def generate(self, payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
        ...


class FakeLlmClient:
    def __init__(self, response_payload: dict[str, Any]) -> None:
        self.response_payload = response_payload

    def generate(self, payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
        return deepcopy(self.response_payload)


class OpenAICompatibleLlmClient:
    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self.http_client = http_client

    def generate(self, payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
        if not _llm_configured(settings):
            raise LlmNotConfiguredError()

        if self.http_client is not None:
            return self._generate_with_client(self.http_client, payload, settings)

        with httpx.Client() as http_client:
            return self._generate_with_client(http_client, payload, settings)

    def _generate_with_client(
        self,
        http_client: httpx.Client,
        payload: dict[str, Any],
        settings: Settings,
    ) -> dict[str, Any]:
        response = http_client.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=settings.llm_timeout_seconds,
            json={
                "model": settings.llm_model,
                "temperature": settings.llm_temperature,
                "response_format": {"type": "json_object"},
                "messages": [
                    {
                        "role": "system",
                        "content": "Return an AutoVideo shot script as JSON.",
                    },
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False),
                    },
                ],
            },
        )
        response.raise_for_status()
        return _parse_openai_response(response)


def validate_script_request(payload: dict[str, Any], settings: Settings) -> None:
    payload_bytes = encoded_json_size(payload)
    if payload_bytes > settings.max_script_payload_bytes:
        raise ScriptPayloadTooLargeError(
            payload_bytes,
            settings.max_script_payload_bytes,
        )
    if not str(payload.get("topic", "")).strip():
        raise ScriptTopicRequiredError()


def heuristic_script(payload: dict[str, Any]) -> dict[str, Any]:
    topic = str(payload["topic"]).strip()
    duration_seconds = int(payload.get("duration_seconds") or 30)
    aspect_ratio = str(payload.get("aspect_ratio") or "9:16")
    selling_points = [
        str(item).strip()
        for item in payload.get("selling_points", [])
        if str(item).strip()
    ]
    base_keywords = selling_points or [topic]
    shot_count = max(3, min(6, duration_seconds // 5 or 3))
    base_duration = max(1, duration_seconds // shot_count)
    extra_seconds = max(0, duration_seconds - base_duration * shot_count)
    shots = []

    for index in range(1, shot_count + 1):
        keyword = base_keywords[(index - 1) % len(base_keywords)]
        shot_duration = base_duration + (1 if index <= extra_seconds else 0)
        shots.append(
            {
                "index": index,
                "duration": shot_duration,
                "narration": f"{topic}，镜头 {index} 展示{keyword}。",
                "subtitle": f"{topic} · {keyword}",
                "visual_description": (
                    f"{topic} related scene, {keyword}, clean commercial video"
                ),
                "keywords": [topic, keyword, "commercial video"],
            }
        )

    return {
        "id": uuid.uuid4().hex,
        "title": f"{topic}短视频",
        "topic": topic,
        "aspect_ratio": aspect_ratio,
        "duration_seconds": duration_seconds,
        "shots": shots,
        "provider": "heuristic",
        "created_at": datetime.now(UTC).isoformat(),
    }


def normalize_llm_script(
    payload: dict[str, Any],
    llm_payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(llm_payload, dict):
        raise LlmResponseInvalidError()
    shots = llm_payload.get("shots")
    if not isinstance(shots, list) or not shots:
        raise LlmResponseInvalidError()
    for shot in shots:
        if not isinstance(shot, dict):
            raise LlmResponseInvalidError()
        if not LLM_SHOT_REQUIRED_FIELDS.issubset(shot):
            raise LlmResponseInvalidError()
        if not isinstance(shot["keywords"], list):
            raise LlmResponseInvalidError()

    topic = str(payload["topic"]).strip()
    return {
        "id": uuid.uuid4().hex,
        "title": str(llm_payload.get("title") or f"{topic}短视频"),
        "topic": topic,
        "aspect_ratio": str(payload.get("aspect_ratio") or "9:16"),
        "duration_seconds": int(payload.get("duration_seconds") or 30),
        "shots": shots,
        "provider": "llm",
        "created_at": datetime.now(UTC).isoformat(),
    }


def _parse_openai_response(response: httpx.Response) -> dict[str, Any]:
    try:
        response_payload = response.json()
    except ValueError as exc:
        raise LlmResponseInvalidError() from exc

    content = _extract_openai_message_content(response_payload)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LlmResponseInvalidError() from exc
    if not isinstance(parsed, dict):
        raise LlmResponseInvalidError()
    return parsed


def _extract_openai_message_content(response_payload: Any) -> str:
    if not isinstance(response_payload, dict):
        raise LlmResponseInvalidError()

    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LlmResponseInvalidError()

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise LlmResponseInvalidError()

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise LlmResponseInvalidError()

    content = message.get("content")
    if not isinstance(content, str):
        raise LlmResponseInvalidError()
    return content


def generate_script(
    payload: dict[str, Any],
    settings: Settings,
    *,
    llm_client: LlmClient | None = None,
) -> dict[str, Any]:
    validate_script_request(payload, settings)

    provider: str = payload.get("provider") or "auto"
    if provider == "heuristic":
        return heuristic_script(payload)

    if provider == "llm_only" and not _llm_configured(settings):
        raise LlmNotConfiguredError()

    if _llm_configured(settings):
        client = llm_client or OpenAICompatibleLlmClient()
        try:
            llm_payload = client.generate(payload, settings)
            return normalize_llm_script(payload, llm_payload)
        except (
            httpx.HTTPError,
            KeyError,
            json.JSONDecodeError,
            LlmResponseInvalidError,
        ):
            if provider == "llm_only":
                raise
            return heuristic_script(payload)

    return heuristic_script(payload)


def _llm_configured(settings: Settings) -> bool:
    return bool(settings.llm_base_url and settings.llm_api_key and settings.llm_model)
