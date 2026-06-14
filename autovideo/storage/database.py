from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from autovideo.core.paths import ensure_data_dirs
from autovideo.core.settings import Settings


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
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO materials (
                    id, original_filename, content_type, size_bytes,
                    storage_path, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    material["id"],
                    material["original_filename"],
                    material["content_type"],
                    material["size_bytes"],
                    material["storage_path"],
                    material["created_at"],
                ),
            )
        return material

    def list_materials(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM materials ORDER BY created_at DESC"
            ).fetchall()
        return [self._material_from_row(row) for row in rows]

    def get_material(self, material_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM materials WHERE id = ?",
                (material_id,),
            ).fetchone()
        return self._material_from_row(row) if row else None

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

    def list_tasks(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC"
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
                    created_at TEXT NOT NULL
                )
                """
            )
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

    @staticmethod
    def _material_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "original_filename": row["original_filename"],
            "content_type": row["content_type"],
            "size_bytes": row["size_bytes"],
            "storage_path": row["storage_path"],
            "created_at": row["created_at"],
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
