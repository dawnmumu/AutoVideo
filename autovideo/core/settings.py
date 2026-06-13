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
