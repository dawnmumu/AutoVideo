from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from autovideo.api.dependencies import get_store
from autovideo.services.materials import (
    MaterialTooLargeError,
    public_material,
    save_material,
)
from autovideo.storage.database import AutoVideoStore

router = APIRouter(prefix="/api/materials", tags=["materials"])


@router.post("", status_code=status.HTTP_201_CREATED)
def upload_material(
    file: UploadFile = File(...),
    store: AutoVideoStore = Depends(get_store),
) -> dict[str, object]:
    try:
        return public_material(save_material(store, file))
    except MaterialTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail={
                "code": "MATERIAL_TOO_LARGE",
                "max_upload_bytes": exc.max_upload_bytes,
            },
        ) from exc


@router.get("")
def list_materials(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    source_type: str | None = Query(default=None, min_length=1, max_length=40),
    source_provider: str | None = Query(default=None, min_length=1, max_length=80),
    current_material_source: bool = Query(default=False),
    store: AutoVideoStore = Depends(get_store),
) -> list[dict[str, object]]:
    return [
        public_material(material)
        for material in store.list_materials(
            limit=limit,
            offset=offset,
            source_type=source_type,
            source_provider=source_provider,
            current_material_source=current_material_source,
        )
    ]
