import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import os
import threading
import queue
import json
from datetime import datetime

# Import the refactored logic from the other file
from git_archive_by_date import archive_git_history, get_file_list_preview
from history_manager import HistoryManager

class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Git Archive Generator")
        self.geometry("650x720") # Adjusted height to ensure footer is visible
        self.resizable(False, False)
        
        # Threading control
        self.cancel_event = None
        self.archive_thread = None
        
        # History manager
        self.history_manager = HistoryManager()
        self._history_entries = {}  # Store history entries for reference
        
        # Set icon
        try:
            # Try .ico first (Windows standard), then .png
            if os.path.exists('logo.ico'):
                self.iconbitmap('logo.ico')
            elif os.path.exists('logo.png'):
                # Try to use PNG (may not work on all Windows versions)
                try:
                    self.iconbitmap('logo.png')
                except:
                    # If PNG doesn't work, try to convert or skip
                    pass
        except:
            pass

        # --- Main Frame ---
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- File/Folder Selection ---
        file_frame = ttk.LabelFrame(main_frame, text="1. Select Paths", padding="10")
        file_frame.pack(fill=tk.X, pady=5)

        self.repo_path = tk.StringVar()
        self.output_path = tk.StringVar()

        ttk.Label(file_frame, text="Git Repo Folder:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(file_frame, textvariable=self.repo_path, width=60).grid(row=0, column=1, sticky=tk.EW)
        ttk.Button(file_frame, text="Browse...", command=self.browse_repo).grid(row=0, column=2, padx=5)

        ttk.Label(file_frame, text="Output File:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(file_frame, textvariable=self.output_path, width=60).grid(row=1, column=1, sticky=tk.EW)
        ttk.Button(file_frame, text="Save As...", command=self.browse_output).grid(row=1, column=2, padx=5)
        
        # Archive Format Selection
        self.archive_format = tk.StringVar(value="zip")
        ttk.Label(file_frame, text="Archive Format:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        format_combo = ttk.Combobox(file_frame, textvariable=self.archive_format, values=["zip", "tar", "gztar"], 
                                    state="readonly", width=57)
        format_combo.grid(row=2, column=1, sticky=tk.EW, padx=5)
        format_combo.bind("<<ComboboxSelected>>", self.on_format_change)
        file_frame.columnconfigure(1, weight=1)

        # --- Mode Selection ---
        mode_frame = ttk.LabelFrame(main_frame, text="2. Select Mode", padding="10")
        mode_frame.pack(fill=tk.X, pady=5)

        self.mode = tk.StringVar(value="date")
        
        ttk.Radiobutton(mode_frame, text="Date Range", variable=self.mode, value="date", command=self.on_mode_change).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(mode_frame, text="SHA Range", variable=self.mode, value="sha_range", command=self.on_mode_change).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(mode_frame, text="Single Commit", variable=self.mode, value="commit_sha", command=self.on_mode_change).pack(side=tk.LEFT, padx=10)

        # --- Parameters Frame ---
        self.params_frame = ttk.LabelFrame(main_frame, text="3. Parameters", padding="10")
        self.params_frame.pack(fill=tk.X, pady=5)

        # Parameters for Date Mode
        self.date_frame = ttk.Frame(self.params_frame)
        self.start_date = tk.StringVar()
        self.end_date = tk.StringVar()
        self.branch = tk.StringVar(value="main")
        ttk.Label(self.date_frame, text="Start Date (YYYY-MM-DD):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.start_date_entry = ttk.Entry(self.date_frame, textvariable=self.start_date)
        self.start_date_entry.grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Label(self.date_frame, text="End Date (YYYY-MM-DD):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.end_date_entry = ttk.Entry(self.date_frame, textvariable=self.end_date)
        self.end_date_entry.grid(row=1, column=1, sticky=tk.EW, padx=5)
        ttk.Label(self.date_frame, text="Branch:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.branch_entry = ttk.Entry(self.date_frame, textvariable=self.branch)
        self.branch_entry.grid(row=2, column=1, sticky=tk.EW, padx=5)

        # Parameters for SHA Range Mode
        self.sha_range_frame = ttk.Frame(self.params_frame)
        self.start_sha = tk.StringVar()
        self.end_sha = tk.StringVar()
        ttk.Label(self.sha_range_frame, text="Start SHA:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.start_sha_entry = ttk.Entry(self.sha_range_frame, textvariable=self.start_sha, width=40)
        self.start_sha_entry.grid(row=0, column=1, sticky=tk.EW, padx=5)
        ttk.Label(self.sha_range_frame, text="End SHA:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.end_sha_entry = ttk.Entry(self.sha_range_frame, textvariable=self.end_sha, width=40)
        self.end_sha_entry.grid(row=1, column=1, sticky=tk.EW, padx=5)

        # Parameters for Single Commit Mode
        self.commit_sha_frame = ttk.Frame(self.params_frame)
        self.commit_sha = tk.StringVar()
        ttk.Label(self.commit_sha_frame, text="Commit SHA:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.commit_sha_entry = ttk.Entry(self.commit_sha_frame, textvariable=self.commit_sha, width=40)
        self.commit_sha_entry.grid(row=0, column=1, sticky=tk.EW, padx=5)

        self.on_mode_change() # Set initial state

        # --- Progress Bar ---
        progress_frame = ttk.Frame(main_frame, padding="10")
        progress_frame.pack(fill=tk.X, pady=5)
        self.progress_var = tk.StringVar(value="Ready")
        self.progress_label = ttk.Label(progress_frame, textvariable=self.progress_var)
        self.progress_label.pack(anchor=tk.W, pady=(0, 5))
        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate', maximum=100)
        self.progress_bar.pack(fill=tk.X)
        
        # --- Action Buttons ---
        action_frame = ttk.Frame(main_frame, padding="10")
        action_frame.pack(fill=tk.X, pady=10)
        button_container = ttk.Frame(action_frame)
        button_container.pack(fill=tk.X)
        self.preview_button = ttk.Button(button_container, text="Preview Files", command=self.preview_files)
        self.preview_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.run_button = ttk.Button(button_container, text="Create Archive", command=self.start_archive_process)
        self.run_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.cancel_button = ttk.Button(button_container, text="Cancel", command=self.cancel_archive_process, state='disabled')
        self.cancel_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        # --- Log Area ---
        log_frame = ttk.LabelFrame(main_frame, text="Logs", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_area = scrolledtext.ScrolledText(log_frame, height=3, state='disabled', wrap=tk.WORD)
        self.log_area.pack(fill=tk.BOTH, expand=True)

        # --- Footer ---
        footer_frame = ttk.Frame(main_frame)
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(5, 0))
        ttk.Separator(footer_frame).pack(fill=tk.X, pady=(0, 5))
        footer_content = ttk.Frame(footer_frame)
        footer_content.pack(fill=tk.X)
        ttk.Button(footer_content, text="History", command=self.show_history, width=10).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(footer_content, text="Developed by ekosiswoyo", anchor=tk.E).pack(side=tk.RIGHT, fill=tk.X, expand=True)

        # --- Threading and Queue for logging ---
        self.log_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        self.after(100, self.process_log_queue)
        self.after(100, self.process_progress_queue)
        
        # Center window on screen after all widgets are created
        # Use longer delay to ensure window is fully rendered
        self.after(200, self.center_window)

    def center_window(self):
        """Center the window on the screen and position it above taskbar"""
        # Force update to get accurate window size
        self.update_idletasks()
        
        # Use fixed size from initial geometry
        width, height = 650, 720
        
        # Try to get actual window size
        try:
            actual_width = self.winfo_width()
            actual_height = self.winfo_height()
            if actual_width > 100 and actual_height > 100:  # Valid window size
                width, height = actual_width, actual_height
        except:
            pass  # Use default size
        
        # Get screen dimensions
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Calculate position to center window
        # Offset upward to avoid taskbar overlap (typically 40-50px on Windows)
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2 - 40  # Offset 40px up to avoid taskbar
        
        # Ensure window is not off-screen
        if y < 0:
            y = 10  # Minimum 10px from top
        
        # Set geometry with position - ensure size is set correctly
        self.geometry(f"{width}x{height}+{x}+{y}")

    def browse_repo(self):
        path = filedialog.askdirectory(title="Select Git Repository Folder")
        if path:
            self.repo_path.set(path)

    def on_format_change(self, event=None):
        """Update output file extension when format changes"""
        current_path = self.output_path.get()
        if current_path:
            # Remove old extension
            for ext in ['.zip', '.tar', '.tar.gz', '.gz']:
                if current_path.lower().endswith(ext):
                    current_path = current_path[:-len(ext)]
                    break
            # Add new extension
            format_ext = {'zip': '.zip', 'tar': '.tar', 'gztar': '.tar.gz'}.get(self.archive_format.get(), '.zip')
            self.output_path.set(current_path + format_ext)
    
    def browse_output(self):
        format_ext = {'zip': '.zip', 'tar': '.tar', 'gztar': '.tar.gz'}.get(self.archive_format.get(), '.zip')
        filetypes_map = {
            'zip': [("Zip files", "*.zip")],
            'tar': [("Tar files", "*.tar")],
            'gztar': [("Gzip Tar files", "*.tar.gz"), ("Tar GZ files", "*.gz")]
        }
        path = filedialog.asksaveasfilename(
            title="Save Archive As",
            defaultextension=format_ext,
            filetypes=filetypes_map.get(self.archive_format.get(), [("All files", "*.*")])
        )
        if path:
            self.output_path.set(path)

    def on_mode_change(self):
        mode = self.mode.get()
        # Hide all frames first
        self.date_frame.pack_forget()
        self.sha_range_frame.pack_forget()
        self.commit_sha_frame.pack_forget()
        # Show the correct frame
        if mode == 'date':
            self.date_frame.pack(fill=tk.X)
        elif mode == 'sha_range':
            self.sha_range_frame.pack(fill=tk.X)
        elif mode == 'commit_sha':
            self.commit_sha_frame.pack(fill=tk.X)

    def log(self, message):
        self.log_queue.put(message)

    def process_log_queue(self):
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.log_area.config(state='normal')
                self.log_area.insert(tk.END, message + '\n')
                self.log_area.see(tk.END) # Scroll to the bottom
                self.log_area.config(state='disabled')
        except queue.Empty:
            pass
        self.after(100, self.process_log_queue)
    
    def process_progress_queue(self):
        try:
            while True:
                progress_data = self.progress_queue.get_nowait()
                progress_value, message = progress_data
                self.progress_bar['value'] = progress_value
                self.progress_var.set(message)
        except queue.Empty:
            pass
        self.after(100, self.process_progress_queue)
    
    def update_progress(self, value, message):
        """Update progress bar from any thread"""
        self.progress_queue.put((value, message))

    def start_archive_process(self):
        self.run_button.config(state='disabled')
        self.cancel_button.config(state='normal')
        self.progress_bar['value'] = 0
        self.progress_var.set("Starting...")
        self.log_area.config(state='normal')
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state='disabled')
        self.log("--- STARTING PROCESS ---\n")

        # Create cancel event for this process
        self.cancel_event = threading.Event()

        params = {
            'log_callback': self.log,
            'progress_callback': self.update_progress,
            'cancel_event': self.cancel_event,
            'repo_path': self.repo_path.get(),
            'output_zip': self.output_path.get(),
            'mode': self.mode.get(),
            'archive_format': self.archive_format.get(),
            'start_date': self.start_date.get(),
            'end_date': self.end_date.get(),
            'branch': self.branch.get(),
            'start_sha': self.start_sha.get(),
            'end_sha': self.end_sha.get(),
            'commit_sha': self.commit_sha.get()
        }

        # Basic validation
        if not params['repo_path'] or not params['output_zip']:
            self.log("Error: Repository path and Output file must be selected.")
            self.log("\n--- PROCESS ABORTED ---")
            self.run_button.config(state='normal')
            self.cancel_button.config(state='disabled')
            self.progress_bar['value'] = 0
            self.progress_var.set("Ready")
            return

        # Run the logic in a separate thread to avoid freezing the UI
        self.archive_thread = threading.Thread(target=archive_git_history, args=(params,))
        self.archive_thread.daemon = True
        self.archive_thread.start()

        # Periodically check if the thread is done
        self.check_thread(self.archive_thread)

    def cancel_archive_process(self):
        """Cancel the current archive process"""
        if self.cancel_event:
            self.cancel_event.set()
            self.log("--- CANCELLING PROCESS ---")
            self.cancel_button.config(state='disabled')
            # Wait a bit for the thread to finish, then re-enable buttons
            self.after(500, self.reset_ui_after_cancel)

    def reset_ui_after_cancel(self):
        """Reset UI after cancellation"""
        self.run_button.config(state='normal')
        self.cancel_button.config(state='disabled')
        self.progress_bar['value'] = 0
        self.progress_var.set("Ready")
        self.cancel_event = None
        self.archive_thread = None

    def check_thread(self, thread):
        if thread.is_alive():
            self.after(100, lambda: self.check_thread(thread))
        else:
            self.run_button.config(state='normal')
            self.cancel_button.config(state='disabled')
            if not self.cancel_event or not self.cancel_event.is_set():
                # Only reset progress if not cancelled
                if self.progress_bar['value'] < 100:
                    self.progress_bar['value'] = 0
                    self.progress_var.set("Ready")
                # Save to history if successful
                if self.progress_bar['value'] == 100:
                    self.save_to_history()
            self.cancel_event = None
            self.archive_thread = None
    
    def save_to_history(self):
        """Save current operation to history"""
        params = {
            'start_date': self.start_date.get(),
            'end_date': self.end_date.get(),
            'branch': self.branch.get(),
            'start_sha': self.start_sha.get(),
            'end_sha': self.end_sha.get(),
            'commit_sha': self.commit_sha.get()
        }
        self.history_manager.add_entry(
            repo_path=self.repo_path.get(),
            output_path=self.output_path.get(),
            mode=self.mode.get(),
            parameters=params,
            archive_format=self.archive_format.get()
        )
    
    def preview_files(self):
        """Preview files that will be archived"""
        if not self.repo_path.get():
            self.log("Error: Please select a repository path first.")
            return
        
        params = {
            'repo_path': self.repo_path.get(),
            'mode': self.mode.get(),
            'start_date': self.start_date.get(),
            'end_date': self.end_date.get(),
            'branch': self.branch.get(),
            'start_sha': self.start_sha.get(),
            'end_sha': self.end_sha.get(),
            'commit_sha': self.commit_sha.get()
        }
        
        # Validate required parameters
        if params['mode'] == 'date' and (not params['start_date'] or not params['end_date'] or not params['branch']):
            self.log("Error: Please fill in all required parameters for Date Range mode.")
            return
        elif params['mode'] == 'sha_range' and (not params['start_sha'] or not params['end_sha']):
            self.log("Error: Please fill in both Start SHA and End SHA for SHA Range mode.")
            return
        elif params['mode'] == 'commit_sha' and not params['commit_sha']:
            self.log("Error: Please fill in Commit SHA for Single Commit mode.")
            return
        
        # Run preview in thread
        def run_preview():
            result = get_file_list_preview(params)
            self.after(0, lambda: self.show_preview_window(result))
        
        thread = threading.Thread(target=run_preview)
        thread.daemon = True
        thread.start()
        self.log("Loading preview...")
    
    def show_preview_window(self, result):
        """Show preview window with file list"""
        preview_window = tk.Toplevel(self)
        preview_window.title("File Preview")
        preview_window.geometry("600x500")
        
        if result.get('error'):
            error_label = ttk.Label(preview_window, text=f"Error: {result['error']}", foreground='red')
            error_label.pack(pady=10)
            ttk.Button(preview_window, text="Close", command=preview_window.destroy).pack(pady=10)
            return
        
        # Header
        header_frame = ttk.Frame(preview_window, padding="10")
        header_frame.pack(fill=tk.X)
        ttk.Label(header_frame, text=f"Total Files: {result['total_files']}", font=('Arial', 10, 'bold')).pack()
        if result.get('commit_hash'):
            ttk.Label(header_frame, text=f"Commit: {result['commit_hash'][:10]}", font=('Arial', 9)).pack()
        
        # File list
        list_frame = ttk.Frame(preview_window)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        file_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=('Courier', 9))
        file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=file_listbox.yview)
        
        for file_path in result['files']:
            file_listbox.insert(tk.END, file_path)
        
        # Close button
        ttk.Button(preview_window, text="Close", command=preview_window.destroy).pack(pady=10)
    
    def show_history(self):
        """Show history window"""
        history_window = tk.Toplevel(self)
        history_window.title("Operation History")
        history_window.geometry("700x500")
        
        # Header
        header_frame = ttk.Frame(history_window, padding="10")
        header_frame.pack(fill=tk.X)
        ttk.Label(header_frame, text="Operation History", font=('Arial', 12, 'bold')).pack()
        
        # History list
        list_frame = ttk.Frame(history_window)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        history_tree = ttk.Treeview(list_frame, columns=("Timestamp", "Mode", "Repo", "Output"), 
                                    show="headings", yscrollcommand=scrollbar.set)
        history_tree.heading("Timestamp", text="Timestamp")
        history_tree.heading("Mode", text="Mode")
        history_tree.heading("Repo", text="Repository")
        history_tree.heading("Output", text="Output Path")
        history_tree.column("Timestamp", width=150)
        history_tree.column("Mode", width=100)
        history_tree.column("Repo", width=200)
        history_tree.column("Output", width=200)
        history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=history_tree.yview)
        
        # Populate history
        history = self.history_manager.get_history()
        for entry in history:
            timestamp = entry.get('timestamp', '')
            try:
                dt = datetime.fromisoformat(timestamp)
                timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass
            mode = entry.get('mode', 'unknown')
            repo = os.path.basename(entry.get('repo_path', '')) if entry.get('repo_path') else entry.get('repo_path', '')
            output = os.path.basename(entry.get('output_path', '')) if entry.get('output_path') else entry.get('output_path', '')
            # Store entry as string in tags (convert dict to string representation)
            entry_str = str(id(entry))  # Use ID as reference
            history_tree.insert("", tk.END, values=(timestamp, mode, repo, output), tags=(entry_str,))
            # Store actual entry in a dictionary
            if not hasattr(self, '_history_entries'):
                self._history_entries = {}
            self._history_entries[entry_str] = entry
        
        # Buttons
        button_frame = ttk.Frame(history_window, padding="10")
        button_frame.pack(fill=tk.X)
        
        def load_selected():
            selection = history_tree.selection()
            if selection:
                item = history_tree.item(selection[0])
                entry_id = item['tags'][0] if item['tags'] else None
                if entry_id and hasattr(self, '_history_entries') and entry_id in self._history_entries:
                    entry = self._history_entries[entry_id]
                    self.load_from_history(entry)
                    history_window.destroy()
        
        def clear_history():
            self.history_manager.clear_history()
            history_window.destroy()
            self.show_history()  # Refresh
        
        ttk.Button(button_frame, text="Load Selected", command=load_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear History", command=clear_history).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Close", command=history_window.destroy).pack(side=tk.RIGHT, padx=5)
    
    def load_from_history(self, entry):
        """Load parameters from history entry"""
        self.repo_path.set(entry.get('repo_path', ''))
        self.output_path.set(entry.get('output_path', ''))
        self.mode.set(entry.get('mode', 'date'))
        self.archive_format.set(entry.get('archive_format', 'zip'))
        
        params = entry.get('parameters', {})
        self.start_date.set(params.get('start_date', ''))
        self.end_date.set(params.get('end_date', ''))
        self.branch.set(params.get('branch', 'main'))
        self.start_sha.set(params.get('start_sha', ''))
        self.end_sha.set(params.get('end_sha', ''))
        self.commit_sha.set(params.get('commit_sha', ''))
        
        self.on_mode_change()
        self.log("Loaded configuration from history.")
    

if __name__ == "__main__":
    app = App()
    app.mainloop()