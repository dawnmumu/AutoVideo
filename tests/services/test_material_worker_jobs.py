import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from autovideo.core.settings import Settings
from autovideo.services.material_sources import MaterialSourceService
from autovideo.services.material_worker import (
    MaterialIndexAlreadyRunningError,
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

