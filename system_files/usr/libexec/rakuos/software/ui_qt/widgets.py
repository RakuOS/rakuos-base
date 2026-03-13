"""
widgets.py — Reusable UI widgets used across all pages.
"""

import os
import urllib.request

from PyQt6.QtWidgets import (
    QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QScrollArea, QSizePolicy,
    QSpacerItem, QDialog, QApplication, QGridLayout,
    QLineEdit, QSlider, QDialogButtonBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QPixmap, QPalette, QCursor, QColor, QIcon, QImage

from .theme import (
    dimmed, bold_font, colored_text,
    col_dim, col_hover, col_success, col_warning,
    _c, _mix,
)

from backend import packages


# ── Layout helpers ────────────────────────────────────────────────────────────

def hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFrameShadow(QFrame.Shadow.Sunken)
    return f


def spacer_v() -> QSpacerItem:
    return QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)


# ── Widgets ───────────────────────────────────────────────────────────────────

class IconWidget(QLabel):
    """Displays an app icon from the AppStream icon cache."""

    def __init__(self, size: int = 64):
        super().__init__("📦")
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = self.font()
        f.setPointSize(size // 3)
        self.setFont(f)
        self._size = size

    def set_icon_name(self, name: str, app_id: str = "", pkg_name: str = "", flatpak_id: str = ""):
        if not name and not app_id and not pkg_name and not flatpak_id:
            return

        # Normalise — strip .desktop suffix everywhere
        app_id = app_id.removesuffix(".desktop")
        flatpak_id = flatpak_id.removesuffix(".desktop")

        # For icon resolution use flatpak_id if available (native stubs carry it)
        icon_id = flatpak_id or app_id

        stem = name
        for ext in (".png", ".svg", ".xpm"):
            if stem.endswith(ext):
                stem = stem[:-len(ext)]
                break

        short = icon_id.split(".")[-1].lower() if icon_id else ""

        def _load(path: str) -> bool:
            pix = QPixmap(path).scaled(
                self._size, self._size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if not pix.isNull():
                self.setPixmap(pix)
                self.setText("")
                return True
            return False

        def _from_theme(candidate: str) -> bool:
            if not candidate:
                return False
            icon = QIcon.fromTheme(candidate)
            if not icon.isNull():
                pix = icon.pixmap(self._size, self._size)
                if not pix.isNull():
                    self.setPixmap(pix)
                    self.setText("")
                    return True
            return False

        # 1. Previously downloaded Flathub icon (instant, cached on disk)
        if icon_id:
            cached = packages.get_cached_icon_path(icon_id)
            if cached and _load(cached):
                return

        # 2. AppStream swcatalog cache (native repo icons)
        for candidate in ([stem] if stem else []) + ([short] if short else []):
            for suffix in ("", ".png", ".svg"):
                path = packages.find_icon(candidate + suffix)
                if path and os.path.exists(path) and _load(path):
                    return

        # 3. Flatpak local icon cache
        flatpak_icon_dirs = [
            "/var/lib/flatpak/appstream/flathub/x86_64/active/icons/64x64",
            "/var/lib/flatpak/appstream/flathub/x86_64/active/icons/128x128",
            "/var/lib/flatpak/appstream/fedora-flatpaks/x86_64/active/icons/64x64",
        ]
        for candidate in ([icon_id] if icon_id else []) + ([stem] if stem else []):
            for d in flatpak_icon_dirs:
                for ext in (".png", ".svg"):
                    p = os.path.join(d, candidate + ext)
                    if os.path.exists(p) and _load(p):
                        return

        # 4. Fetch remotely async — KDE apps.kde.org for org.kde.* else Flathub API
        #    Icon pops in when downloaded, no blocking
        if icon_id:
            self._start_remote_fetch(icon_id)
            return

        # 5. QIcon.fromTheme — last resort, tries full id, short name, pkg_name
        for c in ([app_id] if app_id else []) + ([short] if short else []) + ([stem] if stem else []) + ([pkg_name] if pkg_name else []):
            if _from_theme(c):
                return

    def _start_remote_fetch(self, app_id: str):
        """Fetch icon remotely in background.
        For org.kde.* apps: tries apps.kde.org SVG first, falls back to Flathub.
        For all others: Flathub API icon URL.
        """
        widget_ref = self

        class _FetchThread(QThread):
            def run(self):
                try:
                    data = None

                    # KDE apps — try apps.kde.org SVG first
                    if app_id.startswith("org.kde."):
                        kde_url = f"https://apps.kde.org/app-icons/{app_id}.svg"
                        try:
                            req = urllib.request.Request(
                                kde_url, headers={"User-Agent": "RakuOS-Software/1.0"}
                            )
                            with urllib.request.urlopen(req, timeout=8) as r:
                                if r.status == 200:
                                    data = r.read()
                                    packages.save_icon_to_cache(app_id, data)
                        except Exception:
                            pass  # fall through to Flathub

                    # Flathub API fallback (or primary for non-KDE)
                    if not data:
                        icon_url = packages.get_flathub_icon_url(app_id)
                        if not icon_url:
                            return
                        req = urllib.request.Request(
                            icon_url, headers={"User-Agent": "RakuOS-Software/1.0"}
                        )
                        with urllib.request.urlopen(req, timeout=8) as r:
                            data = r.read()
                        packages.save_icon_to_cache(app_id, data)

                    if not data:
                        return

                    # Render SVG or raster onto main thread
                    img = QImage()
                    img.loadFromData(data)
                    if img.isNull():
                        # Try SVG renderer
                        from PyQt6.QtSvg import QSvgRenderer
                        from PyQt6.QtCore import QByteArray
                        renderer = QSvgRenderer(QByteArray(data))
                        if renderer.isValid():
                            img = QImage(
                                widget_ref._size, widget_ref._size,
                                QImage.Format.Format_ARGB32
                            )
                            img.fill(0)
                            from PyQt6.QtGui import QPainter
                            painter = QPainter(img)
                            renderer.render(painter)
                            painter.end()

                    pix = QPixmap.fromImage(img).scaled(
                        widget_ref._size, widget_ref._size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    if not pix.isNull():
                        widget_ref.setPixmap(pix)
                        widget_ref.setText("")
                except Exception:
                    pass

        t = _FetchThread(self)
        t.start()
        if not hasattr(self, "_icon_threads"):
            self._icon_threads = []
        self._icon_threads.append(t)


class StatusBadge(QLabel):
    """Small rounded badge with a palette-derived tinted background."""

    def __init__(self, text: str, color: QColor):
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bg   = _mix(color, _c(QPalette.ColorRole.Base), 0.85)
        bord = _mix(color, _c(QPalette.ColorRole.Base), 0.6)
        self.setStyleSheet(
            f"border-radius:5px; padding:2px 6px; font-size:10px; font-weight:700;"
            f"color:{color.name()}; background:{bg.name()}; border:1px solid {bord.name()};"
        )


class AppCard(QFrame):
    """Clickable app card used in grid views."""
    clicked = pyqtSignal(dict)

    def __init__(self, app: dict):
        super().__init__()
        self.app = app
        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedSize(160, 190)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(6)

        self.icon_w = IconWidget(56)
        self.icon_w.set_icon_name(app.get("icon", ""), app_id=app.get("id", ""), pkg_name=app.get("pkg_name", ""), flatpak_id=app.get("flatpak_id", ""))
        layout.addWidget(self.icon_w, alignment=Qt.AlignmentFlag.AlignHCenter)

        name_lbl = bold_font(QLabel(app.get("name", "")))
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setWordWrap(True)
        layout.addWidget(name_lbl)

        summary_lbl = dimmed(QLabel(app.get("summary", "")))
        summary_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        summary_lbl.setWordWrap(True)
        summary_lbl.setMaximumHeight(36)
        layout.addWidget(summary_lbl)
        layout.addStretch()

        installed = app.get("installed", False)
        source    = app.get("source", "native")
        if installed:
            badge = StatusBadge("Installed", col_success())
        elif source == "flatpak":
            badge = StatusBadge("Flatpak", _c(QPalette.ColorRole.Highlight))
        else:
            badge = StatusBadge("RPM", col_warning())
        layout.addWidget(badge)

    def enterEvent(self, e):
        p = self.palette()
        p.setColor(QPalette.ColorRole.Window, col_hover())
        self.setPalette(p)
        self.setAutoFillBackground(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.setPalette(QApplication.palette())
        self.setAutoFillBackground(False)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.app)


class FlowGrid(QWidget):
    """Wrapping grid of AppCards."""
    app_clicked = pyqtSignal(dict)

    def __init__(self, cols: int = 5):
        super().__init__()
        self._layout = QGridLayout(self)
        self._layout.setSpacing(12)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._cards: list[AppCard] = []
        self._cols = cols

    def set_apps(self, apps: list[dict]):
        self.clear()
        for i, app in enumerate(apps):
            self._add(app, i)

    def append_apps(self, apps: list[dict]):
        start = len(self._cards)
        for i, app in enumerate(apps):
            self._add(app, start + i)

    def _add(self, app: dict, idx: int):
        card = AppCard(app)
        card.clicked.connect(self.app_clicked)
        self._layout.addWidget(card, idx // self._cols, idx % self._cols)
        self._cards.append(card)

    def clear(self):
        for c in self._cards:
            c.deleteLater()
        self._cards = []


class TerminalWidget(QTextEdit):
    """Read-only terminal output widget for streaming install/update logs."""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setMaximumHeight(200)
        colored_text(self, col_success())
        self.hide()

    def append_line(self, line: str):
        self.append(line)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def reset(self):
        self.clear()
        self.hide()


class NavButton(QPushButton):
    """Sidebar navigation button with active state."""

    def __init__(self, icon_text: str, text: str):
        super().__init__(f"  {icon_text}  {text}")
        self.setObjectName("navbtn")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(38)

    def set_active(self, active: bool):
        from .theme import col_active_nav
        p = self.palette()
        if active:
            p.setColor(QPalette.ColorRole.ButtonText, _c(QPalette.ColorRole.Highlight))
            p.setColor(QPalette.ColorRole.Button, col_active_nav())
        else:
            p.setColor(QPalette.ColorRole.ButtonText, _c(QPalette.ColorRole.WindowText))
            p.setColor(QPalette.ColorRole.Button, Qt.GlobalColor.transparent)
        self.setPalette(p)
        self.setAutoFillBackground(active)
        self.update()


class SectionTitle(QLabel):
    """Bold section heading label."""

    def __init__(self, text: str):
        super().__init__(text)
        bold_font(self, extra_pts=2)


class LoadingWidget(QWidget):
    """Centered loading indicator."""

    def __init__(self, text: str = "Loading…"):
        super().__init__()
        l = QHBoxLayout(self)
        lbl = dimmed(QLabel(f"⏳  {text}"))
        l.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)


class LightboxDialog(QDialog):
    """Popup image viewer — round X button to close."""

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        container = QFrame()
        container.setFrameShape(QFrame.Shape.StyledPanel)
        container.setStyleSheet(
            "QFrame { background: rgba(0,0,0,200); border-radius: 14px; }"
        )
        cl = QVBoxLayout(container)
        cl.setContentsMargins(20, 12, 20, 20)
        cl.setSpacing(10)

        # Round X close button — top right
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedSize(32, 32)
        self._close_btn.setStyleSheet(
            "QPushButton {"
            "  border-radius: 16px;"
            "  background: rgba(255,255,255,0.15);"
            "  color: white; font-weight: bold; font-size: 14px; border: none;"
            "}"
            "QPushButton:hover { background: rgba(255,255,255,0.3); }"
        )
        self._close_btn.clicked.connect(self._do_close)
        btn_row.addWidget(self._close_btn)
        cl.addLayout(btn_row)

        img = QLabel()
        screen = QApplication.primaryScreen().size()
        scaled = pixmap.scaled(
            int(screen.width() * 0.55), int(screen.height() * 0.52),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        img.setPixmap(scaled)
        img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img.setStyleSheet("background: transparent; border: none;")
        cl.addWidget(img)

        outer.addWidget(container)

    def _do_close(self):
        self.done(0)

    def keyPressEvent(self, event):
        from PyQt6.QtCore import Qt as _Qt
        if event.key() == _Qt.Key.Key_Escape:
            self.done(0)
        else:
            super().keyPressEvent(event)



class ClickableImage(QLabel):
    """A QLabel that opens a LightboxDialog when clicked."""
    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._full_pixmap = pixmap
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFrameShape(QFrame.Shape.StyledPanel)

    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                dlg = LightboxDialog(self._full_pixmap, self)
                dlg.exec()
        except Exception:
            pass
        super().mousePressEvent(event)



# ── Reviews widget ────────────────────────────────────────────────────────────

from PyQt6.QtWidgets import QTextEdit, QDialog, QDialogButtonBox, QSlider


class StarRatingWidget(QLabel):
    """Displays a star rating with count label."""

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.set_rating(0, 0)

    def set_rating(self, rating_0_100: int, count: int):
        from backend.reviews import stars_from_rating
        if count == 0:
            self.setText("No ratings yet")
            dimmed(self)
        else:
            stars = stars_from_rating(rating_0_100)
            f = self.font()
            f.setPointSize(f.pointSize() + 2)
            self.setFont(f)
            self.setText(f"{stars}  ({count} ratings)")


class ReviewCard(QFrame):
    """Single review card."""

    def __init__(self, review: dict):
        super().__init__()
        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        # Header: stars + summary + author
        header = QHBoxLayout()
        from backend.reviews import stars_from_rating
        rating = review.get("rating", 0)
        stars_lbl = QLabel(stars_from_rating(rating))
        stars_lbl.setStyleSheet("font-size: 13px;")
        header.addWidget(stars_lbl)

        summary = bold_font(QLabel(review.get("summary", "")))
        summary.setWordWrap(True)
        header.addWidget(summary, stretch=1)

        author = dimmed(QLabel(review.get("user_display") or "Anonymous"))
        author.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(author)
        layout.addLayout(header)

        # Body
        desc = review.get("description", "").strip()
        if desc:
            body = QLabel(desc)
            body.setWordWrap(True)
            body.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(body)

        # Footer: distro + version + date
        footer_parts = []
        if review.get("distro"):
            footer_parts.append(review["distro"])
        if review.get("version"):
            footer_parts.append(f"v{review['version']}")
        if review.get("date_created"):
            from datetime import datetime
            try:
                dt = datetime.fromtimestamp(review["date_created"])
                footer_parts.append(dt.strftime("%b %Y"))
            except Exception:
                pass
        if footer_parts:
            footer = dimmed(QLabel(" · ".join(footer_parts)))
            footer.setStyleSheet("font-size: 11px;")
            layout.addWidget(footer)


class WriteReviewDialog(QDialog):
    """Dialog for submitting a new review."""

    def __init__(self, app_name: str, app_id: str, parent=None):
        super().__init__(parent)
        self.app_id = app_id
        self.setWindowTitle(f"Review {app_name}")
        self.setMinimumWidth(460)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(bold_font(QLabel(f"Write a review for {app_name}")))

        # Star slider
        star_row = QHBoxLayout()
        star_row.addWidget(dimmed(QLabel("Your rating:")))
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(1, 5)
        self._slider.setValue(4)
        self._slider.setTickInterval(1)
        self._slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        star_row.addWidget(self._slider)
        self._star_lbl = QLabel("★★★★☆")
        self._star_lbl.setFixedWidth(80)
        star_row.addWidget(self._star_lbl)
        self._slider.valueChanged.connect(self._on_stars)
        layout.addLayout(star_row)

        # Summary
        layout.addWidget(QLabel("Summary (one line):"))
        self._summary = QLineEdit()
        self._summary.setPlaceholderText("e.g. Great app for everyday use")
        self._summary.setMaxLength(80)
        layout.addWidget(self._summary)

        # Description
        layout.addWidget(QLabel("Your review:"))
        self._desc = QTextEdit()
        self._desc.setPlaceholderText("Tell others what you think…")
        self._desc.setFixedHeight(100)
        layout.addWidget(self._desc)

        # Privacy note
        note = dimmed(QLabel(
            "ⓘ  Reviews are submitted anonymously to odrs.gnome.org "
            "and shared with GNOME Software, KDE Discover, and other app centers."
        ))
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 11px;")
        layout.addWidget(note)

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Submit Review")
        btns.accepted.connect(self._submit)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._result_lbl = QLabel("")
        self._result_lbl.setWordWrap(True)
        layout.addWidget(self._result_lbl)

    def _on_stars(self, value: int):
        self._star_lbl.setText("★" * value + "☆" * (5 - value))

    def _submit(self):
        from backend import reviews as rev_backend
        summary = self._summary.text().strip()
        desc = self._desc.toPlainText().strip()
        rating = self._slider.value() * 20  # 1-5 → 20-100

        ok, msg = rev_backend.submit_review(
            self.app_id, summary, desc, rating
        )
        if ok:
            from .theme import col_success
            colored_text(self._result_lbl, col_success())
            self._result_lbl.setText(f"✓ {msg}")
            self.accept()
        else:
            from .theme import col_danger
            colored_text(self._result_lbl, col_danger())
            self._result_lbl.setText(f"✗ {msg}")


# ── Add-ons Dialog ────────────────────────────────────────────────────────────

class AddonRow(QFrame):
    """Single row in the add-ons dialog with an install/remove progress button."""

    install_requested = pyqtSignal(dict)
    remove_requested  = pyqtSignal(dict)

    def __init__(self, addon: dict):
        super().__init__()
        self._addon = addon
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("card")

        rl = QHBoxLayout(self)
        rl.setContentsMargins(12, 10, 12, 10)
        rl.setSpacing(10)

        icon_w = IconWidget(40)
        icon_w.set_icon_name(addon.get("icon", ""), app_id=addon.get("id", ""), pkg_name=addon.get("pkg_name", ""))
        rl.addWidget(icon_w)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name = addon.get("name") or addon.get("id", "")
        text_col.addWidget(bold_font(QLabel(name)))
        summary = addon.get("summary", "")
        if summary:
            sl = dimmed(QLabel(summary))
            sl.setWordWrap(True)
            text_col.addWidget(sl)
        rl.addLayout(text_col, stretch=1)

        self._btn = QPushButton()
        self._btn.setFixedWidth(110)
        self._btn.setFixedHeight(32)
        self._update_btn()
        self._btn.clicked.connect(self._on_click)
        rl.addWidget(self._btn)

    def _update_btn(self):
        installed = self._addon.get("installed", False)
        self._btn.setText("Remove" if installed else "Install")
        self._btn.setProperty("danger", installed)
        self._btn.style().unpolish(self._btn)
        self._btn.style().polish(self._btn)
        self._btn.setEnabled(True)

    def _on_click(self):
        self._btn.setText("Working…")
        self._btn.setEnabled(False)
        if self._addon.get("installed"):
            self.remove_requested.emit(self._addon)
        else:
            self.install_requested.emit(self._addon)

    def mark_done(self, installed: bool):
        self._addon["installed"] = installed
        self._update_btn()

    def mark_failed(self):
        self._addon_installed = self._addon.get("installed", False)
        self._btn.setText("Failed")
        self._btn.setEnabled(True)


class AddonsDialog(QDialog):
    """Popup listing all add-ons for an app with Install/Remove buttons."""

    install_requested = pyqtSignal(dict)
    remove_requested  = pyqtSignal(dict)

    def __init__(self, addons: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add-ons")
        self.setMinimumWidth(520)
        self.setMinimumHeight(min(120 + len(addons) * 80, 600))
        self.setModal(True)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(16, 16, 16, 16)
        vl.setSpacing(10)

        vl.addWidget(bold_font(QLabel(f"{len(addons)} add-on{'s' if len(addons) != 1 else ''} available"), extra_pts=1))
        vl.addSpacing(4)

        # Scrollable list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner_vl = QVBoxLayout(inner)
        inner_vl.setContentsMargins(0, 0, 0, 0)
        inner_vl.setSpacing(8)

        self._rows: dict[str, AddonRow] = {}
        for addon in addons:
            row = AddonRow(addon)
            row.install_requested.connect(self._on_install)
            row.remove_requested.connect(self._on_remove)
            inner_vl.addWidget(row)
            self._rows[addon.get("id", addon.get("pkg_name", ""))] = row

        inner_vl.addStretch()
        scroll.setWidget(inner)
        vl.addWidget(scroll)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        vl.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _on_install(self, addon: dict):
        self.install_requested.emit(addon)

    def _on_remove(self, addon: dict):
        self.remove_requested.emit(addon)