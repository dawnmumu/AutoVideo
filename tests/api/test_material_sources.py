from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings
from autovideo.services.material_sources import MaterialSourceService
from autovideo.storage.database import AutoVideoStore


class _CountingProcessingService:
    def __init__(self) -> None:
        self.calls = 0

    def process_source(self, source: dict[str, object]) -> dict[str, int]:
        self.calls += 1
        return {"raw_files_total": 0, "segments_total": 0, "failed_total": 0}


def test_material_sources_requires_config(client) -> None:
    response = client.get("/api/material-sources")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "MATERIAL_SOURCE_ROOT_NOT_CONFIGURED"


def test_save_source_redacts_absolute_paths_and_queues_job(tmp_path: Path) -> None:
    root = tmp_path / "source"
    (root / "clips").mkdir(parents=True)
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path / "data",
            material_allowed_roots=f"demo={root}",
        )
    )

    with TestClient(app) as client:
        response = client.put(
            "/api/material-sources/current",
            json={"allowed_root_id": "demo", "source_relative_path": "clips"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_source"]["source_display_path"] == "demo/clips"
    assert payload["job"]["status"] == "queued"
    assert payload["job"]["attempt_count"] == 0
    assert str(root) not in str(payload)


def test_save_source_reuses_active_job_for_same_directory(tmp_path: Path) -> None:
    root = tmp_path / "source"
    (root / "clips").mkdir(parents=True)
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        material_allowed_roots=f"demo={root}",
    )
    app = create_app(settings)
    store = AutoVideoStore(settings)
    processing = _CountingProcessingService()
    app.state.material_processing_service = processing
    source = MaterialSourceService(store).save_current_source("demo", "clips")
    active_job = store.insert_material_index_job(
        {
            "id": "queued-job",
            "source_config_id": source["id"],
            "allowed_root_id": source["allowed_root_id"],
            "source_relative_path": source["source_relative_path"],
            "source_path_hash": source["source_path_hash"],
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
            "created_at": "2026-06-24T00:00:00+00:00",
            "started_at": None,
            "finished_at": None,
        }
    )

    with TestClient(app) as client:
        response = client.put(
            "/api/material-sources/current",
            json={"allowed_root_id": "demo", "source_relative_path": "clips"},
        )
        job_response = client.get(f"/api/material-index/jobs/{active_job['id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_source"]["id"] == source["id"]
    assert payload["job"]["id"] == active_job["id"]
    assert payload["job"]["status"] == "queued"
    assert processing.calls == 0
    job_payload = job_response.json()
    assert job_payload["status"] == "queued"
    assert job_payload["attempt_count"] == 0
    assert job_payload["started_at"] is None


def test_save_source_reuses_running_job_for_same_directory_without_rerun(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    (root / "clips").mkdir(parents=True)
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        material_allowed_roots=f"demo={root}",
    )
    app = create_app(settings)
    store = AutoVideoStore(settings)
    processing = _CountingProcessingService()
    app.state.material_processing_service = processing
    source = MaterialSourceService(store).save_current_source("demo", "clips")
    heartbeat_at = datetime.now(UTC).isoformat()
    running_job = store.insert_material_index_job(
        {
            "id": "running-job",
            "source_config_id": source["id"],
            "allowed_root_id": source["allowed_root_id"],
            "source_relative_path": source["source_relative_path"],
            "source_path_hash": source["source_path_hash"],
            "status": "running",
            "stage": "segmenting",
            "progress_current": 1,
            "progress_total": 3,
            "raw_files_total": 1,
            "segments_total": 0,
            "failed_total": 0,
            "heartbeat_at": heartbeat_at,
            "attempt_count": 1,
            "error_summary": None,
            "created_at": "2026-06-24T00:00:00+00:00",
            "started_at": "2026-06-24T00:00:30+00:00",
            "finished_at": None,
        }
    )

    with TestClient(app) as client:
        response = client.put(
            "/api/material-sources/current",
            json={"allowed_root_id": "demo", "source_relative_path": "clips"},
        )
        job_response = client.get(f"/api/material-index/jobs/{running_job['id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_source"]["id"] == source["id"]
    assert payload["job"]["id"] == running_job["id"]
    assert payload["job"]["status"] == "running"
    assert processing.calls == 0
    job_payload = job_response.json()
    assert job_payload["status"] == "running"
    assert job_payload["heartbeat_at"] == heartbeat_at
    assert job_payload["attempt_count"] == 1
    assert job_payload["started_at"] == "2026-06-24T00:00:30+00:00"
    assert job_payload["finished_at"] is None


def test_save_source_recovers_stale_running_job_for_same_directory(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    (root / "clips").mkdir(parents=True)
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        material_allowed_roots=f"demo={root}",
    )
    app = create_app(settings)
    store = AutoVideoStore(settings)
    processing = _CountingProcessingService()
    app.state.material_processing_service = processing
    source = MaterialSourceService(store).save_current_source("demo", "clips")
    stale_heartbeat = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    running_job = store.insert_material_index_job(
        {
            "id": "stale-running-job",
            "source_config_id": source["id"],
            "allowed_root_id": source["allowed_root_id"],
            "source_relative_path": source["source_relative_path"],
            "source_path_hash": source["source_path_hash"],
            "status": "running",
            "stage": "segmenting",
            "progress_current": 1,
            "progress_total": 3,
            "raw_files_total": 1,
            "segments_total": 0,
            "failed_total": 0,
            "heartbeat_at": stale_heartbeat,
            "attempt_count": 1,
            "error_summary": None,
            "created_at": "2026-06-24T00:00:00+00:00",
            "started_at": "2026-06-24T00:00:30+00:00",
            "finished_at": None,
        }
    )

    with TestClient(app) as client:
        response = client.put(
            "/api/material-sources/current",
            json={"allowed_root_id": "demo", "source_relative_path": "clips"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_source"]["id"] == source["id"]
    assert payload["job"]["id"] != running_job["id"]
    assert payload["job"]["status"] == "queued"
    assert store.get_material_index_job(running_job["id"])["status"] == "stale"


def test_material_sources_status_includes_latest_job_without_absolute_paths(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    (root / "clips").mkdir(parents=True)
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path / "data",
            material_allowed_roots=f"demo={root}",
        )
    )

    with TestClient(app) as client:
        save_response = client.put(
            "/api/material-sources/current",
            json={"allowed_root_id": "demo", "source_relative_path": "clips"},
        )
        response = client.get("/api/material-sources")

    assert save_response.status_code == 200
    assert response.status_code == 200
    payload = response.json()
    assert payload["allowed_roots"] == [
        {"id": "demo", "alias": "demo", "display_name": "demo"}
    ]
    assert payload["current_source"]["source_display_path"] == "demo/clips"
    assert payload["latest_job"]["id"] == save_response.json()["job"]["id"]
    assert str(root) not in str(payload)


def test_material_sources_status_latest_job_follows_current_source(tmp_path: Path) -> None:
    root = tmp_path / "source"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir(parents=True)
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        material_allowed_roots=f"demo={root}",
    )
    app = create_app(settings)
    store = AutoVideoStore(settings)

    with TestClient(app) as client:
        source_a_response = client.put(
            "/api/material-sources/current",
            json={"allowed_root_id": "demo", "source_relative_path": "a"},
        )

    assert source_a_response.status_code == 200
    MaterialSourceService(store).save_current_source("demo", "b")

    with TestClient(app) as client:
        response = client.get("/api/material-sources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_source"]["source_display_path"] == "demo/b"
    assert payload["latest_job"] is None


def test_material_sources_status_keeps_latest_job_visible_after_a_b_a_switch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir(parents=True)
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        material_allowed_roots=f"demo={root}",
    )
    app = create_app(settings)
    store = AutoVideoStore(settings)

    with TestClient(app) as client:
        first_a_response = client.put(
            "/api/material-sources/current",
            json={"allowed_root_id": "demo", "source_relative_path": "a"},
        )

    assert first_a_response.status_code == 200
    MaterialSourceService(store).save_current_source("demo", "b")

    with TestClient(app) as client:
        second_a_response = client.put(
            "/api/material-sources/current",
            json={"allowed_root_id": "demo", "source_relative_path": "a"},
        )
        status_response = client.get("/api/material-sources")

    assert second_a_response.status_code == 200
    assert status_response.status_code == 200
    second_a_payload = second_a_response.json()
    status_payload = status_response.json()
    assert status_payload["current_source"]["source_display_path"] == "demo/a"
    assert status_payload["latest_job"] is not None
    assert status_payload["latest_job"]["id"] == second_a_payload["job"]["id"]


def test_save_source_rejects_out_of_scope_path(tmp_path: Path) -> None:
    root = tmp_path / "source"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path / "data",
            material_allowed_roots=f"demo={root}",
        )
    )

    with TestClient(app) as client:
        response = client.put(
            "/api/material-sources/current",
            json={"allowed_root_id": "demo", "source_relative_path": "../outside"},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "MATERIAL_SOURCE_PATH_OUT_OF_SCOPE"
