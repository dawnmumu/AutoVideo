from pathlib import Path

import pytest

from autovideo.core.settings import Settings
from autovideo.services.material_processing import (
    MaterialFfmpegUnavailableError,
    MaterialProcessingService,
    VideoProbeResult,
)
from autovideo.services.material_sources import MaterialSourceService
from autovideo.storage.database import AutoVideoStore


def _store(tmp_path: Path) -> AutoVideoStore:
    root = tmp_path / "source"
    (root / "clips").mkdir(parents=True, exist_ok=True)
    return AutoVideoStore(
        Settings(
            _env_file=None,
            data_dir=tmp_path / "data",
            ffmpeg_path="missing-ffmpeg",
            material_allowed_roots=f"demo={root}",
        )
    )


def test_scan_copies_and_records_video_segments(tmp_path: Path) -> None:
    source_root = tmp_path / "source" / "clips"
    source_root.mkdir(parents=True)
    (source_root / "clip.mp4").write_bytes(b"video")
    store = _store(tmp_path)
    source = MaterialSourceService(store).save_current_source("demo", "clips")
    service = MaterialProcessingService(
        store,
        probe_video=lambda path: VideoProbeResult(
            duration_seconds=12.0,
            width=1080,
            height=1920,
            codec_name="h264",
        ),
        slice_video=lambda source_path, target_path, start, duration: target_path.write_bytes(
            b"segment"
        ),
    )

    result = service.process_source(source)

    raw_files = store.list_material_raw_files(limit=10, offset=0)
    segments = store.list_material_segments(raw_files[0]["id"], limit=10, offset=0)
    assert result["raw_files_total"] == 1
    assert result["segments_total"] == 2
    assert raw_files[0]["source_display_path"] == "demo/clips/clip.mp4"
    assert Path(raw_files[0]["managed_raw_relative_path"]).is_absolute() is False
    assert segments[0]["managed_segment_relative_path"].startswith(raw_files[0]["id"])
    assert str(tmp_path / "source") not in str(raw_files + segments)


def test_scan_rejects_file_symlink_outside_allowed_root(tmp_path: Path) -> None:
    source_root = tmp_path / "source" / "clips"
    outside = tmp_path / "outside"
    source_root.mkdir(parents=True)
    outside.mkdir()
    (outside / "secret.mp4").write_bytes(b"secret")
    (source_root / "link.mp4").symlink_to(outside / "secret.mp4")
    store = _store(tmp_path)
    source = MaterialSourceService(store).save_current_source("demo", "clips")
    service = MaterialProcessingService(store)

    result = service.process_source(source)

    assert result["raw_files_total"] == 0
    assert result["failed_total"] == 1


def test_ffmpeg_unavailable_marks_job_failure(tmp_path: Path) -> None:
    source_root = tmp_path / "source" / "clips"
    source_root.mkdir(parents=True)
    (source_root / "clip.mp4").write_bytes(b"video")
    store = _store(tmp_path)
    source = MaterialSourceService(store).save_current_source("demo", "clips")
    service = MaterialProcessingService(store)

    with pytest.raises(MaterialFfmpegUnavailableError):
        service.process_source(source)


def test_delete_guard_rejects_corrupted_managed_path(tmp_path: Path) -> None:
    store = _store(tmp_path)
    raw = store.upsert_material_raw_file(
        {
            "id": "raw_1",
            "source_config_id": "source_1",
            "allowed_root_id": "demo",
            "source_relative_path": "clips/clip.mp4",
            "source_path_hash": "abc",
            "source_display_path": "demo/clips/clip.mp4",
            "original_filename": "clip.mp4",
            "managed_raw_relative_path": "../../outside.mp4",
            "content_hash": "content",
            "size_bytes": 5,
            "duration_seconds": 5.0,
            "orientation": "portrait",
            "status": "ready",
            "error_summary": None,
        }
    )

    deleted = MaterialProcessingService(store).delete_raw_file(raw["id"])

    assert deleted["deleted"] is False
    assert store.get_material_raw_file(raw["id"])["deleted_at"] is None


def test_delete_raw_file_removes_local_segment_material_records(tmp_path: Path) -> None:
    store = _store(tmp_path)
    raw_path = store.paths.material_raw / "raw_1.mp4"
    segment_path = store.paths.material_segments / "raw_1" / "seg_1.mp4"
    raw_path.write_bytes(b"raw")
    segment_path.parent.mkdir(parents=True)
    segment_path.write_bytes(b"segment")
    store.upsert_material_raw_file(
        {
            "id": "raw_1",
            "source_config_id": "source_1",
            "allowed_root_id": "demo",
            "source_relative_path": "clips/clip.mp4",
            "source_path_hash": "abc",
            "source_display_path": "demo/clips/clip.mp4",
            "original_filename": "clip.mp4",
            "managed_raw_relative_path": "raw_1.mp4",
            "content_hash": "content",
            "size_bytes": 5,
            "duration_seconds": 5.0,
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
            "duration_seconds": 5.0,
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

    deleted = MaterialProcessingService(store).delete_raw_file("raw_1")

    assert deleted["deleted"] is True
    assert store.get_material("mat_1") is None


def test_delete_raw_file_rejects_segment_directory_escape_before_any_deletion(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    raw_path = store.paths.material_raw / "escape.mp4"
    segment_path = store.paths.material_segments / "safe" / "seg_1.mp4"
    raw_path.write_bytes(b"raw")
    segment_path.parent.mkdir(parents=True)
    segment_path.write_bytes(b"segment")
    store.upsert_material_raw_file(
        {
            "id": "../escape",
            "source_config_id": "source_1",
            "allowed_root_id": "demo",
            "source_relative_path": "clips/clip.mp4",
            "source_path_hash": "abc",
            "source_display_path": "demo/clips/clip.mp4",
            "original_filename": "clip.mp4",
            "managed_raw_relative_path": "escape.mp4",
            "content_hash": "content",
            "size_bytes": 5,
            "duration_seconds": 5.0,
            "orientation": "portrait",
            "status": "ready",
            "error_summary": None,
        }
    )
    store.upsert_material_segment(
        {
            "id": "seg_1",
            "raw_file_id": "../escape",
            "managed_segment_relative_path": "safe/seg_1.mp4",
            "start_seconds": 0.0,
            "duration_seconds": 5.0,
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
            "id": "mat_escape",
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

    deleted = MaterialProcessingService(store).delete_raw_file("../escape")

    assert deleted == {
        "id": "../escape",
        "deleted": False,
        "error_code": "MATERIAL_LIBRARY_CLEAR_FAILED",
    }
    assert raw_path.exists()
    assert segment_path.exists()
    assert store.get_material_raw_file("../escape")["deleted_at"] is None
    assert store.list_material_segments("../escape", limit=10, offset=0)[0]["deleted_at"] is None
    assert store.get_material("mat_escape") is not None


def test_clear_library_validates_every_segment_dir_before_deleting_anything(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    safe_raw_path = store.paths.material_raw / "safe.mp4"
    safe_segment_path = store.paths.material_segments / "safe_raw" / "seg_safe.mp4"
    bad_raw_path = store.paths.material_raw / "bad.mp4"
    bad_segment_path = store.paths.material_segments / "bad_holder" / "seg_bad.mp4"
    safe_raw_path.write_bytes(b"safe-raw")
    bad_raw_path.write_bytes(b"bad-raw")
    safe_segment_path.parent.mkdir(parents=True)
    safe_segment_path.write_bytes(b"safe-segment")
    bad_segment_path.parent.mkdir(parents=True)
    bad_segment_path.write_bytes(b"bad-segment")
    store.upsert_material_raw_file(
        {
            "id": "../bad_raw",
            "source_config_id": "source_1",
            "allowed_root_id": "demo",
            "source_relative_path": "clips/bad.mp4",
            "source_path_hash": "bad",
            "source_display_path": "demo/clips/bad.mp4",
            "original_filename": "bad.mp4",
            "managed_raw_relative_path": "bad.mp4",
            "content_hash": "bad-content",
            "size_bytes": 7,
            "duration_seconds": 5.0,
            "orientation": "portrait",
            "status": "ready",
            "error_summary": None,
            "created_at": "2026-06-25T10:00:00+00:00",
            "updated_at": "2026-06-25T10:00:00+00:00",
        }
    )
    store.upsert_material_segment(
        {
            "id": "seg_bad",
            "raw_file_id": "../bad_raw",
            "managed_segment_relative_path": "bad_holder/seg_bad.mp4",
            "start_seconds": 0.0,
            "duration_seconds": 5.0,
            "orientation": "portrait",
            "status": "ready",
            "match_text": "bad",
            "asr_text": None,
            "ocr_text": None,
            "vision_description": None,
            "content_label_status": "not_configured",
            "embedding_status": "not_configured",
            "error_summary": None,
            "created_at": "2026-06-25T10:00:00+00:00",
            "updated_at": "2026-06-25T10:00:00+00:00",
        }
    )
    store.insert_material(
        {
            "id": "mat_bad",
            "original_filename": "bad.mp4",
            "content_type": "video/mp4",
            "size_bytes": 7,
            "storage_path": str(bad_segment_path),
            "created_at": "2026-06-25T10:00:00+00:00",
            "source_type": "local_segment",
            "source_provider": "local_material_worker",
            "source_asset_id": "seg_bad",
        }
    )
    store.upsert_material_raw_file(
        {
            "id": "safe_raw",
            "source_config_id": "source_1",
            "allowed_root_id": "demo",
            "source_relative_path": "clips/safe.mp4",
            "source_path_hash": "safe",
            "source_display_path": "demo/clips/safe.mp4",
            "original_filename": "safe.mp4",
            "managed_raw_relative_path": "safe.mp4",
            "content_hash": "safe-content",
            "size_bytes": 8,
            "duration_seconds": 5.0,
            "orientation": "portrait",
            "status": "ready",
            "error_summary": None,
            "created_at": "2026-06-25T11:00:00+00:00",
            "updated_at": "2026-06-25T11:00:00+00:00",
        }
    )
    store.upsert_material_segment(
        {
            "id": "seg_safe",
            "raw_file_id": "safe_raw",
            "managed_segment_relative_path": "safe_raw/seg_safe.mp4",
            "start_seconds": 0.0,
            "duration_seconds": 5.0,
            "orientation": "portrait",
            "status": "ready",
            "match_text": "safe",
            "asr_text": None,
            "ocr_text": None,
            "vision_description": None,
            "content_label_status": "not_configured",
            "embedding_status": "not_configured",
            "error_summary": None,
            "created_at": "2026-06-25T11:00:00+00:00",
            "updated_at": "2026-06-25T11:00:00+00:00",
        }
    )
    store.insert_material(
        {
            "id": "mat_safe",
            "original_filename": "safe.mp4",
            "content_type": "video/mp4",
            "size_bytes": 8,
            "storage_path": str(safe_segment_path),
            "created_at": "2026-06-25T11:00:00+00:00",
            "source_type": "local_segment",
            "source_provider": "local_material_worker",
            "source_asset_id": "seg_safe",
        }
    )

    cleared = MaterialProcessingService(store).clear_library("CLEAR_MATERIAL_LIBRARY")

    assert cleared == {
        "id": "../bad_raw",
        "deleted": False,
        "error_code": "MATERIAL_LIBRARY_CLEAR_FAILED",
    }
    assert safe_raw_path.exists()
    assert safe_segment_path.exists()
    assert bad_raw_path.exists()
    assert bad_segment_path.exists()
    assert store.get_material_raw_file("safe_raw")["deleted_at"] is None
    assert store.get_material_raw_file("../bad_raw")["deleted_at"] is None
    assert store.get_material("mat_safe") is not None
    assert store.get_material("mat_bad") is not None
