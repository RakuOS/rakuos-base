"""
pages/webapps.py — Web Apps catalog and management page.

Shows all available web apps from /usr/share/rakuos/webapps/*.json
in a card grid. Installed apps show an "Installed" state.
Clicking a card opens the detail/install view inline.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
    QLabel, QPushButton, QGridLayout, QSizePolicy,
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QPixmap, QIcon

from ..workers import Worker
from ..widgets import SectionTitle, LoadingWidget, IconWidget, hline
from ..theme import dimmed, bold_font
from backend import webapps


# ── Web app card ──────────────────────────────────────────────────────────────

class WebAppCard(QFrame):
    clicked = pyqtSignal(dict)

    def __init__(self, app: dict, parent=None):
        super().__init__(parent)
        self._app = app
        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedWidth(200)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(14, 14, 14, 14)
        vl.setSpacing(8)

        # Icon — load directly from cached icon_path
        icon_w = QLabel()
        icon_w.setFixedSize(64, 64)
        icon_w.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_path = app.get("icon_path", "")
        if icon_path:
            from PyQt6.QtGui import QPixmap
            pix = QPixmap(icon_path)
            if not pix.isNull():
                icon_w.setPixmap(
                    pix.scaled(64, 64,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation))
            else:
                icon_w.setText("🌐")
                f = icon_w.font(); f.setPointSize(28); icon_w.setFont(f)
        else:
            icon_w.setText("🌐")
            f = icon_w.font(); f.setPointSize(28); icon_w.setFont(f)
        vl.addWidget(icon_w, alignment=Qt.AlignmentFlag.AlignCenter)

        # Name
        name_lbl = bold_font(QLabel(app.get("name", "")))
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setWordWrap(True)
        vl.addWidget(name_lbl)

        # Summary
        summary = app.get("summary") or app.get("description", "")
        if summary:
            sum_lbl = dimmed(QLabel(summary[:60] + ("…" if len(summary) > 60 else "")))
            sum_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sum_lbl.setWordWrap(True)
            sum_lbl.setStyleSheet("font-size: 11px;")
            vl.addWidget(sum_lbl)

        # Install state badge
        if app.get("installed"):
            badge = QLabel("✓ Installed")
            badge.setStyleSheet(
                "color: #4caf50; font-size: 11px; font-weight: bold;")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vl.addWidget(badge)

        # WebApp badge
        wb = QLabel("Web App")
        wb.setStyleSheet(
            "QLabel { background: rgba(100,200,130,0.18); color: #4caf50;"
            " border-radius: 4px; padding: 1px 6px; font-size: 10px; }")
        wb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vl.addWidget(wb, alignment=Qt.AlignmentFlag.AlignCenter)

    def mousePressEvent(self, event):
        self.clicked.emit(self._app)
        super().mousePressEvent(event)


# ── Web Apps page ─────────────────────────────────────────────────────────────

class WebAppsPage(QWidget):
    app_clicked = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._workers: list = []

        # Top bar
        topbar = QHBoxLayout()
        topbar.setContentsMargins(24, 16, 24, 8)
        title = bold_font(QLabel("Web Apps"), extra_pts=4)
        topbar.addWidget(title)
        topbar.addStretch()
        refresh_btn = QPushButton("↻  Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.clicked.connect(self.load)
        topbar.addWidget(refresh_btn)
        topbar_w = QWidget()
        topbar_w.setLayout(topbar)

        vl_sub = QVBoxLayout()
        vl_sub.setContentsMargins(24, 4, 24, 8)
        vl_sub.addWidget(dimmed(QLabel(
            "Web apps launch in their own window for a native-like experience. "
            "Each app has isolated cookies and sessions.")))

        # Scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget()
        self._vl = QVBoxLayout(self._content)
        self._vl.setContentsMargins(24, 8, 24, 24)
        self._vl.setSpacing(16)
        scroll.setWidget(self._content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(topbar_w)

        desc_w = QWidget()
        desc_w.setLayout(vl_sub)
        outer.addWidget(desc_w)
        outer.addWidget(hline())
        outer.addWidget(scroll)

    def load(self):
        self._clear()
        self._vl.addWidget(LoadingWidget("Loading web apps…"))
        w = Worker(self._fetch_catalog)
        w.result.connect(self._render)
        w.start()
        self._workers.append(w)

    def _fetch_catalog(self) -> list:
        """
        Fetch catalog and download all icons in this worker thread.
        get_catalog() already calls _resolve_icon() per app which downloads
        from icon_url if not cached — runs here off the main thread so the
        UI never blocks on network I/O.
        """
        return webapps.get_catalog()

    def _render(self, apps: list):
        self._clear()

        if not apps:
            self._vl.addStretch()
            self._vl.addWidget(
                dimmed(QLabel("No web apps available in the catalog.")),
                alignment=Qt.AlignmentFlag.AlignCenter)
            self._vl.addStretch()
            return

        # Split installed vs available
        installed = [a for a in apps if a.get("installed")]
        available = [a for a in apps if not a.get("installed")]

        if installed:
            self._vl.addWidget(SectionTitle("Installed"))
            self._vl.addWidget(self._make_grid(installed))
            self._vl.addWidget(hline())

        if available:
            self._vl.addWidget(SectionTitle("Available"))
            self._vl.addWidget(self._make_grid(available))

        self._vl.addStretch()

    def _make_grid(self, apps: list) -> "QWidget":
        """Return a QWidget containing a grid of WebAppCards."""
        from PyQt6.QtWidgets import QGridLayout
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(12)
        grid.setContentsMargins(0, 0, 0, 0)
        col_count = 4
        for i, app in enumerate(apps):
            card = WebAppCard(app, parent=container)
            card.clicked.connect(self.app_clicked)
            grid.addWidget(card, i // col_count, i % col_count)
        # Fill remaining cells with invisible spacers
        remainder = len(apps) % col_count
        if remainder:
            for j in range(col_count - remainder):
                spacer = QWidget(container)
                spacer.setFixedWidth(200)
                grid.addWidget(spacer,
                               len(apps) // col_count,
                               remainder + j)
        return container

    def _clear(self):
        while self._vl.count():
            item = self._vl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())
        # Delete the layout itself to fully detach it
        try:
            layout.deleteLater()
        except Exception:
            pass
