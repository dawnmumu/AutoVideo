from pathlib import Path

import pytest

from autovideo.core.settings import Settings
from autovideo.services.material_sources import (
    MaterialSourceInvalidPathError,
    MaterialSourceNotFoundError,
    MaterialSourceNotDirectoryError,
    MaterialSourcePathOutOfScopeError,
    MaterialSourceRootNotConfiguredError,
    MaterialSourceService,
)
from autovideo.storage.database import AutoVideoStore


def _service(tmp_path: Path, roots: str | None) -> MaterialSourceService:
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        material_allowed_roots=roots,
    )
    return MaterialSourceService(AutoVideoStore(settings))


def test_allowed_roots_redacts_absolute_paths(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    service = _service(tmp_path, f"demo={root}")

    payload = service.status()

    assert payload["allowed_roots"] == [
        {"id": "demo", "alias": "demo", "display_name": "demo"}
    ]
    assert str(root) not in str(payload)


def test_status_reports_not_configured_without_throwing(tmp_path: Path) -> None:
    service = _service(tmp_path, None)

    payload = service.status()

    assert payload["configured"] is False
    assert payload["allowed_roots"] == []
    assert payload["current_source"] is None
    assert payload["error_summary"] == "material source roots are not configured"


def test_status_skips_invalid_root_config_without_crashing(tmp_path: Path) -> None:
    service = _service(tmp_path, "demo=bad\0root")

    payload = service.status()

    assert payload["configured"] is False
    assert payload["allowed_roots"] == []
    assert payload["current_source"] is None
    assert payload["error_summary"] == "material source roots are not configured"


def test_empty_root_path_is_skipped_and_does_not_use_cwd(tmp_path: Path) -> None:
    service = _service(tmp_path, "demo=")

    payload = service.status()

    assert payload["configured"] is False
    assert payload["allowed_roots"] == []
    assert payload["current_source"] is None
    assert payload["error_summary"] == "material source roots are not configured"

    with pytest.raises(MaterialSourceRootNotConfiguredError):
        service.allowed_roots()


def test_resolve_source_rejects_missing_roots(tmp_path: Path) -> None:
    service = _service(tmp_path, None)

    with pytest.raises(MaterialSourceRootNotConfiguredError):
        service.allowed_roots()


def test_resolve_source_rejects_path_escape_and_absolute_input(tmp_path: Path) -> None:
    root = tmp_path / "source"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    service = _service(tmp_path, f"demo={root}")

    with pytest.raises(MaterialSourcePathOutOfScopeError):
        service.resolve_source("demo", "../outside")

    with pytest.raises(MaterialSourcePathOutOfScopeError):
        service.resolve_source("demo", str(outside))


def test_resolve_source_rejects_empty_and_illegal_paths(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    service = _service(tmp_path, f"demo={root}")

    with pytest.raises(MaterialSourceInvalidPathError):
        service.resolve_source("demo", "")

    with pytest.raises(MaterialSourceInvalidPathError):
        service.resolve_source("demo", "bad\0path")


def test_resolve_source_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "source"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)
    service = _service(tmp_path, f"demo={root}")

    with pytest.raises(MaterialSourcePathOutOfScopeError):
        service.resolve_source("demo", "escape")


def test_save_current_source_stores_relative_identity_only(tmp_path: Path) -> None:
    root = tmp_path / "source"
    child = root / "clips"
    child.mkdir(parents=True)
    service = _service(tmp_path, f"demo={root}")

    config = service.save_current_source("demo", "clips")

    assert config["allowed_root_id"] == "demo"
    assert config["source_relative_path"] == "clips"
    assert config["source_display_path"] == "demo/clips"
    assert str(root) not in str(config)
    assert len(config["source_path_hash"]) == 64


def test_resolve_source_requires_readable_directory(tmp_path: Path) -> None:
    root = tmp_path / "source"
    child = root / "clips"
    root.mkdir()
    child.mkdir()
    service = _service(tmp_path, f"demo={root}")

    resolved = service.resolve_source("demo", "clips")

    assert resolved.source_relative_path == "clips"


def test_resolve_source_rejects_files_and_unreadable_directories(tmp_path: Path) -> None:
    root = tmp_path / "source"
    file_path = root / "clip.mp4"
    locked = root / "locked"
    root.mkdir()
    file_path.write_text("demo", encoding="utf-8")
    locked.mkdir()
    locked.chmod(0)
    service = _service(tmp_path, f"demo={root}")

    try:
        with pytest.raises(MaterialSourceNotDirectoryError):
            service.resolve_source("demo", "clip.mp4")

        with pytest.raises(MaterialSourceNotDirectoryError):
            service.resolve_source("demo", "locked")
    finally:
        locked.chmod(0o755)


def test_resolve_source_maps_permission_error_from_resolve_to_domain_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    locked = root / "locked"
    child = locked / "child"
    root.mkdir()
    locked.mkdir()
    service = _service(tmp_path, f"demo={root}")
    original_resolve = Path.resolve

    def fake_resolve(self: Path, strict: bool = False) -> Path:
        if self == child and strict:
            raise PermissionError("permission denied")
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", fake_resolve)

    with pytest.raises(MaterialSourceNotDirectoryError):
        service.resolve_source("demo", "locked/child")


def test_resolve_source_rejects_missing_child(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    service = _service(tmp_path, f"demo={root}")

    with pytest.raises(MaterialSourceNotFoundError):
        service.resolve_source("demo", "missing")


def test_save_current_source_replaces_older_active_config(tmp_path: Path) -> None:
    root = tmp_path / "source"
    first = root / "clips-a"
    second = root / "clips-b"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    service = _service(tmp_path, f"demo={root}")

    older = service.save_current_source("demo", "clips-a")
    newer = service.save_current_source("demo", "clips-b")

    older_row = service.store.get_material_source_config(older["id"])
    current = service.store.current_material_source_config()

    assert older_row is not None
    assert older_row["status"] == "inactive"
    assert current is not None
    assert current["id"] == newer["id"]
    assert current["status"] == "active"
    assert current["source_relative_path"] == "clips-b"
