from __future__ import annotations

from pathlib import Path
from typing import Any

CAPTIONED_LOCAL_MATERIAL_MARKERS = (
    "口播",
    "字幕",
    "带字",
    "caption",
    "captions",
    "subtitle",
    "subtitled",
    "hard-sub",
    "hardsub",
)
SOURCE_SUBTITLE_MASK_HEIGHT_RATIO = 0.22
MASKED_MATERIAL_SOURCES = {"local", "hybrid"}


def material_path_appears_captioned(file_path: str | Path) -> bool:
    path = Path(file_path)
    candidates = (path.parent.name, path.stem)
    return any(
        marker.casefold() in candidate.casefold()
        for candidate in candidates
        for marker in CAPTIONED_LOCAL_MATERIAL_MARKERS
    )


def build_source_subtitle_masks(
    material_source: str,
    material_paths: list[str] | tuple[str, ...],
    *,
    subtitle_enabled: bool,
    material_plans: list[Any] | tuple[Any, ...] | None = None,
) -> list[bool]:
    paths = list(material_paths)
    plans = list(material_plans or [])
    slot_count = max(len(paths), len(plans))
    if not subtitle_enabled or material_source not in MASKED_MATERIAL_SOURCES:
        return [False] * slot_count

    masks: list[bool] = []
    for index in range(slot_count):
        fallback_path = paths[index] if index < len(paths) else ""
        planned_path = _path_from_plan(plans[index]) if index < len(plans) else None
        masks.append(material_path_appears_captioned(planned_path or fallback_path))
    return masks


def drawbox_filter(width: int, height: int) -> str:
    mask_height = max(1, int(height * SOURCE_SUBTITLE_MASK_HEIGHT_RATIO))
    y = max(0, height - mask_height)
    return f"drawbox=x=0:y={y}:w={int(width)}:h={mask_height}:color=black@1:t=fill"


def _path_from_plan(plan: Any) -> str | None:
    if isinstance(plan, str):
        return plan
    if isinstance(plan, Path):
        return str(plan)
    if isinstance(plan, dict):
        for key in (
            "storage_path",
            "material_path",
            "file_path",
            "local_path",
            "path",
        ):
            value = plan.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, Path):
                return str(value)

        material = plan.get("material")
        if isinstance(material, dict):
            material_path = _path_from_plan(material)
            if material_path:
                return material_path

        for key in ("paths", "material_paths", "candidates"):
            value = plan.get(key)
            if isinstance(value, list | tuple):
                for item in value:
                    item_path = _path_from_plan(item)
                    if item_path:
                        return item_path
    if isinstance(plan, list | tuple):
        for item in plan:
            item_path = _path_from_plan(item)
            if item_path:
                return item_path
    return None
