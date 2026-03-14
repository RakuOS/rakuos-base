"""
pages/installed.py — Installed apps page with tabs.

Tabs:
  RPM (Overlay)  — packages from /var/lib/rakuos/packages.list only
  Flatpak        — apps + runtimes/add-ons, shown as subsections
  AppImages      — user-installed AppImages
  Web Apps       — user-installed web apps

Each tab is a scrollable list of rows with an Uninstall button on the right.
Clicking a row name opens the detail page (existing behaviour).
"""

import subprocess
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
    QLabel, QPushButton, QTabWidget, QSizePolicy,
    QStackedWidget, QProgressBar,
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QPixmap

from ..workers import Worker
from ..widgets import SectionTitle, LoadingWidget, hline
from ..theme import dimmed, bold_font
from backend import packages, flatpak, appimages, webapps


# ── Single list row ───────────────────────────────────────────────────────────

class InstalledRow(QFrame):
    """
    One installed item row — fixed 48px height.
    icon | name + summary | [Runtime] | version | Uninstall/progress/result
    """
    clicked   = pyqtSignal(dict)
    uninstall = pyqtSignal(dict)

    def __init__(self, app: dict, parent=None):
        super().__init__(parent)
        self._app = app
        self.setObjectName("installedRow")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedHeight(48)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        hl = QHBoxLayout(self)
        hl.setContentsMargins(12, 0, 12, 0)
        hl.setSpacing(10)

        # ── Icon 32×32 ────────────────────────────────────────────────────────
        icon_lbl = QLabel(self)
        icon_lbl.setFixedSize(32, 32)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_path = app.get("icon_path", "")
        if icon_path:
            pix = QPixmap(icon_path)
            if not pix.isNull():
                icon_lbl.setPixmap(pix.scaled(
                    32, 32,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
            else:
                icon_lbl.setText(self._fallback_icon(app))
        else:
            icon_lbl.setText(self._fallback_icon(app))
        hl.addWidget(icon_lbl)

        # ── Name (bold) + summary (small, dimmed) — single expanding widget ────
        name    = app.get("name") or app.get("id", "unknown")
        summary = app.get("summary") or app.get("description", "")
        summary_short = summary[:72] + ("…" if len(summary) > 72 else "")

        text_widget = QWidget(self)
        text_widget.setFixedHeight(48)
        text_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        tv = QVBoxLayout(text_widget)
        tv.setContentsMargins(0, 4, 0, 4)
        tv.setSpacing(1)

        name_lbl = QLabel(name, text_widget)
        nf = name_lbl.font()
        nf.setBold(True)
        name_lbl.setFont(nf)
        name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        tv.addWidget(name_lbl)

        if summary_short:
            s_lbl = QLabel(summary_short, text_widget)
            s_lbl.setStyleSheet("font-size: 11px; color: palette(mid);")
            s_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            tv.addWidget(s_lbl)

        hl.addWidget(text_widget, stretch=1)

        # ── Runtime badge ─────────────────────────────────────────────────────
        if app.get("runtime"):
            badge = QLabel("Runtime", self)
            badge.setStyleSheet(
                "QLabel { background: rgba(128,128,128,0.15); color: palette(mid);"
                " border-radius: 4px; padding: 1px 7px; font-size: 10px; }")
            badge.setFixedHeight(18)
            hl.addWidget(badge)

        # ── Version ───────────────────────────────────────────────────────────
        ver = str(app.get("version", ""))
        if ver:
            ver_lbl = QLabel(ver, self)
            ver_lbl.setFixedWidth(90)
            ver_lbl.setAlignment(Qt.AlignmentFlag.AlignRight |
                                  Qt.AlignmentFlag.AlignVCenter)
            ver_lbl.setStyleSheet("font-size: 11px; color: palette(mid);")
            hl.addWidget(ver_lbl)

        # ── Uninstall / progress / result stack ───────────────────────────────
        self._state = 0   # 0=btn 1=progress 2=result

        self._btn = QPushButton("Uninstall", self)
        self._btn.setFixedSize(90, 28)
        self._btn.setObjectName("dangerButton")
        self._btn.clicked.connect(lambda: self.uninstall.emit(self._app))

        self._prog = QProgressBar(self)
        self._prog.setRange(0, 0)
        self._prog.setFixedSize(90, 8)
        self._prog.setTextVisible(False)
        self._prog.setStyleSheet(
            "QProgressBar{border-radius:4px;background:rgba(229,57,53,0.15);}"
            "QProgressBar::chunk{background:#e53935;border-radius:4px;}")
        self._prog.hide()

        self._result = QLabel(self)
        self._result.setFixedSize(90, 28)
        self._result.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._result.hide()

        hl.addWidget(self._btn)
        hl.addWidget(self._prog)
        hl.addWidget(self._result)

    @staticmethod
    def _fallback_icon(app: dict) -> str:
        src = app.get("source", "")
        return ("🌐" if src == "webapp" else
                "📦" if src == "appimage" else
                "◈"     if src == "flatpak" else "⬡")

    def set_uninstalling(self):
        self._btn.hide()
        self._prog.show()
        self._result.hide()
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_done(self, success: bool):
        self._btn.hide()
        self._prog.hide()
        self._result.show()
        if success:
            self._result.setText("✓")
            self._result.setStyleSheet("color: #4caf50; font-size: 18px;")
        else:
            self._result.setText("✗")
            self._result.setStyleSheet("color: #e53935; font-size: 18px;")

    def mousePressEvent(self, event):
        self.clicked.emit(self._app)
        super().mousePressEvent(event)


# ── Scrollable list tab ───────────────────────────────────────────────────────

class ListTab(QWidget):
    """A scrollable list of InstalledRow widgets, optionally with subsections."""
    row_clicked   = pyqtSignal(dict)
    row_uninstall = pyqtSignal(dict, object)   # (app, row)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoFillBackground(True)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget(scroll)
        self._vl = QVBoxLayout(self._content)
        self._vl.setContentsMargins(16, 12, 16, 12)
        self._vl.setSpacing(0)
        scroll.setWidget(self._content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def set_items(self, items: list[dict], empty_text: str = "Nothing installed."):
        self._clear()
        if not items:
            self._vl.addStretch()
            self._vl.addWidget(
                dimmed(QLabel(empty_text)),
                alignment=Qt.AlignmentFlag.AlignCenter)
            self._vl.addStretch()
            return
        for i, app in enumerate(items):
            row = InstalledRow(app)
            row.clicked.connect(self.row_clicked)
            row.uninstall.connect(lambda a, r=row: self.row_uninstall.emit(a, r))
            self._vl.addWidget(row)
            if i < len(items) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.HLine)
                sep.setStyleSheet("color: rgba(128,128,128,0.12);")
                self._vl.addWidget(sep)
        self._vl.addStretch()

    def set_sections(self, sections: list[tuple[str, list[dict]]],
                     empty_text: str = "Nothing installed."):
        """sections = [('Section Title', [app, ...]), ...]"""
        self._clear()
        has_any = any(items for _, items in sections)
        if not has_any:
            self._vl.addStretch()
            self._vl.addWidget(
                dimmed(QLabel(empty_text)),
                alignment=Qt.AlignmentFlag.AlignCenter)
            self._vl.addStretch()
            return
        first = True
        for title, items in sections:
            if not items:
                continue
            if not first:
                self._vl.addWidget(hline())
                self._vl.addSpacing(4)
            self._vl.addWidget(SectionTitle(title))
            self._vl.addSpacing(4)
            for i, app in enumerate(items):
                row = InstalledRow(app)
                row.clicked.connect(self.row_clicked)
                row.uninstall.connect(lambda a, r=row: self.row_uninstall.emit(a, r))
                self._vl.addWidget(row)
                if i < len(items) - 1:
                    sep = QFrame()
                    sep.setFrameShape(QFrame.Shape.HLine)
                    sep.setStyleSheet("color: rgba(128,128,128,0.12);")
                    self._vl.addWidget(sep)
            first = False
        self._vl.addStretch()

    def _clear(self):
        while self._vl.count():
            item = self._vl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


# ── Main installed page ───────────────────────────────────────────────────────

class InstalledPage(QWidget):
    app_clicked      = pyqtSignal(dict)
    appimage_clicked = pyqtSignal(dict)
    webapp_clicked   = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._workers: list = []
        self.setAutoFillBackground(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        # Create the four tab list widgets
        self._rpm_tab  = ListTab()
        self._fp_tab   = ListTab()
        self._ai_tab   = ListTab()
        self._wa_tab   = ListTab()

        self._tabs.addTab(self._rpm_tab,  "⬡  RPM (Overlay)")
        self._tabs.addTab(self._fp_tab,   "◈  Flatpak")
        self._tabs.addTab(self._ai_tab,   "📦  AppImages")
        self._tabs.addTab(self._wa_tab,   "🌐  Web Apps")

        # Wire row signals
        self._rpm_tab.row_clicked.connect(self.app_clicked)
        self._fp_tab.row_clicked.connect(self.app_clicked)
        self._ai_tab.row_clicked.connect(self.appimage_clicked)
        self._wa_tab.row_clicked.connect(self.webapp_clicked)

        self._rpm_tab.row_uninstall.connect(self._do_uninstall_rpm)
        self._fp_tab.row_uninstall.connect(self._do_uninstall_flatpak)
        self._ai_tab.row_uninstall.connect(self._do_uninstall_appimage)
        self._wa_tab.row_uninstall.connect(self._do_uninstall_webapp)
        # Note: all _do_uninstall_* take (app, row) args

        outer.addWidget(self._tabs)

    # ── Load ──────────────────────────────────────────────────────────────────

    def load(self):
        # Show loading state in active tab
        for tab in (self._rpm_tab, self._fp_tab, self._ai_tab, self._wa_tab):
            tab.set_items([], "Loading…")

        w = Worker(self._fetch)
        w.result.connect(self._on_data)
        w.start()
        self._workers.append(w)

    def _fetch(self) -> dict:
        # RPM: only packages from packages.list
        rpm_list = self._get_overlay_packages()

        # Flatpak: apps + runtimes separately
        fp_apps     = flatpak.get_installed_flatpaks()
        fp_runtimes = self._get_flatpak_runtimes()

        return {
            "rpm":         rpm_list,
            "fp_apps":     fp_apps,
            "fp_runtimes": fp_runtimes,
            "appimages":   appimages.get_installed(),
            "webapps":     webapps.get_installed(),
        }

    def _get_overlay_packages(self) -> list[dict]:
        """Read packages.list and return enriched metadata for each package."""
        import re
        from pathlib import Path
        pkgs_file = Path("/var/lib/rakuos/packages.list")
        if not pkgs_file.exists():
            return []
        pkg_names = [
            l.strip() for l in pkgs_file.read_text().splitlines()
            if l.strip() and not l.startswith("#")
        ]
        if not pkg_names:
            return []
        # Get version for each installed package
        result = subprocess.run(
            ["rpm", "-q", "--queryformat",
             "%{NAME}\t%{VERSION}-%{RELEASE}\t%{SUMMARY}\n"] + pkg_names,
            capture_output=True, text=True
        )
        items = []
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 1 and "not installed" not in parts[0]:
                name    = parts[0].strip()
                version = parts[1].strip() if len(parts) > 1 else ""
                summary = parts[2].strip() if len(parts) > 2 else ""
                items.append({
                    "id":       name,
                    "pkg_name": name,
                    "name":     name,
                    "version":  version,
                    "summary":  summary,
                    "source":   "native",
                    "installed": True,
                })
        return items

    def _get_flatpak_runtimes(self) -> list[dict]:
        """Return installed Flatpak runtimes and extensions."""
        try:
            result = subprocess.run(
                ["flatpak", "list", "--runtime",
                 "--columns=application,name,version,branch,origin"],
                capture_output=True, text=True
            )
            items = []
            for line in result.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2:
                    app_id = parts[0].strip()
                    branch = parts[3].strip() if len(parts) > 3 else ""
                    # Full ref needed for flatpak remove on runtimes
                    full_ref = f"{app_id}//{branch}" if branch else app_id
                    items.append({
                        "id":        full_ref,   # used for removal
                        "app_id":    app_id,      # display only
                        "name":      parts[1].strip() if len(parts) > 1 else app_id,
                        "version":   parts[2].strip() if len(parts) > 2 else "",
                        "branch":    branch,
                        "origin":    parts[4].strip() if len(parts) > 4 else "",
                        "summary":   "",
                        "source":    "flatpak",
                        "runtime":   True,
                        "installed": True,
                    })
            return items
        except Exception as e:
            print(f"[installed] get_flatpak_runtimes error: {e}")
            return []

    # ── Render ────────────────────────────────────────────────────────────────

    def _on_data(self, data: dict):
        rpm      = data.get("rpm", [])
        fp_apps  = data.get("fp_apps", [])
        fp_rt    = data.get("fp_runtimes", [])
        ais      = data.get("appimages", [])
        was      = data.get("webapps", [])

        # Sort all lists alphabetically by display name
        key = lambda a: (a.get("name") or a.get("id") or "").lower()
        rpm.sort(key=key)
        fp_apps.sort(key=key)
        fp_rt.sort(key=key)
        ais.sort(key=key)
        was.sort(key=key)

        # Update tab labels with counts
        self._tabs.setTabText(0, f"⬡  RPM ({len(rpm)})")
        self._tabs.setTabText(1, f"◈  Flatpak ({len(fp_apps) + len(fp_rt)})")
        self._tabs.setTabText(2, f"📦  AppImages ({len(ais)})")
        self._tabs.setTabText(3, f"🌐  Web Apps ({len(was)})")

        self._rpm_tab.set_items(rpm, "No overlay packages installed.")
        self._fp_tab.set_sections([
            ("Applications", fp_apps),
            ("Runtimes & Add-ons", fp_rt),
        ], "No Flatpaks installed.")
        self._ai_tab.set_items(ais,  "No AppImages installed.")
        self._wa_tab.set_items(was,  "No web apps installed.")

    # ── Uninstall actions ─────────────────────────────────────────────────────

    def _do_uninstall_rpm(self, app: dict, row: "InstalledRow"):
        from ..workers import StreamWorker
        from backend.packages import remove_package_stream
        pkg = app.get("pkg_name") or app.get("name", "")
        if not pkg:
            return
        self._run_uninstall_stream(row, lambda: remove_package_stream(pkg))

    def _do_uninstall_flatpak(self, app: dict, row: "InstalledRow"):
        from ..workers import StreamWorker
        from backend.flatpak import remove_flatpak_stream
        app_id = app.get("id", "")
        if not app_id:
            return
        is_runtime = app.get("runtime", False)
        self._run_uninstall_stream(
            row, lambda: remove_flatpak_stream(app_id, force=is_runtime))

    def _do_uninstall_appimage(self, app: dict, row: "InstalledRow"):
        app_id = app.get("id", "")
        if not app_id:
            return
        row.set_uninstalling()
        w = Worker(lambda: appimages.uninstall_appimage(app_id))
        w.result.connect(lambda r: self._on_simple_done(row, r[0]))
        w.start()
        self._workers.append(w)

    def _do_uninstall_webapp(self, app: dict, row: "InstalledRow"):
        app_id = app.get("id", "")
        if not app_id:
            return
        row.set_uninstalling()
        w = Worker(lambda: webapps.uninstall(app_id))
        w.result.connect(lambda r: self._on_simple_done(row, r[0]))
        w.start()
        self._workers.append(w)

    def _run_uninstall_stream(self, row: "InstalledRow", gen_fn):
        """Run a streaming uninstall, showing inline progress on the row."""
        from ..workers import StreamWorker
        row.set_uninstalling()

        def _on_done(code):
            row.set_done(code == 0)
            if code == 0:
                # Small delay so user sees the ✓ before row disappears
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(800, self.load)

        w = StreamWorker(gen_fn)
        w.done.connect(_on_done)
        w.start()
        self._workers.append(w)

    def _on_simple_done(self, row: "InstalledRow", success: bool):
        row.set_done(success)
        if success:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(800, self.load)


        dlg.exec()
