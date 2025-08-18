import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
import os
import threading
import queue

# Import the refactored logic from the other file
from git_archive_by_date import archive_git_history

class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Git Archive Generator")
        self.geometry("650x620") # Adjusted height for footer
        self.resizable(False, False)

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

        ttk.Label(file_frame, text="Output File (.zip):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(file_frame, textvariable=self.output_path, width=60).grid(row=1, column=1, sticky=tk.EW)
        ttk.Button(file_frame, text="Save As...", command=self.browse_output).grid(row=1, column=2, padx=5)
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

        # --- Action Button ---
        action_frame = ttk.Frame(main_frame, padding="10")
        action_frame.pack(fill=tk.X, pady=10)
        self.run_button = ttk.Button(action_frame, text="Create Archive", command=self.start_archive_process)
        self.run_button.pack(fill=tk.X)

        # --- Log Area ---
        log_frame = ttk.LabelFrame(main_frame, text="Logs", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_area = scrolledtext.ScrolledText(log_frame, height=10, state='disabled', wrap=tk.WORD)
        self.log_area.pack(fill=tk.BOTH, expand=True)

        # --- Footer ---
        footer_frame = ttk.Frame(main_frame)
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(5,0))
        ttk.Separator(footer_frame).pack(fill=tk.X, pady=(0,5))
        ttk.Label(footer_frame, text="Created by ekosiswoyo", anchor=tk.E).pack(fill=tk.X)

        # --- Threading and Queue for logging ---
        self.log_queue = queue.Queue()
        self.after(100, self.process_log_queue)

    def browse_repo(self):
        path = filedialog.askdirectory(title="Select Git Repository Folder")
        if path:
            self.repo_path.set(path)

    def browse_output(self):
        path = filedialog.asksaveasfilename(
            title="Save Archive As",
            defaultextension=".zip",
            filetypes=[("Zip files", "*.zip")]
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

    def start_archive_process(self):
        self.run_button.config(state='disabled')
        self.log_area.config(state='normal')
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state='disabled')
        self.log("--- STARTING PROCESS ---\n")

        params = {
            'log_callback': self.log,
            'repo_path': self.repo_path.get(),
            'output_zip': self.output_path.get(),
            'mode': self.mode.get(),
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
            return

        # Run the logic in a separate thread to avoid freezing the UI
        thread = threading.Thread(target=archive_git_history, args=(params,))
        thread.daemon = True
        thread.start()

        # Periodically check if the thread is done
        self.check_thread(thread)

    def check_thread(self, thread):
        if thread.is_alive():
            self.after(100, lambda: self.check_thread(thread))
        else:
            self.run_button.config(state='normal')

if __name__ == "__main__":
    app = App()
    app.mainloop()