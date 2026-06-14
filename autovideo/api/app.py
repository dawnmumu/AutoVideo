from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from autovideo.api.routes.health import router as health_router
from autovideo.api.routes.materials import router as materials_router
from autovideo.api.routes.tasks import router as tasks_router
from autovideo.core.settings import Settings

PROJECT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIST_DIR = PROJECT_DIR / "frontend" / "dist"


def _request_length_error_response(request: Request) -> JSONResponse | None:
    content_length = request.headers.get("content-length")
    if content_length is None:
        return JSONResponse(
            status_code=status.HTTP_411_LENGTH_REQUIRED,
            content={"detail": {"code": "REQUEST_LENGTH_REQUIRED"}},
        )
    if not content_length.isdecimal():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": {"code": "INVALID_CONTENT_LENGTH"}},
        )
    return None


def _content_length_exceeds(request: Request, max_request_bytes: int) -> bool:
    content_length = request.headers["content-length"]
    return int(content_length) > max_request_bytes


def _request_too_large_response(max_request_bytes: int) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        content={
            "detail": {
                "code": "REQUEST_TOO_LARGE",
                "max_request_bytes": max_request_bytes,
            }
        },
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings()
    app = FastAPI(title=active_settings.app_name)
    app.state.settings = active_settings

    @app.middleware("http")
    async def reject_oversized_request(request: Request, call_next):
        max_request_bytes: int | None = None
        if request.method == "POST" and request.url.path == "/api/materials":
            max_request_bytes = active_settings.max_material_request_bytes
        elif request.method == "POST" and request.url.path == "/api/tasks":
            max_request_bytes = active_settings.max_task_request_bytes

        if max_request_bytes is not None:
            request_length_error = _request_length_error_response(request)
            if request_length_error is not None:
                return request_length_error
            if _content_length_exceeds(request, max_request_bytes):
                return _request_too_large_response(max_request_bytes)

        return await call_next(request)

    app.include_router(health_router)
    app.include_router(materials_router)
    app.include_router(tasks_router)
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False, response_model=None)
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
