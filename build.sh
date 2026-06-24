#!/usr/bin/env bash
# Build Git Archive Generator executable on Linux/macOS.
set -e

echo "Building Git Archive Generator..."

# Ensure dependencies
python3 -m pip show pyinstaller >/dev/null 2>&1 || python3 -m pip install pyinstaller
python3 -m pip show Pillow >/dev/null 2>&1 || python3 -m pip install Pillow

# Generate .ico (harmless on Linux; used if you later build for Windows)
if [ -f logo.png ] && [ ! -f logo.ico ]; then
    echo "Converting logo.png to logo.ico..."
    python3 convert_icon.py || true
fi

echo "Creating executable..."
python3 -m PyInstaller --onefile --windowed --name GitArchiveGenerator \
    --add-data "logo.png:." \
    git_archive_ui.py

echo ""
echo "Build successful!"
echo "Executable is located at: dist/GitArchiveGenerator"
