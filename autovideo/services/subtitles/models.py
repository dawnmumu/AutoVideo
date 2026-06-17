from __future__ import annotations

from typing import Any

TEMPLATE_ROLES = ("bottom", "highlight", "punch")
SCHEMA_VERSION = 2
RENDERER_MODE = "ass_plus"
MAIN_TRACK_ID = "main"
DEFAULT_TRACK = {"id": MAIN_TRACK_ID, "kind": "subtitle", "z": 10}


def deep_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
