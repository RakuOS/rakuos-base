"""
pages/detail.py — App detail page, Plasma Discover-style.
Screenshot carousel with prev/next arrows, hero header, description below.
"""

import os
import re
import subprocess

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
    QLabel, QPushButton, QToolButton, QMenu, QSizePolicy,
    QDialog, QProgressBar, QStackedWidget, QStackedLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QPalette, QCursor


# ── Distro name from /etc/os-release ─────────────────────────────────────────

def _read_os_release() -> str:
    """Return the distro name from /etc/os-release, e.g. 'RakuOS'."""
    for path in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            with open(path) as f:
                for line in f:
                    if line.startswith("NAME="):
                        return line.split("=", 1)[1].strip().strip('"\'')
        except OSError:
            continue
    return "Linux"

_DISTRO_NAME = _read_os_release()

from ..workers import Worker, StreamWorker, ImageLoader
from ..widgets import IconWidget, TerminalWidget, LightboxDialog, hline, StarRatingWidget, ReviewCard, WriteReviewDialog, AddonsDialog
from ..theme import dimmed, bold_font, colored_text, _c
from backend import packages, flatpak


class ScreenshotCarousel(QWidget):
    """
    Discover-style: one large screenshot at a time, overlaid prev/next arrows,
    dot indicators below. Click image to open lightbox.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmaps: list[QPixmap] = []
        self._index = 0
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(340)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # Image frame — arrows are children so they overlay
        self._img_frame = QWidget()
        self._img_frame.setFixedHeight(300)
        self._img_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._img_lbl = QLabel(self._img_frame)
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setGeometry(0, 0, 800, 300)
        self._img_lbl.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self._prev_btn = self._arrow("‹", self._img_frame)
        self._next_btn = self._arrow("›", self._img_frame)
        self._prev_btn.clicked.connect(self._prev)
        self._next_btn.clicked.connect(self._next)

        root.addWidget(self._img_frame)

        # Dot row
        dot_wrap = QWidget()
        self._dot_row = QHBoxLayout(dot_wrap)
        self._dot_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dot_row.setSpacing(8)
        self._dot_row.setContentsMargins(0, 0, 0, 0)
        root.addWidget(dot_wrap)

        self.hide()

    def _arrow(self, text: str, parent: QWidget) -> QPushButton:
        btn = QPushButton(text, parent)
        btn.setFixedSize(44, 44)
        btn.setStyleSheet(
            "QPushButton {"
            "  border-radius:22px;"
            "  background:rgba(30,30,30,0.55);"
            "  color:white; font-size:24px; font-weight:bold; border:none;"
            "}"
            "QPushButton:hover{background:rgba(30,30,30,0.82);}"
            "QPushButton:disabled{background:rgba(30,30,30,0.18); color:rgba(255,255,255,0.25);}"
        )
        return btn

    # ── resize: reflow image label and arrow positions ────────────────────────

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reflow()

    def _reflow(self):
        w = self._img_frame.width()
        h = self._img_frame.height()
        self._img_lbl.setGeometry(0, 0, w, h)
        cy = (h - 44) // 2
        self._prev_btn.move(14, cy)
        self._next_btn.move(w - 58, cy)
        self._paint_current()

    # ── public ────────────────────────────────────────────────────────────────

    def add_pixmap(self, pixmap: QPixmap):
        self._pixmaps.append(pixmap)
        dot = QLabel("●")
        dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dot_row.addWidget(dot)
        if len(self._pixmaps) == 1:
            self._index = 0
            self.show()
        self._refresh()

    def clear(self):
        self._pixmaps.clear()
        self._index = 0
        while self._dot_row.count():
            item = self._dot_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._img_lbl.clear()
        self.hide()

    # ── internal ──────────────────────────────────────────────────────────────

    def _prev(self):
        if self._index > 0:
            self._index -= 1
            self._refresh()

    def _next(self):
        if self._index < len(self._pixmaps) - 1:
            self._index += 1
            self._refresh()

    def _refresh(self):
        n = len(self._pixmaps)
        self._prev_btn.setVisible(n > 1)
        self._next_btn.setVisible(n > 1)
        self._prev_btn.setEnabled(self._index > 0)
        self._next_btn.setEnabled(self._index < n - 1)
        self._paint_current()
        self._refresh_dots()

    def _paint_current(self):
        if not self._pixmaps:
            return
        w = max(self._img_lbl.width(), 200)
        h = max(self._img_lbl.height(), 100)
        pix = self._pixmaps[self._index].scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._img_lbl.setPixmap(pix)

    def _refresh_dots(self):
        accent = _c(QPalette.ColorRole.Highlight).name()
        dim    = _c(QPalette.ColorRole.PlaceholderText).name()
        for i in range(self._dot_row.count()):
            w = self._dot_row.itemAt(i).widget()
            if w:
                c = accent if i == self._index else dim
                w.setStyleSheet(f"font-size:10px; color:{c};")

    def mousePressEvent(self, e):
        try:
            if e.button() == Qt.MouseButton.LeftButton and self._pixmaps:
                dlg = LightboxDialog(self._pixmaps[self._index], self)
                dlg.exec()
        except Exception:
            pass
        super().mousePressEvent(e)


# ── Main detail page ──────────────────────────────────────────────────────────

class AppDetailPage(QWidget):
    back_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._workers: list = []
        self._app: dict = {}
        self._native: dict | None = None
        self._flatpak_app: dict | None = None
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top action bar (Discover-style) ──────────────────────────────────
        back_bar = QFrame()
        back_bar.setObjectName("topbar")
        back_bar.setFixedHeight(48)
        back_bar.setFrameShape(QFrame.Shape.StyledPanel)
        bl = QHBoxLayout(back_bar)
        bl.setContentsMargins(12, 0, 12, 0)
        bl.setSpacing(6)

        back_btn = QPushButton("← Back")
        back_btn.setFixedWidth(80)
        back_btn.setFlat(True)
        back_btn.clicked.connect(self.back_requested)
        bl.addWidget(back_btn)
        bl.addStretch()

        # Add-ons button (hidden until addons are found)
        self._addons_btn = QPushButton("🧩  Add-ons")
        self._addons_btn.setFlat(True)
        self._addons_btn.setFixedHeight(32)
        self._addons_btn.hide()
        self._addons_btn.clicked.connect(self._show_addons_dialog)
        bl.addWidget(self._addons_btn)

        # _bl is the top bar layout — _render_actions inserts button/dropdown here
        self._bl = bl

        root.addWidget(back_bar)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        self._vl = QVBoxLayout(content)
        self._vl.setContentsMargins(28, 22, 28, 24)
        self._vl.setSpacing(0)

        # ── Hero (matches Discover layout) ────────────────────────────────────
        hero = QHBoxLayout()
        hero.setSpacing(20)
        hero.setContentsMargins(0, 0, 0, 18)

        self._icon = IconWidget(80)
        hero.addWidget(self._icon, alignment=Qt.AlignmentFlag.AlignTop)

        # Left: name / summary / author / meta links
        left = QVBoxLayout()
        left.setSpacing(3)

        self._name_lbl = bold_font(QLabel(), extra_pts=6)
        self._name_lbl.setWordWrap(True)
        left.addWidget(self._name_lbl)

        self._summary_lbl = dimmed(QLabel())
        self._summary_lbl.setWordWrap(True)
        left.addWidget(self._summary_lbl)
        self._star_widget = StarRatingWidget()
        left.addWidget(self._star_widget)

        left.addSpacing(8)
        self._meta_row = QHBoxLayout()
        self._meta_row.setSpacing(6)
        self._meta_row.setContentsMargins(0, 0, 0, 0)
        left.addLayout(self._meta_row)

        hero.addLayout(left, stretch=1)

        # Right: version/size info block (actions moved to top bar)
        right = QVBoxLayout()
        right.setSpacing(6)
        right.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        self._info_block = QVBoxLayout()
        self._info_block.setSpacing(2)
        right.addLayout(self._info_block)

        hero.addLayout(right)
        self._vl.addLayout(hero)
        self._vl.addWidget(hline())
        self._vl.addSpacing(20)

        # ── Screenshot carousel ───────────────────────────────────────────────
        self._carousel = ScreenshotCarousel()
        self._vl.addWidget(self._carousel)
        self._vl.addSpacing(24)

        # ── Description ───────────────────────────────────────────────────────
        self._desc_head = bold_font(QLabel("About this app"), extra_pts=1)
        self._desc_head.hide()
        self._vl.addWidget(self._desc_head)
        self._vl.addSpacing(6)

        self._desc = QLabel()
        self._desc.setWordWrap(True)
        self._desc.setTextFormat(Qt.TextFormat.PlainText)
        self._desc.hide()
        self._vl.addWidget(self._desc)
        self._vl.addSpacing(24)

        # ── Bottom info cards ─────────────────────────────────────────────────
        self._cards_row = QHBoxLayout()
        self._cards_row.setSpacing(12)
        self._vl.addLayout(self._cards_row)
        self._vl.addSpacing(16)

        # ── Terminal (hidden — output goes to progress bar only) ──────────────
        self._terminal = TerminalWidget()
        self._terminal.hide()
        # not added to _vl — detail page has no visible terminal output

        # ── Reviews ───────────────────────────────────────────────────────────
        reviews_head_row = QHBoxLayout()
        self._reviews_head = bold_font(QLabel("Reviews"), extra_pts=1)
        self._reviews_head.hide()
        reviews_head_row.addWidget(self._reviews_head)
        reviews_head_row.addStretch()
        self._write_review_btn = QPushButton("✏  Write a Review")
        self._write_review_btn.setFlat(True)
        self._write_review_btn.hide()
        self._write_review_btn.clicked.connect(self._on_write_review)
        reviews_head_row.addWidget(self._write_review_btn)
        self._vl.addLayout(reviews_head_row)
        self._vl.addSpacing(8)

        self._reviews_container = QVBoxLayout()
        self._reviews_container.setSpacing(10)
        self._vl.addLayout(self._reviews_container)

        # ── Pagination bar ─────────────────────────────────────────────────
        self._review_page = 0
        self._review_page_size = 5
        self._review_data: list = []

        pag_row = QHBoxLayout()
        self._rev_prev_btn = QPushButton("← Previous")
        self._rev_next_btn = QPushButton("Next →")
        self._rev_page_label = QLabel()
        for b in (self._rev_prev_btn, self._rev_next_btn):
            b.setFlat(True)
            b.hide()
        self._rev_page_label.hide()
        self._rev_prev_btn.clicked.connect(self._reviews_prev)
        self._rev_next_btn.clicked.connect(self._reviews_next)
        pag_row.addStretch()
        pag_row.addWidget(self._rev_prev_btn)
        pag_row.addWidget(self._rev_page_label)
        pag_row.addWidget(self._rev_next_btn)
        pag_row.addStretch()
        self._vl.addLayout(pag_row)

        self._vl.addStretch()

    # ── Public ────────────────────────────────────────────────────────────────

    def load_app(self, app: dict):
        self._app = app
        import logging
        logging.debug("load_app: id=%r pkg_name=%r name=%r source=%r",
                      app.get("id"), app.get("pkg_name"), app.get("name"), app.get("source"))
        self._native = self._flatpak_app = None
        self._terminal.reset()
        self._carousel.clear()
        self._clear_action_widgets()
        for layout in (self._meta_row, self._info_block, self._cards_row,
                       self._reviews_container):
            self._clear_layout(layout)
        self._star_widget.set_rating(0, 0)
        self._reviews_head.hide()
        self._write_review_btn.hide()
        self._addons_btn.hide()
        self._addons = []  # reset stored addons
        self._review_page = 0
        self._review_data = []
        self._rev_prev_btn.hide()
        self._rev_next_btn.hide()
        self._rev_page_label.hide()

        # ── webapp / appimage short-circuit — use simple action rendering ──────
        if app.get("source") == "webapp":
            self._load_webapp(app)
            return

        self._name_lbl.setText(app.get("name", ""))
        self._summary_lbl.setText(app.get("summary", ""))
        self._icon.set_icon_name(app.get("icon", ""), app_id=app.get("id", ""), pkg_name=app.get("pkg_name", ""), flatpak_id=app.get("flatpak_id", ""))

        desc = app.get("description", "")
        self._desc.setText(desc)
        self._desc.setVisible(bool(desc))
        self._desc_head.setVisible(bool(desc))

        self._render_basic_actions(app)

        for url in (app.get("screenshots") or [])[:8]:
            ldr = ImageLoader(url)
            ldr.loaded.connect(self._on_screenshot)
            ldr.start()
            self._workers.append(ldr)

        w = Worker(self._fetch_detail, app)
        w.result.connect(self._on_detail)
        w.start()
        self._workers.append(w)

        # Load reviews + addons in parallel
        app_id = app.get("id", app.get("pkg_name", ""))
        w2 = Worker(self._fetch_reviews, app_id)
        w2.result.connect(self._on_reviews)
        w2.start()
        self._workers.append(w2)

        w3 = Worker(self._fetch_addons, app_id)
        w3.result.connect(self._on_addons)
        w3.start()
        self._workers.append(w3)

    # ── Fetching ──────────────────────────────────────────────────────────────

    def _fetch_detail(self, app: dict) -> dict:
        # Local .rpm — no AppStream lookup needed, use metadata as-is
        if app.get("local_rpm"):
            return {"native": app, "flatpak": None, "urls": {
                "homepage": app.get("url", ""), "donation": "",
                "bugtracker": "", "help": "",
            }}

        if app.get("local_flatpak") or app.get("local_flatpakref"):
            return {"native": None, "flatpak": app, "urls": {
                "homepage": app.get("url", ""), "donation": "",
                "bugtracker": "", "help": "",
            }}

        appstream = packages._load_appstream()
        name_lower = app.get("name", "").lower()
        app_id = app.get("id", "")
        pkg_name = app.get("pkg_name", "")
        native = fp = None

        # Pass 1: exact ID match (most reliable, avoids addon collisions)
        for a in appstream.values():
            if a.get("is_addon"):
                continue
            if a["source"] == "native" and a["id"] == app_id:
                native = packages._enrich_installed(a)
            if a["source"] == "flatpak" and a["id"] == app_id:
                fp = packages._enrich_installed(a)

        # Pass 2: pkg_name / name match — only if pass 1 found nothing
        # Exclude addons; skip entries with guessed pkg_name that aren't repo-verified
        if not native:
            candidates = []
            for a in appstream.values():
                if a["source"] != "native" or a.get("is_addon"):
                    continue
                # Skip guessed pkg_names — they may not exist in repos
                if a.get("pkg_name_guessed") and not packages.pkg_exists_in_repos(a["pkg_name"]):
                    continue
                score = 0
                if a["pkg_name"] == pkg_name:
                    score += 2
                if a["name"].lower() == name_lower:
                    score += 1
                if score:
                    candidates.append((score, a))
            if candidates:
                candidates.sort(key=lambda x: -x[0])
                native = packages._enrich_installed(candidates[0][1])

        if not fp:
            for a in appstream.values():
                if a["source"] != "flatpak" or a.get("is_addon"):
                    continue
                if (a["name"].lower() == name_lower
                        or a["id"].split(".")[-1].lower() == pkg_name.lower()):
                    fp = packages._enrich_installed(a)
                    break

        # Inject origin from installed flatpak list — AppStream doesn't carry it
        if fp and not fp.get("origin"):
            installed_fps = {f["id"]: f for f in flatpak.get_installed_flatpaks()}
            match = installed_fps.get(fp.get("id", ""))
            if match:
                fp["origin"] = match.get("origin", "")
            elif app.get("origin"):
                fp["origin"] = app["origin"]
            else:
                # Not installed yet — use first enabled remote name
                remotes = [r for r in flatpak.get_remotes() if r.get("enabled", True)]
                if remotes:
                    fp["origin"] = remotes[0]["name"]

        # If we only have a Flatpak, check whether a native RPM also exists
        if fp and not native:
            native = packages.find_native_counterpart(fp)

        # If we have a pkg_name but no native AppStream entry at all,
        # borrow the Flatpak's rich metadata (name, icon, description) for display
        # while keeping native install mechanics
        if not native and pkg_name and fp and packages.pkg_exists_in_repos(pkg_name):
            native = dict(fp)
            native["source"] = "native"
            native["pkg_name"] = pkg_name
            native["id"] = pkg_name
            native["installed"] = packages.is_installed_native(pkg_name)
            native.pop("origin", None)
            native.pop("remote", None)

        import logging
        logging.debug("_fetch_detail result: native=%r fp=%r",
                      native.get("id") if native else None,
                      fp.get("id") if fp else None)

        urls = {k: "" for k in ("homepage", "donation", "bugtracker", "help")}
        import gzip, xml.etree.ElementTree as ET
        for appstream_dir, _ in packages.APPSTREAM_DIRS:
            if not os.path.isdir(appstream_dir):
                continue
            for fname in os.listdir(appstream_dir):
                fpath = os.path.join(appstream_dir, fname)
                try:
                    if fname.endswith(".gz"):
                        fh = gzip.open(fpath, "rt", encoding="utf-8", errors="ignore")
                    elif fname.endswith(".xml"):
                        fh = open(fpath, "rt", encoding="utf-8", errors="ignore")
                    else:
                        continue
                    root = ET.parse(fh).getroot()
                    fh.close()
                    comps = [root] if root.tag == "component" else root.findall("component")
                    found = False
                    for comp in comps:
                        cid = (comp.findtext("id") or "").strip()
                        if cid == app_id or (comp.findtext("name") or "").lower() == name_lower:
                            for u in comp.findall("url"):
                                ut = u.get("type", "")
                                if ut in urls and u.text:
                                    urls[ut] = u.text.strip()
                            found = True
                            break
                    if found:
                        break
                except Exception:
                    continue

        return {"native": native, "flatpak": fp, "urls": urls}

    def _on_detail(self, data: dict):
        self._native = data.get("native")
        self._flatpak_app = data.get("flatpak")
        self._render_actions(self._native, self._flatpak_app)
        self._render_meta(data["urls"])
        self._render_info_block(self._native, self._flatpak_app)
        self._render_cards(self._native, self._flatpak_app)

        # Fire a second worker to fetch version/size/license (may need repoquery)
        app_for_detail = self._native or self._flatpak_app
        if app_for_detail and not app_for_detail.get("local_rpm") \
                and not app_for_detail.get("local_flatpak") \
                and not app_for_detail.get("local_flatpakref"):
            w = Worker(self._fetch_detail_info, app_for_detail)
            w.result.connect(self._on_detail_info)
            self._workers.append(w)
            w.start()

    def _fetch_detail_info(self, app: dict) -> dict:
        """Background: enrich a single app dict with version/size/license."""
        native = packages._enrich_detail(app) if app.get("source") == "native" else None
        fp     = packages._enrich_detail(app) if app.get("source") == "flatpak" else None
        return {"native": native, "fp": fp}

    def _on_detail_info(self, data: dict):
        """Update info block once version/size/license have been fetched."""
        native = data.get("native")
        fp     = data.get("fp")
        if native:
            self._native = native
        if fp:
            self._flatpak_app = fp
        self._render_info_block(self._native, self._flatpak_app)

    # ── Screenshots ───────────────────────────────────────────────────────────

    def _on_screenshot(self, pixmap: QPixmap, key: str):
        if not pixmap.isNull():
            self._carousel.add_pixmap(pixmap)

    # ── Top-right info block (version, size, license — like Discover) ─────────

    @staticmethod
    def _clean_license(raw: str) -> str:
        """Simplify Fedora SPDX license expressions for display."""
        # Strip Fedora-specific LicenseRef-Callaway- prefix
        cleaned = re.sub(r"LicenseRef-Callaway-", "", raw)
        # Strip version suffixes appended after + e.g. "GPL-2.0-or-later+143.0.4-1.fc43"
        cleaned = re.sub(r"\+[\d][\w.\-]*", "", cleaned)
        # Collapse multiple spaces
        cleaned = re.sub(r"  +", " ", cleaned).strip()
        return cleaned

    def _render_info_block(self, native: dict | None, fp: dict | None):
        self._clear_layout(self._info_block)
        base = native or fp or {}
        rows = []
        if base.get("version"):
            rows.append(("Version", base["version"]))
        if base.get("size"):
            mb = base["size"] / (1024 * 1024)
            rows.append(("Size", f"{mb:.1f} MiB"))
        if base.get("license"):
            rows.append(("License", self._clean_license(base["license"])))
        for label, value in rows:
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl = dimmed(QLabel(f"{label}:"))
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            lbl.setFixedWidth(60)
            val = bold_font(QLabel(value))
            val.setWordWrap(True)
            val.setMaximumWidth(260)
            row.addWidget(lbl)
            row.addWidget(val)
            self._info_block.addLayout(row)

    # ── Install actions ───────────────────────────────────────────────────────
    #
    # Single source:  [ Install from RakuOS ]   or   [ Install from flathub ]
    #                 (no dropdown)
    #
    # Multiple sources:
    #   [ Install ] [ ▾ ]   ← dropdown selects source, button acts on selection
    #   [ Remove  ] [ ▾ ]   ← if selected source is installed
    #
    # Dropdown items show source names only (no action verbs) — selecting
    # one updates the button text to Install/Remove depending on that
    # source's installed state. The button always acts on the current selection.

    def _source_label(self, app: dict) -> str:
        """Human-readable source label: distro name for native, remote name for Flatpak."""
        if app.get("source") == "flatpak":
            raw = app.get("remote") or app.get("origin") or "Flatpak"
            # Title-case each word: "flathub" → "Flathub", "fedora-flatpaks" → "Fedora-Flatpaks"
            return "-".join(w.capitalize() for w in raw.replace("-", " - ").split())
        return _DISTRO_NAME

    def _render_basic_actions(self, app: dict):
        """Single source — plain button only, no dropdown."""
        self._clear_action_widgets()
        self._selected_app = app
        installed = app.get("installed", False)
        btn_text = "Remove" if installed else "Install"
        self._action_stack = self._make_action_stack(
            btn_text, square_right=False, is_remove=installed
        )
        self._action_stack.clicked.connect(self._on_action_clicked)
        self._bl.addWidget(self._action_stack)

    def _render_actions(self, native: dict | None, fp: dict | None):
        self._clear_action_widgets()

        if native and fp:
            # Build ordered source list — installed source first, else native first
            sources: list[dict] = []
            if native.get("installed"):
                sources = [native, fp]
            elif fp.get("installed"):
                sources = [fp, native]
            else:
                sources = [native, fp]

            # Default selection = first in list
            self._selected_app = sources[0]

            # Main action button — added directly to _actions, no wrapper
            self._action_stack = self._make_action_stack(
                self._btn_text_for(self._selected_app),
                square_right=False,
                is_remove=self._selected_app.get("installed", False),
            )
            self._action_stack.clicked.connect(self._on_action_clicked)
            self._bl.addWidget(self._action_stack)

            # Source selector — directly adjacent, no wrapper
            default_label = self._source_label(self._selected_app)
            self._source_btn = QToolButton()
            self._source_btn.setText(f"{default_label}  ▾")
            self._source_btn.setFixedHeight(32)
            self._source_btn.setMinimumWidth(90)
            self._source_btn.setStyleSheet(
                "QToolButton {"
                "  border-radius: 4px;"
                "  border: 1px solid rgba(255,255,255,0.2);"
                "  padding: 0 10px; font-weight: 600; font-size: 12px;"
                "  background: rgba(255,255,255,0.08);"
                "}"
                "QToolButton:hover { background: rgba(255,255,255,0.14); }"
                "QToolButton::menu-indicator { image: none; }"
            )
            self._source_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

            menu = QMenu(self._source_btn)
            for src in sources:
                lbl = self._source_label(src)
                installed_marker = "  ✓" if src.get("installed") else ""
                act = menu.addAction(f"{lbl}{installed_marker}")
                act.triggered.connect(
                    lambda chk=False, s=src: self._select_source(s)
                )
            self._source_btn.setMenu(menu)
            self._bl.addWidget(self._source_btn)

        elif native or fp:
            app = native or fp
            self._render_basic_actions(app)
            return

    def _btn_text_for(self, app: dict) -> str:
        """'Remove' if app is installed, 'Install' if multiple sources, else 'Install from X'."""
        return "Remove" if app.get("installed") else "Install"

    def _apply_btn_state(self, stack: "QWidget", app: dict):
        """Update button text, colours and bar colour for current app state."""
        is_remove = app.get("installed", False)
        sq = getattr(stack, "_square_right", False)
        stack._btn.setText("Remove" if is_remove else "Install")
        stack._btn.setStyleSheet(self._btn_style(is_remove, sq))
        stack._bar.setStyleSheet(self._bar_style(is_remove, sq))
        stack._is_remove = is_remove  # type: ignore[attr-defined]

    def _select_source(self, app: dict):
        """Called when user picks a source from the dropdown — updates button, no install."""
        self._selected_app = app
        if hasattr(self, "_action_stack") and self._action_stack:
            self._apply_btn_state(self._action_stack, app)
        if hasattr(self, "_source_btn") and self._source_btn:
            self._source_btn.setText(f"{self._source_label(app)}  ▾")

    def _on_action_clicked(self):
        """Called when the main Install/Remove button is clicked."""
        app = getattr(self, "_selected_app", None)
        if app is None:
            return
        if app.get("installed"):
            self._do_remove(app)
        else:
            self._do_install(app)

    # ── Colour helpers ────────────────────────────────────────────────────────
    _GREEN      = "#2ecc71"
    _GREEN_DARK = "#27ae60"
    _GREEN_TXT  = "#ffffff"
    _RED        = "#e74c3c"
    _RED_DARK   = "#c0392b"
    _RED_TXT    = "#ffffff"

    def _btn_style(self, is_remove: bool, square_right: bool = False) -> str:
        bg     = self._RED        if is_remove else self._GREEN
        hover  = self._RED_DARK   if is_remove else self._GREEN_DARK
        fg     = self._RED_TXT    if is_remove else self._GREEN_TXT
        r      = "border-top-right-radius:0;border-bottom-right-radius:0;" if square_right else ""
        return (
            f"QPushButton {{ background:{bg}; color:{fg}; border:none; {r}"
            f"  border-radius:4px; padding:0 14px; font-weight:600; font-size:12px; }}"
            f"QPushButton:hover {{ background:{hover}; }}"
            f"QPushButton:pressed {{ background:{hover}; }}"
        )

    def _bar_style(self, is_remove: bool, square_right: bool = False) -> str:
        bg    = self._RED        if is_remove else self._GREEN
        chunk = self._RED_DARK   if is_remove else self._GREEN_DARK
        r     = "border-top-right-radius:0;border-bottom-right-radius:0;" if square_right else ""
        return (
            f"QProgressBar {{ border-radius:4px; {r} border:none;"
            f"  text-align:center; font-size:10px; font-weight:600;"
            f"  color:#ffffff; background:rgba(0,0,0,0.15); }}"
            f"QProgressBar::chunk {{ border-radius:3px; {r} background:{chunk}; }}"
        )

    def _make_action_stack(self, btn_text: str,
                           square_right: bool = False,
                           is_remove: bool = False) -> "QWidget":
        """
        Plain QWidget with QStackedLayout — zero margin, no frame.
        Page 0: solid colour button. Page 1: matching progress bar.
        Green for install, red for remove. Progress driven by _on_stream_line().
        """
        container = QWidget()
        container.setFixedHeight(32)
        container.setFixedWidth(110)
        container.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        layout = QStackedLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setStackingMode(QStackedLayout.StackingMode.StackOne)

        # ── Page 0: action button ─────────────────────────────────────────────
        btn = QPushButton(btn_text)
        btn.setFixedHeight(32)
        btn.setFixedWidth(110)
        btn.setDefault(True)
        btn.setStyleSheet(self._btn_style(is_remove, square_right))
        layout.addWidget(btn)

        # ── Page 1: progress bar ──────────────────────────────────────────────
        bar = QProgressBar()
        bar.setFixedHeight(32)
        bar.setFixedWidth(110)
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(True)
        bar.setFormat("Starting…")
        bar.setStyleSheet(self._bar_style(is_remove, square_right))
        layout.addWidget(bar)

        layout.setCurrentIndex(0)

        container.clicked       = btn.clicked       # type: ignore[attr-defined]
        container._btn          = btn               # type: ignore[attr-defined]
        container._bar          = bar               # type: ignore[attr-defined]
        container._layout       = layout            # type: ignore[attr-defined]
        container._is_remove    = is_remove         # type: ignore[attr-defined]
        container._square_right = square_right      # type: ignore[attr-defined]
        return container

    # ── Progress parsing ──────────────────────────────────────────────────────

    _PROGRESS_PHASES = [
        # (regex, pct_estimate, short_label)
        (r'updating.*repositor|loading repositor',   5,  "Loading repos…"),
        (r'repositories loaded',                     10, "Repos loaded"),
        (r'resolv',                                  15, "Resolving…"),
        (r'looking for match|found.*ref',             8, "Searching…"),
        (r'\[rakuos\].*install',                     10, "Installing…"),
        (r'downloading',                             20, "Downloading…"),
        (r'running transaction|applying.*change',    75, "Applying…"),
        (r'verif',                                   82, "Verifying…"),
        (r'scriptlet',                               88, "Running scripts…"),
        (r'cleanup',                                 92, "Cleaning up…"),
        (r'install.*complet|changes complet|^installed:', 95, "Finishing…"),
        (r'remov.*complet|^removed:',                95, "Finishing…"),
    ]

    def _parse_progress(self, line: str) -> "tuple[int|None, str|None]":
        import re
        # Explicit % — flatpak progress bar or dnf download
        m = re.search(r'(\d{1,3})\s*%', line)
        if m:
            pct = min(int(m.group(1)), 99)
            label = f"Downloading… {pct}%" if re.search(r'[Dd]ownload', line) else f"{pct}%"
            return pct, label
        # DNF fraction  e.g. "Verifying   : pkg  3/10"
        m = re.search(r'\b(\d+)/(\d+)\b', line)
        if m:
            num, den = int(m.group(1)), int(m.group(2))
            if 0 < num <= den:
                pct = min(int(num / den * 100), 99)
                return pct, f"{num}/{den}"
        # Named phases
        lower = line.lower()
        for pattern, pct, label in self._PROGRESS_PHASES:
            if re.search(pattern, lower):
                return pct, label
        return None, None

    def _on_stream_line(self, line: str):
        """Route each output line → terminal + progress bar."""
        self._terminal.append_line(line)
        if not hasattr(self, "_action_stack") or self._action_stack is None:
            return
        if self._action_stack._layout.currentIndex() != 1:
            return
        pct, label = self._parse_progress(line)
        if pct is not None:
            bar = self._action_stack._bar
            if pct > bar.value():
                bar.setValue(pct)
            if label:
                bar.setFormat(label)

    # ── Progress bar show/hide ────────────────────────────────────────────────

    def _set_action_progress(self, active: bool, text: str = ""):
        if not hasattr(self, "_action_stack") or self._action_stack is None:
            return
        stack = self._action_stack
        if active:
            stack._bar.setValue(0)
            stack._bar.setFormat(text or "Starting…")
            is_remove = getattr(stack, "_is_remove", False)
            sq = getattr(stack, "_square_right", False)
            stack._bar.setStyleSheet(self._bar_style(is_remove, sq))
            stack._layout.setCurrentIndex(1)
        else:
            if text:
                stack._btn.setText(text)
            stack._bar.setValue(0)
            stack._layout.setCurrentIndex(0)

    def _set_action_busy(self, busy: bool, text: str = ""):
        self._set_action_progress(busy, text)

    # ── Meta links ────────────────────────────────────────────────────────────

    def _render_meta(self, urls: dict):
        self._clear_layout(self._meta_row)
        labels = {
            "homepage":   ("🌐", "Website"),
            "donation":   ("❤️",  "Donate"),
            "bugtracker": ("🐛", "Bug Tracker"),
            "help":       ("📖", "Help"),
        }
        added = False
        for key, url in urls.items():
            if not url:
                continue
            icon, text = labels[key]
            btn = QPushButton(f"{icon} {text}")
            btn.setFlat(True)
            btn.clicked.connect(lambda checked, u=url: subprocess.Popen(["xdg-open", u]))
            self._meta_row.addWidget(btn)
            added = True
        if added:
            self._meta_row.addStretch()

    # ── Bottom cards (package name, flatpak id, categories) ──────────────────

    def _render_cards(self, native: dict | None, fp: dict | None):
        self._clear_layout(self._cards_row)
        items = []
        if native:
            items.append(("RPM Package", native["pkg_name"]))
        if fp:
            items.append(("Flatpak ID", fp["id"]))
        base = native or fp or {}
        if base.get("categories"):
            items.append(("Categories", ", ".join(base["categories"][:3])))

        for title, value in items:
            card = QFrame()
            card.setObjectName("card")
            card.setFrameShape(QFrame.Shape.StyledPanel)
            card.setFixedWidth(210)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 10, 12, 10)
            cl.setSpacing(3)
            cl.addWidget(dimmed(bold_font(QLabel(title), extra_pts=-1)))
            vl = bold_font(QLabel(value))
            vl.setWordWrap(True)
            cl.addWidget(vl)
            self._cards_row.addWidget(card)
        if items:
            self._cards_row.addStretch()

    # ── Install / remove ──────────────────────────────────────────────────────

    def _do_install(self, app: dict):
        if app.get("source") == "webapp":
            self._do_webapp_install(app)
            return
        if app.get("local_rpm"):
            self._run_stream(
                packages.install_local_rpm_stream,
                app["local_rpm"],
                app, "install",
            )
        elif app.get("local_flatpak"):
            self._run_stream(
                flatpak.install_local_flatpak_stream,
                app["local_flatpak"],
                app, "install",
            )
        elif app.get("local_flatpakref"):
            self._run_stream(
                flatpak.install_flatpakref_stream,
                app["local_flatpakref"],
                app, "install",
            )
        else:
            self._run_stream(
                flatpak.install_flatpak_stream if app.get("source") == "flatpak"
                else packages.install_package_stream,
                app["id"] if app.get("source") == "flatpak" else app["pkg_name"],
                app, "install",
            )

    def _do_remove(self, app: dict):
        if app.get("source") == "webapp":
            self._do_webapp_remove(app)
            return
        self._run_stream(
            flatpak.remove_flatpak_stream if app.get("source") == "flatpak"
            else packages.remove_package_stream,
            app["id"] if app.get("source") == "flatpak" else app["pkg_name"],
            app, "remove",
        )

    # ── Web app install / remove ───────────────────────────────────────────────

    def _load_webapp(self, app: dict):
        """Render detail view for a web app (catalog or installed)."""
        from backend import webapps as _wa
        from PyQt6.QtGui import QPixmap

        self._app = app
        self._name_lbl.setText(app.get("name", ""))
        self._summary_lbl.setText(app.get("summary") or app.get("description", ""))

        # Icon — try icon_path first, async-resolve if missing
        self._icon.setText("🌐")
        icon_path = app.get("icon_path", "")

        def _set_icon(path: str):
            if not path:
                return
            pix = QPixmap(path)
            if not pix.isNull():
                self._icon.setPixmap(
                    pix.scaled(64, 64,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation))

        if icon_path:
            _set_icon(icon_path)
        else:
            # Download icon in background then update the label
            app_id = app.get("id", "")
            w = Worker(lambda: _wa.resolve_icon_for(app_id))
            w.result.connect(_set_icon)
            w.start()
            self._workers.append(w)

        desc = app.get("description", "")
        self._desc.setText(desc)
        self._desc.setVisible(bool(desc))
        self._desc_head.setVisible(bool(desc))

        # URL info card
        from PyQt6.QtWidgets import QLabel
        url = app.get("url", "")
        if url:
            from ..widgets import hline
            url_lbl = QLabel(f"<a href='{url}'>{url}</a>")
            url_lbl.setOpenExternalLinks(True)
            url_lbl.setTextFormat(Qt.TextFormat.RichText)
            self._info_block.addWidget(url_lbl)

        # Web App badge
        badge = QLabel("Web App")
        badge.setStyleSheet(
            "QLabel { background: rgba(100,200,130,0.18); color: #4caf50;"
            " border-radius: 4px; padding: 2px 8px; font-size: 11px; }")
        self._meta_row.addWidget(badge)

        # Screenshots — same carousel used for Flatpak/native apps
        for url in (app.get("screenshots") or [])[:8]:
            ldr = ImageLoader(url)
            ldr.loaded.connect(self._on_screenshot)
            ldr.start()
            self._workers.append(ldr)

        self._render_basic_actions(app)

    def _do_webapp_install(self, app: dict):
        from backend import webapps as _wa
        from ..workers import Worker
        self._terminal.reset()
        self._terminal.show()
        self._terminal.append_line(f"Installing {app.get('name', '')}…")
        app_id = app.get("id", "")

        def _run():
            return _wa.install(app_id)

        w = Worker(_run)
        w.result.connect(self._on_webapp_install_done)
        w.start()
        self._workers.append(w)

    def _on_webapp_install_done(self, result: tuple):
        success, msg = result
        self._terminal.append_line(f"✓ {msg}" if success else f"✗ {msg}")
        if success and self._app:
            self._app["installed"] = True
            self._render_basic_actions(self._app)

    def _do_webapp_remove(self, app: dict):
        from backend import webapps as _wa
        from ..workers import Worker
        self._terminal.reset()
        self._terminal.show()
        self._terminal.append_line(f"Removing {app.get('name', '')}…")
        app_id = app.get("id", "")

        def _run():
            return _wa.uninstall(app_id)

        w = Worker(_run)
        w.result.connect(self._on_webapp_remove_done)
        w.start()
        self._workers.append(w)

    def _on_webapp_remove_done(self, result: tuple):
        success, msg = result
        self._terminal.append_line(f"✓ {msg}" if success else f"✗ {msg}")
        if success and self._app:
            self._app["installed"] = False
            self._render_basic_actions(self._app)

    def _run_stream(self, gen_fn, arg, app: dict, op: str,
                    done_cb=None, ext_btn: "QPushButton | None" = None):
        self._terminal.reset()
        is_remove = (op == "remove")
        label = "Removing…" if is_remove else "Installing…"
        if ext_btn:
            ext_btn.setText(label)
            ext_btn.setEnabled(False)
        else:
            # Stamp the operation colour onto the stack before showing bar
            if hasattr(self, "_action_stack") and self._action_stack:
                sq = getattr(self._action_stack, "_square_right", False)
                self._action_stack._is_remove = is_remove
                self._action_stack._bar.setStyleSheet(self._bar_style(is_remove, sq))
            self._set_action_progress(True, label)
        w = StreamWorker(gen_fn, arg)
        w.line.connect(self._on_stream_line)
        w.done.connect(lambda code: self._op_done(
            code, app, op, done_cb=done_cb, ext_btn=ext_btn))
        w.start()
        self._workers.append(w)

    def _op_done(self, code: int, app: dict, op: str,
                 done_cb=None, ext_btn: "QPushButton | None" = None):
        verb = "Installed" if op == "install" else "Removed"
        if code == 0:
            self._terminal.append_line(f"\n✓ {verb} successfully.")
            if done_cb:
                done_cb(True)
            else:
                self._set_action_progress(False)
                w = Worker(self._fetch_detail, app)
                w.result.connect(self._on_detail)
                w.start()
                self._workers.append(w)
        else:
            self._terminal.append_line(f"\n✗ Failed (exit {code}).")
            self._terminal.show()   # surface the error output
            if ext_btn:
                ext_btn.setText("Retry")
                ext_btn.setEnabled(True)
            else:
                self._set_action_progress(False, "Retry")
            if done_cb:
                done_cb(False)

    # ── Reviews ──────────────────────────────────────────────────────────────

    def _fetch_addons(self, app_id: str) -> list[dict]:
        from backend import packages
        addons = packages.get_addons_for(app_id)
        # Enrich installed status
        for a in addons:
            from backend import packages as pkg
            a["installed"] = pkg.is_installed_native(a["pkg_name"]) or                               pkg.is_installed_flatpak(a.get("id", ""))
        return addons

    def _on_addons(self, addons: list[dict]):
        self._addons = addons
        if not addons:
            self._addons_btn.hide()
            return
        self._addons_btn.setText(f"🧩  Add-ons  ({len(addons)})")
        self._addons_btn.show()

    def _show_addons_dialog(self):
        dlg = AddonsDialog(self._addons, self._run_stream, self)
        dlg.exec()

    def _fetch_reviews(self, app_id: str) -> dict:
        from backend import reviews as rev
        review_list = rev.get_reviews(app_id)
        ratings = rev.get_ratings(app_id)
        avg, total = rev.avg_rating_from_counts(ratings) if ratings else (0, 0)
        return {"reviews": review_list, "avg": avg, "total": total, "app_id": app_id}

    def _on_reviews(self, data: dict):
        self._star_widget.set_rating(data["avg"], data["total"])
        self._review_data = data["reviews"]
        self._review_page = 0
        self._current_review_app_id = data["app_id"]
        self._reviews_head.show()
        self._write_review_btn.show()
        self._render_review_page()

    def _render_review_page(self):
        self._clear_layout(self._reviews_container)
        reviews = self._review_data
        ps = self._review_page_size
        page = self._review_page
        total_pages = max(1, (len(reviews) + ps - 1) // ps)

        if reviews:
            for r in reviews[page * ps:(page + 1) * ps]:
                card = ReviewCard(r)
                self._reviews_container.addWidget(card)
        else:
            from ..theme import dimmed
            no_reviews = dimmed(QLabel("No reviews yet — be the first!"))
            self._reviews_container.addWidget(no_reviews)

        # Show/hide pagination controls
        if total_pages > 1:
            self._rev_page_label.setText(f"Page {page + 1} of {total_pages}")
            self._rev_page_label.show()
            self._rev_prev_btn.setVisible(page > 0)
            self._rev_next_btn.setVisible(page < total_pages - 1)
        else:
            self._rev_page_label.hide()
            self._rev_prev_btn.hide()
            self._rev_next_btn.hide()

    def _reviews_prev(self):
        if self._review_page > 0:
            self._review_page -= 1
            self._render_review_page()

    def _reviews_next(self):
        ps = self._review_page_size
        total_pages = max(1, (len(self._review_data) + ps - 1) // ps)
        if self._review_page < total_pages - 1:
            self._review_page += 1
            self._render_review_page()

    def _on_write_review(self):
        app_id = getattr(self, "_current_review_app_id", self._app.get("id", ""))
        dlg = WriteReviewDialog(self._app.get("name", ""), app_id, self)
        if dlg.exec() == WriteReviewDialog.DialogCode.Accepted:
            # Reload reviews after submit
            w = Worker(self._fetch_reviews, app_id)
            w.result.connect(self._on_reviews)
            w.start()
            self._workers.append(w)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clear_action_widgets(self):
        """Remove install button and source dropdown from the top bar layout."""
        for attr in ("_action_stack", "_source_btn"):
            w = getattr(self, attr, None)
            if w is not None:
                self._bl.removeWidget(w)
                w.deleteLater()
                setattr(self, attr, None)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())


class AddonsDialog(QDialog):
    """
    Popup showing add-ons for an app, Discover-style.
    Each row has icon / name / summary / install button that
    turns into a progress indicator during the operation.
    """

    def __init__(self, addons: list[dict], run_stream_fn, parent=None):
        super().__init__(parent)
        self._run_stream = run_stream_fn
        self.setWindowTitle("Add-ons")
        self.setMinimumWidth(520)
        self.setMinimumHeight(400)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("topbar")
        header.setFixedHeight(52)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 0, 20, 0)
        title = QLabel(f"Add-ons  ({len(addons)})")
        f = title.font(); f.setPointSize(f.pointSize() + 2); f.setBold(True)
        title.setFont(f)
        hl.addWidget(title)
        hl.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFlat(True)
        close_btn.setFixedSize(28, 28)
        close_btn.clicked.connect(self.accept)
        hl.addWidget(close_btn)
        root.addWidget(header)

        # Scrollable addon list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        vl = QVBoxLayout(container)
        vl.setContentsMargins(16, 12, 16, 12)
        vl.setSpacing(8)

        self._rows: list[dict] = []  # {addon, btn, row_frame}

        for addon in addons:
            row = QFrame()
            row.setObjectName("card")
            row.setFrameShape(QFrame.Shape.StyledPanel)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(14, 10, 14, 10)
            rl.setSpacing(12)

            # Icon
            icon_w = IconWidget(36)  # IconWidget already imported at top
            icon_w.set_icon_name(addon.get("icon", ""), app_id=addon.get("id", ""), pkg_name=addon.get("pkg_name", ""))
            rl.addWidget(icon_w)

            # Text
            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            name_lbl = bold_font(QLabel(addon.get("name", addon.get("id", ""))))
            text_col.addWidget(name_lbl)
            summary = addon.get("summary", "")
            if summary:
                sum_lbl = dimmed(QLabel(summary))
                sum_lbl.setWordWrap(True)
                text_col.addWidget(sum_lbl)
            rl.addLayout(text_col, stretch=1)

            # Install / Remove button
            installed = addon.get("installed", False)
            btn = QPushButton("Remove" if installed else "Install")
            btn.setFixedWidth(100)
            btn.setFixedHeight(32)
            btn.clicked.connect(
                lambda checked=False, a=addon, b=btn:
                    self._do_addon(a, b)
            )
            rl.addWidget(btn)

            vl.addWidget(row)
            self._rows.append({"addon": addon, "btn": btn})

        vl.addStretch()

    def _do_addon(self, addon: dict, btn: QPushButton):
        from backend import packages, flatpak
        installed = addon.get("installed", False)
        if installed:
            gen_fn = (flatpak.remove_flatpak_stream if addon.get("source") == "flatpak"
                      else packages.remove_package_stream)
            arg = addon["id"] if addon.get("source") == "flatpak" else addon["pkg_name"]
            op = "remove"
        else:
            gen_fn = (flatpak.install_flatpak_stream if addon.get("source") == "flatpak"
                      else packages.install_package_stream)
            arg = addon["id"] if addon.get("source") == "flatpak" else addon["pkg_name"]
            op = "install"

        def done_cb(success: bool):
            if success:
                addon["installed"] = not installed
                btn.setText("Remove" if addon["installed"] else "Install")
                btn.setEnabled(True)
            else:
                btn.setText("Retry")
                btn.setEnabled(True)

        self._run_stream(gen_fn, arg, addon, op,
                         done_cb=done_cb, ext_btn=btn)
