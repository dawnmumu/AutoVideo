from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from autovideo.services.script_generator import (
    SYSTEM_PROMPT,
    _is_placeholder_title,
    build_script_from_data,
    repair_structured_script_metadata,
    script_matches_topic,
    script_to_response,
    text_matches_topic,
)


AUTOVIDEO_SCRIPT_SCHEMA_PROMPT = SYSTEM_PROMPT


class LlmResponseInvalidError(Exception):
    pass


def normalize_llm_script(
    payload: dict[str, Any],
    llm_payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(llm_payload, dict):
        raise LlmResponseInvalidError()

    try:
        topic = str(payload.get("topic") or "").strip()
        script = build_script_from_data(
            llm_payload,
            fallback_title=topic or "视频脚本",
            target_duration=_target_duration(payload),
            scale_to_target=False,
            strict=True,
        )
        if topic and not text_matches_topic(script.title, topic):
            if _is_placeholder_title(script.title):
                script = script.model_copy(update={"title": topic})
            else:
                raise ValueError("LLM 生成标题与主题不匹配")
        script = repair_structured_script_metadata(
            script,
            topic or script.title,
            force=False,
        )
        if topic and not text_matches_topic(script.title, topic):
            if _is_placeholder_title(script.title):
                script = script.model_copy(update={"title": topic})
            else:
                raise ValueError("LLM 生成标题与主题不匹配")
        if not script_matches_topic(script, topic):
            raise ValueError("LLM 生成内容与主题不匹配")
    except (TypeError, ValueError, ValidationError) as exc:
        raise LlmResponseInvalidError() from exc

    return script_to_response(script, payload, provider="llm")


def _target_duration(payload: dict[str, Any]) -> float | None:
    value = payload.get("duration_seconds")
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    return None
