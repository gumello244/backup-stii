@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0.."
set PYTHON=venv\Scripts\python.exe

if not exist %PYTHON% (
    echo ERROR: Virtual environment not found at venv\Scripts\python.exe
    echo Please run: python -m venv venv
    pause
    exit /b 1
)

:menu
cls
echo ===================================================
echo               REMOS BUILD WIZARD
echo ===================================================
echo.
%PYTHON% dist\build.py --show-version
echo.
echo ----- VERSION MANAGEMENT -------------------------
echo 1. Show Current Version
echo 2. Bump Version (Major, Minor, Patch or Build)
echo 3. Set Custom Version String
echo ----- COMPILE ------------------------------------
echo 4. Bump Build Number + Compile with PyInstaller
echo 5. Bump Build Number + Compile with Nuitka
echo 6. Compile with PyInstaller  (no version change)
echo 7. Compile with Nuitka       (no version change)
echo --------------------------------------------------
echo 8. Exit
echo.
set /p opt="Enter choice (1-8): "

if "%opt%"=="1" (
    cls
    %PYTHON% dist\build.py --show-version
    echo.
    pause
    goto menu
)
if "%opt%"=="2" (
    cls
    echo ===================================================
    echo                   BUMP VERSION
    echo ===================================================
    echo 1. Major  ^(X+1^).0.0
    echo 2. Minor  X.^(Y+1^).0
    echo 3. Patch  X.Y.^(Z+1^)
    echo 4. Build  build number only
    echo 5. Cancel
    echo.
    set /p bopt="Enter choice (1-5): "
    if "!bopt!"=="1" %PYTHON% dist\build.py --bump major
    if "!bopt!"=="2" %PYTHON% dist\build.py --bump minor
    if "!bopt!"=="3" %PYTHON% dist\build.py --bump patch
    if "!bopt!"=="4" %PYTHON% dist\build.py --bump build
    echo.
    pause
    goto menu
)
if "%opt%"=="3" (
    cls
    echo ===================================================
    echo               SET CUSTOM VERSION
    echo ===================================================
    set /p customver="Enter version string (e.g. 1.2.0): "
    %PYTHON% dist\build.py --set-version !customver!
    echo.
    pause
    goto menu
)
if "%opt%"=="4" (
    cls
    echo ===================================================
    echo    BUMP BUILD + COMPILE WITH PYINSTALLER
    echo ===================================================
    %PYTHON% dist\build.py --bump build
    %PYTHON% dist\build.py --pyinstaller
    echo.
    pause
    goto menu
)
if "%opt%"=="5" (
    cls
    echo ===================================================
    echo       BUMP BUILD + COMPILE WITH NUITKA
    echo ===================================================
    %PYTHON% dist\build.py --bump build
    %PYTHON% dist\build.py --nuitka
    echo.
    pause
    goto menu
)
if "%opt%"=="6" (
    cls
    echo ===================================================
    echo           COMPILE WITH PYINSTALLER
    echo ===================================================
    %PYTHON% dist\build.py --pyinstaller
    echo.
    pause
    goto menu
)
if "%opt%"=="7" (
    cls
    echo ===================================================
    echo              COMPILE WITH NUITKA
    echo ===================================================
    %PYTHON% dist\build.py --nuitka
    echo.
    pause
    goto menu
)
if "%opt%"=="8" (
    echo Exiting wizard.
    exit /b 0
)

echo.
echo Invalid option. Please enter a number between 1 and 8.
pause
goto menu
