"""
pages/updates.py — System image and Flatpak updates page.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QLabel,
    QHBoxLayout, QPushButton,
)
from PyQt6.QtCore import pyqtSignal

from ..workers import Worker, StreamWorker
from ..widgets import SectionTitle, LoadingWidget, TerminalWidget
from ..theme import colored_text, col_success, col_warning
from backend import flatpak, updates


class UpdatesPage(QWidget):
    def __init__(self):
        super().__init__()
        self._workers: list[Worker] = []
        self._terminal: TerminalWidget | None = None
        self._reboot_btn: QPushButton | None = None

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget()
        self._vl = QVBoxLayout(self._content)
        self._vl.setContentsMargins(24, 20, 24, 20)
        self._vl.setSpacing(16)
        scroll.setWidget(self._content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def load(self):
        self._clear()
        self._vl.addWidget(LoadingWidget("Checking for updates…"))
        w = Worker(lambda: (updates.check_for_update(), flatpak.get_flatpak_updates()))
        w.result.connect(self._on_data)
        w.start()
        self._workers.append(w)

    def _on_data(self, data: tuple):
        system, fp_updates = data
        self._clear()

        # ── System image card ─────────────────────────────────────────────────
        sys_card = self._make_card()
        cl = sys_card.layout()
        cl.addWidget(SectionTitle("🖥  System Image"))

        if system.get("error"):
            cl.addWidget(QLabel(f"Error: {system['error']}"))
        elif system.get("update_available"):
            row = QHBoxLayout()
            row.addWidget(QLabel(
                f"{system.get('current_version', '')}  →  {system.get('new_version', '')}"
            ))
            row.addStretch()
            btn = QPushButton("Update Now")
            btn.setDefault(True)
            btn.setMinimumWidth(120)
            btn.clicked.connect(self._do_system_update)
            row.addWidget(btn)
            cl.addLayout(row)
        else:
            cl.addWidget(colored_text(
                QLabel(f"Up to date  ·  {system.get('current_version', '')}"),
                col_success(),
            ))

        rollback = QPushButton("Rollback to previous image")
        rollback.setFixedWidth(210)
        rollback.clicked.connect(self._do_rollback)
        cl.addWidget(rollback)
        self._vl.addWidget(sys_card)

        # ── Flatpak updates card ──────────────────────────────────────────────
        fp_card = self._make_card()
        fl = fp_card.layout()
        fl.addWidget(SectionTitle("📦  Flatpak Updates"))

        if fp_updates:
            row2 = QHBoxLayout()
            n = len(fp_updates)
            row2.addWidget(colored_text(
                QLabel(f"{n} update{'s' if n != 1 else ''} available"),
                col_warning(),
            ))
            row2.addStretch()
            fbtn = QPushButton("Update All Flatpaks")
            fbtn.setDefault(True)
            fbtn.setMinimumWidth(150)
            fbtn.clicked.connect(self._do_flatpak_update)
            row2.addWidget(fbtn)
            fl.addLayout(row2)
        else:
            fl.addWidget(colored_text(QLabel("All Flatpaks up to date"), col_success()))
        self._vl.addWidget(fp_card)

        self._terminal = TerminalWidget()
        self._vl.addWidget(self._terminal)

        self._reboot_btn = QPushButton("🔄  Reboot to Apply")
        self._reboot_btn.setFixedWidth(180)
        self._reboot_btn.hide()
        self._reboot_btn.clicked.connect(updates.schedule_reboot)
        self._vl.addWidget(self._reboot_btn)
        self._vl.addStretch()

    def _make_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 16, 18, 16)
        cl.setSpacing(10)
        return card

    def _do_system_update(self):
        self._terminal.reset()
        status = updates.check_for_update()
        w = StreamWorker(
            updates.apply_update_stream,
            status.get("new_tag", ""),
            status.get("repo_url", ""),
        )
        w.line.connect(self._terminal.append_line)
        w.done.connect(self._update_done)
        w.start()
        self._workers.append(w)

    def _do_rollback(self):
        self._terminal.reset()
        w = StreamWorker(updates.rollback_stream)
        w.line.connect(self._terminal.append_line)
        w.done.connect(self._update_done)
        w.start()
        self._workers.append(w)

    def _do_flatpak_update(self):
        self._terminal.reset()
        w = StreamWorker(flatpak.update_all_flatpaks_stream)
        w.line.connect(self._terminal.append_line)
        w.done.connect(lambda c: self._terminal.append_line(
            "\n✓ Flatpaks updated." if c == 0 else f"\n✗ Failed (exit {c})."
        ))
        w.start()
        self._workers.append(w)

    def _update_done(self, code: int):
        self._terminal.append_line(
            "\n✓ Done. Reboot to apply." if code == 0 else f"\n✗ Failed (exit {code})."
        )
        if code == 0 and self._reboot_btn:
            self._reboot_btn.show()

    def _clear(self):
        while self._vl.count():
            i = self._vl.takeAt(0)
            if i.widget():
                i.widget().deleteLater()
