"""
pages/settings.py — RakuOS Software Center Settings page.
Tabs:
  • Flatpak Repositories  — manage flatpak remotes
  • Firmware / LVFS       — manage fwupd remotes and vendor dirs
"""

import os
import subprocess

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QFrame, QScrollArea, QLineEdit, QCheckBox,
    QDialog, QDialogButtonBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal

from ..theme import dimmed, bold_font, col_success, col_danger, col_warning
from ..widgets import hline, TerminalWidget
from ..workers import Worker, StreamWorker


# ── Small status label helper ─────────────────────────────────────────────────

def _status_lbl() -> QLabel:
    lbl = QLabel("")
    lbl.setWordWrap(True)
    lbl.hide()
    return lbl


def _show_status(lbl: QLabel, msg: str, ok: bool):
    from ..theme import col_success, col_danger
    from PyQt6.QtGui import QPalette
    color = col_success() if ok else col_danger()
    lbl.setStyleSheet(f"color: {color.name()};")
    lbl.setText(msg)
    lbl.show()


# ── Flatpak remote row ────────────────────────────────────────────────────────

class FlatpakRemoteRow(QFrame):
    changed = pyqtSignal()

    def __init__(self, remote: dict):
        super().__init__()
        self._remote = remote
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("card")

        rl = QHBoxLayout(self)
        rl.setContentsMargins(14, 10, 14, 10)
        rl.setSpacing(10)

        # Toggle
        self._toggle = QCheckBox()
        self._toggle.setChecked(remote["enabled"])
        self._toggle.setToolTip("Enable / disable this remote")
        self._toggle.toggled.connect(self._on_toggle)
        rl.addWidget(self._toggle)

        # Name + URL
        info = QVBoxLayout()
        info.setSpacing(2)
        name_row = QHBoxLayout()
        name_lbl = bold_font(QLabel(remote["title"] or remote["name"]))
        name_row.addWidget(name_lbl)
        scope_lbl = dimmed(QLabel("system" if remote["system"] else "user"))
        scope_lbl.setStyleSheet("font-size: 10px;")
        name_row.addWidget(scope_lbl)
        name_row.addStretch()
        info.addLayout(name_row)
        if remote["url"]:
            url_lbl = dimmed(QLabel(remote["url"]))
            url_lbl.setStyleSheet("font-size: 11px;")
            info.addWidget(url_lbl)
        rl.addLayout(info, stretch=1)

        # Remove button
        rm_btn = QPushButton("Remove")
        rm_btn.setFixedWidth(80)
        rm_btn.setFixedHeight(28)
        rm_btn.clicked.connect(self._on_remove)
        rl.addWidget(rm_btn)

        self._status = _status_lbl()
        rl.addWidget(self._status)

    def _on_toggle(self, enabled: bool):
        from backend import flatpak as fp
        ok, msg = fp.set_remote_enabled(
            self._remote["name"], enabled, self._remote["system"]
        )
        _show_status(self._status, msg, ok)
        if not ok:
            self._toggle.blockSignals(True)
            self._toggle.setChecked(not enabled)
            self._toggle.blockSignals(False)

    def _on_remove(self):
        from backend import flatpak as fp
        ok, msg = fp.remove_remote(self._remote["name"], self._remote["system"])
        _show_status(self._status, msg, ok)
        if ok:
            self.changed.emit()


# ── Add remote dialog ─────────────────────────────────────────────────────────

class AddRemoteDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Flatpak Remote")
        self.setMinimumWidth(400)
        self.setModal(True)

        vl = QVBoxLayout(self)
        vl.setSpacing(10)
        vl.setContentsMargins(20, 20, 20, 20)

        vl.addWidget(bold_font(QLabel("Add a Flatpak remote")))

        vl.addWidget(QLabel("Name (e.g. flathub):"))
        self._name = QLineEdit()
        self._name.setPlaceholderText("remote-name")
        vl.addWidget(self._name)

        vl.addWidget(QLabel("URL (.flatpakrepo or repository URL):"))
        self._url = QLineEdit()
        self._url.setPlaceholderText("https://...")
        vl.addWidget(self._url)

        self._system = QCheckBox("Install as system-wide remote (recommended)")
        self._system.setChecked(True)
        vl.addWidget(self._system)

        self._status = _status_lbl()
        vl.addWidget(self._status)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Add Remote")
        btns.accepted.connect(self._on_add)
        btns.rejected.connect(self.reject)
        vl.addWidget(btns)

    def _on_add(self):
        from backend import flatpak as fp
        name = self._name.text().strip()
        url  = self._url.text().strip()
        if not name or not url:
            _show_status(self._status, "Name and URL are required.", False)
            return
        ok, msg = fp.add_remote(name, url, self._system.isChecked())
        _show_status(self._status, msg, ok)
        if ok:
            self.accept()


# ── Flatpak repos tab ─────────────────────────────────────────────────────────

class FlatpakReposTab(QWidget):
    def __init__(self):
        super().__init__()
        self._workers = []
        vl = QVBoxLayout(self)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(10)

        # Header row
        head_row = QHBoxLayout()
        head_row.addWidget(bold_font(QLabel("Flatpak Repositories"), extra_pts=1))
        head_row.addStretch()
        self._add_flathub_btn = QPushButton("➕  Add Flathub")
        self._add_flathub_btn.setFixedHeight(32)
        self._add_flathub_btn.hide()
        self._add_flathub_btn.clicked.connect(self._on_add_flathub)
        head_row.addWidget(self._add_flathub_btn)
        add_btn = QPushButton("➕  Add Remote")
        add_btn.setFixedHeight(32)
        add_btn.clicked.connect(self._on_add_remote)
        head_row.addWidget(add_btn)
        vl.addLayout(head_row)

        vl.addWidget(dimmed(QLabel(
            "Manage Flatpak repositories. System remotes are available to all users."
        )))
        vl.addWidget(hline())

        # Scrollable remote list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._inner = QWidget()
        self._list_vl = QVBoxLayout(self._inner)
        self._list_vl.setContentsMargins(0, 0, 0, 0)
        self._list_vl.setSpacing(8)
        self._list_vl.addStretch()
        scroll.setWidget(self._inner)
        vl.addWidget(scroll)

        self._status = _status_lbl()
        vl.addWidget(self._status)

        self._load()

    def _load(self):
        # Clear existing rows
        while self._list_vl.count() > 1:
            item = self._list_vl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        w = Worker(self._fetch)
        w.result.connect(self._on_loaded)
        w.start()
        self._workers.append(w)

    def _fetch(self) -> dict:
        from backend import flatpak as fp
        return {"remotes": fp.get_remotes(), "has_flathub": fp.has_flathub()}

    def _on_loaded(self, data: dict):
        remotes = data["remotes"]
        if not remotes:
            lbl = dimmed(QLabel("No Flatpak remotes configured."))
            self._list_vl.insertWidget(0, lbl)
        else:
            for i, remote in enumerate(remotes):
                row = FlatpakRemoteRow(remote)
                row.changed.connect(self._load)
                self._list_vl.insertWidget(i, row)

        if not data["has_flathub"]:
            self._add_flathub_btn.show()
        else:
            self._add_flathub_btn.hide()

    def _on_add_flathub(self):
        from backend import flatpak as fp
        ok, msg = fp.add_flathub(system=True)
        _show_status(self._status, msg, ok)
        if ok:
            self._load()

    def _on_add_remote(self):
        dlg = AddRemoteDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()


# ── Firmware remote row ───────────────────────────────────────────────────────

class FirmwareRemoteRow(QFrame):
    changed = pyqtSignal()

    def __init__(self, remote: dict):
        super().__init__()
        self._remote = remote
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("card")

        rl = QHBoxLayout(self)
        rl.setContentsMargins(14, 10, 14, 10)
        rl.setSpacing(10)

        self._toggle = QCheckBox()
        self._toggle.setChecked(remote.get("enabled", False))
        self._toggle.setToolTip("Enable / disable this remote")
        self._toggle.toggled.connect(self._on_toggle)
        rl.addWidget(self._toggle)

        info = QVBoxLayout()
        info.setSpacing(2)

        name_row = QHBoxLayout()
        name_lbl = bold_font(QLabel(remote.get("title", remote.get("id", ""))))
        name_row.addWidget(name_lbl)
        kind = remote.get("kind", "")
        if kind:
            kind_lbl = dimmed(QLabel(kind))
            kind_lbl.setStyleSheet("font-size: 10px;")
            name_row.addWidget(kind_lbl)
        name_row.addStretch()
        info.addLayout(name_row)

        url = remote.get("url") or remote.get("metadata_uri", "")
        if url:
            url_lbl = dimmed(QLabel(url))
            url_lbl.setStyleSheet("font-size: 11px;")
            info.addWidget(url_lbl)

        if remote.get("last_updated"):
            ts_lbl = dimmed(QLabel(f"Updated: {remote['last_updated']}"))
            ts_lbl.setStyleSheet("font-size: 10px;")
            info.addWidget(ts_lbl)

        rl.addLayout(info, stretch=1)

        self._status = _status_lbl()
        rl.addWidget(self._status)

    def _on_toggle(self, enabled: bool):
        from backend import firmware as fw
        ok, msg = fw.set_remote_enabled(self._remote["id"], enabled)
        _show_status(self._status, msg, ok)
        if not ok:
            self._toggle.blockSignals(True)
            self._toggle.setChecked(not enabled)
            self._toggle.blockSignals(False)
        else:
            self.changed.emit()


# ── Firmware tab ──────────────────────────────────────────────────────────────

class FirmwareTab(QWidget):
    def __init__(self):
        super().__init__()
        self._workers = []
        vl = QVBoxLayout(self)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(10)

        # Header
        head_row = QHBoxLayout()
        head_row.addWidget(bold_font(QLabel("Firmware & LVFS"), extra_pts=1))
        head_row.addStretch()
        refresh_btn = QPushButton("🔄  Refresh Metadata")
        refresh_btn.setFixedHeight(32)
        refresh_btn.clicked.connect(self._on_refresh)
        head_row.addWidget(refresh_btn)
        vl.addLayout(head_row)

        vl.addWidget(dimmed(QLabel(
            "Manage firmware update sources via fwupd. "
            "LVFS provides updates from hardware vendors."
        )))
        vl.addWidget(hline())

        # Not available notice (shown when fwupd missing)
        self._unavailable = QLabel(
            "⚠  fwupd is not installed. Install it to manage firmware updates."
        )
        self._unavailable.setWordWrap(True)
        self._unavailable.hide()
        vl.addWidget(self._unavailable)

        # Scrollable remotes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._inner = QWidget()
        self._list_vl = QVBoxLayout(self._inner)
        self._list_vl.setContentsMargins(0, 0, 0, 0)
        self._list_vl.setSpacing(8)
        self._list_vl.addStretch()
        scroll.setWidget(self._inner)
        vl.addWidget(scroll)

        # Terminal for refresh output
        self._terminal = TerminalWidget()
        self._terminal.setFixedHeight(120)
        self._terminal.hide()
        vl.addWidget(self._terminal)

        self._load()

    def _load(self):
        while self._list_vl.count() > 1:
            item = self._list_vl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        w = Worker(self._fetch)
        w.result.connect(self._on_loaded)
        w.start()
        self._workers.append(w)

    def _fetch(self) -> dict:
        from backend import firmware as fw
        available = fw.fwupd_available()
        remotes = fw.get_remotes() if available else []
        vendor_dirs = fw.get_vendor_dirs() if available else []
        return {"available": available, "remotes": remotes, "vendor_dirs": vendor_dirs}

    def _on_loaded(self, data: dict):
        if not data["available"]:
            self._unavailable.show()
            return

        self._unavailable.hide()
        all_remotes = data["remotes"]

        if not all_remotes:
            lbl = dimmed(QLabel("No firmware remotes configured."))
            self._list_vl.insertWidget(0, lbl)
            return

        # Group: LVFS first, then vendor, then others
        def sort_key(r):
            k = r.get("kind", "")
            if k == "download":
                return 0
            if k == "local":
                return 1
            return 2

        for i, remote in enumerate(sorted(all_remotes, key=sort_key)):
            row = FirmwareRemoteRow(remote)
            row.changed.connect(self._load)
            self._list_vl.insertWidget(i, row)

        # Vendor dirs note
        vendor_dirs = data["vendor_dirs"]
        if vendor_dirs:
            self._list_vl.insertWidget(
                len(all_remotes),
                hline()
            )
            vendor_head = dimmed(QLabel(f"Vendor directories ({len(vendor_dirs)} found):"))
            vendor_head.setStyleSheet("font-size: 11px; font-weight: bold;")
            self._list_vl.insertWidget(len(all_remotes) + 1, vendor_head)
            for j, vd in enumerate(vendor_dirs):
                row = FirmwareRemoteRow(vd)
                self._list_vl.insertWidget(len(all_remotes) + 2 + j, row)

    def _on_refresh(self):
        self._terminal.reset()
        self._terminal.show()
        w = StreamWorker(self._do_refresh)
        w.line.connect(self._terminal.append_line)
        w.done.connect(self._on_refresh_done)
        w.start()
        self._workers.append(w)

    def _do_refresh(self):
        from backend import firmware as fw
        yield from fw.refresh_metadata_stream()

    def _on_refresh_done(self, code: int):
        from ..theme import col_success, col_danger
        if code == 0:
            self._terminal.append_line("\n✓ Firmware metadata refreshed.")
            self._load()
        else:
            self._terminal.append_line("\n✗ Refresh failed.")


# ── Update Schedule tab ───────────────────────────────────────────────────────

import json as _json

_SCHEDULES = [
    ("Every 6 hours",  360),
    ("Every 12 hours", 720),
    ("Daily",          1440),
    ("Weekly",         10080),
    ("Manual only",    0),
]

class UpdateScheduleTab(QWidget):
    schedule_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        from PyQt6.QtWidgets import QComboBox, QGroupBox
        vl = QVBoxLayout(self)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(16)

        vl.addWidget(bold_font(QLabel("Update Schedule"), extra_pts=1))
        vl.addWidget(dimmed(QLabel(
            "How often RakuOS Software checks for available updates in the background.")))
        vl.addWidget(hline())

        # Schedule dropdown
        sched_row = QHBoxLayout()
        sched_row.addWidget(QLabel("Check for updates:"))
        self._sched_combo = QComboBox()
        self._sched_combo.setFixedWidth(200)
        settings = self._load()
        cur_interval = settings.get("update_interval", 1440)
        for label, minutes in _SCHEDULES:
            self._sched_combo.addItem(label, minutes)
            if minutes == cur_interval:
                self._sched_combo.setCurrentIndex(self._sched_combo.count() - 1)
        self._sched_combo.currentIndexChanged.connect(self._on_schedule_changed)
        sched_row.addWidget(self._sched_combo)
        sched_row.addStretch()
        vl.addLayout(sched_row)
        vl.addWidget(hline())

        # What to check
        vl.addWidget(bold_font(QLabel("Check for")))
        self._check_pkgs = QCheckBox("Overlay package updates")
        self._check_pkgs.setChecked(settings.get("auto_check_packages", True))
        self._check_pkgs.toggled.connect(self._save)
        vl.addWidget(self._check_pkgs)

        self._check_flatpak = QCheckBox("Flatpak updates")
        self._check_flatpak.setChecked(settings.get("auto_check_flatpak", True))
        self._check_flatpak.toggled.connect(self._save)
        vl.addWidget(self._check_flatpak)

        self._check_image = QCheckBox("System image updates (bootc)")
        self._check_image.setChecked(settings.get("auto_check_image", True))
        self._check_image.toggled.connect(self._save)
        vl.addWidget(self._check_image)

        vl.addWidget(hline())

        # Auto-update checkbox
        vl.addWidget(bold_font(QLabel("Automatic Updates")))
        self._auto_update = QCheckBox(
            "Automatically install package and Flatpak updates when found")
        self._auto_update.setChecked(settings.get("auto_update", False))
        self._auto_update.toggled.connect(self._save)
        vl.addWidget(self._auto_update)
        vl.addWidget(dimmed(QLabel(
            "System image updates always require manual approval and a reboot.")))

        self._status = _status_lbl()
        vl.addWidget(self._status)
        vl.addStretch()

    def _load(self) -> dict:
        try:
            with open(os.path.expanduser("~/.config/rakuos/software-settings.json")) as f:
                return _json.load(f)
        except Exception:
            return {}

    def _on_schedule_changed(self, _index: int):
        self._save()
        self.schedule_changed.emit()

    def _save(self):
        settings = self._load()
        settings["update_interval"]     = self._sched_combo.currentData()
        settings["auto_check_packages"] = self._check_pkgs.isChecked()
        settings["auto_check_flatpak"]  = self._check_flatpak.isChecked()
        settings["auto_check_image"]    = self._check_image.isChecked()
        settings["auto_update"]         = self._auto_update.isChecked()
        try:
            os.makedirs(os.path.dirname(
                os.path.expanduser("~/.config/rakuos/software-settings.json")),
                exist_ok=True)
            with open(os.path.expanduser(
                    "~/.config/rakuos/software-settings.json"), "w") as f:
                _json.dump(settings, f, indent=2)
            _show_status(self._status, "Settings saved.", True)
        except Exception as e:
            _show_status(self._status, f"Failed to save: {e}", False)


# ── Settings page (tab container) ─────────────────────────────────────────────

class SettingsPage(QWidget):
    def __init__(self):
        super().__init__()
        vl = QVBoxLayout(self)
        vl.setContentsMargins(20, 20, 20, 20)
        vl.setSpacing(12)

        vl.addWidget(bold_font(QLabel("Settings"), extra_pts=3))

        self._update_tab = UpdateScheduleTab()
        tabs = QTabWidget()
        tabs.addTab(self._update_tab,      "🔄  Updates")
        tabs.addTab(FlatpakReposTab(),     "📦  Flatpak Repositories")
        tabs.addTab(FirmwareTab(),         "🔧  Firmware / LVFS")
        vl.addWidget(tabs)

    def schedule_changed(self):
        return self._update_tab.schedule_changed
