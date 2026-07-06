from __future__ import annotations

"""Remos configuration layer — reads values from app_secrets.py.

All config dataclasses are constructed via factory functions so that
dependency injection is explicit and testable.

Example:
    server = get_server_config()
    root = f"\\\\{server.server_ip}\\\\{server.backup_share}"
"""
from dataclasses import dataclass

# ------------------------------------------------------------------
# Benchmark / speed estimation constants
# ------------------------------------------------------------------

# Size of the temporary write-benchmark file (5 MB)
BENCHMARK_FILE_BYTES: int = 5 * 1024 * 1024
# Block size used inside the benchmark write loop (1 MB)
BENCHMARK_BLOCK_BYTES: int = 1 * 1024 * 1024

# Fallback write speed when the benchmark fails on a local disk (50 MB/s)
LOCAL_SPEED_FALLBACK_BPS: int = 50 * 1024 * 1024
# Fallback write speed when the benchmark fails on a network path (80 MB/s)
NETWORK_SPEED_FALLBACK_BPS: int = 80 * 1024 * 1024

# Upper cap applied to measured local write speed to avoid absurd estimates
# (200 MB/s — fast SSD ceiling for sequential write to a single file)
WRITE_SPEED_CAP_BPS: int = 200 * 1024 * 1024

# ------------------------------------------------------------------
# Disk-space overhead constants (used in confirm_view requirements check)
# ------------------------------------------------------------------

# Fractional size overhead to reserve on top of required bytes (10 %)
DISK_OVERHEAD_FACTOR: float = 1.1
# Minimum free-space buffer beyond the overhead, in bytes (200 MB)
DISK_OVERHEAD_BUFFER_BYTES: int = 200 * 1024 * 1024

# Upper limit of concurrent threads allowed for parallel directory walks to avoid network congestion
MAX_CONCURRENT_DISCOVERY_TASKS: int = 4


try:
    import app_secrets
except ImportError:
    app_secrets = None


def _get_secret(key: str, default: str = "") -> str:
    """Read a single value from app_secrets module.

    Example:
        ip = _get_secret("BACKUP_SERVER_IP", "192.168.11.245")
    """
    if app_secrets and hasattr(app_secrets, key):
        val = getattr(app_secrets, key)
        if val is not None:
            return val
    return default


@dataclass(frozen=True)
class ServerConfig:
    """Network/local backup paths set by IT.

    Example:
        cfg = get_server_config()
        network_root = f"\\\\\\\\{cfg.server_ip}\\\\{cfg.backup_share}"
    """
    server_ip: str
    backup_share: str


@dataclass(frozen=True)
class ApiConfig:
    """Internal telemetry endpoint."""
    url: str
    app_version: str


@dataclass(frozen=True)
class CopyRetryConfig:
    """Retry-with-backoff settings for file copy resilience.

    Example:
        cfg = get_copy_retry_config()
        delay = cfg.backoff_base ** attempt
    """
    max_retries: int
    backoff_base: float
    consecutive_fail_limit: int


def get_server_config() -> ServerConfig:
    """Factory for backup server configuration."""
    return ServerConfig(
        server_ip=_get_secret("BACKUP_SERVER_IP", "localhost"),
        backup_share=_get_secret("BACKUP_SHARE_NAME", "backups"),
    )


def get_api_config() -> ApiConfig:
    """Factory for API telemetry configuration."""
    return ApiConfig(
        url=_get_secret("BACKEND_URL"),
        app_version=_get_secret("APP_VERSION", "1.0.0"),
    )


def get_copy_retry_config() -> CopyRetryConfig:
    """Factory for copy resilience settings."""
    return CopyRetryConfig(
        max_retries=int(_get_secret("COPY_MAX_RETRIES", "3")),
        backoff_base=float(_get_secret("COPY_BACKOFF_BASE_SECONDS", "1.0")),
        consecutive_fail_limit=int(
            _get_secret("COPY_CONSECUTIVE_FAIL_LIMIT", "3")
        ),
    )


def is_test_mode() -> bool:
    """Return True if TEST_MODE is enabled in app_secrets.

    Example:
        if is_test_mode():
            print("Running in test/visualizer mode")
    """
    val = _get_secret("TEST_MODE", "False")
    if isinstance(val, bool):
        return val
    return str(val).lower() == "true" or str(val) == "1"


def get_app_name() -> str:
    """Return the application name configured in app_secrets, default to Remos."""
    return _get_secret("APP_NAME", "Remos")


def get_admin_password() -> str:
    """Return the admin password for entering admin mode.

    Example:
        pwd = get_admin_password()
    """
    return _get_secret("ADMIN_PASSWORD", "superremos")


