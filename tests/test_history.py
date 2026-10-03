import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from history_manager import HistoryManager
from git_archive_ui import App


class HistoryTests(unittest.TestCase):
    def test_persists_nested_path_and_option(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'nested' / 'history.json'
            manager = HistoryManager(path)
            manager.add_entry('/repo', '/output.zip', 'sha_range', {'exclude_start': True})
            restored = HistoryManager(path).get_entry(0)
            self.assertEqual(restored['output_path'], '/output.zip')
            self.assertTrue(restored['parameters']['exclude_start'])
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_legacy_migration_and_stable_location(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / 'old.json'
            legacy.write_text(json.dumps([{'repo_path': '/legacy'}]))
            with patch('history_manager.data_directory', return_value=root / 'data'), patch(
                    'history_manager.legacy_paths', return_value=[legacy]):
                manager = HistoryManager()
                self.assertEqual(manager.get_entry(0)['repo_path'], '/legacy')
                legacy.write_text('[]')
                self.assertEqual(HistoryManager().get_entry(0)['repo_path'], '/legacy')

    def test_write_errors_are_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = HistoryManager(Path(directory) / 'history.json')
            with patch('history_manager.os.replace', side_effect=PermissionError('denied')):
                with self.assertRaises(PermissionError):
                    manager.add_entry('/repo', '/out', 'date', {})
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_completion_saves_before_success_dialog(self):
        app = Mock()
        app.C = {}
        request = {'repo_path': '/original'}
        with patch('git_archive_ui.messagebox.askyesno', return_value=False) as dialog:
            App._handle_complete(app, dict(success=True, request=request, archive_path='/output.zip'))
            app.save_to_history.assert_called_once_with(request, '/output.zip')
            app._refresh_recent_repos.assert_called_once()
            dialog.assert_called_once()

    def test_history_uses_request_snapshot(self):
        app = Mock()
        request = dict(repo_path='/original', output_zip='/requested.zip', mode='sha_range',
                       exclude_start=True, start_sha='12345678', changelog_format='md')
        App.save_to_history(app, request, '/actual.zip')
        entry = app.history_manager.add_entry.call_args.kwargs
        self.assertEqual(entry['repo_path'], '/original')
        self.assertEqual(entry['output_path'], '/actual.zip')
        self.assertTrue(entry['parameters']['exclude_start'])
        self.assertEqual(entry['parameters']['changelog_format'], 'md')


if __name__ == '__main__':
    unittest.main()
