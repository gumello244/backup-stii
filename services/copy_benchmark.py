from __future__ import annotations

"""Write-speed benchmarking and copy-time estimation for the confirm screen.

Split out of backup_copier.py (which owns the actual restore copy engine) —
this is a separate responsibility: measuring disk/network write speed and
using it to estimate how long a restore will take, before any copying starts.

Example:
    speed = run_write_benchmark(Path.home())
    seconds = estimate_copy_seconds_for_files(files, speed)
"""
import logging
import time
from pathlib import Path
from typing import Optional

from config import (
    BENCHMARK_FILE_BYTES,
    BENCHMARK_BLOCK_BYTES,
    LOCAL_SPEED_FALLBACK_BPS,
    NETWORK_SPEED_FALLBACK_BPS,
    WRITE_SPEED_CAP_BPS,
)
from services.backup_merger import MergedFile

logger = logging.getLogger(__name__)


def _do_write_benchmark(test_file: Path) -> int:
    """Perform actual write speed test, returning bytes per second."""
    block_count = BENCHMARK_FILE_BYTES // BENCHMARK_BLOCK_BYTES
    data = b"A" * BENCHMARK_BLOCK_BYTES
    with open(test_file, "wb") as f:
        t0 = time.perf_counter()
        for _ in range(block_count):
            f.write(data)
        dur = max(0.001, time.perf_counter() - t0)
    return int(BENCHMARK_FILE_BYTES / dur)


def run_write_benchmark(target_dir: Path) -> int:
    """Measure disk write speed in target_dir by writing a temporary file.

    Returns speed in bytes/sec. Fallback to 80 MB/s for network, 50 MB/s for local on error.
    """
    from config import is_test_mode
    if is_test_mode():
        return NETWORK_SPEED_FALLBACK_BPS
    is_net = target_dir.drive.startswith("\\\\") or target_dir.as_posix().startswith("//")
    fallback = NETWORK_SPEED_FALLBACK_BPS if is_net else LOCAL_SPEED_FALLBACK_BPS
    test_file = target_dir / f".remos_speedtest_{int(time.time())}"
    logger.debug('{"event":"benchmark_start","path":"%s"}', test_file)
    try:
        speed = _do_write_benchmark(test_file)
        test_file.unlink(missing_ok=True)
        logger.info('{"event":"benchmark_success","path":"%s","speed":%d}', test_file, speed)
        return speed
    except OSError as exc:
        logger.warning('{"event":"benchmark_failed","path":"%s","error":"%s"}', test_file, exc)
        return fallback


def estimate_copy_seconds_for_files(
    files: list[MergedFile], write_speed_bps: int,
    network_speed_bps: Optional[int] = None,
) -> int:
    """Calculate total estimated copy time by summing individual file durations.

    Network files are limited by the minimum of local write and network speeds.
    """
    total_seconds = 0.0
    net_speed = network_speed_bps or NETWORK_SPEED_FALLBACK_BPS
    write_cap = min(write_speed_bps, WRITE_SPEED_CAP_BPS)
    for mf in files:
        is_net = (
            mf.source_path.drive.startswith("\\\\")
            or mf.source_path.as_posix().startswith("//")
        )
        speed = min(write_cap, net_speed) if is_net else write_cap
        total_seconds += mf.size_bytes / max(1.0, speed)
    return max(1, int(total_seconds))
