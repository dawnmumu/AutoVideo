from pathlib import Path

import pytest

from autovideo.core.settings import Settings
from autovideo.services.material_sources import (
    MaterialSourceNotFoundError,
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


def test_resolve_source_rejects_missing_child(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    service = _service(tmp_path, f"demo={root}")

    with pytest.raises(MaterialSourceNotFoundError):
        service.resolve_source("demo", "missing")
