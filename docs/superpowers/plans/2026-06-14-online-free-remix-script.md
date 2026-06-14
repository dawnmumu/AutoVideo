# Online Free Remix Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first usable AutoVideo workflow for topic-to-script generation, online free material search/download, and manifest-based remix task creation.

**Architecture:** Add a backend vertical slice with focused `scripts`, `online_materials`, and `online_mix` services behind FastAPI routes. Keep real rendering out of scope: the workflow downloads selected online material into the existing local material library, then creates a sanitized task manifest through `create_task(..., manifest_payload=...)`. The frontend remains a dense workbench surface, adding a usable online remix panel with explicit loading, retry, selection, and mobile states.

**Tech Stack:** Python 3.12, FastAPI, Pydantic Settings, SQLite, Pytest, HTTPX/TestClient, React 18, TypeScript, Vite, TanStack Query, Testing Library, Lucide icons.

---

## Scope

This plan implements:

- Script generation API with heuristic fallback and OpenAI-compatible LLM plumbing.
- Online material provider status and fake-provider-testable Pexels/Pixabay search adapters.
- Server-signed candidate tokens with HMAC, TTL, fixed error priority, and no download URL exposure.
- Secure online material download with strict provider host allowlists and SSRF/DNS rebinding tests.
- SQLite material source metadata migration.
- `create_task(..., manifest_payload=...)` support with manifest sanitization.
- Online mix API with `shot_assets`, `shot_materials`, auto matching, and safe task manifest output.
- React workbench UI for generating scripts, reviewing candidates, selecting/retrying materials, creating a manifest task, and viewing output links.
- README and `.env.example` updates.

This plan does not implement:

- Real FFmpeg rendering.
- BGM management, subtitle template editing, TTS, or voice center behavior.
- Login, permission management, teams, or multi-tenant isolation.
- Copying old project deployment paths, internal addresses, credentials, tokens, or private service URLs.

## File Structure

- Create: `autovideo/api/errors.py` - shared structured error helper.
- Create: `autovideo/api/routes/scripts.py` - `POST /api/scripts/generate`.
- Create: `autovideo/api/routes/online_materials.py` - status, search, download endpoints.
- Create: `autovideo/api/routes/online_mix.py` - `POST /api/online-mix/tasks`.
- Create: `autovideo/services/scripts.py` - script request validation, heuristic generator, LLM client wrapper.
- Create: `autovideo/services/online_materials.py` - provider models, fake-testable provider registry, candidate token service, search ranking.
- Create: `autovideo/services/online_downloads.py` - secure URL validation, redirect handling, streaming download, local material insertion.
- Create: `autovideo/services/online_mix.py` - shot selection validation, per-shot material resolution, manifest payload assembly.
- Modify: `autovideo/core/settings.py` - LLM, provider, token, download, and payload settings.
- Modify: `pyproject.toml` - promote `httpx` to runtime dependency because provider and LLM clients use it.
- Modify: `autovideo/storage/database.py` - material source columns and migration.
- Modify: `autovideo/services/materials.py` - source metadata insertion support.
- Modify: `autovideo/services/tasks.py` - `manifest_payload` support and manifest sanitization.
- Modify: `autovideo/api/app.py` - include new routers and request limits for new JSON endpoints.
- Modify: `autovideo/api/routes/materials.py` - public material metadata includes safe source fields only.
- Modify: `README.md` and `.env.example` - document new config and APIs without secrets.
- Create: `tests/api/test_scripts.py` - script endpoint tests.
- Create: `tests/api/test_online_materials.py` - provider status, search, token, download tests.
- Create: `tests/api/test_online_mix.py` - online mix API tests.
- Create: `tests/services/test_online_material_security.py` - token and URL security unit tests.
- Modify: `tests/api/test_video_tasks.py` - manifest payload and material metadata migration tests.
- Modify: `tests/core/test_settings.py` - new settings tests.
- Create: `frontend/src/api/onlineRemix.ts` - typed online remix API client.
- Create: `frontend/src/components/OnlineRemixWorkbench.tsx` - workbench feature UI.
- Modify: `frontend/src/App.tsx` - mount online remix workbench.
- Modify: `frontend/src/styles.css` - responsive workbench, form, candidate, state styling.
- Modify: `frontend/src/App.test.tsx` - online workflow UI tests.

## Implementation Setup

- [ ] **Step 1: Confirm branch and clean worktree**

Run:

```bash
git status --short --branch
```

Expected: branch is `codex/online-free-remix-script-design`; no unrelated uncommitted files are present.

- [ ] **Step 2: Install current project dependencies if needed**

Run:

```bash
PYENV_VERSION=3.12.13 python -m pip install -e ".[dev]"
cd frontend && npm install && cd ..
```

Expected: Python package installs and `frontend/node_modules` exists. Do not commit generated dependency directories.

## Task 1: Settings And Structured Errors

**Files:**
- Modify: `autovideo/core/settings.py`
- Create: `autovideo/api/errors.py`
- Modify: `autovideo/api/app.py`
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Modify: `tests/core/test_settings.py`

- [ ] **Step 1: Write the failing settings tests**

Append to `tests/core/test_settings.py`:

```python
def test_online_remix_settings_have_safe_defaults() -> None:
    settings = Settings()

    assert settings.llm_provider == "openai_compatible"
    assert settings.llm_base_url is None
    assert settings.llm_api_key is None
    assert settings.llm_model is None
    assert settings.llm_timeout_seconds == 45
    assert settings.llm_temperature == 0.6
    assert settings.pexels_api_key is None
    assert settings.pixabay_api_key is None
    assert settings.online_material_provider == "auto"
    assert settings.online_material_results_per_query == 8
    assert settings.online_material_download_timeout_seconds == 60
    assert settings.online_material_max_download_bytes == 524288000
    assert settings.candidate_token_secret is None
    assert settings.candidate_token_ttl_seconds == 1800
    assert settings.max_script_payload_bytes == 65536
    assert settings.max_online_mix_request_bytes == 2097152


def test_empty_secret_and_api_keys_are_disabled(monkeypatch) -> None:
    monkeypatch.setenv("AUTOVIDEO_LLM_API_KEY", "")
    monkeypatch.setenv("AUTOVIDEO_PEXELS_API_KEY", "")
    monkeypatch.setenv("AUTOVIDEO_PIXABAY_API_KEY", "")
    monkeypatch.setenv("AUTOVIDEO_CANDIDATE_TOKEN_SECRET", "")

    settings = Settings()

    assert settings.llm_api_key is None
    assert settings.pexels_api_key is None
    assert settings.pixabay_api_key is None
    assert settings.candidate_token_secret is None


def test_online_remix_settings_read_environment(monkeypatch) -> None:
    monkeypatch.setenv("AUTOVIDEO_LLM_BASE_URL", "https://llm.example.test/v1")
    monkeypatch.setenv("AUTOVIDEO_LLM_API_KEY", "test-key")
    monkeypatch.setenv("AUTOVIDEO_LLM_MODEL", "test-model")
    monkeypatch.setenv("AUTOVIDEO_PEXELS_API_KEY", "pexels-key")
    monkeypatch.setenv("AUTOVIDEO_PIXABAY_API_KEY", "pixabay-key")
    monkeypatch.setenv("AUTOVIDEO_CANDIDATE_TOKEN_SECRET", "candidate-secret")
    monkeypatch.setenv("AUTOVIDEO_CANDIDATE_TOKEN_TTL_SECONDS", "60")

    settings = Settings()

    assert settings.llm_base_url == "https://llm.example.test/v1"
    assert settings.llm_api_key == "test-key"
    assert settings.llm_model == "test-model"
    assert settings.pexels_api_key == "pexels-key"
    assert settings.pixabay_api_key == "pixabay-key"
    assert settings.candidate_token_secret == "candidate-secret"
    assert settings.candidate_token_ttl_seconds == 60
```

- [ ] **Step 2: Run the settings tests to verify failure**

Run:

```bash
PYENV_VERSION=3.12.13 python -m pytest tests/core/test_settings.py -q
```

Expected: FAIL because the new settings fields do not exist.

- [ ] **Step 3: Implement settings fields and shared error helper**

Modify `pyproject.toml` so `httpx` is available to runtime services, not only tests:

```toml
dependencies = [
  "fastapi>=0.115,<1.0",
  "httpx>=0.27,<1.0",
  "python-multipart>=0.0.20,<1.0",
  "uvicorn[standard]>=0.30,<1.0",
  "pydantic-settings>=2.4,<3.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2,<9.0",
]
```

Modify `autovideo/core/settings.py` with the new fields and a shared empty-string validator:

```python
class Settings(BaseSettings):
    # existing fields stay unchanged
    llm_provider: str = "openai_compatible"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: int = Field(default=45, ge=1)
    llm_temperature: float = Field(default=0.6, ge=0, le=2)
    pexels_api_key: str | None = None
    pixabay_api_key: str | None = None
    online_material_provider: str = "auto"
    online_material_results_per_query: int = Field(default=8, ge=1, le=25)
    online_material_download_timeout_seconds: int = Field(default=60, ge=1)
    online_material_max_download_bytes: int = Field(default=500 * 1024 * 1024, ge=1)
    candidate_token_secret: str | None = None
    candidate_token_ttl_seconds: int = Field(default=1800, ge=60, le=86400)
    max_script_payload_bytes: int = Field(default=65536, ge=1)
    max_online_mix_request_bytes: int = Field(default=2 * 1024 * 1024, ge=1)

    @field_validator(
        "fish_speech_url",
        "llm_base_url",
        "llm_api_key",
        "llm_model",
        "pexels_api_key",
        "pixabay_api_key",
        "candidate_token_secret",
        mode="before",
    )
    @classmethod
    def empty_string_is_disabled(cls, value: str | None) -> str | None:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value
```

Create `autovideo/api/errors.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from fastapi import HTTPException


def structured_error(
    status_code: int,
    code: str,
    message: str | None = None,
    **extra: Any,
) -> HTTPException:
    detail: dict[str, Any] = {"code": code}
    if message is not None:
        detail["message"] = message
    detail.update(extra)
    return HTTPException(status_code=status_code, detail=detail)
```

Modify `autovideo/api/app.py` so oversized JSON requests are rejected before parsing while preserving the endpoint-specific script error code required by the API contract:

```python
def _request_too_large_response(max_request_bytes: int, code: str = "REQUEST_TOO_LARGE") -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        content={"detail": {"code": code, "max_request_bytes": max_request_bytes}},
    )

@app.middleware("http")
async def reject_oversized_request(request: Request, call_next):
    max_request_bytes: int | None = None
    request_too_large_code = "REQUEST_TOO_LARGE"
    if request.method == "POST" and request.url.path == "/api/materials":
        max_request_bytes = active_settings.max_material_request_bytes
    elif request.method == "POST" and request.url.path == "/api/tasks":
        max_request_bytes = active_settings.max_task_request_bytes
    elif request.method == "POST" and request.url.path == "/api/scripts/generate":
        max_request_bytes = active_settings.max_script_payload_bytes
        request_too_large_code = "SCRIPT_PAYLOAD_TOO_LARGE"
    elif request.method == "POST" and request.url.path == "/api/online-mix/tasks":
        max_request_bytes = active_settings.max_online_mix_request_bytes

    if max_request_bytes is not None:
        request_length_error = _request_length_error_response(request)
        if request_length_error is not None:
            return request_length_error
        if _content_length_exceeds(request, max_request_bytes):
            return _request_too_large_response(max_request_bytes, request_too_large_code)

    return await call_next(request)
```

Update `.env.example` with documented blank values, never real credentials:

```dotenv
AUTOVIDEO_LLM_PROVIDER=openai_compatible
AUTOVIDEO_LLM_BASE_URL=
AUTOVIDEO_LLM_API_KEY=
AUTOVIDEO_LLM_MODEL=
AUTOVIDEO_LLM_TIMEOUT_SECONDS=45
AUTOVIDEO_LLM_TEMPERATURE=0.6
AUTOVIDEO_PEXELS_API_KEY=
AUTOVIDEO_PIXABAY_API_KEY=
AUTOVIDEO_ONLINE_MATERIAL_PROVIDER=auto
AUTOVIDEO_ONLINE_MATERIAL_RESULTS_PER_QUERY=8
AUTOVIDEO_ONLINE_MATERIAL_DOWNLOAD_TIMEOUT_SECONDS=60
AUTOVIDEO_ONLINE_MATERIAL_MAX_DOWNLOAD_BYTES=524288000
AUTOVIDEO_CANDIDATE_TOKEN_SECRET=
AUTOVIDEO_CANDIDATE_TOKEN_TTL_SECONDS=1800
AUTOVIDEO_MAX_SCRIPT_PAYLOAD_BYTES=65536
AUTOVIDEO_MAX_ONLINE_MIX_REQUEST_BYTES=2097152
```

- [ ] **Step 4: Run settings tests**

Run:

```bash
PYENV_VERSION=3.12.13 python -m pytest tests/core/test_settings.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add pyproject.toml autovideo/core/settings.py autovideo/api/errors.py autovideo/api/app.py .env.example tests/core/test_settings.py
git commit -m "feat: add online remix settings"
```

## Task 2: Script Generation API

**Files:**
- Create: `autovideo/services/scripts.py`
- Create: `autovideo/api/routes/scripts.py`
- Modify: `autovideo/api/app.py`
- Create: `tests/api/test_scripts.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/api/test_scripts.py`:

```python
from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings


def test_generate_script_heuristic_returns_structured_shots(tmp_path) -> None:
    app = create_app(Settings(data_dir=tmp_path, ffmpeg_path="missing-autovideo-ffmpeg-binary"))

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={
                "topic": "精油睡眠放松",
                "provider": "heuristic",
                "duration_seconds": 30,
                "aspect_ratio": "9:16",
                "tone": "自然可信",
                "target_audience": "睡眠质量差的年轻人",
                "selling_points": ["舒缓", "睡前仪式感"],
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"]
    assert payload["topic"] == "精油睡眠放松"
    assert payload["aspect_ratio"] == "9:16"
    assert payload["duration_seconds"] == 30
    assert payload["provider"] == "heuristic"
    assert len(payload["shots"]) >= 3
    assert payload["shots"][0]["index"] == 1
    assert payload["shots"][0]["duration"] > 0
    assert payload["shots"][0]["keywords"]


def test_generate_script_auto_falls_back_without_llm(client) -> None:
    response = client.post(
        "/api/scripts/generate",
        json={"topic": "咖啡店早高峰", "provider": "auto", "duration_seconds": 20},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "heuristic"


def test_generate_script_llm_only_requires_config(client) -> None:
    response = client.post(
        "/api/scripts/generate",
        json={"topic": "咖啡店早高峰", "provider": "llm_only"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "LLM_NOT_CONFIGURED"


def test_generate_script_auto_uses_configured_llm_client(tmp_path) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "LLM 生成脚本",
            "shots": [
                {
                    "index": 1,
                    "duration": 6,
                    "narration": "LLM 旁白",
                    "subtitle": "LLM 字幕",
                    "visual_description": "coffee shop morning",
                    "keywords": ["coffee shop", "morning"],
                }
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={"topic": "咖啡店早高峰", "provider": "auto", "duration_seconds": 20},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "llm"
    assert payload["title"] == "LLM 生成脚本"
    assert payload["shots"][0]["keywords"] == ["coffee shop", "morning"]


def test_generate_script_llm_only_parses_fake_structured_response(tmp_path) -> None:
    from autovideo.services.scripts import FakeLlmClient

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FakeLlmClient(
        {
            "title": "结构化脚本",
            "shots": [
                {
                    "index": 1,
                    "duration": 5,
                    "narration": "旁白",
                    "subtitle": "字幕",
                    "visual_description": "oil bottle close up",
                    "keywords": ["oil bottle"],
                }
            ],
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={"topic": "精油睡眠放松", "provider": "llm_only", "duration_seconds": 15},
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "llm"


def test_generate_script_auto_falls_back_when_llm_http_or_parse_fails(tmp_path) -> None:
    from autovideo.services.scripts import LlmResponseInvalidError

    class FailingLlmClient:
        def generate(self, payload, settings):
            raise LlmResponseInvalidError()

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            llm_base_url="https://llm.example.test/v1",
            llm_api_key="test-key",
            llm_model="test-model",
        )
    )
    app.state.llm_client = FailingLlmClient()

    with TestClient(app) as client:
        response = client.post(
            "/api/scripts/generate",
            json={"topic": "咖啡店早高峰", "provider": "auto", "duration_seconds": 20},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "heuristic"
    assert payload["topic"] == "咖啡店早高峰"


def test_generate_script_validates_topic_and_payload(client) -> None:
    blank_response = client.post(
        "/api/scripts/generate",
        json={"topic": "   ", "provider": "heuristic"},
    )
    assert blank_response.status_code == 400
    assert blank_response.json()["detail"]["code"] == "SCRIPT_TOPIC_REQUIRED"

    client.app.state.settings.max_script_payload_bytes = 32
    large_response = client.post(
        "/api/scripts/generate",
        json={"topic": "精油睡眠放松", "selling_points": ["x" * 100]},
    )
    assert large_response.status_code == 413
    assert large_response.json()["detail"]["code"] == "SCRIPT_PAYLOAD_TOO_LARGE"
```

- [ ] **Step 2: Run script tests to verify failure**

Run:

```bash
PYENV_VERSION=3.12.13 python -m pytest tests/api/test_scripts.py -q
```

Expected: FAIL because `/api/scripts/generate` is not registered.

- [ ] **Step 3: Implement script service**

Create `autovideo/services/scripts.py`:

```python
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import httpx
from autovideo.core.settings import Settings
from autovideo.services.tasks import encoded_json_size

ScriptProvider = Literal["auto", "llm_only", "heuristic"]


class ScriptTopicRequiredError(Exception):
    pass


class ScriptPayloadTooLargeError(Exception):
    def __init__(self, payload_bytes: int, max_bytes: int) -> None:
        self.payload_bytes = payload_bytes
        self.max_bytes = max_bytes
        super().__init__(str(payload_bytes))


class LlmNotConfiguredError(Exception):
    pass


class LlmResponseInvalidError(Exception):
    pass


class LlmClient(Protocol):
    def generate(self, payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
        ...


class FakeLlmClient:
    def __init__(self, response_payload: dict[str, Any]) -> None:
        self.response_payload = response_payload

    def generate(self, payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
        return dict(self.response_payload)


class OpenAICompatibleLlmClient:
    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self.http_client = http_client or httpx.Client()

    def generate(self, payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
        if not (settings.llm_base_url and settings.llm_api_key and settings.llm_model):
            raise LlmNotConfiguredError()
        response = self.http_client.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=settings.llm_timeout_seconds,
            json={
                "model": settings.llm_model,
                "temperature": settings.llm_temperature,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "Return an AutoVideo shot script as JSON."},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)


def validate_script_request(payload: dict[str, Any], settings: Settings) -> None:
    payload_bytes = encoded_json_size(payload)
    if payload_bytes > settings.max_script_payload_bytes:
        raise ScriptPayloadTooLargeError(payload_bytes, settings.max_script_payload_bytes)
    if not str(payload.get("topic", "")).strip():
        raise ScriptTopicRequiredError()


def heuristic_script(payload: dict[str, Any]) -> dict[str, Any]:
    topic = str(payload["topic"]).strip()
    duration_seconds = int(payload.get("duration_seconds") or 30)
    aspect_ratio = str(payload.get("aspect_ratio") or "9:16")
    selling_points = [
        str(item).strip()
        for item in payload.get("selling_points", [])
        if str(item).strip()
    ]
    base_keywords = selling_points or [topic]
    shot_count = max(3, min(6, duration_seconds // 5 or 3))
    base_duration = max(3, duration_seconds // shot_count)
    shots = []
    for index in range(1, shot_count + 1):
        keyword = base_keywords[(index - 1) % len(base_keywords)]
        shots.append(
            {
                "index": index,
                "duration": base_duration,
                "narration": f"{topic}，镜头 {index} 展示{keyword}。",
                "subtitle": f"{topic} · {keyword}",
                "visual_description": f"{topic} related scene, {keyword}, clean commercial video",
                "keywords": [topic, keyword, "commercial video"],
            }
        )
    shots[-1]["duration"] += max(0, duration_seconds - sum(shot["duration"] for shot in shots))
    return {
        "id": uuid.uuid4().hex,
        "title": f"{topic}短视频",
        "topic": topic,
        "aspect_ratio": aspect_ratio,
        "duration_seconds": duration_seconds,
        "shots": shots,
        "provider": "heuristic",
        "created_at": datetime.now(UTC).isoformat(),
    }


def normalize_llm_script(payload: dict[str, Any], llm_payload: dict[str, Any]) -> dict[str, Any]:
    shots = llm_payload.get("shots")
    if not isinstance(shots, list) or not shots:
        raise LlmResponseInvalidError()
    topic = str(payload["topic"]).strip()
    return {
        "id": uuid.uuid4().hex,
        "title": str(llm_payload.get("title") or f"{topic}短视频"),
        "topic": topic,
        "aspect_ratio": str(payload.get("aspect_ratio") or "9:16"),
        "duration_seconds": int(payload.get("duration_seconds") or 30),
        "shots": shots,
        "provider": "llm",
        "created_at": datetime.now(UTC).isoformat(),
    }


def generate_script(
    payload: dict[str, Any],
    settings: Settings,
    *,
    llm_client: LlmClient | None = None,
) -> dict[str, Any]:
    validate_script_request(payload, settings)
    provider = payload.get("provider") or "auto"
    if provider == "heuristic":
        return heuristic_script(payload)
    if provider == "llm_only" and not (
        settings.llm_base_url and settings.llm_api_key and settings.llm_model
    ):
        raise LlmNotConfiguredError()
    if settings.llm_base_url and settings.llm_api_key and settings.llm_model:
        client = llm_client or OpenAICompatibleLlmClient()
        try:
            return normalize_llm_script(payload, client.generate(payload, settings))
        except (httpx.HTTPError, KeyError, json.JSONDecodeError, LlmResponseInvalidError):
            if provider == "llm_only":
                raise
            return heuristic_script(payload)
    return heuristic_script(payload)
```

- [ ] **Step 4: Implement script route and register it**

Create `autovideo/api/routes/scripts.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from autovideo.api.dependencies import get_settings
from autovideo.api.errors import structured_error
from autovideo.core.settings import Settings
from autovideo.services.scripts import (
    LlmNotConfiguredError,
    ScriptPayloadTooLargeError,
    ScriptTopicRequiredError,
    generate_script,
)

router = APIRouter(prefix="/api/scripts", tags=["scripts"])


class GenerateScriptRequest(BaseModel):
    topic: str = Field(default="")
    provider: Literal["auto", "llm_only", "heuristic"] = "auto"
    duration_seconds: int = Field(default=30, ge=5, le=300)
    aspect_ratio: str = "9:16"
    tone: str | None = None
    target_audience: str | None = None
    selling_points: list[str] = Field(default_factory=list)


@router.post("/generate")
def generate_video_script(
    request: GenerateScriptRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return generate_script(
            request.model_dump(),
            settings,
            llm_client=getattr(http_request.app.state, "llm_client", None),
        )
    except ScriptTopicRequiredError as exc:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "SCRIPT_TOPIC_REQUIRED",
            "请输入视频主题",
        ) from exc
    except ScriptPayloadTooLargeError as exc:
        raise structured_error(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "SCRIPT_PAYLOAD_TOO_LARGE",
            "脚本请求过大",
            max_script_payload_bytes=exc.max_bytes,
            payload_bytes=exc.payload_bytes,
        ) from exc
    except LlmNotConfiguredError as exc:
        raise structured_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "LLM_NOT_CONFIGURED",
            "未配置 LLM 服务",
        ) from exc
```

Modify `autovideo/api/app.py`:

```python
from autovideo.api.routes.scripts import router as scripts_router

app.include_router(scripts_router)
```

- [ ] **Step 5: Run script tests**

Run:

```bash
PYENV_VERSION=3.12.13 python -m pytest tests/api/test_scripts.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

Run:

```bash
git add autovideo/services/scripts.py autovideo/api/routes/scripts.py autovideo/api/app.py tests/api/test_scripts.py
git commit -m "feat: add script generation api"
```

## Task 3: Material Source Metadata And Manifest Payloads

**Files:**
- Modify: `autovideo/storage/database.py`
- Modify: `autovideo/services/materials.py`
- Modify: `autovideo/services/tasks.py`
- Modify: `autovideo/api/routes/materials.py`
- Modify: `tests/api/test_video_tasks.py`

- [ ] **Step 1: Write failing persistence tests**

Append to `tests/api/test_video_tasks.py`:

```python
def test_material_source_metadata_is_public_but_storage_path_is_hidden(tmp_path) -> None:
    store = AutoVideoStore(Settings(data_dir=tmp_path, ffmpeg_path="missing-autovideo-ffmpeg-binary"))
    material = store.insert_material(
        {
            "id": "online-material-1",
            "original_filename": "pexels-123.mp4",
            "content_type": "video/mp4",
            "size_bytes": 12,
            "storage_path": str(tmp_path / "materials" / "online-material-1.mp4"),
            "created_at": "2026-06-14T00:00:00+00:00",
            "source_type": "online",
            "source_provider": "pexels",
            "source_asset_id": "123",
            "source_url": "https://www.pexels.com/video/123/",
            "license_note": "Pexels source metadata retained",
            "query": "relaxing bedroom night",
        }
    )

    assert material["source_type"] == "online"
    assert store.get_material("online-material-1")["source_url"] == "https://www.pexels.com/video/123/"


def test_existing_upload_material_defaults_to_upload_source(client) -> None:
    upload_response = client.post(
        "/api/materials",
        files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
    )

    assert upload_response.status_code == 201
    payload = upload_response.json()
    assert payload["source_type"] == "upload"
    assert "storage_path" not in payload


def test_create_task_merges_sanitized_manifest_payload(client) -> None:
    material_response = client.post(
        "/api/materials",
        files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
    )
    material = material_response.json()

    from autovideo.storage.database import AutoVideoStore
    from autovideo.services.tasks import create_task

    store = AutoVideoStore(client.app.state.settings)
    task = create_task(
        store,
        title="线上混剪 manifest",
        material_ids=[material["id"]],
        options={"aspect_ratio": "9:16"},
        manifest_payload={
            "script": {"title": "脚本"},
            "source_attribution": [{"source_url": "https://www.pexels.com/video/123/"}],
            "token": "must-not-leak",
            "storage_path": "/tmp/must-not-leak.mp4",
            "provider_download_url": "https://download.example.test/file.mp4",
            "old_project": "<OLD_PROJECT_DEPLOY_PATH>",
            "old_project_internal": "<OLD_PROJECT_INTERNAL_ADDRESS>",
        },
    )
    output = client.get(task["output"]["download_url"]).json()

    assert output["script"] == {"title": "脚本"}
    assert output["source_attribution"] == [{"source_url": "https://www.pexels.com/video/123/"}]
    serialized = json.dumps(output, ensure_ascii=False)
    assert "must-not-leak" not in serialized
    assert "storage_path" not in serialized
    assert "provider_download_url" not in serialized
    assert "<OLD_PROJECT_DEPLOY_PATH>" not in serialized
    assert "<OLD_PROJECT_INTERNAL_ADDRESS>" not in serialized


def test_manifest_sanitization_recurses_through_nested_keys_and_values(client) -> None:
    material_response = client.post(
        "/api/materials",
        files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
    )
    material = material_response.json()

    from autovideo.storage.database import AutoVideoStore
    from autovideo.services.tasks import create_task

    store = AutoVideoStore(client.app.state.settings)
    task = create_task(
        store,
        title="递归清洗 manifest",
        material_ids=[material["id"]],
        options={},
        manifest_payload={
            "nested": {
                "candidate_token": "signed-token",
                "openai_api_key": "api-key",
                "provider_secret": "secret",
                "local_path": "/Users/example/private/video.mp4",
                "download": "https://videos.pexels.com/video-files/123/clip.mp4",
                "pixabay_direct": "https://cdn.pixabay.com/video/2026/clip.mp4",
                "source_url": "https://www.pexels.com/video/123/",
                "lan": "http://10.0.0.2/file.mp4",
            },
            "array": [
                {"refresh_token": "refresh-token"},
                {"source": "http://172.16.0.2/file.mp4"},
            ],
        },
    )
    output = client.get(task["output"]["download_url"]).json()
    serialized = json.dumps(output, ensure_ascii=False)

    assert "signed-token" not in serialized
    assert "api-key" not in serialized
    assert "secret" not in serialized
    assert "/Users/example/private/video.mp4" not in serialized
    assert "videos.pexels.com" not in serialized
    assert "cdn.pixabay.com" not in serialized
    assert "https://www.pexels.com/video/123/" in serialized
    assert "10.0.0.2" not in serialized
    assert "172.16.0.2" not in serialized
```

- [ ] **Step 2: Run persistence tests to verify failure**

Run:

```bash
PYENV_VERSION=3.12.13 python -m pytest tests/api/test_video_tasks.py -q
```

Expected: FAIL because source columns and `manifest_payload` are not implemented.

- [ ] **Step 3: Implement SQLite source columns and public material metadata**

Modify `autovideo/storage/database.py`:

```python
MATERIAL_SOURCE_COLUMNS = {
    "source_type": "TEXT",
    "source_provider": "TEXT",
    "source_asset_id": "TEXT",
    "source_url": "TEXT",
    "license_note": "TEXT",
    "query": "TEXT",
}


def _ensure_columns(self, connection: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for column, definition in columns.items():
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
```

Call `_ensure_columns(connection, "materials", MATERIAL_SOURCE_COLUMNS)` after `CREATE TABLE IF NOT EXISTS materials`.

Update `insert_material` to insert optional source columns:

```python
source_type = material.get("source_type") or "upload"
connection.execute(
    """
    INSERT INTO materials (
        id, original_filename, content_type, size_bytes, storage_path, created_at,
        source_type, source_provider, source_asset_id, source_url, license_note, query
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
        material["id"],
        material["original_filename"],
        material["content_type"],
        material["size_bytes"],
        material["storage_path"],
        material["created_at"],
        source_type,
        material.get("source_provider"),
        material.get("source_asset_id"),
        material.get("source_url"),
        material.get("license_note"),
        material.get("query"),
    ),
)
```

Update `_material_from_row`:

```python
return {
    "id": row["id"],
    "original_filename": row["original_filename"],
    "content_type": row["content_type"],
    "size_bytes": row["size_bytes"],
    "storage_path": row["storage_path"],
    "created_at": row["created_at"],
    "source_type": row["source_type"] or "upload",
    "source_provider": row["source_provider"],
    "source_asset_id": row["source_asset_id"],
    "source_url": row["source_url"],
    "license_note": row["license_note"],
    "query": row["query"],
}
```

Modify `autovideo/api/routes/materials.py` so `public_material` includes safe source fields:

```python
"source_type": material.get("source_type") or "upload",
"source_provider": material.get("source_provider"),
"source_asset_id": material.get("source_asset_id"),
"source_url": material.get("source_url"),
"license_note": material.get("license_note"),
"query": material.get("query"),
```

Modify `autovideo/services/materials.py` so uploads keep their existing streaming API while online downloads can record an already-written file through a shared metadata-aware helper:

```python
from typing import Any, Literal


def record_material_file(
    store: AutoVideoStore,
    *,
    filename: str,
    content_type: str,
    size_bytes: int,
    storage_path: Path,
    source_metadata: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    material_id = uuid.uuid4().hex
    metadata = source_metadata or {}
    return store.insert_material(
        {
            "id": material_id,
            "original_filename": filename,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "storage_path": str(storage_path),
            "created_at": datetime.now(UTC).isoformat(),
            "source_type": metadata.get("source_type") or "upload",
            "source_provider": metadata.get("source_provider"),
            "source_asset_id": metadata.get("source_asset_id"),
            "source_url": metadata.get("source_url"),
            "license_note": metadata.get("license_note"),
            "query": metadata.get("query"),
        }
    )
```

Update the existing `save_material(store, upload)` upload function instead of replacing it:

```python
def save_material(store: AutoVideoStore, upload: UploadFile) -> dict[str, object]:
    material_id = uuid.uuid4().hex
    original_filename = Path(upload.filename or "material.bin").name
    storage_path = store.paths.materials / (
        f"{material_id}{safe_material_extension(original_filename)}"
    )
    size_bytes = 0
    try:
        with storage_path.open("wb") as output_file:
            while chunk := upload.file.read(UPLOAD_CHUNK_SIZE):
                output_file.write(chunk)
                size_bytes += len(chunk)
                if size_bytes > store.settings.max_upload_bytes:
                    raise MaterialTooLargeError(store.settings.max_upload_bytes)
    except MaterialTooLargeError:
        storage_path.unlink(missing_ok=True)
        raise

    return record_material_file(
        store,
        filename=original_filename,
        content_type=upload.content_type or "application/octet-stream",
        size_bytes=size_bytes,
        storage_path=storage_path,
        source_metadata={"source_type": "upload"},
    )
```

Move `public_material` from `autovideo/api/routes/materials.py` to `autovideo/services/materials.py`, and update the route to import it:

```python
from autovideo.services.materials import MaterialTooLargeError, public_material, save_material
```

Task 5 reuses `record_material_file(..., source_metadata={"source_type": "online", ...})` for provider-backed downloads.

- [ ] **Step 4: Implement manifest payload support**

Modify `autovideo/services/tasks.py`:

```python
import re

SENSITIVE_MANIFEST_KEY_RE = re.compile(
    r"(^|_)(token|api_key|secret|password|credential|storage_path|download_url|media_url)$",
    re.IGNORECASE,
)
ABSOLUTE_LOCAL_PATH_RE = re.compile(r"(^|[\s=:])(/Users/|/Volumes/|/private/|/tmp/|[A-Za-z]:\\\\)")
PRIVATE_OR_INTERNAL_URL_RE = re.compile(
    r"https?://(localhost|127\\.0\\.0\\.1|0\\.0\\.0\\.0|10\\.|169\\.254\\.|172\\.(1[6-9]|2\\d|3[0-1])\\.|192\\.168\\.|100\\.6[4-9]\\.|100\\.[7-9]\\d\\.|100\\.1[01]\\d\\.|100\\.12[0-7]\\.)[^\\s\"']*",
    re.IGNORECASE,
)
DIRECT_MEDIA_URL_RE = re.compile(
    r"https?://[^\\s\"']+\\.(mp4|mov|webm|m4v)(\\?[^\\s\"']*)?",
    re.IGNORECASE,
)
REDACTION_TEST_MARKER_RE = re.compile(r"<OLD_PROJECT_(DEPLOY_PATH|INTERNAL_ADDRESS)>")


def sanitize_manifest_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if SENSITIVE_MANIFEST_KEY_RE.search(str(key)):
                continue
            sanitized[key] = sanitize_manifest_payload(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_manifest_payload(item) for item in value]
    if isinstance(value, str) and (
        ABSOLUTE_LOCAL_PATH_RE.search(value)
        or PRIVATE_OR_INTERNAL_URL_RE.search(value)
        or DIRECT_MEDIA_URL_RE.search(value)
        or REDACTION_TEST_MARKER_RE.search(value)
    ):
        return "[redacted]"
    return value
```

Extend the `create_task` signature and output payload:

```python
def create_task(
    store: AutoVideoStore,
    *,
    title: str,
    material_ids: list[str],
    options: dict[str, Any],
    manifest_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ...
    output_payload = {
        "task_id": task_id,
        "title": title,
        "materials": [...],
        "options": options,
        "note": PLACEHOLDER_OUTPUT_NOTE,
    }
    if manifest_payload:
        output_payload.update(sanitize_manifest_payload(manifest_payload))
```

- [ ] **Step 5: Run persistence tests**

Run:

```bash
PYENV_VERSION=3.12.13 python -m pytest tests/api/test_video_tasks.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git add autovideo/storage/database.py autovideo/services/materials.py autovideo/services/tasks.py autovideo/api/routes/materials.py tests/api/test_video_tasks.py
git commit -m "feat: add source metadata and manifest payloads"
```

## Task 4: Candidate Tokens And Online Material Search

**Files:**
- Create: `autovideo/services/online_materials.py`
- Create: `autovideo/api/routes/online_materials.py`
- Modify: `autovideo/api/app.py`
- Create: `tests/services/test_online_material_security.py`
- Create: `tests/api/test_online_materials.py`

- [ ] **Step 1: Write failing token and search tests**

Create `tests/services/test_online_material_security.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest

from autovideo.services.online_materials import (
    CandidateTokenExpiredError,
    CandidateTokenInvalidError,
    CandidateTokenService,
    OnlineMaterialCandidate,
    OnlineMaterialPublicUrlInvalidError,
    public_candidate,
)


def test_candidate_token_round_trip_with_ttl() -> None:
    now = datetime(2026, 6, 14, tzinfo=UTC)
    service = CandidateTokenService(secret="secret", ttl_seconds=1800, now=lambda: now)

    token = service.sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )

    payload = service.verify(token)
    assert payload["provider"] == "pexels"
    assert payload["asset_id"] == "123"
    assert payload["expires_at"] == (now + timedelta(seconds=1800)).isoformat()


def test_candidate_token_rejects_tampering() -> None:
    service = CandidateTokenService(secret="secret", ttl_seconds=1800)
    token = service.sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )

    with pytest.raises(CandidateTokenInvalidError):
        service.verify(token + "x")


def test_candidate_token_rejects_expired_payload() -> None:
    issued_at = datetime(2026, 6, 14, tzinfo=UTC)
    verifier_now = datetime(2026, 6, 14, 0, 31, tzinfo=UTC)
    signer = CandidateTokenService(secret="secret", ttl_seconds=1800, now=lambda: issued_at)
    verifier = CandidateTokenService(secret="secret", ttl_seconds=1800, now=lambda: verifier_now)
    token = signer.sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )

    with pytest.raises(CandidateTokenExpiredError):
        verifier.verify(token)


def test_candidate_token_rejects_missing_required_payload_fields() -> None:
    service = CandidateTokenService(secret="secret", ttl_seconds=1800)
    token = service.sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom",
            "file_variant": "hd",
        }
    )

    with pytest.raises(CandidateTokenInvalidError):
        service.verify(token)


def test_rank_candidates_prefers_matching_ratio_duration_and_resolution() -> None:
    from autovideo.services.online_materials import rank_candidates

    candidates = [
        OnlineMaterialCandidate(
            provider="pexels",
            asset_id="wide",
            query="relaxing bedroom",
            source_url="https://www.pexels.com/video/wide/",
            preview_url="https://images.pexels.com/videos/wide/preview.jpg",
            file_variant="sd",
            duration=2.0,
            width=1920,
            height=1080,
            license_note="Pexels source metadata retained",
        ),
        OnlineMaterialCandidate(
            provider="pixabay",
            asset_id="vertical-hd",
            query="relaxing bedroom",
            source_url="https://pixabay.com/videos/vertical-hd/",
            preview_url="https://i.vimeocdn.com/video/vertical-hd_640x360.jpg",
            file_variant="hd",
            duration=8.0,
            width=1080,
            height=1920,
            license_note="Pixabay source metadata retained",
        ),
    ]

    ranked = rank_candidates(candidates, aspect_ratio="9:16", min_duration_seconds=5)

    assert ranked[0].asset_id == "vertical-hd"


def test_public_candidate_allows_provider_source_and_preview_hosts() -> None:
    candidate = OnlineMaterialCandidate(
        provider="pexels",
        asset_id="123",
        query="relaxing bedroom",
        source_url="https://www.pexels.com/video/123/",
        preview_url="https://images.pexels.com/videos/123/preview.jpg",
        file_variant="hd",
        duration=8.0,
        width=1080,
        height=1920,
        license_note="Pexels source metadata retained",
    )

    payload = public_candidate(candidate, "signed-token")

    assert payload["source_url"] == "https://www.pexels.com/video/123/"
    assert payload["preview_url"] == "https://images.pexels.com/videos/123/preview.jpg"
    assert payload["candidate_token"] == "signed-token"


@pytest.mark.parametrize(
    ("source_url", "preview_url"),
    [
        ("https://videos.pexels.com/video-files/123/clip.mp4", "https://images.pexels.com/videos/123/preview.jpg"),
        ("http://127.0.0.1/video/123", "https://images.pexels.com/videos/123/preview.jpg"),
        ("https://127.0.0.1/video/123", "https://images.pexels.com/videos/123/preview.jpg"),
        ("https://www.pexels.com/search/videos/bedroom/", "https://images.pexels.com/videos/123/preview.jpg"),
        ("https://www.pexels.com/video/123/", "https://evil.example.test/preview.jpg"),
        ("https://www.pexels.com/video/123/", "https://www.pexels.com/video/123/"),
        ("https://www.pexels.com/video/123/", "http://10.0.0.2/preview.jpg"),
    ],
)
def test_public_candidate_rejects_unsafe_source_or_preview_urls(source_url: str, preview_url: str) -> None:
    candidate = OnlineMaterialCandidate(
        provider="pexels",
        asset_id="123",
        query="relaxing bedroom",
        source_url=source_url,
        preview_url=preview_url,
        file_variant="hd",
        duration=8.0,
        width=1080,
        height=1920,
        license_note="Pexels source metadata retained",
    )

    with pytest.raises(OnlineMaterialPublicUrlInvalidError):
        public_candidate(candidate, "signed-token")


def test_pexels_provider_uses_injected_http_client_and_settings_key() -> None:
    import httpx
    from autovideo.services.online_materials import PexelsProvider

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "pexels-key"
        return httpx.Response(
            200,
            json={
                "videos": [
                    {
                        "id": 123,
                        "url": "https://www.pexels.com/video/123/",
                        "image": "https://images.pexels.com/videos/123/preview.jpg",
                        "duration": 8,
                        "video_files": [
                            {
                                "id": "hd",
                                "width": 1080,
                                "height": 1920,
                                "link": "https://videos.pexels.com/video-files/123/clip.mp4",
                            }
                        ],
                    }
                ]
            },
        )

    provider = PexelsProvider(api_key="pexels-key", http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    candidates = provider.search("relaxing bedroom", "9:16", 5, 5)

    assert candidates[0].provider == "pexels"
    assert candidates[0].file_variant == "hd"


def test_pixabay_provider_uses_injected_http_client_and_settings_key() -> None:
    import httpx
    from autovideo.services.online_materials import PixabayProvider

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["key"] == "pixabay-key"
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "id": 456,
                        "pageURL": "https://pixabay.com/videos/456/",
                        "picture_id": "987654321",
                        "duration": 9,
                        "videos": {
                            "large": {
                                "width": 1080,
                                "height": 1920,
                                "url": "https://cdn.pixabay.com/video/2026/clip.mp4",
                            }
                        },
                    }
                ]
            },
        )

    provider = PixabayProvider(api_key="pixabay-key", http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    candidates = provider.search("relaxing bedroom", "9:16", 5, 5)

    assert candidates[0].provider == "pixabay"
    assert candidates[0].file_variant == "large"
    assert candidates[0].preview_url == "https://i.vimeocdn.com/video/987654321_640x360.jpg"
```

Create `tests/api/test_online_materials.py`:

```python
from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings
from autovideo.services.online_materials import OnlineMaterialCandidate


class FakeProvider:
    name = "pexels"
    enabled = True

    def search(self, query: str, aspect_ratio: str, min_duration_seconds: int, limit: int):
        return [
            OnlineMaterialCandidate(
                provider="pexels",
                asset_id="123",
                query=query,
                source_url="https://www.pexels.com/video/123/",
                preview_url="https://images.pexels.com/videos/123/preview.jpg",
                file_variant="hd",
                duration=8.5,
                width=1080,
                height=1920,
                license_note="Pexels source metadata retained",
            )
        ]


class FakePixabayProvider:
    name = "pixabay"
    enabled = True

    def search(self, query: str, aspect_ratio: str, min_duration_seconds: int, limit: int):
        return [
            OnlineMaterialCandidate(
                provider="pixabay",
                asset_id="456",
                query=query,
                source_url="https://pixabay.com/videos/456/",
                preview_url="https://i.vimeocdn.com/video/456_640x360.jpg",
                file_variant="hd",
                duration=9.0,
                width=1080,
                height=1920,
                license_note="Pixabay source metadata retained",
            )
        ]


def test_online_material_status_reports_secret_without_leaking_value(tmp_path) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/online-materials/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate_token_secret_configured"] is True
    assert "secret" not in str(payload)


def test_online_material_search_requires_configured_provider(client) -> None:
    response = client.post(
        "/api/online-materials/search",
        json={"query": "relaxing bedroom night", "aspect_ratio": "9:16"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_PROVIDER_NOT_CONFIGURED"


def test_online_material_search_requires_candidate_secret(tmp_path) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
        )
    )
    app.state.online_material_providers = {"pexels": FakeProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-materials/search",
            json={"query": "relaxing bedroom night", "aspect_ratio": "9:16"},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED"


def test_online_material_search_provider_failure_returns_structured_error(tmp_path) -> None:
    class FailingProvider(FakeProvider):
        def search(self, query: str, aspect_ratio: str, min_duration_seconds: int, limit: int):
            raise RuntimeError("provider failed")

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": FailingProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-materials/search",
            json={"query": "relaxing bedroom night", "aspect_ratio": "9:16"},
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_SEARCH_FAILED"


def test_online_material_search_returns_signed_candidates(tmp_path) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": FakeProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-materials/search",
            json={"query": "relaxing bedroom night", "aspect_ratio": "9:16"},
        )

    assert response.status_code == 200
    candidate = response.json()[0]
    assert candidate["candidate_token"]
    assert candidate["preview_url"].startswith("https://")
    assert "download_url" not in candidate
    assert candidate["source_url"] == "https://www.pexels.com/video/123/"


def test_online_material_search_uses_requested_provider(tmp_path) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            pixabay_api_key="pixabay-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": FakeProvider(), "pixabay": FakePixabayProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-materials/search",
            json={
                "query": "relaxing bedroom night",
                "aspect_ratio": "9:16",
                "provider": "pixabay",
            },
        )

    assert response.status_code == 200
    assert response.json()[0]["provider"] == "pixabay"


def test_online_material_search_unknown_requested_provider_returns_structured_error(tmp_path) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": FakeProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-materials/search",
            json={
                "query": "relaxing bedroom night",
                "aspect_ratio": "9:16",
                "provider": "pixabay",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_PROVIDER_NOT_AVAILABLE"
    assert response.json()["detail"]["provider"] == "pixabay"


def test_online_material_search_auto_merges_and_sorts_candidates(tmp_path) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            pixabay_api_key="pixabay-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": FakeProvider(), "pixabay": FakePixabayProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-materials/search",
            json={
                "query": "relaxing bedroom night",
                "aspect_ratio": "9:16",
                "provider": "auto",
                "min_duration_seconds": 8,
            },
        )

    assert response.status_code == 200
    providers = [candidate["provider"] for candidate in response.json()]
    assert providers == ["pixabay", "pexels"]
```

- [ ] **Step 2: Run token and search tests to verify failure**

Run:

```bash
PYENV_VERSION=3.12.13 python -m pytest tests/services/test_online_material_security.py tests/api/test_online_materials.py -q
```

Expected: FAIL because services and routes do not exist.

- [ ] **Step 3: Implement online material models and token service**

Create `autovideo/services/online_materials.py` with these public names:

```python
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, Protocol
from urllib.parse import urlparse


@dataclass(frozen=True)
class OnlineMaterialCandidate:
    provider: str
    asset_id: str
    query: str
    source_url: str
    preview_url: str
    file_variant: str
    duration: float
    width: int
    height: int
    license_note: str


class OnlineMaterialProvider(Protocol):
    name: str
    enabled: bool

    def search(
        self,
        query: str,
        aspect_ratio: str,
        min_duration_seconds: int,
        limit: int,
    ) -> list[OnlineMaterialCandidate]:
        ...

    def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
        ...


class CandidateTokenInvalidError(Exception):
    pass


class CandidateTokenExpiredError(Exception):
    pass


class OnlineMaterialPublicUrlInvalidError(Exception):
    pass


class OnlineMaterialSearchFailedError(Exception):
    pass


class CandidateTokenService:
    def __init__(
        self,
        *,
        secret: str,
        ttl_seconds: int,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.secret = secret.encode("utf-8")
        self.ttl_seconds = ttl_seconds
        self.now = now or (lambda: datetime.now(UTC))

    def sign(self, payload: dict[str, object]) -> str:
        signed_payload = dict(payload)
        signed_payload["expires_at"] = (
            self.now() + timedelta(seconds=self.ttl_seconds)
        ).isoformat()
        body = json.dumps(signed_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(self.secret, body, hashlib.sha256).digest()
        return ".".join(
            [
                base64.urlsafe_b64encode(body).decode("ascii").rstrip("="),
                base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
            ]
        )

    def verify(self, token: str) -> dict[str, object]:
        try:
            body_part, signature_part = token.split(".", 1)
            body = _urlsafe_b64decode(body_part)
            signature = _urlsafe_b64decode(signature_part)
        except Exception as exc:
            raise CandidateTokenInvalidError() from exc
        expected = hmac.new(self.secret, body, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise CandidateTokenInvalidError()
        try:
            payload = json.loads(body.decode("utf-8"))
            expires_at = datetime.fromisoformat(payload["expires_at"])
        except Exception as exc:
            raise CandidateTokenInvalidError() from exc
        required = {"provider", "asset_id", "query", "file_variant", "source_url", "expires_at"}
        if not required.issubset(payload) or any(not payload[field] for field in required):
            raise CandidateTokenInvalidError()
        if expires_at <= self.now():
            raise CandidateTokenExpiredError()
        return payload


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


PUBLIC_URL_RULES = {
    "pexels": {
        "source_hosts": {"www.pexels.com", "pexels.com"},
        "source_path_prefixes": ("/video/",),
        "preview_hosts": {"images.pexels.com"},
    },
    "pixabay": {
        "source_hosts": {"pixabay.com", "www.pixabay.com"},
        "source_path_prefixes": ("/videos/",),
        "preview_hosts": {"cdn.pixabay.com", "i.vimeocdn.com"},
    },
}

DIRECT_MEDIA_URL_RE = re.compile(r"https?://[^\\s\"']+\\.(mp4|mov|webm|m4v)(\\?[^\\s\"']*)?", re.IGNORECASE)


def _parse_https_public_url(value: str):
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host:
        raise OnlineMaterialPublicUrlInvalidError(value)
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return parsed
    if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
        raise OnlineMaterialPublicUrlInvalidError(value)
    raise OnlineMaterialPublicUrlInvalidError(value)


def validate_public_candidate_urls(candidate: OnlineMaterialCandidate) -> None:
    rules = PUBLIC_URL_RULES.get(candidate.provider)
    if rules is None:
        raise OnlineMaterialPublicUrlInvalidError(candidate.provider)
    source_url = _parse_https_public_url(candidate.source_url)
    preview_url = _parse_https_public_url(candidate.preview_url)
    source_host = (source_url.hostname or "").lower()
    preview_host = (preview_url.hostname or "").lower()
    if (
        DIRECT_MEDIA_URL_RE.search(candidate.source_url)
        or not any(source_url.path.startswith(prefix) for prefix in rules["source_path_prefixes"])
    ):
        raise OnlineMaterialPublicUrlInvalidError(candidate.source_url)
    if source_host not in rules["source_hosts"] or preview_host not in rules["preview_hosts"]:
        raise OnlineMaterialPublicUrlInvalidError(candidate.provider)


def public_candidate(candidate: OnlineMaterialCandidate, token: str) -> dict[str, object]:
    validate_public_candidate_urls(candidate)
    payload = asdict(candidate)
    payload["candidate_token"] = token
    return payload


def rank_candidates(
    candidates: list[OnlineMaterialCandidate],
    *,
    aspect_ratio: str,
    min_duration_seconds: int,
) -> list[OnlineMaterialCandidate]:
    target_ratio = 9 / 16 if aspect_ratio == "9:16" else 16 / 9

    def score(candidate: OnlineMaterialCandidate) -> tuple[float, float, int]:
        ratio = candidate.width / max(candidate.height, 1)
        ratio_penalty = abs(ratio - target_ratio)
        duration_bonus = 1.0 if candidate.duration >= min_duration_seconds else 0.0
        pixels = candidate.width * candidate.height
        return (duration_bonus, -ratio_penalty, pixels)

    return sorted(candidates, key=score, reverse=True)
```

- [ ] **Step 4: Implement provider registry, search ranking, and route**

Add provider registry helpers in `autovideo/services/online_materials.py`:

```python
import httpx


class PexelsProvider:
    name = "pexels"
    allowed_download_hosts = {"videos.pexels.com"}

    def __init__(self, *, api_key: str, http_client: httpx.Client | None = None) -> None:
        self.api_key = api_key
        self.http_client = http_client or httpx.Client()
        self.enabled = bool(api_key)

    def search(self, query: str, aspect_ratio: str, min_duration_seconds: int, limit: int) -> list[OnlineMaterialCandidate]:
        response = self.http_client.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": self.api_key},
            params={"query": query, "per_page": limit, "orientation": "portrait" if aspect_ratio == "9:16" else "landscape"},
        )
        response.raise_for_status()
        candidates = []
        for item in response.json().get("videos", []):
            files = sorted(item.get("video_files", []), key=lambda file: file.get("width", 0) * file.get("height", 0), reverse=True)
            if not files:
                continue
            file_item = files[0]
            candidates.append(
                OnlineMaterialCandidate(
                    provider="pexels",
                    asset_id=str(item["id"]),
                    query=query,
                    source_url=item.get("url") or f"https://www.pexels.com/video/{item['id']}/",
                    preview_url=item.get("image") or "",
                    file_variant=str(file_item.get("id") or "best"),
                    duration=float(item.get("duration") or 0),
                    width=int(file_item.get("width") or 0),
                    height=int(file_item.get("height") or 0),
                    license_note="Pexels source metadata retained",
                )
            )
        return rank_candidates(candidates, aspect_ratio=aspect_ratio, min_duration_seconds=min_duration_seconds)

    def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
        response = self.http_client.get(f"https://api.pexels.com/videos/videos/{asset_id}", headers={"Authorization": self.api_key})
        response.raise_for_status()
        for file_item in response.json().get("video_files", []):
            if str(file_item.get("id")) == file_variant or file_variant == "best":
                return str(file_item["link"])
        raise CandidateTokenInvalidError()


class PixabayProvider:
    name = "pixabay"
    allowed_download_hosts = {"cdn.pixabay.com"}

    def __init__(self, *, api_key: str, http_client: httpx.Client | None = None) -> None:
        self.api_key = api_key
        self.http_client = http_client or httpx.Client()
        self.enabled = bool(api_key)

    def search(self, query: str, aspect_ratio: str, min_duration_seconds: int, limit: int) -> list[OnlineMaterialCandidate]:
        response = self.http_client.get(
            "https://pixabay.com/api/videos/",
            params={"key": self.api_key, "q": query, "per_page": limit, "video_type": "film"},
        )
        response.raise_for_status()
        candidates = []
        for item in response.json().get("hits", []):
            videos = item.get("videos", {})
            file_key, file_item = max(videos.items(), key=lambda pair: pair[1].get("width", 0) * pair[1].get("height", 0))
            candidates.append(
                OnlineMaterialCandidate(
                    provider="pixabay",
                    asset_id=str(item["id"]),
                    query=query,
                    source_url=item.get("pageURL") or f"https://pixabay.com/videos/{item['id']}/",
                    preview_url=(
                        f"https://i.vimeocdn.com/video/{item['picture_id']}_640x360.jpg"
                        if item.get("picture_id")
                        else str(item.get("pageURL") or f"https://pixabay.com/videos/{item['id']}/")
                    ),
                    file_variant=file_key,
                    duration=float(item.get("duration") or 0),
                    width=int(file_item.get("width") or 0),
                    height=int(file_item.get("height") or 0),
                    license_note="Pixabay source metadata retained",
                )
            )
        return rank_candidates(candidates, aspect_ratio=aspect_ratio, min_duration_seconds=min_duration_seconds)

    def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
        response = self.http_client.get("https://pixabay.com/api/videos/", params={"key": self.api_key, "id": asset_id})
        response.raise_for_status()
        hit = response.json()["hits"][0]
        return str(hit["videos"][file_variant]["url"])


def build_provider_registry(settings, *, http_client: httpx.Client | None = None) -> dict[str, OnlineMaterialProvider]:
    providers: dict[str, OnlineMaterialProvider] = {}
    if settings.pexels_api_key:
        providers["pexels"] = PexelsProvider(api_key=settings.pexels_api_key, http_client=http_client)
    if settings.pixabay_api_key:
        providers["pixabay"] = PixabayProvider(api_key=settings.pixabay_api_key, http_client=http_client)
    return providers


def configured_provider_names(settings) -> list[str]:
    names = []
    if settings.pexels_api_key:
        names.append("pexels")
    if settings.pixabay_api_key:
        names.append("pixabay")
    return names


def provider_status(settings) -> dict[str, object]:
    return {
        "providers": [
            {
                "provider": "pexels",
                "configured": bool(settings.pexels_api_key),
                "enabled": bool(settings.pexels_api_key),
            },
            {
                "provider": "pixabay",
                "configured": bool(settings.pixabay_api_key),
                "enabled": bool(settings.pixabay_api_key),
            },
        ],
        "default_provider": settings.online_material_provider,
        "candidate_token_secret_configured": bool(settings.candidate_token_secret),
    }
```

Create `autovideo/api/routes/online_materials.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from autovideo.api.dependencies import get_settings
from autovideo.api.errors import structured_error
from autovideo.core.settings import Settings
from autovideo.services.online_materials import (
    CandidateTokenService,
    build_provider_registry,
    configured_provider_names,
    provider_status,
    public_candidate,
    rank_candidates,
)

router = APIRouter(prefix="/api/online-materials", tags=["online-materials"])


class SearchOnlineMaterialsRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    aspect_ratio: str = "9:16"
    min_duration_seconds: int = Field(default=4, ge=1)
    provider: str = "auto"


@router.get("/status")
def get_online_material_status(settings: Settings = Depends(get_settings)) -> dict[str, object]:
    return provider_status(settings)


@router.post("/search")
def search_online_materials(
    request_body: SearchOnlineMaterialsRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> list[dict[str, object]]:
    if not configured_provider_names(settings):
        raise structured_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "ONLINE_MATERIAL_PROVIDER_NOT_CONFIGURED",
            "未配置线上素材源 API key",
        )
    if not settings.candidate_token_secret:
        raise structured_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED",
            "未配置线上素材候选签名密钥",
        )
    providers = getattr(request.app.state, "online_material_providers", None) or build_provider_registry(settings)
    if request_body.provider != "auto" and request_body.provider not in providers:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "ONLINE_MATERIAL_PROVIDER_NOT_AVAILABLE",
            "选择的素材源不可用",
            provider=request_body.provider,
        )
    selected_names = list(providers) if request_body.provider == "auto" else [request_body.provider]
    selected_providers = [providers[name] for name in selected_names if name in providers]
    if not selected_providers:
        raise structured_error(status.HTTP_503_SERVICE_UNAVAILABLE, "ONLINE_MATERIAL_PROVIDER_NOT_CONFIGURED")
    token_service = CandidateTokenService(
        secret=settings.candidate_token_secret,
        ttl_seconds=settings.candidate_token_ttl_seconds,
    )
    try:
        candidates = rank_candidates(
            [
                candidate
                for provider in selected_providers
                for candidate in provider.search(
                    request_body.query,
                    request_body.aspect_ratio,
                    request_body.min_duration_seconds,
                    settings.online_material_results_per_query,
                )
            ],
            aspect_ratio=request_body.aspect_ratio,
            min_duration_seconds=request_body.min_duration_seconds,
        )[: settings.online_material_results_per_query]
    except Exception as exc:
        raise structured_error(status.HTTP_502_BAD_GATEWAY, "ONLINE_MATERIAL_SEARCH_FAILED") from exc
    return [
        public_candidate(
            candidate,
            token_service.sign(
                {
                    "provider": candidate.provider,
                    "asset_id": candidate.asset_id,
                    "query": candidate.query,
                    "file_variant": candidate.file_variant,
                    "source_url": candidate.source_url,
                }
            ),
        )
        for candidate in candidates
    ]
```

Modify `autovideo/api/app.py`:

```python
from autovideo.api.routes.online_materials import router as online_materials_router

app.include_router(online_materials_router)
```

- [ ] **Step 5: Run token and search tests**

Run:

```bash
PYENV_VERSION=3.12.13 python -m pytest tests/services/test_online_material_security.py tests/api/test_online_materials.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

Run:

```bash
git add autovideo/services/online_materials.py autovideo/api/routes/online_materials.py autovideo/api/app.py tests/services/test_online_material_security.py tests/api/test_online_materials.py
git commit -m "feat: add online material search"
```

## Task 5: Secure Online Material Download

**Files:**
- Create: `autovideo/services/online_downloads.py`
- Modify: `autovideo/api/routes/online_materials.py`
- Modify: `autovideo/services/online_materials.py`
- Modify: `tests/services/test_online_material_security.py`
- Modify: `tests/api/test_online_materials.py`

- [ ] **Step 1: Write failing secure URL tests**

Append to `tests/services/test_online_material_security.py`:

```python
import socket

from autovideo.services.online_downloads import (
    OnlineMaterialContentTypeNotAllowedError,
    OnlineMaterialDownloadUrlNotAllowedError,
    content_type_matches_extension,
    safe_download_suffix,
    validate_connection_addresses,
    validate_download_url,
    validate_redirect_chain,
)


def test_validate_download_url_rejects_non_allowlist_host() -> None:
    with pytest.raises(OnlineMaterialDownloadUrlNotAllowedError):
        validate_download_url(
            "https://evil.example.test/file.mp4",
            allowed_hosts={"videos.pexels.com"},
            resolver=lambda host: ["93.184.216.34"],
        )


def test_validate_download_url_rejects_private_dns_result() -> None:
    with pytest.raises(OnlineMaterialDownloadUrlNotAllowedError):
        validate_download_url(
            "https://videos.pexels.com/file.mp4",
            allowed_hosts={"videos.pexels.com"},
            resolver=lambda host: ["127.0.0.1"],
        )


def test_validate_download_url_accepts_allowed_public_host() -> None:
    parsed = validate_download_url(
        "https://videos.pexels.com/file.mp4",
        allowed_hosts={"videos.pexels.com"},
        resolver=lambda host: ["93.184.216.34"],
    )

    assert parsed.hostname == "videos.pexels.com"


def test_validate_redirect_chain_rejects_private_redirect_target() -> None:
    with pytest.raises(OnlineMaterialDownloadUrlNotAllowedError):
        validate_redirect_chain(
            [
                "https://videos.pexels.com/file.mp4",
                "https://127.0.0.1/file.mp4",
            ],
            allowed_hosts={"videos.pexels.com"},
            resolver=lambda host: ["93.184.216.34"] if host == "videos.pexels.com" else ["127.0.0.1"],
        )


def test_validate_connection_addresses_rejects_dns_rebinding_drift() -> None:
    with pytest.raises(OnlineMaterialDownloadUrlNotAllowedError):
        validate_connection_addresses(
            hostname="videos.pexels.com",
            preflight_addresses=["93.184.216.34"],
            connected_address="127.0.0.1",
        )


def test_validate_download_url_rejects_resolution_drift_between_checks() -> None:
    calls = 0

    def resolver(hostname: str) -> list[str]:
        nonlocal calls
        calls += 1
        return ["93.184.216.34"] if calls == 1 else ["10.0.0.2"]

    with pytest.raises(OnlineMaterialDownloadUrlNotAllowedError):
        validate_download_url(
            "https://videos.pexels.com/file.mp4",
            allowed_hosts={"videos.pexels.com"},
            resolver=resolver,
            verify_stable_resolution=True,
        )


def test_content_type_matches_extension_allowlist() -> None:
    assert content_type_matches_extension("video/mp4", ".mp4")
    assert content_type_matches_extension("video/mp4; charset=binary", ".m4v")
    assert content_type_matches_extension("video/quicktime", ".mov")
    assert content_type_matches_extension("video/webm", ".webm")
    assert not content_type_matches_extension("application/octet-stream", ".mp4")
    assert not content_type_matches_extension("video/mp4", ".webm")


def test_safe_download_suffix_rejects_unknown_or_mismatched_media_identity() -> None:
    assert safe_download_suffix("https://videos.pexels.com/video-files/123/clip.mp4", "video/mp4") == ".mp4"
    with pytest.raises(OnlineMaterialContentTypeNotAllowedError):
        safe_download_suffix("https://videos.pexels.com/video-files/123/clip.bin", "video/mp4")
    with pytest.raises(OnlineMaterialContentTypeNotAllowedError):
        safe_download_suffix("https://videos.pexels.com/video-files/123/clip.mp4", "application/octet-stream")
    with pytest.raises(OnlineMaterialContentTypeNotAllowedError):
        safe_download_suffix("https://videos.pexels.com/video-files/123/clip.mp4", "video/webm")
```

- [ ] **Step 2: Write failing download endpoint tests**

Append to `tests/api/test_online_materials.py`:

```python
def test_download_requires_secret_before_token_parse(tmp_path) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
        )
    )

    with TestClient(app) as client:
        response = client.post("/api/online-materials/download", json={})

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED"


def test_download_rejects_invalid_candidate_token(tmp_path) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/online-materials/download",
            json={"candidate_token": "invalid"},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_CANDIDATE_TOKEN_INVALID"


def test_download_candidate_provider_missing_returns_structured_error(tmp_path) -> None:
    from autovideo.services.online_materials import CandidateTokenService

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": FakeProvider()}
    token = CandidateTokenService(secret="secret", ttl_seconds=1800).sign(
        {
            "provider": "pixabay",
            "asset_id": "456",
            "query": "relaxing bedroom night",
            "file_variant": "hd",
            "source_url": "https://pixabay.com/videos/456/",
        }
    )

    with TestClient(app) as client:
        response = client.post("/api/online-materials/download", json={"candidate_token": token})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_PROVIDER_NOT_AVAILABLE"
    assert response.json()["detail"]["provider"] == "pixabay"


def test_download_streams_provider_asset_into_material_library(tmp_path) -> None:
    import httpx
    from autovideo.services.online_materials import CandidateTokenService

    class DownloadProvider(FakeProvider):
        allowed_download_hosts = {"videos.pexels.com"}

        def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
            assert asset_id == "123"
            assert file_variant == "hd"
            return "https://videos.pexels.com/video-files/123/clip.mp4"

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://videos.pexels.com/video-files/123/clip.mp4"
        return httpx.Response(
            200,
            headers={"content-type": "video/mp4"},
            content=b"video-bytes",
            extensions={"connected_address": "93.184.216.34"},
        )

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
            online_material_max_download_bytes=100,
        )
    )
    app.state.online_material_providers = {"pexels": DownloadProvider()}
    app.state.online_download_http_client = httpx.Client(transport=httpx.MockTransport(handler))
    app.state.online_download_resolver = lambda host: ["93.184.216.34"]
    token = CandidateTokenService(secret="secret", ttl_seconds=1800).sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom night",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )

    with TestClient(app) as client:
        response = client.post("/api/online-materials/download", json={"candidate_token": token})

    assert response.status_code == 201
    material = response.json()
    assert material["source_type"] == "online"
    assert material["source_provider"] == "pexels"
    assert material["source_asset_id"] == "123"
    assert material["query"] == "relaxing bedroom night"
    assert "storage_path" not in material


def test_download_rejects_mismatched_mime_during_streaming_path(tmp_path) -> None:
    import httpx
    from autovideo.services.online_materials import CandidateTokenService

    class DownloadProvider(FakeProvider):
        allowed_download_hosts = {"videos.pexels.com"}

        def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
            return "https://videos.pexels.com/video-files/123/clip.mp4"

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": DownloadProvider()}
    app.state.online_download_http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "application/octet-stream"},
                content=b"video-bytes",
                extensions={"connected_address": "93.184.216.34"},
            )
        )
    )
    app.state.online_download_resolver = lambda host: ["93.184.216.34"]
    token = CandidateTokenService(secret="secret", ttl_seconds=1800).sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom night",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )

    with TestClient(app) as client:
        response = client.post("/api/online-materials/download", json={"candidate_token": token})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_REDIRECT_NOT_ALLOWED"


def test_download_rejects_dns_rebinding_connected_address_during_streaming_path(tmp_path) -> None:
    import httpx
    from autovideo.services.online_materials import CandidateTokenService

    class DownloadProvider(FakeProvider):
        allowed_download_hosts = {"videos.pexels.com"}

        def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
            return "https://videos.pexels.com/video-files/123/clip.mp4"

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": DownloadProvider()}
    app.state.online_download_http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "video/mp4"},
                content=b"video-bytes",
                extensions={"connected_address": "127.0.0.1"},
            )
        )
    )
    app.state.online_download_resolver = lambda host: ["93.184.216.34"]
    token = CandidateTokenService(secret="secret", ttl_seconds=1800).sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom night",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )

    with TestClient(app) as client:
        response = client.post("/api/online-materials/download", json={"candidate_token": token})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_REDIRECT_NOT_ALLOWED"


def test_download_rejects_oversized_stream_with_specific_code(tmp_path) -> None:
    import httpx
    from autovideo.services.online_materials import CandidateTokenService

    class DownloadProvider(FakeProvider):
        allowed_download_hosts = {"videos.pexels.com"}

        def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
            return "https://videos.pexels.com/video-files/123/clip.mp4"

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
            online_material_max_download_bytes=4,
        )
    )
    app.state.online_material_providers = {"pexels": DownloadProvider()}
    app.state.online_download_http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "video/mp4"},
                content=b"video-bytes",
                extensions={"connected_address": "93.184.216.34"},
            )
        )
    )
    app.state.online_download_resolver = lambda host: ["93.184.216.34"]
    token = CandidateTokenService(secret="secret", ttl_seconds=1800).sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom night",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )

    with TestClient(app) as client:
        response = client.post("/api/online-materials/download", json={"candidate_token": token})

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_TOO_LARGE"


def test_download_resolve_failure_returns_structured_error(tmp_path) -> None:
    from autovideo.services.online_materials import CandidateTokenService

    class FailingProvider(FakeProvider):
        allowed_download_hosts = {"videos.pexels.com"}

        def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
            raise RuntimeError("provider failed before URL validation")

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": FailingProvider()}
    token = CandidateTokenService(secret="secret", ttl_seconds=1800).sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom night",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )

    with TestClient(app) as client:
        response = client.post("/api/online-materials/download", json={"candidate_token": token})

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_DOWNLOAD_FAILED"
```

- [ ] **Step 3: Run download tests to verify failure**

Run:

```bash
PYENV_VERSION=3.12.13 python -m pytest tests/services/test_online_material_security.py tests/api/test_online_materials.py -q
```

Expected: FAIL because download service and endpoint are missing.

- [ ] **Step 4: Implement secure URL validation**

Create `autovideo/services/online_downloads.py`:

```python
from __future__ import annotations

import ipaddress
import os
import socket
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from urllib.parse import ParseResult, urlparse

import httpx

from autovideo.services.materials import record_material_file
from autovideo.storage.database import AutoVideoStore


ALLOWED_VIDEO_MIME_EXTENSIONS = {
    "video/mp4": {".mp4", ".m4v"},
    "video/quicktime": {".mov"},
    "video/webm": {".webm"},
}
ALLOWED_VIDEO_EXTENSIONS = {
    extension
    for extensions in ALLOWED_VIDEO_MIME_EXTENSIONS.values()
    for extension in extensions
}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class OnlineMaterialDownloadUrlNotAllowedError(Exception):
    pass


class OnlineMaterialDownloadTooLargeError(Exception):
    pass


class OnlineMaterialContentTypeNotAllowedError(Exception):
    pass


class OnlineMaterialDownloadFailedError(Exception):
    pass


def default_resolver(hostname: str) -> list[str]:
    return [
        item[4][0]
        for item in socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
    ]


def _is_forbidden_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return any(
        [
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        ]
    )


def validate_download_url(
    url: str,
    *,
    allowed_hosts: set[str],
    resolver: Callable[[str], Iterable[str]] = default_resolver,
    verify_stable_resolution: bool = False,
) -> ParseResult:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if parsed.scheme != "https" or not hostname:
        raise OnlineMaterialDownloadUrlNotAllowedError(url)
    if hostname not in allowed_hosts:
        raise OnlineMaterialDownloadUrlNotAllowedError(url)
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise OnlineMaterialDownloadUrlNotAllowedError(url)
    addresses = list(resolver(hostname))
    if not addresses or any(_is_forbidden_ip(address) for address in addresses):
        raise OnlineMaterialDownloadUrlNotAllowedError(url)
    if verify_stable_resolution:
        second_addresses = list(resolver(hostname))
        if set(second_addresses) != set(addresses) or any(_is_forbidden_ip(address) for address in second_addresses):
            raise OnlineMaterialDownloadUrlNotAllowedError(url)
    return parsed


def validate_redirect_chain(
    urls: list[str],
    *,
    allowed_hosts: set[str],
    resolver: Callable[[str], Iterable[str]] = default_resolver,
) -> list[ParseResult]:
    return [
        validate_download_url(
            url,
            allowed_hosts=allowed_hosts,
            resolver=resolver,
            verify_stable_resolution=True,
        )
        for url in urls
    ]


def validate_connection_addresses(
    *,
    hostname: str,
    preflight_addresses: list[str],
    connected_address: str,
) -> None:
    if connected_address not in preflight_addresses or _is_forbidden_ip(connected_address):
        raise OnlineMaterialDownloadUrlNotAllowedError(hostname)


def _preflight_addresses(
    hostname: str,
    resolver: Callable[[str], Iterable[str]],
) -> list[str]:
    addresses = list(resolver(hostname))
    if not addresses or any(_is_forbidden_ip(address) for address in addresses):
        raise OnlineMaterialDownloadUrlNotAllowedError(hostname)
    second_addresses = list(resolver(hostname))
    if set(second_addresses) != set(addresses) or any(_is_forbidden_ip(address) for address in second_addresses):
        raise OnlineMaterialDownloadUrlNotAllowedError(hostname)
    return addresses


def response_connected_address(response: httpx.Response) -> str | None:
    explicit_address = response.extensions.get("connected_address")
    if isinstance(explicit_address, str):
        return explicit_address
    network_stream = response.extensions.get("network_stream")
    if network_stream is not None and hasattr(network_stream, "get_extra_info"):
        server_addr = network_stream.get_extra_info("server_addr")
        if isinstance(server_addr, tuple) and server_addr:
            return str(server_addr[0])
    return None


def _normalized_content_type(content_type: str) -> str:
    return content_type.split(";", 1)[0].strip().lower()


def content_type_matches_extension(content_type: str, extension: str) -> bool:
    normalized_type = _normalized_content_type(content_type)
    normalized_extension = extension.lower()
    return normalized_extension in ALLOWED_VIDEO_MIME_EXTENSIONS.get(normalized_type, set())


def safe_download_suffix(url: str, content_type: str) -> str:
    extension = Path(urlparse(url).path).suffix.lower()
    if extension not in ALLOWED_VIDEO_EXTENSIONS:
        raise OnlineMaterialContentTypeNotAllowedError(url)
    if not content_type_matches_extension(content_type, extension):
        raise OnlineMaterialContentTypeNotAllowedError(content_type)
    return extension


def open_validated_download_response(
    http_client: httpx.Client,
    url: str,
    *,
    allowed_hosts: set[str],
    resolver: Callable[[str], Iterable[str]],
    timeout_seconds: int,
    max_redirects: int = 5,
) -> tuple[httpx.Response, str]:
    current_url = url
    for _ in range(max_redirects + 1):
        parsed = validate_download_url(
            current_url,
            allowed_hosts=allowed_hosts,
            resolver=resolver,
            verify_stable_resolution=True,
        )
        preflight_addresses = _preflight_addresses(str(parsed.hostname), resolver)
        try:
            request = http_client.build_request("GET", current_url, timeout=timeout_seconds)
            prepared_response = http_client.send(
                request,
                stream=True,
                follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            raise OnlineMaterialDownloadFailedError(current_url) from exc
        if prepared_response.history:
            prepared_response.close()
            raise OnlineMaterialDownloadUrlNotAllowedError(current_url)
        connected_address = response_connected_address(prepared_response)
        if connected_address:
            validate_connection_addresses(
                hostname=str(parsed.hostname),
                preflight_addresses=preflight_addresses,
                connected_address=connected_address,
            )
        if prepared_response.status_code in REDIRECT_STATUSES:
            location = prepared_response.headers.get("location")
            prepared_response.close()
            if not location:
                raise OnlineMaterialDownloadUrlNotAllowedError(current_url)
            current_url = str(httpx.URL(current_url).join(location))
            continue
        try:
            prepared_response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            prepared_response.close()
            raise OnlineMaterialDownloadFailedError(current_url) from exc
        return prepared_response, current_url
    raise OnlineMaterialDownloadUrlNotAllowedError(url)


def stream_provider_download_to_material(
    store: AutoVideoStore,
    *,
    provider,
    token_payload: dict[str, object],
    settings,
    http_client: httpx.Client,
    resolver: Callable[[str], Iterable[str]] = default_resolver,
) -> dict[str, object]:
    material_dir = store.paths.materials
    material_dir.mkdir(parents=True, exist_ok=True)
    size = 0
    temporary_path: str | None = None
    final_path: Path | None = None
    try:
        try:
            download_url = provider.resolve_download_url(
                str(token_payload["asset_id"]),
                str(token_payload["file_variant"]),
            )
        except Exception as exc:
            raise OnlineMaterialDownloadFailedError(str(token_payload.get("asset_id"))) from exc
        response, final_url = open_validated_download_response(
            http_client,
            download_url,
            allowed_hosts=provider.allowed_download_hosts,
            resolver=resolver,
            timeout_seconds=settings.online_material_download_timeout_seconds,
        )
        try:
            validate_redirect_chain([download_url, final_url], allowed_hosts=provider.allowed_download_hosts, resolver=resolver)
            content_type = response.headers.get("content-type", "")
            suffix = safe_download_suffix(final_url, content_type)
            fd, temporary_path = tempfile.mkstemp(prefix="online-", suffix=f"{suffix}.tmp", dir=material_dir)
            final_path = Path(str(temporary_path).removesuffix(".tmp"))
            with os.fdopen(fd, "wb") as output:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > settings.online_material_max_download_bytes:
                        raise OnlineMaterialDownloadTooLargeError()
                    output.write(chunk)
        finally:
            response.close()
        os.replace(temporary_path, final_path)
        return record_material_file(
            store,
            filename=f"{token_payload['provider']}-{token_payload['asset_id']}{suffix}",
            content_type=content_type,
            size_bytes=size,
            storage_path=final_path,
            source_metadata={
                "source_type": "online",
                "source_provider": str(token_payload["provider"]),
                "source_asset_id": str(token_payload["asset_id"]),
                "source_url": str(token_payload["source_url"]),
                "license_note": f"{token_payload['provider']} source metadata retained",
                "query": str(token_payload["query"]),
            },
        )
    except Exception:
        if temporary_path is not None:
            Path(temporary_path).unlink(missing_ok=True)
        if final_path is not None:
            final_path.unlink(missing_ok=True)
        raise
```

- [ ] **Step 5: Implement provider-backed download endpoint**

Modify `autovideo/api/routes/online_materials.py` with `DownloadOnlineMaterialRequest` and endpoint:

```python
import httpx

from autovideo.api.dependencies import get_settings, get_store
from autovideo.services.online_downloads import (
    OnlineMaterialContentTypeNotAllowedError,
    OnlineMaterialDownloadFailedError,
    OnlineMaterialDownloadTooLargeError,
    OnlineMaterialDownloadUrlNotAllowedError,
    default_resolver,
    stream_provider_download_to_material,
)
from autovideo.services.materials import public_material
from autovideo.storage.database import AutoVideoStore


class DownloadOnlineMaterialRequest(BaseModel):
    candidate_token: str | None = None


@router.post("/download", status_code=status.HTTP_201_CREATED)
def download_online_material(
    request_body: DownloadOnlineMaterialRequest,
    request: Request,
    store: AutoVideoStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    if not configured_provider_names(settings):
        raise structured_error(status.HTTP_503_SERVICE_UNAVAILABLE, "ONLINE_MATERIAL_PROVIDER_NOT_CONFIGURED")
    if not settings.candidate_token_secret:
        raise structured_error(status.HTTP_503_SERVICE_UNAVAILABLE, "ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED")
    if not request_body.candidate_token:
        raise structured_error(status.HTTP_400_BAD_REQUEST, "ONLINE_MATERIAL_CANDIDATE_TOKEN_INVALID")
    token_service = CandidateTokenService(
        secret=settings.candidate_token_secret,
        ttl_seconds=settings.candidate_token_ttl_seconds,
    )
    try:
        token_payload = token_service.verify(request_body.candidate_token)
    except CandidateTokenExpiredError as exc:
        raise structured_error(status.HTTP_400_BAD_REQUEST, "ONLINE_MATERIAL_CANDIDATE_TOKEN_EXPIRED") from exc
    except CandidateTokenInvalidError as exc:
        raise structured_error(status.HTTP_400_BAD_REQUEST, "ONLINE_MATERIAL_CANDIDATE_TOKEN_INVALID") from exc
    providers = getattr(request.app.state, "online_material_providers", None) or build_provider_registry(settings)
    provider = providers.get(str(token_payload["provider"]))
    if provider is None:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "ONLINE_MATERIAL_PROVIDER_NOT_AVAILABLE",
            provider=str(token_payload["provider"]),
        )
    http_client = getattr(request.app.state, "online_download_http_client", None) or httpx.Client()
    resolver = getattr(request.app.state, "online_download_resolver", default_resolver)
    try:
        material = stream_provider_download_to_material(
            store,
            provider=provider,
            token_payload=token_payload,
            settings=settings,
            http_client=http_client,
            resolver=resolver,
        )
        return public_material(material)
    except (OnlineMaterialDownloadUrlNotAllowedError, OnlineMaterialContentTypeNotAllowedError) as exc:
        raise structured_error(status.HTTP_400_BAD_REQUEST, "ONLINE_MATERIAL_REDIRECT_NOT_ALLOWED") from exc
    except OnlineMaterialDownloadTooLargeError as exc:
        raise structured_error(status.HTTP_413_CONTENT_TOO_LARGE, "ONLINE_MATERIAL_TOO_LARGE") from exc
    except OnlineMaterialDownloadFailedError as exc:
        raise structured_error(status.HTTP_502_BAD_GATEWAY, "ONLINE_MATERIAL_DOWNLOAD_FAILED") from exc
```

This endpoint never trusts a download URL from the candidate token. It verifies the candidate token, asks the provider adapter to re-resolve the internal download URL from `provider + asset_id + file_variant`, validates the allowlisted redirect chain, rejects unknown or mismatched `Content-Type`/extension pairs, and applies DNS rebinding protection on the real streaming path. The streaming path passes through `open_validated_download_response(...)`, which uses `follow_redirects=False`, rejects any populated `response.history`, validates each redirect target before the next request, compares the response `connected_address`/`network_stream.server_addr` against the preflight resolver result when available, and otherwise requires stable public DNS resolution before streaming. After validation it writes to a temporary file under `data_dir/materials`, atomically renames the file, inserts a row through `record_material_file(..., source_metadata=...)`, and returns the same public material object shape as uploaded material.

- [ ] **Step 6: Run secure URL and successful download tests**

Run:

```bash
PYENV_VERSION=3.12.13 python -m pytest tests/services/test_online_material_security.py tests/api/test_online_materials.py -q
```

Expected: PASS, including redirect-chain, DNS rebinding, invalid token priority, and successful provider-backed streaming download tests.

- [ ] **Step 7: Commit Task 5**

Run:

```bash
git add autovideo/services/online_downloads.py autovideo/api/routes/online_materials.py tests/services/test_online_material_security.py tests/api/test_online_materials.py
git commit -m "feat: add secure online material downloads"
```

## Task 6: Provider-Backed Download And Online Mix API

**Files:**
- Modify: `autovideo/services/online_downloads.py`
- Modify: `autovideo/api/routes/online_materials.py`
- Create: `autovideo/services/online_mix.py`
- Create: `autovideo/api/routes/online_mix.py`
- Modify: `autovideo/api/app.py`
- Modify: `tests/api/test_online_materials.py`
- Create: `tests/api/test_online_mix.py`

- [ ] **Step 1: Write failing online mix tests**

Create `tests/api/test_online_mix.py`:

```python
import json

from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings


def _script() -> dict:
    return {
        "id": "script-1",
        "title": "睡前精油短视频",
        "topic": "精油睡眠放松",
        "aspect_ratio": "9:16",
        "duration_seconds": 10,
        "shots": [
            {
                "index": 1,
                "duration": 5,
                "narration": "旁白 1",
                "subtitle": "字幕 1",
                "visual_description": "relaxing bedroom night",
                "keywords": ["relaxing bedroom night"],
            },
            {
                "index": 2,
                "duration": 5,
                "narration": "旁白 2",
                "subtitle": "字幕 2",
                "visual_description": "oil bottle close up",
                "keywords": ["oil bottle"],
            },
        ],
        "provider": "heuristic",
        "created_at": "2026-06-14T00:00:00+00:00",
    }


def test_online_mix_rejects_duplicate_or_conflicting_shot_selection(client) -> None:
    material_response = client.post(
        "/api/materials",
        files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
    )
    material = material_response.json()
    response = client.post(
        "/api/online-mix/tasks",
        json={
            "title": "冲突任务",
            "script": _script(),
            "shot_assets": [{"shot_index": 1, "candidate_token": "token"}],
            "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MIX_SHOT_SELECTION_INVALID"


def test_online_mix_rejects_duplicate_material_selection(client) -> None:
    material_response = client.post(
        "/api/materials",
        files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
    )
    material = material_response.json()
    response = client.post(
        "/api/online-mix/tasks",
        json={
            "title": "重复本地素材",
            "script": _script(),
            "shot_materials": [
                {"shot_index": 1, "material_id": material["id"]},
                {"shot_index": 1, "material_id": material["id"]},
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MIX_SHOT_SELECTION_INVALID"


def test_online_mix_rejects_out_of_range_selection_before_provider_checks(tmp_path) -> None:
    app = create_app(Settings(data_dir=tmp_path, ffmpeg_path="missing-autovideo-ffmpeg-binary"))

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "越界镜头",
                "script": _script(),
                "shot_assets": [{"shot_index": 99, "candidate_token": "invalid"}],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MIX_SHOT_SELECTION_INVALID"


def test_online_mix_creates_manifest_with_user_materials(client) -> None:
    material_response = client.post(
        "/api/materials",
        files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
    )
    material = material_response.json()
    response = client.post(
        "/api/online-mix/tasks",
        json={
            "title": "本地素材混剪",
            "script": _script(),
            "asset_strategy": "manual",
            "shot_materials": [
                {"shot_index": 1, "material_id": material["id"]},
                {"shot_index": 2, "material_id": material["id"]},
            ],
            "options": {"aspect_ratio": "9:16"},
        },
    )

    assert response.status_code == 201
    task = response.json()
    output = client.get(task["output"]["download_url"]).json()
    assert output["script"]["id"] == "script-1"
    assert output["shot_materials"][0]["selection_mode"] == "user_material"
    serialized = json.dumps(output, ensure_ascii=False)
    assert "storage_path" not in serialized
    assert "candidate_token" not in serialized
    assert "<OLD_PROJECT_DEPLOY_PATH>" not in serialized


def test_online_mix_requires_secret_for_user_candidate_token(tmp_path) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "候选任务",
                "script": _script(),
                "shot_assets": [{"shot_index": 1, "candidate_token": "token"}],
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED"


def test_online_mix_downloads_user_candidate_and_creates_task(tmp_path) -> None:
    import httpx
    from autovideo.services.online_materials import CandidateTokenService
    from tests.api.test_online_materials import FakeProvider

    class DownloadProvider(FakeProvider):
        allowed_download_hosts = {"videos.pexels.com"}

        def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
            return "https://videos.pexels.com/video-files/123/clip.mp4"

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": DownloadProvider()}
    app.state.online_download_http_client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, headers={"content-type": "video/mp4"}, content=b"video"))
    )
    app.state.online_download_resolver = lambda host: ["93.184.216.34"]
    token = CandidateTokenService(secret="secret", ttl_seconds=1800).sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom night",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "候选素材混剪",
                "script": _script(),
                "asset_strategy": "manual",
                "shot_assets": [{"shot_index": 1, "candidate_token": token}],
                "shot_materials": [{"shot_index": 2, "material_id": client.post("/api/materials", files={"file": ("clip.mp4", b"fake", "video/mp4")}).json()["id"]}],
            },
        )

    assert response.status_code == 201
    output = client.get(response.json()["output"]["download_url"]).json()
    assert output["shot_materials"][0]["provider"] == "pexels"
    assert output["shot_materials"][0]["source_url"] == "https://www.pexels.com/video/123/"
    assert output["shot_materials"][0]["license_note"] == "pexels source metadata retained"
    assert output["source_attribution"] == [
        {
            "provider": "pexels",
            "source_asset_id": "123",
            "source_url": "https://www.pexels.com/video/123/",
            "license_note": "pexels source metadata retained",
            "query": "relaxing bedroom night",
        }
    ]


def test_online_mix_auto_searches_downloads_and_creates_shot_materials(tmp_path) -> None:
    import httpx
    from tests.api.test_online_materials import FakeProvider

    class DownloadProvider(FakeProvider):
        allowed_download_hosts = {"videos.pexels.com"}

        def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
            return "https://videos.pexels.com/video-files/123/clip.mp4"

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": DownloadProvider()}
    app.state.online_download_http_client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, headers={"content-type": "video/mp4"}, content=b"video"))
    )
    app.state.online_download_resolver = lambda host: ["93.184.216.34"]

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={"title": "自动素材混剪", "script": _script(), "asset_strategy": "auto", "provider": "pexels"},
        )
        output = client.get(response.json()["output"]["download_url"]).json()

    assert response.status_code == 201
    assert [item["shot_index"] for item in output["shot_materials"]] == [1, 2]
    assert all(item["selection_mode"] in {"auto", "user_candidate"} for item in output["shot_materials"])
    assert all(item["provider"] == "pexels" for item in output["shot_materials"])
    assert len(output["source_attribution"]) == 1


def test_online_mix_auto_resolve_failure_returns_structured_error(tmp_path) -> None:
    from tests.api.test_online_materials import FakeProvider

    class FailingDownloadProvider(FakeProvider):
        allowed_download_hosts = {"videos.pexels.com"}

        def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
            raise RuntimeError("provider failed before URL validation")

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": FailingDownloadProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={"title": "自动素材混剪", "script": _script(), "asset_strategy": "auto", "provider": "pexels"},
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_DOWNLOAD_FAILED"


def test_online_mix_auto_search_failure_returns_structured_error(tmp_path) -> None:
    from tests.api.test_online_materials import FakeProvider

    class FailingSearchProvider(FakeProvider):
        def search(self, query: str, aspect_ratio: str, min_duration_seconds: int, limit: int):
            raise RuntimeError("provider search failed")

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": FailingSearchProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={"title": "自动素材混剪", "script": _script(), "asset_strategy": "auto", "provider": "pexels"},
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_SEARCH_FAILED"


def test_online_mix_auto_no_material_match_returns_structured_error(tmp_path) -> None:
    from tests.api.test_online_materials import FakeProvider

    class EmptyProvider(FakeProvider):
        def search(self, query: str, aspect_ratio: str, min_duration_seconds: int, limit: int):
            return []

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": EmptyProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={"title": "无素材匹配", "script": _script(), "asset_strategy": "auto", "provider": "pexels"},
        )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ONLINE_MIX_NO_MATERIAL_MATCH"


def test_online_mix_candidate_token_expired_when_selection_is_valid(tmp_path) -> None:
    from datetime import UTC, datetime
    from autovideo.services.online_materials import CandidateTokenService

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    token = CandidateTokenService(
        secret="secret",
        ttl_seconds=60,
        now=lambda: datetime(2026, 6, 14, 0, 0, tzinfo=UTC),
    ).sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom night",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )

    with TestClient(app) as client:
        client.app.state.candidate_token_now = lambda: datetime(2026, 6, 14, 0, 2, tzinfo=UTC)
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "过期候选",
                "script": _script(),
                "shot_assets": [{"shot_index": 1, "candidate_token": token}],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_CANDIDATE_TOKEN_EXPIRED"


def test_online_mix_selection_conflict_precedes_candidate_token_validation(tmp_path) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "非法候选",
                "script": _script(),
                "shot_assets": [
                    {"shot_index": 1, "candidate_token": "invalid"},
                    {"shot_index": 1, "candidate_token": "invalid-again"},
                ],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MIX_SHOT_SELECTION_INVALID"


def test_online_mix_candidate_token_invalid_when_selection_is_valid(tmp_path) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "非法候选",
                "script": _script(),
                "shot_assets": [{"shot_index": 1, "candidate_token": "invalid"}],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_CANDIDATE_TOKEN_INVALID"


def test_online_mix_candidate_provider_missing_returns_structured_error(tmp_path) -> None:
    from autovideo.services.online_materials import CandidateTokenService
    from tests.api.test_online_materials import FakeProvider

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": FakeProvider()}
    token = CandidateTokenService(secret="secret", ttl_seconds=1800).sign(
        {
            "provider": "pixabay",
            "asset_id": "456",
            "query": "relaxing bedroom night",
            "file_variant": "hd",
            "source_url": "https://pixabay.com/videos/456/",
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "缺失 provider",
                "script": _script(),
                "asset_strategy": "manual",
                "shot_assets": [{"shot_index": 1, "candidate_token": token}],
                "shot_materials": [{"shot_index": 2, "material_id": client.post("/api/materials", files={"file": ("clip.mp4", b"fake", "video/mp4")}).json()["id"]}],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_PROVIDER_NOT_AVAILABLE"
    assert response.json()["detail"]["provider"] == "pixabay"
```

- [ ] **Step 2: Run online mix tests to verify failure**

Run:

```bash
PYENV_VERSION=3.12.13 python -m pytest tests/api/test_online_mix.py -q
```

Expected: FAIL because `/api/online-mix/tasks` is not registered.

- [ ] **Step 3: Implement online mix service**

Create `autovideo/services/online_mix.py`:

```python
from __future__ import annotations

from typing import Any, Literal

import httpx

from autovideo.services.online_downloads import stream_provider_download_to_material
from autovideo.services.online_materials import (
    CandidateTokenService,
    OnlineMaterialProvider,
    OnlineMaterialSearchFailedError,
    rank_candidates,
)
from autovideo.services.tasks import MaterialNotFoundError, create_task
from autovideo.storage.database import AutoVideoStore


class OnlineMixShotSelectionInvalidError(Exception):
    pass


class OnlineMixNoMaterialMatchError(Exception):
    pass


AssetStrategy = Literal["auto", "manual"]
ProviderSelection = Literal["auto", "pexels", "pixabay"]


class OnlineMaterialProviderNotAvailableError(Exception):
    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(provider)


def _shot_indexes(script: dict[str, Any]) -> set[int]:
    return {int(shot["index"]) for shot in script.get("shots", [])}


def validate_shot_selection(
    script: dict[str, Any],
    shot_assets: list[dict[str, Any]],
    shot_materials: list[dict[str, Any]],
) -> None:
    valid = _shot_indexes(script)
    asset_indexes = [int(item["shot_index"]) for item in shot_assets]
    material_indexes = [int(item["shot_index"]) for item in shot_materials]
    if not valid:
        raise OnlineMixShotSelectionInvalidError()
    if len(asset_indexes) != len(set(asset_indexes)):
        raise OnlineMixShotSelectionInvalidError()
    if len(material_indexes) != len(set(material_indexes)):
        raise OnlineMixShotSelectionInvalidError()
    if set(asset_indexes) & set(material_indexes):
        raise OnlineMixShotSelectionInvalidError()
    if not set(asset_indexes + material_indexes).issubset(valid):
        raise OnlineMixShotSelectionInvalidError()


def create_online_mix_task(
    store: AutoVideoStore,
    *,
    title: str,
    script: dict[str, Any],
    shot_assets: list[dict[str, Any]],
    shot_materials: list[dict[str, Any]],
    asset_strategy: AssetStrategy,
    provider_name: ProviderSelection,
    providers: dict[str, OnlineMaterialProvider],
    token_service: CandidateTokenService,
    settings,
    http_client: httpx.Client,
    resolver,
    options: dict[str, Any],
) -> dict[str, Any]:
    validate_shot_selection(script, shot_assets, shot_materials)
    material_ids = []
    manifest_shots = []
    source_attribution_by_key: dict[tuple[str, str], dict[str, object]] = {}
    resolved_materials = list(shot_materials)
    for item in shot_assets:
        payload = token_service.verify(str(item["candidate_token"]))
        provider = providers.get(str(payload["provider"]))
        if provider is None:
            raise OnlineMaterialProviderNotAvailableError(str(payload["provider"]))
        material = stream_provider_download_to_material(
            store,
            provider=provider,
            token_payload=payload,
            settings=settings,
            http_client=http_client,
            resolver=resolver,
        )
        resolved_materials.append({"shot_index": int(item["shot_index"]), "material_id": material["id"], "selection_mode": "user_candidate"})
    if asset_strategy == "auto":
        selected_providers = list(providers.values()) if provider_name == "auto" else [providers.get(provider_name)]
        if not selected_providers or selected_providers[0] is None:
            raise OnlineMaterialProviderNotAvailableError(provider_name)
        selected_indexes = {int(item["shot_index"]) for item in resolved_materials}
        for shot in script.get("shots", []):
            shot_index = int(shot["index"])
            if shot_index in selected_indexes:
                continue
            query = (shot.get("keywords") or [shot.get("visual_description") or script.get("topic")])[0]
            try:
                candidates = rank_candidates(
                    [
                        candidate
                        for provider in selected_providers
                        for candidate in provider.search(
                            str(query),
                            str(script.get("aspect_ratio") or "9:16"),
                            int(shot.get("duration") or 1),
                            settings.online_material_results_per_query,
                        )
                    ],
                    aspect_ratio=str(script.get("aspect_ratio") or "9:16"),
                    min_duration_seconds=int(shot.get("duration") or 1),
                )
            except Exception as exc:
                raise OnlineMaterialSearchFailedError(str(query)) from exc
            if not candidates:
                raise OnlineMixNoMaterialMatchError()
            candidate = candidates[0]
            payload = token_service.verify(
                token_service.sign(
                    {
                        "provider": candidate.provider,
                        "asset_id": candidate.asset_id,
                        "query": candidate.query,
                        "file_variant": candidate.file_variant,
                        "source_url": candidate.source_url,
                    }
                )
            )
            material = stream_provider_download_to_material(
                store,
                provider=providers[candidate.provider],
                token_payload=payload,
                settings=settings,
                http_client=http_client,
                resolver=resolver,
            )
            resolved_materials.append({"shot_index": shot_index, "material_id": material["id"], "selection_mode": "auto"})
    for item in sorted(resolved_materials, key=lambda value: int(value["shot_index"])):
        material = store.get_material(str(item["material_id"]))
        if material is None:
            raise MaterialNotFoundError(str(item["material_id"]))
        material_ids.append(str(item["material_id"]))
        manifest_shots.append(
            shot_manifest := {
                "shot_index": int(item["shot_index"]),
                "material_id": str(item["material_id"]),
                "selection_mode": item.get("selection_mode") or "user_material",
                "selection_reason": {
                    "user_material": "用户选择已有本地素材",
                    "user_candidate": "用户选择线上候选并由服务端下载",
                    "auto": "系统按分镜关键词自动搜索并下载",
                }[item.get("selection_mode") or "user_material"],
            }
        )
        if material.get("source_provider") and material.get("source_url"):
            shot_manifest.update(
                {
                    "provider": material.get("source_provider"),
                    "source_asset_id": material.get("source_asset_id"),
                    "source_url": material.get("source_url"),
                    "license_note": material.get("license_note"),
                    "query": material.get("query"),
                }
            )
            source_key = (str(material.get("source_provider")), str(material.get("source_url")))
            source_attribution_by_key[source_key] = {
                "provider": material.get("source_provider"),
                "source_asset_id": material.get("source_asset_id"),
                "source_url": material.get("source_url"),
                "license_note": material.get("license_note"),
                "query": material.get("query"),
            }
    if set(item["shot_index"] for item in manifest_shots) != _shot_indexes(script):
        raise OnlineMixNoMaterialMatchError()
    manifest_payload = {
        "script": script,
        "shot_materials": manifest_shots,
        "source_attribution": list(source_attribution_by_key.values()),
        "render_plan": {"status": "manifest_only", "renderer": "not_enabled"},
        "provider_status_snapshot": {},
    }
    return create_task(
        store,
        title=title,
        material_ids=material_ids,
        options=options,
        manifest_payload=manifest_payload,
    )
```

- [ ] **Step 4: Implement online mix route**

Create `autovideo/api/routes/online_mix.py`:

```python
from __future__ import annotations

from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from autovideo.api.dependencies import get_settings, get_store
from autovideo.api.errors import structured_error
from autovideo.api.routes.tasks import public_task
from autovideo.core.settings import Settings
from autovideo.services.online_downloads import (
    OnlineMaterialContentTypeNotAllowedError,
    OnlineMaterialDownloadFailedError,
    OnlineMaterialDownloadTooLargeError,
    OnlineMaterialDownloadUrlNotAllowedError,
    default_resolver,
)
from autovideo.services.online_materials import (
    CandidateTokenExpiredError,
    CandidateTokenInvalidError,
    CandidateTokenService,
    OnlineMaterialSearchFailedError,
    build_provider_registry,
    configured_provider_names,
)
from autovideo.services.online_mix import (
    OnlineMaterialProviderNotAvailableError,
    OnlineMixNoMaterialMatchError,
    OnlineMixShotSelectionInvalidError,
    create_online_mix_task,
    validate_shot_selection,
)
from autovideo.services.tasks import MaterialNotFoundError
from autovideo.storage.database import AutoVideoStore

router = APIRouter(prefix="/api/online-mix", tags=["online-mix"])


class ShotAssetSelection(BaseModel):
    shot_index: int
    candidate_token: str


class ShotMaterialSelection(BaseModel):
    shot_index: int
    material_id: str


class CreateOnlineMixTaskRequest(BaseModel):
    title: str = Field(default="未命名线上混剪任务", min_length=1, max_length=120)
    script: dict[str, Any]
    asset_strategy: Literal["auto", "manual"] = "auto"
    provider: Literal["auto", "pexels", "pixabay"] = "auto"
    shot_assets: list[ShotAssetSelection] = Field(default_factory=list)
    shot_materials: list[ShotMaterialSelection] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
def create_online_mix_video_task(
    request_body: CreateOnlineMixTaskRequest,
    request: Request,
    store: AutoVideoStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    shot_assets = [item.model_dump() for item in request_body.shot_assets]
    shot_materials = [item.model_dump() for item in request_body.shot_materials]
    try:
        validate_shot_selection(request_body.script, shot_assets, shot_materials)
    except OnlineMixShotSelectionInvalidError as exc:
        raise structured_error(status.HTTP_400_BAD_REQUEST, "ONLINE_MIX_SHOT_SELECTION_INVALID") from exc

    needs_online_assets = bool(shot_assets) or request_body.asset_strategy == "auto"
    providers = getattr(request.app.state, "online_material_providers", None) or build_provider_registry(settings)
    if needs_online_assets:
        if not configured_provider_names(settings) and not providers:
            raise structured_error(status.HTTP_503_SERVICE_UNAVAILABLE, "ONLINE_MATERIAL_PROVIDER_NOT_CONFIGURED")
        if request_body.provider != "auto" and request_body.provider not in providers:
            raise structured_error(
                status.HTTP_400_BAD_REQUEST,
                "ONLINE_MATERIAL_PROVIDER_NOT_AVAILABLE",
                provider=request_body.provider,
            )
        if not settings.candidate_token_secret:
            raise structured_error(status.HTTP_503_SERVICE_UNAVAILABLE, "ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED")
    token_service = CandidateTokenService(
        secret=settings.candidate_token_secret or "",
        ttl_seconds=settings.candidate_token_ttl_seconds,
        now=getattr(request.app.state, "candidate_token_now", None),
    )
    for item in shot_assets:
        try:
            token_service.verify(item["candidate_token"])
        except CandidateTokenExpiredError as exc:
            raise structured_error(status.HTTP_400_BAD_REQUEST, "ONLINE_MATERIAL_CANDIDATE_TOKEN_EXPIRED") from exc
        except CandidateTokenInvalidError as exc:
            raise structured_error(status.HTTP_400_BAD_REQUEST, "ONLINE_MATERIAL_CANDIDATE_TOKEN_INVALID") from exc
    http_client = getattr(request.app.state, "online_download_http_client", None) or httpx.Client()
    resolver = getattr(request.app.state, "online_download_resolver", default_resolver)
    try:
        return public_task(
            create_online_mix_task(
                store,
                title=request_body.title,
                script=request_body.script,
                shot_assets=shot_assets,
                shot_materials=shot_materials,
                asset_strategy=request_body.asset_strategy,
                provider_name=request_body.provider,
                providers=providers,
                token_service=token_service,
                settings=settings,
                http_client=http_client,
                resolver=resolver,
                options=request_body.options,
            )
        )
    except OnlineMixShotSelectionInvalidError as exc:
        raise structured_error(status.HTTP_400_BAD_REQUEST, "ONLINE_MIX_SHOT_SELECTION_INVALID") from exc
    except OnlineMixNoMaterialMatchError as exc:
        raise structured_error(status.HTTP_409_CONFLICT, "ONLINE_MIX_NO_MATERIAL_MATCH") from exc
    except OnlineMaterialProviderNotAvailableError as exc:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "ONLINE_MATERIAL_PROVIDER_NOT_AVAILABLE",
            provider=exc.provider,
        ) from exc
    except (OnlineMaterialDownloadUrlNotAllowedError, OnlineMaterialContentTypeNotAllowedError) as exc:
        raise structured_error(status.HTTP_400_BAD_REQUEST, "ONLINE_MATERIAL_REDIRECT_NOT_ALLOWED") from exc
    except OnlineMaterialDownloadTooLargeError as exc:
        raise structured_error(status.HTTP_413_CONTENT_TOO_LARGE, "ONLINE_MATERIAL_TOO_LARGE") from exc
    except OnlineMaterialDownloadFailedError as exc:
        raise structured_error(status.HTTP_502_BAD_GATEWAY, "ONLINE_MATERIAL_DOWNLOAD_FAILED") from exc
    except OnlineMaterialSearchFailedError as exc:
        raise structured_error(status.HTTP_502_BAD_GATEWAY, "ONLINE_MATERIAL_SEARCH_FAILED") from exc
    except MaterialNotFoundError as exc:
        raise structured_error(status.HTTP_404_NOT_FOUND, "MATERIAL_NOT_FOUND", material_id=exc.material_id) from exc
```

Modify `autovideo/api/app.py`:

```python
from autovideo.api.routes.online_mix import router as online_mix_router

app.include_router(online_mix_router)
```

- [ ] **Step 5: Run online mix tests**

Run:

```bash
PYENV_VERSION=3.12.13 python -m pytest tests/api/test_online_mix.py tests/api/test_video_tasks.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

Run:

```bash
git add autovideo/services/online_downloads.py autovideo/api/routes/online_materials.py autovideo/services/online_mix.py autovideo/api/routes/online_mix.py autovideo/api/app.py tests/api/test_online_materials.py tests/api/test_online_mix.py
git commit -m "feat: add online mix manifest tasks"
```

## Task 7: Frontend API Client And Online Remix Workbench

**Files:**
- Create: `frontend/src/api/onlineRemix.ts`
- Create: `frontend/src/components/OnlineRemixWorkbench.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.test.tsx`

- [ ] **Step 1: Write failing frontend tests**

Modify `frontend/src/App.test.tsx` to mock the new API module:

```tsx
import userEvent from "@testing-library/user-event";
import {
  createOnlineMixTask,
  fetchMaterials,
  fetchOnlineMaterialStatus,
  generateScript,
  searchOnlineMaterials,
} from "./api/onlineRemix";

vi.mock("./api/onlineRemix", () => ({
  fetchOnlineMaterialStatus: vi.fn(),
  fetchMaterials: vi.fn(),
  generateScript: vi.fn(),
  searchOnlineMaterials: vi.fn(),
  createOnlineMixTask: vi.fn(),
}));

const mockedFetchOnlineMaterialStatus = vi.mocked(fetchOnlineMaterialStatus);
const mockedFetchMaterials = vi.mocked(fetchMaterials);
const mockedGenerateScript = vi.mocked(generateScript);
const mockedSearchOnlineMaterials = vi.mocked(searchOnlineMaterials);
const mockedCreateOnlineMixTask = vi.mocked(createOnlineMixTask);

beforeEach(() => {
  mockedFetchMaterials.mockResolvedValue([]);
});
```

Keep the existing `fetchHealth` mock and runtime-status assertions in this file. Add the online remix API mock alongside the current mock setup so the new workbench tests do not change existing health integration behavior.

Add tests:

```tsx
it("renders the online remix form and provider status", async () => {
  mockedFetchOnlineMaterialStatus.mockResolvedValue({
    providers: [{ provider: "pexels", configured: false, enabled: false }],
    default_provider: "auto",
    candidate_token_secret_configured: false,
  });
  renderApp();

  expect(await screen.findByLabelText("视频主题")).toBeInTheDocument();
  expect(screen.getByLabelText("时长")).toBeInTheDocument();
  expect(screen.getByLabelText("画幅")).toBeInTheDocument();
  expect(screen.getByLabelText("语气")).toBeInTheDocument();
  expect(screen.getByLabelText("受众")).toBeInTheDocument();
  expect(screen.getByLabelText("卖点")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "生成脚本" })).toBeInTheDocument();
  expect(screen.getByText("候选签名密钥未配置")).toBeInTheDocument();
});

it("generates script and shows per-shot candidate actions", async () => {
  const user = userEvent.setup();
  mockedFetchOnlineMaterialStatus.mockResolvedValue({
    providers: [{ provider: "pexels", configured: true, enabled: true }],
    default_provider: "auto",
    candidate_token_secret_configured: true,
  });
  mockedGenerateScript.mockResolvedValue({
    id: "script-1",
    title: "睡前精油短视频",
    topic: "精油睡眠放松",
    aspect_ratio: "9:16",
    duration_seconds: 10,
    provider: "heuristic",
    created_at: "2026-06-14T00:00:00+00:00",
    shots: [
      {
        index: 1,
        duration: 5,
        narration: "旁白",
        subtitle: "字幕",
        visual_description: "relaxing bedroom night",
        keywords: ["relaxing bedroom night"],
      },
    ],
  });
  mockedSearchOnlineMaterials.mockResolvedValue([
    {
      provider: "pexels",
      asset_id: "123",
      query: "relaxing bedroom night",
      source_url: "https://www.pexels.com/video/123/",
      preview_url: "https://images.pexels.com/videos/123/preview.jpg",
      candidate_token: "signed-token",
      file_variant: "hd",
      duration: 8.5,
      width: 1080,
      height: 1920,
      license_note: "Pexels source metadata retained",
    },
  ]);
  renderApp();

  await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
  await user.click(screen.getByRole("button", { name: "生成脚本" }));

  expect(await screen.findByText("镜头 1")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "搜索素材" }));
  expect(await screen.findByRole("button", { name: "选择候选" })).toBeInTheDocument();
  expect(screen.getByText("Pexels")).toBeInTheDocument();
  expect(screen.getByText("8.5 秒 · 1080×1920 · hd")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "替换候选" })).toBeInTheDocument();
});

it("keeps per-shot partial failure recoverable", async () => {
  const user = userEvent.setup();
  mockedFetchOnlineMaterialStatus.mockResolvedValue({
    providers: [{ provider: "pexels", configured: true, enabled: true }],
    default_provider: "auto",
    candidate_token_secret_configured: true,
  });
  mockedGenerateScript.mockResolvedValue({
    id: "script-1",
    title: "睡前精油短视频",
    topic: "精油睡眠放松",
    aspect_ratio: "9:16",
    duration_seconds: 10,
    provider: "heuristic",
    created_at: "2026-06-14T00:00:00+00:00",
    shots: [
      { index: 1, duration: 5, narration: "旁白 1", subtitle: "字幕 1", visual_description: "relaxing bedroom night", keywords: ["relaxing bedroom night"] },
      { index: 2, duration: 5, narration: "旁白 2", subtitle: "字幕 2", visual_description: "oil bottle close up", keywords: ["oil bottle"] },
    ],
  });
  mockedSearchOnlineMaterials.mockRejectedValueOnce(new Error("ONLINE_MATERIAL_PROVIDER_NOT_CONFIGURED"));
  mockedSearchOnlineMaterials.mockResolvedValueOnce([]);
  renderApp();

  await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
  await user.click(screen.getByRole("button", { name: "生成脚本" }));
  await user.click((await screen.findAllByRole("button", { name: "搜索素材" }))[0]);

  expect(await screen.findByText("镜头 1 搜索失败")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "重试镜头 1" }));
  expect(mockedSearchOnlineMaterials).toHaveBeenCalledTimes(2);
});

it("can use existing local material for a shot", async () => {
  const user = userEvent.setup();
  mockedFetchOnlineMaterialStatus.mockResolvedValue({
    providers: [{ provider: "pexels", configured: true, enabled: true }],
    default_provider: "auto",
    candidate_token_secret_configured: true,
  });
  mockedFetchMaterials.mockResolvedValue([
    {
      id: "material-real-1",
      original_filename: "oil-bottle.mp4",
      content_type: "video/mp4",
      size_bytes: 128,
      created_at: "2026-06-14T00:00:00+00:00",
      source_type: "upload",
      download_url: "/api/materials/material-real-1/download",
    },
  ]);
  mockedGenerateScript.mockResolvedValue({
    id: "script-1",
    title: "本地素材脚本",
    topic: "精油睡眠放松",
    aspect_ratio: "9:16",
    duration_seconds: 5,
    provider: "heuristic",
    created_at: "2026-06-14T00:00:00+00:00",
    shots: [{ index: 1, duration: 5, narration: "旁白", subtitle: "字幕", visual_description: "oil bottle", keywords: ["oil bottle"] }],
  });
  renderApp();

  await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
  await user.click(screen.getByRole("button", { name: "生成脚本" }));
  await user.click(await screen.findByRole("button", { name: "改用已有本地素材" }));

  expect(await screen.findByRole("dialog", { name: "选择本地素材" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "选择 oil-bottle.mp4" }));

  expect(screen.getByText("oil-bottle.mp4")).toBeInTheDocument();
});

it("submits edited script fields and selected real material id", async () => {
  const user = userEvent.setup();
  mockedFetchOnlineMaterialStatus.mockResolvedValue({
    providers: [{ provider: "pexels", configured: true, enabled: true }],
    default_provider: "auto",
    candidate_token_secret_configured: true,
  });
  mockedFetchMaterials.mockResolvedValue([
    {
      id: "material-real-1",
      original_filename: "oil-bottle.mp4",
      content_type: "video/mp4",
      size_bytes: 128,
      created_at: "2026-06-14T00:00:00+00:00",
      source_type: "upload",
      download_url: "/api/materials/material-real-1/download",
    },
  ]);
  mockedGenerateScript.mockResolvedValue({
    id: "script-1",
    title: "原始标题",
    topic: "精油睡眠放松",
    aspect_ratio: "9:16",
    duration_seconds: 5,
    provider: "heuristic",
    created_at: "2026-06-14T00:00:00+00:00",
    shots: [{ index: 1, duration: 5, narration: "原始旁白", subtitle: "字幕", visual_description: "oil bottle", keywords: ["oil bottle"] }],
  });
  mockedCreateOnlineMixTask.mockResolvedValue({
    id: "task-1",
    title: "任务",
    output: { download_url: "/api/tasks/task-1/output" },
  });
  renderApp();

  await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
  await user.click(screen.getByRole("button", { name: "生成脚本" }));
  await user.clear(await screen.findByLabelText("脚本标题"));
  await user.type(screen.getByLabelText("脚本标题"), "编辑后的标题");
  await user.clear(screen.getByLabelText("镜头 1 旁白"));
  await user.type(screen.getByLabelText("镜头 1 旁白"), "编辑后的旁白");
  await user.clear(screen.getByLabelText("镜头 1 时长"));
  await user.type(screen.getByLabelText("镜头 1 时长"), "8");
  await user.clear(screen.getByLabelText("镜头 1 关键词"));
  await user.type(screen.getByLabelText("镜头 1 关键词"), "sleep oil,calm");
  await user.click(screen.getByRole("button", { name: "改用已有本地素材" }));
  await user.click(await screen.findByRole("button", { name: "选择 oil-bottle.mp4" }));
  await user.click(screen.getByRole("button", { name: "创建任务" }));

  expect(mockedCreateOnlineMixTask).toHaveBeenCalledWith(
    expect.objectContaining({
      script: expect.objectContaining({
        title: "编辑后的标题",
        shots: [
          expect.objectContaining({
            duration: 8,
            keywords: ["sleep oil", "calm"],
            narration: "编辑后的旁白",
          }),
        ],
      }),
      shot_materials: [{ shot_index: 1, material_id: "material-real-1" }],
    }),
  );
});

it("shows create failure with collapsible error details", async () => {
  const user = userEvent.setup();
  mockedFetchOnlineMaterialStatus.mockResolvedValue({
    providers: [{ provider: "pexels", configured: true, enabled: true }],
    default_provider: "auto",
    candidate_token_secret_configured: true,
  });
  mockedFetchMaterials.mockResolvedValue([
    {
      id: "material-real-1",
      original_filename: "oil-bottle.mp4",
      content_type: "video/mp4",
      size_bytes: 128,
      created_at: "2026-06-14T00:00:00+00:00",
      source_type: "upload",
      download_url: "/api/materials/material-real-1/download",
    },
  ]);
  mockedGenerateScript.mockResolvedValue({
    id: "script-1",
    title: "失败脚本",
    topic: "精油睡眠放松",
    aspect_ratio: "9:16",
    duration_seconds: 5,
    provider: "heuristic",
    created_at: "2026-06-14T00:00:00+00:00",
    shots: [{ index: 1, duration: 5, narration: "旁白", subtitle: "字幕", visual_description: "oil bottle", keywords: ["oil bottle"] }],
  });
  mockedCreateOnlineMixTask.mockRejectedValue(new Error("ONLINE_MATERIAL_DOWNLOAD_FAILED"));
  renderApp();

  await user.type(await screen.findByLabelText("视频主题"), "精油睡眠放松");
  await user.click(screen.getByRole("button", { name: "生成脚本" }));
  await user.click(screen.getByRole("button", { name: "改用已有本地素材" }));
  await user.click(await screen.findByRole("button", { name: "选择 oil-bottle.mp4" }));
  await user.click(screen.getByRole("button", { name: "创建任务" }));

  expect(await screen.findByText("创建失败")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重试创建" })).toBeInTheDocument();
  expect(screen.getByText("错误列表")).toBeInTheDocument();
  expect(screen.getByText("ONLINE_MATERIAL_DOWNLOAD_FAILED")).toBeInTheDocument();
});

it("renders mobile collapsible shots and vertical candidate cards", async () => {
  Object.defineProperty(window, "innerWidth", { value: 390, configurable: true });
  mockedFetchOnlineMaterialStatus.mockResolvedValue({
    providers: [{ provider: "pexels", configured: true, enabled: true }],
    default_provider: "auto",
    candidate_token_secret_configured: true,
  });
  renderApp();

  const workbench = await screen.findByTestId("online-remix-workbench");
  expect(workbench).toHaveClass("online-remix-panel");
  expect(workbench).toHaveAttribute("data-mobile-layout", "collapsible-shots");
});
```

- [ ] **Step 2: Run frontend tests to verify failure**

Run:

```bash
cd frontend && npm test -- --run src/App.test.tsx
```

Expected: FAIL because `onlineRemix` API and workbench UI do not exist.

- [ ] **Step 3: Implement typed API client**

Create `frontend/src/api/onlineRemix.ts`:

```ts
export interface ScriptShot {
  index: number;
  duration: number;
  narration: string;
  subtitle: string;
  visual_description: string;
  keywords: string[];
}

export interface GeneratedScript {
  id: string;
  title: string;
  topic: string;
  aspect_ratio: string;
  duration_seconds: number;
  provider: string;
  created_at: string;
  shots: ScriptShot[];
}

export interface OnlineMaterialStatus {
  providers: Array<{ provider: string; configured: boolean; enabled: boolean }>;
  default_provider: string;
  candidate_token_secret_configured: boolean;
}

export interface OnlineMaterialCandidate {
  provider: string;
  asset_id: string;
  query: string;
  source_url: string;
  preview_url: string;
  candidate_token: string;
  file_variant: string;
  duration: number;
  width: number;
  height: number;
  license_note: string;
}

export interface LocalMaterial {
  id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
  download_url: string;
  source_type: "upload" | "online";
  source_provider?: string | null;
  source_url?: string | null;
  license_note?: string | null;
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload?.detail?.code ?? `HTTP_${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchOnlineMaterialStatus(): Promise<OnlineMaterialStatus> {
  return readJson(await fetch("/api/online-materials/status"));
}

export async function fetchMaterials(): Promise<LocalMaterial[]> {
  return readJson(await fetch("/api/materials?limit=100&offset=0"));
}

export async function generateScript(input: {
  topic: string;
  duration_seconds: number;
  aspect_ratio: string;
  tone: string;
  target_audience: string;
  selling_points: string[];
  provider: "auto" | "llm_only" | "heuristic";
}): Promise<GeneratedScript> {
  return readJson(
    await fetch("/api/scripts/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}

export async function searchOnlineMaterials(input: {
  query: string;
  aspect_ratio: string;
  min_duration_seconds: number;
  provider: string;
}): Promise<OnlineMaterialCandidate[]> {
  return readJson(
    await fetch("/api/online-materials/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}

export async function createOnlineMixTask(input: unknown): Promise<{
  id: string;
  title: string;
  output: { download_url: string };
}> {
  return readJson(
    await fetch("/api/online-mix/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}
```

- [ ] **Step 4: Implement online remix workbench component**

Create `frontend/src/components/OnlineRemixWorkbench.tsx` with visible labels, 44px buttons, loading/retry states, a mobile `details/summary` 可折叠镜头列表, vertical candidate cards, and no implementation-explainer copy:

```tsx
import { useMutation, useQuery } from "@tanstack/react-query";
import { FolderOpen, RefreshCw, Search, Sparkles } from "lucide-react";
import { useState } from "react";

import {
  GeneratedScript,
  LocalMaterial,
  OnlineMaterialCandidate,
  createOnlineMixTask,
  fetchMaterials,
  fetchOnlineMaterialStatus,
  generateScript,
  searchOnlineMaterials,
} from "../api/onlineRemix";

type ShotSearchState = "idle" | "searching" | "ready" | "failed" | "empty";

export function OnlineRemixWorkbench() {
  const [topic, setTopic] = useState("");
  const [durationSeconds, setDurationSeconds] = useState(30);
  const [aspectRatio, setAspectRatio] = useState("9:16");
  const [tone, setTone] = useState("自然可信");
  const [targetAudience, setTargetAudience] = useState("");
  const [sellingPoints, setSellingPoints] = useState("");
  const [script, setScript] = useState<GeneratedScript | null>(null);
  const [provider, setProvider] = useState("auto");
  const [shotState, setShotState] = useState<Record<number, ShotSearchState>>({});
  const [candidatesByShot, setCandidatesByShot] = useState<Record<number, OnlineMaterialCandidate[]>>({});
  const [selectedByShot, setSelectedByShot] = useState<Record<number, OnlineMaterialCandidate>>({});
  const [localMaterialByShot, setLocalMaterialByShot] = useState<Record<number, string>>({});
  const [localPickerShot, setLocalPickerShot] = useState<number | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const status = useQuery({ queryKey: ["online-material-status"], queryFn: fetchOnlineMaterialStatus });
  const materials = useQuery({ queryKey: ["materials"], queryFn: fetchMaterials });
  const generate = useMutation({
    mutationFn: () =>
      generateScript({
        topic,
        provider: "auto",
        duration_seconds: durationSeconds,
        aspect_ratio: aspectRatio,
        tone,
        target_audience: targetAudience,
        selling_points: sellingPoints.split(/[，,]/).map((item) => item.trim()).filter(Boolean),
      }),
    onSuccess: (payload) => {
      setScript(payload);
      setSelectedByShot({});
      setLocalMaterialByShot({});
      setErrors([]);
    },
    onError: (error) => {
      setErrors((current) => [...current, error instanceof Error ? error.message : "SCRIPT_GENERATE_FAILED"]);
    },
  });
  const search = useMutation({
    mutationFn: async (shot: GeneratedScript["shots"][number]) =>
      searchOnlineMaterials({
        query: shot.keywords[0] ?? shot.visual_description,
        aspect_ratio: script?.aspect_ratio ?? "9:16",
        min_duration_seconds: shot.duration,
        provider,
      }),
    onMutate: (shot) => {
      setShotState((current) => ({ ...current, [shot.index]: "searching" }));
    },
    onSuccess: (candidates, shot) => {
      setCandidatesByShot((current) => ({ ...current, [shot.index]: candidates }));
      setShotState((current) => ({ ...current, [shot.index]: candidates.length ? "ready" : "empty" }));
    },
    onError: (_error, shot) => {
      setShotState((current) => ({ ...current, [shot.index]: "failed" }));
      setErrors((current) => [...current, `镜头 ${shot.index} 搜索失败`]);
    },
  });
  const createTask = useMutation({
    mutationFn: () =>
      createOnlineMixTask({
        title: script?.title ?? topic,
        script,
        asset_strategy: "manual",
        provider,
        shot_assets: Object.entries(selectedByShot).map(([shotIndex, candidate]) => ({
          shot_index: Number(shotIndex),
          candidate_token: candidate.candidate_token,
        })),
        shot_materials: Object.entries(localMaterialByShot).map(([shotIndex, materialId]) => ({
          shot_index: Number(shotIndex),
          material_id: materialId,
        })),
        options: { aspect_ratio: script?.aspect_ratio ?? "9:16", resolution: "1080p" },
      }),
    onError: (error) => {
      setErrors((current) => [...current, error instanceof Error ? error.message : "CREATE_TASK_FAILED"]);
    },
  });

  const missingSecret = status.data && !status.data.candidate_token_secret_configured;
  const selectedCount = Object.keys(selectedByShot).length + Object.keys(localMaterialByShot).length;
  const findMaterial = (materialId: string): LocalMaterial | undefined =>
    materials.data?.find((material) => material.id === materialId);
  const updateScript = (updater: (current: GeneratedScript) => GeneratedScript) => {
    setScript((current) => (current ? updater(current) : current));
  };
  const updateShot = (shotIndex: number, patch: Partial<GeneratedScript["shots"][number]>) => {
    updateScript((current) => ({
      ...current,
      shots: current.shots.map((shot) => (shot.index === shotIndex ? { ...shot, ...patch } : shot)),
    }));
  };

  return (
    <article className="panel online-remix-panel" aria-label="线上混剪" data-testid="online-remix-workbench" data-mobile-layout="collapsible-shots">
      <div className="panel-heading">
        <h2>线上混剪</h2>
        <span>{missingSecret ? "候选签名密钥未配置" : "线上素材源状态可用时可搜索候选"}</span>
      </div>
      <form
        className="online-remix-form"
        onSubmit={(event) => {
          event.preventDefault();
          generate.mutate();
        }}
      >
        <label>
          <span>视频主题</span>
          <input value={topic} onChange={(event) => setTopic(event.target.value)} />
        </label>
        <label>
          <span>时长</span>
          <input type="number" min="5" max="300" value={durationSeconds} onChange={(event) => setDurationSeconds(Number(event.target.value))} />
        </label>
        <label>
          <span>画幅</span>
          <select value={aspectRatio} onChange={(event) => setAspectRatio(event.target.value)}>
            <option value="9:16">9:16</option>
            <option value="16:9">16:9</option>
          </select>
        </label>
        <label>
          <span>语气</span>
          <input value={tone} onChange={(event) => setTone(event.target.value)} />
        </label>
        <label>
          <span>受众</span>
          <input value={targetAudience} onChange={(event) => setTargetAudience(event.target.value)} />
        </label>
        <label>
          <span>卖点</span>
          <input value={sellingPoints} onChange={(event) => setSellingPoints(event.target.value)} />
        </label>
        <label>
          <span>素材源</span>
          <select value={provider} onChange={(event) => setProvider(event.target.value)}>
            <option value="auto">Auto</option>
            <option value="pexels">Pexels</option>
            <option value="pixabay">Pixabay</option>
          </select>
        </label>
        <button className="primary-action" disabled={!topic.trim() || generate.isPending} type="submit">
          <Sparkles aria-hidden="true" size={18} />
          {generate.isPending ? "生成中" : "生成脚本"}
        </button>
      </form>
      {generate.isError ? (
        <div className="inline-error" role="alert">
          脚本生成失败
          <button type="button" onClick={() => generate.mutate()}>
            <RefreshCw aria-hidden="true" size={16} />
            重试
          </button>
        </div>
      ) : null}
      {errors.length ? (
        <details className="error-list" open>
          <summary>错误列表</summary>
          <ul>
            {errors.map((error, index) => (
              <li key={`${error}-${index}`}>{error}</li>
            ))}
          </ul>
        </details>
      ) : null}
      {script ? (
        <div className="shot-list">
          <label>
            <span>脚本标题</span>
            <input value={script.title} onChange={(event) => updateScript((current) => ({ ...current, title: event.target.value }))} />
          </label>
          {script.shots.map((shot) => (
            <details className="shot-row" key={shot.index} open={shot.index === 1}>
              <summary>
                <h3>镜头 {shot.index}</h3>
                <span>{shotState[shot.index] ?? "idle"}</span>
              </summary>
              <div>
                <label>
                  <span>镜头 {shot.index} 旁白</span>
                  <textarea value={shot.narration} onChange={(event) => updateShot(shot.index, { narration: event.target.value })} />
                </label>
                <label>
                  <span>镜头 {shot.index} 字幕</span>
                  <input value={shot.subtitle} onChange={(event) => updateShot(shot.index, { subtitle: event.target.value })} />
                </label>
                <label>
                  <span>镜头 {shot.index} 时长</span>
                  <input
                    type="number"
                    min="1"
                    value={shot.duration}
                    onChange={(event) => updateShot(shot.index, { duration: Number(event.target.value) })}
                  />
                </label>
                <label>
                  <span>镜头 {shot.index} 关键词</span>
                  <input
                    value={shot.keywords.join(",")}
                    onChange={(event) =>
                      updateShot(shot.index, {
                        keywords: event.target.value
                          .split(/[，,]/)
                          .map((item) => item.trim())
                          .filter(Boolean),
                      })
                    }
                  />
                </label>
                <label>
                  <span>镜头 {shot.index} 画面</span>
                  <textarea value={shot.visual_description} onChange={(event) => updateShot(shot.index, { visual_description: event.target.value })} />
                </label>
              </div>
              <button type="button" onClick={() => search.mutate(shot)}>
                <Search aria-hidden="true" size={16} />
                搜索素材
              </button>
              {shotState[shot.index] === "failed" ? (
                <div className="inline-error" role="alert">
                  镜头 {shot.index} 搜索失败
                  <button type="button" onClick={() => search.mutate(shot)}>
                    <RefreshCw aria-hidden="true" size={16} />
                    重试镜头 {shot.index}
                  </button>
                </div>
              ) : null}
              {shotState[shot.index] === "empty" ? (
                <div className="inline-error" role="status">
                  镜头 {shot.index} 暂无候选
                  <button type="button" onClick={() => search.mutate(shot)}>重试镜头 {shot.index}</button>
                </div>
              ) : null}
              <button type="button" onClick={() => setLocalPickerShot(shot.index)}>
                <FolderOpen aria-hidden="true" size={16} />
                改用已有本地素材
              </button>
              {localMaterialByShot[shot.index] ? (
                <span className="selected-material">{findMaterial(localMaterialByShot[shot.index])?.original_filename ?? localMaterialByShot[shot.index]}</span>
              ) : null}
              {(candidatesByShot[shot.index] ?? []).map((candidate) => (
                <div className="candidate-row" key={candidate.candidate_token}>
                  <span>{candidate.provider === "pexels" ? "Pexels" : "Pixabay"}</span>
                  <span>{candidate.duration} 秒 · {candidate.width}×{candidate.height} · {candidate.file_variant}</span>
                  <a href={candidate.source_url}>素材源详情</a>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedByShot((current) => ({ ...current, [shot.index]: candidate }));
                      setLocalMaterialByShot((current) => {
                        const next = { ...current };
                        delete next[shot.index];
                        return next;
                      });
                    }}
                  >
                    选择候选
                  </button>
                  <button type="button" onClick={() => search.mutate(shot)}>
                    替换候选
                  </button>
                </div>
              ))}
            </details>
          ))}
        </div>
      ) : null}
      {localPickerShot ? (
        <div role="dialog" aria-label="选择本地素材" className="local-material-dialog">
          {(materials.data ?? []).map((material) => (
            <button
              key={material.id}
              type="button"
              onClick={() => {
                setLocalMaterialByShot((current) => ({ ...current, [localPickerShot]: material.id }));
                setSelectedByShot((current) => {
                  const next = { ...current };
                  delete next[localPickerShot];
                  return next;
                });
                setLocalPickerShot(null);
              }}
            >
              选择 {material.original_filename}
            </button>
          ))}
          {materials.data?.length === 0 ? <span>暂无本地素材</span> : null}
          <button type="button" onClick={() => setLocalPickerShot(null)}>关闭</button>
        </div>
      ) : null}
      {script ? (
        <button
          className="primary-action"
          disabled={selectedCount === 0 || createTask.isPending}
          type="button"
          onClick={() => createTask.mutate()}
        >
          {createTask.isPending ? "创建中" : "创建任务"}
        </button>
      ) : null}
      {createTask.isError ? (
        <div className="inline-error" role="alert">
          创建失败
          <button type="button" onClick={() => createTask.mutate()}>
            <RefreshCw aria-hidden="true" size={16} />
            重试创建
          </button>
        </div>
      ) : null}
      {createTask.data ? <a href={createTask.data.output.download_url}>查看任务输出</a> : null}
    </article>
  );
}
```

Modify `frontend/src/App.tsx`:

```tsx
import { OnlineRemixWorkbench } from "./components/OnlineRemixWorkbench";

<section className="content-grid" id="0">
  <OnlineRemixWorkbench />
  <RuntimeStatus />
</section>
```

- [ ] **Step 5: Add responsive styles**

Append to `frontend/src/styles.css`:

```css
.online-remix-panel,
.online-remix-form,
.shot-list {
  display: grid;
  gap: 14px;
}

.online-remix-form {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
}

.online-remix-form label {
  display: grid;
  gap: 6px;
  color: var(--muted);
  font-size: 14px;
}

.online-remix-form input,
.online-remix-form select,
.shot-row input,
.shot-row textarea {
  min-height: 44px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 10px 12px;
  color: var(--text);
  font: inherit;
}

.shot-row textarea {
  resize: vertical;
  min-height: 88px;
}

button,
.primary-action {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
  font: inherit;
  cursor: pointer;
}

.primary-action {
  border-color: var(--accent);
  background: var(--accent);
  color: #ffffff;
  padding: 10px 14px;
}

button:disabled,
.primary-action:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.shot-row,
.candidate-row,
.inline-error,
.error-list,
.local-material-dialog {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
}

.shot-row {
  display: grid;
  gap: 10px;
  background: var(--surface-strong);
}

.shot-row summary {
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  cursor: pointer;
}

.shot-row h3 {
  margin: 0 0 4px;
  font-size: 16px;
}

.candidate-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: var(--surface);
}

.inline-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #8a1f11;
  background: #fff4f1;
}

.error-list {
  color: #8a1f11;
  background: #fff4f1;
}

.error-list summary {
  min-height: 44px;
  cursor: pointer;
}

.local-material-dialog {
  display: grid;
  gap: 10px;
  background: var(--surface);
}

.selected-material {
  color: var(--muted);
  font-size: 14px;
}

@media (max-width: 760px) {
  .online-remix-form,
  .candidate-row,
  .inline-error,
  .local-material-dialog {
    grid-template-columns: 1fr;
    display: grid;
  }

  .shot-list {
    gap: 10px;
  }

  .shot-row {
    padding: 10px;
  }

  .candidate-row {
    align-items: stretch;
  }

  .candidate-row a,
  .candidate-row button {
    width: 100%;
  }
}
```

- [ ] **Step 6: Run frontend tests**

Run:

```bash
cd frontend && npm test -- --run src/App.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Commit Task 7**

Run:

```bash
git add frontend/src/api/onlineRemix.ts frontend/src/components/OnlineRemixWorkbench.tsx frontend/src/App.tsx frontend/src/styles.css frontend/src/App.test.tsx
git commit -m "feat: add online remix workbench"
```

## Task 8: Documentation, Full Verification, And PR Readiness

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `docs/superpowers/plans/2026-06-14-online-free-remix-script.md` only if execution notes reveal a stale command.

- [ ] **Step 1: Update README configuration and API docs**

Modify `README.md` so the API section includes:

```markdown
- `POST /api/scripts/generate`：根据主题生成结构化分镜脚本。`provider=auto` 未配置 LLM 时使用本地启发式 fallback；`provider=llm_only` 未配置 LLM 时返回 `LLM_NOT_CONFIGURED`。
- `GET /api/online-materials/status`：查看 Pexels/Pixabay 与候选签名密钥配置状态，只返回布尔状态，不泄漏 key 或 secret。
- `POST /api/online-materials/search`：按关键词、画幅和最小时长搜索线上免费素材候选，返回 `candidate_token`、预览 URL 和来源页，不返回真实下载 URL。
- `POST /api/online-materials/download`：只接受 `candidate_token`，服务端验签后重新解析 provider 下载地址并保存到本地素材库。
- `POST /api/online-mix/tasks`：基于脚本、用户选择候选或已有本地素材创建 manifest 任务；当前仍不执行真实渲染。
```

Add config bullets:

```markdown
- `AUTOVIDEO_LLM_BASE_URL`、`AUTOVIDEO_LLM_API_KEY`、`AUTOVIDEO_LLM_MODEL`：OpenAI-compatible LLM 配置，留空时 `provider=auto` 使用启发式脚本 fallback。
- `AUTOVIDEO_PEXELS_API_KEY`、`AUTOVIDEO_PIXABAY_API_KEY`：线上免费素材源 API key，留空时线上素材搜索返回配置错误。
- `AUTOVIDEO_CANDIDATE_TOKEN_SECRET`：候选素材签名密钥；不配置时不能签发或验证可下载候选。
- `AUTOVIDEO_CANDIDATE_TOKEN_TTL_SECONDS`：候选 token 有效期，默认 `1800`。
```

- [ ] **Step 2: Run backend tests**

Run:

```bash
PYENV_VERSION=3.12.13 python -m pytest -q
```

Expected: all backend tests PASS.

- [ ] **Step 3: Run frontend tests**

Run:

```bash
cd frontend && npm test -- --run
```

Expected: all Vitest tests PASS.

- [ ] **Step 4: Build frontend**

Run:

```bash
cd frontend && npm run build
```

Expected: TypeScript and Vite build PASS.

- [ ] **Step 5: Run secret/path scans**

Run:

```bash
rg -n "100\\.95|Services/|AUTOVIDEO_.*(KEY|SECRET)=.+" . \
  --glob '!docs/superpowers/plans/2026-06-14-online-free-remix-script.md'
rg -in "退出登录|个人网盘|NAS 登录|access_token|refresh_token|bearer|authorization" frontend/src frontend/dist
```

Expected: first command has no committed old project internal path or real key/secret values. Second command has no user-facing old auth/netdisk copy in frontend source or built assets. `.env.example` may contain blank keys and documented variable names only.

- [ ] **Step 6: Run local subagent review before final PR work**

Use `superpowers:requesting-code-review` with this scope:

```text
Review the full diff for the online free material remix and script generation workflow.
Check spec compliance against docs/superpowers/specs/2026-06-14-online-free-remix-script-design.md
and implementation plan compliance against docs/superpowers/plans/2026-06-14-online-free-remix-script.md.
Focus on SSRF/download safety, token secret error priority, manifest sanitization, source metadata leakage, UI mobile usability, and test coverage.
```

Expected: reviewer returns `No actionable findings`. If it reports issues, dispatch an independent fix subagent, rerun relevant tests, and request review again.

- [ ] **Step 7: Commit documentation and any review fixes**

Run after the final review loop passes:

```bash
git add README.md .env.example docs/superpowers/plans/2026-06-14-online-free-remix-script.md
git commit -m "docs: document online remix workflow"
```

- [ ] **Step 8: Create or update PR and monitor**

Run:

```bash
git status --short --branch
git push -u origin codex/online-free-remix-script-design
gh pr create --title "[codex] Add online free remix workflow" --body "Implements the first manifest-based online free material remix workflow and script generation plan." --base main --head codex/online-free-remix-script-design
```

Expected: PR URL is created. Per `AGENTS.md`, make the PR ready for review if it is draft, then monitor Codex review every 2 minutes until Codex has no actionable findings or gives a thumbs-up/pass signal.

## Self-Review Checklist

- Spec coverage:
  - Script generation: Task 2.
  - Online material provider status/search/token: Task 4.
  - Download URL and SSRF safety: Task 5.
  - Material source metadata and manifest payload: Task 3.
  - Online mix task creation and shot selection: Task 6.
  - Frontend workflow and mobile states: Task 7.
  - README and `.env.example`: Task 8.
- Placeholder scan:
  - This plan must not contain unfinished marker text, deferred-work wording, or real credentials.
  - Redaction tests use synthetic path and network markers only; no real deployment addresses or credentials are present.
- Type consistency:
  - Backend API fields use `candidate_token`, `shot_assets`, `shot_materials`, `manifest_payload`, and `expires_at` consistently.
  - Frontend TypeScript interfaces mirror backend response fields.
- Required verification before completion:
  - `PYENV_VERSION=3.12.13 python -m pytest -q`
  - `cd frontend && npm test -- --run`
  - `cd frontend && npm run build`
  - local subagent review loop before commit/push/PR updates
  - GitHub Codex PR review monitoring after PR is ready
