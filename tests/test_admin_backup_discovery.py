from __future__ import annotations

"""Unit tests for services.admin_backup_discovery — cheap-probe discovery,
lazy detail loading, query re-validation, and cancellation."""

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from services.admin_backup_discovery import (
    PENDING_STATS,
    AdminBackupSource,
    UserProfileDetail,
    _has_any_file,
    _origin_for,
    _peek_profile,
    _peek_raiz,
    _source_matches_terms,
    build_admin_source,
    load_source_details,
    scan_admin_backups,
)


class TestHasAnyFile(unittest.TestCase):
    """_has_any_file is the cheap early-exit probe discovery relies on to
    decide whether a folder has anything restorable."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def test_true_when_a_real_file_exists(self) -> None:
        (self.tmp / "sub").mkdir()
        (self.tmp / "sub" / "file.txt").write_text("data")
        self.assertTrue(_has_any_file(self.tmp))

    def test_false_for_only_empty_subfolders(self) -> None:
        (self.tmp / "Documentos").mkdir()
        (self.tmp / "Documentos" / "Sub").mkdir()
        self.assertFalse(_has_any_file(self.tmp))

    def test_ignores_system_noise_files(self) -> None:
        (self.tmp / "desktop.ini").write_text("junk")
        (self.tmp / "Thumbs.db").write_text("junk")
        self.assertFalse(_has_any_file(self.tmp))

    def test_false_for_missing_path(self) -> None:
        self.assertFalse(_has_any_file(self.tmp / "does-not-exist"))


class TestPeekProbes(unittest.TestCase):
    """_peek_raiz/_peek_profile exclude empty folders and mark size/counts
    as PENDING_STATS instead of walking the whole tree up front."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def test_peek_raiz_excludes_empty_folder(self) -> None:
        raiz = self.tmp / "RAIZ"
        (raiz / "empty").mkdir(parents=True)
        self.assertIsNone(_peek_raiz(raiz))

    def test_peek_raiz_includes_nonempty_with_pending_sentinel(self) -> None:
        raiz = self.tmp / "RAIZ"
        raiz.mkdir()
        (raiz / "file.txt").write_text("data")
        detail = _peek_raiz(raiz)
        self.assertIsNotNone(detail)
        self.assertEqual(detail.file_count, PENDING_STATS)
        self.assertEqual(detail.dir_count, PENDING_STATS)

    def test_peek_profile_excludes_empty_folder(self) -> None:
        profile = self.tmp / "USUARIOS" / "29107"
        (profile / "Documentos").mkdir(parents=True)
        self.assertIsNone(_peek_profile(profile))

    def test_peek_profile_includes_nonempty_with_pending_sentinel(self) -> None:
        profile = self.tmp / "USUARIOS" / "29107"
        profile.mkdir(parents=True)
        (profile / "file.txt").write_text("data")
        detail = _peek_profile(profile)
        self.assertIsNotNone(detail)
        self.assertEqual(detail.name, "29107")
        self.assertEqual(detail.file_count, PENDING_STATS)


class TestBuildAdminSourceAndLazyDetails(unittest.TestCase):
    """build_admin_source() stays cheap (PENDING_STATS); load_source_details()
    is the only place that pays for exact sizes."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "RAIZ" / "sub").mkdir(parents=True)
        (self.tmp / "RAIZ" / "sub" / "file.txt").write_text("hello world")
        (self.tmp / "USUARIOS" / "29107" / "Desktop").mkdir(parents=True)
        (self.tmp / "USUARIOS" / "29107" / "Desktop" / "a.txt").write_text("data")
        (self.tmp / "USUARIOS" / "emptyuser" / "Documentos").mkdir(parents=True)

    def test_build_admin_source_uses_pending_sentinel(self) -> None:
        src = build_admin_source(self.tmp, "local")
        self.assertIsNotNone(src)
        self.assertEqual(src.total_bytes, PENDING_STATS)
        self.assertEqual(src.raiz.file_count, PENDING_STATS)
        self.assertEqual([p.name for p in src.profiles], ["29107"])

    def test_build_admin_source_none_when_nothing_restorable(self) -> None:
        empty_only = Path(tempfile.mkdtemp())
        (empty_only / "USUARIOS" / "ghost" / "Documentos").mkdir(parents=True)
        self.assertIsNone(build_admin_source(empty_only, "local"))

    def test_load_source_details_computes_exact_sizes(self) -> None:
        src = build_admin_source(self.tmp, "local")
        detailed = load_source_details(src)
        self.assertEqual(detailed.raiz.size_bytes, len("hello world"))
        self.assertEqual(detailed.raiz.file_count, 1)
        self.assertEqual(detailed.profiles[0].size_bytes, len("data"))
        self.assertEqual(detailed.total_bytes, len("hello world") + len("data"))


class TestSourceMatchesTerms(unittest.TestCase):
    """_source_matches_terms re-validates a query match against the final,
    content-filtered source (the 'lello' empty-profile bug)."""

    def test_matches_via_source_name(self) -> None:
        src = AdminBackupSource(
            path=Path("X"), name="OS_5GLPI30327_PMC_125678", origin="network",
            machine_id="125678", total_bytes=PENDING_STATS, raiz=None, profiles=[],
        )
        self.assertTrue(_source_matches_terms(src, {"30327"}))
        self.assertFalse(_source_matches_terms(src, {"unrelated"}))

    def test_matches_via_surviving_profile_name(self) -> None:
        profile = UserProfileDetail(
            name="29107", size_bytes=0, modified_time=1.0, path=Path("P"), file_count=PENDING_STATS,
        )
        src = AdminBackupSource(
            path=Path("X"), name="OS_5", origin="local", machine_id="",
            total_bytes=PENDING_STATS, raiz=None, profiles=[profile],
        )
        self.assertTrue(_source_matches_terms(src, {"29107"}))

    def test_no_match_when_profile_was_filtered_out(self) -> None:
        # Simulates: "lello" matched the raw USUARIOS subfolder name during
        # candidate scanning, but that folder was empty and got excluded
        # from the built source's profile list.
        other_profile = UserProfileDetail(
            name="realuser", size_bytes=0, modified_time=1.0, path=Path("P"), file_count=PENDING_STATS,
        )
        src = AdminBackupSource(
            path=Path("X"), name="OS_5", origin="local", machine_id="",
            total_bytes=PENDING_STATS, raiz=None, profiles=[other_profile],
        )
        self.assertFalse(_source_matches_terms(src, {"lello"}))


class TestScanAdminBackupsQueryValidation(unittest.TestCase):
    """End-to-end: scan_admin_backups must not surface a source whose only
    reason for matching a custom query turned out to be empty content."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def _scan(self, query: str, candidate: Path, cancel_event=None) -> list[AdminBackupSource]:
        with patch("services.admin_backup_discovery._find_network_candidates", return_value=[]), \
             patch("services.admin_backup_discovery._find_local_candidates", return_value=[candidate]), \
             patch("services.admin_backup_discovery._list_dirs", return_value=[]), \
             patch("config.is_test_mode", return_value=False):
            return list(scan_admin_backups("x", "y", custom_query=query, cancel_event=cancel_event))

    def test_query_matching_only_empty_profile_yields_nothing(self) -> None:
        machine = self.tmp / "OS_5_PMC_999999"
        (machine / "USUARIOS" / "lello" / "Documentos").mkdir(parents=True)  # empty
        (machine / "USUARIOS" / "realuser").mkdir(parents=True)
        (machine / "USUARIOS" / "realuser" / "file.txt").write_text("data")

        results = self._scan("lello", machine)
        self.assertEqual(results, [])

    def test_query_matching_nonempty_profile_is_found(self) -> None:
        machine = self.tmp / "OS_5_PMC_888888"
        (machine / "USUARIOS" / "lello").mkdir(parents=True)
        (machine / "USUARIOS" / "lello" / "file.txt").write_text("real data")

        results = self._scan("lello", machine)
        self.assertEqual([r.name for r in results], ["OS_5_PMC_888888"])

    def test_cancel_event_stops_scan_immediately(self) -> None:
        machine = self.tmp / "OS_5_PMC_777777"
        (machine / "USUARIOS" / "someone").mkdir(parents=True)
        (machine / "USUARIOS" / "someone" / "file.txt").write_text("data")

        cancel_event = threading.Event()
        cancel_event.set()
        results = self._scan("someone", machine, cancel_event=cancel_event)
        self.assertEqual(results, [])


class TestOriginFor(unittest.TestCase):
    def test_network_share_path(self) -> None:
        self.assertEqual(_origin_for(Path("\\\\server\\share\\OS_5")), "network")

    def test_local_drive_path(self) -> None:
        self.assertEqual(_origin_for(Path("C:/OS_5")), "local")


if __name__ == "__main__":
    unittest.main()
