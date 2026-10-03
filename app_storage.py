"""Stable per-user storage shared by source and packaged application."""
import os
import sys
from pathlib import Path


def data_directory():
    if sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    elif os.name == 'nt':
        base = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local' / 'share'))
    return base / 'GitArchiveGenerator'


def legacy_paths(filename):
    """Check the old working directory and source/executable directory."""
    base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    return list(dict.fromkeys([Path.cwd() / filename, base / filename]))
