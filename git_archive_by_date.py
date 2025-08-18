

import os
import argparse
import subprocess
import shutil
import tempfile
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

def archive_git_history(params):
    """
    Main logic for archiving files from a git repository.
    Accepts a dictionary of parameters and a log_callback function.
    """
    log_callback = params.get('log_callback', print) # Default to print for CLI mode
    repo_path = params['repo_path']
    output_zip = params['output_zip']
    mode = params['mode']

    try:
        if not os.path.isdir(repo_path) or not os.path.isdir(os.path.join(repo_path, '.git')):
            log_callback(f"Error: Not a valid git repository: '{repo_path}'")
            return

        log_callback(f"Processing repository: {os.path.abspath(repo_path)}")

        files_output = None
        latest_commit_hash = None
        changelog_range_info = ""

        if mode == 'date':
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

        elif mode == 'sha_range':
            start_sha, end_sha = params['start_sha'], params['end_sha']
            range_display = f"{start_sha[:7]}..{end_sha[:7]}"
            changelog_range_info = f"SHA Range: {range_display}"
            log_callback(f"Mode: SHA Range {range_display}")
            latest_commit_hash = end_sha
            diff_cmd = ['git', 'diff', '--name-only', f'{start_sha}..{end_sha}']
            files_output = run_command(diff_cmd, repo_path)

        elif mode == 'commit_sha':
            commit_sha = params['commit_sha']
            range_display = f"Single Commit: {commit_sha[:7]}"
            changelog_range_info = f"Commit: {commit_sha}"
            log_callback(f"Mode: {range_display}")
            latest_commit_hash = commit_sha
            show_cmd = ['git', 'show', '--name-only', '--pretty=format:', commit_sha]
            files_output = run_command(show_cmd, repo_path)

        if files_output is None:
            log_callback("Error: Failed to get file list from git. Check your parameters and that git is installed.")
            return

        changed_files = sorted(list(set(files_output.splitlines())))
        if not changed_files:
            log_callback("No files changed in the specified range or commit.")
            return
            
        log_callback(f"Found {len(changed_files)} unique files.")
        log_callback(f"Using state of files from commit: {latest_commit_hash[:10]}")

        temp_dir = tempfile.mkdtemp(prefix="git-archive-")
        log_callback(f"Created temporary directory: {temp_dir}")

        archived_files = []
        for file_path in changed_files:
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
        
        if not archived_files:
            log_callback("No files could be archived. Aborting.")
            shutil.rmtree(temp_dir)
            return

        archive_name_base = os.path.splitext(output_zip)[0]
        log_callback(f"Creating zip file: {archive_name_base}.zip")
        shutil.make_archive(archive_name_base, 'zip', temp_dir)
        log_callback("Successfully created zip archive.")

        changelog_path = f"{archive_name_base}.txt"
        log_callback(f"Creating changelog file: {changelog_path}")
        with open(changelog_path, 'w', encoding='utf-8') as f:
            f.write(f"Changelog for {os.path.basename(archive_name_base)}.zip\n")
            f.write("="*40 + "\n")
            f.write(f"Repository: {os.path.abspath(repo_path)}\n")
            f.write(changelog_range_info + "\n")
            f.write("="*40 + "\n\n")
            f.write(f"Archived Files ({len(archived_files)}):\n")
            f.write("---"*10 + "\n")
            for file_path in archived_files:
                f.write(f"{file_path}\n")
        log_callback("Successfully created changelog file.")
        log_callback("\n--- PROCESS COMPLETE ---")

    except Exception as e:
        log_callback(f"\nAn unexpected error occurred: {e}")
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

