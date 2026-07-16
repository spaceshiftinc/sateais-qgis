"""Shared lifecycle helpers for one-shot QThread workers.

Every one-shot worker in this plugin (submit, result fetch, connection test)
follows the same ownership pattern:

    1. The owning widget creates the worker with itself as the Qt parent.
    2. ``finished_signal`` carries the result back to the UI thread exactly once.
    3. On completion the owner disconnects its slot and lets ``deleteLater``
       collect the thread object.
    4. If the owner is destroyed while the worker is still running (plugin
       unload, dialog closed mid-request), the worker is *detached* instead of
       destroyed: a QThread whose C++ object dies while the OS thread runs
       makes Qt abort the whole process.
"""

from __future__ import annotations

from qgis.PyQt.QtCore import QThread

# Workers orphaned during teardown are parked here so their Python wrapper is
# not garbage-collected while the OS thread is still running. Each worker
# removes itself once its blocking call finally returns.
_DETACHED_WORKERS: set[QThread] = set()


def detach_worker(worker: QThread) -> None:
    """Orphan a still-running worker so its owner can be destroyed safely.

    Drops the Qt parent (so the owner's C++ destructor no longer owns and
    would-free the thread) and holds a strong module-level reference until the
    worker signals ``finished``, at which point it is safe to release and
    delete.
    """
    worker.setParent(None)
    _DETACHED_WORKERS.add(worker)
    worker.finished.connect(lambda: _DETACHED_WORKERS.discard(worker))
    worker.finished.connect(worker.deleteLater)
