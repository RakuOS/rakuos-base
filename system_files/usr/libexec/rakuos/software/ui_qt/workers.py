"""
workers.py — Background thread workers for data fetching,
             streaming installs, and image loading.
"""

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage
import urllib.request


class Worker(QThread):
    """Run any callable in a background thread, emit result or error."""
    result = pyqtSignal(object)
    error  = pyqtSignal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs

    def run(self):
        try:
            self.result.emit(self.fn(*self.args, **self.kwargs))
        except Exception as e:
            self.error.emit(str(e))


class StreamWorker(QThread):
    """
    Run a generator function in a background thread.
    Emits each yielded line via `line`, then `done` with exit code.
    Generators should yield '__done__0' / '__done__1' to signal completion,
    or simply return (exit code 0 assumed).
    """
    line = pyqtSignal(str)
    done = pyqtSignal(int)

    def __init__(self, gen_fn, *args, **kwargs):
        super().__init__()
        self.gen_fn, self.args, self.kwargs = gen_fn, args, kwargs

    def run(self):
        try:
            for l in self.gen_fn(*self.args, **self.kwargs):
                if l.startswith("__done__"):
                    self.done.emit(int(l.replace("__done__", "") or "0"))
                    return
                self.line.emit(l)
            self.done.emit(0)
        except Exception as e:
            self.line.emit(f"Error: {e}")
            self.done.emit(1)


class ImageLoader(QThread):
    """Fetch a remote image URL and emit a QPixmap."""
    loaded = pyqtSignal(QPixmap, str)

    def __init__(self, url: str, key: str = ""):
        super().__init__()
        self.url, self.key = url, key

    def run(self):
        try:
            with urllib.request.urlopen(self.url, timeout=8) as r:
                data = r.read()
            img = QImage()
            img.loadFromData(data)
            self.loaded.emit(QPixmap.fromImage(img), self.key)
        except Exception:
            pass
