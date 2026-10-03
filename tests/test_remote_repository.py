import base64
from datetime import date
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from git_archive_by_date import archive_git_history, get_file_list_preview, get_repository_info
from remote_repository import (authentication_environment, normalize_url, prepare_repository,
                               RemoteRepositoryError)


class RemoteTests(unittest.TestCase):
    def test_url_rejects_embedded_credentials_and_non_https(self):
        for url in ('http://git.example/repo', 'https://user:token@git.example/repo',
                    'https://git.example/repo?token=secret', 'https://git.example/repo#token'):
            with self.assertRaises(ValueError):
                normalize_url(url)
        self.assertEqual(normalize_url(' https://GitHub.com/team/repo.git/ '), 'https://github.com/team/repo.git')

    def test_token_does_not_require_helper(self):
        with patch('remote_repository.credential_manager', side_effect=AssertionError('must not need GCM')):
            env = authentication_environment('token', 'user', 'secret-token')
        settings = [(env[f'GIT_CONFIG_KEY_{i}'], env[f'GIT_CONFIG_VALUE_{i}'])
                    for i in range(int(env['GIT_CONFIG_COUNT']))]
        self.assertIn(('credential.helper', ''), settings)
        self.assertIn(('http.extraHeader', 'Authorization: Basic ' + base64.b64encode(b'user:secret-token').decode()), settings)
        self.assertEqual(env['GIT_TERMINAL_PROMPT'], '0')

    def test_browser_missing_helper_has_actionable_fallback(self):
        with patch('remote_repository.credential_manager', return_value=None):
            with self.assertRaisesRegex(RemoteRepositoryError, 'Personal access token'):
                authentication_environment('browser')

    def test_browser_forces_browser_mode(self):
        env = authentication_environment('browser', helper='manager')
        values = list(env.values())
        self.assertIn('credential.gitLabAuthModes', values)
        self.assertIn('credential.gitHubAuthModes', values)
        self.assertIn('browser', values)

    def test_failed_clone_cleans_cache_and_redacts_errors(self):
        with tempfile.TemporaryDirectory() as directory, patch('remote_repository.subprocess.run',
                return_value=subprocess.CompletedProcess([], 1, '', 'server echoed secret-token')):
            with self.assertRaises(RemoteRepositoryError) as error:
                prepare_repository('https://git.example/team/repo.git', 'token', 'user', 'secret-token', directory)
            self.assertNotIn('secret-token', str(error.exception))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_cache_clone_fetch_preview_and_archive(self):
        # Exercise real Git objects with local transport, inspecting HTTPS auth separately.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            source.mkdir()
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=source, text=True).strip()
            git('init', '-q')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.com')
            (source / 'first.txt').write_text('first')
            git('add', '.')
            git('commit', '-qm', 'first')
            start = git('rev-parse', 'HEAD')
            git('tag', 'v1')
            real_run = subprocess.run
            captured = []
            def local_transport(args, **kwargs):
                captured.append(args)
                args = list(args)
                if 'clone' in args:
                    args[args.index('--') + 1] = str(source)
                return real_run(args, **kwargs)
            url = 'https://git.example/team/repo.git'
            with patch('remote_repository.subprocess.run', side_effect=local_transport):
                cache = prepare_repository(url, 'token', 'user', 'secret-token', root / 'cache')
                (source / 'second.txt').write_text('second')
                git('add', '.')
                git('commit', '-qm', 'second')
                end = git('rev-parse', 'HEAD')
                git('tag', 'v2')
                self.assertEqual(prepare_repository(url, 'token', 'user', 'secret-token', root / 'cache'), cache)
            self.assertFalse((Path(cache) / '.git').exists())
            info = get_repository_info(cache)
            self.assertFalse(info['error'])
            self.assertIn('v2', info['tags'])
            self.assertEqual(get_file_list_preview(dict(repo_path=cache, mode='tag_range', start_tag='v1', end_tag='v2'))['files'], ['second.txt'])
            self.assertEqual(get_file_list_preview(dict(repo_path=cache, mode='commit_sha', commit_sha=start))['files'], ['first.txt'])
            today = date.today().isoformat()
            self.assertEqual(get_file_list_preview(dict(repo_path=cache, mode='date', branch=info['branch'], start_date=today, end_date=today))['files'], ['first.txt', 'second.txt'])
            params = dict(repo_path=cache, mode='sha_range', start_sha=start, end_sha=end, exclude_start=True)
            self.assertEqual(get_file_list_preview(params)['files'], ['second.txt'])
            params.update(output_zip=str(root / 'output.zip'), log_callback=lambda m: None)
            archive_git_history(params)
            self.assertTrue((root / 'output.zip').is_file())
            for path in Path(cache).glob('config'):
                self.assertNotIn('secret-token', path.read_text())
            self.assertNotIn('secret-token', str(captured))
