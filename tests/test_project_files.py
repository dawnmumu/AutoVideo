import json
import stat
from pathlib import Path

import pytest


FORBIDDEN_ENV_EXAMPLE_MARKERS = ("sk-", "akia", "password=")
SENSITIVE_ENV_KEY_SUFFIXES = ("KEY", "SECRET", "TOKEN")


def _env_example_assignments(content: str) -> list[tuple[str, str]]:
    assignments: list[tuple[str, str]] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        assignments.append((key.strip(), value.strip()))

    return assignments


def _is_sensitive_placeholder_key(key: str) -> bool:
    return key.upper().split("_")[-1] in SENSITIVE_ENV_KEY_SUFFIXES


def _assert_env_example_contains_no_credentials(content: str) -> None:
    lowered_content = content.lower()
    for marker in FORBIDDEN_ENV_EXAMPLE_MARKERS:
        assert marker not in lowered_content

    for key, value in _env_example_assignments(content):
        if _is_sensitive_placeholder_key(key):
            assert value == "", f"{key} must be empty in .env.example"


def test_env_example_contains_only_documented_autovideo_keys() -> None:
    content = Path(".env.example").read_text(encoding="utf-8")

    assert "AUTOVIDEO_DATA_DIR=./data" in content
    assert "AUTOVIDEO_FFMPEG_PATH=ffmpeg" in content
    assert "AUTOVIDEO_FISH_SPEECH_URL=" in content
    _assert_env_example_contains_no_credentials(content)


def _env_line(key: str, value: str = "") -> str:
    return f"{key}={value}"


def test_env_example_guard_allows_empty_secret_placeholders() -> None:
    llm_api_key = "AUTOVIDEO_LLM_API_" + "KEY"
    candidate_token_secret = "AUTOVIDEO_CANDIDATE_TOKEN_" + "SECRET"
    content = "\n".join(
        [
            _env_line(llm_api_key),
            _env_line(candidate_token_secret),
            _env_line("AUTOVIDEO_CANDIDATE_TOKEN_TTL_SECONDS", "1800"),
        ]
    )

    _assert_env_example_contains_no_credentials(content)


@pytest.mark.parametrize(
    "content",
    [
        _env_line("AUTOVIDEO_LLM_API_" + "KEY", "synthetic-value"),
        _env_line("AUTOVIDEO_CANDIDATE_TOKEN_" + "SECRET", "synthetic-value"),
        _env_line("AUTOVIDEO_ACCESS_TOKEN", "synthetic-value"),
        _env_line("AUTOVIDEO_OPENAI_API_" + "KEY", "synthetic-value"),
    ],
)
def test_env_example_guard_rejects_filled_secret_placeholders(content: str) -> None:
    with pytest.raises(AssertionError):
        _assert_env_example_contains_no_credentials(content)


def test_dockerfile_installs_ffmpeg_and_runs_autovideo() -> None:
    content = Path("Dockerfile").read_text(encoding="utf-8")

    assert "ARG NODE_IMAGE=node:22-bookworm-slim" in content
    assert "ARG PYTHON_IMAGE=python:3.12-slim" in content
    assert "node:22" in content
    assert "python:3.12-slim" in content
    assert "npm ci" in content
    assert "npm run build" in content
    assert "fonts-noto-cjk" in content
    assert "frontend/dist" in content
    assert "COPY --from=frontend-builder /frontend/dist ./frontend/dist" in content
    assert "ffmpeg" in content
    assert 'CMD ["python", "-m", "autovideo.main"]' in content


def test_dockerfile_supports_optional_build_mirrors() -> None:
    content = Path("Dockerfile").read_text(encoding="utf-8")

    for build_arg in [
        "NPM_REGISTRY",
        "APT_DEBIAN_MIRROR",
        "APT_SECURITY_MIRROR",
        "PIP_INDEX_URL",
        "PIP_TRUSTED_HOST",
    ]:
        assert f'ARG {build_arg}=""' in content

    assert "npm config set registry" in content
    assert "deb.debian.org/debian" in content
    assert "deb.debian.org/debian-security" in content
    security_sed_marker = "s|http://deb.debian.org/debian-security|"
    debian_sed_marker = "s|http://deb.debian.org/debian|"
    assert content.index(security_sed_marker) < content.index(debian_sed_marker)
    assert "--index-url" in content
    assert "--trusted-host" in content


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


def test_review_process_docs_do_not_restore_legacy_pr_monitoring_rules() -> None:
    checked_paths = [
        Path("docs/superpowers/plans/2026-06-14-online-free-remix-script.md"),
        Path("docs/superpowers/specs/2026-06-14-online-free-remix-script-design.md"),
    ]
    forbidden_phrases = [
        "每隔 2 分钟",
        "2 分钟 Codex review 监控",
        "thumbs up",
        "thumbs-up",
        "GitHub Codex review 监控",
        "GitHub Codex PR review monitoring",
        "monitor Codex review every 2 minutes",
        "用于通知或触发 Codex 复查",
    ]

    for path in checked_paths:
        content = path.read_text(encoding="utf-8")
        for phrase in forbidden_phrases:
            assert phrase not in content, f"{phrase!r} must not appear in {path}"


def test_readme_documents_current_startup() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "阶段 2：脚本生成 + 线上免费素材 manifest 混剪" in content
    assert "React + Vite" in content
    assert "Node.js 20.19+ 或 22.12+" in content
    assert "npm install" in content
    assert "npm run build" in content
    assert "python -m autovideo.main" in content
    assert "docker build -t autovideo ." in content
    assert "NPM_REGISTRY=https://registry.npmmirror.com" in content
    assert "APT_DEBIAN_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian" in content
    assert "PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple" in content
    assert "PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn" in content
    assert "`PIP_TRUSTED_HOST` 是可选参数" in content
    assert "只传 `PIP_INDEX_URL` 也支持构建" in content
    assert "docker run --rm -p 8090:8090" in content
    assert "POST /api/materials" in content
    assert "POST /api/tasks" in content
    assert "source_type" in content
    assert "storage_path" in content
    assert "manifest" in content
    assert "POST /api/scripts/generate" in content
    assert "GET /api/online-materials/status" in content
    assert "POST /api/online-materials/search" in content
    assert "POST /api/online-materials/download" in content
    assert "POST /api/online-mix/tasks" in content
    assert "default_provider" in content
    assert "candidate_token_secret_configured" in content
    assert "enabled" in content
    assert "candidate_token" in content
    assert "ONLINE_MATERIAL_SEARCH_FAILED" in content
    assert "ONLINE_MATERIAL_REDIRECT_NOT_ALLOWED" in content
    assert "ONLINE_MATERIAL_TOO_LARGE" in content
    assert "provider" in content
    assert "LLM_GENERATION_FAILED" in content
    assert "SCRIPT_PAYLOAD_TOO_LARGE" in content
    assert "GET /api/tasks/{task_id}/output" in content
    assert "AUTOVIDEO_DATA_DIR" in content
    assert "AUTOVIDEO_FFMPEG_PATH" in content
    assert "AUTOVIDEO_MAX_UPLOAD_BYTES" in content
    assert "AUTOVIDEO_FISH_SPEECH_URL" in content
    assert "AUTOVIDEO_LLM_PROVIDER" in content
    assert "AUTOVIDEO_LLM_BASE_URL" in content
    assert "AUTOVIDEO_LLM_API_KEY" in content
    assert "AUTOVIDEO_LLM_MODEL" in content
    assert "AUTOVIDEO_PEXELS_API_KEY" in content
    assert "AUTOVIDEO_PIXABAY_API_KEY" in content
    assert "AUTOVIDEO_ONLINE_MATERIAL_PROVIDER" in content
    assert "AUTOVIDEO_CANDIDATE_TOKEN_SECRET" in content
    assert "AUTOVIDEO_CANDIDATE_TOKEN_TTL_SECONDS" in content
    assert "AUTOVIDEO_MAX_SCRIPT_PAYLOAD_BYTES" in content
    assert "AUTOVIDEO_MAX_ONLINE_MIX_REQUEST_BYTES" in content
    assert "尚未接入登录" in content
    assert "权限管理" in content
    assert "个人网盘导入" in content
    assert "真实混剪渲染" in content
    assert "AGPL-3.0-only" in content
