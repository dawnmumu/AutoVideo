from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from autovideo.services.materials import record_material_file
from autovideo.services.material_sources import MaterialSourceService
from autovideo.services.material_worker import (
    ACTIVE_JOB_STATUSES,
    MaterialIndexAlreadyRunningError,
    MaterialWorkerService,
)
from autovideo.storage.database import AutoVideoStore

MaterialSourceMode = Literal["local", "hybrid", "online_free"]
LOCAL_SEGMENT_PROVIDER = "local_material_worker"


class MaterialLibraryEmptyError(Exception):
    """Raised when no local material library source or ready segments exist."""


class MaterialLibraryNotReadyError(Exception):
    """Raised when a configured local library needs indexing before matching."""

    def __init__(self, job: dict[str, Any]) -> None:
        self.job = job
        super().__init__(str(job.get("id") or "material library not ready"))


def _orientation_for_aspect_ratio(aspect_ratio: str) -> str:
    if aspect_ratio == "9:16":
        return "portrait"
    if aspect_ratio == "16:9":
        return "landscape"
    if aspect_ratio == "1:1":
        return "square"
    return "unknown"


def _shot_indexes(script: dict[str, Any]) -> list[int]:
    indexes: list[int] = []
    shots = script.get("shots")
    if not isinstance(shots, list):
        return indexes
    for shot in shots:
        if isinstance(shot, dict):
            try:
                indexes.append(int(shot["index"]))
            except (KeyError, TypeError, ValueError):
                continue
    return indexes


def _tokens(value: Any) -> set[str]:
    if isinstance(value, list):
        text = " ".join(str(item) for item in value if isinstance(item, str))
    elif isinstance(value, str):
        text = value
    else:
        text = ""
    return {token.lower() for token in re.findall(r"[\w\u4e00-\u9fff]+", text)}


class MaterialMatcherService:
    def __init__(
        self,
        store: AutoVideoStore,
        source_service: MaterialSourceService | None = None,
        worker_service: MaterialWorkerService | None = None,
    ) -> None:
        self.store = store
        self.source_service = source_service or MaterialSourceService(store)
        self.worker_service = worker_service or MaterialWorkerService(store)

    def prepare_for_script(
        self,
        script: dict[str, Any],
        mode: MaterialSourceMode,
        *,
        only_shot_indexes: set[int] | None = None,
    ) -> list[dict[str, Any]]:
        aspect_ratio = str(script.get("aspect_ratio") or "9:16")
        orientation = _orientation_for_aspect_ratio(aspect_ratio)
        segments = self.store.ready_material_segments(orientation=orientation)
        if not segments:
            self._raise_empty_or_not_ready()

        shots = [
            shot
            for shot in script.get("shots", [])
            if isinstance(shot, dict)
            and (
                only_shot_indexes is None
                or _safe_int(shot.get("index")) in only_shot_indexes
            )
        ]
        if not shots:
            return []

        reusable = len(segments) < len(shots)
        used_segment_ids: set[str] = set()
        selections: list[dict[str, Any]] = []
        for shot in shots:
            segment = self._best_segment_for_shot(
                shot,
                segments,
                orientation=orientation,
                used_segment_ids=used_segment_ids,
                reusable=reusable,
            )
            if segment is None:
                continue
            if not reusable:
                used_segment_ids.add(str(segment["id"]))
            material = self._material_for_segment(segment)
            selections.append(
                {
                    "shot_index": int(shot["index"]),
                    "material_id": material["id"],
                    "material_segment_id": segment["id"],
                    "raw_file_id": segment["raw_file_id"],
                    "orientation": segment.get("orientation"),
                    "duration_seconds": segment.get("duration_seconds"),
                    "source_display_path": self._source_display_path(segment),
                    "selection_mode": "local_segment",
                    "selection_reason": "本地素材库匹配",
                }
            )
        if not selections and mode == "local":
            raise MaterialLibraryEmptyError()
        return selections

    def _raise_empty_or_not_ready(self) -> None:
        current_source = self.store.current_material_source_config()
        if current_source is None:
            raise MaterialLibraryEmptyError()

        latest_job = self.worker_service.latest_job_for_identity(
            str(current_source["allowed_root_id"]),
            str(current_source["source_path_hash"]),
        )
        if latest_job is not None and latest_job.get("status") in ACTIVE_JOB_STATUSES:
            raise MaterialLibraryNotReadyError(latest_job)
        try:
            job = self.worker_service.create_index_job(str(current_source["id"]))
        except MaterialIndexAlreadyRunningError:
            active_job = self.store.active_material_index_job(
                str(current_source["allowed_root_id"]),
                str(current_source["source_path_hash"]),
            )
            if active_job is None:
                raise
            raise MaterialLibraryNotReadyError(active_job) from None
        raise MaterialLibraryNotReadyError(job)

    def _best_segment_for_shot(
        self,
        shot: dict[str, Any],
        segments: list[dict[str, Any]],
        *,
        orientation: str,
        used_segment_ids: set[str],
        reusable: bool,
    ) -> dict[str, Any] | None:
        candidates = [
            segment
            for segment in segments
            if reusable or str(segment["id"]) not in used_segment_ids
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda segment: self._score_segment(
                shot,
                segment,
                orientation=orientation,
            ),
        )

    def _score_segment(
        self,
        shot: dict[str, Any],
        segment: dict[str, Any],
        *,
        orientation: str,
    ) -> tuple[int, int, float, str]:
        raw = self.store.get_material_raw_file(str(segment["raw_file_id"])) or {}
        shot_tokens = (
            _tokens(shot.get("keywords"))
            | _tokens(shot.get("visual_description"))
            | _tokens(shot.get("narration"))
            | _tokens(shot.get("subtitle"))
        )
        segment_tokens = (
            _tokens(segment.get("match_text"))
            | _tokens(segment.get("asr_text"))
            | _tokens(segment.get("ocr_text"))
            | _tokens(segment.get("vision_description"))
            | _tokens(raw.get("original_filename"))
            | _tokens(raw.get("source_display_path"))
        )
        duration = _safe_float(segment.get("duration_seconds"))
        shot_duration = _safe_float(shot.get("duration")) or 1.0
        return (
            2 if segment.get("orientation") == orientation else 0,
            len(shot_tokens & segment_tokens),
            1.0 if duration >= shot_duration else 0.0,
            str(segment.get("created_at") or ""),
        )

    def _material_for_segment(self, segment: dict[str, Any]) -> dict[str, Any]:
        existing = self._existing_material_for_segment(str(segment["id"]))
        if existing is not None:
            return existing

        raw = self.store.get_material_raw_file(str(segment["raw_file_id"])) or {}
        storage_path = self._managed_segment_path(segment)
        return record_material_file(
            self.store,
            Path(str(raw.get("original_filename") or f"{segment['id']}.mp4")).name,
            "video/mp4",
            storage_path.stat().st_size if storage_path.exists() else 0,
            storage_path,
            {
                "source_type": "local_segment",
                "source_provider": LOCAL_SEGMENT_PROVIDER,
                "source_asset_id": segment["id"],
            },
        )

    def _existing_material_for_segment(
        self,
        segment_id: str,
    ) -> dict[str, Any] | None:
        with self.store.connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM materials
                WHERE source_type = 'local_segment'
                  AND source_provider = ?
                  AND source_asset_id = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1
                """,
                (LOCAL_SEGMENT_PROVIDER, segment_id),
            ).fetchone()
        return self.store._material_from_row(row) if row else None

    def _managed_segment_path(self, segment: dict[str, Any]) -> Path:
        relative_path = Path(str(segment["managed_segment_relative_path"]))
        return self.store.paths.material_segments / relative_path

    def _source_display_path(self, segment: dict[str, Any]) -> str | None:
        raw = self.store.get_material_raw_file(str(segment["raw_file_id"]))
        if raw is None:
            return None
        value = raw.get("source_display_path")
        return value if isinstance(value, str) and value else None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
