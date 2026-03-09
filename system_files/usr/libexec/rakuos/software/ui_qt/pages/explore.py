"""
pages/explore.py — App grid page, driven by sidebar category selection.
No chips — just a title + infinite-scroll grid.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QLabel,
)
from PyQt6.QtCore import pyqtSignal

from ..workers import Worker
from ..widgets import FlowGrid, SectionTitle
from backend import packages, flatpak


class ExplorePage(QWidget):
    app_clicked = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._offset = self._total = 0
        self._loading = False
        self._current_cat = ""
        self._current_label = ""
        self._workers: list[Worker] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        self._vl = QVBoxLayout(inner)
        self._vl.setContentsMargins(24, 20, 24, 20)
        self._vl.setSpacing(12)

        self._title_lbl = SectionTitle("")
        self._vl.addWidget(self._title_lbl)

        self._grid = FlowGrid()
        self._grid.app_clicked.connect(self.app_clicked)
        self._vl.addWidget(self._grid)
        self._vl.addStretch()

        scroll.setWidget(inner)
        scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._scroll = scroll
        outer.addWidget(scroll)

    def load_category(self, cat: str, label: str = ""):
        self._current_cat = cat
        self._current_label = label
        self._offset = self._total = 0
        self._loading = False
        self._grid.clear()
        self._title_lbl.setText(label)
        self._load_more()

    def _load_more(self):
        if self._loading or (self._offset > 0 and self._offset >= self._total):
            return
        self._loading = True
        cat = self._current_cat
        offset = self._offset
        w = Worker(packages.get_by_category, cat, 40, offset, "all")
        w.result.connect(self._on_apps)
        w.start()
        self._workers.append(w)

    def _on_apps(self, data: dict):
        items = data.get("items", [])
        self._total = data.get("total", 0)
        self._offset += len(items)
        self._loading = False
        if self._offset == len(items):
            self._grid.set_apps(items)
        else:
            self._grid.append_apps(items)

    def _on_scroll(self, value: int):
        if value >= self._scroll.verticalScrollBar().maximum() - 200:
            self._load_more()
