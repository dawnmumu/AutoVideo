from __future__ import annotations

import copy
from typing import Any

from autovideo.services.subtitles.timeline import SubtitleEvent

PUNCH_CUES = ("！", "!", "立即", "现在", "关键")
HIGHLIGHT_CUES = ("AI", "效率", "降低", "提升", "自动")


def assign_template_roles(
    events: list[SubtitleEvent],
    template_set: dict[str, Any],
    *,
    random_seed: int | None = None,
) -> list[SubtitleEvent]:
    del random_seed

    assigned = copy.deepcopy(events)
    for event in assigned:
        role = _role_for_text(event.text)
        event.template = role
        event.template_variant = _first_variant_id(template_set, role)
    return assigned


def _role_for_text(text: str) -> str:
    if any(cue in text for cue in PUNCH_CUES):
        return "punch"
    if any(cue in text for cue in HIGHLIGHT_CUES):
        return "highlight"
    return "bottom"


def _first_variant_id(template_set: dict[str, Any], role: str) -> str | None:
    variants = template_set.get("template_variants") if isinstance(template_set, dict) else {}
    if not isinstance(variants, dict):
        return None

    role_variants = variants.get(role)
    if isinstance(role_variants, list):
        for variant in role_variants:
            if isinstance(variant, dict):
                return _variant_identifier(variant)
        return None

    if isinstance(role_variants, dict):
        for key, variant in role_variants.items():
            if isinstance(variant, dict):
                return _variant_identifier(variant) or str(key)
            return str(key)

    return None


def _variant_identifier(variant: dict[str, Any]) -> str | None:
    for key in ("id", "key", "name"):
        value = variant.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
