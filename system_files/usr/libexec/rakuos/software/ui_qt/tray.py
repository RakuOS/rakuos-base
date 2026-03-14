"""
ui_qt/tray.py — RakuOS Software Center system tray icon.

KDE/Qt DEs: QSystemTrayIcon with passive hide when no updates,
            badge count when updates available.
GNOME:      No tray by default — runs silently, surfaces via
            notify-send notifications only (unless AppIndicator
            extension is installed, in which case tray works too).
"""

import os
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import Qt, QSize


def _badge_icon(count: int) -> QIcon:
    """Return tray icon with a red badge showing update count."""
    base = QIcon.fromTheme("system-software-update",
                           QIcon.fromTheme("software-update-available"))
    pix = base.pixmap(QSize(22, 22))
    if pix.isNull():
        pix = QPixmap(22, 22)
        pix.fill(Qt.GlobalColor.transparent)

    if count > 0:
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Badge circle
        badge_color = QColor("#e53935")
        painter.setBrush(badge_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(12, 0, 10, 10)
        # Badge count
        painter.setPen(QColor("white"))
        f = QFont()
        f.setPointSize(5)
        f.setBold(True)
        painter.setFont(f)
        label = str(count) if count < 100 else "!"
        painter.drawText(12, 0, 10, 10, Qt.AlignmentFlag.AlignCenter, label)
        painter.end()

    return QIcon(pix)


def _plain_icon() -> QIcon:
    """Return plain tray icon (no updates)."""
    icon = QIcon.fromTheme("system-software-update",
                           QIcon.fromTheme("applications-system"))
    if icon.isNull():
        icon = QIcon.fromTheme("package-manager")
    return icon


class RakuOSTray(QSystemTrayIcon):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._win = main_window
        self._update_count = 0

        self.setIcon(_plain_icon())
        self.setToolTip("RakuOS Software")

        # Build context menu
        menu = QMenu()
        self._show_action = menu.addAction("Show Software Center")
        self._show_action.triggered.connect(self._show_window)
        menu.addSeparator()
        self._updates_action = menu.addAction("No updates available")
        self._updates_action.setEnabled(False)
        menu.addSeparator()
        check_action = menu.addAction("Check for Updates")
        check_action.triggered.connect(self._check_updates)
        menu.addSeparator()
        quit_action = menu.addAction("Exit")
        quit_action.triggered.connect(QApplication.quit)
        self.setContextMenu(menu)

        # Always visible — main.py calls show() after construction
        # Single click shows window
        self.activated.connect(self._on_activated)
        self._kde = "kde" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower() or \
                    "plasma" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower()

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_window()

    def _show_window(self):
        self._win.show()
        self._win.raise_()
        self._win.activateWindow()

    def _check_updates(self):
        """Trigger an immediate update check via the daemon."""
        if hasattr(self._win, "_daemon"):
            self._win._daemon.check_now()

    def set_updates(self, count: int, summary: str = ""):
        """Called by daemon when update check completes."""
        self._update_count = count
        if count > 0:
            self.setIcon(_badge_icon(count))
            self.setToolTip(f"RakuOS Software — {count} update{'s' if count != 1 else ''} available")
            self._updates_action.setText(summary or f"{count} update{'s' if count != 1 else ''} available")
            self._updates_action.setEnabled(True)
        else:
            self.setIcon(_plain_icon())
            self.setToolTip("RakuOS Software — Up to date")
            self._updates_action.setText("No updates available")
            self._updates_action.setEnabled(False)
