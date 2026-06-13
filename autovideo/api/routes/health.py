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
