from __future__ import annotations

"""Elevated-helper client/server for restores targeting another user's profile.

Writing into another Windows account's C:\\Users\\<name> folder requires an
admin token. Rather than relaunching all of Remos elevated, a single helper
process is spawned once — via a "runas" ShellExecute, one UAC prompt — the
moment the admin unlocks "Modo admin", and stays alive for the rest of the
run. It services copy requests over a named pipe, so only that one action
needs elevation and every restore afterward in the same session reuses it.

Example:
    if ensure_helper_started():
        ok, err = copy_via_helper(source, dest, cut_mode=False)
"""
import ctypes
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from config import (
    ADMIN_HELPER_CONNECT_TIMEOUT_SECONDS,
    ADMIN_HELPER_CONNECT_POLL_SECONDS,
    ADMIN_HELPER_PIPE_BUFFER_BYTES,
    ADMIN_HELPER_CONNECT_RETRY_ATTEMPTS,
    ADMIN_HELPER_CONNECT_RETRY_DELAY_SECONDS,
)

logger = logging.getLogger(__name__)

PIPE_NAME = r"\\.\pipe\RemosAdminHelper"

# CLI flag main.py checks for to run run_helper_server() instead of the GUI.
ADMIN_HELPER_FLAG = "--admin-helper"

# ERROR_PIPE_BUSY (231): the pipe exists but the server hasn't looped back
# to a fresh listening instance yet — happens between two back-to-back
# requests during a large restore. ERROR_FILE_NOT_FOUND (2): the brief gap
# where the previous instance already closed and the next one isn't created
# yet. Both are expected, transient states of the server's request loop, not
# real failures, so the client retries a few times before giving up.
_RETRYABLE_CONNECT_ERRORS = {231, 2}

# The pipe is created by the elevated (High-integrity) helper but must be
# reachable from the unprivileged (Medium-integrity) main app. Windows'
# Mandatory Integrity Control blocks that write-up by default regardless of
# the DACL, so the pipe needs an explicit Low-integrity label with no
# no-write-up restriction ("S:(ML;;;;;LW)") on top of a DACL that grants
# Everyone access.
_PIPE_SDDL = "D:(A;;GA;;;WD)S:(ML;;;;;LW)"

_helper_started = False

# One connection is opened lazily on the first copy request and reused for
# every request after that, instead of reconnecting per file — for a restore
# with hundreds of foreign-profile files that was the single biggest source
# of IPC overhead (and of the ERROR_PIPE_BUSY contention fixed above).
# Requests are serialized through this lock since a pipe handle can't safely
# carry two request/response round trips at once.
_client_lock = threading.Lock()
_client_handle: Optional[object] = None


def _pipe_security_attributes() -> object:
    """Security attributes allowing a Medium-integrity client to connect to
    a pipe created by this (High-integrity, once elevated) process."""
    import pywintypes
    import win32security
    sd = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
        _PIPE_SDDL, win32security.SDDL_REVISION_1,
    )
    sa = pywintypes.SECURITY_ATTRIBUTES()
    sa.SECURITY_DESCRIPTOR = sd
    return sa


def is_admin() -> bool:
    """True if the current process already holds an elevated token."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _helper_launch_command() -> tuple[str, str]:
    """Return (executable, args) that relaunch this app in helper mode.

    The helper has no UI of its own, so in dev mode it's launched with
    pythonw.exe rather than python.exe — the latter always allocates a
    console window, which would otherwise flash up on every UAC accept.
    """
    if getattr(sys, "frozen", False):
        return sys.executable, ADMIN_HELPER_FLAG
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pythonw):
        exe = pythonw
    main_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "main.py")
    return exe, f'"{os.path.abspath(main_path)}" {ADMIN_HELPER_FLAG}'


def _connect_client_handle() -> object:
    """Open a client handle to the helper's pipe, riding out the transient
    ERROR_PIPE_BUSY / ERROR_FILE_NOT_FOUND windows described above."""
    import win32file
    import pywintypes
    last_exc: Optional[pywintypes.error] = None
    for _ in range(ADMIN_HELPER_CONNECT_RETRY_ATTEMPTS):
        try:
            return win32file.CreateFile(
                PIPE_NAME, win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None, win32file.OPEN_EXISTING, 0, None,
            )
        except pywintypes.error as exc:
            if exc.winerror not in _RETRYABLE_CONNECT_ERRORS:
                raise
            last_exc = exc
            time.sleep(ADMIN_HELPER_CONNECT_RETRY_DELAY_SECONDS)
    raise last_exc


def _pipe_available() -> bool:
    """Cheap probe: can a client connect to the helper's named pipe right now."""
    import pywintypes
    try:
        handle = _connect_client_handle()
    except pywintypes.error:
        return False
    import win32file
    win32file.CloseHandle(handle)
    return True


def ensure_helper_started() -> bool:
    """Spawn the elevated helper (one UAC prompt) if it isn't already running.

    Safe to call repeatedly — a no-op once the helper is up. If Remos itself
    was already launched elevated (e.g. "Run as administrator"), this is a
    no-op too: the current process can already write anywhere it needs to
    (see _needs_elevated_write in backup_copier.py), so spawning a second
    elevated process would only add a redundant UAC prompt.

    Returns False if the user declines UAC or the helper doesn't come up in
    time; callers should degrade gracefully (restores to the current user's
    own profile never needed this and keep working either way).
    """
    global _helper_started
    if is_admin() or _helper_started:
        # Once the helper is up, the client holds one persistent connection
        # open for the rest of the run (see _get_client_handle) — the pipe's
        # sole instance is then busy servicing it, so a fresh probe
        # connection here would itself fail with ERROR_PIPE_BUSY and (wrongly)
        # look like the helper isn't running. _helper_started is the source
        # of truth instead; no new connection attempt is needed at all.
        return True
    if _pipe_available():
        _helper_started = True
        return True
    _helper_started = _spawn_and_wait_for_helper()
    return _helper_started


def _spawn_and_wait_for_helper() -> bool:
    """Launch the elevated helper via a "runas" ShellExecute (the one UAC
    prompt) and poll its pipe until it comes up or ADMIN_HELPER_CONNECT_TIMEOUT_SECONDS
    elapses.
    """
    import win32api
    import win32con
    exe, args = _helper_launch_command()
    try:
        win32api.ShellExecute(0, "runas", exe, args, None, win32con.SW_HIDE)
    except Exception as exc:
        logger.error('{"event":"admin_helper_launch_failed","error":"%s"}', exc)
        return False

    deadline = time.time() + ADMIN_HELPER_CONNECT_TIMEOUT_SECONDS
    while time.time() < deadline:
        if _pipe_available():
            return True
        time.sleep(ADMIN_HELPER_CONNECT_POLL_SECONDS)
    logger.error('{"event":"admin_helper_timeout"}')
    return False


def shutdown_helper() -> None:
    """Tell a running helper to exit. Called once, at app shutdown."""
    global _helper_started
    if not _helper_started:
        return
    try:
        _send_request({"op": "shutdown"})
    except Exception:
        pass
    _drop_client_handle()
    _helper_started = False


def copy_via_helper(source: Path, dest: Path, cut_mode: bool = False) -> tuple[bool, str]:
    """Ask the elevated helper to write *source* to *dest*.

    Returns (success, error_message).
    """
    try:
        resp = _send_request({
            "op": "copy",
            "source": str(source),
            "dest": str(dest),
            "cut": cut_mode,
        })
    except Exception as exc:
        return False, f"Falha de comunicação com o processo elevado: {exc}"
    if resp.get("ok"):
        return True, ""
    return False, resp.get("error", "Erro desconhecido no processo elevado")


def _get_client_handle() -> object:
    """Return the persistent client connection, opening one the first time
    it's needed."""
    global _client_handle
    if _client_handle is None:
        _client_handle = _connect_client_handle()
    return _client_handle


def _drop_client_handle() -> None:
    """Discard the cached connection so the next request reconnects from
    scratch — used after a shutdown and after a broken-connection retry."""
    global _client_handle
    if _client_handle is not None:
        import win32file
        try:
            win32file.CloseHandle(_client_handle)
        except Exception:
            pass
        _client_handle = None


def _send_request(payload: dict) -> dict:
    """Send one request over the persistent connection, reconnecting once
    if it turns out to have gone stale (e.g. the helper cycled its listening
    instance between restores). Requests are serialized: only one is ever
    in flight on the shared handle at a time.
    """
    import win32file
    import pywintypes
    message = (json.dumps(payload) + "\n").encode("utf-8")
    with _client_lock:
        try:
            handle = _get_client_handle()
            win32file.WriteFile(handle, message)
            return _read_message(handle)
        except pywintypes.error:
            _drop_client_handle()
            handle = _get_client_handle()
            win32file.WriteFile(handle, message)
            return _read_message(handle)


def _read_message(handle) -> dict:
    import win32file
    chunks = []
    while True:
        _, chunk = win32file.ReadFile(handle, ADMIN_HELPER_PIPE_BUFFER_BYTES)
        chunks.append(chunk)
        if chunk.endswith(b"\n"):
            break
    return json.loads(b"".join(chunks).decode("utf-8"))


# ---------------------------------------------------------------------
# Helper-process side (runs only inside the elevated process, launched
# via `main.py --admin-helper` — see ADMIN_HELPER_FLAG)
# ---------------------------------------------------------------------


def _create_server_pipe() -> object:
    import win32pipe
    return win32pipe.CreateNamedPipe(
        PIPE_NAME,
        win32pipe.PIPE_ACCESS_DUPLEX,
        win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
        win32pipe.PIPE_UNLIMITED_INSTANCES,
        ADMIN_HELPER_PIPE_BUFFER_BYTES, ADMIN_HELPER_PIPE_BUFFER_BYTES, 0,
        _pipe_security_attributes(),
    )


def _serve_one_connection(pipe: object) -> bool:
    """Service every request sent on one accepted connection until the
    client disconnects or asks to shut down. Returns True if shutdown was
    requested.
    """
    import win32pipe
    import win32file
    import pywintypes
    try:
        win32pipe.ConnectNamedPipe(pipe, None)
        while True:
            request = _read_message(pipe)
            if request.get("op") == "shutdown":
                return True
            win32file.WriteFile(pipe, (json.dumps(_handle_request(request)) + "\n").encode("utf-8"))
    except pywintypes.error as exc:
        # The client disconnected (or a genuine I/O error) — recycle this
        # instance and wait for the next connection.
        logger.debug('{"event":"admin_helper_client_disconnected","error":"%s"}', exc)
        return False


def run_helper_server() -> None:
    """Entry point for the elevated helper process. Blocks forever.

    The client now keeps one persistent connection open for the whole
    restore session, so each accepted connection here services every
    request sent on it — not just one — until the client disconnects (a
    fresh connection is then accepted, e.g. for the next restore session)
    or sends {"op": "shutdown"}.
    """
    import win32file

    logger.info('{"event":"admin_helper_started"}')
    shutdown_requested = False
    while not shutdown_requested:
        pipe = _create_server_pipe()
        try:
            shutdown_requested = _serve_one_connection(pipe)
        finally:
            try:
                win32file.CloseHandle(pipe)
            except Exception:
                pass
    logger.info('{"event":"admin_helper_stopped"}')


def _handle_request(request: dict) -> dict:
    if request.get("op") != "copy":
        return {"ok": False, "error": f"Operação desconhecida: {request.get('op')}"}
    from services.backup_copier import _copy_single_file, _delete_source_file
    source = Path(request["source"])
    dest = Path(request["dest"])
    try:
        _copy_single_file(source, dest)
        if request.get("cut"):
            _delete_source_file(source)
        return {"ok": True}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
