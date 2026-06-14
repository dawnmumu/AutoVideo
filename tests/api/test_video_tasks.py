from types import SimpleNamespace

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


def test_task_creation_rejects_missing_material(client) -> None:
    response = client.post(
        "/api/tasks",
        json={"title": "缺失素材", "material_ids": ["missing-material-id"]},
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["detail"]["code"] == "MATERIAL_NOT_FOUND"
    assert payload["detail"]["material_id"] == "missing-material-id"


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
