#!/usr/bin/env python3
"""
ui_qt/main.py — RakuOS Software Center
Sidebar with expandable category tree (Discover-style) + page stack.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFrame, QStackedWidget,
    QSizePolicy, QSpacerItem, QScrollArea, QToolButton,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPalette, QPixmap, QIcon

from .theme import STYLE, bold_font, _c, _mix, col_active_nav
from .widgets import NavButton, spacer_v
from .tray import RakuOSTray
from .daemon import UpdateDaemon
from .pages.home      import HomePage
from .pages.explore   import ExplorePage
from .pages.search    import SearchPage
from .pages.installed import InstalledPage
from .pages.updates   import UpdatesPage
from .pages.system    import SystemPage
from .pages.settings  import SettingsPage
from .pages.detail    import AppDetailPage
from .pages.webapps   import WebAppsPage
from .pages.appimage_detail import AppImageDetailPage

from backend import packages


# ── Category tree ─────────────────────────────────────────────────────────────
# (top_label, top_appstream_cat, [(sub_label, sub_appstream_cat), ...])

CATEGORY_TREE = [
    ("🎮 Games", "Game", [
        ("Action",          "ActionGame"),
        ("Adventure",       "AdventureGame"),
        ("Arcade",          "ArcadeGame"),
        ("Board Games",     "BoardGame"),
        ("Card Games",      "CardGame"),
        ("Emulators",       "Emulator"),
        ("Kids",            "KidsGame"),
        ("Logic",           "LogicGame"),
        ("Role Playing",    "RolePlaying"),
        ("Shooter",         "Shooter"),
        ("Simulation",      "Simulation"),
        ("Sports",          "SportsGame"),
        ("Strategy",        "StrategyGame"),
    ]),
    ("🌐 Internet", "Network", [
        ("Web Browsers",    "WebBrowser"),
        ("Email",           "Email"),
        ("Chat & IM",       "InstantMessaging"),
        ("File Sharing",    "FileTransfer"),
        ("News & RSS",      "News"),
        ("Remote Access",   "RemoteAccess"),
    ]),
    ("🎵 Audio & Video", "AudioVideo", [
        ("Music Players",   "Music"),
        ("Video Players",   "Video"),
        ("Editors",         "AudioVideoEditing"),
        ("Mixers",          "Mixer"),
        ("Podcasts",        "Podcasting"),
        ("Recorders",       "Recorder"),
    ]),
    ("📷 Graphics", "Graphics", [
        ("2D Editors",      "2DGraphics"),
        ("3D Editors",      "3DGraphics"),
        ("Photography",     "Photography"),
        ("Scanning",        "Scanning"),
        ("Viewers",         "Viewer"),
        ("Publishing",      "Publishing"),
    ]),
    ("💼 Office", "Office", [
        ("Word Processing", "WordProcessor"),
        ("Spreadsheets",    "Spreadsheet"),
        ("Presentations",   "Presentation"),
        ("Calendars",       "Calendar"),
        ("Contacts",        "ContactManagement"),
        ("Finance",         "Finance"),
    ]),
    ("🛠 Development", "Development", [
        ("IDEs",            "IDE"),
        ("Debuggers",       "Debugger"),
        ("Version Control", "RevisionControl"),
        ("Web Dev",         "WebDevelopment"),
        ("Databases",       "Database"),
    ]),
    ("⚙️ System", "System", [
        ("File Managers",   "FileManager"),
        ("Terminals",       "TerminalEmulator"),
        ("Monitors",        "Monitor"),
        ("Package Mgmt",    "PackageManager"),
        ("Security",        "Security"),
        ("Virtualisation",  "Emulator"),
    ]),
    ("🎓 Education", "Education", [
        ("Science",         "Science"),
        ("Maths",           "Math"),
        ("Languages",       "Languages"),
        ("Kids",            "KidsGame"),
    ]),
    ("♿ Accessibility", "Accessibility", []),
]


# ── Sidebar category widget ───────────────────────────────────────────────────

class CategoryTreeWidget(QWidget):
    """
    Expandable category tree for the sidebar.
    Emits category_selected(cat, label) when any item is clicked.
    """
    category_selected = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self._active_btn: QPushButton | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        for top_label, top_cat, subs in CATEGORY_TREE:
            # Top-level row: expand toggle + clickable label
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(4, 0, 4, 0)
            rl.setSpacing(0)

            # Arrow toggle (only shown if has subs)
            toggle = QToolButton()
            toggle.setFixedSize(22, 28)
            toggle.setArrowType(Qt.ArrowType.RightArrow if subs else Qt.ArrowType.NoArrow)
            toggle.setStyleSheet("QToolButton { border: none; background: transparent; }")

            # Top-level button
            top_btn = self._make_btn(f"  {top_label}", top_cat, top_label, indent=0)
            rl.addWidget(toggle)
            rl.addWidget(top_btn, stretch=1)
            layout.addWidget(row)

            # Sub-item container
            if subs:
                sub_container = QWidget()
                sub_container.hide()
                sl = QVBoxLayout(sub_container)
                sl.setContentsMargins(28, 0, 0, 0)
                sl.setSpacing(1)

                for sub_label, sub_cat in subs:
                    sb = self._make_btn(sub_label, sub_cat, sub_label, indent=1)
                    sl.addWidget(sb)

                layout.addWidget(sub_container)

                # Wire toggle
                toggle.clicked.connect(
                    lambda checked, tc=toggle, sc=sub_container: self._toggle(tc, sc)
                )

        layout.addStretch()

    def _make_btn(self, text: str, cat: str, label: str, indent: int) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("navbtn")
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        h = 34 if indent == 0 else 28
        btn.setMinimumHeight(h)
        if indent == 1:
            f = btn.font()
            f.setPointSize(f.pointSize() - 1)
            btn.setFont(f)
        btn.clicked.connect(lambda checked=False, c=cat, l=label: self._on_click(btn, c, l))
        return btn

    def _toggle(self, toggle: QToolButton, container: QWidget):
        expanded = container.isVisible()
        container.setVisible(not expanded)
        toggle.setArrowType(
            Qt.ArrowType.DownArrow if not expanded else Qt.ArrowType.RightArrow
        )

    def _on_click(self, btn: QPushButton, cat: str, label: str):
        self._set_active(btn)
        self.category_selected.emit(cat, label)

    def _set_active(self, btn: QPushButton):
        if self._active_btn and self._active_btn is not btn:
            self._clear_active(self._active_btn)
        self._active_btn = btn
        p = btn.palette()
        p.setColor(QPalette.ColorRole.ButtonText, _c(QPalette.ColorRole.Highlight))
        p.setColor(QPalette.ColorRole.Button, col_active_nav())
        btn.setPalette(p)
        btn.setAutoFillBackground(True)
        btn.update()

    def _clear_active(self, btn: QPushButton):
        btn.setPalette(QApplication.palette())
        btn.setAutoFillBackground(False)
        btn.update()

    def clear_active(self):
        if self._active_btn:
            self._clear_active(self._active_btn)
            self._active_btn = None


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RakuOS Software")
        self.setWindowIcon(QIcon.fromTheme("system-software-install"))
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
        sidebar.setFixedWidth(230)
        sidebar.setFrameShape(QFrame.Shape.StyledPanel)

        sidebar_scroll = QScrollArea()
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        sidebar_content = QWidget()
        sl = QVBoxLayout(sidebar_content)
        sl.setContentsMargins(10, 14, 10, 14)
        sl.setSpacing(2)

        # Logo
        logo_row = QHBoxLayout()
        _logo_pix = QPixmap("/usr/share/pixmaps/rakuos-logo.svg")
        if _logo_pix.isNull():
            # fallback: try without extension
            _logo_pix = QPixmap("/usr/share/pixmaps/rakuos-logo")
        logo_icon = QLabel()
        if not _logo_pix.isNull():
            logo_icon.setPixmap(_logo_pix.scaled(28, 28,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            logo_icon.setText("🐉")
            f = logo_icon.font(); f.setPointSize(f.pointSize() + 6); logo_icon.setFont(f)
        logo_row.addWidget(logo_icon)
        logo_text = bold_font(QLabel("RakuOS Software"))
        logo_row.addWidget(logo_text)
        logo_row.addStretch()
        sl.addLayout(logo_row)
        sl.addSpacing(10)

        # Static nav buttons
        self._nav_btns: dict[str, NavButton] = {}
        for page_id, icon, text in [
            ("home",      "🏠", "Home"),
            ("installed", "📦", "Installed"),
            ("webapps",   "🌐", "Web Apps"),
            ("updates",   "🔄", "Updates"),
            ("system",    "⚙️",  "System"),
            ("settings",  "🛠",  "Settings"),
        ]:
            btn = NavButton(icon, text)
            btn.clicked.connect(lambda checked=False, p=page_id: self.navigate(p))
            sl.addWidget(btn)
            self._nav_btns[page_id] = btn

        # Separator + Categories heading
        sl.addSpacing(8)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine); sl.addWidget(sep)
        sl.addSpacing(4)
        cat_heading = bold_font(QLabel("  Categories"))
        f2 = cat_heading.font(); f2.setPointSize(f2.pointSize() - 1); cat_heading.setFont(f2)
        sl.addWidget(cat_heading)
        sl.addSpacing(2)

        # Category tree
        self._cat_tree = CategoryTreeWidget()
        self._cat_tree.category_selected.connect(self._on_category)
        sl.addWidget(self._cat_tree)
        sl.addStretch()

        sidebar_scroll.setWidget(sidebar_content)

        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.addWidget(sidebar_scroll)
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

        ml.addWidget(topbar)

        # Page stack
        self._stack = QStackedWidget()
        self._home           = HomePage()
        self._explore        = ExplorePage()
        self._explore.subcat_clicked.connect(self._on_subcat)
        self._search_p       = SearchPage()
        self._installed      = InstalledPage()
        self._updates        = UpdatesPage()
        self._system         = SystemPage()
        self._settings       = SettingsPage()
        self._detail         = AppDetailPage()
        self._webapps        = WebAppsPage()
        self._appimage_detail = AppImageDetailPage()

        self._pages: dict[str, QWidget] = {
            "home":            self._home,
            "explore":         self._explore,
            "search":          self._search_p,
            "installed":       self._installed,
            "updates":         self._updates,
            "system":          self._system,
            "settings":        self._settings,
            "detail":          self._detail,
            "webapps":         self._webapps,
            "appimage_detail": self._appimage_detail,
        }
        for widget in self._pages.values():
            widget.setAutoFillBackground(True)
            self._stack.addWidget(widget)

        ml.addWidget(self._stack)
        root.addWidget(main_area)

        # Wire signals
        for pg in (self._home, self._explore, self._search_p, self._installed):
            pg.app_clicked.connect(self._open_detail)
        self._home.see_all_clicked.connect(self._on_category)
        self._detail.back_requested.connect(self._on_back)
        self._webapps.app_clicked.connect(self._open_webapp_detail)
        self._installed.appimage_clicked.connect(self._open_appimage_installed)
        self._installed.webapp_clicked.connect(self._open_webapp_detail)
        self._appimage_detail.back_requested.connect(self._on_back)
        self._appimage_detail.installed.connect(lambda _: self._installed.load())
        self._prev_page = "home"

        self.navigate("home")
        packages.preload_appstream()

        # ── Tray + background daemon ──────────────────────────────────────────
        self._tray = RakuOSTray(self, parent=self)
        self._tray.show()  # always visible
        self._daemon = UpdateDaemon(self)
        self._daemon.updates_ready.connect(self._on_updates_ready)
        self._daemon.updates_ready.connect(self._on_daemon_refresh_home)
        self._daemon.notify.connect(self._on_notify)
        self._daemon.start()

        # Wire settings schedule changes to reschedule daemon
        self._settings._update_tab.schedule_changed.connect(
            self._daemon._reschedule)

    def closeEvent(self, event):
        """Hide to tray instead of quitting."""
        event.ignore()
        self.hide()

    def _on_daemon_refresh_home(self, result: dict):
        """Silently reload home page sections when daemon check completes."""
        if self._stack.currentWidget() is not self._home:
            # Reload in background so next visit is fresh
            self._home.load()

    def _on_updates_ready(self, result: dict):
        """Update tray badge and updates page when check completes."""
        total = result["total"]
        pkg_count = len(result.get("packages", []))
        fp_count  = len(result.get("flatpak", []))
        img       = result.get("image_available", False)

        parts = []
        if pkg_count:
            parts.append(f"{pkg_count} package{'s' if pkg_count != 1 else ''}")
        if fp_count:
            parts.append(f"{fp_count} Flatpak{'s' if fp_count != 1 else ''}")
        if img:
            parts.append("system image")
        summary = ", ".join(parts) + " available" if parts else ""

        self._tray.set_updates(total, summary)

        # Refresh updates page if it's currently visible
        if self._stack.currentWidget() is self._updates:
            self._updates.load(result)

    def _on_notify(self, title: str, body: str):
        """Show desktop notification via tray or notify-send."""
        if self._tray.isSystemTrayAvailable() and self._tray.supportsMessages():
            self._tray.showMessage(title, body,
                                   self._tray.MessageIcon.Information, 8000)
        else:
            # GNOME fallback — notify-send
            try:
                import subprocess
                subprocess.Popen(["notify-send", "--app-name=RakuOS Software",
                                  "--icon=system-software-update", title, body])
            except Exception:
                pass

    # ── Navigation ────────────────────────────────────────────────────────────

    def navigate(self, page_id: str):
        if page_id == "detail":
            return
        self._prev_page = page_id
        self._stack.setCurrentWidget(self._pages[page_id])

        # Update static nav button active states
        for pid, btn in self._nav_btns.items():
            btn.set_active(pid == page_id)

        # Clear category tree active if not on explore
        if page_id != "explore":
            self._cat_tree.clear_active()

        loaders = {
            "home":      self._home.load,
            "installed": self._installed.load,
            "updates":   lambda: self._updates.load(self._daemon.last_result() or None),
            "system":    self._system.load,
            "webapps":   self._webapps.load,
        }
        if page_id in loaders:
            loaders[page_id]()

    def _on_category(self, cat: str, label: str):
        """Called when a sidebar category is clicked."""
        for btn in self._nav_btns.values():
            btn.set_active(False)
        self._prev_page = "explore"
        self._stack.setCurrentWidget(self._explore)
        # Look up subcategories for this top-level cat
        subcats = None
        for top_label, top_cat, subs in CATEGORY_TREE:
            if top_cat == cat and subs:
                subcats = subs
                break
        self._explore.load_category(cat, label, subcats=subcats)

    def _on_subcat(self, cat: str, label: str):
        """Called when user clicks a subcategory tile inside explore."""
        self._explore.load_category(cat, label, subcats=None)

    def _show_page(self, widget):
        """Switch to a page widget."""
        self._stack.setCurrentWidget(widget)

    def _open_detail(self, app: dict):
        self._detail.load_app(app)
        self._show_page(self._detail)

    def _open_webapp_detail(self, app: dict):
        """Open webapp install/detail view — reuses AppDetailPage with webapp info."""
        self._detail.load_app(app)
        self._show_page(self._detail)

    def _open_appimage_file(self, path: str):
        """Called when user double-clicks an .AppImage file."""
        import os
        if os.environ.get("RAKUOS_DEBUG"):
            print(f"[main] _open_appimage_file: {path!r}")
        if not path:
            print("[main] _open_appimage_file called with empty path")
            return
        self._appimage_detail.load_from_file(path)
        self._show_page(self._appimage_detail)
        for btn in self._nav_btns.values():
            btn.set_active(False)

    def _open_appimage_installed(self, app: dict):
        """Called from Installed page for an already-installed AppImage."""
        self._appimage_detail.load_installed(app)
        self._show_page(self._appimage_detail)
        for btn in self._nav_btns.values():
            btn.set_active(False)

    def _on_back(self):
        self.navigate(self._prev_page)

    def _on_search(self):
        q = self._search.text().strip()
        if not q:
            return
        for btn in self._nav_btns.values():
            btn.set_active(False)
        self._cat_tree.clear_active()
        self._stack.setCurrentWidget(self._search_p)
        self._search_p.search(q)

    def _set_source(self, src: str):
        for s, b in self._src_btns.items():
            b.setChecked(s == src)
            b.setFlat(s != src)


# ── Entry point ───────────────────────────────────────────────────────────────

def run(rpm_file: str = None, flatpak_file: str = None,
        flatpakref: str = None, appimage_file: str = None):
    de = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "kde" in de or "plasma" in de:
        os.environ.setdefault("QT_QPA_PLATFORMTHEME", "kde")
    else:
        os.environ.setdefault("QT_QPA_PLATFORMTHEME", "qt6ct")

    app = QApplication(sys.argv)
    app.setApplicationName("RakuOS Software")
    app.setOrganizationName("RakuOS")
    app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(False)  # keep alive in tray

    # ── Single instance via QLocalServer ─────────────────────────────────────
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket
    _SOCKET_NAME = f"rakuos-software-{os.environ.get('USER', 'user')}"

    # Try connecting to an existing instance first
    _probe = QLocalSocket()
    _probe.connectToServer(_SOCKET_NAME)
    if _probe.waitForConnected(300):
        # Already running — forward file path if any, then raise
        import json as _json
        msg = {
            "cmd":          "raise",
            "rpm_file":     rpm_file     or "",
            "flatpak_file": flatpak_file or "",
            "flatpakref":   flatpakref   or "",
            "appimage":     appimage_file or "",
        }
        _probe.write((_json.dumps(msg) + "\n").encode())
        _probe.flush()
        _probe.waitForBytesWritten(500)
        _probe.disconnectFromServer()
        sys.exit(0)

    win = MainWindow()

    # Start the local server to accept commands from future invocations
    _server = QLocalServer(win)
    QLocalServer.removeServer(_SOCKET_NAME)  # clean up stale socket
    _server.listen(_SOCKET_NAME)

    def _on_new_connection():
        import json as _json
        conn = _server.nextPendingConnection()
        if not conn:
            return
        conn.waitForReadyRead(500)
        raw = conn.readAll().data().decode().strip()
        conn.disconnectFromServer()
        win.show()
        win.raise_()
        win.activateWindow()
        try:
            msg = _json.loads(raw)
        except Exception:
            return  # plain "raise" from old client — just show window
        # Forward file opens to the correct detail page
        ai = msg.get("appimage", "")
        rpm = msg.get("rpm_file", "")
        fp  = msg.get("flatpak_file", "")
        ref = msg.get("flatpakref", "")
        if ai:
            QTimer.singleShot(200, lambda: win._open_appimage_file(ai))
        elif rpm:
            from backend import packages as _pkg
            QTimer.singleShot(200, lambda: win._open_detail(
                _pkg.get_local_rpm_info(rpm)))
        elif fp:
            from backend import flatpak as _fp2
            QTimer.singleShot(200, lambda: win._open_detail(
                _fp2.get_local_flatpak_info(fp)))
        elif ref:
            from backend import flatpak as _fp2
            QTimer.singleShot(200, lambda: win._open_detail(
                _fp2.get_flatpakref_info(ref)))

    _server.newConnection.connect(_on_new_connection)

    # ── --tray flag: start hidden ─────────────────────────────────────────────
    tray_mode = "--tray" in sys.argv
    if not tray_mode:
        win.show()

    # Open local file directly on the detail page
    # NOTE: QTimer is imported at module level — no local re-imports needed
    from backend import flatpak as _fp

    if rpm_file:
        win.show()
        win.raise_()
        def _open_rpm():
            info = packages.get_local_rpm_info(rpm_file)
            win._open_detail(info)
        QTimer.singleShot(300, _open_rpm)

    elif flatpak_file:
        win.show()
        win.raise_()
        def _open_flatpak():
            info = _fp.get_local_flatpak_info(flatpak_file)
            win._open_detail(info)
        QTimer.singleShot(300, _open_flatpak)

    elif flatpakref:
        win.show()
        win.raise_()
        def _open_ref():
            info = _fp.get_flatpakref_info(flatpakref)
            win._open_detail(info)
        QTimer.singleShot(300, _open_ref)

    elif appimage_file:
        print(f"[run] Opening AppImage: {appimage_file!r}")
        win.show()
        win.raise_()
        win.activateWindow()
        def _open_ai():
            win._open_appimage_file(appimage_file)
            win.raise_()
        QTimer.singleShot(400, _open_ai)

    sys.exit(app.exec())


if __name__ == "__main__":
    run()
