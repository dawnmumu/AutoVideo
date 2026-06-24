from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status
from pydantic import BaseModel

from autovideo.api.dependencies import get_store
from autovideo.api.errors import structured_error
from autovideo.services.material_processing import MaterialProcessingService
from autovideo.services.material_worker import (
    MaterialIndexAlreadyRunningError,
    MaterialIndexJobNotFoundError,
    MaterialIndexRunner,
    MaterialWorkerService,
)
from autovideo.storage.database import AutoVideoStore

router = APIRouter(prefix="/api/material-index", tags=["material-index"])


class StartMaterialIndexRequest(BaseModel):
    source_config_id: str | None = None
    force: bool = False


class ClearMaterialLibraryRequest(BaseModel):
    confirm: str | None = None


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


def _public_raw_file(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": raw["id"],
        "source_config_id": raw.get("source_config_id"),
        "allowed_root_id": raw["allowed_root_id"],
        "source_relative_path": raw["source_relative_path"],
        "source_display_path": raw["source_display_path"],
        "filename": raw["original_filename"],
        "size_bytes": raw["size_bytes"],
        "duration_seconds": raw.get("duration_seconds"),
        "orientation": raw.get("orientation"),
        "segments": raw.get("segments", 0),
        "status": raw["status"],
        "error_summary": raw.get("error_summary"),
        "asr_status": raw.get("asr_status"),
        "ocr_status": raw.get("ocr_status"),
        "vision_status": raw.get("vision_status"),
        "embedding_status": raw.get("embedding_status"),
        "created_at": raw["created_at"],
        "updated_at": raw["updated_at"],
    }


def _public_segment(segment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": segment["id"],
        "raw_file_id": segment["raw_file_id"],
        "start_seconds": segment["start_seconds"],
        "duration_seconds": segment["duration_seconds"],
        "orientation": segment.get("orientation"),
        "status": segment["status"],
        "match_text": segment.get("match_text"),
        "asr_text": segment.get("asr_text"),
        "ocr_text": segment.get("ocr_text"),
        "vision_description": segment.get("vision_description"),
        "content_label_status": segment.get("content_label_status"),
        "embedding_status": segment.get("embedding_status"),
        "error_summary": segment.get("error_summary"),
        "created_at": segment["created_at"],
        "updated_at": segment["updated_at"],
    }


def _segment_total(store: AutoVideoStore, raw_file_id: str) -> int:
    with store.connect() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*)
            FROM material_segments
            WHERE raw_file_id = ?
              AND deleted_at IS NULL
            """,
            (raw_file_id,),
        ).fetchone()
    return int(row[0]) if row else 0


def _current_source_or_error(store: AutoVideoStore) -> dict[str, Any]:
    source = store.current_material_source_config()
    if source is None:
        raise structured_error(
            status.HTTP_404_NOT_FOUND,
            "MATERIAL_SOURCE_NOT_FOUND",
        )
    return source


def _raw_file_or_404(store: AutoVideoStore, raw_file_id: str) -> dict[str, Any]:
    raw_file = store.get_material_raw_file(raw_file_id)
    if raw_file is None or raw_file.get("deleted_at") is not None:
        raise structured_error(
            status.HTTP_404_NOT_FOUND,
            "MATERIAL_RAW_FILE_NOT_FOUND",
        )
    return raw_file


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


@router.post("/jobs")
def create_material_index_job(
    payload: StartMaterialIndexRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    store: AutoVideoStore = Depends(get_store),
) -> dict[str, Any]:
    source = (
        store.get_material_source_config(payload.source_config_id)
        if payload.source_config_id
        else _current_source_or_error(store)
    )
    if source is None:
        raise structured_error(
            status.HTTP_404_NOT_FOUND,
            "MATERIAL_SOURCE_NOT_FOUND",
        )
    try:
        job = MaterialWorkerService(store).create_index_job(str(source["id"]), force=payload.force)
    except MaterialIndexAlreadyRunningError as exc:
        raise structured_error(
            status.HTTP_409_CONFLICT,
            "MATERIAL_INDEX_ALREADY_RUNNING",
        ) from exc
    except MaterialIndexJobNotFoundError as exc:
        raise structured_error(
            status.HTTP_404_NOT_FOUND,
            "MATERIAL_INDEX_JOB_NOT_FOUND",
        ) from exc
    _enqueue_material_index(request, background_tasks, store, str(job["id"]))
    return {
        "job_id": job["id"],
        "status": job["status"],
    }


@router.get("/jobs/{job_id}")
def get_material_index_job(
    job_id: str,
    store: AutoVideoStore = Depends(get_store),
) -> dict[str, Any]:
    job = store.get_material_index_job(job_id)
    if job is None:
        raise structured_error(
            status.HTTP_404_NOT_FOUND,
            "MATERIAL_INDEX_JOB_NOT_FOUND",
        )
    return _public_job(job)


@router.get("/summary")
def get_material_index_summary(
    store: AutoVideoStore = Depends(get_store),
) -> dict[str, Any]:
    current_source = store.current_material_source_config()
    return {
        "totals": store.material_library_summary(),
        "current_source": _public_source_config(current_source),
        "latest_job": _public_job(
            MaterialWorkerService(store).latest_job_for_identity(
                str(current_source["allowed_root_id"]),
                str(current_source["source_path_hash"]),
            )
            if current_source is not None
            else None
        ),
    }


@router.get("/raw-files")
def list_material_raw_files(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    store: AutoVideoStore = Depends(get_store),
) -> dict[str, Any]:
    items = store.list_material_raw_files(
        limit=limit,
        offset=offset,
        status=status_filter,
    )
    total = store.count_material_raw_files(status=status_filter)
    return {
        "items": [_public_raw_file(item) for item in items],
        "limit": limit,
        "offset": offset,
        "total": total,
    }


@router.get("/raw-files/{raw_file_id}/segments")
def list_material_segments(
    raw_file_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    store: AutoVideoStore = Depends(get_store),
) -> dict[str, Any]:
    _raw_file_or_404(store, raw_file_id)
    items = store.list_material_segments(raw_file_id, limit=limit, offset=offset)
    return {
        "items": [_public_segment(item) for item in items],
        "limit": limit,
        "offset": offset,
        "total": _segment_total(store, raw_file_id),
    }


@router.delete("/raw-files/{raw_file_id}")
def delete_material_raw_file(
    raw_file_id: str,
    store: AutoVideoStore = Depends(get_store),
) -> dict[str, Any]:
    _raw_file_or_404(store, raw_file_id)
    deleted = MaterialProcessingService(store).delete_raw_file(raw_file_id)
    if not deleted.get("deleted"):
        raise structured_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            str(deleted.get("error_code") or "MATERIAL_LIBRARY_CLEAR_FAILED"),
        )
    return deleted


@router.post("/library/clear")
def clear_material_library(
    payload: ClearMaterialLibraryRequest,
    store: AutoVideoStore = Depends(get_store),
) -> dict[str, Any]:
    if payload.confirm != "CLEAR_MATERIAL_LIBRARY":
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "MATERIAL_LIBRARY_CLEAR_CONFIRMATION_REQUIRED",
        )
    cleared = MaterialProcessingService(store).clear_library(payload.confirm)
    if "error_code" in cleared:
        raise structured_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            str(cleared["error_code"]),
        )
    return cleared
