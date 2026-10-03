#!/usr/bin/env bash
# Build with a Python installation that includes Tk (Homebrew Python on macOS).
set -euo pipefail
cd "$(dirname "$0")"
if [ -z "${BUILD_PYTHON:-}" ]; then
    if [ -x .venv/bin/python ]; then
        BUILD_PYTHON=.venv/bin/python
    else
        BUILD_PYTHON=python3
    fi
fi
"$BUILD_PYTHON" -c 'import tkinter'
"$BUILD_PYTHON" -m pip show pyinstaller Pillow >/dev/null 2>&1 || "$BUILD_PYTHON" -m pip install -r requirements.txt

if [ "$(uname -s)" = "Darwin" ]; then
    mkdir -p build
    "$BUILD_PYTHON" -c 'from PIL import Image; Image.open("logo.png").convert("RGBA").save("build/logo.icns")'
    "$BUILD_PYTHON" -m PyInstaller --noconfirm --onedir --windowed \
        --name GitArchiveGenerator --osx-bundle-identifier com.ekosiswoyo.gitarchivegenerator \
        --icon build/logo.icns --add-data "logo.png:." git_archive_ui.py
    echo "App: dist/GitArchiveGenerator.app"
else
    "$BUILD_PYTHON" -m PyInstaller --noconfirm --onefile --windowed \
        --name GitArchiveGenerator --add-data "logo.png:." git_archive_ui.py
    echo "Executable: dist/GitArchiveGenerator"
fi
