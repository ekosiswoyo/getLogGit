
# Git Archive Generator

A user-friendly tool, available in both GUI and CLI versions, to archive files from a Git repository based on commit history over a specific date range, commit range, or from a single commit.

This tool creates a `.zip` file containing the specified files and a `.txt` changelog detailing the contents.

![Screenshot of the GUI application](placeholder.png)

## Features

- **Graphical User Interface (GUI):** An easy-to-use interface for non-technical users.
- **Command-Line Interface (CLI):** A powerful and scriptable interface for developers.
- **Cross-Platform:** Runs on Windows, macOS, and Linux from the source code.
- **Multiple Selection Modes:**
  - **Date Range:** Archive all changes on a specific branch within a start and end date.
  - **SHA Range:** Archive all changes between two specific commit SHAs.
  - **Single Commit:** Archive only the files that were modified in one specific commit.
- **Dual Output:**
  - Creates a `.zip` archive with the full directory structure preserved.
  - Creates a `.txt` changelog file listing all included files and the range criteria.
- **Portable Executable:** Can be packaged into a standalone executable for easy distribution.

---

## How to Use (for End-Users)

1.  Go to the [**Releases**](https://github.com/ekosiswoyo/getLogGit/releases) page of this repository.
2.  Download the latest `.exe` file (`git_archive_ui.exe` for the graphical version is recommended).
3.  Double-click `git_archive_ui.exe` to run the application.
4.  Follow the on-screen instructions:
    -   Browse for your local Git repository folder.
    -   Choose where to save the output `.zip` file.
    -   Select your desired mode (Date, SHA Range, or Single Commit).
    -   Fill in the parameters.
    -   Click "Create Archive".

---

## How to Run from Source (for Developers)

If you want to run or modify the source code directly.

**Prerequisites:**
- [Git](https://git-scm.com/)
- [Python 3](https://www.python.org/)

**Instructions:**

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/ekosiswoyo/getLogGit.git
    cd your-repo-name
    ```

2.  **Run the GUI version:**
    ```bash
    python git_archive_ui.py
    ```

3.  **Run the CLI version:**
    ```bash
    # See all options
    python git_archive_by_date.py --help

    # Example: by single commit
    python git_archive_by_date.py "C:\path\to\your\repo" -o my_archive --commit-sha <commit_hash>

    # Example: by SHA range
    python git_archive_by_date.py "C:\path\to\your\repo" -o my_archive --start-sha <starting_commit_hash> --end-sha <ending_commit_hash>

    # Example: by date range
    python git_archive_by_date.py "C:\path\to\your\repo" -o my_archive --branch main --start-date YYYY-MM-DD --end-date YYYY-MM-DD
    
    ```


### Building Your Own Executable

To create the executable file yourself:

1.  **Install dependencies:**
    ```bash
    pip install pyinstaller
    ```

2.  **Build the executable:**
    *   For Windows (`.exe`):
        ```bash
        # GUI App
        pyinstaller --onefile --windowed git_archive_ui.py
        # CLI App
        pyinstaller --onefile git_archive_by_date.py
        ```
    *   For macOS (`.app`):
        ```bash
        # GUI App
        pyinstaller --onefile --windowed git_archive_ui.py
        # CLI App
        pyinstaller --onefile git_archive_by_date.py
        ```

3.  The final executable will be located in the `dist/` folder.

---

## Author

Created by **ekosiswoyo**

