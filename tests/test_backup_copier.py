from __future__ import annotations

"""Unit tests for backup_copier.py using unittest, tempfile, and patches."""
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import os
import time
from threading import Event

from config import CopyRetryConfig
from services.backup_merger import MergedFile
from services.backup_copier import (
    resolve_dest_path,
    copy_merged_files,
    copy_skipped_to_desktop,
    PROFILE_FOLDER_MAP,
    SkippedFile,
    _delete_source_file,
    _copy_via_helper_with_retry,
    _needs_elevated_write,
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
        """f1 succeeds immediately; f2 fails once then succeeds on retry; f3
        always fails and survives past the end-of-run retry pass too.

        The copy loop now runs files concurrently, so the mock is keyed by
        source path (not a shared ordered call sequence) — call order across
        files is no longer deterministic, but each file's own outcome is.
        """
        import threading as _threading
        call_counts: dict[str, int] = {}
        counts_lock = _threading.Lock()

        def fake_copy(source: object, dest: object, chunk_cb: object = None, cancel_event: object = None) -> int:
            name = Path(source).name
            with counts_lock:
                call_counts[name] = call_counts.get(name, 0) + 1
                attempt = call_counts[name]
            if name == "f1.txt":
                return 100
            if name == "f2.txt":
                if attempt == 1:
                    raise OSError("Network timeout")
                return 200
            raise OSError("Network down")  # f3.txt: always fails

        mock_copy.side_effect = fake_copy

        mfiles = [
            MergedFile(source_path=Path("s1/f1.txt"), dest_folder="Desktop", relative_name="f1.txt", size_bytes=100, modified_time=0.0),
            MergedFile(source_path=Path("s2/f2.txt"), dest_folder="Desktop", relative_name="f2.txt", size_bytes=200, modified_time=0.0),
            MergedFile(source_path=Path("s3/f3.txt"), dest_folder="Desktop", relative_name="f3.txt", size_bytes=300, modified_time=0.0),
        ]

        cancel_event = Event()
        retry_cfg = CopyRetryConfig(max_retries=1, backoff_base=0.001, consecutive_fail_limit=3)

        with patch.dict(PROFILE_FOLDER_MAP, self.env.get_profile_map(), clear=True):
            res = copy_merged_files(mfiles, lambda *a: None, cancel_event, retry_cfg)

        self.assertTrue(res.success)
        self.assertEqual(res.files_copied, 2)
        self.assertEqual(len(res.failed_files), 1)
        self.assertEqual(res.failed_files[0].source, Path("s3/f3.txt"))

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
        # 20000 bytes fits in a single 1 MB chunk read.
        self.assertEqual(chunk_sizes, [20000])

    def test_copy_merged_files_cancellation(self) -> None:
        """Test that copy_merged_files does not copy anything once cancel_event is set."""
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
        cancel_event.set()  # simulate cancel already requested when the copy starts
        retry_cfg = CopyRetryConfig(max_retries=0, backoff_base=0.01, consecutive_fail_limit=1)

        with patch.dict(PROFILE_FOLDER_MAP, self.env.get_profile_map(), clear=True):
            res = copy_merged_files(mfiles, lambda *a: None, cancel_event, retry_cfg)

        self.assertFalse(res.success)
        self.assertTrue(res.cancelled)

        dest_file = self.env.desktop / "dst_cancel.txt"
        self.assertFalse(dest_file.exists())

    def test_copy_single_file_stops_and_cleans_up_on_cancel(self) -> None:
        """_copy_single_file must stop mid-write and remove the partial file
        once cancel_event is set during the copy (checked once per chunk)."""
        from services.backup_copier import _copy_single_file, COPY_CHUNK_BYTES

        src_file = self.env.source_dir / "src_cancel_midcopy.txt"
        src_file.write_bytes(b"A" * (COPY_CHUNK_BYTES * 3))
        dest_file = self.env.desktop / "dst_cancel_midcopy.txt"

        cancel_event = Event()

        def chunk_cb(n: int) -> None:
            cancel_event.set()  # cancel right after the first chunk is written

        with self.assertRaises(OSError):
            _copy_single_file(src_file, dest_file, chunk_cb, cancel_event)

        self.assertFalse(dest_file.exists())

    @patch("services.backup_copier.ctypes")
    def test_copy_merged_files_cut_mode_moves_file_and_deletes_source(self, mock_ctypes: object) -> None:
        """cut_mode=True must leave the destination copy in place and remove the source."""
        src_file = self.env.source_dir / "move_me.txt"
        src_file.write_text("moved content", encoding="utf-8")

        mfiles = [
            MergedFile(
                source_path=src_file, dest_folder="Desktop", relative_name="move_me.txt",
                size_bytes=src_file.stat().st_size, modified_time=src_file.stat().st_mtime,
            )
        ]
        cancel_event = Event()
        retry_cfg = CopyRetryConfig(max_retries=1, backoff_base=0.01, consecutive_fail_limit=3)

        with patch.dict(PROFILE_FOLDER_MAP, self.env.get_profile_map(), clear=True):
            res = copy_merged_files(mfiles, lambda *a: None, cancel_event, retry_cfg, cut_mode=True)

        self.assertTrue(res.success)
        self.assertEqual(res.files_copied, 1)
        dest_file = self.env.desktop / "move_me.txt"
        self.assertTrue(dest_file.exists())
        self.assertEqual(dest_file.read_text(encoding="utf-8"), "moved content")
        self.assertFalse(src_file.exists())

    @patch("services.backup_copier.ctypes")
    def test_copy_merged_files_cut_mode_deletes_source_when_dest_already_identical(self, mock_ctypes: object) -> None:
        """An already-identical destination is skipped, but the source must still be removed."""
        src_file = self.env.source_dir / "identical.txt"
        src_file.write_text("same content", encoding="utf-8")
        dest_file = self.env.desktop / "identical.txt"
        dest_file.write_text("same content", encoding="utf-8")
        t_now = time.time()
        os.utime(src_file, (t_now, t_now))
        os.utime(dest_file, (t_now, t_now))

        mfiles = [
            MergedFile(
                source_path=src_file, dest_folder="Desktop", relative_name="identical.txt",
                size_bytes=src_file.stat().st_size, modified_time=src_file.stat().st_mtime,
            )
        ]
        cancel_event = Event()
        retry_cfg = CopyRetryConfig(max_retries=1, backoff_base=0.01, consecutive_fail_limit=3)

        with patch.dict(PROFILE_FOLDER_MAP, self.env.get_profile_map(), clear=True):
            res = copy_merged_files(mfiles, lambda *a: None, cancel_event, retry_cfg, cut_mode=True)

        self.assertTrue(res.success)
        self.assertEqual(len(res.skipped_files), 0)
        self.assertEqual(dest_file.read_text(encoding="utf-8"), "same content")
        self.assertFalse(src_file.exists())

    @patch("services.backup_copier.ctypes")
    def test_copy_merged_files_cut_mode_keeps_source_on_conflict(self, mock_ctypes: object) -> None:
        """A genuine conflict (different content) must not delete the source file."""
        src_file = self.env.source_dir / "conflict.txt"
        src_file.write_text("new content", encoding="utf-8")
        dest_file = self.env.desktop / "conflict.txt"
        dest_file.write_text("old different content", encoding="utf-8")

        mfiles = [
            MergedFile(
                source_path=src_file, dest_folder="Desktop", relative_name="conflict.txt",
                size_bytes=src_file.stat().st_size, modified_time=src_file.stat().st_mtime,
            )
        ]
        cancel_event = Event()
        retry_cfg = CopyRetryConfig(max_retries=1, backoff_base=0.01, consecutive_fail_limit=3)

        with patch.dict(PROFILE_FOLDER_MAP, self.env.get_profile_map(), clear=True):
            res = copy_merged_files(mfiles, lambda *a: None, cancel_event, retry_cfg, cut_mode=True)

        self.assertEqual(len(res.skipped_files), 1)
        self.assertTrue(src_file.exists())
        self.assertEqual(dest_file.read_text(encoding="utf-8"), "old different content")

    def test_delete_source_file_clears_readonly_and_removes(self) -> None:
        """_delete_source_file must succeed even on a read-only source file."""
        target = self.env.source_dir / "readonly.txt"
        target.write_text("data", encoding="utf-8")
        target.chmod(0o444)

        _delete_source_file(target)

        self.assertFalse(target.exists())

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

    def test_copy_merged_files_abort_accounts_for_every_file(self) -> None:
        """An early abort (consecutive_fail_limit reached) must not silently
        drop files — every file ends up counted as copied or failed, even
        the ones the thread pool never got around to starting.

        The copy loop now runs several files concurrently (see COPY_WORKERS
        in backup_copier.py), so exactly *which* file ends up "not attempted"
        is no longer deterministic — this asserts the invariant the fix is
        actually about instead of a specific split.
        """
        from services.backup_copier import COPY_WORKERS
        total_files = COPY_WORKERS + 8
        missing_file = self.env.source_dir / "missing.txt"  # never created -> always fails
        mfiles = [
            MergedFile(source_path=missing_file, dest_folder="Desktop", relative_name="missing.txt",
                       size_bytes=1, modified_time=0.0)
        ]
        for i in range(total_files - 1):
            f = self.env.source_dir / f"later_{i}.txt"
            f.write_text("later", encoding="utf-8")
            mfiles.append(MergedFile(
                source_path=f, dest_folder="Desktop", relative_name=f"later_{i}.txt",
                size_bytes=5, modified_time=0.0,
            ))

        cancel_event = Event()
        retry_cfg = CopyRetryConfig(max_retries=0, backoff_base=0.001, consecutive_fail_limit=1)

        with patch.dict(PROFILE_FOLDER_MAP, self.env.get_profile_map(), clear=True):
            res = copy_merged_files(mfiles, lambda *a: None, cancel_event, retry_cfg)

        self.assertFalse(res.success)
        self.assertEqual(res.files_copied + len(res.failed_files), total_files)
        self.assertGreaterEqual(len(res.failed_files), 1)


class TestNeedsElevatedWrite(unittest.TestCase):
    """Tests for _needs_elevated_write's routing decision."""

    def test_false_when_already_admin(self) -> None:
        """An elevated process can write anywhere — never needs the helper."""
        with patch("services.elevation.is_admin", return_value=True):
            self.assertFalse(_needs_elevated_write(Path("C:\\Users\\someone_else\\Desktop\\f.txt")))

    def test_false_for_current_users_own_profile(self) -> None:
        with patch("services.elevation.is_admin", return_value=False), \
             patch("services.backup_copier.Path.home", return_value=Path("C:\\Users\\me")):
            dest = Path("C:\\Users\\me\\Desktop\\f.txt")
            self.assertFalse(_needs_elevated_write(dest))

    def test_true_for_another_users_profile(self) -> None:
        with patch("services.elevation.is_admin", return_value=False), \
             patch("services.backup_copier.Path.home", return_value=Path("C:\\Users\\me")):
            dest = Path("C:\\Users\\someone_else\\Desktop\\f.txt")
            self.assertTrue(_needs_elevated_write(dest))

    def test_false_for_paths_outside_users_root(self) -> None:
        """RAIZ-scope files resolve under C:\\, not C:\\Users — never elevated."""
        with patch("services.elevation.is_admin", return_value=False):
            self.assertFalse(_needs_elevated_write(Path("C:\\ProgramData\\f.txt")))


class TestCopyViaHelperWithRetry(unittest.TestCase):
    """Tests for _copy_via_helper_with_retry's backoff behavior."""

    def test_recovers_after_transient_failure(self) -> None:
        """A transient elevated-helper failure (e.g. the pipe being briefly
        busy) should be retried and can still succeed within max_retries."""
        calls: list[int] = []

        def fake_copy_via_helper(source: Path, dest: Path, cut_mode: bool = False) -> tuple[bool, str]:
            calls.append(1)
            if len(calls) < 3:
                return False, "Falha de comunicação com o processo elevado: pipe busy"
            return True, ""

        retry_cfg = CopyRetryConfig(max_retries=3, backoff_base=0.001, consecutive_fail_limit=3)
        with patch("services.elevation.copy_via_helper", side_effect=fake_copy_via_helper):
            ok, err = _copy_via_helper_with_retry(Path("C:/fake/src.txt"), Path("C:/fake/dst.txt"), retry_cfg)

        self.assertTrue(ok)
        self.assertEqual(err, "")
        self.assertEqual(len(calls), 3)

    def test_gives_up_after_max_retries(self) -> None:
        """A persistent elevated-helper failure should be reported once
        max_retries is exhausted rather than retried forever."""
        retry_cfg = CopyRetryConfig(max_retries=2, backoff_base=0.001, consecutive_fail_limit=3)
        with patch("services.elevation.copy_via_helper", return_value=(False, "erro persistente")) as mock_copy:
            ok, err = _copy_via_helper_with_retry(Path("C:/fake/src.txt"), Path("C:/fake/dst.txt"), retry_cfg)

        self.assertFalse(ok)
        self.assertEqual(err, "erro persistente")
        self.assertEqual(mock_copy.call_count, 3)
