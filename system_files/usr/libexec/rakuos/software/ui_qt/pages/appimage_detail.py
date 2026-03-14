"""
pages/appimage_detail.py — AppImage detail and install page.

Opened when user double-clicks an .AppImage file.
Shows extracted metadata (name, icon, version, description, update source)
and an Install button that copies + sets up the AppImage.
Also used for installed AppImage management (uninstall, update source config).
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QComboBox, QProgressBar,
    QSizePolicy,
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QPixmap

from ..workers import Worker, StreamWorker
from ..widgets import SectionTitle, LoadingWidget, TerminalWidget, hline
from ..theme import dimmed, bold_font
from backend import appimages


class AppImageDetailPage(QWidget):
    back_requested = pyqtSignal()
    installed      = pyqtSignal(dict)   # emitted after successful install

    def __init__(self):
        super().__init__()
        self.setAutoFillBackground(True)
        self._workers: list = []
        self._app_info: dict = {}
        self._src_path: str = ""
        self._terminal = None
        self._progress = None
        self._action_btn = None
        self._loading = False   # guard against stale worker callbacks

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget(scroll)
        self._vl = QVBoxLayout(self._content)
        self._vl.setContentsMargins(32, 24, 32, 24)
        self._vl.setSpacing(16)
        scroll.setWidget(self._content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Load ─────────────────────────────────────────────────────────────────

    def load_from_file(self, path: str):
        """Called when user opens an .AppImage file."""
        import os
        print(f"[appimage_detail] load_from_file: {path!r}")
        self._abort_workers()
        self._src_path = path
        self._loading = True
        self._clear()
        self._vl.addWidget(LoadingWidget("Reading AppImage…"))
        w = Worker(lambda: appimages.get_appimage_info_for_display(path))
        w.result.connect(self._on_render_ready)
        w.start()
        self._workers.append(w)

    def load_installed(self, app_info: dict):
        """Called from Installed page for an already-installed AppImage."""
        self._abort_workers()
        self._src_path = app_info.get("installed_path", "")
        self._loading = True
        self._clear()
        self._render(app_info)

    # ── Render ────────────────────────────────────────────────────────────────

    def _abort_workers(self):
        """Stop all pending workers so stale callbacks don't fire."""
        for w in self._workers:
            try:
                w.quit()
                w.wait(100)
            except Exception:
                pass
        self._workers.clear()

    def _on_render_ready(self, info: dict):
        """Guard wrapper — ignore result if a new load was started."""
        if not self._loading:
            return
        self._render(info)

    def _render(self, info: dict):
        self._loading = False
        self._clear()
        self._app_info = info

        # ── Back button ───────────────────────────────────────────────────────
        back_btn = QPushButton("← Back")
        back_btn.setFixedWidth(80)
        back_btn.clicked.connect(self.back_requested)
        self._vl.addWidget(back_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        # ── Header row: icon + name + version + badges ────────────────────────
        header = QHBoxLayout()
        header.setSpacing(20)

        # Icon
        icon_w = QLabel()
        icon_w.setFixedSize(96, 96)
        icon_w.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_data = info.get("icon_data")
        if icon_data:
            pix = QPixmap()
            pix.loadFromData(icon_data)
            if not pix.isNull():
                icon_w.setPixmap(
                    pix.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation))
            else:
                icon_w.setText("📦")
                f = icon_w.font(); f.setPointSize(40); icon_w.setFont(f)
        else:
            # Try icon_path for installed apps
            icon_path = info.get("icon_path", "")
            if icon_path:
                pix = QPixmap(icon_path)
                if not pix.isNull():
                    icon_w.setPixmap(
                        pix.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation))
                else:
                    icon_w.setText("📦")
                    f = icon_w.font(); f.setPointSize(40); icon_w.setFont(f)
            else:
                icon_w.setText("📦")
                f = icon_w.font(); f.setPointSize(40); icon_w.setFont(f)
        header.addWidget(icon_w)

        # Name / version / badges
        meta_col = QVBoxLayout()
        meta_col.setSpacing(4)

        name_lbl = bold_font(QLabel(info.get("name", "Unknown")), extra_pts=5)
        meta_col.addWidget(name_lbl)

        ver = info.get("version", "")
        if ver:
            meta_col.addWidget(dimmed(QLabel(f"Version {ver}")))

        # Badges row
        badges = QHBoxLayout()
        ai_badge = QLabel("AppImage")
        ai_badge.setStyleSheet(
            "QLabel { background: rgba(255,180,50,0.2); color: #ffb432;"
            " border-radius: 4px; padding: 2px 8px; font-size: 11px; }")
        badges.addWidget(ai_badge)

        src = info.get("update_source", "none")
        if src != "none":
            src_badge = QLabel(f"Updates: {src.title()}")
            src_badge.setStyleSheet(
                "QLabel { background: rgba(100,180,255,0.15); color: #60aaff;"
                " border-radius: 4px; padding: 2px 8px; font-size: 11px; }")
            badges.addWidget(src_badge)
        badges.addStretch()
        meta_col.addLayout(badges)

        # Summary
        summary = info.get("summary") or info.get("description", "")
        if summary:
            meta_col.addWidget(dimmed(QLabel(summary)))

        header.addLayout(meta_col, stretch=1)

        # Install / Uninstall button
        self._action_btn = QPushButton()
        self._action_btn.setFixedWidth(130)
        self._action_btn.setFixedHeight(36)
        if info.get("installed"):
            self._action_btn.setText("Uninstall")
            self._action_btn.setObjectName("dangerButton")
            self._action_btn.clicked.connect(self._do_uninstall)
        else:
            self._action_btn.setText("Install")
            self._action_btn.setDefault(True)
            self._action_btn.clicked.connect(self._do_install)
        header.addWidget(self._action_btn,
                         alignment=Qt.AlignmentFlag.AlignTop)
        self._vl.addLayout(header)
        self._vl.addWidget(hline())

        # ── Description ───────────────────────────────────────────────────────
        desc = info.get("description", "")
        if desc and desc != summary:
            self._vl.addWidget(SectionTitle("About"))
            desc_lbl = QLabel(desc)
            desc_lbl.setWordWrap(True)
            self._vl.addWidget(desc_lbl)
            self._vl.addWidget(hline())

        # ── Update source config ──────────────────────────────────────────────
        self._vl.addWidget(SectionTitle("Update Source"))
        self._vl.addWidget(dimmed(QLabel(
            "Configure how RakuOS checks for updates for this AppImage.")))

        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Source:"))
        self._src_combo = QComboBox()
        self._src_combo.setFixedWidth(150)
        for label, val in [("None", "none"), ("GitHub", "github"),
                           ("GitLab", "gitlab"), ("URL", "url")]:
            self._src_combo.addItem(label, val)
        cur = info.get("update_source", "none")
        idx = self._src_combo.findData(cur)
        if idx >= 0:
            self._src_combo.setCurrentIndex(idx)
        self._src_combo.currentIndexChanged.connect(self._on_src_changed)
        src_row.addWidget(self._src_combo)
        src_row.addStretch()
        self._vl.addLayout(src_row)

        # URL field (shown for github/gitlab/url)
        self._url_field = QLineEdit()
        self._url_field.setPlaceholderText(
            "e.g. https://api.github.com/repos/owner/repo/releases/latest")
        self._url_field.setText(info.get("update_url", ""))
        self._url_field.setVisible(cur != "none")
        self._vl.addWidget(self._url_field)

        # Pattern field
        self._pattern_field = QLineEdit()
        self._pattern_field.setPlaceholderText("e.g. AppName-*.AppImage")
        self._pattern_field.setText(info.get("update_pattern", "*.AppImage"))
        self._pattern_field.setVisible(cur != "none")
        self._vl.addWidget(self._pattern_field)

        if info.get("installed"):
            save_btn = QPushButton("Save Update Settings")
            save_btn.setFixedWidth(180)
            save_btn.clicked.connect(self._save_update_settings)
            self._vl.addWidget(save_btn)

        # ── Progress / terminal ───────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.hide()
        self._vl.addWidget(self._progress)

        self._terminal = TerminalWidget()
        self._terminal.hide()
        self._vl.addWidget(self._terminal)

        self._vl.addStretch()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_src_changed(self, _):
        val = self._src_combo.currentData()
        self._url_field.setVisible(val != "none")
        self._pattern_field.setVisible(val != "none")

    def _do_install(self):
        self._action_btn.setEnabled(False)
        self._action_btn.setText("Installing…")
        self._progress.show()

        w = Worker(lambda: appimages.install_appimage(self._src_path))
        w.result.connect(self._on_install_done)
        w.start()
        self._workers.append(w)

    def _on_install_done(self, result: tuple):
        success, msg, app_info = result
        self._progress.hide()
        self._terminal.show()
        self._terminal.reset()
        self._terminal.append_line(
            f"✓ {msg}" if success else f"✗ {msg}")
        if success:
            self._action_btn.setText("Uninstall")
            self._action_btn.setEnabled(True)
            self._action_btn.setObjectName("dangerButton")
            self._action_btn.clicked.disconnect()
            self._action_btn.clicked.connect(self._do_uninstall)
            self._app_info = app_info
            self.installed.emit(app_info)
        else:
            self._action_btn.setText("Install")
            self._action_btn.setEnabled(True)

    def _do_uninstall(self):
        app_id = self._app_info.get("id", "")
        if not app_id:
            return
        self._action_btn.setEnabled(False)
        self._action_btn.setText("Removing…")
        self._progress.show()

        w = Worker(lambda: appimages.uninstall_appimage(app_id))
        w.result.connect(self._on_uninstall_done)
        w.start()
        self._workers.append(w)

    def _on_uninstall_done(self, result: tuple):
        success, msg = result
        self._progress.hide()
        self._terminal.show()
        self._terminal.reset()
        self._terminal.append_line(
            f"✓ {msg}" if success else f"✗ {msg}")
        if success:
            self._action_btn.setText("Install")
            self._action_btn.setEnabled(True)
            self._action_btn.setObjectName("")
            self._action_btn.clicked.disconnect()
            self._action_btn.clicked.connect(self._do_install)
            self._app_info["installed"] = False

    def _save_update_settings(self):
        import json
        from pathlib import Path
        app_id = self._app_info.get("id", "")
        if not app_id:
            return
        sidecar_path = appimages.INSTALL_DIR / f"{app_id}.json"
        if not sidecar_path.exists():
            return
        try:
            sidecar = json.loads(sidecar_path.read_text())
            sidecar["update_source"]  = self._src_combo.currentData()
            sidecar["update_url"]     = self._url_field.text().strip()
            sidecar["update_pattern"] = self._pattern_field.text().strip()
            sidecar_path.write_text(json.dumps(sidecar, indent=2))
            self._terminal.show()
            self._terminal.reset()
            self._terminal.append_line("✓ Update settings saved.")
        except Exception as e:
            self._terminal.show()
            self._terminal.append_line(f"✗ Failed to save: {e}")

    # ── Clear ─────────────────────────────────────────────────────────────────

    def _clear(self):
        # Null out refs before deleting widgets to sever signal connections
        self._terminal      = None
        self._progress      = None
        self._action_btn    = None
        self._src_combo     = None
        self._url_field     = None
        self._pattern_field = None
        # Use setParent(None) for immediate synchronous deletion
        # deleteLater() is async and causes stacking when _render fires quickly
        while self._vl.count():
            item = self._vl.takeAt(0)
            if item.widget():
                w = item.widget()
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                w = item.widget()
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())
