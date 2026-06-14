from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from starlette.datastructures import UploadFile

from autovideo.storage.database import AutoVideoStore

SAFE_EXTENSION_RE = re.compile(r"^\.[A-Za-z0-9]{1,12}$")
SAFE_MATERIAL_EXTENSIONS = {
    ".aac",
    ".avi",
    ".bin",
    ".gif",
    ".jpeg",
    ".jpg",
    ".json",
    ".m4a",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".png",
    ".srt",
    ".txt",
    ".vtt",
    ".wav",
    ".webm",
    ".webp",
}
UPLOAD_CHUNK_SIZE = 1024 * 1024


class MaterialTooLargeError(Exception):
    def __init__(self, max_upload_bytes: int) -> None:
        self.max_upload_bytes = max_upload_bytes
        super().__init__(str(max_upload_bytes))


def safe_material_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if (
        extension in SAFE_MATERIAL_EXTENSIONS
        and SAFE_EXTENSION_RE.fullmatch(extension)
    ):
        return extension
    return ".bin"


def save_material(store: AutoVideoStore, upload: UploadFile) -> dict[str, object]:
    material_id = uuid.uuid4().hex
    original_filename = Path(upload.filename or "material.bin").name
    storage_path = store.paths.materials / (
        f"{material_id}{safe_material_extension(original_filename)}"
    )
    size_bytes = 0
    try:
        with storage_path.open("wb") as output_file:
            while chunk := upload.file.read(UPLOAD_CHUNK_SIZE):
                output_file.write(chunk)
                size_bytes += len(chunk)
                if size_bytes > store.settings.max_upload_bytes:
                    raise MaterialTooLargeError(store.settings.max_upload_bytes)
    except MaterialTooLargeError:
        storage_path.unlink(missing_ok=True)
        raise

    return store.insert_material(
        {
            "id": material_id,
            "original_filename": original_filename,
            "content_type": upload.content_type,
            "size_bytes": size_bytes,
            "storage_path": str(storage_path),
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
