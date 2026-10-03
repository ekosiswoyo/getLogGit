import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import app_storage


class PlatformStorageTests(unittest.TestCase):
    def test_macos_storage(self):
        with patch.object(app_storage.sys, 'platform', 'darwin'):
            self.assertEqual(app_storage.data_directory(), Path.home() / 'Library/Application Support/GitArchiveGenerator')

    def test_windows_uses_appdata(self):
        with patch.object(app_storage.sys, 'platform', 'win32'), patch.object(
                app_storage, 'os', SimpleNamespace(name='nt', environ={'APPDATA': '/test/Roaming'})):
            self.assertEqual(app_storage.data_directory(), Path('/test/Roaming/GitArchiveGenerator'))

    def test_linux_uses_xdg(self):
        with patch.object(app_storage.sys, 'platform', 'linux'), patch.object(
                app_storage, 'os', SimpleNamespace(name='posix', environ={'XDG_DATA_HOME': '/test/data'})):
            self.assertEqual(app_storage.data_directory(), Path('/test/data/GitArchiveGenerator'))
