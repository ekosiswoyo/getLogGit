import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import os
import sys
import json
import threading
import queue
import subprocess
import calendar
import webbrowser
from datetime import datetime, timedelta, date

# Import the refactored logic from the other file
from git_archive_by_date import (archive_git_history, get_file_list_preview,
                                 get_recent_commits, get_repository_info, is_git_repository)
from history_manager import HistoryManager
from app_storage import data_directory, legacy_paths
from remote_repository import prepare_repository, normalize_url
from rounded_theme import install_rounded_elements
from macos_icon import set_dock_icon


# ---------------------------------------------------------------------------
# Theme / color palettes
# ---------------------------------------------------------------------------
PALETTES = {
    "dark": {
        "BG": "#1c1c1e",
        "CARD": "#2c2c2e",
        "CARD_ALT": "#363638",
        "BORDER": "#48484a",
        "TEXT": "#f2f2f7",
        "TEXT_MUTED": "#98989d",
        "ACCENT": "#007aff",
        "ACCENT_HOVER": "#409cff",
        "DANGER": "#ef4444",
        "DANGER_HOVER": "#f87171",
        "WARN": "#f59e0b",
        "OK": "#22c55e",
        "INPUT_BG": "#232325",
        "DISABLED_BG": "#48484a",
        "DISABLED_FG": "#98989d",
        "SECONDARY_BG": "#363638",
        "SECONDARY_HOVER": "#48484a",
        "SECONDARY_FG": "#f2f2f7",
    },
    "light": {
        "BG": "#f5f5f7",
        "CARD": "#ffffff",
        "CARD_ALT": "#f2f2f7",
        "BORDER": "#d1d1d6",
        "TEXT": "#2c2c2e",
        "TEXT_MUTED": "#6c6c70",
        "ACCENT": "#007aff",
        "ACCENT_HOVER": "#409cff",
        "DANGER": "#ef4444",
        "DANGER_HOVER": "#f87171",
        "WARN": "#d97706",
        "OK": "#16a34a",
        "INPUT_BG": "#ffffff",
        "DISABLED_BG": "#d1d1d6",
        "DISABLED_FG": "#98989d",
        "SECONDARY_BG": "#f2f2f7",
        "SECONDARY_HOVER": "#d1d1d6",
        "SECONDARY_FG": "#2c2c2e",
    },
}

FONT_PRIMARY = "Helvetica Neue" if sys.platform == "darwin" else "Segoe UI"
FONT_FALLBACK = "DejaVu Sans"
MONO_FONT = "Consolas" if os.name == "nt" else "Menlo" if sys.platform == "darwin" else "monospace"
SETTINGS_FILE = data_directory() / "settings.json"


def resource_path(rel):
    """Resolve a bundled resource path (works for PyInstaller --onefile and source)."""
    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
    return os.path.join(base, rel)


class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Git Archive Generator")
        self.geometry("780x900")
        self.minsize(700, 700)

        # Threading control
        self.cancel_event = None
        self.archive_thread = None
        self.git_pull_thread = None

        # History manager
        try:
            self.history_manager = HistoryManager()
        except OSError as exc:
            messagebox.showwarning("History", f"Could not migrate history: {exc}")
            self.history_manager = HistoryManager(history_file=data_directory() / "history.json")
        self._history_entries = {}

        # Theme state
        self.theme_name = self._load_theme_pref()
        self.C = PALETTES[self.theme_name]

        # Registry of (widget, apply_fn) for live theming
        self._theme_appliers = []

        self.ui_font = self._resolve_font()

        # Set icon
        try:
            ico = resource_path('logo.ico')
            png = resource_path('logo.png')
            if sys.platform == "win32" and os.path.exists(ico):
                self.iconbitmap(ico)
            elif os.path.exists(png):
                try:
                    self._icon_img = tk.PhotoImage(file=png)
                    self.iconphoto(True, self._icon_img)
                except Exception:
                    pass
        except Exception:
            pass

        if sys.platform == "darwin":
            try:
                self._dock_icon_set = set_dock_icon(resource_path('logo.png'))
            except (OSError, AttributeError):
                self._dock_icon_set = False

        self.style = ttk.Style(self)
        try:
            self.style.theme_use('clam')
        except tk.TclError:
            pass

        install_rounded_elements(self, PALETTES)

        # State vars
        self.repo_path = tk.StringVar()
        self.source_mode = tk.StringVar(value="Local folder")
        self.remote_url = tk.StringVar()
        self.remote_url.trace_add("write", lambda *args: self.invalidate_remote())
        self.remote_busy = False
        self.remote_connected_url = ''
        self.output_path = tk.StringVar()
        self.archive_format = tk.StringVar(value="zip")
        self.changelog_format = tk.StringVar(value="txt")
        self.mode = tk.StringVar(value="date")
        self.start_date = tk.StringVar()
        self.end_date = tk.StringVar()
        self.branch = tk.StringVar(value="main")
        self.author = tk.StringVar()
        self.start_sha = tk.StringVar()
        self.exclude_start = tk.BooleanVar(value=False)
        self.end_sha = tk.StringVar()
        self.commit_sha = tk.StringVar()
        self.start_tag = tk.StringVar()
        self.end_tag = tk.StringVar()
        self.exclude_patterns = tk.StringVar(value=".git/*; .env; node_modules/*; __pycache__/*")
        self.selected_files = None

        # Outer container
        self.outer = tk.Frame(self)
        self.outer.pack(fill=tk.BOTH, expand=True)
        self._track(self.outer, lambda w, C: w.config(bg=C["BG"]))
        self._track(self, lambda w, C: w.config(bg=C["BG"]))

        self._build_header(self.outer)

        body_shell = tk.Frame(self.outer)
        body_shell.pack(fill=tk.BOTH, expand=True, padx=(18, 6), pady=(4, 0))
        self._track(body_shell, lambda w, C: w.config(bg=C["BG"]))
        body_canvas = tk.Canvas(body_shell, highlightthickness=0, bd=0)
        body_scroll = ttk.Scrollbar(body_shell, orient=tk.VERTICAL, command=body_canvas.yview,
                                    style="Modern.Vertical.TScrollbar")
        body_canvas.configure(yscrollcommand=body_scroll.set)
        body_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        body_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._track(body_canvas, lambda w, C: w.config(bg=C["BG"]))
        body = tk.Frame(body_canvas)
        body_window = body_canvas.create_window((0, 0), window=body, anchor=tk.NW)
        body.bind("<Configure>", lambda e: body_canvas.configure(scrollregion=body_canvas.bbox("all")))
        body_canvas.bind("<Configure>", lambda e: body_canvas.itemconfigure(body_window, width=e.width))
        def scroll_body(event):
            if event.widget.winfo_toplevel() != self or isinstance(event.widget, (tk.Text, ttk.Treeview)):
                return
            delta = -event.delta if sys.platform == "darwin" else int(-event.delta / 120)
            body_canvas.yview_scroll(int(delta), "units")
        body_canvas.bind_all("<MouseWheel>", scroll_body)
        self._track(body, lambda w, C: w.config(bg=C["BG"]))

        self._build_paths_card(body)
        self._build_mode_card(body)
        self._build_params_card(body)
        self._build_progress(body)
        self._build_actions(body)
        self._build_log(body)
        self._build_footer(self.outer)

        self.on_mode_change()
        self.apply_theme()

        # Real-time validation triggers
        for var in (self.repo_path, self.start_date, self.end_date):
            var.trace_add("write", lambda *a: self._validate_inputs())
        self._validate_inputs()

        # Threading and queues
        self.ui_queue = queue.Queue()
        self.completion_queue = queue.Queue()
        self.log_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        self.after(100, self.process_log_queue)
        self.after(100, self.process_progress_queue)
        self.after(100, self.process_completion_queue)

        self.after(200, self.center_window)

    # ------------------------------------------------------------------
    # Theme infrastructure
    # ------------------------------------------------------------------
    def _track(self, widget, apply_fn):
        """Register a widget with a (widget, palette) -> None applier."""
        self._theme_appliers.append((widget, apply_fn))

    def apply_theme(self):
        C = self.C
        self._style_ttk(C)
        for widget, fn in self._theme_appliers:
            try:
                if widget.winfo_exists():
                    fn(widget, C)
            except tk.TclError:
                pass
        self._refresh_mode_buttons()
        def update_fields(parent):
            for child in parent.winfo_children():
                if isinstance(child, ttk.Combobox):
                    child.configure(style=f"{self.theme_name}.Modern.TCombobox")
                elif isinstance(child, ttk.Entry):
                    child.configure(style=f"{self.theme_name}.Modern.TEntry")
                update_fields(child)
        update_fields(self)

    def toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.C = PALETTES[self.theme_name]
        self._save_theme_pref()
        self.apply_theme()
        if hasattr(self, "theme_button"):
            self.theme_button.config(text=self._theme_button_label())
        self._validate_inputs()

    def _theme_button_label(self):
        return "Light Mode" if self.theme_name == "dark" else "Dark Mode"

    def _load_theme_pref(self):
        try:
            candidates = [SETTINGS_FILE] if SETTINGS_FILE.exists() else legacy_paths("settings.json")
            for candidate in candidates:
                if not candidate.is_file():
                    continue
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    name = data.get("theme", "dark")
                    if name in PALETTES:
                        return name
        except Exception:
            pass
        return "dark"

    def _save_theme_pref(self):
        try:
            data = {}
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data["theme"] = self.theme_name
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _resolve_font(self):
        try:
            import tkinter.font as tkfont
            families = set(tkfont.families())
            for fam in (FONT_PRIMARY, FONT_FALLBACK, "Helvetica"):
                if fam in families:
                    return fam
        except Exception:
            pass
        return "TkDefaultFont"

    def _style_ttk(self, C):
        f = self.ui_font
        s = self.style
        for kind in ("primary", "secondary", "danger"):
            base, hover, fg = self._btn_colors(kind)
            name = f"{kind.title()}.TButton"
            s.configure(name, font=(f, 10), padding=(8, 2), width=0,
                        background=base, foreground=fg, borderwidth=0, relief="flat",
                        bordercolor=base, lightcolor=base, darkcolor=base, focusthickness=1,
                        focuscolor=C["ACCENT"])
            s.map(name, background=[("disabled", C["DISABLED_BG"]), ("pressed", hover), ("active", hover)],
                  foreground=[("disabled", C["DISABLED_FG"])])
        s.configure("Modern.TCheckbutton", background=C["CARD"], foreground=C["TEXT"], font=(f, 10))
        s.map("Modern.TCheckbutton", background=[("active", C["CARD"])],
              foreground=[("disabled", C["DISABLED_FG"]), ("active", C["TEXT"])])
        s.configure("Modern.TCheckbutton", indicatorbackground=C["INPUT_BG"],
                    indicatorforeground=C["TEXT"], bordercolor=C["BORDER"])
        s.map("Modern.TCheckbutton", indicatorbackground=[("selected", C["ACCENT"])])

        s.configure("Modern.TEntry", fieldbackground=C["INPUT_BG"], foreground=C["TEXT"],
                    bordercolor=C["BORDER"], lightcolor=C["BORDER"], darkcolor=C["BORDER"],
                    insertcolor=C["TEXT"], background=C["CARD"], padding=(6, 2))
        s.map("Modern.TEntry",
              bordercolor=[("focus", C["ACCENT"])],
              lightcolor=[("focus", C["ACCENT"])],
              darkcolor=[("focus", C["ACCENT"])])

        s.configure("Modern.TCombobox", fieldbackground=C["INPUT_BG"], background=C["CARD_ALT"],
                    foreground=C["TEXT"], arrowcolor=C["TEXT"], bordercolor=C["BORDER"], lightcolor=C["BORDER"], darkcolor=C["BORDER"], padding=(6, 2))
        s.map("Modern.TCombobox", fieldbackground=[("readonly", C["INPUT_BG"])],
              foreground=[("disabled", C["DISABLED_FG"]), ("readonly", C["TEXT"])],
              selectbackground=[("readonly", C["INPUT_BG"])],
              selectforeground=[("readonly", C["TEXT"])])
        self.option_add("*TCombobox*Listbox.background", C["CARD"])
        self.option_add("*TCombobox*Listbox.foreground", C["TEXT"])
        self.option_add("*TCombobox*Listbox.selectBackground", C["ACCENT"])
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        self.option_add("*TCombobox*Listbox.font", (f, 10))

        s.configure("Modern.Horizontal.TProgressbar", troughcolor=C["INPUT_BG"],
                    background=C["ACCENT"], bordercolor=C["INPUT_BG"],
                    lightcolor=C["ACCENT"], darkcolor=C["ACCENT"], thickness=10)

        s.configure("Modern.Treeview", background=C["CARD"], fieldbackground=C["CARD"],
                    foreground=C["TEXT"], bordercolor=C["BORDER"], rowheight=24, font=(f, 9))
        s.configure("Modern.Treeview.Heading", background=C["CARD_ALT"], foreground=C["TEXT"],
                    font=(f, 9, "bold"), relief="flat")
        s.map("Modern.Treeview", background=[("selected", C["ACCENT"])],
              foreground=[("selected", "#ffffff")])

        s.configure("Modern.Vertical.TScrollbar", background=C["CARD_ALT"],
                    troughcolor=C["BG"], bordercolor=C["BG"], arrowcolor=C["TEXT"])

    # ------------------------------------------------------------------
    # Widget factories
    # ------------------------------------------------------------------
    def _make_button(self, parent, text, command, kind="primary", width=None):
        btn = ttk.Button(parent, text=text, command=command,
                         style=f"{self.theme_name}.{kind.title()}.TButton", cursor="hand2")
        if width:
            btn.config(width=width)
        btn._kind = kind
        btn._disabled = False
        self._track(btn, lambda w, C: self._recolor_button(w))
        return btn

    def _btn_colors(self, kind):
        C = self.C
        if kind == "primary":
            return (C["ACCENT"], C["ACCENT_HOVER"], "#ffffff")
        if kind == "danger":
            return (C["DANGER"], C["DANGER_HOVER"], "#ffffff")
        return (C["SECONDARY_BG"], C["SECONDARY_HOVER"], C["SECONDARY_FG"])

    def _recolor_button(self, btn):
        base_style = f"{self.theme_name}.{btn._kind.title()}.TButton"
        surface = "Outer" if btn.master.cget("bg") == self.C["BG"] else "Card"
        name = f"{self.theme_name}.{surface}.{btn._kind.title()}.TButton"
        self.style.layout(name, self.style.layout(base_style))
        surface_color = btn.master.cget("bg")
        self.style.configure(name, background=surface_color)
        # Transparent rounded corners must show the parent in every state.
        self.style.map(name, background=[(state, surface_color) for state in
                                        ("disabled", "pressed", "active", "focus")])
        btn.configure(style=name)

    def _set_button_state(self, btn, state):
        btn._disabled = (state == "disabled")
        btn.config(state="disabled" if btn._disabled else "normal",
                   cursor="arrow" if btn._disabled else "hand2")
        self._recolor_button(btn)

    def _make_card(self, parent, title, step=None):
        wrapper = tk.Frame(parent)
        wrapper.pack(fill=tk.X, pady=(0, 14))
        self._track(wrapper, lambda w, C: w.config(bg=C["BG"]))

        card = tk.Frame(wrapper, highlightthickness=1, bd=0)
        card.pack(fill=tk.X)
        self._track(card, lambda w, C: w.config(bg=C["CARD"], highlightbackground=C["BORDER"]))

        header = tk.Frame(card)
        header.pack(fill=tk.X, padx=16, pady=(12, 0))
        self._track(header, lambda w, C: w.config(bg=C["CARD"]))

        if step is not None:
            badge = tk.Label(header, text=str(step), font=(self.ui_font, 9, "bold"), width=3)
            badge.pack(side=tk.LEFT, padx=(0, 10), ipady=2)
            self._track(badge, lambda w, C: w.config(bg=C["ACCENT"], fg="#ffffff"))

        title_lbl = tk.Label(header, text=title, font=(self.ui_font, 11, "bold"))
        title_lbl.pack(side=tk.LEFT)
        self._track(title_lbl, lambda w, C: w.config(bg=C["CARD"], fg=C["TEXT"]))

        inner = tk.Frame(card)
        inner.pack(fill=tk.X, padx=16, pady=12)
        self._track(inner, lambda w, C: w.config(bg=C["CARD"]))
        return inner

    def _label(self, parent, text, muted=False):
        lbl = tk.Label(parent, text=text, font=(self.ui_font, 10))
        if muted:
            self._track(lbl, lambda w, C: w.config(bg=C["CARD"], fg=C["TEXT_MUTED"]))
        else:
            self._track(lbl, lambda w, C: w.config(bg=C["CARD"], fg=C["TEXT"]))
        return lbl

    # ------------------------------------------------------------------
    # UI sections
    # ------------------------------------------------------------------
    def _build_header(self, parent):
        header = tk.Frame(parent)
        header.pack(fill=tk.X, padx=18, pady=(16, 6))
        self._track(header, lambda w, C: w.config(bg=C["BG"]))

        top = tk.Frame(header)
        top.pack(fill=tk.X)
        self._track(top, lambda w, C: w.config(bg=C["BG"]))

        titles = tk.Frame(top)
        titles.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._track(titles, lambda w, C: w.config(bg=C["BG"]))

        t1 = tk.Label(titles, text="Git Archive Generator", font=(self.ui_font, 18, "bold"), anchor=tk.W)
        t1.pack(anchor=tk.W)
        self._track(t1, lambda w, C: w.config(bg=C["BG"], fg=C["TEXT"]))

        t2 = tk.Label(titles, text="Archive repository files by date, SHA range, or single commit",
                      font=(self.ui_font, 10), anchor=tk.W)
        t2.pack(anchor=tk.W, pady=(2, 0))
        self._track(t2, lambda w, C: w.config(bg=C["BG"], fg=C["TEXT_MUTED"]))

        self.theme_button = self._make_button(top, self._theme_button_label(),
                                              self.toggle_theme, kind="secondary")
        self.theme_button.pack(side=tk.RIGHT, anchor=tk.N)

        sep = tk.Frame(header, height=1)
        sep.pack(fill=tk.X, pady=(12, 0))
        self._track(sep, lambda w, C: w.config(bg=C["BORDER"]))

    def _build_paths_card(self, parent):
        inner = self._make_card(parent, "Select Paths", step=1)
        inner.columnconfigure(1, weight=1)
        source = tk.Frame(inner)
        source.grid(row=0, column=0, columnspan=5, sticky=tk.EW, pady=(10, 0))
        self._track(source, lambda w, C: w.config(bg=C["CARD"]))
        self._label(source, "Source").pack(side=tk.LEFT, padx=(0, 10))
        selector = ttk.Combobox(source, textvariable=self.source_mode,
                                values=("Local folder", "HTTPS URL"), state="readonly", width=13,
                                style=f"{self.theme_name}.Modern.TCombobox")
        selector.pack(side=tk.LEFT)
        selector.bind("<<ComboboxSelected>>", self.change_source)
        self.remote_panel = tk.Frame(inner)
        self._track(self.remote_panel, lambda w, C: w.config(bg=C["CARD"]))
        self.remote_panel.columnconfigure(1, weight=1)
        self._label(self.remote_panel, "HTTPS clone URL").grid(row=0, column=0, padx=(0, 10))
        ttk.Entry(self.remote_panel, textvariable=self.remote_url,
                  style=f"{self.theme_name}.Modern.TEntry").grid(row=0, column=1, sticky=tk.EW, pady=4)
        self.remote_connect_button = self._make_button(self.remote_panel, "Connect / Update", self.connect_remote,
                                                      kind="secondary")
        self.remote_connect_button.grid(row=0, column=2, padx=(8, 0))
        self._label(self.remote_panel, "Private repo: PAT or Web login. Token is used for this connection only.",
                    muted=True).grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(4, 0))

        self.local_panel = tk.Frame(inner)
        self.local_panel.grid(row=1, column=0, columnspan=5, sticky=tk.EW, pady=(8, 0))
        self.local_panel.columnconfigure(1, weight=1)
        self._track(self.local_panel, lambda w, C: w.config(bg=C["CARD"]))
        self._label(self.local_panel, "Local Git folder").grid(row=0, column=0, sticky=tk.W, pady=6, padx=(0, 12))
        self.repo_combo = ttk.Combobox(self.local_panel, textvariable=self.repo_path,
                                       style=f"{self.theme_name}.Modern.TCombobox")
        self.repo_combo.grid(row=0, column=1, sticky=tk.EW, pady=4)
        self.repo_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_repository())
        self._refresh_recent_repos()
        self._make_button(self.local_panel, "Browse", self.browse_repo, kind="secondary").grid(row=0, column=2, padx=(10, 0))
        self.git_pull_button = self._make_button(self.local_panel, "Git Pull", self.start_git_pull, kind="secondary")
        self.git_pull_button.grid(row=0, column=3, padx=(8, 0))
        self.fetch_button = self._make_button(self.local_panel, "Fetch", self.start_git_fetch, kind="secondary")
        self.fetch_button.grid(row=0, column=4, padx=(8, 0))

        # repo validation hint
        self.repo_hint = tk.Label(inner, text="", font=(self.ui_font, 8), anchor=tk.W)
        self.repo_hint.grid(row=2, column=1, sticky=tk.W, pady=(0, 2))
        self._track(self.repo_hint, lambda w, C: w.config(bg=C["CARD"]))

        self.repo_status = tk.Label(inner, text="Repository status will appear here", font=(self.ui_font, 8),
                                    anchor=tk.W, justify=tk.LEFT, wraplength=520)
        self.repo_status.grid(row=3, column=1, columnspan=4, sticky=tk.EW, pady=(0, 5))
        self._track(self.repo_status, lambda w, C: w.config(bg=C["CARD"], fg=C["TEXT_MUTED"]))

        self._label(inner, "Output File").grid(row=4, column=0, sticky=tk.W, pady=6, padx=(0, 12))
        ttk.Entry(inner, textvariable=self.output_path, style=f"{self.theme_name}.Modern.TEntry").grid(row=4, column=1, sticky=tk.EW, pady=4)
        self._make_button(inner, "Save As", self.browse_output, kind="secondary").grid(row=4, column=2, padx=(10, 0))

        self._label(inner, "Archive Format").grid(row=5, column=0, sticky=tk.W, pady=6, padx=(0, 12))
        fmt_row = tk.Frame(inner)
        fmt_row.grid(row=5, column=1, columnspan=4, sticky=tk.EW)

        self._label(inner, "Exclude").grid(row=6, column=0, sticky=tk.W, pady=6, padx=(0, 12))
        ttk.Entry(inner, textvariable=self.exclude_patterns, style=f"{self.theme_name}.Modern.TEntry").grid(row=6, column=1, columnspan=3, sticky=tk.EW, pady=4)
        self._track(fmt_row, lambda w, C: w.config(bg=C["CARD"]))
        fmt_row.columnconfigure(0, weight=1)
        fmt_row.columnconfigure(2, weight=1)
        format_combo = ttk.Combobox(fmt_row, textvariable=self.archive_format,
                                    values=["zip", "tar", "gztar"], width=8, state="readonly", style=f"{self.theme_name}.Modern.TCombobox")
        format_combo.grid(row=0, column=0, sticky=tk.EW, pady=4)
        format_combo.bind("<<ComboboxSelected>>", self.on_format_change)
        cl = self._label(fmt_row, "Changelog")
        cl.grid(row=0, column=1, padx=(12, 6))
        changelog_combo = ttk.Combobox(fmt_row, textvariable=self.changelog_format,
                                       values=["txt", "md"], state="readonly", width=6, style=f"{self.theme_name}.Modern.TCombobox")
        changelog_combo.grid(row=0, column=2, sticky=tk.EW, pady=4)

    def _build_mode_card(self, parent):
        inner = self._make_card(parent, "Select Mode", step=2)
        self._mode_buttons = {}
        modes = [("Date Range", "date"), ("SHA Range", "sha_range"),
                 ("Single Commit", "commit_sha"), ("Tag Range", "tag_range")]
        row = tk.Frame(inner)
        row.pack(fill=tk.X)
        self._track(row, lambda w, C: w.config(bg=C["CARD"]))
        for index, (label, value) in enumerate(modes):
            b = self._make_button(row, label, lambda v=value: self._select_mode(v),
                                  kind="secondary")
            row.columnconfigure(index, weight=1, uniform="modes")
            b.grid(row=0, column=index, sticky=tk.EW, padx=(0, 8 if index < 3 else 0))
            self._mode_buttons[value] = b

    def _select_mode(self, value):
        self.mode.set(value)
        self._refresh_mode_buttons()
        self.on_mode_change()
        self._validate_inputs()

    def _refresh_mode_buttons(self):
        if not hasattr(self, "_mode_buttons"):
            return
        C = self.C
        current = self.mode.get()
        for value, btn in self._mode_buttons.items():
            if not btn.winfo_exists():
                continue
            btn.configure(style=f"{self.theme_name}.Primary.TButton" if value == current else f"{self.theme_name}.Secondary.TButton")
            btn.state(["pressed"] if value == current else ["!pressed"])

    def _build_params_card(self, parent):
        self.params_inner = self._make_card(parent, "Parameters", step=3)

        # Date mode
        self.date_frame = tk.Frame(self.params_inner)
        self._track(self.date_frame, lambda w, C: w.config(bg=C["CARD"]))
        self.date_frame.columnconfigure(1, weight=1)
        self._label(self.date_frame, "Start Date (YYYY-MM-DD)").grid(row=0, column=0, sticky=tk.W, pady=6, padx=(0, 12))
        self.start_date_entry = ttk.Entry(self.date_frame, textvariable=self.start_date, style=f"{self.theme_name}.Modern.TEntry")
        self.start_date_entry.grid(row=0, column=1, sticky=tk.EW, pady=4)
        self._make_button(self.date_frame, "Calendar", lambda: self.open_date_picker(self.start_date),
                          kind="secondary").grid(row=0, column=2, padx=(8, 0))
        self._label(self.date_frame, "End Date (YYYY-MM-DD)").grid(row=1, column=0, sticky=tk.W, pady=6, padx=(0, 12))
        self.end_date_entry = ttk.Entry(self.date_frame, textvariable=self.end_date, style=f"{self.theme_name}.Modern.TEntry")
        self.end_date_entry.grid(row=1, column=1, sticky=tk.EW, pady=4)
        self._make_button(self.date_frame, "Calendar", lambda: self.open_date_picker(self.end_date),
                          kind="secondary").grid(row=1, column=2, padx=(8, 0))
        self.date_hint = tk.Label(self.date_frame, text="", font=(self.ui_font, 8), anchor=tk.W)
        self.date_hint.grid(row=2, column=1, sticky=tk.W)
        self._track(self.date_hint, lambda w, C: w.config(bg=C["CARD"]))
        self._label(self.date_frame, "Branch").grid(row=3, column=0, sticky=tk.W, pady=6, padx=(0, 12))
        self.branch_entry = ttk.Combobox(self.date_frame, textvariable=self.branch, style=f"{self.theme_name}.Modern.TCombobox")
        self.branch_entry.grid(row=3, column=1, sticky=tk.EW, pady=4)
        self._label(self.date_frame, "Author (optional)").grid(row=4, column=0, sticky=tk.W, pady=6, padx=(0, 12))
        self.author_entry = ttk.Entry(self.date_frame, textvariable=self.author, style=f"{self.theme_name}.Modern.TEntry")
        self.author_entry.grid(row=4, column=1, sticky=tk.EW, pady=4)
        preset_row = tk.Frame(self.date_frame)
        preset_row.grid(row=5, column=1, columnspan=2, sticky=tk.W, pady=(5, 0))
        self._track(preset_row, lambda w, C: w.config(bg=C["CARD"]))
        for label, days in (("Today", 0), ("Last 7 Days", 6), ("This Month", -1)):
            self._make_button(preset_row, label, lambda d=days: self.set_date_preset(d),
                              kind="secondary").pack(side=tk.LEFT, padx=(0, 6))

        # SHA range mode
        self.sha_range_frame = tk.Frame(self.params_inner)
        self._track(self.sha_range_frame, lambda w, C: w.config(bg=C["CARD"]))
        self.sha_range_frame.columnconfigure(1, weight=1)
        self._label(self.sha_range_frame, "Start SHA").grid(row=0, column=0, sticky=tk.W, pady=6, padx=(0, 12))
        self.start_sha_entry = ttk.Entry(self.sha_range_frame, textvariable=self.start_sha, style=f"{self.theme_name}.Modern.TEntry")
        self.start_sha_entry.grid(row=0, column=1, sticky=tk.EW, pady=4)
        self._make_button(self.sha_range_frame, "Pick…", lambda: self.open_commit_picker(self.start_sha),
                          kind="secondary").grid(row=0, column=2, padx=(8, 0))
        self._label(self.sha_range_frame, "End SHA (included)").grid(row=1, column=0, sticky=tk.W, pady=6, padx=(0, 12))
        self.end_sha_entry = ttk.Entry(self.sha_range_frame, textvariable=self.end_sha, style=f"{self.theme_name}.Modern.TEntry")
        self.end_sha_entry.grid(row=1, column=1, sticky=tk.EW, pady=4)
        self._make_button(self.sha_range_frame, "Pick…", lambda: self.open_commit_picker(self.end_sha),
                          kind="secondary").grid(row=1, column=2, padx=(8, 0))

        for row, variable in enumerate((self.start_sha, self.end_sha)):
            self._make_button(self.sha_range_frame, "Copy SHA", lambda v=variable: self.copy_sha(v.get()),
                              kind="secondary").grid(row=row, column=3, padx=(8, 0))
        ttk.Checkbutton(self.sha_range_frame, text="Exclude start commit (C → F includes D, E, F)",
                        variable=self.exclude_start, style="Modern.TCheckbutton",
                        command=lambda: setattr(self, "selected_files", None)).grid(
                            row=2, column=1, columnspan=3, sticky=tk.W, pady=(10, 0))

        # Single commit mode
        self.commit_sha_frame = tk.Frame(self.params_inner)
        self._track(self.commit_sha_frame, lambda w, C: w.config(bg=C["CARD"]))
        self.commit_sha_frame.columnconfigure(1, weight=1)
        self._label(self.commit_sha_frame, "Commit SHA").grid(row=0, column=0, sticky=tk.W, pady=6, padx=(0, 12))
        self.commit_sha_entry = ttk.Entry(self.commit_sha_frame, textvariable=self.commit_sha, style=f"{self.theme_name}.Modern.TEntry")
        self.commit_sha_entry.grid(row=0, column=1, sticky=tk.EW, pady=4)
        self._make_button(self.commit_sha_frame, "Pick…", lambda: self.open_commit_picker(self.commit_sha),
                          kind="secondary").grid(row=0, column=2, padx=(8, 0))

        self.tag_range_frame = tk.Frame(self.params_inner)
        self._track(self.tag_range_frame, lambda w, C: w.config(bg=C["CARD"]))
        self.tag_range_frame.columnconfigure(1, weight=1)
        self._label(self.tag_range_frame, "Start Tag").grid(row=0, column=0, sticky=tk.W, pady=6, padx=(0, 12))
        self.start_tag_combo = ttk.Combobox(self.tag_range_frame, textvariable=self.start_tag,
                                            state="readonly", style=f"{self.theme_name}.Modern.TCombobox")
        self.start_tag_combo.grid(row=0, column=1, sticky=tk.EW, pady=4)
        self._label(self.tag_range_frame, "End Tag").grid(row=1, column=0, sticky=tk.W, pady=6, padx=(0, 12))
        self.end_tag_combo = ttk.Combobox(self.tag_range_frame, textvariable=self.end_tag,
                                          state="readonly", style=f"{self.theme_name}.Modern.TCombobox")
        self.end_tag_combo.grid(row=1, column=1, sticky=tk.EW, pady=4)

    def _build_progress(self, parent):
        wrapper = tk.Frame(parent)
        wrapper.pack(fill=tk.X, pady=(0, 12))
        self._track(wrapper, lambda w, C: w.config(bg=C["BG"]))
        self.progress_var = tk.StringVar(value="Ready")
        self.progress_label = tk.Label(wrapper, textvariable=self.progress_var, font=(self.ui_font, 9))
        self.progress_label.pack(anchor=tk.W, pady=(0, 6))
        self._track(self.progress_label, lambda w, C: w.config(bg=C["BG"], fg=C["TEXT_MUTED"]))
        self.progress_bar = ttk.Progressbar(wrapper, mode='determinate', maximum=100,
                                            style="Modern.Horizontal.TProgressbar")
        self.progress_bar.pack(fill=tk.X)

    def _build_actions(self, parent):
        wrapper = tk.Frame(parent)
        wrapper.pack(fill=tk.X, pady=(0, 12))
        self._track(wrapper, lambda w, C: w.config(bg=C["BG"]))
        self.preview_button = self._make_button(wrapper, "Preview Files", self.preview_files, kind="secondary")
        self.preview_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.run_button = self._make_button(wrapper, "Create Archive", self.start_archive_process, kind="primary")
        self.run_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.cancel_button = self._make_button(wrapper, "Cancel", self.cancel_archive_process, kind="danger")
        self.cancel_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        self._set_button_state(self.cancel_button, "disabled")

    def _build_log(self, parent):
        inner = self._make_card(parent, "Logs")
        self.log_area = scrolledtext.ScrolledText(inner, height=5, state='disabled', wrap=tk.WORD,
                                                  relief="flat", bd=0, highlightthickness=0,
                                                  font=(MONO_FONT, 9))
        self.log_area.pack(fill=tk.BOTH, expand=True)
        self._track(self.log_area, lambda w, C: w.config(bg=C["INPUT_BG"], fg=C["TEXT"], insertbackground=C["TEXT"]))

    def _build_footer(self, parent):
        footer = tk.Frame(parent)
        footer.pack(fill=tk.X, side=tk.BOTTOM, padx=18, pady=(0, 14))
        self._track(footer, lambda w, C: w.config(bg=C["BG"]))
        sep = tk.Frame(footer, height=1)
        sep.pack(fill=tk.X, pady=(0, 10))
        self._track(sep, lambda w, C: w.config(bg=C["BORDER"]))
        content = tk.Frame(footer)
        content.pack(fill=tk.X)
        self._track(content, lambda w, C: w.config(bg=C["BG"]))
        self._make_button(content, "History", self.show_history, kind="secondary").pack(side=tk.LEFT)
        credit = tk.Label(content, text="Developed by ekosiswoyo", font=(self.ui_font, 9))
        credit.pack(side=tk.RIGHT)
        self._track(credit, lambda w, C: w.config(bg=C["BG"], fg=C["TEXT_MUTED"]))

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _is_git_repo(self, path):
        return is_git_repository(path)

    def _valid_date(self, text):
        if not text:
            return None  # empty = neutral
        try:
            datetime.strptime(text, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def _validate_inputs(self):
        C = self.C
        # Repo hint
        path = self.repo_path.get().strip()
        if not path:
            self.repo_hint.config(text="", fg=C["TEXT_MUTED"])
        elif self._is_git_repo(path):
            self.repo_hint.config(text="✓ Valid git repository", fg=C["OK"])
        else:
            self.repo_hint.config(text="✗ Not a git repository (no .git folder found)", fg=C["DANGER"])

        # Date hints (only relevant in date mode)
        if hasattr(self, "date_hint"):
            sd, ed = self.start_date.get().strip(), self.end_date.get().strip()
            msgs, color = [], C["OK"]
            sd_ok, ed_ok = self._valid_date(sd), self._valid_date(ed)
            if sd_ok is False or ed_ok is False:
                msgs.append("Date format must be YYYY-MM-DD")
                color = C["DANGER"]
            elif sd_ok and ed_ok and sd > ed:
                msgs.append("Start date is after end date")
                color = C["WARN"]
            self.date_hint.config(text=("⚠ " + "; ".join(msgs)) if msgs else "", fg=color)

    # ------------------------------------------------------------------
    # Recent repos
    # ------------------------------------------------------------------
    def _refresh_recent_repos(self):
        seen, recents = set(), []
        for entry in self.history_manager.get_history():
            if entry.get("parameters", {}).get("remote_url"):
                continue
            rp = entry.get("repo_path", "")
            if rp and rp not in seen and os.path.isdir(rp):
                seen.add(rp)
                recents.append(rp)
        self.repo_combo['values'] = recents

    # ------------------------------------------------------------------
    def center_window(self):
        self.update_idletasks()
        width, height = 700, 880
        try:
            actual_width = self.winfo_width()
            actual_height = self.winfo_height()
            if actual_width > 100 and actual_height > 100:
                width, height = actual_width, actual_height
        except Exception:
            pass
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        width = min(width, screen_width - 80)
        height = min(height, screen_height - 100)
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2 - 40
        if y < 0:
            y = 10
        self.geometry(f"{width}x{height}+{x}+{y}")

    def invalidate_remote(self):
        if hasattr(self, 'remote_connected_url') and self.source_mode.get() == 'HTTPS URL':
            self.remote_connected_url = ''
            self.repo_path.set('')
            self.selected_files = None

    def change_source(self, event=None):
        self.selected_files = None
        self.repo_path.set('')
        self.remote_connected_url = ''
        self.repo_status.config(text='Connect an HTTPS repository' if self.source_mode.get() == 'HTTPS URL' else 'Select a local Git folder')
        if self.source_mode.get() == 'HTTPS URL':
            self.local_panel.grid_remove()
            self.remote_panel.grid(row=1, column=0, columnspan=5, sticky=tk.EW, pady=(8, 0))
        else:
            self.remote_panel.grid_remove()
            self.local_panel.grid()

    def connect_remote(self):
        if self.remote_busy:
            return
        try:
            url = normalize_url(self.remote_url.get())
        except ValueError as exc:
            messagebox.showerror('Repository URL', str(exc))
            return
        win = tk.Toplevel(self)
        win.title('Connect to HTTPS repository')
        win.configure(bg=self.C['CARD'])
        win.transient(self)
        win.grab_set()
        method = tk.StringVar(value='Personal access token')
        username = tk.StringVar()
        token = tk.StringVar()
        self._label(win, 'Authentication').pack(anchor=tk.W, padx=16, pady=(16, 4))
        ttk.Combobox(win, textvariable=method, state='readonly', width=30,
                     values=('Personal access token', 'Web login (Git Credential Manager)', 'Existing credentials / Public'),
                     style=f'{self.theme_name}.Modern.TCombobox').pack(fill=tk.X, padx=16)
        token_fields = tk.Frame(win, bg=self.C['CARD'])
        self._label(token_fields, 'Username').pack(anchor=tk.W, pady=(10, 4))
        ttk.Entry(token_fields, textvariable=username, style=f'{self.theme_name}.Modern.TEntry').pack(fill=tk.X)
        self._label(token_fields, 'Personal access token (not your password)').pack(anchor=tk.W, pady=(10, 4))
        ttk.Entry(token_fields, textvariable=token, show='•', style=f'{self.theme_name}.Modern.TEntry').pack(fill=tk.X)
        hint = self._label(win, '', muted=True)
        hint.configure(wraplength=480, justify=tk.LEFT, anchor=tk.W)
        hint.pack(fill=tk.X, padx=16, pady=12)
        def update_authentication(*args):
            if method.get() == 'Personal access token':
                token_fields.pack(fill=tk.X, padx=16, before=hint)
                hint.configure(text='Enter your username and token. With 2FA, use a token instead of your account password.\nGitHub: Contents read. GitLab: read_repository.')
                help_button.configure(text='Token help')
                help_button.pack(padx=16, pady=(0, 12), before=actions)
            else:
                token_fields.pack_forget()
                token.set('')
                if method.get() == 'Existing credentials / Public':
                    hint.configure(text='No fields to fill in. Click Connect to use credentials already stored in Git or access a public repository.')
                    help_button.pack_forget()
                else:
                    hint.configure(text='No username or token needed here. Click Connect to start web login through Git Credential Manager. Company servers may require OAuth setup.')
                    help_button.configure(text='Web login help')
                    help_button.pack(padx=16, pady=(0, 12), before=actions)
            win.update_idletasks()
            win.geometry('')
        def submit():
            auth = {'Personal access token': 'token', 'Web login (Git Credential Manager)': 'browser',
                    'Existing credentials / Public': 'auto'}[method.get()]
            user, secret = (username.get(), token.get()) if auth == 'token' else ('', '')
            if auth == 'token' and (not user.strip() or not secret.strip()):
                messagebox.showwarning('Authentication', 'Enter a username and personal access token.', parent=win)
                return
            token.set('')
            self.remote_url.set(url)
            win.destroy()
            self.remote_busy = True
            self._set_button_state(self.remote_connect_button, 'disabled')
            self.repo_path.set('')
            self.remote_connected_url = ''
            self.repo_status.config(text='Connecting / downloading Git history…')
            def load():
                try:
                    path = prepare_repository(url, auth, user, secret)
                    self.ui_queue.put(lambda: self.finish_remote(url, path, None))
                except Exception as exc:
                    error = str(exc)
                    self.ui_queue.put(lambda: self.finish_remote(url, None, error))
            threading.Thread(target=load, daemon=True).start()
        help_button = self._make_button(win, 'Token help', lambda: webbrowser.open(
            'https://github.com/git-ecosystem/git-credential-manager/blob/main/docs/README.md'), kind='secondary')
        actions = tk.Frame(win, bg=self.C['CARD'])
        actions.pack(fill=tk.X, padx=16, pady=(0, 16))
        self._make_button(actions, 'Connect', submit).pack(side=tk.RIGHT)
        self._make_button(actions, 'Cancel', win.destroy, kind='secondary').pack(side=tk.LEFT)
        method.trace_add('write', update_authentication)
        update_authentication()

    def finish_remote(self, url, path, error):
        self.remote_busy = False
        self._set_button_state(self.remote_connect_button, 'normal')
        if error:
            self.repo_status.config(text='Connection failed')
            messagebox.showerror('HTTPS repository', error)
            return
        if self.source_mode.get() != 'HTTPS URL' or self.remote_url.get().strip().rstrip('/') != url:
            return
        self.remote_connected_url = url
        self.repo_path.set(path)
        self.refresh_repository()
        self.log('Remote repository ready. Branches, dates, SHA and tags can now be selected.')

    def browse_repo(self):
        if self.source_mode.get() == 'HTTPS URL':
            self.connect_remote()
            return
        path = filedialog.askdirectory(title="Select Git Repository Folder")
        if path:
            self.repo_path.set(path)
            self.refresh_repository()

    def refresh_repository(self):
        self._validate_inputs()
        repo = self.repo_path.get().strip()
        self.selected_files = None
        if not self._is_git_repo(repo):
            return
        self.repo_status.config(text="Reading repository status...")
        def load():
            info = get_repository_info(repo)
            self.ui_queue.put(lambda: self._show_repository_info(info) if self.repo_path.get().strip() == repo else None)
        threading.Thread(target=load, daemon=True).start()

    def _show_repository_info(self, info):
        if info.get('error'):
            self.repo_status.config(text=info['error'], fg=self.C["DANGER"])
            return
        clean = "clean" if not info['dirty'] else f"{info['changes']} local change(s)"
        sync = f"↑{info['ahead']} ↓{info['behind']}" if info['upstream'] else "no upstream"
        self.repo_status.config(
            text=f"{info['branch']}  ·  {sync}  ·  {clean}\n{info['last_commit']}  ·  {info['remote']}",
            fg=self.C["OK"] if not info['dirty'] else self.C["WARN"]
        )
        self.branch_entry['values'] = info['branches']
        if info['branch'] != '(detached HEAD)': self.branch.set(info['branch'])
        self.start_tag_combo['values'] = info['tags']
        self.end_tag_combo['values'] = info['tags']
        if info['tags']:
            if not self.end_tag.get(): self.end_tag.set(info['tags'][0])
            if not self.start_tag.get() and len(info['tags']) > 1: self.start_tag.set(info['tags'][1])

    def start_git_fetch(self):
        if self.source_mode.get() == 'HTTPS URL':
            self.connect_remote()
            return
        repo = self.repo_path.get().strip()
        if not self._is_git_repo(repo):
            messagebox.showerror("Invalid repository", "Please select a valid Git repository first.")
            return
        self._set_button_state(self.fetch_button, "disabled")
        self.progress_var.set("Fetching remote updates...")
        def fetch():
            try:
                result = subprocess.run(['git', 'fetch', '--prune'], cwd=repo, capture_output=True,
                                        text=True, encoding='utf-8', errors='replace')
                message = (result.stdout + result.stderr).strip() or "Fetch complete."
                self.ui_queue.put(lambda: self._finish_git_fetch(result.returncode == 0, message))
            except Exception as exc:
                message = str(exc)
                self.ui_queue.put(lambda: self._finish_git_fetch(False, message))
        threading.Thread(target=fetch, daemon=True).start()

    def _finish_git_fetch(self, success, message):
        self._set_button_state(self.fetch_button, "normal")
        self.progress_var.set("Fetch complete" if success else "Fetch failed")
        self.log(message)
        self.refresh_repository()
        if not success: messagebox.showerror("Git Fetch failed", message)

    def set_date_preset(self, days):
        today = date.today()
        start = today.replace(day=1) if days == -1 else today - timedelta(days=days)
        self.start_date.set(start.isoformat())
        self.end_date.set(today.isoformat())

    def open_date_picker(self, target_var):
        try:
            selected = datetime.strptime(target_var.get(), "%Y-%m-%d").date()
        except ValueError:
            selected = date.today()
        win = tk.Toplevel(self); win.title("Select Date"); win.resizable(False, False)
        state = [selected.year, selected.month]
        calendar_frame = tk.Frame(win); calendar_frame.pack(padx=8, pady=8)

        def choose(year, month, day):
            target_var.set(date(year, month, day).isoformat()); win.destroy()

        def move(delta):
            year, month = state
            month += delta
            if month == 0: year, month = year - 1, 12
            elif month == 13: year, month = year + 1, 1
            state[:] = [year, month]; draw()

        def draw():
            for widget in calendar_frame.winfo_children(): widget.destroy()
            year, month = state
            tk.Button(calendar_frame, text='‹', command=lambda: move(-1), width=3).grid(row=0, column=0)
            tk.Label(calendar_frame, text=f"{calendar.month_name[month]} {year}",
                     font=(self.ui_font, 11, 'bold')).grid(row=0, column=1, columnspan=5, pady=8)
            tk.Button(calendar_frame, text='›', command=lambda: move(1), width=3).grid(row=0, column=6)
            for col, name in enumerate(('Mo','Tu','We','Th','Fr','Sa','Su')):
                tk.Label(calendar_frame, text=name, width=4).grid(row=1, column=col)
            for row, week in enumerate(calendar.monthcalendar(year, month), 2):
                for col, day_number in enumerate(week):
                    if day_number:
                        tk.Button(calendar_frame, text=str(day_number), width=4,
                                  command=lambda d=day_number, y=year, m=month: choose(y, m, d)).grid(row=row, column=col)
        draw()

    def start_git_pull(self):
        """Safely update the selected repository without blocking the UI."""
        if self.source_mode.get() == 'HTTPS URL':
            self.connect_remote()
            return
        repo_path = self.repo_path.get().strip()
        if not self._is_git_repo(repo_path):
            messagebox.showerror(
                "Invalid repository",
                "Please select a valid Git repository before pulling."
            )
            return
        if self.git_pull_thread and self.git_pull_thread.is_alive():
            return

        try:
            status = subprocess.run(
                ["git", "status", "--porcelain"], cwd=repo_path,
                capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
        except FileNotFoundError:
            messagebox.showerror("Git Pull failed", "Git is not installed or is not available in PATH.")
            return
        if status.returncode != 0:
            detail = status.stderr.strip() or status.stdout.strip() or "Could not read repository status."
            messagebox.showerror("Git Pull failed", detail)
            return

        use_autostash = bool(status.stdout.strip())
        if use_autostash and not messagebox.askyesno(
                "Local changes detected",
                "This repository has local changes. Git will temporarily stash tracked changes, "
                "pull with fast-forward only, then restore those changes.\n\nContinue?"):
            return

        self._set_button_state(self.git_pull_button, "disabled")
        self.progress_var.set("Pulling latest changes...")
        self.log("--- GIT PULL ---")
        self.git_pull_thread = threading.Thread(
            target=self._run_git_pull,
            args=(repo_path, use_autostash),
            daemon=True
        )
        self.git_pull_thread.start()

    def _run_git_pull(self, repo_path, use_autostash=False):
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        def run_git(*args):
            return subprocess.run(
                ["git", *args], cwd=repo_path, capture_output=True, text=True,
                encoding="utf-8", errors="replace", startupinfo=startupinfo
            )

        try:
            pull_args = ["pull", "--ff-only"]
            if use_autostash:
                pull_args.append("--autostash")
            result = run_git(*pull_args)
            output = "\n".join(
                part.strip() for part in (result.stdout, result.stderr) if part.strip()
            )
            success = result.returncode == 0
            self.ui_queue.put(lambda: self._finish_git_pull(success, output or "Git Pull completed."))
        except FileNotFoundError:
            self.ui_queue.put(lambda: self._finish_git_pull(False, "Git is not installed or is not available in PATH."))
        except Exception as exc:
            message = str(exc)
            self.ui_queue.put(lambda: self._finish_git_pull(False, message))

    def _finish_git_pull(self, success, message):
        self._set_button_state(self.git_pull_button, "normal")
        self.progress_var.set("Git Pull complete" if success else "Git Pull failed")
        self.log(message)
        self.git_pull_thread = None
        self.refresh_repository()
        self.show_git_output("Git Pull" if success else "Git Pull failed", message)

    def show_git_output(self, title, message):
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=self.C["BG"])
        win.transient(self)
        width = min(720, self.winfo_screenwidth() - 80)
        height = min(480, self.winfo_screenheight() - 120)
        win.geometry(f"{width}x{height}")
        win.minsize(min(420, width), min(260, height))
        # Reserve footer space before packing the expanding log.
        footer = tk.Frame(win, bg=self.C["BG"])
        footer.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=12)
        ok = self._make_button(footer, "OK", win.destroy)
        ok.pack(side=tk.RIGHT)
        output = scrolledtext.ScrolledText(win, wrap=tk.WORD, font=(MONO_FONT, 10),
                                          bg=self.C["INPUT_BG"], fg=self.C["TEXT"],
                                          relief="flat", padx=12, pady=12)
        output.pack(fill=tk.BOTH, expand=True, padx=16, pady=(16, 0))
        output.insert("1.0", message)
        output.configure(state="disabled")
        win.bind("<Escape>", lambda e: win.destroy())
        win.bind("<Return>", lambda e: win.destroy())
        win.grab_set()
        ok.focus_set()

    def copy_sha(self, value):
        value = value.strip()
        if not value:
            self.log("Select or enter a SHA first.")
            return
        if len(value) < 8 or any(c not in "0123456789abcdefABCDEF" for c in value):
            try:
                result = subprocess.run(["git", "rev-parse", "--verify", f"{value}^{{commit}}"],
                                        cwd=self.repo_path.get(), capture_output=True, text=True)
                if result.returncode:
                    self.log("Could not resolve SHA to a commit.")
                    return
                value = result.stdout.strip()
            except OSError as exc:
                self.log(f"Could not copy SHA: {exc}")
                return
        self.clipboard_clear()
        self.clipboard_append(value[:8])
        self.log(f"Copied SHA: {value[:8]}")

    def on_format_change(self, event=None):
        current_path = self.output_path.get()
        if current_path:
            for ext in ['.zip', '.tar', '.tar.gz', '.gz']:
                if current_path.lower().endswith(ext):
                    current_path = current_path[:-len(ext)]
                    break
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
        self.date_frame.pack_forget()
        self.sha_range_frame.pack_forget()
        self.commit_sha_frame.pack_forget()
        self.tag_range_frame.pack_forget()
        if mode == 'date':
            self.date_frame.pack(fill=tk.X)
        elif mode == 'sha_range':
            self.sha_range_frame.pack(fill=tk.X)
        elif mode == 'commit_sha':
            self.commit_sha_frame.pack(fill=tk.X)
        elif mode == 'tag_range':
            self.tag_range_frame.pack(fill=tk.X)

    def log(self, message):
        self.log_queue.put(message)

    def process_log_queue(self):
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.log_area.config(state='normal')
                self.log_area.insert(tk.END, message + '\n')
                self.log_area.see(tk.END)
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

    def process_completion_queue(self):
        try:
            while True:
                self.ui_queue.get_nowait()()
        except queue.Empty:
            pass
        try:
            while True:
                self._handle_complete(self.completion_queue.get_nowait())
        except queue.Empty:
            pass
        self.after(100, self.process_completion_queue)

    def update_progress(self, value, message):
        self.progress_queue.put((value, message))

    def _exclude_list(self):
        return [item.strip() for item in self.exclude_patterns.get().replace('\n', ';').split(';') if item.strip()]

    # ------------------------------------------------------------------
    # Completion handling (messageboxes + open folder)
    # ------------------------------------------------------------------
    def _on_complete(self, result):
        # The UI queue avoids calling Tk from the archive worker.
        self.completion_queue.put(result)

    def _handle_complete(self, result):
        if result.get('success'):
            try:
                self.save_to_history(result.get('request'), result.get('archive_path'))
                self._refresh_recent_repos()
            except OSError as exc:
                self.log(f'History could not be saved: {exc}')
                messagebox.showwarning('History not saved', f'Archive created, but history could not be saved:\n{exc}')
            self._last_archive_path = result.get('archive_path', '')
            archive = result.get('archive_path', '')
            count = result.get('file_count', 0)
            deleted = result.get('deleted_count', 0)
            folder = os.path.dirname(os.path.abspath(archive)) if archive else ''
            msg = (f"Archive created successfully.\n\n"
                   f"Files archived: {count}\n"
                   f"Files to delete on deployment: {deleted}\n"
                   f"Output: {archive}\n\n"
                   f"Open the output folder now?")
            if messagebox.askyesno("Success", msg):
                self._open_folder(folder)
        else:
            messagebox.showerror("Error", f"Archive failed:\n\n{result.get('error', 'Unknown error')}")

    def _open_folder(self, folder):
        if not folder or not os.path.isdir(folder):
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # noqa
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            self.log(f"Could not open folder: {e}")

    def start_archive_process(self):
        # Pre-flight validation with messageboxes
        if not self.repo_path.get().strip() or not self.output_path.get().strip():
            messagebox.showwarning("Missing fields", "Repository path and Output file must be selected.")
            return
        if not self._is_git_repo(self.repo_path.get().strip()):
            messagebox.showerror("Invalid repository",
                                 "The selected folder is not a git repository (no .git folder found).")
            return
        mode = self.mode.get()
        if mode == 'date':
            if self._valid_date(self.start_date.get().strip()) is not True or \
               self._valid_date(self.end_date.get().strip()) is not True:
                messagebox.showerror("Invalid dates", "Start and End dates must be in YYYY-MM-DD format.")
                return
            if not self.branch.get().strip():
                messagebox.showwarning("Missing branch", "Please specify a branch for Date Range mode.")
                return
        elif mode == 'sha_range':
            if not self.start_sha.get().strip() or not self.end_sha.get().strip():
                messagebox.showwarning("Missing SHA", "Both Start SHA and End SHA are required.")
                return
        elif mode == 'commit_sha':
            if not self.commit_sha.get().strip():
                messagebox.showwarning("Missing SHA", "Commit SHA is required for Single Commit mode.")
                return
        elif mode == 'tag_range':
            if not self.start_tag.get() or not self.end_tag.get():
                messagebox.showwarning("Missing tags", "Start Tag and End Tag are required.")
                return
            if self.start_tag.get() == self.end_tag.get():
                messagebox.showwarning("Invalid tags", "Start Tag and End Tag must be different.")
                return

        self._set_button_state(self.run_button, "disabled")
        self._set_button_state(self.cancel_button, "normal")
        self.progress_bar['value'] = 0
        self.progress_var.set("Starting...")
        self.log_area.config(state='normal')
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state='disabled')
        self.log("--- STARTING PROCESS ---\n")

        self.cancel_event = threading.Event()

        params = {
            'log_callback': self.log,
            'progress_callback': self.update_progress,
            'complete_callback': self._on_complete,
            'cancel_event': self.cancel_event,
            'repo_path': self.repo_path.get(),
            'output_zip': self.output_path.get(),
            'mode': self.mode.get(),
            'archive_format': self.archive_format.get(),
            'changelog_format': self.changelog_format.get(),
            'start_date': self.start_date.get(),
            'end_date': self.end_date.get(),
            'branch': self.branch.get(),
            'author': self.author.get(),
            'start_sha': self.start_sha.get(),
            'exclude_start': self.exclude_start.get(),
            'end_sha': self.end_sha.get(),
            'commit_sha': self.commit_sha.get(),
            'start_tag': self.start_tag.get(),
            'end_tag': self.end_tag.get(),
            'exclude_patterns': self._exclude_list(),
            'selected_files': self.selected_files
        }

        request = {key: value for key, value in params.items()
                   if key not in ('log_callback', 'progress_callback', 'complete_callback', 'cancel_event')}
        request['exclude_patterns'] = self.exclude_patterns.get()
        request['remote_url'] = self.remote_connected_url if self.source_mode.get() == 'HTTPS URL' else ''
        def completed(result):
            self._on_complete(dict(result, request=request))
        params['complete_callback'] = completed
        self.archive_thread = threading.Thread(target=archive_git_history, args=(params,))
        self.archive_thread.daemon = True
        self.archive_thread.start()
        self.check_thread(self.archive_thread)

    def cancel_archive_process(self):
        if self.cancel_event:
            self.cancel_event.set()
            self.log("--- CANCELLING PROCESS ---")
            self._set_button_state(self.cancel_button, "disabled")
            self.after(500, self.reset_ui_after_cancel)

    def reset_ui_after_cancel(self):
        self._set_button_state(self.run_button, "normal")
        self._set_button_state(self.cancel_button, "disabled")
        self.progress_bar['value'] = 0
        self.progress_var.set("Ready")
        self.cancel_event = None
        self.archive_thread = None

    def check_thread(self, thread):
        if thread.is_alive():
            self.after(100, lambda: self.check_thread(thread))
        else:
            self._set_button_state(self.run_button, "normal")
            self._set_button_state(self.cancel_button, "disabled")
            if not self.cancel_event or not self.cancel_event.is_set():
                if self.progress_bar['value'] < 100:
                    self.progress_bar['value'] = 0
                    self.progress_var.set("Ready")
            self.cancel_event = None
            self.archive_thread = None

    def save_to_history(self, request, archive_path):
        if not request:
            raise OSError("Archive request is missing; history was not saved.")
        parameters = {key: request.get(key, '') for key in (
            'start_date', 'end_date', 'branch', 'author', 'start_sha', 'end_sha',
            'commit_sha', 'start_tag', 'end_tag', 'exclude_patterns', 'changelog_format')}
        parameters['exclude_start'] = request.get('exclude_start', False)
        parameters['remote_url'] = request.get('remote_url', '')
        self.history_manager.add_entry(
            repo_path=request['repo_path'], output_path=archive_path or request['output_zip'],
            mode=request['mode'], parameters=parameters,
            archive_format=request.get('archive_format', 'zip'))

    def preview_files(self):
        if not self.repo_path.get():
            messagebox.showwarning("Missing repository", "Please select a repository path first.")
            return

        params = {
            'repo_path': self.repo_path.get(),
            'mode': self.mode.get(),
            'start_date': self.start_date.get(),
            'end_date': self.end_date.get(),
            'branch': self.branch.get(),
            'author': self.author.get(),
            'start_sha': self.start_sha.get(),
            'exclude_start': self.exclude_start.get(),
            'end_sha': self.end_sha.get(),
            'commit_sha': self.commit_sha.get(),
            'start_tag': self.start_tag.get(),
            'end_tag': self.end_tag.get(),
            'exclude_patterns': self._exclude_list()
        }

        if params['mode'] == 'date' and (not params['start_date'] or not params['end_date'] or not params['branch']):
            messagebox.showwarning("Missing fields", "Please fill in all required parameters for Date Range mode.")
            return
        elif params['mode'] == 'sha_range' and (not params['start_sha'] or not params['end_sha']):
            messagebox.showwarning("Missing fields", "Please fill in both Start SHA and End SHA for SHA Range mode.")
            return
        elif params['mode'] == 'commit_sha' and not params['commit_sha']:
            messagebox.showwarning("Missing fields", "Please fill in Commit SHA for Single Commit mode.")
            return
        elif params['mode'] == 'tag_range' and (not params['start_tag'] or not params['end_tag']):
            messagebox.showwarning("Missing fields", "Please select both tags for Tag Range mode.")
            return

        def run_preview():
            result = get_file_list_preview(params)
            self.ui_queue.put(lambda: self.show_preview_window(result))

        thread = threading.Thread(target=run_preview)
        thread.daemon = True
        thread.start()
        self.log("Loading preview...")

    def show_preview_window(self, result):
        C = self.C
        win = tk.Toplevel(self)
        win.title("File Preview")
        win.geometry("620x520")
        win.configure(bg=C["BG"])

        if result.get('error'):
            tk.Label(win, text=f"Error: {result['error']}", bg=C["BG"], fg=C["DANGER"],
                     font=(self.ui_font, 10), wraplength=560, justify=tk.LEFT).pack(pady=16, padx=16)
            self._make_button(win, "Close", win.destroy, kind="secondary").pack(pady=10)
            return

        header = tk.Frame(win, bg=C["BG"])
        header.pack(fill=tk.X, padx=16, pady=(16, 8))
        size_text = f"{result.get('total_size', 0) / 1024:.1f} KB"
        tk.Label(header, text=f"Changes: {result['total_files']}  ·  Deleted: {len(result.get('deleted_files', []))}  ·  Size: {size_text}", bg=C["BG"], fg=C["TEXT"],
                 font=(self.ui_font, 12, "bold")).pack(anchor=tk.W)
        if result.get('commit_hash'):
            tk.Label(header, text=f"Commit: {result['commit_hash'][:10]}", bg=C["BG"],
                     fg=C["TEXT_MUTED"], font=(self.ui_font, 9)).pack(anchor=tk.W)

        search_var = tk.StringVar()
        search_row = tk.Frame(win, bg=C["BG"]); search_row.pack(fill=tk.X, padx=16)
        tk.Label(search_row, text="Filter:", bg=C["BG"], fg=C["TEXT_MUTED"]).pack(side=tk.LEFT)
        ttk.Entry(search_row, textvariable=search_var, style=f"{self.theme_name}.Modern.TEntry").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        list_frame = tk.Frame(win, bg=C["CARD"], highlightbackground=C["BORDER"], highlightthickness=1)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        scrollbar = ttk.Scrollbar(list_frame, style="Modern.Vertical.TScrollbar")
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree = ttk.Treeview(list_frame, columns=('pick', 'status', 'size', 'commit', 'path'), show='headings',
                            yscrollcommand=scrollbar.set, style='Modern.Treeview')
        tree.heading('pick', text='Include'); tree.column('pick', width=65, anchor=tk.CENTER)
        tree.heading('status', text='Status'); tree.column('status', width=85)
        tree.heading('size', text='Size'); tree.column('size', width=70, anchor=tk.E)
        tree.heading('commit', text='Commit'); tree.column('commit', width=75)
        tree.heading('path', text='File'); tree.column('path', width=330)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=tree.yview)
        labels = {'A':'Added', 'M':'Modified', 'D':'Deleted', 'R':'Renamed', 'C':'Copied'}
        included = set(result['files'])
        def populate(*args):
            tree.delete(*tree.get_children())
            term = search_var.get().lower()
            for index, change in enumerate(result['changes']):
                if term and term not in (change['path'] + ' ' + labels.get(change['status'], '')).lower(): continue
                size = '—' if change['status'] == 'D' else f"{change.get('size', 0) / 1024:.1f} KB"
                tree.insert('', tk.END, iid=str(index), values=(
                    '☑' if change['path'] in included else '☐', labels.get(change['status'], change['status']),
                    size, change.get('commit', ''), change['path']))
        populate()
        search_var.trace_add('write', populate)

        def toggle(event=None):
            for item in tree.selection():
                path = tree.set(item, 'path')
                if path in included: included.remove(path); tree.set(item, 'pick', '☐')
                else: included.add(path); tree.set(item, 'pick', '☑')
        tree.bind('<Double-1>', toggle)

        btn_row = tk.Frame(win, bg=C["BG"])
        btn_row.pack(fill=tk.X, padx=16, pady=12)

        def copy_list():
            self.clipboard_clear()
            self.clipboard_append("\n".join(sorted(included)))
            self.log(f"Copied {len(included)} file paths to clipboard.")

        def apply_selection():
            self.selected_files = sorted(included)
            self.log(f"Applied preview selection: {len(included)} change(s).")
            win.destroy()

        self._make_button(btn_row, "Copy List", copy_list, kind="secondary").pack(side=tk.LEFT)
        self._make_button(btn_row, "Toggle Selected", toggle, kind="secondary").pack(side=tk.LEFT, padx=6)
        self._make_button(btn_row, "Apply Selection", apply_selection, kind="primary").pack(side=tk.RIGHT)
        self._make_button(btn_row, "Close", win.destroy, kind="secondary").pack(side=tk.RIGHT, padx=6)

    # ------------------------------------------------------------------
    # Commit picker
    # ------------------------------------------------------------------
    def open_commit_picker(self, target_var):
        repo = self.repo_path.get().strip()
        if not self._is_git_repo(repo):
            messagebox.showerror("Invalid repository",
                                 "Select a valid git repository before picking a commit.")
            return

        C = self.C
        win = tk.Toplevel(self)
        win.title("Pick a Commit")
        win.geometry("760x520")
        win.configure(bg=C["BG"])

        header = tk.Frame(win, bg=C["BG"])
        header.pack(fill=tk.X, padx=16, pady=(16, 8))
        tk.Label(header, text="Recent Commits", bg=C["BG"], fg=C["TEXT"],
                 font=(self.ui_font, 13, "bold")).pack(side=tk.LEFT)

        search_var = tk.StringVar()
        search_entry = ttk.Entry(header, textvariable=search_var, style=f"{self.theme_name}.Modern.TEntry", width=28)
        search_entry.pack(side=tk.RIGHT)
        tk.Label(header, text="Filter:", bg=C["BG"], fg=C["TEXT_MUTED"],
                 font=(self.ui_font, 9)).pack(side=tk.RIGHT, padx=(0, 6))

        list_frame = tk.Frame(win, bg=C["BG"])
        list_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        scrollbar = ttk.Scrollbar(list_frame, style="Modern.Vertical.TScrollbar")
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        tree = ttk.Treeview(list_frame, columns=("hash", "date", "author", "message"),
                            show="headings", yscrollcommand=scrollbar.set, style="Modern.Treeview")
        for col, text, w in [("hash", "SHA", 90), ("date", "Date", 90),
                             ("author", "Author", 140), ("message", "Message", 380)]:
            tree.heading(col, text=text)
            tree.column(col, width=w)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=tree.yview)

        status = tk.Label(win, text="Loading commits…", bg=C["BG"], fg=C["TEXT_MUTED"],
                          font=(self.ui_font, 9))
        status.pack(anchor=tk.W, padx=16)

        all_commits = []

        def populate(commits):
            tree.delete(*tree.get_children())
            term = search_var.get().lower()
            shown = 0
            for c in commits:
                hay = f"{c['short_hash']} {c['author']} {c['message']}".lower()
                if term and term not in hay:
                    continue
                tree.insert("", tk.END, iid=c['hash'],
                            values=(c['hash'][:8], c['date'], c['author'], c['message']))
                shown += 1
            status.config(text=f"{shown} commit(s) shown")

        def load():
            branch = self.branch.get().strip() or None
            data = get_recent_commits(repo, limit=200, branch=branch if self.mode.get() == 'date' else None)
            if data.get('error'):
                # fallback: try without branch
                data = get_recent_commits(repo, limit=200)
            self.ui_queue.put(lambda: finish_load(data))

        def finish_load(data):
            nonlocal all_commits
            if data.get('error'):
                status.config(text=data['error'], fg=C["DANGER"])
                return
            all_commits = data['commits']
            populate(all_commits)

        def choose():
            sel = tree.selection()
            if sel:
                target_var.set(sel[0])
                self._validate_inputs()
                win.destroy()

        search_var.trace_add("write", lambda *a: populate(all_commits))
        tree.bind("<Double-1>", lambda e: choose())

        btn_row = tk.Frame(win, bg=C["BG"])
        btn_row.pack(fill=tk.X, padx=16, pady=12)
        self._make_button(btn_row, "Use Selected", choose, kind="primary").pack(side=tk.LEFT)
        self._make_button(btn_row, "Copy SHA", lambda: self.copy_sha(tree.selection()[0]) if tree.selection() else None,
                          kind="secondary").pack(side=tk.LEFT, padx=8)
        self._make_button(btn_row, "Close", win.destroy, kind="secondary").pack(side=tk.RIGHT)

        threading.Thread(target=load, daemon=True).start()

    def show_history(self):
        C = self.C
        win = tk.Toplevel(self)
        win.title("Operation History")
        win.geometry("720x520")
        win.configure(bg=C["BG"])

        header = tk.Frame(win, bg=C["BG"])
        header.pack(fill=tk.X, padx=16, pady=(16, 8))
        tk.Label(header, text="Operation History", bg=C["BG"], fg=C["TEXT"],
                 font=(self.ui_font, 14, "bold")).pack(anchor=tk.W)

        list_frame = tk.Frame(win, bg=C["BG"])
        list_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        scrollbar = ttk.Scrollbar(list_frame, style="Modern.Vertical.TScrollbar")
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        history_tree = ttk.Treeview(list_frame, columns=("Timestamp", "Mode", "Repo", "Output"),
                                    show="headings", yscrollcommand=scrollbar.set, style="Modern.Treeview")
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

        history = self.history_manager.get_history()
        for entry in history:
            timestamp = entry.get('timestamp', '')
            try:
                dt = datetime.fromisoformat(timestamp)
                timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
            mode = entry.get('mode', 'unknown')
            repo = entry.get('parameters', {}).get('remote_url') or os.path.basename(entry.get('repo_path', ''))
            output = os.path.basename(entry.get('output_path', '')) if entry.get('output_path') else entry.get('output_path', '')
            entry_str = str(id(entry))
            history_tree.insert("", tk.END, values=(timestamp, mode, repo, output), tags=(entry_str,))
            if not hasattr(self, '_history_entries'):
                self._history_entries = {}
            self._history_entries[entry_str] = entry

        button_frame = tk.Frame(win, bg=C["BG"])
        button_frame.pack(fill=tk.X, padx=16, pady=12)

        def load_selected():
            selection = history_tree.selection()
            if selection:
                item = history_tree.item(selection[0])
                entry_id = item['tags'][0] if item['tags'] else None
                if entry_id and hasattr(self, '_history_entries') and entry_id in self._history_entries:
                    entry = self._history_entries[entry_id]
                    self.load_from_history(entry)
                    win.destroy()

        def clear_history():
            if messagebox.askyesno("Clear history", "Delete all saved history entries?"):
                try:
                    self.history_manager.clear_history()
                except OSError as exc:
                    messagebox.showerror("History", f"Could not clear saved history: {exc}")
                    return
                win.destroy()
                self._refresh_recent_repos()
                self.show_history()

        self._make_button(button_frame, "Load Selected", load_selected, kind="primary").pack(side=tk.LEFT, padx=(0, 8))
        self._make_button(button_frame, "Clear History", clear_history, kind="danger").pack(side=tk.LEFT)
        self._make_button(button_frame, "Close", win.destroy, kind="secondary").pack(side=tk.RIGHT)

    def load_from_history(self, entry):
        remote = entry.get('parameters', {}).get('remote_url', '')
        self.source_mode.set('HTTPS URL' if remote else 'Local folder')
        self.change_source()
        self.remote_url.set(remote)
        if remote:
            cached = entry.get('repo_path', '')
            if self._is_git_repo(cached):
                self.remote_connected_url = remote
                self.repo_path.set(cached)
        else:
            self.repo_path.set(entry.get('repo_path', ''))
        self.output_path.set(entry.get('output_path', ''))
        self.mode.set(entry.get('mode', 'date'))
        self.archive_format.set(entry.get('archive_format', 'zip'))

        params = entry.get('parameters', {})
        self.start_date.set(params.get('start_date', ''))
        self.end_date.set(params.get('end_date', ''))
        self.branch.set(params.get('branch', 'main'))
        self.author.set(params.get('author', ''))
        self.start_sha.set(params.get('start_sha', ''))
        self.exclude_start.set(params.get('exclude_start', False))
        self.changelog_format.set(params.get('changelog_format', 'txt'))
        self.end_sha.set(params.get('end_sha', ''))
        self.commit_sha.set(params.get('commit_sha', ''))
        self.start_tag.set(params.get('start_tag', ''))
        self.end_tag.set(params.get('end_tag', ''))
        self.exclude_patterns.set(params.get('exclude_patterns', self.exclude_patterns.get()))

        self._refresh_mode_buttons()
        self.on_mode_change()
        self.refresh_repository()
        self.log("Loaded configuration from history.")


if __name__ == "__main__":
    app = App()
    app.mainloop()
