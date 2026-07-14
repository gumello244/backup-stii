from __future__ import annotations

"""Unit tests for services/elevation.py.

Scoped to the pure/mockable logic (launch-command construction, the
early-return gates in ensure_helper_started, request routing, shutdown
bookkeeping). Actual named-pipe I/O and the real UAC prompt need a live
Windows session and aren't exercised here — see the module docstring in
elevation.py for the end-to-end flow this supports.
"""
import unittest
from unittest.mock import patch, MagicMock

import services.elevation as elevation


class TestIsAdmin(unittest.TestCase):
    """Tests for is_admin()."""

    def test_true_when_shell32_reports_elevated(self) -> None:
        with patch("services.elevation.ctypes") as mock_ctypes:
            mock_ctypes.windll.shell32.IsUserAnAdmin.return_value = 1
            self.assertTrue(elevation.is_admin())

    def test_false_when_shell32_reports_not_elevated(self) -> None:
        with patch("services.elevation.ctypes") as mock_ctypes:
            mock_ctypes.windll.shell32.IsUserAnAdmin.return_value = 0
            self.assertFalse(elevation.is_admin())

    def test_false_on_error(self) -> None:
        with patch("services.elevation.ctypes") as mock_ctypes:
            mock_ctypes.windll.shell32.IsUserAnAdmin.side_effect = OSError("no shell32")
            self.assertFalse(elevation.is_admin())


class TestHelperLaunchCommand(unittest.TestCase):
    """Tests for _helper_launch_command()."""

    def test_frozen_uses_own_executable(self) -> None:
        """A PyInstaller-frozen build relaunches itself with the helper flag."""
        with patch("services.elevation.sys") as mock_sys:
            mock_sys.frozen = True
            mock_sys.executable = "C:\\Program Files\\Remos\\Remos.exe"
            exe, args = elevation._helper_launch_command()
        self.assertEqual(exe, "C:\\Program Files\\Remos\\Remos.exe")
        self.assertEqual(args, elevation.ADMIN_HELPER_FLAG)

    @patch("services.elevation.os.path.exists", return_value=True)
    def test_dev_mode_prefers_pythonw_when_available(self, _mock_exists: MagicMock) -> None:
        """pythonw.exe avoids flashing a console window on every UAC accept."""
        with patch("services.elevation.sys") as mock_sys:
            mock_sys.frozen = False
            mock_sys.executable = "C:\\venv\\Scripts\\python.exe"
            exe, args = elevation._helper_launch_command()
        self.assertEqual(exe, "C:\\venv\\Scripts\\pythonw.exe")
        self.assertIn(elevation.ADMIN_HELPER_FLAG, args)
        self.assertIn("main.py", args)

    @patch("services.elevation.os.path.exists", return_value=False)
    def test_dev_mode_falls_back_to_python_when_no_pythonw(self, _mock_exists: MagicMock) -> None:
        with patch("services.elevation.sys") as mock_sys:
            mock_sys.frozen = False
            mock_sys.executable = "C:\\venv\\Scripts\\python.exe"
            exe, args = elevation._helper_launch_command()
        self.assertEqual(exe, "C:\\venv\\Scripts\\python.exe")


class TestEnsureHelperStarted(unittest.TestCase):
    """Tests for the early-return gates in ensure_helper_started()."""

    def setUp(self) -> None:
        self._original_helper_started = elevation._helper_started

    def tearDown(self) -> None:
        elevation._helper_started = self._original_helper_started

    def test_already_admin_short_circuits_without_probing_pipe(self) -> None:
        """Remos running elevated already can write anywhere it needs to —
        spawning a second elevated helper would just be a redundant prompt."""
        elevation._helper_started = False
        with patch("services.elevation.is_admin", return_value=True), \
             patch("services.elevation._pipe_available") as mock_probe:
            self.assertTrue(elevation.ensure_helper_started())
        mock_probe.assert_not_called()

    def test_already_started_short_circuits_without_probing_pipe(self) -> None:
        """Once the helper is up, the client's persistent connection keeps
        the pipe's sole instance busy — a fresh probe would (wrongly) look
        like the helper isn't running, so _helper_started is trusted instead."""
        elevation._helper_started = True
        with patch("services.elevation.is_admin", return_value=False), \
             patch("services.elevation._pipe_available") as mock_probe:
            self.assertTrue(elevation.ensure_helper_started())
        mock_probe.assert_not_called()

    def test_pipe_already_available_marks_started_without_spawning(self) -> None:
        """A helper from an earlier run in this process is detected via the
        probe, without launching a new one."""
        elevation._helper_started = False
        with patch("services.elevation.is_admin", return_value=False), \
             patch("services.elevation._pipe_available", return_value=True), \
             patch("services.elevation._spawn_and_wait_for_helper") as mock_spawn:
            self.assertTrue(elevation.ensure_helper_started())
        mock_spawn.assert_not_called()
        self.assertTrue(elevation._helper_started)

    def test_spawns_helper_when_not_already_running(self) -> None:
        elevation._helper_started = False
        with patch("services.elevation.is_admin", return_value=False), \
             patch("services.elevation._pipe_available", return_value=False), \
             patch("services.elevation._spawn_and_wait_for_helper", return_value=True) as mock_spawn:
            self.assertTrue(elevation.ensure_helper_started())
        mock_spawn.assert_called_once()
        self.assertTrue(elevation._helper_started)

    def test_spawn_failure_leaves_helper_started_false(self) -> None:
        elevation._helper_started = False
        with patch("services.elevation.is_admin", return_value=False), \
             patch("services.elevation._pipe_available", return_value=False), \
             patch("services.elevation._spawn_and_wait_for_helper", return_value=False):
            self.assertFalse(elevation.ensure_helper_started())
        self.assertFalse(elevation._helper_started)


class TestShutdownHelper(unittest.TestCase):
    """Tests for shutdown_helper()."""

    def setUp(self) -> None:
        self._original_helper_started = elevation._helper_started

    def tearDown(self) -> None:
        elevation._helper_started = self._original_helper_started

    def test_noop_when_helper_never_started(self) -> None:
        elevation._helper_started = False
        with patch("services.elevation._send_request") as mock_send, \
             patch("services.elevation._drop_client_handle") as mock_drop:
            elevation.shutdown_helper()
        mock_send.assert_not_called()
        mock_drop.assert_not_called()

    def test_sends_shutdown_and_drops_connection_when_running(self) -> None:
        elevation._helper_started = True
        with patch("services.elevation._send_request") as mock_send, \
             patch("services.elevation._drop_client_handle") as mock_drop:
            elevation.shutdown_helper()
        mock_send.assert_called_once_with({"op": "shutdown"})
        mock_drop.assert_called_once()
        self.assertFalse(elevation._helper_started)

    def test_swallows_communication_errors(self) -> None:
        """The helper process may already be gone — shutdown must not raise."""
        elevation._helper_started = True
        with patch("services.elevation._send_request", side_effect=OSError("gone")), \
             patch("services.elevation._drop_client_handle") as mock_drop:
            elevation.shutdown_helper()
        mock_drop.assert_called_once()
        self.assertFalse(elevation._helper_started)


class TestHandleRequest(unittest.TestCase):
    """Tests for _handle_request() — the elevated helper's request router."""

    def test_unknown_op_reports_error(self) -> None:
        resp = elevation._handle_request({"op": "delete"})
        self.assertFalse(resp["ok"])
        self.assertIn("delete", resp["error"])

    def test_copy_success(self) -> None:
        with patch("services.backup_copier._copy_single_file") as mock_copy, \
             patch("services.backup_copier._delete_source_file") as mock_delete:
            resp = elevation._handle_request({
                "op": "copy", "source": "C:\\src.txt", "dest": "C:\\dst.txt", "cut": False,
            })
        self.assertEqual(resp, {"ok": True})
        mock_copy.assert_called_once()
        mock_delete.assert_not_called()

    def test_copy_with_cut_deletes_source(self) -> None:
        with patch("services.backup_copier._copy_single_file"), \
             patch("services.backup_copier._delete_source_file") as mock_delete:
            elevation._handle_request({
                "op": "copy", "source": "C:\\src.txt", "dest": "C:\\dst.txt", "cut": True,
            })
        mock_delete.assert_called_once()

    def test_copy_failure_reports_error_message(self) -> None:
        with patch("services.backup_copier._copy_single_file", side_effect=OSError("disk full")):
            resp = elevation._handle_request({
                "op": "copy", "source": "C:\\src.txt", "dest": "C:\\dst.txt", "cut": False,
            })
        self.assertFalse(resp["ok"])
        self.assertIn("disk full", resp["error"])


if __name__ == "__main__":
    unittest.main()
