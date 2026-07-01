from __future__ import annotations

"""Merge multiple backup sources into a single optimal file set.

For each file found across sources, keeps the version with the most
recent modification time.  Files exclusive to one source are always
included.

Example:
    merged = merge_sources(sources)
    print(merged.total_bytes, merged.source_summary)
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple

from services.backup_discovery import BackupSource

logger = logging.getLogger(__name__)


@dataclass
class MergedFile:
    """A single file resolved after comparing all sources.

    Example:
        f = MergedFile(
            source_path=Path("\\\\...\\Desktop\\report.pdf"),
            dest_folder="Desktop", relative_name="report.pdf",
            size_bytes=2048, modified_time=1719100000.0,
        )
    """
    source_path: Path
    dest_folder: str
    relative_name: str
    size_bytes: int
    modified_time: float


@dataclass
class FolderSummary:
    """Aggregate stats for one destination folder.

    Example:
        fs = FolderSummary(file_count=10, total_bytes=4096)
    """
    file_count: int
    total_bytes: int


@dataclass
class MergedFileSet:
    """Complete merge result with per-folder breakdown.

    Example:
        ms = merge_sources(sources)
        for folder, summary in ms.by_folder.items():
            print(folder, summary.file_count)
    """
    files: list[MergedFile]
    total_bytes: int
    by_folder: dict[str, FolderSummary] = field(default_factory=dict)
    source_summary: str = ""


@dataclass
class _FileEntry:
    """Internal index entry for one file inside a source."""
    source_path: Path
    modified_time: float
    size_bytes: int


# Key: (dest_folder, relative_name_posix)
_IndexKey = Tuple[str, str]


def _index_source(source: BackupSource) -> dict[_IndexKey, _FileEntry]:
    """Walk *source.path* and index every file by (folder, relname).

    Example:
        idx = _index_source(source)
        # idx[("Desktop", "report.pdf")] → _FileEntry(...)
    """
    index: dict[_IndexKey, _FileEntry] = {}
    for folder_name in source.folder_list:
        if folder_name == "RAIZ":
            folder_path = source.path.parent.parent / "RAIZ"
        else:
            folder_path = source.path / folder_name

        if not folder_path.is_dir():
            continue
        _walk_folder(index, folder_path, folder_name)
    return index



def _walk_folder(
    index: dict[_IndexKey, _FileEntry],
    folder_path: Path,
    dest_folder: str,
) -> None:
    """Recursively add files from *folder_path* into *index*."""
    try:
        for entry in folder_path.rglob("*"):
            if not entry.is_file():
                continue
            if entry.name.lower() in {"desktop.ini", "thumbs.db", ".ds_store"}:
                continue
            _add_file_entry(index, entry, folder_path, dest_folder)
    except OSError:
        pass


def _add_file_entry(
    index: dict[_IndexKey, _FileEntry],
    entry: Path,
    folder_root: Path,
    dest_folder: str,
) -> None:
    """Create an index entry for a single file."""
    try:
        stat = entry.stat()
    except OSError:
        return
    rel = entry.relative_to(folder_root).as_posix()
    key: _IndexKey = (dest_folder, rel)
    index[key] = _FileEntry(
        source_path=entry,
        modified_time=stat.st_mtime,
        size_bytes=stat.st_size,
    )


def _merge_indexes(
    *indexes: dict[_IndexKey, _FileEntry],
) -> dict[_IndexKey, _FileEntry]:
    """Merge multiple file indexes, keeping the newest version per key."""
    merged: dict[_IndexKey, _FileEntry] = {}
    for idx in indexes:
        for key, entry in idx.items():
            existing = merged.get(key)
            if existing is None or entry.modified_time > existing.modified_time:
                merged[key] = entry
    return merged


def _build_merged_files(
    merged_index: dict[_IndexKey, _FileEntry],
) -> list[MergedFile]:
    """Convert the merged index into a list of MergedFile objects."""
    return [
        MergedFile(
            source_path=entry.source_path,
            dest_folder=key[0],
            relative_name=key[1],
            size_bytes=entry.size_bytes,
            modified_time=entry.modified_time,
        )
        for key, entry in merged_index.items()
    ]


def group_by_folder(
    files: list[MergedFile],
) -> dict[str, FolderSummary]:
    """Group merged files by destination folder with totals.

    Example:
        by_folder = group_by_folder(merged_files)
        by_folder["Desktop"].file_count  # 42
    """
    groups: dict[str, FolderSummary] = {}
    for f in files:
        summary = groups.get(f.dest_folder)
        if summary is None:
            summary = FolderSummary(file_count=0, total_bytes=0)
            groups[f.dest_folder] = summary
        summary.file_count += 1
        summary.total_bytes += f.size_bytes
    return groups


def _determine_summary(sources: list[BackupSource]) -> str:
    """Human-readable description of which sources contributed."""
    origins = {s.origin for s in sources}
    if origins == {"network", "local"}:
        return "Mesclado (rede + local)"
    if "network" in origins:
        return "Rede"
    return "Local"


def merge_sources(sources: list[BackupSource], admin_mode: bool = False) -> MergedFileSet:
    """Merge all *sources* into a single optimal MergedFileSet.

    Example:
        result = merge_sources(discovered_sources, admin_mode=False)
        print(result.total_bytes, result.source_summary)
    """
    from config import is_test_mode
    if is_test_mode():
        return _simulate_merge_sources()

    if not sources:
        return MergedFileSet(files=[], total_bytes=0, source_summary="Nenhuma")

    from concurrent.futures import ThreadPoolExecutor
    from config import MAX_CONCURRENT_DISCOVERY_TASKS

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DISCOVERY_TASKS) as executor:
        indexes = list(executor.map(_index_source, sources))

    if not admin_mode and len(sources) > 1:
        sources, indexes = _filter_newest_source_only(sources, indexes)

    merged_index = _merge_indexes(*indexes)
    files = _build_merged_files(merged_index)
    return _build_file_set_result(files, sources)


def _filter_newest_source_only(
    sources: list[BackupSource],
    indexes: list[dict[_IndexKey, _FileEntry]],
) -> tuple[list[BackupSource], list[dict[_IndexKey, _FileEntry]]]:
    """Find and return only the source (and its index) with the newest file modification time.

    Example:
        s, idx = _filter_newest_source_only(sources, indexes)
    """
    selected_idx = 0
    max_mtime = -1.0
    for i, idx in enumerate(indexes):
        newest_mtime = max((entry.modified_time for entry in idx.values()), default=0.0)
        if newest_mtime > max_mtime:
            max_mtime = newest_mtime
            selected_idx = i
    return [sources[selected_idx]], [indexes[selected_idx]]



def _simulate_merge_sources() -> MergedFileSet:
    """Return a mock MergedFileSet for testing/visualizer mode.

    Example:
        res = _simulate_merge_sources()
    """
    files = [
        MergedFile(Path("C:/Fake/Desktop/foto_ferias.jpg"), "Desktop", "foto_ferias.jpg", 150000000, 1719100000.0),
        MergedFile(Path("C:/Fake/Desktop/planilha_orcamento.xlsx"), "Desktop", "planilha_orcamento.xlsx", 50000000, 1719110000.0),
        MergedFile(Path("C:/Fake/Documents/relatorio_anual.pdf"), "Documents", "relatorio_anual.pdf", 800000000, 1719120000.0),
        MergedFile(Path("C:/Fake/Documents/portfolio.key"), "Documents", "portfolio.key", 1200000000, 1719130000.0),
        MergedFile(Path("C:/Fake/Downloads/VSCodeUserSetup.exe"), "Downloads", "VSCodeUserSetup.exe", 300000000, 1719140000.0),
        MergedFile(Path("C:/Fake/Pictures/avatar.png"), "Pictures", "avatar.png", 50000000, 1719150000.0),
        MergedFile(Path("C:/Fake/Videos/treinamento.mp4"), "Videos", "treinamento.mp4", 1000000000, 1719160000.0),
    ]
    by_folder = group_by_folder(files)
    total = sum(f.size_bytes for f in files)
    return MergedFileSet(
        files=files,
        total_bytes=total,
        by_folder=by_folder,
        source_summary="Mesclado (rede + local - Simulado)"
    )


def _build_file_set_result(files: list[MergedFile], sources: list[BackupSource]) -> MergedFileSet:
    """Construct the final MergedFileSet and log the summary.

    Example:
        res = _build_file_set_result(files, sources)
    """
    by_folder = group_by_folder(files)
    total = sum(f.size_bytes for f in files)
    summary = _determine_summary(sources)

    logger.info(
        '{"event":"merge_complete","files":%d,"bytes":%d,"summary":"%s"}',
        len(files), total, summary,
    )
    return MergedFileSet(
        files=files,
        total_bytes=total,
        by_folder=by_folder,
        source_summary=summary,
    )

