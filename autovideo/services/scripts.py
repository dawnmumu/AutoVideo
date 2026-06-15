from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Literal, Protocol

import httpx

from autovideo.core.settings import Settings
from autovideo.services.script_schema import (
    AUTOVIDEO_SCRIPT_SCHEMA_PROMPT,
    LlmResponseInvalidError,
    normalize_llm_script,
)
from autovideo.services.script_generator import (
    ScriptTextInvalidError,
    analyze_script_text,
    generate_fallback_script,
    script_to_response,
)
from autovideo.services.tasks import encoded_json_size

ScriptProvider = Literal["auto", "llm_only", "heuristic"]


class ScriptTopicRequiredError(Exception):
    pass


class ScriptPayloadTooLargeError(Exception):
    def __init__(self, payload_bytes: int, max_bytes: int) -> None:
        self.payload_bytes = payload_bytes
        self.max_bytes = max_bytes
        super().__init__(str(payload_bytes))


class LlmNotConfiguredError(Exception):
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
                        "content": AUTOVIDEO_SCRIPT_SCHEMA_PROMPT,
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
    has_topic = bool(str(payload.get("topic", "")).strip())
    has_script_text = bool(str(payload.get("script_text") or "").strip())
    if not has_topic and not has_script_text:
        raise ScriptTopicRequiredError()


def heuristic_script(payload: dict[str, Any]) -> dict[str, Any]:
    topic = str(payload.get("topic") or "").strip()
    script_text = str(payload.get("script_text") or "").strip()
    if script_text:
        result = analyze_script_text(
            script_text,
            topic=topic or None,
            max_single_duration=payload.get("max_single_duration"),
        )
        return script_to_response(
            result["script"],
            payload,
            provider="heuristic",
            script_text=result["script_text"],
            analysis=result["analysis"],
        )

    duration_seconds = int(payload.get("duration_seconds") or 30)
    script = generate_fallback_script(
        topic,
        duration_seconds,
        payload.get("selling_points") or [],
    )
    return script_to_response(script, payload, provider="heuristic")


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
