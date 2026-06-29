@echo off
REM Activate the virtual environment
call venv\Scripts\activate.bat

REM Run nuitka from the venv
python -m nuitka ^
    --mingw64 ^
    --onefile ^
    --disable-cache=all ^
    --standalone ^
    --enable-plugin=pyqt5 ^
    --windows-console-mode="disable" ^
    --windows-icon-from-ico="ui\assets\icon.ico" ^
    --include-data-dir="ui\assets"="ui\assets" ^
    --output-dir="dist-nuitka" ^
    --output-filename="Remos.exe" ^
    main.py

pause
