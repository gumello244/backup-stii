from __future__ import annotations

"""Unit tests for copy_benchmark.py — write-speed measurement and estimation."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import NETWORK_SPEED_FALLBACK_BPS, LOCAL_SPEED_FALLBACK_BPS
from services.backup_merger import MergedFile
from services.copy_benchmark import run_write_benchmark, estimate_copy_seconds_for_files


class TestCopyBenchmark(unittest.TestCase):
    """Test suite for copy_benchmark.py."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.desktop = Path(self.temp_dir.name) / "Desktop"
        self.desktop.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_run_write_benchmark(self) -> None:
        """Test write speed benchmark and its fallbacks."""
        with patch("config.is_test_mode", return_value=True):
            speed = run_write_benchmark(self.desktop)
            self.assertEqual(speed, NETWORK_SPEED_FALLBACK_BPS)
        with patch("config.is_test_mode", return_value=False):
            speed_real = run_write_benchmark(self.desktop)
            self.assertGreater(speed_real, 0)
            err_speed = run_write_benchmark(Path("nonexistent_drive:/invalid_folder"))
            self.assertEqual(err_speed, LOCAL_SPEED_FALLBACK_BPS)
            net_err_speed = run_write_benchmark(Path("\\\\nonexistent_server\\share"))
            self.assertEqual(net_err_speed, NETWORK_SPEED_FALLBACK_BPS)

    def test_estimate_copy_seconds_for_files(self) -> None:
        """Test file list duration estimation with local vs network rules."""
        local_file = MergedFile(
            source_path=Path("C:/local/f1.txt"), dest_folder="Desktop",
            relative_name="f1.txt", size_bytes=100 * 1024 * 1024, modified_time=0.0
        )
        net_file = MergedFile(
            source_path=Path("\\\\server\\share\\f2.txt"), dest_folder="Desktop",
            relative_name="f2.txt", size_bytes=100 * 1024 * 1024, modified_time=0.0
        )
        est_local = estimate_copy_seconds_for_files([local_file], 50 * 1024 * 1024)
        self.assertEqual(est_local, 2)
        est_net = estimate_copy_seconds_for_files([net_file], 100 * 1024 * 1024)
        self.assertEqual(est_net, 1)
        est_both = estimate_copy_seconds_for_files(
            [local_file, net_file], 50 * 1024 * 1024, 10 * 1024 * 1024
        )
        self.assertEqual(est_both, 12)


if __name__ == "__main__":
    unittest.main()
