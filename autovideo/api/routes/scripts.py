from __future__ import annotations

import json
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from autovideo.api.dependencies import get_settings
from autovideo.api.errors import structured_error
from autovideo.core.settings import Settings
from autovideo.services.scripts import (
    LlmNotConfiguredError,
    LlmResponseInvalidError,
    ScriptPayloadTooLargeError,
    ScriptTextInvalidError,
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
    script_text: str | None = None
    max_single_duration: float | None = Field(default=None, ge=1, le=300)


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
    except ScriptTextInvalidError as exc:
        raise structured_error(
            status.HTTP_400_BAD_REQUEST,
            "SCRIPT_TEXT_INVALID",
            "脚本中没有可用内容",
        ) from exc
    except LlmNotConfiguredError as exc:
        raise structured_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "LLM_NOT_CONFIGURED",
            "未配置 LLM 服务",
        ) from exc
    except (
        httpx.HTTPError,
        KeyError,
        json.JSONDecodeError,
        LlmResponseInvalidError,
    ) as exc:
        raise structured_error(
            status.HTTP_502_BAD_GATEWAY,
            "LLM_GENERATION_FAILED",
            "LLM 生成脚本失败",
        ) from exc
