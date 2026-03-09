#!/usr/bin/env python3
"""
ui_qt/main.py — RakuOS Software Center entry point.
Wires together MainWindow, sidebar navigation, and all pages.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFrame, QStackedWidget, QSizePolicy, QSpacerItem,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette

from .theme import STYLE, bold_font
from .widgets import NavButton, spacer_v
from .pages.home      import HomePage
from .pages.explore   import ExplorePage
from .pages.search    import SearchPage
from .pages.installed import InstalledPage
from .pages.updates   import UpdatesPage
from .pages.system    import SystemPage
from .pages.detail    import AppDetailPage

from backend import packages


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RakuOS Software")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ───────────────────────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        sidebar.setFrameShape(QFrame.Shape.StyledPanel)
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(12, 16, 12, 16)
        sl.setSpacing(2)

        logo_row = QHBoxLayout()
        logo_icon = bold_font(QLabel("🐉"), extra_pts=8)
        logo_row.addWidget(logo_icon)
        logo_text = bold_font(QLabel("RakuOS Software"))
        logo_row.addWidget(logo_text)
        logo_row.addStretch()
        sl.addLayout(logo_row)
        sl.addSpacing(12)

        self._nav_btns: dict[str, NavButton] = {}
        for page_id, icon, text in [
            ("home",      "🏠", "Home"),
            ("explore",   "🔭", "Explore"),
            ("installed", "📦", "Installed"),
            ("updates",   "🔄", "Updates"),
            ("system",    "⚙️",  "System"),
        ]:
            btn = NavButton(icon, text)
            btn.clicked.connect(lambda checked, p=page_id: self.navigate(p))
            sl.addWidget(btn)
            self._nav_btns[page_id] = btn

        sl.addItem(spacer_v())
        root.addWidget(sidebar)

        # ── Main area ─────────────────────────────────────────────────────────
        main_area = QWidget()
        main_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        ml = QVBoxLayout(main_area)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        # Topbar
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(56)
        topbar.setFrameShape(QFrame.Shape.StyledPanel)
        tl = QHBoxLayout(topbar)
        tl.setContentsMargins(20, 0, 20, 0)
        tl.setSpacing(12)

        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search apps…")
        self._search.setMaximumWidth(420)
        self._search.returnPressed.connect(self._on_search)
        tl.addWidget(self._search)
        tl.addStretch()

        self._src_btns: dict[str, QPushButton] = {}
        for src, lbl_text in [("all", "All"), ("native", "RPM"), ("flatpak", "Flatpak")]:
            b = QPushButton(lbl_text)
            b.setCheckable(True)
            b.setChecked(src == "all")
            b.setFlat(src != "all")
            b.clicked.connect(lambda checked, s=src: self._set_source(s))
            tl.addWidget(b)
            self._src_btns[src] = b

        ml.addWidget(topbar)

        # Pages
        self._stack = QStackedWidget()
        self._home      = HomePage()
        self._explore   = ExplorePage()
        self._search_p  = SearchPage()
        self._installed = InstalledPage()
        self._updates   = UpdatesPage()
        self._system    = SystemPage()
        self._detail    = AppDetailPage()

        self._pages: dict[str, QWidget] = {
            "home":      self._home,
            "explore":   self._explore,
            "search":    self._search_p,
            "installed": self._installed,
            "updates":   self._updates,
            "system":    self._system,
            "detail":    self._detail,
        }
        for widget in self._pages.values():
            self._stack.addWidget(widget)

        ml.addWidget(self._stack)
        root.addWidget(main_area)

        # Connect app clicks → detail page
        for pg in (self._home, self._explore, self._search_p, self._installed):
            pg.app_clicked.connect(self._open_detail)
        self._detail.back_requested.connect(self._on_back)
        self._prev_page = "home"

        self.navigate("home")
        packages.preload_appstream()

    # ── Navigation ────────────────────────────────────────────────────────────

    def navigate(self, page_id: str):
        if page_id == "detail":
            return
        self._prev_page = page_id
        self._stack.setCurrentWidget(self._pages[page_id])

        for pid, btn in self._nav_btns.items():
            btn.set_active(pid == page_id)

        loaders = {
            "home":      self._home.load,
            "explore":   self._explore.load_category,
            "installed": self._installed.load,
            "updates":   self._updates.load,
            "system":    self._system.load,
        }
        if page_id in loaders:
            loaders[page_id]()

    def _open_detail(self, app: dict):
        self._detail.load_app(app)
        self._stack.setCurrentWidget(self._detail)

    def _on_back(self):
        self.navigate(self._prev_page)

    def _on_search(self):
        q = self._search.text().strip()
        if not q:
            return
        for btn in self._nav_btns.values():
            btn.set_active(False)
        self._stack.setCurrentWidget(self._search_p)
        self._search_p.search(q)

    def _set_source(self, src: str):
        for s, b in self._src_btns.items():
            b.setChecked(s == src)
            b.setFlat(s != src)




# ── Entry point ───────────────────────────────────────────────────────────────

def run():
    de = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "gnome" not in de:
        os.environ.setdefault("QT_QPA_PLATFORMTHEME", "kde")

    app = QApplication(sys.argv)
    app.setApplicationName("RakuOS Software")
    app.setOrganizationName("RakuOS")
    app.setStyleSheet(STYLE)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()
