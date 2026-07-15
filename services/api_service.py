from __future__ import annotations

"""Telemetry HTTP client for Remos — mirrors SONICO's ApiService pattern.

Wraps httpx behind a project-owned interface so the third-party dependency
stays swappable. All methods are fire-and-forget; failures are logged but
never block the user flow.

Example:
    api = ApiService(get_api_config())
    await api.report_startup()
"""
import logging
import os
import platform
import socket
import traceback
import uuid
from typing import Optional

import httpx

from config import ApiConfig, get_app_name

logger = logging.getLogger(__name__)


class ApiService:
    """Async HTTP telemetry client injected with ApiConfig.

    Example:
        svc = ApiService(ApiConfig(url="http://...", app_version="1.0.0"))
        await svc.report_startup()
    """

    def __init__(self, config: ApiConfig) -> None:
        self._config = config
        self._base_url = config.url.rstrip("/")
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            timeout=10.0, trust_env=False,
        )
        self._session_id = str(uuid.uuid4())
        self._system_info = self._gather_system_info()

    # ------------------------------------------------------------------
    # System helpers
    # ------------------------------------------------------------------

    def _gather_system_info(self) -> dict[str, str]:
        """Collect static OS/host info once at init."""
        return {
            "operating_system": f"{platform.system()} {platform.release()}",
            "device_hostname": socket.gethostname(),
            "version": self._config.app_version,
        }

    def _get_user_login(self) -> str:
        """Current Windows login name."""
        return os.environ.get("USERNAME", "Unknown")

    def _get_local_ip(self) -> str:
        """Best-effort local IPv4 address."""
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "0.0.0.0"

    # ------------------------------------------------------------------
    # Core transport
    # ------------------------------------------------------------------

    async def _post_event(
        self,
        event_type: str,
        status: str,
        details: Optional[dict[str, object]] = None,
    ) -> None:
        """Send a single telemetry event, swallowing errors."""
        if not self._base_url:
            return

        payload_details = {**self._system_info, "session_id": self._session_id}
        if details:
            payload_details.update(details)

        payload = {
            "tool_name": get_app_name(),
            "event": event_type,
            "status": status,
            "details": payload_details,
            "user_login": self._get_user_login(),
            "device_ip": self._get_local_ip(),
        }
        try:
            resp = await self._client.post(
                f"{self._base_url}/event", json=payload,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.error(
                '{"event":"telemetry_send_failed","target":"%s","error":"%s"}',
                event_type,
                exc,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def report_startup(self) -> None:
        """Log application launch."""
        await self._post_event("APP_STARTUP", "SUCCESS")

    async def report_shutdown(self) -> None:
        """Log graceful shutdown."""
        await self._post_event("APP_SHUTDOWN", "SUCCESS")

    async def report_success(
        self, event: str, details: Optional[dict[str, object]] = None,
    ) -> None:
        """Log a successful restore operation."""
        await self._post_event(event, "SUCCESS", details)

    async def report_failure(
        self,
        event: str,
        error_msg: str,
        details: Optional[dict[str, object]] = None,
    ) -> None:
        """Log a failed restore operation with error context."""
        merged = dict(details) if details else {}
        merged["error_message"] = str(error_msg)
        await self._post_event(event, "FAILURE", merged)

    async def report_crash(
        self,
        exc_type: type,
        exc_value: BaseException,
        exc_traceback: object,
    ) -> None:
        """Log unhandled crash with full stack trace."""
        tb_lines = traceback.format_exception(
            exc_type, exc_value, exc_traceback,
        )
        details = {
            "error_type": exc_type.__name__,
            "error_message": str(exc_value),
            "stack_trace": "".join(tb_lines),
        }
        await self._post_event("APP_CRASH", "FAILURE", details)

    async def close(self) -> None:
        """Cleanly close the underlying HTTP client."""
        await self._client.aclose()
