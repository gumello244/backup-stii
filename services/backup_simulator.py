from __future__ import annotations

"""Simulation of file copy operations for visualization in test mode."""
import time
from pathlib import Path
from threading import Event

from services.backup_merger import MergedFile
from services.backup_copier import (
    CopyResult,
    SkippedFile,
    ProgressCallback,
    resolve_dest_path,
)

# Constants to replace magic numbers
_SIM_CHUNK_SIZE: int = 20 * 1024 * 1024  # 20 MB chunks
_SIM_DELAY_SMALL: float = 0.04
_SIM_DELAY_LARGE: float = 0.2


def do_simulated_copy(
    files: list[MergedFile],
    progress_cb: ProgressCallback,
    cancel_event: Event,
) -> CopyResult:
    """Simulate file copying for visualization in test mode."""
    total_bytes = sum(f.size_bytes for f in files)
    copied_bytes, actual_bytes_copied, copied_count = 0, 0, 0
    skipped: list[SkippedFile] = []
    failed: list[SkippedFile] = []

    for mf in files:
        if cancel_event.is_set():
            return CopyResult(False, copied_count, actual_bytes_copied, skipped, failed, True)

        res, actual, ok, abort = _simulate_single_file_step(
            mf, total_bytes, copied_bytes, progress_cb, skipped, failed, cancel_event
        )
        if abort:
            return CopyResult(False, copied_count, actual_bytes_copied, skipped, failed, True)
        copied_bytes = res
        actual_bytes_copied += actual
        if ok:
            copied_count += 1

    return CopyResult(True, copied_count, actual_bytes_copied, skipped, failed, False)


def _simulate_single_file_step(
    mf: MergedFile,
    total_bytes: int,
    copied_bytes: int,
    progress_cb: ProgressCallback,
    skipped: list[SkippedFile],
    failed: list[SkippedFile],
    cancel_event: Event,
) -> tuple[int, int, bool, bool]:
    """Simulate single file, returning (new_copied_bytes, actual_copied_bytes, is_copied, is_aborted)."""
    dest = resolve_dest_path(mf.dest_folder, mf.relative_name, getattr(mf, "target_profile", None))

    from services.backup_copier import _is_identical
    if dest.exists() and _is_identical(mf.source_path, dest):
        copied_bytes += mf.size_bytes
        progress_cb(copied_bytes, total_bytes, mf.relative_name)
        time.sleep(_SIM_DELAY_SMALL)
        return copied_bytes, 0, False, False

    if "avatar.png" in mf.relative_name:
        skipped.append(SkippedFile(mf.source_path, dest, "já existia no destino com conteúdo diferente (Simulado)"))
        copied_bytes += mf.size_bytes
        progress_cb(copied_bytes, total_bytes, mf.relative_name)
        time.sleep(_SIM_DELAY_LARGE)
        return copied_bytes, 0, False, False

    if "treinamento.mp4" in mf.relative_name:
        failed.append(SkippedFile(mf.source_path, dest, "Erro de E/S simulado em modo teste"))
        copied_bytes += mf.size_bytes
        progress_cb(copied_bytes, total_bytes, mf.relative_name)
        time.sleep(_SIM_DELAY_LARGE)
        return copied_bytes, 0, False, False

    res = _sim_chunk_loop(mf.size_bytes, copied_bytes, total_bytes, mf.relative_name, progress_cb, cancel_event)
    if res is None:
        return copied_bytes, 0, False, True
    return res, mf.size_bytes, True, False


def _sim_chunk_loop(
    file_size: int,
    copied_bytes: int,
    total_bytes: int,
    name: str,
    progress_cb: ProgressCallback,
    cancel_event: Event,
) -> int | None:
    file_copied = 0
    while file_copied < file_size:
        if cancel_event.is_set():
            return None
        to_add = min(_SIM_CHUNK_SIZE, file_size - file_copied)
        file_copied += to_add
        copied_bytes += to_add
        progress_cb(copied_bytes, total_bytes, name)
        time.sleep(_SIM_DELAY_SMALL)
    return copied_bytes
