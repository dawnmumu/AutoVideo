import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from autovideo.core.settings import Settings
from autovideo.services.bgm import (
    BgmCategoryDuplicateError,
    BgmCategoryEmptyError,
    BgmCategoryNotFoundError,
    BgmFileEmptyError,
    BgmFileTooLargeError,
    BgmFileUnsupportedError,
    BgmLibraryCorruptError,
    BgmLibraryService,
    BgmTrackNameRequiredError,
    BgmTrackNotFoundError,
    AudioProbeResult,
)


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        data_dir=tmp_path,
        ffmpeg_path="missing-ffmpeg",
        **overrides,
    )


def _probe(duration_seconds: float = 12.5, media_type: str = "audio/mpeg"):
    def probe(path: Path) -> AudioProbeResult:
        return AudioProbeResult(duration_seconds=duration_seconds, media_type=media_type)

    return probe


def test_store_track_generates_stable_id_and_audio_metadata(tmp_path: Path) -> None:
    service = BgmLibraryService(_settings(tmp_path), audio_probe=_probe(184.32))
    category = service.create_category("舒缓")

    track = service.store_track(
        content=b"fake mp3 bytes",
        original_filename="春日疗愈.mp3",
        category_id=category["id"],
    )
    library = service.library()

    assert track["id"].startswith("bgm_")
    assert track["filename"] == f"{track['id']}.mp3"
    assert track["original_filename"] == "春日疗愈.mp3"
    assert track["display_name"] == "春日疗愈"
    assert track["category_id"] == category["id"]
    assert track["category_name"] == "舒缓"
    assert track["duration_seconds"] == 184.32
    assert track["media_type"] == "audio/mpeg"
    assert track["audio_url"] == f"/api/bgm/tracks/{track['id']}/file"
    assert "directory" not in library
    assert library["total_tracks"] == 1
    assert (tmp_path / "bgm" / "tracks" / track["filename"]).is_file()


def test_store_track_rejects_empty_and_unsupported_files(tmp_path: Path) -> None:
    service = BgmLibraryService(_settings(tmp_path), audio_probe=_probe())

    with pytest.raises(BgmFileEmptyError):
        service.store_track(content=b"", original_filename="empty.mp3")

    with pytest.raises(BgmFileUnsupportedError):
        service.store_track(content=b"not audio", original_filename="track.exe")


def test_store_track_rejects_content_over_configured_limit(tmp_path: Path) -> None:
    service = BgmLibraryService(
        _settings(tmp_path, max_upload_bytes=4),
        audio_probe=_probe(),
    )

    with pytest.raises(BgmFileTooLargeError):
        service.store_track(content=b"12345", original_filename="large.mp3")

    assert list((tmp_path / "bgm" / "tracks").glob("*")) == []
    assert service.library()["items"] == []


def test_store_track_rejects_extension_and_probe_media_type_mismatch(tmp_path: Path) -> None:
    service = BgmLibraryService(_settings(tmp_path), audio_probe=_probe(media_type="audio/wav"))

    with pytest.raises(BgmFileUnsupportedError):
        service.store_track(content=b"real wav bytes", original_filename="pretend.mp3")

    assert list((tmp_path / "bgm" / "tracks").glob("*")) == []
    assert service.library()["items"] == []


def test_store_track_rejects_probe_failures_and_cleans_temp_file(tmp_path: Path) -> None:
    def failing_probe(path: Path) -> AudioProbeResult:
        raise BgmFileUnsupportedError("no audio stream")

    service = BgmLibraryService(_settings(tmp_path), audio_probe=failing_probe)

    with pytest.raises(BgmFileUnsupportedError):
        service.store_track(content=b"fake", original_filename="fake.mp3")

    assert list((tmp_path / "bgm" / "tracks").glob("*")) == []
    assert service.library()["items"] == []


def test_update_track_preserves_id_and_audio_url(tmp_path: Path) -> None:
    service = BgmLibraryService(_settings(tmp_path), audio_probe=_probe())
    first = service.create_category("舒缓")
    second = service.create_category("欢快")
    track = service.store_track(b"fake", "night.mp3", category_id=first["id"])

    updated = service.update_track(
        track["id"],
        display_name="夜间放松",
        category_id=second["id"],
    )

    assert updated["id"] == track["id"]
    assert updated["audio_url"] == track["audio_url"]
    assert updated["display_name"] == "夜间放松"
    assert updated["category_id"] == second["id"]
    assert updated["category_name"] == "欢快"


def test_update_track_rejects_blank_name_and_missing_category(tmp_path: Path) -> None:
    service = BgmLibraryService(_settings(tmp_path), audio_probe=_probe())
    track = service.store_track(b"fake", "night.mp3")

    with pytest.raises(BgmTrackNameRequiredError):
        service.update_track(track["id"], display_name="   ")

    with pytest.raises(BgmCategoryNotFoundError):
        service.update_track(track["id"], category_id="cat_missing")


def test_delete_category_moves_tracks_to_uncategorized(tmp_path: Path) -> None:
    service = BgmLibraryService(_settings(tmp_path), audio_probe=_probe())
    category = service.create_category("舒缓")
    track = service.store_track(b"fake", "night.mp3", category_id=category["id"])

    service.delete_category(category["id"])
    updated = service.get_track(track["id"])

    assert updated["category_id"] is None
    assert updated["category_name"] == "未分类"
    assert service.library()["categories"] == []


def test_duplicate_category_names_are_rejected_case_insensitively(tmp_path: Path) -> None:
    service = BgmLibraryService(_settings(tmp_path), audio_probe=_probe())
    service.create_category("Calm")

    with pytest.raises(BgmCategoryDuplicateError):
        service.create_category(" calm ")


def test_select_track_for_category_is_deterministic_and_snapshotted(tmp_path: Path) -> None:
    service = BgmLibraryService(_settings(tmp_path), audio_probe=_probe())
    category = service.create_category("舒缓")
    first = service.store_track(b"first", "a-first.mp3", category_id=category["id"])
    service.store_track(b"second", "b-second.mp3", category_id=category["id"])

    selected = service.select_track_for_category(category["id"])
    snapshot = service.track_snapshot(selected["id"])

    assert selected["id"] == first["id"]
    assert snapshot["id"] == first["id"]
    assert snapshot["duration_seconds"] == first["duration_seconds"]


def test_select_track_for_empty_category_raises(tmp_path: Path) -> None:
    service = BgmLibraryService(_settings(tmp_path), audio_probe=_probe())
    category = service.create_category("空分类")

    with pytest.raises(BgmCategoryEmptyError):
        service.select_track_for_category(category["id"])


def test_missing_registered_file_is_cleaned_when_deleted(tmp_path: Path) -> None:
    service = BgmLibraryService(_settings(tmp_path), audio_probe=_probe())
    track = service.store_track(b"fake", "lost.mp3")
    (tmp_path / "bgm" / "tracks" / track["filename"]).unlink()

    result = service.delete_track(track["id"])

    assert result == {"id": track["id"], "deleted": True}
    assert service.library()["items"] == []


def test_unknown_track_delete_raises_not_found(tmp_path: Path) -> None:
    service = BgmLibraryService(_settings(tmp_path), audio_probe=_probe())

    with pytest.raises(BgmTrackNotFoundError):
        service.delete_track("bgm_missing")


def test_corrupt_metadata_is_not_overwritten(tmp_path: Path) -> None:
    service = BgmLibraryService(_settings(tmp_path), audio_probe=_probe())
    metadata_path = service.metadata_path()
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(BgmLibraryCorruptError):
        service.library()

    assert metadata_path.read_text(encoding="utf-8") == "{not-json"


def test_concurrent_metadata_mutations_do_not_drop_updates(tmp_path: Path) -> None:
    service = BgmLibraryService(_settings(tmp_path), audio_probe=_probe())

    def upload(index: int) -> str:
        return service.store_track(
            content=f"fake-{index}".encode("utf-8"),
            original_filename=f"track-{index}.mp3",
        )["id"]

    with ThreadPoolExecutor(max_workers=4) as executor:
        ids = list(executor.map(upload, range(8)))

    library = service.library()
    assert sorted(item["id"] for item in library["items"]) == sorted(ids)
    raw = json.loads(service.metadata_path().read_text(encoding="utf-8"))
    assert len(raw["tracks"]) == 8
