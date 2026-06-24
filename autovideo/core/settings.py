from functools import cached_property
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AutoVideo"
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8090
    data_dir: Path = Field(default=Path("data"))
    ffmpeg_path: str = "ffmpeg"
    fish_speech_url: str | None = None
    edge_tts_default_voice: str = "zh-CN-XiaoxiaoNeural"
    max_voice_preview_text_chars: int = Field(default=300, ge=1, le=2000)
    max_voice_preview_request_bytes: int = Field(default=8192, ge=1)
    max_upload_bytes: int = Field(default=2 * 1024 * 1024 * 1024, ge=1)
    max_multipart_overhead_bytes: int = Field(default=1024 * 1024, ge=0)
    max_task_materials: int = Field(default=100, ge=1)
    max_task_options_bytes: int = Field(default=1024 * 1024, ge=1)
    max_task_request_bytes: int = Field(default=2 * 1024 * 1024, ge=1)
    llm_provider: Literal["openai_compatible"] = "openai_compatible"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: int = Field(default=45, ge=1)
    llm_temperature: float = Field(default=0.6, ge=0, le=2)
    pexels_api_key: str | None = None
    pixabay_api_key: str | None = None
    online_material_provider: Literal["auto"] = "auto"
    online_material_results_per_query: int = Field(default=8, ge=1, le=25)
    online_material_download_timeout_seconds: int = Field(default=60, ge=1)
    online_material_max_download_bytes: int = Field(default=500 * 1024 * 1024, ge=1)
    max_online_material_request_bytes: int = Field(default=65536, ge=1)
    candidate_token_secret: str | None = None
    candidate_token_ttl_seconds: int = Field(default=1800, ge=60, le=86400)
    max_script_payload_bytes: int = Field(default=65536, ge=1)
    max_online_mix_request_bytes: int = Field(default=2 * 1024 * 1024, ge=1)
    material_allowed_roots: str | None = None

    model_config = SettingsConfigDict(
        env_prefix="AUTOVIDEO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator(
        "fish_speech_url",
        "llm_base_url",
        "llm_api_key",
        "llm_model",
        "pexels_api_key",
        "pixabay_api_key",
        "candidate_token_secret",
        "material_allowed_roots",
        mode="before",
    )
    @classmethod
    def empty_string_is_disabled(cls, value: str | None) -> str | None:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @cached_property
    def resolved_data_dir(self) -> Path:
        return self.data_dir.expanduser().resolve()

    @property
    def max_material_request_bytes(self) -> int:
        return self.max_upload_bytes + self.max_multipart_overhead_bytes
