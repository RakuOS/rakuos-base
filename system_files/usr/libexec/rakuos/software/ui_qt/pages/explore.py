"""
pages/explore.py — App grid page, driven by sidebar category selection.

Top-level categories with subcategories show:
  1. Subcat tiles (2-column grid)
  2. "Top Apps" section — first 12 apps in the category below the tiles

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
from ..theme import bold_font, dimmed, _c
from backend import packages

# ── Flathub popularity helpers (self-contained so no home.py dep) ─────────────

import json as _json
import os as _os
import urllib.request as _urllib

_CACHE_DIR      = _os.path.join(_os.path.expanduser("~"), ".cache", "rakuos")
_POP_CACHE      = _os.path.join(_CACHE_DIR, "flathub_popular.json")
_CAT_CACHE_TTL  = 6 * 3600


def _cache_valid(path: str, ttl: int = _CAT_CACHE_TTL) -> bool:
    try:
        return (_os.path.getmtime(path) + ttl) > __import__("time").time()
    except OSError:
        return False


def _fetch_app_installs(app_id: str) -> int:
    """Fetch total install count for one app from Flathub stats API."""
    try:
        req = _urllib.Request(
            f"https://flathub.org/api/v2/stats/{app_id}",
            headers={"User-Agent": "RakuOS-Software/1.0"})
        with _urllib.urlopen(req, timeout=5) as r:
            data = _json.loads(r.read())
        return data.get("installs_total", data.get("downloads_total", 0))
    except Exception:
        return 0


_CAT_CACHE_VERSION = 2   # bump to invalidate old unsorted caches


def _get_top_by_category(category: str, limit: int = 12) -> list:
    """
    Return top apps for a category sorted by Flathub install stats.
    Gets category apps from AppStream (local/fast), fetches stats only
    for the first batch of Flatpak candidates, caches result 6h.
    """
    cache_path = _os.path.join(_CACHE_DIR, f"cat_top_v{_CAT_CACHE_VERSION}_{category.lower()}.json")
    if _cache_valid(cache_path):
        try:
            return _json.loads(open(cache_path).read())[:limit]
        except Exception:
            pass

    # Get category apps — flatpaks first since they have stats
    fp_data  = packages.get_by_category(category, limit=40, offset=0, source="flatpak")
    rpm_data = packages.get_by_category(category, limit=20, offset=0, source="native")
    fp_apps  = fp_data.get("items", [])
    rpm_apps = rpm_data.get("items", [])

    # Score flatpak apps by install count (fetch up to 40)
    scored = []
    for app in fp_apps:
        app_id = app.get("id") or app.get("pkg_name", "")
        count  = _fetch_app_installs(app_id) if app_id else 0
        scored.append((count, app))
    scored.sort(key=lambda x: -x[0])
    sorted_fps = [app for _, app in scored]

    # RPMs sort to bottom (no stats)
    result = sorted_fps + rpm_apps

    try:
        _os.makedirs(_CACHE_DIR, exist_ok=True)
        open(cache_path, "w").write(_json.dumps(result))
        print(f"[explore] cached {len(result)} sorted apps for {category}")
    except Exception:
        pass
    return result[:limit]


# ── Subcategory tile ──────────────────────────────────────────────────────────

class SubcatTile(QFrame):
    """Clickable tile representing a subcategory — Discover style."""
    clicked = pyqtSignal(str, str)  # cat, label

    def __init__(self, label: str, cat: str):
        super().__init__()
        self._cat   = cat
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
    app_clicked    = pyqtSignal(dict)
    subcat_clicked = pyqtSignal(str, str)   # emitted when user picks a subcat tile

    # How many top apps to show below subcat tiles
    TOP_APPS_LIMIT = 12

    def __init__(self):
        super().__init__()
        self._offset = self._total = 0
        self._loading = False
        self._current_cat   = ""
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

        # ── Subcategory 2-column grid ─────────────────────────────────────────
        self._subcat_widget = QWidget()
        self._subcat_grid   = QGridLayout(self._subcat_widget)
        self._subcat_grid.setSpacing(10)
        self._subcat_widget.hide()
        self._vl.addWidget(self._subcat_widget)

        # ── Top Apps section (shown below subcats on top-level categories) ────
        self._top_section = QWidget()
        self._top_vl = QVBoxLayout(self._top_section)
        self._top_vl.setContentsMargins(0, 8, 0, 0)
        self._top_vl.setSpacing(8)
        self._top_section.hide()
        self._vl.addWidget(self._top_section)

        # ── App grid (leaf / subcategory views) ───────────────────────────────
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
        If provided → show subcat browser + top apps below.
        If None/empty → show app grid directly.
        """
        self._current_cat   = cat
        self._current_label = label
        self._title_lbl.setText(label)
        self._scroll.verticalScrollBar().setValue(0)

        if subcats:
            self._show_subcats(subcats)
        else:
            self._show_app_grid()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _abort_workers(self):
        for w in self._workers:
            try:
                w.quit()
                w.wait(200)
            except Exception:
                pass
        self._workers.clear()

    def _show_subcats(self, subcats: list):
        self._abort_workers()
        self._grid.hide()
        self._grid.clear()
        self._top_section.hide()
        self._clear_top_section()

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

        # Load top apps sorted by Flathub popularity
        cat   = self._current_cat
        limit = self.TOP_APPS_LIMIT

        def _fetch_top():
            try:
                items = _get_top_by_category(cat, limit)
            except Exception as e:
                print(f"[explore] get_top_by_category error: {e}")
                items = []
            try:
                total = packages.get_by_category(cat, 1, 0, "all").get("total", 0)
            except Exception as e:
                print(f"[explore] get total error: {e}")
                total = len(items)
            print(f"[explore] top apps for {cat!r}: {len(items)} items, total={total}")
            return {"items": items, "total": total}

        w = Worker(_fetch_top)
        w.result.connect(self._on_top_apps)
        w.error.connect(lambda e: print(f"[explore] worker error: {e}"))
        w.start()
        self._workers.append(w)

    def _clear_top_section(self):
        while self._top_vl.count():
            item = self._top_vl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_top_apps(self, data: dict):
        items = data.get("items", [])
        total = data.get("total", 0)
        print(f"[explore] _on_top_apps: {len(items)} items, total={total}")
        if not items:
            print("[explore] no items — top section not shown")
            return

        self._clear_top_section()

        # Header row: "Top Apps" + "See all →" button
        hdr = QHBoxLayout()
        sec = SectionTitle(f"Top {self._current_label} Apps")
        hdr.addWidget(sec)
        hdr.addStretch()
        if total > self.TOP_APPS_LIMIT:
            see_all = QPushButton(f"See all {total} →")
            see_all.setFlat(True)
            see_all.setStyleSheet("color: palette(highlight); font-size: 12px;")
            see_all.clicked.connect(self._show_app_grid)
            hdr.addWidget(see_all)
        hdr_w = QWidget()
        hdr_w.setLayout(hdr)
        self._top_vl.addWidget(hdr_w)

        # App grid with top apps
        top_grid = FlowGrid()
        top_grid.set_apps(items)
        top_grid.app_clicked.connect(self.app_clicked)
        self._top_vl.addWidget(top_grid)

        self._top_section.show()

    def _show_app_grid(self):
        self._abort_workers()
        self._subcat_widget.hide()
        self._top_section.hide()
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
        self._total  = data.get("total", 0)
        self._offset += len(items)
        self._loading = False
        if self._offset == len(items):
            self._grid.set_apps(items)
        else:
            self._grid.append_apps(items)

    def _on_scroll(self, value: int):
        if value >= self._scroll.verticalScrollBar().maximum() - 200:
            self._load_more()
