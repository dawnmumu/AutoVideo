from __future__ import annotations

from collections.abc import Callable
import copy
from datetime import UTC, datetime
import json
import math
import os
from pathlib import Path
import secrets
import subprocess
import threading
from typing import Any

from autovideo.core.paths import build_data_paths
from autovideo.core.settings import Settings
from autovideo.services.bgm.models import (
    SUPPORTED_BGM_MEDIA_TYPES,
    AudioProbeResult,
    BgmCategoryDuplicateError,
    BgmCategoryEmptyError,
    BgmCategoryNameRequiredError,
    BgmCategoryNotFoundError,
    BgmFileEmptyError,
    BgmFileTooLargeError,
    BgmFileUnsupportedError,
    BgmLibraryCorruptError,
    BgmTrackNameRequiredError,
    BgmTrackNotFoundError,
    UNCATEGORIZED_NAME,
)

_STORE_LOCKS_GUARD = threading.Lock()
_STORE_LOCKS: dict[Path, threading.RLock] = {}
_CATEGORY_UNSET = object()
FFPROBE_TIMEOUT_SECONDS = 15
SUPPORTED_PROBE_MEDIA = (
    (
        "audio/mpeg",
        {"mp3"},
        {"mp3"},
    ),
    (
        "audio/wav",
        {"wav"},
        {
            "pcm_alaw",
            "pcm_f32be",
            "pcm_f32le",
            "pcm_f64be",
            "pcm_f64le",
            "pcm_mulaw",
            "pcm_s16be",
            "pcm_s16le",
            "pcm_s24be",
            "pcm_s24le",
            "pcm_s32be",
            "pcm_s32le",
            "pcm_u8",
        },
    ),
    (
        "audio/mp4",
        {"3g2", "3gp", "m4a", "mj2", "mov", "mp4"},
        {"aac", "alac"},
    ),
    (
        "audio/aac",
        {"aac"},
        {"aac"},
    ),
    (
        "audio/ogg",
        {"ogg"},
        {"flac", "opus", "vorbis"},
    ),
    (
        "audio/flac",
        {"flac"},
        {"flac"},
    ),
)

AudioProbe = Callable[[Path], AudioProbeResult]


class BgmLibraryService:
    def __init__(self, settings: Settings, audio_probe: AudioProbe | None = None) -> None:
        self.settings = settings
        self.audio_probe = audio_probe or probe_audio_metadata
        self.bgm_dir = build_data_paths(settings).bgm
        self._metadata_path = self.bgm_dir / "bgm_library.json"
        self._tracks_dir = self.bgm_dir / "tracks"

    def metadata_path(self) -> Path:
        return self._metadata_path

    def library(self) -> dict[str, Any]:
        with self._mutation_lock():
            data = self._load()
            categories = self._public_categories(data)
            tracks = self._public_tracks(data)
            return {
                "categories": categories,
                "items": tracks,
                "total_tracks": len(tracks),
            }

    def create_category(self, name: str) -> dict[str, Any]:
        normalized_name = self._normalize_category_name(name)
        with self._mutation_lock():
            data = self._load()
            self._ensure_category_name_available(data, normalized_name)
            now = _utc_now()
            category = {
                "id": self._new_category_id(data),
                "name": normalized_name,
                "created_at": now,
                "updated_at": now,
            }
            data["categories"].append(category)
            self._write(data)
            return copy.deepcopy(category)

    def update_category(self, category_id: str, name: str) -> dict[str, Any]:
        normalized_name = self._normalize_category_name(name)
        with self._mutation_lock():
            data = self._load()
            category = self._find_category(data, category_id)
            self._ensure_category_name_available(
                data,
                normalized_name,
                exclude_category_id=category_id,
            )
            category["name"] = normalized_name
            category["updated_at"] = _utc_now()
            self._write(data)
            return copy.deepcopy(category)

    def delete_category(self, category_id: str) -> dict[str, Any]:
        with self._mutation_lock():
            data = self._load()
            categories = data["categories"]
            index = self._category_index(data, category_id)
            del categories[index]
            for track in data["tracks"]:
                if isinstance(track, dict) and track.get("category_id") == category_id:
                    track["category_id"] = None
                    track["updated_at"] = _utc_now()
            self._write(data)
            return {"id": category_id, "deleted": True}

    def store_track(
        self,
        content: bytes,
        original_filename: str,
        *,
        category_id: str | None = None,
    ) -> dict[str, Any]:
        if not content:
            raise BgmFileEmptyError("BGM file is empty")
        if len(content) > self.settings.max_upload_bytes:
            raise BgmFileTooLargeError(self.settings.max_upload_bytes)

        filename = Path(original_filename).name
        extension = self._extension(filename)
        expected_media_type = SUPPORTED_BGM_MEDIA_TYPES.get(extension)
        if expected_media_type is None:
            raise BgmFileUnsupportedError(f"Unsupported BGM file extension: {extension}")

        self._tracks_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self._tracks_dir / f".upload-{secrets.token_hex(16)}.{extension}.tmp"
        target_path: Path | None = None

        try:
            temp_path.write_bytes(content)
            metadata = self.audio_probe(temp_path)
            if metadata.media_type != expected_media_type:
                raise BgmFileUnsupportedError(
                    f"BGM media type {metadata.media_type} does not match .{extension}"
                )

            with self._mutation_lock():
                data = self._load()
                if category_id is not None:
                    self._find_category(data, category_id)

                track_id = self._new_track_id(data)
                target_filename = f"{track_id}.{extension}"
                target_path = self._track_path(target_filename)
                os.replace(temp_path, target_path)
                temp_path = None

                now = _utc_now()
                track = {
                    "id": track_id,
                    "filename": target_filename,
                    "original_filename": filename,
                    "display_name": self._display_name(filename),
                    "category_id": category_id,
                    "duration_seconds": float(metadata.duration_seconds),
                    "media_type": metadata.media_type,
                    "created_at": now,
                    "updated_at": now,
                }
                data["tracks"].append(track)
                self._write(data)
                return self._public_track(track, self._categories_by_id(data))
        except Exception:
            self._cleanup_file(temp_path)
            self._cleanup_file(target_path)
            raise

    def update_track(
        self,
        track_id: str,
        *,
        display_name: str | None = None,
        category_id: str | None | object = _CATEGORY_UNSET,
    ) -> dict[str, Any]:
        with self._mutation_lock():
            data = self._load()
            track = self._find_track(data, track_id)
            if display_name is not None:
                normalized_name = display_name.strip()
                if not normalized_name:
                    raise BgmTrackNameRequiredError("BGM track display name is required")
                track["display_name"] = normalized_name
            if category_id is not _CATEGORY_UNSET:
                if category_id is not None:
                    self._find_category(data, str(category_id))
                track["category_id"] = category_id
            track["updated_at"] = _utc_now()
            self._write(data)
            return self._public_track(track, self._categories_by_id(data))

    def delete_track(self, track_id: str) -> dict[str, Any]:
        with self._mutation_lock():
            data = self._load()
            index = self._track_index(data, track_id)
            track = data["tracks"][index]
            filename = str(track.get("filename") or "")
            del data["tracks"][index]
            self._write(data)

        if filename:
            self._cleanup_file(self._track_path(filename))
        return {"id": track_id, "deleted": True}

    def get_track(self, track_id: str) -> dict[str, Any]:
        with self._mutation_lock():
            data = self._load()
            track = self._find_track(data, track_id)
            return self._public_track(track, self._categories_by_id(data))

    def track_file(self, track_id: str) -> Path:
        with self._mutation_lock():
            data = self._load()
            track = self._find_track(data, track_id)
            path = self._track_path(str(track.get("filename") or ""))
        if not path.is_file():
            raise BgmTrackNotFoundError(track_id)
        return path

    def track_snapshot(self, track_id: str) -> dict[str, Any]:
        return copy.deepcopy(self.get_track(track_id))

    def select_track_for_category(self, category_id: str | None) -> dict[str, Any]:
        with self._mutation_lock():
            data = self._load()
            if category_id is not None:
                self._find_category(data, category_id)
            tracks = [
                track
                for track in data["tracks"]
                if isinstance(track, dict) and track.get("category_id") == category_id
            ]
            if not tracks:
                raise BgmCategoryEmptyError(category_id or UNCATEGORIZED_NAME)
            selected = sorted(tracks, key=_track_selection_key)[0]
            return self._public_track(selected, self._categories_by_id(data))

    def _load(self) -> dict[str, Any]:
        if not self._metadata_path.exists():
            return {"tracks": [], "categories": []}

        try:
            raw = self._metadata_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise _corrupt_library("invalid JSON") from exc

        if not isinstance(data, dict):
            raise _corrupt_library("root must be an object")
        tracks = data.get("tracks")
        categories = data.get("categories")
        if not isinstance(tracks, list) or not isinstance(categories, list):
            raise _corrupt_library("tracks and categories must be arrays")

        normalized_categories = [_validate_category_row(category) for category in categories]
        _require_unique_ids(normalized_categories, "category")
        normalized_tracks = [_validate_track_row(track) for track in tracks]
        _require_unique_ids(normalized_tracks, "track")
        return {
            "tracks": normalized_tracks,
            "categories": normalized_categories,
        }

    def _write(self, data: dict[str, Any]) -> None:
        payload = {
            "categories": data.get("categories") if isinstance(data.get("categories"), list) else [],
            "tracks": data.get("tracks") if isinstance(data.get("tracks"), list) else [],
        }
        self._metadata_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = Path(f"{self._metadata_path}.{secrets.token_hex(8)}.tmp")
        try:
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(temp_path, self._metadata_path)
        finally:
            self._cleanup_file(temp_path)

    def _mutation_lock(self) -> threading.RLock:
        return _store_lock_for_path(self._metadata_path)

    def _new_track_id(self, data: dict[str, Any]) -> str:
        existing = {str(track.get("id")) for track in data["tracks"] if isinstance(track, dict)}
        while True:
            track_id = f"bgm_{secrets.token_hex(8)}"
            if track_id not in existing:
                return track_id

    def _new_category_id(self, data: dict[str, Any]) -> str:
        existing = {str(category.get("id")) for category in data["categories"] if isinstance(category, dict)}
        while True:
            category_id = f"cat_{secrets.token_hex(8)}"
            if category_id not in existing:
                return category_id

    def _find_track(self, data: dict[str, Any], track_id: str) -> dict[str, Any]:
        return data["tracks"][self._track_index(data, track_id)]

    def _track_index(self, data: dict[str, Any], track_id: str) -> int:
        for index, track in enumerate(data["tracks"]):
            if isinstance(track, dict) and track.get("id") == track_id:
                return index
        raise BgmTrackNotFoundError(track_id)

    def _find_category(self, data: dict[str, Any], category_id: str) -> dict[str, Any]:
        return data["categories"][self._category_index(data, category_id)]

    def _category_index(self, data: dict[str, Any], category_id: str) -> int:
        for index, category in enumerate(data["categories"]):
            if isinstance(category, dict) and category.get("id") == category_id:
                return index
        raise BgmCategoryNotFoundError(category_id)

    def _ensure_category_name_available(
        self,
        data: dict[str, Any],
        name: str,
        *,
        exclude_category_id: str | None = None,
    ) -> None:
        normalized = _category_lookup_key(name)
        for category in data["categories"]:
            if category.get("id") == exclude_category_id:
                continue
            if _category_lookup_key(str(category.get("name") or "")) == normalized:
                raise BgmCategoryDuplicateError(name)

    def _public_tracks(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        categories = self._categories_by_id(data)
        return [
            self._public_track(track, categories)
            for track in sorted(data["tracks"], key=_track_selection_key)
            if isinstance(track, dict)
        ]

    def _public_track(self, track: dict[str, Any], categories: dict[str, dict[str, Any]]) -> dict[str, Any]:
        category_id = track.get("category_id") if isinstance(track.get("category_id"), str) else None
        category = categories.get(category_id or "")
        public_category_id = category_id if category is not None else None
        category_name = str(category.get("name")) if category is not None else UNCATEGORIZED_NAME
        track_id = str(track.get("id") or "")
        filename = str(track.get("filename") or "")
        return {
            "id": track_id,
            "filename": filename,
            "original_filename": str(track.get("original_filename") or filename),
            "display_name": str(track.get("display_name") or Path(filename).stem or track_id),
            "category_id": public_category_id,
            "category_name": category_name,
            "duration_seconds": float(track.get("duration_seconds") or 0),
            "media_type": str(track.get("media_type") or ""),
            "audio_url": f"/api/bgm/tracks/{track_id}/file",
            "created_at": track.get("created_at"),
            "updated_at": track.get("updated_at"),
        }

    def _public_categories(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        return [copy.deepcopy(category) for category in sorted(data["categories"], key=_category_sort_key)]

    def _categories_by_id(self, data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {
            str(category.get("id")): category
            for category in data["categories"]
            if isinstance(category, dict) and str(category.get("id") or "").strip()
        }

    def _track_path(self, filename: str) -> Path:
        path = (self._tracks_dir / filename).resolve()
        tracks_dir = self._tracks_dir.resolve()
        if tracks_dir != path.parent:
            raise BgmTrackNotFoundError(filename)
        return path

    @staticmethod
    def _normalize_category_name(name: str) -> str:
        normalized = name.strip()
        if not normalized:
            raise BgmCategoryNameRequiredError("BGM category name is required")
        return normalized

    @staticmethod
    def _display_name(filename: str) -> str:
        display_name = Path(filename).stem.strip()
        return display_name or "未命名BGM"

    @staticmethod
    def _extension(filename: str) -> str:
        return Path(filename).suffix.lower().lstrip(".")

    @staticmethod
    def _cleanup_file(path: Path | None) -> None:
        if path is not None and path.exists():
            path.unlink()


def probe_audio_metadata(path: Path) -> AudioProbeResult:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=FFPROBE_TIMEOUT_SECONDS,
        )
        payload = json.loads(result.stdout)
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
    ) as exc:
        raise BgmFileUnsupportedError("Unable to probe BGM audio metadata") from exc

    stream = _first_audio_stream(payload)
    duration_seconds = _probe_duration_seconds(stream, payload.get("format"))
    codec_name = str(stream.get("codec_name") or "").strip().lower()
    format_name = str((payload.get("format") or {}).get("format_name") or "").strip().lower()
    media_type = _media_type_from_probe(codec_name, format_name)
    return AudioProbeResult(duration_seconds=duration_seconds, media_type=media_type)


def _store_lock_for_path(path: Path) -> threading.RLock:
    normalized = path.resolve()
    with _STORE_LOCKS_GUARD:
        lock = _STORE_LOCKS.get(normalized)
        if lock is None:
            lock = threading.RLock()
            _STORE_LOCKS[normalized] = lock
        return lock


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _track_selection_key(track: dict[str, Any]) -> tuple[str, str, str]:
    display_name = str(track.get("display_name") or track.get("filename") or "")
    filename = str(track.get("filename") or "")
    track_id = str(track.get("id") or "")
    return (display_name.casefold(), filename.casefold(), track_id)


def _category_sort_key(category: dict[str, Any]) -> tuple[str, str]:
    name = str(category.get("name") or "")
    category_id = str(category.get("id") or "")
    return (name.casefold(), category_id)


def _category_lookup_key(name: str) -> str:
    return name.strip().casefold()


def _first_audio_stream(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise BgmFileUnsupportedError("ffprobe payload is invalid")
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise BgmFileUnsupportedError("No audio stream found")
    for stream in streams:
        if isinstance(stream, dict) and stream.get("codec_type") == "audio":
            return stream
    raise BgmFileUnsupportedError("No audio stream found")


def _probe_duration_seconds(stream: dict[str, Any], format_info: Any) -> float:
    candidates = [stream.get("duration")]
    if isinstance(format_info, dict):
        candidates.append(format_info.get("duration"))

    for candidate in candidates:
        try:
            duration = float(candidate)
        except (TypeError, ValueError):
            continue
        if math.isfinite(duration) and duration > 0:
            return duration
    raise BgmFileUnsupportedError("Audio duration is missing")


def _media_type_from_probe(codec_name: str, format_name: str) -> str:
    format_names = {item for item in format_name.split(",") if item}
    for media_type, allowed_containers, allowed_codecs in SUPPORTED_PROBE_MEDIA:
        if codec_name in allowed_codecs and format_names.intersection(allowed_containers):
            return media_type
    raise BgmFileUnsupportedError(f"Unsupported BGM audio codec/container: {codec_name}/{format_name}")


def _corrupt_library(reason: str) -> BgmLibraryCorruptError:
    return BgmLibraryCorruptError(f"Invalid BGM library metadata: {reason}")


def _validate_category_row(category: Any) -> dict[str, Any]:
    if not isinstance(category, dict):
        raise _corrupt_library("category row must be an object")
    return {
        "id": _required_text(category, "id", "category"),
        "name": _required_text(category, "name", "category"),
        "created_at": _required_text(category, "created_at", "category"),
        "updated_at": _required_text(category, "updated_at", "category"),
    }


def _validate_track_row(track: Any) -> dict[str, Any]:
    if not isinstance(track, dict):
        raise _corrupt_library("track row must be an object")
    filename = _required_text(track, "filename", "track")
    if Path(filename).name != filename:
        raise _corrupt_library("track filename is invalid")
    media_type = _required_text(track, "media_type", "track")
    if media_type not in set(SUPPORTED_BGM_MEDIA_TYPES.values()):
        raise _corrupt_library("track media_type is unsupported")
    extension = Path(filename).suffix.lower().lstrip(".")
    if SUPPORTED_BGM_MEDIA_TYPES.get(extension) != media_type:
        raise _corrupt_library("track media_type does not match filename")
    return {
        "id": _required_text(track, "id", "track"),
        "filename": filename,
        "original_filename": _required_text(track, "original_filename", "track"),
        "display_name": _required_text(track, "display_name", "track"),
        "category_id": _optional_text(track, "category_id", "track"),
        "duration_seconds": _required_duration(track),
        "media_type": media_type,
        "created_at": _required_text(track, "created_at", "track"),
        "updated_at": _required_text(track, "updated_at", "track"),
    }


def _required_text(row: dict[str, Any], key: str, row_name: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _corrupt_library(f"{row_name}.{key} is required")
    return value


def _optional_text(row: dict[str, Any], key: str, row_name: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _corrupt_library(f"{row_name}.{key} must be a string")
    return value


def _required_duration(track: dict[str, Any]) -> float:
    try:
        duration = float(track.get("duration_seconds"))
    except (TypeError, ValueError) as exc:
        raise _corrupt_library("track.duration_seconds must be numeric") from exc
    if not math.isfinite(duration) or duration <= 0:
        raise _corrupt_library("track.duration_seconds must be positive")
    return duration


def _require_unique_ids(rows: list[dict[str, Any]], row_name: str) -> None:
    seen: set[str] = set()
    for row in rows:
        row_id = str(row["id"])
        if row_id in seen:
            raise _corrupt_library(f"duplicate {row_name} id")
        seen.add(row_id)
