from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autovideo.storage.database import AutoVideoStore

ROOT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class MaterialSourceRootNotConfiguredError(Exception):
    pass


class MaterialSourceRootNotFoundError(Exception):
    pass


class MaterialSourceNotFoundError(Exception):
    pass


class MaterialSourceInvalidPathError(Exception):
    pass


class MaterialSourceNotDirectoryError(Exception):
    pass


class MaterialSourcePathOutOfScopeError(Exception):
    pass


@dataclass(frozen=True)
class AllowedMaterialRoot:
    id: str
    alias: str
    display_name: str
    resolved_path: Path


@dataclass(frozen=True)
class ResolvedMaterialSource:
    allowed_root: AllowedMaterialRoot
    source_relative_path: str
    source_display_path: str
    source_path_hash: str
    resolved_path: Path


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise MaterialSourcePathOutOfScopeError() from exc
    return "." if str(relative) == "." else relative.as_posix()


def _hash_source_identity(source_relative_path: str) -> str:
    return hashlib.sha256(source_relative_path.encode("utf-8")).hexdigest()


def _public_allowed_root(root: AllowedMaterialRoot) -> dict[str, str]:
    return {
        "id": root.id,
        "alias": root.alias,
        "display_name": root.display_name,
    }


def _parse_allowed_roots(raw: str | None) -> list[AllowedMaterialRoot]:
    if raw is None or raw.strip() == "":
        return []

    roots: list[AllowedMaterialRoot] = []
    seen_ids: set[str] = set()
    for entry in raw.split(";"):
        candidate = entry.strip()
        if not candidate or "=" not in candidate:
            continue
        root_id, root_path = (part.strip() for part in candidate.split("=", 1))
        if (
            not ROOT_ID_RE.fullmatch(root_id)
            or root_id in seen_ids
            or root_path == ""
        ):
            continue
        try:
            resolved_path = Path(root_path).expanduser().resolve(strict=True)
        except (OSError, RuntimeError, ValueError):
            continue
        if not resolved_path.is_dir() or not os.access(resolved_path, os.R_OK | os.X_OK):
            continue
        seen_ids.add(root_id)
        roots.append(
            AllowedMaterialRoot(
                id=root_id,
                alias=root_id,
                display_name=root_id,
                resolved_path=resolved_path,
            )
        )
    return roots


class MaterialSourceService:
    def __init__(self, store: AutoVideoStore) -> None:
        self.store = store

    def allowed_roots(self) -> list[AllowedMaterialRoot]:
        roots = _parse_allowed_roots(self.store.settings.material_allowed_roots)
        if not roots:
            raise MaterialSourceRootNotConfiguredError()
        return roots

    def resolve_source(
        self,
        allowed_root_id: str,
        source_path: str,
    ) -> ResolvedMaterialSource:
        allowed_root = next(
            (root for root in self.allowed_roots() if root.id == allowed_root_id),
            None,
        )
        if allowed_root is None:
            raise MaterialSourceRootNotFoundError()

        if source_path == "":
            raise MaterialSourceInvalidPathError()
        try:
            requested_path = Path(source_path)
        except ValueError as exc:
            raise MaterialSourceInvalidPathError() from exc
        if requested_path.is_absolute():
            raise MaterialSourcePathOutOfScopeError()

        try:
            resolved_path = (allowed_root.resolved_path / requested_path).resolve(
                strict=True
            )
        except FileNotFoundError as exc:
            raise MaterialSourceNotFoundError() from exc
        except PermissionError as exc:
            raise MaterialSourceNotDirectoryError() from exc
        except ValueError as exc:
            raise MaterialSourceInvalidPathError() from exc

        source_relative_path = _relative_to_root(resolved_path, allowed_root.resolved_path)
        if not resolved_path.is_dir() or not os.access(resolved_path, os.R_OK | os.X_OK):
            raise MaterialSourceNotDirectoryError()
        source_display_path = allowed_root.id
        if source_relative_path != ".":
            source_display_path = f"{allowed_root.id}/{source_relative_path}"

        return ResolvedMaterialSource(
            allowed_root=allowed_root,
            source_relative_path=source_relative_path,
            source_display_path=source_display_path,
            source_path_hash=_hash_source_identity(source_relative_path),
            resolved_path=resolved_path,
        )

    def save_current_source(
        self,
        allowed_root_id: str,
        source_path: str,
    ) -> dict[str, Any]:
        resolved_source = self.resolve_source(allowed_root_id, source_path)
        now = datetime.now(UTC).isoformat()
        return self.store.insert_material_source_config(
            {
                "id": uuid.uuid4().hex,
                "allowed_root_id": resolved_source.allowed_root.id,
                "allowed_root_alias": resolved_source.allowed_root.alias,
                "source_relative_path": resolved_source.source_relative_path,
                "source_display_path": resolved_source.source_display_path,
                "source_path_hash": resolved_source.source_path_hash,
                "status": "active",
                "error_summary": None,
                "created_at": now,
                "updated_at": now,
            }
        )

    def status(self) -> dict[str, Any]:
        current_source = self.store.current_material_source_config()
        try:
            allowed_roots = self.allowed_roots()
        except MaterialSourceRootNotConfiguredError:
            return {
                "configured": False,
                "allowed_roots": [],
                "current_source": current_source,
                "error_summary": "material source roots are not configured",
            }
        return {
            "configured": True,
            "allowed_roots": [_public_allowed_root(root) for root in allowed_roots],
            "current_source": current_source,
            "error_summary": None,
        }
