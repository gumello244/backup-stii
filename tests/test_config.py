from __future__ import annotations

"""Unit tests for config.py configuration factories and fallbacks."""
import unittest
from unittest.mock import patch

import config


class TestConfig(unittest.TestCase):
    """Test suite for config.py configurations and env parameters."""

    def test_get_server_config_defaults(self) -> None:
        """Verify get_server_config defaults when secrets are not present."""
        with patch("config.app_secrets", None):
            cfg = config.get_server_config()
            self.assertEqual(cfg.server_ip, "localhost")
            self.assertEqual(cfg.backup_share, "backups")

    def test_get_server_config_custom(self) -> None:
        """Verify get_server_config overrides from app_secrets."""
        class MockSecrets:
            BACKUP_SERVER_IP = "10.0.0.1"
            BACKUP_SHARE_NAME = "custom_share"

        with patch("config.app_secrets", MockSecrets):
            cfg = config.get_server_config()
            self.assertEqual(cfg.server_ip, "10.0.0.1")
            self.assertEqual(cfg.backup_share, "custom_share")

    def test_get_api_config_defaults(self) -> None:
        """Verify get_api_config fallback values."""
        with patch("config.app_secrets", None):
            cfg = config.get_api_config()
            self.assertEqual(cfg.url, "")
            self.assertEqual(cfg.app_version, "0.0.2")

    def test_get_copy_retry_config_defaults(self) -> None:
        """Verify copy retry settings default mapping."""
        with patch("config.app_secrets", None):
            cfg = config.get_copy_retry_config()
            self.assertEqual(cfg.max_retries, 3)
            self.assertEqual(cfg.backoff_base, 1.0)
            self.assertEqual(cfg.consecutive_fail_limit, 3)

    def test_get_copy_retry_config_custom(self) -> None:
        """Verify custom retry configuration mapping."""
        class MockSecrets:
            COPY_MAX_RETRIES = 5
            COPY_BACKOFF_BASE_SECONDS = 0.5
            COPY_CONSECUTIVE_FAIL_LIMIT = 2

        with patch("config.app_secrets", MockSecrets):
            cfg = config.get_copy_retry_config()
            self.assertEqual(cfg.max_retries, 5)
            self.assertEqual(cfg.backoff_base, 0.5)
            self.assertEqual(cfg.consecutive_fail_limit, 2)

    def test_is_test_mode(self) -> None:
        """Verify test mode identification formats."""
        with patch("config.app_secrets", None):
            self.assertFalse(config.is_test_mode())

        class MockTrueBool:
            TEST_MODE = True

        with patch("config.app_secrets", MockTrueBool):
            self.assertTrue(config.is_test_mode())

        class MockTrueStr:
            TEST_MODE = "true"

        with patch("config.app_secrets", MockTrueStr):
            self.assertTrue(config.is_test_mode())

        class MockOneStr:
            TEST_MODE = "1"

        with patch("config.app_secrets", MockOneStr):
            self.assertTrue(config.is_test_mode())

    def test_get_app_name(self) -> None:
        """Verify get_app_name resolution."""
        with patch("config.app_secrets", None):
            self.assertEqual(config.get_app_name(), "Remos")

        class MockAppName:
            APP_NAME = "CustomRemos"

        with patch("config.app_secrets", MockAppName):
            self.assertEqual(config.get_app_name(), "CustomRemos")

    def test_get_discovery_cache_ttl_seconds_default(self) -> None:
        """Verify the discovery cache TTL default when secrets are not present."""
        with patch("config.app_secrets", None):
            self.assertEqual(config.get_discovery_cache_ttl_seconds(), 30.0)

    def test_get_discovery_cache_ttl_seconds_custom(self) -> None:
        """Verify the discovery cache TTL overrides from app_secrets."""
        class MockSecrets:
            DISCOVERY_CACHE_TTL_SECONDS = 90.0

        with patch("config.app_secrets", MockSecrets):
            self.assertEqual(config.get_discovery_cache_ttl_seconds(), 90.0)


if __name__ == "__main__":
    unittest.main()
