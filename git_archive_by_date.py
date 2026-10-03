

import os
import argparse
import subprocess
import shutil
import tempfile
import json
import fnmatch
from datetime import datetime

# This script can be run as a standalone CLI or imported by another script (like a UI).

def run_command(command, cwd):
    """Runs a shell command and returns its output."""
    try:
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        result = subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            startupinfo=startupinfo
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def is_git_repository(path):
    """Support normal repositories and linked worktrees (.git can be a file)."""
    if not path or not os.path.isdir(path):
        return False
    if os.path.exists(os.path.join(path, '.git')):
        return True
    return run_command(['git', 'rev-parse', '--is-bare-repository'], path) == 'true'


def get_repository_info(repo_path):
    """Return the repository dashboard data used by the GUI."""
    if not is_git_repository(repo_path):
        return {'error': f"Not a valid git repository: '{repo_path}'"}
    branch = run_command(['git', 'branch', '--show-current'], repo_path) or '(detached HEAD)'
    remote = run_command(['git', 'remote', 'get-url', 'origin'], repo_path) or '(no origin)'
    last = run_command(['git', 'log', '-1', '--pretty=format:%h|%ad|%s', '--date=short'], repo_path) or ''
    dirty = run_command(['git', 'status', '--porcelain'], repo_path)
    upstream = run_command(['git', 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}'], repo_path)
    ahead = behind = 0
    if upstream:
        counts = run_command(['git', 'rev-list', '--left-right', '--count', f'{upstream}...HEAD'], repo_path)
        if counts:
            behind, ahead = (int(value) for value in counts.split())
    branches = (run_command(['git', 'for-each-ref', '--format=%(refname:short)',
                             'refs/heads', 'refs/remotes'], repo_path) or '').splitlines()
    branches = sorted({b for b in branches if not b.endswith('/HEAD')})
    tags = (run_command(['git', 'tag', '--sort=-creatordate'], repo_path) or '').splitlines()
    return {'error': None, 'branch': branch, 'remote': remote, 'last_commit': last,
            'dirty': bool(dirty), 'changes': len(dirty.splitlines()) if dirty else 0,
            'upstream': upstream, 'ahead': ahead, 'behind': behind,
            'branches': branches, 'tags': tags}


def _parse_name_status(output):
    changes = []
    for line in (output or '').splitlines():
        parts = line.split('\t')
        if len(parts) < 2:
            continue
        code = parts[0][0]
        old_path = parts[1] if code in ('R', 'C') and len(parts) > 2 else None
        path = parts[2] if old_path else parts[1]
        changes.append({'status': code, 'path': path, 'old_path': old_path})
    return changes


def _resolve_changes(params):
    repo_path, mode = params['repo_path'], params['mode']
    commits_info, range_info = [], ''
    if mode == 'date':
        start, end, branch = params['start_date'], params['end_date'], params['branch']
        author = params.get('author')
        latest = run_command(['git', 'rev-list', '-1', f'--before={end} 23:59:59', branch], repo_path)
        if not latest:
            return {'error': f"Could not find a commit on branch '{branch}' before '{end}'."}
        if author:
            cmd = ['git', 'log', branch, f'--since={start} 00:00:00', f'--until={end} 23:59:59',
                   '--name-status', '--format=', f'--author={author}']
            output = run_command(cmd, repo_path)
        else:
            base = run_command(['git', 'rev-list', '-1', f'--before={start} 00:00:00', branch], repo_path)
            base = base or '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
            output = run_command(['git', 'diff', '--name-status', '-M', base, latest], repo_path)
        commits_info = get_commits_with_files(repo_path, mode, branch=branch, start_date=start, end_date=end, author=author)
        range_info = f'Branch: {branch}\nDate Range: {start} to {end}' + (f'\nAuthor Filter: {author}' if author else '')
    elif mode == 'sha_range':
        start, latest = params['start_sha'], params['end_sha']
        exclude_start = params.get('exclude_start', False)
        start_parent = start if exclude_start else run_command(['git', 'rev-parse', '--verify', f'{start}^'], repo_path)
        base = start_parent or '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
        output = run_command(['git', 'diff', '--name-status', '-M', base, latest], repo_path)
        commits_info = get_commits_with_files(repo_path, mode, start_sha=start, end_sha=latest, exclude_start=exclude_start)
        range_info = f"SHA Range ({'start excluded' if exclude_start else 'inclusive'}): {start[:8]}..{latest[:8]}"
    elif mode == 'commit_sha':
        latest = params['commit_sha']
        output = run_command(['git', 'diff-tree', '--root', '--no-commit-id', '--name-status', '-r', '-M', latest], repo_path)
        commits_info = get_commits_with_files(repo_path, mode, commit_sha=latest)
        range_info = f'Commit: {latest}'
    elif mode == 'tag_range':
        start, latest = params['start_tag'], params['end_tag']
        output = run_command(['git', 'diff', '--name-status', '-M', f'{start}..{latest}'], repo_path)
        commits_info = get_commits_with_files(repo_path, 'sha_range', start_sha=start, end_sha=latest)
        range_info = f'Tag Range: {start}..{latest}'
    else:
        return {'error': f'Unknown mode: {mode}'}
    if output is None:
        return {'error': 'Failed to read changes from Git. Check the selected references.'}
    excludes = [p.strip() for p in params.get('exclude_patterns', []) if p.strip()]
    parsed = [c for c in _parse_name_status(output)
              if not any(fnmatch.fnmatch(c['path'], p) or fnmatch.fnmatch(c['path'], p.rstrip('/') + '/*') for p in excludes)]
    # git log returns newest commits first; retain the newest effective status per path.
    changes_by_path = {}
    for change in parsed:
        changes_by_path.setdefault(change['path'], change)
    changes = sorted(changes_by_path.values(), key=lambda item: item['path'])
    selected = params.get('selected_files')
    if selected is not None:
        selected = set(selected)
        changes = [c for c in changes if c['path'] in selected]
    return {'error': None, 'changes': changes, 'commit_hash': latest,
            'commits_info': commits_info, 'range_info': range_info}

def get_commit_details(repo_path, commit_hash):
    """Get commit message, author, and date for a specific commit."""
    if not commit_hash:
        return None
    
    # Get commit info in a structured format
    log_cmd = ['git', 'log', '-1', '--pretty=format:%H|%an|%ae|%ad|%s', '--date=iso', commit_hash]
    commit_info = run_command(log_cmd, repo_path)
    
    if commit_info:
        parts = commit_info.split('|', 4)
        if len(parts) == 5:
            return {
                'hash': parts[0],
                'author_name': parts[1],
                'author_email': parts[2],
                'date': parts[3],
                'message': parts[4]
            }
    return None

def get_commits_in_range(repo_path, mode, **kwargs):
    """Get all commits in the specified range with their details."""
    commits = []
    
    if mode == 'date':
        branch = kwargs.get('branch')
        start_date = kwargs.get('start_date')
        end_date = kwargs.get('end_date')
        author = kwargs.get('author')
        log_cmd = ['git', 'log', branch, f'--since={start_date} 00:00:00', f'--until={end_date} 23:59:59',
                   '--pretty=format:%H|%an|%ae|%ad|%s', '--date=iso']
        if author:
            log_cmd.append(f'--author={author}')
    elif mode == 'sha_range':
        start_sha = kwargs.get('start_sha')
        end_sha = kwargs.get('end_sha')
        start_parent = start_sha if kwargs.get('exclude_start', False) else run_command(['git', 'rev-parse', '--verify', f'{start_sha}^'], repo_path)
        revision_range = f'{start_parent}..{end_sha}' if start_parent else end_sha
        log_cmd = ['git', 'log', revision_range, '--pretty=format:%H|%an|%ae|%ad|%s', '--date=iso']
    elif mode == 'commit_sha':
        commit_sha = kwargs.get('commit_sha')
        log_cmd = ['git', 'log', '-1', '--pretty=format:%H|%an|%ae|%ad|%s', '--date=iso', commit_sha]
    else:
        return commits
    
    commit_output = run_command(log_cmd, repo_path)
    if commit_output:
        for line in commit_output.splitlines():
            parts = line.split('|', 4)
            if len(parts) == 5:
                commits.append({
                    'hash': parts[0],
                    'author_name': parts[1],
                    'author_email': parts[2],
                    'date': parts[3],
                    'message': parts[4]
                })
    
    return commits

def get_recent_commits(repo_path, limit=100, branch=None):
    """Get a list of recent commits for browsing/picking.

    Returns a list of dicts with hash, short_hash, author, date, message.
    """
    if not is_git_repository(repo_path):
        return {'error': f"Not a valid git repository: '{repo_path}'", 'commits': []}

    log_cmd = ['git', 'log', f'-{limit}', '--pretty=format:%H|%an|%ad|%s', '--date=short']
    if branch:
        log_cmd.append(branch)
    output = run_command(log_cmd, repo_path)
    if output is None:
        return {'error': "Failed to read git log. Check the repository and branch.", 'commits': []}

    commits = []
    for line in output.splitlines():
        parts = line.split('|', 3)
        if len(parts) == 4:
            commits.append({
                'hash': parts[0],
                'short_hash': parts[0][:10],
                'author': parts[1],
                'date': parts[2],
                'message': parts[3],
            })
    return {'error': None, 'commits': commits}


def get_files_changed_in_commit(repo_path, commit_hash):
    """Get list of files changed in a specific commit."""
    if not commit_hash:
        return []
    
    # First check if this is a merge commit
    merge_check_cmd = ['git', 'cat-file', '-p', commit_hash]
    commit_info = run_command(merge_check_cmd, repo_path)
    
    is_merge_commit = False
    if commit_info:
        parent_lines = [line for line in commit_info.splitlines() if line.startswith('parent ')]
        is_merge_commit = len(parent_lines) > 1
    
    if is_merge_commit:
        # For merge commits, get files that were actually changed in the merge
        # Use --cc flag to show combined diff for merge commits
        show_cmd = ['git', 'show', '--name-only', '--cc', '--pretty=format:', commit_hash]
        files_output = run_command(show_cmd, repo_path)
        
        if not files_output or not files_output.strip():
            # If no files in combined diff, try getting files from the merge parents
            # This shows files that were different between the merged branches
            diff_cmd = ['git', 'diff-tree', '--name-only', '-r', commit_hash]
            files_output = run_command(diff_cmd, repo_path)
    else:
        # Regular commit
        show_cmd = ['git', 'show', '--name-only', '--pretty=format:', commit_hash]
        files_output = run_command(show_cmd, repo_path)
    
    if files_output:
        return [f.strip() for f in files_output.splitlines() if f.strip()]
    return []

def is_merge_commit(repo_path, commit_hash):
    """Check if a commit is a merge commit."""
    merge_check_cmd = ['git', 'cat-file', '-p', commit_hash]
    commit_info = run_command(merge_check_cmd, repo_path)
    
    if commit_info:
        parent_lines = [line for line in commit_info.splitlines() if line.startswith('parent ')]
        return len(parent_lines) > 1
    return False

def get_commits_with_files(repo_path, mode, **kwargs):
    """Get commits with their associated changed files."""
    commits = get_commits_in_range(repo_path, mode, **kwargs)
    
    # Add files and merge info for each commit
    for commit in commits:
        commit['files'] = get_files_changed_in_commit(repo_path, commit['hash'])
        commit['is_merge'] = is_merge_commit(repo_path, commit['hash'])
    
    return commits

def get_file_list_preview(params):
    """
    Get list of files that would be archived without actually creating the archive.
    Returns a dictionary with file list and metadata.
    """
    repo_path = params['repo_path']
    if not is_git_repository(repo_path):
        return {'error': f"Not a valid git repository: '{repo_path}'"}
    try:
        result = _resolve_changes(params)
        if result.get('error'):
            return result
        changes = result['changes']
        total_size = 0
        for change in changes:
            if change['status'] == 'D':
                change['size'] = 0
            else:
                raw_size = run_command(['git', 'cat-file', '-s',
                                        f"{result['commit_hash']}:{change['path']}"], repo_path)
                change['size'] = int(raw_size) if raw_size and raw_size.isdigit() else 0
            change['commit'] = run_command(['git', 'log', '-1', '--format=%h',
                                            result['commit_hash'], '--', change['path']], repo_path) or ''
            total_size += change['size']
        result.update({
            'files': [c['path'] for c in changes],
            'deleted_files': sorted({c['path'] for c in changes if c['status'] == 'D'} |
                                    {c['old_path'] for c in changes if c['status'] == 'R' and c['old_path']}),
            'total_files': len(changes),
            'total_size': total_size,
        })
        return result
    except Exception as e:
        return {'error': str(e)}

def _write_text_changelog(changelog_path, archive_name_base, archive_ext, repo_path,
                          changelog_range_info, archived_files, commits_info,
                          changes=None, deleted_files=None):
    """Write the classic plain-text changelog."""
    with open(changelog_path, 'w', encoding='utf-8') as f:
        f.write(f"Changelog for {os.path.basename(archive_name_base)}{archive_ext}\n")
        f.write("=" * 70 + "\n")
        f.write(f"Repository: {os.path.abspath(repo_path)}\n")
        f.write(changelog_range_info + "\n")
        f.write(f"Total Files Archived: {len(archived_files)}\n")
        f.write(f"Deleted Files: {len(deleted_files or [])}\n")
        f.write("=" * 70 + "\n\n")

        if commits_info:
            f.write(f"Commits with Changed Files ({len(commits_info)}):\n")
            f.write("=" * 70 + "\n")

            total_commit_files = 0
            for i, commit in enumerate(commits_info, 1):
                commit_archived_files = [c for c in commit.get('files', []) if c in archived_files]
                total_commit_files += len(commit_archived_files)

                commit_type = " [MERGE]" if commit.get('is_merge', False) else ""
                f.write(f"\n[{i}] Commit: {commit['hash'][:10]}{commit_type}\n")
                f.write(f"    Author: {commit['author_name']} <{commit['author_email']}>\n")
                f.write(f"    Date: {commit['date']}\n")
                f.write(f"    Message: {commit['message']}\n")

                if commit.get('is_merge', False):
                    f.write(f"    Type: Merge Commit\n")
                    if not commit_archived_files:
                        f.write(f"    Note: Merge commits may not show direct file changes\n")

                f.write(f"    Files Changed ({len(commit_archived_files)}):\n")
                if commit_archived_files:
                    for file_path in sorted(commit_archived_files):
                        f.write(f"      - {file_path}\n")
                else:
                    if commit.get('is_merge', False):
                        f.write(f"      (Merge commit - files may have been changed in merged branches)\n")
                    else:
                        f.write(f"      (No files from this commit were archived)\n")
                f.write("-" * 60 + "\n")

            f.write(f"\nSummary:\n")
            f.write(f"- Total commits: {len(commits_info)}\n")
            f.write(f"- Total unique files archived: {len(archived_files)}\n")
            f.write(f"- Total file changes across all commits: {total_commit_files}\n")
        else:
            f.write(f"Archived Files ({len(archived_files)}):\n")
            f.write("-" * 50 + "\n")
            for file_path in sorted(archived_files):
                f.write(f"{file_path}\n")
        if changes:
            labels = {'A': 'Added', 'M': 'Modified', 'D': 'Deleted', 'R': 'Renamed', 'C': 'Copied'}
            f.write("\nFile Status:\n" + "-" * 50 + "\n")
            for change in changes:
                f.write(f"[{labels.get(change['status'], change['status'])}] {change['path']}\n")
        if deleted_files:
            f.write("\nDEPLOYMENT DELETIONS (also in deleted_files.txt):\n")
            for path in sorted(deleted_files):
                f.write(f"DELETE {path}\n")


def _write_markdown_changelog(changelog_path, archive_name_base, archive_ext, repo_path,
                              changelog_range_info, archived_files, commits_info,
                              changes=None, deleted_files=None):
    """Write a Markdown-formatted changelog."""
    remote = run_command(['git', 'remote', 'get-url', 'origin'], repo_path) or ''
    if remote.startswith('git@') and ':' in remote:
        host_path = remote[4:].replace(':', '/', 1)
        remote = 'https://' + host_path
    if remote.endswith('.git'):
        remote = remote[:-4]
    web_remote = remote if remote.startswith(('http://', 'https://')) else ''
    with open(changelog_path, 'w', encoding='utf-8') as f:
        f.write(f"# Changelog for `{os.path.basename(archive_name_base)}{archive_ext}`\n\n")
        f.write(f"- **Repository:** `{os.path.abspath(repo_path)}`\n")
        for line in changelog_range_info.splitlines():
            if ':' in line:
                key, _, val = line.partition(':')
                f.write(f"- **{key.strip()}:** {val.strip()}\n")
            else:
                f.write(f"- {line}\n")
        f.write(f"- **Total Files Archived:** {len(archived_files)}\n\n")
        f.write(f"- **Deleted Files:** {len(deleted_files or [])}\n\n")

        if commits_info:
            f.write(f"## Commits ({len(commits_info)})\n\n")
            total_commit_files = 0
            for i, commit in enumerate(commits_info, 1):
                commit_archived_files = [c for c in commit.get('files', []) if c in archived_files]
                total_commit_files += len(commit_archived_files)
                merge_tag = " _(merge)_" if commit.get('is_merge', False) else ""
                sha_label = f"`{commit['hash'][:10]}`"
                if web_remote:
                    sha_label = f"[`{commit['hash'][:10]}`]({web_remote}/commit/{commit['hash']})"
                f.write(f"### {i}. {sha_label}{merge_tag} — {commit['message']}\n\n")
                f.write(f"- **Author:** {commit['author_name']} &lt;{commit['author_email']}&gt;\n")
                f.write(f"- **Date:** {commit['date']}\n")
                f.write(f"- **Files Changed ({len(commit_archived_files)}):**\n")
                if commit_archived_files:
                    for file_path in sorted(commit_archived_files):
                        f.write(f"  - `{file_path}`\n")
                else:
                    f.write(f"  - _(no archived files from this commit)_\n")
                f.write("\n")

            f.write(f"## Summary\n\n")
            f.write(f"- Total commits: **{len(commits_info)}**\n")
            f.write(f"- Total unique files archived: **{len(archived_files)}**\n")
            f.write(f"- Total file changes across all commits: **{total_commit_files}**\n")
        else:
            f.write(f"## Archived Files ({len(archived_files)})\n\n")
            for file_path in sorted(archived_files):
                f.write(f"- `{file_path}`\n")
        if changes:
            labels = {'A': 'Added', 'M': 'Modified', 'D': 'Deleted', 'R': 'Renamed', 'C': 'Copied'}
            f.write("\n## File Status\n\n| Status | File |\n|---|---|\n")
            for change in changes:
                f.write(f"| {labels.get(change['status'], change['status'])} | `{change['path']}` |\n")
        if deleted_files:
            f.write("\n## Deployment Deletions\n\nThese paths must be removed from the deployment target and are also listed in `deleted_files.txt`.\n\n")
            for path in sorted(deleted_files):
                f.write(f"- `{path}`\n")


def archive_git_history(params):
    """
    Main logic for archiving files from a git repository.
    Accepts a dictionary of parameters and a log_callback function.
    """
    log_callback = params.get('log_callback', print) # Default to print for CLI mode
    progress_callback = params.get('progress_callback', None) # Progress callback
    cancel_event = params.get('cancel_event', None) # Threading.Event for cancellation
    repo_path = params['repo_path']
    output_zip = params['output_zip']
    mode = params['mode']
    archive_format = params.get('archive_format', 'zip')  # Default to zip

    def check_cancel():
        """Check if cancellation was requested"""
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("Process cancelled by user")

    try:
        if not is_git_repository(repo_path):
            log_callback(f"Error: Not a valid git repository: '{repo_path}'")
            return

        check_cancel()
        if progress_callback:
            progress_callback(5, "Validating repository...")
        log_callback(f"Processing repository: {os.path.abspath(repo_path)}")

        if progress_callback:
            progress_callback(10, "Reading changes from Git...")
        resolved = _resolve_changes(params)
        if resolved.get('error'):
            raise ValueError(resolved['error'])
        latest_commit_hash = resolved['commit_hash']
        changelog_range_info = resolved['range_info']
        commits_info = resolved['commits_info']
        changes = resolved['changes']
        changed_files = [c['path'] for c in changes]
        deleted_files = sorted({c['path'] for c in changes if c['status'] == 'D'} |
                               {c['old_path'] for c in changes if c['status'] == 'R' and c['old_path']})
        if not changed_files:
            log_callback("No files changed in the specified range or commit.")
            return
            
        log_callback(f"Found {len(changed_files)} unique files.")
        log_callback(f"Using state of files from commit: {latest_commit_hash[:10]}")

        check_cancel()
        if progress_callback:
            progress_callback(20, "Creating temporary directory...")
        temp_dir = tempfile.mkdtemp(prefix="git-archive-")
        log_callback(f"Created temporary directory: {temp_dir}")

        archived_files = []
        total_files = len(changed_files)
        for idx, file_path in enumerate(changed_files):
            check_cancel()
            if progress_callback:
                progress = 20 + int((idx / total_files) * 50)  # 20-70% for file archiving
                progress_callback(progress, f"Archiving file {idx+1}/{total_files}: {file_path[:50]}...")
            if not file_path or file_path in deleted_files:
                continue
            dest_path = os.path.join(temp_dir, file_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            show_cmd = ['git', 'show', f'{latest_commit_hash}:{file_path}']
            try:
                startupinfo = None
                if os.name == 'nt':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                with open(dest_path, 'wb') as f:
                    content = subprocess.run(show_cmd, cwd=repo_path, check=True, capture_output=True, startupinfo=startupinfo).stdout
                    f.write(content)
                archived_files.append(file_path)
            except subprocess.CalledProcessError:
                log_callback(f"Warning: Could not find '{file_path}' in commit {latest_commit_hash[:10]}. Skipping.")
        
        check_cancel()
        manifest_name = 'deleted_files.txt'
        if deleted_files:
            with open(os.path.join(temp_dir, manifest_name), 'w', encoding='utf-8') as manifest:
                manifest.write('\n'.join(sorted(deleted_files)) + '\n')
            log_callback(f"Added deletion manifest with {len(deleted_files)} file(s).")

        if progress_callback:
            format_name = {'zip': 'ZIP', 'tar': 'TAR', 'gztar': 'TAR.GZ'}.get(archive_format, 'ZIP')
            progress_callback(70, f"Creating {format_name} archive...")
        
        # Remove extension from output_zip if present, we'll add the correct one
        archive_name_base = output_zip
        for ext in ['.zip', '.tar', '.tar.gz', '.gz']:
            if archive_name_base.lower().endswith(ext):
                archive_name_base = archive_name_base[:-len(ext)]
                break
        
        # Map format to extension for changelog
        format_ext_map = {'zip': '.zip', 'tar': '.tar', 'gztar': '.tar.gz'}
        archive_ext = format_ext_map.get(archive_format, '.zip')
        
        log_callback(f"Creating {archive_format.upper()} archive: {archive_name_base}{archive_ext}")
        shutil.make_archive(archive_name_base, archive_format, temp_dir)
        log_callback(f"Successfully created {archive_format.upper()} archive.")

        check_cancel()
        if progress_callback:
            progress_callback(85, "Creating changelog file...")
        changelog_format = params.get('changelog_format', 'txt')
        if changelog_format == 'md':
            changelog_path = f"{archive_name_base}.md"
            log_callback(f"Creating changelog file: {changelog_path}")
            _write_markdown_changelog(changelog_path, archive_name_base, archive_ext,
                                      repo_path, changelog_range_info, archived_files, commits_info,
                                      changes, deleted_files)
        else:
            changelog_path = f"{archive_name_base}.txt"
            log_callback(f"Creating changelog file: {changelog_path}")
            _write_text_changelog(changelog_path, archive_name_base, archive_ext,
                                  repo_path, changelog_range_info, archived_files, commits_info,
                                  changes, deleted_files)
        if progress_callback:
            progress_callback(100, "Process complete!")
        log_callback("Successfully created changelog file.")
        log_callback("\n--- PROCESS COMPLETE ---")
        complete_callback = params.get('complete_callback', None)
        if complete_callback:
            complete_callback({
                'success': True,
                'archive_path': f"{archive_name_base}{archive_ext}",
                'changelog_path': changelog_path,
                'file_count': len(archived_files),
                'deleted_count': len(deleted_files),
            })

    except InterruptedError as e:
        log_callback(f"\n--- PROCESS CANCELLED ---")
        log_callback(str(e))
        if progress_callback:
            progress_callback(0, "Cancelled")
    except Exception as e:
        log_callback(f"\nAn unexpected error occurred: {e}")
        if progress_callback:
            progress_callback(0, "Error occurred")
        complete_callback = params.get('complete_callback', None)
        if complete_callback:
            complete_callback({'success': False, 'error': str(e)})
    finally:
        if 'temp_dir' in locals() and os.path.exists(temp_dir):
            log_callback(f"Cleaning up temporary directory: {temp_dir}")
            shutil.rmtree(temp_dir)

def main():
    parser = argparse.ArgumentParser(
        description="Archive files from a Git repository based on a date range, commit range, or a single commit.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="Created by ekosiswoyo"
    )
    parser.add_argument("repo_path", help="Absolute path to the local Git repository.")
    parser.add_argument("-o", "--output-zip", required=True, help="Base name for the output zip file (e.g., 'my-archive').")
    
    group = parser.add_argument_group('Range Selection (choose one method)')
    group.add_argument("-b", "--branch", help="The branch to inspect (required for date range).")
    group.add_argument("-s", "--start-date", help="Start date in YYYY-MM-DD format.")
    group.add_argument("-e", "--end-date", help="End date in YYYY-MM-DD format.")
    group.add_argument("--start-sha", help="The starting commit SHA for the range.")
    group.add_argument("--exclude-start", action="store_true", help="Exclude the starting commit in SHA range mode.")
    group.add_argument("--end-sha", help="The ending commit SHA for the range.")
    group.add_argument("--commit-sha", help="The single commit SHA to archive changes from.")
    group.add_argument("--start-tag", help="The starting tag for a release range.")
    group.add_argument("--end-tag", help="The ending tag for a release range.")
    parser.add_argument("--archive-format", choices=['zip', 'tar', 'gztar'], default='zip')
    parser.add_argument("--changelog-format", choices=['txt', 'md'], default='txt')
    parser.add_argument("--exclude", action='append', default=[], help="Glob to exclude (repeatable).")

    args = parser.parse_args()

    params = {
        'repo_path': args.repo_path,
        'output_zip': args.output_zip,
        'archive_format': args.archive_format,
        'changelog_format': args.changelog_format,
        'exclude_patterns': args.exclude,
    }

    is_date_mode = bool(args.start_date or args.end_date)
    is_sha_range_mode = bool(args.start_sha or args.end_sha)
    is_single_sha_mode = bool(args.commit_sha)
    is_tag_range_mode = bool(args.start_tag or args.end_tag)

    mode_count = sum([is_date_mode, is_sha_range_mode, is_single_sha_mode, is_tag_range_mode])
    if mode_count > 1:
        parser.error("argument conflict: please use only one method: date range, SHA range, or single commit.")
    if mode_count == 0:
        parser.error("missing arguments: you must specify a range (date, SHA range, or single commit).")

    if is_date_mode:
        if not (args.start_date and args.end_date and args.branch):
            parser.error("for date mode, --start-date, --end-date, and --branch are all required.")
        try:
            datetime.strptime(args.start_date, '%Y-%m-%d')
            datetime.strptime(args.end_date, '%Y-%m-%d')
        except ValueError:
            parser.error("dates must be in YYYY-MM-DD format.")
        params.update({'mode': 'date', 'start_date': args.start_date, 'end_date': args.end_date, 'branch': args.branch})
    
    elif is_sha_range_mode:
        if not (args.start_sha and args.end_sha):
            parser.error("for SHA range mode, both --start-sha and --end-sha are required.")
        params.update({'mode': 'sha_range', 'start_sha': args.start_sha, 'end_sha': args.end_sha, 'exclude_start': args.exclude_start})

    elif is_single_sha_mode:
        params.update({'mode': 'commit_sha', 'commit_sha': args.commit_sha})

    elif is_tag_range_mode:
        if not (args.start_tag and args.end_tag):
            parser.error("for tag range mode, both --start-tag and --end-tag are required.")
        params.update({'mode': 'tag_range', 'start_tag': args.start_tag, 'end_tag': args.end_tag})

    archive_git_history(params)

if __name__ == "__main__":
    main()
