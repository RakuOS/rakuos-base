"""
pages/system.py — System info + DE image switcher.

Shows:
  - Current booted image details (image, version, digest, timestamp)
  - DE Selector — dropdown of available RakuOS image variants
    Current image gets a ✓. Selecting a different one shows a Switch button.
    Switch button → inline progress bar → Reboot button on completion.
  - Overlay packages list + Reset Overlay button

Adding a new DE later:
  Add an entry to RAKUOS_IMAGES below. That's it.
"""

import re
import subprocess
import urllib.request
import urllib.error
import json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
    QLabel, QPushButton, QComboBox, QSizePolicy, QStackedWidget,
    QProgressBar,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from ..workers import Worker, StreamWorker
from ..widgets import SectionTitle, LoadingWidget, hline
from ..theme import dimmed, bold_font
from backend import updates


# ── Available RakuOS image variants ──────────────────────────────────────────
# To add a new DE: append an entry here.
#   label       — shown in the dropdown
#   image_name  — base GHCR repo name (without -nvidia suffix)
#
# Nvidia variant is detected automatically from the booted image name —
# if the current image ends in -nvidia, the switch target will also use
# the -nvidia variant of the selected DE.
#
RAKUOS_IMAGES = [
    {"label": "KDE Plasma",  "image_name": "rakuos-kde"},
    {"label": "GNOME",       "image_name": "rakuos-gnome"},
    # {"label": "COSMIC",    "image_name": "rakuos-cosmic"},   # uncomment when ready
]

GHCR_ORG = "rakuos"   # ghcr.io/<GHCR_ORG>/<image_name>


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_image_name(image_full: str) -> tuple[str, bool]:
    """
    Extract (image_name, is_nvidia) from full ref.
    e.g. ghcr.io/rakuos/rakuos-kde-nvidia:latest → ("rakuos-kde-nvidia", True)
         ghcr.io/rakuos/rakuos-kde:latest         → ("rakuos-kde", False)
    """
    try:
        path = image_full.replace("ghcr.io/", "").split(":")[0]
        name = path.split("/")[-1]
        is_nvidia = name.endswith("-nvidia")
        return name, is_nvidia
    except Exception:
        return "", False


def _base_image_name(image_name: str) -> str:
    """Strip -nvidia suffix to get the base DE image name."""
    return image_name.removesuffix("-nvidia")


def _nvidia_image_name(image_name: str) -> str:
    """Add -nvidia suffix if not already present."""
    base = _base_image_name(image_name)
    return f"{base}-nvidia"


def _get_latest_tag_for(image_name: str) -> str:
    """
    Fetch the latest date tag for a given image from GHCR.
    Returns the tag string on success, or:
      "__unavailable__" if image does not exist (403/404)
      ""               on other errors
    """
    repo_path = f"{GHCR_ORG}/{image_name}"
    try:
        token = updates._get_ghcr_token(repo_path)
        annotation = updates._get_latest_version_annotation(repo_path, token)
        tag = re.sub(r"^latest\.", "", annotation).strip()
        if re.match(r"^\d{8}$", tag):
            return tag
        return ""
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            print(f"[system] {image_name} not available on GHCR ({e.code})")
            return "__unavailable__"
        print(f"[system] _get_latest_tag_for {image_name}: {e}")
        return ""
    except Exception as e:
        print(f"[system] _get_latest_tag_for {image_name}: {e}")
        return ""


def _switch_image_stream(image_name: str, tag: str):
    """Generator that runs bootc switch and yields output lines."""
    target = f"ghcr.io/{GHCR_ORG}/{image_name}:{tag}"
    print(f"[system] bootc switch → {target}")
    try:
        proc = subprocess.Popen(
            ["sudo", "bootc", "switch", target],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in proc.stdout:
            yield line.rstrip()
        proc.wait()
        yield f"__done__{proc.returncode}"
    except Exception as e:
        yield f"Error: {e}"
        yield "__done__1"


# ── DE Selector card ──────────────────────────────────────────────────────────

class DESelectorCard(QFrame):
    """
    Card showing current DE + dropdown to switch.
    States: idle → switching (progress) → done (reboot button)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers: list = []
        self._current_image_name = ""
        self._target_image_name  = ""
        self._target_tag         = ""
        self._is_nvidia          = False

        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._vl = QVBoxLayout(self)
        self._vl.setContentsMargins(18, 16, 18, 16)
        self._vl.setSpacing(12)

        self._vl.addWidget(SectionTitle("🖥  Desktop Environment"))

        # ── Dropdown row ──────────────────────────────────────────────────────
        drop_row = QHBoxLayout()
        drop_row.addWidget(dimmed(QLabel("Image:")))
        self._combo = QComboBox()
        self._combo.setMinimumWidth(220)
        for entry in RAKUOS_IMAGES:
            self._combo.addItem(entry["label"], entry["image_name"])
        self._combo.currentIndexChanged.connect(self._on_combo_changed)
        drop_row.addWidget(self._combo)
        drop_row.addStretch()
        self._vl.addLayout(drop_row)

        # ── Right side stack: Switch btn / progress / reboot ──────────────────
        action_row = QHBoxLayout()
        action_row.addStretch()

        self._stack = QStackedWidget()
        self._stack.setFixedHeight(36)
        self._stack.setFixedWidth(220)

        # Page 0 — Switch button (hidden until different DE selected)
        self._switch_btn = QPushButton()
        self._switch_btn.setFixedHeight(34)
        self._switch_btn.clicked.connect(self._do_switch)
        self._switch_btn.hide()
        self._stack.addWidget(self._switch_btn)

        # Page 1 — Progress bar
        prog_wrap = QWidget()
        pw = QVBoxLayout(prog_wrap)
        pw.setContentsMargins(0, 12, 0, 12)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(8)
        pw.addWidget(self._progress)
        self._stack.addWidget(prog_wrap)

        # Page 2 — Reboot button
        self._reboot_btn = QPushButton("🔄  Reboot to Apply")
        self._reboot_btn.setFixedHeight(34)
        self._reboot_btn.setStyleSheet(
            "QPushButton { background: #1976d2; color: white; border-radius: 4px;"
            " font-weight: bold; }"
            "QPushButton:hover { background: #1565c0; }")
        self._reboot_btn.clicked.connect(
            lambda: subprocess.Popen(["systemctl", "reboot"]))
        self._stack.addWidget(self._reboot_btn)

        self._stack.setCurrentIndex(0)
        action_row.addWidget(self._stack)
        self._vl.addLayout(action_row)

        # ── Status label (shows "Fetching latest tag…" / error) ──────────────
        self._status_lbl = dimmed(QLabel(""))
        self._status_lbl.setWordWrap(True)
        self._vl.addWidget(self._status_lbl)

        # ── Output log (shown during switch) ─────────────────────────────────
        self._log = QLabel("")
        self._log.setWordWrap(True)
        self._log.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self._log.setStyleSheet(
            "font-family: monospace; font-size: 11px; "
            "background: rgba(0,0,0,0.06); padding: 8px; border-radius: 4px;")
        self._log.hide()
        self._vl.addWidget(self._log)

    def set_current(self, image_name: str, is_nvidia: bool = False):
        """Set the currently booted image name and configure dropdown."""
        self._current_image_name = image_name
        self._is_nvidia          = is_nvidia

        # Show Nvidia badge if applicable
        nvidia_note = "  💠 Nvidia" if is_nvidia else ""

        # Match against base name (strip -nvidia for comparison)
        base_current = _base_image_name(image_name)

        # Mark current in combo items and select it
        for i in range(self._combo.count()):
            img = self._combo.itemData(i)   # base image name e.g. rakuos-kde
            label = RAKUOS_IMAGES[i]["label"]
            if img == base_current:
                self._combo.setItemText(i, f"✓  {label}{nvidia_note}")
                self._combo.setCurrentIndex(i)
            else:
                self._combo.setItemText(i, f"    {label}")

        self._switch_btn.hide()
        self._stack.setCurrentIndex(0)
        self._status_lbl.setText("")

    def _on_combo_changed(self, idx: int):
        if idx < 0:
            return
        selected_base = self._combo.itemData(idx)   # e.g. rakuos-kde
        # Apply nvidia suffix if current image is nvidia
        selected_full = (_nvidia_image_name(selected_base)
                         if self._is_nvidia else selected_base)

        if selected_base == _base_image_name(self._current_image_name):
            self._switch_btn.hide()
            self._status_lbl.setText("")
            return

        # Show switch button with DE name + nvidia hint if applicable
        label = RAKUOS_IMAGES[idx]["label"]
        nvidia_hint = " (Nvidia)" if self._is_nvidia else ""
        self._switch_btn.setText(f"Switch to {label}{nvidia_hint}")
        self._switch_btn.show()
        self._switch_btn.setEnabled(False)
        self._status_lbl.setText("Fetching latest tag…")
        self._stack.setCurrentIndex(0)

        # Fetch latest tag for the target image (with nvidia suffix if needed)
        target = selected_full
        w = Worker(lambda: _get_latest_tag_for(target))
        w.result.connect(lambda tag: self._on_tag_fetched(target, tag))
        w.start()
        self._workers.append(w)

    def _on_tag_fetched(self, image_name: str, tag: str):
        self._target_image_name = image_name
        self._target_tag        = tag

        if tag == "__unavailable__":
            # Mark combo item as not yet available
            idx = self._combo.currentIndex()
            label = RAKUOS_IMAGES[idx]["label"]
            self._combo.setItemText(idx, f"    {label}  (coming soon)")
            self._switch_btn.hide()
            self._status_lbl.setText(
                "⚠  This image is not yet available.")
            self._status_lbl.setStyleSheet("color: palette(mid);")
        elif tag:
            self._status_lbl.setText(f"Latest build: {tag}")
            self._status_lbl.setStyleSheet("")
            self._switch_btn.setEnabled(True)
        else:
            self._status_lbl.setText(
                "⚠  Could not fetch latest tag — check connection.")
            self._status_lbl.setStyleSheet("color: #e53935;")
            self._switch_btn.setEnabled(False)

    def _do_switch(self):
        if not self._target_tag:
            return
        self._switch_btn.setEnabled(False)
        self._stack.setCurrentIndex(1)   # progress bar
        self._log.setText("")
        self._log.show()
        self._status_lbl.setText(
            f"Switching to ghcr.io/{GHCR_ORG}/{self._target_image_name}:{self._target_tag}")
        self._log_lines = []

        w = StreamWorker(
            lambda: _switch_image_stream(self._target_image_name, self._target_tag))
        w.line.connect(self._on_log_line)
        w.done.connect(self._on_switch_done)
        w.start()
        self._workers.append(w)

    def _on_log_line(self, line: str):
        self._log_lines = getattr(self, "_log_lines", [])
        self._log_lines.append(line)
        # Keep last 20 lines
        if len(self._log_lines) > 20:
            self._log_lines = self._log_lines[-20:]
        self._log.setText("\n".join(self._log_lines))

    def _on_switch_done(self, code: int):
        if code == 0:
            self._stack.setCurrentIndex(2)   # reboot button
            self._status_lbl.setText(
                "\u2713 Switch staged successfully. Reboot to apply.")
            self._status_lbl.setStyleSheet("color: #4caf50;")
        else:
            self._stack.setCurrentIndex(0)
            self._switch_btn.setEnabled(True)
            self._status_lbl.setText(
                "\u2717 Switch failed. Check output above.")
            self._status_lbl.setStyleSheet("color: #e53935;")


# ── System page ───────────────────────────────────────────────────────────────

class SystemPage(QWidget):
    def __init__(self):
        super().__init__()
        self._workers: list[Worker] = []

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget(scroll)
        self._vl = QVBoxLayout(self._content)
        self._vl.setContentsMargins(24, 20, 24, 20)
        self._vl.setSpacing(16)
        self._vl.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)
        scroll.setWidget(self._content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def load(self):
        self._clear()
        self._vl.addWidget(LoadingWidget())
        def _fetch():
            from pathlib import Path
            status  = updates.get_system_status()
            pkgs_file = Path("/var/lib/rakuos/packages.list")
            pkgs = []
            if pkgs_file.exists():
                pkgs = [l.strip() for l in pkgs_file.read_text().splitlines()
                        if l.strip() and not l.startswith("#")]
            print(f"[system] packages.list read: {len(pkgs)} packages")
            return status, {"packages": pkgs}

        w = Worker(_fetch)
        w.result.connect(self._on_data)
        w.start()
        self._workers.append(w)

    def _on_data(self, data: tuple):
        status, overlay = data
        self._clear()

        image_full = status.get("image", "")
        version    = status.get("version", "")
        digest     = status.get("digest", "")
        timestamp  = status.get("timestamp", "")
        current_name, is_nvidia = _parse_image_name(image_full)

        # ── Image details card ─────────────────────────────────────────────────
        img_card = self._make_card()
        cl = img_card.layout()
        cl.addWidget(SectionTitle("\U0001f5a5  Booted Image"))

        nvidia_str = "\U0001f4a0 Yes" if is_nvidia else "No"
        rows = [
            ("Image",     image_full or "\u2014"),
            ("Version",   version    or "\u2014"),
            ("Digest",    (digest[:24] + "\u2026") if digest else "\u2014"),
            ("Timestamp", timestamp  or "\u2014"),
            ("Nvidia",    nvidia_str),
        ]
        for key, val in rows:
            row = QHBoxLayout()
            kl = dimmed(QLabel(key))
            kl.setFixedWidth(90)
            row.addWidget(kl)
            vl = QLabel(str(val))
            vl.setWordWrap(True)
            vl.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(vl, stretch=1)
            cl.addLayout(row)

        self._vl.addWidget(img_card)

        # ── DE Selector card ───────────────────────────────────────────────────
        self._de_card = DESelectorCard()
        self._de_card.set_current(current_name, is_nvidia)
        self._vl.addWidget(self._de_card)

        # ── Overlay packages card ──────────────────────────────────────────────
        ov_card = self._make_card()
        ol = ov_card.layout()

        # Header row: title + Reset button on the right
        hdr = QHBoxLayout()
        hdr.addWidget(SectionTitle("\U0001f4e6  Overlay Packages"))
        hdr.addStretch()
        reset_btn = QPushButton("Reset Overlay")
        reset_btn.setFixedWidth(130)
        reset_btn.clicked.connect(self._reset_overlay)
        hdr.addWidget(reset_btn)
        ol.addLayout(hdr)
        ol.addWidget(hline())

        pkgs = overlay.get("packages", [])
        if pkgs:
            for pkg in sorted(pkgs):
                lbl = QLabel(f"  • {pkg}")
                lbl.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse)
                ol.addWidget(lbl)
        else:
            ol.addWidget(dimmed(QLabel("No overlay packages installed")))

        self._vl.addWidget(ov_card)
        self._vl.addStretch()  # pushes cards to top, scroll handles the rest

    def _make_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 16, 18, 16)
        cl.setSpacing(8)
        return card

    def _reset_overlay(self):
        subprocess.Popen(
            ["sudo", "/usr/libexec/rakuos/rakuos-reset-overlay", "--confirm"])

    def _clear(self):
        while self._vl.count():
            i = self._vl.takeAt(0)
            if i.widget():
                i.widget().deleteLater()
