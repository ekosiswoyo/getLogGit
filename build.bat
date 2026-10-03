@echo off
echo Building Git Archive Generator Windows Executable...
echo.

REM Check if PyInstaller is installed
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    python -m pip install pyinstaller
)

REM Check if Pillow is installed (needed for icon conversion)
python -m pip show Pillow >nul 2>&1
if errorlevel 1 (
    echo Pillow not found. Installing...
    python -m pip install Pillow
)

REM Convert logo.png to logo.ico if needed
if exist logo.png (
    if not exist logo.ico (
        echo Converting logo.png to logo.ico...
        python convert_icon.py
    )
)

echo.
echo Creating executable...
python -m PyInstaller --noconfirm --onefile --windowed --name GitArchiveGenerator --icon logo.ico --add-data "logo.png;." git_archive_ui.py

if errorlevel 1 (
    echo.
    echo Build failed!
    pause
    exit /b 1
)

echo.
echo Build successful!
echo Executable is located in: dist\GitArchiveGenerator.exe
echo.
pause

