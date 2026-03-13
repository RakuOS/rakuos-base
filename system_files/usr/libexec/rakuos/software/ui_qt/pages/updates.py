"""
pages/updates.py — Updates page (Discover-style).

Groups (only shown when updates exist):
  1. Applications  — GUI RPMs + Flatpak apps combined, flatpaks tagged
  2. Add-ons       — Flatpak runtimes / extensions
  3. System Deps   — Non-GUI overlay RPM dependencies
  4. OS Image      — bootc image update

Top bar: "Check for Updates" (always) + "Update All" (when updates exist)
Empty state: large green checkmark with "Check for Updates" top-right.

Per-package rows have inline progress bars during update.
"""

import subprocess
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QLabel,
    QHBoxLayout, QPushButton, QProgressBar, QSizePolicy,
)
from PyQt6.QtCore import pyqtSignal, Qt

from ..workers import Worker, StreamWorker
from ..widgets import SectionTitle, LoadingWidget, TerminalWidget, IconWidget, hline
from ..theme import dimmed
from backend import flatpak, updates as upd


# ── Per-package row ───────────────────────────────────────────────────────────

class PackageUpdateRow(QFrame):
    update_clicked = pyqtSignal(dict)

    def __init__(self, pkg: dict, show_icon: bool = False, parent=None):
        super().__init__(parent)
        self._pkg = pkg
        self.setObjectName("updateRow")
        self.setFrameShape(QFrame.Shape.NoFrame)

        hl = QHBoxLayout(self)
        hl.setContentsMargins(4, 8, 8, 8)
        hl.setSpacing(10)

        if show_icon:
            icon_w = IconWidget(size=36)
            icon_w.set_icon_name(
                "", app_id=pkg.get("app_id", ""), pkg_name=pkg.get("name", ""))
            hl.addWidget(icon_w)

        # Name + version + flatpak badge
        info_col = QVBoxLayout()
        info_col.setSpacing(1)

        name_lbl = QLabel(pkg.get("name") or pkg.get("app_id", ""))
        nf = name_lbl.font()
        nf.setPointSize(nf.pointSize() + 1)
        name_lbl.setFont(nf)
        info_col.addWidget(name_lbl)

        ver_row = QHBoxLayout()
        ver_row.setSpacing(6)
        ver = pkg.get("version", "")
        if ver:
            ver_row.addWidget(dimmed(QLabel(f"→  {ver}")))
        if pkg.get("is_flatpak"):
            badge = QLabel("Flatpak")
            badge.setStyleSheet(
                "QLabel { background: rgba(100,180,255,0.18); color: #60aaff;"
                " border-radius: 4px; padding: 1px 6px; font-size: 10px; }")
            ver_row.addWidget(badge)
        if pkg.get("is_appimage"):
            badge = QLabel("AppImage")
            badge.setStyleSheet(
                "QLabel { background: rgba(255,180,50,0.2); color: #ffb432;"
                " border-radius: 4px; padding: 1px 6px; font-size: 10px; }")
            ver_row.addWidget(badge)
        ver_row.addStretch()
        info_col.addLayout(ver_row)
        hl.addLayout(info_col, stretch=1)

        # Progress bar — hidden until update starts
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._progress.hide()
        hl.addWidget(self._progress, stretch=1)

        self._status = QLabel("")
        self._status.hide()
        hl.addWidget(self._status)

        self._btn = QPushButton("Update")
        self._btn.setFixedWidth(88)
        self._btn.clicked.connect(lambda: self.update_clicked.emit(self._pkg))
        hl.addWidget(self._btn)

    def set_updating(self):
        self._btn.hide()
        self._progress.show()

    def set_done(self, success: bool):
        self._progress.hide()
        self._status.setText("✓" if success else "✗")
        self._status.setStyleSheet(
            "color: #4caf50; font-size: 16px;" if success
            else "color: #e53935; font-size: 16px;")
        self._status.show()


# ── Section card ──────────────────────────────────────────────────────────────

class UpdateSection(QFrame):
    update_all_clicked = pyqtSignal(list)

    def __init__(self, title: str, packages: list,
                 show_icons: bool = False, parent=None):
        super().__init__(parent)
        self._packages = packages
        self._rows: list[PackageUpdateRow] = []
        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(16, 12, 16, 12)
        vl.setSpacing(0)

        hdr = QHBoxLayout()
        hdr.addWidget(SectionTitle(title))
        hdr.addStretch()
        n = len(packages)
        hdr.addWidget(dimmed(QLabel(f"{n} update{'s' if n != 1 else ''}")))
        hdr.addSpacing(12)
        self._update_all_btn = QPushButton("Update All")
        self._update_all_btn.setFixedWidth(96)
        self._update_all_btn.clicked.connect(
            lambda: self.update_all_clicked.emit(self._packages))
        hdr.addWidget(self._update_all_btn)
        vl.addLayout(hdr)
        vl.addWidget(hline())
        vl.addSpacing(4)

        for i, pkg in enumerate(packages):
            row = PackageUpdateRow(pkg, show_icon=show_icons)
            row.update_clicked.connect(lambda p: self.update_all_clicked.emit([p]))
            vl.addWidget(row)
            self._rows.append(row)
            if i < len(packages) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.HLine)
                sep.setStyleSheet("color: rgba(128,128,128,0.15);")
                vl.addWidget(sep)

    def set_all_updating(self):
        self._update_all_btn.setEnabled(False)
        self._update_all_btn.setText("Updating…")
        for row in self._rows:
            row.set_updating()

    def set_all_done(self, success: bool):
        self._update_all_btn.hide()
        for row in self._rows:
            row.set_done(success)


# ── OS Image card ─────────────────────────────────────────────────────────────

class ImageUpdateCard(QFrame):
    update_clicked = pyqtSignal()
    rollback_clicked = pyqtSignal()

    def __init__(self, info: dict, parent=None):
        super().__init__(parent)
        self._info = info
        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(16, 12, 16, 12)
        vl.setSpacing(0)

        hdr = QHBoxLayout()
        hdr.addWidget(SectionTitle("Operating System"))
        hdr.addStretch()
        hdr.addWidget(dimmed(QLabel("1 update")))
        vl.addLayout(hdr)
        vl.addWidget(hline())
        vl.addSpacing(4)

        booted      = info.get("booted", "current")
        available   = info.get("available", "new")
        update_type = info.get("type", "switch")

        row_hl = QHBoxLayout()
        row_hl.setContentsMargins(4, 8, 8, 8)
        row_hl.setSpacing(10)

        icon_lbl = QLabel("🖥")
        icon_lbl.setFixedSize(36, 36)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = icon_lbl.font()
        f.setPointSize(20)
        icon_lbl.setFont(f)
        row_hl.addWidget(icon_lbl)

        info_col = QVBoxLayout()
        info_col.setSpacing(1)
        name_lbl = QLabel("RakuOS")
        nf = name_lbl.font()
        nf.setPointSize(nf.pointSize() + 1)
        name_lbl.setFont(nf)
        info_col.addWidget(name_lbl)
        if update_type == "switch":
            info_col.addWidget(dimmed(QLabel(f"{booted}  →  {available}")))
        else:
            info_col.addWidget(dimmed(QLabel(f"Refresh of {booted}")))
        row_hl.addLayout(info_col, stretch=1)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(4)
        self._progress.setTextVisible(False)
        self._progress.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._progress.hide()
        row_hl.addWidget(self._progress, stretch=1)

        self._status_lbl = QLabel("")
        self._status_lbl.hide()
        row_hl.addWidget(self._status_lbl)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)
        self._update_btn = QPushButton(
            "Update" if update_type == "switch" else "Apply Hotfix")
        self._update_btn.setFixedWidth(110)
        self._update_btn.clicked.connect(self.update_clicked)
        btn_col.addWidget(self._update_btn)
        rollback_btn = QPushButton("Rollback")
        rollback_btn.setFixedWidth(110)
        rollback_btn.clicked.connect(self.rollback_clicked)
        btn_col.addWidget(rollback_btn)
        row_hl.addLayout(btn_col)
        vl.addLayout(row_hl)

    def set_updating(self):
        self._update_btn.hide()
        self._progress.show()

    def set_done(self, success: bool):
        self._progress.hide()
        self._status_lbl.setText("✓" if success else "✗")
        self._status_lbl.setStyleSheet(
            "color: #4caf50; font-size: 16px;" if success
            else "color: #e53935; font-size: 16px;")
        self._status_lbl.show()


# ── Main page ─────────────────────────────────────────────────────────────────

class UpdatesPage(QWidget):
    def __init__(self):
        super().__init__()
        self._workers: list = []
        self._terminal: TerminalWidget | None = None
        self._reboot_btn: QPushButton | None = None
        self._image_card: ImageUpdateCard | None = None
        self._image_info: dict = {}
        self._all_sections: list[UpdateSection] = []
        self._last_result: dict = {}

        # ── Top bar ──────────────────────────────────────────────────────────
        topbar = QHBoxLayout()
        topbar.setContentsMargins(24, 16, 24, 8)

        title_lbl = QLabel("Updates")
        tf = title_lbl.font()
        tf.setPointSize(tf.pointSize() + 4)
        tf.setBold(True)
        title_lbl.setFont(tf)
        topbar.addWidget(title_lbl)
        topbar.addStretch()

        self._update_all_btn = QPushButton("⬆  Update All")
        self._update_all_btn.setFixedWidth(130)
        self._update_all_btn.hide()
        self._update_all_btn.clicked.connect(self._do_update_all)
        topbar.addWidget(self._update_all_btn)

        self._refresh_btn = QPushButton("↻  Check for Updates")
        self._refresh_btn.setFixedWidth(160)
        self._refresh_btn.clicked.connect(lambda: self.load(None))
        topbar.addWidget(self._refresh_btn)

        topbar_w = QWidget()
        topbar_w.setLayout(topbar)

        # ── Scroll ───────────────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget()
        self._vl = QVBoxLayout(self._content)
        self._vl.setContentsMargins(24, 8, 24, 24)
        self._vl.setSpacing(16)
        scroll.setWidget(self._content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(topbar_w)
        outer.addWidget(scroll)

    # ── Load ─────────────────────────────────────────────────────────────────

    def load(self, result: dict = None):
        self._clear()
        self._update_all_btn.hide()
        if result is not None:
            self._render(result)
        else:
            self._vl.addWidget(LoadingWidget("Checking for updates…"))
            w = Worker(self._fetch_updates)
            w.result.connect(self._render)
            w.start()
            self._workers.append(w)

    def _fetch_updates(self) -> dict:
        import json
        RAKUOS_UPDATE = "/usr/libexec/rakuos/rakuos-update"

        def _check(cmd):
            try:
                r = subprocess.run([RAKUOS_UPDATE, cmd],
                    capture_output=True, text=True, timeout=120)
                data = json.loads(r.stdout)
                return r.returncode == 0, data.get("updates", [])
            except Exception:
                return False, []

        def _check_image():
            try:
                r = subprocess.run([RAKUOS_UPDATE, "check-image"],
                    capture_output=True, text=True, timeout=30)
                data = json.loads(r.stdout)
                return r.returncode == 0, data
            except Exception:
                return False, {}

        _, pkgs          = _check("check")
        _, fps           = _check("check-flatpak")
        img_avail, img_info = _check_image()

        return {
            "packages":        pkgs,
            "flatpak":         fps,
            "image_available": img_avail,
            "image_info":      img_info,
            "total": len(pkgs) + len(fps) + (1 if img_avail else 0),
        }

    # ── Render ────────────────────────────────────────────────────────────────

    def _render(self, result: dict):
        self._clear()
        self._all_sections = []

        self._last_result = result
        pkgs      = result.get("packages", [])
        fps       = result.get("flatpak", [])
        ais       = result.get("appimages", [])
        img_avail = result.get("image_available", False)
        img_info  = result.get("image_info", {})
        total     = result.get("total", 0)
        self._image_info = img_info

        # ── Empty state ───────────────────────────────────────────────────────
        if total == 0:
            self._vl.addStretch()
            up_lbl = QLabel("✓  Fully up to date")
            f = up_lbl.font()
            f.setPointSize(f.pointSize() + 6)
            up_lbl.setFont(f)
            up_lbl.setStyleSheet("color: #4caf50;")
            up_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._vl.addWidget(up_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
            sub = dimmed(QLabel("Your system and all apps are up to date."))
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._vl.addWidget(sub, alignment=Qt.AlignmentFlag.AlignCenter)
            self._vl.addStretch()
            return

        self._update_all_btn.show()

        # ── Group 1: Applications (GUI RPMs + Flatpak apps + AppImages merged) ─
        gui_pkgs = [p for p in pkgs if p.get("gui")]
        fp_apps  = [dict(p, is_flatpak=True) for p in fps if not p.get("runtime")]
        ai_apps  = [dict(a, is_appimage=True) for a in ais]
        app_group = gui_pkgs + fp_apps + ai_apps
        if app_group:
            sec = UpdateSection("Applications", app_group, show_icons=True)
            sec.update_all_clicked.connect(self._on_app_update)
            self._vl.addWidget(sec)
            self._all_sections.append(sec)

        # ── Group 2: Add-ons (Flatpak runtimes/extensions) ────────────────────
        fp_runtimes = [dict(p, is_flatpak=True) for p in fps if p.get("runtime")]
        if fp_runtimes:
            sec = UpdateSection("Add-ons", fp_runtimes)
            sec.update_all_clicked.connect(self._do_fp_update)
            self._vl.addWidget(sec)
            self._all_sections.append(sec)

        # ── Group 3: System Dependencies (non-GUI overlay RPMs) ───────────────
        sys_pkgs = [p for p in pkgs if not p.get("gui")]
        if sys_pkgs:
            sec = UpdateSection("System Dependencies", sys_pkgs)
            sec.update_all_clicked.connect(self._do_pkg_update)
            self._vl.addWidget(sec)
            self._all_sections.append(sec)

        # ── Group 4: OS Image ─────────────────────────────────────────────────
        if img_avail:
            self._image_card = ImageUpdateCard(img_info)
            self._image_card.update_clicked.connect(self._do_image_update)
            self._image_card.rollback_clicked.connect(self._do_rollback)
            self._vl.addWidget(self._image_card)

        # Terminal (hidden until update starts)
        self._terminal = TerminalWidget()
        self._terminal.hide()
        self._vl.addWidget(self._terminal)

        # Reboot button (shown after image update staged)
        self._reboot_btn = QPushButton("🔄  Reboot to Apply")
        self._reboot_btn.setFixedWidth(180)
        self._reboot_btn.hide()
        self._reboot_btn.clicked.connect(upd.schedule_reboot)
        self._vl.addWidget(self._reboot_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        self._vl.addStretch()

    # ── Update actions ────────────────────────────────────────────────────────

    def _show_terminal(self):
        if self._terminal:
            self._terminal.reset()
            self._terminal.show()

    def _on_app_update(self, pkg_list: list):
        """Mixed list of GUI RPMs + Flatpaks + AppImages — split and run each."""
        rpms = [p for p in pkg_list
                if not p.get("is_flatpak") and not p.get("is_appimage")]
        fps  = [p for p in pkg_list if p.get("is_flatpak")]
        ais  = [p for p in pkg_list if p.get("is_appimage")]
        self._show_terminal()
        if rpms:
            w = StreamWorker(upd.upgrade_packages_stream)
            w.line.connect(self._terminal.append_line)
            w.done.connect(lambda c: self._terminal.append_line(
                "\n✓ Packages updated." if c == 0 else f"\n✗ Failed (exit {c})."))
            w.start()
            self._workers.append(w)
        if fps:
            w = StreamWorker(flatpak.update_all_flatpaks_stream)
            w.line.connect(self._terminal.append_line)
            w.done.connect(lambda c: self._terminal.append_line(
                "\n✓ Flatpaks updated." if c == 0 else f"\n✗ Failed (exit {c})."))
            w.start()
            self._workers.append(w)
        from backend import appimages as _aim
        for ai in ais:
            app_id = ai.get("id", "")
            dl_url = ai.get("download_url", "")
            if not app_id or not dl_url:
                continue
            w = StreamWorker(
                lambda _id=app_id, _url=dl_url:
                    _aim.update_appimage_stream(_id, _url))
            w.line.connect(self._terminal.append_line)
            w.done.connect(lambda c, n=ai.get("name", app_id):
                self._terminal.append_line(
                    f"\n✓ {n} updated." if c == 0
                    else f"\n✗ {n} update failed (exit {c})."))
            w.start()
            self._workers.append(w)

    def _do_pkg_update(self, pkg_list: list):
        self._show_terminal()
        w = StreamWorker(upd.upgrade_packages_stream)
        w.line.connect(self._terminal.append_line)
        w.done.connect(lambda c: self._terminal.append_line(
            "\n✓ Packages updated." if c == 0 else f"\n✗ Failed (exit {c})."))
        w.start()
        self._workers.append(w)

    def _do_fp_update(self, fp_list: list):
        self._show_terminal()
        w = StreamWorker(flatpak.update_all_flatpaks_stream)
        w.line.connect(self._terminal.append_line)
        w.done.connect(lambda c: self._terminal.append_line(
            "\n✓ Flatpaks updated." if c == 0 else f"\n✗ Failed (exit {c})."))
        w.start()
        self._workers.append(w)

    def _do_update_all(self):
        self._show_terminal()
        for sec in self._all_sections:
            sec.set_all_updating()
        self._update_all_btn.setEnabled(False)
        self._update_all_btn.setText("Updating…")
        w = StreamWorker(self._run_all_updates_stream)
        w.line.connect(self._terminal.append_line)
        w.done.connect(lambda c: (
            self._terminal.append_line(
                "\n✓ All updates complete." if c == 0
                else f"\n✗ Some updates failed (exit {c})."),
            [sec.set_all_done(c == 0) for sec in self._all_sections]
        ))
        w.start()
        self._workers.append(w)

    def _run_all_updates_stream(self):
        yield from upd.upgrade_packages_stream()
        yield from flatpak.update_all_flatpaks_stream()
        # AppImage updates — userspace, no sudo
        try:
            from backend import appimages as _aim
            for ai_upd in (self._last_result or {}).get("appimages", []):
                app_id = ai_upd.get("id", "")
                dl_url = ai_upd.get("download_url", "")
                if app_id and dl_url:
                    yield from _aim.update_appimage_stream(app_id, dl_url)
        except Exception as e:
            yield f"AppImage update error: {e}"
        yield "__done__0"

    def _do_image_update(self):
        if self._image_card:
            self._image_card.set_updating()
        self._show_terminal()
        info = self._image_info or {}
        w = StreamWorker(
            upd.upgrade_image_stream,
            info.get("type", "switch"),
            info.get("repo", ""),
            info.get("available", ""),
        )
        w.line.connect(self._terminal.append_line)
        w.done.connect(self._image_done)
        w.start()
        self._workers.append(w)

    def _image_done(self, code: int):
        if self._image_card:
            self._image_card.set_done(code == 0)
        if code == 0:
            self._terminal.append_line("\n✓ Image staged. Reboot to apply.")
            if self._reboot_btn:
                self._reboot_btn.show()
        else:
            self._terminal.append_line(f"\n✗ Failed (exit {code}).")

    def _do_rollback(self):
        self._show_terminal()
        w = StreamWorker(upd.rollback_stream)
        w.line.connect(self._terminal.append_line)
        w.done.connect(lambda c: self._terminal.append_line(
            "\n✓ Rollback staged. Reboot to apply." if c == 0
            else f"\n✗ Rollback failed (exit {c})."))
        w.start()
        self._workers.append(w)

    def _clear(self):
        self._terminal = None
        self._reboot_btn = None
        self._image_card = None
        self._image_info = {}
        self._all_sections = []
        while self._vl.count():
            item = self._vl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
