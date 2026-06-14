from pathlib import Path

from autovideo.core.paths import DATA_SUBDIRS, build_data_paths, ensure_data_dirs
from autovideo.core.settings import Settings


def test_data_subdirs_match_product_design() -> None:
    assert DATA_SUBDIRS == (
        "materials",
        "bgm",
        "voices",
        "subtitle_templates",
        "outputs",
        "tasks",
    )


def test_build_data_paths_returns_absolute_paths(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)

    paths = build_data_paths(settings)

    assert paths.root == tmp_path
    assert paths.materials == tmp_path / "materials"
    assert paths.bgm == tmp_path / "bgm"
    assert paths.voices == tmp_path / "voices"
    assert paths.subtitle_templates == tmp_path / "subtitle_templates"
    assert paths.outputs == tmp_path / "outputs"
    assert paths.tasks == tmp_path / "tasks"


def test_ensure_data_dirs_creates_all_directories(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path)

    paths = ensure_data_dirs(settings)

    for name in ("root", *DATA_SUBDIRS):
        path = getattr(paths, name)
        assert isinstance(path, Path)
        assert path.exists()
        assert path.is_dir()
