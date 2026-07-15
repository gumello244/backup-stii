from __future__ import annotations

"""Unit tests for backup_discovery.py using standard unittest library and FakePath."""
import unittest
from unittest.mock import patch
from pathlib import Path
from services.backup_discovery import (
    detect_user_login,
    extract_machine_id,
    _calculate_dir_stats,
    _list_subfolders,
    _extract_id_from_folder,
    scan_network_source,
    scan_local_sources,
    discover_all_sources,
    BackupSource
)


class FakeStat:
    """Fake stat result object."""
    def __init__(self, size: int = 0, mtime: float = 0.0) -> None:
        self.st_size = size
        self.st_mtime = mtime
        self.st_atime = 0.0


class FakePath:
    """A named fake for pathlib.Path to simulate filesystem structures without accessing disk."""
    def __init__(self, path_str: str, fs_structure: dict = None) -> None:
        self.path_str = str(path_str).replace("\\", "/")
        self.fs_structure = fs_structure if fs_structure is not None else {}

    def __truediv__(self, other: str) -> "FakePath":
        base = self.path_str
        sub = str(other).replace("\\", "/")
        res = base + ("" if base.endswith("/") else "/") + sub
        if res.startswith("//"):
            res = "//" + res[2:].replace("//", "/")
        else:
            res = res.replace("//", "/")
        return FakePath(res, self.fs_structure)

    @property
    def name(self) -> str:
        return self.path_str.split("/")[-1]

    @property
    def parts(self) -> tuple[str, ...]:
        return tuple(self.path_str.split("/"))

    @property
    def parent(self) -> "FakePath":
        parts = self.path_str.split("/")
        if len(parts) <= 1:
            return FakePath(".", self.fs_structure)
        return FakePath("/".join(parts[:-1]), self.fs_structure)


    def is_dir(self) -> bool:
        p = self.path_str
        if p in self.fs_structure:
            return self.fs_structure[p].get("is_dir", False)
        prefix = p if p.endswith("/") else p + "/"
        return any(k.startswith(prefix) for k in self.fs_structure.keys())

    def is_file(self) -> bool:
        p = self.path_str
        if p in self.fs_structure:
            return not self.fs_structure[p].get("is_dir", False)
        return False

    def exists(self) -> bool:
        return self.is_dir() or self.is_file()

    def iterdir(self) -> list["FakePath"]:
        p = self.path_str
        prefix = p if p.endswith("/") else p + "/"
        children = set()
        for k in self.fs_structure.keys():
            if k.startswith(prefix):
                sub = k[len(prefix):]
                parts = sub.split("/")
                children.add(parts[0])
        return [self / child for child in sorted(children)]

    def rglob(self, pattern: str) -> list["FakePath"]:
        p = self.path_str
        prefix = p if p.endswith("/") else p + "/"
        results = []
        for k in self.fs_structure.keys():
            if k.startswith(prefix):
                if not self.fs_structure[k].get("is_dir", False):
                    results.append(FakePath(k, self.fs_structure))
        return results

    def stat(self) -> FakeStat:
        p = self.path_str
        info = self.fs_structure.get(p, {})
        return FakeStat(size=info.get("size", 0), mtime=info.get("mtime", 0.0))

    def relative_to(self, other: object) -> "FakePath":
        o_str = getattr(other, "path_str", str(other)).replace("\\", "/")
        if self.path_str.startswith(o_str):
            rel = self.path_str[len(o_str):].lstrip("/")
            return FakePath(rel, self.fs_structure)
        raise ValueError(f"{self.path_str} does not start with {o_str}")

    def as_posix(self) -> str:
        return self.path_str

    def __str__(self) -> str:
        return self.path_str

    def __repr__(self) -> str:
        return f"FakePath({self.path_str})"


class TestBackupDiscovery(unittest.TestCase):
    """Test suite for backup_discovery.py."""

    def setUp(self) -> None:
        self.patcher = patch("config.is_test_mode", return_value=False)
        self.patcher.start()

    def tearDown(self) -> None:
        self.patcher.stop()

    def test_extract_machine_id_pmc(self) -> None:
        """Test machine id extraction with PMC_ prefix."""
        self.assertEqual(extract_machine_id("DESKTOP-PMC_600259"), "600259")
        self.assertEqual(extract_machine_id("WORKSTATION-PMC_12345"), "12345")

    def test_extract_machine_id_numeric(self) -> None:
        """Test machine id extraction with raw numbers."""
        self.assertEqual(extract_machine_id("25ABC1T123456"), "123456")
        self.assertEqual(extract_machine_id("NO-PMC-HERE"), "")

    def test_extract_id_from_folder(self) -> None:
        """Test extracting id from backup folder names."""
        self.assertEqual(_extract_id_from_folder("OS_5GLPI29516_PMC_600259"), "600259")
        self.assertEqual(_extract_id_from_folder("OS_12345_PMC123456"), "123456")
        self.assertEqual(_extract_id_from_folder("OS_SIMPLE"), "")

    @patch("services.backup_discovery.os.environ", {"USERNAME": "14029"})
    def test_detect_user_login(self) -> None:
        """Test current login extraction."""
        self.assertEqual(detect_user_login(), "14029")

    def test_calculate_dir_stats(self) -> None:
        """Test directory stats calculation ignoring system files."""
        structure = {
            "root/file1.txt": {"size": 100, "mtime": 10.0},
            "root/file2.txt": {"size": 250, "mtime": 20.0},
            "root/desktop.ini": {"size": 84, "mtime": 30.0},
            "root/Thumbs.db": {"size": 12000, "mtime": 40.0},
            "root/subdir/.DS_Store": {"size": 4096, "mtime": 50.0},
            "root/subdir/file3.txt": {"size": 50, "mtime": 15.0},
        }
        root = FakePath("root", structure)
        total_bytes, max_mtime = _calculate_dir_stats(root)
        self.assertEqual(total_bytes, 400)
        self.assertEqual(max_mtime, 20.0)

    def test_list_subfolders(self) -> None:
        """Test listing subfolders."""
        structure = {
            "root/Desktop": {"is_dir": True},
            "root/Documents": {"is_dir": True},
            "root/file.txt": {"is_dir": False},
        }
        root = FakePath("root", structure)
        self.assertEqual(_list_subfolders(root), ["Desktop", "Documents"])

    @patch("services.backup_discovery.Path")
    def test_scan_network_source_machine_id_normal(self, mock_path: object) -> None:
        """Test network scan with machine_id in normal mode (picks most recent)."""
        fs = {
            "//192.168.11.245/backups/OS_5_PMC_600259/USUARIOS/14029": {"is_dir": True, "mtime": 100.0},
            "//192.168.11.245/backups/OS_6_PMC_600259/USUARIOS/14029": {"is_dir": True, "mtime": 200.0},
        }
        setattr(mock_path, "side_effect", lambda p: FakePath(p, fs))
        sources = scan_network_source("192.168.11.245", "backups", "600259", "14029", admin_mode=False)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].path.as_posix(), "//192.168.11.245/backups/OS_6_PMC_600259/USUARIOS/14029")

    @patch("services.backup_discovery.Path")
    def test_scan_network_source_machine_id_admin(self, mock_path: object) -> None:
        """Test network scan with machine_id in admin mode (returns all)."""
        fs = {
            "//192.168.11.245/backups/OS_5_PMC_600259/USUARIOS/14029": {"is_dir": True, "mtime": 100.0},
            "//192.168.11.245/backups/OS_6_PMC_600259/USUARIOS/14029": {"is_dir": True, "mtime": 200.0},
        }
        setattr(mock_path, "side_effect", lambda p: FakePath(p, fs))
        sources = scan_network_source("192.168.11.245", "backups", "600259", "14029", admin_mode=True)
        self.assertEqual(len(sources), 2)

    @patch("services.backup_discovery.Path")
    def test_scan_network_source_fallback_normal(self, mock_path: object) -> None:
        """Test network fallback in normal mode (picks most recent and stops)."""
        fs = {
            "//192.168.11.245/backups/OS_5_PMC_111111/USUARIOS/14029": {"is_dir": True, "mtime": 100.0},
            "//192.168.11.245/backups/OS_5_PMC_222222/USUARIOS/14029": {"is_dir": True, "mtime": 200.0},
        }
        setattr(mock_path, "side_effect", lambda p: FakePath(p, fs))
        sources = scan_network_source("192.168.11.245", "backups", "", "14029", admin_mode=False)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].machine_id, "222222")

    @patch("services.backup_discovery.Path")
    def test_scan_network_source_fallback_admin(self, mock_path: object) -> None:
        """Test network fallback in admin mode (returns all matches)."""
        fs = {
            "//192.168.11.245/backups/OS_5_PMC_111111/USUARIOS/14029": {"is_dir": True, "mtime": 100.0},
            "//192.168.11.245/backups/OS_5_PMC_222222/USUARIOS/14029": {"is_dir": True, "mtime": 200.0},
        }
        setattr(mock_path, "side_effect", lambda p: FakePath(p, fs))
        sources = scan_network_source("192.168.11.245", "backups", "", "14029", admin_mode=True)
        self.assertEqual(len(sources), 2)

    @patch("services.backup_discovery.Path")
    def test_scan_local_sources_normal(self, mock_path: object) -> None:
        """Test local scan in normal mode (picks most recent)."""
        fs = {
            "C:/OS_5_PMC_600259/14029": {"is_dir": True, "mtime": 100.0},
            "C:/OS_6_PMC_600259/14029": {"is_dir": True, "mtime": 200.0},
            "C:/Windows/14029": {"is_dir": True, "mtime": 300.0},
        }
        setattr(mock_path, "side_effect", lambda p: FakePath(p, fs))
        sources = scan_local_sources("14029", admin_mode=False)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].path.as_posix(), "C:/OS_6_PMC_600259/14029")

    @patch("services.backup_discovery.Path")
    def test_scan_local_sources_admin(self, mock_path: object) -> None:
        """Test local scan in admin mode (returns all matches)."""
        fs = {
            "C:/OS_5_PMC_600259/14029": {"is_dir": True, "mtime": 100.0},
            "C:/OS_6_PMC_600259/14029": {"is_dir": True, "mtime": 200.0},
            "C:/Windows/14029": {"is_dir": True, "mtime": 300.0},
        }
        setattr(mock_path, "side_effect", lambda p: FakePath(p, fs))
        sources = scan_local_sources("14029", admin_mode=True)
        self.assertEqual(len(sources), 2)

    @patch("services.backup_discovery.detect_user_login", return_value="14029")
    @patch("services.backup_discovery.socket.gethostname", return_value="DESKTOP-PMC_600259")
    @patch("services.backup_discovery.scan_network_source")
    @patch("services.backup_discovery.scan_local_sources")
    def test_discover_all_sources(
        self, mock_local: object, mock_net: object, mock_host: object, mock_login: object
    ) -> None:
        """Test discover_all_sources orchestrator calls."""
        setattr(mock_net, "return_value", [BackupSource(Path("net"), "network", "600259", 100)])
        setattr(mock_local, "return_value", [BackupSource(Path("loc"), "local", "600259", 200)])
        all_sources = discover_all_sources("192.168.11.245", "backups")
        self.assertEqual(len(all_sources), 2)

    @patch("services.backup_discovery.Path")
    def test_scan_local_sources_multiple_drives(self, mock_path: object) -> None:
        """Test scanning local sources on multiple drives."""
        fs = {
            "C:/OS_5_PMC_600259/14029": {"is_dir": True, "mtime": 100.0},
            "D:/OS_6_PMC_600259/14029": {"is_dir": True, "mtime": 200.0},
        }
        setattr(mock_path, "side_effect", lambda p: FakePath(p, fs))
        sources = scan_local_sources("14029", admin_mode=True)
        self.assertEqual(len(sources), 2)
        paths = [s.path.as_posix() for s in sources]
        self.assertIn("C:/OS_5_PMC_600259/14029", paths)
        self.assertIn("D:/OS_6_PMC_600259/14029", paths)

    def test_build_source_with_raiz(self) -> None:
        """Test that _build_source includes RAIZ directory size and names."""
        from services.backup_discovery import _build_source
        fs = {
            "C:/OS_5_PMC_600259/USUARIOS/14029": {"is_dir": True},
            "C:/OS_5_PMC_600259/USUARIOS/14029/Desktop/a.txt": {"size": 15},
            "C:/OS_5_PMC_600259/RAIZ/db.sqlite": {"size": 25},
        }
        fs["C:/OS_5_PMC_600259/RAIZ"] = {"is_dir": True}
        fs["C:/OS_5_PMC_600259/USUARIOS"] = {"is_dir": True}
        fs["C:/OS_5_PMC_600259/USUARIOS/14029/Desktop"] = {"is_dir": True}

        user_path = FakePath("C:/OS_5_PMC_600259/USUARIOS/14029", fs)
        source = _build_source(user_path, "local", "600259")  # type: ignore

        self.assertEqual(source.total_bytes, 40)
        self.assertIn("RAIZ", source.folder_list)

