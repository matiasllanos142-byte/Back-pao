import re
import threading
import time

import requests
from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


GITHUB_API_VERSION = "2022-11-28"
GITHUB_USER_AGENT = "paola-psicope-backend"
STREAM_CHUNK_SIZE = 64 * 1024
CHECKSUM_MAX_BYTES = 4096

_cache_lock = threading.Lock()
_release_cache = {"expires_at": 0.0, "value": None}


class AndroidReleaseNotFound(Exception):
    pass


class GitHubReleaseUnavailable(Exception):
    pass


def _github_headers(accept="application/vnd.github+json"):
    headers = {
        "Accept": accept,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": GITHUB_USER_AGENT,
    }
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
    return headers


def _release_api_url():
    return (
        f"https://api.github.com/repos/{settings.GITHUB_OWNER}/"
        f"{settings.GITHUB_REPO}/releases/latest"
    )


def _format_size(size):
    value = float(size or 0)
    units = ["B", "KB", "MB", "GB"]
    unit = units[0]
    for candidate in units:
        unit = candidate
        if value < 1024 or candidate == units[-1]:
            break
        value /= 1024
    return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"


def _asset_by_name(release, name):
    return next(
        (asset for asset in release.get("assets", []) if asset.get("name") == name),
        None,
    )


def _sha256_from_digest(asset):
    digest = str(asset.get("digest") or "")
    if digest.lower().startswith("sha256:"):
        value = digest.split(":", 1)[1].strip().lower()
        if re.fullmatch(r"[a-f0-9]{64}", value):
            return value
    return None


def _download_small_text_asset(asset):
    if not asset:
        return None
    try:
        response = requests.get(
            asset["url"],
            headers=_github_headers("application/octet-stream"),
            allow_redirects=True,
            timeout=(settings.GITHUB_CONNECT_TIMEOUT_SECONDS, settings.GITHUB_READ_TIMEOUT_SECONDS),
        )
        if response.status_code != 200 or len(response.content) > CHECKSUM_MAX_BYTES:
            return None
        match = re.search(r"\b[a-fA-F0-9]{64}\b", response.text)
        return match.group(0).lower() if match else None
    except (KeyError, requests.RequestException):
        return None


def _fetch_latest_release():
    if not settings.GITHUB_OWNER or not settings.GITHUB_REPO or not settings.GITHUB_APK_ASSET_NAME:
        raise GitHubReleaseUnavailable("missing_configuration")
    try:
        response = requests.get(
            _release_api_url(),
            headers=_github_headers(),
            timeout=(settings.GITHUB_CONNECT_TIMEOUT_SECONDS, settings.GITHUB_READ_TIMEOUT_SECONDS),
        )
    except requests.RequestException as exc:
        raise GitHubReleaseUnavailable("github_unreachable") from exc

    if response.status_code == 404:
        raise AndroidReleaseNotFound
    if response.status_code != 200:
        raise GitHubReleaseUnavailable(f"github_status_{response.status_code}")
    try:
        release = response.json()
    except ValueError as exc:
        raise GitHubReleaseUnavailable("invalid_github_response") from exc

    if release.get("draft") or release.get("prerelease"):
        raise AndroidReleaseNotFound
    apk_asset = _asset_by_name(release, settings.GITHUB_APK_ASSET_NAME)
    if not apk_asset or not apk_asset.get("url"):
        raise AndroidReleaseNotFound

    checksum = _sha256_from_digest(apk_asset)
    if checksum is None and settings.GITHUB_SHA256_ASSET_NAME:
        checksum = _download_small_text_asset(
            _asset_by_name(release, settings.GITHUB_SHA256_ASSET_NAME)
        )

    tag = str(release.get("tag_name") or "")
    version = tag[1:] if tag.lower().startswith("v") else tag
    size = int(apk_asset.get("size") or 0)
    return {
        "platform": "android",
        "available": True,
        "version": version,
        "tag": tag,
        "name": str(release.get("name") or tag or "Paola Psicopé Android"),
        "publishedAt": release.get("published_at"),
        "fileName": settings.GITHUB_APK_ASSET_NAME,
        "size": size,
        "sizeFormatted": _format_size(size),
        "sha256": checksum,
        "downloadUrl": "/api/app/android/download",
        "_assetApiUrl": apk_asset["url"],
    }


def get_latest_android_release():
    now = time.monotonic()
    with _cache_lock:
        if _release_cache["value"] is not None and now < _release_cache["expires_at"]:
            return _release_cache["value"]

    value = _fetch_latest_release()
    with _cache_lock:
        _release_cache["value"] = value
        _release_cache["expires_at"] = now + settings.GITHUB_RELEASE_CACHE_TTL_SECONDS
    return value


def _public_release(metadata):
    return {key: value for key, value in metadata.items() if not key.startswith("_")}


def _release_error(exc):
    if isinstance(exc, AndroidReleaseNotFound):
        return Response(
            {
                "error": "ANDROID_RELEASE_NOT_FOUND",
                "message": "La aplicación Android todavía no está disponible.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(
        {
            "error": "GITHUB_RELEASE_UNAVAILABLE",
            "message": "No se pudo consultar la aplicación Android.",
        },
        status=status.HTTP_502_BAD_GATEWAY,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def android_latest_view(request):
    try:
        return Response(_public_release(get_latest_android_release()))
    except (AndroidReleaseNotFound, GitHubReleaseUnavailable) as exc:
        return _release_error(exc)


@api_view(["GET"])
@permission_classes([AllowAny])
def android_download_view(request):
    try:
        metadata = get_latest_android_release()
        remote = requests.get(
            metadata["_assetApiUrl"],
            headers=_github_headers("application/octet-stream"),
            allow_redirects=True,
            stream=True,
            timeout=(settings.GITHUB_CONNECT_TIMEOUT_SECONDS, settings.GITHUB_READ_TIMEOUT_SECONDS),
        )
        if remote.status_code == 404:
            remote.close()
            raise AndroidReleaseNotFound
        if remote.status_code != 200:
            remote.close()
            raise GitHubReleaseUnavailable(f"asset_status_{remote.status_code}")

        iterator = remote.iter_content(chunk_size=STREAM_CHUNK_SIZE)
        first_chunk = next((chunk for chunk in iterator if chunk), b"")
        if not first_chunk:
            remote.close()
            raise GitHubReleaseUnavailable("empty_asset")

        def stream():
            try:
                if first_chunk:
                    yield first_chunk
                for chunk in iterator:
                    if chunk:
                        yield chunk
            finally:
                remote.close()

        response = StreamingHttpResponse(
            streaming_content=stream(),
            content_type="application/vnd.android.package-archive",
            status=200,
        )
        response["Content-Disposition"] = f'attachment; filename="{settings.GITHUB_APK_ASSET_NAME}"'
        response["Cache-Control"] = "public, max-age=300"
        response["X-Content-Type-Options"] = "nosniff"
        content_length = remote.headers.get("Content-Length") or metadata.get("size")
        if content_length:
            response["Content-Length"] = str(content_length)
        return response
    except requests.RequestException:
        return _release_error(GitHubReleaseUnavailable("asset_unreachable"))
    except (AndroidReleaseNotFound, GitHubReleaseUnavailable) as exc:
        return _release_error(exc)
