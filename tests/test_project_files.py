import json
import stat
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

    assert "node:22" in content
    assert "python:3.12-slim" in content
    assert "npm ci" in content
    assert "npm run build" in content
    assert "fonts-noto-cjk" in content
    assert "frontend/dist" in content
    assert "COPY --from=frontend-builder /frontend/dist ./frontend/dist" in content
    assert "ffmpeg" in content
    assert 'CMD ["python", "-m", "autovideo.main"]' in content


def test_frontend_package_declares_supported_node_runtime() -> None:
    package = json.loads(Path("frontend/package.json").read_text(encoding="utf-8"))
    lockfile = json.loads(Path("frontend/package-lock.json").read_text(encoding="utf-8"))

    assert package["engines"]["node"] == "^20.19.0 || >=22.12.0"
    assert lockfile["packages"][""]["engines"]["node"] == package["engines"]["node"]
    assert package["devDependencies"]["vite"].startswith("^8.")


def test_dockerignore_excludes_local_build_and_dependency_outputs() -> None:
    content = Path(".dockerignore").read_text(encoding="utf-8")

    required_patterns = [
        ".git",
        ".env",
        ".env.*",
        "!.env.example",
        ".venv/",
        "venv/",
        "__pycache__/",
        ".pytest_cache/",
        ".ruff_cache/",
        ".mypy_cache/",
        "data/",
        "outputs/",
        "frontend/node_modules/",
        "frontend/dist/",
        "*.log",
    ]
    for pattern in required_patterns:
        assert pattern in content


def test_dev_script_runs_from_repo_root_and_supports_python_bin() -> None:
    script_path = Path("scripts/dev.sh")
    content = script_path.read_text(encoding="utf-8")

    assert 'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' in content
    assert 'REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"' in content
    assert 'cd "${REPO_ROOT}"' in content
    assert "AUTOVIDEO_HOST:-0.0.0.0" in content
    assert "AUTOVIDEO_PORT:-8090" in content
    assert "AUTOVIDEO_DATA_DIR:-./data" in content
    assert '"${PYTHON_BIN:-python}" -m autovideo.main' in content
    assert script_path.stat().st_mode & stat.S_IXUSR


def test_readme_documents_phase_one_startup() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "阶段 1：产品骨架" in content
    assert "React + Vite" in content
    assert "Node.js 20.19+ 或 22.12+" in content
    assert "npm install" in content
    assert "npm run build" in content
    assert "python -m autovideo.main" in content
    assert "docker build -t autovideo ." in content
    assert "docker run --rm -p 8090:8090" in content
    assert "AUTOVIDEO_DATA_DIR" in content
    assert "AUTOVIDEO_FFMPEG_PATH" in content
    assert "AUTOVIDEO_FISH_SPEECH_URL" in content
    assert "尚未接入登录" in content
    assert "权限管理" in content
    assert "个人网盘导入" in content
    assert "真实混剪渲染" in content
    assert "AGPL-3.0-only" in content
