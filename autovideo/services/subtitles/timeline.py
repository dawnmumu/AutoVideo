from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

SPLIT_PUNCTUATION = {",", "，", ".", "。", "!", "！", "?", "？", ";", "；"}
TRIM_PUNCTUATION = "".join(SPLIT_PUNCTUATION)


@dataclass
class SubtitleEvent:
    index: int
    shot_index: int
    start_ms: int
    end_ms: int
    text: str
    template: str = "bottom"
    template_variant: str | None = None
    track_id: str = "main"
    spans: list[dict[str, Any]] = field(default_factory=list)
    keyword_spans: list[dict[str, Any]] = field(default_factory=list)
    event_animations: dict[str, Any] = field(default_factory=dict)
    style: dict[str, Any] = field(default_factory=dict)
    position: dict[str, Any] = field(default_factory=dict)


def events_from_render_timeline(timeline: Any) -> list[SubtitleEvent]:
    items = timeline.get("items") if isinstance(timeline, dict) else []
    if not isinstance(items, list):
        return []

    events: list[SubtitleEvent] = []
    for item_index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue

        text = _event_text(item)
        if not text:
            continue

        start_seconds = _coerce_seconds(item.get("start_time"))
        end_seconds = _coerce_seconds(item.get("end_time"))
        if start_seconds is None:
            continue
        if end_seconds is None:
            duration_seconds = _coerce_seconds(item.get("duration"))
            if duration_seconds is None:
                continue
            end_seconds = start_seconds + duration_seconds

        start_ms = _seconds_to_ms(start_seconds)
        end_ms = _seconds_to_ms(end_seconds)
        if end_ms <= start_ms:
            continue

        shot_index = _coerce_int(item.get("shot_index"), default=item_index)
        parts = _split_text(text)
        for part_start, part_end, part_text in _allocate_parts(parts, start_ms, end_ms):
            if part_end <= part_start:
                continue
            events.append(
                SubtitleEvent(
                    index=len(events) + 1,
                    shot_index=shot_index,
                    start_ms=part_start,
                    end_ms=part_end,
                    text=part_text,
                    template="bottom",
                )
            )

    return events


def _event_text(item: dict[str, Any]) -> str:
    for key in ("subtitle", "narration"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _split_text(text: str) -> list[str]:
    parts: list[str] = []
    buffer: list[str] = []

    for index, char in enumerate(text):
        if char in SPLIT_PUNCTUATION and not _is_decimal_point(text, index):
            part = _trim_part("".join(buffer))
            if part:
                parts.append(part)
            buffer = []
            continue
        buffer.append(char)

    part = _trim_part("".join(buffer))
    if part:
        parts.append(part)
    fallback = _trim_part(text)
    return parts or ([fallback] if fallback else [])


def _is_decimal_point(text: str, index: int) -> bool:
    if text[index] != ".":
        return False
    previous_char = text[index - 1] if index > 0 else ""
    next_char = text[index + 1] if index + 1 < len(text) else ""
    return previous_char.isdigit() and next_char.isdigit()


def _trim_part(value: str) -> str:
    return value.strip().strip(TRIM_PUNCTUATION).strip()


def _allocate_parts(parts: list[str], start_ms: int, end_ms: int) -> list[tuple[int, int, str]]:
    if not parts:
        return []
    if len(parts) == 1:
        return [(start_ms, end_ms, parts[0])]

    duration_ms = end_ms - start_ms
    if duration_ms < len(parts):
        return [(start_ms, end_ms, "".join(parts))]

    weights = [max(1, len(part.strip())) for part in parts]
    total_weight = sum(weights)
    allocated: list[tuple[int, int, str]] = []
    current_start = start_ms
    consumed_weight = 0

    for index, (part, weight) in enumerate(zip(parts, weights, strict=True)):
        if index == len(parts) - 1:
            current_end = end_ms
        else:
            consumed_weight += weight
            remaining_parts = len(parts) - index - 1
            proportional_end = start_ms + int(round(duration_ms * consumed_weight / total_weight))
            min_end = current_start + 1
            max_end = end_ms - remaining_parts
            if max_end < min_end:
                return [(start_ms, end_ms, "".join(parts))]
            current_end = min(max(proportional_end, min_end), max_end)
        if current_end <= current_start:
            return [(start_ms, end_ms, "".join(parts))]
        allocated.append((current_start, current_end, part))
        current_start = current_end

    return allocated


def _seconds_to_ms(value: int | float) -> int:
    return int(round(value * 1000))


def _coerce_seconds(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            number = float(candidate)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _coerce_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return default
        return int(value)
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return default
        try:
            number = float(candidate)
        except ValueError:
            return default
        if not math.isfinite(number):
            return default
        return int(number)
    return default
