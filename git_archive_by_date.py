

import os
import argparse
import subprocess
import shutil
import tempfile
import json
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
        log_cmd = ['git', 'log', branch, f'--since="{start_date} 00:00:00"', f'--until="{end_date} 23:59:59"', 
                   '--pretty=format:%H|%an|%ae|%ad|%s', '--date=iso']
    elif mode == 'sha_range':
        start_sha = kwargs.get('start_sha')
        end_sha = kwargs.get('end_sha')
        log_cmd = ['git', 'log', f'{start_sha}..{end_sha}', '--pretty=format:%H|%an|%ae|%ad|%s', '--date=iso']
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
    mode = params['mode']
    
    if not os.path.isdir(repo_path) or not os.path.isdir(os.path.join(repo_path, '.git')):
        return {'error': f"Not a valid git repository: '{repo_path}'"}
    
    files_output = None
    latest_commit_hash = None
    commits_info = []
    
    try:
        if mode == 'date':
            start_date, end_date, branch = params['start_date'], params['end_date'], params['branch']
            latest_commit_cmd = ['git', 'rev-list', '-1', f'--before="{end_date} 23:59:59"', branch]
            latest_commit_hash = run_command(latest_commit_cmd, repo_path)
            if not latest_commit_hash:
                return {'error': f"Could not find a commit on branch '{branch}' before '{end_date}'."}
            log_cmd = ['git', 'log', branch, f'--since="{start_date} 00:00:00"', f'--until="{end_date} 23:59:59"', '--name-only', '--pretty=format:']
            files_output = run_command(log_cmd, repo_path)
            commits_info = get_commits_with_files(repo_path, 'date', branch=branch, start_date=start_date, end_date=end_date)
            
        elif mode == 'sha_range':
            start_sha, end_sha = params['start_sha'], params['end_sha']
            latest_commit_hash = end_sha
            diff_cmd = ['git', 'diff', '--name-only', f'{start_sha}..{end_sha}']
            files_output = run_command(diff_cmd, repo_path)
            commits_info = get_commits_with_files(repo_path, 'sha_range', start_sha=start_sha, end_sha=end_sha)
            
        elif mode == 'commit_sha':
            commit_sha = params['commit_sha']
            latest_commit_hash = commit_sha
            show_cmd = ['git', 'show', '--name-only', '--pretty=format:', commit_sha]
            files_output = run_command(show_cmd, repo_path)
            commits_info = get_commits_with_files(repo_path, 'commit_sha', commit_sha=commit_sha)
        
        if files_output is None:
            return {'error': "Failed to get file list from git. Check your parameters and that git is installed."}
        
        # Split lines and filter out empty strings
        all_files = files_output.splitlines()
        changed_files = sorted(list(set([f.strip() for f in all_files if f.strip()])))
        
        return {
            'files': changed_files,
            'total_files': len(changed_files),
            'commit_hash': latest_commit_hash,
            'commits_info': commits_info,
            'error': None
        }
    except Exception as e:
        return {'error': str(e)}

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
        if not os.path.isdir(repo_path) or not os.path.isdir(os.path.join(repo_path, '.git')):
            log_callback(f"Error: Not a valid git repository: '{repo_path}'")
            return

        check_cancel()
        if progress_callback:
            progress_callback(5, "Validating repository...")
        log_callback(f"Processing repository: {os.path.abspath(repo_path)}")

        files_output = None
        latest_commit_hash = None
        changelog_range_info = ""
        commits_info = []

        if mode == 'date':
            check_cancel()
            if progress_callback:
                progress_callback(10, "Getting commits from date range...")
            start_date, end_date, branch = params['start_date'], params['end_date'], params['branch']
            range_display = f"{start_date} to {end_date}"
            changelog_range_info = f"Branch: {branch}\nDate Range: {range_display}"
            log_callback(f"Mode: Date Range on branch '{branch}' from {range_display}")
            latest_commit_cmd = ['git', 'rev-list', '-1', f'--before="{end_date} 23:59:59"', branch]
            latest_commit_hash = run_command(latest_commit_cmd, repo_path)
            if not latest_commit_hash:
                log_callback(f"Error: Could not find a commit on branch '{branch}' before '{end_date}'.")
                return
            log_cmd = ['git', 'log', branch, f'--since="{start_date} 00:00:00"', f'--until="{end_date} 23:59:59"', '--name-only', '--pretty=format:']
            files_output = run_command(log_cmd, repo_path)
            check_cancel()
            # Get commit details with files for date range
            commits_info = get_commits_with_files(repo_path, 'date', branch=branch, start_date=start_date, end_date=end_date)

        elif mode == 'sha_range':
            check_cancel()
            if progress_callback:
                progress_callback(10, "Getting commits from SHA range...")
            start_sha, end_sha = params['start_sha'], params['end_sha']
            range_display = f"{start_sha[:7]}..{end_sha[:7]}"
            changelog_range_info = f"SHA Range: {range_display}"
            log_callback(f"Mode: SHA Range {range_display}")
            latest_commit_hash = end_sha
            diff_cmd = ['git', 'diff', '--name-only', f'{start_sha}..{end_sha}']
            files_output = run_command(diff_cmd, repo_path)
            check_cancel()
            # Get commit details with files for SHA range
            commits_info = get_commits_with_files(repo_path, 'sha_range', start_sha=start_sha, end_sha=end_sha)

        elif mode == 'commit_sha':
            check_cancel()
            if progress_callback:
                progress_callback(10, "Getting commit details...")
            commit_sha = params['commit_sha']
            range_display = f"Single Commit: {commit_sha[:7]}"
            changelog_range_info = f"Commit: {commit_sha}"
            log_callback(f"Mode: {range_display}")
            latest_commit_hash = commit_sha
            show_cmd = ['git', 'show', '--name-only', '--pretty=format:', commit_sha]
            files_output = run_command(show_cmd, repo_path)
            check_cancel()
            # Get commit details with files for single commit
            commits_info = get_commits_with_files(repo_path, 'commit_sha', commit_sha=commit_sha)

        if files_output is None:
            log_callback("Error: Failed to get file list from git. Check your parameters and that git is installed.")
            return

        check_cancel()
        # Split lines and filter out empty strings
        all_files = files_output.splitlines()
        changed_files = sorted(list(set([f.strip() for f in all_files if f.strip()])))
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
            if not file_path:
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
        if not archived_files:
            log_callback("No files could be archived. Aborting.")
            shutil.rmtree(temp_dir)
            return

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
        changelog_path = f"{archive_name_base}.txt"
        log_callback(f"Creating changelog file: {changelog_path}")
        with open(changelog_path, 'w', encoding='utf-8') as f:
            f.write(f"Changelog for {os.path.basename(archive_name_base)}{archive_ext}\n")
            f.write("="*70 + "\n")
            f.write(f"Repository: {os.path.abspath(repo_path)}\n")
            f.write(changelog_range_info + "\n")
            f.write(f"Total Files Archived: {len(archived_files)}\n")
            f.write("="*70 + "\n\n")
            
            # Write commit information with their files
            if commits_info:
                f.write(f"Commits with Changed Files ({len(commits_info)}):\n")
                f.write("="*70 + "\n")
                
                total_commit_files = 0
                for i, commit in enumerate(commits_info, 1):
                    # Filter files that were actually archived
                    commit_archived_files = [f for f in commit.get('files', []) if f in archived_files]
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
                # Fallback for when no commit info is available
                f.write(f"Archived Files ({len(archived_files)}):\n")
                f.write("-" * 50 + "\n")
                for file_path in sorted(archived_files):
                    f.write(f"{file_path}\n")
        if progress_callback:
            progress_callback(100, "Process complete!")
        log_callback("Successfully created changelog file.")
        log_callback("\n--- PROCESS COMPLETE ---")

    except InterruptedError as e:
        log_callback(f"\n--- PROCESS CANCELLED ---")
        log_callback(str(e))
        if progress_callback:
            progress_callback(0, "Cancelled")
    except Exception as e:
        log_callback(f"\nAn unexpected error occurred: {e}")
        if progress_callback:
            progress_callback(0, "Error occurred")
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
    group.add_argument("--end-sha", help="The ending commit SHA for the range.")
    group.add_argument("--commit-sha", help="The single commit SHA to archive changes from.")

    args = parser.parse_args()

    params = {
        'repo_path': args.repo_path,
        'output_zip': args.output_zip,
    }

    is_date_mode = bool(args.start_date or args.end_date)
    is_sha_range_mode = bool(args.start_sha or args.end_sha)
    is_single_sha_mode = bool(args.commit_sha)

    mode_count = sum([is_date_mode, is_sha_range_mode, is_single_sha_mode])
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
        params.update({'mode': 'sha_range', 'start_sha': args.start_sha, 'end_sha': args.end_sha})

    elif is_single_sha_mode:
        params.update({'mode': 'commit_sha', 'commit_sha': args.commit_sha})

    archive_git_history(params)

if __name__ == "__main__":
    main()

