from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from autovideo.storage.database import AutoVideoStore

PLACEHOLDER_OUTPUT_NOTE = "这是任务骨架生成的占位输出，尚未执行真实混剪渲染。"
RESERVED_MANIFEST_PAYLOAD_KEYS = frozenset(
    {"task_id", "title", "materials", "options", "note"}
)
SENSITIVE_MANIFEST_KEY_RE = re.compile(
    r"("
    r"token|api[_-]?key|secret|password|credentials?|signature|"
    r"authorization|auth[_-]?header|storage[_-]?path|"
    r"download[_-]?url|media[_-]?url"
    r")",
    re.IGNORECASE,
)
ABSOLUTE_LOCAL_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"((?:file://)?/"
    r"(Users|Volumes|private|tmp|var|home|opt|app|mnt|workspace|srv)(?=/|$)|"
    r"[A-Za-z]:\\)"
)
RELATIVE_LOCAL_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9:/])"
    r"\.{1,2}/data/materials/[^\s\"'<>]+",
    re.IGNORECASE,
)
PRIVATE_OR_INTERNAL_URL_RE = re.compile(
    r"https?://("
    r"localhost|127\.|0\.0\.0\.0|"
    r"10\.|169\.254\.|"
    r"172\.(1[6-9]|2\d|3[0-1])\.|"
    r"192\.168\.|"
    r"100\.6[4-9]\.|100\.[7-9]\d\.|100\.1[01]\d\.|100\.12[0-7]\.|"
    r"[^/\s\"']+\.(internal|local)"
    r")[^\s\"']*",
    re.IGNORECASE,
)
DIRECT_MEDIA_URL_RE = re.compile(
    r"https?://[^\s\"'<>]+\."
    r"(mp4|mov|webm|m4v|mp3|wav|aac|flac|ogg|srt|vtt|jpe?g|png|webp|gif)"
    r"([?#][^\s\"'<>]*)?",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
AUTH_CREDENTIAL_RE = re.compile(
    r"(authorization\s*:|bearer\s+\S+|basic\s+\S+)",
    re.IGNORECASE,
)
SENSITIVE_URL_QUERY_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "auth",
        "authorization",
        "client_secret",
        "credential",
        "credentials",
        "password",
        "secret",
        "signature",
        "sig",
        "token",
        "access_token",
        "refresh_token",
        "x_amz_credential",
        "x_amz_security_token",
        "x_amz_signature",
    }
)
REDACTION_TEST_MARKER_RE = re.compile(
    r"<OLD_PROJECT_(DEPLOY_PATH|INTERNAL_ADDRESS)>"
)


class MaterialNotFoundError(Exception):
    def __init__(self, material_id: str) -> None:
        self.material_id = material_id
        super().__init__(material_id)


class TaskMaterialLimitExceededError(Exception):
    def __init__(self, material_count: int, max_task_materials: int) -> None:
        self.material_count = material_count
        self.max_task_materials = max_task_materials
        super().__init__(str(material_count))


class TaskOptionsTooLargeError(Exception):
    def __init__(self, options_bytes: int, max_task_options_bytes: int) -> None:
        self.options_bytes = options_bytes
        self.max_task_options_bytes = max_task_options_bytes
        super().__init__(str(options_bytes))


class TaskNotFoundError(Exception):
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        super().__init__(task_id)


class OutputNotFoundError(Exception):
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        super().__init__(task_id)


def encoded_json_size(value: Any) -> int:
    return len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


def _normalized_manifest_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _url_has_sensitive_query(value: str) -> bool:
    for match in URL_RE.finditer(value):
        url = match.group(0).rstrip(").,;")
        query = urlsplit(url).query
        if not query:
            continue
        for key, _ in parse_qsl(query, keep_blank_values=True):
            if _normalized_manifest_key(key) in SENSITIVE_URL_QUERY_KEYS:
                return True
    return False


def _is_sensitive_manifest_string(value: str) -> bool:
    return (
        ABSOLUTE_LOCAL_PATH_RE.search(value) is not None
        or RELATIVE_LOCAL_PATH_RE.search(value) is not None
        or PRIVATE_OR_INTERNAL_URL_RE.search(value) is not None
        or DIRECT_MEDIA_URL_RE.search(value) is not None
        or _url_has_sensitive_query(value)
        or AUTH_CREDENTIAL_RE.search(value) is not None
        or REDACTION_TEST_MARKER_RE.search(value) is not None
    )


def sanitize_manifest_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            if SENSITIVE_MANIFEST_KEY_RE.search(str(key)):
                continue
            sanitized[key] = sanitize_manifest_payload(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_manifest_payload(item) for item in value]
    if isinstance(value, str) and _is_sensitive_manifest_string(value):
        return "[redacted]"
    return value


def create_task(
    store: AutoVideoStore,
    *,
    title: str,
    material_ids: list[str],
    options: dict[str, Any],
    manifest_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    material_count = len(material_ids)
    if material_count > store.settings.max_task_materials:
        raise TaskMaterialLimitExceededError(
            material_count,
            store.settings.max_task_materials,
        )

    options_bytes = encoded_json_size(options)
    if options_bytes > store.settings.max_task_options_bytes:
        raise TaskOptionsTooLargeError(
            options_bytes,
            store.settings.max_task_options_bytes,
        )
    sanitized_options = sanitize_manifest_payload(options)
    if not isinstance(sanitized_options, dict):
        sanitized_options = {}

    materials = []
    for material_id in material_ids:
        material = store.get_material(material_id)
        if material is None:
            raise MaterialNotFoundError(material_id)
        materials.append(material)

    task_id = uuid.uuid4().hex
    now = datetime.now(UTC).isoformat()
    output_dir = store.paths.outputs / task_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "manifest.json"
    output_payload = {
        "task_id": task_id,
        "title": title,
        "materials": [
            {
                "id": material["id"],
                "original_filename": material["original_filename"],
                "size_bytes": material["size_bytes"],
                "content_type": material["content_type"],
            }
            for material in materials
        ],
        "options": sanitized_options,
        "note": PLACEHOLDER_OUTPUT_NOTE,
    }
    if manifest_payload:
        for key, value in sanitize_manifest_payload(manifest_payload).items():
            if key not in RESERVED_MANIFEST_PAYLOAD_KEYS:
                output_payload[key] = value
    output_path.write_text(
        json.dumps(output_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return store.insert_task(
        {
            "id": task_id,
            "title": title,
            "status": "succeeded",
            "material_ids": material_ids,
            "options": sanitized_options,
            "output": {
                "path": str(output_path),
                "download_url": f"/api/tasks/{task_id}/output",
            },
            "created_at": now,
            "updated_at": now,
        }
    )


def require_task(store: AutoVideoStore, task_id: str) -> dict[str, Any]:
    task = store.get_task(task_id)
    if task is None:
        raise TaskNotFoundError(task_id)
    return task


def require_output_path(store: AutoVideoStore, task_id: str):
    require_task(store, task_id)
    path = store.output_path_for(task_id)
    if path is None or not path.is_file():
        raise OutputNotFoundError(task_id)
    return path
