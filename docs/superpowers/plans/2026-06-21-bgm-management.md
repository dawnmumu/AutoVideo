# BGM 管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 AutoVideo 的 BGM 资源管理、混剪工作台 BGM 选择和任务快照保存。

**Architecture:** 后端新增 `autovideo/services/bgm/` 服务包和 `/api/bgm` 路由，文件系统保存音频，JSON 保存元数据，所有元数据读改写在同一把 mutation lock 内完成。混剪任务只保存清洗后的 BGM 配置和快照，本轮不把 BGM 混入最终 MP4。前端新增 BGM API、BGM 管理工作台和混剪工作台选择器，并同步 README。

**Tech Stack:** FastAPI, Pydantic, pytest, React, TypeScript, TanStack Query, Vitest, Testing Library, Lucide, CSS.

---

## 关联文档

- Spec: `docs/superpowers/specs/2026-06-20-bgm-management-design.md`
- Product baseline: `docs/superpowers/specs/2026-06-13-autovideo-product-redesign-design.md`
- Voice selection reference: `docs/superpowers/specs/2026-06-20-mix-workbench-voice-selection-design.md`

## 文件结构

- Create: `autovideo/services/bgm/models.py`
  - BGM 扩展名、媒体类型、结构化模型和异常基础类型。
- Create: `autovideo/services/bgm/service.py`
  - BGM library JSON 读写、mutation lock、音频探测、分类与曲目 CRUD、快照解析。
- Create: `autovideo/services/bgm/__init__.py`
  - 导出服务层 API。
- Create: `autovideo/api/routes/bgm.py`
  - `/api/bgm` 路由和结构化错误映射。
- Modify: `autovideo/api/app.py`
  - 注册 BGM 路由；把 `POST /api/bgm/tracks` 接入 request-size middleware。
- Modify: `autovideo/services/online_mix.py`
  - 新增 `normalize_bgm_options()` 并写入 task options 与 manifest。
- Modify: `autovideo/api/routes/online_mix.py`
  - 映射 BGM 相关结构化错误。
- Create: `tests/services/test_bgm_library.py`
  - BGM service 行为测试。
- Create: `tests/api/test_bgm.py`
  - BGM API 行为测试。
- Modify: `tests/api/test_online_mix.py`
  - BGM task snapshot 测试。
- Create: `frontend/src/api/bgm.ts`
  - BGM API client、类型、错误 helper。
- Create: `frontend/src/components/BgmManagementWorkbench.tsx`
  - BGM 管理页。
- Create: `frontend/src/components/BgmSelector.tsx`
  - 混剪工作台 BGM 选择器。
- Modify: `frontend/src/components/OnlineRemixWorkbench.tsx`
  - 接入 `BgmSelector`，提交 BGM options。
- Modify: `frontend/src/api/onlineRemix.ts`
  - 增加 BGM options 类型。
- Modify: `frontend/src/App.tsx`
  - 启用 `BGM 管理` 导航和 section。
- Modify: `frontend/src/App.test.tsx`
  - BGM 导航、管理页、选择器、任务提交测试。
- Modify: `frontend/src/styles.css`
  - BGM 管理页和选择器响应式样式。
- Modify: `tests/web/test_frontend_build.py`
  - 静态源检查 BGM 布局约束。
- Modify: `README.md`
  - API、功能状态、混剪 options 和当前未混音说明。

---

### Task 1: BGM Service Models And Library Store

**Files:**
- Create: `tests/services/test_bgm_library.py`
- Create: `autovideo/services/bgm/models.py`
- Create: `autovideo/services/bgm/service.py`
- Create: `autovideo/services/bgm/__init__.py`

- [ ] **Step 1: 写服务层失败测试**

Create `tests/services/test_bgm_library.py` with these tests:

```python
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
```

- [ ] **Step 2: 运行服务层测试确认失败**

Run:

```bash
pytest tests/services/test_bgm_library.py -q
```

Expected:

```text
ERROR tests/services/test_bgm_library.py
ModuleNotFoundError: No module named 'autovideo.services.bgm'
```

- [ ] **Step 3: 实现 BGM models**

Create `autovideo/services/bgm/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_BGM_MEDIA_TYPES: dict[str, str] = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "aac": "audio/aac",
    "ogg": "audio/ogg",
    "flac": "audio/flac",
}
SUPPORTED_BGM_EXTENSIONS = frozenset(SUPPORTED_BGM_MEDIA_TYPES)
UNCATEGORIZED_NAME = "未分类"


@dataclass(frozen=True)
class AudioProbeResult:
    duration_seconds: float
    media_type: str


class BgmLibraryError(RuntimeError):
    code = "BGM_LIBRARY_ERROR"


class BgmLibraryCorruptError(BgmLibraryError):
    code = "BGM_LIBRARY_CORRUPT"


class BgmFileUnsupportedError(BgmLibraryError):
    code = "BGM_FILE_UNSUPPORTED"


class BgmFileEmptyError(BgmLibraryError):
    code = "BGM_FILE_EMPTY"


class BgmFileTooLargeError(BgmLibraryError):
    code = "BGM_FILE_TOO_LARGE"

    def __init__(self, max_upload_bytes: int) -> None:
        self.max_upload_bytes = max_upload_bytes
        super().__init__(str(max_upload_bytes))


class BgmTrackNotFoundError(BgmLibraryError):
    code = "BGM_TRACK_NOT_FOUND"


class BgmCategoryNotFoundError(BgmLibraryError):
    code = "BGM_CATEGORY_NOT_FOUND"


class BgmCategoryDuplicateError(BgmLibraryError):
    code = "BGM_CATEGORY_DUPLICATE"


class BgmCategoryNameRequiredError(BgmLibraryError):
    code = "BGM_CATEGORY_NAME_REQUIRED"


class BgmTrackNameRequiredError(BgmLibraryError):
    code = "BGM_TRACK_NAME_REQUIRED"


class BgmCategoryEmptyError(BgmLibraryError):
    code = "BGM_CATEGORY_EMPTY"
```

- [ ] **Step 4: 实现 BGM service**

Create `autovideo/services/bgm/service.py` with these public names and behavior:

```python
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from typing import Any, Callable

from autovideo.core.paths import build_data_paths
from autovideo.core.settings import Settings
from autovideo.services.bgm.models import (
    SUPPORTED_BGM_EXTENSIONS,
    SUPPORTED_BGM_MEDIA_TYPES,
    UNCATEGORIZED_NAME,
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
)

AudioProbe = Callable[[Path], AudioProbeResult]
_LOCKS: dict[Path, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()
CODEC_CONTAINER_MEDIA_TYPES: dict[str, dict[str, set[str]]] = {
    "audio/mpeg": {"formats": {"mp3"}, "codecs": {"mp3"}},
    "audio/wav": {"formats": {"wav"}, "codecs": {"pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le", "pcm_f64le"}},
    "audio/mp4": {"formats": {"m4a", "mp4", "mov"}, "codecs": {"aac", "alac", "mp3"}},
    "audio/aac": {"formats": {"aac"}, "codecs": {"aac"}},
    "audio/ogg": {"formats": {"ogg"}, "codecs": {"vorbis", "opus", "flac"}},
    "audio/flac": {"formats": {"flac"}, "codecs": {"flac"}},
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _clean_text(value: str | None, max_length: int = 120) -> str:
    return str(value or "").strip()[:max_length]


def _extension(filename: str) -> str:
    ext = Path(str(filename or "")).suffix.lower().lstrip(".")
    if ext not in SUPPORTED_BGM_EXTENSIONS:
        raise BgmFileUnsupportedError(ext or "missing")
    return ext


def _display_name(filename: str) -> str:
    return _clean_text(Path(str(filename or "")).stem) or "未命名 BGM"


def _probe_media_type(audio_stream: dict[str, Any], format_payload: dict[str, Any]) -> str:
    codec = str(audio_stream.get("codec_name") or "").lower()
    format_names = {
        item.strip().lower()
        for item in str(format_payload.get("format_name") or "").split(",")
        if item.strip()
    }
    for media_type, rule in CODEC_CONTAINER_MEDIA_TYPES.items():
        if codec in rule["codecs"] and format_names.intersection(rule["formats"]):
            return media_type
    raise BgmFileUnsupportedError(
        f"unsupported audio codec/container: {codec or 'unknown'}/"
        f"{','.join(sorted(format_names)) or 'unknown'}"
    )


def probe_audio_metadata(path: Path) -> AudioProbeResult:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_type,codec_name:format=duration,format_name",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        payload = json.loads(completed.stdout or "{}")
    except Exception as exc:
        raise BgmFileUnsupportedError("audio probe failed") from exc
    streams = payload.get("streams")
    if not isinstance(streams, list) or not any(
        isinstance(item, dict) and item.get("codec_type") == "audio" for item in streams
    ):
        raise BgmFileUnsupportedError("no audio stream")
    audio_stream = next(
        item for item in streams if isinstance(item, dict) and item.get("codec_type") == "audio"
    )
    format_payload = payload.get("format")
    if not isinstance(format_payload, dict):
        raise BgmFileUnsupportedError("format unavailable")
    duration = format_payload.get("duration")
    try:
        duration_seconds = round(float(duration), 3)
    except (TypeError, ValueError) as exc:
        raise BgmFileUnsupportedError("duration unavailable") from exc
    return AudioProbeResult(
        duration_seconds=duration_seconds,
        media_type=_probe_media_type(audio_stream, format_payload),
    )


class BgmLibraryService:
    def __init__(self, settings: Settings, audio_probe: AudioProbe | None = None) -> None:
        self.settings = settings
        self.paths = build_data_paths(settings)
        self.root = self.paths.bgm
        self.tracks_dir = self.root / "tracks"
        self.audio_probe = audio_probe or probe_audio_metadata

    def metadata_path(self) -> Path:
        return self.root / "bgm_library.json"

    def _lock(self) -> threading.RLock:
        path = self.metadata_path().resolve()
        with _LOCKS_GUARD:
            lock = _LOCKS.get(path)
            if lock is None:
                lock = threading.RLock()
                _LOCKS[path] = lock
            return lock

    def _empty_library(self) -> dict[str, Any]:
        return {"version": 1, "categories": [], "tracks": []}

    def _ensure_dirs(self) -> None:
        self.tracks_dir.mkdir(parents=True, exist_ok=True)

    def _read_library_unlocked(self) -> dict[str, Any]:
        path = self.metadata_path()
        if not path.exists():
            return self._empty_library()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise BgmLibraryCorruptError(str(path)) from exc
        if not isinstance(payload, dict):
            raise BgmLibraryCorruptError(str(path))
        categories = payload.get("categories")
        tracks = payload.get("tracks")
        if not isinstance(categories, list) or not isinstance(tracks, list):
            raise BgmLibraryCorruptError(str(path))
        return {"version": 1, "categories": categories, "tracks": tracks}

    def _write_library_unlocked(self, payload: dict[str, Any]) -> None:
        self._ensure_dirs()
        path = self.metadata_path()
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(tmp_path, path)

    def _category_by_id(self, library: dict[str, Any], category_id: str | None) -> dict[str, Any] | None:
        if not category_id:
            return None
        for category in library["categories"]:
            if category.get("id") == category_id:
                return category
        return None

    def _track_by_id(self, library: dict[str, Any], track_id: str) -> dict[str, Any] | None:
        for track in library["tracks"]:
            if track.get("id") == track_id:
                return track
        return None

    def _public_track(self, track: dict[str, Any], library: dict[str, Any]) -> dict[str, Any]:
        category = self._category_by_id(library, track.get("category_id"))
        return {
            "id": track["id"],
            "filename": track["filename"],
            "original_filename": track["original_filename"],
            "display_name": track["display_name"],
            "category_id": track.get("category_id"),
            "category_name": category["name"] if category else UNCATEGORIZED_NAME,
            "media_type": track["media_type"],
            "extension": track["extension"],
            "size_bytes": int(track["size_bytes"]),
            "duration_seconds": float(track["duration_seconds"]),
            "audio_url": f"/api/bgm/tracks/{track['id']}/file",
            "created_at": track["created_at"],
            "updated_at": track["updated_at"],
        }

    def _public_category(self, category: dict[str, Any], library: dict[str, Any]) -> dict[str, Any]:
        count = sum(
            1 for track in library["tracks"] if track.get("category_id") == category["id"]
        )
        return {
            "id": category["id"],
            "name": category["name"],
            "sort_order": int(category.get("sort_order") or 0),
            "track_count": count,
            "created_at": category["created_at"],
            "updated_at": category["updated_at"],
        }

    def library(self) -> dict[str, Any]:
        with self._lock():
            library = self._read_library_unlocked()
            return {
                "items": [self._public_track(track, library) for track in library["tracks"]],
                "categories": [
                    self._public_category(category, library)
                    for category in sorted(
                        library["categories"],
                        key=lambda item: (int(item.get("sort_order") or 0), str(item.get("name") or "").lower()),
                    )
                ],
                "storage_status": "ready",
                "total_tracks": len(library["tracks"]),
                "supported_extensions": sorted(SUPPORTED_BGM_EXTENSIONS),
            }

    def create_category(self, name: str) -> dict[str, Any]:
        clean_name = _clean_text(name, max_length=80)
        if not clean_name:
            raise BgmCategoryNameRequiredError()
        with self._lock():
            library = self._read_library_unlocked()
            if any(str(item.get("name") or "").lower() == clean_name.lower() for item in library["categories"]):
                raise BgmCategoryDuplicateError(clean_name)
            now = _utc_now()
            sort_order = max([int(item.get("sort_order") or 0) for item in library["categories"]] or [0]) + 10
            category = {
                "id": f"cat_{uuid.uuid4().hex}",
                "name": clean_name,
                "sort_order": sort_order,
                "created_at": now,
                "updated_at": now,
            }
            library["categories"].append(category)
            self._write_library_unlocked(library)
            return self._public_category(category, library)

    def update_category(self, category_id: str, name: str) -> dict[str, Any]:
        clean_name = _clean_text(name, max_length=80)
        if not clean_name:
            raise BgmCategoryNameRequiredError()
        with self._lock():
            library = self._read_library_unlocked()
            category = self._category_by_id(library, category_id)
            if category is None:
                raise BgmCategoryNotFoundError(category_id)
            if any(
                item.get("id") != category_id and str(item.get("name") or "").lower() == clean_name.lower()
                for item in library["categories"]
            ):
                raise BgmCategoryDuplicateError(clean_name)
            category["name"] = clean_name
            category["updated_at"] = _utc_now()
            self._write_library_unlocked(library)
            return self._public_category(category, library)

    def delete_category(self, category_id: str) -> dict[str, Any]:
        with self._lock():
            library = self._read_library_unlocked()
            category = self._category_by_id(library, category_id)
            if category is None:
                raise BgmCategoryNotFoundError(category_id)
            library["categories"] = [
                item for item in library["categories"] if item.get("id") != category_id
            ]
            for track in library["tracks"]:
                if track.get("category_id") == category_id:
                    track["category_id"] = None
                    track["updated_at"] = _utc_now()
            self._write_library_unlocked(library)
            return {"id": category_id, "deleted": True}

    def store_track(
        self,
        content: bytes,
        original_filename: str,
        category_id: str | None = None,
    ) -> dict[str, Any]:
        if not content:
            raise BgmFileEmptyError()
        ext = _extension(original_filename)
        self._ensure_dirs()
        track_id = f"bgm_{uuid.uuid4().hex}"
        filename = f"{track_id}.{ext}"
        tmp_path = self.tracks_dir / f"{filename}.tmp"
        target_path = self.tracks_dir / filename
        tmp_path.write_bytes(content)
        try:
            size_bytes = tmp_path.stat().st_size
            if size_bytes <= 0:
                raise BgmFileEmptyError()
            if size_bytes > self.settings.max_upload_bytes:
                raise BgmFileTooLargeError(self.settings.max_upload_bytes)
            probe = self.audio_probe(tmp_path)
            expected_media_type = SUPPORTED_BGM_MEDIA_TYPES[ext]
            if probe.media_type != expected_media_type:
                raise BgmFileUnsupportedError(
                    f"{probe.media_type} does not match .{ext} ({expected_media_type})"
                )
            now = _utc_now()
            with self._lock():
                library = self._read_library_unlocked()
                if category_id and self._category_by_id(library, category_id) is None:
                    raise BgmCategoryNotFoundError(category_id)
                os.replace(tmp_path, target_path)
                track = {
                    "id": track_id,
                    "filename": filename,
                    "original_filename": Path(str(original_filename)).name,
                    "display_name": _display_name(original_filename),
                    "category_id": category_id,
                    "media_type": probe.media_type,
                    "extension": ext,
                    "size_bytes": int(target_path.stat().st_size),
                    "duration_seconds": probe.duration_seconds,
                    "created_at": now,
                    "updated_at": now,
                }
                library["tracks"].append(track)
                self._write_library_unlocked(library)
                return self._public_track(track, library)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            if target_path.exists():
                target_path.unlink()
            raise

    def get_track(self, track_id: str) -> dict[str, Any]:
        with self._lock():
            library = self._read_library_unlocked()
            track = self._track_by_id(library, track_id)
            if track is None:
                raise BgmTrackNotFoundError(track_id)
            return self._public_track(track, library)

    def update_track(
        self,
        track_id: str,
        display_name: str | None = None,
        category_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock():
            library = self._read_library_unlocked()
            track = self._track_by_id(library, track_id)
            if track is None:
                raise BgmTrackNotFoundError(track_id)
            if category_id and self._category_by_id(library, category_id) is None:
                raise BgmCategoryNotFoundError(category_id)
            clean_name = _clean_text(display_name if display_name is not None else track.get("display_name"))
            if not clean_name:
                raise BgmTrackNameRequiredError()
            track["display_name"] = clean_name
            track["category_id"] = category_id
            track["updated_at"] = _utc_now()
            self._write_library_unlocked(library)
            return self._public_track(track, library)

    def delete_track(self, track_id: str) -> dict[str, Any]:
        with self._lock():
            library = self._read_library_unlocked()
            track = self._track_by_id(library, track_id)
            if track is None:
                raise BgmTrackNotFoundError(track_id)
            track_path = self.tracks_dir / str(track["filename"])
            if track_path.exists():
                track_path.unlink()
            library["tracks"] = [item for item in library["tracks"] if item.get("id") != track_id]
            self._write_library_unlocked(library)
            return {"id": track_id, "deleted": True}

    def track_file(self, track_id: str) -> tuple[Path, str, str]:
        with self._lock():
            library = self._read_library_unlocked()
            track = self._track_by_id(library, track_id)
            if track is None:
                raise BgmTrackNotFoundError(track_id)
            path = (self.tracks_dir / str(track["filename"])).resolve()
            if self.tracks_dir.resolve() not in path.parents or not path.is_file():
                raise BgmTrackNotFoundError(track_id)
            return path, str(track["media_type"]), str(track["original_filename"])

    def track_snapshot(self, track_id: str) -> dict[str, Any]:
        track = self.get_track(track_id)
        return {
            "id": track["id"],
            "display_name": track["display_name"],
            "filename": track["filename"],
            "original_filename": track["original_filename"],
            "media_type": track["media_type"],
            "size_bytes": track["size_bytes"],
            "duration_seconds": track["duration_seconds"],
        }

    def select_track_for_category(self, category_id: str) -> dict[str, Any]:
        with self._lock():
            library = self._read_library_unlocked()
            if self._category_by_id(library, category_id) is None:
                raise BgmCategoryNotFoundError(category_id)
            tracks = [
                track for track in library["tracks"] if track.get("category_id") == category_id
            ]
            if not tracks:
                raise BgmCategoryEmptyError(category_id)
            selected = sorted(tracks, key=lambda item: str(item.get("display_name") or item.get("filename") or ""))[0]
            return self._public_track(selected, library)
```

- [ ] **Step 5: 导出 service API**

Create `autovideo/services/bgm/__init__.py`:

```python
from autovideo.services.bgm.models import (
    AudioProbeResult,
    BgmCategoryDuplicateError,
    BgmCategoryEmptyError,
    BgmCategoryNameRequiredError,
    BgmCategoryNotFoundError,
    BgmFileEmptyError,
    BgmFileTooLargeError,
    BgmFileUnsupportedError,
    BgmLibraryCorruptError,
    BgmLibraryError,
    BgmTrackNameRequiredError,
    BgmTrackNotFoundError,
)
from autovideo.services.bgm.service import BgmLibraryService, probe_audio_metadata

__all__ = [
    "AudioProbeResult",
    "BgmCategoryDuplicateError",
    "BgmCategoryEmptyError",
    "BgmCategoryNameRequiredError",
    "BgmCategoryNotFoundError",
    "BgmFileEmptyError",
    "BgmFileTooLargeError",
    "BgmFileUnsupportedError",
    "BgmLibraryCorruptError",
    "BgmLibraryError",
    "BgmLibraryService",
    "BgmTrackNameRequiredError",
    "BgmTrackNotFoundError",
    "probe_audio_metadata",
]
```

- [ ] **Step 6: 运行服务层测试确认通过**

Run:

```bash
pytest tests/services/test_bgm_library.py -q
```

Expected:

```text
15 passed
```

- [ ] **Step 7: 提交 Task 1**

Run:

```bash
git add tests/services/test_bgm_library.py autovideo/services/bgm
git commit -m "feat: add bgm library service"
```

---

### Task 2: BGM API Routes And Request Size Gate

**Files:**
- Create: `tests/api/test_bgm.py`
- Create: `autovideo/api/routes/bgm.py`
- Modify: `autovideo/api/app.py`

- [ ] **Step 1: 写 API 失败测试**

Create `tests/api/test_bgm.py`:

```python
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings
from autovideo.services.bgm import AudioProbeResult


def bgm_client(tmp_path: Path, **overrides: Any) -> TestClient:
    settings = Settings(_env_file=None, data_dir=tmp_path, **overrides)
    app = create_app(settings)
    app.state.bgm_audio_probe = lambda path: AudioProbeResult(
        duration_seconds=9.75,
        media_type="audio/mpeg",
    )
    return TestClient(app)


def test_bgm_library_starts_empty_without_exposing_directory(tmp_path: Path) -> None:
    with bgm_client(tmp_path) as client:
        response = client.get("/api/bgm")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["categories"] == []
    assert payload["storage_status"] == "ready"
    assert payload["total_tracks"] == 0
    assert "mp3" in payload["supported_extensions"]
    assert "directory" not in payload
    assert str(tmp_path) not in response.text


def test_upload_bgm_track_and_download_audio(tmp_path: Path) -> None:
    with bgm_client(tmp_path) as client:
        category = client.post("/api/bgm/categories", json={"name": "舒缓"}).json()
        upload = client.post(
            "/api/bgm/tracks",
            data={"category_id": category["id"]},
            files={"file": ("spring.mp3", b"fake audio bytes", "audio/mpeg")},
        )
        audio = client.get(upload.json()["audio_url"])

    assert upload.status_code == 201
    payload = upload.json()
    assert payload["display_name"] == "spring"
    assert payload["category_name"] == "舒缓"
    assert payload["duration_seconds"] == 9.75
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/mpeg")
    assert audio.headers["x-content-type-options"] == "nosniff"
    assert audio.content == b"fake audio bytes"


def test_upload_bgm_rejects_unsupported_extension(tmp_path: Path) -> None:
    with bgm_client(tmp_path) as client:
        response = client.post(
            "/api/bgm/tracks",
            files={"file": ("bad.exe", b"fake", "application/octet-stream")},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "BGM_FILE_UNSUPPORTED"


def test_upload_bgm_oversized_request_uses_global_middleware(tmp_path: Path) -> None:
    with bgm_client(tmp_path, max_upload_bytes=2, max_multipart_overhead_bytes=0) as client:
        response = client.post(
            "/api/bgm/tracks",
            files={"file": ("too-large.mp3", b"1234567890", "audio/mpeg")},
        )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "REQUEST_TOO_LARGE"
    assert response.json()["detail"]["max_request_bytes"] == 2


def test_upload_bgm_oversized_file_uses_service_limit_after_multipart_parse(tmp_path: Path) -> None:
    with bgm_client(tmp_path, max_upload_bytes=4, max_multipart_overhead_bytes=4096) as client:
        response = client.post(
            "/api/bgm/tracks",
            files={"file": ("too-large.mp3", b"12345", "audio/mpeg")},
        )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "BGM_FILE_TOO_LARGE"
    assert response.json()["detail"]["max_upload_bytes"] == 4


def test_update_and_delete_bgm_track(tmp_path: Path) -> None:
    with bgm_client(tmp_path) as client:
        category = client.post("/api/bgm/categories", json={"name": "舒缓"}).json()
        track = client.post(
            "/api/bgm/tracks",
            files={"file": ("spring.mp3", b"fake", "audio/mpeg")},
        ).json()
        updated = client.put(
            f"/api/bgm/tracks/{track['id']}",
            json={"display_name": "春日疗愈", "category_id": category["id"]},
        )
        deleted = client.delete(f"/api/bgm/tracks/{track['id']}")
        missing = client.get(f"/api/bgm/tracks/{track['id']}/file")

    assert updated.status_code == 200
    assert updated.json()["display_name"] == "春日疗愈"
    assert updated.json()["category_id"] == category["id"]
    assert deleted.status_code == 200
    assert deleted.json() == {"id": track["id"], "deleted": True}
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "BGM_TRACK_NOT_FOUND"


def test_delete_category_moves_tracks_to_uncategorized(tmp_path: Path) -> None:
    with bgm_client(tmp_path) as client:
        category = client.post("/api/bgm/categories", json={"name": "舒缓"}).json()
        track = client.post(
            "/api/bgm/tracks",
            data={"category_id": category["id"]},
            files={"file": ("spring.mp3", b"fake", "audio/mpeg")},
        ).json()
        response = client.delete(f"/api/bgm/categories/{category['id']}")
        library = client.get("/api/bgm").json()

    assert response.status_code == 200
    assert response.json() == {"id": category["id"], "deleted": True}
    assert library["categories"] == []
    item = next(item for item in library["items"] if item["id"] == track["id"])
    assert item["category_id"] is None
    assert item["category_name"] == "未分类"


def test_duplicate_category_returns_structured_error(tmp_path: Path) -> None:
    with bgm_client(tmp_path) as client:
        client.post("/api/bgm/categories", json={"name": "舒缓"})
        response = client.post("/api/bgm/categories", json={"name": " 舒缓 "})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "BGM_CATEGORY_DUPLICATE"
```

- [ ] **Step 2: 运行 API 测试确认失败**

Run:

```bash
pytest tests/api/test_bgm.py -q
```

Expected:

```text
404 Not Found
```

or:

```text
ModuleNotFoundError: No module named 'autovideo.api.routes.bgm'
```

- [ ] **Step 3: 实现 BGM routes**

Create `autovideo/api/routes/bgm.py`:

```python
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from autovideo.api.dependencies import get_settings
from autovideo.api.errors import structured_error
from autovideo.core.settings import Settings
from autovideo.services.bgm import (
    BgmCategoryDuplicateError,
    BgmCategoryEmptyError,
    BgmCategoryNameRequiredError,
    BgmCategoryNotFoundError,
    BgmFileEmptyError,
    BgmFileTooLargeError,
    BgmFileUnsupportedError,
    BgmLibraryCorruptError,
    BgmLibraryService,
    BgmTrackNameRequiredError,
    BgmTrackNotFoundError,
)

router = APIRouter(prefix="/api/bgm", tags=["bgm"])


class BgmCategoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class BgmTrackUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    category_id: str | None = None


def _service(request: Request, settings: Settings) -> BgmLibraryService:
    return BgmLibraryService(
        settings,
        audio_probe=getattr(request.app.state, "bgm_audio_probe", None),
    )


def _raise_bgm_error(exc: Exception) -> None:
    if isinstance(exc, BgmFileUnsupportedError):
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "BGM_FILE_UNSUPPORTED",
            allowed=["mp3", "wav", "m4a", "aac", "ogg", "flac"],
        ) from exc
    if isinstance(exc, BgmFileEmptyError):
        raise structured_error(status.HTTP_400_BAD_REQUEST, "BGM_FILE_EMPTY") from exc
    if isinstance(exc, BgmFileTooLargeError):
        raise structured_error(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "BGM_FILE_TOO_LARGE",
            max_upload_bytes=exc.max_upload_bytes,
        ) from exc
    if isinstance(exc, BgmTrackNotFoundError):
        raise structured_error(status.HTTP_404_NOT_FOUND, "BGM_TRACK_NOT_FOUND") from exc
    if isinstance(exc, BgmCategoryNotFoundError):
        raise structured_error(status.HTTP_404_NOT_FOUND, "BGM_CATEGORY_NOT_FOUND") from exc
    if isinstance(exc, BgmCategoryDuplicateError):
        raise structured_error(status.HTTP_400_BAD_REQUEST, "BGM_CATEGORY_DUPLICATE") from exc
    if isinstance(exc, BgmCategoryNameRequiredError):
        raise structured_error(status.HTTP_400_BAD_REQUEST, "BGM_CATEGORY_NAME_REQUIRED") from exc
    if isinstance(exc, BgmTrackNameRequiredError):
        raise structured_error(status.HTTP_400_BAD_REQUEST, "BGM_TRACK_NAME_REQUIRED") from exc
    if isinstance(exc, BgmCategoryEmptyError):
        raise structured_error(status.HTTP_400_BAD_REQUEST, "BGM_CATEGORY_EMPTY") from exc
    if isinstance(exc, BgmLibraryCorruptError):
        raise structured_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "BGM_LIBRARY_CORRUPT") from exc
    raise exc


@router.get("")
def list_bgm(request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    try:
        return _service(request, settings).library()
    except Exception as exc:
        _raise_bgm_error(exc)
        raise


@router.post("/tracks", status_code=status.HTTP_201_CREATED)
async def upload_bgm_track(
    request: Request,
    file: UploadFile = File(...),
    category_id: str | None = Form(default=None),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return _service(request, settings).store_track(
            content=await file.read(),
            original_filename=file.filename or "bgm",
            category_id=category_id or None,
        )
    except Exception as exc:
        _raise_bgm_error(exc)
        raise


@router.put("/tracks/{track_id}")
def update_bgm_track(
    track_id: str,
    body: BgmTrackUpdateRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return _service(request, settings).update_track(
            track_id,
            display_name=body.display_name,
            category_id=body.category_id,
        )
    except Exception as exc:
        _raise_bgm_error(exc)
        raise


@router.delete("/tracks/{track_id}")
def delete_bgm_track(
    track_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return _service(request, settings).delete_track(track_id)
    except Exception as exc:
        _raise_bgm_error(exc)
        raise


@router.get("/tracks/{track_id}/file")
def download_bgm_track(
    track_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> Response:
    try:
        path, media_type, filename = _service(request, settings).track_file(track_id)
    except Exception as exc:
        _raise_bgm_error(exc)
        raise
    response = FileResponse(path, media_type=media_type, filename=filename)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@router.post("/categories", status_code=status.HTTP_201_CREATED)
def create_bgm_category(
    body: BgmCategoryRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return _service(request, settings).create_category(body.name)
    except Exception as exc:
        _raise_bgm_error(exc)
        raise


@router.put("/categories/{category_id}")
def update_bgm_category(
    category_id: str,
    body: BgmCategoryRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return _service(request, settings).update_category(category_id, body.name)
    except Exception as exc:
        _raise_bgm_error(exc)
        raise


@router.delete("/categories/{category_id}")
def delete_bgm_category(
    category_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return _service(request, settings).delete_category(category_id)
    except Exception as exc:
        _raise_bgm_error(exc)
        raise
```

- [ ] **Step 4: 注册 BGM route 和 size middleware**

Modify `autovideo/api/app.py`:

```python
from autovideo.api.routes.bgm import router as bgm_router
```

Add this branch in `reject_oversized_request` after `/api/materials`:

```python
        elif request.method == "POST" and request.url.path == "/api/bgm/tracks":
            max_request_bytes = active_settings.max_material_request_bytes
```

Register route before static frontend:

```python
    app.include_router(bgm_router)
```

- [ ] **Step 5: 运行 API 测试确认通过**

Run:

```bash
pytest tests/api/test_bgm.py -q
```

Expected:

```text
8 passed
```

- [ ] **Step 6: 运行相关后端测试**

Run:

```bash
pytest tests/services/test_bgm_library.py tests/api/test_bgm.py tests/api/test_health.py -q
```

Expected:

```text
passed
```

- [ ] **Step 7: 提交 Task 2**

Run:

```bash
git add tests/api/test_bgm.py autovideo/api/routes/bgm.py autovideo/api/app.py
git commit -m "feat: expose bgm management api"
```

---

### Task 3: BGM Options In Online Mix Tasks

**Files:**
- Modify: `tests/api/test_online_mix.py`
- Modify: `autovideo/services/online_mix.py`
- Modify: `autovideo/api/routes/online_mix.py`

- [ ] **Step 1: 写混剪任务失败测试**

Append these tests to `tests/api/test_online_mix.py`:

```python
def _create_bgm_track(client, name: str = "calm.mp3") -> dict:
    category = client.post("/api/bgm/categories", json={"name": "舒缓"}).json()
    track = client.post(
        "/api/bgm/tracks",
        data={"category_id": category["id"]},
        files={"file": (name, b"fake audio bytes", "audio/mpeg")},
    ).json()
    return {"category": category, "track": track}


def test_online_mix_persists_bgm_track_options_in_task_and_manifest(tmp_path):
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path=_write_fake_ffmpeg(tmp_path),
        )
    )
    app.state.bgm_audio_probe = lambda path: AudioProbeResult(
        duration_seconds=8.5,
        media_type="audio/mpeg",
    )

    with TestClient(app) as client:
        material = client.post(
            "/api/materials",
            files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
        ).json()
        bgm = _create_bgm_track(client)
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "带 BGM 配置任务",
                "script": _single_shot_script(),
                "asset_strategy": "manual",
                "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
                "options": {
                    "aspect_ratio": "9:16",
                    "subtitle_enabled": False,
                    "bgm_enabled": True,
                    "bgm_track_id": bgm["track"]["id"],
                    "bgm_volume": 0.2,
                },
            },
        )
        task = response.json()

    assert response.status_code == 201
    manifest = json.loads(
        (tmp_path / "outputs" / task["id"] / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    for payload in [task["options"], manifest]:
        assert payload["bgm_enabled"] is True
        assert payload["bgm_track_id"] == bgm["track"]["id"]
        assert payload["bgm_display_name"] == "calm"
        assert payload["bgm_category_id"] == bgm["category"]["id"]
        assert payload["bgm_category_name"] == "舒缓"
        assert payload["bgm_volume"] == 0.2
        assert payload["bgm_snapshot"]["id"] == bgm["track"]["id"]
        assert payload["bgm_snapshot"]["duration_seconds"] == 8.5
        assert payload["bgm_mix_status"] == "selected_not_mixed"


def test_online_mix_resolves_category_only_bgm_to_track_snapshot(tmp_path):
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path=_write_fake_ffmpeg(tmp_path),
        )
    )
    app.state.bgm_audio_probe = lambda path: AudioProbeResult(
        duration_seconds=5.0,
        media_type="audio/mpeg",
    )

    with TestClient(app) as client:
        material = client.post(
            "/api/materials",
            files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
        ).json()
        bgm = _create_bgm_track(client, name="category-first.mp3")
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "分类 BGM 任务",
                "script": _single_shot_script(),
                "asset_strategy": "manual",
                "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
                "options": {
                    "aspect_ratio": "9:16",
                    "subtitle_enabled": False,
                    "bgm_enabled": True,
                    "bgm_category_id": bgm["category"]["id"],
                },
            },
        )

    assert response.status_code == 201
    payload = response.json()["options"]
    assert payload["bgm_track_id"] == bgm["track"]["id"]
    assert payload["bgm_snapshot"]["id"] == bgm["track"]["id"]
    assert payload["bgm_mix_status"] == "selected_not_mixed"


def test_online_mix_rejects_empty_bgm_category(tmp_path):
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path=_write_fake_ffmpeg(tmp_path),
        )
    )

    with TestClient(app) as client:
        material = client.post(
            "/api/materials",
            files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
        ).json()
        category = client.post("/api/bgm/categories", json={"name": "空分类"}).json()
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "空 BGM 分类任务",
                "script": _single_shot_script(),
                "asset_strategy": "manual",
                "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
                "options": {
                    "aspect_ratio": "9:16",
                    "subtitle_enabled": False,
                    "bgm_enabled": True,
                    "bgm_category_id": category["id"],
                },
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "BGM_CATEGORY_EMPTY"


def test_online_mix_defaults_disabled_bgm_options_to_null(tmp_path):
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path=_write_fake_ffmpeg(tmp_path),
        )
    )

    with TestClient(app) as client:
        material = client.post(
            "/api/materials",
            files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
        ).json()
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "无 BGM 任务",
                "script": _single_shot_script(),
                "asset_strategy": "manual",
                "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
                "options": {"aspect_ratio": "9:16", "subtitle_enabled": False},
            },
        )
        task = response.json()

    assert response.status_code == 201
    manifest = json.loads(
        (tmp_path / "outputs" / task["id"] / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    for payload in [task["options"], manifest]:
        assert payload["bgm_enabled"] is False
        assert payload["bgm_track_id"] is None
        assert payload["bgm_category_id"] is None
        assert payload["bgm_volume"] is None
        assert payload["bgm_snapshot"] is None
        assert payload["bgm_mix_status"] == "not_requested"
```

Also add this import near the top of `tests/api/test_online_mix.py`:

```python
from autovideo.services.bgm import AudioProbeResult
```

- [ ] **Step 2: 运行混剪 BGM 测试确认失败**

Run:

```bash
pytest tests/api/test_online_mix.py -q -k "bgm"
```

Expected before implementation:

```text
FAILED tests/api/test_online_mix.py::test_online_mix_defaults_disabled_bgm_options_to_null
KeyError: 'bgm_enabled'
```

or:

```text
FAILED tests/api/test_online_mix.py::test_online_mix_rejects_empty_bgm_category
assert response.status_code == 400
```

- [ ] **Step 3: 实现 `normalize_bgm_options`**

Modify `autovideo/services/online_mix.py`:

```python
from autovideo.services.bgm import (
    BgmCategoryEmptyError,
    BgmCategoryNotFoundError,
    BgmLibraryService,
    BgmTrackNotFoundError,
)
```

Add these classes next to existing online mix exceptions:

```python
class BgmOptionInvalidError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
```

Add this function after `normalize_voice_options`:

```python
def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_bgm_options(
    store: AutoVideoStore,
    options: dict[str, Any],
) -> dict[str, Any]:
    bgm_enabled = bool(options.get("bgm_enabled", False))
    if not bgm_enabled:
        return {
            "bgm_enabled": False,
            "bgm_track_id": None,
            "bgm_display_name": None,
            "bgm_category_id": None,
            "bgm_category_name": None,
            "bgm_volume": None,
            "bgm_snapshot": None,
            "bgm_mix_status": "not_requested",
        }

    service = BgmLibraryService(store.settings)
    track_id = _optional_text(options.get("bgm_track_id"))
    category_id = _optional_text(options.get("bgm_category_id"))
    try:
        if track_id:
            track = service.get_track(track_id)
        elif category_id:
            track = service.select_track_for_category(category_id)
        else:
            return {
                "bgm_enabled": False,
                "bgm_track_id": None,
                "bgm_display_name": None,
                "bgm_category_id": None,
                "bgm_category_name": None,
                "bgm_volume": None,
                "bgm_snapshot": None,
                "bgm_mix_status": "not_requested",
            }
    except BgmTrackNotFoundError as exc:
        raise BgmOptionInvalidError("BGM_TRACK_NOT_FOUND") from exc
    except BgmCategoryNotFoundError as exc:
        raise BgmOptionInvalidError("BGM_CATEGORY_NOT_FOUND") from exc
    except BgmCategoryEmptyError as exc:
        raise BgmOptionInvalidError("BGM_CATEGORY_EMPTY") from exc

    raw_volume = _optional_float(options.get("bgm_volume"))
    volume = 0.12 if raw_volume is None else min(1.0, max(0.0, raw_volume))
    return {
        "bgm_enabled": True,
        "bgm_track_id": track["id"],
        "bgm_display_name": track["display_name"],
        "bgm_category_id": track["category_id"],
        "bgm_category_name": track["category_name"],
        "bgm_volume": volume,
        "bgm_snapshot": service.track_snapshot(track["id"]),
        "bgm_mix_status": "selected_not_mixed",
    }
```

- [ ] **Step 4: 写入 task options 和 manifest**

Modify `create_online_mix_task()` in `autovideo/services/online_mix.py`:

```python
    subtitle_options = normalize_subtitle_options(store, options)
    voice_options = normalize_voice_options(options)
    bgm_options = normalize_bgm_options(store, options)
```

Then include BGM in sanitized options:

```python
    sanitized_options = sanitized_online_mix_options(
        {**options, **subtitle_options, **voice_options, **bgm_options}
    )
```

Then add these keys to `manifest_payload`:

```python
            "bgm_enabled": bgm_options["bgm_enabled"],
            "bgm_track_id": bgm_options["bgm_track_id"],
            "bgm_display_name": bgm_options["bgm_display_name"],
            "bgm_category_id": bgm_options["bgm_category_id"],
            "bgm_category_name": bgm_options["bgm_category_name"],
            "bgm_volume": bgm_options["bgm_volume"],
            "bgm_snapshot": bgm_options["bgm_snapshot"],
            "bgm_mix_status": bgm_options["bgm_mix_status"],
```

- [ ] **Step 5: 映射 BGM option 错误**

Modify `autovideo/api/routes/online_mix.py` imports:

```python
    BgmOptionInvalidError,
```

Add this except block in `create_online_mix_video_task()` around the `create_online_mix_task()` call:

```python
    except BgmOptionInvalidError as exc:
        code = exc.code
        status_code = (
            status.HTTP_404_NOT_FOUND
            if code in {"BGM_TRACK_NOT_FOUND", "BGM_CATEGORY_NOT_FOUND"}
            else status.HTTP_400_BAD_REQUEST
        )
        raise structured_error(status_code, code) from exc
```

- [ ] **Step 6: 运行混剪 BGM 测试确认通过**

Run:

```bash
pytest tests/api/test_online_mix.py -q -k "bgm"
```

Expected:

```text
4 passed
```

- [ ] **Step 7: 运行相关 API 测试**

Run:

```bash
pytest tests/api/test_bgm.py tests/api/test_online_mix.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8: 提交 Task 3**

Run:

```bash
git add tests/api/test_online_mix.py autovideo/services/online_mix.py autovideo/api/routes/online_mix.py
git commit -m "feat: persist bgm options in remix tasks"
```

---

### Task 4: Frontend BGM API And Management Workbench

**Files:**
- Create: `frontend/src/api/bgm.ts`
- Create: `frontend/src/components/BgmManagementWorkbench.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `tests/web/test_frontend_build.py`

- [ ] **Step 1: 扩展前端 mock 并写失败测试**

In `frontend/src/App.test.tsx`, add imports near the existing API imports:

```tsx
import {
  createBgmCategory,
  deleteBgmCategory,
  deleteBgmTrack,
  fetchBgmLibrary,
  updateBgmCategory,
  updateBgmTrack,
  uploadBgmTrack,
} from "./api/bgm";
import type { BgmLibrary } from "./api/bgm";
```

Add the mock for `./api/bgm` near existing API mocks. Keep the factory self-contained so Vitest hoisting cannot close over external fixture constants:

```tsx
vi.mock("./api/bgm", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api/bgm")>();
  return {
    ...actual,
    fetchBgmLibrary: vi.fn(),
    uploadBgmTrack: vi.fn(),
    updateBgmTrack: vi.fn(),
    deleteBgmTrack: vi.fn(),
    createBgmCategory: vi.fn(),
    updateBgmCategory: vi.fn(),
    deleteBgmCategory: vi.fn(),
  };
});
```

Add typed mocked helpers after the existing `vi.mocked(...)` declarations:

```tsx
const mockedFetchBgmLibrary = vi.mocked(fetchBgmLibrary);
const mockedUploadBgmTrack = vi.mocked(uploadBgmTrack);
const mockedUpdateBgmTrack = vi.mocked(updateBgmTrack);
const mockedDeleteBgmTrack = vi.mocked(deleteBgmTrack);
const mockedCreateBgmCategory = vi.mocked(createBgmCategory);
const mockedUpdateBgmCategory = vi.mocked(updateBgmCategory);
const mockedDeleteBgmCategory = vi.mocked(deleteBgmCategory);
```

Add this fixture helper near the existing fixture helpers:

```tsx
function bgmLibraryFixture(): BgmLibrary {
  return {
  items: [
    {
      id: "bgm_calm_late",
      filename: "bgm_calm_late.mp3",
      original_filename: "late-calm.mp3",
      display_name: "静谧长夜",
      category_id: "cat_calm",
      category_name: "舒缓",
      media_type: "audio/mpeg",
      extension: "mp3",
      size_bytes: 1536,
      duration_seconds: 15,
      audio_url: "/api/bgm/tracks/bgm_calm_late/file",
      created_at: "2026-06-21T00:00:00Z",
      updated_at: "2026-06-21T00:00:00Z",
    },
    {
      id: "bgm_calm",
      filename: "bgm_calm.mp3",
      original_filename: "calm.mp3",
      display_name: "舒缓钢琴",
      category_id: "cat_calm",
      category_name: "舒缓",
      media_type: "audio/mpeg",
      extension: "mp3",
      size_bytes: 1024,
      duration_seconds: 12.5,
      audio_url: "/api/bgm/tracks/bgm_calm/file",
      created_at: "2026-06-21T00:00:00Z",
      updated_at: "2026-06-21T00:00:00Z",
    },
    {
      id: "bgm_upbeat",
      filename: "bgm_upbeat.mp3",
      original_filename: "upbeat.mp3",
      display_name: "轻快鼓点",
      category_id: "cat_upbeat",
      category_name: "欢快",
      media_type: "audio/mpeg",
      extension: "mp3",
      size_bytes: 2048,
      duration_seconds: 10,
      audio_url: "/api/bgm/tracks/bgm_upbeat/file",
      created_at: "2026-06-21T00:00:00Z",
      updated_at: "2026-06-21T00:00:00Z",
    },
  ],
  categories: [
    {
      id: "cat_calm",
      name: "舒缓",
      sort_order: 10,
      track_count: 2,
      created_at: "2026-06-21T00:00:00Z",
      updated_at: "2026-06-21T00:00:00Z",
    },
    {
      id: "cat_upbeat",
      name: "欢快",
      sort_order: 20,
      track_count: 1,
      created_at: "2026-06-21T00:00:00Z",
      updated_at: "2026-06-21T00:00:00Z",
    },
  ],
  storage_status: "ready",
  total_tracks: 3,
  supported_extensions: ["mp3", "wav", "m4a", "aac", "ogg", "flac"],
  };
}
```

Inside the existing `beforeEach`, after current API mock defaults are set, add:

```tsx
const bgmLibrary = bgmLibraryFixture();
mockedFetchBgmLibrary.mockResolvedValue(bgmLibrary);
mockedUploadBgmTrack.mockImplementation(async ({ file, category_id }) => ({
  ...bgmLibrary.items[0],
  original_filename: file.name,
  display_name: file.name.replace(/\.[^.]+$/, ""),
  category_id: category_id ?? null,
  category_name: category_id ? "舒缓" : "未分类",
}));
mockedUpdateBgmTrack.mockResolvedValue(bgmLibrary.items[0]);
mockedDeleteBgmTrack.mockResolvedValue({ id: "bgm_calm", deleted: true });
mockedCreateBgmCategory.mockResolvedValue(bgmLibrary.categories[0]);
mockedUpdateBgmCategory.mockResolvedValue(bgmLibrary.categories[0]);
mockedDeleteBgmCategory.mockResolvedValue({ id: "cat_calm", deleted: true });
```

Add tests:

```tsx
it("opens BGM management from navigation and renders library controls", async () => {
  renderApp();

  await userEvent.click(screen.getByRole("link", { name: "BGM 管理" }));

  expect(window.location.hash).toBe("#bgm");
  expect(await screen.findByRole("article", { name: "BGM 管理" })).toBeInTheDocument();
  expect(screen.getByLabelText("BGM 音频文件")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "上传 BGM" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "新增分类" })).toBeInTheDocument();
  expect(screen.getByText("舒缓钢琴")).toBeInTheDocument();
  expect(screen.getByLabelText("试听 舒缓钢琴")).toHaveAttribute(
    "src",
    "/api/bgm/tracks/bgm_calm/file",
  );
});

it("clears the BGM file input after a successful upload", async () => {
  renderApp();

  await userEvent.click(screen.getByRole("link", { name: "BGM 管理" }));
  const fileInput = (await screen.findByLabelText("BGM 音频文件")) as HTMLInputElement;
  const file = new File(["fake audio bytes"], "new-track.mp3", { type: "audio/mpeg" });

  await userEvent.upload(fileInput, file);
  expect(fileInput.files?.[0]).toBe(file);
  await userEvent.click(screen.getByRole("button", { name: "上传 BGM" }));

  await waitFor(() =>
    expect(mockedUploadBgmTrack).toHaveBeenCalledWith({
      file,
      category_id: null,
    }),
  );
  await waitFor(() => expect(fileInput.value).toBe(""));
  expect(fileInput.files).toHaveLength(0);
});

it("keeps enabled mobile navigation entries including BGM before future disabled entries", async () => {
  renderApp();

  const mobileNav = screen.getByRole("navigation", { name: "移动端导航" });
  const labels = Array.from(mobileNav.querySelectorAll("a, span")).map((item) =>
    item.textContent?.trim(),
  );

  expect(labels.slice(0, 5)).toEqual(["混剪", "字幕", "BGM", "音色", "任务"]);
});

it("declares responsive BGM workbench styles without hover-only dependencies", () => {
  expect(stylesCss).toMatch(/\.bgm-workbench-grid \{[\s\S]*?grid-template-columns:/);
  expect(stylesCss).toMatch(
    /@media \(max-width: 760px\) \{[\s\S]*?\.bgm-workbench-grid \{[\s\S]*?grid-template-columns: 1fr;/,
  );
  expect(stylesCss).toMatch(
    /\.bgm-management-panel input,\s*\.bgm-management-panel select,\s*\.bgm-management-panel button \{[\s\S]*?min-height:\s*44px;/,
  );
  expect(stylesCss).toMatch(
    /\.bgm-audio-player \{[\s\S]*?width:\s*100%;[\s\S]*?max-width:\s*100%;/,
  );
  expect(stylesCss).not.toMatch(/\.bgm-management-panel[^{,]*:hover/);
});
```

- [ ] **Step 2: 运行前端测试确认失败**

Run:

```bash
cd frontend && npm test -- src/App.test.tsx
```

Expected before implementation:

```text
FAIL src/App.test.tsx > opens BGM management from navigation and renders library controls
TestingLibraryElementError: Unable to find role="link" and name "BGM 管理"
```

- [ ] **Step 3: 实现 BGM API client**

Create `frontend/src/api/bgm.ts`:

```ts
export interface BgmCategory {
  id: string;
  name: string;
  sort_order: number;
  track_count: number;
  created_at: string;
  updated_at: string;
}

export interface BgmTrack {
  id: string;
  filename: string;
  original_filename: string;
  display_name: string;
  category_id: string | null;
  category_name: string;
  media_type: string;
  extension: string;
  size_bytes: number;
  duration_seconds: number;
  audio_url: string;
  created_at: string;
  updated_at: string;
}

export interface BgmLibrary {
  items: BgmTrack[];
  categories: BgmCategory[];
  storage_status: "ready";
  total_tracks: number;
  supported_extensions: string[];
}

export class BgmApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly detail: Record<string, unknown>;

  constructor(code: string, status: number, detail: Record<string, unknown> = {}) {
    super(code);
    this.name = "BgmApiError";
    this.code = code;
    this.status = status;
    this.detail = detail;
  }
}

function responseErrorCode(payload: unknown, status: number): string {
  if (
    typeof payload === "object" &&
    payload !== null &&
    "detail" in payload &&
    typeof payload.detail === "object" &&
    payload.detail !== null &&
    "code" in payload.detail &&
    typeof payload.detail.code === "string"
  ) {
    return payload.detail.code;
  }
  return `HTTP_${status}`;
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const detail =
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof payload.detail === "object" &&
      payload.detail !== null
        ? (payload.detail as Record<string, unknown>)
        : {};
    throw new BgmApiError(responseErrorCode(payload, response.status), response.status, detail);
  }
  return response.json() as Promise<T>;
}

export function readableBgmError(error: unknown): string {
  if (error instanceof BgmApiError) {
    if (error.code === "BGM_FILE_UNSUPPORTED") return "不支持的音频格式或文件中没有音频流";
    if (error.code === "BGM_FILE_EMPTY") return "上传的 BGM 文件为空";
    if (error.code === "BGM_CATEGORY_DUPLICATE") return "分类名已存在";
    if (error.code === "BGM_CATEGORY_NAME_REQUIRED") return "请输入分类名";
    if (error.code === "BGM_TRACK_NAME_REQUIRED") return "请输入 BGM 名称";
    if (error.code === "BGM_FILE_TOO_LARGE") return "BGM 文件超过上传大小限制";
    if (error.code === "REQUEST_TOO_LARGE") return "BGM 文件超过上传大小限制";
  }
  return error instanceof Error ? error.message : "BGM 操作失败";
}

export async function fetchBgmLibrary(): Promise<BgmLibrary> {
  return readJson(await fetch("/api/bgm"));
}

export async function uploadBgmTrack(input: {
  file: File;
  category_id?: string | null;
}): Promise<BgmTrack> {
  const formData = new FormData();
  formData.append("file", input.file);
  if (input.category_id) formData.append("category_id", input.category_id);
  return readJson(await fetch("/api/bgm/tracks", { method: "POST", body: formData }));
}

export async function updateBgmTrack(input: {
  id: string;
  display_name: string;
  category_id?: string | null;
}): Promise<BgmTrack> {
  return readJson(
    await fetch(`/api/bgm/tracks/${encodeURIComponent(input.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        display_name: input.display_name,
        category_id: input.category_id ?? null,
      }),
    }),
  );
}

export async function deleteBgmTrack(trackId: string): Promise<{ id: string; deleted: boolean }> {
  return readJson(
    await fetch(`/api/bgm/tracks/${encodeURIComponent(trackId)}`, { method: "DELETE" }),
  );
}

export async function createBgmCategory(input: { name: string }): Promise<BgmCategory> {
  return readJson(
    await fetch("/api/bgm/categories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}

export async function updateBgmCategory(input: {
  id: string;
  name: string;
}): Promise<BgmCategory> {
  return readJson(
    await fetch(`/api/bgm/categories/${encodeURIComponent(input.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: input.name }),
    }),
  );
}

export async function deleteBgmCategory(
  categoryId: string,
): Promise<{ id: string; deleted: boolean }> {
  return readJson(
    await fetch(`/api/bgm/categories/${encodeURIComponent(categoryId)}`, { method: "DELETE" }),
  );
}
```

- [ ] **Step 4: 实现 BGM 管理工作台**

Create `frontend/src/components/BgmManagementWorkbench.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Save, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";

import {
  createBgmCategory,
  deleteBgmCategory,
  deleteBgmTrack,
  fetchBgmLibrary,
  readableBgmError,
  updateBgmCategory,
  updateBgmTrack,
  uploadBgmTrack,
} from "../api/bgm";

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDuration(seconds: number): string {
  const rounded = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(rounded / 60);
  const rest = rounded % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

export function BgmManagementWorkbench() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadCategoryId, setUploadCategoryId] = useState("");
  const [newCategoryName, setNewCategoryName] = useState("");

  const library = useQuery({ queryKey: ["bgm-library"], queryFn: fetchBgmLibrary });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["bgm-library"] });

  const upload = useMutation({
    mutationFn: () => {
      if (!selectedFile) throw new Error("请选择 BGM 文件");
      return uploadBgmTrack({ file: selectedFile, category_id: uploadCategoryId || null });
    },
    onSuccess: () => {
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      void invalidate();
    },
  });
  const createCategory = useMutation({
    mutationFn: () => createBgmCategory({ name: newCategoryName }),
    onSuccess: () => {
      setNewCategoryName("");
      void invalidate();
    },
  });
  const saveTrack = useMutation({ mutationFn: updateBgmTrack, onSuccess: invalidate });
  const removeTrack = useMutation({ mutationFn: deleteBgmTrack, onSuccess: invalidate });
  const saveCategory = useMutation({ mutationFn: updateBgmCategory, onSuccess: invalidate });
  const removeCategory = useMutation({ mutationFn: deleteBgmCategory, onSuccess: invalidate });

  const categories = library.data?.categories ?? [];
  const tracks = library.data?.items ?? [];
  const actionError =
    upload.error ||
    createCategory.error ||
    saveTrack.error ||
    removeTrack.error ||
    saveCategory.error ||
    removeCategory.error ||
    null;

  return (
    <article className="panel bgm-management-panel" aria-label="BGM 管理">
      <div className="panel-heading">
        <div>
          <h2>BGM 管理</h2>
          <span>
            {library.data
              ? `共 ${library.data.total_tracks} 条 BGM，支持 ${library.data.supported_extensions.join(", ")}`
              : "读取 BGM 列表"}
          </span>
        </div>
        <button type="button" onClick={() => void library.refetch()}>
          <RefreshCw aria-hidden="true" size={18} />
          刷新
        </button>
      </div>

      {library.isLoading ? (
        <div className="runtime-status" role="status" aria-live="polite">
          正在读取 BGM 列表
        </div>
      ) : null}
      {library.isError ? (
        <div className="inline-error" role="alert">
          <span>{readableBgmError(library.error)}</span>
          <button type="button" onClick={() => void library.refetch()}>重试</button>
        </div>
      ) : null}
      {actionError ? (
        <div className="inline-error" role="alert">
          {readableBgmError(actionError)}
        </div>
      ) : null}

      <div className="bgm-workbench-grid">
        <section className="bgm-upload-panel" aria-label="上传 BGM">
          <h3>上传 BGM</h3>
          <label>
            BGM 音频文件
            <input
              ref={fileInputRef}
              accept=".mp3,.wav,.m4a,.aac,.ogg,.flac,audio/*"
              aria-label="BGM 音频文件"
              type="file"
              onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <label>
            上传分类
            <select value={uploadCategoryId} onChange={(event) => setUploadCategoryId(event.target.value)}>
              <option value="">未分类</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>{category.name}</option>
              ))}
            </select>
          </label>
          <button
            className="primary-action"
            disabled={!selectedFile || upload.isPending}
            type="button"
            onClick={() => upload.mutate()}
          >
            <Upload aria-hidden="true" size={18} />
            {upload.isPending ? "上传中" : "上传 BGM"}
          </button>
        </section>

        <section className="bgm-category-panel" aria-label="BGM 分类">
          <h3>BGM 分类</h3>
          <div className="bgm-inline-form">
            <label>
              新分类名
              <input value={newCategoryName} onChange={(event) => setNewCategoryName(event.target.value)} />
            </label>
            <button disabled={!newCategoryName.trim()} type="button" onClick={() => createCategory.mutate()}>
              新增分类
            </button>
          </div>
          {categories.length === 0 ? <div className="empty-state">还没有分类</div> : null}
          {categories.map((category) => (
            <div className="bgm-category-row" key={category.id}>
              <input
                aria-label={`${category.name} 分类名`}
                defaultValue={category.name}
                onBlur={(event) => {
                  const name = event.currentTarget.value.trim();
                  if (name && name !== category.name) saveCategory.mutate({ id: category.id, name });
                }}
              />
              <span>{category.track_count} 条</span>
              <button
                aria-label={`删除分类 ${category.name}`}
                type="button"
                onClick={() => {
                  if (window.confirm("确定删除这个 BGM 分类吗？分类下的 BGM 会移动到未分类。")) {
                    removeCategory.mutate(category.id);
                  }
                }}
              >
                <Trash2 aria-hidden="true" size={18} />
                删除
              </button>
            </div>
          ))}
        </section>

        <section className="bgm-list-panel" aria-label="BGM 列表">
          <h3>BGM 列表</h3>
          {tracks.length === 0 ? (
            <div className="empty-state">还没有 BGM，先上传一条背景音乐。</div>
          ) : null}
          {tracks.map((track) => (
            <article className="bgm-track-row" key={track.id}>
              <div className="bgm-track-main">
                <strong>{track.display_name}</strong>
                <span>{track.original_filename} · {formatBytes(track.size_bytes)} · {formatDuration(track.duration_seconds)}</span>
                <span>{track.category_name}</span>
              </div>
              <audio
                aria-label={`试听 ${track.display_name}`}
                className="bgm-audio-player"
                controls
                preload="none"
                src={track.audio_url}
              />
              <label>
                BGM 名称
                <input
                  defaultValue={track.display_name}
                  onBlur={(event) => {
                    const displayName = event.currentTarget.value.trim();
                    if (displayName && displayName !== track.display_name) {
                      saveTrack.mutate({
                        id: track.id,
                        display_name: displayName,
                        category_id: track.category_id,
                      });
                    }
                  }}
                />
              </label>
              <label>
                分类
                <select
                  value={track.category_id ?? ""}
                  onChange={(event) =>
                    saveTrack.mutate({
                      id: track.id,
                      display_name: track.display_name,
                      category_id: event.target.value || null,
                    })
                  }
                >
                  <option value="">未分类</option>
                  {categories.map((category) => (
                    <option key={category.id} value={category.id}>{category.name}</option>
                  ))}
                </select>
              </label>
              <button
                aria-label={`删除 BGM ${track.display_name}`}
                type="button"
                onClick={() => {
                  if (window.confirm(`确定删除 BGM “${track.display_name}”吗？`)) {
                    removeTrack.mutate(track.id);
                  }
                }}
              >
                <Trash2 aria-hidden="true" size={18} />
                删除
              </button>
            </article>
          ))}
        </section>
      </div>
    </article>
  );
}
```

- [ ] **Step 5: 启用 BGM 导航**

Modify `frontend/src/App.tsx`:

```tsx
import { BgmManagementWorkbench } from "./components/BgmManagementWorkbench";
```

Update types:

```tsx
type ActiveSection = "remix" | "subtitles" | "bgm" | "voices" | "tasks";
```

Enable BGM nav:

```tsx
  { id: "bgm", label: "BGM 管理", shortLabel: "BGM", icon: Music, enabled: true },
```

Add heading:

```tsx
  bgm: {
    title: "BGM 管理",
    summary: "上传、分类、试听与选择背景音乐",
  },
```

Update hash parser:

```tsx
  if (hashId === "subtitles" || hashId === "bgm" || hashId === "voices" || hashId === "tasks") {
    return hashId;
  }
```

Update opened sections initial state:

```tsx
      bgm: initialSection === "bgm",
```

Add BGM section before voices:

```tsx
        {openedSections.bgm ? (
          <section
            className="content-grid single-column"
            hidden={activeSection !== "bgm"}
            id="bgm"
          >
            <BgmManagementWorkbench />
          </section>
        ) : null}
```

- [ ] **Step 6: 添加 BGM styles**

Append to `frontend/src/styles.css`:

```css
.bgm-management-panel {
  display: grid;
  gap: 20px;
}

.bgm-workbench-grid {
  display: grid;
  grid-template-columns: minmax(240px, 0.8fr) minmax(260px, 1fr) minmax(360px, 1.4fr);
  gap: 16px;
  align-items: start;
}

.bgm-upload-panel,
.bgm-category-panel,
.bgm-list-panel {
  display: grid;
  gap: 14px;
  min-width: 0;
}

.bgm-management-panel input,
.bgm-management-panel select,
.bgm-management-panel button {
  min-height: 44px;
}

.bgm-inline-form,
.bgm-category-row,
.bgm-track-row {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.bgm-category-row {
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
}

.bgm-track-row {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 14px;
  background: var(--panel-muted, rgba(255, 255, 255, 0.04));
}

.bgm-track-main {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.bgm-track-main span {
  color: var(--text-muted);
  overflow-wrap: anywhere;
}

.bgm-audio-player {
  width: 100%;
  max-width: 100%;
}

@media (max-width: 1160px) {
  .bgm-workbench-grid {
    grid-template-columns: 1fr 1fr;
  }

  .bgm-list-panel {
    grid-column: 1 / -1;
  }
}

@media (max-width: 760px) {
  .bgm-workbench-grid,
  .bgm-category-row {
    grid-template-columns: 1fr;
  }

  .bgm-track-row button,
  .bgm-track-row select,
  .bgm-track-row input {
    width: 100%;
  }
}
```

- [ ] **Step 7: 更新静态源测试**

Modify `tests/web/test_frontend_build.py`:

```python
def test_frontend_source_enables_bgm_navigation() -> None:
    app_source = (FRONTEND_ROOT / "src" / "App.tsx").read_text(encoding="utf-8")

    assert '{ id: "bgm", label: "BGM 管理", shortLabel: "BGM", icon: Music, enabled: true }' in app_source
    assert "BgmManagementWorkbench" in app_source
```

- [ ] **Step 8: 运行前端测试确认通过**

Run:

```bash
cd frontend && npm test -- src/App.test.tsx
```

Expected:

```text
PASS src/App.test.tsx
```

- [ ] **Step 9: 运行前端静态测试**

Run:

```bash
pytest tests/web/test_frontend_build.py -q
```

Expected:

```text
passed
```

- [ ] **Step 10: 提交 Task 4**

Run:

```bash
git add frontend/src/api/bgm.ts frontend/src/components/BgmManagementWorkbench.tsx frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/styles.css tests/web/test_frontend_build.py
git commit -m "feat: add bgm management workbench"
```

---

### Task 5: BGM Selector In Remix Workbench

**Files:**
- Create: `frontend/src/components/BgmSelector.tsx`
- Modify: `frontend/src/components/OnlineRemixWorkbench.tsx`
- Modify: `frontend/src/api/onlineRemix.ts`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: 写 BGM 选择器失败测试**

Add tests to `frontend/src/App.test.tsx`:

```tsx
it("previews the sorted automatic BGM for category-only selection", async () => {
  renderApp();

  expect(await screen.findByRole("group", { name: "BGM 设置" })).toBeInTheDocument();
  expect(screen.getByLabelText("启用 BGM")).toBeChecked();
  await waitFor(() => expect(screen.getByLabelText("BGM 分类")).toHaveValue("cat_calm"));
  expect(screen.getByLabelText("具体 BGM")).toHaveValue("");
  expect(screen.getByRole("option", { name: "从当前分类自动选择" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "静谧长夜" })).toBeInTheDocument();
  expect(screen.getByLabelText("BGM 试听音频")).toHaveAttribute(
    "src",
    "/api/bgm/tracks/bgm_calm/file",
  );
});

it("keeps category-only automatic BGM selection scoped to the current category", async () => {
  renderApp();

  const group = await screen.findByRole("group", { name: "BGM 设置" });
  const categorySelect = within(group).getByLabelText("BGM 分类");
  const trackSelect = within(group).getByLabelText("具体 BGM");

  await waitFor(() => expect(categorySelect).toHaveValue("cat_calm"));
  expect(trackSelect).toHaveValue("");

  await userEvent.selectOptions(categorySelect, "cat_upbeat");

  expect(trackSelect).toHaveValue("");
  expect(within(group).getByLabelText("BGM 试听音频")).toHaveAttribute(
    "src",
    "/api/bgm/tracks/bgm_upbeat/file",
  );
});

it("sends category-only BGM when creating an online remix task", async () => {
  renderApp();

  await userEvent.type(screen.getByLabelText("视频主题"), "睡前放松");
  await userEvent.click(screen.getByRole("button", { name: "生成脚本" }));
  await screen.findByText("镜头 1");
  await waitFor(() => expect(screen.getByLabelText("BGM 分类")).toHaveValue("cat_calm"));
  expect(screen.getByLabelText("具体 BGM")).toHaveValue("");
  expect(screen.getByLabelText("BGM 试听音频")).toHaveAttribute(
    "src",
    "/api/bgm/tracks/bgm_calm/file",
  );
  await userEvent.click(screen.getByRole("button", { name: "创建任务" }));

  expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
    expect.objectContaining({
      options: expect.objectContaining({
        bgm_enabled: true,
        bgm_category_id: "cat_calm",
        bgm_track_id: null,
        bgm_volume: 0.12,
      }),
    }),
  );
});

it("keeps BGM selector mobile controls touch friendly", () => {
  expect(stylesCss).toMatch(/\.bgm-selector \{[\s\S]*?display:\s*grid;/);
  expect(stylesCss).toMatch(
    /\.bgm-selector input,\s*\.bgm-selector select,\s*\.bgm-selector button \{[\s\S]*?min-height:\s*44px;/,
  );
  expect(stylesCss).toMatch(/\.bgm-selector-audio \{[\s\S]*?width:\s*100%;[\s\S]*?max-width:\s*100%;/);
});
```

- [ ] **Step 2: 运行相关前端测试确认失败**

Run:

```bash
cd frontend && npm test -- src/App.test.tsx -t "BGM"
```

Expected before implementation:

```text
FAIL src/App.test.tsx > previews the sorted automatic BGM for category-only selection
TestingLibraryElementError: Unable to find role="group" and name "BGM 设置"
```

- [ ] **Step 3: 扩展 online remix input 类型**

Modify `frontend/src/api/onlineRemix.ts`:

```ts
    bgm_enabled?: boolean;
    bgm_track_id?: string | null;
    bgm_category_id?: string | null;
    bgm_volume?: number | null;
```

- [ ] **Step 4: 实现 `BgmSelector`**

Create `frontend/src/components/BgmSelector.tsx`:

Category-only behavior is intentional: when `trackId` is an empty string and `categoryId` is set, the UI shows `从当前分类自动选择`, previews the first track in that category after applying the same automatic-selection sort rule as the backend (`display_name || filename`, ascending), and submits `bgm_track_id: null` so the backend resolves a fresh category snapshot at task creation time.

```tsx
import { useQuery } from "@tanstack/react-query";
import { Music, RefreshCw } from "lucide-react";
import { useEffect, useMemo } from "react";

import { BgmTrack, fetchBgmLibrary, readableBgmError } from "../api/bgm";

interface BgmSelectorValue {
  enabled: boolean;
  categoryId: string;
  trackId: string;
  volume: number;
}

interface BgmSelectorProps {
  value: BgmSelectorValue;
  onChange: (value: BgmSelectorValue) => void;
  onOpenBgmManagement?: () => void;
}

export type { BgmSelectorValue };

function sortTracksForAutomaticBgm(items: BgmTrack[]): BgmTrack[] {
  return [...items].sort((left, right) => {
    const leftKey = left.display_name || left.filename || "";
    const rightKey = right.display_name || right.filename || "";
    if (leftKey < rightKey) return -1;
    if (leftKey > rightKey) return 1;
    return 0;
  });
}

export function BgmSelector({ value, onChange, onOpenBgmManagement }: BgmSelectorProps) {
  const library = useQuery({ queryKey: ["bgm-library"], queryFn: fetchBgmLibrary });
  const categories = library.data?.categories ?? [];
  const tracks = library.data?.items ?? [];
  const firstCategoryWithTracks = useMemo(
    () =>
      categories.find((category) =>
        tracks.some((track) => track.category_id === category.id),
      ) ??
      categories[0] ??
      null,
    [categories, tracks],
  );
  const filteredTracks = useMemo(
    () => sortTracksForAutomaticBgm(
      value.categoryId
        ? tracks.filter((track) => track.category_id === value.categoryId)
        : tracks,
    ),
    [tracks, value.categoryId],
  );
  const explicitTrack = value.trackId
    ? filteredTracks.find((track) => track.id === value.trackId) ?? null
    : null;
  const selectedTrack = explicitTrack ?? filteredTracks[0] ?? null;

  useEffect(() => {
    if (!value.categoryId && !value.trackId && firstCategoryWithTracks) {
      onChange({ ...value, categoryId: firstCategoryWithTracks.id, trackId: "" });
    }
  }, [firstCategoryWithTracks, onChange, value]);

  const selectedTrackId = explicitTrack?.id ?? "";

  return (
    <fieldset className="bgm-selector" aria-label="BGM 设置">
      <legend>BGM 设置</legend>
      <label className="switch-row">
        <input
          aria-label="启用 BGM"
          checked={value.enabled}
          type="checkbox"
          onChange={(event) => onChange({ ...value, enabled: event.target.checked })}
        />
        <span>启用 BGM</span>
      </label>

      {library.isLoading ? (
        <div className="runtime-status" role="status" aria-live="polite">正在读取 BGM</div>
      ) : null}
      {library.isError ? (
        <div className="inline-error" role="alert">
          <span>{readableBgmError(library.error)}</span>
          <button type="button" onClick={() => void library.refetch()}>
            <RefreshCw aria-hidden="true" size={16} />
            重试
          </button>
        </div>
      ) : null}

      <label>
        BGM 分类
        <select
          aria-label="BGM 分类"
          disabled={!value.enabled}
          value={value.categoryId}
          onChange={(event) => onChange({ ...value, categoryId: event.target.value, trackId: "" })}
        >
          <option value="">全部分类</option>
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}（{category.track_count}）
            </option>
          ))}
        </select>
      </label>

      <label>
        具体 BGM
        <select
          aria-label="具体 BGM"
          disabled={!value.enabled || filteredTracks.length === 0}
          value={selectedTrackId}
          onChange={(event) => onChange({ ...value, trackId: event.target.value })}
        >
          {filteredTracks.length === 0 ? (
            <option value="">当前分类暂无 BGM</option>
          ) : (
            <option value="">从当前分类自动选择</option>
          )}
          {filteredTracks.map((track: BgmTrack) => (
            <option key={track.id} value={track.id}>
              {track.display_name}
            </option>
          ))}
        </select>
      </label>

      <label>
        BGM 音量 {Math.round(value.volume * 100)}%
        <input
          aria-label="BGM 音量"
          disabled={!value.enabled}
          max="1"
          min="0"
          step="0.01"
          type="range"
          value={value.volume}
          onChange={(event) => onChange({ ...value, volume: Number(event.target.value) })}
        />
      </label>

      {value.enabled && selectedTrack ? (
        <div className="bgm-selector-preview">
          <Music aria-hidden="true" size={18} />
          <span>{selectedTrack.display_name}</span>
          <audio
            aria-label="BGM 试听音频"
            className="bgm-selector-audio"
            controls
            preload="none"
            src={selectedTrack.audio_url}
          />
        </div>
      ) : null}

      <button type="button" onClick={onOpenBgmManagement}>
        去 BGM 管理页
      </button>
    </fieldset>
  );
}
```

- [ ] **Step 5: 接入 `OnlineRemixWorkbench`**

Modify imports in `frontend/src/components/OnlineRemixWorkbench.tsx`:

```tsx
import { BgmSelector } from "./BgmSelector";
import type { BgmSelectorValue } from "./BgmSelector";
```

Update props:

```tsx
interface OnlineRemixWorkbenchProps {
  onOpenSubtitleTemplates?: () => void;
  onOpenBgmManagement?: () => void;
}

export function OnlineRemixWorkbench({
  onOpenSubtitleTemplates,
  onOpenBgmManagement,
}: OnlineRemixWorkbenchProps) {
```

Add state:

```tsx
  const [selectedBgm, setSelectedBgm] = useState<BgmSelectorValue>({
    enabled: true,
    categoryId: "",
    trackId: "",
    volume: 0.12,
  });
```

Add options in `createOnlineMixTask`:

```tsx
          bgm_enabled: selectedBgm.enabled,
          bgm_category_id: selectedBgm.enabled ? selectedBgm.categoryId || null : null,
          bgm_track_id: selectedBgm.enabled ? selectedBgm.trackId || null : null,
          bgm_volume: selectedBgm.enabled ? selectedBgm.volume : null,
```

Render after `VoiceSelector`:

```tsx
        <BgmSelector
          value={selectedBgm}
          onChange={setSelectedBgm}
          onOpenBgmManagement={onOpenBgmManagement}
        />
```

- [ ] **Step 6: Wire App openSection to BGM management**

Modify `frontend/src/App.tsx` remix render:

```tsx
            <OnlineRemixWorkbench
              onOpenSubtitleTemplates={() => openSection("subtitles")}
              onOpenBgmManagement={() => openSection("bgm")}
            />
```

- [ ] **Step 7: 添加 BGM selector styles**

Append to `frontend/src/styles.css`:

```css
.bgm-selector {
  display: grid;
  gap: 12px;
  min-width: 0;
}

.bgm-selector input,
.bgm-selector select,
.bgm-selector button {
  min-height: 44px;
}

.bgm-selector-preview {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}

.bgm-selector-audio {
  grid-column: 1 / -1;
  width: 100%;
  max-width: 100%;
}

@media (max-width: 760px) {
  .bgm-selector-preview {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 8: 运行 BGM 前端测试确认通过**

Run:

```bash
cd frontend && npm test -- src/App.test.tsx -t "BGM"
```

Expected:

```text
PASS src/App.test.tsx
```

- [ ] **Step 9: 运行完整前端测试**

Run:

```bash
cd frontend && npm test -- src/App.test.tsx
```

Expected:

```text
PASS src/App.test.tsx
```

- [ ] **Step 10: 提交 Task 5**

Run:

```bash
git add frontend/src/components/BgmSelector.tsx frontend/src/components/OnlineRemixWorkbench.tsx frontend/src/api/onlineRemix.ts frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/styles.css
git commit -m "feat: add bgm selector to remix workbench"
```

---

### Task 6: README And Final Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 写 README 静态失败测试**

Add to `tests/web/test_frontend_build.py`:

```python
def test_readme_documents_bgm_management_without_claiming_audio_mix() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "BGM 管理已支持上传、分类、试听、重命名和删除" in readme
    assert "GET /api/bgm" in readme
    assert "POST /api/bgm/tracks" in readme
    assert "bgm_track_id" in readme
    assert "当前最终视频还未混入 BGM 音轨" in readme
```

- [ ] **Step 2: 运行 README 测试确认失败**

Run:

```bash
pytest tests/web/test_frontend_build.py -q -k "bgm_management"
```

Expected before implementation:

```text
FAILED tests/web/test_frontend_build.py::test_readme_documents_bgm_management_without_claiming_audio_mix
AssertionError
```

- [ ] **Step 3: 更新 README 功能状态**

Modify top feature list in `README.md` to include:

```markdown
- BGM 管理已支持上传、分类、试听、重命名和删除；混剪工作台会保存 BGM 曲目、分类和音量配置
```

Replace the old sentence that says BGM upload is not connected with:

```markdown
尚未接入登录、权限管理、个人网盘导入、Fish Speech 音色复刻和功能提取处理。当前最终视频还未混入 BGM 音轨，BGM 字段用于任务配置和后续混音。
```

- [ ] **Step 4: 更新 README API section**

Add API bullets near existing API list:

```markdown
- `GET /api/bgm`：返回 BGM 曲目、分类、存储状态、总数和支持格式，不返回本机数据目录路径。
- `POST /api/bgm/tracks`：上传 BGM 音频文件，支持 `mp3`、`wav`、`m4a`、`aac`、`ogg`、`flac`；请求体大小沿用 `AUTOVIDEO_MAX_UPLOAD_BYTES` 和 multipart 开销限制。
- `PUT /api/bgm/tracks/{track_id}`：更新 BGM 显示名和分类。
- `DELETE /api/bgm/tracks/{track_id}`：删除 BGM 文件和元数据。
- `GET /api/bgm/tracks/{track_id}/file`：播放或下载已登记的 BGM 音频，响应包含 `X-Content-Type-Options: nosniff`。
- `POST /api/bgm/categories`、`PUT /api/bgm/categories/{category_id}`、`DELETE /api/bgm/categories/{category_id}`：创建、重命名和删除 BGM 分类；删除分类后曲目迁移到未分类。
```

Update online mix options description:

```markdown
`options` 可包含 `bgm_enabled`、`bgm_track_id`、`bgm_category_id` 和 `bgm_volume`，用于保存 BGM 配置；只选择分类时，任务创建阶段会解析为当前分类中的具体曲目快照。当前最终视频还未混入 BGM 音轨。
```

Add curl example:

```markdown
curl "http://127.0.0.1:8090/api/bgm"

curl -X POST http://127.0.0.1:8090/api/bgm/categories \
  -H "Content-Type: application/json" \
  -d '{"name":"舒缓"}'
```

- [ ] **Step 5: 运行 README 测试确认通过**

Run:

```bash
pytest tests/web/test_frontend_build.py -q -k "bgm_management"
```

Expected:

```text
passed
```

- [ ] **Step 6: 运行全量目标测试**

Run:

```bash
pytest tests/services/test_bgm_library.py tests/api/test_bgm.py tests/api/test_online_mix.py tests/web/test_frontend_build.py -q
cd frontend && npm test -- src/App.test.tsx
cd frontend && npm run build
```

Expected:

```text
pytest: passed
vitest: PASS src/App.test.tsx
vite build: built
```

- [ ] **Step 7: 启动本地服务做视觉验证**

Run backend in one terminal:

```bash
AUTOVIDEO_DATA_DIR="$(pwd)/data" python -m autovideo.main
```

If port `8090` is busy, use:

```bash
AUTOVIDEO_PORT=8091 AUTOVIDEO_DATA_DIR="$(pwd)/data" python -m autovideo.main
```

Run frontend in another terminal:

```bash
cd frontend && npm run dev -- --host 127.0.0.1 --port 5173
```

Open the Vite URL and verify:

```js
window.location.hash = "#bgm";
document.body.scrollWidth <= window.innerWidth;
document.querySelector(".bgm-audio-player")?.getBoundingClientRect().right <= window.innerWidth;
```

Expected on 375px viewport:

```text
true
true
```

- [ ] **Step 8: 提交 Task 6**

Run:

```bash
git add README.md tests/web/test_frontend_build.py
git commit -m "docs: document bgm management"
```

---

## Final Review And PR Gate

After all tasks are committed:

- [ ] Run final verification:

```bash
pytest tests/services/test_bgm_library.py tests/api/test_bgm.py tests/api/test_online_mix.py tests/web/test_frontend_build.py -q
cd frontend && npm test -- src/App.test.tsx
cd frontend && npm run build
```

- [ ] Run local pre-PR review with `superpowers:requesting-code-review`, including:
  - `BASE_SHA=$(git merge-base main HEAD)`
  - `git diff "$BASE_SHA"..HEAD --stat`
  - `git diff "$BASE_SHA"..HEAD`
  - `docs/superpowers/specs/2026-06-20-bgm-management-design.md`
  - this plan file

- [ ] If review finds actionable findings, fix them in a new commit and repeat local review.

- [ ] Push branch and create a ready PR after review passes:

```bash
git push -u origin codex/bgm-management
gh pr create --base main --head codex/bgm-management --title "[codex] Add BGM management" --body "Implements BGM resource management, BGM selection in remix tasks, and task snapshot persistence."
```

- [ ] After PR is ready, run PR-level `superpowers:requesting-code-review`. Fix, test, commit, and push until there are no actionable findings.
