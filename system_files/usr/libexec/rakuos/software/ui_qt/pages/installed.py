"""
pages/installed.py — Installed apps page.

Sections:
  - Native (Overlay RPMs)
  - Flatpak
  - AppImages
  - Web Apps
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QLabel,
)
from PyQt6.QtCore import pyqtSignal, Qt

from ..workers import Worker
from ..widgets import FlowGrid, SectionTitle, LoadingWidget, hline
from ..theme import dimmed
from backend import packages, flatpak, appimages, webapps


class InstalledPage(QWidget):
    app_clicked      = pyqtSignal(dict)
    appimage_clicked = pyqtSignal(dict)
    webapp_clicked   = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._workers: list[Worker] = []

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget()
        self._vl = QVBoxLayout(self._content)
        self._vl.setContentsMargins(24, 20, 24, 20)
        self._vl.setSpacing(16)
        scroll.setWidget(self._content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def load(self):
        self._clear()
        self._vl.addWidget(LoadingWidget())
        w = Worker(self._fetch)
        w.result.connect(self._on_data)
        w.start()
        self._workers.append(w)

    def _fetch(self) -> dict:
        return {
            "native":    packages.get_installed_with_metadata(),
            "flatpak":   flatpak.get_installed_flatpaks(),
            "appimages": appimages.get_installed(),
            "webapps":   webapps.get_installed(),
        }

    def _on_data(self, data: dict):
        self._clear()
        native    = data.get("native", [])
        fps       = data.get("flatpak", [])
        ais       = data.get("appimages", [])
        was       = data.get("webapps", [])
        any_installed = any([native, fps, ais, was])

        if native:
            self._vl.addWidget(SectionTitle("Native (Overlay)"))
            g = FlowGrid()
            g.set_apps(native)
            g.app_clicked.connect(self.app_clicked)
            self._vl.addWidget(g)

        if fps:
            if native:
                self._vl.addWidget(hline())
            self._vl.addWidget(SectionTitle("Flatpak"))
            g = FlowGrid()
            g.set_apps(fps)
            g.app_clicked.connect(self.app_clicked)
            self._vl.addWidget(g)

        if ais:
            if native or fps:
                self._vl.addWidget(hline())
            self._vl.addWidget(SectionTitle("AppImages"))
            # Tag each with source + badge info
            ai_apps = [dict(a, source="appimage") for a in ais]
            g = FlowGrid()
            g.set_apps(ai_apps)
            g.app_clicked.connect(self.appimage_clicked)
            self._vl.addWidget(g)

        if was:
            if native or fps or ais:
                self._vl.addWidget(hline())
            self._vl.addWidget(SectionTitle("Web Apps"))
            wa_apps = [dict(a, source="webapp") for a in was]
            g = FlowGrid()
            g.set_apps(wa_apps)
            g.app_clicked.connect(self.webapp_clicked)
            self._vl.addWidget(g)

        if not any_installed:
            self._vl.addStretch()
            self._vl.addWidget(
                dimmed(QLabel("No apps installed yet.")),
                alignment=Qt.AlignmentFlag.AlignCenter)
            self._vl.addStretch()
            return

        self._vl.addStretch()

    def _clear(self):
        while self._vl.count():
            i = self._vl.takeAt(0)
            if i.widget():
                i.widget().deleteLater()
