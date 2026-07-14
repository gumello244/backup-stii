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
    _determine_summary,
    is_raiz_file,
    filter_files_by_selection,
    MergedFile,
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

    def test_index_source_raiz(self) -> None:
        """Verify _index_source correctly maps and indexes the RAIZ folder parallel to USUARIOS."""
        fs = {
            "source/USUARIOS/14029/Desktop/file1.txt": {"size": 100, "mtime": 10.0},
            "source/RAIZ/rootfile.exe": {"size": 500, "mtime": 50.0},
        }
        fs["source/RAIZ"] = {"is_dir": True}
        fs["source/USUARIOS"] = {"is_dir": True}
        fs["source/USUARIOS/14029"] = {"is_dir": True}
        fs["source/USUARIOS/14029/Desktop"] = {"is_dir": True}

        source_path = FakePath("source/USUARIOS/14029", fs)
        source = BackupSource(
            path=source_path,  # type: ignore
            origin="local",
            machine_id="PMC_1",
            total_bytes=600,
            folder_list=["Desktop", "RAIZ"]
        )

        idx = _index_source(source)
        self.assertEqual(len(idx), 2)
        self.assertIn(("Desktop", "file1.txt"), idx)
        self.assertIn(("RAIZ", "rootfile.exe"), idx)

        raiz_entry = idx[("RAIZ", "rootfile.exe")]
        self.assertEqual(raiz_entry.size_bytes, 500)
        self.assertEqual(raiz_entry.modified_time, 50.0)

    def test_merge_sources_parallel(self) -> None:
        """Verify merge_sources works with parallel processing of multiple sources in normal mode."""
        fs1 = {"s1/Desktop/file1.txt": {"size": 10, "mtime": 1.0}}
        fs2 = {"s2/Desktop/file2.txt": {"size": 20, "mtime": 2.0}}
        s1 = BackupSource(
            path=FakePath("s1", fs1),  # type: ignore
            origin="local",
            machine_id="PMC_1",
            total_bytes=10,
            folder_list=["Desktop"]
        )
        s2 = BackupSource(
            path=FakePath("s2", fs2),  # type: ignore
            origin="network",
            machine_id="PMC_1",
            total_bytes=20,
            folder_list=["Desktop"]
        )
        res = merge_sources([s1, s2], admin_mode=False)
        self.assertEqual(len(res.files), 1)
        self.assertEqual(res.total_bytes, 20)
        self.assertEqual(res.source_summary, "Rede")

    def test_merge_sources_admin_mode(self) -> None:
        """Verify merge_sources merges multiple sources when admin_mode is True."""
        fs1 = {"s1/Desktop/file1.txt": {"size": 10, "mtime": 1.0}}
        fs2 = {"s2/Desktop/file2.txt": {"size": 20, "mtime": 2.0}}
        s1 = BackupSource(
            path=FakePath("s1", fs1),  # type: ignore
            origin="local",
            machine_id="PMC_1",
            total_bytes=10,
            folder_list=["Desktop"]
        )
        s2 = BackupSource(
            path=FakePath("s2", fs2),  # type: ignore
            origin="network",
            machine_id="PMC_1",
            total_bytes=20,
            folder_list=["Desktop"]
        )
        res = merge_sources([s1, s2], admin_mode=True)
        self.assertEqual(len(res.files), 2)
        self.assertEqual(res.total_bytes, 30)
        self.assertEqual(res.source_summary, "Mesclado (rede + local)")


class TestIsRaizFile(unittest.TestCase):
    """is_raiz_file() distinguishes RAIZ-sourced files from profile files —
    used by ConfirmView and MainWindow to group/filter admin restore selections."""

    def test_true_for_file_under_raiz_folder(self) -> None:
        mf = MergedFile(
            source_path=Path("C:/OS_5/RAIZ/Documentos/nota.txt"),
            dest_folder="Documentos", relative_name="Documentos/nota.txt",
            size_bytes=1, modified_time=1.0,
        )
        self.assertTrue(is_raiz_file(mf))

    def test_false_for_file_under_user_profile(self) -> None:
        mf = MergedFile(
            source_path=Path("C:/OS_5/USUARIOS/joao/Desktop/nota.txt"),
            dest_folder="Desktop", relative_name="nota.txt",
            size_bytes=1, modified_time=1.0, target_profile="joao",
        )
        self.assertFalse(is_raiz_file(mf))


class TestFilterFilesBySelection(unittest.TestCase):
    """filter_files_by_selection() maps ConfirmView's checkbox keys —
    plain folder, "profile::folder", and "raiz::subfolder" — back onto
    the MergedFile list that should actually be copied."""

    def _profile_file(self, profile: str, folder: str) -> MergedFile:
        return MergedFile(
            source_path=Path(f"C:/OS_5/USUARIOS/{profile}/{folder}/f.txt"),
            dest_folder=folder, relative_name="f.txt",
            size_bytes=1, modified_time=1.0, target_profile=profile,
        )

    def _raiz_file(self, sub_folder: str) -> MergedFile:
        return MergedFile(
            source_path=Path(f"C:/OS_5/RAIZ/{sub_folder}/f.txt"),
            dest_folder=sub_folder, relative_name=f"{sub_folder}/f.txt",
            size_bytes=1, modified_time=1.0,
        )

    def test_plain_folder_key_matches_unscoped_file(self) -> None:
        mf = MergedFile(
            source_path=Path("C:/Fake/Desktop/f.txt"), dest_folder="Desktop",
            relative_name="f.txt", size_bytes=1, modified_time=1.0,
        )
        self.assertEqual(filter_files_by_selection([mf], ["Desktop"]), [mf])
        self.assertEqual(filter_files_by_selection([mf], ["Downloads"]), [])

    def test_profile_scoped_key_matches_only_that_profile(self) -> None:
        joao = self._profile_file("joao", "Desktop")
        maria = self._profile_file("maria", "Desktop")
        result = filter_files_by_selection([joao, maria], ["joao::Desktop"])
        self.assertEqual(result, [joao])

    def test_raiz_scoped_key_matches_raiz_subfolder(self) -> None:
        raiz_docs = self._raiz_file("Documentos")
        raiz_other = self._raiz_file("Financeiro")
        result = filter_files_by_selection([raiz_docs, raiz_other], ["raiz::Documentos"])
        self.assertEqual(result, [raiz_docs])

    def test_unselected_keys_are_excluded(self) -> None:
        joao = self._profile_file("joao", "Desktop")
        self.assertEqual(filter_files_by_selection([joao], []), [])


