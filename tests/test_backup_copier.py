from __future__ import annotations

"""Unit tests for backup_copier.py using unittest, tempfile, and patches."""
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import os
import time
from threading import Event

from config import (
    CopyRetryConfig,
    NETWORK_SPEED_FALLBACK_BPS,
    LOCAL_SPEED_FALLBACK_BPS,
)
from services.backup_merger import MergedFile
from services.backup_copier import (
    resolve_dest_path,
    copy_merged_files,
    copy_skipped_to_desktop,
    PROFILE_FOLDER_MAP,
    SkippedFile
)


class FakeExecutionState:
    """Named fake to trace SetThreadExecutionState calls."""
    def __init__(self) -> None:
        self.calls: list[int] = []

    def __call__(self, state: int) -> None:
        self.calls.append(state)


class CopyTestEnvironment:
    """Named fake environment for copying tests, scopes files to a temp directory."""
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.source_dir = base_dir / "source_backup"
        self.dest_profile = base_dir / "user_profile"

        self.source_dir.mkdir()
        self.dest_profile.mkdir()

        self.desktop = self.dest_profile / "Desktop"
        self.documents = self.dest_profile / "Documents"

        self.desktop.mkdir()
        self.documents.mkdir()

    def get_profile_map(self) -> dict[str, Path]:
        """Return fake profile folder mappings."""
        return {
            "Desktop": self.desktop,
            "Documents": self.documents,
        }


class TestBackupCopier(unittest.TestCase):
    """Test suite for backup_copier.py."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env = CopyTestEnvironment(Path(self.temp_dir.name))
        self.patcher = patch("config.is_test_mode", return_value=False)
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()
        self.temp_dir.cleanup()



    def test_resolve_dest_path(self) -> None:
        profile_map = self.env.get_profile_map()
        with patch.dict(PROFILE_FOLDER_MAP, profile_map, clear=True):
            resolved = resolve_dest_path("Desktop", "test/file.txt")
            expected = self.env.desktop / "test" / "file.txt"
            self.assertEqual(resolved.resolve(), expected.resolve())

    @patch("services.backup_copier.ctypes")
    def test_copy_merged_files_success(self, mock_ctypes: object) -> None:
        fake_state = FakeExecutionState()
        setattr(mock_ctypes.windll.kernel32, "SetThreadExecutionState", fake_state)

        # Setup source files
        src_file1 = self.env.source_dir / "file1.txt"
        src_file1.write_text("Hello from file 1", encoding="utf-8")

        src_file2 = self.env.source_dir / "file2.txt"
        src_file2.write_text("Hello from file 2", encoding="utf-8")

        mfiles = [
            MergedFile(
                source_path=src_file1,
                dest_folder="Desktop",
                relative_name="file1.txt",
                size_bytes=src_file1.stat().st_size,
                modified_time=src_file1.stat().st_mtime
            ),
            MergedFile(
                source_path=src_file2,
                dest_folder="Documents",
                relative_name="sub/file2.txt",
                size_bytes=src_file2.stat().st_size,
                modified_time=src_file2.stat().st_mtime
            )
        ]

        progress_calls = []
        def progress_cb(copied: int, total: int, filename: str) -> None:
            progress_calls.append((copied, total, filename))

        cancel_event = Event()
        retry_cfg = CopyRetryConfig(max_retries=1, backoff_base=0.01, consecutive_fail_limit=3)

        with patch.dict(PROFILE_FOLDER_MAP, self.env.get_profile_map(), clear=True):
            res = copy_merged_files(mfiles, progress_cb, cancel_event, retry_cfg)

        self.assertTrue(res.success)
        self.assertEqual(res.files_copied, 2)
        self.assertEqual(len(res.skipped_files), 0)
        self.assertEqual(len(res.failed_files), 0)

        dest_file1 = self.env.desktop / "file1.txt"
        dest_file2 = self.env.documents / "sub/file2.txt"

        self.assertTrue(dest_file1.exists())
        self.assertEqual(dest_file1.read_text(encoding="utf-8"), "Hello from file 1")
        self.assertTrue(dest_file2.exists())
        self.assertEqual(dest_file2.read_text(encoding="utf-8"), "Hello from file 2")

        # Sleep prevention check (ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        self.assertIn(0x80000000 | 0x00000001, fake_state.calls)
        # Sleep release check (ES_CONTINUOUS)
        self.assertIn(0x80000000, fake_state.calls)

    @patch("services.backup_copier.ctypes")
    def test_copy_merged_files_skips_and_conflicts(self, mock_ctypes: object) -> None:
        src_identical = self.env.source_dir / "identical.txt"
        src_identical.write_text("Same content", encoding="utf-8")

        src_conflict = self.env.source_dir / "conflict.txt"
        src_conflict.write_text("New content", encoding="utf-8")

        dest_identical = self.env.desktop / "identical.txt"
        dest_identical.write_text("Same content", encoding="utf-8")

        t_now = time.time()
        os.utime(src_identical, (t_now, t_now))
        os.utime(dest_identical, (t_now, t_now))

        dest_conflict = self.env.desktop / "conflict.txt"
        dest_conflict.write_text("Old different content", encoding="utf-8")

        mfiles = [
            MergedFile(
                source_path=src_identical,
                dest_folder="Desktop",
                relative_name="identical.txt",
                size_bytes=src_identical.stat().st_size,
                modified_time=src_identical.stat().st_mtime
            ),
            MergedFile(
                source_path=src_conflict,
                dest_folder="Desktop",
                relative_name="conflict.txt",
                size_bytes=src_conflict.stat().st_size,
                modified_time=src_conflict.stat().st_mtime
            )
        ]

        def progress_cb(copied: int, total: int, filename: str) -> None:
            pass

        cancel_event = Event()
        retry_cfg = CopyRetryConfig(max_retries=1, backoff_base=0.01, consecutive_fail_limit=3)

        with patch.dict(PROFILE_FOLDER_MAP, self.env.get_profile_map(), clear=True):
            res = copy_merged_files(mfiles, progress_cb, cancel_event, retry_cfg)

        self.assertTrue(res.success)
        self.assertEqual(res.files_copied, 0)
        self.assertEqual(len(res.skipped_files), 1)
        self.assertEqual(res.skipped_files[0].reason, "já existia no destino com conteúdo diferente")

        # Conflict file was not overwritten
        self.assertEqual(dest_conflict.read_text(encoding="utf-8"), "Old different content")

    @patch("services.backup_copier.ctypes")
    def test_copy_skipped_to_desktop(self, mock_ctypes: object) -> None:
        src_file = self.env.source_dir / "conflict.txt"
        src_file.write_text("My conflict content", encoding="utf-8")

        dest_profile_file = self.env.documents / "sub/conflict.txt"

        skipped = [
            SkippedFile(source=src_file, dest=dest_profile_file, reason="conflito")
        ]

        with patch("services.backup_copier.Path.home", return_value=self.env.dest_profile):
            ok, target_root = copy_skipped_to_desktop(skipped)

        self.assertTrue(ok)
        from config import get_app_name
        expected_path = self.env.desktop / f"{get_app_name()} - Arquivos Pulados" / "Documents" / "sub" / "conflict.txt"
        self.assertTrue(expected_path.exists())
        self.assertEqual(expected_path.read_text(encoding="utf-8"), "My conflict content")

    @patch("services.backup_copier.ctypes")
    @patch("services.backup_copier._copy_single_file")
    def test_copy_merged_files_retry_and_fail(self, mock_copy: object, mock_ctypes: object) -> None:
        setattr(mock_copy, "side_effect", [
            100,
            OSError("Network timeout"),
            200,
            OSError("Network down"),
            OSError("Network down"),
            OSError("Network down"),
            OSError("Network down")
        ])

        mfiles = [
            MergedFile(source_path=Path("s1"), dest_folder="Desktop", relative_name="f1.txt", size_bytes=100, modified_time=0.0),
            MergedFile(source_path=Path("s2"), dest_folder="Desktop", relative_name="f2.txt", size_bytes=200, modified_time=0.0),
            MergedFile(source_path=Path("s3"), dest_folder="Desktop", relative_name="f3.txt", size_bytes=300, modified_time=0.0),
        ]

        def progress_cb(copied: int, total: int, filename: str) -> None:
            pass

        cancel_event = Event()
        retry_cfg = CopyRetryConfig(max_retries=1, backoff_base=0.001, consecutive_fail_limit=3)

        with patch.dict(PROFILE_FOLDER_MAP, self.env.get_profile_map(), clear=True):
            res = copy_merged_files(mfiles, progress_cb, cancel_event, retry_cfg)

        self.assertTrue(res.success)
        self.assertEqual(res.files_copied, 2)
        self.assertEqual(len(res.failed_files), 1)
        self.assertEqual(res.failed_files[0].source, Path("s3"))

    def test_file_progress_tracker_and_chunk_copy(self) -> None:
        """Test FileProgressTracker updates bytes and handles retry reset."""
        calls = []
        def progress_cb(copied: int, total: int, filename: str) -> None:
            calls.append((copied, total, filename))

        from services.backup_copier import FileProgressTracker
        tracker = FileProgressTracker(progress_cb, 1000, "test.txt", 100)
        tracker.on_chunk(50)
        self.assertEqual(tracker.file_written, 50)
        self.assertEqual(calls[-1], (150, 1000, "test.txt"))

        tracker.reset_attempt()
        self.assertEqual(tracker.file_written, 0)

        # Test actual chunk copying in _copy_single_file
        src_file = self.env.source_dir / "src_chunk.txt"
        dest_file = self.env.desktop / "dst_chunk.txt"
        src_file.write_bytes(b"A" * 20000)

        chunk_sizes = []
        def chunk_cb(n: int) -> None:
            chunk_sizes.append(n)

        from services.backup_copier import _copy_single_file
        written = _copy_single_file(src_file, dest_file, chunk_cb)
        self.assertEqual(written, 20000)
        self.assertEqual(chunk_sizes, [8192, 8192, 3616])

    def test_copy_merged_files_cancellation(self) -> None:
        """Test that copy_merged_files aborts immediately when cancel_event is set."""
        src_file = self.env.source_dir / "src_cancel.txt"
        src_file.write_bytes(b"A" * 50000)

        mfiles = [
            MergedFile(
                source_path=src_file,
                dest_folder="Desktop",
                relative_name="dst_cancel.txt",
                size_bytes=50000,
                modified_time=0.0
            )
        ]

        cancel_event = Event()
        progress_calls = []

        def progress_cb(copied: int, total: int, filename: str) -> None:
            progress_calls.append((copied, total, filename))
            cancel_event.set()

        retry_cfg = CopyRetryConfig(max_retries=0, backoff_base=0.01, consecutive_fail_limit=1)

        with patch.dict(PROFILE_FOLDER_MAP, self.env.get_profile_map(), clear=True):
            res = copy_merged_files(mfiles, progress_cb, cancel_event, retry_cfg)

        self.assertFalse(res.success)
        self.assertTrue(res.cancelled)

        dest_file = self.env.desktop / "dst_cancel.txt"
        self.assertFalse(dest_file.exists())

    def test_run_write_benchmark(self) -> None:
        """Test write speed benchmark and its fallbacks."""
        from services.backup_copier import run_write_benchmark
        with patch("config.is_test_mode", return_value=True):
            speed = run_write_benchmark(self.env.desktop)
            self.assertEqual(speed, NETWORK_SPEED_FALLBACK_BPS)
        with patch("config.is_test_mode", return_value=False):
            speed_real = run_write_benchmark(self.env.desktop)
            self.assertGreater(speed_real, 0)
            err_speed = run_write_benchmark(Path("nonexistent_drive:/invalid_folder"))
            self.assertEqual(err_speed, LOCAL_SPEED_FALLBACK_BPS)
            net_err_speed = run_write_benchmark(Path("\\\\nonexistent_server\\share"))
            self.assertEqual(net_err_speed, NETWORK_SPEED_FALLBACK_BPS)

    def test_estimate_copy_seconds_for_files(self) -> None:
        """Test file list duration estimation with local vs network rules."""
        from services.backup_copier import estimate_copy_seconds_for_files
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

    def test_copy_merged_files_records_duration(self) -> None:
        """Test that copy_merged_files records the elapsed duration in duration_seconds."""
        src_file = self.env.source_dir / "duration_test.txt"
        src_file.write_text("Test duration", encoding="utf-8")
        mfiles = [
            MergedFile(
                source_path=src_file,
                dest_folder="Desktop",
                relative_name="duration_test.txt",
                size_bytes=src_file.stat().st_size,
                modified_time=src_file.stat().st_mtime
            )
        ]
        cancel_event = Event()
        retry_cfg = CopyRetryConfig(max_retries=0, backoff_base=0.01, consecutive_fail_limit=1)
        with patch.dict(PROFILE_FOLDER_MAP, self.env.get_profile_map(), clear=True):
            res = copy_merged_files(mfiles, lambda x, y, z: None, cancel_event, retry_cfg)
        self.assertTrue(res.success)
        self.assertGreaterEqual(res.duration_seconds, 1)
