from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from autovideo.core.settings import Settings
from autovideo.services.material_matcher import (
    MaterialLibraryEmptyError,
    MaterialLibraryNotReadyError,
    MaterialMatcherService,
)
from autovideo.services.material_sources import MaterialSourceService
from autovideo.services.material_worker import MaterialWorkerService
from autovideo.storage.database import AutoVideoStore


def _store_with_current_source(tmp_path: Path) -> tuple[AutoVideoStore, dict[str, object]]:
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


def test_prepare_for_script_creates_material_id_for_ready_segment(tmp_path: Path) -> None:
    store = AutoVideoStore(Settings(_env_file=None, data_dir=tmp_path))
    segment_path = store.paths.material_segments / "raw_1" / "seg_1.mp4"
    segment_path.parent.mkdir(parents=True)
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
            "size_bytes": 7,
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
            "match_text": "spa room clip",
            "asr_text": None,
            "ocr_text": None,
            "vision_description": None,
            "content_label_status": "not_configured",
            "embedding_status": "not_configured",
            "error_summary": None,
        }
    )
    script = {
        "aspect_ratio": "9:16",
        "shots": [
            {
                "index": 1,
                "duration": 5,
                "keywords": ["spa"],
                "visual_description": "spa room",
            }
        ],
    }

    selections = MaterialMatcherService(store).prepare_for_script(script, "local")

    assert selections[0]["shot_index"] == 1
    assert selections[0]["material_id"]
    assert selections[0]["material_segment_id"] == "seg_1"
    material = store.get_material(selections[0]["material_id"])
    assert material["source_type"] == "local_segment"
    assert material["source_provider"] == "local_material_worker"
    assert material["source_asset_id"] == "seg_1"


def test_prepare_for_script_raises_empty_when_no_ready_segments(tmp_path: Path) -> None:
    store = AutoVideoStore(Settings(_env_file=None, data_dir=tmp_path))
    script = {"aspect_ratio": "9:16", "shots": [{"index": 1, "duration": 5}]}

    with pytest.raises(MaterialLibraryEmptyError):
        MaterialMatcherService(store).prepare_for_script(script, "local")


def test_prepare_for_script_creates_index_job_when_current_source_has_no_ready_segments(
    tmp_path: Path,
) -> None:
    store, source = _store_with_current_source(tmp_path)
    script = {"aspect_ratio": "9:16", "shots": [{"index": 1, "duration": 5}]}

    with pytest.raises(MaterialLibraryNotReadyError) as exc_info:
        MaterialMatcherService(store).prepare_for_script(script, "local")

    job = exc_info.value.job
    assert job["source_config_id"] == source["id"]
    assert job["status"] == "queued"
    assert store.latest_material_index_job(source["id"])["id"] == job["id"]


def test_prepare_for_script_reuses_active_job_when_current_source_has_no_ready_segments(
    tmp_path: Path,
) -> None:
    store, source = _store_with_current_source(tmp_path)
    existing_job = MaterialWorkerService(store).create_index_job(source["id"])
    script = {"aspect_ratio": "9:16", "shots": [{"index": 1, "duration": 5}]}

    with pytest.raises(MaterialLibraryNotReadyError) as exc_info:
        MaterialMatcherService(store).prepare_for_script(script, "hybrid")

    assert exc_info.value.job["id"] == existing_job["id"]
    assert exc_info.value.job["status"] == "queued"


def test_prepare_for_script_reuses_active_job_for_same_source_identity(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir()
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        material_allowed_roots=f"demo={root}",
    )
    store = AutoVideoStore(settings)
    source_a = MaterialSourceService(store).save_current_source("demo", "a")
    existing_job = MaterialWorkerService(store).create_index_job(source_a["id"])
    MaterialSourceService(store).save_current_source("demo", "b")
    MaterialSourceService(store).save_current_source("demo", "a")
    script = {"aspect_ratio": "9:16", "shots": [{"index": 1, "duration": 5}]}

    with pytest.raises(MaterialLibraryNotReadyError) as exc_info:
        MaterialMatcherService(store).prepare_for_script(script, "local")

    assert exc_info.value.job["id"] == existing_job["id"]
    assert exc_info.value.job["status"] == "queued"


def test_prepare_for_script_recovers_stale_running_job_before_not_ready(
    tmp_path: Path,
) -> None:
    store, source = _store_with_current_source(tmp_path)
    stale_heartbeat = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    stale_job = store.insert_material_index_job(
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
    script = {"aspect_ratio": "9:16", "shots": [{"index": 1, "duration": 5}]}

    with pytest.raises(MaterialLibraryNotReadyError) as exc_info:
        MaterialMatcherService(store).prepare_for_script(script, "local")

    assert exc_info.value.job["id"] != stale_job["id"]
    assert exc_info.value.job["status"] == "queued"
    assert store.get_material_index_job(stale_job["id"])["status"] == "stale"
