import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from git_archive_by_date import archive_git_history, get_file_list_preview


class ShaRangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.com')
        self.shas = []
        for letter in 'CDEF':
            (self.repo / f'{letter}.txt').write_text(letter)
            self.git('add', '.')
            self.git('commit', '-qm', letter)
            self.shas.append(self.git('rev-parse', 'HEAD'))

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.repo, text=True).strip()

    def params(self, start=0, end=3, exclude=False):
        return dict(repo_path=str(self.repo), mode='sha_range',
                    start_sha=self.shas[start], end_sha=self.shas[end],
                    exclude_start=exclude)

    def test_inclusive_and_exclusive_root(self):
        for excluded, expected in ((False, ['C.txt', 'D.txt', 'E.txt', 'F.txt']),
                                   (True, ['D.txt', 'E.txt', 'F.txt'])):
            result = get_file_list_preview(self.params(exclude=excluded))
            self.assertFalse(result['error'])
            self.assertEqual(result['files'], expected)
            self.assertEqual(len(result['commits_info']), len(expected))

    def test_non_root_start(self):
        result = get_file_list_preview(self.params(start=1, exclude=True))
        self.assertEqual(result['files'], ['E.txt', 'F.txt'])
        self.assertEqual(len(result['commits_info']), 2)

    def test_same_endpoints(self):
        self.assertEqual(get_file_list_preview(self.params(start=1, end=1))['files'], ['D.txt'])
        result = get_file_list_preview(self.params(start=1, end=1, exclude=True))
        self.assertEqual(result['files'], [])
        self.assertEqual(result['commits_info'], [])

    def test_archive_and_changelog_exclude_start(self):
        output = self.repo / 'release.zip'
        params = self.params(exclude=True)
        params.update(output_zip=str(output), log_callback=lambda message: None)
        archive_git_history(params)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(sorted(archive.namelist()), ['D.txt', 'E.txt', 'F.txt'])
        changelog = (self.repo / 'release.txt').read_text()
        self.assertIn('start excluded', changelog)
        self.assertNotIn('C.txt', changelog)


if __name__ == '__main__':
    unittest.main()
