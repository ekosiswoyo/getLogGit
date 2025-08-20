# 🎉 Git Archive Generator v2.0.0

A major update with enhanced commit tracking, merge commit support, and improved changelog format!

## ✨ New Features

### 📝 **Detailed Commit Information**
- **Commit Message**: Shows the full commit message for each commit
- **Author Details**: Displays author name and email address
- **Commit Date**: Shows when each commit was made (ISO format)
- **Commit Hash**: Displays shortened commit hash for easy reference

### 🔀 **Merge Commit Support**
- **Smart Detection**: Automatically detects merge commits
- **Special Handling**: Uses appropriate Git commands (`--cc`, `diff-tree`) for merge commits
- **Visual Indicators**: Merge commits are clearly marked with `[MERGE]` tag
- **Better File Tracking**: Now correctly shows files involved in merge commits

### 📊 **Enhanced Changelog Format**
- **File Grouping**: Files are now grouped by the commit that changed them
- **Per-Commit Breakdown**: See exactly which files were modified in each commit
- **Comprehensive Statistics**: 
  - Total commits processed
  - Total unique files archived
  - Total file changes across all commits
- **Professional Layout**: Clean, readable format with proper sections and separators

## 🔧 Improvements

### 🎯 **File Tracking**
- Files that appear in multiple commits are now shown under each relevant commit
- Better handling of edge cases (empty commits, deleted files)
- More accurate file change detection

### 🖥️ **User Experience**
- Both CLI and GUI versions benefit from all improvements
- More informative error messages
- Better progress feedback during processing

## 📋 **Example Output Format**

```
Changelog for my_archive.zip
======================================================================
Repository: D:\Path\To\Repository
Branch: main
Date Range: 2024-01-01 to 2024-01-31
Total Files Archived: 8
======================================================================

Commits with Changed Files (3):
======================================================================

[1] Commit: a1b2c3d4e5
    Author: John Doe <john@example.com>
    Date: 2024-01-15 10:30:45 +0700
    Message: Add user authentication feature
    Files Changed (4):
      - src/auth/login.py
      - src/auth/register.py
      - tests/test_auth.py
      - requirements.txt
------------------------------------------------------------

[2] Commit: f6g7h8i9j0 [MERGE]
    Author: Jane Smith <jane@example.com>
    Date: 2024-01-20 14:22:10 +0700
    Message: Merge branch 'feature/validation' into 'main'
    Type: Merge Commit
    Files Changed (2):
      - src/validation.py
      - tests/test_validation.py
------------------------------------------------------------

Summary:
- Total commits: 3
- Total unique files archived: 8
- Total file changes across all commits: 9
```

## 📦 **What's Included**

- **`git_archive_by_date.exe`** - Command Line Interface (CLI) version
- **`git_archive_ui.exe`** - Graphical User Interface (GUI) version

Both executables are standalone and don't require Python installation.

## 🚀 **Usage**

### GUI Version (Recommended for most users)
1. Download `git_archive_ui.exe`
2. Double-click to run
3. Follow the intuitive interface

### CLI Version (For developers and automation)
```bash
git_archive_by_date.exe "C:\path\to\repo" -o "my_archive" -b "main" -s "2024-01-01" -e "2024-01-31"
```

## 🔄 **Supported Modes**

- **Date Range**: Archive files changed between two dates on a specific branch
- **SHA Range**: Archive files changed between two commit SHAs  
- **Single Commit**: Archive files from a specific commit (including merge commits)

## 🐛 **Bug Fixes**

- Fixed merge commit file detection (previously showed 0 files)
- Improved file path handling for complex directory structures
- Better error handling for edge cases
- Fixed timezone display in commit dates

## 💡 **Technical Details**

- Built with Python 3.10+ and PyInstaller
- Uses advanced Git commands for accurate file tracking
- Optimized for Windows environments
- Comprehensive error handling and logging

## 🙏 **Credits**

Created by **ekosiswoyo** with ❤️

---

### 📥 **Download**

Choose the version that fits your needs:
- 🖥️ **GUI Version**: `git_archive_ui.exe` (Recommended for most users)
- ⚡ **CLI Version**: `git_archive_by_date.exe` (For automation and scripting)

### 🔗 **System Requirements**
- Windows 10/11
- Git installed and available in PATH
- No Python installation required
