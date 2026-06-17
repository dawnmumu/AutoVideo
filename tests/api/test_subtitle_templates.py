import math

from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings
from autovideo.services.subtitles import preview_renderer


def _client(tmp_path):
    return TestClient(create_app(Settings(_env_file=None, data_dir=tmp_path, ffmpeg_path="missing-ffmpeg")))


def test_list_create_update_validate_and_delete_template_set(tmp_path):
    with _client(tmp_path) as client:
        listing = client.get("/api/subtitle-template-sets")
        preset_id = listing.json()["presets"][0]["id"]
        created = client.post("/api/subtitle-template-sets", json={"name": "我的模板", "preset_id": preset_id})
        template_id = created.json()["id"]
        updated = client.put(
            f"/api/subtitle-template-sets/{template_id}",
            json={"name": "默认模板", "is_favorite": True},
        )
        validated = client.post("/api/subtitle-template-sets/validate", json=updated.json())
        deleted = client.delete(f"/api/subtitle-template-sets/{template_id}")

    assert listing.status_code == 200
    assert created.status_code == 201
    assert updated.json()["is_favorite"] is True
    assert validated.json()["ok"] is True
    assert deleted.status_code == 204


def test_preview_reports_ffmpeg_unavailable_without_blocking_template_save(tmp_path):
    with _client(tmp_path) as client:
        template = client.get("/api/subtitle-template-sets").json()["presets"][0]
        response = client.post(
            "/api/subtitle-template-sets/preview",
            json={
                "template_set": template,
                "template_type": "bottom",
                "aspect_ratio": "9:16",
                "sample_text": "AI 提升效率",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "SUBTITLE_PREVIEW_RENDERER_UNAVAILABLE"


def test_preview_reports_invalid_executable_ffmpeg_as_renderer_unavailable(tmp_path):
    ffmpeg_path = _write_invalid_executable_ffmpeg(tmp_path)
    with TestClient(create_app(Settings(_env_file=None, data_dir=tmp_path, ffmpeg_path=ffmpeg_path))) as client:
        template = client.get("/api/subtitle-template-sets").json()["presets"][0]
        response = client.post(
            "/api/subtitle-template-sets/preview",
            json={
                "template_set": template,
                "template_type": "bottom",
                "aspect_ratio": "9:16",
                "sample_text": "AI 提升效率",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "SUBTITLE_PREVIEW_RENDERER_UNAVAILABLE"


def test_preset_override_reset_and_timeline_preview_routes(tmp_path):
    ffmpeg_path = _write_preview_fake_ffmpeg(tmp_path)
    with TestClient(create_app(Settings(_env_file=None, data_dir=tmp_path, ffmpeg_path=ffmpeg_path))) as client:
        preset_id = client.get("/api/subtitle-template-sets").json()["presets"][0]["id"]
        overridden = client.put(
            f"/api/subtitle-template-sets/presets/{preset_id}",
            json={"name": "收藏预设", "is_favorite": True},
        )
        listing = client.get("/api/subtitle-template-sets").json()
        timeline_preview = client.post(
            "/api/subtitle-template-sets/preview-timeline",
            json={
                "template_set": overridden.json(),
                "template_type": "bottom",
                "aspect_ratio": "9:16",
                "sample_text": "AI 提升效率",
                "duration_ms": 1200,
            },
        )
        reset = client.delete(f"/api/subtitle-template-sets/presets/{preset_id}")

    assert overridden.status_code == 200
    assert any(item["is_favorite"] for item in listing["presets"] if item["id"] == preset_id)
    assert timeline_preview.status_code == 200
    assert timeline_preview.json()["mime_type"] == "video/mp4"
    assert timeline_preview.json()["duration_ms"] == 1200
    assert reset.status_code == 204


def test_update_missing_template_set_returns_not_found(tmp_path):
    with _client(tmp_path) as client:
        response = client.put(
            "/api/subtitle-template-sets/missing-template",
            json={"name": "不存在模板"},
        )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "SUBTITLE_TEMPLATE_NOT_FOUND"


def test_update_missing_preset_returns_not_found(tmp_path):
    with _client(tmp_path) as client:
        response = client.put(
            "/api/subtitle-template-sets/presets/missing-preset",
            json={"name": "不存在预设"},
        )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "SUBTITLE_TEMPLATE_NOT_FOUND"


def test_preview_timeline_normalizes_non_finite_duration_inputs_at_endpoint(tmp_path):
    ffmpeg_path = _write_preview_fake_ffmpeg(tmp_path)
    with TestClient(create_app(Settings(_env_file=None, data_dir=tmp_path, ffmpeg_path=ffmpeg_path))) as client:
        template = client.get("/api/subtitle-template-sets").json()["presets"][0]
        responses = [
            client.post(
                "/api/subtitle-template-sets/preview-timeline",
                json={
                    "template_set": template,
                    "template_type": "bottom",
                    "aspect_ratio": "9:16",
                    "sample_text": "AI 提升效率",
                    "duration_ms": duration_ms,
                },
            )
            for duration_ms in ("nan", "-inf", None)
        ]

    assert [response.status_code for response in responses] == [200, 200, 200]
    assert [response.json()["duration_ms"] for response in responses] == [1200, 1200, 1200]


def test_clean_timeline_duration_uses_default_for_non_finite_numbers():
    assert preview_renderer._clean_timeline_duration_ms(math.nan) == preview_renderer.DEFAULT_PREVIEW_DURATION_MS
    assert preview_renderer._clean_timeline_duration_ms(math.inf) == preview_renderer.DEFAULT_PREVIEW_DURATION_MS
    assert preview_renderer._clean_timeline_duration_ms("nan") == preview_renderer.DEFAULT_PREVIEW_DURATION_MS
    assert preview_renderer._clean_timeline_duration_ms("-inf") == preview_renderer.DEFAULT_PREVIEW_DURATION_MS


def _write_preview_fake_ffmpeg(tmp_path) -> str:
    ffmpeg_path = tmp_path / "preview-ffmpeg"
    ffmpeg_path.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "pathlib.Path(sys.argv[-1]).write_bytes(b'preview-media')\n",
        encoding="utf-8",
    )
    ffmpeg_path.chmod(0o755)
    return str(ffmpeg_path)


def _write_invalid_executable_ffmpeg(tmp_path) -> str:
    ffmpeg_path = tmp_path / "invalid-ffmpeg"
    ffmpeg_path.write_text("not a valid executable\n", encoding="utf-8")
    ffmpeg_path.chmod(0o755)
    return str(ffmpeg_path)
