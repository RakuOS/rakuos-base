"""
pages/home.py — Home page with category sections.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
)
from PyQt6.QtCore import pyqtSignal

from ..workers import Worker
from ..widgets import FlowGrid, SectionTitle, LoadingWidget
from backend import packages


class HomePage(QWidget):
    app_clicked = pyqtSignal(dict)

    SECTIONS = [
        ("🎮 Games",   "Game"),
        ("🌐 Network", "Network"),
        ("🎵 Audio",   "AudioVideo"),
        ("🎬 Video",   "Video"),
    ]

    def __init__(self):
        super().__init__()
        self._workers: list[Worker] = []

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget()
        self._vl = QVBoxLayout(self._content)
        self._vl.setContentsMargins(24, 20, 24, 20)
        self._vl.setSpacing(24)
        scroll.setWidget(self._content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def load(self):
        self._clear()
        self._vl.addWidget(LoadingWidget())
        for title, cat in self.SECTIONS:
            w = Worker(packages.get_by_category, cat, 6, 0, "all")
            w.result.connect(lambda data, t=title: self._on_section(data, t))
            w.start()
            self._workers.append(w)

    def _on_section(self, data: dict, title: str):
        items = data.get("items", [])
        if not items:
            return
        # Remove loading widget on first result
        if self._vl.count() == 1:
            item = self._vl.itemAt(0)
            if item and isinstance(item.widget(), LoadingWidget):
                item.widget().deleteLater()
                self._vl.takeAt(0)

        wrapper = QWidget()
        vl = QVBoxLayout(wrapper)
        vl.setSpacing(10)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.addWidget(SectionTitle(title))
        grid = FlowGrid()
        grid.set_apps(items)
        grid.app_clicked.connect(self.app_clicked)
        vl.addWidget(grid)
        self._vl.insertWidget(self._vl.count(), wrapper)

    def _clear(self):
        while self._vl.count():
            i = self._vl.takeAt(0)
            if i.widget():
                i.widget().deleteLater()
