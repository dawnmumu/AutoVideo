from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from pydantic import BaseModel, Field

from autovideo.api.dependencies import get_store
from autovideo.api.errors import structured_error
from autovideo.services.material_sources import (
    MaterialSourceInvalidPathError,
    MaterialSourceNotDirectoryError,
    MaterialSourceNotFoundError,
    MaterialSourcePathOutOfScopeError,
    MaterialSourceRootNotConfiguredError,
    MaterialSourceRootNotFoundError,
    MaterialSourceService,
)
from autovideo.services.material_worker import (
    MaterialIndexAlreadyRunningError,
    MaterialIndexRunner,
    MaterialWorkerService,
)
from autovideo.storage.database import AutoVideoStore

router = APIRouter(prefix="/api/material-sources", tags=["material-sources"])


class SaveMaterialSourceRequest(BaseModel):
    allowed_root_id: str = Field(min_length=1, max_length=40)
    source_relative_path: str = Field(min_length=1, max_length=500)


def _public_source_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    if config is None:
        return None
    return {
        "id": config["id"],
        "allowed_root_id": config["allowed_root_id"],
        "allowed_root_alias": config["allowed_root_alias"],
        "source_relative_path": config["source_relative_path"],
        "source_display_path": config["source_display_path"],
        "status": config["status"],
        "error_summary": config.get("error_summary"),
        "created_at": config["created_at"],
        "updated_at": config["updated_at"],
    }


def _public_job(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if job is None:
        return None
    return {
        "id": job["id"],
        "source_config_id": job["source_config_id"],
        "allowed_root_id": job["allowed_root_id"],
        "source_relative_path": job["source_relative_path"],
        "status": job["status"],
        "stage": job["stage"],
        "progress_current": job["progress_current"],
        "progress_total": job["progress_total"],
        "progress": {
            "current": job["progress_current"],
            "total": job["progress_total"],
        },
        "raw_files_total": job["raw_files_total"],
        "segments_total": job["segments_total"],
        "failed_total": job["failed_total"],
        "counts": {
            "raw": job["raw_files_total"],
            "segments": job["segments_total"],
            "failed": job["failed_total"],
        },
        "heartbeat_at": job.get("heartbeat_at"),
        "attempt_count": job["attempt_count"],
        "error_summary": job.get("error_summary"),
        "created_at": job["created_at"],
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
    }


def _status_payload(store: AutoVideoStore) -> dict[str, Any]:
    service = MaterialSourceService(store)
    status_payload = service.status()
    if not status_payload["configured"]:
        raise structured_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "MATERIAL_SOURCE_ROOT_NOT_CONFIGURED",
        )
    current_source = status_payload["current_source"]
    latest_job = (
        MaterialWorkerService(store).latest_job_for_identity(
            str(current_source["allowed_root_id"]),
            str(current_source["source_path_hash"]),
        )
        if current_source is not None
        else None
    )
    return {
        "allowed_roots": status_payload["allowed_roots"],
        "current_source": _public_source_config(current_source),
        "latest_job": _public_job(latest_job),
    }


def _save_source_config(
    store: AutoVideoStore,
    payload: SaveMaterialSourceRequest,
) -> dict[str, Any]:
    service = MaterialSourceService(store)
    try:
        resolved = service.resolve_source(
            payload.allowed_root_id,
            payload.source_relative_path,
        )
    except MaterialSourceRootNotConfiguredError as exc:
        raise structured_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "MATERIAL_SOURCE_ROOT_NOT_CONFIGURED",
        ) from exc
    except (MaterialSourceInvalidPathError, MaterialSourcePathOutOfScopeError) as exc:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "MATERIAL_SOURCE_PATH_OUT_OF_SCOPE",
        ) from exc
    except (
        MaterialSourceRootNotFoundError,
        MaterialSourceNotFoundError,
        MaterialSourceNotDirectoryError,
    ) as exc:
        raise structured_error(
            status.HTTP_404_NOT_FOUND,
            "MATERIAL_SOURCE_NOT_FOUND",
        ) from exc

    current_source = store.current_material_source_config()
    if (
        current_source is not None
        and str(current_source["allowed_root_id"]) == resolved.allowed_root.id
        and str(current_source["source_relative_path"]) == resolved.source_relative_path
    ):
        return current_source

    return service.save_current_source(
        payload.allowed_root_id,
        payload.source_relative_path,
    )


def _enqueue_material_index(
    request: Request,
    background_tasks: BackgroundTasks,
    store: AutoVideoStore,
    job_id: str,
) -> None:
    runner = MaterialIndexRunner(
        store,
        processing_service=getattr(
            request.app.state,
            "material_processing_service",
            None,
        ),
    )
    background_tasks.add_task(runner.run, job_id)


@router.get("")
def get_material_sources(
    store: AutoVideoStore = Depends(get_store),
) -> dict[str, Any]:
    return _status_payload(store)


@router.put("/current")
def save_material_source(
    payload: SaveMaterialSourceRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    store: AutoVideoStore = Depends(get_store),
) -> dict[str, Any]:
    current_source = _save_source_config(store, payload)
    worker = MaterialWorkerService(store)
    worker.recover_stale_jobs()
    active_job = store.active_material_index_job(
        str(current_source["allowed_root_id"]),
        str(current_source["source_path_hash"]),
    )
    if active_job is not None:
        return {
            "current_source": _public_source_config(current_source),
            "job": _public_job(active_job),
        }
    latest_job = worker.latest_job_for_identity(
        str(current_source["allowed_root_id"]),
        str(current_source["source_path_hash"]),
    )
    if latest_job is not None and latest_job.get("status") != "stale":
        return {
            "current_source": _public_source_config(current_source),
            "job": _public_job(latest_job),
        }
    try:
        job = worker.create_index_job(str(current_source["id"]))
    except MaterialIndexAlreadyRunningError as exc:
        raise structured_error(
            status.HTTP_409_CONFLICT,
            "MATERIAL_INDEX_ALREADY_RUNNING",
        ) from exc
    _enqueue_material_index(request, background_tasks, store, str(job["id"]))

    return {
        "current_source": _public_source_config(current_source),
        "job": _public_job(job),
    }
