from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from autovideo.storage.database import AutoVideoStore

PLACEHOLDER_OUTPUT_NOTE = "这是任务骨架生成的占位输出，尚未执行真实混剪渲染。"


class MaterialNotFoundError(Exception):
    def __init__(self, material_id: str) -> None:
        self.material_id = material_id
        super().__init__(material_id)


class TaskMaterialLimitExceededError(Exception):
    def __init__(self, material_count: int, max_task_materials: int) -> None:
        self.material_count = material_count
        self.max_task_materials = max_task_materials
        super().__init__(str(material_count))


class TaskOptionsTooLargeError(Exception):
    def __init__(self, options_bytes: int, max_task_options_bytes: int) -> None:
        self.options_bytes = options_bytes
        self.max_task_options_bytes = max_task_options_bytes
        super().__init__(str(options_bytes))


class TaskNotFoundError(Exception):
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        super().__init__(task_id)


class OutputNotFoundError(Exception):
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        super().__init__(task_id)


def encoded_json_size(value: Any) -> int:
    return len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def create_task(
    store: AutoVideoStore,
    *,
    title: str,
    material_ids: list[str],
    options: dict[str, Any],
) -> dict[str, Any]:
    material_count = len(material_ids)
    if material_count > store.settings.max_task_materials:
        raise TaskMaterialLimitExceededError(
            material_count,
            store.settings.max_task_materials,
        )

    options_bytes = encoded_json_size(options)
    if options_bytes > store.settings.max_task_options_bytes:
        raise TaskOptionsTooLargeError(
            options_bytes,
            store.settings.max_task_options_bytes,
        )

    materials = []
    for material_id in material_ids:
        material = store.get_material(material_id)
        if material is None:
            raise MaterialNotFoundError(material_id)
        materials.append(material)

    task_id = uuid.uuid4().hex
    now = datetime.now(UTC).isoformat()
    output_dir = store.paths.outputs / task_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "manifest.json"
    output_payload = {
        "task_id": task_id,
        "title": title,
        "materials": [
            {
                "id": material["id"],
                "original_filename": material["original_filename"],
                "size_bytes": material["size_bytes"],
                "content_type": material["content_type"],
            }
            for material in materials
        ],
        "options": options,
        "note": PLACEHOLDER_OUTPUT_NOTE,
    }
    output_path.write_text(
        json.dumps(output_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return store.insert_task(
        {
            "id": task_id,
            "title": title,
            "status": "succeeded",
            "material_ids": material_ids,
            "options": options,
            "output": {
                "path": str(output_path),
                "download_url": f"/api/tasks/{task_id}/output",
            },
            "created_at": now,
            "updated_at": now,
        }
    )


def require_task(store: AutoVideoStore, task_id: str) -> dict[str, Any]:
    task = store.get_task(task_id)
    if task is None:
        raise TaskNotFoundError(task_id)
    return task


def require_output_path(store: AutoVideoStore, task_id: str):
    require_task(store, task_id)
    path = store.output_path_for(task_id)
    if path is None or not path.is_file():
        raise OutputNotFoundError(task_id)
    return path
