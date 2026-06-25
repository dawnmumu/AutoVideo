import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from autovideo.core.settings import Settings
from autovideo.services.material_processing import MaterialFfmpegUnavailableError
from autovideo.services.material_sources import (
    MaterialSourceNotFoundError,
    MaterialSourceService,
)
from autovideo.services.material_worker import (
    MaterialIndexAlreadyRunningError,
    MaterialIndexJobNotFoundError,
    MaterialIndexJobNotRunnableError,
    MaterialWorkerService,
)
from autovideo.storage.database import AutoVideoStore


def _store_and_source(tmp_path: Path) -> tuple[AutoVideoStore, dict[str, str]]:
    root = tmp_path / "source"
    (root / "clips").mkdir(parents=True)
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        material_allowed_roots=f"demo={root}",
    )
    store = AutoVideoStore(settings)
    source = MaterialSourceService(store).save_current_source("demo", "clips")
    return store, source


def test_create_job_rejects_active_job_for_same_directory(tmp_path: Path) -> None:
    store, source = _store_and_source(tmp_path)
    service = MaterialWorkerService(store)
    first = service.create_index_job(source["id"])

    with pytest.raises(MaterialIndexAlreadyRunningError):
        service.create_index_job(source["id"], force=True)

    assert first["status"] == "queued"


def test_create_job_uses_directory_identity_not_source_config_id(tmp_path: Path) -> None:
    store, source = _store_and_source(tmp_path)
    duplicate = dict(source)
    duplicate["id"] = "duplicate-config"
    store.insert_material_source_config(duplicate)
    service = MaterialWorkerService(store)
    service.create_index_job(source["id"])

    with pytest.raises(MaterialIndexAlreadyRunningError):
        service.create_index_job("duplicate-config")


def test_active_job_unique_index_rejects_direct_duplicate_insert(tmp_path: Path) -> None:
    store, source = _store_and_source(tmp_path)
    service = MaterialWorkerService(store)
    first = service.create_index_job(source["id"])

    with pytest.raises(sqlite3.IntegrityError):
        with store.connect() as connection:
            connection.execute(
                """
                INSERT INTO material_index_jobs (
                    id, source_config_id, allowed_root_id, source_relative_path,
                    source_path_hash, status, stage, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "duplicate-active-job",
                    source["id"],
                    source["allowed_root_id"],
                    source["source_relative_path"],
                    source["source_path_hash"],
                    "queued",
                    "scanning",
                    first["created_at"],
                ),
            )


def test_second_connection_cannot_create_active_job_while_running(tmp_path: Path) -> None:
    root = tmp_path / "source"
    (root / "clips").mkdir(parents=True)
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        material_allowed_roots=f"demo={root}",
    )
    store_one = AutoVideoStore(settings)
    source = MaterialSourceService(store_one).save_current_source("demo", "clips")
    service_one = MaterialWorkerService(store_one)
    created = service_one.create_index_job(source["id"])

    claimed = service_one.claim_next_job()

    assert claimed is not None
    assert claimed["id"] == created["id"]
    assert claimed["status"] == "running"
    store_two = AutoVideoStore(settings)
    service_two = MaterialWorkerService(store_two)
    with pytest.raises(MaterialIndexAlreadyRunningError):
        service_two.create_index_job(source["id"], force=True)
    with pytest.raises(sqlite3.IntegrityError):
        with store_two.connect() as connection:
            connection.execute(
                """
                INSERT INTO material_index_jobs (
                    id, source_config_id, allowed_root_id, source_relative_path,
                    source_path_hash, status, stage, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "second-connection-active-job",
                    source["id"],
                    source["allowed_root_id"],
                    source["source_relative_path"],
                    source["source_path_hash"],
                    "queued",
                    "scanning",
                    created["created_at"],
                ),
            )


def test_claim_next_job_marks_running_and_heartbeat(tmp_path: Path) -> None:
    store, source = _store_and_source(tmp_path)
    service = MaterialWorkerService(store)
    created = service.create_index_job(source["id"])

    claimed = service.claim_next_job()

    assert claimed is not None
    assert claimed["id"] == created["id"]
    assert claimed["status"] == "running"
    assert claimed["attempt_count"] == 1
    assert claimed["started_at"]
    assert claimed["heartbeat_at"]


def test_claim_job_only_transitions_queued_row(tmp_path: Path) -> None:
    store, source = _store_and_source(tmp_path)
    service = MaterialWorkerService(store)
    created = service.create_index_job(source["id"])

    claimed = service.claim_job(created["id"])
    again = service.claim_job(created["id"])

    assert claimed is not None
    assert claimed["id"] == created["id"]
    assert claimed["status"] == "running"
    assert again is None


def test_mark_stale_jobs_closes_old_running_jobs(tmp_path: Path) -> None:
    store, source = _store_and_source(tmp_path)
    service = MaterialWorkerService(store)
    created = service.create_index_job(source["id"])
    claimed = service.claim_next_job()
    assert claimed is not None
    old = datetime.now(UTC) - timedelta(hours=2)
    store.update_material_index_job(
        claimed["id"],
        {"heartbeat_at": old.isoformat()},
    )

    count = service.mark_stale_jobs(stale_after_seconds=60)
    job = store.get_material_index_job(created["id"])

    assert count == 1
    assert job is not None
    assert job["status"] == "stale"
    assert job["finished_at"] is not None
    assert job["error_summary"] == "MATERIAL_INDEX_JOB_STALE"


def test_update_job_rejects_unknown_fields(tmp_path: Path) -> None:
    store, source = _store_and_source(tmp_path)
    service = MaterialWorkerService(store)
    created = service.create_index_job(source["id"])

    with pytest.raises(ValueError):
        store.update_material_index_job(created["id"], {"bad_field": 1})


def test_latest_job_filters_by_source_and_excludes_absolute_paths(tmp_path: Path) -> None:
    store, source = _store_and_source(tmp_path)
    service = MaterialWorkerService(store)
    created = service.create_index_job(source["id"])

    latest = service.latest_job()
    latest_for_source = service.latest_job(source["id"])

    assert latest is not None
    assert latest_for_source is not None
    assert latest["id"] == created["id"]
    assert latest_for_source["id"] == created["id"]
    assert latest["source_relative_path"] == "clips"
    assert "resolved_path" not in latest
    assert str(tmp_path / "source") not in str(latest)


class _FakeProcessingService:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result or {
            "raw_files_total": 0,
            "segments_total": 0,
            "failed_total": 0,
        }
        self.error = error
        self.calls: list[dict[str, str]] = []

    def process_source(
        self,
        source: dict[str, str],
        progress_callback=None,
    ) -> dict[str, int]:
        self.calls.append(source)
        if self.error is not None:
            raise self.error
        return self.result


class _LeaseProbeProcessingService:
    def __init__(
        self,
        store: AutoVideoStore,
        job_id: str,
    ) -> None:
        self.store = store
        self.job_id = job_id
        self.stale_count: int | None = None
        self.duplicate_created = False

    def process_source(
        self,
        source: dict[str, str],
        progress_callback=None,
    ) -> dict[str, int]:
        old = datetime.now(UTC) - timedelta(hours=2)
        self.store.update_material_index_job(
            self.job_id,
            {"heartbeat_at": old.isoformat()},
        )
        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "segmenting",
                    "progress_current": 1,
                    "progress_total": 2,
                }
            )
        self.stale_count = MaterialWorkerService(self.store).recover_stale_jobs()
        try:
            MaterialWorkerService(self.store).create_index_job(source["id"], force=True)
        except MaterialIndexAlreadyRunningError:
            self.duplicate_created = False
        else:
            self.duplicate_created = True
        return {
            "raw_files_total": 1,
            "segments_total": 1,
            "failed_total": 0,
        }


class _ExternallyStalesProcessingService:
    def __init__(
        self,
        store: AutoVideoStore,
        job_id: str,
        *,
        error: Exception | None = None,
    ) -> None:
        self.store = store
        self.job_id = job_id
        self.error = error

    def process_source(
        self,
        source: dict[str, str],
        progress_callback=None,
    ) -> dict[str, int]:
        finished_at = datetime.now(UTC).isoformat()
        self.store.update_material_index_job(
            self.job_id,
            {
                "status": "stale",
                "finished_at": finished_at,
                "error_summary": "MATERIAL_INDEX_JOB_STALE",
            },
        )
        if self.error is not None:
            raise self.error
        return {
            "raw_files_total": 1,
            "segments_total": 1,
            "failed_total": 0,
        }


def test_run_job_claims_specific_job_and_marks_succeeded(tmp_path: Path) -> None:
    store, source = _store_and_source(tmp_path)
    processing = _FakeProcessingService(
        {
            "raw_files_total": 1,
            "segments_total": 2,
            "failed_total": 0,
        }
    )
    service = MaterialWorkerService(store, processing_service=processing)
    created = service.create_index_job(source["id"])

    finished = service.run_job(created["id"])

    assert finished["id"] == created["id"]
    assert finished["status"] == "succeeded"
    assert finished["stage"] == "ready"
    assert finished["attempt_count"] == 1
    assert finished["raw_files_total"] == 1
    assert finished["segments_total"] == 2
    assert finished["failed_total"] == 0
    assert finished["started_at"] is not None
    assert finished["heartbeat_at"] is not None
    assert finished["finished_at"] is not None
    assert processing.calls == [source]


def test_run_job_heartbeat_keeps_long_running_job_active(tmp_path: Path) -> None:
    store, source = _store_and_source(tmp_path)
    created = MaterialWorkerService(store).create_index_job(source["id"])
    processing = _LeaseProbeProcessingService(store, created["id"])
    service = MaterialWorkerService(store, processing_service=processing)

    finished = service.run_job(created["id"])

    latest = store.latest_material_index_job_for_source_identity(
        source["allowed_root_id"],
        source["source_path_hash"],
    )
    assert processing.stale_count == 0
    assert processing.duplicate_created is False
    assert finished["status"] == "succeeded"
    assert latest is not None
    assert latest["id"] == created["id"]


def test_run_job_does_not_overwrite_externally_staled_job_on_success(
    tmp_path: Path,
) -> None:
    store, source = _store_and_source(tmp_path)
    created = MaterialWorkerService(store).create_index_job(source["id"])
    processing = _ExternallyStalesProcessingService(store, created["id"])
    service = MaterialWorkerService(store, processing_service=processing)

    finished = service.run_job(created["id"])
    current = store.get_material_index_job(created["id"])

    assert finished["status"] == "stale"
    assert current is not None
    assert current["status"] == "stale"
    assert current["error_summary"] == "MATERIAL_INDEX_JOB_STALE"


def test_run_job_does_not_overwrite_externally_staled_job_on_failure(
    tmp_path: Path,
) -> None:
    store, source = _store_and_source(tmp_path)
    created = MaterialWorkerService(store).create_index_job(source["id"])
    processing = _ExternallyStalesProcessingService(
        store,
        created["id"],
        error=RuntimeError("boom"),
    )
    service = MaterialWorkerService(store, processing_service=processing)

    finished = service.run_job(created["id"])
    current = store.get_material_index_job(created["id"])

    assert finished["status"] == "stale"
    assert current is not None
    assert current["status"] == "stale"
    assert current["error_summary"] == "MATERIAL_INDEX_JOB_STALE"


def test_run_job_fails_when_no_segments_were_produced(tmp_path: Path) -> None:
    store, source = _store_and_source(tmp_path)
    processing = _FakeProcessingService(
        {
            "raw_files_total": 1,
            "segments_total": 0,
            "failed_total": 1,
        }
    )
    service = MaterialWorkerService(store, processing_service=processing)
    created = service.create_index_job(source["id"])

    finished = service.run_job(created["id"])

    assert finished["status"] == "failed"
    assert finished["stage"] == "segmenting"
    assert finished["raw_files_total"] == 1
    assert finished["segments_total"] == 0
    assert finished["failed_total"] == 1
    assert finished["progress_current"] == 1
    assert finished["progress_total"] == 1
    assert finished["finished_at"] is not None


def test_run_job_marks_ffmpeg_unavailable_failure(tmp_path: Path) -> None:
    store, source = _store_and_source(tmp_path)
    processing = _FakeProcessingService(
        error=MaterialFfmpegUnavailableError("missing ffmpeg")
    )
    service = MaterialWorkerService(store, processing_service=processing)
    created = service.create_index_job(source["id"])

    finished = service.run_job(created["id"])

    assert finished["status"] == "failed"
    assert finished["error_summary"] == "MATERIAL_FFMPEG_UNAVAILABLE"
    assert finished["finished_at"] is not None


def test_run_job_marks_source_error_failed_after_claim(tmp_path: Path) -> None:
    store, source = _store_and_source(tmp_path)
    processing = _FakeProcessingService(error=MaterialSourceNotFoundError())
    service = MaterialWorkerService(store, processing_service=processing)
    created = service.create_index_job(source["id"])

    finished = service.run_job(created["id"])

    assert finished["status"] == "failed"
    assert finished["stage"] == "segmenting"
    assert finished["error_summary"] == "MATERIAL_SOURCE_NOT_FOUND"
    assert finished["heartbeat_at"] is not None
    assert finished["finished_at"] is not None
    assert store.get_material_index_job(created["id"])["status"] == "failed"


def test_run_job_marks_unexpected_processing_error_failed_after_claim(
    tmp_path: Path,
) -> None:
    store, source = _store_and_source(tmp_path)
    processing = _FakeProcessingService(
        error=RuntimeError(f"boom at {tmp_path / 'source' / 'clips'}")
    )
    service = MaterialWorkerService(store, processing_service=processing)
    created = service.create_index_job(source["id"])

    finished = service.run_job(created["id"])

    assert finished["status"] == "failed"
    assert finished["stage"] == "segmenting"
    assert finished["error_summary"] == "MATERIAL_INDEX_JOB_FAILED"
    assert str(tmp_path) not in str(finished)
    assert finished["heartbeat_at"] is not None
    assert finished["finished_at"] is not None
    assert store.get_material_index_job(created["id"])["status"] == "failed"


def test_run_job_requires_claimable_job(tmp_path: Path) -> None:
    store, source = _store_and_source(tmp_path)
    processing = _FakeProcessingService()
    service = MaterialWorkerService(store, processing_service=processing)
    created = service.create_index_job(source["id"])

    claimed = service.claim_job(created["id"])

    assert claimed is not None
    with pytest.raises(MaterialIndexJobNotRunnableError):
        service.run_job(created["id"])
    assert processing.calls == []


def test_run_job_raises_not_found_for_missing_job(tmp_path: Path) -> None:
    store, _source = _store_and_source(tmp_path)
    processing = _FakeProcessingService()
    service = MaterialWorkerService(store, processing_service=processing)

    with pytest.raises(MaterialIndexJobNotFoundError):
        service.run_job("missing-job")

    assert processing.calls == []
