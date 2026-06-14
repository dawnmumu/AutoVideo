from dataclasses import dataclass
from pathlib import Path

from autovideo.core.settings import Settings

DATA_SUBDIRS = (
    "materials",
    "bgm",
    "voices",
    "subtitle_templates",
    "outputs",
    "tasks",
)


@dataclass(frozen=True)
class DataPaths:
    root: Path
    materials: Path
    bgm: Path
    voices: Path
    subtitle_templates: Path
    outputs: Path
    tasks: Path


def build_data_paths(settings: Settings) -> DataPaths:
    root = settings.resolved_data_dir
    return DataPaths(
        root=root,
        materials=root / "materials",
        bgm=root / "bgm",
        voices=root / "voices",
        subtitle_templates=root / "subtitle_templates",
        outputs=root / "outputs",
        tasks=root / "tasks",
    )


def ensure_data_dirs(settings: Settings) -> DataPaths:
    paths = build_data_paths(settings)
    for path in (
        paths.root,
        paths.materials,
        paths.bgm,
        paths.voices,
        paths.subtitle_templates,
        paths.outputs,
        paths.tasks,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return paths
