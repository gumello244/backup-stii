from __future__ import annotations

"""Unit tests for backup_simulator.py copy simulator."""
import unittest
import unittest.mock
from pathlib import Path
from threading import Event

from services.backup_merger import MergedFile
from services.backup_simulator import do_simulated_copy


class TestBackupSimulator(unittest.TestCase):
    """Test suite for the test-mode simulated copier."""

    def test_simulated_copy_success(self) -> None:
        """Verify normal simulated file copy runs to completion."""
        files = [
            MergedFile(
                source_path=Path("src/f1.txt"),
                dest_folder="Desktop",
                relative_name="f1.txt",
                size_bytes=100,
                modified_time=0.0,
            )
        ]
        progress_calls = []

        def progress_cb(copied: int, total: int, filename: str) -> None:
            progress_calls.append((copied, total, filename))

        cancel_event = Event()
        # Temporarily mock sleep to make simulation instantaneous in tests
        with unittest.mock.patch("time.sleep", return_value=None):
            result = do_simulated_copy(files, progress_cb, cancel_event)

        self.assertTrue(result.success)
        self.assertEqual(result.files_copied, 1)
        self.assertEqual(result.bytes_copied, 100)
        self.assertFalse(result.cancelled)
        self.assertGreater(len(progress_calls), 0)

    def test_simulated_copy_cancelled(self) -> None:
        """Verify simulation stops immediately if cancel_event is set."""
        files = [
            MergedFile(
                source_path=Path("src/f1.txt"),
                dest_folder="Desktop",
                relative_name="f1.txt",
                size_bytes=100,
                modified_time=0.0,
            )
        ]
        progress_calls = []

        def progress_cb(copied: int, total: int, filename: str) -> None:
            progress_calls.append((copied, total, filename))

        cancel_event = Event()
        cancel_event.set()

        result = do_simulated_copy(files, progress_cb, cancel_event)
        self.assertFalse(result.success)
        self.assertEqual(result.files_copied, 0)
        self.assertTrue(result.cancelled)
        self.assertEqual(len(progress_calls), 0)

    def test_simulated_copy_avatar_skipped(self) -> None:
        """Verify avatar.png is cataloged as a conflict/skipped file."""
        files = [
            MergedFile(
                source_path=Path("src/avatar.png"),
                dest_folder="Pictures",
                relative_name="avatar.png",
                size_bytes=200,
                modified_time=0.0,
            )
        ]
        progress_calls = []

        def progress_cb(copied: int, total: int, filename: str) -> None:
            progress_calls.append((copied, total, filename))

        cancel_event = Event()
        with unittest.mock.patch("time.sleep", return_value=None):
            result = do_simulated_copy(files, progress_cb, cancel_event)

        self.assertTrue(result.success)
        self.assertEqual(result.files_copied, 0)
        self.assertEqual(len(result.skipped_files), 1)
        self.assertIn("já existia no destino", result.skipped_files[0].reason)

    def test_simulated_copy_treinamento_failed(self) -> None:
        """Verify treinamento.mp4 is cataloged as a copy failure."""
        files = [
            MergedFile(
                source_path=Path("src/treinamento.mp4"),
                dest_folder="Videos",
                relative_name="treinamento.mp4",
                size_bytes=300,
                modified_time=0.0,
            )
        ]
        progress_calls = []

        def progress_cb(copied: int, total: int, filename: str) -> None:
            progress_calls.append((copied, total, filename))

        cancel_event = Event()
        with unittest.mock.patch("time.sleep", return_value=None):
            result = do_simulated_copy(files, progress_cb, cancel_event)

        self.assertTrue(result.success)
        self.assertEqual(result.files_copied, 0)
        self.assertEqual(len(result.failed_files), 1)
        self.assertIn("Erro de E/S simulado", result.failed_files[0].reason)

    def test_simulated_copy_skips_identical(self) -> None:
        """Verify that simulation skips copy if destination file exists and is identical."""
        files = [
            MergedFile(
                source_path=Path("src/f1.txt"),
                dest_folder="Desktop",
                relative_name="f1.txt",
                size_bytes=100,
                modified_time=0.0,
            )
        ]
        from unittest.mock import MagicMock
        mock_dest = MagicMock(spec=Path)
        mock_dest.exists.return_value = True

        with unittest.mock.patch("services.backup_simulator.resolve_dest_path", return_value=mock_dest), \
             unittest.mock.patch("services.backup_copier._is_identical", return_value=True), \
             unittest.mock.patch("time.sleep", return_value=None):
            result = do_simulated_copy(files, lambda x, y, z: None, Event())

        self.assertTrue(result.success)
        self.assertEqual(result.files_copied, 0)
        self.assertEqual(result.bytes_copied, 0)


if __name__ == "__main__":
    unittest.main()
