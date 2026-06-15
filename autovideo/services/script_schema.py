from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from autovideo.services.script_generator import (
    SYSTEM_PROMPT,
    build_script_from_data,
    repair_structured_script_metadata,
    script_to_response,
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
        script = build_script_from_data(
            llm_payload,
            fallback_title=str(payload.get("topic") or "视频脚本"),
            target_duration=_target_duration(payload),
            scale_to_target=False,
            strict=True,
        )
        script = repair_structured_script_metadata(
            script,
            str(payload.get("topic") or script.title),
            force=False,
        )
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
