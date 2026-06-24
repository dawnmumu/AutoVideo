from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from autovideo.storage.database import AutoVideoStore

TERMINAL_JOB_STATUSES = {"succeeded", "failed", "stale", "canceled"}
ACTIVE_JOB_STATUSES = {"queued", "running"}


class MaterialIndexAlreadyRunningError(Exception):
    pass


class MaterialIndexJobNotFoundError(Exception):
    pass


class MaterialIndexJobNotRunnableError(Exception):
    pass


class MaterialWorkerService:
    def __init__(self, store: AutoVideoStore) -> None:
        self.store = store

    def create_index_job(
        self,
        source_config_id: str,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        source_config = self.store.get_material_source_config(source_config_id)
        if source_config is None:
            raise MaterialIndexJobNotFoundError()
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
            raise MaterialIndexJobNotRunnableError()
        return claimed

    def mark_stale_jobs(self, stale_after_seconds: int = 900) -> int:
        now = datetime.now(UTC)
        stale_before = (now - timedelta(seconds=stale_after_seconds)).isoformat()
        return self.store.mark_stale_material_index_jobs(stale_before, now.isoformat())

    def latest_job(self, source_config_id: str | None = None) -> dict[str, Any] | None:
        return self.store.latest_material_index_job(source_config_id)
