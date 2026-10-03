"""Real HTTPS authentication against a temporary private Git server."""
import base64
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from remote_repository import prepare_repository
from git_archive_by_date import get_file_list_preview


@unittest.skipUnless(shutil.which('openssl'), 'openssl is needed for the temporary HTTPS certificate')
class PrivateHttpsTests(unittest.TestCase):
    def test_fresh_machine_token_https_without_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            source.mkdir()
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=source, text=True).strip()
            git('init', '-q')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.com')
            (source / 'hello.txt').write_text('private content')
            git('add', '.')
            git('commit', '-qm', 'private commit')
            sha = git('rev-parse', 'HEAD')
            server_root = root / 'server'
            server_root.mkdir()
            subprocess.run(['git', 'clone', '-q', '--bare', str(source), str(server_root / 'repo.git')], check=True)
            subprocess.run(['git', 'update-server-info'], cwd=server_root / 'repo.git', check=True)
            config = root / 'certificate.cnf'
            config.write_text('[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n[dn]\nCN=localhost\n[ext]\nsubjectAltName=DNS:localhost\nbasicConstraints=critical,CA:TRUE\n')
            cert, key = root / 'cert.pem', root / 'key.pem'
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                            '-config', str(config), '-keyout', str(key), '-out', str(cert)],
                           check=True, capture_output=True)
            authorized = []
            expected = 'Basic ' + base64.b64encode(b'new-user:test-token').decode()
            class Handler(SimpleHTTPRequestHandler):
                def do_GET(self):
                    if self.headers.get('Authorization') != expected:
                        self.send_response(401)
                        self.send_header('WWW-Authenticate', 'Basic realm="private"')
                        self.end_headers()
                        return
                    authorized.append(self.path)
                    super().do_GET()
                def log_message(self, *args):
                    pass
            server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(server_root)))
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            server.socket = context.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                environment = {'GIT_SSL_CAINFO': str(cert), 'GIT_CONFIG_GLOBAL': os.devnull,
                               'GIT_CONFIG_NOSYSTEM': '1'}
                if os.name == 'nt':
                    environment['GIT_SSL_BACKEND'] = 'openssl'
                with patch.dict(os.environ, environment):
                    cache = prepare_repository(f'https://localhost:{server.server_port}/repo.git',
                                               'token', 'new-user', 'test-token', root / 'cache')
                result = get_file_list_preview(dict(repo_path=cache, mode='commit_sha', commit_sha=sha))
                self.assertEqual(result['files'], ['hello.txt'])
                self.assertTrue(authorized)
                self.assertNotIn('test-token', (Path(cache) / 'config').read_text())
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
