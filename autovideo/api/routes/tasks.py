from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from autovideo.api.dependencies import get_store
from autovideo.services.rendering import media_type_for_output
from autovideo.services.tasks import (
    MaterialNotFoundError,
    OutputNotFoundError,
    TaskNotFoundError,
    TaskMaterialLimitExceededError,
    TaskOptionsTooLargeError,
    create_task,
    require_output_path,
    require_task,
)
from autovideo.storage.database import AutoVideoStore

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    title: str = Field(default="未命名混剪任务", min_length=1, max_length=120)
    material_ids: list[str] = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)


def public_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task["id"],
        "title": task["title"],
        "status": task["status"],
        "material_ids": task["material_ids"],
        "options": task["options"],
        "output": {"download_url": task["output"]["download_url"]},
        "created_at": task["created_at"],
        "updated_at": task["updated_at"],
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_video_task(
    request: CreateTaskRequest,
    store: AutoVideoStore = Depends(get_store),
) -> dict[str, Any]:
    try:
        return public_task(
            create_task(
                store,
                title=request.title,
                material_ids=request.material_ids,
                options=request.options,
            )
        )
    except MaterialNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MATERIAL_NOT_FOUND", "material_id": exc.material_id},
        ) from exc
    except TaskMaterialLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={
                "code": "TASK_MATERIAL_LIMIT_EXCEEDED",
                "max_task_materials": exc.max_task_materials,
                "material_count": exc.material_count,
            },
        ) from exc
    except TaskOptionsTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={
                "code": "TASK_OPTIONS_TOO_LARGE",
                "max_task_options_bytes": exc.max_task_options_bytes,
                "options_bytes": exc.options_bytes,
            },
        ) from exc


@router.get("")
def list_video_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    store: AutoVideoStore = Depends(get_store),
) -> list[dict[str, Any]]:
    return [public_task(task) for task in store.list_tasks(limit=limit, offset=offset)]


@router.get("/{task_id}")
def get_video_task(
    task_id: str,
    store: AutoVideoStore = Depends(get_store),
) -> dict[str, Any]:
    try:
        return public_task(require_task(store, task_id))
    except TaskNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TASK_NOT_FOUND", "task_id": exc.task_id},
        ) from exc


@router.get("/{task_id}/output")
def download_task_output(
    task_id: str,
    store: AutoVideoStore = Depends(get_store),
) -> FileResponse:
    try:
        output_path = require_output_path(store, task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TASK_NOT_FOUND", "task_id": exc.task_id},
        ) from exc
    except OutputNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "OUTPUT_NOT_FOUND", "task_id": exc.task_id},
        ) from exc
    return FileResponse(output_path, media_type=media_type_for_output(output_path))
