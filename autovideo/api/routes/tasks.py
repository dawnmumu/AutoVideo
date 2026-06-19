import json
from pathlib import Path
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
    TaskOutputCleanupError,
    TaskOutputPathInvalidError,
    create_task,
    delete_task,
    require_output_path,
    require_task,
    sanitize_manifest_payload,
)
from autovideo.storage.database import AutoVideoStore

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class CreateTaskRequest(BaseModel):
    title: str = Field(default="未命名混剪任务", min_length=1, max_length=120)
    material_ids: list[str] = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)


SUCCESS_RENDER_STATUSES = frozenset({"video_rendered", "subtitle_burned"})


def _read_manifest_for_output(output_path: Path) -> dict[str, Any]:
    manifest_path = output_path.parent / "manifest.json"
    if not manifest_path.is_file():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    sanitized = sanitize_manifest_payload(str(value).strip())
    if not isinstance(sanitized, str):
        return None
    return sanitized or None


def _render_plan(manifest: dict[str, Any]) -> dict[str, Any]:
    plan = manifest.get("render_plan")
    return plan if isinstance(plan, dict) else {}


def _output_kind(
    *,
    filename: str,
    media_type: str,
    render_status: str | None,
) -> str:
    if filename == "output.mp4" and media_type == "video/mp4":
        return "video"
    if filename == "manifest.json":
        return "manifest"
    if filename == "output.base.mp4" and render_status == "subtitle_burn_failed":
        return "partial_video"
    if media_type == "video/mp4":
        return "partial_video"
    return "file"


def _failure_reason(
    *,
    kind: str,
    render_status: str | None,
    render_plan: dict[str, Any],
) -> str | None:
    error_summary = _safe_text(render_plan.get("error_summary"))
    if error_summary:
        return error_summary
    if render_status == "subtitle_burn_failed":
        return "字幕烧录失败，已保留未烧录字幕的视频。"
    if render_status == "base_video_failed":
        return "基础视频渲染失败，仅保留任务清单。"
    if render_status == "manifest_only" and render_plan.get("renderer") == "ffmpeg_unavailable":
        return "FFmpeg 不可用，仅保留任务清单。"
    if kind == "manifest":
        return "当前任务仅生成输出清单。"
    if render_status and render_status not in SUCCESS_RENDER_STATUSES:
        return f"渲染状态：{render_status}"
    return None


def _public_output(task: dict[str, Any], store: AutoVideoStore) -> dict[str, Any]:
    output = {"download_url": task["output"]["download_url"]}
    output_path = store.output_path_for(task["id"])
    if output_path is None or not output_path.is_file():
        return output

    media_type = media_type_for_output(output_path)
    manifest = _read_manifest_for_output(output_path)
    render_plan = _render_plan(manifest)
    render_status = _safe_text(render_plan.get("status"))
    filename = output_path.name
    kind = _output_kind(
        filename=filename,
        media_type=media_type,
        render_status=render_status,
    )

    output.update(
        {
            "filename": filename,
            "media_type": media_type,
            "kind": kind,
        }
    )
    if render_status:
        output["render_status"] = render_status
    reason = _failure_reason(
        kind=kind,
        render_status=render_status,
        render_plan=render_plan,
    )
    if reason:
        output["failure_reason"] = reason
    return output


def public_task(task: dict[str, Any], store: AutoVideoStore) -> dict[str, Any]:
    return {
        "id": task["id"],
        "title": task["title"],
        "status": task["status"],
        "material_ids": task["material_ids"],
        "options": task["options"],
        "output": _public_output(task, store),
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
            ),
            store,
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
    return [
        public_task(task, store)
        for task in store.list_tasks(limit=limit, offset=offset)
    ]


@router.get("/{task_id}")
def get_video_task(
    task_id: str,
    store: AutoVideoStore = Depends(get_store),
) -> dict[str, Any]:
    try:
        return public_task(require_task(store, task_id), store)
    except TaskNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TASK_NOT_FOUND", "task_id": exc.task_id},
        ) from exc


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video_task(
    task_id: str,
    store: AutoVideoStore = Depends(get_store),
) -> None:
    try:
        delete_task(store, task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "TASK_NOT_FOUND", "task_id": exc.task_id},
        ) from exc
    except TaskOutputCleanupError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "TASK_OUTPUT_CLEANUP_FAILED", "task_id": exc.task_id},
        ) from exc
    except TaskOutputPathInvalidError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "TASK_OUTPUT_PATH_INVALID", "task_id": exc.task_id},
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
