from __future__ import annotations

import copy
from typing import Any

from autovideo.services.subtitles.models import DEFAULT_TRACK, RENDERER_MODE, SCHEMA_VERSION


def _block(role: str, y: float, size: int) -> dict[str, Any]:
    return {
        "id": f"{role}-main",
        "role": role,
        "track_id": "main",
        "position": {"x": 0.5, "y": y, "anchor": "center"},
        "style": {
            "font_family": "PingFang SC",
            "font_size": size,
            "primary_color": "#FFFFFF",
            "outline_color": "#111827",
            "outline_width": 3,
            "shadow_color": "#000000",
            "shadow_depth": 2,
        },
        "spans": [
            {
                "selector": {"type": "keyword", "value": ""},
                "style": {"primary_color": "#FFD54F", "font_scale": 1.15},
            }
        ],
        "animations": {"in": {"type": "fade", "duration_ms": 120}},
    }


PRESETS: list[dict[str, Any]] = [
    {
        "id": "preset-clean-bottom",
        "name": "清晰底部字幕",
        "schema_version": SCHEMA_VERSION,
        "renderer_mode": RENDERER_MODE,
        "tracks": [copy.deepcopy(DEFAULT_TRACK)],
        "blocks": [
            _block("bottom", 0.82, 54),
            _block("highlight", 0.72, 60),
            _block("punch", 0.62, 68),
        ],
    }
]


def list_presets() -> list[dict[str, Any]]:
    return [copy.deepcopy(item) for item in PRESETS]
