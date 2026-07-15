from __future__ import annotations

"""Discover backup sources for administrative recovery.

Scans for backup folders on network and local drives, retrieves detailed
metadata for RAIZ and USUARIOS profiles, and yields matching sources.
"""

import logging
import os
import socket
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event
from typing import Callable, Optional, Generator

from services.backup_discovery import (
    _safe_mtime,
    _extract_id_from_folder,
    _LOCAL_EXCLUDE,
    get_local_drives,
    extract_machine_id,
    detect_user_login,
)
from services.backup_merger import MergedFile

logger = logging.getLogger(__name__)

# Search-stage identifiers, reported via scan_admin_backups' stage_cb so the
# UI can show what the current discovery pass is looking for.
STAGE_MACHINE = "machine"
STAGE_CURRENT_USER = "current_user"
STAGE_MACHINE_USERS = "machine_users"
STAGE_QUERY = "query"

StageCallback = Callable[[str], None]

# Sentinel for size_bytes/total_bytes/file_count/dir_count fields that
# haven't been computed yet — discovery only proves a source has restorable
# content (see _peek_raiz/_peek_profile); exact numbers are filled in later
# by load_source_details(), once the admin actually selects the source.
PENDING_STATS = -1
ERROR_STATS = -2

# Short-lived cache for network discovery to prevent redundant network scans
# on fast queries — TTL is configurable via DISCOVERY_CACHE_TTL_SECONDS in
# app_secrets.py, see config.get_discovery_cache_ttl_seconds().
_DISCOVERY_CACHE: dict[tuple[str, str], tuple[float, list[Path], list[Path]]] = {}

# Filesystem noise ignored everywhere sizes/file counts are computed — these
# never represent restorable user content.
_SKIPPED_FILE_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}


@dataclass
class UserProfileDetail:
    """Detailed metadata for a backup user profile folder."""
    name: str
    size_bytes: int
    modified_time: float
    path: Path
    file_count: int = 0


@dataclass
class RaizDetail:
    """Detailed metadata for a RAIZ backup folder."""
    size_bytes: int
    file_count: int
    dir_count: int
    path: Path
    modified_time: float = 0.0


@dataclass
class AdminBackupSource:
    """A discovered backup source containing RAIZ and profiles metadata."""
    path: Path
    name: str
    origin: str
    machine_id: str
    total_bytes: int
    raiz: Optional[RaizDetail]
    profiles: list[UserProfileDetail]


def _is_running_under_test_runner() -> bool:
    """True when executing under unittest/pytest — lets scan_admin_backups
    skip the discovery cache so each test starts from a clean candidate list."""
    return "unittest" in sys.modules or "pytest" in sys.modules


def _walk_stats_recursive(path: str | Path) -> tuple[int, int, int, float]:
    total_bytes, file_count, dir_count, max_mtime = 0, 0, 0, 0.0
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.name.lower() in _SKIPPED_FILE_NAMES:
                    continue
                if entry.is_symlink():
                    continue
                if entry.is_file():
                    file_count += 1
                    try:
                        stat = entry.stat(follow_symlinks=False)
                        total_bytes += stat.st_size
                        max_mtime = max(max_mtime, stat.st_mtime)
                    except OSError:
                        pass
                elif entry.is_dir(follow_symlinks=False):
                    dir_count += 1
                    sub_bytes, sub_files, sub_dirs, sub_mtime = _walk_stats_recursive(entry.path)
                    total_bytes += sub_bytes
                    file_count += sub_files
                    dir_count += sub_dirs
                    max_mtime = max(max_mtime, sub_mtime)
    except OSError:
        pass
    return total_bytes, file_count, dir_count, max_mtime


def _walk_profile_stats_recursive(path: str | Path, start_mtime: float) -> tuple[int, int, float]:
    total_bytes, file_count, max_mtime = 0, 0, start_mtime
    try:
        with os.scandir(path) as it:
            for entry in it:
                if entry.name.lower() in _SKIPPED_FILE_NAMES:
                    continue
                if entry.is_symlink():
                    continue
                if entry.is_file():
                    file_count += 1
                    try:
                        stat = entry.stat(follow_symlinks=False)
                        total_bytes += stat.st_size
                        max_mtime = max(max_mtime, stat.st_mtime)
                    except OSError:
                        pass
                elif entry.is_dir(follow_symlinks=False):
                    sub_bytes, sub_files, sub_mtime = _walk_profile_stats_recursive(entry.path, max_mtime)
                    total_bytes += sub_bytes
                    file_count += sub_files
                    max_mtime = max(max_mtime, sub_mtime)
    except OSError:
        pass
    return total_bytes, file_count, max_mtime


def _has_any_file(root: Path) -> bool:
    """Cheaply check whether *root* holds at least one real file anywhere in
    its tree, stopping at the first match instead of walking everything.

    Used during discovery to decide whether a RAIZ/profile folder has
    anything restorable, without paying for a full recursive size count.
    """
    try:
        with os.scandir(root) as it:
            for entry in it:
                if entry.name.lower() in _SKIPPED_FILE_NAMES:
                    continue
                if entry.is_symlink():
                    continue
                if entry.is_file():
                    return True
                if entry.is_dir(follow_symlinks=False):
                    if _has_any_file(Path(entry.path)):
                        return True
    except OSError:
        pass
    return False


def _peek_raiz(raiz_path: Path) -> Optional[RaizDetail]:
    """Cheap RAIZ existence probe for discovery: confirms there's at least
    one real file without computing exact size. The exact size is filled in
    later via get_raiz_detail(), once the admin actually selects the source.
    """
    if not raiz_path.is_dir() or not _has_any_file(raiz_path):
        return None
    return RaizDetail(size_bytes=0, file_count=PENDING_STATS, dir_count=PENDING_STATS, path=raiz_path)


def _peek_profile(user_path: Path) -> Optional[UserProfileDetail]:
    """Cheap profile existence probe for discovery — see _peek_raiz()."""
    if not _has_any_file(user_path):
        return None
    return UserProfileDetail(
        name=user_path.name, size_bytes=0, modified_time=_safe_mtime(user_path),
        path=user_path, file_count=PENDING_STATS,
    )


def load_source_details(
    source: AdminBackupSource,
    progress_cb: Optional[Callable[[AdminBackupSource], None]] = None,
) -> AdminBackupSource:
    """Compute exact sizes for *source*'s RAIZ and profiles in parallel.

    Discovery only proves a source has *something* restorable — this is the
    only place that pays for walking every file. Progressive updates are
    reported via *progress_cb* as individual parallel walks complete.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from config import MAX_CONCURRENT_DISCOVERY_TASKS

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DISCOVERY_TASKS) as executor:
        futures = {}
        if source.raiz:
            futures[executor.submit(get_raiz_detail, source.path / "RAIZ")] = "raiz"
        for p in source.profiles:
            futures[executor.submit(get_profile_detail, p.path)] = p.name

        completed_profiles = {p.name: p for p in source.profiles}
        raiz_detail = source.raiz

        for future in as_completed(futures):
            key = futures[future]
            try:
                res = future.result()
            except Exception:
                if key == "raiz":
                    res = RaizDetail(size_bytes=0, file_count=ERROR_STATS, dir_count=ERROR_STATS, path=source.path / "RAIZ")
                else:
                    original_p = next(p for p in source.profiles if p.name == key)
                    res = replace(original_p, size_bytes=0, file_count=ERROR_STATS)

            if key == "raiz":
                raiz_detail = res
            else:
                # get_profile_detail() (and the except-branch fallback above)
                # always return a UserProfileDetail, never None.
                completed_profiles[key] = res

            if progress_cb:
                current_profiles = list(completed_profiles.values())
                current_total = 0
                if raiz_detail and raiz_detail.size_bytes != PENDING_STATS and raiz_detail.size_bytes != ERROR_STATS:
                    current_total += raiz_detail.size_bytes
                for p in current_profiles:
                    if p.size_bytes != PENDING_STATS and p.size_bytes != ERROR_STATS:
                        current_total += p.size_bytes
                progress_cb(replace(source, raiz=raiz_detail, profiles=current_profiles, total_bytes=current_total))

        # Final result
        final_profiles = [p for p in completed_profiles.values() if p.file_count > 0 or p.file_count == ERROR_STATS]
        final_total = 0
        if raiz_detail and raiz_detail.size_bytes != ERROR_STATS:
            final_total += raiz_detail.size_bytes
        final_total += sum(p.size_bytes for p in final_profiles if p.size_bytes != ERROR_STATS)
        return replace(source, raiz=raiz_detail, profiles=final_profiles, total_bytes=final_total)


def get_raiz_detail(raiz_path: Path) -> Optional[RaizDetail]:
    """Calculate stats for RAIZ directory. Returns None if it holds no actual
    files (e.g. only empty subfolders) — there would be nothing to restore."""
    if not raiz_path.is_dir():
        return None
    bytes_sz, files, dirs, max_m = _walk_stats_recursive(raiz_path)
    if files == 0:
        return None
    if max_m == 0.0:
        max_m = _safe_mtime(raiz_path)
    return RaizDetail(size_bytes=bytes_sz, file_count=files, dir_count=dirs, path=raiz_path, modified_time=max_m)


def get_profile_detail(user_path: Path) -> UserProfileDetail:
    """Calculate stats for a single user profile."""
    name = user_path.name
    total_bytes, file_count, mtime = _walk_profile_stats_recursive(user_path, 0.0)
    if mtime == 0.0:
        mtime = _safe_mtime(user_path)
    return UserProfileDetail(
        name=name, size_bytes=total_bytes, modified_time=mtime, path=user_path, file_count=file_count,
    )


def _find_user_profiles(usuarios_path: Path) -> list[UserProfileDetail]:
    """Return profile folders that hold at least one actual file — folders
    containing only empty subfolders have nothing to restore and are skipped.

    Uses the cheap _peek_profile() probe rather than a full size walk; exact
    sizes are computed later via load_source_details(), once selected.
    """
    profiles = []
    if not usuarios_path.is_dir():
        return profiles
    try:
        for folder in usuarios_path.iterdir():
            if folder.is_dir() and folder.name.lower() not in {"administrador", "administrator"}:
                detail = _peek_profile(folder)
                if detail:
                    profiles.append(detail)
    except OSError:
        pass
    return profiles


def build_admin_source(candidate: Path, origin: str) -> Optional[AdminBackupSource]:
    """Build AdminBackupSource metadata from candidate path.

    Only proves the source has restorable content (cheap probes) — exact
    total size is left as PENDING_STATS and computed lazily via
    load_source_details() once the admin actually selects this source, so a
    broad search doesn't pay for statting every match's full history.
    """
    if not candidate.is_dir():
        return None
    raiz = _peek_raiz(candidate / "RAIZ")
    profiles = _find_user_profiles(candidate / "USUARIOS")
    if not raiz and not profiles:
        return None
    total = PENDING_STATS
    mid = _extract_id_from_folder(candidate.name)
    return AdminBackupSource(
        path=candidate,
        name=candidate.name,
        origin=origin,
        machine_id=mid,
        total_bytes=total,
        raiz=raiz,
        profiles=profiles,
    )


def _source_matches_terms(source: AdminBackupSource, terms: set[str]) -> bool:
    """True if *source*'s own name or any of its (already content-filtered)
    profiles matches one of *terms* — used to re-validate a query match
    after empty profiles have been filtered out of the built source."""
    name_lower = source.name.lower()
    if any(term in name_lower for term in terms):
        return True
    return any(term in p.name.lower() for p in source.profiles for term in terms)


def _origin_for(path: Path) -> str:
    """Classify a candidate path as "network" (UNC share) or "local" drive."""
    return "network" if path.drive.startswith("\\\\") else "local"


def _is_backup_root(path: Path) -> bool:
    try:
        return (path / "USUARIOS").is_dir() or (path / "RAIZ").is_dir()
    except OSError:
        return False


def _list_dirs(root: Path) -> list[Path]:
    """List immediate subdirectories of *root* (single directory listing)."""
    try:
        return [d for d in root.iterdir() if d.is_dir()]
    except OSError:
        return []


def _find_network_candidates(
    server_ip: str, share: str, listing: Optional[list[Path]] = None,
) -> list[Path]:
    """Return network-share folders that follow the RAIZ/USUARIOS convention.

    *listing* lets callers reuse an already-fetched directory listing instead
    of hitting the (potentially slow) network share again.
    """
    dirs = listing if listing is not None else _list_dirs(Path(f"\\\\{server_ip}\\{share}"))
    return [d for d in dirs if _is_backup_root(d)]


def _find_local_candidates() -> list[Path]:
    candidates = []
    for drive in get_local_drives():
        try:
            for entry in drive.iterdir():
                if entry.name.lower() in _LOCAL_EXCLUDE:
                    continue
                if entry.is_dir() and _is_backup_root(entry):
                    candidates.append(entry)
                try:
                    for sub in entry.iterdir():
                        if sub.is_dir() and _is_backup_root(sub):
                            candidates.append(sub)
                except OSError:
                    pass
        except OSError:
            pass
    return candidates


def _find_flat_profile_matches(
    server_ip: str, share: str, query_lower: str, listing: Optional[list[Path]] = None,
) -> list[AdminBackupSource]:
    """Scan network folders without RAIZ/USUARIOS (e.g. 'Backuphelpdesk') for a
    profile folder directly nested one level down that matches *query_lower*.

    Some technicians drop ad-hoc backups straight under the share (no RAIZ/
    USUARIOS convention), so the standard candidate scan never sees them.
    *listing* lets callers reuse an already-fetched directory listing.
    """
    dirs = listing if listing is not None else _list_dirs(Path(f"\\\\{server_ip}\\{share}"))
    matches: list[AdminBackupSource] = []
    folders = [d for d in dirs if not _is_backup_root(d)]

    for folder in folders:
        try:
            subs = [s for s in folder.iterdir() if s.is_dir() and query_lower in s.name.lower()]
        except OSError:
            continue
        if not subs:
            continue
        profiles = [p for p in (_peek_profile(s) for s in subs) if p]
        if not profiles:
            continue
        matches.append(AdminBackupSource(
            path=folder,
            name=folder.name,
            origin="network",
            machine_id="",
            total_bytes=PENDING_STATS,
            raiz=None,
            profiles=profiles,
        ))
    return matches


def get_local_user_profiles() -> list[str]:
    """Retrieve all Windows user profiles on the machine (excluding system/admin)."""
    profiles_root = Path("C:\\Users")
    if not profiles_root.is_dir():
        return []
    excluded = {
        "public", "default", "default user", "all users",
        "administrador", "administrator", "system", "networkservice",
        "localservice", "lello"
    }
    profiles = []
    try:
        for entry in profiles_root.iterdir():
            if entry.is_dir() and entry.name.lower() not in excluded:
                profiles.append(entry.name)
    except OSError:
        pass
    return profiles


def _mock_admin_sources() -> list[AdminBackupSource]:
    """Return mock AdminBackupSource list for visual validation."""
    return [
        AdminBackupSource(
            path=Path("C:/OS_5_PMC_600259"),
            name="OS_5_PMC_600259",
            origin="network",
            machine_id="600259",
            total_bytes=3500000000,
            raiz=RaizDetail(
                size_bytes=500000000,
                file_count=12,
                dir_count=3,
                path=Path("C:/OS_5_PMC_600259/RAIZ")
            ),
            profiles=[
                UserProfileDetail(
                    name="14029",
                    size_bytes=2000000000,
                    modified_time=1719100000.0,
                    path=Path("C:/OS_5_PMC_600259/USUARIOS/14029")
                ),
                UserProfileDetail(
                    name="12345",
                    size_bytes=1000000000,
                    modified_time=1719110000.0,
                    path=Path("C:/OS_5_PMC_600259/USUARIOS/12345")
                )
            ]
        ),
        AdminBackupSource(
            path=Path("D:/OS_6_PMC_700123"),
            name="OS_6_PMC_700123",
            origin="local",
            machine_id="700123",
            total_bytes=1200000000,
            raiz=None,
            profiles=[
                UserProfileDetail(
                    name="14029",
                    size_bytes=1200000000,
                    modified_time=1719120000.0,
                    path=Path("D:/OS_6_PMC_700123/USUARIOS/14029")
                )
            ]
        )
    ]


def scan_admin_backups(
    server_ip: str,
    share: str,
    custom_query: Optional[str] = None,
    stage_cb: Optional[StageCallback] = None,
    cancel_event: Optional[Event] = None,
) -> Generator[AdminBackupSource, None, None]:
    """Incremental generator yielding discovered admin backup sources.

    When *custom_query* is given, discovery scans ONLY for that query — the
    machine-id/local-profile fallback stages are skipped so an explicit
    search never surfaces unrelated machines ahead of (or instead of) the
    thing the admin typed.

    *cancel_event*, if set, stops the scan at the next checkpoint — used so
    starting a new search doesn't leave the previous one still grinding
    through the network share in the background.
    """
    from config import is_test_mode
    if is_test_mode():
        for src in _mock_admin_sources():
            yield src
        return

    def cancelled() -> bool:
        return cancel_event is not None and cancel_event.is_set()

    if cancelled():
        return

    # Phase 1: Gather all candidates (single directory listing of the network
    # share, reused below for the flat-folder query fallback to avoid a
    # second network round trip).
    # The cache is skipped under a test runner so each test starts from a
    # clean candidate list instead of leaking state from a previous test's
    # (possibly mocked) network scan into this process's shared cache.
    from config import get_discovery_cache_ttl_seconds
    is_testing = _is_running_under_test_runner()
    cache_key = (server_ip, share)
    now = time.time()
    cache_ttl = get_discovery_cache_ttl_seconds()
    if not is_testing and cache_key in _DISCOVERY_CACHE and (now - _DISCOVERY_CACHE[cache_key][0]) < cache_ttl:
        _, candidates, network_listing = _DISCOVERY_CACHE[cache_key]
        candidates = list(candidates)  # shallow copy
    else:
        network_listing = _list_dirs(Path(f"\\\\{server_ip}\\{share}"))
        candidates = _find_network_candidates(server_ip, share, listing=network_listing)
        candidates.extend(_find_local_candidates())
        if not is_testing:
            _DISCOVERY_CACHE[cache_key] = (now, list(candidates), network_listing)

    yielded_paths: set[Path] = set()

    # Helper to build, cache, and yield
    def build_and_yield(
        path: Path, origin: str, query_terms: Optional[set[str]] = None,
    ) -> Generator[AdminBackupSource, None, None]:
        if path in yielded_paths:
            return
        src = build_admin_source(path, origin)
        if not src:
            return
        if query_terms is not None and not _source_matches_terms(src, query_terms):
            # The folder name that triggered the match (e.g. a USUARIOS
            # subfolder named "lello") turned out to hold no real files and
            # was filtered out — nothing here actually answers the search,
            # so don't surface an unrelated/empty source as a "result".
            return
        yielded_paths.add(path)
        yield src

    if custom_query:
        if cancelled():
            return
        if stage_cb:
            stage_cb(STAGE_QUERY)
        q = custom_query.lower()
        # Admins often search by hostname (e.g. "25STI3T125678") rather than
        # by the backup folder's own naming convention (e.g.
        # "OS_5GLPI30327_PMC_125678") — extract the machine id the same way
        # the automatic hostname-match stage does, so both work.
        q_machine = extract_machine_id(custom_query).lower()
        query_terms = {q} | ({q_machine} if q_machine else set())

        for path in candidates:
            if cancelled():
                return
            # Check if query matches folder name or is subfolder profile name
            name_lower = path.name.lower()
            match = any(term in name_lower for term in query_terms)
            if not match:
                usuarios_dir = path / "USUARIOS"
                if usuarios_dir.is_dir():
                    try:
                        match = any(
                            term in sub.name.lower()
                            for sub in usuarios_dir.iterdir() if sub.is_dir()
                            for term in query_terms
                        )
                    except OSError:
                        pass
            if match:
                yield from build_and_yield(path, _origin_for(path), query_terms=query_terms)

        if cancelled():
            return
        for src in _find_flat_profile_matches(server_ip, share, q, listing=network_listing):
            if cancelled():
                return
            if src.path not in yielded_paths:
                yielded_paths.add(src.path)
                yield src
        return

    # Stage 1: Match by machine ID from hostname
    if stage_cb:
        stage_cb(STAGE_MACHINE)
    hostname = socket.gethostname()
    machine_id = extract_machine_id(hostname)
    if machine_id:
        for path in candidates:
            if cancelled():
                return
            if machine_id.lower() in path.name.lower():
                yield from build_and_yield(path, _origin_for(path))

    # Stage 2: Match by local user profiles if no machine ID match was found
    if not yielded_paths:
        local_profiles = get_local_user_profiles()
        current_user = detect_user_login()
        if current_user in local_profiles:
            local_profiles.remove(current_user)
            local_profiles.insert(0, current_user)  # prioritize current user
        for i, profile in enumerate(local_profiles):
            if cancelled():
                return
            if stage_cb:
                stage_cb(STAGE_CURRENT_USER if i == 0 else STAGE_MACHINE_USERS)
            for path in candidates:
                if cancelled():
                    return
                usuarios_dir = path / "USUARIOS" / profile
                if usuarios_dir.is_dir():
                    yield from build_and_yield(path, _origin_for(path))


def compile_admin_restore_files(
    source: AdminBackupSource,
    scope: str,
    profile_name: Optional[str] = None,
) -> list[MergedFile]:
    """Compile the list of MergedFiles based on selected admin scope."""
    files = []
    if scope in ("raiz", "all") and source.raiz:
        files.extend(_scan_raiz_files(source.path / "RAIZ"))

    profiles_to_scan = []
    if scope == "all":
        profiles_to_scan = source.profiles
    elif scope == "profile" and profile_name:
        profiles_to_scan = [p for p in source.profiles if p.name == profile_name]

    for p in profiles_to_scan:
        files.extend(_scan_profile_files(p))
    from services.backup_merger import filter_contacts_folder
    return filter_contacts_folder(files)


def _scan_dir_files_recursive(
    current_dir: Path,
    base_dir: Path,
    dest_folder: str,
    target_profile: Optional[str]
) -> list[MergedFile]:
    files = []
    try:
        with os.scandir(current_dir) as it:
            for entry in it:
                if entry.name.lower() in _SKIPPED_FILE_NAMES:
                    continue
                if entry.is_symlink():
                    continue
                if entry.is_file():
                    try:
                        stat = entry.stat(follow_symlinks=False)
                        entry_path = Path(entry.path)
                        files.append(MergedFile(
                            source_path=entry_path,
                            dest_folder=dest_folder,
                            relative_name=entry_path.relative_to(base_dir).as_posix(),
                            size_bytes=stat.st_size,
                            modified_time=stat.st_mtime,
                            target_profile=target_profile,
                        ))
                    except OSError:
                        pass
                elif entry.is_dir(follow_symlinks=False):
                    files.extend(_scan_dir_files_recursive(
                        Path(entry.path), base_dir, dest_folder, target_profile
                    ))
    except OSError:
        pass
    return files


def _scan_raiz_files(raiz_path: Path) -> list[MergedFile]:
    if not raiz_path.is_dir():
        return []
    return _scan_dir_files_recursive(raiz_path, raiz_path, "RAIZ", None)


def _scan_profile_files(profile: UserProfileDetail) -> list[MergedFile]:
    files = []
    usuarios_dir = profile.path
    if not usuarios_dir.is_dir():
        return files
    tgt_profile = None if profile.name == detect_user_login() else profile.name
    try:
        with os.scandir(usuarios_dir) as it:
            for folder_entry in it:
                if folder_entry.is_symlink():
                    continue
                if folder_entry.is_dir(follow_symlinks=False):
                    folder_path = Path(folder_entry.path)
                    files.extend(_scan_dir_files_recursive(
                        folder_path, folder_path, folder_entry.name, tgt_profile
                    ))
    except OSError:
        pass
    return files
