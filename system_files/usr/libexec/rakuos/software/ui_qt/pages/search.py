"""
pages/search.py — Search results page.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QLabel,
)
from PyQt6.QtCore import pyqtSignal, Qt

from ..workers import Worker
from ..widgets import FlowGrid, LoadingWidget
from ..theme import dimmed
from backend import packages, flatpak


class SearchPage(QWidget):
    app_clicked = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self._workers: list[Worker] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 16)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget()
        self._vl = QVBoxLayout(self._content)
        self._vl.setContentsMargins(0, 0, 0, 0)

        empty = dimmed(QLabel("Search for apps above"))
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._vl.addWidget(empty, alignment=Qt.AlignmentFlag.AlignCenter)
        self._vl.addStretch()

        scroll.setWidget(self._content)
        outer.addWidget(scroll)

    def search(self, query: str):
        self._clear()
        self._vl.addWidget(LoadingWidget(f'Searching "{query}"…'))
        w = Worker(lambda q=query: packages.search_packages(q) + flatpak.search_flatpaks(q))
        w.result.connect(self._on_results)
        w.start()
        self._workers.append(w)

    def _on_results(self, results: list[dict]):
        self._clear()
        if results:
            grid = FlowGrid()
            grid.set_apps(results)
            grid.app_clicked.connect(self.app_clicked)
            self._vl.addWidget(grid)
        else:
            self._vl.addWidget(
                dimmed(QLabel("No apps found")),
                alignment=Qt.AlignmentFlag.AlignCenter,
            )
        self._vl.addStretch()

    def _clear(self):
        while self._vl.count():
            i = self._vl.takeAt(0)
            if i.widget():
                i.widget().deleteLater()
