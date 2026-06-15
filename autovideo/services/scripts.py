from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Literal, Protocol

import httpx
from pydantic import ValidationError

from autovideo.core.settings import Settings
from autovideo.services.script_schema import (
    AUTOVIDEO_SCRIPT_SCHEMA_PROMPT,
    LlmResponseInvalidError,
    normalize_llm_script,
)
from autovideo.services.script_generator import (
    PLAIN_TEXT_ENRICH_SYSTEM_PROMPT,
    ScriptTextInvalidError,
    analyze_script_text,
    build_plain_text_enriched_script,
    extract_json_content,
    generate_fallback_script,
    has_spoken_content,
    script_to_response,
)
from autovideo.services.tasks import encoded_json_size

ScriptProvider = Literal["auto", "llm_only", "heuristic"]
PLAIN_TEXT_ENRICH_MODE = "plain_text_enrich"


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
        system_prompt, user_content = _build_llm_messages(payload)
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
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_content,
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


def _build_llm_messages(payload: dict[str, Any]) -> tuple[str, str]:
    if payload.get("_script_mode") == PLAIN_TEXT_ENRICH_MODE:
        return PLAIN_TEXT_ENRICH_SYSTEM_PROMPT, _build_plain_text_enrich_user_prompt(payload)
    return AUTOVIDEO_SCRIPT_SCHEMA_PROMPT, json.dumps(payload, ensure_ascii=False)


def _build_plain_text_enrich_user_prompt(payload: dict[str, Any]) -> str:
    topic = str(payload.get("topic") or "自定义脚本视频").strip() or "自定义脚本视频"
    raw_parts = payload.get("parts")
    parts = raw_parts if isinstance(raw_parts, list) else []
    numbered_lines = "\n".join(
        f"{index}. {str(part).strip()}"
        for index, part in enumerate(parts, start=1)
        if str(part).strip()
    )
    return f"""标题/主题：{topic}

已定稿旁白句子（必须逐字保留）：
{numbered_lines}

请为每句补充适合视频素材检索的画面描述和关键词。
注意：
- narration 字段必须和对应原句完全一致
- subtitle 字段用于屏幕显示，可等于 narration，也可更短或不同
- 相邻句的关键词不要返回几乎一模一样的一组
- keywords 请优先体现标题主题、场景、动作、人物/物体、结果
- 不要解释，只返回 JSON"""


def _parse_openai_response(response: httpx.Response) -> dict[str, Any]:
    try:
        response_payload = response.json()
    except ValueError as exc:
        raise LlmResponseInvalidError() from exc

    content = _extract_openai_message_content(response_payload)
    try:
        parsed = json.loads(extract_json_content(content))
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
    script_text = str(payload.get("script_text") or "").strip()
    if script_text and not has_spoken_content(script_text):
        raise ScriptTextInvalidError("脚本中没有可用内容")

    provider: str = payload.get("provider") or "auto"
    if script_text:
        return _generate_script_from_text(payload, settings, provider, llm_client)

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


def _generate_script_from_text(
    payload: dict[str, Any],
    settings: Settings,
    provider: str,
    llm_client: LlmClient | None,
) -> dict[str, Any]:
    if provider == "heuristic":
        return heuristic_script(payload)

    if provider == "llm_only" and not _llm_configured(settings):
        raise LlmNotConfiguredError()

    if not _llm_configured(settings):
        return heuristic_script(payload)

    client = llm_client or OpenAICompatibleLlmClient()
    try:
        result = analyze_script_text(
            str(payload.get("script_text") or ""),
            topic=str(payload.get("topic") or "") or None,
            max_single_duration=payload.get("max_single_duration"),
            plain_text_enricher=_build_plain_text_enricher(client, settings),
        )
    except (
        httpx.HTTPError,
        KeyError,
        json.JSONDecodeError,
        LlmResponseInvalidError,
    ):
        if provider == "llm_only":
            raise
        return heuristic_script(payload)

    return script_to_response(
        result["script"],
        payload,
        provider="llm",
        script_text=result["script_text"],
        analysis=result["analysis"],
    )


def _build_plain_text_enricher(
    client: LlmClient,
    settings: Settings,
):
    def enrich(parts: list[str], topic: str):
        llm_payload = client.generate(
            {
                "_script_mode": PLAIN_TEXT_ENRICH_MODE,
                "topic": topic,
                "parts": parts,
            },
            settings,
        )
        try:
            return build_plain_text_enriched_script(parts, topic, llm_payload)
        except (TypeError, ValueError, ValidationError) as exc:
            raise LlmResponseInvalidError() from exc

    return enrich


def _llm_configured(settings: Settings) -> bool:
    return bool(settings.llm_base_url and settings.llm_api_key and settings.llm_model)
