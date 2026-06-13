# AutoVideo Product Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first runnable AutoVideo skeleton: FastAPI service, React/Vite Chinese workbench shell, configuration, data directory layout, runtime dependency checks, local launch, Docker launch, and tests.

**Architecture:** This plan implements only Phase 1 from the product redesign spec. The backend is a small FastAPI application split into `api` and `core` packages, while the frontend lives in `frontend/` as a React + Vite + TypeScript SPA. FastAPI serves the built `frontend/dist` assets in production; local development can run the Vite dev server with `/api` proxied to FastAPI.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, Pydantic Settings, Pytest, HTTPX/TestClient, React, TypeScript, Vite, Vitest, Testing Library, Docker with FFmpeg and Node build stage.

---

## Scope

This plan covers:

- Package structure and Python project metadata.
- Environment-based configuration with no real credentials.
- Data directory creation for materials, BGM, voices, subtitle templates, outputs, and tasks.
- Runtime dependency checks for FFmpeg and optional Fish Speech configuration.
- FastAPI app factory, health endpoint, React build asset serving.
- Chinese React UI shell with desktop and mobile layout.
- Local development script, Dockerfile, `.env.example`, `.gitignore`, README updates.
- Backend and frontend tests for the skeleton.

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

- [ ] **Step 2: Ensure Node.js is available for the React frontend**

Run:

```bash
node --version
npm --version
```

Expected: Node.js 20 or newer is available, and npm prints a version.

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
- Create: `frontend/package.json` - React/Vite scripts and frontend dependencies.
- Create: `frontend/tsconfig.json` - TypeScript compiler settings.
- Create: `frontend/tsconfig.node.json` - TypeScript settings for Vite config.
- Create: `frontend/vite.config.ts` - Vite config, backend proxy, Vitest config.
- Create: `frontend/index.html` - Vite HTML entry.
- Create: `frontend/src/main.tsx` - React entrypoint.
- Create: `frontend/src/App.tsx` - Chinese workbench shell component.
- Create: `frontend/src/api/health.ts` - typed health API client.
- Create: `frontend/src/styles.css` - responsive workbench layout.
- Create: `frontend/src/App.test.tsx` - React component tests.
- Create: `frontend/src/test/setup.ts` - Testing Library setup.
- Create: `frontend/src/vite-env.d.ts` - Vite type declarations.
- Create: `tests/conftest.py` - test helpers.
- Create: `tests/core/test_settings.py` - configuration tests.
- Create: `tests/core/test_paths.py` - data directory tests.
- Create: `tests/core/test_runtime.py` - runtime dependency tests.
- Create: `tests/api/test_health.py` - API health tests.
- Create: `tests/web/test_frontend_build.py` - static frontend build integration tests.
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
frontend/dist/
frontend/node_modules/
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

PROJECT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIST_DIR = PROJECT_DIR / "frontend" / "dist"


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings()
    app = FastAPI(title=active_settings.app_name)
    app.state.settings = active_settings
    app.include_router(health_router)
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse | JSONResponse:
        index_file = FRONTEND_DIST_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return JSONResponse(
            {
                "app": active_settings.app_name,
                "message": "AutoVideo frontend build is not installed",
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

## Task 5: React + Vite Chinese Workbench Shell

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/api/health.ts`
- Create: `frontend/src/styles.css`
- Create: `frontend/src/App.test.tsx`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/vite-env.d.ts`
- Create: `tests/web/test_frontend_build.py`

- [ ] **Step 1: Create frontend package and failing React tests**

Create `frontend/package.json`:

```json
{
  "name": "autovideo-frontend",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite --host 0.0.0.0 --port 5173",
    "build": "tsc -b && vite build",
    "test": "vitest run",
    "test:watch": "vitest",
    "preview": "vite preview --host 0.0.0.0 --port 4173"
  },
  "dependencies": {
    "@tanstack/react-query": "^5.59.0",
    "lucide-react": "^0.468.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.4.8",
    "@testing-library/react": "^16.0.1",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.5",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "jsdom": "^24.1.1",
    "typescript": "^5.5.4",
    "vite": "^5.4.2",
    "vitest": "^2.0.5"
  }
}
```

Create `frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["DOM", "DOM.Iterable", "ES2020"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Create `frontend/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "composite": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

Create `frontend/vite.config.ts`:

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8090",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
    globals: true,
  },
});
```

Create `frontend/src/App.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { fetchHealth } from "./api/health";

vi.mock("./api/health", () => ({
  fetchHealth: vi.fn(),
}));

const mockedFetchHealth = vi.mocked(fetchHealth);

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
}

describe("AutoVideo shell", () => {
  beforeEach(() => {
    mockedFetchHealth.mockResolvedValue({
      app: "AutoVideo",
      status: "degraded",
      environment: "development",
      data_dir: "/tmp/autovideo",
      checks: {
        ffmpeg: {
          name: "ffmpeg",
          ok: false,
          required: true,
          message: "未找到 FFmpeg，可执行文件：ffmpeg",
        },
        fish_speech: {
          name: "fish_speech",
          ok: false,
          required: false,
          message: "Fish Speech 未配置，音色复刻功能将保持禁用",
        },
      },
    });
  });

  it("renders the Chinese product navigation", async () => {
    renderApp();

    expect(await screen.findByRole("heading", { name: "混剪工作台" })).toBeInTheDocument();
    expect(screen.getByText("素材库")).toBeInTheDocument();
    expect(screen.getByText("字幕模板")).toBeInTheDocument();
    expect(screen.getByText("BGM 管理")).toBeInTheDocument();
    expect(screen.getByText("音色中心")).toBeInTheDocument();
    expect(screen.getByText("任务与输出")).toBeInTheDocument();
    expect(screen.getByText("系统设置")).toBeInTheDocument();
  });

  it("does not render removed auth or netdisk copy", async () => {
    renderApp();
    await screen.findByRole("heading", { name: "混剪工作台" });

    expect(screen.queryByText(/退出登录|个人网盘|NAS 登录|token/i)).not.toBeInTheDocument();
  });

  it("shows runtime check feedback", async () => {
    renderApp();

    expect(await screen.findByText("运行环境需检查")).toBeInTheDocument();
    expect(screen.getByText("未找到 FFmpeg，可执行文件：ffmpeg")).toBeInTheDocument();
  });
});
```

Create `frontend/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 2: Run frontend tests to verify they fail**

Run:

```bash
cd frontend
npm install
npm test -- --run
```

Expected: FAIL with `Failed to resolve import "./App"` or equivalent missing component error.

- [ ] **Step 3: Create the React workbench shell**

Create `frontend/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>AutoVideo</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `frontend/src/vite-env.d.ts`:

```ts
/// <reference types="vite/client" />
```

Create `frontend/src/api/health.ts`:

```ts
export interface RuntimeCheck {
  name: string;
  ok: boolean;
  required: boolean;
  message: string;
}

export interface HealthPayload {
  app: string;
  status: "ok" | "degraded";
  environment: string;
  data_dir: string;
  checks: Record<string, RuntimeCheck>;
}

export async function fetchHealth(): Promise<HealthPayload> {
  const response = await fetch("/api/health");
  if (!response.ok) {
    throw new Error(`health request failed: ${response.status}`);
  }
  return response.json() as Promise<HealthPayload>;
}
```

Create `frontend/src/main.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
```

Create `frontend/src/App.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import {
  Captions,
  Clapperboard,
  FolderVideo,
  Music,
  Settings,
  Sparkles,
  SquarePlay,
  Volume2,
} from "lucide-react";

import { fetchHealth } from "./api/health";

const navItems = [
  { label: "混剪工作台", shortLabel: "混剪", icon: Clapperboard },
  { label: "素材库", shortLabel: "素材", icon: FolderVideo },
  { label: "字幕模板", shortLabel: "字幕", icon: Captions },
  { label: "BGM 管理", shortLabel: "BGM", icon: Music },
  { label: "音色中心", shortLabel: "音色", icon: Volume2 },
  { label: "任务与输出", shortLabel: "任务", icon: SquarePlay },
  { label: "系统设置", shortLabel: "设置", icon: Settings },
];

function RuntimeStatus() {
  const query = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  if (query.isLoading) {
    return <div className="runtime-status">正在检查运行环境</div>;
  }

  if (query.isError || !query.data) {
    return <div className="runtime-status degraded">无法读取运行状态</div>;
  }

  const checks = Object.values(query.data.checks);
  const statusText = query.data.status === "ok" ? "运行环境正常" : "运行环境需检查";

  return (
    <aside className="panel status-panel" aria-label="运行检查">
      <div className={`runtime-status ${query.data.status}`}>{statusText}</div>
      <h2>运行检查</h2>
      <dl>
        {checks.map((check) => (
          <div key={check.name}>
            <dt>{check.name}</dt>
            <dd>{check.message}</dd>
          </div>
        ))}
      </dl>
    </aside>
  );
}

export default function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="主导航">
        <div className="brand">
          <span className="brand-mark">AV</span>
          <div>
            <strong>AutoVideo</strong>
            <small>视频混剪工作台</small>
          </div>
        </div>
        <nav className="nav-list">
          {navItems.map((item, index) => {
            const Icon = item.icon;
            return (
              <a className={index === 0 ? "active" : ""} href={`#${index}`} key={item.label}>
                <Icon aria-hidden="true" size={18} />
                <span>{item.label}</span>
              </a>
            );
          })}
        </nav>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">本地自托管</p>
            <h1>混剪工作台</h1>
          </div>
          <div className="topbar-summary">
            <Sparkles aria-hidden="true" size={18} />
            <span>React + Vite 产品骨架</span>
          </div>
        </header>

        <nav className="mobile-tabs" aria-label="移动端导航">
          {navItems.slice(0, 6).map((item, index) => (
            <a className={index === 0 ? "active" : ""} href={`#${index}`} key={item.shortLabel}>
              {item.shortLabel}
            </a>
          ))}
        </nav>

        <section className="content-grid" id="0">
          <article className="panel primary-panel">
            <div className="panel-heading">
              <h2>新建混剪任务</h2>
              <span>阶段 1 先搭建产品骨架，后续阶段接入素材、字幕模板、BGM 和音色资源。</span>
            </div>
            <div className="empty-state">
              <strong>工作台已就绪</strong>
              <p>下一阶段将接入资源中心和混剪任务流。</p>
            </div>
          </article>

          <RuntimeStatus />
        </section>
      </main>
    </div>
  );
}
```

Create `frontend/src/styles.css`:

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
  --warning: #9a5b00;
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
  min-height: 100dvh;
  display: grid;
  grid-template-columns: 248px 1fr;
}

.sidebar {
  background: #10242d;
  color: #f8fafc;
  padding: 24px 18px;
}

.brand,
.topbar-summary,
.nav-list a {
  display: flex;
  align-items: center;
}

.brand {
  gap: 12px;
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
  min-height: 44px;
  gap: 10px;
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

.topbar-summary,
.runtime-status {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  padding: 10px 12px;
  color: var(--muted);
}

.topbar-summary {
  gap: 8px;
}

.runtime-status {
  margin-bottom: 14px;
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
    min-height: 44px;
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

Create `tests/web/test_frontend_build.py`:

```python
from pathlib import Path


FRONTEND_ROOT = Path("frontend")


def test_frontend_source_contains_chinese_product_shell() -> None:
    app_source = (FRONTEND_ROOT / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "混剪工作台" in app_source
    assert "素材库" in app_source
    assert "字幕模板" in app_source
    assert "BGM 管理" in app_source
    assert "音色中心" in app_source
    assert "任务与输出" in app_source
    assert "系统设置" in app_source


def test_frontend_source_does_not_include_removed_auth_or_netdisk_copy() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (FRONTEND_ROOT / "src").rglob("*")
        if path.suffix in {".ts", ".tsx", ".css"}
    )

    forbidden = ["退出登录", "个人网盘", "NAS 登录", "token"]
    for value in forbidden:
        assert value not in text


def test_frontend_build_outputs_static_assets() -> None:
    index_file = FRONTEND_ROOT / "dist" / "index.html"
    assets_dir = FRONTEND_ROOT / "dist" / "assets"

    assert index_file.exists()
    assert 'id="root"' in index_file.read_text(encoding="utf-8")
    assert assets_dir.exists()
    assert any(path.suffix == ".js" for path in assets_dir.iterdir())
    assert any(path.suffix == ".css" for path in assets_dir.iterdir())


def test_fastapi_serves_built_frontend(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "AutoVideo" in response.text
    assert 'id="root"' in response.text
```

- [ ] **Step 4: Run frontend tests and build**

Run:

```bash
cd frontend
npm test -- --run
npm run build
cd ..
pytest tests/web/test_frontend_build.py tests/api/test_health.py -v
```

Expected: frontend tests pass, Vite build succeeds, and 6 Python tests pass.

- [ ] **Step 5: Commit Task 5**

```bash
git add frontend tests/web/test_frontend_build.py
git commit -m "feat: add React AutoVideo workbench shell"
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

    assert "node:20" in content
    assert "python:3.12-slim" in content
    assert "npm run build" in content
    assert "frontend/dist" in content
    assert "ffmpeg" in content
    assert 'CMD ["python", "-m", "autovideo.main"]' in content


def test_readme_documents_phase_one_startup() -> None:
    content = Path("README.md").read_text(encoding="utf-8")

    assert "阶段 1：产品骨架" in content
    assert "React + Vite" in content
    assert "npm install" in content
    assert "npm run build" in content
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
FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm install

COPY frontend ./
RUN npm run build

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
COPY --from=frontend-builder /frontend/dist ./frontend/dist

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
- React + Vite 中文工作台首页
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
cd frontend
npm install
npm run build
cd ..
cp .env.example .env
python -m autovideo.main
```

打开 `http://127.0.0.1:8090`。

开发时建议分别启动后端和前端：

```bash
./scripts/dev.sh
```

另开一个终端：

```bash
cd frontend
npm run dev
```

打开 `http://127.0.0.1:5173`，Vite 会把 `/api` 代理到 FastAPI。

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
cd frontend
npm test -- --run
npm run build
cd ..
pytest -v
```

Expected: frontend tests pass, Vite build succeeds, and all Python tests pass.

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
cd frontend
npm install
cd ..
```

Expected: Python package installs successfully and frontend dependencies install successfully.

- [ ] **Step 2: Run frontend tests and build**

Run:

```bash
cd frontend
npm test -- --run
npm run build
cd ..
```

Expected: Vitest passes and Vite writes `frontend/dist/index.html`.

- [ ] **Step 3: Run full Python test suite**

Run:

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 4: Start the local service**

Run:

```bash
AUTOVIDEO_PORT=8090 python -m autovideo.main
```

Expected: Uvicorn starts and listens on `http://0.0.0.0:8090`.

- [ ] **Step 5: Verify health endpoint from another terminal**

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

- [ ] **Step 6: Verify browser shell**

Open `http://127.0.0.1:8090` in the browser.

Expected:

- Page title is `AutoVideo`.
- The page shows `混剪工作台`.
- The navigation shows `素材库`, `字幕模板`, `BGM 管理`, `音色中心`, `任务与输出`, `系统设置`.
- The page does not show login, permission, personal netdisk, or NAS copy.
- On mobile-width viewport, horizontal tabs are visible and content remains readable.

- [ ] **Step 7: Build Docker image**

Run:

```bash
docker build -t autovideo .
```

Expected: image builds successfully.

- [ ] **Step 8: Commit only if verification required file fixes**

If Step 1 through Step 6 pass without file changes, do not create a commit.

If a file fix was needed, run:

```bash
cd frontend && npm test -- --run && npm run build && cd ..
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
