from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from autovideo.services.material_processing import (
    MaterialFfmpegUnavailableError,
    MaterialProcessingService,
)
from autovideo.services.material_sources import (
    MaterialSourceInvalidPathError,
    MaterialSourceNotDirectoryError,
    MaterialSourceNotFoundError,
    MaterialSourcePathOutOfScopeError,
    MaterialSourceRootNotConfiguredError,
    MaterialSourceRootNotFoundError,
)
from autovideo.storage.database import AutoVideoStore

TERMINAL_JOB_STATUSES = {"succeeded", "failed", "stale", "canceled"}
ACTIVE_JOB_STATUSES = {"queued", "running"}
MATERIAL_INDEX_JOB_STALE_AFTER_SECONDS = 900
MATERIAL_SOURCE_ERRORS = (
    MaterialSourceInvalidPathError,
    MaterialSourceNotDirectoryError,
    MaterialSourceNotFoundError,
    MaterialSourcePathOutOfScopeError,
    MaterialSourceRootNotConfiguredError,
    MaterialSourceRootNotFoundError,
)


class MaterialIndexAlreadyRunningError(Exception):
    pass


class MaterialIndexJobNotFoundError(Exception):
    pass


class MaterialIndexJobNotRunnableError(Exception):
    pass


class MaterialWorkerService:
    def __init__(
        self,
        store: AutoVideoStore,
        processing_service: Any | None = None,
    ) -> None:
        self.store = store
        self.processing_service = processing_service

    def create_index_job(
        self,
        source_config_id: str,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        source_config = self.store.get_material_source_config(source_config_id)
        if source_config is None:
            raise MaterialIndexJobNotFoundError()
        self.recover_stale_jobs()
        active = self.store.active_material_index_job(
            source_config["allowed_root_id"],
            source_config["source_path_hash"],
        )
        if active is not None:
            raise MaterialIndexAlreadyRunningError()
        now = datetime.now(UTC).isoformat()
        return self.store.insert_material_index_job(
            {
                "id": uuid.uuid4().hex,
                "source_config_id": source_config_id,
                "allowed_root_id": source_config["allowed_root_id"],
                "source_relative_path": source_config["source_relative_path"],
                "source_path_hash": source_config["source_path_hash"],
                "status": "queued",
                "stage": "scanning",
                "progress_current": 0,
                "progress_total": 0,
                "raw_files_total": 0,
                "segments_total": 0,
                "failed_total": 0,
                "heartbeat_at": None,
                "attempt_count": 0,
                "error_summary": None,
                "created_at": now,
                "started_at": None,
                "finished_at": None,
            }
        )

    def claim_next_job(self) -> dict[str, Any] | None:
        now = datetime.now(UTC).isoformat()
        return self.store.claim_next_material_index_job(now)

    def claim_job(self, job_id: str) -> dict[str, Any] | None:
        now = datetime.now(UTC).isoformat()
        return self.store.claim_material_index_job(job_id, now)

    def run_job(self, job_id: str) -> dict[str, Any]:
        claimed = self.claim_job(job_id)
        if claimed is None:
            existing = self.store.get_material_index_job(job_id)
            if existing is None:
                raise MaterialIndexJobNotFoundError()
            raise MaterialIndexJobNotRunnableError()
        now = datetime.now(UTC).isoformat()
        claimed = self.store.update_material_index_job(
            claimed["id"],
            {"stage": "segmenting", "heartbeat_at": now},
        )
        source_config = self.store.get_material_source_config(claimed["source_config_id"])
        if source_config is None:
            return self._fail_claimed_job(
                claimed["id"],
                error_summary="MATERIAL_SOURCE_NOT_FOUND",
            )
        processing_service = self.processing_service or MaterialProcessingService(
            self.store
        )
        try:
            counts = processing_service.process_source(source_config)
        except MaterialFfmpegUnavailableError:
            return self._fail_claimed_job(
                claimed["id"],
                error_summary="MATERIAL_FFMPEG_UNAVAILABLE",
            )
        except MATERIAL_SOURCE_ERRORS:
            return self._fail_claimed_job(
                claimed["id"],
                error_summary="MATERIAL_SOURCE_NOT_FOUND",
            )
        except Exception:
            return self._fail_claimed_job(
                claimed["id"],
                error_summary="MATERIAL_INDEX_JOB_FAILED",
            )

        finished_at = datetime.now(UTC).isoformat()
        raw_files_total = int(counts.get("raw_files_total", 0))
        segments_total = int(counts.get("segments_total", 0))
        failed_total = int(counts.get("failed_total", 0))
        total = raw_files_total
        status = "succeeded" if segments_total > 0 else "failed"
        error_summary = None if status == "succeeded" else "MATERIAL_INDEX_JOB_FAILED"
        stage = "ready" if status == "succeeded" else "segmenting"
        return self.store.update_material_index_job(
            claimed["id"],
            {
                "status": status,
                "stage": stage,
                "progress_current": total,
                "progress_total": total,
                "raw_files_total": raw_files_total,
                "segments_total": segments_total,
                "failed_total": failed_total,
                "error_summary": error_summary,
                "heartbeat_at": finished_at,
                "finished_at": finished_at,
            },
        )

    def _fail_claimed_job(self, job_id: str, *, error_summary: str) -> dict[str, Any]:
        finished_at = datetime.now(UTC).isoformat()
        return self.store.update_material_index_job(
            job_id,
            {
                "status": "failed",
                "stage": "segmenting",
                "error_summary": error_summary,
                "heartbeat_at": finished_at,
                "finished_at": finished_at,
            },
        )

    def mark_stale_jobs(self, stale_after_seconds: int = 900) -> int:
        now = datetime.now(UTC)
        stale_before = (now - timedelta(seconds=stale_after_seconds)).isoformat()
        return self.store.mark_stale_material_index_jobs(stale_before, now.isoformat())

    def recover_stale_jobs(self) -> int:
        return self.mark_stale_jobs(
            stale_after_seconds=MATERIAL_INDEX_JOB_STALE_AFTER_SECONDS,
        )

    def latest_job(self, source_config_id: str | None = None) -> dict[str, Any] | None:
        return self.store.latest_material_index_job(source_config_id)

    def latest_job_for_identity(
        self,
        allowed_root_id: str,
        source_path_hash: str,
    ) -> dict[str, Any] | None:
        return self.store.latest_material_index_job_for_source_identity(
            allowed_root_id,
            source_path_hash,
        )


class MaterialIndexRunner:
    def __init__(
        self,
        store: AutoVideoStore,
        processing_service: Any | None = None,
    ) -> None:
        self.store = store
        self.processing_service = processing_service

    def run(self, job_id: str) -> dict[str, Any]:
        service = MaterialWorkerService(
            self.store,
            processing_service=self.processing_service,
        )
        return service.run_job(job_id)
