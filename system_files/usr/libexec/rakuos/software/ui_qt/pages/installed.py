"""
pages/installed.py — Installed apps page (native overlay + Flatpak).
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QLabel,
)
from PyQt6.QtCore import pyqtSignal, Qt

from ..workers import Worker
from ..widgets import FlowGrid, SectionTitle, LoadingWidget
from ..theme import dimmed
from backend import packages, flatpak


class InstalledPage(QWidget):
    app_clicked = pyqtSignal(dict)

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
        w = Worker(lambda: (
            packages.get_installed_with_metadata(),
            flatpak.get_installed_flatpaks(),
        ))
        w.result.connect(self._on_data)
        w.start()
        self._workers.append(w)

    def _on_data(self, data: tuple):
        native, fps = data
        self._clear()

        if native:
            self._vl.addWidget(SectionTitle("Native (Overlay)"))
            g = FlowGrid()
            g.set_apps(native)
            g.app_clicked.connect(self.app_clicked)
            self._vl.addWidget(g)

        if fps:
            self._vl.addWidget(SectionTitle("Flatpak"))
            g = FlowGrid()
            g.set_apps(fps)
            g.app_clicked.connect(self.app_clicked)
            self._vl.addWidget(g)

        if not native and not fps:
            self._vl.addWidget(
                dimmed(QLabel("No apps installed via overlay or Flatpak")),
                alignment=Qt.AlignmentFlag.AlignCenter,
            )

        self._vl.addStretch()

    def _clear(self):
        while self._vl.count():
            i = self._vl.takeAt(0)
            if i.widget():
                i.widget().deleteLater()
