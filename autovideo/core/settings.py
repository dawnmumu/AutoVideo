from functools import cached_property
from pathlib import Path

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
    max_upload_bytes: int = Field(default=2 * 1024 * 1024 * 1024, ge=1)
    max_multipart_overhead_bytes: int = Field(default=1024 * 1024, ge=0)
    max_task_materials: int = Field(default=100, ge=1)
    max_task_options_bytes: int = Field(default=1024 * 1024, ge=1)
    max_task_request_bytes: int = Field(default=2 * 1024 * 1024, ge=1)

    model_config = SettingsConfigDict(
        env_prefix="AUTOVIDEO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("fish_speech_url", mode="before")
    @classmethod
    def empty_fish_speech_url_is_disabled(cls, value: str | None) -> str | None:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @cached_property
    def resolved_data_dir(self) -> Path:
        return self.data_dir.expanduser().resolve()

    @property
    def max_material_request_bytes(self) -> int:
        return self.max_upload_bytes + self.max_multipart_overhead_bytes
