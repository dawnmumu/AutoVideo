from __future__ import annotations

from pathlib import Path

FILTERGRAPH_PATH_ESCAPES = {
    "\\": "\\\\",
    ":": "\\:",
    "'": "\\'",
    ",": "\\,",
    ";": "\\;",
    "[": "\\[",
    "]": "\\]",
}


def ass_filter(path: str | Path) -> str:
    return f"ass=filename={escape_filter_path(path)}"


def escape_filter_path(path: str | Path) -> str:
    value = str(path)
    return "".join(FILTERGRAPH_PATH_ESCAPES.get(char, char) for char in value)
