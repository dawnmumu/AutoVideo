from fastapi import Request

from autovideo.core.settings import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings
