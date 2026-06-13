from pathlib import Path


def test_env_example_contains_only_documented_autovideo_keys() -> None:
    content = Path(".env.example").read_text(encoding="utf-8")

    assert "AUTOVIDEO_DATA_DIR=./data" in content
    assert "AUTOVIDEO_FFMPEG_PATH=ffmpeg" in content
    assert "AUTOVIDEO_FISH_SPEECH_URL=" in content
    forbidden = ["sk-", "akia", "password=", "token=", "secret="]
    for text in forbidden:
        assert text not in content.lower()


def test_dockerfile_installs_ffmpeg_and_runs_autovideo() -> None:
    content = Path("Dockerfile").read_text(encoding="utf-8")

    assert "node:20" in content
    assert "python:3.12-slim" in content
    assert "npm ci" in content
    assert "npm run build" in content
    assert "frontend/dist" in content
    assert "ffmpeg" in content
    assert 'CMD ["python", "-m", "autovideo.main"]' in content


def test_dockerignore_excludes_local_build_and_dependency_outputs() -> None:
    content = Path(".dockerignore").read_text(encoding="utf-8")

    assert "frontend/node_modules/" in content
    assert "frontend/dist/" in content


def test_dev_script_runs_from_repo_root_and_supports_python_bin() -> None:
    content = Path("scripts/dev.sh").read_text(encoding="utf-8")

    assert 'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' in content
    assert 'REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"' in content
    assert 'cd "${REPO_ROOT}"' in content
    assert '"${PYTHON_BIN:-python}" -m autovideo.main' in content


def test_readme_documents_phase_one_startup() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "阶段 1：产品骨架" in content
    assert "React + Vite" in content
    assert "npm install" in content
    assert "npm run build" in content
    assert "python -m autovideo.main" in content
    assert "docker build -t autovideo ." in content
    assert "AGPL-3.0-only" in content
