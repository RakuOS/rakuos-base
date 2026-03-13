"""
ui_qt/daemon.py — RakuOS Software Center background daemon.

Runs on a QTimer schedule, calls rakuos-update check commands,
emits signals for the tray and updates page.

Schedule options (minutes):
    0   = manual only
    360 = every 6 hours
    720 = every 12 hours
    1440 = daily (default)
    10080 = weekly
"""

import json
import subprocess
import os
from PyQt6.QtCore import QObject, QTimer, pyqtSignal


RAKUOS_UPDATE = "/usr/libexec/rakuos/rakuos-update"
SETTINGS_FILE = os.path.expanduser("~/.config/rakuos/software-settings.json")

DEFAULT_INTERVAL = 1440   # minutes — daily
MIN_INTERVAL     = 60     # never poll faster than hourly


def _load_settings() -> dict:
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _run_check(command: str) -> tuple[bool, list]:
    """Run rakuos-update <command>, return (success, parsed_updates_list)."""
    _debug = os.environ.get("RAKUOS_DEBUG")
    try:
        r = subprocess.run(
            [RAKUOS_UPDATE, command],
            capture_output=True, text=True, timeout=120
        )
        if _debug:
            print(f"[daemon] {command} exit={r.returncode} stdout={r.stdout[:200]!r}")
        # exit 0 = updates available, exit 1 = none, other = error
        if r.returncode not in (0, 1):
            return False, []
        data = json.loads(r.stdout)
        return r.returncode == 0, data.get("updates", [])
    except Exception as e:
        if _debug:
            print(f"[daemon] {command} error: {e}")
        return False, []


def _run_check_image() -> tuple[bool, dict]:
    """Run rakuos-update check-image, return (update_available, info_dict)."""
    _debug = os.environ.get("RAKUOS_DEBUG")
    try:
        r = subprocess.run(
            [RAKUOS_UPDATE, "check-image"],
            capture_output=True, text=True, timeout=120
        )
        if _debug:
            print(f"[daemon] check-image exit={r.returncode} "
                  f"stdout={r.stdout.strip()!r} "
                  f"stderr={r.stderr.strip()[-200:]!r}")
        data = json.loads(r.stdout)
        return r.returncode == 0, data
    except subprocess.TimeoutExpired:
        if _debug:
            print("[daemon] check-image TIMED OUT after 120s")
        return False, {}
    except Exception as e:
        if _debug:
            print(f"[daemon] check-image error: {e}")
        return False, {}


class UpdateDaemon(QObject):
    # Emitted when a check completes — carries combined update info
    updates_ready = pyqtSignal(dict)
    # Emitted to ask tray to show a desktop notification
    notify = pyqtSignal(str, str)   # title, body
    # Internal signal to reschedule timer on main thread
    _reschedule_signal = pyqtSignal()
    # Internal signal to deliver check result from worker thread to main thread
    _check_done_signal = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._run_checks)
        self._last_result: dict = {}
        self._running = False
        self._reschedule_signal.connect(self._reschedule)
        self._check_done_signal.connect(self._on_check_done)

    def start(self):
        """Start the daemon — runs an immediate check then schedules future ones."""
        self._reschedule()
        # Delay first check by 30s so app finishes loading first
        QTimer.singleShot(30_000, self._run_checks)

    def check_now(self):
        """Trigger an immediate check regardless of schedule."""
        if not self._running:
            QTimer.singleShot(0, self._run_checks)

    def _reschedule(self):
        """Read settings and set timer interval."""
        settings = _load_settings()
        interval_min = settings.get("update_interval", DEFAULT_INTERVAL)
        interval_min = max(interval_min, MIN_INTERVAL) if interval_min > 0 else 0

        self._timer.stop()
        if interval_min > 0:
            self._timer.start(interval_min * 60 * 1000)

    def _run_checks(self):
        if self._running:
            return
        self._running = True
        if os.environ.get("RAKUOS_DEBUG"):
            import datetime
            print(f"[daemon] Running update check at {datetime.datetime.now()}")

        from PyQt6.QtCore import QThread

        daemon_ref = self

        class _CheckThread(QThread):
            def run(self):
                settings = _load_settings()

                pkg_updates, fp_updates, img_info = [], [], {}
                img_available = False
                appimage_updates = []

                if settings.get("auto_check_packages", True):
                    _, pkg_updates = _run_check("check")

                if settings.get("auto_check_flatpak", True):
                    _, fp_updates = _run_check("check-flatpak")

                if settings.get("auto_check_image", True):
                    img_available, img_info = _run_check_image()

                # AppImage checks — userspace only, no sudo
                if settings.get("auto_check_appimages", True):
                    try:
                        from backend import appimages as _ai
                        appimage_updates = _ai.check_updates()
                        if os.environ.get("RAKUOS_DEBUG") and appimage_updates:
                            print(f"[daemon] appimage updates: {len(appimage_updates)}")
                    except Exception as e:
                        if os.environ.get("RAKUOS_DEBUG"):
                            print(f"[daemon] appimage check error: {e}")

                # Auto-update packages + flatpaks if enabled (never image)
                if settings.get("auto_update", False):
                    if pkg_updates:
                        subprocess.run(
                            [RAKUOS_UPDATE, "upgrade"],
                            capture_output=True, timeout=300)
                        _, pkg_updates = _run_check("check")
                    if fp_updates:
                        subprocess.run(
                            ["flatpak", "update", "-y", "--noninteractive"],
                            capture_output=True, timeout=300)
                        _, fp_updates = _run_check("check-flatpak")

                result = {
                    "packages":        pkg_updates,
                    "flatpak":         fp_updates,
                    "appimages":       appimage_updates,
                    "image_available": img_available,
                    "image_info":      img_info,
                    "total": len(pkg_updates) + len(fp_updates) +
                             len(appimage_updates) +
                             (1 if img_available else 0),
                }
                daemon_ref._check_done_signal.emit(result)

        t = _CheckThread(self)
        t.finished.connect(lambda: setattr(self, "_running", False))
        t.start()
        if not hasattr(self, "_threads"):
            self._threads = []
        self._threads.append(t)

    def _on_check_done(self, result: dict):
        self._last_result = result
        self.updates_ready.emit(result)
        # Reschedule via signal so timer is touched on main thread
        self._reschedule_signal.emit()

        total = result["total"]
        if total == 0:
            return

        # Build notification summary
        parts = []
        if result["packages"]:
            n = len(result["packages"])
            parts.append(f"{n} package update{'s' if n != 1 else ''}")
        if result["flatpak"]:
            n = len(result["flatpak"])
            parts.append(f"{n} Flatpak update{'s' if n != 1 else ''}")
        if result["image_available"]:
            info = result["image_info"]
            parts.append(f"System image {info.get('available', 'new version')} available")

        body = "\n".join(parts)
        self.notify.emit("Updates Available", body)

    def last_result(self) -> dict | None:
        return self._last_result if self._last_result else None
