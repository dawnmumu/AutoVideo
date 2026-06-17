from __future__ import annotations

import copy
import random
from typing import Any, Callable

from autovideo.services.subtitles.timeline import SubtitleEvent

DEFAULT_KEYWORD_STYLE = {"primary_color": "#FFD54F", "font_scale": 1.15}
KeywordExtractor = Callable[[list[dict[str, Any]], dict[str, Any]], Any]


def apply_keyword_spans(
    events: list[SubtitleEvent],
    template_set: dict[str, Any],
    *,
    keyword_extractor: KeywordExtractor | None = None,
    sample_rate: float = 0.2,
    random_seed: int | None = None,
) -> list[SubtitleEvent]:
    copied = copy.deepcopy(events)
    for event in copied:
        event.keyword_spans = []

    selected = _sample_events(copied, sample_rate=sample_rate, random_seed=random_seed)
    if not selected or keyword_extractor is None:
        return copied

    payload = [{"index": event.index, "text": event.text, "template": event.template} for event in selected]
    context = {"sample_rate": sample_rate}

    try:
        extracted = keyword_extractor(payload, context)
        keywords_by_index = _parse_extracted_keywords(extracted, [event.index for event in selected])
    except Exception:
        return copied

    if keywords_by_index is None:
        return copied

    style = _default_keyword_style(template_set)
    events_by_index = {event.index: event for event in copied}
    for event_index, terms in keywords_by_index.items():
        event = events_by_index.get(event_index)
        if event is None:
            continue

        for term in _valid_terms(event.text, terms):
            span = {
                "selector": {"type": "keyword", "value": term},
                "style": copy.deepcopy(style),
            }
            event.keyword_spans.append(copy.deepcopy(span))
            event.spans.append(span)

    return copied


def _sample_events(
    events: list[SubtitleEvent],
    *,
    sample_rate: float,
    random_seed: int | None,
) -> list[SubtitleEvent]:
    eligible = [event for event in events if event.text.strip()]
    if sample_rate <= 0 or not eligible:
        return []
    if sample_rate >= 1:
        return eligible

    rng = random.Random(random_seed)
    selected = [event for event in eligible if rng.random() < sample_rate]
    return selected or [eligible[0]]


def _parse_extracted_keywords(raw: Any, selected_indexes: list[int]) -> dict[int, list[str]] | None:
    entries = raw.get("keywords") if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        return None

    result: dict[int, list[str]] = {}
    for entry in entries:
        if isinstance(entry, dict):
            event_index = _coerce_int(entry.get("index"))
            if event_index is None and len(selected_indexes) == 1:
                event_index = selected_indexes[0]
            terms = _coerce_terms(entry.get("terms", entry.get("keywords", entry.get("term"))))
        elif isinstance(entry, str) and len(selected_indexes) == 1:
            event_index = selected_indexes[0]
            terms = [entry]
        else:
            continue

        if event_index is None:
            continue
        result.setdefault(event_index, []).extend(terms)

    return result


def _valid_terms(text: str, terms: list[str]) -> list[str]:
    valid: list[str] = []
    seen: set[str] = set()
    for term in terms:
        candidate = term.strip()
        if not candidate or candidate in seen or candidate not in text:
            continue
        valid.append(candidate)
        seen.add(candidate)
        if len(valid) == 2:
            break
    return valid


def _coerce_terms(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            return int(candidate)
        except ValueError:
            return None
    return None


def _default_keyword_style(template_set: dict[str, Any]) -> dict[str, Any]:
    blocks = template_set.get("blocks") if isinstance(template_set, dict) else []
    if isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, dict):
                continue
            spans = block.get("spans")
            if not isinstance(spans, list):
                continue
            for span in spans:
                if not isinstance(span, dict):
                    continue
                selector = span.get("selector")
                style = span.get("style")
                if (
                    isinstance(selector, dict)
                    and selector.get("type") == "keyword"
                    and isinstance(style, dict)
                    and style
                ):
                    return copy.deepcopy(style)
    return copy.deepcopy(DEFAULT_KEYWORD_STYLE)
