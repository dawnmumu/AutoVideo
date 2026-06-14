from __future__ import annotations

import ipaddress
import os
import socket
import uuid
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import ParseResult, urljoin, urlparse

import httpx

from autovideo.services.materials import record_material_file
from autovideo.storage.database import AutoVideoStore

DownloadResolver = Callable[[str], Iterable[str]]

DOWNLOAD_CHUNK_SIZE = 1024 * 1024
MAX_REDIRECTS = 5
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
ALLOWED_CONTENT_TYPE_SUFFIXES = {
    "video/mp4": {".mp4", ".m4v"},
    "video/quicktime": {".mov"},
    "video/webm": {".webm"},
}


class OnlineMaterialDownloadUrlNotAllowedError(ValueError):
    """Raised when a resolved download URL, DNS result, or connection is unsafe."""


class OnlineMaterialDownloadTooLargeError(Exception):
    def __init__(self, max_download_bytes: int) -> None:
        self.max_download_bytes = max_download_bytes
        super().__init__(str(max_download_bytes))


class OnlineMaterialContentTypeNotAllowedError(ValueError):
    """Raised when the response content type and file extension are not allowed."""


class OnlineMaterialDownloadFailedError(RuntimeError):
    """Raised when provider resolution or HTTP streaming fails."""


def default_download_resolver(hostname: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise OnlineMaterialDownloadUrlNotAllowedError(
            "download host could not be resolved"
        ) from exc

    addresses: list[str] = []
    seen: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        address = str(sockaddr[0])
        if address not in seen:
            seen.add(address)
            addresses.append(address)
    if not addresses:
        raise OnlineMaterialDownloadUrlNotAllowedError(
            "download host did not resolve to an address"
        )
    return addresses


def _normalize_hostname(hostname: str) -> str:
    host = hostname.rstrip(".").lower()
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise OnlineMaterialDownloadUrlNotAllowedError(
            "download host is not a valid hostname"
        ) from exc


def _normalize_allowed_hosts(allowed_hosts: Iterable[str]) -> set[str]:
    return {_normalize_hostname(host) for host in allowed_hosts if host}


def _address_from_value(value: Any) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    if isinstance(value, tuple):
        value = value[0] if value else ""
    address = str(value).strip().strip("[]")
    try:
        return ipaddress.ip_address(address)
    except ValueError as exc:
        raise OnlineMaterialDownloadUrlNotAllowedError(
            "download connection address is not an IP address"
        ) from exc


def _ip_is_forbidden(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        not address.is_global
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _validate_addresses(addresses: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in addresses:
        address = _address_from_value(value)
        if _ip_is_forbidden(address):
            raise OnlineMaterialDownloadUrlNotAllowedError(
                "download host resolved to a forbidden address"
            )
        normalized_address = str(address)
        if normalized_address not in seen:
            seen.add(normalized_address)
            normalized.append(normalized_address)
    if not normalized:
        raise OnlineMaterialDownloadUrlNotAllowedError(
            "download host did not resolve to an address"
        )
    return tuple(normalized)


def _validate_download_url_with_addresses(
    url: str,
    allowed_hosts: Iterable[str],
    resolver: DownloadResolver = default_download_resolver,
    *,
    verify_stable_resolution: bool = False,
) -> tuple[ParseResult, tuple[str, ...]]:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if parsed.scheme.lower() != "https" or not hostname:
        raise OnlineMaterialDownloadUrlNotAllowedError(
            "download URL must use https and include a hostname"
        )

    normalized_host = _normalize_hostname(hostname)
    try:
        ipaddress.ip_address(normalized_host)
    except ValueError:
        pass
    else:
        raise OnlineMaterialDownloadUrlNotAllowedError(
            "download URL hostname cannot be an IP address"
        )

    if normalized_host not in _normalize_allowed_hosts(allowed_hosts):
        raise OnlineMaterialDownloadUrlNotAllowedError(
            "download URL host is not allowed"
        )

    first_resolution = _validate_addresses(resolver(normalized_host))
    if not verify_stable_resolution:
        return parsed, first_resolution

    second_resolution = _validate_addresses(resolver(normalized_host))
    if set(first_resolution) != set(second_resolution):
        raise OnlineMaterialDownloadUrlNotAllowedError(
            "download host resolution changed between checks"
        )
    return parsed, second_resolution


def validate_download_url(
    url: str,
    allowed_hosts: Iterable[str],
    resolver: DownloadResolver = default_download_resolver,
    *,
    verify_stable_resolution: bool = False,
) -> ParseResult:
    parsed, _addresses = _validate_download_url_with_addresses(
        url,
        allowed_hosts,
        resolver,
        verify_stable_resolution=verify_stable_resolution,
    )
    return parsed


def validate_redirect_chain(
    urls: Iterable[str],
    allowed_hosts: Iterable[str],
    resolver: DownloadResolver = default_download_resolver,
) -> None:
    for url in urls:
        validate_download_url(
            url,
            allowed_hosts,
            resolver,
            verify_stable_resolution=True,
        )


def validate_connection_addresses(
    hostname: str,
    preflight_addresses: Iterable[str],
    connected_address: Any,
) -> None:
    _normalize_hostname(hostname)
    connected = _address_from_value(connected_address)
    if _ip_is_forbidden(connected):
        raise OnlineMaterialDownloadUrlNotAllowedError(
            "download connected to a forbidden address"
        )
    allowed_addresses = {
        _address_from_value(address) for address in preflight_addresses
    }
    if connected not in allowed_addresses:
        raise OnlineMaterialDownloadUrlNotAllowedError(
            "download connected address did not match preflight DNS resolution"
        )


def _base_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def content_type_matches_extension(content_type: str | None, extension: str) -> bool:
    allowed_suffixes = ALLOWED_CONTENT_TYPE_SUFFIXES.get(
        _base_content_type(content_type)
    )
    return allowed_suffixes is not None and extension.lower() in allowed_suffixes


def safe_download_suffix(url: str, content_type: str | None) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if not suffix or not content_type_matches_extension(content_type, suffix):
        raise OnlineMaterialContentTypeNotAllowedError(
            "download content type does not match an allowed file extension"
        )
    return suffix


def _connected_address_from_response(response: httpx.Response) -> Any | None:
    connected_address = response.extensions.get("connected_address")
    if connected_address is not None:
        return connected_address

    network_stream = response.extensions.get("network_stream")
    if network_stream is None:
        return None

    get_extra_info = getattr(network_stream, "get_extra_info", None)
    if callable(get_extra_info):
        connected_address = get_extra_info("server_addr")
        if connected_address is not None:
            return connected_address
    return getattr(network_stream, "server_addr", None)


def _validate_response_connection(
    response: httpx.Response,
    hostname: str,
    preflight_addresses: Iterable[str],
) -> None:
    connected_address = _connected_address_from_response(response)
    if connected_address is None:
        raise OnlineMaterialDownloadUrlNotAllowedError(
            "download response did not expose a connected address"
        )
    validate_connection_addresses(hostname, preflight_addresses, connected_address)


@contextmanager
def open_validated_download_response(
    http_client: httpx.Client,
    url: str,
    allowed_hosts: Iterable[str],
    resolver: DownloadResolver = default_download_resolver,
    *,
    timeout: float | None = None,
    max_redirects: int = MAX_REDIRECTS,
) -> Iterator[tuple[httpx.Response, str]]:
    current_url = url
    for _redirect_count in range(max_redirects + 1):
        parsed, preflight_addresses = _validate_download_url_with_addresses(
            current_url,
            allowed_hosts,
            resolver,
            verify_stable_resolution=True,
        )
        stream = http_client.stream(
            "GET",
            current_url,
            follow_redirects=False,
            timeout=timeout,
        )
        try:
            response = stream.__enter__()
        except httpx.HTTPError as exc:
            raise OnlineMaterialDownloadFailedError(
                "download request failed"
            ) from exc

        try:
            _validate_response_connection(
                response,
                parsed.hostname or "",
                preflight_addresses,
            )

            if response.status_code in REDIRECT_STATUS_CODES:
                location = response.headers.get("location")
                if not location:
                    raise OnlineMaterialDownloadUrlNotAllowedError(
                        "download redirect did not include a location"
                    )
                current_url = urljoin(str(response.url), location)
                validate_download_url(
                    current_url,
                    allowed_hosts,
                    resolver,
                    verify_stable_resolution=True,
                )
                stream.__exit__(None, None, None)
                continue

            if 200 <= response.status_code < 300:
                try:
                    yield response, current_url
                finally:
                    stream.__exit__(None, None, None)
                return

            raise OnlineMaterialDownloadFailedError(
                "download response returned an unsuccessful status"
            )
        except BaseException as exc:
            stream.__exit__(type(exc), exc, exc.__traceback__)
            raise

    raise OnlineMaterialDownloadUrlNotAllowedError("download redirected too many times")


def _safe_original_filename(
    provider_name: str,
    asset_id: str,
    suffix: str,
) -> str:
    safe_provider = "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in provider_name
    ) or "online"
    safe_asset_id = "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in asset_id
    ) or "asset"
    return f"{safe_provider}-{safe_asset_id}{suffix}"


def stream_provider_download_to_material(
    *,
    store: AutoVideoStore,
    provider: Any,
    asset_id: str,
    file_variant: str,
    source_url: str,
    license_note: str | None,
    query: str,
    http_client: httpx.Client,
    max_download_bytes: int,
    resolver: DownloadResolver = default_download_resolver,
    timeout: float | None = None,
) -> dict[str, Any]:
    provider_name = str(getattr(provider, "name", "online"))
    allowed_hosts = set(getattr(provider, "allowed_download_hosts", set()) or set())
    if not allowed_hosts:
        raise OnlineMaterialDownloadUrlNotAllowedError(
            "provider does not declare allowed download hosts"
        )

    try:
        download_url = provider.resolve_download_url(asset_id, file_variant)
    except Exception as exc:
        raise OnlineMaterialDownloadFailedError(
            "provider failed to resolve a download URL"
        ) from exc

    material_id = uuid.uuid4().hex
    temp_path = store.paths.materials / f".{material_id}.download"
    final_path: Path | None = None
    success = False

    try:
        with open_validated_download_response(
            http_client,
            str(download_url),
            allowed_hosts,
            resolver,
            timeout=timeout,
        ) as (response, final_url):
            content_type = response.headers.get("content-type")
            suffix = safe_download_suffix(final_url, content_type)
            final_path = store.paths.materials / f"{material_id}{suffix}"

            content_length = response.headers.get("content-length")
            if content_length and content_length.isdecimal():
                if int(content_length) > max_download_bytes:
                    raise OnlineMaterialDownloadTooLargeError(max_download_bytes)

            size_bytes = 0
            with temp_path.open("wb") as output_file:
                try:
                    for chunk in response.iter_bytes(DOWNLOAD_CHUNK_SIZE):
                        if not chunk:
                            continue
                        size_bytes += len(chunk)
                        if size_bytes > max_download_bytes:
                            raise OnlineMaterialDownloadTooLargeError(
                                max_download_bytes
                            )
                        output_file.write(chunk)
                except httpx.HTTPError as exc:
                    raise OnlineMaterialDownloadFailedError(
                        "download stream failed"
                    ) from exc

        if final_path is None:
            raise OnlineMaterialDownloadFailedError(
                "download response did not produce a material file path"
            )
        os.replace(temp_path, final_path)
        material = record_material_file(
            store,
            _safe_original_filename(provider_name, asset_id, suffix),
            content_type,
            size_bytes,
            final_path,
            {
                "source_type": "online",
                "source_provider": provider_name,
                "source_asset_id": asset_id,
                "source_url": source_url,
                "license_note": license_note,
                "query": query,
            },
            material_id=material_id,
        )
        success = True
        return material
    finally:
        if not success:
            temp_path.unlink(missing_ok=True)
            if final_path is not None:
                final_path.unlink(missing_ok=True)
