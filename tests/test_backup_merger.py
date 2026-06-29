from __future__ import annotations

"""Unit tests for backup_merger.py using unittest and FakePath."""
import unittest
from unittest.mock import patch
from pathlib import Path
from services.backup_discovery import BackupSource
from services.backup_merger import (
    merge_sources,
    _index_source,
    _merge_indexes,
    group_by_folder,
    _determine_summary
)
from tests.test_backup_discovery import FakePath


class TestBackupMerger(unittest.TestCase):
    """Test suite for backup_merger.py."""

    def setUp(self) -> None:
        self.patcher = patch("config.is_test_mode", return_value=False)
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()

    def test_index_source(self) -> None:
        fs = {
            "source/Desktop/file1.txt": {"size": 100, "mtime": 10.0},
            "source/Desktop/sub/file2.txt": {"size": 200, "mtime": 20.0},
            "source/Documents/doc.pdf": {"size": 500, "mtime": 30.0},
        }
        # FakePath instances can be used as paths
        source_path = FakePath("source", fs)
        source = BackupSource(
            path=source_path,  # type: ignore
            origin="local",
            machine_id="PMC_1",
            total_bytes=800,
            folder_list=["Desktop", "Documents"]
        )

        idx = _index_source(source)
        self.assertEqual(len(idx), 3)
        self.assertIn(("Desktop", "file1.txt"), idx)
        self.assertIn(("Desktop", "sub/file2.txt"), idx)
        self.assertIn(("Documents", "doc.pdf"), idx)

        entry1 = idx[("Desktop", "file1.txt")]
        self.assertEqual(entry1.size_bytes, 100)
        self.assertEqual(entry1.modified_time, 10.0)

    def test_merge_indexes_prefers_newest(self) -> None:
        fs1 = {
            "s1/Desktop/file.txt": {"size": 100, "mtime": 10.0},
            "s1/Desktop/only_in_s1.txt": {"size": 50, "mtime": 5.0},
        }
        fs2 = {
            "s2/Desktop/file.txt": {"size": 150, "mtime": 20.0},  # Newest version
            "s2/Desktop/only_in_s2.txt": {"size": 250, "mtime": 8.0},
        }

        s1_path = FakePath("s1", fs1)
        s1 = BackupSource(
            path=s1_path,  # type: ignore
            origin="local",
            machine_id="PMC_1",
            total_bytes=150,
            folder_list=["Desktop"]
        )

        s2_path = FakePath("s2", fs2)
        s2 = BackupSource(
            path=s2_path,  # type: ignore
            origin="network",
            machine_id="PMC_1",
            total_bytes=400,
            folder_list=["Desktop"]
        )

        idx1 = _index_source(s1)
        idx2 = _index_source(s2)

        merged = _merge_indexes(idx1, idx2)
        self.assertEqual(len(merged), 3)

        # "file.txt" exists in both, version from s2 should be kept since mtime is higher
        file_entry = merged[("Desktop", "file.txt")]
        self.assertEqual(file_entry.size_bytes, 150)
        self.assertEqual(file_entry.modified_time, 20.0)
        self.assertTrue(str(file_entry.source_path).startswith("s2"))

        # Exclusive files are kept
        self.assertIn(("Desktop", "only_in_s1.txt"), merged)
        self.assertIn(("Desktop", "only_in_s2.txt"), merged)

    def test_group_by_folder(self) -> None:
        fs = {
            "source/Desktop/file1.txt": {"size": 100, "mtime": 10.0},
            "source/Desktop/file2.txt": {"size": 200, "mtime": 20.0},
            "source/Documents/doc.pdf": {"size": 500, "mtime": 30.0},
        }
        source_path = FakePath("source", fs)
        source = BackupSource(
            path=source_path,  # type: ignore
            origin="local",
            machine_id="PMC_1",
            total_bytes=800,
            folder_list=["Desktop", "Documents"]
        )
        merged_set = merge_sources([source])

        groups = group_by_folder(merged_set.files)
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups["Desktop"].file_count, 2)
        self.assertEqual(groups["Desktop"].total_bytes, 300)
        self.assertEqual(groups["Documents"].file_count, 1)
        self.assertEqual(groups["Documents"].total_bytes, 500)

    def test_determine_summary(self) -> None:
        s_network = BackupSource(Path("net"), "network", "PMC_1", 100)
        s_local = BackupSource(Path("loc"), "local", "PMC_1", 200)

        self.assertEqual(_determine_summary([s_network]), "Rede")
        self.assertEqual(_determine_summary([s_local]), "Local")
        self.assertEqual(_determine_summary([s_network, s_local]), "Mesclado (rede + local)")

    def test_merge_sources_empty(self) -> None:
        merged = merge_sources([])
        self.assertEqual(len(merged.files), 0)
        self.assertEqual(merged.total_bytes, 0)
        self.assertEqual(merged.source_summary, "Nenhuma")
