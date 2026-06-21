from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings
from autovideo.services.bgm import AudioProbeResult


def bgm_client(tmp_path: Path, **overrides: Any) -> TestClient:
    settings = Settings(_env_file=None, data_dir=tmp_path, **overrides)
    app = create_app(settings)
    app.state.bgm_audio_probe = lambda path: AudioProbeResult(
        duration_seconds=9.75,
        media_type="audio/mpeg",
    )
    return TestClient(app)


def test_bgm_library_starts_empty_without_exposing_directory(tmp_path: Path) -> None:
    with bgm_client(tmp_path) as client:
        response = client.get("/api/bgm")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["categories"] == []
    assert payload["storage_status"] == "ready"
    assert payload["total_tracks"] == 0
    assert "mp3" in payload["supported_extensions"]
    assert "directory" not in payload
    assert "tmp_path" not in response.text
    assert str(tmp_path) not in response.text


def test_upload_bgm_track_and_download_audio(tmp_path: Path) -> None:
    content = b"fake audio bytes"

    with bgm_client(tmp_path) as client:
        category = client.post("/api/bgm/categories", json={"name": "舒缓"}).json()
        upload = client.post(
            "/api/bgm/tracks",
            data={"category_id": category["id"]},
            files={"file": ("spring.mp3", content, "audio/mpeg")},
        )
        audio = client.get(upload.json()["audio_url"])

    assert upload.status_code == 201
    payload = upload.json()
    assert payload["display_name"] == "spring"
    assert payload["category_id"] == category["id"]
    assert payload["category_name"] == "舒缓"
    assert payload["duration_seconds"] == 9.75
    assert payload["extension"] == "mp3"
    assert payload["size_bytes"] == len(content)
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/mpeg")
    assert audio.headers["x-content-type-options"] == "nosniff"
    assert audio.content == content


def test_upload_bgm_rejects_unsupported_extension(tmp_path: Path) -> None:
    with bgm_client(tmp_path) as client:
        response = client.post(
            "/api/bgm/tracks",
            files={"file": ("bad.exe", b"fake", "application/octet-stream")},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "BGM_FILE_UNSUPPORTED"


def test_upload_bgm_oversized_request_uses_global_middleware(tmp_path: Path) -> None:
    with bgm_client(tmp_path, max_upload_bytes=2, max_multipart_overhead_bytes=0) as client:
        response = client.post(
            "/api/bgm/tracks",
            files={"file": ("too-large.mp3", b"1234567890", "audio/mpeg")},
        )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "REQUEST_TOO_LARGE"
    assert response.json()["detail"]["max_request_bytes"] == 2


def test_upload_bgm_oversized_file_uses_service_limit_after_multipart_parse(tmp_path: Path) -> None:
    with bgm_client(tmp_path, max_upload_bytes=4, max_multipart_overhead_bytes=4096) as client:
        response = client.post(
            "/api/bgm/tracks",
            files={"file": ("too-large.mp3", b"12345", "audio/mpeg")},
        )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "BGM_FILE_TOO_LARGE"
    assert response.json()["detail"]["max_upload_bytes"] == 4


def test_update_and_delete_bgm_track(tmp_path: Path) -> None:
    with bgm_client(tmp_path) as client:
        category = client.post("/api/bgm/categories", json={"name": "舒缓"}).json()
        track = client.post(
            "/api/bgm/tracks",
            files={"file": ("spring.mp3", b"fake", "audio/mpeg")},
        ).json()
        updated = client.put(
            f"/api/bgm/tracks/{track['id']}",
            json={"display_name": "春日疗愈", "category_id": category["id"]},
        )
        deleted = client.delete(f"/api/bgm/tracks/{track['id']}")
        missing = client.get(f"/api/bgm/tracks/{track['id']}/file")

    assert updated.status_code == 200
    assert updated.json()["display_name"] == "春日疗愈"
    assert updated.json()["category_id"] == category["id"]
    assert deleted.status_code == 200
    assert deleted.json() == {"id": track["id"], "deleted": True}
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "BGM_TRACK_NOT_FOUND"


def test_rename_bgm_track_preserves_existing_category_when_category_omitted(
    tmp_path: Path,
) -> None:
    with bgm_client(tmp_path) as client:
        category = client.post("/api/bgm/categories", json={"name": "舒缓"}).json()
        track = client.post(
            "/api/bgm/tracks",
            data={"category_id": category["id"]},
            files={"file": ("spring.mp3", b"fake", "audio/mpeg")},
        ).json()
        response = client.put(
            f"/api/bgm/tracks/{track['id']}",
            json={"display_name": "新名字"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["display_name"] == "新名字"
    assert payload["category_id"] == category["id"]
    assert payload["category_name"] == "舒缓"


def test_update_bgm_track_with_explicit_null_category_clears_category(
    tmp_path: Path,
) -> None:
    with bgm_client(tmp_path) as client:
        category = client.post("/api/bgm/categories", json={"name": "舒缓"}).json()
        track = client.post(
            "/api/bgm/tracks",
            data={"category_id": category["id"]},
            files={"file": ("spring.mp3", b"fake", "audio/mpeg")},
        ).json()
        response = client.put(
            f"/api/bgm/tracks/{track['id']}",
            json={"display_name": "新名字", "category_id": None},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["display_name"] == "新名字"
    assert payload["category_id"] is None
    assert payload["category_name"] == "未分类"


def test_delete_category_moves_tracks_to_uncategorized(tmp_path: Path) -> None:
    with bgm_client(tmp_path) as client:
        category = client.post("/api/bgm/categories", json={"name": "舒缓"}).json()
        track = client.post(
            "/api/bgm/tracks",
            data={"category_id": category["id"]},
            files={"file": ("spring.mp3", b"fake", "audio/mpeg")},
        ).json()
        response = client.delete(f"/api/bgm/categories/{category['id']}")
        library = client.get("/api/bgm").json()

    assert response.status_code == 200
    assert response.json() == {"id": category["id"], "deleted": True}
    assert library["categories"] == []
    item = next(item for item in library["items"] if item["id"] == track["id"])
    assert item["category_id"] is None
    assert item["category_name"] == "未分类"


def test_bgm_library_returns_category_sort_order_without_exposing_directory(
    tmp_path: Path,
) -> None:
    with bgm_client(tmp_path) as client:
        first = client.post("/api/bgm/categories", json={"name": "舒缓"}).json()
        second = client.post("/api/bgm/categories", json={"name": "欢快"}).json()
        response = client.get("/api/bgm")

    assert response.status_code == 200
    payload = response.json()
    by_id = {category["id"]: category for category in payload["categories"]}
    assert first["sort_order"] == 0
    assert second["sort_order"] == 1
    assert by_id[first["id"]]["sort_order"] == 0
    assert by_id[second["id"]]["sort_order"] == 1
    assert "directory" not in payload
    assert str(tmp_path) not in response.text


def test_duplicate_category_returns_structured_error(tmp_path: Path) -> None:
    with bgm_client(tmp_path) as client:
        client.post("/api/bgm/categories", json={"name": "舒缓"})
        response = client.post("/api/bgm/categories", json={"name": " 舒缓 "})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "BGM_CATEGORY_DUPLICATE"


def test_empty_category_name_returns_structured_error(tmp_path: Path) -> None:
    with bgm_client(tmp_path) as client:
        response = client.post("/api/bgm/categories", json={"name": ""})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "BGM_CATEGORY_NAME_REQUIRED"


def test_empty_track_display_name_returns_structured_error(tmp_path: Path) -> None:
    with bgm_client(tmp_path) as client:
        track = client.post(
            "/api/bgm/tracks",
            files={"file": ("spring.mp3", b"fake", "audio/mpeg")},
        ).json()
        response = client.put(
            f"/api/bgm/tracks/{track['id']}",
            json={"display_name": ""},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "BGM_TRACK_NAME_REQUIRED"
