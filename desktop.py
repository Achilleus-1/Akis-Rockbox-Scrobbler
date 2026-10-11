"""Native Qt interface, with network work kept off the GUI thread."""
from __future__ import annotations
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
import webbrowser
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
    QFileDialog, QHeaderView, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QTextBrowser,
    QVBoxLayout, QWidget)
from glass import AeroBackdrop, GlassPanel, PocketPlayer
from scrobbler import App, AppError, MAX_UPLOAD, acquire_instance_lock
from version import APP_NAME, VERSION

ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "assets"
STATUS = {"pending": "Ready", "expired": "Too old", "accepted": "Accepted",
          "uncertain": "Check outcome", "sending": "Sending", "ignored": "Ignored"}

def date_label(timestamp):
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")

def label(text, kind="", wrap=False):
    widget = QLabel(text)
    widget.setProperty("kind", kind)
    widget.setWordWrap(wrap)
    return widget

def button(text, action, kind=""):
    widget = QPushButton(text)
    widget.setProperty("kind", kind)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.clicked.connect(action)
    return widget

def column(widget, margin=22, spacing=10):
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(margin, margin, margin, margin)
    layout.setSpacing(spacing)
    return layout

class Desktop(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.rows, self.selected = {}, set()
        self.snapshot = None
        self.busy = self.closed = self.sample = False
        self.results = queue.Queue()
        self.dialogs = []
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(ASSETS / "app.ico")))
        self.resize(1440, 1000)
        self.setMinimumSize(1000, 760)
        self.scene = AeroBackdrop()
        self.setCentralWidget(self.scene)
        self._build()
        self.scene.setMouseTracking(True)
        for child in self.findChildren(QWidget):
            child.setMouseTracking(True)
        prefs = app.preferences()
        self.dark.setChecked(prefs["dark_mode"])
        self.live.setChecked(prefs["live_glass"])
        self.apply_theme()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    def _build(self):
        outer = QHBoxLayout(self.scene)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(18)
        sidebar = GlassPanel(self.scene, material=1, radius=28)
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(224)
        outer.addWidget(sidebar)
        side = column(sidebar, 22, 10)
        logo = label("")
        logo.setPixmap(QPixmap(str(ASSETS / "branding/achilleus-white-small.png")).scaled(76, 76,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        side.addWidget(logo)
        side.addWidget(label("ACHILLEUS", "wordmark"))
        side.addSpacing(10)
        side.addWidget(label("Aki's Rockbox\nScrobbler", "brand"))
        side.addWidget(label("YOUR MUSIC DESK", "eyebrow"))
        side.addSpacing(22)
        side.addWidget(button("♫  Your queue", lambda: self.scroll.verticalScrollBar().setValue(0), "nav"))
        side.addWidget(button("How it works", self.guide, "nav"))
        side.addWidget(button("Privacy & storage", self.privacy, "nav"))
        side.addStretch()
        side.addWidget(label("●  RUNNING ON YOUR PC", "eyebrow"))
        side.addWidget(label("Your music has a story.\nKeep the record.", "sidequote", True))
        side.addSpacing(18)
        self.dark, self.live = QCheckBox("Dark mode"), QCheckBox("Live liquid glass")
        self.dark.clicked.connect(self.toggle_appearance)
        self.live.clicked.connect(self.toggle_appearance)
        side.addWidget(self.dark)
        side.addWidget(self.live)
        side.addWidget(button("Settings", self.settings, "nav"))
        side.addWidget(button("About · Product of Achilleus", self.about, "smallnav"))
        side.addWidget(label(f"v{VERSION} · Native desktop", "fine"))
        right = QWidget()
        right_layout = column(right, 0, 14)
        outer.addWidget(right, 1)
        top = GlassPanel(self.scene, radius=22)
        top_row = QHBoxLayout(top)
        top_row.setContentsMargins(22, 14, 22, 14)
        top_row.addWidget(label("♫  YOUR MUSIC DESK   /   Your queue", "eyebrow"))
        top_row.addStretch()
        self.account = label("Last.fm is disconnected", "account")
        top_row.addWidget(self.account)
        right_layout.addWidget(top)
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().setAutoFillBackground(False)
        self.scroll.verticalScrollBar().valueChanged.connect(lambda _: self.scene.tick())
        right_layout.addWidget(self.scroll, 1)
        body = QWidget()
        body.setObjectName("content")
        layout = column(body, 0, 14)
        self.scroll.setWidget(body)
        hero = GlassPanel(self.scene, radius=28)
        hero_row = QHBoxLayout(hero)
        hero_row.setContentsMargins(28, 18, 24, 18)
        words = QVBoxLayout()
        for text, kind in [("YOUR PLAYER. YOUR PLAYS. YOUR PROFILE.", "eyebrow"),
                           ("Offline plays.\nOnline memories.", "hero"),
                           ("Your favorite pocket player, meet your music history.\nBring every listen from Rockbox to Last.fm.", "subtitle"),
                           ("Made by Achilleus   ·   Built to stay local", "fine")]:
            words.addWidget(label(text, kind, kind == "subtitle"))
        hero_row.addLayout(words, 1)
        art = QVBoxLayout()
        art.addWidget(PocketPlayer())
        caption = label("GOOD MUSIC GOES WITH YOU", "eyebrow")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        art.addWidget(caption)
        hero_row.addLayout(art)
        layout.addWidget(hero)
        steps = QHBoxLayout()
        for number, title, hint in [(1, "Import your log", "Bring your offline listens"), (2, "Connect Last.fm", "Give your music a home"), (3, "Review & scrobble", "You choose what gets sent")]:
            step = GlassPanel(self.scene, radius=18)
            row = QHBoxLayout(step)
            row.setContentsMargins(16, 12, 16, 12)
            numeral = label(str(number), "step")
            numeral.setFixedWidth(32)
            row.addWidget(numeral)
            copy = QVBoxLayout()
            copy.setSpacing(2)
            copy.addWidget(label(title, "heading"))
            copy.addWidget(label(hint, "fine"))
            row.addLayout(copy)
            steps.addWidget(step, 1)
        layout.addLayout(steps)
        cards = QHBoxLayout()
        cards.setSpacing(14)
        upload = GlassPanel(self.scene)
        upl = column(upload, 22, 7)
        upl.addWidget(label("↑  ROCKBOX → YOUR QUEUE", "eyebrow"))
        upl.addWidget(label("Drop your listening log here.", "cardtitle"))
        upl.addWidget(label("Choose the .scrobbler.log exported by your player.\nReview your listens before anything leaves your PC.", "muted", True))
        controls = QHBoxLayout()
        controls.addWidget(button("Choose log file", lambda: self.import_dialog(), "primary"))
        controls.addWidget(button("Try a sample", self.show_sample, "quiet"))
        controls.addStretch()
        upl.addLayout(controls)
        upload.setAcceptDrops(True)
        upload.dragEnterEvent = self.drag_enter
        upload.dropEvent = self.drop_log
        cards.addWidget(upload, 3)
        account_card = GlassPanel(self.scene, material=2)
        account_card.setObjectName("accountCard")
        acc = column(account_card, 22, 7)
        self.connection_badge = label("LAST.FM · NOT CONNECTED", "eyebrow")
        acc.addWidget(self.connection_badge)
        acc.addWidget(label("A home for every listen.", "cardtitle"))
        acc.addWidget(label("Connect securely through Last.fm.\nYour password stays with Last.fm.", "muted", True))
        self.connect_button = button("Connect Last.fm", self.connect, "glassbutton")
        acc.addWidget(self.connect_button)
        cards.addWidget(account_card, 2)
        layout.addLayout(cards)
        strip = label("◈  LOCAL BY DESIGN   ·   Your logs stay untouched. You decide what gets sent.", "fine")
        strip.setContentsMargins(14, 2, 0, 2)
        layout.addWidget(strip)
        queue_panel = GlassPanel(self.scene)
        q = column(queue_panel, 22, 10)
        heading = QHBoxLayout()
        heading.addWidget(label("Your listening queue", "cardtitle"))
        heading.addStretch()
        self.total = label("0 plays", "fine")
        heading.addWidget(self.total)
        q.addLayout(heading)
        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search artist, title, or album…")
        self.search.textChanged.connect(self.render_rows)
        filters.addWidget(self.search, 1)
        self.filter = QComboBox()
        self.filter.addItems(["All plays", *STATUS.values()])
        self.filter.currentTextChanged.connect(self.render_rows)
        filters.addWidget(self.filter)
        filters.addWidget(button("Select ready", self.select_ready, "quiet"))
        filters.addWidget(button("Deselect", self.deselect, "quiet"))
        q.addLayout(filters)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["", "Track / artist", "Album", "Listening date", "Status", "Source"])
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(240)
        self.table.setMaximumHeight(330)
        header = self.table.horizontalHeader()
        for col in (1, 2, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        for col, width in [(0, 32), (3, 155), (4, 115)]:
            self.table.setColumnWidth(col, width)
        self.table.itemChanged.connect(self.check_row)
        self.table.itemSelectionChanged.connect(self.show_detail)
        self.select_shortcut = QShortcut(QKeySequence("Space"), self.table)
        self.select_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.select_shortcut.activated.connect(self.toggle_focused)
        q.addWidget(self.table)
        self.detail = label("Select a play to see its original date and source.", "fine", True)
        q.addWidget(self.detail)
        actions = QHBoxLayout()
        self.selection_text = label("0 plays selected", "muted")
        actions.addWidget(self.selection_text)
        actions.addStretch()
        actions.addWidget(button("Check outcome", self.resolve, "quiet"))
        actions.addWidget(button("Clear queue", self.clear, "quiet"))
        self.submit_button = button("Scrobble selected →", self.submit, "primary")
        actions.addWidget(self.submit_button)
        q.addLayout(actions)
        layout.addWidget(queue_panel)
        self.progress = QProgressBar()
        self.progress.setMaximumHeight(5)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = label("Choose a Rockbox log to get started.", "fine", True)
        layout.addWidget(self.status)

    def apply_theme(self):
        dark = self.dark.isChecked()
        fg, muted = ("#e8f4fb", "#b0c9d8") if dark else ("#163e53", "#527489")
        field, edge = ("rgba(12,29,47,225)", "#456177") if dark else ("rgba(255,255,255,220)", "#bed7e1")
        hover = "#215875" if dark else "#e3f7ff"
        self.setStyleSheet(f'''
          QWidget {{ font-family: 'Segoe UI'; font-size: 13px; color: {fg}; }}
          QMainWindow, QScrollArea, QScrollArea > QWidget > QWidget, QWidget#content {{ background: transparent; }}
          QLabel {{ background: transparent; border: none; }}
          QLabel[kind="hero"] {{ font-size: 40px; font-weight: 700; letter-spacing: -1px; }}
          QLabel[kind="brand"] {{ font-size: 23px; font-weight: 700; }}
          QLabel[kind="wordmark"] {{ font-size: 15px; letter-spacing: 3px; font-weight: 600; }}
          QLabel[kind="cardtitle"] {{ font-size: 22px; font-weight: 650; }}
          QLabel[kind="heading"] {{ font-size: 14px; font-weight: 650; }}
          QLabel[kind="subtitle"] {{ font-size: 15px; color: {muted}; }}
          QLabel[kind="muted"], QLabel[kind="fine"] {{ color: {muted}; }}
          QLabel[kind="fine"] {{ font-size: 11px; }}
          QLabel[kind="eyebrow"] {{ font-size: 10px; font-weight: 700; letter-spacing: 1px; color: {muted}; }}
          QLabel[kind="step"] {{ font-size: 22px; font-weight: 700; color: {'#8ce2ec' if dark else '#138eb2'}; padding-right: 9px; }}
          QLabel[kind="account"] {{ border: 1px solid {edge}; border-radius: 14px; padding: 7px 13px; color: {muted}; }}
          QCheckBox {{ spacing: 8px; background: transparent; }}
          QCheckBox::indicator {{ width: 17px; height: 17px; border: 1px solid {edge}; border-radius: 5px; background: {field}; }}
          QCheckBox::indicator:checked {{ background: #23a7cb; border-color: #93e7f7; }}
          QPushButton {{ padding: 9px 15px; border: 1px solid {edge}; border-radius: 15px; background: {field}; font-weight: 600; }}
          QPushButton:hover {{ background: {hover}; border-color: #71c6df; }}
          QPushButton:pressed {{ padding-top: 10px; padding-bottom: 8px; }}
          QPushButton:disabled {{ color: {muted}; background: {'#1d3648' if dark else '#deedf2'}; border-color: {edge}; }}
          QPushButton[kind="primary"] {{ color: white; border-color: #82d5e8; background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #60cbe2,stop:.48 #189fca,stop:.52 #078bb6,stop:1 #077397); }}
          QPushButton[kind="primary"]:hover {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #8fe8ef,stop:.5 #23afd2,stop:1 #0983aa); }}
          QPushButton[kind="primary"]:disabled {{ color: {muted}; background: {'#274455' if dark else '#c5dfe7'}; }}
          QPushButton[kind="quiet"] {{ background: transparent; border-color: transparent; }}
          QPushButton[kind="quiet"]:hover {{ background: {hover}; border-color: {edge}; }}
          QLineEdit, QComboBox, QDoubleSpinBox {{ border: 1px solid {edge}; border-radius: 12px; padding: 8px 12px; background: {field}; selection-background-color: #2394ba; }}
          QComboBox QAbstractItemView {{ background: {'#182e43' if dark else '#f5fcff'}; color: {fg}; }}
          QTableWidget {{ border: 1px solid {edge}; border-radius: 14px; background: {field}; alternate-background-color: {'#193145' if dark else '#edf8fb'}; selection-background-color: {'#275672' if dark else '#cfedf7'}; selection-color: {fg}; }}
          QTableWidget::item {{ padding: 5px; border-bottom: 1px solid {'#243e51' if dark else '#deedf2'}; }}
          QHeaderView::section {{ background: {'#203a4d' if dark else '#e8f5f9'}; color: {muted}; padding: 10px 5px; border: none; font-size: 11px; font-weight: 600; }}
          QScrollBar:vertical {{ width: 8px; background: transparent; margin: 0; }}
          QScrollBar::handle:vertical {{ background: {'#43687c' if dark else '#8fbccf'}; border-radius: 4px; min-height: 30px; }}
          QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
          QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
          QProgressBar {{ border: none; background: {field}; border-radius: 2px; }}
          QProgressBar::chunk {{ background: #159fc3; border-radius: 2px; }}
          QDialog {{ background: {'#172c3d' if dark else '#eaf6fa'}; }}
          QTextBrowser {{ background: {field}; border: 1px solid {edge}; border-radius: 12px; padding: 12px; }}
          QWidget#sidebar QLabel, QWidget#accountCard QLabel, QWidget#sidebar QCheckBox {{ color: #e8f8ff; }}
          QWidget#sidebar QLabel[kind="fine"], QWidget#sidebar QLabel[kind="eyebrow"], QWidget#accountCard QLabel[kind="muted"], QWidget#accountCard QLabel[kind="eyebrow"] {{ color: #b6e3f0; }}
          QWidget#sidebar QLabel[kind="sidequote"] {{ font-size: 17px; font-weight: 600; }}
          QWidget#sidebar QPushButton, QPushButton[kind="glassbutton"] {{ color: #effaff; border-color: rgba(215,245,255,90); background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(190,237,255,55),stop:.5 rgba(117,191,219,20),stop:1 rgba(14,68,101,80)); }}
          QWidget#sidebar QPushButton[kind="nav"] {{ text-align: left; padding: 11px 12px; }}
          QWidget#sidebar QPushButton[kind="smallnav"] {{ font-size: 10px; padding: 8px 3px; border: none; background: transparent; }}
          QWidget#sidebar QPushButton:hover, QPushButton[kind="glassbutton"]:hover {{ background: rgba(166,227,250,65); }}
        ''')
        self.scene.set_appearance(dark, self.live.isChecked())
        for panel in self.scene.panels:
            panel.update()
        self.live.setToolTip("Animated refraction, pointer reflections, and click ripples." if self.scene.renderer.available else "OpenGL is unavailable. The still Aero background remains active.")

    def toggle_appearance(self):
        if not self.idle():
            prefs = self.snapshot["preferences"]
            self.dark.setChecked(prefs["dark_mode"])
            self.live.setChecked(prefs["live_glass"])
            return
        try:
            self.app.dispatch("/api/appearance", {"dark_mode": self.dark.isChecked(), "live_glass": self.live.isChecked()})
            self.apply_theme()
            self.refresh()
        except (AppError, OSError) as exc:
            prefs = self.app.preferences()
            self.dark.setChecked(prefs["dark_mode"])
            self.live.setChecked(prefs["live_glass"])
            self.error(exc)

    def refresh(self):
        self.snapshot = self.app.state()
        state = self.snapshot
        if not self.sample:
            self.rows = {row["id"]: row for row in state["tracks"]}
        self.selected &= {key for key, row in self.rows.items() if row["status"] == "pending"}
        self.account.setText(f"Last.fm · {state['username']}" if state["username"] else "Last.fm is disconnected")
        self.connection_badge.setText("LAST.FM · CONNECTED" if state["username"] else "LAST.FM · NOT CONNECTED")
        self.connect_button.setText("Finish connecting" if state["auth_pending"] else "Open profile" if state["username"] else "Connect Last.fm")
        self.total.setText(f"{len(self.rows)} plays · {sum(r['status']=='pending' for r in self.rows.values())} ready" + (" · SAMPLE" if self.sample else ""))
        self.render_rows()
        if state["warning"]:
            self.status.setText(state["warning"])

    def visible_rows(self):
        query = self.search.text().strip().casefold()
        choice = self.filter.currentText()
        return [(key, row) for key, row in self.rows.items()
                if (not query or query in " ".join(row[field] for field in ("artist", "track", "album")).casefold())
                and choice in {"All plays", STATUS[row["status"]]}]

    def render_rows(self, *_):
        if not hasattr(self, "table"):
            return
        self.table.blockSignals(True)
        visible = self.visible_rows()
        self.table.setRowCount(len(visible))
        for index, (key, row) in enumerate(visible):
            checkbox = QTableWidgetItem()
            checkbox.setData(Qt.ItemDataRole.UserRole, key)
            checkbox.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable |
                (Qt.ItemFlag.ItemIsUserCheckable if row["status"] == "pending" else Qt.ItemFlag.NoItemFlags))
            if row["status"] == "pending":
                checkbox.setCheckState(Qt.CheckState.Checked if key in self.selected else Qt.CheckState.Unchecked)
            self.table.setItem(index, 0, checkbox)
            values = [f"{row['track']}\n{row['artist']}", row["album"], date_label(row["timestamp"]) + (" *" if row["date_adjusted"] else ""), STATUS[row["status"]], row["filename"]]
            for col, value in enumerate(values, 1):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(index, col, item)
            self.table.setRowHeight(index, 51)
        self.table.blockSignals(False)
        self.update_controls()

    def update_controls(self):
        if not self.snapshot:
            return
        locked = self.busy or self.snapshot["job"]["running"]
        self.selection_text.setText(f"{len(self.selected)} plays selected")
        self.submit_button.setEnabled(bool(self.selected and self.snapshot["username"] and not locked and not self.sample))
        self.connect_button.setEnabled(not locked)
        self.table.setEnabled(not locked)

    def check_row(self, item):
        if item.column() != 0 or not self.idle():
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if self.rows[key]["status"] == "pending":
            if item.checkState() == Qt.CheckState.Checked:
                self.selected.add(key)
            else:
                self.selected.discard(key)
        self.update_controls()

    def select_ready(self):
        if self.idle():
            self.selected.update(key for key, row in self.visible_rows() if row["status"] == "pending")
            self.render_rows()

    def deselect(self):
        if self.idle():
            self.selected.clear()
            self.render_rows()

    def focused_key(self):
        item = self.table.item(self.table.currentRow(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def toggle_focused(self):
        key = self.focused_key()
        if self.idle() and key in self.rows and self.rows[key]["status"] == "pending":
            item = self.table.item(self.table.currentRow(), 0)
            item.setCheckState(Qt.CheckState.Unchecked if key in self.selected else Qt.CheckState.Checked)

    def show_detail(self):
        key = self.focused_key()
        if key in self.rows:
            row = self.rows[key]
            self.detail.setText(f"{row['filename']} · Original: {date_label(row['original_timestamp'])} · Submission: {date_label(row['timestamp'])}" + (" (adjusted)" if row["date_adjusted"] else "") + f"\n{row['message'] or 'Rockbox flag: ' + row['original_rating'] + '. Treated as at least 50% listened.'}")

    def idle(self):
        if self.busy or self.app.job["running"]:
            self.status.setText("Wait for the current operation to finish.")
            return False
        return True

    def error(self, exc):
        self.status.setText(str(exc))
        QMessageBox.critical(self, APP_NAME, str(exc))

    def confirm(self, title, text):
        return QMessageBox.question(self, title, text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def task(self, work, done=None):
        if not self.idle():
            return
        self.busy = True
        self.status.setText("Working…")
        self.update_controls()
        def run():
            try:
                self.results.put((True, work(), done))
            except Exception as exc:
                self.results.put((False, str(exc) if isinstance(exc, (AppError, OSError, UnicodeError)) else "This action could not be completed. Check available disk space and try again.", None))
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
                self.status.setText("Done.")
                if done:
                    done(value)
            else:
                self.error(value)
        if not self.busy and (self.snapshot["job"]["running"] or self.app.job["running"]):
            self.refresh()
            job = self.snapshot["job"]
            self.progress.setVisible(job["running"])
            self.progress.setMaximum(max(1, job["total"]))
            self.progress.setValue(job["done"])
            self.status.setText(job["message"])

    def dialog(self, title):
        window = QDialog(self)
        window.setWindowTitle(title)
        window.resize(580, 520)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.dialogs.append(window)
        window.destroyed.connect(lambda: self.dialogs.remove(window) if window in self.dialogs else None)
        body = column(window, 24, 12)
        body.addWidget(label(title, "cardtitle"))
        return window, body

    def text_dialog(self, title, text):
        window, body = self.dialog(title)
        area = QTextBrowser()
        area.setPlainText(text)
        body.addWidget(area, 1)
        body.addWidget(button("Close", window.close))
        window.show()
        return window

    def settings(self):
        if not self.idle():
            return
        window, body = self.dialog("Your preferences.")
        body.addWidget(label("Dark mode and live liquid glass are available in the sidebar. Animation respects Windows reduced motion and pauses when the app is inactive.", "muted", True))
        remap = QCheckBox("Adjust outdated listening dates")
        remap.setChecked(self.app.preferences()["remap_outdated"])
        body.addWidget(remap)
        body.addWidget(label("Older unsent plays will be spread across the last 13 days. Last.fm will show those adjusted dates. Original dates stay on this PC.", "muted", True))
        def save_history():
            value = remap.isChecked()
            self.task(lambda: self.app.dispatch("/api/preferences", {"remap_outdated": value}), lambda result: self.status.setText(f"History preferences saved. {result['adjusted']} dates adjusted."))
        body.addWidget(button("Save history preferences", save_history))
        body.addWidget(label("Last.fm account", "heading"))
        body.addWidget(button("Create a Last.fm API account ↗", lambda: webbrowser.open("https://www.last.fm/api/account/create")))
        body.addWidget(label("Use your API key and shared secret, not your Last.fm password. Saving new credentials disconnects the current account.", "muted", True))
        fields = []
        for name in ("API key", "Shared secret"):
            entry = QLineEdit()
            entry.setPlaceholderText(name)
            entry.setEchoMode(QLineEdit.EchoMode.Password)
            body.addWidget(entry)
            fields.append(entry)
        remember = QCheckBox("Remember on this PC (Windows encryption)")
        remember.setChecked(self.app.remember)
        body.addWidget(remember)
        def save():
            data = {"api_key": fields[0].text(), "secret": fields[1].text(), "remember": remember.isChecked()}
            self.task(lambda: self.app.dispatch("/api/settings", data), lambda _: self.dismiss(window))
        row = QHBoxLayout()
        row.addWidget(button("Save credentials", save, "primary"))
        row.addWidget(button("Disconnect", lambda: self.task(lambda: self.app.dispatch("/api/disconnect", {}), lambda _: self.dismiss(window))))
        body.addLayout(row)
        window.show()

    def connect(self):
        if not self.idle():
            return
        if self.snapshot["auth_pending"]:
            self.task(lambda: self.app.dispatch("/api/auth/finish", {}))
        elif self.snapshot["username"]:
            self.open_profile()
        elif not self.snapshot["configured"]:
            self.settings()
        else:
            def authorize(result):
                webbrowser.open(result["url"])
                self.status.setText("Approve access on Last.fm, return here, and click Finish connecting.")
            self.task(lambda: self.app.dispatch("/api/auth/start", {}), authorize)

    def open_profile(self):
        from urllib.parse import quote
        if self.snapshot["username"]:
            webbrowser.open("https://www.last.fm/user/" + quote(self.snapshot["username"], safe="") + "/library")

    def drag_enter(self, event):
        if event.mimeData().hasUrls() and all(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def drop_log(self, event):
        self.import_dialog([url.toLocalFile() for url in event.mimeData().urls()])
        event.acceptProposedAction()

    def import_dialog(self, paths=None):
        if not self.idle():
            return
        if not paths:
            paths, _ = QFileDialog.getOpenFileNames(self, "Import Rockbox .scrobbler.log", "", "Rockbox logs (*.log);;All files (*)")
        if not paths:
            return
        window, body = self.dialog("A note about your clock.")
        body.addWidget(label(f"{len(paths)} file(s) selected. Every valid entry is treated as at least 50% listened, including skipped plays. Your source files stay unchanged.", wrap=True))
        body.addWidget(label("Leave correction at zero unless your player clock needs adjusting. For a player that logged UTC−5 local time as UTC, subtract 5 hours.", "muted", True))
        body.addWidget(label("Time correction (hours, in 15-minute steps)"))
        offset = QDoubleSpinBox()
        offset.setRange(-24, 24)
        offset.setSingleStep(.25)
        offset.setDecimals(2)
        body.addWidget(offset)
        def start():
            correction = offset.value()
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
            self.sample = False
            self.selected.clear()
            window.close()
            self.task(import_files, lambda report: self.text_dialog("Import results", report))
        body.addStretch()
        body.addWidget(button("Import & review", start, "primary"))
        window.show()

    def show_sample(self):
        if not self.idle():
            return
        if self.sample:
            self.sample = False
            self.selected.clear()
            self.refresh()
            self.status.setText("Your saved queue is back.")
            return
        self.sample = True
        self.selected.clear()
        songs = [("Björk", "Homogenic", "Jóga"), ("Daft Punk", "Discovery", "Digital Love"), ("Aphex Twin", "Selected Ambient Works 85–92", "Xtal"), ("Massive Attack", "Mezzanine", "Teardrop")]
        now = int(time.time()) - 3600
        self.rows = {f"sample-{i}": dict(id=f"sample-{i}", artist=artist, album=album, track=title, timestamp=now-i*300, original_timestamp=now-i*300, date_adjusted=False, status="pending", filename="Sample preview", message="Preview only. Nothing is saved or submitted.", original_rating="L") for i, (artist, album, title) in enumerate(songs)}
        self.refresh()
        self.status.setText("Sample preview · nothing is saved or submitted. Click Try a sample again to return to your queue.")

    def submit(self):
        if not self.idle() or self.sample:
            return
        self.refresh()
        rows = [self.rows[key] for key in self.selected]
        account = self.snapshot["username"]
        if not rows or not account:
            return
        dates = sorted(row["timestamp"] for row in rows)
        if self.confirm("Review your submission", f"Send {len(rows)} plays to Last.fm account {account}?\n\nListening dates: {date_label(dates[0])} through {date_label(dates[-1])}.\n{sum(row['date_adjusted'] for row in rows)} plays use adjusted dates; Last.fm will display those dates."):
            data = {"ids": [row["id"] for row in rows], "account": account, "confirmed": True, "timestamps": {row["id"]: row["timestamp"] for row in rows}}
            self.task(lambda: self.app.dispatch("/api/submit", data))

    def resolve(self):
        if not self.idle() or self.sample:
            return
        key = self.focused_key()
        if key not in self.rows or self.rows[key]["status"] != "uncertain":
            self.status.setText("Highlight a play marked Check outcome first.")
            return
        row, account = self.rows[key], self.snapshot["username"]
        if not account:
            self.error("Connect your Last.fm account first.")
            return
        window, body = self.dialog("Check this play's outcome")
        body.addWidget(label(f"{row['artist']} — {row['track']}\n{date_label(row['timestamp'])}", "heading", True))
        body.addWidget(label(f"This play may already be on {account}'s Last.fm profile. Check the listening history before marking it received or allowing a retry. Retrying an accepted play can duplicate it.", wrap=True))
        body.addWidget(button("Open listening history ↗", self.open_profile))
        checked = QCheckBox("I checked this account's listening history")
        body.addWidget(checked)
        def finish(action):
            if checked.isChecked():
                data = {"ids": [key], "account": account, "action": action, "confirmed": True}
                self.task(lambda: self.app.dispatch("/api/resolve", data), lambda _: self.dismiss(window))
        for title, action in [("Already received", "accepted"), ("Missing — allow retry", "retry")]:
            btn = button(title, lambda _checked=False, a=action: finish(a))
            btn.setEnabled(False)
            checked.toggled.connect(btn.setEnabled)
            body.addWidget(btn)
        window.show()

    def clear(self):
        if self.idle() and not self.sample and self.confirm("Clear queue", "Remove imported plays from this PC's queue? Submission receipts remain for duplicate protection. Your source logs stay unchanged."):
            self.task(lambda: self.app.dispatch("/api/clear", {}))
            self.detail.setText("Select a play to see its original date and source.")

    @staticmethod
    def dismiss(window):
        from shiboken6 import isValid
        if isValid(window):
            window.close()

    def guide(self):
        self.text_dialog("How it works", "1. In Rockbox, enable playback logging and run Plugins → Applications → lastfm_scrobbler. Import the exported .scrobbler.log; playback.log is a different format.\n\n2. In Settings, create a Last.fm API account and save its key and shared secret. Connect Last.fm, approve access in your browser, then click Finish connecting.\n\n3. Import a log. Correct the player's clock only if needed. Review listening dates, artists and titles. Click a checkbox or press Space to select. Select ready selects eligible plays in the current search/filter.\n\n4. Scrobble selected shows the account and date range before sending. Plays older than 14 days are held back unless you enable date adjustment in Settings. Adjusted dates have an asterisk; original dates appear below the table.\n\nInterrupted replies become Check outcome. Check your profile and explicitly mark them received or allow a retry. Uncertain plays are never retried automatically.\n\nClose the app window to quit. During an operation, wait for it to finish before closing.")

    def privacy(self):
        self.text_dialog("Privacy & storage", "This native interface does not start a local server. Only Last.fm API operations use the network, over verified HTTPS. External links open in your browser.\n\nImporting never submits plays or edits source logs. Selected song metadata is sent after your confirmation. There is no telemetry.\n\nCredentials stay in memory by default. Remember on this PC encrypts them using Windows DPAPI for your Windows user. Software running as that user may still access them.\n\n" + f"Queue, receipts, and appearance preferences are stored here:\n{self.app.data_dir}\n\nClear queue preserves submission fingerprints. Uninstall preserves this folder. To remove all data, close the app and delete this folder; doing so loses duplicate protection.\n\nDisconnect deletes saved credentials. To revoke Last.fm access too, remove this app from Last.fm's application settings.")

    def about(self):
        graphics = "Native OpenGL liquid glass is active." if self.scene.renderer.available else "Still Aero background: " + self.scene.renderer.error
        self.text_dialog("About", f"{APP_NAME}\nVersion {VERSION}\nProduct of Achilleus\n\nNative Qt desktop app with Frutiger Aero and liquid glass. Windows releases include Python and Qt; no separate Python installation or FFmpeg is needed.\n\n{graphics}\n\nOriginal application and restored shaders: MIT. Qt/PySide shared libraries: LGPLv3; see the release's licenses folder and THIRD-PARTY-NOTICES.txt.\n\nhttps://github.com/Achilleus-1/Akis-Rockbox-Scrobbler")

    def closeEvent(self, event):
        if not self.idle():
            QMessageBox.information(self, APP_NAME, "An operation is still running. Wait for it to finish before closing the app.")
            event.ignore()
            return
        self.closed = True
        self.timer.stop()
        self.scene.dispose()
        event.accept()

def smoke_test(report, require_gl=False):
    """Offline runtime check including real shader rendering where available."""
    application = QApplication.instance() or QApplication(sys.argv[:1])
    with tempfile.TemporaryDirectory(prefix="rockbox-smoke-") as directory:
        app = App(directory)
        ui = Desktop(app)
        try:
            ui.show()
            application.processEvents()
            app.dispatch("/api/import", {"content": f"Test Artist\tTest Album\tTest Track\t1\t240\tL\t{int(time.time())-3600}", "filename": "synthetic.log"})
            ui.refresh()
            ui.select_ready()
            assert len(ui.selected) == 1
            renderer = ui.scene.renderer
            if require_gl:
                assert renderer.available, renderer.error
            shader_verified = False
            if renderer.available:
                from PySide6.QtCore import QRectF
                rect = QRectF(50, 50, 700, 500)
                panes = [(rect, 26, 0, rect.adjusted(-2, -2, 2, 2))]
                first = renderer.render(900, 700, 0, (150, 100, 0), [], panes, False)
                moving = renderer.render(900, 700, 25, (150, 100, 0), [], panes, False)
                pointer = renderer.render(900, 700, 0, (150, 100, 1), [], panes, False)
                ripple = renderer.render(900, 700, 0, (150, 100, 0), [(300, 250, .3, 1)], panes, False)
                night = renderer.render(900, 700, 25, (600, 400, 1), [], panes, True)
                assert all(first != frame for frame in (moving, pointer, ripple, night)), "A shader effect did not change its output."
                shader_verified = True
            for dark in (True, False):
                ui.dark.setChecked(dark)
                ui.toggle_appearance()
                application.processEvents()
                assert app.preferences()["dark_mode"] == dark
            ui.live.setChecked(False)
            ui.toggle_appearance()
            assert not ui.scene.timer.isActive() and not app.preferences()["live_glass"]
            ui.show_sample()
            assert len(app.state()["tracks"]) == 1 and not ui.submit_button.isEnabled()
            ui.show_sample()
            assert len(ui.rows) == 1 and not app.job["running"]
            if getattr(sys, "frozen", False):
                for name in ("Python-LICENSE.txt", "Qt-LGPL-3.0.txt", "Qt-GPL-3.0.txt", "Qt-THIRD-PARTY.txt", "RUNTIME-VERSIONS.json"):
                    assert (Path(sys._MEIPASS) / "licenses" / name).is_file(), f"Missing bundled notice: {name}"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps({"ok": True, "version": VERSION, "native_gui": "Qt", "imported": len(ui.rows), "themes": ["dark", "light"], "liquid_glass_verified": shader_verified, "graphics_fallback": renderer.error, "frozen": bool(getattr(sys, "frozen", False))}), encoding="utf-8")
        finally:
            ui.close()
            application.processEvents()
            app.db.close()

def main():
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--data-dir", type=Path, default=Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share"))) / "RockboxRelay")
    parser.add_argument("--smoke-test", type=Path, metavar="REPORT_JSON")
    parser.add_argument("--require-gl", action="store_true", help="Require real OpenGL output in the smoke test")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args()
    application = QApplication(sys.argv[:1])
    application.setApplicationName(APP_NAME)
    application.setOrganizationName("Achilleus")
    if args.smoke_test:
        try:
            smoke_test(args.smoke_test, args.require_gl)
        except Exception:
            import traceback
            args.smoke_test.parent.mkdir(parents=True, exist_ok=True)
            args.smoke_test.write_text(json.dumps({"ok": False, "error": traceback.format_exc()}), encoding="utf-8")
            raise SystemExit(1)
        return
    instance = app = ui = None
    try:
        args.data_dir.mkdir(parents=True, exist_ok=True)
        instance = acquire_instance_lock(args.data_dir)
        if instance is None:
            QMessageBox.information(None, APP_NAME, "The app is already running. Switch to its existing window.")
            return
        app = App(args.data_dir)
        ui = Desktop(app)
        ui.show()
        application.exec()
    except (AppError, OSError) as exc:
        QMessageBox.critical(None, APP_NAME, str(exc))
    finally:
        if ui and not ui.closed:
            ui.scene.dispose()
        if app:
            app.db.close()
        if instance:
            instance.close()

if __name__ == "__main__":
    main()
