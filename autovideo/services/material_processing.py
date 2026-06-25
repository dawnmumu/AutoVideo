from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from autovideo.services.material_sources import MaterialSourceService
from autovideo.storage.database import AutoVideoStore

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
SEGMENT_DURATION_SECONDS = 8.0
MIN_SEGMENT_DURATION_SECONDS = 1.0
FFPROBE_TIMEOUT_SECONDS = 20
FFMPEG_TIMEOUT_SECONDS = 120
CONTENT_TYPES = {
    ".avi": "video/x-msvideo",
    ".m4v": "video/x-m4v",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}


class MaterialFfmpegUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class VideoProbeResult:
    duration_seconds: float
    width: int
    height: int
    codec_name: str | None = None


ProbeVideo = Callable[[Path], VideoProbeResult]
SliceVideo = Callable[[Path, Path, float, float], None]


class MaterialProcessingService:
    def __init__(
        self,
        store: AutoVideoStore,
        *,
        probe_video: ProbeVideo | None = None,
        slice_video: SliceVideo | None = None,
    ) -> None:
        self.store = store
        self._probe_uses_ffprobe = probe_video is None
        self._slice_uses_ffmpeg = slice_video is None
        self.probe_video = probe_video or probe_video_metadata
        self.slice_video = slice_video or (
            lambda source_path, target_path, start, duration: slice_video_with_ffmpeg(
                source_path,
                target_path,
                start,
                duration,
                ffmpeg_path=self.store.settings.ffmpeg_path,
            )
        )

    def process_source(self, source_config: dict[str, Any]) -> dict[str, int]:
        resolved_source = MaterialSourceService(self.store).resolve_source(
            str(source_config["allowed_root_id"]),
            str(source_config["source_relative_path"]),
        )
        raw_files_total = 0
        segments_total = 0
        failed_total = 0

        for source_path in self._iter_source_files(
            resolved_source.resolved_path, resolved_source.allowed_root.resolved_path
        ):
            try:
                processed = self._process_video_file(
                    source_config,
                    source_path,
                    resolved_source.allowed_root.resolved_path,
                )
            except MaterialFfmpegUnavailableError:
                raise
            except Exception:
                failed_total += 1
                continue
            if processed is None:
                continue
            raw_files_total += 1
            segments_total += processed["segments_total"]
            failed_total += processed["failed_total"]

        return {
            "raw_files_total": raw_files_total,
            "segments_total": segments_total,
            "failed_total": failed_total,
        }

    def delete_raw_file(self, raw_file_id: str) -> dict[str, Any]:
        raw = self.store.get_material_raw_file(raw_file_id)
        if raw is None:
            return {
                "id": raw_file_id,
                "deleted": False,
                "error_code": "MATERIAL_LIBRARY_CLEAR_FAILED",
            }
        planned = self._plan_raw_cleanup(raw_file_id, raw, self._segment_rows_for_raw(raw_file_id))
        if planned is None:
            return self._clear_failed(raw_file_id)

        for path in planned["segment_paths"]:
            path.unlink(missing_ok=True)
        if planned["segment_dir"].exists():
            shutil.rmtree(planned["segment_dir"], ignore_errors=True)
        planned["raw_path"].unlink(missing_ok=True)
        deleted_at = self._now_isoformat()
        segment_ids = planned["segment_ids"]
        self.store.delete_local_segment_materials(segment_ids)
        self.store.mark_material_segments_deleted(raw_file_id, deleted_at)
        self.store.mark_material_raw_file_deleted(raw_file_id, deleted_at)
        return {
            "id": raw_file_id,
            "deleted": True,
            "deleted_segments": len(segment_ids),
        }

    def clear_library(self, confirm: str | None) -> dict[str, Any]:
        if confirm != "CLEAR_MATERIAL_LIBRARY":
            return {
                "deleted_raw": 0,
                "deleted_segments": 0,
                "error_code": "MATERIAL_LIBRARY_CLEAR_CONFIRMATION_REQUIRED",
            }
        raw_rows = self._all_raw_rows()
        planned: list[dict[str, Any]] = []
        for raw in raw_rows:
            raw_id = str(raw["id"])
            raw_plan = self._plan_raw_cleanup(
                raw_id,
                raw,
                self._segment_rows_for_raw(raw_id),
            )
            if raw_plan is None:
                return self._clear_failed(raw_id)
            planned.append(raw_plan)

        deleted_raw = 0
        deleted_segments = 0
        deleted_at = self._now_isoformat()
        for raw_plan in planned:
            raw_id = str(raw_plan["raw_id"])
            for path in raw_plan["segment_paths"]:
                path.unlink(missing_ok=True)
            if raw_plan["segment_dir"].exists():
                shutil.rmtree(raw_plan["segment_dir"], ignore_errors=True)
            raw_plan["raw_path"].unlink(missing_ok=True)
            segment_ids = raw_plan["segment_ids"]
            self.store.delete_local_segment_materials(segment_ids)
            deleted_segments += self.store.mark_material_segments_deleted(
                raw_id, deleted_at
            )
            self.store.mark_material_raw_file_deleted(raw_id, deleted_at)
            deleted_raw += 1
        return {
            "deleted_raw": deleted_raw,
            "deleted_segments": deleted_segments,
        }

    def _process_video_file(
        self,
        source_config: dict[str, Any],
        source_path: Path,
        allowed_root: Path,
    ) -> dict[str, int] | None:
        if source_path.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
            return None
        source_relative_path = source_path.relative_to(allowed_root).as_posix()
        copy_source = source_path
        if source_path.is_symlink():
            resolved = source_path.resolve(strict=True)
            try:
                resolved.relative_to(allowed_root)
            except ValueError as exc:
                raise ValueError("symlink target escaped allowed root") from exc
            if not resolved.is_file():
                raise ValueError("symlink target is not a file")
            copy_source = resolved
        if self._probe_uses_ffprobe and shutil.which("ffprobe") is None:
            raise MaterialFfmpegUnavailableError("ffprobe")
        if self._slice_uses_ffmpeg and shutil.which(self.store.settings.ffmpeg_path) is None:
            raise MaterialFfmpegUnavailableError(self.store.settings.ffmpeg_path)
        return self._process_video_file_resolved(
            source_config,
            copy_source,
            source_path.name,
            source_relative_path,
        )

    def _process_video_file_resolved(
        self,
        source_config: dict[str, Any],
        source_path: Path,
        original_filename: str,
        source_relative_path: str,
    ) -> dict[str, int]:
        source_identity = (
            f"{source_config['allowed_root_id']}:{source_relative_path}"
        )
        raw_id = hashlib.sha256(source_identity.encode("utf-8")).hexdigest()
        ext = source_path.suffix.lower()
        raw_relative_path = f"{raw_id}{ext}"
        raw_path = self.store.paths.material_raw / raw_relative_path
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        size_bytes, content_hash = self._copy_file_with_hash(source_path, raw_path)
        segment_dir = self.store.paths.material_segments / raw_id
        if segment_dir.exists():
            shutil.rmtree(segment_dir)
        segment_dir.mkdir(parents=True, exist_ok=True)
        existing_segment_ids = [str(row["id"]) for row in self._segment_rows_for_raw(raw_id)]
        if existing_segment_ids:
            self.store.delete_local_segment_materials(existing_segment_ids)
        deleted_at = self._now_isoformat()
        self.store.mark_material_segments_deleted(raw_id, deleted_at)
        failure_error_summary = "MATERIAL_PROBE_FAILED"
        try:
            probe = self.probe_video(raw_path)
            ranges = _segment_ranges(probe.duration_seconds)
            if not ranges:
                raise ValueError("video is too short to segment")
            created_segments: list[dict[str, Any]] = []
            for index, (start, duration) in enumerate(ranges, start=1):
                failure_error_summary = "MATERIAL_SEGMENT_FAILED"
                segment_id = f"{raw_id}_{index}"
                segment_relative_path = f"{raw_id}/{segment_id}{ext}"
                segment_path = self.store.paths.material_segments / segment_relative_path
                segment_path.parent.mkdir(parents=True, exist_ok=True)
                self.slice_video(raw_path, segment_path, start, duration)
                created_segments.append(
                    {
                        "id": segment_id,
                        "raw_file_id": raw_id,
                        "managed_segment_relative_path": segment_relative_path,
                        "start_seconds": start,
                        "duration_seconds": duration,
                        "orientation": _orientation_for_size(
                            probe.width, probe.height
                        ),
                        "status": "ready",
                        "match_text": _match_text_for_path(source_relative_path),
                        "asr_text": None,
                        "ocr_text": None,
                        "vision_description": None,
                        "content_label_status": "not_configured",
                        "embedding_status": "not_configured",
                        "error_summary": None,
                        "deleted_at": None,
                    }
                )
            raw_row = self.store.upsert_material_raw_file(
                {
                    "id": raw_id,
                    "source_config_id": source_config["id"],
                    "allowed_root_id": source_config["allowed_root_id"],
                    "source_relative_path": source_relative_path,
                    "source_path_hash": hashlib.sha256(
                        source_identity.encode("utf-8")
                    ).hexdigest(),
                    "source_display_path": f"{source_config['allowed_root_id']}/{source_relative_path}",
                    "original_filename": original_filename,
                    "managed_raw_relative_path": raw_relative_path,
                    "content_hash": content_hash,
                    "size_bytes": size_bytes,
                    "duration_seconds": probe.duration_seconds,
                    "orientation": _orientation_for_size(probe.width, probe.height),
                    "status": "ready",
                    "error_summary": None,
                    "deleted_at": None,
                }
            )
            for segment in created_segments:
                saved = self.store.upsert_material_segment(segment)
                self.store.delete_local_segment_materials([str(saved["id"])])
                self.store.insert_material(
                    {
                        "id": uuid.uuid5(uuid.NAMESPACE_URL, f"local-segment:{saved['id']}").hex,
                        "original_filename": raw_row["original_filename"],
                        "content_type": CONTENT_TYPES.get(ext, "video/mp4"),
                        "size_bytes": segment_path_size(
                            self.store.paths.material_segments
                            / str(saved["managed_segment_relative_path"])
                        ),
                        "storage_path": str(
                            self.store.paths.material_segments
                            / str(saved["managed_segment_relative_path"])
                        ),
                        "created_at": self._now_isoformat(),
                        "source_type": "local_segment",
                        "source_provider": "local_material_worker",
                        "source_asset_id": saved["id"],
                    }
                )
            return {"raw_files_total": 1, "segments_total": len(created_segments), "failed_total": 0}
        except MaterialFfmpegUnavailableError:
            raw_path.unlink(missing_ok=True)
            if segment_dir.exists():
                shutil.rmtree(segment_dir, ignore_errors=True)
            raise
        except Exception as exc:
            if segment_dir.exists():
                shutil.rmtree(segment_dir, ignore_errors=True)
            self.store.upsert_material_raw_file(
                {
                    "id": raw_id,
                    "source_config_id": source_config["id"],
                    "allowed_root_id": source_config["allowed_root_id"],
                    "source_relative_path": source_relative_path,
                    "source_path_hash": hashlib.sha256(
                        source_identity.encode("utf-8")
                    ).hexdigest(),
                    "source_display_path": f"{source_config['allowed_root_id']}/{source_relative_path}",
                    "original_filename": original_filename,
                    "managed_raw_relative_path": raw_relative_path,
                    "content_hash": content_hash,
                    "size_bytes": size_bytes,
                    "duration_seconds": None,
                    "orientation": None,
                    "status": "failed",
                    "error_summary": failure_error_summary,
                    "deleted_at": None,
                }
            )
            return {"raw_files_total": 1, "segments_total": 0, "failed_total": 1}

    def _iter_source_files(self, source_root: Path, allowed_root: Path) -> list[Path]:
        files: list[Path] = []
        for current_root, dirnames, filenames in os.walk(source_root, followlinks=False):
            current_path = Path(current_root)
            filtered_dirs: list[str] = []
            for dirname in dirnames:
                child = current_path / dirname
                if child.is_symlink():
                    continue
                filtered_dirs.append(dirname)
            dirnames[:] = filtered_dirs
            for filename in filenames:
                candidate = current_path / filename
                try:
                    candidate.relative_to(allowed_root)
                except ValueError:
                    continue
                files.append(candidate)
        return sorted(files)

    def _segment_rows_for_raw(self, raw_file_id: str) -> list[dict[str, Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM material_segments
                WHERE raw_file_id = ?
                  AND deleted_at IS NULL
                ORDER BY start_seconds ASC, rowid ASC
                """,
                (raw_file_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _all_raw_rows(self) -> list[dict[str, Any]]:
        with self.store.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM material_raw_files
                WHERE deleted_at IS NULL
                ORDER BY created_at DESC, rowid DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def _copy_file_with_hash(self, source_path: Path, target_path: Path) -> tuple[int, str]:
        digest = hashlib.sha256()
        size_bytes = 0
        with source_path.open("rb") as source_file, target_path.open("wb") as target_file:
            while chunk := source_file.read(1024 * 1024):
                target_file.write(chunk)
                digest.update(chunk)
                size_bytes += len(chunk)
        return size_bytes, digest.hexdigest()

    def _guarded_managed_path(self, root: Path, relative_path: str) -> Path | None:
        if not _is_safe_managed_relative_path(relative_path):
            return None
        root = root.resolve()
        candidate = (root / relative_path).resolve()
        if candidate == root:
            return None
        try:
            candidate.relative_to(root)
        except ValueError:
            return None
        return candidate

    def _plan_raw_cleanup(
        self,
        raw_file_id: str,
        raw: dict[str, Any],
        segment_rows: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        raw_path = self._guarded_managed_path(
            self.store.paths.material_raw,
            str(raw["managed_raw_relative_path"]),
        )
        if raw_path is None:
            return None
        if not _is_safe_managed_child_name(raw_file_id):
            return None
        expected_segment_dir = self._guarded_managed_path(
            self.store.paths.material_segments,
            raw_file_id,
        )
        if expected_segment_dir is None:
            return None
        segment_paths: list[Path] = []
        segment_ids: list[str] = []
        for row in segment_rows:
            segment_path = self._guarded_managed_path(
                self.store.paths.material_segments,
                str(row["managed_segment_relative_path"]),
            )
            if segment_path is None:
                return None
            if segment_path.parent != expected_segment_dir:
                return None
            segment_paths.append(segment_path)
            segment_ids.append(str(row["id"]))
        return {
            "raw_id": raw_file_id,
            "raw_path": raw_path,
            "segment_dir": expected_segment_dir,
            "segment_paths": segment_paths,
            "segment_ids": segment_ids,
        }

    def _clear_failed(self, raw_file_id: str) -> dict[str, Any]:
        return {
            "id": raw_file_id,
            "deleted": False,
            "error_code": "MATERIAL_LIBRARY_CLEAR_FAILED",
        }

    @staticmethod
    def _now_isoformat() -> str:
        from datetime import UTC, datetime

        return datetime.now(UTC).isoformat()


def probe_video_metadata(path: Path) -> VideoProbeResult:
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
    except FileNotFoundError as exc:
        raise MaterialFfmpegUnavailableError("ffprobe is unavailable") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("ffprobe timed out") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(exc.stderr or exc.stdout or "ffprobe failed") from exc
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("ffprobe payload is invalid")
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise RuntimeError("ffprobe streams are missing")
    video_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        None,
    )
    if not isinstance(video_stream, dict):
        raise RuntimeError("video stream is missing")
    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    duration_seconds = _probe_duration_seconds(video_stream, payload.get("format"))
    return VideoProbeResult(
        duration_seconds=duration_seconds,
        width=width,
        height=height,
        codec_name=str(video_stream.get("codec_name") or "").strip().lower() or None,
    )


def slice_video_with_ffmpeg(
    source_path: Path,
    target_path: Path,
    start: float,
    duration: float,
    *,
    ffmpeg_path: str = "ffmpeg",
) -> None:
    ffmpeg_binary = shutil.which(ffmpeg_path)
    if ffmpeg_binary is None:
        raise MaterialFfmpegUnavailableError(ffmpeg_path)
    try:
        subprocess.run(
            [
                ffmpeg_binary,
                "-y",
                "-ss",
                _ffmpeg_number(start),
                "-i",
                str(source_path),
                "-t",
                _ffmpeg_number(duration),
                "-c",
                "copy",
                str(target_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("ffmpeg timed out") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(exc.stderr or exc.stdout or "ffmpeg failed") from exc


def _probe_duration_seconds(stream: dict[str, Any], format_info: Any) -> float:
    candidates = [stream.get("duration")]
    if isinstance(format_info, dict):
        candidates.append(format_info.get("duration"))
    for candidate in candidates:
        try:
            duration = float(candidate)
        except (TypeError, ValueError):
            continue
        if duration > 0:
            return duration
    raise RuntimeError("video duration is missing")


def _segment_ranges(duration_seconds: float) -> list[tuple[float, float]]:
    if duration_seconds < MIN_SEGMENT_DURATION_SECONDS:
        return []
    segments: list[tuple[float, float]] = []
    start = 0.0
    while start < duration_seconds:
        remaining = duration_seconds - start
        duration = min(SEGMENT_DURATION_SECONDS, remaining)
        if remaining > SEGMENT_DURATION_SECONDS and remaining - SEGMENT_DURATION_SECONDS < MIN_SEGMENT_DURATION_SECONDS:
            duration = remaining
        if duration < MIN_SEGMENT_DURATION_SECONDS:
            break
        segments.append((round(start, 3), round(duration, 3)))
        start += duration
    return segments


def _orientation_for_size(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "unknown"
    if width == height:
        return "square"
    if width > height:
        return "landscape"
    return "portrait"


def _match_text_for_path(relative_path: str) -> str:
    parts = [part.replace("_", " ").replace("-", " ") for part in Path(relative_path).parts]
    return " ".join(part for part in parts if part).strip()


def _is_safe_managed_relative_path(relative_path: str) -> bool:
    if relative_path == "" or relative_path.strip() == "":
        return False
    path = Path(relative_path)
    if path.is_absolute():
        return False
    parts = [part for part in relative_path.replace("\\", "/").split("/") if part != ""]
    if not parts:
        return False
    if any(part in {".", ".."} for part in parts):
        return False
    return True


def _is_safe_managed_child_name(value: str) -> bool:
    return _is_safe_managed_relative_path(value) and len(Path(value).parts) == 1


def _ffmpeg_number(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def segment_path_size(path: Path) -> int:
    return path.stat().st_size
