@echo off
REM Activate the virtual environment
call venv\Scripts\activate.bat

REM Run pyinstaller from the venv
python -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name "Remos" ^
  --add-data "ui/assets;ui/assets" ^
  --icon "ui/assets/icon.ico" ^
  --version-file=version.txt main.py

pause
