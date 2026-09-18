"""In-process background job runner.

Local development uses a queue + worker threads (no Redis/Celery required).
The interface (submit(fn, *args) -> job_id) is deliberately queue-like so a
production deployment can swap in SQS/Celery behind the same seam.
"""
from __future__ import annotations

import queue
import threading
import time
import traceback
import uuid
from collections import deque


class JobRunner:
    def __init__(self, n_workers: int = 2) -> None:
        self._q: queue.Queue = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()
        self._n = n_workers
        self.jobs: dict[str, dict] = {}
        self._log: deque = deque(maxlen=200)

    def start(self) -> None:
        for i in range(self._n):
            t = threading.Thread(target=self._work, name=f"nexus-job-{i}", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        for _ in self._threads:
            self._q.put(None)
        deadline = time.time() + timeout
        for t in self._threads:
            t.join(max(0.1, deadline - time.time()))

    def submit(self, fn, *args, **kwargs) -> str:
        job_id = uuid.uuid4().hex[:12]
        self.jobs[job_id] = {"status": "QUEUED", "created": time.time()}
        self._q.put((job_id, fn, args, kwargs))
        return job_id

    def _work(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                continue
            job_id, fn, args, kwargs = item
            self.jobs[job_id]["status"] = "RUNNING"
            try:
                fn(*args, **kwargs)
                self.jobs[job_id]["status"] = "DONE"
                self._log.append(f"{job_id} done")
            except Exception as e:  # noqa: BLE001 - job errors must not kill the worker
                self.jobs[job_id]["status"] = "ERROR"
                self.jobs[job_id]["error"] = f"{type(e).__name__}: {e}"
                self._log.append(f"{job_id} error: {e}")
                traceback.print_exc()


_runner: JobRunner | None = None


def get_runner() -> JobRunner:
    global _runner
    if _runner is None:
        from ..core.config import get_settings
        _runner = JobRunner(n_workers=get_settings().worker_threads)
    return _runner
