"""Native Tk desktop interface. Network work stays off the UI thread."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from scrobbler import App, AppError, MAX_UPLOAD, acquire_instance_lock
from version import APP_NAME, VERSION

ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets"
STATUS = {"pending": "Ready", "expired": "Too old", "accepted": "Accepted",
          "uncertain": "Check outcome", "sending": "Sending", "ignored": "Ignored"}
THEMES = {
    False: dict(bg="#eaf3f7", panel="#ffffff", fg="#17384a", muted="#526b7c",
                edge="#cbdde7", accent="#067ba6", selection="#c9eaf7", field="#ffffff"),
    True: dict(bg="#101c29", panel="#192a3b", fg="#e7f3fc", muted="#a3bdce",
               edge="#334b60", accent="#126b93", selection="#264f6b", field="#122233"),
}


def date_label(timestamp):
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


class Desktop:
    def __init__(self, root, app):
        self.root, self.app = root, app
        self.selected = set()
        self.rows = {}
        self.snapshot = None
        self.busy = False
        self.results = queue.Queue()
        self.dialogs = []
        self.closed = False
        root.title(APP_NAME)
        root.geometry("1200x880")
        root.minsize(950, 760)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.style = ttk.Style(root)
        self.style.theme_use("clam")
        self.dark = tk.BooleanVar(root, value=app.preferences()["dark_mode"])
        self.search = tk.StringVar(root)
        self.filter = tk.StringVar(root, value="All plays")
        self.status = tk.StringVar(root, value="Choose a Rockbox log to get started.")
        self.account = tk.StringVar(root, value="Last.fm is disconnected")
        self.total = tk.StringVar(root)
        self.ready = tk.StringVar(root)
        self.accepted = tk.StringVar(root)
        self.selection_text = tk.StringVar(root)
        self.detail = tk.StringVar(root, value="Select a play to see its source and listening dates.")
        try:
            self.icon = tk.PhotoImage(file=str(ASSETS / "app.png"))
            root.iconphoto(True, self.icon)
        except tk.TclError:
            pass
        self._build()
        self.apply_theme()
        self.refresh()
        self.search.trace_add("write", lambda *_: self.render_rows())
        self.timer = root.after(100, self.poll)

    def _build(self):
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)
        sidebar = tk.Frame(self.root, bg="#10344c", width=218)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        try:
            self.logo = tk.PhotoImage(file=str(ASSETS / "branding/achilleus-white-small.png"))
            tk.Label(sidebar, image=self.logo, bg="#10344c").pack(pady=(30, 12))
        except tk.TclError:
            pass
        tk.Label(sidebar, text="AKI'S ROCKBOX\nSCROBBLER", font=("Segoe UI", 16, "bold"),
                 justify="left", bg="#10344c", fg="#effaff").pack(padx=22, anchor="w")
        tk.Label(sidebar, text="Your music. Your history.", font=("Segoe UI", 10),
                 bg="#10344c", fg="#a6d6e9").pack(padx=22, pady=(10, 25), anchor="w")
        for title, action in [("Settings", self.settings), ("User guide", self.guide),
                              ("Privacy & storage", self.privacy), ("About", self.about)]:
            ttk.Button(sidebar, text=title, command=action).pack(fill="x", padx=20, pady=5)
        ttk.Checkbutton(sidebar, text="Dark mode", variable=self.dark,
                        command=self.toggle_theme, style="Sidebar.TCheckbutton").pack(padx=22, pady=22, anchor="w")
        tk.Label(sidebar, text=f"Product of Achilleus\nv{VERSION}  ·  Native desktop", justify="left",
                 bg="#10344c", fg="#a6d6e9", font=("Segoe UI", 9)).pack(side="bottom", padx=22, pady=22, anchor="w")
        main = ttk.Frame(self.root, padding=(28, 22))
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(5, weight=1)
        self.banner = tk.Canvas(main, height=100, highlightthickness=0)
        self.banner.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        self.banner.bind("<Configure>", lambda _: self.draw_banner())
        account_row = ttk.Frame(main)
        account_row.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        account_row.columnconfigure(0, weight=1)
        ttk.Label(account_row, textvariable=self.account, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.connect_button = ttk.Button(account_row, text="Connect Last.fm", command=self.connect)
        self.connect_button.grid(row=0, column=1)
        self.stats = ttk.Frame(main)
        self.stats.grid(row=2, column=0, sticky="ew", pady=(0, 18))
        for i, (label, value) in enumerate([("IN YOUR QUEUE", self.total), ("READY TO SCROBBLE", self.ready), ("ACCEPTED", self.accepted)]):
            self.stats.columnconfigure(i, weight=1)
            card = ttk.Frame(self.stats, style="Card.TFrame", padding=(18, 12))
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 10, 0))
            ttk.Label(card, text=label, style="CardCaption.TLabel").pack(anchor="w")
            ttk.Label(card, textvariable=value, style="CardValue.TLabel").pack(anchor="w")
        controls = ttk.Frame(main)
        controls.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        controls.columnconfigure(1, weight=1)
        ttk.Button(controls, text="Import Rockbox log", command=self.import_dialog, style="Accent.TButton").grid(row=0, column=0, padx=(0, 12))
        entry = ttk.Entry(controls, textvariable=self.search)
        entry.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        entry.insert(0, "")
        ttk.Label(controls, text="Search artist / title / album", style="Muted.TLabel").grid(row=1, column=1, sticky="w", pady=(4, 0))
        filters = ttk.Combobox(controls, textvariable=self.filter, state="readonly", width=17,
                              values=["All plays", *STATUS.values()])
        filters.grid(row=0, column=2)
        filters.bind("<<ComboboxSelected>>", lambda _: self.render_rows())
        actions = ttk.Frame(main)
        actions.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        for text, action in [("Select ready", self.select_ready), ("Deselect all", self.deselect),
                             ("Check outcome", self.resolve), ("Clear queue", self.clear)]:
            ttk.Button(actions, text=text, command=action).pack(side="left", padx=(0, 8))
        table = ttk.Frame(main)
        table.grid(row=5, column=0, sticky="nsew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=("chosen", "artist", "title", "album", "date", "status"),
                                 show="headings", selectmode="browse")
        for name, heading, width in [("chosen", "✓", 34), ("artist", "Artist", 130), ("title", "Track", 160),
                                      ("album", "Album", 125), ("date", "Listening time", 145), ("status", "Status", 106)]:
            self.tree.heading(name, text=heading)
            self.tree.column(name, width=width, minwidth=34 if name == "chosen" else 70,
                             stretch=name in {"artist", "title", "album"})
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        xscroll = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        xscroll.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=scroll.set, xscrollcommand=xscroll.set)
        self.tree.bind("<Button-1>", self.click_row)
        self.tree.bind("<space>", self.toggle_focused)
        self.tree.bind("<<TreeviewSelect>>", self.show_detail)
        ttk.Label(main, textvariable=self.detail, style="Muted.TLabel", wraplength=760,
                  padding=(0, 10)).grid(row=6, column=0, sticky="ew")
        footer = ttk.Frame(main)
        footer.grid(row=7, column=0, sticky="ew", pady=(4, 10))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.selection_text).grid(row=0, column=0, sticky="w")
        self.submit_button = ttk.Button(footer, text="Scrobble selected", command=self.submit, style="Accent.TButton")
        self.submit_button.grid(row=0, column=1)
        self.progress = ttk.Progressbar(main, mode="determinate")
        self.progress.grid(row=8, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(main, textvariable=self.status, style="Muted.TLabel", wraplength=760).grid(row=9, column=0, sticky="ew")

    def apply_theme(self):
        c = THEMES[self.dark.get()]
        self.root.configure(bg=c["bg"])
        self.style.configure(".", background=c["bg"], foreground=c["fg"], font=("Segoe UI", 10),
                             lightcolor=c["edge"], darkcolor=c["edge"], bordercolor=c["edge"],
                             troughcolor=c["bg"], arrowcolor=c["fg"])
        self.style.configure("TFrame", background=c["bg"])
        self.style.configure("TLabel", background=c["bg"], foreground=c["fg"])
        self.style.configure("Muted.TLabel", foreground=c["muted"])
        self.style.configure("Card.TFrame", background=c["panel"])
        self.style.configure("CardCaption.TLabel", background=c["panel"], foreground=c["muted"], font=("Segoe UI", 9))
        self.style.configure("CardValue.TLabel", background=c["panel"], foreground=c["fg"], font=("Segoe UI", 24, "bold"))
        self.style.configure("TButton", background=c["panel"], foreground=c["fg"], bordercolor=c["edge"], padding=(12, 8))
        self.style.map("TButton", background=[("active", c["selection"])], foreground=[("disabled", c["muted"])])
        self.style.configure("Accent.TButton", background=c["accent"], foreground="#ffffff")
        self.style.map("Accent.TButton", background=[("active", "#168fb7"), ("disabled", c["edge"])], foreground=[("disabled", c["muted"])])
        self.style.configure("TEntry", fieldbackground=c["field"], foreground=c["fg"], insertcolor=c["fg"], bordercolor=c["edge"], padding=7)
        self.style.configure("TSpinbox", fieldbackground=c["field"], foreground=c["fg"], arrowcolor=c["fg"], padding=7)
        self.style.configure("TCombobox", fieldbackground=c["field"], foreground=c["fg"], arrowcolor=c["fg"], padding=7)
        self.style.map("TCombobox", fieldbackground=[("readonly", c["field"])], foreground=[("readonly", c["fg"])], selectbackground=[("readonly", c["field"])], selectforeground=[("readonly", c["fg"])])
        self.root.option_add("*TCombobox*Listbox.background", c["field"])
        self.root.option_add("*TCombobox*Listbox.foreground", c["fg"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", c["selection"])
        self.style.configure("TCheckbutton", background=c["bg"], foreground=c["fg"])
        self.style.map("TCheckbutton", background=[("active", c["bg"])], indicatorbackground=[("selected", c["accent"]), ("!selected", c["field"])])
        self.style.configure("Sidebar.TCheckbutton", background="#10344c", foreground="#effaff")
        self.style.map("Sidebar.TCheckbutton", background=[("active", "#10344c")])
        self.style.configure("Treeview", background=c["panel"], fieldbackground=c["panel"], foreground=c["fg"], rowheight=33, bordercolor=c["edge"])
        self.style.map("Treeview", background=[("selected", c["selection"])], foreground=[("selected", c["fg"])])
        self.style.configure("Treeview.Heading", background=c["bg"], foreground=c["muted"], padding=(8, 9), font=("Segoe UI", 9, "bold"))
        self.style.map("Treeview.Heading", background=[("active", c["selection"])])
        self.tree.tag_configure("muted", foreground=c["muted"])
        self.style.configure("Horizontal.TProgressbar", background=c["accent"], troughcolor=c["edge"])
        self.style.configure("TScrollbar", background=c["panel"], troughcolor=c["bg"], arrowcolor=c["fg"])
        self.style.map("TScrollbar", background=[("active", c["selection"])])
        for dialog in self.dialogs:
            if dialog.winfo_exists():
                dialog.configure(bg=c["bg"])
                def recolor(widget):
                    if isinstance(widget, tk.Text):
                        widget.configure(bg=c["panel"], fg=c["fg"], insertbackground=c["fg"])
                    for child in widget.winfo_children():
                        recolor(child)
                recolor(dialog)
        self.draw_banner()
        if os.name == "nt":
            import ctypes
            # Use the OS title-bar appearance when supported by Windows 10/11.
            try:
                self.root.update_idletasks()
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                dark = ctypes.c_int(int(self.dark.get()))
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))
            except (AttributeError, OSError):
                pass

    def draw_banner(self):
        dark = self.dark.get()
        c = self.banner
        w = max(c.winfo_width(), 700)
        c.delete("all")
        c.configure(bg="#174259" if dark else "#c8e9f5")
        c.create_oval(w - 230, -120, w + 85, 195, fill="#215b6b" if dark else "#b5e8dc", outline="")
        c.create_oval(w - 155, -120, w + 140, 125, fill="#236078" if dark else "#c0e7f6", outline="")
        c.create_text(22, 22, text="ROCKBOX → LAST.FM", anchor="w", fill="#a4d6e9" if dark else "#407487", font=("Segoe UI", 9, "bold"))
        c.create_text(22, 54, text="Give your plays a home.", anchor="w", fill="#effaff" if dark else "#123e55", font=("Segoe UI", 25, "bold"))
        c.create_text(22, 83, text="Import, review, and scrobble from your desktop.", anchor="w", fill="#bddfeb" if dark else "#3e687c", font=("Segoe UI", 10))

    def toggle_theme(self):
        if self.busy:
            self.dark.set(self.snapshot["preferences"]["dark_mode"])
            self.status.set("Wait for the current operation to finish before changing appearance.")
            return
        try:
            self.app.dispatch("/api/appearance", {"dark_mode": self.dark.get()})
        except (AppError, OSError) as exc:
            self.dark.set(not self.dark.get())
            self.error(exc)
        self.apply_theme()

    def refresh(self):
        state = self.app.state()
        if state == self.snapshot:
            self.update_controls()
            return
        self.snapshot = state
        state = self.snapshot
        self.rows = {row["id"]: row for row in state["tracks"]}
        self.selected &= {key for key, row in self.rows.items() if row["status"] == "pending"}
        counts = Counter(row["status"] for row in self.rows.values())
        self.total.set(str(len(self.rows)))
        self.ready.set(str(counts["pending"]))
        self.accepted.set(str(counts["accepted"]))
        self.account.set(f"Connected to Last.fm · {state['username']}" if state["username"] else "Last.fm is disconnected")
        self.connect_button.configure(text="Finish connecting" if state["auth_pending"] else "Open profile" if state["username"] else "Connect Last.fm")
        self.render_rows()
        self.update_controls()
        if state["warning"]:
            self.status.set(state["warning"])

    def render_rows(self):
        if not hasattr(self, "tree"):
            return
        focused = self.tree.focus()
        scroll = self.tree.yview()[0]
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        query = self.search.get().strip().casefold()
        for key, row in self.rows.items():
            if query and query not in " ".join(row[field] for field in ("artist", "track", "album")).casefold():
                continue
            status = STATUS[row["status"]]
            if self.filter.get() not in {"All plays", status}:
                continue
            self.tree.insert("", "end", iid=key, values=("☑" if key in self.selected else "☐" if row["status"] == "pending" else "—",
                             row["artist"], row["track"], row["album"], date_label(row["timestamp"]) + (" *" if row["date_adjusted"] else ""), status),
                             tags=() if row["status"] == "pending" else ("muted",))
        if focused and self.tree.exists(focused):
            self.tree.focus(focused)
            self.tree.selection_set(focused)
        self.tree.yview_moveto(scroll)
        self.update_controls()

    def update_controls(self):
        if not self.snapshot:
            return
        locked = self.busy or self.snapshot["job"]["running"]
        self.selection_text.set(f"{len(self.selected)} plays selected  ·  Space or click the checkbox to choose")
        self.submit_button.configure(state="normal" if self.selected and self.snapshot["username"] and not locked else "disabled")
        self.connect_button.configure(state="disabled" if locked else "normal")

    def click_row(self, event):
        if self.tree.identify_column(event.x) == "#1" and self.tree.identify_region(event.x, event.y) == "cell":
            self.toggle(self.tree.identify_row(event.y))

    def toggle_focused(self, _event=None):
        self.toggle(self.tree.focus())
        return "break"

    def toggle(self, key):
        if key in self.rows and self.rows[key]["status"] == "pending" and not self.busy and not self.snapshot["job"]["running"]:
            if key in self.selected:
                self.selected.remove(key)
            else:
                self.selected.add(key)
            self.render_rows()

    def select_ready(self):
        if self.idle():
            self.selected.update(key for key in self.tree.get_children() if self.rows[key]["status"] == "pending")
            self.render_rows()

    def deselect(self):
        if self.idle():
            self.selected.clear()
            self.render_rows()

    def show_detail(self, _event=None):
        key = self.tree.focus()
        if key in self.rows:
            row = self.rows[key]
            self.detail.set(f"{row['filename']} · Original: {date_label(row['original_timestamp'])} · "
                            f"Submission: {date_label(row['timestamp'])}" + (" (adjusted)" if row["date_adjusted"] else "") +
                            f"\n{row['message'] or 'Original Rockbox flag: ' + row['original_rating'] + '. Treated as at least 50% listened.'}")

    def idle(self):
        if self.busy or self.app.job["running"]:
            self.status.set("Wait for the current operation to finish.")
            return False
        return True

    def error(self, exc):
        self.status.set(str(exc))
        messagebox.showerror(APP_NAME, str(exc), parent=self.root)

    def task(self, work, done=None):
        if not self.idle():
            return
        self.busy = True
        self.status.set("Working…")
        self.update_controls()
        def run():
            try:
                self.results.put((True, work(), done))
            except Exception as exc:
                self.results.put((False, str(exc) if isinstance(exc, (AppError, OSError, UnicodeError)) else
                                  "This action could not be completed. Check available disk space and try again.", None))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        if self.closed:
            return
        try:
            ok, value, done = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.refresh()
            if ok:
                self.status.set("Done.")
                if done:
                    done(value)
            else:
                self.error(value)
        if not self.busy:
            # Reading state while auth owns the backend lock would freeze Tk.
            if self.snapshot["job"]["running"] or self.app.job["running"]:
                self.refresh()
                job = self.snapshot["job"]
                self.progress.configure(maximum=max(1, job["total"]), value=job["done"])
                self.status.set(job["message"])
        self.timer = self.root.after(200, self.poll)

    def dialog(self, title):
        window = tk.Toplevel(self.root)
        window.title(title)
        window.configure(bg=THEMES[self.dark.get()]["bg"])
        window.transient(self.root)
        window.geometry("580x520")
        window.minsize(520, 460)
        self.dialogs = [w for w in self.dialogs if w.winfo_exists()]
        self.dialogs.append(window)
        body = ttk.Frame(window, padding=24)
        body.pack(fill="both", expand=True)
        return window, body

    def text_dialog(self, title, text):
        window, body = self.dialog(title)
        ttk.Label(body, text=title, font=("Segoe UI", 19, "bold")).pack(anchor="w", pady=(0, 16))
        c = THEMES[self.dark.get()]
        area = tk.Text(body, wrap="word", bg=c["panel"], fg=c["fg"], insertbackground=c["fg"],
                       font=("Segoe UI", 11), relief="flat", padx=14, pady=14)
        scrollbar = ttk.Scrollbar(body, command=area.yview)
        scrollbar.pack(side="right", fill="y")
        area.configure(yscrollcommand=scrollbar.set)
        area.pack(fill="both", expand=True)
        area.insert("1.0", text)
        area.configure(state="disabled")
        return window

    def settings(self):
        if not self.idle():
            return
        window, body = self.dialog("Settings")
        window.geometry("580x670")
        ttk.Label(body, text="Your preferences.", font=("Segoe UI", 21, "bold")).pack(anchor="w", pady=(0, 18))
        ttk.Checkbutton(body, text="Dark mode", variable=self.dark, command=self.toggle_theme).pack(anchor="w")
        remap = tk.BooleanVar(window, value=self.app.preferences()["remap_outdated"])
        ttk.Checkbutton(body, text="Adjust outdated listening dates", variable=remap).pack(anchor="w", pady=(18, 6))
        ttk.Label(body, text="Older unsent plays will be spread across the last 13 days. Last.fm will show those adjusted dates. Original dates stay on this PC.", wraplength=510, style="Muted.TLabel").pack(anchor="w")
        def save_history():
            value = remap.get()
            self.task(lambda: self.app.dispatch("/api/preferences", {"remap_outdated": value}),
                      lambda result: self.status.set(f"History preferences saved. {result['adjusted']} dates adjusted."))
        ttk.Button(body, text="Save history preferences", command=save_history).pack(anchor="w", pady=(8, 18))
        ttk.Label(body, text="Last.fm account", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Button(body, text="Create a Last.fm API account ↗", command=lambda: webbrowser.open("https://www.last.fm/api/account/create")).pack(anchor="w", pady=(8, 8))
        ttk.Label(body, text="Use your API key and shared secret, not your Last.fm password. Saving new credentials disconnects the current account.", wraplength=510, style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        fields = []
        for label in ["API key", "Shared secret"]:
            ttk.Label(body, text=label).pack(anchor="w")
            entry = ttk.Entry(body, show="•")
            entry.pack(fill="x", pady=(4, 10))
            fields.append(entry)
        remember = tk.BooleanVar(window, value=self.app.remember)
        ttk.Checkbutton(body, text="Remember on this PC (Windows encryption)", variable=remember).pack(anchor="w", pady=(0, 8))
        def save():
            data = {"api_key": fields[0].get(), "secret": fields[1].get(), "remember": remember.get()}
            self.task(lambda: self.app.dispatch("/api/settings", data), lambda _: self.dismiss(window))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="Save credentials", command=save, style="Accent.TButton").pack(side="left")
        ttk.Button(buttons, text="Disconnect", command=lambda: self.task(lambda: self.app.dispatch("/api/disconnect", {}), lambda _: self.dismiss(window))).pack(side="left", padx=10)

    def connect(self):
        if not self.idle():
            return
        if self.snapshot["auth_pending"]:
            self.task(lambda: self.app.dispatch("/api/auth/finish", {}))
        elif self.snapshot["username"]:
            self.open_profile()
        else:
            def authorize(result):
                webbrowser.open(result["url"])
                self.status.set("Approve access on Last.fm, return here, and click Finish connecting.")
            self.task(lambda: self.app.dispatch("/api/auth/start", {}), authorize)

    def open_profile(self):
        from urllib.parse import quote
        if self.snapshot["username"]:
            webbrowser.open("https://www.last.fm/user/" + quote(self.snapshot["username"], safe="") + "/library")

    def import_dialog(self):
        if not self.idle():
            return
        paths = filedialog.askopenfilenames(parent=self.root, title="Import Rockbox .scrobbler.log",
                                           filetypes=[("Rockbox logs", "*.log"), ("All files", "*")])
        if not paths:
            return
        window, body = self.dialog("Import & review")
        window.geometry("580x470")
        ttk.Label(body, text="A note about your clock.", font=("Segoe UI", 20, "bold")).pack(anchor="w", pady=(0, 14))
        ttk.Label(body, text=f"{len(paths)} file(s) selected. Every valid entry is treated as at least 50% listened, including skipped plays. Your source files stay unchanged.", wraplength=510).pack(anchor="w", pady=(0, 15))
        ttk.Label(body, text="Leave correction at zero unless your player clock needs adjusting. For a player that logged UTC−5 local time as UTC, subtract 5 hours.", wraplength=510, style="Muted.TLabel").pack(anchor="w", pady=(0, 15))
        ttk.Label(body, text="Time correction (hours, in 15-minute steps)").pack(anchor="w")
        offset = tk.StringVar(window, value="0")
        ttk.Spinbox(body, from_=-24, to=24, increment=0.25, textvariable=offset, width=12).pack(anchor="w", pady=10)
        def start():
            correction = offset.get()
            def import_files():
                report = []
                for path in paths:
                    try:
                        with open(path, "rb") as file:
                            raw = file.read(MAX_UPLOAD + 1)
                        if len(raw) > MAX_UPLOAD:
                            raise AppError("Choose a UTF-8 log smaller than 8 MB.")
                        result = self.app.dispatch("/api/import", {"content": raw.decode("utf-8-sig"), "filename": Path(path).name, "offset": correction})
                        report.append(f"{Path(path).name}: {result['added']} added, {result['duplicates']} duplicates, {result['excluded']} excluded. {result['outdated']} too old in queue.")
                        report.extend(f"  Line {issue['line']}: {issue['reason']}" for issue in result["issues"])
                    except (AppError, OSError, UnicodeError) as exc:
                        report.append(f"{Path(path).name}: {exc}")
                return "\n".join(report)
            window.destroy()
            self.task(import_files, lambda report: self.text_dialog("Import results", report))
        ttk.Button(body, text="Import & review", command=start, style="Accent.TButton").pack(anchor="w", pady=18)

    def submit(self):
        if not self.idle():
            return
        self.refresh()
        rows = [self.rows[key] for key in self.selected]
        if not rows:
            return
        account = self.snapshot["username"]
        adjusted = sum(row["date_adjusted"] for row in rows)
        dates = sorted(row["timestamp"] for row in rows)
        if messagebox.askyesno("Review your submission", f"Send {len(rows)} plays to Last.fm account {account}?\n\n"
                              f"Listening dates: {date_label(dates[0])} through {date_label(dates[-1])}.\n"
                              f"{adjusted} plays use adjusted dates; Last.fm will display those dates.", parent=self.root):
            data = {"ids": [row["id"] for row in rows], "account": account, "confirmed": True,
                    "timestamps": {row["id"]: row["timestamp"] for row in rows}}
            self.task(lambda: self.app.dispatch("/api/submit", data))

    def resolve(self):
        if not self.idle():
            return
        key = self.tree.focus()
        if key not in self.rows or self.rows[key]["status"] != "uncertain":
            self.status.set("Highlight a play marked Check outcome first.")
            return
        row, account = self.rows[key], self.snapshot["username"]
        if not account:
            self.error("Connect your Last.fm account first.")
            return
        window, body = self.dialog("Check this play's outcome")
        window.geometry("580x470")
        ttk.Label(body, text=f"{row['artist']} — {row['track']}\n{date_label(row['timestamp'])}", wraplength=510, font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(0, 18))
        ttk.Label(body, text=f"This play may already be on {account}'s Last.fm profile. Check the listening history before marking it received or allowing a retry. Retrying an accepted play can duplicate it.", wraplength=510).pack(anchor="w", pady=(0, 14))
        ttk.Button(body, text="Open listening history ↗", command=self.open_profile).pack(anchor="w")
        checked = tk.BooleanVar(window)
        buttons = []
        def enable():
            for button in buttons:
                button.configure(state="normal" if checked.get() else "disabled")
        ttk.Checkbutton(body, text="I checked this account's listening history", variable=checked, command=enable).pack(anchor="w", pady=18)
        def finish(action):
            if not checked.get():
                return
            data = {"ids": [key], "account": account, "action": action, "confirmed": True}
            self.task(lambda: self.app.dispatch("/api/resolve", data), lambda _: self.dismiss(window))
        for title, action in [("Already received", "accepted"), ("Missing — allow retry", "retry")]:
            button = ttk.Button(body, text=title, state="disabled", command=lambda a=action: finish(a))
            button.pack(side="left", padx=(0, 10))
            buttons.append(button)

    def clear(self):
        if self.idle() and messagebox.askyesno("Clear queue", "Remove imported plays from this PC's queue? Submission receipts remain for duplicate protection. Your source logs stay unchanged.", parent=self.root):
            self.task(lambda: self.app.dispatch("/api/clear", {}))
            self.detail.set("Select a play to see its source and listening dates.")

    @staticmethod
    def dismiss(window):
        if window.winfo_exists():
            window.destroy()

    def guide(self):
        self.text_dialog("User guide", "1. In Rockbox, enable playback logging and run Plugins → Applications → lastfm_scrobbler. Import the exported .scrobbler.log; playback.log is a different format.\n\n"
                         "2. In Settings, create a Last.fm API account and save its key and shared secret. Connect Last.fm, approve access in your browser, then click Finish connecting.\n\n"
                         "3. Import a log. Correct the player's clock only if needed. Review each play's listening date, artist and title. Click its checkbox or press Space to select. Select ready selects eligible plays in the current search/filter.\n\n"
                         "4. Scrobble selected shows the destination account and date range before sending. Plays older than 14 days are held back unless you enable date adjustment in Settings. Adjusted dates have an asterisk; original dates appear below the table.\n\n"
                         "Interrupted replies become Check outcome. Check your profile and explicitly mark them received or allow a retry. The app never automatically retries uncertain plays.\n\n"
                         "Close the app window to quit. During an operation, wait for it to finish before closing.")

    def privacy(self):
        self.text_dialog("Privacy & storage", "The interface is native and does not start a local server. Only Last.fm API operations use the network, over verified HTTPS. External links open in your browser.\n\n"
                         "Importing never submits plays or edits source logs. Selected song metadata is sent only after your confirmation. There is no telemetry.\n\n"
                         "Credentials stay in memory by default. Remember on this PC encrypts them using Windows DPAPI for your Windows user. Software running as that user may still access them.\n\n"
                         f"The unencrypted queue, receipts, and appearance preferences are stored here:\n{self.app.data_dir}\n\n"
                         "Clear queue preserves submission fingerprints. Uninstall preserves this folder. To remove all data, close the app and delete this folder; doing so loses duplicate protection.\n\n"
                         "Disconnect deletes saved credentials. To revoke access on Last.fm too, remove this app from Last.fm's application settings.")

    def about(self):
        self.text_dialog("About", f"{APP_NAME}\nVersion {VERSION}\n\nProduct of Achilleus\nhttps://github.com/Achilleus-1/Akis-Rockbox-Scrobbler\n\n"
                         "Native desktop software built with Python and Tcl/Tk. Windows releases include a private runtime; no Python installation or FFmpeg is needed.\n\n"
                         "Original source: MIT license. Dependency licenses and notices are included in the release's licenses folder. Independent of Rockbox and Last.fm.")

    def close(self):
        if not self.idle():
            messagebox.showinfo(APP_NAME, "An operation is still running. Wait for it to finish before closing the app.", parent=self.root)
            return
        self.closed = True
        self.root.after_cancel(self.timer)
        self.root.destroy()


def smoke_test(report):
    """Verify the bundled GUI, parser, SQLite and theme in isolated storage, offline."""
    with tempfile.TemporaryDirectory(prefix="rockbox-smoke-") as directory:
        app = App(directory)
        root = None
        try:
            root = tk.Tk()
            ui = Desktop(root, app)
            import time
            content = f"Test Artist\tTest Album\tTest Track\t1\t240\tL\t{int(time.time())-3600}"
            app.dispatch("/api/import", {"content": content, "filename": "synthetic.log"})
            ui.refresh()
            ui.select_ready()
            assert len(ui.selected) == 1
            for dark in (True, False):
                ui.dark.set(dark)
                ui.toggle_theme()
                root.update()
                assert app.preferences()["dark_mode"] == dark
            assert not app.job["running"]
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps({"ok": True, "version": VERSION, "native_gui": "Tk", "imported": len(ui.rows), "themes": ["dark", "light"], "frozen": bool(getattr(sys, "frozen", False))}), encoding="utf-8")
        finally:
            if root:
                root.destroy()
            app.db.close()


def main():
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share"))) / "RockboxRelay")
    parser.add_argument("--smoke-test", type=Path, metavar="REPORT_JSON", help="Check native GUI offline using temporary data")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args()
    if args.smoke_test:
        try:
            smoke_test(args.smoke_test)
        except Exception:
            import traceback
            args.smoke_test.parent.mkdir(parents=True, exist_ok=True)
            args.smoke_test.write_text(json.dumps({"ok": False, "error": traceback.format_exc()}), encoding="utf-8")
            raise SystemExit(1)
        return
    root = tk.Tk()
    root.withdraw()
    instance = app = None
    try:
        args.data_dir.mkdir(parents=True, exist_ok=True)
        instance = acquire_instance_lock(args.data_dir)
        if instance is None:
            messagebox.showinfo(APP_NAME, "The app is already running. Switch to its existing window.", parent=root)
            return
        app = App(args.data_dir)
        Desktop(root, app)
        root.deiconify()
        root.mainloop()
    except (AppError, OSError) as exc:
        messagebox.showerror(APP_NAME, str(exc), parent=root)
    finally:
        if app:
            app.db.close()
        if instance:
            instance.close()
        try:
            root.destroy()
        except tk.TclError:
            pass


if __name__ == "__main__":
    main()
