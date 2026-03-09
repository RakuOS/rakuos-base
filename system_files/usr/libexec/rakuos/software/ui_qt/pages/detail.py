"""
pages/detail.py — Full app detail page with install/remove, screenshots, lightbox.
"""

import os
import subprocess

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
    QLabel, QPushButton, QToolButton, QMenu,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QPalette, QCursor

from ..workers import Worker, StreamWorker, ImageLoader
from ..widgets import (
    IconWidget, TerminalWidget, ClickableImage, hline,
)
from ..theme import dimmed, bold_font, colored_text, _c
from backend import packages, flatpak


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

        # Back bar
        back_bar = QFrame()
        back_bar.setObjectName("topbar")
        back_bar.setFixedHeight(48)
        back_bar.setFrameShape(QFrame.Shape.StyledPanel)
        bl = QHBoxLayout(back_bar)
        bl.setContentsMargins(16, 0, 16, 0)
        back_btn = QPushButton("← Back")
        back_btn.setFixedWidth(90)
        back_btn.clicked.connect(self.back_requested)
        bl.addWidget(back_btn)
        bl.addStretch()
        root.addWidget(back_bar)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        self._vl = QVBoxLayout(content)
        self._vl.setContentsMargins(24, 24, 24, 24)
        self._vl.setSpacing(16)

        # ── Hero ──────────────────────────────────────────────────────────────
        hero = QHBoxLayout()
        hero.setSpacing(20)
        self._icon = IconWidget(96)
        hero.addWidget(self._icon, alignment=Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(4)
        self._name_lbl = bold_font(QLabel(), extra_pts=6)
        self._name_lbl.setWordWrap(True)
        info.addWidget(self._name_lbl)

        self._summary_lbl = dimmed(QLabel())
        self._summary_lbl.setWordWrap(True)
        info.addWidget(self._summary_lbl)
        info.addSpacing(8)

        self._actions = QHBoxLayout()
        self._actions.setSpacing(8)
        info.addLayout(self._actions)
        hero.addLayout(info)
        hero.addStretch()
        self._vl.addLayout(hero)
        self._vl.addWidget(hline())

        # Meta links (website, donate, etc.)
        self._meta_row = QHBoxLayout()
        self._meta_row.setSpacing(8)
        self._vl.addLayout(self._meta_row)

        # Screenshots
        self._ss_label = bold_font(QLabel("Screenshots"))
        self._ss_label.hide()
        self._vl.addWidget(self._ss_label)

        # Screenshot row — mirrors the working test_scroll.py exactly
        self._ss_scroll = QScrollArea()
        self._ss_scroll.setFixedHeight(212)
        self._ss_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._ss_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._ss_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._ss_scroll.setWidgetResizable(False)
        self._ss_container = QWidget()
        self._ss_container.setFixedSize(1, 178)  # grows via setFixedSize as images arrive
        self._ss_scroll.setWidget(self._ss_container)
        self._ss_images: list = []
        self._ss_x = 0
        self._ss_scroll.hide()
        self._vl.addWidget(self._ss_scroll)

        # Description
        self._desc_label = bold_font(QLabel("About"))
        self._desc_label.hide()
        self._vl.addWidget(self._desc_label)

        self._desc = dimmed(QLabel())
        self._desc.setWordWrap(True)
        self._desc.setTextFormat(Qt.TextFormat.PlainText)
        self._vl.addWidget(self._desc)

        # Info cards (package name, flatpak id, categories)
        self._info_row = QHBoxLayout()
        self._info_row.setSpacing(10)
        self._vl.addLayout(self._info_row)

        # Terminal log
        self._terminal = TerminalWidget()
        self._vl.addWidget(self._terminal)
        self._vl.addStretch()

    # ── Public ────────────────────────────────────────────────────────────────

    def load_app(self, app: dict):
        self._app = app
        self._native = None
        self._flatpak_app = None
        self._terminal.reset()
        self._clear_layout(self._actions)
        self._clear_layout(self._meta_row)
        self._clear_screenshots()
        self._clear_layout(self._info_row)

        self._name_lbl.setText(app.get("name", ""))
        self._summary_lbl.setText(app.get("summary", ""))
        self._icon.set_icon_name(app.get("icon", ""))

        desc = app.get("description", "")
        self._desc.setText(desc)
        self._desc_label.setVisible(bool(desc))

        self._render_basic_actions(app)

        for url in (app.get("screenshots") or [])[:6]:
            ldr = ImageLoader(url)
            ldr.loaded.connect(self._on_screenshot)
            ldr.start()
            self._workers.append(ldr)

        w = Worker(self._fetch_detail, app)
        w.result.connect(self._on_detail)
        w.start()
        self._workers.append(w)

    # ── Data fetching ─────────────────────────────────────────────────────────

    def _fetch_detail(self, app: dict) -> dict:
        """Fetch native + flatpak variants and URL metadata."""
        appstream = packages._load_appstream()
        name_lower = app.get("name", "").lower()
        app_id = app.get("id", "")
        native = fp = None

        for a in appstream.values():
            if a["source"] == "native" and (
                a["id"] == app_id
                or a["pkg_name"] == app.get("pkg_name")
                or a["name"].lower() == name_lower
            ):
                native = packages._enrich_installed(a)
            if a["source"] == "flatpak" and (
                a["id"] == app_id
                or a["name"].lower() == name_lower
                or a["id"].split(".")[-1].lower() == app.get("pkg_name", "").lower()
            ):
                fp = packages._enrich_installed(a)

        urls = {k: "" for k in ("homepage", "donation", "bugtracker", "help")}
        import gzip
        import xml.etree.ElementTree as ET
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
        self._native = data["native"]
        self._flatpak_app = data["flatpak"]
        self._render_actions(self._native, self._flatpak_app)
        self._render_meta(data["urls"])
        self._render_info(self._native, self._flatpak_app)

    # ── Screenshots ───────────────────────────────────────────────────────────

    def _on_screenshot(self, pixmap: QPixmap, key: str):
        if pixmap.isNull():
            return
        self._ss_label.show()
        self._ss_scroll.show()
        thumb = pixmap.scaledToHeight(170, Qt.TransformationMode.SmoothTransformation)
        img = ClickableImage(pixmap)
        img.setPixmap(thumb)
        img.setParent(self._ss_container)
        img.setFixedSize(thumb.width(), 170)
        img.move(self._ss_x, 4)
        img.show()
        self._ss_x += thumb.width() + 10
        self._ss_images.append(img)
        # setFixedSize (not just setFixedWidth) is what the test uses — must match
        self._ss_container.setFixedSize(self._ss_x, 178)

    # ── Action buttons ────────────────────────────────────────────────────────

    def _render_basic_actions(self, app: dict):
        """Show a basic install/remove button before full detail loads."""
        self._clear_layout(self._actions)
        installed = app.get("installed", False)
        btn = QPushButton("Remove" if installed else "Install")
        if not installed:
            btn.setDefault(True)
        btn.setMinimumWidth(110)
        handler = self._do_remove if installed else self._do_install
        btn.clicked.connect(lambda: handler(app))
        self._actions.addWidget(btn)
        self._actions.addStretch()

    def _render_actions(self, native: dict | None, fp: dict | None):
        """Render split dropdown when both RPM + Flatpak available."""
        self._clear_layout(self._actions)

        if native and fp:
            installed = native.get("installed")
            main_btn = QPushButton("Remove (RPM)" if installed else "Install (RPM)")
            if not installed:
                main_btn.setDefault(True)
            main_btn.setMinimumWidth(130)
            handler = self._do_remove if installed else self._do_install
            main_btn.clicked.connect(lambda: handler(native))
            self._actions.addWidget(main_btn)

            arrow = QToolButton()
            arrow.setText("▾")
            arrow.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(arrow)
            fp_installed = fp.get("installed")
            act = menu.addAction(
                f"{'Remove' if fp_installed else 'Install'} (Flatpak) — {fp['pkg_name']}"
            )
            fp_handler = self._do_remove if fp_installed else self._do_install
            act.triggered.connect(lambda: fp_handler(fp))
            arrow.setMenu(menu)
            self._actions.addWidget(arrow)

        elif native or fp:
            app = native or fp
            installed = app.get("installed")
            src_label = " (Flatpak)" if fp else ""
            btn = QPushButton(f"{'Remove' if installed else 'Install'}{src_label}")
            if not installed:
                btn.setDefault(True)
            btn.setMinimumWidth(110)
            handler = self._do_remove if installed else self._do_install
            btn.clicked.connect(lambda: handler(app))
            self._actions.addWidget(btn)

        self._actions.addStretch()

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

    # ── Info cards ────────────────────────────────────────────────────────────

    def _render_info(self, native: dict | None, fp: dict | None):
        self._clear_layout(self._info_row)
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
            card.setFixedWidth(200)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 10, 12, 10)
            cl.setSpacing(3)
            cl.addWidget(dimmed(bold_font(QLabel(title), extra_pts=-1)))
            vl = bold_font(QLabel(value))
            vl.setWordWrap(True)
            cl.addWidget(vl)
            self._info_row.addWidget(card)

        if items:
            self._info_row.addStretch()

    # ── Install / remove ──────────────────────────────────────────────────────

    def _do_install(self, app: dict):
        self._run_stream(
            flatpak.install_flatpak_stream if app.get("source") == "flatpak"
            else packages.install_package_stream,
            app["id"] if app.get("source") == "flatpak" else app["pkg_name"],
            app, "install",
        )

    def _do_remove(self, app: dict):
        self._run_stream(
            flatpak.remove_flatpak_stream if app.get("source") == "flatpak"
            else packages.remove_package_stream,
            app["id"] if app.get("source") == "flatpak" else app["pkg_name"],
            app, "remove",
        )

    def _run_stream(self, gen_fn, arg, app: dict, op: str):
        self._terminal.reset()
        w = StreamWorker(gen_fn, arg)
        w.line.connect(self._terminal.append_line)
        w.done.connect(lambda code: self._op_done(code, app, op))
        w.start()
        self._workers.append(w)

    def _op_done(self, code: int, app: dict, op: str):
        if code == 0:
            self._terminal.append_line(
                f"\n✓ {'Installed' if op == 'install' else 'Removed'} successfully."
            )
            w = Worker(self._fetch_detail, app)
            w.result.connect(self._on_detail)
            w.start()
            self._workers.append(w)
        else:
            self._terminal.append_line(f"\n✗ Failed (exit {code}).")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _clear_screenshots(self):
        for img in self._ss_images:
            img.deleteLater()
        self._ss_images = []
        self._ss_x = 0
        self._ss_container.setFixedSize(1, 178)
        self._ss_label.hide()
        self._ss_scroll.hide()
