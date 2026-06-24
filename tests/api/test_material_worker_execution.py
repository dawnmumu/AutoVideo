from pathlib import Path

from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings
from autovideo.storage.database import AutoVideoStore


class FakeMaterialProcessingService:
    def __init__(self, store: AutoVideoStore) -> None:
        self.store = store

    def process_source(self, source: dict[str, object]) -> dict[str, int]:
        segment_path = self.store.paths.material_segments / "raw_1" / "seg_1.mp4"
        segment_path.parent.mkdir(parents=True, exist_ok=True)
        segment_path.write_bytes(b"segment")
        self.store.upsert_material_raw_file(
            {
                "id": "raw_1",
                "source_config_id": str(source["id"]),
                "allowed_root_id": str(source["allowed_root_id"]),
                "source_relative_path": "clips/clip.mp4",
                "source_path_hash": "a" * 64,
                "source_display_path": "demo/clips/clip.mp4",
                "original_filename": "clip.mp4",
                "managed_raw_relative_path": "raw_1.mp4",
                "content_hash": "b" * 64,
                "size_bytes": 1024,
                "duration_seconds": 8.0,
                "orientation": "portrait",
                "status": "ready",
                "error_summary": None,
            }
        )
        self.store.upsert_material_segment(
            {
                "id": "seg_1",
                "raw_file_id": "raw_1",
                "managed_segment_relative_path": "raw_1/seg_1.mp4",
                "start_seconds": 0.0,
                "duration_seconds": 8.0,
                "orientation": "portrait",
                "status": "ready",
                "match_text": "clip",
                "asr_text": None,
                "ocr_text": None,
                "vision_description": None,
                "content_label_status": "not_configured",
                "embedding_status": "not_configured",
                "error_summary": None,
            }
        )
        return {"raw_files_total": 1, "segments_total": 1, "failed_total": 0}


def test_save_source_runs_index_job_in_background(tmp_path: Path) -> None:
    root = tmp_path / "source"
    (root / "clips").mkdir(parents=True)
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        material_allowed_roots=f"demo={root}",
    )
    app = create_app(settings)
    store = AutoVideoStore(settings)
    app.state.material_processing_service = FakeMaterialProcessingService(store)

    with TestClient(app) as client:
        response = client.put(
            "/api/material-sources/current",
            json={"allowed_root_id": "demo", "source_relative_path": "clips"},
        )
        payload = response.json()
        job_response = client.get(f"/api/material-index/jobs/{payload['job']['id']}")
        raw_response = client.get("/api/material-index/raw-files")
        segment_response = client.get("/api/material-index/raw-files/raw_1/segments")
        summary_response = client.get("/api/material-index/summary")

    assert response.status_code == 200
    job_payload = job_response.json()
    assert job_payload["status"] == "succeeded"
    assert job_payload["stage"] == "ready"
    assert job_payload["attempt_count"] == 1
    assert job_payload["started_at"]
    assert job_payload["heartbeat_at"]
    assert raw_response.json()["total"] == 1
    assert raw_response.json()["items"][0]["segments"] == 1
    assert segment_response.json()["total"] == 1
    assert segment_response.json()["items"][0]["id"] == "seg_1"
    assert summary_response.json()["totals"]["segments"] == 1


def test_manual_refresh_runs_index_job_in_background(tmp_path: Path) -> None:
    root = tmp_path / "source"
    (root / "clips").mkdir(parents=True)
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        material_allowed_roots=f"demo={root}",
    )
    app = create_app(settings)
    store = AutoVideoStore(settings)
    app.state.material_processing_service = FakeMaterialProcessingService(store)

    with TestClient(app) as client:
        source_response = client.put(
            "/api/material-sources/current",
            json={"allowed_root_id": "demo", "source_relative_path": "clips"},
        )
        first_job = source_response.json()["job"]["id"]
        store.update_material_index_job(
            first_job,
            {"status": "failed", "finished_at": "2026-06-24T00:00:00+00:00"},
        )
        refresh_response = client.post(
            "/api/material-index/jobs",
            json={"source_config_id": source_response.json()["current_source"]["id"], "force": True},
        )
        refresh_job = refresh_response.json()["job_id"]
        job_response = client.get(f"/api/material-index/jobs/{refresh_job}")

    assert refresh_response.status_code == 200
    job_payload = job_response.json()
    assert job_payload["status"] == "succeeded"
    assert job_payload["stage"] == "ready"
    assert job_payload["attempt_count"] == 1
    assert job_payload["started_at"]
    assert job_payload["heartbeat_at"]
