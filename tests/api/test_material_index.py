from pathlib import Path

from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings
from autovideo.services.material_sources import MaterialSourceService
from autovideo.services.material_worker import MaterialWorkerService
from autovideo.storage.database import AutoVideoStore


def _store_with_root(tmp_path: Path) -> tuple[Settings, AutoVideoStore]:
    root = tmp_path / "source"
    (root / "clips").mkdir(parents=True, exist_ok=True)
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        material_allowed_roots=f"demo={root}",
    )
    return settings, AutoVideoStore(settings)


def test_create_index_job_rejects_active_job(tmp_path: Path) -> None:
    settings, store = _store_with_root(tmp_path)
    source = MaterialSourceService(store).save_current_source("demo", "clips")
    MaterialWorkerService(store).create_index_job(source["id"])
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.post(
            "/api/material-index/jobs",
            json={"source_config_id": source["id"], "force": True},
        )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "MATERIAL_INDEX_ALREADY_RUNNING"


def test_get_material_index_job_not_found(client) -> None:
    response = client.get("/api/material-index/jobs/missing-job")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "MATERIAL_INDEX_JOB_NOT_FOUND"


def test_clear_library_requires_confirmation(client) -> None:
    response = client.post("/api/material-index/library/clear", json={})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "MATERIAL_LIBRARY_CLEAR_CONFIRMATION_REQUIRED"


def test_clear_library_rejects_wrong_confirmation(client) -> None:
    response = client.post(
        "/api/material-index/library/clear",
        json={"confirm": "WRONG"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "MATERIAL_LIBRARY_CLEAR_CONFIRMATION_REQUIRED"


def test_raw_files_pagination_summary_and_segment_list(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")
    app = create_app(settings)
    store = AutoVideoStore(settings)
    store.insert_material_source_config(
        {
            "id": "source_1",
            "allowed_root_id": "demo",
            "allowed_root_alias": "demo",
            "source_relative_path": "clips",
            "source_display_path": "demo/clips",
            "source_path_hash": "a" * 64,
            "status": "active",
            "error_summary": None,
            "created_at": "2026-06-24T00:00:00+00:00",
            "updated_at": "2026-06-24T00:00:00+00:00",
        }
    )
    store.insert_material_index_job(
        {
            "id": "job_1",
            "source_config_id": "source_1",
            "allowed_root_id": "demo",
            "source_relative_path": "clips",
            "source_path_hash": "a" * 64,
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
    store.upsert_material_raw_file(
        {
            "id": "raw_1",
            "source_config_id": "source_1",
            "allowed_root_id": "demo",
            "source_relative_path": "clips/clip.mp4",
            "source_path_hash": "a" * 64,
            "source_display_path": "demo/clips/clip.mp4",
            "original_filename": "clip.mp4",
            "managed_raw_relative_path": "raw_1.mp4",
            "content_hash": "b" * 64,
            "size_bytes": 1024,
            "duration_seconds": 12.0,
            "orientation": "portrait",
            "status": "ready",
            "error_summary": None,
        }
    )
    store.upsert_material_segment(
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

    with TestClient(app) as client:
        raw_response = client.get("/api/material-index/raw-files?limit=1&offset=0")
        segment_response = client.get("/api/material-index/raw-files/raw_1/segments")
        summary_response = client.get("/api/material-index/summary")

    assert raw_response.status_code == 200
    raw_payload = raw_response.json()
    assert raw_payload["limit"] == 1
    assert raw_payload["offset"] == 0
    assert raw_payload["total"] == 1
    assert raw_payload["items"][0]["source_display_path"] == "demo/clips/clip.mp4"
    assert raw_payload["items"][0]["filename"] == "clip.mp4"
    assert raw_payload["items"][0]["segments"] == 1
    assert "managed_raw_relative_path" not in raw_payload["items"][0]

    assert segment_response.status_code == 200
    segment_payload = segment_response.json()
    assert segment_payload["limit"] == 50
    assert segment_payload["offset"] == 0
    assert segment_payload["total"] == 1
    assert segment_payload["items"][0]["id"] == "seg_1"
    assert "managed_segment_relative_path" not in segment_payload["items"][0]

    assert summary_response.status_code == 200
    summary_payload = summary_response.json()
    assert summary_payload["totals"]["raw"] == 1
    assert summary_payload["totals"]["segments"] == 1
    assert summary_payload["current_source"]["source_display_path"] == "demo/clips"
    assert summary_payload["latest_job"]["id"] == "job_1"
    assert "managed_raw_relative_path" not in str(summary_payload)


def test_delete_raw_file_removes_local_segment_material_records(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path / "data")
    app = create_app(settings)
    store = AutoVideoStore(settings)
    raw_path = store.paths.material_raw / "raw_1.mp4"
    segment_path = store.paths.material_segments / "raw_1" / "seg_1.mp4"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(b"raw")
    segment_path.parent.mkdir(parents=True, exist_ok=True)
    segment_path.write_bytes(b"segment")
    store.upsert_material_raw_file(
        {
            "id": "raw_1",
            "source_config_id": "source_1",
            "allowed_root_id": "demo",
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
    store.upsert_material_segment(
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
    store.insert_material(
        {
            "id": "mat_1",
            "original_filename": "clip.mp4",
            "content_type": "video/mp4",
            "size_bytes": 7,
            "storage_path": str(segment_path),
            "created_at": "2026-06-24T00:00:00+00:00",
            "source_type": "local_segment",
            "source_provider": "local_material_worker",
            "source_asset_id": "seg_1",
        }
    )

    with TestClient(app) as client:
        response = client.delete("/api/material-index/raw-files/raw_1")
        materials_response = client.get("/api/materials")

    assert response.status_code == 200
    assert response.json() == {"id": "raw_1", "deleted": True, "deleted_segments": 1}
    assert store.get_material("mat_1") is None
    assert all(item["id"] != "mat_1" for item in materials_response.json())


def test_clear_library_deletes_managed_files_and_material_rows_but_keeps_external_source(
    tmp_path: Path,
) -> None:
    external_root = tmp_path / "source"
    external_file = external_root / "clips" / "clip.mp4"
    external_file.parent.mkdir(parents=True)
    external_file.write_bytes(b"external original")
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        material_allowed_roots=f"demo={external_root}",
    )
    app = create_app(settings)
    store = AutoVideoStore(settings)
    raw_path = store.paths.material_raw / "raw_1.mp4"
    segment_path = store.paths.material_segments / "raw_1" / "seg_1.mp4"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(b"raw copy")
    segment_path.parent.mkdir(parents=True, exist_ok=True)
    segment_path.write_bytes(b"segment")
    store.upsert_material_raw_file(
        {
            "id": "raw_1",
            "source_config_id": "source_1",
            "allowed_root_id": "demo",
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
    store.upsert_material_segment(
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
    store.insert_material(
        {
            "id": "mat_1",
            "original_filename": "clip.mp4",
            "content_type": "video/mp4",
            "size_bytes": 7,
            "storage_path": str(segment_path),
            "created_at": "2026-06-24T00:00:00+00:00",
            "source_type": "local_segment",
            "source_provider": "local_material_worker",
            "source_asset_id": "seg_1",
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/material-index/library/clear",
            json={"confirm": "CLEAR_MATERIAL_LIBRARY"},
        )
        materials_response = client.get("/api/materials")

    assert response.status_code == 200
    assert response.json()["deleted_raw"] == 1
    assert response.json()["deleted_segments"] == 1
    assert external_file.exists()
    assert not raw_path.exists()
    assert not segment_path.exists()
    assert store.get_material_raw_file("raw_1")["deleted_at"] is not None
    assert store.get_material("mat_1") is None
    assert all(item["id"] != "mat_1" for item in materials_response.json())
