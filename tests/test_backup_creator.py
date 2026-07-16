from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.backup_merger import MergedFile
from services.backup_creator import (
    should_skip_file,
    resolve_backup_dest_path,
    backup_local_data,
    generate_installed_programs_report,
    generate_profile_html_tree,
)
from config import CopyRetryConfig


def test_should_skip_file() -> None:
    assert should_skip_file("desktop.ini") is True
    assert should_skip_file("thumbs.db") is True
    assert should_skip_file("music.mp3") is True
    assert should_skip_file("video.mp4") is True
    assert should_skip_file("program.exe") is True
    assert should_skip_file("document.txt") is False
    assert should_skip_file("image.png") is False


def test_resolve_backup_dest_path() -> None:
    dest_root = Path("D:/BackupTarget")
    
    # Test RAIZ file
    path1 = resolve_backup_dest_path(dest_root, "RAIZ", "Sistemas/sys.dat")
    assert path1 == Path("D:/BackupTarget/RAIZ/Sistemas/sys.dat")

    # Test Profile file
    path2 = resolve_backup_dest_path(dest_root, "Desktop", "my_shortcut.txt", "John")
    assert path2 == Path("D:/BackupTarget/USUARIOS/John/Desktop/my_shortcut.txt")


def test_generate_installed_programs_report() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        dest_root = Path(tmp_dir)
        generate_installed_programs_report(dest_root)
        
        report_file = dest_root / "Programas_Instalados.txt"
        assert report_file.exists()
        with open(report_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert "=== RELAÇÃO DE PASTAS DE PROGRAMAS" in content


def test_generate_profile_html_tree() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        dest_root = Path(tmp_dir)
        # Create some fake files and dirs
        user_dir = dest_root / "USUARIOS" / "John"
        user_dir.mkdir(parents=True, exist_ok=True)
        (user_dir / "Desktop").mkdir(exist_ok=True)
        with open(user_dir / "Desktop" / "test.txt", "w") as f:
            f.write("hello")
            
        report_file = user_dir / "Relatorio_John.html"
        generate_profile_html_tree(user_dir, report_file, "John")
        
        assert report_file.exists()
        with open(report_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert "Relatório de Backup - John" in content
        assert "test.txt" in content
