from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from typing import Tuple

# Ensure execution from project root if build.py is inside dist/
_script_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(_script_dir) == "dist":
    os.chdir(os.path.dirname(_script_dir))


def parse_version_tuple(version_str: str) -> Tuple[int, int, int, int]:
    """Parse semver string like '1.1.0' into 4-integer tuple (major, minor, patch, build)."""
    parts = version_str.split(".")
    try:
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return (major, minor, patch, 0)
    except ValueError as err:
        raise ValueError(
            f"Invalid version format: '{version_str}'. Expected 'X.Y.Z' format."
        ) from err


def read_version_info() -> Tuple[str, int]:
    """Read APP_VERSION and BUILD_NUMBER from config.py without importing it."""
    config_path = "config.py"
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    app_version_match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', content)
    build_number_match = re.search(r'BUILD_NUMBER\s*=\s*(\d+)', content)

    if not app_version_match or not build_number_match:
        raise ValueError(
            "Could not parse APP_VERSION or BUILD_NUMBER from config.py. "
            'Expected APP_VERSION = "X.Y.Z" and BUILD_NUMBER = N.'
        )

    return app_version_match.group(1), int(build_number_match.group(1))


def _bump_semver(current_version: str, level: str) -> str:
    """Helper to bump major, minor, or patch version component."""
    parts = current_version.split(".")
    if len(parts) != 3:
        raise ValueError(
            f"Invalid current version: '{current_version}'. "
            "Expected 'major.minor.patch' format (e.g. '1.1.0')."
        )
    try:
        major, minor, patch = map(int, parts)
    except ValueError as err:
        raise ValueError(
            f"Non-integer components in version: '{current_version}'. "
            "Expected 'major.minor.patch' with integer values."
        ) from err

    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def bump_version(current_version: str, current_build: int, level: str) -> Tuple[str, int]:
    """Bump the version string and build number."""
    if level == "build":
        return current_version, current_build + 1
    new_version = _bump_semver(current_version, level)
    return new_version, current_build + 1


def update_config_file(app_version: str, build_number: int) -> None:
    """Update APP_VERSION and BUILD_NUMBER variables in config.py."""
    config_path = "config.py"
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    content = re.sub(r'(APP_VERSION\s*=\s*)"[^"]*"', f'\\g<1>"{app_version}"', content)
    content = re.sub(r'(BUILD_NUMBER\s*=\s*)\d+', f'\\g<1>{build_number}', content)

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(content)


def generate_version_info_content(app_version: str, build_number: int) -> str:
    """Generate the VSVersionInfo file contents for Windows executable versioning."""
    prod_tuple = parse_version_tuple(app_version)
    file_tuple = (build_number, 0, 0, 0)

    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={file_tuple},
    prodvers={prod_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'STII'),
         StringStruct(u'FileDescription', u'Recuperação de Backups'),
         StringStruct(u'FileVersion', u'{build_number}.0.0'),
         StringStruct(u'InternalName', u'Remos'),
         StringStruct(u'LegalCopyright', u'2026 © STII'),
         StringStruct(u'OriginalFilename', u'Remos.exe'),
         StringStruct(u'ProductName', u'Remos'),
         StringStruct(u'ProductVersion', u'{app_version}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1046, 1200])])
  ]
)
"""


def write_version_file(app_version: str, build_number: int) -> None:
    """Write generated version info to dist/version.txt."""
    os.makedirs("dist", exist_ok=True)
    content = generate_version_info_content(app_version, build_number)
    with open("dist/version.txt", "w", encoding="utf-8") as f:
        f.write(content)


def run_pyinstaller(app_version: str) -> int:
    """Execute PyInstaller build using the current venv's Python."""
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", f"Remos {app_version}",
        "--distpath", "dist/pyinstaller",
        "--workpath", "build/pyinstaller",
        "--specpath", "build/pyinstaller",
        "--add-data", "ui/assets;ui/assets",
        "--icon", "ui/assets/icon.ico",
        "--version-file=dist/version.txt",
        "main.py"
    ]
    return subprocess.call(cmd)


def run_nuitka(app_version: str) -> int:
    """Execute Nuitka build using the current venv's Python."""
    cmd = [
        sys.executable, "-m", "nuitka",
        "--mingw64", "--onefile", "--disable-cache=all", "--standalone",
        "--enable-plugin=pyqt5",
        "--windows-console-mode=disable",
        "--windows-icon-from-ico=ui\\assets\\icon.ico",
        "--include-data-dir=ui\\assets=ui\\assets",
        "--output-dir=dist/nuitka",
        f"--output-filename=Remos {app_version}.exe",
        "main.py"
    ]
    return subprocess.call(cmd)


def handle_version_update(app_version: str, build_number: int) -> None:
    """Update version configuration files and regenerate version.txt."""
    update_config_file(app_version, build_number)
    write_version_file(app_version, build_number)
    print(f"Updated config.py and version.txt to version {app_version} (Build {build_number})")


def handle_bump(bump_level: str) -> None:
    """Read version, bump it, update files."""
    version, build = read_version_info()
    new_version, new_build = bump_version(version, build, bump_level)
    handle_version_update(new_version, new_build)


def handle_set_version(version_str: str) -> None:
    """Set absolute version string, bump build number."""
    _, build = read_version_info()
    parse_version_tuple(version_str)
    handle_version_update(version_str, build + 1)


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Remos Build and Versioning Script")
    parser.add_argument("--pyinstaller", action="store_true", help="Build with PyInstaller")
    parser.add_argument("--nuitka", action="store_true", help="Build with Nuitka")
    parser.add_argument("--set-version", type=str, help="Set application version (e.g. 1.2.0)")
    parser.add_argument("--bump", choices=["major", "minor", "patch", "build"], help="Bump version level")
    parser.add_argument("--show-version", action="store_true", help="Show current version and build number")
    return parser.parse_args()


def _handle_build_commands(args: argparse.Namespace) -> bool:
    """Execute PyInstaller or Nuitka compiler if requested."""
    if args.pyinstaller:
        version, build = read_version_info()
        write_version_file(version, build)
        exit_code = run_pyinstaller(version)
        print(f"\nPyInstaller finished with exit code {exit_code}.")
        return True
    if args.nuitka:
        version, build = read_version_info()
        write_version_file(version, build)
        exit_code = run_nuitka(version)
        print(f"\nNuitka finished with exit code {exit_code}.")
        return True
    return False


def handle_arguments(args: argparse.Namespace) -> None:
    """Execute operations based on parsed arguments."""
    if args.show_version:
        version, build = read_version_info()
        print(f"Remos Version: {version} (Build: {build})")
        return
    if args.bump:
        handle_bump(args.bump)
        return
    if args.set_version:
        handle_set_version(args.set_version)
        return
    _handle_build_commands(args)


def main() -> None:
    """Entry point for build script."""
    args = parse_arguments()
    handle_arguments(args)


if __name__ == "__main__":
    main()
