"""Background job runner.

All GitHub work happens on one worker thread pulling from a queue. Serialising
it matters: two backups racing on the same branch would fight over the ref, and
the retry-on-conflict path in SyncEngine is meant for *other machines*, not for
this app competing with itself.
"""

from __future__ import annotations

import queue
import threading
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal


@dataclass
class Job:
    kind: str  # "backup" | "restore" | "connect" | "history" | custom
    label: str
    fn: Callable[..., Any]
    slug: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


class _Stop:
    """Sentinel that ends the worker loop."""


class JobRunner(QThread):
    """Serialised background queue; all signals arrive on the GUI thread."""

    job_started = Signal(object)  # Job
    job_progress = Signal(object, int, str)  # Job, percent, text
    job_finished = Signal(object, object)  # Job, result
    job_failed = Signal(object, str)  # Job, message
    went_idle = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._queue: "queue.Queue[Job | _Stop]" = queue.Queue()
        self._lock = threading.Lock()
        self._pending: set[str] = set()

    # ---- public API (GUI thread) ----------------------------------------

    def submit(self, job: Job, dedupe_key: str | None = None) -> bool:
        """Queue a job. With a dedupe key, a duplicate already queued is dropped."""
        if dedupe_key:
            with self._lock:
                if dedupe_key in self._pending:
                    return False
                self._pending.add(dedupe_key)
            job.meta["_dedupe"] = dedupe_key
        self._queue.put(job)
        return True

    def is_queued(self, dedupe_key: str) -> bool:
        with self._lock:
            return dedupe_key in self._pending

    def pending_count(self) -> int:
        return self._queue.qsize()

    def shutdown(self, wait_ms: int = 5000) -> None:
        self._queue.put(_Stop())
        if not self.wait(wait_ms):
            self.terminate()
            self.wait(500)

    # ---- worker thread ---------------------------------------------------

    def run(self) -> None:
        while True:
            item = self._queue.get()
            if isinstance(item, _Stop):
                return

            job = item
            key = job.meta.pop("_dedupe", None)
            if key:
                with self._lock:
                    self._pending.discard(key)

            self.job_started.emit(job)
            try:
                def report(pct: int, text: str, _job: Job = job) -> None:
                    self.job_progress.emit(_job, pct, text)

                result = job.fn(report)
            except Exception as exc:  # noqa: BLE001 - surfaced in the UI
                traceback.print_exc()
                self.job_failed.emit(job, str(exc) or exc.__class__.__name__)
            else:
                self.job_finished.emit(job, result)

            if self._queue.empty():
                self.went_idle.emit()
