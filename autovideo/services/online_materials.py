from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True)
class OnlineMaterialCandidate:
    provider: str
    asset_id: str
    query: str
    source_url: str
    preview_url: str
    file_variant: str
    duration: float
    width: int
    height: int
    license_note: str


class CandidateTokenInvalidError(ValueError):
    """Raised when a candidate token is malformed or has an invalid signature."""


class CandidateTokenExpiredError(ValueError):
    """Raised when a candidate token has passed its expiration time."""


class OnlineMaterialPublicUrlInvalidError(ValueError):
    """Raised when a provider candidate contains an unsafe public URL."""


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _utc_now(now: Callable[[], datetime] | None) -> datetime:
    current = now() if now is not None else datetime.now(UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


class CandidateTokenService:
    _required_fields = frozenset(
        {
            "provider",
            "asset_id",
            "query",
            "file_variant",
            "source_url",
            "expires_at",
        }
    )

    def __init__(
        self,
        *,
        secret: str,
        ttl_seconds: int = 1800,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._secret = secret.encode("utf-8")
        self._ttl_seconds = ttl_seconds
        self._now = now

    def sign(self, payload: Mapping[str, Any]) -> str:
        token_payload = dict(payload)
        expires_at = _utc_now(self._now) + timedelta(seconds=self._ttl_seconds)
        token_payload["expires_at"] = expires_at.isoformat()
        payload_part = _base64url_encode(
            json.dumps(
                token_payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        signature_part = self._signature(payload_part)
        return f"{payload_part}.{signature_part}"

    def verify(self, token: str) -> dict[str, Any]:
        try:
            payload_part, signature_part = token.split(".", 1)
        except ValueError as exc:
            raise CandidateTokenInvalidError("candidate token format is invalid") from exc
        if not payload_part or not signature_part or "." in signature_part:
            raise CandidateTokenInvalidError("candidate token format is invalid")

        expected_signature = self._signature(payload_part)
        if not hmac.compare_digest(expected_signature, signature_part):
            raise CandidateTokenInvalidError("candidate token signature is invalid")

        try:
            payload = json.loads(_base64url_decode(payload_part).decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CandidateTokenInvalidError("candidate token payload is invalid") from exc
        if not isinstance(payload, dict):
            raise CandidateTokenInvalidError("candidate token payload is invalid")

        missing_fields = [
            field
            for field in self._required_fields
            if field not in payload or payload[field] in (None, "")
        ]
        if missing_fields:
            raise CandidateTokenInvalidError("candidate token payload is incomplete")

        try:
            expires_at = datetime.fromisoformat(
                str(payload["expires_at"]).replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise CandidateTokenInvalidError("candidate token expiration is invalid") from exc
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at.astimezone(UTC) <= _utc_now(self._now):
            raise CandidateTokenExpiredError("candidate token has expired")

        return payload

    def _signature(self, payload_part: str) -> str:
        digest = hmac.new(
            self._secret,
            payload_part.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return _base64url_encode(digest)


def _hostname_is_ip_or_local(hostname: str) -> bool:
    host = hostname.rstrip(".").lower()
    if host in {"localhost", "0.0.0.0"}:
        return True
    if host.endswith((".localhost", ".local", ".internal")):
        return True
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


def _https_url(url: str):
    parsed = urlparse(url)
    hostname = parsed.hostname
    if parsed.scheme.lower() != "https" or not hostname:
        raise OnlineMaterialPublicUrlInvalidError("public URLs must use https")
    if _hostname_is_ip_or_local(hostname):
        raise OnlineMaterialPublicUrlInvalidError("public URLs cannot use local hosts")
    return parsed, hostname.rstrip(".").lower()


def _looks_like_direct_media(path: str) -> bool:
    return path.lower().endswith((".mp4", ".mov", ".m4v", ".webm", ".m3u8"))


def _looks_like_image(path: str) -> bool:
    return path.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))


def _validate_source_url(candidate: OnlineMaterialCandidate) -> None:
    parsed, host = _https_url(candidate.source_url)
    path = parsed.path or "/"
    if _looks_like_direct_media(path):
        raise OnlineMaterialPublicUrlInvalidError("source URL cannot be direct media")

    if candidate.provider == "pexels":
        if host not in {"www.pexels.com", "pexels.com"} or not path.startswith(
            "/video/"
        ):
            raise OnlineMaterialPublicUrlInvalidError("pexels source URL is invalid")
        return

    if candidate.provider == "pixabay":
        if host not in {"www.pixabay.com", "pixabay.com"} or not path.startswith(
            "/videos/"
        ):
            raise OnlineMaterialPublicUrlInvalidError("pixabay source URL is invalid")
        return

    raise OnlineMaterialPublicUrlInvalidError("provider source URL rules are unknown")


def _validate_preview_url(candidate: OnlineMaterialCandidate) -> None:
    source = urlparse(candidate.source_url)
    parsed, host = _https_url(candidate.preview_url)
    if _looks_like_direct_media(parsed.path or "/"):
        raise OnlineMaterialPublicUrlInvalidError("preview URL cannot be direct media")
    if (
        source.scheme.lower(),
        source.hostname,
        source.path,
    ) == (parsed.scheme.lower(), parsed.hostname, parsed.path):
        raise OnlineMaterialPublicUrlInvalidError("preview URL cannot be the source page")

    if candidate.provider == "pexels":
        if host != "images.pexels.com":
            raise OnlineMaterialPublicUrlInvalidError("pexels preview URL is invalid")
        return

    if candidate.provider == "pixabay":
        path = parsed.path or "/"
        if host == "i.vimeocdn.com":
            if path.startswith("/video/") and _looks_like_image(path):
                return
            raise OnlineMaterialPublicUrlInvalidError("pixabay preview URL is invalid")
        if host == "cdn.pixabay.com":
            if path.startswith("/video/") or not _looks_like_image(path):
                raise OnlineMaterialPublicUrlInvalidError(
                    "pixabay preview URL is invalid"
                )
            return
        raise OnlineMaterialPublicUrlInvalidError("pixabay preview URL is invalid")

    raise OnlineMaterialPublicUrlInvalidError("provider preview URL rules are unknown")


def public_candidate(
    candidate: OnlineMaterialCandidate,
    token: str,
) -> dict[str, Any]:
    _validate_source_url(candidate)
    _validate_preview_url(candidate)
    return {
        "provider": candidate.provider,
        "asset_id": candidate.asset_id,
        "query": candidate.query,
        "source_url": candidate.source_url,
        "preview_url": candidate.preview_url,
        "file_variant": candidate.file_variant,
        "duration": candidate.duration,
        "width": candidate.width,
        "height": candidate.height,
        "license_note": candidate.license_note,
        "candidate_token": token,
    }


def _aspect_ratio_value(aspect_ratio: str) -> float | None:
    try:
        width, height = aspect_ratio.split(":", 1)
        parsed_width = float(width)
        parsed_height = float(height)
    except ValueError:
        return None
    if parsed_width <= 0 or parsed_height <= 0:
        return None
    return parsed_width / parsed_height


def rank_candidates(
    candidates: list[OnlineMaterialCandidate],
    *,
    aspect_ratio: str,
    min_duration_seconds: float,
) -> list[OnlineMaterialCandidate]:
    target_ratio = _aspect_ratio_value(aspect_ratio)

    def sort_key(candidate: OnlineMaterialCandidate) -> tuple[object, ...]:
        duration_matches = candidate.duration >= min_duration_seconds
        if target_ratio is None or candidate.height <= 0:
            ratio_delta = float("inf")
        else:
            ratio_delta = abs((candidate.width / candidate.height) - target_ratio)
        pixels = max(candidate.width, 0) * max(candidate.height, 0)
        return (
            not duration_matches,
            ratio_delta,
            -pixels,
            -candidate.duration,
            candidate.provider,
            candidate.asset_id,
        )

    return sorted(candidates, key=sort_key)


def _best_video_file(files: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not files:
        return None
    return max(
        files,
        key=lambda item: (
            int(item.get("width") or 0) * int(item.get("height") or 0),
            int(item.get("width") or 0),
            int(item.get("height") or 0),
        ),
    )


class PexelsProvider:
    name = "pexels"
    allowed_download_hosts = {"videos.pexels.com"}

    def __init__(
        self,
        *,
        api_key: str,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.enabled = bool(api_key)
        self._http_client = http_client

    def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        if self._http_client is not None:
            return self._http_client.get(url, **kwargs)
        with httpx.Client() as http_client:
            return http_client.get(url, **kwargs)

    def search(
        self,
        query: str,
        aspect_ratio: str,
        min_duration_seconds: int,
        limit: int,
    ) -> list[OnlineMaterialCandidate]:
        response = self._get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": self.api_key},
            params={"query": query, "per_page": limit},
        )
        response.raise_for_status()
        candidates: list[OnlineMaterialCandidate] = []
        for item in response.json().get("videos", []):
            best_file = _best_video_file(list(item.get("video_files") or []))
            if best_file is None:
                continue
            asset_id = str(item.get("id"))
            candidates.append(
                OnlineMaterialCandidate(
                    provider=self.name,
                    asset_id=asset_id,
                    query=query,
                    source_url=str(
                        item.get("url") or f"https://www.pexels.com/video/{asset_id}/"
                    ),
                    preview_url=str(item.get("image") or ""),
                    file_variant=str(
                        best_file.get("id")
                        or best_file.get("quality")
                        or best_file.get("file_type")
                        or "best"
                    ),
                    duration=float(item.get("duration") or 0),
                    width=int(best_file.get("width") or 0),
                    height=int(best_file.get("height") or 0),
                    license_note="Pexels source metadata retained",
                )
            )
        return rank_candidates(
            candidates,
            aspect_ratio=aspect_ratio,
            min_duration_seconds=min_duration_seconds,
        )

    def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
        response = self._get(
            f"https://api.pexels.com/videos/videos/{asset_id}",
            headers={"Authorization": self.api_key},
        )
        response.raise_for_status()
        for item in response.json().get("video_files", []):
            variant = str(
                item.get("id")
                or item.get("quality")
                or item.get("file_type")
                or "best"
            )
            if variant == file_variant:
                return str(item["link"])
        raise LookupError("pexels video file variant was not found")


def _best_pixabay_video(
    videos: Mapping[str, dict[str, Any]],
) -> tuple[str, dict[str, Any]] | None:
    if not videos:
        return None
    return max(
        videos.items(),
        key=lambda pair: (
            int(pair[1].get("width") or 0) * int(pair[1].get("height") or 0),
            int(pair[1].get("width") or 0),
            int(pair[1].get("height") or 0),
        ),
    )


class PixabayProvider:
    name = "pixabay"
    allowed_download_hosts = {"cdn.pixabay.com"}

    def __init__(
        self,
        *,
        api_key: str,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.enabled = bool(api_key)
        self._http_client = http_client

    def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        if self._http_client is not None:
            return self._http_client.get(url, **kwargs)
        with httpx.Client() as http_client:
            return http_client.get(url, **kwargs)

    def search(
        self,
        query: str,
        aspect_ratio: str,
        min_duration_seconds: int,
        limit: int,
    ) -> list[OnlineMaterialCandidate]:
        response = self._get(
            "https://pixabay.com/api/videos/",
            params={"key": self.api_key, "q": query, "per_page": limit},
        )
        response.raise_for_status()
        candidates: list[OnlineMaterialCandidate] = []
        for item in response.json().get("hits", []):
            best_video = _best_pixabay_video(item.get("videos") or {})
            if best_video is None:
                continue
            file_variant, video = best_video
            asset_id = str(item.get("id"))
            picture_id = str(item.get("picture_id") or asset_id)
            candidates.append(
                OnlineMaterialCandidate(
                    provider=self.name,
                    asset_id=asset_id,
                    query=query,
                    source_url=str(
                        item.get("pageURL") or f"https://pixabay.com/videos/{asset_id}/"
                    ),
                    preview_url=(
                        f"https://i.vimeocdn.com/video/{picture_id}_640x360.jpg"
                    ),
                    file_variant=file_variant,
                    duration=float(item.get("duration") or 0),
                    width=int(video.get("width") or 0),
                    height=int(video.get("height") or 0),
                    license_note="Pixabay source metadata retained",
                )
            )
        return rank_candidates(
            candidates,
            aspect_ratio=aspect_ratio,
            min_duration_seconds=min_duration_seconds,
        )

    def resolve_download_url(self, asset_id: str, file_variant: str) -> str:
        response = self._get(
            "https://pixabay.com/api/videos/",
            params={"key": self.api_key, "id": asset_id},
        )
        response.raise_for_status()
        for item in response.json().get("hits", []):
            if str(item.get("id")) != str(asset_id):
                continue
            video = (item.get("videos") or {}).get(file_variant)
            if video is not None:
                return str(video["url"])
        raise LookupError("pixabay video file variant was not found")


def build_provider_registry(settings: Any) -> dict[str, Any]:
    registry: dict[str, Any] = {}
    if getattr(settings, "pexels_api_key", None):
        registry["pexels"] = PexelsProvider(api_key=settings.pexels_api_key)
    if getattr(settings, "pixabay_api_key", None):
        registry["pixabay"] = PixabayProvider(api_key=settings.pixabay_api_key)
    return registry


def configured_provider_names(settings_or_registry: Any) -> list[str]:
    if isinstance(settings_or_registry, Mapping):
        return [
            name
            for name, provider in settings_or_registry.items()
            if _provider_is_enabled(provider)
        ]

    names: list[str] = []
    if getattr(settings_or_registry, "pexels_api_key", None):
        names.append("pexels")
    if getattr(settings_or_registry, "pixabay_api_key", None):
        names.append("pixabay")
    return names


def _provider_is_enabled(provider: Any) -> bool:
    return bool(getattr(provider, "enabled", True))


def provider_status(
    settings: Any,
    providers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    providers = providers or {}
    provider_config_keys = (
        ("pexels", "pexels_api_key"),
        ("pixabay", "pixabay_api_key"),
    )
    return {
        "default_provider": getattr(settings, "online_material_provider", "auto"),
        "candidate_token_secret_configured": bool(
            getattr(settings, "candidate_token_secret", None)
        ),
        "providers": [
            {
                "provider": provider_name,
                "configured": bool(getattr(settings, config_key, None)),
                "enabled": provider_name in providers
                and _provider_is_enabled(providers[provider_name]),
            }
            for provider_name, config_key in provider_config_keys
        ],
    }
