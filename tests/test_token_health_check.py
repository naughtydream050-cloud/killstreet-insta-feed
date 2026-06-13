import json
import unittest
from unittest.mock import Mock

from scripts import token_health_check as thc


class TokenHealthCheckTests(unittest.TestCase):
    def test_instagram_refreshes_when_expiring_soon(self):
        responses = [
            Mock(
                status_code=200,
                json=lambda: {
                    "data": {
                        "is_valid": True,
                        "expires_at": thc.now_epoch() + 5 * 24 * 60 * 60,
                        "scopes": [
                            "instagram_basic",
                            "instagram_content_publish",
                            "pages_show_list",
                            "pages_read_engagement",
                        ],
                    }
                },
            ),
            Mock(status_code=200, json=lambda: {"id": "17841444299065004", "username": "killstreetbrand"}),
            Mock(status_code=200, json=lambda: {"access_token": "new-token", "expires_in": 5184000}),
        ]
        session = Mock(get=Mock(side_effect=responses))
        updates = []

        result = thc.check_instagram(
            session,
            token="old-token",
            ig_user_id="17841444299065004",
            secret_updater=lambda name, value: updates.append((name, value)) or True,
            refresh_threshold_days=14,
        )

        self.assertEqual(result["status"], "refreshed")
        self.assertEqual(updates, [("INSTAGRAM_TOKEN", "new-token")])
        self.assertNotIn("new-token", json.dumps(result))

    def test_instagram_does_not_refresh_when_secret_updates_unavailable(self):
        responses = [
            Mock(
                status_code=200,
                json=lambda: {
                    "data": {
                        "is_valid": True,
                        "expires_at": thc.now_epoch() + 5 * 24 * 60 * 60,
                        "scopes": [
                            "instagram_basic",
                            "instagram_content_publish",
                            "pages_show_list",
                            "pages_read_engagement",
                        ],
                    }
                },
            ),
            Mock(status_code=200, json=lambda: {"id": "17841444299065004", "username": "killstreetbrand"}),
        ]
        session = Mock(get=Mock(side_effect=responses))

        result = thc.check_instagram(
            session,
            token="old-token",
            ig_user_id="17841444299065004",
            refresh_threshold_days=14,
            can_save_secrets=False,
        )

        self.assertEqual(result["status"], "valid_refresh_not_saved")
        self.assertEqual(result["refresh_status"], "secret_updater_missing")
        self.assertEqual(session.get.call_count, 2)

    def test_base_refreshes_access_and_refresh_token_when_access_invalid(self):
        responses = [
            Mock(status_code=401, json=lambda: {"error": "invalid_request"}),
            Mock(
                status_code=200,
                json=lambda: {"access_token": "new-access", "refresh_token": "new-refresh"},
            ),
            Mock(status_code=200, json=lambda: {"items": [{"item_id": 1}]}),
        ]
        session = Mock()
        session.get.side_effect = [responses[0], responses[2]]
        session.post.return_value = responses[1]
        updates = []

        result = thc.check_base(
            session,
            access_token="old-access",
            refresh_token="old-refresh",
            client_id="client-id",
            client_secret="client-secret",
            secret_updater=lambda name, value: updates.append((name, value)) or True,
        )

        self.assertEqual(result["status"], "refreshed")
        self.assertEqual(updates, [("BASE_ACCESS_TOKEN", "new-access"), ("BASE_REFRESH_TOKEN", "new-refresh")])
        self.assertNotIn("new-access", json.dumps(result))
        self.assertNotIn("new-refresh", json.dumps(result))

    def test_base_does_not_refresh_when_secret_updates_unavailable(self):
        session = Mock()
        session.get.return_value = Mock(status_code=401, json=lambda: {"error": "invalid_request"})

        result = thc.check_base(
            session,
            access_token="old-access",
            refresh_token="old-refresh",
            client_id="client-id",
            client_secret="client-secret",
            can_save_secrets=False,
        )

        self.assertEqual(result["status"], "access_invalid")
        self.assertEqual(result["refresh_status"], "secret_updater_missing")
        session.post.assert_not_called()

    def test_hf_distinguishes_invalid_token_from_quota_message(self):
        invalid = Mock(status_code=401, text="Unauthorized", json=lambda: {"error": "Invalid token"})
        session = Mock(get=Mock(return_value=invalid))
        invalid_result = thc.check_hf(session, token="bad-token")
        self.assertEqual(invalid_result["status"], "invalid")

        quota_result = thc.classify_hf_generation_error("You have exceeded your ZeroGPU quota")
        self.assertEqual(quota_result, "quota_limited")


if __name__ == "__main__":
    unittest.main()
