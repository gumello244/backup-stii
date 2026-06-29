from __future__ import annotations

"""Discover backup sources on the network server and local volumes.

Scans for folders matching machine identifier patterns in network shares
and local drives with fallbacks and admin/normal mode options.

Example:
    sources = discover_all_sources("192.168.11.245", "backups")
"""
import logging
import os
import re
import socket
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Excluded system directory names under drive C:\ (case-insensitive)
_LOCAL_EXCLUDE = {
    "arquivos de programas", "program files", "program files (x86)",
    "inetpub", "intel", "nvidia", "perflogs", "temp",
    "usuários", "users", "windows", "programdata"
}


@dataclass
class BackupSource:
    """A discovered backup source with metadata.

    Example:
        src = BackupSource(
            path=Path("\\\\192.168.11.245\\backups\\OS_5\\USUARIOS\\14029"),
            origin="network", machine_id="PMC_600259",
            total_bytes=1024, folder_list=["Desktop", "Documents"],
        )
    """
    path: Path
    origin: str             # "network" | "local"
    machine_id: str
    total_bytes: int
    folder_list: list[str] = field(default_factory=list)


def detect_user_login() -> str:
    """Return the current Windows login name.

    Example:
        login = detect_user_login()  # "14029"
    """
    return os.environ.get("USERNAME", os.getlogin())


def extract_machine_id(hostname: str) -> str:
    """Extract machine identifier (e.g. '123456' or '600259') from hostname.

    Example:
        extract_machine_id("DESKTOP-PMC_600259")  # "600259"
        extract_machine_id("25ABC1T123456")       # "123456"
    """
    match_pmc = re.search(r"PMC_?(\d+)", hostname, re.IGNORECASE)
    if match_pmc:
        return match_pmc.group(1)
    match_digits = re.search(r"\d{6}", hostname)
    if match_digits:
        return match_digits.group(0)
    match_trailing = re.search(r"\d+$", hostname)
    if match_trailing:
        return match_trailing.group(0)
    return ""


def _calculate_dir_bytes(root: Path) -> int:
    """Sum file sizes recursively under *root*, ignoring system files.

    Example:
        total = _calculate_dir_bytes(Path("C:/"))
    """
    total = 0
    try:
        for entry in root.rglob("*"):
            if entry.is_file() and entry.name.lower() not in {
                "desktop.ini", "thumbs.db", ".ds_store"
            }:
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _list_subfolders(user_path: Path) -> list[str]:
    """Return immediate child directory names inside *user_path*.

    Example:
        subs = _list_subfolders(Path("C:/"))
    """
    try:
        return sorted(
            e.name for e in user_path.iterdir() if e.is_dir()
        )
    except OSError:
        return []


def _build_source(user_path: Path, origin: str, machine_id: str) -> BackupSource:
    """Construct a BackupSource from a validated user directory.

    Example:
        src = _build_source(Path("C:/"), "local", "PMC_12345")
    """
    return BackupSource(
        path=user_path,
        origin=origin,
        machine_id=machine_id,
        total_bytes=_calculate_dir_bytes(user_path),
        folder_list=_list_subfolders(user_path),
    )


def _extract_id_from_folder(folder_name: str) -> str:
    """Try to pull a machine id out of a backup folder name.

    Example:
        mid = _extract_id_from_folder("OS_PMC_12345")
    """
    return extract_machine_id(folder_name)


def _safe_mtime(path: Path) -> float:
    """Return mtime of path, or 0.0 on OSError.

    Example:
        t = _safe_mtime(path)
    """
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _fallback_sort_key(folder: Path, login: str) -> float:
    """Get sort key for fallback candidates using max mtime.

    Example:
        key = _fallback_sort_key(folder, "14029")
    """
    return max(_safe_mtime(folder), _safe_mtime(folder / "USUARIOS" / login))


# ------------------------------------------------------------------
# Network discovery
# ------------------------------------------------------------------

def scan_network_source(
    server_ip: str,
    share: str,
    machine_id: str,
    login: str,
    admin_mode: bool = False,
) -> list[BackupSource]:
    """Scan the network backup share for matching backup folders.

    Example:
        sources = scan_network_source("192.168.11.245", "backups", "PMC_600259", "14029")
    """
    network_root = Path(f"\\\\{server_ip}\\{share}")
    return _scan_root_for_sources(network_root, machine_id, login, "network", admin_mode)


def _scan_root_for_sources(
    root: Path,
    machine_id: str,
    login: str,
    origin: str,
    admin_mode: bool = False,
) -> list[BackupSource]:
    """Scan *root* for backup folders containing USUARIOS\\{login}."""
    try:
        candidates = [d for d in root.iterdir() if d.is_dir()]
    except OSError as exc:
        logger.warning(
            '{"event":"scan_root_failed","root":"%s","error":"%s"}',
            root, exc,
        )
        return []

    if machine_id:
        matched = _filter_by_machine_id(candidates, machine_id, login, origin, admin_mode)
        if matched:
            return matched

    return _filter_by_login_only(candidates, login, origin, admin_mode)


def _find_folders_with_id(
    candidates: list[Path],
    machine_id: str,
    login: str,
) -> list[tuple[float, Path]]:
    """Find directories containing machine_id and USUARIOS\\login.

    Example:
        folders = _find_folders_with_id(candidates, "123456", "login")
    """
    matched: list[tuple[float, Path]] = []
    for folder in candidates:
        if machine_id.lower() in folder.name.lower():
            user_path = folder / "USUARIOS" / login
            if user_path.is_dir():
                matched.append((_safe_mtime(user_path), user_path))
    return matched


def _filter_by_machine_id(
    candidates: list[Path],
    machine_id: str,
    login: str,
    origin: str,
    admin_mode: bool = False,
) -> list[BackupSource]:
    """Return sources from folders containing machine_id.

    Example:
        srcs = _filter_by_machine_id(candidates, "123456", "14029", "network")
    """
    matched_dirs = _find_folders_with_id(candidates, machine_id, login)
    if not matched_dirs:
        return []

    matched_dirs.sort(key=lambda t: t[0], reverse=True)
    if admin_mode:
        return [
            _build_source(p, origin, machine_id)
            for _, p in matched_dirs
        ]
    return [_build_source(matched_dirs[0][1], origin, machine_id)]


def _filter_by_login_only(
    candidates: list[Path],
    login: str,
    origin: str,
    admin_mode: bool = False,
) -> list[BackupSource]:
    """Fallback: scan folders for USUARIOS\\login, starting from newest.

    Example:
        srcs = _filter_by_login_only(candidates, "14029", "network")
    """
    sorted_dirs = sorted(
        candidates,
        key=lambda d: _fallback_sort_key(d, login),
        reverse=True
    )
    results: list[BackupSource] = []

    for folder in sorted_dirs:
        user_path = folder / "USUARIOS" / login
        if user_path.is_dir():
            mid = _extract_id_from_folder(folder.name)
            results.append(_build_source(user_path, origin, mid))
            if not admin_mode:
                return results
    return results


# ------------------------------------------------------------------
# Local discovery
# ------------------------------------------------------------------

def _scan_local_dir_depth(
    parent: Path,
    login: str,
    matches: list[tuple[float, Path]],
) -> None:
    """Scan subdirectories of parent up to depth 2 for login name.

    Example:
        _scan_local_dir_depth(parent_path, "14029", matches)
    """
    try:
        subdirs = [s for s in parent.iterdir() if s.is_dir()]
    except OSError:
        return

    for s in subdirs:
        if login.lower() in s.name.lower():
            matches.append((_safe_mtime(s), s))
            continue
        try:
            for gs in s.iterdir():
                if gs.is_dir() and login.lower() in gs.name.lower():
                    matches.append((_safe_mtime(gs), gs))
        except OSError:
            pass


def _find_local_matches(drive_root: Path, login: str) -> list[tuple[float, Path]]:
    """Scan drive_root for directories containing login, excluding default dirs.

    Example:
        matches = _find_local_matches(Path("C:/"), "14029")
    """
    matches: list[tuple[float, Path]] = []
    try:
        children = [d for d in drive_root.iterdir() if d.is_dir()]
    except OSError:
        return []

    for d in children:
        if d.name.lower() in _LOCAL_EXCLUDE:
            continue
        _scan_local_dir_depth(d, login, matches)
    return matches


def scan_local_sources(login: str, admin_mode: bool = False) -> list[BackupSource]:
    """Scan C:\\ non-system directories for login backups.

    Example:
        sources = scan_local_sources("14029")
    """
    matches = _find_local_matches(Path("C:\\"), login)
    if not matches:
        return []

    matches.sort(key=lambda t: t[0], reverse=True)

    if admin_mode:
        return [
            _build_source(path, "local", _extract_id_from_folder(path.parts[1]))
            for _, path in matches
        ]

    _, path = matches[0]
    mid = _extract_id_from_folder(path.parts[1])
    return [_build_source(path, "local", mid)]


# ------------------------------------------------------------------
# Orchestrator
# ------------------------------------------------------------------

def _mock_test_sources(login: str) -> list[BackupSource]:
    """Return mock sources for testing.

    Example:
        srcs = _mock_test_sources("14029")
    """
    logger.info('{"event":"discovery_test_mode","msg":"Returning mock sources"}')
    return [
        BackupSource(
            path=Path("//192.168.11.245/backups/OS_5_PMC_600259/USUARIOS/" + login),
            origin="network",
            machine_id="PMC_600259",
            total_bytes=2450000000,
            folder_list=["Desktop", "Documents", "Downloads", "Pictures"]
        ),
        BackupSource(
            path=Path("C:/OS_5_PMC_600259/USUARIOS/" + login),
            origin="local",
            machine_id="PMC_600259",
            total_bytes=1520000000,
            folder_list=["Desktop", "Documents", "Videos"]
        )
    ]


def discover_all_sources(
    server_ip: str,
    backup_share: str,
    admin_mode: bool = False,
) -> list[BackupSource]:
    """Discover all backup sources (network + local).

    Example:
        sources = discover_all_sources("192.168.11.245", "backups")
    """
    login = detect_user_login()
    hostname = socket.gethostname()
    machine_id = extract_machine_id(hostname)

    logger.info(
        '{"event":"discovery_start","login":"%s","hostname":"%s","machine_id":"%s"}',
        login, hostname, machine_id,
    )

    from config import is_test_mode
    if is_test_mode():
        return _mock_test_sources(login)

    network = scan_network_source(
        server_ip, backup_share, machine_id, login, admin_mode
    )
    local = scan_local_sources(login, admin_mode)
    return network + local
