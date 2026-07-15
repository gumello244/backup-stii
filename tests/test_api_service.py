from __future__ import annotations

"""Unit tests for ApiService telemetry reporting client."""
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from config import ApiConfig
from services.api_service import ApiService


class TestApiService(unittest.IsolatedAsyncioTestCase):
    """Test suite for telemetry client API formatting and behavior."""

    async def test_report_startup(self) -> None:
        """Verify startup event formats correct json payload."""
        cfg = ApiConfig(url="http://test-server/api", app_version="2.0.0")
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_resp = AsyncMock()
            mock_resp.raise_for_status = lambda: None
            mock_post.return_value = mock_resp

            svc = ApiService(cfg)
            await svc.report_startup()

            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            self.assertIn("/event", args[0])

            payload = kwargs["json"]
            self.assertEqual(payload["event"], "APP_STARTUP")
            self.assertEqual(payload["status"], "SUCCESS")
            self.assertEqual(payload["details"]["version"], "2.0.0")

    async def test_report_shutdown(self) -> None:
        """Verify shutdown event formatting."""
        cfg = ApiConfig(url="http://test-server/api", app_version="2.0.0")
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_resp = AsyncMock()
            mock_resp.raise_for_status = lambda: None
            mock_post.return_value = mock_resp

            svc = ApiService(cfg)
            await svc.report_shutdown()

            mock_post.assert_called_once()
            payload = mock_post.call_args[1]["json"]
            self.assertEqual(payload["event"], "APP_SHUTDOWN")
            self.assertEqual(payload["status"], "SUCCESS")

    async def test_report_success(self) -> None:
        """Verify success telemetry payload inclusion."""
        cfg = ApiConfig(url="http://test-server/api", app_version="2.0.0")
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_resp = AsyncMock()
            mock_resp.raise_for_status = lambda: None
            mock_post.return_value = mock_resp

            svc = ApiService(cfg)
            await svc.report_success("RESTORE_COMPLETED", {"files": 12})

            mock_post.assert_called_once()
            payload = mock_post.call_args[1]["json"]
            self.assertEqual(payload["event"], "RESTORE_COMPLETED")
            self.assertEqual(payload["status"], "SUCCESS")
            self.assertEqual(payload["details"]["files"], 12)

    async def test_report_failure(self) -> None:
        """Verify failure telemetry reports error message context."""
        cfg = ApiConfig(url="http://test-server/api", app_version="2.0.0")
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_resp = AsyncMock()
            mock_resp.raise_for_status = lambda: None
            mock_post.return_value = mock_resp

            svc = ApiService(cfg)
            await svc.report_failure("RESTORE_FAILED", "Disk full", {"attempt": 1})

            mock_post.assert_called_once()
            payload = mock_post.call_args[1]["json"]
            self.assertEqual(payload["event"], "RESTORE_FAILED")
            self.assertEqual(payload["status"], "FAILURE")
            self.assertEqual(payload["details"]["error_message"], "Disk full")
            self.assertEqual(payload["details"]["attempt"], 1)

    async def test_report_crash(self) -> None:
        """Verify crash telemetry extracts exceptions type and traceback."""
        cfg = ApiConfig(url="http://test-server/api", app_version="2.0.0")
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_resp = AsyncMock()
            mock_resp.raise_for_status = lambda: None
            mock_post.return_value = mock_resp

            svc = ApiService(cfg)
            try:
                raise ValueError("Oops crash")
            except ValueError as exc:
                import sys
                _, val, tb = sys.exc_info()
                await svc.report_crash(ValueError, val, tb)

            mock_post.assert_called_once()
            payload = mock_post.call_args[1]["json"]
            self.assertEqual(payload["event"], "APP_CRASH")
            self.assertEqual(payload["status"], "FAILURE")
            self.assertEqual(payload["details"]["error_type"], "ValueError")
            self.assertEqual(payload["details"]["error_message"], "Oops crash")
            self.assertIn("ValueError: Oops crash", payload["details"]["stack_trace"])

    async def test_post_swallows_errors_silently(self) -> None:
        """Verify network exceptions are caught and logged without propagating."""
        cfg = ApiConfig(url="http://test-server/api", app_version="2.0.0")
        with patch("httpx.AsyncClient.post", side_effect=httpx.NetworkError("Down")):
            svc = ApiService(cfg)
            # Should not raise exception
            await svc.report_startup()


if __name__ == "__main__":
    unittest.main()
