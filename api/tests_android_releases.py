from unittest.mock import Mock, patch

from django.test import override_settings
from rest_framework.test import APITestCase

from . import android_releases


def release_payload(include_apk=True, include_checksum=False):
    assets = []
    if include_apk:
        assets.append({
            "id": 10,
            "name": "paola-psicope.apk",
            "url": "https://api.github.com/repos/owner/repo/releases/assets/10",
            "browser_download_url": "https://github.com/private/download.apk",
            "size": 12_345_678,
        })
    if include_checksum:
        assets.append({
            "id": 11,
            "name": "paola-psicope.apk.sha256",
            "url": "https://api.github.com/repos/owner/repo/releases/assets/11",
            "size": 80,
        })
    return {
        "tag_name": "v1.2.3",
        "name": "Paola Psicopé 1.2.3",
        "published_at": "2026-07-10T20:00:00Z",
        "draft": False,
        "prerelease": False,
        "assets": assets,
    }


def json_response(payload, status_code=200):
    response = Mock(status_code=status_code)
    response.json.return_value = payload
    return response


@override_settings(
    GITHUB_OWNER="negro123454332-jpg",
    GITHUB_REPO="app-pao",
    GITHUB_TOKEN="test-secret-token",
    GITHUB_APK_ASSET_NAME="paola-psicope.apk",
    GITHUB_SHA256_ASSET_NAME="paola-psicope.apk.sha256",
    GITHUB_RELEASE_CACHE_TTL_SECONDS=300,
    GITHUB_CONNECT_TIMEOUT_SECONDS=1,
    GITHUB_READ_TIMEOUT_SECONDS=1,
)
class AndroidReleaseTests(APITestCase):
    def setUp(self):
        android_releases._release_cache["value"] = None
        android_releases._release_cache["expires_at"] = 0

    @patch("api.android_releases.requests.get")
    def test_latest_returns_safe_metadata(self, mocked_get):
        mocked_get.return_value = json_response(release_payload())
        response = self.client.get("/api/app/android/latest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["version"], "1.2.3")
        self.assertEqual(response.data["tag"], "v1.2.3")
        self.assertEqual(response.data["fileName"], "paola-psicope.apk")
        self.assertEqual(response.data["downloadUrl"], "/api/app/android/download")
        self.assertEqual(
            response["Cache-Control"],
            "no-store, no-cache, must-revalidate, max-age=0",
        )

    @patch("api.android_releases.requests.get")
    def test_latest_never_exposes_github_url_or_token(self, mocked_get):
        mocked_get.return_value = json_response(release_payload())
        response = self.client.get("/api/app/android/latest")
        serialized = str(response.data)
        self.assertNotIn("browser_download_url", serialized)
        self.assertNotIn("api.github.com", serialized)
        self.assertNotIn("test-secret-token", serialized)

    @patch("api.android_releases.requests.get")
    def test_latest_uses_fixed_owner_and_repo(self, mocked_get):
        mocked_get.return_value = json_response(release_payload())
        self.client.get("/api/app/android/latest?owner=attacker&repo=other")
        called_url = mocked_get.call_args.args[0]
        self.assertEqual(
            called_url,
            "https://api.github.com/repos/negro123454332-jpg/app-pao/releases/latest",
        )

    @patch("api.android_releases.requests.get")
    def test_latest_sends_token_only_to_github(self, mocked_get):
        mocked_get.return_value = json_response(release_payload())
        self.client.get("/api/app/android/latest")
        self.assertEqual(
            mocked_get.call_args.kwargs["headers"]["Authorization"],
            "Bearer test-secret-token",
        )

    @patch("api.android_releases.requests.get")
    def test_latest_returns_404_when_release_does_not_exist(self, mocked_get):
        mocked_get.return_value = json_response({}, status_code=404)
        response = self.client.get("/api/app/android/latest")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["error"], "ANDROID_RELEASE_NOT_FOUND")

    @patch("api.android_releases.requests.get")
    def test_latest_returns_404_when_apk_is_missing(self, mocked_get):
        mocked_get.return_value = json_response(release_payload(include_apk=False))
        response = self.client.get("/api/app/android/latest")
        self.assertEqual(response.status_code, 404)

    @patch("api.android_releases.requests.get")
    def test_checksum_is_null_when_asset_is_missing(self, mocked_get):
        mocked_get.return_value = json_response(release_payload())
        response = self.client.get("/api/app/android/latest")
        self.assertIsNone(response.data["sha256"])

    @patch("api.android_releases.requests.get")
    def test_checksum_asset_is_parsed(self, mocked_get):
        metadata_response = json_response(release_payload(include_checksum=True))
        checksum_response = Mock(status_code=200)
        checksum_response.content = b"a" * 64
        checksum_response.text = "a" * 64 + "  paola-psicope.apk\n"
        mocked_get.side_effect = [metadata_response, checksum_response]
        response = self.client.get("/api/app/android/latest")
        self.assertEqual(response.data["sha256"], "a" * 64)

    @patch("api.android_releases.requests.get")
    def test_force_refresh_bypasses_metadata_cache(self, mocked_get):
        mocked_get.return_value = json_response(release_payload())
        self.client.get("/api/app/android/latest")
        self.client.get("/api/app/android/latest")
        self.assertEqual(mocked_get.call_count, 2)

    @patch("api.android_releases.requests.get")
    def test_internal_cached_lookup_still_avoids_repeated_github_calls(self, mocked_get):
        mocked_get.return_value = json_response(release_payload())
        android_releases.get_latest_android_release()
        android_releases.get_latest_android_release()
        self.assertEqual(mocked_get.call_count, 1)

    @patch("api.android_releases.get_latest_android_release")
    @patch("api.android_releases.requests.get")
    def test_download_streams_apk_with_safe_headers(self, mocked_get, mocked_latest):
        mocked_latest.return_value = {
            "_assetApiUrl": "https://api.github.com/assets/10",
            "size": 6,
        }
        remote = Mock(status_code=200)
        remote.headers = {"Content-Length": "6"}
        remote.iter_content.return_value = iter([b"abc", b"def"])
        mocked_get.return_value = remote
        response = self.client.get("/api/app/android/download")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/vnd.android.package-archive")
        self.assertIn("paola-psicope.apk", response["Content-Disposition"])
        self.assertEqual(b"".join(response.streaming_content), b"abcdef")
        mocked_latest.assert_called_once_with(force_refresh=True)
        remote.close.assert_called()

    @patch("api.android_releases.get_latest_android_release")
    @patch("api.android_releases.requests.get")
    def test_download_returns_502_when_github_fails(self, mocked_get, mocked_latest):
        mocked_latest.return_value = {"_assetApiUrl": "https://api.github.com/assets/10", "size": 6}
        remote = Mock(status_code=503)
        mocked_get.return_value = remote
        response = self.client.get("/api/app/android/download")
        self.assertEqual(response.status_code, 502)

    @patch("api.android_releases.get_latest_android_release")
    @patch("api.android_releases.requests.get")
    def test_download_does_not_buffer_entire_apk(self, mocked_get, mocked_latest):
        mocked_latest.return_value = {"_assetApiUrl": "https://api.github.com/assets/10", "size": 3}
        remote = Mock(status_code=200)
        remote.headers = {}
        remote.iter_content.return_value = iter([b"a", b"b", b"c"])
        mocked_get.return_value = remote
        response = self.client.get("/api/app/android/download")
        self.assertTrue(response.streaming)
        self.assertTrue(mocked_get.call_args.kwargs["stream"])
        self.assertEqual(b"".join(response.streaming_content), b"abc")

