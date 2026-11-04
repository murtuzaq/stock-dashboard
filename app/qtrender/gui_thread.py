"""Bridge for core.background: run a callable on the GUI thread, from any thread."""
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from core.background import BackgroundLoader


class _Poster(QObject):
    _call = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._call.connect(lambda call: call())  # emitted from a worker thread, delivered on this object's thread

    def post(self, call: Callable[[], None]) -> None:
        self._call.emit(call)


def make_loader() -> BackgroundLoader:
    """A loader that delivers results on the GUI thread. Create it after the QApplication, on the GUI thread."""
    poster = _Poster()
    loader = BackgroundLoader(post=poster.post)
    loader._poster = poster  # keep the QObject alive as long as the loader
    return loader
