import json
import subprocess
from concurrent.futures import TimeoutError
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
    probe_audio_metadata,
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


def test_store_track_does_not_hold_metadata_lock_while_probe_runs(tmp_path: Path) -> None:
    service = BgmLibraryService(_settings(tmp_path))

    def probe(path: Path) -> AudioProbeResult:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(service.create_category, "Probe Side Category")
        try:
            future.result(timeout=0.5)
        except TimeoutError:
            future.cancel()
            raise
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        return AudioProbeResult(duration_seconds=12.5, media_type="audio/mpeg")

    service.audio_probe = probe

    track = service.store_track(content=b"fake", original_filename="probe-lock.mp3")

    assert track["display_name"] == "probe-lock"
    assert [category["name"] for category in service.library()["categories"]] == [
        "Probe Side Category"
    ]


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

    with pytest.raises(BgmLibraryCorruptError) as exc_info:
        service.library()

    assert str(tmp_path) not in str(exc_info.value)
    assert metadata_path.read_text(encoding="utf-8") == "{not-json"


def test_invalid_utf8_metadata_is_corrupt_and_not_overwritten(tmp_path: Path) -> None:
    service = BgmLibraryService(_settings(tmp_path), audio_probe=_probe())
    metadata_path = service.metadata_path()
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_bytes(b"\xff\xfe\xfd")

    with pytest.raises(BgmLibraryCorruptError) as exc_info:
        service.library()

    assert str(tmp_path) not in str(exc_info.value)
    assert metadata_path.read_bytes() == b"\xff\xfe\xfd"


@pytest.mark.parametrize(
    "payload",
    [
        {"tracks": [{"id": "bgm_bad"}], "categories": []},
        {
            "tracks": [
                {
                    "id": "bgm_bad",
                    "filename": "bgm_bad.mp3",
                    "original_filename": "bad.mp3",
                    "display_name": "bad",
                    "category_id": None,
                    "duration_seconds": "not-a-number",
                    "media_type": "audio/mpeg",
                    "created_at": "2026-06-21T00:00:00+00:00",
                    "updated_at": "2026-06-21T00:00:00+00:00",
                }
            ],
            "categories": [],
        },
        {"tracks": [], "categories": [{"id": "cat_bad"}]},
        {
            "tracks": [],
            "categories": [
                {
                    "id": "",
                    "name": "bad",
                    "created_at": "2026-06-21T00:00:00+00:00",
                    "updated_at": "2026-06-21T00:00:00+00:00",
                }
            ],
        },
    ],
)
def test_malformed_metadata_rows_are_corrupt_and_not_overwritten(
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    service = BgmLibraryService(_settings(tmp_path), audio_probe=_probe())
    metadata_path = service.metadata_path()
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False)
    metadata_path.write_text(raw, encoding="utf-8")

    with pytest.raises(BgmLibraryCorruptError) as exc_info:
        service.library()

    assert str(tmp_path) not in str(exc_info.value)
    assert metadata_path.read_text(encoding="utf-8") == raw


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


def _patch_ffprobe(monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]):
    calls = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append({"args": args, "kwargs": kwargs})
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr("autovideo.services.bgm.service.subprocess.run", fake_run)
    return calls


def _ffprobe_payload(
    *,
    codec_name: str = "mp3",
    format_name: str = "mp3",
    stream_duration: str | None = "12.5",
    format_duration: str | None = "12.5",
    codec_type: str = "audio",
) -> dict[str, object]:
    stream = {
        "codec_type": codec_type,
        "codec_name": codec_name,
    }
    if stream_duration is not None:
        stream["duration"] = stream_duration
    format_info = {"format_name": format_name}
    if format_duration is not None:
        format_info["duration"] = format_duration
    return {"streams": [stream], "format": format_info}


def test_probe_audio_metadata_maps_valid_ffprobe_json_and_sets_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_ffprobe(monkeypatch, _ffprobe_payload())

    result = probe_audio_metadata(tmp_path / "track.mp3")

    assert result == AudioProbeResult(duration_seconds=12.5, media_type="audio/mpeg")
    assert calls[0]["kwargs"]["timeout"] > 0


def test_probe_audio_metadata_uses_format_duration_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ffprobe(
        monkeypatch,
        _ffprobe_payload(stream_duration=None, format_duration="7.25"),
    )

    result = probe_audio_metadata(tmp_path / "track.mp3")

    assert result.duration_seconds == 7.25


def test_probe_audio_metadata_rejects_missing_duration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ffprobe(
        monkeypatch,
        _ffprobe_payload(stream_duration=None, format_duration=None),
    )

    with pytest.raises(BgmFileUnsupportedError):
        probe_audio_metadata(tmp_path / "track.mp3")


def test_probe_audio_metadata_rejects_no_audio_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ffprobe(
        monkeypatch,
        _ffprobe_payload(codec_name="h264", format_name="mov,mp4,m4a,3gp,3g2,mj2", codec_type="video"),
    )

    with pytest.raises(BgmFileUnsupportedError):
        probe_audio_metadata(tmp_path / "track.mp4")


def test_probe_audio_metadata_rejects_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=args, timeout=kwargs["timeout"])

    monkeypatch.setattr("autovideo.services.bgm.service.subprocess.run", fake_run)

    with pytest.raises(BgmFileUnsupportedError):
        probe_audio_metadata(tmp_path / "track.mp3")


def test_probe_audio_metadata_rejects_unsupported_wav_codec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_ffprobe(monkeypatch, _ffprobe_payload(codec_name="mp3", format_name="wav"))

    with pytest.raises(BgmFileUnsupportedError):
        probe_audio_metadata(tmp_path / "track.wav")


@pytest.mark.parametrize(
    "codec_name, format_name",
    [
        ("vorbis", "mov,mp4,m4a,3gp,3g2,mj2"),
        ("aac", "matroska,webm"),
    ],
)
def test_probe_audio_metadata_rejects_unsupported_mp4_codec_container_combinations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    codec_name: str,
    format_name: str,
) -> None:
    _patch_ffprobe(monkeypatch, _ffprobe_payload(codec_name=codec_name, format_name=format_name))

    with pytest.raises(BgmFileUnsupportedError):
        probe_audio_metadata(tmp_path / "track.m4a")
