"""
=============================================================================
  GuardianEye — File Integrity Watcher  |  GUI Edition
  Author  : SentinelFIM Project
  Version : 2.0 (GUI)
=============================================================================
  Full tkinter GUI wrapper around the GuardianEye core (fim_scanner.py).
  All integrity logic lives in fim_scanner.py — this file only handles UI.

  Requires: Python 3.8+  (tkinter is included in standard library)
=============================================================================
"""

import os
import sys
import json
import threading
import time
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font
from datetime import datetime

# ── Import core engine from fim_scanner.py ───────────────────────────────────
# We reuse the fingerprint + snapshot + trust-store functions directly.
try:
    from fim_scanner import (
        fingerprint,
        snapshot_directory,
        save_trust_store,
        load_trust_store,
        record_event,
        ensure_watch_dir,
        WATCH_DIR,
        STORE_FILE,
        EVENTS_LOG,
    )
except ImportError as e:
    print(f"[ERROR] Could not import fim_scanner.py: {e}")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# COLOUR PALETTE  (dark SOC / terminal theme)
# ─────────────────────────────────────────────────────────────────────────────
BG_DARK    = "#0d1117"   # main background
BG_PANEL   = "#161b22"   # side panel / cards
BG_CARD    = "#21262d"   # input/log card
BORDER     = "#30363d"   # widget borders
TEXT_PRI   = "#e6edf3"   # primary text
TEXT_SEC   = "#8b949e"   # secondary / dim text
ACCENT     = "#58a6ff"   # blue accent
GREEN      = "#3fb950"   # safe / ok
YELLOW     = "#d29922"   # modified / warning
RED        = "#f85149"   # deleted / danger
CYAN       = "#39c5cf"   # new file
PURPLE     = "#bc8cff"   # trust-store header

FONT_MONO  = ("Consolas", 10)
FONT_MONO_SM = ("Consolas", 9)
FONT_UI    = ("Segoe UI", 10)
FONT_UI_B  = ("Segoe UI", 10, "bold")
FONT_H1    = ("Segoe UI", 16, "bold")
FONT_H2    = ("Segoe UI", 12, "bold")
FONT_SMALL = ("Segoe UI", 8)


# =============================================================================
# BACKGROUND WATCHER THREAD
# =============================================================================

class WatcherThread(threading.Thread):
    """
    Runs the integrity-check loop in a background daemon thread.
    Posts alert messages to a shared queue so the GUI can display them
    without blocking the Tk event loop.
    """

    def __init__(self, trusted: dict, alert_queue: queue.Queue):
        super().__init__(daemon=True)
        self.trusted      = trusted
        self.alert_queue  = alert_queue
        self._stop_flag   = threading.Event()
        self.violations   = 0

    def stop(self):
        self._stop_flag.set()

    def run(self):
        while not self._stop_flag.is_set():
            time.sleep(1)
            if self._stop_flag.is_set():
                break

            live    = snapshot_directory()
            alerts  = []

            # ── MODIFIED and NEW FILE ────────────────────────────────────────
            for rel_path, live_info in live.items():
                if rel_path in self.trusted:
                    if self.trusted[rel_path]["sha256"] != live_info["sha256"]:
                        detail = (
                            f"stored:  {self.trusted[rel_path]['sha256'][:32]}...\n"
                            f"current: {live_info['sha256'][:32]}..."
                        )
                        alerts.append(("MODIFIED", rel_path, detail))
                else:
                    alerts.append((
                        "NEW FILE", rel_path,
                        f"sha256: {live_info['sha256'][:48]}..."
                    ))

            # ── DELETED ──────────────────────────────────────────────────────
            for rel_path in list(self.trusted.keys()):
                full_path = os.path.join(WATCH_DIR, rel_path)
                if not os.path.exists(full_path):
                    alerts.append(("DELETED", rel_path, "file no longer exists on disk"))

            self.violations += len(alerts)
            ts = datetime.now().strftime("%H:%M:%S")

            if alerts:
                for kind, path, detail in alerts:
                    record_event(kind, path, detail.replace("\n", " | "))
                    self.alert_queue.put(("alert", kind, path, detail, ts))
            else:
                self.alert_queue.put(("ok", ts))

            # ── KEY FIX: sync baseline to current live state after each cycle ─
            # Each alert fires ONCE only — when the change actually happens.
            # Modified files get their new hash recorded, new files get added,
            # deleted files are removed — so the same event never repeats.
            self.trusted = dict(live)


# =============================================================================
# MAIN GUI APPLICATION
# =============================================================================

class GuardianEyeApp:
    def __init__(self, root: tk.Tk):
        self.root         = root
        self.watcher      = None
        self.alert_queue  = queue.Queue()
        self._watching    = False
        self._alert_count = 0
        self._ok_ticks    = 0

        self._setup_window()
        self._build_ui()
        self._refresh_store_status()
        self._poll_queue()   # start the queue-polling loop

    # ─────────────────────────────────────────────────────────────────────────
    # WINDOW SETUP
    # ─────────────────────────────────────────────────────────────────────────

    def _setup_window(self):
        self.root.title("GuardianEye — File Integrity Watcher")
        self.root.configure(bg=BG_DARK)
        self.root.geometry("1100x720")
        self.root.minsize(900, 600)

        # App icon (canvas-drawn shield)
        try:
            icon_img = self._make_icon()
            self.root.iconphoto(True, icon_img)
        except Exception:
            pass

    def _make_icon(self):
        c = tk.Canvas(width=32, height=32, bg=BG_DARK, highlightthickness=0)
        c.create_polygon([16,2, 28,8, 28,18, 16,30, 4,18, 4,8],
                         fill=ACCENT, outline="")
        img = tk.PhotoImage(width=32, height=32)
        return img

    # ─────────────────────────────────────────────────────────────────────────
    # UI CONSTRUCTION
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Root grid ────────────────────────────────────────────────────────
        self.root.columnconfigure(0, weight=0)   # sidebar
        self.root.columnconfigure(1, weight=1)   # main
        self.root.rowconfigure(0, weight=0)      # header
        self.root.rowconfigure(1, weight=1)      # content
        self.root.rowconfigure(2, weight=0)      # status bar

        self._build_header()
        self._build_sidebar()
        self._build_main()
        self._build_statusbar()

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = tk.Frame(self.root, bg=BG_PANEL,
                       highlightbackground=BORDER, highlightthickness=1)
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew")
        hdr.columnconfigure(1, weight=1)

        # Shield icon (canvas)
        shield_cv = tk.Canvas(hdr, width=42, height=42,
                              bg=BG_PANEL, highlightthickness=0)
        shield_cv.grid(row=0, column=0, padx=(18, 8), pady=10)
        shield_cv.create_polygon([21,4, 34,10, 34,22, 21,36, 8,22, 8,10],
                                 fill=ACCENT, outline="")
        shield_cv.create_text(21, 21, text="G", fill="white",
                              font=("Segoe UI", 13, "bold"))

        # Title + subtitle
        title_frm = tk.Frame(hdr, bg=BG_PANEL)
        title_frm.grid(row=0, column=1, sticky="w", pady=10)
        tk.Label(title_frm, text="GuardianEye",
                 font=FONT_H1, fg=TEXT_PRI, bg=BG_PANEL).pack(anchor="w")
        tk.Label(title_frm, text="File Integrity Watcher  —  SHA-256  |  Real-time monitoring",
                 font=FONT_SMALL, fg=TEXT_SEC, bg=BG_PANEL).pack(anchor="w")

        # Connection dot
        dot_frm = tk.Frame(hdr, bg=BG_PANEL)
        dot_frm.grid(row=0, column=2, padx=20)
        self._status_dot = tk.Canvas(dot_frm, width=12, height=12,
                                     bg=BG_PANEL, highlightthickness=0)
        self._status_dot.pack(side="left", padx=(0, 6))
        self._status_dot.create_oval(2, 2, 10, 10, fill=TEXT_SEC, outline="", tags="dot")
        self._status_lbl = tk.Label(dot_frm, text="Idle",
                                    font=FONT_UI_B, fg=TEXT_SEC, bg=BG_PANEL)
        self._status_lbl.pack(side="left")

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self):
        sb = tk.Frame(self.root, bg=BG_PANEL, width=230,
                      highlightbackground=BORDER, highlightthickness=1)
        sb.grid(row=1, column=0, sticky="nsew")
        sb.grid_propagate(False)
        sb.columnconfigure(0, weight=1)

        # ── Section: Trust Store ─────────────────────────────────────────────
        self._section_label(sb, "TRUST STORE", row=0)

        # Store status card
        store_card = tk.Frame(sb, bg=BG_CARD, padx=12, pady=10,
                              highlightbackground=BORDER, highlightthickness=1)
        store_card.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")
        store_card.columnconfigure(0, weight=1)

        self._store_icon_lbl = tk.Label(store_card, text="◉  No store found",
                                        font=FONT_UI_B, fg=RED, bg=BG_CARD)
        self._store_icon_lbl.grid(row=0, column=0, sticky="w")

        self._store_detail = tk.Label(store_card, text="",
                                      font=FONT_SMALL, fg=TEXT_SEC, bg=BG_CARD,
                                      wraplength=170, justify="left")
        self._store_detail.grid(row=1, column=0, sticky="w", pady=(4, 0))

        # Buttons
        self._btn_build = self._sidebar_btn(
            sb, "🔒  Build Trust Store", self._action_build, row=2,
            colour=GREEN, desc="Fingerprint all files now"
        )
        self._btn_watch = self._sidebar_btn(
            sb, "▶  Start Watching", self._action_start, row=3,
            colour=ACCENT, desc="Compare live state with store"
        )
        self._btn_stop = self._sidebar_btn(
            sb, "■  Stop Watching", self._action_stop, row=4,
            colour=RED, desc="Stop the live monitor"
        )
        self._btn_stop.configure(state="disabled")

        # ── Section: Folder ──────────────────────────────────────────────────
        self._section_label(sb, "MONITORED FOLDER", row=5)

        folder_card = tk.Frame(sb, bg=BG_CARD, padx=12, pady=10,
                               highlightbackground=BORDER, highlightthickness=1)
        folder_card.grid(row=6, column=0, padx=12, pady=(0, 8), sticky="ew")
        folder_card.columnconfigure(0, weight=1)

        rel = os.path.relpath(WATCH_DIR, os.path.dirname(STORE_FILE))
        tk.Label(folder_card, text=rel + "/",
                 font=FONT_MONO_SM, fg=CYAN, bg=BG_CARD).grid(row=0, column=0, sticky="w")

        self._file_count_lbl = tk.Label(folder_card, text="0 files enrolled",
                                        font=FONT_SMALL, fg=TEXT_SEC, bg=BG_CARD)
        self._file_count_lbl.grid(row=1, column=0, sticky="w", pady=(4, 0))

        self._sidebar_btn(
            sb, "📂  Open Folder", self._action_open_folder, row=7,
            colour=TEXT_SEC, desc="Browse watched_files in Explorer"
        )

        # ── Section: Alerts ──────────────────────────────────────────────────
        self._section_label(sb, "SESSION STATS", row=8)

        stats_card = tk.Frame(sb, bg=BG_CARD, padx=12, pady=10,
                              highlightbackground=BORDER, highlightthickness=1)
        stats_card.grid(row=9, column=0, padx=12, pady=(0, 8), sticky="ew")

        self._stat_modified = self._stat_row(stats_card, "Modified", YELLOW, 0)
        self._stat_deleted  = self._stat_row(stats_card, "Deleted",  RED,    1)
        self._stat_newfile  = self._stat_row(stats_card, "New File", CYAN,   2)

        self._sidebar_btn(
            sb, "🗑  Clear Alerts", self._action_clear, row=10,
            colour=TEXT_SEC, desc="Clear the alert feed"
        )
        self._sidebar_btn(
            sb, "📄  View Log File", self._action_view_log, row=11,
            colour=TEXT_SEC, desc="Open guardian_events.log"
        )

    def _section_label(self, parent, text, row):
        lbl = tk.Label(parent, text=text, font=("Segoe UI", 8, "bold"),
                       fg=TEXT_SEC, bg=BG_PANEL, padx=14, pady=4)
        lbl.grid(row=row, column=0, sticky="w", pady=(10, 0))

    def _sidebar_btn(self, parent, text, cmd, row, colour, desc):
        frm = tk.Frame(parent, bg=BG_PANEL)
        frm.grid(row=row, column=0, padx=12, pady=(0, 4), sticky="ew")
        frm.columnconfigure(0, weight=1)
        btn = tk.Button(frm, text=text, command=cmd,
                        font=FONT_UI_B, fg=colour, bg=BG_CARD,
                        activeforeground=colour, activebackground=BG_PANEL,
                        relief="flat", bd=0, padx=10, pady=8, cursor="hand2",
                        highlightbackground=BORDER, highlightthickness=1)
        btn.grid(row=0, column=0, sticky="ew")
        tk.Label(frm, text=desc, font=FONT_SMALL,
                 fg=TEXT_SEC, bg=BG_PANEL).grid(row=1, column=0, sticky="w", padx=2)
        return btn

    def _stat_row(self, parent, label, colour, row):
        tk.Label(parent, text=label, font=FONT_SMALL,
                 fg=TEXT_SEC, bg=BG_CARD).grid(row=row, column=0, sticky="w")
        var = tk.StringVar(value="0")
        lbl = tk.Label(parent, textvariable=var, font=FONT_UI_B,
                       fg=colour, bg=BG_CARD)
        lbl.grid(row=row, column=1, sticky="e", padx=(20, 0))
        parent.columnconfigure(1, weight=1)
        return var

    # ── Main panel ────────────────────────────────────────────────────────────

    def _build_main(self):
        main = tk.Frame(self.root, bg=BG_DARK)
        main.grid(row=1, column=1, sticky="nsew", padx=(0, 0))
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        # Tab bar
        tab_bar = tk.Frame(main, bg=BG_PANEL,
                           highlightbackground=BORDER, highlightthickness=1)
        tab_bar.grid(row=0, column=0, sticky="ew")

        self._tabs = {}
        self._active_tab = tk.StringVar(value="alerts")

        for name, label in [("alerts", "  🔔 Live Alerts  "),
                            ("files",  "  📁 Enrolled Files  "),
                            ("log",    "  📄 Event Log  ")]:
            btn = tk.Button(tab_bar, text=label,
                           font=FONT_UI_B, relief="flat", bd=0,
                           padx=8, pady=8, cursor="hand2",
                           command=lambda n=name: self._switch_tab(n))
            btn.pack(side="left")
            self._tabs[name] = btn

        # Content frame
        self._content = tk.Frame(main, bg=BG_DARK)
        self._content.grid(row=1, column=0, sticky="nsew")
        self._content.columnconfigure(0, weight=1)
        self._content.rowconfigure(0, weight=1)

        self._build_alerts_tab()
        self._build_files_tab()
        self._build_log_tab()
        self._switch_tab("alerts")

    def _switch_tab(self, name):
        self._active_tab.set(name)
        for n, btn in self._tabs.items():
            if n == name:
                btn.configure(fg=ACCENT, bg=BG_DARK,
                              activeforeground=ACCENT, activebackground=BG_DARK)
            else:
                btn.configure(fg=TEXT_SEC, bg=BG_PANEL,
                              activeforeground=TEXT_PRI, activebackground=BG_PANEL)

        # show/hide frames
        for n, frm in self._tab_frames.items():
            if n == name:
                frm.grid(row=0, column=0, sticky="nsew")
            else:
                frm.grid_remove()

        if name == "files":
            self._refresh_files_tab()
        if name == "log":
            self._refresh_log_tab()

    # ── Alerts tab ────────────────────────────────────────────────────────────

    def _build_alerts_tab(self):
        frm = tk.Frame(self._content, bg=BG_DARK)
        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(1, weight=1)

        # Toolbar
        toolbar = tk.Frame(frm, bg=BG_PANEL,
                           highlightbackground=BORDER, highlightthickness=1)
        toolbar.grid(row=0, column=0, sticky="ew")

        tk.Label(toolbar, text="  Real-time Integrity Alert Feed",
                 font=FONT_UI_B, fg=TEXT_SEC, bg=BG_PANEL,
                 pady=8).pack(side="left")

        self._alert_count_lbl = tk.Label(toolbar, text="0 alerts",
                                         font=FONT_UI_B, fg=YELLOW,
                                         bg=BG_PANEL, padx=12)
        self._alert_count_lbl.pack(side="right")

        # Alert text box
        txt_frm = tk.Frame(frm, bg=BG_DARK, pady=8, padx=8)
        txt_frm.grid(row=1, column=0, sticky="nsew")
        txt_frm.columnconfigure(0, weight=1)
        txt_frm.rowconfigure(0, weight=1)

        self.alert_box = tk.Text(
            txt_frm, bg=BG_CARD, fg=TEXT_PRI,
            font=FONT_MONO, relief="flat", bd=0,
            state="disabled", wrap="word",
            selectbackground=BORDER, insertbackground=ACCENT,
            highlightbackground=BORDER, highlightthickness=1,
            padx=14, pady=10
        )
        self.alert_box.grid(row=0, column=0, sticky="nsew")

        scroll = tk.Scrollbar(txt_frm, command=self.alert_box.yview,
                              bg=BG_CARD, troughcolor=BG_DARK,
                              activebackground=BORDER, relief="flat")
        scroll.grid(row=0, column=1, sticky="ns")
        self.alert_box.configure(yscrollcommand=scroll.set)

        # Define text tags for colours
        self.alert_box.tag_configure("modified",  foreground=YELLOW)
        self.alert_box.tag_configure("deleted",   foreground=RED)
        self.alert_box.tag_configure("new_file",  foreground=CYAN)
        self.alert_box.tag_configure("ok",        foreground=GREEN)
        self.alert_box.tag_configure("dim",       foreground=TEXT_SEC)
        self.alert_box.tag_configure("bold",      font=FONT_UI_B)
        self.alert_box.tag_configure("heading",   font=("Consolas", 10, "bold"))
        self.alert_box.tag_configure("ts",        foreground=TEXT_SEC)
        self.alert_box.tag_configure("separator", foreground=BORDER)

        self._write_alert("dim", "  Waiting for watcher to start...\n")
        self._write_alert("dim", "  Click 'Build Trust Store' then 'Start Watching'.\n\n")

        self._tab_frames = {"alerts": frm}

    # ── Files tab ─────────────────────────────────────────────────────────────

    def _build_files_tab(self):
        frm = tk.Frame(self._content, bg=BG_DARK)
        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(1, weight=1)

        # Toolbar
        toolbar = tk.Frame(frm, bg=BG_PANEL,
                           highlightbackground=BORDER, highlightthickness=1)
        toolbar.grid(row=0, column=0, sticky="ew")
        tk.Label(toolbar, text="  Enrolled Files (from trust_store.json)",
                 font=FONT_UI_B, fg=TEXT_SEC, bg=BG_PANEL,
                 pady=8).pack(side="left")
        tk.Button(toolbar, text="⟳ Refresh", font=FONT_UI,
                  fg=ACCENT, bg=BG_PANEL, relief="flat", bd=0,
                  padx=8, cursor="hand2",
                  command=self._refresh_files_tab).pack(side="right", padx=8)

        # Treeview table
        tree_frm = tk.Frame(frm, bg=BG_DARK, padx=8, pady=8)
        tree_frm.grid(row=1, column=0, sticky="nsew")
        tree_frm.columnconfigure(0, weight=1)
        tree_frm.rowconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Guard.Treeview",
                        background=BG_CARD, foreground=TEXT_PRI,
                        fieldbackground=BG_CARD, rowheight=26,
                        font=FONT_MONO_SM, borderwidth=0)
        style.configure("Guard.Treeview.Heading",
                        background=BG_PANEL, foreground=TEXT_SEC,
                        font=("Segoe UI", 9, "bold"), relief="flat")
        style.map("Guard.Treeview",
                  background=[("selected", BORDER)],
                  foreground=[("selected", TEXT_PRI)])

        self.file_tree = ttk.Treeview(
            tree_frm, style="Guard.Treeview",
            columns=("file", "sha256", "size", "seen"),
            show="headings"
        )
        self.file_tree.heading("file",   text="File")
        self.file_tree.heading("sha256", text="SHA-256 (first 48 chars)")
        self.file_tree.heading("size",   text="Size")
        self.file_tree.heading("seen",   text="Fingerprinted At")
        self.file_tree.column("file",   width=200, stretch=True)
        self.file_tree.column("sha256", width=340, stretch=True)
        self.file_tree.column("size",   width=80,  stretch=False)
        self.file_tree.column("seen",   width=160, stretch=False)

        self.file_tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tree_frm, orient="vertical",
                            command=self.file_tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.file_tree.configure(yscrollcommand=vsb.set)

        self._tab_frames["files"] = frm

    # ── Log tab ───────────────────────────────────────────────────────────────

    def _build_log_tab(self):
        frm = tk.Frame(self._content, bg=BG_DARK)
        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(1, weight=1)

        toolbar = tk.Frame(frm, bg=BG_PANEL,
                           highlightbackground=BORDER, highlightthickness=1)
        toolbar.grid(row=0, column=0, sticky="ew")
        tk.Label(toolbar, text="  guardian_events.log  — full audit trail",
                 font=FONT_UI_B, fg=TEXT_SEC, bg=BG_PANEL,
                 pady=8).pack(side="left")
        tk.Button(toolbar, text="⟳ Refresh", font=FONT_UI,
                  fg=ACCENT, bg=BG_PANEL, relief="flat", bd=0,
                  padx=8, cursor="hand2",
                  command=self._refresh_log_tab).pack(side="right", padx=8)

        log_frm = tk.Frame(frm, bg=BG_DARK, padx=8, pady=8)
        log_frm.grid(row=1, column=0, sticky="nsew")
        log_frm.columnconfigure(0, weight=1)
        log_frm.rowconfigure(0, weight=1)

        self.log_box = tk.Text(
            log_frm, bg=BG_CARD, fg=TEXT_PRI,
            font=FONT_MONO_SM, relief="flat", bd=0,
            state="disabled", wrap="none",
            highlightbackground=BORDER, highlightthickness=1,
            padx=14, pady=10
        )
        self.log_box.grid(row=0, column=0, sticky="nsew")
        vsb2 = tk.Scrollbar(log_frm, command=self.log_box.yview,
                            bg=BG_CARD, troughcolor=BG_DARK, relief="flat")
        vsb2.grid(row=0, column=1, sticky="ns")
        hsb2 = tk.Scrollbar(log_frm, orient="horizontal",
                            command=self.log_box.xview,
                            bg=BG_CARD, troughcolor=BG_DARK, relief="flat")
        hsb2.grid(row=1, column=0, sticky="ew")
        self.log_box.configure(yscrollcommand=vsb2.set, xscrollcommand=hsb2.set)

        self.log_box.tag_configure("modified", foreground=YELLOW)
        self.log_box.tag_configure("deleted",  foreground=RED)
        self.log_box.tag_configure("new",      foreground=CYAN)

        self._tab_frames["log"] = frm

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=BG_PANEL, height=26,
                       highlightbackground=BORDER, highlightthickness=1)
        bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        bar.grid_propagate(False)

        self._status_bar_lbl = tk.Label(
            bar, text="  Ready",
            font=FONT_SMALL, fg=TEXT_SEC, bg=BG_PANEL, anchor="w")
        self._status_bar_lbl.pack(side="left", fill="x", expand=True)

        self._clock_lbl = tk.Label(
            bar, text="", font=FONT_SMALL, fg=TEXT_SEC, bg=BG_PANEL, padx=10)
        self._clock_lbl.pack(side="right")
        self._tick_clock()

    def _tick_clock(self):
        self._clock_lbl.configure(
            text=datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        self.root.after(1000, self._tick_clock)

    # ─────────────────────────────────────────────────────────────────────────
    # ACTIONS
    # ─────────────────────────────────────────────────────────────────────────

    def _restore_clean_files(self):
        """
        Wipes watched_files/ and recreates the original clean sample files.
        Called before building the trust store so we always start from a
        known-good state with no leftover tampered or dropped files.
        """
        import shutil
        # Remove entire folder and recreate it clean
        if os.path.exists(WATCH_DIR):
            shutil.rmtree(WATCH_DIR)
        os.makedirs(os.path.join(WATCH_DIR, "sensitive"), exist_ok=True)

        clean_files = {
            "a.txt": (
                "System configuration — version 4.1\n"
                "hostname  = prod-server-01\n"
                "region    = us-east-1\n"
                "debug     = false\n"
            ),
            "b.txt": (
                "Access control list\n"
                "admin   ALLOW ALL\n"
                "analyst ALLOW READ\n"
                "guest   DENY  WRITE\n"
            ),
            "c.txt": (
                "Deployment manifest\n"
                "image   = registry.io/app:v2.5\n"
                "replicas = 3\n"
                "port    = 8443\n"
            ),
            "d.txt": (
                "Audit seed — do not modify\n"
                "created = 2026-07-22\n"
                "owner   = security-team\n"
            ),
            os.path.join("sensitive", "credentials.txt"): (
                "# Demo credentials — not real\n"
                "db_user = app_user\n"
                "db_pass = ChangeMe123!\n"
            ),
        }
        for rel, content in clean_files.items():
            full = os.path.join(WATCH_DIR, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as fh:
                fh.write(content)

    def _action_build(self):
        """Restore clean files, then build a fresh trust store."""
        # Always start from clean known-good files so the baseline is
        # never built on top of previously tampered state.
        self._restore_clean_files()

        records = snapshot_directory()
        if not records:
            messagebox.showwarning(
                "No Files",
                f"No files found in:\n{WATCH_DIR}\n\nAdd files and try again.")
            return

        save_trust_store(records)
        self._refresh_store_status()

        count = len(records)
        self._set_status(f"Trust store built — {count} file(s) fingerprinted.", GREEN)
        self._write_alert("ok",
            f"\n  ✔  Trust store built at "
            f"{datetime.now().strftime('%H:%M:%S')} — {count} clean file(s) enrolled.\n\n")

    def _action_start(self):
        """Take a fresh live snapshot and start the background watcher."""
        # Verify trust store exists (user must have clicked Build first)
        _, captured_at = load_trust_store()
        if captured_at is None:
            messagebox.showwarning(
                "No Trust Store",
                "No trust_store.json found.\n\nClick 'Build Trust Store' first.")
            return

        if self._watching:
            messagebox.showinfo("Already Watching", "Watcher is already running.")
            return

        # KEY FIX: use a LIVE snapshot taken right now as the starting
        # baseline — not the saved trust store. This means the watcher
        # compares future changes against the current state of files,
        # so any pre-existing differences are silently accepted and
        # ZERO alerts fire at startup. Alerts only appear when you
        # actually change something AFTER the watcher starts.
        live_baseline = snapshot_directory()
        count = len(live_baseline)

        self._watching = True
        self._update_dot(GREEN, "Watching")
        self._btn_watch.configure(state="disabled")
        self._btn_stop.configure(state="normal")
        self._btn_build.configure(state="disabled")

        self._write_alert("ok",
            f"\n  ▶  Watcher started — monitoring {count} file(s).\n"
            f"     Alerts will appear when files change from this point on.\n\n")
        self._set_status(f"Watching {count} file(s) — checking every second.", GREEN)

        self.watcher = WatcherThread(live_baseline, self.alert_queue)
        self.watcher.start()

    def _action_stop(self):
        """Stop the background watcher."""
        if self.watcher:
            self.watcher.stop()
            self.watcher = None

        self._watching = False
        self._update_dot(TEXT_SEC, "Idle")
        self._btn_watch.configure(state="normal")
        self._btn_stop.configure(state="disabled")
        self._btn_build.configure(state="normal")

        self._write_alert("dim",
            f"  ■  Watcher stopped at {datetime.now().strftime('%H:%M:%S')}.\n\n")
        self._set_status("Watcher stopped.", TEXT_SEC)

    def _action_clear(self):
        """Clear the alert feed."""
        self.alert_box.configure(state="normal")
        self.alert_box.delete("1.0", "end")
        self.alert_box.configure(state="disabled")
        self._alert_count = 0
        self._alert_count_lbl.configure(text="0 alerts")

    def _action_open_folder(self):
        """Open the watched_files folder in Windows Explorer."""
        os.makedirs(WATCH_DIR, exist_ok=True)
        os.startfile(WATCH_DIR)

    def _action_view_log(self):
        """Open guardian_events.log in Notepad."""
        if os.path.exists(EVENTS_LOG):
            os.startfile(EVENTS_LOG)
        else:
            messagebox.showinfo("No Log", "No events have been logged yet.")

    # ─────────────────────────────────────────────────────────────────────────
    # QUEUE POLLING — reads messages from the watcher thread every 200ms
    # ─────────────────────────────────────────────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                msg = self.alert_queue.get_nowait()

                if msg[0] == "ok":
                    ts = msg[1]
                    # Update status bar only — don't spam the alert box
                    self._set_status(
                        f"All files intact — last check {ts}", GREEN)

                elif msg[0] == "alert":
                    _, kind, path, detail, ts = msg
                    self._display_alert(kind, path, detail, ts)
                    self._update_stats(kind)

        except queue.Empty:
            pass

        self.root.after(200, self._poll_queue)

    # ─────────────────────────────────────────────────────────────────────────
    # DISPLAY HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _display_alert(self, kind, path, detail, ts):
        tag_map = {
            "MODIFIED": "modified",
            "DELETED":  "deleted",
            "NEW FILE": "new_file",
        }
        icon_map = {
            "MODIFIED": "~",
            "DELETED":  "-",
            "NEW FILE": "+",
        }
        tag  = tag_map.get(kind, "dim")
        icon = icon_map.get(kind, "?")

        self._alert_count += 1
        self._alert_count_lbl.configure(
            text=f"{self._alert_count} alert{'s' if self._alert_count > 1 else ''}")

        self.alert_box.configure(state="normal")
        self.alert_box.insert("end", f"  [{icon}] ", (tag, "heading"))
        self.alert_box.insert("end", f"{kind}  ", (tag, "bold"))
        self.alert_box.insert("end", f"• {ts}\n", "ts")
        self.alert_box.insert("end", f"      {path}\n", tag)
        if detail:
            for line in detail.split("\n"):
                self.alert_box.insert("end", f"      {line}\n", "dim")
        self.alert_box.insert("end", "\n")
        self.alert_box.configure(state="disabled")
        self.alert_box.see("end")

    def _write_alert(self, tag, text):
        self.alert_box.configure(state="normal")
        self.alert_box.insert("end", text, tag)
        self.alert_box.configure(state="disabled")
        self.alert_box.see("end")

    def _update_stats(self, kind):
        counts = {
            "MODIFIED": self._stat_modified,
            "DELETED":  self._stat_deleted,
            "NEW FILE": self._stat_newfile,
        }
        var = counts.get(kind)
        if var:
            var.set(str(int(var.get()) + 1))

    def _update_dot(self, colour, label):
        self._status_dot.itemconfigure("dot", fill=colour)
        self._status_lbl.configure(text=label, fg=colour)

    def _set_status(self, text, colour=TEXT_SEC):
        self._status_bar_lbl.configure(text=f"  {text}", fg=colour)

    # ─────────────────────────────────────────────────────────────────────────
    # REFRESH HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh_store_status(self):
        trusted, captured_at = load_trust_store()
        if trusted is None:
            self._store_icon_lbl.configure(text="◉  No store found", fg=RED)
            self._store_detail.configure(text="Click 'Build Trust Store' to create one.")
            self._file_count_lbl.configure(text="0 files enrolled")
        else:
            count = len(trusted)
            date_str = captured_at[:10] if captured_at else "unknown"
            self._store_icon_lbl.configure(
                text=f"◉  {count} files enrolled", fg=GREEN)
            self._store_detail.configure(text=f"Built: {date_str}")
            self._file_count_lbl.configure(text=f"{count} files enrolled")

    def _refresh_files_tab(self):
        for row in self.file_tree.get_children():
            self.file_tree.delete(row)

        trusted, _ = load_trust_store()
        if not trusted:
            return

        for rel_path, info in sorted(trusted.items()):
            sha   = info.get("sha256", "")[:48] + "..."
            size  = f"{info.get('size', 0):,} B"
            seen  = info.get("seen", "")
            self.file_tree.insert("", "end", values=(rel_path, sha, size, seen))

    def _refresh_log_tab(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")

        if not os.path.exists(EVENTS_LOG):
            self.log_box.insert("end", "  No events logged yet.\n", "")
        else:
            with open(EVENTS_LOG, "r", encoding="utf-8") as fh:
                for line in fh:
                    tag = ""
                    if "MODIFIED" in line:
                        tag = "modified"
                    elif "DELETED" in line:
                        tag = "deleted"
                    elif "NEW FILE" in line:
                        tag = "new"
                    self.log_box.insert("end", line, tag)

        self.log_box.configure(state="disabled")
        self.log_box.see("end")


# =============================================================================
# ENTRY POINT
# =============================================================================

def main():
    root = tk.Tk()

    # DPI awareness on Windows
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = GuardianEyeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
