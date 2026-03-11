"""
pages/home.py — Home page.
Sections: Editor's Picks, Popular Apps, Recently Updated, New Apps.
All loaded async so the page renders instantly and sections pop in.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
    QLabel, QPushButton, QSizePolicy,
)
from PyQt6.QtCore import pyqtSignal, Qt

from ..workers import Worker
from ..widgets import FlowGrid, SectionTitle, AppCard, LoadingWidget
from ..theme import dimmed, bold_font
from backend import packages, home as home_data


# ── Section header row (title + "See all →") ─────────────────────────────────

class SectionHeader(QWidget):
    see_all_clicked = pyqtSignal(str, str)   # cat, label

    def __init__(self, title: str, cat: str = "", label: str = ""):
        super().__init__()
        self._cat   = cat
        self._label = label
        hl = QHBoxLayout(self)
        hl.setContentsMargins(0, 0, 0, 0)

        title_lbl = SectionTitle(title)
        hl.addWidget(title_lbl)
        hl.addStretch()

        if cat:
            see_all = QPushButton("See all →")
            see_all.setFlat(True)
            see_all.setCursor(Qt.CursorShape.PointingHandCursor)
            see_all.clicked.connect(
                lambda: self.see_all_clicked.emit(self._cat, self._label)
            )
            hl.addWidget(see_all)


# ── Home page ─────────────────────────────────────────────────────────────────

class HomePage(QWidget):
    app_clicked     = pyqtSignal(dict)
    see_all_clicked = pyqtSignal(str, str)   # wired to main.py _on_category

    _SECTIONS = [
        # (key, title, emoji, cat_for_see_all, label_for_see_all)
        ("picks",   "⭐ Editor's Picks",    "",           ""),
        ("popular", "🔥 Popular Apps",      "",           ""),
        ("updated", "🔄 Recently Updated",  "",           ""),
        ("new",     "🆕 New Apps",          "",           ""),
    ]

    def __init__(self):
        super().__init__()
        self._workers: list[Worker] = []
        self._section_widgets: dict[str, QWidget] = {}
        self._pending = set()

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._content = QWidget()
        self._vl = QVBoxLayout(self._content)
        self._vl.setContentsMargins(24, 20, 24, 20)
        self._vl.setSpacing(28)
        scroll.setWidget(self._content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Public ────────────────────────────────────────────────────────────────

    def load(self):
        self._clear()
        self._pending.clear()

        # Add placeholder sections in order so they appear top-to-bottom
        for key, title, cat, label in self._SECTIONS:
            self._add_placeholder(key, title, cat, label)
            self._pending.add(key)

        self._vl.addStretch()

        # Fetch all section data in parallel
        self._fetch_section("picks",   home_data.get_picks)
        self._fetch_section("popular", home_data.get_popular)
        self._fetch_section("updated", home_data.get_recently_updated)
        self._fetch_section("new",     home_data.get_new_apps)

    # ── Section management ────────────────────────────────────────────────────

    def _add_placeholder(self, key: str, title: str, cat: str, label: str):
        """Add a section container with loading spinner — replaced when data arrives."""
        wrapper = QWidget()
        wrapper.setProperty("section_key", key)
        vl = QVBoxLayout(wrapper)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(10)

        header = SectionHeader(title, cat, label)
        header.see_all_clicked.connect(self.see_all_clicked)
        vl.addWidget(header)
        vl.addWidget(LoadingWidget())

        self._section_widgets[key] = wrapper
        self._vl.addWidget(wrapper)

    def _fetch_section(self, key: str, fn):
        w = Worker(fn)
        w.result.connect(lambda ids, k=key: self._on_ids(k, ids))
        w.start()
        self._workers.append(w)

    def _on_ids(self, key: str, app_ids: list):
        """App IDs received — resolve to full app dicts then render."""
        if not app_ids:
            self._replace_section(key, [])
            return
        # Resolve IDs against AppStream cache
        w = Worker(self._resolve_apps, app_ids)
        w.result.connect(lambda apps, k=key: self._replace_section(k, apps))
        w.start()
        self._workers.append(w)

    def _resolve_apps(self, app_ids: list, limit: int = 12) -> list:
        """Match Flathub app IDs against local AppStream cache."""
        appstream = packages._load_appstream()
        result = []
        seen = set()

        for app_id in app_ids:
            if len(result) >= limit:
                break
            clean_id = app_id.removesuffix(".desktop").lower()
            # Try exact match, then .desktop suffix variant
            match = None
            for key in (clean_id, clean_id + ".desktop",
                        app_id, app_id + ".desktop"):
                if key in appstream:
                    match = appstream[key]
                    break
            # Fallback: scan by id field
            if not match:
                for a in appstream.values():
                    aid = a.get("id", "").removesuffix(".desktop").lower()
                    if aid == clean_id:
                        match = a
                        break
            if match and match.get("id") not in seen:
                seen.add(match.get("id"))
                app = dict(match)
                app["installed"] = (
                    packages.is_installed_flatpak(app.get("pkg_name", ""))
                    if app.get("source") == "flatpak"
                    else packages.is_installed_native(app.get("pkg_name", ""))
                )
                result.append(app)

        return result

    def _replace_section(self, key: str, apps: list):
        """Replace the loading placeholder with actual app cards."""
        self._pending.discard(key)
        wrapper = self._section_widgets.get(key)
        if not wrapper:
            return

        vl = wrapper.layout()

        # Remove loading spinner (index 1)
        if vl.count() > 1:
            item = vl.itemAt(1)
            if item and item.widget():
                item.widget().deleteLater()
                vl.takeAt(1)

        if not apps:
            wrapper.hide()
            return

        grid = FlowGrid()
        grid.set_apps(apps)
        grid.app_clicked.connect(self.app_clicked)
        vl.addWidget(grid)

    def _clear(self):
        self._section_widgets.clear()
        while self._vl.count():
            i = self._vl.takeAt(0)
            if i.widget():
                i.widget().deleteLater()
