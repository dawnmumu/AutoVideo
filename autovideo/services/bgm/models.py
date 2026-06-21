from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SUPPORTED_BGM_MEDIA_TYPES: dict[str, str] = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "aac": "audio/aac",
    "ogg": "audio/ogg",
    "flac": "audio/flac",
}
SUPPORTED_BGM_EXTENSIONS = frozenset(SUPPORTED_BGM_MEDIA_TYPES)
UNCATEGORIZED_NAME = "未分类"


@dataclass(frozen=True)
class AudioProbeResult:
    duration_seconds: float
    media_type: str


@dataclass(frozen=True)
class BgmTrackFile:
    path: Path
    media_type: str
    original_filename: str

    def __iter__(self):
        yield self.path
        yield self.media_type
        yield self.original_filename


class BgmLibraryError(RuntimeError):
    code = "BGM_LIBRARY_ERROR"


class BgmLibraryCorruptError(BgmLibraryError):
    code = "BGM_LIBRARY_CORRUPT"


class BgmFileUnsupportedError(BgmLibraryError):
    code = "BGM_FILE_UNSUPPORTED"


class BgmFileEmptyError(BgmLibraryError):
    code = "BGM_FILE_EMPTY"


class BgmFileTooLargeError(BgmLibraryError):
    code = "BGM_FILE_TOO_LARGE"

    def __init__(self, max_upload_bytes: int) -> None:
        self.max_upload_bytes = max_upload_bytes
        super().__init__(str(max_upload_bytes))


class BgmTrackNotFoundError(BgmLibraryError):
    code = "BGM_TRACK_NOT_FOUND"


class BgmTrackFileDeleteError(BgmLibraryError):
    code = "BGM_TRACK_FILE_DELETE_FAILED"


class BgmCategoryNotFoundError(BgmLibraryError):
    code = "BGM_CATEGORY_NOT_FOUND"


class BgmCategoryDuplicateError(BgmLibraryError):
    code = "BGM_CATEGORY_DUPLICATE"


class BgmCategoryNameRequiredError(BgmLibraryError):
    code = "BGM_CATEGORY_NAME_REQUIRED"


class BgmTrackNameRequiredError(BgmLibraryError):
    code = "BGM_TRACK_NAME_REQUIRED"


class BgmCategoryEmptyError(BgmLibraryError):
    code = "BGM_CATEGORY_EMPTY"
