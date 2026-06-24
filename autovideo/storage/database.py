from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from autovideo.core.paths import ensure_data_dirs
from autovideo.core.settings import Settings

MATERIAL_SOURCE_COLUMNS = {
    "source_type": "TEXT",
    "source_provider": "TEXT",
    "source_asset_id": "TEXT",
    "source_url": "TEXT",
    "license_note": "TEXT",
    "query": "TEXT",
}

MATERIAL_INDEX_JOB_COLUMNS = {
    "source_config_id",
    "allowed_root_id",
    "source_relative_path",
    "source_path_hash",
    "status",
    "stage",
    "progress_current",
    "progress_total",
    "raw_files_total",
    "segments_total",
    "failed_total",
    "heartbeat_at",
    "attempt_count",
    "error_summary",
    "created_at",
    "started_at",
    "finished_at",
}

MATERIAL_RAW_FILE_COLUMNS = (
    "id",
    "source_config_id",
    "allowed_root_id",
    "source_relative_path",
    "source_path_hash",
    "source_display_path",
    "original_filename",
    "managed_raw_relative_path",
    "content_hash",
    "size_bytes",
    "duration_seconds",
    "orientation",
    "status",
    "error_summary",
    "asr_status",
    "ocr_status",
    "vision_status",
    "embedding_status",
    "created_at",
    "updated_at",
    "deleted_at",
)

MATERIAL_SEGMENT_COLUMNS = (
    "id",
    "raw_file_id",
    "managed_segment_relative_path",
    "start_seconds",
    "duration_seconds",
    "orientation",
    "status",
    "match_text",
    "asr_text",
    "ocr_text",
    "vision_description",
    "content_label_status",
    "embedding_status",
    "error_summary",
    "created_at",
    "updated_at",
    "deleted_at",
)


class AutoVideoStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.paths = ensure_data_dirs(settings)
        self.db_path = self.paths.root / "autovideo.sqlite3"
        self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def insert_material(self, material: dict[str, Any]) -> dict[str, Any]:
        source_type = material.get("source_type") or "upload"
        inserted_material = {
            **material,
            "source_type": source_type,
            "source_provider": material.get("source_provider"),
            "source_asset_id": material.get("source_asset_id"),
            "source_url": material.get("source_url"),
            "license_note": material.get("license_note"),
            "query": material.get("query"),
        }
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO materials (
                    id, original_filename, content_type, size_bytes,
                    storage_path, created_at, source_type, source_provider,
                    source_asset_id, source_url, license_note, query
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    material["id"],
                    material["original_filename"],
                    material["content_type"],
                    material["size_bytes"],
                    material["storage_path"],
                    material["created_at"],
                    source_type,
                    material.get("source_provider"),
                    material.get("source_asset_id"),
                    material.get("source_url"),
                    material.get("license_note"),
                    material.get("query"),
                ),
            )
        return inserted_material

    def list_materials(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM materials
                ORDER BY created_at DESC, rowid DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [self._material_from_row(row) for row in rows]

    def get_material(self, material_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM materials WHERE id = ?",
                (material_id,),
            ).fetchone()
        return self._material_from_row(row) if row else None

    def insert_material_source_config(self, config: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            if config["status"] == "active":
                connection.execute(
                    """
                    UPDATE material_source_configs
                    SET status = 'inactive', updated_at = ?
                    WHERE status = 'active'
                    """,
                    (config["updated_at"],),
                )
            connection.execute(
                """
                INSERT INTO material_source_configs (
                    id, allowed_root_id, allowed_root_alias,
                    source_relative_path, source_display_path, source_path_hash,
                    status, error_summary, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    config["id"],
                    config["allowed_root_id"],
                    config["allowed_root_alias"],
                    config["source_relative_path"],
                    config["source_display_path"],
                    config["source_path_hash"],
                    config["status"],
                    config.get("error_summary"),
                    config["created_at"],
                    config["updated_at"],
                ),
            )
            row = connection.execute(
                "SELECT * FROM material_source_configs WHERE id = ?",
                (config["id"],),
            ).fetchone()
        return self._material_source_config_from_row(row) if row else config

    def get_material_source_config(self, config_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM material_source_configs WHERE id = ?",
                (config_id,),
            ).fetchone()
        return self._material_source_config_from_row(row) if row else None

    def current_material_source_config(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM material_source_configs
                WHERE status = 'active'
                ORDER BY updated_at DESC, rowid DESC
                LIMIT 1
                """
            ).fetchone()
        return self._material_source_config_from_row(row) if row else None

    def insert_material_index_job(self, job: dict[str, Any]) -> dict[str, Any]:
        from autovideo.services.material_worker import MaterialIndexAlreadyRunningError

        with self.connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                active = connection.execute(
                    """
                    SELECT * FROM material_index_jobs
                    WHERE allowed_root_id = ?
                      AND source_path_hash = ?
                      AND status IN ('queued', 'running')
                    ORDER BY created_at ASC, rowid ASC
                    LIMIT 1
                    """,
                    (job["allowed_root_id"], job["source_path_hash"]),
                ).fetchone()
                if active is not None:
                    connection.rollback()
                    raise MaterialIndexAlreadyRunningError()
                connection.execute(
                    """
                    INSERT INTO material_index_jobs (
                        id, source_config_id, allowed_root_id, source_relative_path,
                        source_path_hash, status, stage, progress_current,
                        progress_total, raw_files_total, segments_total, failed_total,
                        heartbeat_at, attempt_count, error_summary, created_at,
                        started_at, finished_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job["id"],
                        job["source_config_id"],
                        job["allowed_root_id"],
                        job["source_relative_path"],
                        job["source_path_hash"],
                        job["status"],
                        job["stage"],
                        job.get("progress_current", 0),
                        job.get("progress_total", 0),
                        job.get("raw_files_total", 0),
                        job.get("segments_total", 0),
                        job.get("failed_total", 0),
                        job.get("heartbeat_at"),
                        job.get("attempt_count", 0),
                        job.get("error_summary"),
                        job["created_at"],
                        job.get("started_at"),
                        job.get("finished_at"),
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM material_index_jobs WHERE id = ?",
                    (job["id"],),
                ).fetchone()
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                if "material_index_jobs.allowed_root_id, material_index_jobs.source_path_hash" in str(
                    exc
                ):
                    raise MaterialIndexAlreadyRunningError() from exc
                raise
        return self._material_index_job_from_row(row) if row else job

    def get_material_index_job(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM material_index_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return self._material_index_job_from_row(row) if row else None

    def update_material_index_job(
        self,
        job_id: str,
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        unknown = set(patch) - MATERIAL_INDEX_JOB_COLUMNS
        if unknown:
            raise ValueError(f"unknown material index job fields: {sorted(unknown)}")
        if not patch:
            existing = self.get_material_index_job(job_id)
            if existing is None:
                raise KeyError(job_id)
            return existing

        assignments = ", ".join(f"{column} = ?" for column in patch)
        values = list(patch.values()) + [job_id]
        with self.connect() as connection:
            cursor = connection.execute(
                f"""
                UPDATE material_index_jobs
                SET {assignments}
                WHERE id = ?
                """,
                values,
            )
            if cursor.rowcount == 0:
                raise KeyError(job_id)
            row = connection.execute(
                "SELECT * FROM material_index_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return self._material_index_job_from_row(row) if row else {}

    def latest_material_index_job(
        self,
        source_config_id: str | None = None,
    ) -> dict[str, Any] | None:
        query = """
            SELECT * FROM material_index_jobs
        """
        params: tuple[Any, ...] = ()
        if source_config_id is not None:
            query += " WHERE source_config_id = ?"
            params = (source_config_id,)
        query += " ORDER BY created_at DESC, rowid DESC LIMIT 1"
        with self.connect() as connection:
            row = connection.execute(query, params).fetchone()
        return self._material_index_job_from_row(row) if row else None

    def active_material_index_job(
        self,
        allowed_root_id: str,
        source_path_hash: str,
    ) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM material_index_jobs
                WHERE allowed_root_id = ?
                  AND source_path_hash = ?
                  AND status IN ('queued', 'running')
                ORDER BY created_at ASC, rowid ASC
                LIMIT 1
                """,
                (allowed_root_id, source_path_hash),
            ).fetchone()
        return self._material_index_job_from_row(row) if row else None

    def claim_next_material_index_job(self, now: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT id FROM material_index_jobs
                WHERE status = 'queued'
                ORDER BY created_at ASC, rowid ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            connection.execute(
                """
                UPDATE material_index_jobs
                SET status = 'running',
                    started_at = COALESCE(started_at, ?),
                    heartbeat_at = ?,
                    attempt_count = attempt_count + 1
                WHERE id = ?
                  AND status = 'queued'
                """,
                (now, now, row["id"]),
            )
            claimed = connection.execute(
                "SELECT * FROM material_index_jobs WHERE id = ?",
                (row["id"],),
            ).fetchone()
            connection.commit()
        return self._material_index_job_from_row(claimed) if claimed else None

    def claim_material_index_job(self, job_id: str, now: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT id FROM material_index_jobs
                WHERE id = ?
                  AND status = 'queued'
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            connection.execute(
                """
                UPDATE material_index_jobs
                SET status = 'running',
                    started_at = COALESCE(started_at, ?),
                    heartbeat_at = ?,
                    attempt_count = attempt_count + 1
                WHERE id = ?
                  AND status = 'queued'
                """,
                (now, now, job_id),
            )
            claimed = connection.execute(
                "SELECT * FROM material_index_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            connection.commit()
        return self._material_index_job_from_row(claimed) if claimed else None

    def mark_stale_material_index_jobs(self, stale_before: str, now: str) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE material_index_jobs
                SET status = 'stale',
                    finished_at = ?,
                    error_summary = 'MATERIAL_INDEX_JOB_STALE'
                WHERE status = 'running'
                  AND heartbeat_at < ?
                """,
                (now, stale_before),
            )
        return cursor.rowcount

    def insert_task(self, task: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    id, title, status, material_ids, options_json,
                    output_path, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task["id"],
                    task["title"],
                    task["status"],
                    json.dumps(task["material_ids"], ensure_ascii=False),
                    json.dumps(task["options"], ensure_ascii=False),
                    task["output"]["path"],
                    task["created_at"],
                    task["updated_at"],
                ),
            )
        return self.get_task(task["id"]) or task

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        return self._task_from_row(row) if row else None

    def delete_task(self, task_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM tasks WHERE id = ?",
                (task_id,),
            )
        return cursor.rowcount > 0

    def upsert_material_raw_file(self, raw_file: dict[str, Any]) -> dict[str, Any]:
        now = self._now_isoformat()
        record = {
            "id": raw_file["id"],
            "source_config_id": raw_file.get("source_config_id"),
            "allowed_root_id": raw_file["allowed_root_id"],
            "source_relative_path": raw_file["source_relative_path"],
            "source_path_hash": raw_file["source_path_hash"],
            "source_display_path": raw_file["source_display_path"],
            "original_filename": raw_file["original_filename"],
            "managed_raw_relative_path": raw_file["managed_raw_relative_path"],
            "content_hash": raw_file.get("content_hash"),
            "size_bytes": raw_file["size_bytes"],
            "duration_seconds": raw_file.get("duration_seconds"),
            "orientation": raw_file.get("orientation"),
            "status": raw_file["status"],
            "error_summary": raw_file.get("error_summary"),
            "asr_status": raw_file.get("asr_status", "not_configured"),
            "ocr_status": raw_file.get("ocr_status", "not_configured"),
            "vision_status": raw_file.get("vision_status", "not_configured"),
            "embedding_status": raw_file.get("embedding_status", "not_configured"),
            "created_at": raw_file.get("created_at", now),
            "updated_at": raw_file.get("updated_at", now),
            "deleted_at": raw_file.get("deleted_at"),
        }
        update_columns = [
            "source_config_id",
            "allowed_root_id",
            "source_relative_path",
            "source_path_hash",
            "source_display_path",
            "original_filename",
            "managed_raw_relative_path",
            "content_hash",
            "size_bytes",
            "duration_seconds",
            "orientation",
            "status",
            "error_summary",
            "asr_status",
            "ocr_status",
            "vision_status",
            "embedding_status",
            "updated_at",
        ]
        if "deleted_at" in raw_file:
            update_columns.append("deleted_at")
        assignments = ", ".join(
            f"{column} = excluded.{column}" for column in update_columns
        )
        placeholders = ", ".join("?" for _ in MATERIAL_RAW_FILE_COLUMNS)
        with self.connect() as connection:
            connection.execute(
                f"""
                INSERT INTO material_raw_files ({", ".join(MATERIAL_RAW_FILE_COLUMNS)})
                VALUES ({placeholders})
                ON CONFLICT(id) DO UPDATE SET
                    {assignments}
                """,
                tuple(record[column] for column in MATERIAL_RAW_FILE_COLUMNS),
            )
            row = connection.execute(
                "SELECT * FROM material_raw_files WHERE id = ?",
                (record["id"],),
            ).fetchone()
        return self._material_raw_file_from_row(row) if row else record

    def get_material_raw_file(self, raw_file_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM material_raw_files WHERE id = ?",
                (raw_file_id,),
            ).fetchone()
        return self._material_raw_file_from_row(row) if row else None

    def list_material_raw_files(
        self,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["raw.deleted_at IS NULL"]
        params: list[Any] = []
        if status is not None:
            clauses.append("raw.status = ?")
            params.append(status)
        params.extend([limit, offset])
        query = f"""
            SELECT raw.*, COUNT(seg.id) AS segments
            FROM material_raw_files raw
            LEFT JOIN material_segments seg
              ON seg.raw_file_id = raw.id
             AND seg.deleted_at IS NULL
            WHERE {" AND ".join(clauses)}
            GROUP BY raw.id
            ORDER BY raw.created_at DESC, raw.rowid DESC
            LIMIT ? OFFSET ?
        """
        with self.connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._material_raw_file_from_row(row) for row in rows]

    def count_material_raw_files(self, *, status: str | None = None) -> int:
        query = "SELECT COUNT(*) FROM material_raw_files WHERE deleted_at IS NULL"
        params: tuple[Any, ...] = ()
        if status is not None:
            query += " AND status = ?"
            params = (status,)
        with self.connect() as connection:
            value = connection.execute(query, params).fetchone()
        return int(value[0]) if value else 0

    def upsert_material_segment(self, segment: dict[str, Any]) -> dict[str, Any]:
        now = self._now_isoformat()
        record = {
            "id": segment["id"],
            "raw_file_id": segment["raw_file_id"],
            "managed_segment_relative_path": segment["managed_segment_relative_path"],
            "start_seconds": segment["start_seconds"],
            "duration_seconds": segment["duration_seconds"],
            "orientation": segment.get("orientation"),
            "status": segment["status"],
            "match_text": segment.get("match_text"),
            "asr_text": segment.get("asr_text"),
            "ocr_text": segment.get("ocr_text"),
            "vision_description": segment.get("vision_description"),
            "content_label_status": segment.get(
                "content_label_status", "not_configured"
            ),
            "embedding_status": segment.get("embedding_status", "not_configured"),
            "error_summary": segment.get("error_summary"),
            "created_at": segment.get("created_at", now),
            "updated_at": segment.get("updated_at", now),
            "deleted_at": segment.get("deleted_at"),
        }
        update_columns = [
            "raw_file_id",
            "managed_segment_relative_path",
            "start_seconds",
            "duration_seconds",
            "orientation",
            "status",
            "match_text",
            "asr_text",
            "ocr_text",
            "vision_description",
            "content_label_status",
            "embedding_status",
            "error_summary",
            "updated_at",
        ]
        if "deleted_at" in segment:
            update_columns.append("deleted_at")
        assignments = ", ".join(
            f"{column} = excluded.{column}" for column in update_columns
        )
        placeholders = ", ".join("?" for _ in MATERIAL_SEGMENT_COLUMNS)
        with self.connect() as connection:
            connection.execute(
                f"""
                INSERT INTO material_segments ({", ".join(MATERIAL_SEGMENT_COLUMNS)})
                VALUES ({placeholders})
                ON CONFLICT(id) DO UPDATE SET
                    {assignments}
                """,
                tuple(record[column] for column in MATERIAL_SEGMENT_COLUMNS),
            )
            row = connection.execute(
                "SELECT * FROM material_segments WHERE id = ?",
                (record["id"],),
            ).fetchone()
        return self._material_segment_from_row(row) if row else record

    def list_material_segments(
        self,
        raw_file_id: str,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM material_segments
                WHERE raw_file_id = ?
                  AND deleted_at IS NULL
                ORDER BY start_seconds ASC, rowid ASC
                LIMIT ? OFFSET ?
                """,
                (raw_file_id, limit, offset),
            ).fetchall()
        return [self._material_segment_from_row(row) for row in rows]

    def ready_material_segments(
        self,
        *,
        orientation: str | None = None,
    ) -> list[dict[str, Any]]:
        params: tuple[Any, ...] = ()
        order_by = "seg.created_at DESC, seg.rowid DESC"
        if orientation is not None:
            order_by = """
                CASE
                    WHEN seg.orientation = ? THEN 0
                    WHEN seg.orientation = 'unknown' THEN 1
                    ELSE 2
                END,
                seg.created_at DESC,
                seg.rowid DESC
            """
            params = (orientation,)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT seg.*
                FROM material_segments seg
                JOIN material_raw_files raw
                  ON raw.id = seg.raw_file_id
                WHERE seg.status = 'ready'
                  AND seg.deleted_at IS NULL
                  AND raw.deleted_at IS NULL
                ORDER BY {order_by}
                """,
                params,
            ).fetchall()
        return [self._material_segment_from_row(row) for row in rows]

    def mark_material_raw_file_deleted(self, raw_file_id: str, deleted_at: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE material_raw_files
                SET deleted_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (deleted_at, deleted_at, raw_file_id),
            )

    def mark_material_segments_deleted(self, raw_file_id: str, deleted_at: str) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """
                UPDATE material_segments
                SET deleted_at = ?, updated_at = ?
                WHERE raw_file_id = ?
                  AND deleted_at IS NULL
                """,
                (deleted_at, deleted_at, raw_file_id),
            )
        return cursor.rowcount

    def material_library_summary(self) -> dict[str, Any]:
        with self.connect() as connection:
            raw_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM material_raw_files WHERE deleted_at IS NULL"
                ).fetchone()[0]
            )
            segment_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM material_segments WHERE deleted_at IS NULL"
                ).fetchone()[0]
            )
            orientation_counts = {
                row["orientation"] or "unknown": row["count"]
                for row in connection.execute(
                    """
                    SELECT COALESCE(orientation, 'unknown') AS orientation, COUNT(*) AS count
                    FROM material_segments
                    WHERE deleted_at IS NULL
                    GROUP BY COALESCE(orientation, 'unknown')
                    """
                ).fetchall()
            }
            failed_count = int(
                connection.execute(
                    """
                    SELECT
                        COALESCE((
                            SELECT COUNT(*) FROM material_raw_files
                            WHERE deleted_at IS NULL AND status = 'failed'
                        ), 0)
                        +
                        COALESCE((
                            SELECT COUNT(*) FROM material_segments
                            WHERE deleted_at IS NULL AND status = 'failed'
                        ), 0)
                    """
                ).fetchone()[0]
            )
            totals = {
                "raw": raw_count,
                "segments": segment_count,
                "portrait": int(orientation_counts.get("portrait", 0)),
                "landscape": int(orientation_counts.get("landscape", 0)),
                "square": int(orientation_counts.get("square", 0)),
                "unknown": int(orientation_counts.get("unknown", 0)),
                "failed": failed_count,
            }
            for prefix, column, table in (
                ("raw_asr", "asr_status", "material_raw_files"),
                ("raw_ocr", "ocr_status", "material_raw_files"),
                ("raw_vision", "vision_status", "material_raw_files"),
                ("raw_embedding", "embedding_status", "material_raw_files"),
                ("segment_content_label", "content_label_status", "material_segments"),
                ("segment_embedding", "embedding_status", "material_segments"),
            ):
                rows = connection.execute(
                    f"""
                    SELECT COALESCE({column}, 'unknown') AS status, COUNT(*) AS count
                    FROM {table}
                    WHERE deleted_at IS NULL
                    GROUP BY COALESCE({column}, 'unknown')
                    """
                ).fetchall()
                for row in rows:
                    totals[f"{prefix}_{row['status']}"] = row["count"]
        return totals

    def delete_local_segment_materials(self, segment_ids: list[str]) -> int:
        if not segment_ids:
            return 0
        placeholders = ", ".join("?" for _ in segment_ids)
        with self.connect() as connection:
            cursor = connection.execute(
                f"""
                DELETE FROM materials
                WHERE source_type = 'local_segment'
                  AND source_provider = 'local_material_worker'
                  AND source_asset_id IN ({placeholders})
                """,
                tuple(segment_ids),
            )
        return cursor.rowcount

    def list_tasks(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM tasks
                ORDER BY created_at DESC, rowid DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def output_path_for(self, task_id: str) -> Path | None:
        task = self.get_task(task_id)
        if not task:
            return None
        output_path = Path(task["output"]["path"])
        try:
            output_path.resolve().relative_to(self.paths.outputs.resolve())
        except ValueError:
            return None
        return output_path

    def _ensure_schema(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS materials (
                    id TEXT PRIMARY KEY,
                    original_filename TEXT NOT NULL,
                    content_type TEXT,
                    size_bytes INTEGER NOT NULL,
                    storage_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    source_type TEXT,
                    source_provider TEXT,
                    source_asset_id TEXT,
                    source_url TEXT,
                    license_note TEXT,
                    query TEXT
                )
                """
            )
            self._ensure_columns(connection, "materials", MATERIAL_SOURCE_COLUMNS)
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    material_ids TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    output_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS material_source_configs (
                    id TEXT PRIMARY KEY,
                    allowed_root_id TEXT NOT NULL,
                    allowed_root_alias TEXT NOT NULL,
                    source_relative_path TEXT NOT NULL,
                    source_display_path TEXT NOT NULL,
                    source_path_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_summary TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS material_index_jobs (
                    id TEXT PRIMARY KEY,
                    source_config_id TEXT NOT NULL,
                    allowed_root_id TEXT NOT NULL,
                    source_relative_path TEXT NOT NULL,
                    source_path_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress_current INTEGER NOT NULL DEFAULT 0,
                    progress_total INTEGER NOT NULL DEFAULT 0,
                    raw_files_total INTEGER NOT NULL DEFAULT 0,
                    segments_total INTEGER NOT NULL DEFAULT 0,
                    failed_total INTEGER NOT NULL DEFAULT 0,
                    heartbeat_at TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    error_summary TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_material_index_jobs_active_source
                ON material_index_jobs (allowed_root_id, source_path_hash)
                WHERE status IN ('queued', 'running')
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS material_raw_files (
                    id TEXT PRIMARY KEY,
                    source_config_id TEXT,
                    allowed_root_id TEXT NOT NULL,
                    source_relative_path TEXT NOT NULL,
                    source_path_hash TEXT NOT NULL,
                    source_display_path TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    managed_raw_relative_path TEXT NOT NULL,
                    content_hash TEXT,
                    size_bytes INTEGER NOT NULL,
                    duration_seconds REAL,
                    orientation TEXT,
                    status TEXT NOT NULL,
                    error_summary TEXT,
                    asr_status TEXT NOT NULL DEFAULT 'not_configured',
                    ocr_status TEXT NOT NULL DEFAULT 'not_configured',
                    vision_status TEXT NOT NULL DEFAULT 'not_configured',
                    embedding_status TEXT NOT NULL DEFAULT 'not_configured',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS material_segments (
                    id TEXT PRIMARY KEY,
                    raw_file_id TEXT NOT NULL,
                    managed_segment_relative_path TEXT NOT NULL,
                    start_seconds REAL NOT NULL,
                    duration_seconds REAL NOT NULL,
                    orientation TEXT,
                    status TEXT NOT NULL,
                    match_text TEXT,
                    asr_text TEXT,
                    ocr_text TEXT,
                    vision_description TEXT,
                    content_label_status TEXT NOT NULL DEFAULT 'not_configured',
                    embedding_status TEXT NOT NULL DEFAULT 'not_configured',
                    error_summary TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT
                )
                """
            )

    @staticmethod
    def _ensure_columns(
        connection: sqlite3.Connection,
        table: str,
        columns: dict[str, str],
    ) -> None:
        existing = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for column, definition in columns.items():
            if column not in existing:
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                )

    @staticmethod
    def _now_isoformat() -> str:
        from datetime import UTC, datetime

        return datetime.now(UTC).isoformat()

    @staticmethod
    def _material_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "original_filename": row["original_filename"],
            "content_type": row["content_type"],
            "size_bytes": row["size_bytes"],
            "storage_path": row["storage_path"],
            "created_at": row["created_at"],
            "source_type": row["source_type"] or "upload",
            "source_provider": row["source_provider"],
            "source_asset_id": row["source_asset_id"],
            "source_url": row["source_url"],
            "license_note": row["license_note"],
            "query": row["query"],
        }

    @staticmethod
    def _task_from_row(row: sqlite3.Row) -> dict[str, Any]:
        task_id = row["id"]
        return {
            "id": task_id,
            "title": row["title"],
            "status": row["status"],
            "material_ids": json.loads(row["material_ids"]),
            "options": json.loads(row["options_json"]),
            "output": {
                "path": row["output_path"],
                "download_url": f"/api/tasks/{task_id}/output",
            },
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _material_source_config_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "allowed_root_id": row["allowed_root_id"],
            "allowed_root_alias": row["allowed_root_alias"],
            "source_relative_path": row["source_relative_path"],
            "source_display_path": row["source_display_path"],
            "source_path_hash": row["source_path_hash"],
            "status": row["status"],
            "error_summary": row["error_summary"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _material_raw_file_from_row(row: sqlite3.Row) -> dict[str, Any]:
        payload = {
            "id": row["id"],
            "source_config_id": row["source_config_id"],
            "allowed_root_id": row["allowed_root_id"],
            "source_relative_path": row["source_relative_path"],
            "source_path_hash": row["source_path_hash"],
            "source_display_path": row["source_display_path"],
            "original_filename": row["original_filename"],
            "managed_raw_relative_path": row["managed_raw_relative_path"],
            "content_hash": row["content_hash"],
            "size_bytes": row["size_bytes"],
            "duration_seconds": row["duration_seconds"],
            "orientation": row["orientation"],
            "status": row["status"],
            "error_summary": row["error_summary"],
            "asr_status": row["asr_status"],
            "ocr_status": row["ocr_status"],
            "vision_status": row["vision_status"],
            "embedding_status": row["embedding_status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "deleted_at": row["deleted_at"],
        }
        if "segments" in row.keys():
            payload["segments"] = row["segments"]
        return payload

    @staticmethod
    def _material_segment_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "raw_file_id": row["raw_file_id"],
            "managed_segment_relative_path": row["managed_segment_relative_path"],
            "start_seconds": row["start_seconds"],
            "duration_seconds": row["duration_seconds"],
            "orientation": row["orientation"],
            "status": row["status"],
            "match_text": row["match_text"],
            "asr_text": row["asr_text"],
            "ocr_text": row["ocr_text"],
            "vision_description": row["vision_description"],
            "content_label_status": row["content_label_status"],
            "embedding_status": row["embedding_status"],
            "error_summary": row["error_summary"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "deleted_at": row["deleted_at"],
        }

    @staticmethod
    def _material_index_job_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "source_config_id": row["source_config_id"],
            "allowed_root_id": row["allowed_root_id"],
            "source_relative_path": row["source_relative_path"],
            "source_path_hash": row["source_path_hash"],
            "status": row["status"],
            "stage": row["stage"],
            "progress_current": row["progress_current"],
            "progress_total": row["progress_total"],
            "raw_files_total": row["raw_files_total"],
            "segments_total": row["segments_total"],
            "failed_total": row["failed_total"],
            "heartbeat_at": row["heartbeat_at"],
            "attempt_count": row["attempt_count"],
            "error_summary": row["error_summary"],
            "created_at": row["created_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
        }
