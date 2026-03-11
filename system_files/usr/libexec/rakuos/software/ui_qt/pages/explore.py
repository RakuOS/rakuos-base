"""
pages/explore.py — App grid page, driven by sidebar category selection.
Top-level categories with subcategories show a Discover-style subcat browser.
Subcategory / leaf clicks show the normal infinite-scroll app grid.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
    QLabel, QPushButton, QSizePolicy, QGridLayout,
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QPalette

from ..workers import Worker
from ..widgets import FlowGrid, SectionTitle
from ..theme import bold_font, _c
from backend import packages


# ── Subcategory tile ──────────────────────────────────────────────────────────

class SubcatTile(QFrame):
    """Clickable tile representing a subcategory — Discover style."""
    clicked = pyqtSignal(str, str)  # cat, label

    def __init__(self, label: str, cat: str):
        super().__init__()
        self._cat = cat
        self._label = label
        self.setFixedHeight(72)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        p = self.palette()
        bg_normal = p.color(QPalette.ColorRole.Base).name()
        bg_hover  = p.color(QPalette.ColorRole.AlternateBase).name()
        mid       = p.color(QPalette.ColorRole.Mid).name()

        self.setStyleSheet(f"""
            SubcatTile {{
                background: {bg_normal};
                border: 1px solid {mid};
                border-radius: 8px;
            }}
            SubcatTile:hover {{
                background: {bg_hover};
            }}
        """)

        hl = QHBoxLayout(self)
        hl.setContentsMargins(16, 8, 16, 8)

        name_lbl = bold_font(QLabel(label))
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        name_lbl.setStyleSheet("background: transparent;")

        arrow = QLabel("›")
        f = arrow.font(); f.setPointSize(f.pointSize() + 6); arrow.setFont(f)
        arrow.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        arrow.setStyleSheet("background: transparent;")

        hl.addWidget(name_lbl, stretch=1)
        hl.addWidget(arrow)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._cat, self._label)


# ── Main explore page ─────────────────────────────────────────────────────────

class ExplorePage(QWidget):
    app_clicked = pyqtSignal(dict)
    subcat_clicked = pyqtSignal(str, str)   # emitted when user picks a subcat tile

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

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self._inner = QWidget()
        self._vl = QVBoxLayout(self._inner)
        self._vl.setContentsMargins(24, 20, 24, 20)
        self._vl.setSpacing(12)

        self._title_lbl = SectionTitle("")
        self._vl.addWidget(self._title_lbl)

        # Subcategory 2-column grid (top-level categories)
        self._subcat_widget = QWidget()
        self._subcat_grid = QGridLayout(self._subcat_widget)
        self._subcat_grid.setSpacing(10)
        self._subcat_widget.hide()
        self._vl.addWidget(self._subcat_widget)

        # App grid (leaf / subcategory views)
        self._grid = FlowGrid()
        self._grid.app_clicked.connect(self.app_clicked)
        self._vl.addWidget(self._grid)

        self._vl.addStretch()
        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll)

    # ── Public API ────────────────────────────────────────────────────────────

    def load_category(self, cat: str, label: str = "",
                      subcats: list | None = None):
        """
        subcats: list of (label, cat) pairs from CATEGORY_TREE.
        If provided → show subcat browser.
        If None/empty → show app grid directly.
        """
        self._current_cat = cat
        self._current_label = label
        self._title_lbl.setText(label)
        self._scroll.verticalScrollBar().setValue(0)

        if subcats:
            self._show_subcats(subcats)
        else:
            self._show_app_grid()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _show_subcats(self, subcats: list):
        self._grid.hide()
        self._grid.clear()

        # Clear previous tiles
        while self._subcat_grid.count():
            item = self._subcat_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for i, (sub_label, sub_cat) in enumerate(subcats):
            tile = SubcatTile(sub_label, sub_cat)
            tile.clicked.connect(self._on_subcat_tile)
            self._subcat_grid.addWidget(tile, i // 2, i % 2)

        self._subcat_widget.show()
        self._offset = self._total = 0
        self._loading = False

    def _show_app_grid(self):
        self._subcat_widget.hide()
        self._grid.show()
        self._offset = self._total = 0
        self._loading = False
        self._grid.clear()
        self._load_more()

    def _on_subcat_tile(self, cat: str, label: str):
        self.subcat_clicked.emit(cat, label)

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
