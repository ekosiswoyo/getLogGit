"""HTTPS Git cache and session-only token authentication."""
import base64
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit, urlunsplit

from app_storage import data_directory


class RemoteRepositoryError(RuntimeError):
    pass


def normalize_url(value):
    parts = urlsplit(value.strip())
    if parts.scheme != 'https' or not parts.hostname or not parts.path.strip('/'):
        raise ValueError('Enter an HTTPS clone URL, for example https://github.com/team/repo.git.')
    if parts.username is not None or parts.password is not None or parts.query or parts.fragment:
        raise ValueError('Use a clean clone URL without credentials, query parameters, or fragments. Enter the token separately.')
    if any(ord(char) < 32 for char in value):
        raise ValueError('The URL contains invalid characters.')
    return urlunsplit(('https', parts.netloc.lower(), parts.path.rstrip('/'), '', ''))


def credential_manager():
    for helper in ('manager', 'manager-core'):
        try:
            result = subprocess.run(['git', f'credential-{helper}', '--version'],
                                    capture_output=True, timeout=10)
            if result.returncode == 0:
                return helper
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None


def authentication_environment(method='auto', username='', token='', helper=None):
    env = os.environ.copy()
    env['GIT_TERMINAL_PROMPT'] = '0'
    env['GCM_INTERACTIVE'] = 'true'
    env['GCM_GUI_PROMPT'] = 'true'
    settings = [('http.sslVerify', 'true')]
    if method == 'token':
        if not username.strip() or not token.strip():
            raise ValueError('Enter your Git username and personal access token. Use a token instead of an account password with 2FA.')
        if ':' in username or any(c in username + token for c in '\r\n'):
            raise ValueError('Username and token must not contain line breaks.')
        authorization = base64.b64encode(f'{username.strip()}:{token.strip()}'.encode()).decode()
        settings += [('credential.helper', ''), ('http.extraHeader', ''), ('http.extraHeader', f'Authorization: Basic {authorization}')]
    elif method == 'browser':
        helper = helper or credential_manager()
        if not helper:
            raise RemoteRepositoryError('Web login requires Git Credential Manager. Install it from https://github.com/git-ecosystem/git-credential-manager/releases or choose Personal access token, which works without a credential helper.')
        settings += [('credential.helper', ''), ('credential.helper', helper),
                     ('credential.gitHubAuthModes', 'browser'), ('credential.gitLabAuthModes', 'browser')]
    elif method != 'auto':
        raise ValueError('Unknown authentication method.')
    # Overrides are in the child process environment, never Git config or argv.
    env['GIT_CONFIG_COUNT'] = str(len(settings))
    for index, (key, value) in enumerate(settings):
        env[f'GIT_CONFIG_KEY_{index}'] = key
        env[f'GIT_CONFIG_VALUE_{index}'] = value
    # HTTP tracing may print authorization headers on some Git versions.
    for key in tuple(env):
        if key.startswith('GIT_TRACE') or key == 'GIT_CURL_VERBOSE':
            env.pop(key, None)
    return env


def prepare_repository(url, method='auto', username='', token='', cache_root=None):
    url = normalize_url(url)
    env = authentication_environment(method, username, token)
    root = Path(cache_root) if cache_root is not None else data_directory() / 'repositories'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = root / (hashlib.sha256(url.encode()).hexdigest() + '.git')
    def git(*args, cwd=None):
        try:
            result = subprocess.run(['git', *args], cwd=cwd, env=env, capture_output=True,
                                    text=True, encoding='utf-8', errors='replace', timeout=600)
        except FileNotFoundError:
            raise RemoteRepositoryError('Git is not installed. Install Git and restart the application.') from None
        except subprocess.TimeoutExpired:
            raise RemoteRepositoryError('Connection timed out. Check VPN/network access and retry.') from None
        if result.returncode:
            # Do not expose server responses, which may echo supplied secrets.
            raise RemoteRepositoryError('Git could not access this repository. Check the HTTPS clone URL, VPN/network, and account permissions. For private repositories, use a personal access token with repository read access (and SSO authorization if required), or Web login.')
        return result.stdout.strip()
    if not destination.exists():
        temporary = Path(tempfile.mkdtemp(prefix='clone-', dir=root))
        try:
            git('clone', '--bare', '--', url, str(temporary))
            temporary.rename(destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    else:
        git('fetch', '--prune', 'origin', '+refs/heads/*:refs/heads/*', '+refs/tags/*:refs/tags/*', cwd=destination)
    return str(destination)
