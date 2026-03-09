"""
pages/explore.py — Explore page with category chips and infinite scroll.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QHBoxLayout, QPushButton,
)
from PyQt6.QtCore import pyqtSignal

from ..workers import Worker
from ..widgets import FlowGrid
from backend import packages


class ExplorePage(QWidget):
    app_clicked = pyqtSignal(dict)

    CATEGORIES = [
        ("🎮 Games",       "Game"),
        ("🌐 Network",     "Network"),
        ("🎵 Audio",       "AudioVideo"),
        ("🎬 Video",       "Video"),
        ("📷 Graphics",    "Graphics"),
        ("💼 Office",      "Office"),
        ("🛠 Development", "Development"),
        ("🔧 System",      "System"),
        ("🎓 Education",   "Education"),
        ("♟ Strategy",     "Strategy"),
    ]

    def __init__(self):
        super().__init__()
        self._offset = self._total = 0
        self._loading = False
        self._current_cat = "Game"
        self._workers: list[Worker] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Category chip bar
        chip_scroll = QScrollArea()
        chip_scroll.setFixedHeight(52)
        chip_scroll.setFrameShape(QFrame.Shape.NoFrame)
        from PyQt6.QtCore import Qt
        chip_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        chip_w = QWidget()
        self._chip_row = QHBoxLayout(chip_w)
        self._chip_row.setContentsMargins(16, 8, 16, 8)
        self._chip_row.setSpacing(8)
        self._chip_btns: dict[str, QPushButton] = {}
        for lbl_text, cat in self.CATEGORIES:
            btn = QPushButton(lbl_text)
            btn.setCheckable(True)
            btn.setChecked(cat == self._current_cat)
            btn.setFlat(cat != self._current_cat)
            btn.clicked.connect(lambda checked, c=cat, b=btn: self._on_chip(c, b))
            self._chip_row.addWidget(btn)
            self._chip_btns[cat] = btn
        self._chip_row.addStretch()
        chip_scroll.setWidget(chip_w)
        chip_scroll.setWidgetResizable(True)
        outer.addWidget(chip_scroll)

        # App grid with infinite scroll
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        sc = QWidget()
        gl = QVBoxLayout(sc)
        gl.setContentsMargins(24, 16, 24, 16)
        self._grid = FlowGrid()
        self._grid.app_clicked.connect(self.app_clicked)
        gl.addWidget(self._grid)
        gl.addStretch()
        self._scroll.setWidget(sc)
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        outer.addWidget(self._scroll)

    def _on_chip(self, cat: str, btn: QPushButton):
        self._current_cat = cat
        for c, b in self._chip_btns.items():
            b.setFlat(c != cat)
            b.setChecked(c == cat)
        self.load_category(cat)

    def load_category(self, cat: str = None):
        if cat:
            self._current_cat = cat
        self._offset = self._total = 0
        self._grid.clear()
        self._loading = False
        self._load_more()

    def _load_more(self):
        if self._loading or (self._offset > 0 and self._offset >= self._total):
            return
        self._loading = True
        w = Worker(packages.get_by_category, self._current_cat, 40, self._offset, "all")
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
