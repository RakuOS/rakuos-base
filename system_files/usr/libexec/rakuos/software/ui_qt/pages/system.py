"""
pages/system.py — System info page (booted image + overlay packages).
"""

import subprocess

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QFrame, QLabel,
    QHBoxLayout, QPushButton,
)
from PyQt6.QtCore import Qt

from ..workers import Worker
from ..widgets import SectionTitle, LoadingWidget
from ..theme import dimmed, bold_font
from backend import updates


class SystemPage(QWidget):
    def __init__(self):
        super().__init__()
        self._workers: list[Worker] = []

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
        self._vl.addWidget(LoadingWidget())
        w = Worker(lambda: (updates.get_system_status(), updates.get_overlay_status()))
        w.result.connect(self._on_data)
        w.start()
        self._workers.append(w)

    def _on_data(self, data: tuple):
        status, overlay = data
        self._clear()

        # ── Booted image card ─────────────────────────────────────────────────
        img_card = self._make_card()
        cl = img_card.layout()
        cl.addWidget(SectionTitle("🖥  Booted Image"))

        digest = status.get("digest") or ""
        for key, val in [
            ("Image",   status.get("image",   "—")),
            ("Version", status.get("version", "—")),
            ("Digest",  digest[:16] + "…" if digest else "—"),
        ]:
            row = QHBoxLayout()
            kl = dimmed(QLabel(key))
            kl.setFixedWidth(80)
            row.addWidget(kl)
            vl = bold_font(QLabel(str(val)))
            vl.setWordWrap(True)
            row.addWidget(vl)
            row.addStretch()
            cl.addLayout(row)

        self._vl.addWidget(img_card)

        # ── Overlay packages card ─────────────────────────────────────────────
        ov_card = self._make_card()
        ol = ov_card.layout()
        ol.addWidget(SectionTitle("📦  Overlay Packages"))

        pkgs = overlay.get("packages", [])
        if pkgs:
            for pkg in pkgs:
                ol.addWidget(QLabel(f"  • {pkg}"))
        else:
            ol.addWidget(dimmed(QLabel("No overlay packages installed")))

        reset_btn = QPushButton("Reset Overlay")
        reset_btn.setFixedWidth(130)
        reset_btn.clicked.connect(self._reset_overlay)
        ol.addWidget(reset_btn)
        self._vl.addWidget(ov_card)
        self._vl.addStretch()

    def _make_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 16, 18, 16)
        cl.setSpacing(8)
        return card

    def _reset_overlay(self):
        subprocess.Popen(
            ["pkexec", "/usr/libexec/rakuos/rakuos", "reset-overlay", "--confirm"]
        )

    def _clear(self):
        while self._vl.count():
            i = self._vl.takeAt(0)
            if i.widget():
                i.widget().deleteLater()
