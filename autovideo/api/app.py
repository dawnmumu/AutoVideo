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
