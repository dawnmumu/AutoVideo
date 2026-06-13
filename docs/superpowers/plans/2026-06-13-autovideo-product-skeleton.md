# AutoVideo Product Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first runnable AutoVideo skeleton: FastAPI service, static Chinese workbench shell, configuration, data directory layout, runtime dependency checks, local launch, Docker launch, and tests.

**Architecture:** This plan implements only Phase 1 from the product redesign spec. The backend is a small FastAPI application split into `api`, `core`, and `web` packages. Resource-center features and real video rendering stay out of this plan; later plans will attach BGM, subtitle, voice, and mix-task modules to this skeleton.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Pydantic Settings, Pytest, HTTPX/TestClient, static HTML/CSS/JavaScript, Docker with FFmpeg.

---

## Scope

This plan covers:

- Package structure and Python project metadata.
- Environment-based configuration with no real credentials.
- Data directory creation for materials, BGM, voices, subtitle templates, outputs, and tasks.
- Runtime dependency checks for FFmpeg and optional Fish Speech configuration.
- FastAPI app factory, health endpoint, root static page, static assets.
- Chinese UI shell with desktop and mobile layout.
- Local development script, Dockerfile, `.env.example`, `.gitignore`, README updates.
- Tests for the skeleton.

This plan does not implement:

- BGM upload or category APIs.
- Subtitle template editing or ASS rendering.
- Edge TTS or Fish Speech voice operations.
- Video mix task creation or FFmpeg rendering.
- Login, permission management, personal netdisk import, NAS login state.

## Implementation Setup

- [ ] **Step 1: Ensure Pytest is available before the first red test**

Run:

```bash
python -m pip install "pytest>=8.2,<9.0"
```

Expected: Pytest is installed and `python -m pytest --version` prints a version.

## File Structure

- Create: `pyproject.toml` - Python package metadata and dependencies.
- Create: `.gitignore` - ignore local data, env files, caches, generated outputs.
- Create: `.env.example` - documented example config without secrets.
- Create: `autovideo/__init__.py` - package marker and version.
- Create: `autovideo/main.py` - module entrypoint for Uvicorn.
- Create: `autovideo/api/__init__.py` - API package marker.
- Create: `autovideo/api/app.py` - FastAPI app factory, static mounts, root page.
- Create: `autovideo/api/dependencies.py` - request-scoped settings access.
- Create: `autovideo/api/routes/__init__.py` - route package marker.
- Create: `autovideo/api/routes/health.py` - health and runtime status endpoint.
- Create: `autovideo/core/__init__.py` - core package marker.
- Create: `autovideo/core/settings.py` - environment-backed settings.
- Create: `autovideo/core/paths.py` - data directory layout and safe creation.
- Create: `autovideo/core/runtime.py` - FFmpeg and optional service checks.
- Create: `autovideo/web/index.html` - Chinese workbench shell.
- Create: `autovideo/web/assets/styles.css` - responsive workbench layout.
- Create: `autovideo/web/assets/app.js` - static shell status wiring.
- Create: `tests/conftest.py` - test helpers.
- Create: `tests/core/test_settings.py` - configuration tests.
- Create: `tests/core/test_paths.py` - data directory tests.
- Create: `tests/core/test_runtime.py` - runtime dependency tests.
- Create: `tests/api/test_health.py` - API health tests.
- Create: `tests/web/test_static_shell.py` - static UI shell tests.
- Create: `scripts/dev.sh` - local development launcher.
- Create: `Dockerfile` - container image with FFmpeg.
- Modify: `README.md` - local start, Docker start, config, phase scope.

## Task 1: Python Project And Settings

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `autovideo/__init__.py`
- Create: `autovideo/core/__init__.py`
- Create: `autovideo/core/settings.py`
- Create: `tests/core/test_settings.py`

- [ ] **Step 1: Write the failing settings tests**

Create `tests/core/test_settings.py`:

```python
from pathlib import Path

from autovideo.core.settings import Settings


def test_settings_have_safe_defaults() -> None:
    settings = Settings()

    assert settings.app_name == "AutoVideo"
    assert settings.environment == "development"
    assert settings.host == "0.0.0.0"
    assert settings.port == 8090
    assert settings.data_dir == Path("data")
    assert settings.ffmpeg_path == "ffmpeg"
    assert settings.fish_speech_url is None


def test_settings_read_autovideo_environment(monkeypatch) -> None:
    monkeypatch.setenv("AUTOVIDEO_DATA_DIR", "/tmp/autovideo-data")
    monkeypatch.setenv("AUTOVIDEO_PORT", "9010")
    monkeypatch.setenv("AUTOVIDEO_FFMPEG_PATH", "/usr/local/bin/ffmpeg")
    monkeypatch.setenv("AUTOVIDEO_FISH_SPEECH_URL", "http://127.0.0.1:7860")

    settings = Settings()

    assert settings.data_dir == Path("/tmp/autovideo-data")
    assert settings.port == 9010
    assert settings.ffmpeg_path == "/usr/local/bin/ffmpeg"
    assert settings.fish_speech_url == "http://127.0.0.1:7860"


def test_resolved_data_dir_is_absolute(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path / "runtime")

    assert settings.resolved_data_dir == tmp_path / "runtime"
    assert settings.resolved_data_dir.is_absolute()
```

- [ ] **Step 2: Run the settings tests to verify they fail**

Run:

```bash
pytest tests/core/test_settings.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autovideo'`.

- [ ] **Step 3: Create project metadata and settings implementation**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=70", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "autovideo"
version = "0.1.0"
description = "Self-hosted video remix workbench."
readme = "README.md"
requires-python = ">=3.12"
license = { text = "AGPL-3.0-only" }
dependencies = [
  "fastapi>=0.115,<1.0",
  "uvicorn[standard]>=0.30,<1.0",
  "pydantic-settings>=2.4,<3.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2,<9.0",
  "httpx>=0.27,<1.0",
]

[project.scripts]
autovideo = "autovideo.main:main"

[tool.setuptools.packages.find]
include = ["autovideo*"]

[tool.setuptools.package-data]
autovideo = ["web/*.html", "web/assets/*.css", "web/assets/*.js"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Create `.gitignore`:

```gitignore
.DS_Store
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.mypy_cache/
.venv/
venv/
.env
.env.*
!.env.example
data/
outputs/
*.log
dist/
build/
*.egg-info/
```

Create `.env.example`:

```dotenv
# AutoVideo local configuration example.
# Copy this file to .env for local use. Do not commit real credentials.

AUTOVIDEO_APP_NAME=AutoVideo
AUTOVIDEO_ENVIRONMENT=development
AUTOVIDEO_HOST=0.0.0.0
AUTOVIDEO_PORT=8090
AUTOVIDEO_DATA_DIR=./data
AUTOVIDEO_FFMPEG_PATH=ffmpeg

# Optional external services. Leave empty to keep the feature disabled.
AUTOVIDEO_FISH_SPEECH_URL=
```

Create `autovideo/__init__.py`:

```python
__all__ = ["__version__"]

__version__ = "0.1.0"
```

Create `autovideo/core/__init__.py`:

```python
"""Core configuration and runtime helpers for AutoVideo."""
```

Create `autovideo/core/settings.py`:

```python
from functools import cached_property
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AutoVideo"
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8090
    data_dir: Path = Field(default=Path("data"))
    ffmpeg_path: str = "ffmpeg"
    fish_speech_url: str | None = None

    model_config = SettingsConfigDict(
        env_prefix="AUTOVIDEO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @cached_property
    def resolved_data_dir(self) -> Path:
        return self.data_dir.expanduser().resolve()
```

- [ ] **Step 4: Install the package in editable development mode**

Run:

```bash
python -m pip install -e ".[dev]"
```

Expected: `autovideo` installs successfully with development dependencies.

- [ ] **Step 5: Run the settings tests to verify they pass**

Run:

```bash
pytest tests/core/test_settings.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit Task 1**

```bash
git add pyproject.toml .gitignore .env.example autovideo/__init__.py autovideo/core/__init__.py autovideo/core/settings.py tests/core/test_settings.py
git commit -m "chore: add AutoVideo project settings"
```

## Task 2: Data Directory Layout

**Files:**
- Create: `autovideo/core/paths.py`
- Create: `tests/core/test_paths.py`

- [ ] **Step 1: Write the failing path tests**

Create `tests/core/test_paths.py`:

```python
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
```

- [ ] **Step 2: Run the path tests to verify they fail**

Run:

```bash
pytest tests/core/test_paths.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autovideo.core.paths'`.

- [ ] **Step 3: Implement data path helpers**

Create `autovideo/core/paths.py`:

```python
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
```

- [ ] **Step 4: Run the path tests to verify they pass**

Run:

```bash
pytest tests/core/test_paths.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit Task 2**

```bash
git add autovideo/core/paths.py tests/core/test_paths.py
git commit -m "feat: add AutoVideo data directory layout"
```

## Task 3: Runtime Dependency Checks

**Files:**
- Create: `autovideo/core/runtime.py`
- Create: `tests/core/test_runtime.py`

- [ ] **Step 1: Write the failing runtime tests**

Create `tests/core/test_runtime.py`:

```python
from autovideo.core.runtime import RuntimeCheck, check_runtime
from autovideo.core.settings import Settings


def test_runtime_marks_missing_ffmpeg_as_error() -> None:
    settings = Settings(ffmpeg_path="missing-autovideo-ffmpeg-binary")

    status = check_runtime(settings)

    assert status["ffmpeg"] == RuntimeCheck(
        name="ffmpeg",
        ok=False,
        required=True,
        message="未找到 FFmpeg，可执行文件：missing-autovideo-ffmpeg-binary",
    )


def test_runtime_marks_empty_fish_speech_as_optional() -> None:
    settings = Settings(fish_speech_url=None)

    status = check_runtime(settings)

    assert status["fish_speech"] == RuntimeCheck(
        name="fish_speech",
        ok=False,
        required=False,
        message="Fish Speech 未配置，音色复刻功能将保持禁用",
    )


def test_runtime_marks_configured_fish_speech_as_available() -> None:
    settings = Settings(fish_speech_url="http://127.0.0.1:7860")

    status = check_runtime(settings)

    assert status["fish_speech"] == RuntimeCheck(
        name="fish_speech",
        ok=True,
        required=False,
        message="Fish Speech 已配置：http://127.0.0.1:7860",
    )
```

- [ ] **Step 2: Run the runtime tests to verify they fail**

Run:

```bash
pytest tests/core/test_runtime.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autovideo.core.runtime'`.

- [ ] **Step 3: Implement runtime checks**

Create `autovideo/core/runtime.py`:

```python
from dataclasses import dataclass
from shutil import which

from autovideo.core.settings import Settings


@dataclass(frozen=True)
class RuntimeCheck:
    name: str
    ok: bool
    required: bool
    message: str


def check_ffmpeg(settings: Settings) -> RuntimeCheck:
    binary = settings.ffmpeg_path
    if which(binary) is None:
        return RuntimeCheck(
            name="ffmpeg",
            ok=False,
            required=True,
            message=f"未找到 FFmpeg，可执行文件：{binary}",
        )
    return RuntimeCheck(
        name="ffmpeg",
        ok=True,
        required=True,
        message=f"FFmpeg 可用：{binary}",
    )


def check_fish_speech(settings: Settings) -> RuntimeCheck:
    if not settings.fish_speech_url:
        return RuntimeCheck(
            name="fish_speech",
            ok=False,
            required=False,
            message="Fish Speech 未配置，音色复刻功能将保持禁用",
        )
    return RuntimeCheck(
        name="fish_speech",
        ok=True,
        required=False,
        message=f"Fish Speech 已配置：{settings.fish_speech_url}",
    )


def check_runtime(settings: Settings) -> dict[str, RuntimeCheck]:
    return {
        "ffmpeg": check_ffmpeg(settings),
        "fish_speech": check_fish_speech(settings),
    }
```

- [ ] **Step 4: Run the runtime tests to verify they pass**

Run:

```bash
pytest tests/core/test_runtime.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit Task 3**

```bash
git add autovideo/core/runtime.py tests/core/test_runtime.py
git commit -m "feat: add runtime dependency checks"
```

## Task 4: FastAPI App And Health API

**Files:**
- Create: `autovideo/api/__init__.py`
- Create: `autovideo/api/app.py`
- Create: `autovideo/api/dependencies.py`
- Create: `autovideo/api/routes/__init__.py`
- Create: `autovideo/api/routes/health.py`
- Create: `autovideo/main.py`
- Create: `tests/conftest.py`
- Create: `tests/api/test_health.py`

- [ ] **Step 1: Write the failing API tests**

Create `tests/conftest.py`:

```python
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    settings = Settings(
        data_dir=tmp_path,
        ffmpeg_path="missing-autovideo-ffmpeg-binary",
        fish_speech_url=None,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
```

Create `tests/api/test_health.py`:

```python
def test_health_endpoint_reports_app_and_runtime(client) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["app"] == "AutoVideo"
    assert payload["status"] == "degraded"
    assert payload["environment"] == "development"
    assert payload["data_dir"]
    assert payload["data_dir"].startswith("/")
    assert payload["checks"]["ffmpeg"]["ok"] is False
    assert payload["checks"]["ffmpeg"]["required"] is True
    assert payload["checks"]["fish_speech"]["ok"] is False
    assert payload["checks"]["fish_speech"]["required"] is False


def test_openapi_is_available(client) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["info"]["title"] == "AutoVideo"
```

- [ ] **Step 2: Run the API tests to verify they fail**

Run:

```bash
pytest tests/api/test_health.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autovideo.api'`.

- [ ] **Step 3: Implement FastAPI app and health route**

Create `autovideo/api/__init__.py`:

```python
"""HTTP API package for AutoVideo."""
```

Create `autovideo/api/dependencies.py`:

```python
from fastapi import Request

from autovideo.core.settings import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings
```

Create `autovideo/api/routes/__init__.py`:

```python
"""API route modules."""
```

Create `autovideo/api/routes/health.py`:

```python
from dataclasses import asdict

from fastapi import APIRouter, Depends

from autovideo.api.dependencies import get_settings
from autovideo.core.paths import ensure_data_dirs
from autovideo.core.runtime import check_runtime
from autovideo.core.settings import Settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    paths = ensure_data_dirs(settings)
    checks = check_runtime(settings)
    required_checks = [check for check in checks.values() if check.required]
    status = "ok" if all(check.ok for check in required_checks) else "degraded"

    return {
        "app": settings.app_name,
        "status": status,
        "environment": settings.environment,
        "data_dir": str(paths.root),
        "checks": {name: asdict(check) for name, check in checks.items()},
    }
```

Create `autovideo/api/app.py`:

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from autovideo.api.routes.health import router as health_router
from autovideo.core.settings import Settings

PACKAGE_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = PACKAGE_DIR / "web"


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings()
    app = FastAPI(title=active_settings.app_name)
    app.state.settings = active_settings
    app.include_router(health_router)
    assets_dir = WEB_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse | JSONResponse:
        index_file = WEB_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return JSONResponse(
            {
                "app": active_settings.app_name,
                "message": "AutoVideo web shell is not installed",
            }
        )

    return app
```

Create `autovideo/main.py`:

```python
import uvicorn

from autovideo.api.app import create_app
from autovideo.core.settings import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the API tests to verify they pass**

Run:

```bash
pytest tests/api/test_health.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit Task 4**

```bash
git add autovideo/api autovideo/main.py tests/conftest.py tests/api/test_health.py
git commit -m "feat: add FastAPI health skeleton"
```

## Task 5: Static Chinese Workbench Shell

**Files:**
- Create: `autovideo/web/index.html`
- Create: `autovideo/web/assets/styles.css`
- Create: `autovideo/web/assets/app.js`
- Create: `tests/web/test_static_shell.py`

- [ ] **Step 1: Write the failing static shell tests**

Create `tests/web/test_static_shell.py`:

```python
from pathlib import Path


WEB_ROOT = Path("autovideo/web")


def test_index_contains_chinese_product_shell() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")

    assert "AutoVideo" in html
    assert "混剪工作台" in html
    assert "素材库" in html
    assert "字幕模板" in html
    assert "BGM 管理" in html
    assert "音色中心" in html
    assert "任务与输出" in html
    assert "系统设置" in html


def test_index_does_not_include_removed_auth_or_netdisk_copy() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")

    forbidden = ["登录", "退出登录", "权限", "个人网盘", "NAS 登录", "token"]
    for text in forbidden:
        assert text not in html


def test_static_assets_define_mobile_layout() -> None:
    css = (WEB_ROOT / "assets" / "styles.css").read_text(encoding="utf-8")

    assert "@media (max-width: 760px)" in css
    assert ".app-shell" in css
    assert ".mobile-tabs" in css


def test_root_page_serves_static_shell(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "混剪工作台" in response.text
```

- [ ] **Step 2: Run static and API tests to verify they fail**

Run:

```bash
pytest tests/web/test_static_shell.py tests/api/test_health.py -v
```

Expected: FAIL with missing `autovideo/web/index.html` or missing `autovideo/web/assets`.

- [ ] **Step 3: Create the static workbench shell**

Create `autovideo/web/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>AutoVideo</title>
    <link rel="stylesheet" href="/assets/styles.css" />
  </head>
  <body>
    <div class="app-shell">
      <aside class="sidebar" aria-label="主导航">
        <div class="brand">
          <span class="brand-mark">AV</span>
          <div>
            <strong>AutoVideo</strong>
            <small>视频混剪工作台</small>
          </div>
        </div>
        <nav class="nav-list">
          <a class="active" href="#mix">混剪工作台</a>
          <a href="#materials">素材库</a>
          <a href="#subtitles">字幕模板</a>
          <a href="#bgm">BGM 管理</a>
          <a href="#voices">音色中心</a>
          <a href="#tasks">任务与输出</a>
          <a href="#settings">系统设置</a>
        </nav>
      </aside>

      <main class="workspace">
        <header class="topbar">
          <div>
            <p class="eyebrow">本地自托管</p>
            <h1>混剪工作台</h1>
          </div>
          <div class="runtime-status" id="runtime-status" aria-live="polite">正在检查运行环境</div>
        </header>

        <nav class="mobile-tabs" aria-label="移动端导航">
          <a class="active" href="#mix">混剪</a>
          <a href="#materials">素材</a>
          <a href="#subtitles">字幕</a>
          <a href="#bgm">BGM</a>
          <a href="#voices">音色</a>
          <a href="#tasks">任务</a>
        </nav>

        <section class="content-grid" id="mix">
          <article class="panel primary-panel">
            <div class="panel-heading">
              <h2>新建混剪任务</h2>
              <span>阶段 1 已搭建产品骨架，功能模块将在后续阶段接入。</span>
            </div>
            <div class="empty-state">
              <strong>工作台已就绪</strong>
              <p>下一阶段将接入素材、字幕模板、BGM 和音色资源。</p>
            </div>
          </article>

          <aside class="panel status-panel">
            <h2>运行检查</h2>
            <dl id="check-list">
              <div>
                <dt>服务状态</dt>
                <dd>等待检查</dd>
              </div>
            </dl>
          </aside>
        </section>
      </main>
    </div>
    <script src="/assets/app.js" type="module"></script>
  </body>
</html>
```

Create `autovideo/web/assets/styles.css`:

```css
:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --surface: #ffffff;
  --surface-strong: #eef2f6;
  --text: #17202a;
  --muted: #667085;
  --line: #d7dde5;
  --accent: #176b87;
  --accent-strong: #0f4c5c;
  --success: #257a4f;
  --warning: #a15c05;
  --danger: #b42318;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
}

a {
  color: inherit;
  text-decoration: none;
}

.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 248px 1fr;
}

.sidebar {
  background: #10242d;
  color: #f8fafc;
  padding: 24px 18px;
}

.brand {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 28px;
}

.brand-mark {
  width: 42px;
  height: 42px;
  display: inline-grid;
  place-items: center;
  border-radius: 8px;
  background: #f0b429;
  color: #10242d;
  font-weight: 800;
}

.brand small {
  display: block;
  margin-top: 3px;
  color: #c7d2da;
}

.nav-list {
  display: grid;
  gap: 6px;
}

.nav-list a {
  padding: 11px 12px;
  border-radius: 8px;
  color: #dbe4ea;
}

.nav-list a.active,
.nav-list a:hover {
  background: rgba(255, 255, 255, 0.12);
  color: #ffffff;
}

.workspace {
  min-width: 0;
  padding: 24px;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--accent);
  font-size: 13px;
  font-weight: 700;
}

h1,
h2,
p {
  margin-top: 0;
}

h1 {
  margin-bottom: 0;
  font-size: 30px;
}

h2 {
  font-size: 18px;
}

.runtime-status {
  min-width: 180px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  padding: 10px 12px;
  color: var(--muted);
  text-align: center;
}

.runtime-status.ok {
  color: var(--success);
}

.runtime-status.degraded {
  color: var(--warning);
}

.mobile-tabs {
  display: none;
}

.content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 18px;
}

.panel {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  padding: 18px;
}

.panel-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.panel-heading span {
  max-width: 360px;
  color: var(--muted);
  font-size: 14px;
  line-height: 1.6;
}

.empty-state {
  margin-top: 22px;
  min-height: 260px;
  border: 1px dashed var(--line);
  border-radius: 8px;
  background: var(--surface-strong);
  display: grid;
  place-content: center;
  gap: 8px;
  text-align: center;
  color: var(--muted);
}

.empty-state strong {
  color: var(--text);
  font-size: 20px;
}

.status-panel dl {
  display: grid;
  gap: 12px;
}

.status-panel div {
  border-top: 1px solid var(--line);
  padding-top: 12px;
}

.status-panel dt {
  color: var(--muted);
  font-size: 13px;
}

.status-panel dd {
  margin: 4px 0 0;
  line-height: 1.5;
}

@media (max-width: 760px) {
  .app-shell {
    display: block;
  }

  .sidebar {
    padding: 16px;
  }

  .nav-list {
    display: none;
  }

  .workspace {
    padding: 16px;
  }

  .topbar {
    align-items: stretch;
    flex-direction: column;
  }

  h1 {
    font-size: 24px;
  }

  .mobile-tabs {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding: 4px 0 14px;
  }

  .mobile-tabs a {
    flex: 0 0 auto;
    min-height: 40px;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: var(--surface);
    padding: 10px 12px;
  }

  .mobile-tabs a.active {
    border-color: var(--accent);
    color: var(--accent-strong);
    font-weight: 700;
  }

  .content-grid {
    grid-template-columns: 1fr;
  }

  .panel-heading {
    display: block;
  }

  .panel-heading span {
    display: block;
    margin-top: 8px;
  }
}
```

Create `autovideo/web/assets/app.js`:

```javascript
const statusEl = document.querySelector("#runtime-status");
const checkListEl = document.querySelector("#check-list");

function renderChecks(payload) {
  statusEl.textContent = payload.status === "ok" ? "运行环境正常" : "运行环境需检查";
  statusEl.classList.toggle("ok", payload.status === "ok");
  statusEl.classList.toggle("degraded", payload.status !== "ok");

  checkListEl.innerHTML = "";
  Object.values(payload.checks).forEach((check) => {
    const row = document.createElement("div");
    const title = document.createElement("dt");
    const body = document.createElement("dd");
    title.textContent = check.name;
    body.textContent = check.message;
    row.append(title, body);
    checkListEl.append(row);
  });
}

async function loadHealth() {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) {
      throw new Error(`health request failed: ${response.status}`);
    }
    renderChecks(await response.json());
  } catch (error) {
    statusEl.textContent = "无法读取运行状态";
    statusEl.classList.add("degraded");
    checkListEl.innerHTML = "<div><dt>服务状态</dt><dd>请确认后端服务已启动</dd></div>";
  }
}

loadHealth();
```

- [ ] **Step 4: Run static and API tests to verify they pass**

Run:

```bash
pytest tests/web/test_static_shell.py tests/api/test_health.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit Task 5**

```bash
git add autovideo/web tests/web/test_static_shell.py
git commit -m "feat: add static AutoVideo workbench shell"
```

## Task 6: Local Launch, Docker, And README

**Files:**
- Create: `scripts/dev.sh`
- Create: `Dockerfile`
- Create: `tests/test_project_files.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing project file tests**

Create `tests/test_project_files.py`:

```python
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

    assert "python:3.12-slim" in content
    assert "ffmpeg" in content
    assert 'CMD ["python", "-m", "autovideo.main"]' in content


def test_readme_documents_phase_one_startup() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "阶段 1：产品骨架" in content
    assert "python -m autovideo.main" in content
    assert "docker build -t autovideo ." in content
    assert "AGPL-3.0-only" in content
```

- [ ] **Step 2: Run the project file tests to verify they fail**

Run:

```bash
pytest tests/test_project_files.py -v
```

Expected: FAIL because `Dockerfile` is missing and README does not yet document phase one startup.

- [ ] **Step 3: Add local launcher and Dockerfile**

Create `scripts/dev.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

export AUTOVIDEO_HOST="${AUTOVIDEO_HOST:-0.0.0.0}"
export AUTOVIDEO_PORT="${AUTOVIDEO_PORT:-8090}"
export AUTOVIDEO_DATA_DIR="${AUTOVIDEO_DATA_DIR:-./data}"

python -m autovideo.main
```

Run:

```bash
chmod +x scripts/dev.sh
```

Create `Dockerfile`:

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV AUTOVIDEO_HOST=0.0.0.0
ENV AUTOVIDEO_PORT=8090
ENV AUTOVIDEO_DATA_DIR=/app/data

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY autovideo ./autovideo

RUN pip install --no-cache-dir .

EXPOSE 8090

CMD ["python", "-m", "autovideo.main"]
```

- [ ] **Step 4: Update README**

Replace `README.md` with:

```markdown
# AutoVideo

AutoVideo 是一个个人自托管的视频混剪工作台。项目会从产品骨架开始，逐步接入字幕模板、BGM 管理、音色中心和混剪任务流。

## 当前阶段

阶段 1：产品骨架

- FastAPI 后端服务
- 中文静态工作台首页
- 环境变量配置
- 数据目录初始化
- FFmpeg 与可选 Fish Speech 运行检查
- 本地启动和 Docker 启动

尚未接入登录、权限管理、个人网盘导入、BGM 上传、字幕模板编辑、音色复刻和真实混剪渲染。

## 本地启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python -m autovideo.main
```

打开 `http://127.0.0.1:8090`。

也可以使用脚本启动：

```bash
./scripts/dev.sh
```

## Docker 启动

```bash
docker build -t autovideo .
docker run --rm -p 8090:8090 -v "$PWD/data:/app/data" autovideo
```

## 配置

所有配置通过环境变量提供。示例见 `.env.example`。

- `AUTOVIDEO_DATA_DIR`：运行数据目录。
- `AUTOVIDEO_FFMPEG_PATH`：FFmpeg 可执行文件。
- `AUTOVIDEO_FISH_SPEECH_URL`：可选 Fish Speech 服务地址，留空时音色复刻功能禁用。

不要把真实 token、key、密码或内网地址提交到仓库。

## License

This project is licensed under the GNU Affero General Public License v3.0 only
(`AGPL-3.0-only`).

If you modify this software and let users interact with it over a network, the
AGPL requires you to make the corresponding source code available to those
users.

See [LICENSE](LICENSE) for the full terms.
```

- [ ] **Step 5: Run project file tests to verify they pass**

Run:

```bash
pytest tests/test_project_files.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Run all tests**

Run:

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 6**

```bash
git add scripts/dev.sh Dockerfile README.md tests/test_project_files.py
git commit -m "chore: document AutoVideo skeleton startup"
```

## Task 7: End-To-End Skeleton Verification

**Files:**
- No file changes expected unless verification exposes a concrete defect.

- [ ] **Step 1: Install development dependencies**

Run:

```bash
python -m pip install -e ".[dev]"
```

Expected: package installs successfully.

- [ ] **Step 2: Run full test suite**

Run:

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Start the local service**

Run:

```bash
AUTOVIDEO_PORT=8090 python -m autovideo.main
```

Expected: Uvicorn starts and listens on `http://0.0.0.0:8090`.

- [ ] **Step 4: Verify health endpoint from another terminal**

Run:

```bash
curl -s http://127.0.0.1:8090/api/health
```

Expected response includes:

```json
{
  "app": "AutoVideo",
  "environment": "development",
  "checks": {
    "ffmpeg": {
      "name": "ffmpeg",
      "required": true
    },
    "fish_speech": {
      "name": "fish_speech",
      "required": false
    }
  }
}
```

- [ ] **Step 5: Verify browser shell**

Open `http://127.0.0.1:8090` in the browser.

Expected:

- Page title is `AutoVideo`.
- The page shows `混剪工作台`.
- The navigation shows `素材库`, `字幕模板`, `BGM 管理`, `音色中心`, `任务与输出`, `系统设置`.
- The page does not show login, permission, personal netdisk, or NAS copy.
- On mobile-width viewport, horizontal tabs are visible and content remains readable.

- [ ] **Step 6: Build Docker image**

Run:

```bash
docker build -t autovideo .
```

Expected: image builds successfully.

- [ ] **Step 7: Commit only if verification required file fixes**

If Step 1 through Step 6 pass without file changes, do not create a commit.

If a file fix was needed, run:

```bash
pytest -v
git add <changed-files>
git commit -m "fix: stabilize AutoVideo skeleton verification"
```

Replace `<changed-files>` with the actual files changed by the fix.

## Spec Coverage Review

- Product architecture and clean module boundaries: covered by Tasks 1, 2, 4, and 5.
- Environment-only configuration and no real credentials: covered by Tasks 1 and 6.
- Data directory layout for future resources and tasks: covered by Task 2.
- Runtime checks for FFmpeg and optional Fish Speech: covered by Task 3 and exposed by Task 4.
- Static Chinese product shell with desktop and mobile structure: covered by Task 5.
- Local and Docker startup: covered by Task 6 and verified by Task 7.
- Resource center and mix-task features: intentionally deferred to later implementation plans after this skeleton is complete.

## Execution Notes

- Keep each task on the existing `codex/autovideo-product-redesign-spec` branch unless the current maintainer chooses a new implementation branch.
- Do not copy code or configuration values from `/Users/sha/junxincode` during this phase.
- Do not add login, permission checks, user tokens, personal netdisk imports, or NAS login copy.
- Run the specified tests immediately after each implementation step.
- Commit after each task so the branch stays reviewable.
