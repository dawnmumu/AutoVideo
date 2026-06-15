from __future__ import annotations

import math
import re
import uuid
from datetime import UTC, datetime
from typing import Any

_POSITIVE_INTEGER_RE = re.compile(r"[1-9]\d*")
_NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)")
_POSITIVE_NUMBER_RE = re.compile(r"(?:\d+(?:\.\d+)?|\.\d+)")

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
AUTOVIDEO_SCRIPT_SCHEMA_PROMPT = """Return only a JSON object for an AutoVideo shot script.
The top-level object must have:
- title: string
- shots: array

Each shots item must have exactly these user-facing fields:
- index: positive integer, starting at 1
- duration: number of seconds for this shot
- narration: spoken narration text
- subtitle: short on-screen subtitle text
- visual_description: concise English search phrase or visual scene description
- keywords: array of 1-5 short English search keywords for stock video search

Do not wrap the JSON in markdown. Do not add explanatory text."""


class LlmResponseInvalidError(Exception):
    pass


def normalize_llm_script(
    payload: dict[str, Any],
    llm_payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(llm_payload, dict):
        raise LlmResponseInvalidError()
    shots = llm_payload.get("shots")
    if not isinstance(shots, list) or not shots:
        raise LlmResponseInvalidError()
    normalized_shots = []
    for fallback_index, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict):
            raise LlmResponseInvalidError()
        normalized_shots.append(_normalize_llm_shot(payload, shot, fallback_index))

    topic = str(payload["topic"]).strip()
    return {
        "id": uuid.uuid4().hex,
        "title": str(llm_payload.get("title") or f"{topic}短视频"),
        "topic": topic,
        "aspect_ratio": str(payload.get("aspect_ratio") or "9:16"),
        "duration_seconds": int(payload.get("duration_seconds") or 30),
        "shots": normalized_shots,
        "provider": "llm",
        "created_at": datetime.now(UTC).isoformat(),
    }


def _normalize_llm_shot(
    payload: dict[str, Any],
    shot: dict[str, Any],
    fallback_index: int,
) -> dict[str, Any]:
    if LLM_SHOT_REQUIRED_FIELDS.issubset(shot):
        normalized = {field: shot[field] for field in LLM_SHOT_REQUIRED_FIELDS}
    elif _has_common_llm_aliases(shot):
        visual_description = _first_non_empty_text(
            shot,
            "visual_description",
            "description",
            "shot_description",
            "visual",
        )
        normalized = {
            "index": _coerce_positive_int(
                _first_present(shot, "index", "shot_id", default=fallback_index)
            ),
            "duration": _coerce_positive_duration(
                _first_present(shot, "duration", default=None),
                start_time=_first_present(shot, "start_time", default=None),
                end_time=_first_present(shot, "end_time", default=None),
            ),
            "narration": _first_non_empty_text(
                shot,
                "narration",
                "voiceover",
                "voice_over",
                "audio_cue",
            ),
            "subtitle": _first_non_empty_text(
                shot,
                "subtitle",
                "caption",
                "description",
            ),
            "visual_description": visual_description,
            "keywords": _normalize_keywords(
                shot.get("keywords"),
                topic=str(payload["topic"]).strip(),
                visual_description=visual_description,
                allow_fallback=True,
            ),
        }
    else:
        raise LlmResponseInvalidError()

    normalized["index"] = _coerce_positive_int(normalized["index"])
    normalized["duration"] = _coerce_positive_duration(normalized["duration"])
    normalized["narration"] = _require_text(normalized["narration"])
    normalized["subtitle"] = _require_text(normalized["subtitle"])
    normalized["visual_description"] = _require_text(normalized["visual_description"])
    normalized["keywords"] = _normalize_keywords(
        normalized["keywords"],
        topic=str(payload["topic"]).strip(),
        visual_description=normalized["visual_description"],
        allow_fallback=False,
    )
    return normalized


def _has_common_llm_aliases(shot: dict[str, Any]) -> bool:
    return any(
        key in shot
        for key in (
            "shot_id",
            "start_time",
            "end_time",
            "description",
            "shot_description",
            "audio_cue",
            "camera_movement",
            "voiceover",
            "voice_over",
            "caption",
            "visual",
        )
    )


def _first_present(
    shot: dict[str, Any],
    *keys: str,
    default: Any,
) -> Any:
    for key in keys:
        if key in shot:
            return shot[key]
    return default


def _first_non_empty_text(shot: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = shot.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise LlmResponseInvalidError()


def _require_text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LlmResponseInvalidError()
    return value.strip()


def _coerce_positive_int(value: Any) -> int:
    if isinstance(value, bool):
        raise LlmResponseInvalidError()
    if isinstance(value, int):
        integer = value
    elif isinstance(value, float) and math.isfinite(value) and value.is_integer():
        integer = int(value)
    elif isinstance(value, str) and _POSITIVE_INTEGER_RE.fullmatch(value.strip()):
        integer = int(value.strip())
    else:
        raise LlmResponseInvalidError()

    if integer <= 0:
        raise LlmResponseInvalidError()
    return integer


def _coerce_positive_duration(
    value: Any,
    *,
    start_time: Any = None,
    end_time: Any = None,
) -> int | float:
    if value is None and start_time is not None and end_time is not None:
        duration = _coerce_number(end_time, positive=False) - _coerce_number(
            start_time,
            positive=False,
        )
    else:
        duration = _coerce_number(value, positive=True)

    if duration <= 0:
        raise LlmResponseInvalidError()
    if duration.is_integer():
        return int(duration)
    return duration


def _normalize_keywords(
    value: Any,
    *,
    topic: str,
    visual_description: str,
    allow_fallback: bool,
) -> list[str]:
    if isinstance(value, list):
        if not value:
            raise LlmResponseInvalidError()
        keywords = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise LlmResponseInvalidError()
            keywords.append(item.strip())
        return keywords[:5]
    elif value is not None:
        raise LlmResponseInvalidError()

    if not allow_fallback:
        raise LlmResponseInvalidError()

    visual_keyword = visual_description.split("，", 1)[0].split(",", 1)[0].strip()
    visual_keyword = visual_keyword.rstrip("。. ")
    keywords = [topic]
    if visual_keyword and visual_keyword != topic:
        keywords.append(visual_keyword)
    return keywords[:5]


def _coerce_number(value: Any, *, positive: bool) -> float:
    if isinstance(value, bool):
        raise LlmResponseInvalidError()

    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        pattern = _POSITIVE_NUMBER_RE if positive else _NUMBER_RE
        if not pattern.fullmatch(text):
            raise LlmResponseInvalidError()
        number = float(text)
    else:
        raise LlmResponseInvalidError()

    if not math.isfinite(number):
        raise LlmResponseInvalidError()
    if positive and number <= 0:
        raise LlmResponseInvalidError()
    return number
