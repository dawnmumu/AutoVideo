import json

from fastapi.testclient import TestClient

from autovideo.api.app import create_app
from autovideo.core.settings import Settings
from autovideo.services.online_materials import (
    CandidateTokenService,
    OnlineMaterialCandidate,
)


class FakeProvider:
    name = "pexels"
    enabled = True

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


class FakePixabayProvider:
    name = "pixabay"
    enabled = True

    def search(
        self,
        query: str,
        aspect_ratio: str,
        min_duration_seconds: int,
        limit: int,
    ):
        return [
            OnlineMaterialCandidate(
                provider="pixabay",
                asset_id="456",
                query=query,
                source_url="https://pixabay.com/videos/456/",
                preview_url="https://i.vimeocdn.com/video/456_640x360.jpg",
                file_variant="hd",
                duration=9.0,
                width=1080,
                height=1920,
                license_note="Pixabay source metadata retained",
            )
        ]


class DisabledProvider:
    name = "pexels"
    enabled = False

    def search(
        self,
        query: str,
        aspect_ratio: str,
        min_duration_seconds: int,
        limit: int,
    ):
        raise AssertionError("disabled provider must not be searched")


def test_online_material_status_reports_secret_without_leaking_value(tmp_path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="super-sensitive-token",
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/online-materials/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate_token_secret_configured"] is True
    assert payload["default_provider"] == "auto"
    assert payload["providers"] == [
        {"provider": "pexels", "configured": True, "enabled": True},
        {"provider": "pixabay", "configured": False, "enabled": False},
    ]
    assert "super-sensitive-token" not in str(payload)


def test_online_material_status_does_not_mark_disabled_provider_available(
    tmp_path,
) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="super-sensitive-token",
        )
    )
    app.state.online_material_providers = {"pexels": DisabledProvider()}

    with TestClient(app) as client:
        response = client.get("/api/online-materials/status")

    assert response.status_code == 200
    payload = response.json()
    providers = {item["provider"]: item for item in payload["providers"]}
    assert providers["pexels"] == {
        "provider": "pexels",
        "configured": True,
        "enabled": False,
    }


def test_online_material_search_rejects_zero_min_duration(client) -> None:
    response = client.post(
        "/api/online-materials/search",
        json={
            "query": "relaxing bedroom night",
            "aspect_ratio": "9:16",
            "min_duration_seconds": 0,
        },
    )

    assert response.status_code == 422


def test_online_material_search_requires_configured_provider(client) -> None:
    response = client.post(
        "/api/online-materials/search",
        json={"query": "relaxing bedroom night", "aspect_ratio": "9:16"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == (
        "ONLINE_MATERIAL_PROVIDER_NOT_CONFIGURED"
    )


def test_online_material_search_requires_candidate_secret(tmp_path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret=None,
        )
    )
    app.state.online_material_providers = {"pexels": FakeProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-materials/search",
            json={"query": "relaxing bedroom night", "aspect_ratio": "9:16"},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == (
        "ONLINE_MATERIAL_TOKEN_SECRET_NOT_CONFIGURED"
    )


def test_online_material_search_provider_failure_returns_structured_error(
    tmp_path,
) -> None:
    class FailingProvider(FakeProvider):
        def search(
            self,
            query: str,
            aspect_ratio: str,
            min_duration_seconds: int,
            limit: int,
        ):
            raise RuntimeError("provider failed with pexels-key super-sensitive-token")

    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": FailingProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-materials/search",
            json={"query": "relaxing bedroom night", "aspect_ratio": "9:16"},
        )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "ONLINE_MATERIAL_SEARCH_FAILED"
    assert "pexels-key" not in response.text
    assert "super-sensitive-token" not in response.text


def test_online_material_search_returns_signed_candidates(tmp_path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="super-sensitive-token",
        )
    )
    app.state.online_material_providers = {"pexels": FakeProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-materials/search",
            json={"query": "relaxing bedroom night", "aspect_ratio": "9:16"},
        )

    assert response.status_code == 200
    candidate = response.json()[0]
    assert candidate["candidate_token"]
    assert candidate["preview_url"].startswith("https://")
    assert "download_url" not in candidate
    assert candidate["source_url"] == "https://www.pexels.com/video/123/"

    token_service = CandidateTokenService(
        secret="super-sensitive-token",
        ttl_seconds=1800,
    )
    payload = token_service.verify(candidate["candidate_token"])
    payload_text = json.dumps(payload, sort_keys=True)
    assert "download_url" not in payload
    assert "api_key" not in payload
    assert "secret" not in payload
    assert "download_url" not in payload_text
    assert "api_key" not in payload_text
    assert "secret" not in payload_text
    assert "pexels-key" not in payload_text
    assert "super-sensitive-token" not in payload_text


def test_online_material_search_uses_requested_provider(tmp_path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            pixabay_api_key="pixabay-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {
        "pexels": FakeProvider(),
        "pixabay": FakePixabayProvider(),
    }

    with TestClient(app) as client:
        response = client.post(
            "/api/online-materials/search",
            json={
                "query": "relaxing bedroom night",
                "aspect_ratio": "9:16",
                "provider": "pixabay",
            },
        )

    assert response.status_code == 200
    assert response.json()[0]["provider"] == "pixabay"


def test_online_material_search_unknown_requested_provider_returns_structured_error(
    tmp_path,
) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            pixabay_api_key=None,
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": FakeProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-materials/search",
            json={
                "query": "relaxing bedroom night",
                "aspect_ratio": "9:16",
                "provider": "pixabay",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == (
        "ONLINE_MATERIAL_PROVIDER_NOT_AVAILABLE"
    )
    assert response.json()["detail"]["provider"] == "pixabay"


def test_online_material_search_auto_skips_disabled_provider(tmp_path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            pixabay_api_key="pixabay-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {
        "pexels": DisabledProvider(),
        "pixabay": FakePixabayProvider(),
    }

    with TestClient(app) as client:
        response = client.post(
            "/api/online-materials/search",
            json={
                "query": "relaxing bedroom night",
                "aspect_ratio": "9:16",
                "provider": "auto",
            },
        )

    assert response.status_code == 200
    assert [candidate["provider"] for candidate in response.json()] == ["pixabay"]


def test_online_material_search_auto_with_only_disabled_provider_is_not_configured(
    tmp_path,
) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": DisabledProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-materials/search",
            json={
                "query": "relaxing bedroom night",
                "aspect_ratio": "9:16",
                "provider": "auto",
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == (
        "ONLINE_MATERIAL_PROVIDER_NOT_CONFIGURED"
    )


def test_online_material_search_requested_disabled_provider_is_not_available(
    tmp_path,
) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {"pexels": DisabledProvider()}

    with TestClient(app) as client:
        response = client.post(
            "/api/online-materials/search",
            json={
                "query": "relaxing bedroom night",
                "aspect_ratio": "9:16",
                "provider": "pexels",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == (
        "ONLINE_MATERIAL_PROVIDER_NOT_AVAILABLE"
    )
    assert response.json()["detail"]["provider"] == "pexels"


def test_online_material_search_auto_merges_and_sorts_candidates(tmp_path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            ffmpeg_path="missing-autovideo-ffmpeg-binary",
            pexels_api_key="pexels-key",
            pixabay_api_key="pixabay-key",
            candidate_token_secret="secret",
        )
    )
    app.state.online_material_providers = {
        "pexels": FakeProvider(),
        "pixabay": FakePixabayProvider(),
    }

    with TestClient(app) as client:
        response = client.post(
            "/api/online-materials/search",
            json={
                "query": "relaxing bedroom night",
                "aspect_ratio": "9:16",
                "provider": "auto",
                "min_duration_seconds": 8,
            },
        )

    assert response.status_code == 200
    providers = [candidate["provider"] for candidate in response.json()]
    assert providers == ["pixabay", "pexels"]
