from fastapi import Depends, Request

from autovideo.core.settings import Settings
from autovideo.storage.database import AutoVideoStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_store(settings: Settings = Depends(get_settings)) -> AutoVideoStore:
    return AutoVideoStore(settings)
