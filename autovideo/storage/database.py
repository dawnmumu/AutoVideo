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
