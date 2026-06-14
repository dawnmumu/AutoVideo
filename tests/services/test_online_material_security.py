from datetime import UTC, datetime, timedelta

import httpx
import pytest

from autovideo.services.online_downloads import (
    OnlineMaterialContentTypeNotAllowedError,
    OnlineMaterialDownloadUrlNotAllowedError,
    content_type_matches_extension,
    open_validated_download_response,
    safe_download_suffix,
    validate_connection_addresses,
    validate_download_url,
    validate_redirect_chain,
)
from autovideo.services.online_materials import (
    CandidateTokenExpiredError,
    CandidateTokenInvalidError,
    CandidateTokenService,
    OnlineMaterialCandidate,
    OnlineMaterialPublicUrlInvalidError,
    public_candidate,
)


def test_candidate_token_round_trip_with_ttl() -> None:
    now = datetime(2026, 6, 14, tzinfo=UTC)
    service = CandidateTokenService(secret="secret", ttl_seconds=1800, now=lambda: now)

    token = service.sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )

    payload = service.verify(token)
    assert payload["provider"] == "pexels"
    assert payload["asset_id"] == "123"
    assert payload["expires_at"] == (now + timedelta(seconds=1800)).isoformat()


def test_candidate_token_rejects_tampering() -> None:
    service = CandidateTokenService(secret="secret", ttl_seconds=1800)
    token = service.sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )

    with pytest.raises(CandidateTokenInvalidError):
        service.verify(token + "x")


def test_candidate_token_rejects_expired_payload() -> None:
    issued_at = datetime(2026, 6, 14, tzinfo=UTC)
    verifier_now = datetime(2026, 6, 14, 0, 31, tzinfo=UTC)
    signer = CandidateTokenService(
        secret="secret",
        ttl_seconds=1800,
        now=lambda: issued_at,
    )
    verifier = CandidateTokenService(
        secret="secret",
        ttl_seconds=1800,
        now=lambda: verifier_now,
    )
    token = signer.sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom",
            "file_variant": "hd",
            "source_url": "https://www.pexels.com/video/123/",
        }
    )

    with pytest.raises(CandidateTokenExpiredError):
        verifier.verify(token)


def test_candidate_token_rejects_missing_required_payload_fields() -> None:
    service = CandidateTokenService(secret="secret", ttl_seconds=1800)
    token = service.sign(
        {
            "provider": "pexels",
            "asset_id": "123",
            "query": "relaxing bedroom",
            "file_variant": "hd",
        }
    )

    with pytest.raises(CandidateTokenInvalidError):
        service.verify(token)


def test_rank_candidates_prefers_matching_ratio_duration_and_resolution() -> None:
    from autovideo.services.online_materials import rank_candidates

    candidates = [
        OnlineMaterialCandidate(
            provider="pexels",
            asset_id="wide",
            query="relaxing bedroom",
            source_url="https://www.pexels.com/video/wide/",
            preview_url="https://images.pexels.com/videos/wide/preview.jpg",
            file_variant="sd",
            duration=2.0,
            width=1920,
            height=1080,
            license_note="Pexels source metadata retained",
        ),
        OnlineMaterialCandidate(
            provider="pixabay",
            asset_id="vertical-hd",
            query="relaxing bedroom",
            source_url="https://pixabay.com/videos/vertical-hd/",
            preview_url="https://i.vimeocdn.com/video/vertical-hd_640x360.jpg",
            file_variant="hd",
            duration=8.0,
            width=1080,
            height=1920,
            license_note="Pixabay source metadata retained",
        ),
    ]

    ranked = rank_candidates(candidates, aspect_ratio="9:16", min_duration_seconds=5)

    assert ranked[0].asset_id == "vertical-hd"


def test_public_candidate_allows_provider_source_and_preview_hosts() -> None:
    candidate = OnlineMaterialCandidate(
        provider="pexels",
        asset_id="123",
        query="relaxing bedroom",
        source_url="https://www.pexels.com/video/123/",
        preview_url="https://images.pexels.com/videos/123/preview.jpg",
        file_variant="hd",
        duration=8.0,
        width=1080,
        height=1920,
        license_note="Pexels source metadata retained",
    )

    payload = public_candidate(candidate, "signed-token")

    assert payload["source_url"] == "https://www.pexels.com/video/123/"
    assert payload["preview_url"] == "https://images.pexels.com/videos/123/preview.jpg"
    assert payload["candidate_token"] == "signed-token"


@pytest.mark.parametrize(
    ("source_url", "preview_url"),
    [
        (
            "https://videos.pexels.com/video-files/123/clip.mp4",
            "https://images.pexels.com/videos/123/preview.jpg",
        ),
        (
            "http://127.0.0.1/video/123",
            "https://images.pexels.com/videos/123/preview.jpg",
        ),
        (
            "https://127.0.0.1/video/123",
            "https://images.pexels.com/videos/123/preview.jpg",
        ),
        (
            "https://www.pexels.com/search/videos/bedroom/",
            "https://images.pexels.com/videos/123/preview.jpg",
        ),
        ("https://www.pexels.com/video/123/", "https://evil.example.test/preview.jpg"),
        ("https://www.pexels.com/video/123/", "https://www.pexels.com/video/123/"),
        ("https://www.pexels.com/video/123/", "http://10.0.0.2/preview.jpg"),
    ],
)
def test_public_candidate_rejects_unsafe_source_or_preview_urls(
    source_url: str,
    preview_url: str,
) -> None:
    candidate = OnlineMaterialCandidate(
        provider="pexels",
        asset_id="123",
        query="relaxing bedroom",
        source_url=source_url,
        preview_url=preview_url,
        file_variant="hd",
        duration=8.0,
        width=1080,
        height=1920,
        license_note="Pexels source metadata retained",
    )

    with pytest.raises(OnlineMaterialPublicUrlInvalidError):
        public_candidate(candidate, "signed-token")


@pytest.mark.parametrize(
    ("provider", "source_url", "preview_url"),
    [
        (
            "pexels",
            "https://www.pexels.com/video/123/",
            "https://images.pexels.com/videos/123/clip.mp4",
        ),
        (
            "pexels",
            "https://www.pexels.com/video/123/",
            "https://images.pexels.com/videos/123/clip.mov",
        ),
        (
            "pexels",
            "https://www.pexels.com/video/123/",
            "https://images.pexels.com/videos/123/clip.m4v",
        ),
        (
            "pexels",
            "https://www.pexels.com/video/123/",
            "https://images.pexels.com/videos/123/clip.webm",
        ),
        (
            "pexels",
            "https://www.pexels.com/video/123/",
            "https://images.pexels.com/videos/123/playlist.m3u8",
        ),
        (
            "pixabay",
            "https://pixabay.com/videos/456/",
            "https://cdn.pixabay.com/video/2026/clip.mp4",
        ),
        (
            "pixabay",
            "https://pixabay.com/videos/456/",
            "https://cdn.pixabay.com/video/2026/clip.mov",
        ),
        (
            "pixabay",
            "https://pixabay.com/videos/456/",
            "https://cdn.pixabay.com/video/2026/clip.m4v",
        ),
        (
            "pixabay",
            "https://pixabay.com/videos/456/",
            "https://cdn.pixabay.com/video/2026/clip.webm",
        ),
        (
            "pixabay",
            "https://pixabay.com/videos/456/",
            "https://cdn.pixabay.com/video/2026/playlist.m3u8",
        ),
        (
            "pixabay",
            "https://pixabay.com/videos/456/",
            "https://cdn.pixabay.com/video/2026/clip",
        ),
    ],
)
def test_public_candidate_rejects_direct_media_preview_urls(
    provider: str,
    source_url: str,
    preview_url: str,
) -> None:
    candidate = OnlineMaterialCandidate(
        provider=provider,
        asset_id="123",
        query="relaxing bedroom",
        source_url=source_url,
        preview_url=preview_url,
        file_variant="hd",
        duration=8.0,
        width=1080,
        height=1920,
        license_note="Source metadata retained",
    )

    with pytest.raises(OnlineMaterialPublicUrlInvalidError):
        public_candidate(candidate, "signed-token")


def test_pexels_provider_uses_injected_http_client_and_settings_key() -> None:
    from autovideo.services.online_materials import PexelsProvider

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "pexels-key"
        return httpx.Response(
            200,
            json={
                "videos": [
                    {
                        "id": 123,
                        "url": "https://www.pexels.com/video/123/",
                        "image": "https://images.pexels.com/videos/123/preview.jpg",
                        "duration": 8,
                        "video_files": [
                            {
                                "id": "hd",
                                "width": 1080,
                                "height": 1920,
                                "link": (
                                    "https://videos.pexels.com/video-files/123/clip.mp4"
                                ),
                            }
                        ],
                    }
                ]
            },
        )

    provider = PexelsProvider(
        api_key="pexels-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    candidates = provider.search("relaxing bedroom", "9:16", 5, 5)

    assert candidates[0].provider == "pexels"
    assert candidates[0].file_variant == "hd"


def test_pixabay_provider_uses_injected_http_client_and_settings_key() -> None:
    from autovideo.services.online_materials import PixabayProvider

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["key"] == "pixabay-key"
        return httpx.Response(
            200,
            json={
                "hits": [
                    {
                        "id": 456,
                        "pageURL": "https://pixabay.com/videos/456/",
                        "picture_id": "987654321",
                        "duration": 9,
                        "videos": {
                            "large": {
                                "width": 1080,
                                "height": 1920,
                                "url": "https://cdn.pixabay.com/video/2026/clip.mp4",
                            }
                        },
                    }
                ]
            },
        )

    provider = PixabayProvider(
        api_key="pixabay-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    candidates = provider.search("relaxing bedroom", "9:16", 5, 5)

    assert candidates[0].provider == "pixabay"
    assert candidates[0].file_variant == "large"
    assert candidates[0].preview_url == "https://i.vimeocdn.com/video/987654321_640x360.jpg"


def test_validate_download_url_rejects_non_allowlist_host() -> None:
    with pytest.raises(OnlineMaterialDownloadUrlNotAllowedError):
        validate_download_url(
            "https://evil.example.test/file.mp4",
            allowed_hosts={"videos.pexels.com"},
            resolver=lambda host: ["93.184.216.34"],
        )


def test_validate_download_url_rejects_private_dns_result() -> None:
    with pytest.raises(OnlineMaterialDownloadUrlNotAllowedError):
        validate_download_url(
            "https://videos.pexels.com/file.mp4",
            allowed_hosts={"videos.pexels.com"},
            resolver=lambda host: ["127.0.0.1"],
        )


def test_validate_download_url_rejects_direct_ip_host_without_dns_lookup() -> None:
    def resolver(hostname: str) -> list[str]:
        raise AssertionError("direct IP hosts must be rejected before DNS lookup")

    with pytest.raises(OnlineMaterialDownloadUrlNotAllowedError):
        validate_download_url(
            "https://93.184.216.34/file.mp4",
            allowed_hosts={"93.184.216.34"},
            resolver=resolver,
        )


def test_validate_download_url_accepts_allowed_public_host() -> None:
    parsed = validate_download_url(
        "https://videos.pexels.com/file.mp4",
        allowed_hosts={"videos.pexels.com"},
        resolver=lambda host: ["93.184.216.34"],
    )

    assert parsed.hostname == "videos.pexels.com"


def test_validate_redirect_chain_rejects_private_redirect_target() -> None:
    with pytest.raises(OnlineMaterialDownloadUrlNotAllowedError):
        validate_redirect_chain(
            [
                "https://videos.pexels.com/file.mp4",
                "https://127.0.0.1/file.mp4",
            ],
            allowed_hosts={"videos.pexels.com"},
            resolver=lambda host: (
                ["93.184.216.34"]
                if host == "videos.pexels.com"
                else ["127.0.0.1"]
            ),
        )


def test_open_validated_download_response_rejects_private_redirect_without_next_hop() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.host != "videos.pexels.com":
            raise AssertionError("private redirect target must not be requested")
        return httpx.Response(
            302,
            headers={"location": "https://127.0.0.1/private.mp4"},
            extensions={"connected_address": "93.184.216.34"},
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(OnlineMaterialDownloadUrlNotAllowedError):
        with open_validated_download_response(
            http_client,
            "https://videos.pexels.com/file.mp4",
            allowed_hosts={"videos.pexels.com"},
            resolver=lambda host: ["93.184.216.34"],
        ):
            raise AssertionError("unsafe redirect must not yield a response")

    assert requested_urls == ["https://videos.pexels.com/file.mp4"]


def test_open_validated_download_response_respects_max_redirects() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": "https://videos.pexels.com/next.mp4"},
            extensions={"connected_address": "93.184.216.34"},
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(OnlineMaterialDownloadUrlNotAllowedError):
        with open_validated_download_response(
            http_client,
            "https://videos.pexels.com/file.mp4",
            allowed_hosts={"videos.pexels.com"},
            resolver=lambda host: ["93.184.216.34"],
            max_redirects=0,
        ):
            raise AssertionError("redirect limit must prevent yielding a response")

    assert requested_urls == ["https://videos.pexels.com/file.mp4"]


def test_validate_connection_addresses_rejects_dns_rebinding_drift() -> None:
    with pytest.raises(OnlineMaterialDownloadUrlNotAllowedError):
        validate_connection_addresses(
            hostname="videos.pexels.com",
            preflight_addresses=["93.184.216.34"],
            connected_address="127.0.0.1",
        )


def test_validate_download_url_rejects_resolution_drift_between_checks() -> None:
    calls = 0

    def resolver(hostname: str) -> list[str]:
        nonlocal calls
        calls += 1
        return ["93.184.216.34"] if calls == 1 else ["10.0.0.2"]

    with pytest.raises(OnlineMaterialDownloadUrlNotAllowedError):
        validate_download_url(
            "https://videos.pexels.com/file.mp4",
            allowed_hosts={"videos.pexels.com"},
            resolver=resolver,
            verify_stable_resolution=True,
        )


def test_content_type_matches_extension_allowlist() -> None:
    assert content_type_matches_extension("video/mp4", ".mp4")
    assert content_type_matches_extension("video/mp4; charset=binary", ".m4v")
    assert content_type_matches_extension("video/quicktime", ".mov")
    assert content_type_matches_extension("video/webm", ".webm")
    assert not content_type_matches_extension("application/octet-stream", ".mp4")
    assert not content_type_matches_extension("video/mp4", ".webm")


def test_safe_download_suffix_rejects_unknown_or_mismatched_media_identity() -> None:
    assert (
        safe_download_suffix(
            "https://videos.pexels.com/video-files/123/clip.mp4",
            "video/mp4",
        )
        == ".mp4"
    )
    with pytest.raises(OnlineMaterialContentTypeNotAllowedError):
        safe_download_suffix(
            "https://videos.pexels.com/video-files/123/clip.bin",
            "video/mp4",
        )
    with pytest.raises(OnlineMaterialContentTypeNotAllowedError):
        safe_download_suffix(
            "https://videos.pexels.com/video-files/123/clip.mp4",
            "application/octet-stream",
        )
    with pytest.raises(OnlineMaterialContentTypeNotAllowedError):
        safe_download_suffix(
            "https://videos.pexels.com/video-files/123/clip.mp4",
            "video/webm",
        )
