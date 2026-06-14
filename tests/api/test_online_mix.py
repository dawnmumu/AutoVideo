import json

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
    assert "candidate_token" not in serialized
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
        "render_profile": {"preset": "fast"},
    }
    serialized = json.dumps(output, ensure_ascii=False)
    assert "signed-token" not in serialized
    assert "provider_download_url" not in serialized
    assert "videos.pexels.com" not in serialized


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
