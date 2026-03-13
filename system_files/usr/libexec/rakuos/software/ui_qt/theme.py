"""
theme.py — Palette helpers and structural stylesheet.
Zero hardcoded colors — all derived from the active Qt/KDE palette at runtime.
"""

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QColor, QPalette


def _c(role: QPalette.ColorRole) -> QColor:
    return QApplication.palette().color(role)


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    """Blend: t=0 → a, t=1 → b"""
    return QColor(
        int(a.red()   + (b.red()   - a.red())   * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue()  + (b.blue()  - a.blue())  * t),
    )


def col_dim() -> QColor:
    ph = _c(QPalette.ColorRole.PlaceholderText)
    return ph if ph.isValid() and ph.alpha() > 10 \
        else _mix(_c(QPalette.ColorRole.WindowText), _c(QPalette.ColorRole.Base), 0.5)


def col_hover() -> QColor:
    return _mix(_c(QPalette.ColorRole.Highlight), _c(QPalette.ColorRole.Base), 0.88)


def col_active_nav() -> QColor:
    return _mix(_c(QPalette.ColorRole.Highlight), _c(QPalette.ColorRole.Window), 0.85)


def _is_dark() -> bool:
    w = _c(QPalette.ColorRole.Window)
    return (0.299 * w.red() + 0.587 * w.green() + 0.114 * w.blue()) < 128


def col_success() -> QColor:
    return QColor("#4ade80") if _is_dark() else QColor("#16a34a")


def col_warning() -> QColor:
    return QColor("#fbbf24") if _is_dark() else QColor("#d97706")


def col_danger() -> QColor:
    return QColor("#f87171") if _is_dark() else QColor("#dc2626")


def dimmed(widget):
    """Apply dim/placeholder color to a widget's text. Returns widget."""
    p = widget.palette()
    p.setColor(QPalette.ColorRole.WindowText, col_dim())
    widget.setPalette(p)
    return widget


def colored_text(widget, color: QColor):
    """Apply a specific color to a widget's text. Returns widget."""
    p = widget.palette()
    p.setColor(QPalette.ColorRole.WindowText, color)
    widget.setPalette(p)
    return widget


def bold_font(widget, extra_pts: int = 0):
    """Make a widget's font bold, optionally larger. Returns widget."""
    f = widget.font()
    f.setBold(True)
    if extra_pts:
        f.setPointSize(f.pointSize() + extra_pts)
    widget.setFont(f)
    return widget


# Purely structural stylesheet — no color values
STYLE = """
QScrollArea, QScrollArea > QWidget > QWidget { border: none; }
QScrollBar:vertical   { width: 6px;  border-radius: 3px; border: none; }
QScrollBar:horizontal { height: 6px; border-radius: 3px; border: none; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal { border-radius: 3px; }
QScrollBar::add-line:vertical,   QScrollBar::sub-line:vertical   { height: 0; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:  0; }
QLineEdit   { border-radius: 8px; padding: 8px 12px; }
QPushButton {
    border-radius: 8px; padding: 7px 16px; font-weight: 600;
    border: 1px solid rgba(128,128,128,0.35);
}
QPushButton:hover  { border-color: rgba(128,128,128,0.6); }
QPushButton:pressed { border-color: rgba(128,128,128,0.8); }
QPushButton:default {
    border-color: palette(highlight);
    color: palette(highlight);
}
QPushButton:default:hover   { background: rgba(128,128,128,0.08); }
QPushButton:default:pressed { background: rgba(128,128,128,0.15); }
QPushButton#dangerButton {
    color: #e53935;
    border: 1px solid rgba(229,57,53,0.5);
    border-radius: 4px;
    padding: 4px 10px;
    background: transparent;
}
QPushButton#dangerButton:hover { background: rgba(229,57,53,0.08); }
QPushButton#dangerButton:pressed { background: rgba(229,57,53,0.15); }

QPushButton[danger="true"] {
    border-color: #c0392b; color: #c0392b;
}
QPushButton[danger="true"]:hover   { background: rgba(192,57,43,0.08); }
QToolButton {
    border-radius: 8px; padding: 7px 10px; font-weight: 600;
    border: 1px solid rgba(128,128,128,0.35);
}
QToolButton:hover  { border-color: rgba(128,128,128,0.6); }
QToolButton:pressed { border-color: rgba(128,128,128,0.8); }
QTextEdit   { border-radius: 8px; padding: 10px;
              font-family: 'Hack', 'Source Code Pro', 'Monospace', monospace;
              font-size: 11px; }
QFrame#card { border-radius: 12px; }
QPushButton#navbtn {
    border: none; border-radius: 8px;
    text-align: left; padding: 9px 12px;
    font-size: 13px; font-weight: 500;
    background: transparent;
}
"""
