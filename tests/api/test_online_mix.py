import json
import os

from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings


def _script() -> dict:
    return {
        "id": "script-1",
        "title": "睡前精油短视频",
        "topic": "精油睡眠放松",
        "aspect_ratio": "9:16",
        "duration_seconds": 10,
        "shots": [
            {
                "index": 1,
                "duration": 5,
                "narration": "旁白 1",
                "subtitle": "字幕 1",
                "visual_description": "relaxing bedroom night",
                "keywords": ["relaxing bedroom night"],
            },
            {
                "index": 2,
                "duration": 5,
                "narration": "旁白 2",
                "subtitle": "字幕 2",
                "visual_description": "oil bottle close up",
                "keywords": ["oil bottle"],
            },
        ],
        "provider": "heuristic",
        "created_at": "2026-06-14T00:00:00+00:00",
    }


def _single_shot_script() -> dict:
    script = _script()
    script["shots"] = [script["shots"][0]]
    script["duration_seconds"] = 5
    return script


def _write_fake_ffmpeg(tmp_path) -> str:
    log_path = tmp_path / "ffmpeg-argv.json"
    ffmpeg_path = tmp_path / "fake-ffmpeg"
    ffmpeg_path.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import pathlib\n"
        "import sys\n"
        f"pathlib.Path({str(log_path)!r}).write_text("
        "json.dumps(sys.argv[1:], ensure_ascii=False), encoding='utf-8')\n"
        "pathlib.Path(sys.argv[-1]).write_bytes(b'rendered video')\n",
        encoding="utf-8",
    )
    os.chmod(ffmpeg_path, 0o755)
    return str(ffmpeg_path)


def _write_failing_fake_ffmpeg(tmp_path) -> str:
    ffmpeg_path = tmp_path / "failing-online-mix-ffmpeg"
    ffmpeg_path.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "sys.stderr.write('base render failed')\n"
        "sys.exit(12)\n",
        encoding="utf-8",
    )
    ffmpeg_path.chmod(0o755)
    return str(ffmpeg_path)


def _write_leaky_failing_fake_ffmpeg(tmp_path) -> str:
    ffmpeg_path = tmp_path / "leaky-failing-online-mix-ffmpeg"
    ffmpeg_path.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "sys.stderr.write('token=render-secret-token ' + ' '.join(sys.argv))\n"
        "sys.exit(12)\n",
        encoding="utf-8",
    )
    ffmpeg_path.chmod(0o755)
    return str(ffmpeg_path)


def _write_plain_secret_failing_fake_ffmpeg(tmp_path, stderr: str) -> str:
    ffmpeg_path = tmp_path / "plain-secret-failing-online-mix-ffmpeg"
    ffmpeg_path.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        f"sys.stderr.write({stderr!r})\n"
        "sys.exit(12)\n",
        encoding="utf-8",
    )
    ffmpeg_path.chmod(0o755)
    return str(ffmpeg_path)


def test_online_mix_renders_video_and_writes_timeline_when_ffmpeg_available(
    tmp_path,
) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path=_write_fake_ffmpeg(tmp_path),
        )
    )

    with TestClient(app) as client:
        first_material = client.post(
            "/api/materials",
            files={"file": ("clip-1.mp4", b"fake video bytes 1", "video/mp4")},
        ).json()
        second_material = client.post(
            "/api/materials",
            files={"file": ("clip-2.mp4", b"fake video bytes 2", "video/mp4")},
        ).json()
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "本地素材渲染",
                "script": _script(),
                "asset_strategy": "manual",
                "shot_materials": [
                    {"shot_index": 1, "material_id": first_material["id"]},
                    {"shot_index": 2, "material_id": second_material["id"]},
                ],
                "options": {"aspect_ratio": "9:16", "subtitle_enabled": False},
            },
        )
        task = response.json()
        output_response = client.get(task["output"]["download_url"])

    assert response.status_code == 201
    assert output_response.status_code == 200
    assert output_response.headers["content-type"].startswith("video/mp4")
    assert output_response.content == b"rendered video"

    output_dir = tmp_path / "outputs" / task["id"]
    timeline = json.loads((output_dir / "timeline.json").read_text(encoding="utf-8"))
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    argv = json.loads((tmp_path / "ffmpeg-argv.json").read_text(encoding="utf-8"))

    assert (output_dir / "subtitles.srt").is_file()
    assert timeline["total_duration"] == 10
    assert [
        (item["shot_index"], item["start_time"], item["end_time"])
        for item in timeline["items"]
    ] == [(1, 0, 5), (2, 5, 10)]
    assert timeline["items"][0]["narration"] == "旁白 1"
    assert timeline["items"][0]["subtitle"] == "字幕 1"
    assert manifest["render_plan"]["status"] == "video_rendered"
    assert manifest["render_plan"]["renderer"] == "ffmpeg"
    assert argv[-1].endswith("output.mp4")


def test_online_mix_cleans_unregistered_output_dir_when_ffmpeg_fails(
    tmp_path,
) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path=_write_failing_fake_ffmpeg(tmp_path),
        )
    )

    with TestClient(app) as client:
        first_material = client.post(
            "/api/materials",
            files={"file": ("clip-1.mp4", b"fake video bytes 1", "video/mp4")},
        ).json()
        second_material = client.post(
            "/api/materials",
            files={"file": ("clip-2.mp4", b"fake video bytes 2", "video/mp4")},
        ).json()
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "失败渲染清理",
                "script": _script(),
                "asset_strategy": "manual",
                "shot_materials": [
                    {"shot_index": 1, "material_id": first_material["id"]},
                    {"shot_index": 2, "material_id": second_material["id"]},
                ],
                "options": {"aspect_ratio": "9:16", "subtitle_enabled": False},
            },
        )
        tasks_response = client.get("/api/tasks")

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "FFMPEG_RENDER_FAILED"
    assert tasks_response.json() == []
    assert list((tmp_path / "outputs").iterdir()) == []


def test_online_mix_rejects_duplicate_or_conflicting_shot_selection(client) -> None:
    material_response = client.post(
        "/api/materials",
        files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
    )
    material = material_response.json()
    response = client.post(
        "/api/online-mix/tasks",
        json={
            "title": "冲突任务",
            "script": _script(),
            "shot_assets": [{"shot_index": 1, "candidate_token": "token"}],
            "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MIX_SHOT_SELECTION_INVALID"


def test_online_mix_rejects_duplicate_material_selection(client) -> None:
    material_response = client.post(
        "/api/materials",
        files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
    )
    material = material_response.json()
    response = client.post(
        "/api/online-mix/tasks",
        json={
            "title": "重复本地素材",
            "script": _script(),
            "shot_materials": [
                {"shot_index": 1, "material_id": material["id"]},
                {"shot_index": 1, "material_id": material["id"]},
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MIX_SHOT_SELECTION_INVALID"


def test_online_mix_rejects_script_with_duplicate_shot_indexes(client) -> None:
    material_response = client.post(
        "/api/materials",
        files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
    )
    material = material_response.json()
    script = _script()
    script["shots"][1]["index"] = 1

    response = client.post(
        "/api/online-mix/tasks",
        json={
            "title": "重复镜头脚本",
            "script": script,
            "asset_strategy": "manual",
            "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MIX_SHOT_SELECTION_INVALID"


def test_online_mix_rejects_out_of_range_selection_before_provider_checks(
    tmp_path,
) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "越界镜头",
                "script": _script(),
                "shot_assets": [{"shot_index": 99, "candidate_token": "invalid"}],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MIX_SHOT_SELECTION_INVALID"


def test_online_mix_creates_manifest_with_user_materials(client) -> None:
    material_response = client.post(
        "/api/materials",
        files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
    )
    material = material_response.json()
    response = client.post(
        "/api/online-mix/tasks",
        json={
            "title": "本地素材混剪",
            "script": _script(),
            "asset_strategy": "manual",
            "shot_materials": [
                {"shot_index": 1, "material_id": material["id"]},
                {"shot_index": 2, "material_id": material["id"]},
            ],
            "options": {"aspect_ratio": "9:16"},
        },
    )

    assert response.status_code == 201
    task = response.json()
    output = client.get(task["output"]["download_url"]).json()
    assert output["script"]["id"] == "script-1"
    assert output["shot_materials"][0]["selection_mode"] == "user_material"
    serialized = json.dumps(output, ensure_ascii=False)
    assert "storage_path" not in serialized
    assert '"candidate_token":' not in serialized
    assert "<OLD_PROJECT_DEPLOY_PATH>" not in serialized


def test_online_mix_sanitizes_sensitive_options_in_manifest(client) -> None:
    material_response = client.post(
        "/api/materials",
        files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
    )
    material = material_response.json()
    response = client.post(
        "/api/online-mix/tasks",
        json={
            "title": "敏感配置混剪",
            "script": _script(),
            "asset_strategy": "manual",
            "shot_materials": [
                {"shot_index": 1, "material_id": material["id"]},
                {"shot_index": 2, "material_id": material["id"]},
            ],
            "options": {
                "aspect_ratio": "9:16",
                "subtitle_enabled": False,
                "candidate_token": "signed-token",
                "provider_download_url": (
                    "https://videos.pexels.com/video-files/123/clip.mp4"
                ),
                "render_profile": {"preset": "fast"},
            },
        },
    )

    assert response.status_code == 201
    output = client.get(response.json()["output"]["download_url"]).json()
    assert output["options"] == {
        "aspect_ratio": "9:16",
        "subtitle_enabled": False,
        "render_profile": {"preset": "fast"},
    }
    serialized = json.dumps(output, ensure_ascii=False)
    assert "signed-token" not in serialized
    assert "provider_download_url" not in serialized
    assert "videos.pexels.com" not in serialized


def test_online_mix_persists_subtitle_snapshot_and_font_override(tmp_path):
    app = create_app(
        Settings(data_dir=tmp_path, ffmpeg_path="missing-autovideo-ffmpeg-binary")
    )

    with TestClient(app) as client:
        material = client.post(
            "/api/materials", files={"file": ("clip.mp4", b"fake", "video/mp4")}
        ).json()
        template = client.get("/api/subtitle-template-sets").json()["presets"][0]
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "字幕快照",
                "script": _single_shot_script(),
                "asset_strategy": "manual",
                "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
                "options": {
                    "aspect_ratio": "9:16",
                    "subtitle_enabled": True,
                    "subtitle_template_snapshot": template,
                    "subtitle_template_set_id": template["id"],
                    "subtitle_font_family": "Noto Sans CJK SC",
                },
            },
        )
        task = response.json()

    manifest = json.loads(
        (tmp_path / "outputs" / task["id"] / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    snapshot = manifest["subtitle_template_snapshot"]
    assert response.status_code == 201
    assert manifest["subtitle_enabled"] is True
    assert snapshot["id"] == template["id"]
    assert "template_variants" in snapshot
    assert snapshot["templates"]["bottom"]["font_family"] == "Noto Sans CJK SC"
    assert snapshot["blocks"][0]["style"]["font_family"] == "Noto Sans CJK SC"
    assert manifest["render_plan"]["subtitles_ass"] == "subtitles.ass"


def test_online_mix_rejects_snapshot_id_mismatch(tmp_path):
    app = create_app(
        Settings(data_dir=tmp_path, ffmpeg_path="missing-autovideo-ffmpeg-binary")
    )

    with TestClient(app) as client:
        material = client.post(
            "/api/materials", files={"file": ("clip.mp4", b"fake", "video/mp4")}
        ).json()
        template = client.get("/api/subtitle-template-sets").json()["presets"][0]
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "快照不匹配",
                "script": _single_shot_script(),
                "asset_strategy": "manual",
                "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
                "options": {
                    "subtitle_enabled": True,
                    "subtitle_template_set_id": "different-id",
                    "subtitle_template_snapshot": template,
                },
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "SUBTITLE_TEMPLATE_INVALID"


def test_online_mix_keeps_manifest_and_ass_when_base_video_fails(tmp_path):
    app = create_app(
        Settings(data_dir=tmp_path, ffmpeg_path=_write_failing_fake_ffmpeg(tmp_path))
    )

    with TestClient(app) as client:
        material = client.post(
            "/api/materials", files={"file": ("clip.mp4", b"fake", "video/mp4")}
        ).json()
        template = client.get("/api/subtitle-template-sets").json()["presets"][0]
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "保留字幕产物",
                "script": _single_shot_script(),
                "asset_strategy": "manual",
                "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
                "options": {
                    "subtitle_enabled": True,
                    "subtitle_template_snapshot": template,
                    "subtitle_template_set_id": template["id"],
                },
            },
        )
        task = response.json()

    output_dir = tmp_path / "outputs" / task["id"]
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert response.status_code == 201
    assert manifest["render_plan"]["status"] == "base_video_failed"
    assert (output_dir / "timeline.json").is_file()
    assert (output_dir / "subtitles.srt").is_file()
    assert (output_dir / "subtitles.ass").is_file()


def test_online_mix_sanitizes_render_error_summary_when_base_video_fails(tmp_path):
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path=_write_leaky_failing_fake_ffmpeg(tmp_path),
        )
    )

    with TestClient(app) as client:
        material = client.post(
            "/api/materials", files={"file": ("clip.mp4", b"fake", "video/mp4")}
        ).json()
        template = client.get("/api/subtitle-template-sets").json()["presets"][0]
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "错误摘要脱敏",
                "script": _single_shot_script(),
                "asset_strategy": "manual",
                "shot_materials": [{"shot_index": 1, "material_id": material["id"]}],
                "options": {
                    "subtitle_enabled": True,
                    "subtitle_template_snapshot": template,
                    "subtitle_template_set_id": template["id"],
                },
            },
        )
        task = response.json()
        output = client.get(task["output"]["download_url"]).json()

    manifest = json.loads(
        (tmp_path / "outputs" / task["id"] / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    summary = output["render_plan"]["error_summary"]
    render_plan_json = json.dumps(output["render_plan"], ensure_ascii=False)
    manifest_json = json.dumps(manifest, ensure_ascii=False)

    assert response.status_code == 201
    assert summary == "[redacted]"
    assert "render-secret-token" not in render_plan_json
    assert "render-secret-token" not in manifest_json
    assert str(tmp_path) not in render_plan_json
    assert str(tmp_path) not in manifest_json
    assert "materials" not in render_plan_json
    assert "outputs" not in render_plan_json


def test_online_mix_sanitizes_plain_secret_render_error_summary(tmp_path):
    for index, stderr in enumerate(
        [
            "token=plain-secret-value",
            "secret: plain-secret-value",
            "password plain-secret-value",
            "api_key=plain-secret-value",
            "api key: plain-secret-value",
            "X-API-Key: plain-secret-value",
            "x_api_key=plain-secret-value",
            "x api key plain-secret-value",
            "x-api key: plain-secret-value",
            "ACCESS-token=plain-secret-value",
        ],
        start=1,
    ):
        data_dir = tmp_path / f"case-{index}"
        data_dir.mkdir()
        app = create_app(
            Settings(
                data_dir=data_dir,
                ffmpeg_path=_write_plain_secret_failing_fake_ffmpeg(
                    data_dir,
                    stderr,
                ),
            )
        )

        with TestClient(app) as client:
            material = client.post(
                "/api/materials", files={"file": ("clip.mp4", b"fake", "video/mp4")}
            ).json()
            template = client.get("/api/subtitle-template-sets").json()["presets"][0]
            response = client.post(
                "/api/online-mix/tasks",
                json={
                    "title": "纯密钥错误摘要脱敏",
                    "script": _single_shot_script(),
                    "asset_strategy": "manual",
                    "shot_materials": [
                        {"shot_index": 1, "material_id": material["id"]}
                    ],
                    "options": {
                        "subtitle_enabled": True,
                        "subtitle_template_snapshot": template,
                        "subtitle_template_set_id": template["id"],
                    },
                },
            )
            task = response.json()
            output = client.get(task["output"]["download_url"]).json()

        manifest = json.loads(
            (data_dir / "outputs" / task["id"] / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        summary = output["render_plan"]["error_summary"]
        serialized = json.dumps(
            [output["render_plan"], manifest["render_plan"]],
            ensure_ascii=False,
        )

        assert response.status_code == 201
        assert output["render_plan"]["status"] == "base_video_failed"
        assert summary == "[redacted]"
        assert "plain-secret-value" not in serialized
        assert stderr not in serialized


def test_online_mix_manifest_records_captioned_local_source_masks(tmp_path):
    from datetime import UTC, datetime

    from autovideo.storage.database import AutoVideoStore

    settings = Settings(data_dir=tmp_path, ffmpeg_path="missing-ffmpeg")
    store = AutoVideoStore(settings)
    captioned_dir = tmp_path / "字幕素材"
    clean_dir = tmp_path / "clean"
    captioned_dir.mkdir()
    clean_dir.mkdir()
    captioned_path = captioned_dir / "clip.mp4"
    clean_path = clean_dir / "clip.mp4"
    captioned_path.write_bytes(b"captioned")
    clean_path.write_bytes(b"clean")
    now = datetime.now(UTC).isoformat()
    captioned = store.insert_material(
        {
            "id": "captioned-local",
            "original_filename": "clip.mp4",
            "content_type": "video/mp4",
            "size_bytes": captioned_path.stat().st_size,
            "storage_path": str(captioned_path),
            "created_at": now,
            "source_type": "upload",
        }
    )
    clean = store.insert_material(
        {
            "id": "clean-local",
            "original_filename": "clip.mp4",
            "content_type": "video/mp4",
            "size_bytes": clean_path.stat().st_size,
            "storage_path": str(clean_path),
            "created_at": now,
            "source_type": "upload",
        }
    )
    app = create_app(settings)

    with TestClient(app) as client:
        template = client.get("/api/subtitle-template-sets").json()["presets"][0]
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "源字幕遮挡",
                "script": _script(),
                "asset_strategy": "manual",
                "shot_materials": [
                    {"shot_index": 1, "material_id": captioned["id"]},
                    {"shot_index": 2, "material_id": clean["id"]},
                ],
                "options": {
                    "subtitle_enabled": True,
                    "subtitle_template_snapshot": template,
                    "subtitle_template_set_id": template["id"],
                },
            },
        )
        task = response.json()

    output_dir = tmp_path / "outputs" / task["id"]
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert response.status_code == 201
    assert manifest["render_plan"]["status"] == "manifest_only"
    assert manifest["render_plan"]["base_video_skipped"] is True
    assert manifest["render_plan"]["subtitle_burn_skipped"] is True
    assert manifest["render_plan"]["source_subtitle_masked"] is True
    assert manifest["render_plan"]["source_subtitle_mask_count"] == 1
    assert manifest["render_plan"]["source_subtitle_masks"] == [True, False]


def test_online_mix_sanitizes_timeline_manifest_and_artifacts_when_ffmpeg_unavailable(
    tmp_path,
) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
        )
    )
    script = _single_shot_script()
    script["shots"][0]["visual_description"] = (
        "直接素材 https://cdn.example.com/private/clip.mp4?token=direct-secret"
    )
    script["shots"][0]["narration"] = (
        "旁白引用 https://example.com/story?id=1&token=query-secret"
    )
    script["shots"][0]["subtitle"] = "字幕来自 /Users/sha/private/subtitle.srt"

    with TestClient(app) as client:
        material = client.post(
            "/api/materials",
            files={"file": ("clip.mp4", b"fake video bytes", "video/mp4")},
        ).json()
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "敏感 timeline 混剪",
                "script": script,
                "asset_strategy": "manual",
                "shot_materials": [
                    {"shot_index": 1, "material_id": material["id"]},
                ],
            },
        )
        task = response.json()
        output = client.get(task["output"]["download_url"]).json()

    output_dir = tmp_path / "outputs" / task["id"]
    timeline = json.loads((output_dir / "timeline.json").read_text(encoding="utf-8"))
    subtitles = (output_dir / "subtitles.srt").read_text(encoding="utf-8")

    assert response.status_code == 201
    assert output["render_plan"]["renderer"] == "ffmpeg_unavailable"
    assert output["timeline"]["items"][0]["visual_description"] == "[redacted]"
    assert output["timeline"]["items"][0]["narration"] == "[redacted]"
    assert output["timeline"]["items"][0]["subtitle"] == "[redacted]"
    assert timeline["items"][0]["visual_description"] == "[redacted]"
    assert timeline["items"][0]["narration"] == "[redacted]"
    assert timeline["items"][0]["subtitle"] == "[redacted]"
    assert "[redacted]" in subtitles

    serialized = "\n".join(
        [
            json.dumps(output, ensure_ascii=False),
            json.dumps(timeline, ensure_ascii=False),
            subtitles,
        ]
    )
    for leaked in [
        "cdn.example.com",
        "direct-secret",
        "query-secret",
        "/Users/sha/private",
    ]:
        assert leaked not in serialized


def test_online_mix_requires_secret_for_user_candidate_token(tmp_path) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "候选任务",
                "script": _script(),
                "shot_assets": [{"shot_index": 1, "candidate_token": "token"}],
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == (
        "ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED"
    )


def test_online_mix_user_candidate_secret_check_ignores_requested_provider(
    tmp_path,
) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "候选任务",
                "script": _script(),
                "asset_strategy": "manual",
                "provider": "pixabay",
                "shot_assets": [{"shot_index": 1, "candidate_token": "token"}],
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == (
        "ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED"
    )


def test_online_mix_requested_disabled_provider_is_not_available(tmp_path) -> None:
    from tests.api.test_online_materials import DisabledProvider

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": DisabledProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "禁用素材源",
                "script": _script(),
                "asset_strategy": "auto",
                "provider": "pexels",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_PROVIDER_NOT_AVAILABLE"
    assert response.json()["detail"]["provider"] == "pexels"


def test_online_mix_downloads_user_candidate_and_creates_task(tmp_path) -> None:
    import httpx

    from autovideo.services.online_materials import CandidateTokenService
    from tests.api.test_online_materials import FakeProvider

    class DownloadProvider(FakeProvider):
        allowed_download_hosts = {"videos.pexels.com"}

        def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
            return "https://videos.pexels.com/video-files/123/clip.mp4"

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": DownloadProvider()}
    app.state.online_download_http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "video/mp4"},
                content=b"video",
                extensions={"connected_address": "93.184.216.34"},
            )
        )
    )
    app.state.online_download_resolver = lambda host: ["93.184.216.34"]
    token = CandidateTokenService(secret="secret", ttl_seconds=1800).sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom night",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )

    with TestClient(app) as client:
        material = client.post(
            "/api/materials",
            files={"file": ("clip.mp4", b"fake", "video/mp4")},
        ).json()
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "候选素材混剪",
                "script": _script(),
                "asset_strategy": "manual",
                "shot_assets": [{"shot_index": 1, "candidate_token": token}],
                "shot_materials": [
                    {"shot_index": 2, "material_id": material["id"]}
                ],
            },
        )

        output = client.get(response.json()["output"]["download_url"]).json()

    assert response.status_code == 201
    assert output["shot_materials"][0]["provider"] == "pexels"
    assert output["shot_materials"][0]["source_url"] == (
        "https://www.pexels.com/video/123/"
    )
    assert output["shot_materials"][0]["license_note"] == (
        "pexels source metadata retained"
    )
    assert output["source_attribution"] == [
        {
            "provider": "pexels",
            "source_asset_id": "123",
            "source_url": "https://www.pexels.com/video/123/",
            "license_note": "pexels source metadata retained",
            "query": "relaxing bedroom night",
        }
    ]
    assert output["provider_status_snapshot"] == {
        "default_provider": "auto",
        "candidate_token_secret_configured": True,
        "providers": [
            {"provider": "pexels", "configured": True, "enabled": True},
            {"provider": "pixabay", "configured": False, "enabled": False},
        ],
    }


def test_online_mix_invalid_subtitle_template_does_not_download_candidate(
    tmp_path,
) -> None:
    import httpx

    from autovideo.services.online_materials import CandidateTokenService
    from tests.api.test_online_materials import FakeProvider

    class CountingDownloadProvider(FakeProvider):
        allowed_download_hosts = {"videos.pexels.com"}

        def __init__(self) -> None:
            self.download_calls = 0

        def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
            self.download_calls += 1
            return "https://videos.pexels.com/video-files/123/clip.mp4"

    provider = CountingDownloadProvider()
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": provider}
    app.state.online_download_http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "video/mp4"},
                content=b"video",
                extensions={"connected_address": "93.184.216.34"},
            )
        )
    )
    app.state.online_download_resolver = lambda host: ["93.184.216.34"]
    token = CandidateTokenService(secret="secret", ttl_seconds=1800).sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom night",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )

    with TestClient(app) as client:
        material = client.post(
            "/api/materials",
            files={"file": ("clip.mp4", b"fake", "video/mp4")},
        ).json()
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "无效字幕模板不下载",
                "script": _script(),
                "asset_strategy": "manual",
                "shot_assets": [{"shot_index": 1, "candidate_token": token}],
                "shot_materials": [
                    {"shot_index": 2, "material_id": material["id"]}
                ],
                "options": {
                    "subtitle_enabled": True,
                    "subtitle_template_set_id": "missing-template",
                },
            },
        )
        materials = client.get("/api/materials").json()

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "SUBTITLE_TEMPLATE_INVALID"
    assert provider.download_calls == 0
    assert [item["id"] for item in materials] == [material["id"]]


def test_online_mix_auto_searches_downloads_and_creates_shot_materials(
    tmp_path,
) -> None:
    import httpx

    from tests.api.test_online_materials import FakeProvider

    class DownloadProvider(FakeProvider):
        allowed_download_hosts = {"videos.pexels.com"}

        def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
            return "https://videos.pexels.com/video-files/123/clip.mp4"

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": DownloadProvider()}
    app.state.online_download_http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "video/mp4"},
                content=b"video",
                extensions={"connected_address": "93.184.216.34"},
            )
        )
    )
    app.state.online_download_resolver = lambda host: ["93.184.216.34"]

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "自动素材混剪",
                "script": _script(),
                "asset_strategy": "auto",
                "provider": "pexels",
            },
        )
        output = client.get(response.json()["output"]["download_url"]).json()

    assert response.status_code == 201
    assert [item["shot_index"] for item in output["shot_materials"]] == [1, 2]
    assert all(
        item["selection_mode"] in {"auto", "user_candidate"}
        for item in output["shot_materials"]
    )
    assert all(item["provider"] == "pexels" for item in output["shot_materials"])
    assert len(output["source_attribution"]) == 1


def test_online_mix_auto_prefers_unused_provider_assets(tmp_path) -> None:
    import httpx

    from autovideo.services.online_materials import OnlineMaterialCandidate

    class DuplicateFirstProvider:
        name = "pexels"
        enabled = True
        allowed_download_hosts = {"videos.pexels.com"}

        def search(
            self,
            query: str,
            aspect_ratio: str,
            min_duration_seconds: int,
            limit: int,
        ):
            return [
                OnlineMaterialCandidate(
                    provider="pexels",
                    asset_id="123",
                    query=query,
                    source_url="https://www.pexels.com/video/123/",
                    preview_url="https://images.pexels.com/videos/123/preview.jpg",
                    file_variant="hd",
                    duration=8.5,
                    width=1080,
                    height=1920,
                    license_note="Pexels source metadata retained",
                ),
                OnlineMaterialCandidate(
                    provider="pexels",
                    asset_id="456",
                    query=query,
                    source_url="https://www.pexels.com/video/456/",
                    preview_url="https://images.pexels.com/videos/456/preview.jpg",
                    file_variant="hd",
                    duration=8.5,
                    width=1080,
                    height=1920,
                    license_note="Pexels source metadata retained",
                ),
            ]

        def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
            return f"https://videos.pexels.com/video-files/{asset_id}/clip.mp4"

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": DuplicateFirstProvider()}
    app.state.online_download_http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "video/mp4"},
                content=b"video",
                extensions={"connected_address": "93.184.216.34"},
            )
        )
    )
    app.state.online_download_resolver = lambda host: ["93.184.216.34"]

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "自动素材去重",
                "script": _script(),
                "asset_strategy": "auto",
                "provider": "pexels",
            },
        )
        output = client.get(response.json()["output"]["download_url"]).json()

    assert response.status_code == 201
    assert [
        item["source_asset_id"] for item in output["shot_materials"]
    ] == ["123", "456"]
    assert [
        item["source_asset_id"] for item in output["source_attribution"]
    ] == ["123", "456"]


def test_online_mix_auto_avoids_user_candidate_asset(tmp_path) -> None:
    import httpx

    from autovideo.services.online_materials import (
        CandidateTokenService,
        OnlineMaterialCandidate,
    )

    class DuplicateFirstProvider:
        name = "pexels"
        enabled = True
        allowed_download_hosts = {"videos.pexels.com"}

        def search(
            self,
            query: str,
            aspect_ratio: str,
            min_duration_seconds: int,
            limit: int,
        ):
            return [
                OnlineMaterialCandidate(
                    provider="pexels",
                    asset_id="123",
                    query=query,
                    source_url="https://www.pexels.com/video/123/",
                    preview_url="https://images.pexels.com/videos/123/preview.jpg",
                    file_variant="hd",
                    duration=8.5,
                    width=1080,
                    height=1920,
                    license_note="Pexels source metadata retained",
                ),
                OnlineMaterialCandidate(
                    provider="pexels",
                    asset_id="456",
                    query=query,
                    source_url="https://www.pexels.com/video/456/",
                    preview_url="https://images.pexels.com/videos/456/preview.jpg",
                    file_variant="hd",
                    duration=8.5,
                    width=1080,
                    height=1920,
                    license_note="Pexels source metadata retained",
                ),
            ]

        def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
            return f"https://videos.pexels.com/video-files/{asset_id}/clip.mp4"

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": DuplicateFirstProvider()}
    app.state.online_download_http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "video/mp4"},
                content=b"video",
                extensions={"connected_address": "93.184.216.34"},
            )
        )
    )
    app.state.online_download_resolver = lambda host: ["93.184.216.34"]
    token = CandidateTokenService(secret="secret", ttl_seconds=1800).sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom night",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )
    script = _script()

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "用户候选后自动去重",
                "script": script,
                "asset_strategy": "auto",
                "provider": "pexels",
                "shot_assets": [{"shot_index": 1, "candidate_token": token}],
            },
        )
        output = client.get(response.json()["output"]["download_url"]).json()

    assert response.status_code == 201
    assert [
        item["source_asset_id"] for item in output["shot_materials"]
    ] == ["123", "456"]


def test_online_mix_auto_avoids_existing_online_material_asset(tmp_path) -> None:
    import httpx

    from autovideo.services.materials import record_material_file
    from autovideo.services.online_materials import OnlineMaterialCandidate
    from autovideo.storage.database import AutoVideoStore

    class DuplicateFirstProvider:
        name = "pexels"
        enabled = True
        allowed_download_hosts = {"videos.pexels.com"}

        def search(
            self,
            query: str,
            aspect_ratio: str,
            min_duration_seconds: int,
            limit: int,
        ):
            return [
                OnlineMaterialCandidate(
                    provider="pexels",
                    asset_id="123",
                    query=query,
                    source_url="https://www.pexels.com/video/123/",
                    preview_url="https://images.pexels.com/videos/123/preview.jpg",
                    file_variant="hd",
                    duration=8.5,
                    width=1080,
                    height=1920,
                    license_note="Pexels source metadata retained",
                ),
                OnlineMaterialCandidate(
                    provider="pexels",
                    asset_id="456",
                    query=query,
                    source_url="https://www.pexels.com/video/456/",
                    preview_url="https://images.pexels.com/videos/456/preview.jpg",
                    file_variant="hd",
                    duration=8.5,
                    width=1080,
                    height=1920,
                    license_note="Pexels source metadata retained",
                ),
            ]

        def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
            return f"https://videos.pexels.com/video-files/{asset_id}/clip.mp4"

    settings = Settings(
        data_dir=tmp_path,
        ffmpeg_path="missing-autovideo-ffmpeg-binary",
        pexels_api_key="pexels-key",
        candidate_token_secret="secret",
    )
    store = AutoVideoStore(settings)
    existing_path = tmp_path / "materials" / "pexels-123.mp4"
    existing_path.write_bytes(b"existing")
    existing = record_material_file(
        store,
        "pexels-123.mp4",
        "video/mp4",
        existing_path.stat().st_size,
        existing_path,
        {
            "source_type": "online",
            "source_provider": "pexels",
            "source_asset_id": "123",
            "source_url": "https://www.pexels.com/video/123/",
            "license_note": "pexels source metadata retained",
            "query": "relaxing bedroom night",
        },
    )
    app = create_app(settings)
    app.state.online_material_providers = {"pexels": DuplicateFirstProvider()}
    app.state.online_download_http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "video/mp4"},
                content=b"video",
                extensions={"connected_address": "93.184.216.34"},
            )
        )
    )
    app.state.online_download_resolver = lambda host: ["93.184.216.34"]

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "已有线上素材后自动去重",
                "script": _script(),
                "asset_strategy": "auto",
                "provider": "pexels",
                "shot_materials": [{"shot_index": 1, "material_id": existing["id"]}],
            },
        )
        output = client.get(response.json()["output"]["download_url"]).json()

    assert response.status_code == 201
    assert [
        item["source_asset_id"] for item in output["shot_materials"]
    ] == ["123", "456"]


def test_online_mix_auto_records_reason_when_reusing_exhausted_asset(tmp_path) -> None:
    import httpx

    from autovideo.services.materials import record_material_file
    from autovideo.services.online_materials import OnlineMaterialCandidate
    from autovideo.storage.database import AutoVideoStore

    class SingleAssetProvider:
        name = "pexels"
        enabled = True
        allowed_download_hosts = {"videos.pexels.com"}

        def search(
            self,
            query: str,
            aspect_ratio: str,
            min_duration_seconds: int,
            limit: int,
        ):
            return [
                OnlineMaterialCandidate(
                    provider="pexels",
                    asset_id="123",
                    query=query,
                    source_url="https://www.pexels.com/video/123/",
                    preview_url="https://images.pexels.com/videos/123/preview.jpg",
                    file_variant="hd",
                    duration=8.5,
                    width=1080,
                    height=1920,
                    license_note="Pexels source metadata retained",
                )
            ]

        def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
            return f"https://videos.pexels.com/video-files/{asset_id}/clip.mp4"

    settings = Settings(
        data_dir=tmp_path,
        ffmpeg_path="missing-autovideo-ffmpeg-binary",
        pexels_api_key="pexels-key",
        candidate_token_secret="secret",
    )
    store = AutoVideoStore(settings)
    existing_path = tmp_path / "materials" / "pexels-123.mp4"
    existing_path.write_bytes(b"existing")
    existing = record_material_file(
        store,
        "pexels-123.mp4",
        "video/mp4",
        existing_path.stat().st_size,
        existing_path,
        {
            "source_type": "online",
            "source_provider": "pexels",
            "source_asset_id": "123",
            "source_url": "https://www.pexels.com/video/123/",
            "license_note": "pexels source metadata retained",
            "query": "relaxing bedroom night",
        },
    )
    app = create_app(settings)
    app.state.online_material_providers = {"pexels": SingleAssetProvider()}
    app.state.online_download_http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "video/mp4"},
                content=b"video",
                extensions={"connected_address": "93.184.216.34"},
            )
        )
    )
    app.state.online_download_resolver = lambda host: ["93.184.216.34"]

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "候选耗尽后复用",
                "script": _script(),
                "asset_strategy": "auto",
                "provider": "pexels",
                "shot_materials": [{"shot_index": 1, "material_id": existing["id"]}],
            },
        )
        output = client.get(response.json()["output"]["download_url"]).json()

    assert response.status_code == 201
    assert output["shot_materials"][1]["source_asset_id"] == "123"
    assert output["shot_materials"][1]["selection_reason"] == (
        "候选不足，复用已下载的线上素材"
    )


def test_online_mix_auto_rejects_provider_direct_media_source_url(
    tmp_path,
) -> None:
    from autovideo.services.online_materials import OnlineMaterialCandidate
    from tests.api.test_online_materials import FakeProvider

    class DirectMediaSourceProvider(FakeProvider):
        def search(
            self,
            query: str,
            aspect_ratio: str,
            min_duration_seconds: int,
            limit: int,
        ):
            return [
                OnlineMaterialCandidate(
                    provider="pexels",
                    asset_id="123",
                    query=query,
                    source_url="https://videos.pexels.com/video-files/123/clip.mp4",
                    preview_url="https://images.pexels.com/videos/123/preview.jpg",
                    file_variant="hd",
                    duration=8.5,
                    width=1080,
                    height=1920,
                    license_note="Pexels source metadata retained",
                )
            ]

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": DirectMediaSourceProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "污染来源素材混剪",
                "script": _script(),
                "asset_strategy": "auto",
                "provider": "pexels",
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_SEARCH_FAILED"
    assert list((tmp_path / "materials").iterdir()) == []


def test_online_mix_auto_resolve_failure_returns_structured_error(tmp_path) -> None:
    from tests.api.test_online_materials import FakeProvider

    class FailingDownloadProvider(FakeProvider):
        allowed_download_hosts = {"videos.pexels.com"}

        def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
            raise RuntimeError("provider failed before URL validation")

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": FailingDownloadProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "自动素材混剪",
                "script": _script(),
                "asset_strategy": "auto",
                "provider": "pexels",
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_DOWNLOAD_FAILED"


def test_online_mix_validates_user_materials_before_online_downloads(
    tmp_path,
) -> None:
    import httpx

    from autovideo.services.online_materials import CandidateTokenService
    from tests.api.test_online_materials import FakeProvider

    class DownloadProvider(FakeProvider):
        allowed_download_hosts = {"videos.pexels.com"}

        def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
            return "https://videos.pexels.com/video-files/123/clip.mp4"

    download_requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        download_requests.append(str(request.url))
        return httpx.Response(
            200,
            headers={"content-type": "video/mp4"},
            content=b"video",
            extensions={"connected_address": "93.184.216.34"},
        )

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": DownloadProvider()}
    app.state.online_download_http_client = httpx.Client(
        transport=httpx.MockTransport(handler)
    )
    app.state.online_download_resolver = lambda host: ["93.184.216.34"]
    token = CandidateTokenService(secret="secret", ttl_seconds=1800).sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom night",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "缺失本地素材",
                "script": _script(),
                "asset_strategy": "manual",
                "shot_assets": [{"shot_index": 1, "candidate_token": token}],
                "shot_materials": [
                    {"shot_index": 2, "material_id": "missing-material"}
                ],
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "MATERIAL_NOT_FOUND"
    assert download_requests == []
    assert list((tmp_path / "materials").iterdir()) == []


def test_online_mix_manual_requires_all_shots_before_online_downloads(
    tmp_path,
) -> None:
    import httpx

    from autovideo.services.online_materials import CandidateTokenService
    from tests.api.test_online_materials import FakeProvider

    class DownloadProvider(FakeProvider):
        allowed_download_hosts = {"videos.pexels.com"}

        def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
            return "https://videos.pexels.com/video-files/123/clip.mp4"

    download_requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        download_requests.append(str(request.url))
        return httpx.Response(
            200,
            headers={"content-type": "video/mp4"},
            content=b"video",
            extensions={"connected_address": "93.184.216.34"},
        )

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": DownloadProvider()}
    app.state.online_download_http_client = httpx.Client(
        transport=httpx.MockTransport(handler)
    )
    app.state.online_download_resolver = lambda host: ["93.184.216.34"]
    token = CandidateTokenService(secret="secret", ttl_seconds=1800).sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom night",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "手动素材不完整",
                "script": _script(),
                "asset_strategy": "manual",
                "shot_assets": [{"shot_index": 1, "candidate_token": token}],
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ONLINE_MIX_NO_MATERIAL_MATCH"
    assert download_requests == []
    assert list((tmp_path / "materials").iterdir()) == []


def test_online_mix_auto_search_failure_returns_structured_error(tmp_path) -> None:
    from tests.api.test_online_materials import FakeProvider

    class FailingSearchProvider(FakeProvider):
        def search(
            self,
            query: str,
            aspect_ratio: str,
            min_duration_seconds: int,
            limit: int,
        ):
            raise RuntimeError("provider search failed")

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": FailingSearchProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "自动素材混剪",
                "script": _script(),
                "asset_strategy": "auto",
                "provider": "pexels",
            },
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_SEARCH_FAILED"


def test_online_mix_auto_no_material_match_returns_structured_error(
    tmp_path,
) -> None:
    from tests.api.test_online_materials import FakeProvider

    class EmptyProvider(FakeProvider):
        def search(
            self,
            query: str,
            aspect_ratio: str,
            min_duration_seconds: int,
            limit: int,
        ):
            return []

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": EmptyProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "无素材匹配",
                "script": _script(),
                "asset_strategy": "auto",
                "provider": "pexels",
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ONLINE_MIX_NO_MATERIAL_MATCH"


def test_online_mix_candidate_token_expired_when_selection_is_valid(
    tmp_path,
) -> None:
    from datetime import UTC, datetime

    from autovideo.services.online_materials import CandidateTokenService

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    token = CandidateTokenService(
        secret="secret",
        ttl_seconds=60,
        now=lambda: datetime(2026, 6, 14, 0, 0, tzinfo=UTC),
    ).sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom night",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )

    with TestClient(app) as client:
        client.app.state.candidate_token_now = lambda: datetime(
            2026,
            6,
            14,
            0,
            2,
            tzinfo=UTC,
        )
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "过期候选",
                "script": _script(),
                "shot_assets": [{"shot_index": 1, "candidate_token": token}],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == (
        "ONLINE_MATERIAL_CANDIDATE_TOKEN_EXPIRED"
    )


def test_online_mix_selection_conflict_precedes_candidate_token_validation(
    tmp_path,
) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "非法候选",
                "script": _script(),
                "shot_assets": [
                    {"shot_index": 1, "candidate_token": "invalid"},
                    {"shot_index": 1, "candidate_token": "invalid-again"},
                ],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MIX_SHOT_SELECTION_INVALID"


def test_online_mix_missing_material_precedes_candidate_token_validation(
    tmp_path,
) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "缺失素材优先",
                "script": _script(),
                "asset_strategy": "manual",
                "shot_assets": [{"shot_index": 1, "candidate_token": "invalid"}],
                "shot_materials": [
                    {"shot_index": 2, "material_id": "missing-material"}
                ],
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == {
        "code": "MATERIAL_NOT_FOUND",
        "material_id": "missing-material",
    }


def test_online_mix_candidate_token_invalid_when_selection_is_valid(
    tmp_path,
) -> None:
    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "非法候选",
                "script": _script(),
                "shot_assets": [{"shot_index": 1, "candidate_token": "invalid"}],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == (
        "ONLINE_MATERIAL_CANDIDATE_TOKEN_INVALID"
    )


def test_online_mix_candidate_provider_missing_returns_structured_error(
    tmp_path,
) -> None:
    from autovideo.services.online_materials import CandidateTokenService
    from tests.api.test_online_materials import FakeProvider

    app = create_app(
        Settings(
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": FakeProvider()}
    token = CandidateTokenService(secret="secret", ttl_seconds=1800).sign(
        {
            "provider": "pixabay",
            "asset_id": "456",
            "query": "relaxing bedroom night",
            "file_variant": "hd",
            "source_url": "https://pixabay.com/videos/456/",
        }
    )

    with TestClient(app) as client:
        material = client.post(
            "/api/materials",
            files={"file": ("clip.mp4", b"fake", "video/mp4")},
        ).json()
        response = client.post(
            "/api/online-mix/tasks",
            json={
                "title": "缺失 provider",
                "script": _script(),
                "asset_strategy": "manual",
                "shot_assets": [{"shot_index": 1, "candidate_token": token}],
                "shot_materials": [
                    {"shot_index": 2, "material_id": material["id"]}
                ],
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_PROVIDER_NOT_AVAILABLE"
    assert response.json()["detail"]["provider"] == "pixabay"
