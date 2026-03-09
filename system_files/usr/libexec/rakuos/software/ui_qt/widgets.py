"""
widgets.py — Reusable UI widgets used across all pages.
"""

import os

from PyQt6.QtWidgets import (
    QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QScrollArea, QSizePolicy,
    QSpacerItem, QDialog, QApplication, QGridLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QPalette, QCursor, QColor

from .theme import (
    dimmed, bold_font, colored_text,
    col_dim, col_hover, col_success, col_warning,
    _c, _mix,
)

from backend import packages


# ── Layout helpers ────────────────────────────────────────────────────────────

def hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFrameShadow(QFrame.Shadow.Sunken)
    return f


def spacer_v() -> QSpacerItem:
    return QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)


# ── Widgets ───────────────────────────────────────────────────────────────────

class IconWidget(QLabel):
    """Displays an app icon from the AppStream icon cache."""

    def __init__(self, size: int = 64):
        super().__init__("📦")
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = self.font()
        f.setPointSize(size // 3)
        self.setFont(f)
        self._size = size

    def set_icon_name(self, name: str):
        if not name:
            return
        path = packages.find_icon(name)
        if path and os.path.exists(path):
            pix = QPixmap(path).scaled(
                self._size, self._size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(pix)
            self.setText("")


class StatusBadge(QLabel):
    """Small rounded badge with a palette-derived tinted background."""

    def __init__(self, text: str, color: QColor):
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bg   = _mix(color, _c(QPalette.ColorRole.Base), 0.85)
        bord = _mix(color, _c(QPalette.ColorRole.Base), 0.6)
        self.setStyleSheet(
            f"border-radius:5px; padding:2px 6px; font-size:10px; font-weight:700;"
            f"color:{color.name()}; background:{bg.name()}; border:1px solid {bord.name()};"
        )


class AppCard(QFrame):
    """Clickable app card used in grid views."""
    clicked = pyqtSignal(dict)

    def __init__(self, app: dict):
        super().__init__()
        self.app = app
        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedSize(160, 190)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(6)

        self.icon_w = IconWidget(56)
        self.icon_w.set_icon_name(app.get("icon", ""))
        layout.addWidget(self.icon_w, alignment=Qt.AlignmentFlag.AlignHCenter)

        name_lbl = bold_font(QLabel(app.get("name", "")))
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setWordWrap(True)
        layout.addWidget(name_lbl)

        summary_lbl = dimmed(QLabel(app.get("summary", "")))
        summary_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        summary_lbl.setWordWrap(True)
        summary_lbl.setMaximumHeight(36)
        layout.addWidget(summary_lbl)
        layout.addStretch()

        installed = app.get("installed", False)
        source    = app.get("source", "native")
        if installed:
            badge = StatusBadge("Installed", col_success())
        elif source == "flatpak":
            badge = StatusBadge("Flatpak", _c(QPalette.ColorRole.Highlight))
        else:
            badge = StatusBadge("RPM", col_warning())
        layout.addWidget(badge)

    def enterEvent(self, e):
        p = self.palette()
        p.setColor(QPalette.ColorRole.Window, col_hover())
        self.setPalette(p)
        self.setAutoFillBackground(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.setPalette(QApplication.palette())
        self.setAutoFillBackground(False)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.app)


class FlowGrid(QWidget):
    """Wrapping grid of AppCards."""
    app_clicked = pyqtSignal(dict)

    def __init__(self, cols: int = 5):
        super().__init__()
        self._layout = QGridLayout(self)
        self._layout.setSpacing(12)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._cards: list[AppCard] = []
        self._cols = cols

    def set_apps(self, apps: list[dict]):
        self.clear()
        for i, app in enumerate(apps):
            self._add(app, i)

    def append_apps(self, apps: list[dict]):
        start = len(self._cards)
        for i, app in enumerate(apps):
            self._add(app, start + i)

    def _add(self, app: dict, idx: int):
        card = AppCard(app)
        card.clicked.connect(self.app_clicked)
        self._layout.addWidget(card, idx // self._cols, idx % self._cols)
        self._cards.append(card)

    def clear(self):
        for c in self._cards:
            c.deleteLater()
        self._cards = []


class TerminalWidget(QTextEdit):
    """Read-only terminal output widget for streaming install/update logs."""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setMaximumHeight(200)
        colored_text(self, col_success())
        self.hide()

    def append_line(self, line: str):
        self.show()
        self.append(line)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def reset(self):
        self.clear()
        self.hide()


class NavButton(QPushButton):
    """Sidebar navigation button with active state."""

    def __init__(self, icon_text: str, text: str):
        super().__init__(f"  {icon_text}  {text}")
        self.setObjectName("navbtn")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(38)

    def set_active(self, active: bool):
        from .theme import col_active_nav
        p = self.palette()
        if active:
            p.setColor(QPalette.ColorRole.ButtonText, _c(QPalette.ColorRole.Highlight))
            p.setColor(QPalette.ColorRole.Button, col_active_nav())
        else:
            p.setColor(QPalette.ColorRole.ButtonText, _c(QPalette.ColorRole.WindowText))
            p.setColor(QPalette.ColorRole.Button, Qt.GlobalColor.transparent)
        self.setPalette(p)
        self.setAutoFillBackground(active)
        self.update()


class SectionTitle(QLabel):
    """Bold section heading label."""

    def __init__(self, text: str):
        super().__init__(text)
        bold_font(self, extra_pts=2)


class LoadingWidget(QWidget):
    """Centered loading indicator."""

    def __init__(self, text: str = "Loading…"):
        super().__init__()
        l = QHBoxLayout(self)
        lbl = dimmed(QLabel(f"⏳  {text}"))
        l.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)


class LightboxDialog(QDialog):
    """Popup image viewer — round X button to close."""

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        container = QFrame()
        container.setFrameShape(QFrame.Shape.StyledPanel)
        container.setStyleSheet(
            "QFrame { background: rgba(0,0,0,200); border-radius: 14px; }"
        )
        cl = QVBoxLayout(container)
        cl.setContentsMargins(20, 12, 20, 20)
        cl.setSpacing(10)

        # Round X close button — top right
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedSize(32, 32)
        self._close_btn.setStyleSheet(
            "QPushButton {"
            "  border-radius: 16px;"
            "  background: rgba(255,255,255,0.15);"
            "  color: white; font-weight: bold; font-size: 14px; border: none;"
            "}"
            "QPushButton:hover { background: rgba(255,255,255,0.3); }"
        )
        self._close_btn.clicked.connect(self._do_close)
        btn_row.addWidget(self._close_btn)
        cl.addLayout(btn_row)

        img = QLabel()
        screen = QApplication.primaryScreen().size()
        scaled = pixmap.scaled(
            int(screen.width() * 0.55), int(screen.height() * 0.52),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        img.setPixmap(scaled)
        img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img.setStyleSheet("background: transparent; border: none;")
        cl.addWidget(img)

        outer.addWidget(container)

    def _do_close(self):
        self.done(0)

    def keyPressEvent(self, event):
        from PyQt6.QtCore import Qt as _Qt
        if event.key() == _Qt.Key.Key_Escape:
            self.done(0)
        else:
            super().keyPressEvent(event)



class ClickableImage(QLabel):
    """A QLabel that opens a LightboxDialog when clicked."""
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._full_pixmap = pixmap
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFrameShape(QFrame.Shape.StyledPanel)

    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                dlg = LightboxDialog(self._full_pixmap, self)
                dlg.exec()
        except Exception:
            pass
        super().mousePressEvent(event)

