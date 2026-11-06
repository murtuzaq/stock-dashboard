"""Run slow work (downloads) off the GUI thread and deliver the result back on it.

The toolkit supplies `post`, a function that runs a callable on the GUI thread. Tests supply an immediate one.
"""
import logging
import threading
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

Post = Callable[[Callable[[], None]], None]


class BackgroundLoader:
    def __init__(self, post: Post, threaded: bool = True) -> None:
        self._post = post
        self._threaded = threaded

    @classmethod
    def immediate(cls) -> 'BackgroundLoader':
        """Work and delivery both run on the calling thread, right away: for tests."""
        return cls(post=lambda call: call(), threaded=False)

    def run(self, work: Callable[[], Any], done: Callable[[Any], None],
            failed: Callable[[Exception], None] | None = None) -> None:
        """Call work() in the background, then done(result) on the GUI thread (or failed(error) if it raised)."""
        if self._threaded:
            threading.Thread(target=self._execute, args=(work, done, failed), daemon=True).start()
        else:
            self._execute(work, done, failed)

    def run_with_progress(self, work: Callable[[Callable[[Any], None]], Any], done: Callable[[Any], None],
                          failed: Callable[[Exception], None] | None = None,
                          progress: Callable[[Any], None] | None = None) -> None:
        """Like run, for long jobs: work(report) may call report(update) any number of times, and each update is
        delivered to progress(update) on the GUI thread, in order, before done(result)."""
        def report(update: Any) -> None:
            if progress is not None:
                self._post(lambda: progress(update))
        self.run(lambda: work(report), done, failed)

    def _execute(self, work, done, failed) -> None:
        try:
            result = work()
        except Exception as error:  # a download must never kill the thread silently and leave "Loading…" up
            log.exception('Background work failed')
            if failed is not None:
                self._post(lambda reason=error: failed(reason))  # `error` is unbound once this block ends
            return
        self._post(lambda: done(result))
