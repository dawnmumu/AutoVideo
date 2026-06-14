import asyncio
import json
from collections.abc import Iterable
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings
from autovideo.services.materials import save_material
from autovideo.storage.database import AutoVideoStore


class ChunkOnlyFile:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if size < 1:
            raise AssertionError("material uploads must be read in bounded chunks")
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


def _post_asgi(
    app,
    path: str,
    body: bytes,
    headers: Iterable[tuple[bytes, bytes]],
) -> tuple[int, dict]:
    sent_messages = []
    receive_messages = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive():
        if receive_messages:
            return receive_messages.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        sent_messages.append(message)

    async def run_request() -> None:
        await app(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.3"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": list(headers),
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
                "root_path": "",
            },
            receive,
            send,
        )

    asyncio.run(run_request())

    status_code = next(
        message["status"]
        for message in sent_messages
        if message["type"] == "http.response.start"
    )
    response_body = b"".join(
        message.get("body", b"")
        for message in sent_messages
        if message["type"] == "http.response.body"
    )
    return status_code, json.loads(response_body)


def _small_request_limit_app(tmp_path):
    return create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            fish_speech_url=None,
            max_upload_bytes=4,
            max_multipart_overhead_bytes=1,
            max_task_request_bytes=8,
        )
    )


@pytest.mark.parametrize(
    ("path", "body", "headers"),
    [
        (
            "/api/materials",
            b"not multipart",
            [(b"content-type", b"multipart/form-data; boundary=autovideo")],
        ),
        (
            "/api/tasks",
            b'{"title":"missing length"}',
            [(b"content-type", b"application/json")],
        ),
    ],
)
def test_limited_post_requires_content_length_before_body_parse(
    tmp_path,
    path: str,
    body: bytes,
    headers: list[tuple[bytes, bytes]],
) -> None:
    status_code, payload = _post_asgi(
        _small_request_limit_app(tmp_path),
        path,
        body,
        headers,
    )

    assert status_code == 411
    assert payload["detail"]["code"] == "REQUEST_LENGTH_REQUIRED"


@pytest.mark.parametrize("content_length", [b"not-a-number", b"-1"])
@pytest.mark.parametrize(
    ("path", "body", "headers"),
    [
        (
            "/api/materials",
            b"not multipart",
            [(b"content-type", b"multipart/form-data; boundary=autovideo")],
        ),
        (
            "/api/tasks",
            b'{"title":"invalid length"}',
            [(b"content-type", b"application/json")],
        ),
    ],
)
def test_limited_post_rejects_invalid_content_length_before_body_parse(
    tmp_path,
    path: str,
    body: bytes,
    headers: list[tuple[bytes, bytes]],
    content_length: bytes,
) -> None:
    status_code, payload = _post_asgi(
        _small_request_limit_app(tmp_path),
        path,
        body,
        [*headers, (b"content-length", content_length)],
    )

    assert status_code == 400
    assert payload["detail"]["code"] == "INVALID_CONTENT_LENGTH"


def test_material_upload_task_creation_and_output_download(client) -> None:
    upload_response = client.post(
        "/api/materials",
        files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
    )

    assert upload_response.status_code == 201
    material = upload_response.json()
    assert material["id"]
    assert material["original_filename"] == "clip.mp4"
    assert material["content_type"] == "video/mp4"
    assert material["size_bytes"] == len(b"fake video bytes")
    assert "storage_path" not in material

    task_response = client.post(
        "/api/tasks",
        json={
            "title": "测试混剪任务",
            "material_ids": [material["id"]],
            "options": {"aspect_ratio": "16:9", "resolution": "1080p"},
        },
    )

    assert task_response.status_code == 201
    task = task_response.json()
    assert task["id"]
    assert task["title"] == "测试混剪任务"
    assert task["status"] == "succeeded"
    assert task["material_ids"] == [material["id"]]
    assert task["options"]["aspect_ratio"] == "16:9"
    assert task["output"]["download_url"] == f"/api/tasks/{task['id']}/output"
    assert "path" not in task["output"]

    detail_response = client.get(f"/api/tasks/{task['id']}")

    assert detail_response.status_code == 200
    assert detail_response.json() == task

    output_response = client.get(task["output"]["download_url"])

    assert output_response.status_code == 200
    assert output_response.headers["content-type"].startswith("application/json")
    output = output_response.json()
    assert output["task_id"] == task["id"]
    assert output["title"] == "测试混剪任务"
    assert output["materials"][0]["id"] == material["id"]
    assert output["note"] == "这是任务骨架生成的占位输出，尚未执行真实混剪渲染。"


def test_material_save_streams_upload_in_chunks(tmp_path) -> None:
    store = AutoVideoStore(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            fish_speech_url=None,
        )
    )
    upload_file = ChunkOnlyFile([b"fake ", b"video ", b"bytes"])
    upload = SimpleNamespace(
        filename="clip.mp4",
        content_type="video/mp4",
        file=upload_file,
    )

    material = save_material(store, upload)

    assert material["size_bytes"] == len(b"fake video bytes")
    assert upload_file.read_sizes
    assert all(size > 0 for size in upload_file.read_sizes)


def test_material_upload_rejects_files_over_configured_limit(tmp_path) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            fish_speech_url=None,
            max_upload_bytes=4,
        )
    )

    with TestClient(app) as limited_client:
        response = limited_client.post(
            "/api/materials",
            files={"file": ("clip.mp4", b"12345", "video/mp4")},
        )

    assert response.status_code == 413
    payload = response.json()
    assert payload["detail"]["code"] == "MATERIAL_TOO_LARGE"
    assert payload["detail"]["max_upload_bytes"] == 4
    assert list((tmp_path / "materials").iterdir()) == []


def test_material_upload_rejects_request_content_length_before_multipart_parse(
    tmp_path,
) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            fish_speech_url=None,
            max_upload_bytes=4,
            max_multipart_overhead_bytes=1,
        )
    )

    with TestClient(app) as limited_client:
        response = limited_client.post(
            "/api/materials",
            content=b"123456",
            headers={"content-type": "multipart/form-data; boundary=autovideo"},
        )

    assert response.status_code == 413
    payload = response.json()
    assert payload["detail"]["code"] == "REQUEST_TOO_LARGE"
    assert payload["detail"]["max_request_bytes"] == 5
    materials_dir = tmp_path / "materials"
    assert not materials_dir.exists() or list(materials_dir.iterdir()) == []


def test_material_save_uses_short_server_filename_for_long_original_name(
    tmp_path,
) -> None:
    store = AutoVideoStore(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            fish_speech_url=None,
        )
    )
    long_filename = f"{'a' * 260}.mp4"
    upload = SimpleNamespace(
        filename=long_filename,
        content_type="video/mp4",
        file=ChunkOnlyFile([b"fake video bytes"]),
    )

    material = save_material(store, upload)

    storage_path = tmp_path / "materials" / f"{material['id']}.mp4"
    assert material["original_filename"] == long_filename
    assert material["storage_path"] == str(storage_path)
    assert storage_path.read_bytes() == b"fake video bytes"


def test_material_save_falls_back_to_bin_for_unsafe_or_overlong_extension(
    tmp_path,
) -> None:
    store = AutoVideoStore(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            fish_speech_url=None,
        )
    )
    upload = SimpleNamespace(
        filename=f"clip.{'x' * 80}",
        content_type="video/mp4",
        file=ChunkOnlyFile([b"fake video bytes"]),
    )

    material = save_material(store, upload)

    storage_path = tmp_path / "materials" / f"{material['id']}.bin"
    assert material["original_filename"] == f"clip.{'x' * 80}"
    assert material["storage_path"] == str(storage_path)
    assert storage_path.read_bytes() == b"fake video bytes"


def test_task_creation_rejects_missing_material(client) -> None:
    response = client.post(
        "/api/tasks",
        json={"title": "缺失素材", "material_ids": ["missing-material-id"]},
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["detail"]["code"] == "MATERIAL_NOT_FOUND"
    assert payload["detail"]["material_id"] == "missing-material-id"


def test_task_creation_rejects_request_content_length_before_json_parse(
    tmp_path,
) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            fish_speech_url=None,
            max_task_request_bytes=8,
        )
    )

    with TestClient(app) as limited_client:
        response = limited_client.post(
            "/api/tasks",
            content=b'{"title":"too large"}',
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 413
    payload = response.json()
    assert payload["detail"]["code"] == "REQUEST_TOO_LARGE"
    assert payload["detail"]["max_request_bytes"] == 8


def test_script_generation_rejects_request_content_length_before_route_handling(
    tmp_path,
) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            fish_speech_url=None,
            max_script_payload_bytes=8,
        )
    )

    with TestClient(app) as limited_client:
        response = limited_client.post(
            "/api/scripts/generate",
            content=b'{"topic":"too large"}',
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 413
    payload = response.json()
    assert payload["detail"]["code"] == "SCRIPT_PAYLOAD_TOO_LARGE"
    assert payload["detail"]["max_request_bytes"] == 8


def test_online_mix_rejects_request_content_length_before_route_handling(
    tmp_path,
) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            fish_speech_url=None,
            max_online_mix_request_bytes=8,
        )
    )

    with TestClient(app) as limited_client:
        response = limited_client.post(
            "/api/online-mix/tasks",
            content=b'{"script":{"shots":[]}}',
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 413
    payload = response.json()
    assert payload["detail"]["code"] == "REQUEST_TOO_LARGE"
    assert payload["detail"]["max_request_bytes"] == 8


def test_task_creation_rejects_too_many_material_ids(tmp_path) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            fish_speech_url=None,
            max_task_materials=1,
        )
    )

    with TestClient(app) as limited_client:
        response = limited_client.post(
            "/api/tasks",
            json={
                "title": "过多素材",
                "material_ids": ["material-1", "material-2"],
            },
        )

    assert response.status_code == 413
    payload = response.json()
    assert payload["detail"]["code"] == "TASK_MATERIAL_LIMIT_EXCEEDED"
    assert payload["detail"]["max_task_materials"] == 1
    assert payload["detail"]["material_count"] == 2


def test_task_creation_rejects_options_over_configured_limit(client) -> None:
    upload_response = client.post(
        "/api/materials",
        files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
    )
    assert upload_response.status_code == 201
    material = upload_response.json()
    client.app.state.settings.max_task_options_bytes = 8

    response = client.post(
        "/api/tasks",
        json={
            "title": "配置过大",
            "material_ids": [material["id"]],
            "options": {"long": "value"},
        },
    )

    assert response.status_code == 413
    payload = response.json()
    assert payload["detail"]["code"] == "TASK_OPTIONS_TOO_LARGE"
    assert payload["detail"]["max_task_options_bytes"] == 8
    assert payload["detail"]["options_bytes"] > 8


def test_material_and_task_lists_are_paginated(client) -> None:
    materials = []
    for index in range(3):
        response = client.post(
            "/api/materials",
            files={"file": (f"clip-{index}.mp4", b"fake video bytes", "video/mp4")},
        )
        assert response.status_code == 201
        materials.append(response.json())

    material_list_response = client.get("/api/materials?limit=2&offset=1")

    assert material_list_response.status_code == 200
    assert [item["id"] for item in material_list_response.json()] == [
        materials[1]["id"],
        materials[0]["id"],
    ]

    tasks = []
    for index in range(3):
        response = client.post(
            "/api/tasks",
            json={
                "title": f"任务 {index}",
                "material_ids": [materials[0]["id"]],
            },
        )
        assert response.status_code == 201
        tasks.append(response.json())

    task_list_response = client.get("/api/tasks?limit=2&offset=1")

    assert task_list_response.status_code == 200
    assert [item["id"] for item in task_list_response.json()] == [
        tasks[1]["id"],
        tasks[0]["id"],
    ]


def test_unknown_task_returns_structured_error(client) -> None:
    response = client.get("/api/tasks/missing-task-id")

    assert response.status_code == 404
    payload = response.json()
    assert payload["detail"]["code"] == "TASK_NOT_FOUND"
    assert payload["detail"]["task_id"] == "missing-task-id"


def test_unknown_task_output_returns_task_not_found(client) -> None:
    response = client.get("/api/tasks/missing-task-id/output")

    assert response.status_code == 404
    payload = response.json()
    assert payload["detail"]["code"] == "TASK_NOT_FOUND"
    assert payload["detail"]["task_id"] == "missing-task-id"
